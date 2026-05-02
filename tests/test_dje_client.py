"""Testes do ``notion_rpadv.services.dje_client``: HTTP, paginação,
retry/backoff, anotação ``advogado_consultado``, falha por advogado.

Sem chamada à API real — todas as requisições mockadas via
``unittest.mock``. Sleep injetado pra eliminar espera real.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers de mock
# ---------------------------------------------------------------------------


def _mock_response(
    status: int = 200,
    json_payload: Any = None,
    text: str = "",
    raise_json: bool = False,
):
    """Constrói um mock que parece com requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    if raise_json:
        resp.json.side_effect = ValueError("invalid JSON")
    else:
        resp.json.return_value = json_payload if json_payload is not None else {}
    return resp


def _make_session(side_effect):
    """Cria um Session mockado com .get configurado via side_effect.
    ``side_effect`` pode ser lista de responses ou callable."""
    session = MagicMock()
    session.headers = {}
    if isinstance(side_effect, list):
        session.get.side_effect = side_effect
    else:
        session.get.side_effect = side_effect
    return session


def _make_client(session, sleep=None):
    from notion_rpadv.services.dje_client import DJEClient
    return DJEClient(
        sleep=sleep if sleep is not None else (lambda _: None),
        session=session,
    )


# ---------------------------------------------------------------------------
# Case 1 — Construção dos parâmetros da query
# ---------------------------------------------------------------------------


def test_build_query_params_oab_sem_ponto() -> None:
    """numeroOab vai sempre como dígitos puros, mesmo se a entrada
    tiver ponto (formatação BR comum)."""
    from notion_rpadv.services.dje_client import build_query_params
    params = build_query_params(
        oab="36.129", uf="DF",
        data_inicio=date(2026, 5, 1),
        data_fim=date(2026, 5, 1),
        pagina=1,
    )
    assert params["numeroOab"] == "36129"
    assert params["ufOab"] == "DF"


def test_build_query_params_datas_iso() -> None:
    """Datas no formato YYYY-MM-DD (ISO)."""
    from notion_rpadv.services.dje_client import build_query_params
    params = build_query_params(
        "36129", "DF",
        date(2026, 5, 1), date(2026, 5, 3), 1,
    )
    assert params["dataDisponibilizacaoInicio"] == "2026-05-01"
    assert params["dataDisponibilizacaoFim"] == "2026-05-03"


def test_build_query_params_uf_uppercase() -> None:
    """ufOab é uppercased — entrada com lowercase ainda casa o backend."""
    from notion_rpadv.services.dje_client import build_query_params
    params = build_query_params(
        "36129", "df",
        date(2026, 5, 1), date(2026, 5, 1), 1,
    )
    assert params["ufOab"] == "DF"


def test_build_query_params_no_tribunal_no_nome() -> None:
    """Não passa siglaTribunal nem nomeAdvogado — busca nacional por
    OAB é a chave canônica do Round 7."""
    from notion_rpadv.services.dje_client import build_query_params
    params = build_query_params(
        "36129", "DF",
        date(2026, 5, 1), date(2026, 5, 1), 1,
    )
    assert "siglaTribunal" not in params
    assert "nomeAdvogado" not in params


def test_build_query_params_pagination_and_size() -> None:
    """pagina vai como string; itensPorPagina default 100."""
    from notion_rpadv.services.dje_client import build_query_params
    params = build_query_params(
        "36129", "DF",
        date(2026, 5, 1), date(2026, 5, 1), 7,
    )
    assert params["pagina"] == "7"
    assert params["itensPorPagina"] == "100"


# ---------------------------------------------------------------------------
# Case 2 — Parsing de resposta com 1 página de 3 itens
# ---------------------------------------------------------------------------


def test_parsing_3_items_anota_advogado_consultado() -> None:
    """Fixture com 3 items → 3 linhas, todas com advogado_consultado
    no formato 'Nome (OAB/UF)'."""
    items = [
        {"id": 1, "hash": "abc", "texto": "publicacao 1"},
        {"id": 2, "hash": "def", "texto": "publicacao 2"},
        {"id": 3, "hash": "ghi", "texto": "publicacao 3"},
    ]
    session = _make_session([_mock_response(json_payload={"items": items})])
    client = _make_client(session)
    advogado = {
        "nome": "Leonardo Guedes da Fonseca Passos",
        "oab": "36129", "uf": "DF",
    }
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert len(result.items) == 3
    expected_label = "Leonardo Guedes da Fonseca Passos (36129/DF)"
    for it in result.items:
        assert it["advogado_consultado"] == expected_label
    # Campos originais preservados (sem renomear, sem traduzir).
    assert result.items[0]["id"] == 1
    assert result.items[0]["hash"] == "abc"
    assert result.items[0]["texto"] == "publicacao 1"


