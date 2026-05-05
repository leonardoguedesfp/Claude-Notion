"""Cliente HTTP pra API pública DataJud do CNJ.

Fase 1 da feature DataJUD: para cada CNJ, consulta o(s) endpoint(s)
correspondente(s) ao tribunal cadastrado e devolve a lista de
``_source`` (um por grau encontrado), ordenada por grau ascendente
(G1 < G2 < GS). Camadas superiores (``datajud_enricher``) decidem
quais endpoints chamar para cada processo e como mesclar os resultados.

Endpoint:
    POST https://api-publica.datajud.cnj.jus.br/api_publica_<endpoint>/_search

Body padrão (Elasticsearch query):
    {"query": {"match": {"numeroProcesso": "<20-digitos-sem-mascara>"}}, "size": 10}

API pública com autenticação via APIKey fixa (publicada pelo CNJ).
``size: 10`` permite múltiplos graus do mesmo CNJ em uma chamada;
raramente um CNJ tem > 3 documentos no mesmo endpoint.

Política de retry pra HTTP 429/503/timeout/erro de rede:
- 3 tentativas totais
- esperas de 2s e 8s entre elas (backoff exponencial truncado)
- 429 honra header ``Retry-After`` (cap em 60s)
- última falha → levanta ``DataJudAPIError`` /
  ``DataJudRateLimitError`` (NÃO silencia como o ``dje_client``,
  pois o caller — enricher — distingue erro vs lista vazia para
  classificar diagnóstico do processo).

HTTP 4xx ≠ 429 → levanta ``DataJudAPIError`` imediatamente
(sem retry — request mal formado, retry não vai consertar).

"0 hits" no payload **não** levanta exceção: retorna lista vazia
(``DataJudNotFoundError`` é declarado pra uso futuro de callers que
queiram converter "0 hits" em exceção, mas o método principal
``consultar`` não a usa).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Final

import requests

logger = logging.getLogger("datajud.client")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL: Final[str] = (
    "https://api-publica.datajud.cnj.jus.br/api_publica_{endpoint}/_search"
)
USER_AGENT: Final[str] = (
    "RicardoPassosAdvocacia-DataJUD/0.1 (leonardo@ricardopassos.adv.br)"
)
TIMEOUT_SECONDS: Final[float] = 30.0
RATE_LIMIT_SECONDS: Final[float] = 2.0
RETRY_BACKOFFS: Final[tuple[float, ...]] = (2.0, 8.0)
_RETRY_STATUS: Final[frozenset[int]] = frozenset({429, 503})
RETRY_AFTER_CAP_SECONDS: Final[float] = 60.0
DEFAULT_SIZE: Final[int] = 10

# APIKey pública do CNJ pra DataJud (padrão documentado).
# Override via env var DATAJUD_APIKEY (com ou sem prefixo "APIKey ").
DATAJUD_APIKEY_DEFAULT: Final[str] = (
    "APIKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
)
DATAJUD_APIKEY_ENV: Final[str] = "DATAJUD_APIKEY"


# Mapa Tribunal Notion → endpoint DataJud. STF não tem endpoint
# público; "Outro" fica fora intencionalmente — o enricher trata
# esses dois casos com diagnóstico específico.
TRIB_ENDPOINT: Final[dict[str, str]] = {
    "TJDFT": "tjdft",
    "TRT/10": "trt10",
    "TRT/2":  "trt2",
    "TST":    "tst",
    "STJ":    "stj",
    "TJSP":   "tjsp",
    "TJRJ":   "tjrj",
    "TJRS":   "tjrs",
    "TJBA":   "tjba",
    "TJMG":   "tjmg",
    "TJSC":   "tjsc",
    "TJPR":   "tjpr",
    "TJMS":   "tjms",
    "TJES":   "tjes",
    "TJGO":   "tjgo",
}

_VALID_ENDPOINTS: Final[frozenset[str]] = frozenset(TRIB_ENDPOINT.values())

# Ordem canônica de grau: G1 < G2 < GS. Outros valores caem no fim
# (ordenação defensiva — se a API trouxer um grau inesperado, não
# quebra; apenas vai pro final da lista).
_GRAU_ORDEM: Final[dict[str, int]] = {"G1": 0, "G2": 1, "GS": 2}
_GRAU_FALLBACK_RANK: Final[int] = 99


# ---------------------------------------------------------------------------
# Exceções
# ---------------------------------------------------------------------------


class DataJudAPIError(Exception):
    """Falha HTTP/4xx/5xx ou erro de rede após esgotar retries."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class DataJudRateLimitError(DataJudAPIError):
    """Rate limit (HTTP 429) persistente após esgotar retries."""


