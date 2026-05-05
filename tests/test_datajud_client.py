"""Testes do ``notion_rpadv.services.datajud_client``: HTTP, retry/backoff,
APIKey, throttle, ordenação por grau.

Sem chamada à API real — todas as requisições mockadas via
``unittest.mock``. Sleep injetado pra eliminar espera real, espelhando
o pattern do ``test_dje_client``.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from notion_rpadv.services.datajud_client import (
    DATAJUD_APIKEY_DEFAULT,
    DATAJUD_APIKEY_ENV,
    RATE_LIMIT_SECONDS,
    RETRY_BACKOFFS,
    DataJudAPIError,
    DataJudClient,
    DataJudRateLimitError,
    endpoint_de_tribunal,
    get_apikey,
    normalize_cnj,
)


# ---------------------------------------------------------------------------
# Helpers de mock
# ---------------------------------------------------------------------------


def _mock_response(
    status: int = 200,
    json_payload: Any = None,
    headers: dict[str, str] | None = None,
    raise_json: bool = False,
) -> MagicMock:
    """Constrói um mock que parece com ``requests.Response``."""
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.text = ""
    if raise_json:
        resp.json.side_effect = ValueError("invalid JSON")
    else:
        resp.json.return_value = (
            json_payload if json_payload is not None else {}
        )
    return resp


def _make_session(side_effect: Any) -> MagicMock:
    session = MagicMock()
    session.headers = {}
    if isinstance(side_effect, list):
        session.post.side_effect = side_effect
    else:
        session.post.side_effect = side_effect
    return session


def _make_client(
    session: MagicMock | None = None,
    sleep: Any = None,
    apikey: str = "APIKey test",
) -> DataJudClient:
    if session is None:
        session = _make_session([_mock_response(200, {})])
    return DataJudClient(
        sleep=sleep if sleep is not None else (lambda _s: None),
        session=session,
        apikey=apikey,
    )


def _source_for_grau(grau: str, **extra: Any) -> dict[str, Any]:
    src: dict[str, Any] = {
        "numeroProcesso": "00003986920215100013",
        "tribunal":       "TRT10",
        "grau":           grau,
    }
    src.update(extra)
    return src


def _payload_es(*sources: dict[str, Any]) -> dict[str, Any]:
    """Constrói payload no formato Elasticsearch que o DataJud retorna."""
    return {
        "took":      1,
        "timed_out": False,
        "hits": {
            "total":    {"value": len(sources), "relation": "eq"},
            "max_score": 1.0,
            "hits": [
                {"_index": "api_publica_x", "_source": src} for src in sources
            ],
        },
    }


# ---------------------------------------------------------------------------
# 1) consultar() em CNJ existente — retorna lista de _source ordenada
# ---------------------------------------------------------------------------


def test_consultar_cnj_existente_retorna_lista() -> None:
    """200 com hits → lista de ``_source`` ordenada por grau (G1 < G2 < GS)."""
    payload = _payload_es(
        _source_for_grau("G2", orgaoJulgador={"nome": "8ª Turma"}),
        _source_for_grau("G1", orgaoJulgador={"nome": "13ª Vara"}),
    )
    session = _make_session([_mock_response(200, payload)])
    client = _make_client(session=session)

    sources = client.consultar("0000398-69.2021.5.10.0013", "trt10")

    assert len(sources) == 2
    # G1 antes de G2 (ordenação ascendente, independente da ordem do payload).
    assert sources[0]["grau"] == "G1"
    assert sources[1]["grau"] == "G2"
    assert sources[0]["orgaoJulgador"]["nome"] == "13ª Vara"


# ---------------------------------------------------------------------------
# 2) consultar() em CNJ inexistente — lista vazia (sem exceção)
# ---------------------------------------------------------------------------


def test_consultar_cnj_inexistente_retorna_lista_vazia() -> None:
    """200 com ``hits.hits=[]`` → lista vazia. NÃO levanta DataJudNotFoundError."""
    payload = {
        "took": 1,
        "hits": {"total": {"value": 0, "relation": "eq"}, "hits": []},
    }
    session = _make_session([_mock_response(200, payload)])
    client = _make_client(session=session)

    sources = client.consultar("9999999-99.9999.9.99.9999", "trt10")

    assert sources == []


# ---------------------------------------------------------------------------
# 3) endpoint inválido → ValueError antes de qualquer HTTP
# ---------------------------------------------------------------------------


def test_consultar_endpoint_invalido_levanta_value_error() -> None:
    """Endpoint fora de ``TRIB_ENDPOINT.values()`` falha early com ValueError."""
    session = _make_session([_mock_response(200, {})])
    client = _make_client(session=session)

    with pytest.raises(ValueError, match="Endpoint desconhecido"):
        client.consultar("00003986920215100013", "endpoint_inexistente")

    # Nenhuma chamada HTTP foi feita
    session.post.assert_not_called()


# ---------------------------------------------------------------------------
# 4) Retry em 429 honra Retry-After
# ---------------------------------------------------------------------------


def test_retry_em_429_honra_retry_after() -> None:
    """Primeiro POST retorna 429 com ``Retry-After: 3``; segundo POST 200.

    O sleep entre eles deve usar 3.0s (não o backoff default de 2.0).
    """
    sleeps: list[float] = []
    payload = _payload_es(_source_for_grau("G1"))
    session = _make_session([
        _mock_response(429, {}, headers={"Retry-After": "3"}),
        _mock_response(200, payload),
    ])
    client = _make_client(session=session, sleep=sleeps.append)

    sources = client.consultar("0000398-69.2021.5.10.0013", "trt10")

    assert len(sources) == 1
    # Sleep com 3.0s (retry-after) DEVE estar na lista. Outros sleeps
    # podem ser do throttle mas não devem mascarar o 3.0.
    assert 3.0 in sleeps, f"Esperava 3.0 em sleeps, recebido {sleeps!r}"


# ---------------------------------------------------------------------------
# 5) Retry em 503 aplica backoff fixo
# ---------------------------------------------------------------------------


def test_retry_em_503_aplica_backoff() -> None:
    """503 → 200; sleep aplica RETRY_BACKOFFS[0] (= 2.0s) entre tentativas."""
    sleeps: list[float] = []
    payload = _payload_es(_source_for_grau("G1"))
    session = _make_session([
        _mock_response(503, {}),
        _mock_response(200, payload),
    ])
    client = _make_client(session=session, sleep=sleeps.append)

    sources = client.consultar("0000398-69.2021.5.10.0013", "trt10")

    assert len(sources) == 1
    # RETRY_BACKOFFS[0] (=2.0) deve aparecer ao menos uma vez (entre as
    # duas tentativas). Pode coincidir com sleep do throttle se elapsed
    # for ínfimo, mas o backoff explícito sempre é chamado.
    assert RETRY_BACKOFFS[0] in sleeps, (
        f"Esperava {RETRY_BACKOFFS[0]} em sleeps, recebido {sleeps!r}"
    )


# ---------------------------------------------------------------------------
# 6) APIKey padrão quando env var ausente
# ---------------------------------------------------------------------------


def test_apikey_padrao_quando_env_var_ausente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem env ``DATAJUD_APIKEY`` → ``get_apikey()`` retorna o default."""
    monkeypatch.delenv(DATAJUD_APIKEY_ENV, raising=False)

    apikey = get_apikey()

    assert apikey == DATAJUD_APIKEY_DEFAULT
    # E o default já vem com prefixo "APIKey "
    assert apikey.startswith("APIKey ")


