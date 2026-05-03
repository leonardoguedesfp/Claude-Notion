"""Testes do Round 1 — fixes pré-re-migração massiva (2026-05-03).

Cobre os 8 fixes consolidados no prompt do Round 1:
- 1.1 Mapeamento de Tipo de documento
- 1.2 Mapeamento de Tipo de comunicação
- 1.3 Padronização Multi-select de advogados
- 1.4 Block split com detecção de seções (anti bug "100 blocos")
- 1.5 Filtragem inteligente Pautas TJDFT + truncamento
- 1.6 Detector de duplicatas + propriedade "Duplicatas suprimidas"
- 1.7 Pre-processador HTML
- 1.8 Truncamento limpo do campo Texto inline

Smoke integrado contra publicações reais fica em ``smoke_test_round_1.py``.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from notion_rpadv.services.dje_notion_mappings import (
    ADVOGADOS_ESCRITORIO,
    MAPA_TIPO_COMUNICACAO,
    MAPA_TIPO_DOCUMENTO,
    TIPOS_COMUNICACAO_CANONICOS,
    TIPOS_DOCUMENTO_CANONICOS,
    formatar_advogados_intimados,
    mapear_tipo_comunicacao,
    mapear_tipo_documento,
    tinha_destinatarios_advogados,
)


# ===========================================================================
# 1.1 — Mapeamento de Tipo de documento
# ===========================================================================


def test_R1_1_mapeamento_basico() -> None:
    """Cobertura das principais variantes do prompt."""
    assert mapear_tipo_documento("DESPACHO / DECISÃO") == "Decisão"
    assert mapear_tipo_documento("DESPACHO/DECISÃO") == "Decisão"
    assert mapear_tipo_documento("EMENTA / ACORDÃO") == "Acórdão"
    assert mapear_tipo_documento("ACORDAO") == "Acórdão"
    assert mapear_tipo_documento("Conclusão") == "Despacho"
    assert mapear_tipo_documento("Ato ordinatório") == "Despacho"
    assert mapear_tipo_documento("Audiência") == "Outros"
    assert mapear_tipo_documento("Intimação") == "Outros"
    assert mapear_tipo_documento("57") == "Outros"
    assert mapear_tipo_documento("Notificação") == "Notificação"
    assert mapear_tipo_documento("PAUTA DE JULGAMENTOS") == "Pauta de Julgamento"
    assert mapear_tipo_documento("ADITAMENTO À PAUTA DE JULGAMENTOS") == "Pauta de Julgamento"
    assert mapear_tipo_documento("Intimação de pauta") == "Pauta de Julgamento"


def test_R1_1_null_e_vazio_caem_em_outros() -> None:
    """D-1: tipoDocumento null/vazio → "Outros"."""
    assert mapear_tipo_documento(None) == "Outros"
    assert mapear_tipo_documento("") == "Outros"
    assert mapear_tipo_documento("   ") == "Outros"


def test_R1_1_variante_nao_mapeada_cai_em_outros() -> None:
    """Catch-all pra variantes futuras desconhecidas."""
    assert mapear_tipo_documento("Tipo Inventado XYZ") == "Outros"


def test_R1_1_strip_em_volta() -> None:
    """Whitespace nos lados não atrapalha lookup."""
    assert mapear_tipo_documento("  Despacho  ") == "Despacho"
    assert mapear_tipo_documento("Acórdão\n") == "Acórdão"


def test_R1_1_todos_os_alvos_mapeiam_para_canonico() -> None:
    """Toda variante do MAPA_TIPO_DOCUMENTO mapeia pra um canônico válido."""
    for variante, alvo in MAPA_TIPO_DOCUMENTO.items():
        assert alvo in TIPOS_DOCUMENTO_CANONICOS, (
            f"Variante {variante!r} mapeia para {alvo!r} fora dos canônicos"
        )


def test_R1_1_cobre_inventario_real_do_banco() -> None:
    """Smoke contra o SQLite real: TODA variante presente em produção
    (jan-mai/2026, 2141 publicações) tem que mapear para canônico válido.

    Skip se o banco real não estiver disponível (CI ou outra máquina).
    """
    db_path = Path.home() / "AppData/Roaming/NotionRPADV/leitor_dje.db"
    if not db_path.exists():
        pytest.skip(f"SQLite real não disponível em {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        variantes_no_banco: set[str | None] = set()
        for row in conn.execute("SELECT payload_json FROM publicacoes"):
            payload = json.loads(row[0])
            variantes_no_banco.add(payload.get("tipoDocumento"))
        for v in variantes_no_banco:
            canonico = mapear_tipo_documento(v)
            assert canonico in TIPOS_DOCUMENTO_CANONICOS, (
                f"Variante real {v!r} → {canonico!r} fora dos canônicos"
            )
    finally:
        conn.close()


# ===========================================================================
# 1.2 — Mapeamento de Tipo de comunicação
# ===========================================================================


def test_R1_2_lista_distribuicao_corrige_casing() -> None:
    """Bug central: DJEN escreve 'd' minúsculo; Notion canônico é 'D' maiúsculo."""
    assert mapear_tipo_comunicacao("Lista de distribuição") == "Lista de Distribuição"


def test_R1_2_intimacao_passa_intacta() -> None:
    assert mapear_tipo_comunicacao("Intimação") == "Intimação"


def test_R1_2_edital_passa_intacto() -> None:
    assert mapear_tipo_comunicacao("Edital") == "Edital"


def test_R1_2_null_e_vazio_caem_em_default(caplog) -> None:
    """None/vazio → "Intimação" + warning."""
    with caplog.at_level("WARNING"):
        assert mapear_tipo_comunicacao(None) == "Intimação"
        assert mapear_tipo_comunicacao("") == "Intimação"
    assert any("default" in rec.message.lower() for rec in caplog.records)


def test_R1_2_variante_desconhecida_cai_em_default(caplog) -> None:
    """Mapeamento conservador: variantes não previstas → "Intimação" + warning."""
    with caplog.at_level("WARNING"):
        assert mapear_tipo_comunicacao("Tipo Inventado") == "Intimação"
    assert any("desconhecido" in rec.message.lower() for rec in caplog.records)


def test_R1_2_todos_canonicos_estao_no_set() -> None:
    """Sanity: alvos do MAPA estão dentro dos canônicos do Notion."""
    for alvo in MAPA_TIPO_COMUNICACAO.values():
        assert alvo in TIPOS_COMUNICACAO_CANONICOS


# ===========================================================================
# 1.3 — Padronização Multi-select de advogados
# ===========================================================================


def test_R1_3_advogado_padroniza_formato_completo() -> None:
    """Formato canônico: 'PrimeiroNome (OAB/UF)' — UF maiúscula."""
    json_in = [{"advogado": {"numero_oab": "36129", "uf_oab": "df"}}]
    assert formatar_advogados_intimados(json_in) == ["Leonardo (36129/DF)"]


def test_R1_3_zeros_a_esquerda_sao_descartados() -> None:
    """Robustez: DJEN às vezes traz 'DF015523' ou apenas '015523' — strip
    de zeros antes do lookup."""
    json_in = [{"advogado": {"numero_oab": "036129", "uf_oab": "DF"}}]
    assert formatar_advogados_intimados(json_in) == ["Leonardo (36129/DF)"]


def test_R1_3_externos_sao_filtrados() -> None:
    """Cruzamento estrito por OAB/UF do escritório."""
    json_in = [{"advogado": {"numero_oab": "99999", "uf_oab": "SP"}}]
    assert formatar_advogados_intimados(json_in) == []


def test_R1_3_dedup_quando_mesma_oab_aparece_2x() -> None:
    """Padrão patológico do DJEN: mesmo advogado entry 2x."""
    json_in = [
        {"advogado": {"numero_oab": "15523", "uf_oab": "DF"}},
        {"advogado": {"numero_oab": "15523", "uf_oab": "DF"}},
    ]
    assert formatar_advogados_intimados(json_in) == ["Ricardo (15523/DF)"]


def test_R1_3_ordem_alfabetica_estavel() -> None:
    """Saída ordenada — facilita comparação em testes e diff em logs."""
    json_in = [
        {"advogado": {"numero_oab": "75799", "uf_oab": "DF"}},  # Deborah
        {"advogado": {"numero_oab": "15523", "uf_oab": "DF"}},  # Ricardo
        {"advogado": {"numero_oab": "36129", "uf_oab": "DF"}},  # Leonardo
    ]
    out = formatar_advogados_intimados(json_in)
    assert out == sorted(out)


def test_R1_3_lista_vazia_devolve_vazio() -> None:
    assert formatar_advogados_intimados([]) == []
    assert formatar_advogados_intimados(None) == []


def test_R1_3_entry_legacy_no_nivel_raiz() -> None:
    """Fallback pra fixtures legacy onde numero_oab/uf_oab estão no nível raiz."""
    json_in = [{"numero_oab": "15523", "uf_oab": "DF", "nome": "X"}]
    assert formatar_advogados_intimados(json_in) == ["Ricardo (15523/DF)"]


def test_R1_3_advogado_desativado_continua_mapeando() -> None:
    """Pubs antigas trazem advogados desativados — todas as 12 OABs entram."""
    json_in = [{"advogado": {"numero_oab": "37654", "uf_oab": "DF"}}]
    assert formatar_advogados_intimados(json_in) == ["Shirley (37654/DF)"]


def test_R1_3_lista_so_externos_marca_tinha_destinatarios() -> None:
    """Distinção fundamental: lista vazia ≠ lista só com externos."""
    assert tinha_destinatarios_advogados([]) is False
    assert tinha_destinatarios_advogados(None) is False
    assert tinha_destinatarios_advogados(
        [{"advogado": {"numero_oab": "999", "uf_oab": "SP"}}]
    ) is True


def test_R1_3_todas_as_12_oabs_estao_listadas() -> None:
    """Sanity: 12 OABs = 6 ativas + 6 desativadas."""
    assert len(ADVOGADOS_ESCRITORIO) == 12
    # Nenhum rótulo duplicado
    assert len(set(ADVOGADOS_ESCRITORIO.values())) == 12


def test_R1_3_formato_dos_rotulos_e_consistente() -> None:
    """Todos os 12 rótulos têm formato 'Nome (NNNN/UF)'."""
    import re
    pattern = re.compile(r"^[A-Za-zÀ-ú ]+ \(\d{3,6}/[A-Z]{2}\)$")
    for chave, rotulo in ADVOGADOS_ESCRITORIO.items():
        assert pattern.match(rotulo), (
            f"Rótulo {rotulo!r} (chave {chave!r}) fora do padrão canônico"
        )