class DataJudNotFoundError(Exception):
    """Marker pra "processo não encontrado no endpoint consultado".

    O método ``consultar`` NÃO levanta esta exceção — ele retorna
    lista vazia para "0 hits". A classe existe pra callers que
    queiram converter "0 hits" em exceção (e.g. um helper de busca
    única que falha cedo).
    """


# ---------------------------------------------------------------------------
# Helpers públicos
# ---------------------------------------------------------------------------


def normalize_cnj(cnj: str) -> str:
    """Extrai os 20 dígitos do CNJ, ignorando máscara (pontos, hífen).

    Raises:
        ValueError: Se o CNJ não tiver exatamente 20 dígitos após
            remoção de máscara.

    Examples:
        >>> normalize_cnj("0000398-69.2021.5.10.0013")
        '00003986920215100013'
    """
    digits = "".join(ch for ch in str(cnj) if ch.isdigit())
    if len(digits) != 20:
        raise ValueError(
            f"CNJ deve ter 20 dígitos (com ou sem máscara); "
            f"recebido {len(digits)} em {cnj!r}",
        )
    return digits


def get_apikey(env: dict[str, str] | None = None) -> str:
    """Retorna o valor a usar no header ``Authorization``.

    Lê ``DATAJUD_APIKEY`` do environment; se ausente ou vazio,
    devolve ``DATAJUD_APIKEY_DEFAULT``. Se o valor do env não
    começar com ``"APIKey "``, prepende — o header sempre sai
    no formato ``Authorization: APIKey <token>``.

    Args:
        env: Dict alternativo (pra teste). Default = ``os.environ``.
    """
    src: dict[str, str] = dict(env) if env is not None else dict(os.environ)
    val = src.get(DATAJUD_APIKEY_ENV, "").strip()
    if not val:
        return DATAJUD_APIKEY_DEFAULT
    if val.startswith("APIKey "):
        return val
    return f"APIKey {val}"


def endpoint_de_tribunal(tribunal: str) -> str | None:
    """Retorna o endpoint DataJud para um Tribunal cadastrado no Notion.

    None quando o Tribunal é ``"Outro"``, vazio, ou não está no mapa
    (e.g. STF, que não tem endpoint público). O enricher consome
    isso pra decidir diagnóstico ``Tribunal não suportado``.
    """
    if not tribunal:
        return None
    return TRIB_ENDPOINT.get(tribunal.strip())


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------


