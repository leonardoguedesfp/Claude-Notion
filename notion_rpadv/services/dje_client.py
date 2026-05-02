"""Cliente HTTP pra API pública do DJEN (Diário de Justiça Eletrônico Nacional).

Fase 1 do Leitor DJE: para cada advogado do escritório (`dje_advogados`),
faz GET paginado em ``/api/v1/comunicacao`` por intervalo de datas, agrega
todos os items em uma lista única, anota cada item com ``advogado_consultado``
(formato ``"Nome (OAB/UF)"``) — depois o ``dje_exporter`` empilha tudo num
xlsx.

Endpoint:
    GET https://comunicaapi.pje.jus.br/api/v1/comunicacao

API pública (sem auth) com rate limit empírico ~1 req/s. Aplicamos sleep
entre TODAS as requisições (paginação inclusive) pra não estourar.

Política de retry pra HTTP 429/503/timeout/erro de rede:
- 3 tentativas totais
- esperas de 2s e 8s entre elas (backoff exponencial truncado)
- última falha → registra no logger e segue pro próximo advogado
  (varredura inteira não aborta).

HTTP 4xx ≠ 429 → registra corpo da resposta e segue (sem retry — request
mal formado, retry não vai consertar).

Idempotência: a coluna ``hash`` retornada pela API é a chave única
estável das publicações. Fase 2 vai deduplicar via ``hash``; nesta fase
deixamos linhas duplicadas (litisconsórcio interno do escritório → mesma
publicação aparece N vezes, uma por advogado consultado — comportamento
esperado).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

import requests

from notion_rpadv.services.dje_advogados import Advogado, format_advogado_label

logger = logging.getLogger("dje.client")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL: str = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
USER_AGENT: str = (
    "RicardoPassosAdvocacia-LeitorDJE/0.1 (leonardo@ricardopassos.adv.br)"
)
TIMEOUT_SECONDS: float = 15.0
PAGE_SIZE: int = 100
# Pausa entre TODAS as requisições. Fase 2.1 (2026-05-01): 1.0 → 2.0
# após smoke real em janela longa (01/01→30/04/2026) gerar 429
# catastrófico em 7 de 12 advogados.
RATE_LIMIT_SECONDS: float = 2.0

# 3 tentativas totais, 2 esperas entre elas (2s e 8s).
RETRY_BACKOFFS: tuple[float, ...] = (2.0, 8.0)

# Status HTTP que disparam retry (transientes).
_RETRY_STATUS: frozenset[int] = frozenset({429, 503})

# Cap superior pro header ``Retry-After``. Servidor que pede uma espera
# absurda (e.g. 600s) não trava o thread por minutos — capamos em 60s
# e logamos. 60s (e não 30s) pra reduzir risco de cair no mesmo 429.
RETRY_AFTER_CAP_SECONDS: float = 60.0

# Fase 2.2 — Split de janela longa em sub-janelas calendar-aligned.
# Threshold > 31 dias dispara o split. Mantém 1 sub-janela por mês,
# alinhada ao calendário. Hipótese: paginação profunda no backend é
# o trigger principal do 429 cascade observado em janelas de 4 meses.
WINDOW_SPLIT_THRESHOLD_DAYS: int = 31

# Fase 2.2 — Pausa entre requests do retry diferido. Após varredura
# inicial, advogados que falharam são retentados UMA vez com pausa maior
# pra dar tempo do backend recuperar bucket de rate limit.
RETRY_DEFERRED_PAUSE_SECONDS: float = 30.0


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------


@dataclass
class AdvogadoResult:
    """Resultado por advogado: items coletados + meta de execução."""

    advogado: Advogado
    items: list[dict[str, Any]] = field(default_factory=list)
    paginas: int = 0
    erro: str | None = None  # None = sucesso, string = mensagem de falha


@dataclass
class FetchSummary:
    """Resultado agregado de uma varredura (todos os advogados).

    Fase 2.2: ganha ``cancelled`` (varredura interrompida pelo usuário
    via cancel button) — quando True, ``rows`` contém só os items
    coletados até o checkpoint do cancelamento.
    """

    rows: list[dict[str, Any]] = field(default_factory=list)
    by_advogado: list[AdvogadoResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def total_items(self) -> int:
        return len(self.rows)

    @property
    def errors(self) -> list[AdvogadoResult]:
        return [r for r in self.by_advogado if r.erro is not None]


# ---------------------------------------------------------------------------
# Helpers de janela (Fase 2.2)
# ---------------------------------------------------------------------------


def _split_window_monthly(
    data_inicio: date,
    data_fim: date,
    threshold_days: int = WINDOW_SPLIT_THRESHOLD_DAYS,
) -> list[tuple[date, date]]:
    """Divide uma janela em sub-janelas calendar-aligned (1 por mês).

    Retorna lista de tuplas ``(sub_inicio, sub_fim)`` ordenadas
    cronologicamente, cobrindo o intervalo ``[data_inicio, data_fim]``
    SEM gaps e SEM overlaps.

    - **Janela ≤ ``threshold_days``** → retorna ``[(data_inicio, data_fim)]``
      (não splita; mantém comportamento da Fase 2.1).
    - **Janela > ``threshold_days``** → splita por mês calendário:
      sub-janela 1 vai de ``data_inicio`` até o último dia do mês de
      ``data_inicio``; sub-janela 2 vai do dia 1 do mês seguinte até o
      último dia desse mês; ...; sub-janela última vai do dia 1 do mês
      de ``data_fim`` até ``data_fim``.

    Decisão de design: split mensal calendar-aligned (não 31 dias
    fixos) é mais legível pro operador no log ("jan/26, fev/26, ...")
    e também mais determinístico (mesma janela sempre divide igual).

    Casos de borda:
    - Mesmo mês com janela > 31 dias → impossível (mês tem ≤ 31 dias),
      cai no caminho ``≤ threshold``.
    - Janela atravessando ano (15/12/25 → 15/02/26) → 3 sub-janelas
      (dez/25, jan/26, fev/26).
    - ``data_inicio`` no dia 1 / ``data_fim`` no último dia do mês →
      sub-janelas têm fronteiras "inteiras".
    """
    delta = (data_fim - data_inicio).days
    if delta <= threshold_days:
        return [(data_inicio, data_fim)]

    sub_windows: list[tuple[date, date]] = []
    cursor = data_inicio
    while cursor <= data_fim:
        # Último dia do mês de ``cursor``: vai pro dia 28 do PRÓXIMO mês,
        # subtrai 1 dia até virar o último dia do mês atual. Truque
        # padrão pra evitar lidar com meses de 28/29/30/31 explicitamente.
        if cursor.month == 12:
            first_of_next = date(cursor.year + 1, 1, 1)
        else:
            first_of_next = date(cursor.year, cursor.month + 1, 1)
        last_of_month = first_of_next - timedelta(days=1)
        sub_end = min(last_of_month, data_fim)
        sub_windows.append((cursor, sub_end))
        cursor = sub_end + timedelta(days=1)
    return sub_windows


# ---------------------------------------------------------------------------
# Construção de query
# ---------------------------------------------------------------------------


def build_query_params(
    oab: str,
    uf: str,
    data_inicio: date,
    data_fim: date,
    pagina: int,
    itens_por_pagina: int = PAGE_SIZE,
) -> dict[str, str]:
    """Constrói o dict de query params pra um GET no DJEN.

    Não passa ``siglaTribunal`` (queremos publicações de qualquer
    tribunal nacional) nem ``nomeAdvogado`` (matching parcial e
    sensível a acentos — OAB é a chave canônica).

    ``oab`` é normalizada pra dígitos puros (sem ponto, espaço, hífen)
    antes de envio — defesa contra entrada com formato BR.
    """
    digits_only = "".join(ch for ch in str(oab) if ch.isdigit())
    return {
        "numeroOab":                  digits_only,
        "ufOab":                      uf.upper(),
        "dataDisponibilizacaoInicio": data_inicio.isoformat(),
        "dataDisponibilizacaoFim":    data_fim.isoformat(),
        "itensPorPagina":             str(itens_por_pagina),
        "pagina":                     str(pagina),
    }


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------


class DJEClientError(Exception):
    """Falha persistente em uma requisição (após esgotar retries)."""


class DJEClient:
    """Cliente HTTP pro DJEN. Síncrono, single-threaded.

    Construtor aceita ``sleep`` e ``session`` injetáveis pra testes
    determinísticos (sem chamada real à API, sem espera real)."""

    def __init__(
        self,
        sleep: Callable[[float], None] | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self._sleep = sleep if sleep is not None else time.sleep
        if session is None:
            session = requests.Session()
            session.headers.update({"User-Agent": USER_AGENT})
        self._session = session

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def fetch_advogado(
        self,
        advogado: Advogado,
        data_inicio: date,
        data_fim: date,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> AdvogadoResult:
        """Pagina e coleta TODAS as publicações de um único advogado
        no intervalo. Cada item retornado vira dict do JSON da API com
        ``advogado_consultado`` injetado (formato ``"Nome (OAB/UF)"``).

        Aplica rate limit de 1 req/s ENTRE páginas via ``self._sleep``.

        Falha persistente (após retries) NÃO levanta — popula
        ``result.erro`` com a mensagem e retorna o que já tinha
        coletado em páginas anteriores. Caller decide se segue.

        **Fase 2.2 — cancelamento:** ``is_cancelled`` é uma callable
        opcional que, se retornar True, faz a paginação parar entre
        páginas (não no meio de retry HTTP). Items já coletados em
        páginas anteriores são preservados; ``result.erro`` permanece
        None — não é "erro", é cancelamento. Caller distingue via
        ``summary.cancelled`` no FetchSummary agregador.
        """
        result = AdvogadoResult(advogado=advogado)
        label = format_advogado_label(advogado)
        pagina = 1
        while True:
            # Checkpoint de cancelamento ENTRE páginas (não no meio de
            # uma request HTTP em retry — ver spec do user da Fase 2.2).
            if is_cancelled is not None and is_cancelled():
                logger.info(
                    "DJE: %s — cancelamento detectado antes da pag %d "
                    "(parcial: %d publicações em %d página(s))",
                    label, pagina, len(result.items), result.paginas,
                )
                return result
            if pagina > 1:
                # Rate limit entre páginas do mesmo advogado.
                self._sleep(RATE_LIMIT_SECONDS)
            params = build_query_params(
                advogado["oab"], advogado["uf"],
                data_inicio, data_fim, pagina,
            )
            try:
                items = self._fetch_page_with_retry(params)
            except DJEClientError as exc:
                result.erro = str(exc)
                logger.warning(
                    "DJE: falha persistente em %s pagina=%d: %s",
                    label, pagina, exc,
                )
                return result
            result.paginas = pagina
            for it in items:
                # Anotação obrigatória: identifica de qual advogado do
                # escritório veio o resultado (mesma publicação pode
                # aparecer em N advogados em caso de litisconsórcio).
                annotated = {"advogado_consultado": label, **it}
                result.items.append(annotated)
            # Última página: API retorna lista menor que PAGE_SIZE
            # (ou vazia). Não tem total/has_more no payload — page-size
            # check é a heurística canônica.
            if len(items) < PAGE_SIZE:
                break
            pagina += 1
        logger.info(
            "DJE: %s — %d publicações em %d página(s)",
            label, len(result.items), result.paginas,
        )
        return result

    def fetch_all(
        self,
        advogados: list[Advogado],
        data_inicio: date,
        data_fim: date,
        on_progress: Callable[[int, int, AdvogadoResult], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> FetchSummary:
        """Itera sobre todos os advogados sequencialmente, aplicando
        rate limit entre cada chamada HTTP. Acumula em ``FetchSummary``.

        ``on_progress(idx, total, result)`` é chamado após cada
        advogado concluir TODAS as suas sub-janelas (sucesso ou erro
        persistente em pelo menos uma sub-janela) — UI usa pra
        atualizar barra de progresso e log.

        Erros em advogados individuais NÃO abortam a varredura
        (registrados em ``summary.errors`` e seguem).

        **Fase 2.2 — split de janela longa em sub-janelas mensais:**
        Janelas > ``WINDOW_SPLIT_THRESHOLD_DAYS`` (default 31) são
        divididas em sub-janelas calendar-aligned (jan/26, fev/26, ...)
        pra reduzir paginação profunda no backend. Cada sub-janela é
        consultada independentemente; items são agregados em uma única
        ``AdvogadoResult`` por advogado.

        **Fase 2.2 — retry diferido:** após a varredura principal, se
        algum advogado teve falha persistente em alguma sub-janela
        E a janela original foi splitada (>31 dias), reagendamos UMA
        rodada adicional só nas sub-janelas que falharam, com pausa de
        ``RETRY_DEFERRED_PAUSE_SECONDS`` (30s) entre cada — dá tempo
        do backend recuperar bucket de rate limit. Se o retry
        recuperar todas as falhas de um advogado, ``erro`` é limpo;
        caso contrário, mantém como falha definitiva.

        Retry diferido NÃO dispara em janelas curtas (≤ 31 dias) —
        nessas, falha persistente é registrada e segue, comportamento
        Fase 2.1 preservado. Decisão: H1 do diagnóstico Fase 2.2
        identifica paginação profunda como trigger principal do 429
        cascade; janelas curtas raramente atingem profundidade
        problemática.

        **Fase 2.2 — cancelamento:** ``is_cancelled`` é uma callable
        opcional checada nos checkpoints (entre advogados, entre
        sub-janelas e — via propagação ao ``fetch_advogado`` — entre
        páginas). Quando True, varredura para de forma limpa,
        ``summary.cancelled = True``, e items já coletados são
        preservados pra exporter parcial. Cancelamento NÃO interrompe
        request HTTP em retry.
        """
        summary = FetchSummary()
        sub_windows = _split_window_monthly(data_inicio, data_fim)
        if len(sub_windows) > 1:
            labels = [di.strftime("%b/%y") for di, _ in sub_windows]
            logger.info(
                "DJE: janela > %d dias dividida em %d sub-janelas: %s",
                WINDOW_SPLIT_THRESHOLD_DAYS, len(sub_windows),
                ", ".join(labels),
            )

        total = len(advogados)
        # Um AdvogadoResult agregado por advogado (acumula items de
        # todas as sub-janelas).
        aggs: list[AdvogadoResult] = [
            AdvogadoResult(advogado=a) for a in advogados
        ]
        # Sub-janelas que falharam, indexadas por advogado.
        failed_per_adv: list[set[int]] = [set() for _ in advogados]
        first_request = True

        # Varredura principal: cada advogado em todas as sub-janelas.
        for adv_idx, adv in enumerate(advogados):
            # Checkpoint de cancelamento ANTES de iniciar próximo advogado.
            if is_cancelled is not None and is_cancelled():
                summary.cancelled = True
                break
            for sub_idx, (sub_di, sub_df) in enumerate(sub_windows):
                # Checkpoint de cancelamento ANTES de iniciar próxima
                # sub-janela do mesmo advogado.
                if is_cancelled is not None and is_cancelled():
                    summary.cancelled = True
                    break
                if not first_request:
                    self._sleep(RATE_LIMIT_SECONDS)
                first_request = False
                sub_result = self.fetch_advogado(
                    adv, sub_di, sub_df, is_cancelled=is_cancelled,
                )
                aggs[adv_idx].items.extend(sub_result.items)
                aggs[adv_idx].paginas += sub_result.paginas
                if sub_result.erro is not None:
                    failed_per_adv[adv_idx].add(sub_idx)
                    aggs[adv_idx].erro = sub_result.erro
                # Cancelamento detectado DENTRO de fetch_advogado precisa
                # ser propagado pra summary.cancelled aqui — fetch_advogado
                # não tem como sinalizar cancel via AdvogadoResult.
                if is_cancelled is not None and is_cancelled():
                    summary.cancelled = True
                    break
            if on_progress is not None:
                try:
                    on_progress(adv_idx + 1, total, aggs[adv_idx])
                except Exception:  # noqa: BLE001
                    # Callback faulty não pode derrubar a varredura.
                    logger.exception("DJE: on_progress raised")
            # Pós-iteração interna: se cancelado, sai do outer loop tb.
            if summary.cancelled:
                break

        # Retry diferido: só dispara em janelas splitadas E não cancelado.
        if (
            len(sub_windows) > 1
            and any(failed_per_adv)
            and not summary.cancelled
        ):
            n_failed = sum(len(f) for f in failed_per_adv)
            logger.info(
                "DJE: %d sub-janela(s) falharam → retry diferido com "
                "pausa de %.0fs entre cada",
                n_failed, RETRY_DEFERRED_PAUSE_SECONDS,
            )
            for adv_idx, fails in enumerate(failed_per_adv):
                for sub_idx in sorted(fails):
                    if is_cancelled is not None and is_cancelled():
                        summary.cancelled = True
                        break
                    self._sleep(RETRY_DEFERRED_PAUSE_SECONDS)
                    sub_di, sub_df = sub_windows[sub_idx]
                    sub_result = self.fetch_advogado(
                        advogados[adv_idx], sub_di, sub_df,
                        is_cancelled=is_cancelled,
                    )
                    if sub_result.erro is None:
                        aggs[adv_idx].items.extend(sub_result.items)
                        aggs[adv_idx].paginas += sub_result.paginas
                        failed_per_adv[adv_idx].discard(sub_idx)
                if summary.cancelled:
                    break
            # Após retry: se TODAS as falhas de um advogado foram
            # recuperadas, limpa o erro do agregado. Senão, mantém.
            for adv_idx in range(len(advogados)):
                if not failed_per_adv[adv_idx]:
                    aggs[adv_idx].erro = None

        # Popular summary a partir dos agregados.
        for agg in aggs:
            summary.by_advogado.append(agg)
            summary.rows.extend(agg.items)

        return summary

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _fetch_page_with_retry(
        self, params: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Faz GET com retry pra status transientes (429/503/timeout/
        erro de rede). Na última falha, levanta DJEClientError com
        sumário do que aconteceu."""
        attempts = 1 + len(RETRY_BACKOFFS)  # 3 totais
        last_error: str = ""
        for attempt in range(1, attempts + 1):
            try:
                response = self._session.get(
                    BASE_URL, params=params, timeout=TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                last_error = f"network error: {exc}"
                logger.warning(
                    "DJE: tentativa %d/%d falhou (rede): %s",
                    attempt, attempts, exc,
                )
                if attempt < attempts:
                    self._sleep(RETRY_BACKOFFS[attempt - 1])
                    continue
                break
            status = response.status_code
            if status == 200:
                try:
                    payload = response.json()
                except ValueError as exc:
                    last_error = f"JSON inválido: {exc}"
                    logger.warning(
                        "DJE: tentativa %d/%d JSON inválido: %s",
                        attempt, attempts, exc,
                    )
                    # JSON inválido em 200 é raro — não retry; sai.
                    break
                return _extract_items(payload)
            if status in _RETRY_STATUS:
                last_error = f"HTTP {status}"
                logger.warning(
                    "DJE: tentativa %d/%d retornou %d",
                    attempt, attempts, status,
                )
                if attempt < attempts:
                    backoff = RETRY_BACKOFFS[attempt - 1]
                    # Fase 2.1: 429 com header ``Retry-After`` honrado
                    # quando inteiro (segundos). Formato HTTP-date da
                    # RFC 7231 NÃO suportado intencionalmente — cai no
                    # backoff atual. Cap superior em ``RETRY_AFTER_CAP_SECONDS``.
                    if status == 429:
                        backoff = _resolve_retry_after_seconds(
                            response, fallback=backoff,
                        )
                    self._sleep(backoff)
                    continue
                break
            # 4xx ≠ 429 → request mal formado; retry não consertaria.
            body_preview = (response.text or "")[:300]
            last_error = f"HTTP {status}: {body_preview}"
            logger.warning(
                "DJE: HTTP %d não-retryable: %s", status, body_preview,
            )
            break
        raise DJEClientError(last_error or "falha desconhecida")


# ---------------------------------------------------------------------------
# Helpers de payload
# ---------------------------------------------------------------------------


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    """A API DJEN retorna itens em ``items`` (dict) — defensivo contra
    variações de schema. Lista vazia quando não há nada."""
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def _resolve_retry_after_seconds(
    response: Any, fallback: float,
) -> float:
    """Lê o header ``Retry-After`` de uma resposta 429 e devolve a
    espera em segundos.

    Casos tratados (comportamento por categoria do valor):

    - **Ausente/vazio** → ``fallback`` (silencioso).
    - **Inteiro positivo** (``"5"``) → o valor, capado em
      ``RETRY_AFTER_CAP_SECONDS``.
    - **Zero** (``"0"``) → 0.0 (servidor liberou, não esperar).
    - **Inteiro negativo** (``"-39"``, ``"-57"``) → ``fallback``. Bug
      conhecido do DJEN observado no smoke da Fase 2.1: servidor envia
      valores negativos (provavelmente um delta-time mal-calculado que
      virou negativo). Log warning específico classifica como bug do
      servidor pra dar contexto ao operador.
    - **Outros formatos** (HTTP-date RFC 7231, string solta,
      ``"5.5"``) → ``fallback``. Suporte a HTTP-date NÃO implementado
      intencionalmente — DJEN historicamente só envia inteiro.

    Cap acima de ``RETRY_AFTER_CAP_SECONDS`` emite warning e usa o cap.
    """
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("Retry-After")
    if raw is None:
        return fallback
    raw_str = str(raw).strip()
    if not raw_str:
        return fallback
    # Detecta inteiro com sinal opcional. ``int()`` aceita ``"-39"``;
    # ``isdigit()`` não — usar try/except é mais limpo que regex.
    try:
        seconds_int = int(raw_str)
    except ValueError:
        logger.warning(
            "DJE: Retry-After=%r formato não suportado, usando fallback %.1fs",
            raw, fallback,
        )
        return fallback
    if seconds_int < 0:
        logger.warning(
            "DJE: Retry-After=%ds inválido (negativo, bug do servidor), "
            "usando fallback %.1fs",
            seconds_int, fallback,
        )
        return fallback
    seconds = float(seconds_int)
    if seconds > RETRY_AFTER_CAP_SECONDS:
        logger.warning(
            "DJE: Retry-After=%ds recebido, capando em %.0fs",
            seconds_int, RETRY_AFTER_CAP_SECONDS,
        )
        return RETRY_AFTER_CAP_SECONDS
    return seconds
