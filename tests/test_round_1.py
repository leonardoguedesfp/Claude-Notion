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
from notion_rpadv.services.dje_text_pipeline import (
    LIMITE_BLOCOS_INICIAIS,
    NOTION_BLOCK_HARD_LIMIT,
    preprocessar_texto_djen,
    quebrar_em_blocos,
    truncar_texto_inline,
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


# ===========================================================================
# 1.7 — Pré-processador HTML
# ===========================================================================


def test_R1_7_html_unescape_basico() -> None:
    """``html.unescape`` cobre as entities mais comuns do DJEN."""
    assert preprocessar_texto_djen("&amp;") == "&"
    # &nbsp; vira espaço (após normalização)
    assert preprocessar_texto_djen("a&nbsp;b") == "a b"


def test_R1_7_br_vira_quebra_de_linha() -> None:
    assert preprocessar_texto_djen("linha1<br>linha2") == "linha1\nlinha2"
    assert preprocessar_texto_djen("linha1<br />linha2") == "linha1\nlinha2"
    assert preprocessar_texto_djen("linha1<BR/>linha2") == "linha1\nlinha2"


def test_R1_7_link_simplificado_quando_texto_eh_url() -> None:
    """``<a href="X">X</a>`` → ``"X"`` (sem duplicar)."""
    s = preprocessar_texto_djen('<a href="https://x.com">https://x.com</a>')
    assert s == "https://x.com"


def test_R1_7_link_com_texto_diferente() -> None:
    """``<a href="X">Y</a>`` → ``"Y (X)"``."""
    s = preprocessar_texto_djen('<a href="https://x.com">clique aqui</a>')
    assert s == "clique aqui (https://x.com)"


def test_R1_7_escape_duplo_desfeito() -> None:
    """DJEN às vezes serializa ``\\<br\\>`` por dupla camada de escape;
    preprocessador desfaz pra que o BR seja interpretado."""
    assert preprocessar_texto_djen("a\\<br\\>b") == "a\nb"


def test_R1_7_tags_residuais_removidas() -> None:
    s = preprocessar_texto_djen('<p><strong>Atenção</strong>: aviso</p>')
    assert s == "Atenção: aviso"


def test_R1_7_normaliza_espacos_e_quebras() -> None:
    """Múltiplos espaços colapsam pra 1; 3+ quebras viram 2."""
    s = preprocessar_texto_djen("a    b\n\n\n\nc")
    assert s == "a b\n\nc"


def test_R1_7_none_e_vazio_devolvem_string_vazia() -> None:
    assert preprocessar_texto_djen(None) == ""
    assert preprocessar_texto_djen("") == ""
    assert preprocessar_texto_djen("   ") == ""


def test_R1_7_publicacao_dje_real_pattern() -> None:
    """Padrão real visto em pautas TJDFT em produção (HTML cru com
    span+br+nbsp)."""
    bruto = (
        '<p><span style="font-size: medium;">VITOR GUEDES DA FONSECA PASSOS '
        '- DF48468-A<br />LEONARDO GUEDES DA FONSECA PASSOS - DF36129</span></p>'
    )
    s = preprocessar_texto_djen(bruto)
    assert "VITOR GUEDES" in s
    assert "DF48468-A" in s
    assert "DF36129" in s
    # BR virou \n entre os dois nomes
    assert "VITOR GUEDES DA FONSECA PASSOS - DF48468-A\nLEONARDO" in s


def test_R1_7_idempotente_em_texto_limpo() -> None:
    """Texto sem HTML passa intacto (modulo stripping/normalization)."""
    limpo = "Texto puro sem HTML."
    assert preprocessar_texto_djen(limpo) == limpo


# ===========================================================================
# 1.8 — Truncamento limpo do campo Texto inline
# ===========================================================================


def test_R1_8_curto_passa_intacto() -> None:
    assert truncar_texto_inline("texto curto") == "texto curto"
    assert truncar_texto_inline("a" * 2000, limite=2000) == "a" * 2000


def test_R1_8_corta_em_palavra() -> None:
    """Não termina no meio da palavra — busca último espaço dentro de janela."""
    texto = "Embargos de declaração conhecidos e parcialmente acolhidos para " * 100
    truncado = truncar_texto_inline(texto, limite=100)
    assert len(truncado) <= 100
    # Termina com o marcador
    assert truncado.endswith(" […]")
    # Não corta no meio de uma palavra
    assert not truncado[: -len(" […]")].rstrip().endswith(("parcialme", "decla", "Embar"))


def test_R1_8_marcador_conta_no_limite() -> None:
    """Output total ≤ limite (marcador entra na conta)."""
    out = truncar_texto_inline("a " * 5000, limite=50)
    assert len(out) <= 50


def test_R1_8_none_e_vazio_devolvem_string_vazia() -> None:
    assert truncar_texto_inline(None) == ""
    assert truncar_texto_inline("") == ""


def test_R1_8_marcador_customizado() -> None:
    out = truncar_texto_inline("palavras " * 200, limite=50, marcador="...")
    assert out.endswith("...")
    assert len(out) <= 50


def test_R1_8_sem_espacos_corta_cru() -> None:
    """Texto sem espaços (cenário patológico) corta no meio mesmo."""
    out = truncar_texto_inline("a" * 5000, limite=20)
    assert len(out) <= 20


# ===========================================================================
# 1.4 — Block split com detecção de seções
# ===========================================================================


def test_R1_4_split_em_secoes_logicas() -> None:
    """Acórdão com RELATÓRIO + VOTO gera 2 heading_3 (1 por seção)."""
    texto = "RELATÓRIO\n\nIsso é o relatório.\n\nVOTO\n\nEsse é o voto."
    blocos = quebrar_em_blocos(texto)
    headings = [b for b in blocos if b["type"] == "heading_3"]
    assert len(headings) == 2
    titulos = [
        h["heading_3"]["rich_text"][0]["text"]["content"]
        for h in headings
    ]
    assert titulos == ["RELATÓRIO", "VOTO"]


def test_R1_4_secoes_caps_insensitive() -> None:
    """Seções podem aparecer em casing variado — detector é case-insensitive."""
    texto = "ementa\n\nUma ementa.\n\nVoto\n\nUm voto."
    blocos = quebrar_em_blocos(texto)
    headings = [b for b in blocos if b["type"] == "heading_3"]
    titulos = [h["heading_3"]["rich_text"][0]["text"]["content"] for h in headings]
    # Output sempre uppercase canônico.
    assert titulos == ["EMENTA", "VOTO"]


def test_R1_4_preambulo_antes_da_primeira_secao() -> None:
    """Texto antes da 1ª seção (preâmbulo) entra como paragraph SEM heading."""
    texto = "Cabeçalho do acórdão.\n\nEMENTA\n\nA ementa."
    blocos = quebrar_em_blocos(texto)
    # 1º bloco é paragraph (preâmbulo), depois vem o heading_3 EMENTA.
    assert blocos[0]["type"] == "paragraph"
    assert "Cabeçalho" in blocos[0]["paragraph"]["rich_text"][0]["text"]["content"]
    assert blocos[1]["type"] == "heading_3"


def test_R1_4_sem_secoes_so_paragraphs() -> None:
    """Texto sem keywords de seção → só paragraphs, sem heading."""
    texto = "Parágrafo 1.\n\nParágrafo 2.\n\nParágrafo 3."
    blocos = quebrar_em_blocos(texto)
    types = {b["type"] for b in blocos}
    assert types == {"paragraph"}


def test_R1_4_paragrafo_longo_e_split_sem_perda() -> None:
    """Parágrafo único > 2000 chars vira múltiplos blocks SEM perder
    conteúdo (vs. truncar)."""
    texto = "x" * 5500
    blocos = quebrar_em_blocos(texto)
    paragraphs = [b for b in blocos if b["type"] == "paragraph"]
    total_chars = sum(
        len(b["paragraph"]["rich_text"][0]["text"]["content"])
        for b in paragraphs
    )
    # Tolera diff de quebras inseridas; não pode haver mais de 5% de perda.
    assert total_chars >= 5500 * 0.95
    # Cada bloco respeita o limite duro do Notion.
    for b in paragraphs:
        assert len(b["paragraph"]["rich_text"][0]["text"]["content"]) <= NOTION_BLOCK_HARD_LIMIT


def test_R1_4_500_paragrafos_curtos_agrupam_sob_100_blocos() -> None:
    """Spec: 500 parágrafos curtos NÃO devem virar 500 blocos —
    agrupamento até ~1500 chars de buffer."""
    texto = "\n\n".join([f"Parágrafo {i} com algum texto." for i in range(500)])
    blocos = quebrar_em_blocos(texto)
    # Sem heading_3 esperado (não há keywords). Total deve ser razoável.
    assert len(blocos) < 200  # margem larga
    assert all(b["type"] == "paragraph" for b in blocos)


def test_R1_4_texto_vazio_devolve_lista_vazia() -> None:
    assert quebrar_em_blocos("") == []
    assert quebrar_em_blocos(None) == []
    assert quebrar_em_blocos("   ") == []


def test_R1_4_cada_bloco_respeita_limite_2000() -> None:
    """Sanity duro: nenhum bloco gerado pode exceder NOTION_BLOCK_HARD_LIMIT."""
    texto = ("a" * 1900 + "\n\n") * 10 + "RELATÓRIO\n\n" + ("b" * 1900 + "\n\n") * 5
    blocos = quebrar_em_blocos(texto)
    for b in blocos:
        if b["type"] == "paragraph":
            content = b["paragraph"]["rich_text"][0]["text"]["content"]
        elif b["type"] == "heading_3":
            content = b["heading_3"]["rich_text"][0]["text"]["content"]
        else:
            content = ""
        assert len(content) <= NOTION_BLOCK_HARD_LIMIT


def test_R1_4_limite_blocos_iniciais_e_90() -> None:
    """Sanity: constante usada pelo overflow API é 90 (margem de 10 do
    limite duro 100 do Notion)."""
    assert LIMITE_BLOCOS_INICIAIS == 90