class DataJudClient:
    """Cliente HTTP síncrono pra API pública DataJud do CNJ.

    Construtor aceita ``sleep`` e ``session`` injetáveis pra testes
    determinísticos (sem chamada real à API, sem espera real),
    espelhando ``DJEClient``.

    Args:
        sleep: Função de espera (default ``time.sleep``).
        session: ``requests.Session`` reutilizável (default cria nova).
        apikey: Override explícito do APIKey. Default lê via
            ``get_apikey()`` (env ``DATAJUD_APIKEY`` ou padrão).
    """

    def __init__(
        self,
        sleep: Callable[[float], None] | None = None,
        session: requests.Session | None = None,
        apikey: str | None = None,
    ) -> None:
        self._sleep: Callable[[float], None] = (
            sleep if sleep is not None else time.sleep
        )
        self._apikey: str = apikey if apikey is not None else get_apikey()
        if session is None:
            session = requests.Session()
        session.headers.update(
            {
                "User-Agent":    USER_AGENT,
                "Authorization": self._apikey,
                "Content-Type":  "application/json",
            },
        )
        self._session: requests.Session = session
        self._min_interval: float = RATE_LIMIT_SECONDS
        self._last_call: float = 0.0

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def consultar(
        self,
        numero_cnj: str,
        endpoint: str,
        *,
        size: int = DEFAULT_SIZE,
    ) -> list[dict[str, Any]]:
        """Consulta um CNJ num endpoint específico do DataJud.

        Args:
            numero_cnj: CNJ com ou sem máscara. Normalizado pra 20
                dígitos antes do envio.
            endpoint: Slug do endpoint (e.g. ``"trt10"``, ``"tjdft"``).
                Validado contra ``TRIB_ENDPOINT.values()``.
            size: Tamanho da query Elasticsearch (default 10 — cobre
                G1, G2, GS sobrando margem).

        Returns:
            Lista de ``_source`` dos hits, ordenada por grau
            ascendente (G1 < G2 < GS). Lista vazia quando o
            processo não tem registro no endpoint (não levanta).

        Raises:
            ValueError: Endpoint desconhecido ou CNJ malformado.
            DataJudRateLimitError: HTTP 429 persistente após retries.
            DataJudAPIError: Outros 4xx/5xx, JSON inválido, ou erro
                de rede após esgotar retries.
        """
        if endpoint not in _VALID_ENDPOINTS:
            raise ValueError(
                f"Endpoint desconhecido: {endpoint!r}. "
                f"Suportados: {sorted(_VALID_ENDPOINTS)}",
            )
        digits = normalize_cnj(numero_cnj)
        url = BASE_URL.format(endpoint=endpoint)
        body: dict[str, Any] = {
            "query": {"match": {"numeroProcesso": digits}},
            "size":  size,
        }
        return self._post_with_retry(url, body, endpoint=endpoint)

    def consultar_multi(
        self,
        numero_cnj: str,
        endpoints: list[str],
        *,
        size: int = DEFAULT_SIZE,
    ) -> dict[str, list[dict[str, Any]]]:
        """Consulta o mesmo CNJ em N endpoints, devolve dict
        ``endpoint → list[_source]``.

        Endpoints com 0 hits aparecem com lista vazia. Endpoints
        duplicados na entrada são deduplicados preservando a primeira
        ocorrência (e.g. ``["trt10", "tst", "tst"]`` → 2 chamadas).

        Esta é a porta de entrada do ``datajud_enricher``: ele decide
        a lista de endpoints (via ``endpoints_candidatos``), passa
        para cá, e foca em mesclar resultados — toda a orquestração
        HTTP (throttle, retry, exceções) fica no cliente.

        Erros de qualquer endpoint propagam (``DataJudAPIError`` /
        ``DataJudRateLimitError``) — caller decide como classificar
        diagnóstico do processo. Não silencia falhas parciais.
        """
        seen: set[str] = set()
        result: dict[str, list[dict[str, Any]]] = {}
        for ep in endpoints:
            if ep in seen:
                continue
            seen.add(ep)
            result[ep] = self.consultar(numero_cnj, ep, size=size)
        return result

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Aguarda o intervalo mínimo entre chamadas (rate limit por
        instância). Usa ``time.monotonic()`` real pra medir; ``self._sleep``
        injetável para testes."""
        now = time.monotonic()
        elapsed = now - self._last_call
        wait = self._min_interval - elapsed
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.monotonic()

    def _post_with_retry(
        self,
        url: str,
        body: dict[str, Any],
        *,
        endpoint: str,
    ) -> list[dict[str, Any]]:
        """POST com retry pra status transientes (429/503/erro de rede).

        Após esgotar retries, levanta ``DataJudRateLimitError`` (429) ou
        ``DataJudAPIError`` (outros). 4xx ≠ 429 não retry — levanta
        imediatamente.
        """
        attempts = 1 + len(RETRY_BACKOFFS)  # 3 totais
        last_status: int = 0
        last_error: str = ""
        for attempt in range(1, attempts + 1):
            self._throttle()
            try:
                response = self._session.post(
                    url, json=body, timeout=TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                last_error = f"erro de rede: {exc}"
                logger.warning(
                    "DataJUD: %s — tentativa %d/%d falhou (rede): %s",
                    endpoint, attempt, attempts, exc,
                )
                if attempt < attempts:
                    self._sleep(RETRY_BACKOFFS[attempt - 1])
                    continue
                raise DataJudAPIError(0, last_error) from exc

            status = response.status_code
            if status == 200:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise DataJudAPIError(
                        status, f"JSON inválido: {exc}",
                    ) from exc
                return _extract_sources(payload)

            if status in _RETRY_STATUS:
                last_status = status
                last_error = f"HTTP {status}"
                logger.warning(
                    "DataJUD: %s — tentativa %d/%d retornou %d",
                    endpoint, attempt, attempts, status,
                )
                if attempt < attempts:
                    backoff = RETRY_BACKOFFS[attempt - 1]
                    if status == 429:
                        backoff = _resolve_retry_after_seconds(
                            response, fallback=backoff,
                        )
                    self._sleep(backoff)
                    continue
                # Esgotou retries em status retryable
                if status == 429:
                    raise DataJudRateLimitError(
                        status,
                        f"Rate limit em {endpoint} após {attempts} tentativas",
                    )
                raise DataJudAPIError(
                    status,
                    f"HTTP {status} persistente em {endpoint} "
                    f"após {attempts} tentativas",
                )

            # 4xx ≠ 429 e outros — não retryable.
            try:
                body_preview = (response.text or "")[:300]
            except Exception:  # noqa: BLE001
                body_preview = ""
            logger.warning(
                "DataJUD: %s — HTTP %d não-retryable: %s",
                endpoint, status, body_preview,
            )
            raise DataJudAPIError(status, body_preview or f"HTTP {status}")

        # Inalcançável (todos os caminhos do loop ou retornam ou
        # levantam). Defensivo pra mypy strict não reclamar.
        raise DataJudAPIError(
            last_status,
            last_error or "loop de retry finalizou sem resposta válida",
        )


# ---------------------------------------------------------------------------
# Helpers de payload
# ---------------------------------------------------------------------------


def _extract_sources(payload: Any) -> list[dict[str, Any]]:
    """Extrai ``_source`` de cada hit do payload Elasticsearch e ordena
    por grau ascendente (G1 < G2 < GS).

    Defensivo contra variações de schema (payload não-dict, ``hits``
    ausente, hits sem ``_source``, etc.) — devolve lista vazia ao
    invés de quebrar.
    """
    if not isinstance(payload, dict):
        return []
    hits_block = payload.get("hits")
    if not isinstance(hits_block, dict):
        return []
    hits_list = hits_block.get("hits")
    if not isinstance(hits_list, list):
        return []
    sources: list[dict[str, Any]] = []
    for h in hits_list:
        if not isinstance(h, dict):
            continue
        src = h.get("_source")
        if isinstance(src, dict):
            sources.append(src)
    sources.sort(
        key=lambda s: _GRAU_ORDEM.get(
            str(s.get("grau", "")), _GRAU_FALLBACK_RANK,
        ),
    )
    return sources


def _resolve_retry_after_seconds(
    response: Any, fallback: float,
) -> float:
    """Lê o header ``Retry-After`` de uma resposta 429 e devolve a
    espera em segundos. Espelha ``dje_client._resolve_retry_after_seconds``
    (mesma política: aceita inteiro ≥ 0, capa em ``RETRY_AFTER_CAP_SECONDS``,
    valores negativos/HTTP-date/string solta caem no fallback).
    """
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("Retry-After")
    if raw is None:
        return fallback
    raw_str = str(raw).strip()
    if not raw_str:
        return fallback
    try:
        seconds_int = int(raw_str)
    except ValueError:
        logger.warning(
            "DataJUD: Retry-After=%r formato não suportado, fallback %.1fs",
            raw, fallback,
        )
        return fallback
    if seconds_int < 0:
        logger.warning(
            "DataJUD: Retry-After=%ds inválido (negativo), fallback %.1fs",
            seconds_int, fallback,
        )
        return fallback
    seconds = float(seconds_int)
    if seconds > RETRY_AFTER_CAP_SECONDS:
        logger.warning(
            "DataJUD: Retry-After=%ds recebido, capando em %.0fs",
            seconds_int, RETRY_AFTER_CAP_SECONDS,
        )
        return RETRY_AFTER_CAP_SECONDS
    return seconds