# ---------------------------------------------------------------------------
# Case 3 — Paginação até esgotar
# ---------------------------------------------------------------------------


def test_paginacao_100_47_0() -> None:
    """Página 1 com 100 items, 2 com 47, 3 vazia → 147 items totais
    e 3 chamadas (a 3ª seria evitada se a 2ª já < PAGE_SIZE; o spec
    diz 'até o lote vir vazio OU abaixo do tamanho da página')."""
    page1 = [{"id": i, "hash": f"h{i}"} for i in range(100)]
    page2 = [{"id": i + 100, "hash": f"h{i+100}"} for i in range(47)]
    session = _make_session([
        _mock_response(json_payload={"items": page1}),
        _mock_response(json_payload={"items": page2}),
    ])
    client = _make_client(session)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert len(result.items) == 147
    # Esgota em 2 páginas (a 2ª já < PAGE_SIZE de 100 → para).
    assert result.paginas == 2
    assert session.get.call_count == 2


def test_paginacao_pagina_completa_seguida_de_vazia() -> None:
    """Quando todas as páginas vêm completas exceto a última (vazia),
    paginação termina na vazia — 3 chamadas, 200 items."""
    page1 = [{"id": i, "hash": f"h{i}"} for i in range(100)]
    page2 = [{"id": i + 100, "hash": f"h{i+100}"} for i in range(100)]
    page3: list[dict] = []
    session = _make_session([
        _mock_response(json_payload={"items": page1}),
        _mock_response(json_payload={"items": page2}),
        _mock_response(json_payload={"items": page3}),
    ])
    client = _make_client(session)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert len(result.items) == 200
    assert result.paginas == 3
    assert session.get.call_count == 3


# ---------------------------------------------------------------------------
# Case 4 — Empilhamento entre 2 advogados
# ---------------------------------------------------------------------------


