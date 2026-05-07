"""Testes da camada base do Round 10 — TA01, TA02, TC01, TC02.

Cada regra é testada isoladamente (input → TagApp ou None) e em
conjunto via :func:`aplicar_todas_regras` (foco aqui na camada base;
Alerta contadoria fica em ``test_round_10_alerta_contadoria.py``).
"""
from __future__ import annotations

from notion_rpadv.services.dje_regras import aplicar_todas_regras
from notion_rpadv.services.dje_regras.camada_base import (
    regra_ta01_analisar_sentenca,
    regra_ta02_analisar_acordao,
    regra_tc01_distribuicao,
    regra_tc02_pauta_julgamento,
)


# ---------------------------------------------------------------------------
# TA01 — Analisar sentença
# ---------------------------------------------------------------------------


def test_ta01_intimacao_sentenca_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Sentença"}
    t = regra_ta01_analisar_sentenca(pub)
    assert t is not None
    assert t.regra == "TA01"
    assert t.propriedade == "Tarefa advogado"
    assert t.tag_base == "Analisar sentença"
    assert t.tag == "Analisar sentença - App"


def test_ta01_outras_combinacoes_nao_disparam() -> None:
    casos: list[dict] = [
        {"tipoComunicacao": "Intimação", "tipoDocumento": "Despacho"},
        {"tipoComunicacao": "Edital", "tipoDocumento": "Sentença"},
        {"tipoComunicacao": "Lista de Distribuição", "tipoDocumento": "Sentença"},
        {"tipoComunicacao": "", "tipoDocumento": ""},
    ]
    for pub in casos:
        assert regra_ta01_analisar_sentenca(pub) is None


# ---------------------------------------------------------------------------
# TA02 — Analisar acórdão (Acórdão e Ementa)
# ---------------------------------------------------------------------------


def test_ta02_intimacao_acordao_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Acórdão"}
    t = regra_ta02_analisar_acordao(pub)
    assert t is not None
    assert t.regra == "TA02"
    assert t.tag == "Analisar acórdão - App"


def test_ta02_intimacao_ementa_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Ementa"}
    t = regra_ta02_analisar_acordao(pub)
    assert t is not None
    assert t.regra == "TA02"


def test_ta02_intimacao_outros_nao_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Despacho"}
    assert regra_ta02_analisar_acordao(pub) is None


def test_ta02_edital_acordao_nao_dispara() -> None:
    """Acórdão só vira tarefa de advogado em Intimação — em Edital
    seria atípico e fora do escopo do app."""
    pub = {"tipoComunicacao": "Edital", "tipoDocumento": "Acórdão"}
    assert regra_ta02_analisar_acordao(pub) is None


# ---------------------------------------------------------------------------
# TC01 — Distribuição
# ---------------------------------------------------------------------------


def test_tc01_lista_de_distribuicao_qualquer_doc() -> None:
    """Lista de Distribuição dispara TC01 independente do
    tipoDocumento."""
    for tipo_doc in ("Despacho", "Distribuição", "Sentença", "Notificação"):
        pub = {
            "tipoComunicacao": "Lista de Distribuição",
            "tipoDocumento": tipo_doc,
        }
        t = regra_tc01_distribuicao(pub)
        assert t is not None, f"falhou em {tipo_doc!r}"
        assert t.regra == "TC01"
        assert t.tag == "Processo/recurso distribuído - App"


def test_tc01_intimacao_com_distribuicao_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Distribuição"}
    t = regra_tc01_distribuicao(pub)
    assert t is not None
    assert t.regra == "TC01"


def test_tc01_intimacao_outros_nao_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Sentença"}
    assert regra_tc01_distribuicao(pub) is None


# ---------------------------------------------------------------------------
# TC02 — Pauta de Julgamento
# ---------------------------------------------------------------------------


def test_tc02_pauta_em_edital_dispara() -> None:
    pub = {"tipoComunicacao": "Edital", "tipoDocumento": "Pauta de Julgamento"}
    t = regra_tc02_pauta_julgamento(pub)
    assert t is not None
    assert t.regra == "TC02"
    assert t.tag == "Incluir julgamento no controle - App"


def test_tc02_pauta_em_intimacao_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Pauta de Julgamento"}
    t = regra_tc02_pauta_julgamento(pub)
    assert t is not None


def test_tc02_outros_docs_nao_disparam() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Despacho"}
    assert regra_tc02_pauta_julgamento(pub) is None


# ---------------------------------------------------------------------------
# Integração via aplicar_todas_regras
# ---------------------------------------------------------------------------


def test_camada_base_via_orquestrador_intimacao_sentenca() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Sentença"}
    v = aplicar_todas_regras(pub, processo_record=None)
    assert [t.regra for t in v.tarefa_advogado] == ["TA01"]
    assert v.tarefa_contadoria == []


def test_camada_base_via_orquestrador_lista_distribuicao_sem_proc() -> None:
    """Lista de Distribuição sem processo cadastrado: dispara TC01
    (camada base) — não dispara AC26 (Processo não cadastrado)
    porque distribuições já têm sinal correto via TC01."""
    pub = {
        "tipoComunicacao": "Lista de Distribuição",
        "tipoDocumento": "Notificação",
    }
    v = aplicar_todas_regras(pub, processo_record=None)
    tcs = [t.regra for t in v.tarefa_contadoria]
    acs = [t.regra for t in v.alerta_contadoria]
    assert tcs == ["TC01"]
    assert "AC26" not in acs