# ---------------------------------------------------------------------------
# 7) APIKey override via env var
# ---------------------------------------------------------------------------


def test_apikey_override_via_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env ``DATAJUD_APIKEY=secret_token`` → ``"APIKey secret_token"``.
    Se já vem com prefixo, mantém literal.
    """
    monkeypatch.setenv(DATAJUD_APIKEY_ENV, "secret_token")
    assert get_apikey() == "APIKey secret_token"

    monkeypatch.setenv(DATAJUD_APIKEY_ENV, "APIKey custom_full")
    assert get_apikey() == "APIKey custom_full"

    # Whitespace-only é tratado como ausente
    monkeypatch.setenv(DATAJUD_APIKEY_ENV, "   ")
    assert get_apikey() == DATAJUD_APIKEY_DEFAULT


# ---------------------------------------------------------------------------
# 8) Throttle aplica sleep mínimo entre chamadas
# ---------------------------------------------------------------------------


def test_throttle_aplica_sleep_minimo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duas chamadas com diff < RATE_LIMIT → sleep com (RATE_LIMIT - elapsed).

    Mockamos ``time.monotonic`` pra controlar o relógio. Sequência:
      - 1ª _throttle: now=100.0 (last_call=0 → não dorme), last_call=100.0
      - POST 1
      - 2ª _throttle: now=100.5 (elapsed=0.5 → sleep 1.5s), last_call=102.0
      - POST 2
    """
    sleeps: list[float] = []
    times = iter([100.0, 100.0, 100.5, 102.0])
    monkeypatch.setattr(
        "notion_rpadv.services.datajud_client.time.monotonic",
        lambda: next(times),
    )

    payload = _payload_es(_source_for_grau("G1"))
    session = _make_session([
        _mock_response(200, payload),
        _mock_response(200, payload),
    ])
    client = _make_client(session=session, sleep=sleeps.append)

    client.consultar("0000398-69.2021.5.10.0013", "trt10")
    client.consultar("0000398-69.2021.5.10.0013", "trt10")

    # 1ª call: sem sleep (last_call=0, elapsed gigante).
    # 2ª call: sleep(RATE_LIMIT_SECONDS - 0.5) = sleep(1.5).
    expected = RATE_LIMIT_SECONDS - 0.5
    assert any(abs(s - expected) < 0.01 for s in sleeps), (
        f"Esperava sleep ~{expected}s em {sleeps!r}"
    )


# ---------------------------------------------------------------------------
# Testes auxiliares — normalize_cnj, endpoint_de_tribunal
# ---------------------------------------------------------------------------