def test_empilhamento_2_advogados_5_pubs_cada() -> None:
    """fetch_all com 2 advogados de 5 pubs cada → 10 linhas com
    advogado_consultado distinguindo origem."""
    pubs_a = [{"id": i, "hash": f"a{i}"} for i in range(5)]
    pubs_b = [{"id": i + 100, "hash": f"b{i}"} for i in range(5)]
    session = _make_session([
        _mock_response(json_payload={"items": pubs_a}),
        _mock_response(json_payload={"items": pubs_b}),
    ])
    client = _make_client(session)
    advogados = [
        {"nome": "Alice", "oab": "1", "uf": "DF"},
        {"nome": "Bob",   "oab": "2", "uf": "DF"},
    ]
    summary = client.fetch_all(
        advogados, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert summary.total_items == 10
    # Cada advogado tem seu próprio result.
    assert len(summary.by_advogado) == 2
    labels = {r["advogado_consultado"] for r in summary.rows}
    assert labels == {"Alice (1/DF)", "Bob (2/DF)"}
    assert not summary.errors


# ---------------------------------------------------------------------------
# Case 7 — Erro num advogado não derruba os outros
# ---------------------------------------------------------------------------


def test_erro_persistente_em_um_advogado_nao_derruba_demais() -> None:
    """503 persistente no 2º advogado → o 1º e o 3º são processados
    normalmente; summary.errors contém só o 2º."""

    call_order = []

    def get_side_effect(url, params=None, timeout=None):
        oab = params.get("numeroOab") if params else ""
        call_order.append(oab)
        if oab == "200":  # 2º advogado falha persistente
            return _mock_response(status=503, text="service unavailable")
        return _mock_response(
            json_payload={"items": [{"id": oab, "hash": f"h{oab}"}]},
        )

    session = _make_session(get_side_effect)
    client = _make_client(session)
    advogados = [
        {"nome": "AdvA", "oab": "100", "uf": "DF"},
        {"nome": "AdvB", "oab": "200", "uf": "DF"},
        {"nome": "AdvC", "oab": "300", "uf": "DF"},
    ]
    summary = client.fetch_all(
        advogados, date(2026, 5, 1), date(2026, 5, 1),
    )
    # 2 sucessos × 1 item = 2 linhas
    assert summary.total_items == 2
    # Erros: só o B.
    err_oabs = {r.advogado["oab"] for r in summary.errors}
    assert err_oabs == {"200"}
    # Os 3 foram processados (não abortou na falha).
    assert {r.advogado["oab"] for r in summary.by_advogado} == {"100", "200", "300"}


# ---------------------------------------------------------------------------
# Case 8 — Retry com backoff em 429
# ---------------------------------------------------------------------------


def test_retry_429_2x_depois_200() -> None:
    """429 nas 2 primeiras tentativas, 200 na 3ª → cliente esperou
    e retornou os dados. Sleep capturado registra os backoffs."""
    sleeps: list[float] = []
    items_ok = [{"id": 1, "hash": "x"}]
    session = _make_session([
        _mock_response(status=429, text="rate limit"),
        _mock_response(status=429, text="rate limit"),
        _mock_response(json_payload={"items": items_ok}),
    ])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert len(result.items) == 1
    # 3 tentativas → 2 sleeps de backoff (2s e 8s). Não houve
    # sleep entre páginas (foi 1 página só).
    assert sleeps == [2.0, 8.0]
    assert result.erro is None


def test_retry_429_persistente_3_tentativas() -> None:
    """429 nas 3 tentativas → falha persistente, advogado entra em
    summary.errors e log da varredura inteira segue."""
    sleeps: list[float] = []
    session = _make_session([
        _mock_response(status=429, text="rate limit"),
        _mock_response(status=429, text="rate limit"),
        _mock_response(status=429, text="rate limit"),
    ])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.erro is not None
    assert "429" in result.erro
    # Backoffs aplicados nas 2 esperas.
    assert sleeps == [2.0, 8.0]


def test_retry_503_idem_429() -> None:
    """503 também é retryable (transient)."""
    sleeps: list[float] = []
    session = _make_session([
        _mock_response(status=503, text="unavailable"),
        _mock_response(json_payload={"items": [{"id": 1, "hash": "x"}]}),
    ])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.erro is None
    assert len(result.items) == 1
    assert sleeps == [2.0]


def test_retry_timeout_de_rede() -> None:
    """Timeout (requests.RequestException) também é retryable."""
    import requests
    sleeps: list[float] = []
    session = MagicMock()
    session.headers = {}
    # Lado A: lança Timeout 2x; lado B: 200 OK.
    session.get.side_effect = [
        requests.Timeout("timeout"),
        requests.ConnectionError("network down"),
        _mock_response(json_payload={"items": [{"id": 1, "hash": "x"}]}),
    ]
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.erro is None
    assert len(result.items) == 1
    assert sleeps == [2.0, 8.0]


def test_retry_4xx_nao_retryable() -> None:
    """HTTP 400 (bad request) — sem retry, falha imediata."""
    sleeps: list[float] = []
    session = _make_session([
        _mock_response(status=400, text='{"error":"bad request"}'),
    ])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.erro is not None
    assert "400" in result.erro
    # Sem backoff — não retryable.
    assert sleeps == []


def test_json_invalido_em_200() -> None:
    """200 com JSON malformado → falha sem retry (não é transiente)."""
    sleeps: list[float] = []
    session = _make_session([
        _mock_response(status=200, raise_json=True),
    ])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.erro is not None
    assert "JSON" in result.erro
    assert sleeps == []


# ---------------------------------------------------------------------------
# Case 9 — Resposta com array vazio
# ---------------------------------------------------------------------------


def test_array_vazio_nao_quebra() -> None:
    """``items: []`` é cenário válido (advogado sem publicações no
    período). Não deve levantar; resultado tem 0 items, 1 página
    consumida."""
    session = _make_session([_mock_response(json_payload={"items": []})])
    client = _make_client(session)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.items == []
    assert result.paginas == 1
    assert result.erro is None


def test_payload_sem_chave_items() -> None:
    """Defesa contra schema variante: payload sem ``items`` não quebra,
    é tratado como 0 items (página vazia)."""
    session = _make_session([_mock_response(json_payload={"meta": "x"})])
    client = _make_client(session)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.items == []
    assert result.erro is None


# ---------------------------------------------------------------------------
# Rate limit entre advogados
# ---------------------------------------------------------------------------


def test_rate_limit_entre_advogados_e_paginas() -> None:
    """fetch_all aplica RATE_LIMIT_SECONDS sleep entre cada chamada
    HTTP — incluindo entre páginas do mesmo advogado e entre
    advogados consecutivos."""
    page1 = [{"id": i, "hash": f"h{i}"} for i in range(100)]
    page2 = [{"id": i + 100, "hash": f"h{i+100}"} for i in range(5)]
    pubs_b = [{"id": 999, "hash": "z"}]
    session = _make_session([
        _mock_response(json_payload={"items": page1}),  # adv A pg1
        _mock_response(json_payload={"items": page2}),  # adv A pg2
        _mock_response(json_payload={"items": pubs_b}),  # adv B pg1
    ])
    sleeps: list[float] = []
    client = _make_client(session, sleep=sleeps.append)
    summary = client.fetch_all(
        [
            {"nome": "AdvA", "oab": "1", "uf": "DF"},
            {"nome": "AdvB", "oab": "2", "uf": "DF"},
        ],
        date(2026, 5, 1), date(2026, 5, 1),
    )
    # 1 sleep entre páginas do A + 1 sleep entre A e B = 2 sleeps de 1s.
    # Não há sleep antes da 1ª requisição (otimização — operador já
    # esperou pra clicar o botão).
    from notion_rpadv.services.dje_client import RATE_LIMIT_SECONDS
    assert sleeps == [RATE_LIMIT_SECONDS, RATE_LIMIT_SECONDS]
    assert summary.total_items == 100 + 5 + 1


# ---------------------------------------------------------------------------
# on_progress callback
# ---------------------------------------------------------------------------


def test_on_progress_callback_chamado_por_advogado() -> None:
    """on_progress(idx, total, result) chamado uma vez por advogado,
    seja sucesso ou erro persistente."""
    session = _make_session([
        _mock_response(json_payload={"items": [{"id": 1, "hash": "x"}]}),
        _mock_response(status=503, text="down"),
        _mock_response(status=503, text="down"),
        _mock_response(status=503, text="down"),
    ])
    client = _make_client(session)
    advogados = [
        {"nome": "AdvA", "oab": "1", "uf": "DF"},
        {"nome": "AdvB", "oab": "2", "uf": "DF"},
    ]
    progress_calls: list[tuple[int, int, str]] = []

    def cb(idx, total, result):
        progress_calls.append(
            (idx, total, result.advogado["nome"]),
        )
    summary = client.fetch_all(
        advogados, date(2026, 5, 1), date(2026, 5, 1),
        on_progress=cb,
    )
    assert progress_calls == [
        (1, 2, "AdvA"),
        (2, 2, "AdvB"),
    ]
    # Erros do B presentes
    assert len(summary.errors) == 1
    assert summary.errors[0].advogado["nome"] == "AdvB"


def test_on_progress_exception_nao_aborta() -> None:
    """Callback que levanta não derruba a varredura."""
    session = _make_session([
        _mock_response(json_payload={"items": []}),
        _mock_response(json_payload={"items": []}),
    ])
    client = _make_client(session)
    advogados = [
        {"nome": "AdvA", "oab": "1", "uf": "DF"},
        {"nome": "AdvB", "oab": "2", "uf": "DF"},
    ]

    def bad_cb(idx, total, result):
        raise RuntimeError("boom")

    summary = client.fetch_all(
        advogados, date(2026, 5, 1), date(2026, 5, 1),
        on_progress=bad_cb,
    )
    assert len(summary.by_advogado) == 2


# ---------------------------------------------------------------------------
# Anotação ``advogado_consultado`` formato canônico
# ---------------------------------------------------------------------------


def test_format_advogado_label() -> None:
    """Formato canônico ``Nome (OAB/UF)``."""
    from notion_rpadv.services.dje_advogados import format_advogado_label
    label = format_advogado_label({
        "nome": "Maria Silva", "oab": "12345", "uf": "DF",
    })
    assert label == "Maria Silva (12345/DF)"


def test_advogados_lista_completa() -> None:
    """Sanity: lista oficial atual tem os 6 advogados ativos com OAB DF.

    Fase 2.1 (2026-05-01): reduzida de 12 → 6 (6 desativados ficam
    comentados em ``dje_advogados.py``)."""
    from notion_rpadv.services.dje_advogados import ADVOGADOS
    assert len(ADVOGADOS) == 6
    for a in ADVOGADOS:
        assert a["uf"] == "DF"
        assert a["oab"].isdigit()
        assert a["nome"].strip()


# ---------------------------------------------------------------------------
# DJEClient construtor
# ---------------------------------------------------------------------------


def test_default_session_has_user_agent_header() -> None:
    """Sessão default carrega User-Agent canônico."""
    from notion_rpadv.services.dje_client import DJEClient, USER_AGENT
    client = DJEClient()
    # Acessa via internal — teste de smoke; não chama API.
    assert client._session.headers["User-Agent"] == USER_AGENT  # noqa: SLF001


# ---------------------------------------------------------------------------
# Fase 2.1 — Rate limit + Retry-After (Bug A do hotfix)
# ---------------------------------------------------------------------------


def test_F21_09_rate_limit_constant_eh_2_segundos() -> None:
    """Pausa entre TODAS as requisições subiu de 1.0 → 2.0s na Fase 2.1
    (smoke real em janela longa quebrou com 1s)."""
    from notion_rpadv.services.dje_client import RATE_LIMIT_SECONDS
    assert RATE_LIMIT_SECONDS == 2.0


def test_F21_10_retry_after_inteiro_no_429_eh_honrado() -> None:
    """429 com header ``Retry-After: 5`` → cliente espera 5s antes do
    retry, em vez de aplicar o backoff fixo (2s/8s)."""
    sleeps: list[float] = []
    # 1ª tentativa: 429 com Retry-After=5; 2ª tentativa: 200 com items.
    resp_429 = _mock_response(status=429)
    resp_429.headers = {"Retry-After": "5"}
    resp_ok = _mock_response(json_payload={"items": []})
    session = _make_session([resp_429, resp_ok])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    # Sucesso — 2ª tentativa retornou 0 items.
    assert result.erro is None
    # 1ª espera (entre 429 e retry): 5s do header, NÃO 2s do backoff.
    assert sleeps[0] == 5.0


def test_F21_11_retry_after_ausente_usa_backoff_atual() -> None:
    """429 sem header ``Retry-After`` → fallback no backoff (2s na 1ª
    espera entre tentativas, 8s na 2ª)."""
    from notion_rpadv.services.dje_client import RETRY_BACKOFFS
    sleeps: list[float] = []
    # 1ª e 2ª tentativas: 429 sem header; 3ª: 200.
    resp_429a = _mock_response(status=429)
    resp_429a.headers = {}
    resp_429b = _mock_response(status=429)
    resp_429b.headers = {}
    resp_ok = _mock_response(json_payload={"items": []})
    session = _make_session([resp_429a, resp_429b, resp_ok])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.erro is None
    # 1ª espera = backoff[0] (2s), 2ª espera = backoff[1] (8s).
    assert sleeps[0] == RETRY_BACKOFFS[0]
    assert sleeps[1] == RETRY_BACKOFFS[1]


def test_F21_12_retry_after_malformado_usa_backoff_atual() -> None:
    """Header ``Retry-After`` com valor não-numérico (e.g. HTTP-date
    RFC 7231 ou texto solto) → fallback no backoff atual, sem crash."""
    from notion_rpadv.services.dje_client import RETRY_BACKOFFS
    sleeps: list[float] = []
    resp_429 = _mock_response(status=429)
    resp_429.headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
    resp_ok = _mock_response(json_payload={"items": []})
    session = _make_session([resp_429, resp_ok])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.erro is None
    # Espera caiu no backoff (não no header malformado).
    assert sleeps[0] == RETRY_BACKOFFS[0]


def test_F21_12cap_retry_after_acima_do_cap_eh_capado_em_60s() -> None:
    """Header ``Retry-After: 600`` → espera capa em 60s (não trava o
    thread por 10min). Decisão de design Fase 2.1."""
    from notion_rpadv.services.dje_client import RETRY_AFTER_CAP_SECONDS
    sleeps: list[float] = []
    resp_429 = _mock_response(status=429)
    resp_429.headers = {"Retry-After": "600"}
    resp_ok = _mock_response(json_payload={"items": []})
    session = _make_session([resp_429, resp_ok])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.erro is None
    # Cap em 60s (default em Fase 2.1).
    assert sleeps[0] == RETRY_AFTER_CAP_SECONDS == 60.0


# ---------------------------------------------------------------------------
# Fase 2.2 — Retry-After refinado (zero válido, negativo distinguido)
# ---------------------------------------------------------------------------


def test_F22_14_retry_after_zero_nao_espera_e_prossegue() -> None:
    """``Retry-After: 0`` → cliente não espera (sleep com valor 0)
    antes do retry. Servidor sinalizou 'pode prosseguir agora'."""
    sleeps: list[float] = []
    resp_429 = _mock_response(status=429)
    resp_429.headers = {"Retry-After": "0"}
    resp_ok = _mock_response(json_payload={"items": []})
    session = _make_session([resp_429, resp_ok])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    result = client.fetch_advogado(
        advogado, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert result.erro is None
    assert sleeps[0] == 0.0


def test_F22_15_retry_after_negativo_eh_invalido_log_classifica_bug_servidor(
    caplog,
) -> None:
    """``Retry-After: -39`` → fallback no backoff atual + warning log
    com mensagem específica "negativo, bug do servidor". Bug observado
    no smoke real da Fase 2.1 (DJEN envia valores tipo -39, -41, -57)."""
    import logging
    from notion_rpadv.services.dje_client import RETRY_BACKOFFS
    sleeps: list[float] = []
    resp_429 = _mock_response(status=429)
    resp_429.headers = {"Retry-After": "-39"}
    resp_ok = _mock_response(json_payload={"items": []})
    session = _make_session([resp_429, resp_ok])
    client = _make_client(session, sleep=sleeps.append)
    advogado = {"nome": "X", "oab": "1", "uf": "DF"}
    with caplog.at_level(logging.WARNING, logger="dje.client"):
        result = client.fetch_advogado(
            advogado, date(2026, 5, 1), date(2026, 5, 1),
        )
    assert result.erro is None
    # Caiu no fallback do backoff (não no valor negativo).
    assert sleeps[0] == RETRY_BACKOFFS[0]
    # Mensagem de log classifica o erro como bug do servidor.
    relevant = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING and "Retry-After" in r.getMessage()
    ]
    assert any("negativo" in m and "bug do servidor" in m for m in relevant), (
        f"esperava warning 'negativo, bug do servidor', got: {relevant!r}"
    )


# ---------------------------------------------------------------------------
# Fase 2.2 — Split de janela mensal (puro)
# ---------------------------------------------------------------------------


def test_F22_06_split_window_janela_curta_nao_splita() -> None:
    """Janela ≤ 31 dias → 1 sub-janela (não splita; comportamento
    Fase 2.1 preservado)."""
    from notion_rpadv.services.dje_client import _split_window_monthly
    # Mesmo dia
    assert _split_window_monthly(date(2026, 5, 1), date(2026, 5, 1)) == [
        (date(2026, 5, 1), date(2026, 5, 1)),
    ]
    # 31 dias exatos
    assert _split_window_monthly(date(2026, 5, 1), date(2026, 6, 1)) == [
        (date(2026, 5, 1), date(2026, 6, 1)),
    ]
    # 7 dias dentro do mesmo mês
    assert _split_window_monthly(date(2026, 5, 1), date(2026, 5, 8)) == [
        (date(2026, 5, 1), date(2026, 5, 8)),
    ]


def test_F22_07_split_window_4_meses_calendar_aligned() -> None:
    """Janela 01/01→01/05/2026 (4 meses, > 31 dias) → 5 sub-janelas
    calendar-aligned (jan/fev/mar/abr/mai). Cada sub-janela vai do
    dia 1 ao último dia do mês, exceto a primeira (que começa em
    data_inicio) e a última (que termina em data_fim)."""
    from notion_rpadv.services.dje_client import _split_window_monthly
    result = _split_window_monthly(date(2026, 1, 1), date(2026, 5, 1))
    assert result == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 31)),
        (date(2026, 4, 1), date(2026, 4, 30)),
        (date(2026, 5, 1), date(2026, 5, 1)),
    ]


