"""Camada base do Round 10 — TA01, TA02, TC01, TC02.

A matriz Tipo de comunicação × Tipo de documento define o conjunto
**inicial** de tags da publicação, por categoria:

+-----------------------+----------------------+---------------------+----------------------------------+
| tipoComunicação       | tipoDocumento        | Tarefa advogado     | Tarefa contadoria                |
+=======================+======================+=====================+==================================+
| Lista de Distribuição | (qualquer)           | —                   | Processo/recurso distribuído     |
| Intimação             | Distribuição         | —                   | Processo/recurso distribuído     |
| Edital                | Pauta de Julgamento  | —                   | Incluir julgamento no controle   |
| Intimação             | Pauta de Julgamento  | —                   | Incluir julgamento no controle   |
| Intimação             | Sentença             | Analisar sentença   | —                                |
| Intimação             | Acórdão / Ementa     | Analisar acórdão    | —                                |
| (demais combinações)  |                      | —                   | —                                |
+-----------------------+----------------------+---------------------+----------------------------------+

A camada base nunca emite ``Alerta contadoria`` — esse fica reservado
para as regras de monitoramento (AC01-AC26), que podem coexistir com
as tarefas (uma pub de Distribuição com vara divergente recebe TC01
+ AC18, por exemplo).
"""
from __future__ import annotations

from typing import Any

from notion_rpadv.services.dje_notion_mappings import (
    mapear_tipo_comunicacao,
    mapear_tipo_documento,
)

from .tipos import TagApp

# ---------------------------------------------------------------------------
# Tag bases (sem sufixo " - App") — espelham as opções no Notion
# ---------------------------------------------------------------------------

TAG_TA01_ANALISAR_SENTENCA: str = "Analisar sentença"
TAG_TA02_ANALISAR_ACORDAO: str = "Analisar acórdão"
TAG_TC01_PROCESSO_RECURSO_DISTRIBUIDO: str = "Processo/recurso distribuído"
TAG_TC02_INCLUIR_JULGAMENTO_NO_CONTROLE: str = "Incluir julgamento no controle"


# ---------------------------------------------------------------------------
# TA01 / TA02 — Tarefa advogado
# ---------------------------------------------------------------------------


def regra_ta01_analisar_sentenca(
    publicacao: dict[str, Any],
) -> TagApp | None:
    """TA01 — Sentença em intimação: tarefa do advogado de analisar.

    Disparo: ``tipoComunicação = "Intimação"`` E ``tipoDocumento =
    "Sentença"``. Substitui a antiga Regra 42 (v8).
    """
    tipo_com = mapear_tipo_comunicacao(publicacao.get("tipoComunicacao"))
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_com == "Intimação" and tipo_doc == "Sentença":
        return TagApp(
            propriedade="Tarefa advogado",
            tag_base=TAG_TA01_ANALISAR_SENTENCA,
            regra="TA01",
        )
    return None


def regra_ta02_analisar_acordao(
    publicacao: dict[str, Any],
) -> TagApp | None:
    """TA02 — Acórdão ou Ementa em intimação: tarefa do advogado.

    Disparo: ``tipoComunicação = "Intimação"`` E
    ``tipoDocumento ∈ {Acórdão, Ementa}``. Substitui a antiga Regra 43
    (v8); Acórdão e Ementa compartilham a mesma tarefa porque são duas
    formas de comunicar o mesmo julgamento colegiado.
    """
    tipo_com = mapear_tipo_comunicacao(publicacao.get("tipoComunicacao"))
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_com == "Intimação" and tipo_doc in {"Acórdão", "Ementa"}:
        return TagApp(
            propriedade="Tarefa advogado",
            tag_base=TAG_TA02_ANALISAR_ACORDAO,
            regra="TA02",
        )
    return None


# ---------------------------------------------------------------------------
# TC01 / TC02 — Tarefa contadoria
# ---------------------------------------------------------------------------


def regra_tc01_distribuicao(
    publicacao: dict[str, Any],
) -> TagApp | None:
    """TC01 — Distribuição (inicial ou recursal): contadoria revisa.

    Disparo: ``tipoComunicação = "Lista de Distribuição"`` (qualquer
    tipoDocumento) **OU** ``tipoComunicação = "Intimação"`` E
    ``tipoDocumento = "Distribuição"``. Substitui a antiga Regra 40.

    Toda distribuição é evento estrutural — cadastrar processo novo
    se for inicial, atualizar instância/vara/relator se já existe.
    """
    tipo_com = mapear_tipo_comunicacao(publicacao.get("tipoComunicacao"))
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_com == "Lista de Distribuição":
        return TagApp(
            propriedade="Tarefa contadoria",
            tag_base=TAG_TC01_PROCESSO_RECURSO_DISTRIBUIDO,
            regra="TC01",
        )
    if tipo_com == "Intimação" and tipo_doc == "Distribuição":
        return TagApp(
            propriedade="Tarefa contadoria",
            tag_base=TAG_TC01_PROCESSO_RECURSO_DISTRIBUIDO,
            regra="TC01",
        )
    return None


def regra_tc02_pauta_julgamento(
    publicacao: dict[str, Any],
) -> TagApp | None:
    """TC02 — Pauta de Julgamento: contadoria precisa lançar no controle.

    Disparo: ``tipoDocumento = "Pauta de Julgamento"`` (qualquer tipo
    de comunicação — Edital ou Intimação). Substitui a antiga Regra 41.
    """
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc == "Pauta de Julgamento":
        return TagApp(
            propriedade="Tarefa contadoria",
            tag_base=TAG_TC02_INCLUIR_JULGAMENTO_NO_CONTROLE,
            regra="TC02",
        )
    return None
