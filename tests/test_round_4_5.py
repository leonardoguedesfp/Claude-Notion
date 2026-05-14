"""Testes do Round 4.5 — Status default + filtro Atas TJDFT (2026-05-03).

Round 11 (2026-05-13): a Frente 1 original deste round criava o auto-
Status ``Nada para fazer`` para Listas de Distribuição em TRT10/TST com
Processo cadastrado. Esse valor foi removido do select ``Status`` no
Notion — semântica passou para ``Conclusão automática`` (classificador).
Os testes desta frente foram removidos; resta sanity check do default.

Continua válida:
- Frente 2: filtro de Atas TJDFT tipo "57" (extensão de ``aplicar_caso_15``).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from notion_rpadv.services.dje_notion_mapper import STATUS_DEFAULT_CRIACAO
from notion_rpadv.services.dje_text_pipeline import (
    aplicar_caso_15,
    deve_filtrar_ata_tjdft,
    filtrar_ata_tjdft_57,
    preprocessar_texto_djen,
)


# ===========================================================================
# Frente 1 — Status default na criação (Round 11)
# ===========================================================================


def test_R11_status_default_e_nova() -> None:
    """Round 11: o único valor possível na criação é ``Nova``. O valor
    ``Nada para fazer`` foi removido do select do Notion — semântica
    passou para ``Conclusão automática`` (classificador)."""
    assert STATUS_DEFAULT_CRIACAO == "Nova"


# ===========================================================================
# Frente 2 — Filtro Atas TJDFT (tipoDocumento bruto = "57")
# ===========================================================================


# Helper: monta texto sintético de Ata TJDFT tipo 57 com lista de CNJs.
def _ata_57_sintetica(cnjs_julgados: list[str]) -> str:
    lista = "\n".join(f" {cnj}" for cnj in cnjs_julgados)
    return (
        "Poder Judiciário da União\n"
        "TRIBUNAL DE JUSTIÇA DO DISTRITO FEDERAL E DOS TERRITÓRIOS\n\n"
        "1ª Turma Cível\n"
        "1ª Sessão Ordinária Virtual - 1TCV (período 21 a 28/1/2026)\n\n"
        "Ata da 1ª Sessão Ordinária Virtual da Primeira Turma Cível, "
        "sob a presidência do Excelentíssimo Senhor Desembargador "
        "FABRICIO FONTOURA BEZERRA…\n"
        "Lida e aprovada a ata da sessão anterior, foram julgados "
        f"{len(cnjs_julgados)} processos abaixo relacionados:\n"
        f"\n JULGADOS\n{lista}\n"
        "\nEu, Secretária de Sessão, lavrei a presente ata.\n"
    )


def test_R4_5_F2_deve_filtrar_ata_tjdft_57() -> None:
    """Trigger: TJDFT + tipoDocumento bruto '57'."""
    assert deve_filtrar_ata_tjdft("TJDFT", "57") is True
    # Variantes de casing/whitespace no tribunal
    assert deve_filtrar_ata_tjdft("tjdft", "57") is True
    assert deve_filtrar_ata_tjdft("  TJDFT ", "57") is True
    # Tribunal diferente: não filtra
    assert deve_filtrar_ata_tjdft("STJ", "57") is False
    # Tipo diferente: não filtra
    assert deve_filtrar_ata_tjdft("TJDFT", "Pauta de Julgamento") is False
    assert deve_filtrar_ata_tjdft("TJDFT", "Outros") is False
    # Inputs nulos: não filtra
    assert deve_filtrar_ata_tjdft(None, None) is False
    assert deve_filtrar_ata_tjdft("TJDFT", None) is False
    assert deve_filtrar_ata_tjdft(None, "57") is False


def test_R4_5_F2_filtrar_ata_cnj_no_meio_da_lista() -> None:
    """Caso 1: CNJ do escritório está no meio da lista — preservado."""
    cnj_alvo = "0707739-37.2025.8.07.0001"
    cnjs = [
        "0716816-23.2019.8.07.0020",
        "0711719-65.2020.8.07.0001",
        cnj_alvo,
        "0734331-83.2023.8.07.0003",
        "0022530-04.2015.8.07.0001",
    ]
    texto = _ata_57_sintetica(cnjs)
    out = filtrar_ata_tjdft_57(texto, cnj_alvo)
    assert out is not None
    # Cabeçalho preservado
    assert "TRIBUNAL DE JUSTIÇA DO DISTRITO FEDERAL" in out
    assert "1ª Sessão Ordinária Virtual" in out
    # Nota explicativa
    assert "[Ata filtrada automaticamente: 1 de 5 processos pertence ao escritório" in out
    # CNJ alvo presente, demais ausentes
    assert cnj_alvo in out
    for cnj in cnjs:
        if cnj != cnj_alvo:
            assert cnj not in out
    # Trailer preservado
    assert "lavrei a presente ata" in out


def test_R4_5_F2_filtrar_ata_cnj_no_final_da_lista_preservado() -> None:
    """Caso 2: CNJ no final da lista (após posição que cairia em
    truncamento simples) — ainda filtrado e preservado."""
    cnj_alvo = "0709464-61.2025.8.07.0001"
    # Simula 50 CNJs, alvo no fim
    cnjs = [f"071{i:04d}-99.2024.8.07.0001" for i in range(49)] + [cnj_alvo]
    texto = _ata_57_sintetica(cnjs)
    out = filtrar_ata_tjdft_57(texto, cnj_alvo)
    assert out is not None
    assert cnj_alvo in out
    assert "1 de 50 processos" in out


def test_R4_5_F2_filtrar_ata_cnj_nao_na_lista_devolve_none() -> None:
    """Caso 3 (caso real djen=525274051): CNJ payload NÃO está na lista
    de JULGADOS — função devolve None, caller faz fallback."""
    cnjs = [
        "0716816-23.2019.8.07.0020",
        "0711719-65.2020.8.07.0001",
    ]
    texto = _ata_57_sintetica(cnjs)
    cnj_fora_da_lista = "9999999-99.9999.9.99.9999"
    assert filtrar_ata_tjdft_57(texto, cnj_fora_da_lista) is None


def test_R4_5_F2_filtrar_ata_sem_julgados_devolve_none() -> None:
    """Texto sem 'JULGADOS' (parsing falha) → devolve None."""
    texto = "Texto qualquer sem o marcador esperado.\n0001234-56.2025.8.07.0001"
    assert filtrar_ata_tjdft_57(texto, "0001234-56.2025.8.07.0001") is None


def test_R4_5_F2_filtrar_ata_cnj_escritorio_none_devolve_none() -> None:
    """``cnj_escritorio=None`` (sem CNJ no payload) → devolve None."""
    texto = _ata_57_sintetica(["0001234-56.2025.8.07.0001"])
    assert filtrar_ata_tjdft_57(texto, None) is None


def test_R4_5_F2_aplicar_caso_15_ata_tjdft_57_filtrada() -> None:
    """Wire: aplicar_caso_15 com tipo_documento_bruto='57' + CNJ válido
    aciona o filtro Frente 2 e devolve texto filtrado SEM callout."""
    cnj_alvo = "0001234-56.2025.8.07.0001"
    texto = _ata_57_sintetica([
        "0700000-01.2025.8.07.0001",
        cnj_alvo,
        "0700000-02.2025.8.07.0001",
    ])
    corpo, callouts = aplicar_caso_15(
        tribunal="TJDFT",
        tipo_documento="Outros",  # canon do tipo "57"
        texto=texto,
        hash_djen="abc",
        tipo_documento_bruto="57",
        cnj_escritorio=cnj_alvo,
    )
    assert "[Ata filtrada automaticamente: 1 de 3 processos" in corpo
    assert cnj_alvo in corpo
    assert callouts == []  # filtragem é suficiente


def test_R4_5_F2_aplicar_caso_15_ata_57_cnj_fora_da_lista_cai_caso_b() -> None:
    """Quando o filtro Ata 57 retorna None (CNJ não na lista), o pipeline
    cai pro caso B (truncamento + callout, ou passa intacto se cabe)."""
    cnj_alvo = "9999999-99.9999.9.99.9999"  # não está na lista
    texto = _ata_57_sintetica([
        "0700000-01.2025.8.07.0001",
        "0700000-02.2025.8.07.0001",
    ])  # texto curto — passa intacto no caso B
    corpo, callouts = aplicar_caso_15(
        tribunal="TJDFT",
        tipo_documento="Outros",
        texto=texto,
        hash_djen="abc",
        tipo_documento_bruto="57",
        cnj_escritorio=cnj_alvo,
    )
    # Texto bruto preservado (sem nota de filtragem)
    assert "[Ata filtrada" not in corpo
    assert corpo == texto  # passou intacto
    assert callouts == []


def test_R4_5_F2_aplicar_caso_15_pauta_tjdft_NAO_dispara_frente_2() -> None:
    """Pauta TJDFT (tipo bruto = 'PAUTA DE JULGAMENTOS' ou 'Pauta de
    Julgamento', não '57'): fluxo antigo (caso A do Round 1) preservado.
    Frente 2 não interfere."""
    # Pauta sintética com bloco "Processo\n{CNJ}" (formato Round 1)
    pauta = (
        "TJDFT - Pauta de Julgamentos da 5ª Turma Cível\n\n"
        "Processo\n0001234-56.2025.8.07.0001\n\n"
        "Polo Ativo: BANCO TESTE\n"
        "Advogado(s) - Polo Ativo: NOME ADVOGADO - DF15523-A\n"
    ) + ("x" * 6000)  # padding pra ultrapassar 5KB
    corpo, callouts = aplicar_caso_15(
        tribunal="TJDFT",
        tipo_documento="Pauta de Julgamento",
        texto=pauta,
        hash_djen="abc",
        tipo_documento_bruto="Pauta de Julgamento",
        cnj_escritorio="0001234-56.2025.8.07.0001",
    )
    # Caso A do Round 1 deve ter disparado (regex Processo\n{CNJ} acha)
    assert "[Pauta filtrada automaticamente:" in corpo
    assert "[Ata filtrada" not in corpo  # frente 2 não disparou
    assert callouts == []


def test_R4_5_F2_aplicar_caso_15_ementa_tjdft_NAO_dispara_frente_2() -> None:
    """Ementa TJDFT (tipo bruto != '57'): fluxo Round 1 preservado.
    Texto pequeno passa intacto, sem callout."""
    texto = (
        "Ementa: Direito civil. Apelação cível…\n\n"
        "I. Caso em exame\n1. Cuida-se de apelação interposta…"
    )
    corpo, callouts = aplicar_caso_15(
        tribunal="TJDFT",
        tipo_documento="Ementa",
        texto=texto,
        hash_djen="abc",
        tipo_documento_bruto="Ementa",
        cnj_escritorio="0001234-56.2025.8.07.0001",
    )
    assert corpo == texto
    assert callouts == []


def test_R4_5_F2_aplicar_caso_15_ata_57_kwargs_ausentes_passa_intacto() -> None:
    """Backward-compat: caller que NÃO passa tipo_documento_bruto nem
    cnj_escritorio (callers antigos) não dispara frente 2 — texto cai
    no caso B normal. Garante que mudança de assinatura não quebra
    chamadas existentes."""
    texto = "Qualquer texto curto sem JULGADOS"
    corpo, callouts = aplicar_caso_15(
        tribunal="TJDFT",
        tipo_documento="Outros",
        texto=texto,
        hash_djen="abc",
    )
    assert corpo == texto
    assert callouts == []


# ---------------------------------------------------------------------------
# Smoke real contra SQLite local (dados de produção do Round 3)
# ---------------------------------------------------------------------------


_PROD_DB = Path.home() / "AppData/Roaming/NotionRPADV/leitor_dje.db"


def _carregar_pub_real(djen_id: int) -> dict:
    if not _PROD_DB.exists():
        pytest.skip(f"SQLite real ausente em {_PROD_DB}")
    conn = sqlite3.connect(f"file:{_PROD_DB}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT payload_json FROM publicacoes WHERE djen_id=?",
            (djen_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        pytest.skip(f"djen={djen_id} ausente do banco real")
    return json.loads(row[0])


def test_R4_5_F2_smoke_djen_524038068_ata_filtrada() -> None:
    """djen=524038068 (1ª Turma Cível, 240 julgados): filtro Frente 2
    preserva CNJ payload e reduz drasticamente o tamanho."""
    pub = _carregar_pub_real(524038068)
    pre = preprocessar_texto_djen(pub.get("texto") or "")
    cnj = pub.get("numeroprocessocommascara") or pub.get("numero_processo")
    out = filtrar_ata_tjdft_57(pre, cnj)
    assert out is not None
    assert cnj in out
    assert "[Ata filtrada automaticamente: 1 de" in out
    assert len(out) < len(pre) * 0.3  # redução substancial


def test_R4_5_F2_smoke_djen_525274051_cnj_fora_fallback() -> None:
    """djen=525274051: CNJ payload NÃO está na lista de JULGADOS — filtro
    retorna None, pipeline cai no caso B."""
    pub = _carregar_pub_real(525274051)
    pre = preprocessar_texto_djen(pub.get("texto") or "")
    cnj = pub.get("numeroprocessocommascara") or pub.get("numero_processo")
    out = filtrar_ata_tjdft_57(pre, cnj)
    assert out is None  # fallback gracioso


def test_R4_5_F2_smoke_djen_542171781_ata_pequena_filtrada() -> None:
    """djen=542171781 (5ª Turma Cível Presencial, 44 julgados): texto
    curto que cabia no limite, mas Frente 2 ainda filtra pra reduzir."""
    pub = _carregar_pub_real(542171781)
    pre = preprocessar_texto_djen(pub.get("texto") or "")
    cnj = pub.get("numeroprocessocommascara") or pub.get("numero_processo")
    out = filtrar_ata_tjdft_57(pre, cnj)
    assert out is not None
    assert cnj in out
    assert "1 de 44 processos" in out