def test_F22_08_split_window_atravessando_ano_e_dezembro() -> None:
    """Janela 15/12/2025 → 15/02/2026 (3 meses parciais, atravessa
    ano) → 3 sub-janelas (dez/25, jan/26, fev/26). Testa o branch
    de mês == 12 (incrementa ano)."""
    from notion_rpadv.services.dje_client import _split_window_monthly
    result = _split_window_monthly(date(2025, 12, 15), date(2026, 2, 15))
    assert result == [
        (date(2025, 12, 15), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 15)),
    ]


# ---------------------------------------------------------------------------
# Fase 2.2 — fetch_all com sub-janelas (integração)
# ---------------------------------------------------------------------------


def test_F22_09_fetch_all_janela_longa_chama_sub_janelas() -> None:
    """fetch_all com janela > 31 dias chama fetch_advogado uma vez
    por sub-janela. Items são agregados num único AdvogadoResult."""
    # Janela 4 meses → 5 sub-janelas. Mock: cada sub-janela retorna
    # 2 items (1 página, < PAGE_SIZE → fetch_advogado para após 1 req).
    sub_payloads = [
        _mock_response(json_payload={"items": [
            {"id": f"{m}-1", "hash": "x"},
            {"id": f"{m}-2", "hash": "y"},
        ]})
        for m in range(5)  # 5 sub-janelas
    ]
    session = _make_session(sub_payloads)
    client = _make_client(session)
    advogados = [{"nome": "X", "oab": "1", "uf": "DF"}]
    summary = client.fetch_all(
        advogados, date(2026, 1, 1), date(2026, 5, 1),
    )
    # 5 sub-janelas × 2 items = 10 items totais.
    assert summary.total_items == 10
    assert len(summary.by_advogado) == 1
    # Sem erros: tudo correu bem.
    assert summary.errors == []
    # 5 chamadas HTTP (1 por sub-janela, cada uma com 2 items < PAGE_SIZE).
    assert session.get.call_count == 5


