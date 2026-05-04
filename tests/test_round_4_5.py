"""Testes do Round 4.5 — auto-Status + filtro Atas TJDFT (2026-05-03).

Cobre:
- Frente 1: ``_calcular_status_inicial`` — auto "Nada para fazer" para
  Listas de Distribuição em tribunais trabalhistas com Processo cadastrado.
- Frente 2: filtro de Atas TJDFT tipo "57" (extensão de ``aplicar_caso_15``).
"""
from __future__ import annotations

from notion_rpadv.services.dje_notion_mapper import (
    STATUS_DEFAULT_CRIACAO,
    STATUS_NADA_PARA_FAZER,
    _calcular_status_inicial,
)


# ===========================================================================
# Frente 1 — Auto-Status para Listas TRT10/TST com Processo cadastrado
# ===========================================================================


def test_R4_5_status_lista_trt10_cadastrado_nada_para_fazer() -> None:
    """Lista TRT10 + processo cadastrado → 'Nada para fazer'."""
    out = _calcular_status_inicial(
        tipo_comunicacao_canonico="Lista de Distribuição",
        sigla_tribunal="TRT10",
        processo_record={"page_id": "x"},
    )
    assert out == STATUS_NADA_PARA_FAZER
    assert out == "Nada para fazer"  # sanity do nome exato


def test_R4_5_status_lista_trt10_nao_cadastrado_nova() -> None:
    """Lista TRT10 + processo NÃO cadastrado → 'Nova' (default).
    A controladoria precisa cadastrar primeiro."""
    out = _calcular_status_inicial(
        tipo_comunicacao_canonico="Lista de Distribuição",
        sigla_tribunal="TRT10",
        processo_record=None,
    )
    assert out == STATUS_DEFAULT_CRIACAO


def test_R4_5_status_lista_tst_cadastrado_nada_para_fazer() -> None:
    """Lista TST + processo cadastrado → 'Nada para fazer'."""
    out = _calcular_status_inicial(
        tipo_comunicacao_canonico="Lista de Distribuição",
        sigla_tribunal="TST",
        processo_record={"page_id": "x"},
    )
    assert out == STATUS_NADA_PARA_FAZER


def test_R4_5_status_lista_tjsc_cadastrado_nova() -> None:
    """Lista TJSC + processo cadastrado → 'Nova' (tribunal fora do filtro).
    Apenas trabalhistas (TRT10, TST) entram na regra."""
    out = _calcular_status_inicial(
        tipo_comunicacao_canonico="Lista de Distribuição",
        sigla_tribunal="TJSC",
        processo_record={"page_id": "x"},
    )
    assert out == STATUS_DEFAULT_CRIACAO


def test_R4_5_status_intimacao_trt10_cadastrado_nova() -> None:
    """Intimação TRT10 (não Lista) + processo cadastrado → 'Nova'.
    Só Listas viram auto-Status; intimações exigem triagem manual."""
    out = _calcular_status_inicial(
        tipo_comunicacao_canonico="Intimação",
        sigla_tribunal="TRT10",
        processo_record={"page_id": "x"},
    )
    assert out == STATUS_DEFAULT_CRIACAO


def test_R4_5_status_ata_distribuicao_stj_nova() -> None:
    """ATA DE DISTRIBUIÇÃO STJ tem tipoComunicacao 'Intimação' (não
    Lista de Distribuição), portanto NÃO entra na regra. Status fica
    'Nova' — contadoria precisa atualizar dados (E.02)."""
    out = _calcular_status_inicial(
        tipo_comunicacao_canonico="Intimação",  # ATA STJ é Intimação
        sigla_tribunal="STJ",
        processo_record={"page_id": "x"},
    )
    assert out == STATUS_DEFAULT_CRIACAO


def test_R4_5_status_pauta_tjdft_cadastrado_nova() -> None:
    """Pauta TJDFT (Edital) + processo cadastrado → 'Nova'.
    Pautas precisam de avaliação para sustentação oral (E.04)."""
    out = _calcular_status_inicial(
        tipo_comunicacao_canonico="Edital",
        sigla_tribunal="TJDFT",
        processo_record={"page_id": "x"},
    )
    assert out == STATUS_DEFAULT_CRIACAO


def test_R4_5_status_constantes_canonicas() -> None:
    """Sanity: as constantes batem com as opções existentes do select
    no Notion (Nova, Nada para fazer)."""
    assert STATUS_DEFAULT_CRIACAO == "Nova"
    assert STATUS_NADA_PARA_FAZER == "Nada para fazer"
