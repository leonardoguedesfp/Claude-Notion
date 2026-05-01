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
from datetime import date
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
RATE_LIMIT_SECONDS: float = 1.0  # entre TODAS as requisições

# 3 tentativas totais, 2 esperas entre elas (2s e 8s).
RETRY_BACKOFFS: tuple[float, ...] = (2.0, 8.0)

# Status HTTP que disparam retry (transientes).
_RETRY_STATUS: frozenset[int] = frozenset({429, 503})


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
    """Resultado agregado de uma varredura (todos os advogados)."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    by_advogado: list[AdvogadoResult] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        return len(self.rows)

    @property
    def errors(self) -> list[AdvogadoResult]:
        return [r for r in self.by_advogado if r.erro is not None]


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
    ) -> AdvogadoResult:
        """Pagina e coleta TODAS as publicações de um único advogado
        no intervalo. Cada item retornado vira dict do JSON da API com
        ``advogado_consultado`` injetado (formato ``"Nome (OAB/UF)"``).

        Aplica rate limit de 1 req/s ENTRE páginas via ``self._sleep``.

        Falha persistente (após retries) NÃO levanta — popula
        ``result.erro`` com a mensagem e retorna o que já tinha
        coletado em páginas anteriores. Caller decide se segue.
        """
        result = AdvogadoResult(advogado=advogado)
        label = format_advogado_label(advogado)
        pagina = 1
        while True:
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
    ) -> FetchSummary:
        """Itera sobre todos os advogados sequencialmente, aplicando
        rate limit entre advogados também. Acumula em ``FetchSummary``.

        ``on_progress(idx, total, result)`` é chamado após cada
        advogado concluir (sucesso ou erro persistente) — UI usa pra
        atualizar barra de progresso e log.

        Erros em advogados individuais NÃO abortam a varredura
        (registrados em ``summary.errors`` e seguem).
        """
        summary = FetchSummary()
        total = len(advogados)
        for idx, adv in enumerate(advogados, start=1):
            if idx > 1:
                # Rate limit entre advogados.
                self._sleep(RATE_LIMIT_SECONDS)
            result = self.fetch_advogado(adv, data_inicio, data_fim)
            summary.by_advogado.append(result)
            summary.rows.extend(result.items)
            if on_progress is not None:
                try:
                    on_progress(idx, total, result)
                except Exception:  # noqa: BLE001
                    # Callback faulty não pode derrubar a varredura.
                    logger.exception("DJE: on_progress raised")
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
                    self._sleep(RETRY_BACKOFFS[attempt - 1])
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