def test_F22_10_retry_diferido_recupera_falha_em_sub_janela() -> None:
    """Janela longa (split): 1 sub-janela falha persistente na 1ª
    passada → retry diferido tenta de novo, sucesso → ``erro`` é
    limpo no AdvogadoResult agregado."""
    from notion_rpadv.services.dje_client import RETRY_DEFERRED_PAUSE_SECONDS

    # Cenário: 4 sub-janelas (jan/fev/mar/abr/26 numa janela de 4 meses
    # ajustada pra cair em 4). Janela 02/01 → 02/05 = 5 sub-janelas
    # iremos usar 02/01 → 30/04 = 4 sub-janelas (jan/fev/mar/abr).
    # Sub 0,1,2 ok; sub 3 (abr) falha 503 3x na 1ª passada;
    # depois retry diferido: 1 chamada extra OK.
    responses = [
        _mock_response(json_payload={"items": [{"id": "j", "hash": "j"}]}),  # jan
        _mock_response(json_payload={"items": [{"id": "f", "hash": "f"}]}),  # fev
        _mock_response(json_payload={"items": [{"id": "m", "hash": "m"}]}),  # mar
        # abr — 3 falhas (retry budget esgotado)
        _mock_response(status=503),
        _mock_response(status=503),
        _mock_response(status=503),
        # retry diferido na sub abr — 1 chamada bem-sucedida
        _mock_response(json_payload={"items": [{"id": "a", "hash": "a"}]}),
    ]
    sleeps: list[float] = []
    session = _make_session(responses)
    client = _make_client(session, sleep=sleeps.append)
    advogados = [{"nome": "X", "oab": "1", "uf": "DF"}]
    summary = client.fetch_all(
        advogados, date(2026, 1, 2), date(2026, 4, 30),
    )
    # 4 sub-janelas × 1 item cada = 4 items totais (incluindo o recuperado).
    assert summary.total_items == 4
    # Sem erros: retry diferido recuperou.
    assert summary.errors == []
    # Pausa de retry diferido foi aplicada (≥ RETRY_DEFERRED_PAUSE_SECONDS).
    assert RETRY_DEFERRED_PAUSE_SECONDS in sleeps