def test_normalize_cnj_aceita_com_e_sem_mascara() -> None:
    assert normalize_cnj("0000398-69.2021.5.10.0013") == "00003986920215100013"
    assert normalize_cnj("00003986920215100013") == "00003986920215100013"
    # Ignora espaços extras
    assert normalize_cnj("  0000398-69.2021.5.10.0013  ") == "00003986920215100013"


def test_normalize_cnj_rejeita_tamanho_invalido() -> None:
    with pytest.raises(ValueError, match="20 dígitos"):
        normalize_cnj("123")
    with pytest.raises(ValueError, match="20 dígitos"):
        normalize_cnj("0000398692021510001")  # 19 dígitos


def test_endpoint_de_tribunal_mapeia_e_devolve_none_para_outro() -> None:
    assert endpoint_de_tribunal("TJDFT") == "tjdft"
    assert endpoint_de_tribunal("TRT/10") == "trt10"
    assert endpoint_de_tribunal("STJ") == "stj"
    assert endpoint_de_tribunal("Outro") is None
    assert endpoint_de_tribunal("STF") is None  # sem endpoint público
    assert endpoint_de_tribunal("") is None
    assert endpoint_de_tribunal("ALGUM_TRIBUNAL_INEXISTENTE") is None


# ---------------------------------------------------------------------------
# Testes auxiliares — comportamento de exceção
# ---------------------------------------------------------------------------


def test_429_persistente_levanta_rate_limit_error() -> None:
    """3 tentativas todas em 429 → ``DataJudRateLimitError``."""
    sleeps: list[float] = []
    session = _make_session([
        _mock_response(429, {}, headers={"Retry-After": "1"}),
        _mock_response(429, {}, headers={"Retry-After": "1"}),
        _mock_response(429, {}, headers={"Retry-After": "1"}),
    ])
    client = _make_client(session=session, sleep=sleeps.append)

    with pytest.raises(DataJudRateLimitError) as exc_info:
        client.consultar("0000398-69.2021.5.10.0013", "trt10")

    assert exc_info.value.status_code == 429


def test_4xx_nao_429_nao_retry_levanta_imediatamente() -> None:
    """HTTP 400 → ``DataJudAPIError`` na primeira tentativa, sem retry."""
    session = _make_session([
        _mock_response(400, {}),
    ])
    client = _make_client(session=session)

    with pytest.raises(DataJudAPIError) as exc_info:
        client.consultar("0000398-69.2021.5.10.0013", "trt10")

    assert exc_info.value.status_code == 400
    assert session.post.call_count == 1


def test_payload_sem_hits_retorna_lista_vazia() -> None:
    """Payload malformado (sem ``hits`` ou ``hits.hits``) → lista vazia,
    não levanta. Defensivo contra variações de schema."""
    session = _make_session([_mock_response(200, {"unexpected": "shape"})])
    client = _make_client(session=session)

    sources = client.consultar("0000398-69.2021.5.10.0013", "trt10")

    assert sources == []


# ---------------------------------------------------------------------------
# consultar_multi — orquestração de múltiplos endpoints
# ---------------------------------------------------------------------------


def test_consultar_multi_chama_cada_endpoint_uma_vez() -> None:
    """consultar_multi(["trt10", "tst"]) faz exatamente 2 chamadas HTTP."""
    payload_trt = _payload_es(_source_for_grau("G1"))
    payload_tst = _payload_es(_source_for_grau("GS"))
    session = _make_session([
        _mock_response(200, payload_trt),
        _mock_response(200, payload_tst),
    ])
    client = _make_client(session=session)

    result = client.consultar_multi(
        "0000398-69.2021.5.10.0013",
        ["trt10", "tst"],
    )

    assert set(result.keys()) == {"trt10", "tst"}
    assert len(result["trt10"]) == 1
    assert result["trt10"][0]["grau"] == "G1"
    assert len(result["tst"]) == 1
    assert result["tst"][0]["grau"] == "GS"
    assert session.post.call_count == 2


def test_consultar_multi_dedup_endpoints_duplicados() -> None:
    """Endpoints duplicados (e.g. tribunal == STJ + instância == STJ)
    causam apenas 1 chamada — o caller (enricher) confia nessa dedup."""
    payload = _payload_es(_source_for_grau("GS"))
    session = _make_session([_mock_response(200, payload)])
    client = _make_client(session=session)

    result = client.consultar_multi(
        "0000398-69.2021.5.10.0013",
        ["stj", "stj"],
    )

    assert list(result.keys()) == ["stj"]
    assert session.post.call_count == 1


def test_consultar_multi_endpoint_com_zero_hits_aparece_no_dict() -> None:
    """Endpoint que devolve 0 hits aparece no dict com lista vazia
    (caller distingue "consultei e não tem nada" de "nem consultei")."""
    payload_trt = _payload_es(_source_for_grau("G1"))
    payload_vazio = {"hits": {"total": {"value": 0}, "hits": []}}
    session = _make_session([
        _mock_response(200, payload_trt),
        _mock_response(200, payload_vazio),
    ])
    client = _make_client(session=session)

    result = client.consultar_multi(
        "0000398-69.2021.5.10.0013",
        ["trt10", "tst"],
    )

    assert len(result["trt10"]) == 1
    assert result["tst"] == []