def test_F22_11_retry_diferido_falha_em_ambas_passadas_mantem_erro() -> None:
    """Janela longa: 1 sub-janela falha 503 na 1ª passada E no retry
    diferido → ``erro`` permanece no AdvogadoResult agregado, listado
    em summary.errors."""
    # 4 sub-janelas (jan/fev/mar/abr). Sub 3 (abr) falha em todas
    # as 6 chamadas (3 na 1ª passada + 3 no retry diferido).
    responses = [
        _mock_response(json_payload={"items": [{"id": "j", "hash": "j"}]}),
        _mock_response(json_payload={"items": [{"id": "f", "hash": "f"}]}),
        _mock_response(json_payload={"items": [{"id": "m", "hash": "m"}]}),
        # 1ª passada da abr — 3 falhas
        _mock_response(status=503),
        _mock_response(status=503),
        _mock_response(status=503),
        # Retry diferido — também 3 falhas
        _mock_response(status=503),
        _mock_response(status=503),
        _mock_response(status=503),
    ]
    session = _make_session(responses)
    client = _make_client(session)
    advogados = [{"nome": "X", "oab": "1", "uf": "DF"}]
    summary = client.fetch_all(
        advogados, date(2026, 1, 2), date(2026, 4, 30),
    )
    # 3 items das sub-janelas que sucederam (jan/fev/mar).
    assert summary.total_items == 3
    # Erro permanece no advogado (sub-janela abr falhou definitivamente).
    assert len(summary.errors) == 1
    assert summary.errors[0].advogado["oab"] == "1"


# ---------------------------------------------------------------------------
# Fase 2.2 — Cancelamento (is_cancelled)
# ---------------------------------------------------------------------------


def test_F22_12_cancelamento_entre_advogados_para_e_marca_cancelled() -> None:
    """``is_cancelled`` retorna True após o 1º advogado completar →
    a varredura para no início do 2º; ``summary.cancelled == True``;
    items do 1º preservados."""
    # Single-day window (sem split). 1ª chamada: AdvA OK. Antes da
    # 2ª chamada (AdvB), is_cancelled vira True → para.
    items_a = [{"id": 1, "hash": "a"}]
    session = _make_session([
        _mock_response(json_payload={"items": items_a}),
    ])
    client = _make_client(session)
    advogados = [
        {"nome": "AdvA", "oab": "1", "uf": "DF"},
        {"nome": "AdvB", "oab": "2", "uf": "DF"},
    ]
    # Flag que vira True após 1ª chamada à get.
    cancel_after_calls = [1]  # mutable container
    def is_cancelled():
        return session.get.call_count >= cancel_after_calls[0]

    summary = client.fetch_all(
        advogados, date(2026, 5, 1), date(2026, 5, 1),
        is_cancelled=is_cancelled,
    )
    assert summary.cancelled is True
    # 1 item do AdvA captado (não perdeu).
    assert summary.total_items == 1
    # session.get foi chamado exatamente 1 vez (AdvB nunca).
    assert session.get.call_count == 1


def test_F22_13_cancelamento_entre_paginas_retorna_parcial() -> None:
    """``is_cancelled`` retorna True após pag 2 do AdvA → fetch_advogado
    para entre páginas; items das 2 páginas preservados, summary
    marca cancelled."""
    page1 = [{"id": i, "hash": f"h{i}"} for i in range(100)]
    page2 = [{"id": i + 100, "hash": f"h{i+100}"} for i in range(100)]
    page3 = [{"id": i + 200, "hash": f"h{i+200}"} for i in range(50)]  # nunca alcançada
    session = _make_session([
        _mock_response(json_payload={"items": page1}),
        _mock_response(json_payload={"items": page2}),
        _mock_response(json_payload={"items": page3}),
    ])
    client = _make_client(session)
    advogados = [{"nome": "X", "oab": "1", "uf": "DF"}]
    # Cancela após 2 calls (= entre pag 2 e pag 3).
    def is_cancelled():
        return session.get.call_count >= 2

    summary = client.fetch_all(
        advogados, date(2026, 5, 1), date(2026, 5, 1),
        is_cancelled=is_cancelled,
    )
    assert summary.cancelled is True
    # 100 + 100 = 200 items das 2 primeiras páginas.
    assert summary.total_items == 200
    # 2 chamadas, não 3.
    assert session.get.call_count == 2
    # AdvogadoResult agregado preservou os items.
    assert len(summary.by_advogado[0].items) == 200
    # erro = None (cancelamento ≠ erro).
    assert summary.by_advogado[0].erro is None
