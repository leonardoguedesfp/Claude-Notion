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
import re
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from notion_bulk_edit.notion_api import NotionAPIError, NotionClient
from notion_rpadv.services import dje_db
from notion_rpadv.services.dje_dedup import (
    TipoDestino,
    _merge_advogados,
    _merge_partes,
    calcular_chave_canonica,
    calcular_chave_para_publicacao,
    determinar_destino,
    flush_atualizacoes_canonicas,
    marcar_como_canonica,
    marcar_como_duplicata,
)
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
from notion_rpadv.services.dje_notion_sync import sincronizar_pendentes
from notion_rpadv.services.dje_text_pipeline import (
    LIMITE_BLOCOS_INICIAIS,
    LIMITE_TRUNCAMENTO_BYTES,
    NOTION_BLOCK_HARD_LIMIT,
    aplicar_caso_15,
    deve_filtrar_pauta_tjdft,
    filtrar_pauta_tjdft,
    preprocessar_texto_djen,
    quebrar_em_blocos,
    truncar_corpo_simples,
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


# ===========================================================================
# 1.5 — Filtragem inteligente Pautas TJDFT + Truncamento simples
# ===========================================================================


def _pauta_sintetica(processos: list[tuple[str, list[str]]]) -> str:
    """Gera uma pauta TJDFT sintética com formato real do DJEN
    (após 1.7). Cada tupla é (cnj, [oab1, oab2, ...]) — OABs no formato
    'DF15523-A' ou similar."""
    cabecalho = (
        "TRIBUNAL DE JUSTIÇA DO DISTRITO FEDERAL E TERRITÓRIOS\n"
        "PAUTA DE JULGAMENTOS - 1ª Turma Cível\n"
        "Sessão Virtual de 12/05/2026 a 19/05/2026\n"
    )
    blocos = []
    for cnj, oabs in processos:
        oab_str = "\n".join([f"NOME ADVOGADO {i + 1} - {oab}" for i, oab in enumerate(oabs)])
        bloco = (
            f"\nProcesso\n{cnj}\n\n"
            f"Número de ordem\n1\n\n"
            f"Órgão julgador\nGabinete Teste\n\n"
            f"Polo Ativo\nPARTE TESTE\n\n"
            f"Advogado(s) - Polo Ativo\n{oab_str}\n"
        )
        blocos.append(bloco)
    return cabecalho + "".join(blocos) + "\n"


def test_R1_5_deve_filtrar_so_em_pauta_tjdft_grande() -> None:
    """Trigger: TJDFT + Pauta de Julgamento + > 5000 chars."""
    grande = "x" * 6000
    assert deve_filtrar_pauta_tjdft("TJDFT", "Pauta de Julgamento", grande) is True
    assert deve_filtrar_pauta_tjdft("TJDFT", "PAUTA DE JULGAMENTOS", grande) is True
    # Tribunal diferente: não filtra
    assert deve_filtrar_pauta_tjdft("STJ", "Pauta de Julgamento", grande) is False
    # Tipo diferente: não filtra
    assert deve_filtrar_pauta_tjdft("TJDFT", "Acórdão", grande) is False
    # Pequeno: não filtra
    assert deve_filtrar_pauta_tjdft("TJDFT", "Pauta de Julgamento", "x" * 100) is False
    # Inputs nulos: não filtra
    assert deve_filtrar_pauta_tjdft(None, None, None) is False


def test_R1_5_filtragem_pauta_tjdft_com_match_sintetica() -> None:
    """Pauta com 1 escritório match em 3 processos: filtragem deixa 1 bloco."""
    pauta = _pauta_sintetica([
        ("0707739-37.2025.8.07.0001", ["DF99999"]),  # externo
        ("0707740-37.2025.8.07.0001", ["DF15523-A", "DF36129-A"]),  # escritório
        ("0707741-37.2025.8.07.0001", ["DF88888"]),  # externo
    ])
    # Padding pra ultrapassar 5000 chars (trigger)
    pauta = pauta + ("x" * 6000)
    resultado = filtrar_pauta_tjdft(pauta)
    assert resultado is not None
    assert "1 de 3 processos pertencem ao escritório" in resultado
    # CNJ do match aparece, dos outros não
    assert "0707740-37" in resultado
    assert "0707739-37" not in resultado
    assert "0707741-37" not in resultado
    # Cabeçalho preservado
    assert "PAUTA DE JULGAMENTOS" in resultado


def test_R1_5_filtragem_pauta_d9_zero_matches() -> None:
    """Pauta sem nenhum escritório match (D-9): nota explicativa."""
    pauta = _pauta_sintetica([
        ("0707739-37.2025.8.07.0001", ["DF99999"]),
        ("0707740-37.2025.8.07.0001", ["DF88888"]),
    ])
    resultado = filtrar_pauta_tjdft(pauta)
    assert resultado is not None
    assert "0 processos do escritório" in resultado
    assert "menção tangencial" in resultado
    # Cabeçalho preservado mas nenhum CNJ
    assert "0707739" not in resultado
    assert "0707740" not in resultado


def test_R1_5_filtragem_sem_blocos_processo_devolve_none() -> None:
    """Se o regex de Processo não acha nenhum bloco, devolve None
    (caller faz fallback caso B)."""
    texto_sem_processos = "Texto qualquer sem blocos no formato esperado.\n" * 200
    assert filtrar_pauta_tjdft(texto_sem_processos) is None


def test_R1_5_oab_com_zeros_a_esquerda_e_sufixo_a_match() -> None:
    """Regex aceita 5 ou 6 dígitos (zeros à esquerda) + sufixo opcional -A."""
    pauta = _pauta_sintetica([
        ("0707740-37.2025.8.07.0001", ["DF015523-A"]),  # 6 dígitos + -A
    ])
    resultado = filtrar_pauta_tjdft(pauta)
    assert "1 de 1 processos" in resultado


def test_R1_5_truncar_corpo_simples_curto_passa_intacto() -> None:
    texto = "x" * 10_000
    truncado, foi = truncar_corpo_simples(texto)
    assert foi is False
    assert truncado == texto


def test_R1_5_truncar_corpo_simples_grande_corta() -> None:
    texto = "x" * 100_000
    truncado, foi = truncar_corpo_simples(texto)
    assert foi is True
    assert len(truncado) <= LIMITE_TRUNCAMENTO_BYTES


def test_R1_5_truncar_corpo_simples_corta_em_quebra_se_possivel() -> None:
    """Janela de 200 chars antes do limite procura por \\n — se acha,
    corta lá. Resultado tem TODAS as linhas completas (nenhum corte
    no meio de uma linha)."""
    base = "linha que termina com newline.\n" * 4000  # >> 80KB
    truncado, foi = truncar_corpo_simples(base)
    assert foi is True
    # Cabe no limite
    assert len(truncado) <= LIMITE_TRUNCAMENTO_BYTES
    # Todas as ocorrências da linha estão completas (nenhuma quebrada
    # no meio): split em \n só devolve linha-padrão ou string vazia.
    for linha in truncado.split("\n"):
        assert linha == "linha que termina com newline." or linha == ""


def test_R1_5_aplicar_caso_15_pauta_tjdft_filtrada() -> None:
    """Caso A: pauta TJDFT > 5000 chars vira filtrado, sem callout."""
    pauta = _pauta_sintetica([
        ("0707739-37.2025.8.07.0001", ["DF15523-A"]),
        ("0707740-37.2025.8.07.0001", ["DF99999"]),
    ])
    pauta = pauta + ("x" * 6000)  # ultrapassa 5000
    corpo, callouts = aplicar_caso_15(
        tribunal="TJDFT",
        tipo_documento="Pauta de Julgamento",
        texto=pauta,
        hash_djen="abc123",
    )
    assert "1 de 2 processos" in corpo
    assert callouts == []  # filtragem é suficiente


def test_R1_5_aplicar_caso_15_acordao_grande_trunca_e_callout() -> None:
    """Caso B: acórdão TST > 80KB vira truncado + callout pra certidão."""
    texto = "Texto do acórdão\n" * 20_000  # ~340KB
    corpo, callouts = aplicar_caso_15(
        tribunal="TST",
        tipo_documento="Acórdão",
        texto=texto,
        hash_djen="abc123",
    )
    assert len(corpo) <= LIMITE_TRUNCAMENTO_BYTES
    assert len(callouts) == 1
    callout = callouts[0]
    assert callout["type"] == "callout"
    assert callout["callout"]["color"] == "yellow_background"
    # Link pra certidão presente
    rich_texts = callout["callout"]["rich_text"]
    link_text = next(rt for rt in rich_texts if rt["text"].get("link"))
    assert "abc123" in link_text["text"]["link"]["url"]


def test_R1_5_aplicar_caso_15_pequeno_passa_intacto() -> None:
    """Texto pequeno (caso C implícito): passa sem mudança, sem callout."""
    texto = "Despacho curto."
    corpo, callouts = aplicar_caso_15(
        tribunal="TJDFT",
        tipo_documento="Despacho",
        texto=texto,
        hash_djen="abc",
    )
    assert corpo == texto
    assert callouts == []


def test_R1_5_aplicar_caso_15_vazio_devolve_vazio() -> None:
    corpo, callouts = aplicar_caso_15(
        tribunal="TJDFT", tipo_documento="Acórdão",
        texto=None, hash_djen="abc",
    )
    assert corpo == ""
    assert callouts == []


def test_R1_5_pauta_tjdft_pequena_nao_dispara_filtragem() -> None:
    """Pauta TJDFT mas com texto < 5000 chars (single-process): caso C
    (passa intacta), sem callout."""
    pauta_pequena = _pauta_sintetica([
        ("0707739-37.2025.8.07.0001", ["DF15523-A"]),
    ])
    assert len(pauta_pequena) < 5000
    corpo, callouts = aplicar_caso_15(
        tribunal="TJDFT",
        tipo_documento="Pauta de Julgamento",
        texto=pauta_pequena,
        hash_djen="abc",
    )
    assert corpo == pauta_pequena
    assert callouts == []


def test_R1_5_pauta_tst_grande_cai_no_caso_b() -> None:
    """Pautas STJ/TST/TRF1 NÃO filtram (caso A é só TJDFT). Se grande,
    cai em truncamento simples + callout."""
    texto = "Texto longo de pauta STJ.\n" * 10_000  # > 80KB
    corpo, callouts = aplicar_caso_15(
        tribunal="STJ",
        tipo_documento="Pauta de Julgamento",
        texto=texto,
        hash_djen="abc",
    )
    assert len(corpo) <= LIMITE_TRUNCAMENTO_BYTES
    assert len(callouts) == 1


# ===========================================================================
# 1.6 — Detector de duplicatas + propriedade "Duplicatas suprimidas"
# ===========================================================================


@pytest.fixture
def dedup_dje_conn(tmp_path: Path):
    """Conexão SQLite isolada por teste, schema migrado."""
    db = tmp_path / "leitor_dje.db"
    conn = dje_db.get_connection(db)
    yield conn
    conn.close()


def _seed_canonical_publicacao(
    conn,
    *,
    djen_id: int,
    cnj: str = "0000338-82.2024.5.10.0016",
    data: str = "2026-02-10",
    tribunal: str = "TRT10",
    tipo: str = "Acórdão",
    texto: str = "Texto canônico " * 50,
    advogados: list[dict] | None = None,
    notion_page_id: str | None = None,
    chave: str | None = None,
) -> None:
    """Insere uma publicação direto via API do dje_db, e opcionalmente
    marca como já-enviada-ao-Notion (canônica)."""
    payload = {
        "id": djen_id,
        "hash": f"hash-{djen_id}",
        "siglaTribunal": tribunal,
        "data_disponibilizacao": data,
        "numeroprocessocommascara": cnj,
        "tipoDocumento": tipo,
        "tipoComunicacao": "Intimação",
        "texto": texto,
        "destinatarios": [{"nome": "BANCO X", "polo": "PASSIVO"}],
        "destinatarioadvogados": advogados or [
            {"advogado": {"numero_oab": "15523", "uf_oab": "DF"}},
        ],
    }
    dje_db.insert_publicacao(
        conn,
        djen_id=djen_id,
        hash_=f"hash-{djen_id}",
        oabs_escritorio="Ricardo (15523/DF)",
        oabs_externas="",
        numero_processo=cnj,
        data_disponibilizacao=data,
        sigla_tribunal=tribunal,
        payload=payload,
        mode=dje_db.CAPTURE_MODE_PADRAO,
    )
    if notion_page_id:
        dje_db.mark_publicacao_sent_to_notion(conn, djen_id, notion_page_id)
    if chave:
        dje_db.mark_publicacao_dup_chave(conn, djen_id, chave)


def test_R1_6_chave_canonica_estavel() -> None:
    """Mesmos inputs → mesma chave SHA-256 (determinismo)."""
    args = dict(
        numero_processo="0001234-56.2024.5.10.0001",
        data_disponibilizacao="2026-02-10",
        tribunal="TRT10",
        tipo_documento_canonico="Acórdão",
        texto_pre_processado="texto " * 100,
    )
    assert calcular_chave_canonica(**args) == calcular_chave_canonica(**args)


def test_R1_6_chave_canonica_cnj_nulo_devolve_none() -> None:
    """D-2: CNJ ausente → chave None → não deduplica."""
    assert calcular_chave_canonica(
        numero_processo=None,
        data_disponibilizacao="2026-02-10",
        tribunal="TRT10",
        tipo_documento_canonico="Acórdão",
        texto_pre_processado="x",
    ) is None
    assert calcular_chave_canonica(
        numero_processo="",
        data_disponibilizacao="2026-02-10",
        tribunal="TRT10",
        tipo_documento_canonico="Acórdão",
        texto_pre_processado="x",
    ) is None


def test_R1_6_chave_diferente_quando_qualquer_componente_muda() -> None:
    base = dict(
        numero_processo="000-0",
        data_disponibilizacao="2026-02-10",
        tribunal="TRT10",
        tipo_documento_canonico="Acórdão",
        texto_pre_processado="texto",
    )
    chave_base = calcular_chave_canonica(**base)
    # CNJ diferente
    assert calcular_chave_canonica(**{**base, "numero_processo": "001-0"}) != chave_base
    # Data diferente
    assert calcular_chave_canonica(**{**base, "data_disponibilizacao": "2026-02-11"}) != chave_base
    # Tribunal diferente
    assert calcular_chave_canonica(**{**base, "tribunal": "TJDFT"}) != chave_base
    # Tipo diferente
    assert calcular_chave_canonica(**{**base, "tipo_documento_canonico": "Despacho"}) != chave_base
    # Texto diferente
    assert calcular_chave_canonica(**{**base, "texto_pre_processado": "outro"}) != chave_base


def test_R1_6_chave_para_publicacao_aplica_pipeline_internamente() -> None:
    """Helper aplica preprocess HTML + mapping de tipo internamente."""
    from notion_rpadv.services.dje_text_pipeline import preprocessar_texto_djen

    pub = {
        "id": 1,
        "numeroprocessocommascara": "0001234-56.2024.5.10.0001",
        "data_disponibilizacao": "2026-02-10",
        "siglaTribunal": "TRT10",
        "tipoDocumento": "ACORDAO",  # variante mapeada pra "Acórdão"
        "texto": "<p>Texto com <br>HTML</p>",
    }
    chave1 = calcular_chave_para_publicacao(pub)
    # Chave equivalente computada manualmente — usa o resultado real do
    # preprocessador (não a forma idealizada).
    texto_pre_real = preprocessar_texto_djen(pub["texto"])
    chave2 = calcular_chave_canonica(
        numero_processo="0001234-56.2024.5.10.0001",
        data_disponibilizacao="2026-02-10",
        tribunal="TRT10",
        tipo_documento_canonico="Acórdão",
        texto_pre_processado=texto_pre_real,
    )
    assert chave1 == chave2


def test_R1_6_dedup_migration_idempotente(tmp_path: Path) -> None:
    """Schema migration roda 2x sem erro (init_db é chamado de novo na
    re-conexão)."""
    db = tmp_path / "leitor_dje.db"
    conn1 = dje_db.get_connection(db)
    cols1 = {r["name"] for r in conn1.execute("PRAGMA table_info(publicacoes)")}
    conn1.close()
    conn2 = dje_db.get_connection(db)
    cols2 = {r["name"] for r in conn2.execute("PRAGMA table_info(publicacoes)")}
    conn2.close()
    assert cols1 == cols2
    assert "dup_chave" in cols1
    assert "dup_canonical_djen_id" in cols1


def test_R1_6_dup_pendentes_table_existe(dedup_dje_conn) -> None:
    """Migration cria a tabela dup_pendentes."""
    rows = list(dedup_dje_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dup_pendentes'"
    ))
    assert len(rows) == 1


def test_R1_6_determinar_destino_sem_dedup_sem_cnj(dedup_dje_conn) -> None:
    """D-2: pub sem CNJ → SEM_DEDUP."""
    pub = {"id": 1, "siglaTribunal": "TRT10", "tipoDocumento": "Acórdão"}
    res = determinar_destino(pub, dedup_dje_conn)
    assert res.tipo == TipoDestino.SEM_DEDUP
    assert res.chave is None


def test_R1_6_determinar_destino_nova_canonica_quando_chave_inedita(
    dedup_dje_conn,
) -> None:
    """1ª pub do grupo → NOVA_CANONICA, chave gerada."""
    pub = {
        "id": 1,
        "numeroprocessocommascara": "0001234-56.2024.5.10.0001",
        "data_disponibilizacao": "2026-02-10",
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Acórdão",
        "texto": "Texto da pub.",
    }
    res = determinar_destino(pub, dedup_dje_conn)
    assert res.tipo == TipoDestino.NOVA_CANONICA
    assert res.chave is not None
    assert res.canonica is None


def test_R1_6_determinar_destino_duplicata_quando_canonica_ja_no_banco(
    dedup_dje_conn,
) -> None:
    """2ª pub do grupo c/ mesma chave + canônica já enviada → DUPLICATA_DE."""
    # Calcula chave que vai ser usada
    pub_canonica = {
        "id": 100,
        "numeroprocessocommascara": "0001234-56.2024.5.10.0001",
        "data_disponibilizacao": "2026-02-10",
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Acórdão",
        "texto": "Texto da pub.",
    }
    chave = calcular_chave_para_publicacao(pub_canonica)
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=100,
        cnj="0001234-56.2024.5.10.0001", texto="Texto da pub.",
        notion_page_id="page-uuid-canonica", chave=chave,
    )
    # Pub 101: mesmo CNJ + data + tribunal + tipo + prefix de texto
    pub_dup = {**pub_canonica, "id": 101}
    res = determinar_destino(pub_dup, dedup_dje_conn)
    assert res.tipo == TipoDestino.DUPLICATA_DE
    assert res.chave == chave
    assert res.canonica is not None
    assert res.canonica["djen_id"] == 100
    assert res.canonica["notion_page_id"] == "page-uuid-canonica"


def test_R1_6_canonica_skipped_nao_e_canonica(dedup_dje_conn) -> None:
    """Pub com notion_page_id == SKIPPED não conta como canônica
    (não tem página real no Notion)."""
    pub = {
        "id": 100,
        "numeroprocessocommascara": "0001234-56.2024.5.10.0001",
        "data_disponibilizacao": "2026-02-10",
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Acórdão",
        "texto": "x",
    }
    chave = calcular_chave_para_publicacao(pub)
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=100,
        cnj="0001234-56.2024.5.10.0001", texto="x",
        notion_page_id=dje_db.NOTION_SKIPPED_SENTINEL,
        chave=chave,
    )
    pub_dup = {**pub, "id": 101}
    res = determinar_destino(pub_dup, dedup_dje_conn)
    # SKIPPED não conta — vai como NOVA_CANONICA
    assert res.tipo == TipoDestino.NOVA_CANONICA


def test_R1_6_marcar_como_canonica_persiste_chave(dedup_dje_conn) -> None:
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=100,
        notion_page_id="page-uuid", chave=None,
    )
    marcar_como_canonica(dedup_dje_conn, djen_id=100, chave="abc")
    row = dedup_dje_conn.execute(
        "SELECT dup_chave FROM publicacoes WHERE djen_id=100"
    ).fetchone()
    assert row["dup_chave"] == "abc"


def test_R1_6_marcar_como_duplicata_atualiza_pub_e_insere_pendente(
    dedup_dje_conn,
) -> None:
    """Marcar como duplicata: atualiza colunas + insere em dup_pendentes."""
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=100,
        notion_page_id="page-uuid-canon", chave="chave-X",
    )
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=101, notion_page_id=None,
    )

    pub_dup = {
        "id": 101,
        "numeroprocessocommascara": "0001234-56.2024.5.10.0001",
        "destinatarios": [{"nome": "ACME LTDA", "polo": "ATIVO"}],
        "destinatarioadvogados": [
            {"advogado": {"numero_oab": "36129", "uf_oab": "DF"}},
        ],
    }
    canonica_row = dict(dedup_dje_conn.execute(
        "SELECT * FROM publicacoes WHERE djen_id=100"
    ).fetchone())

    marcar_como_duplicata(
        dedup_dje_conn,
        publicacao_duplicata=pub_dup,
        canonica_row=canonica_row,
        chave="chave-X",
    )

    # Pub 101 atualizada
    row = dedup_dje_conn.execute(
        "SELECT dup_chave, dup_canonical_djen_id, notion_page_id "
        "FROM publicacoes WHERE djen_id=101"
    ).fetchone()
    assert row["dup_chave"] == "chave-X"
    assert row["dup_canonical_djen_id"] == 100
    assert row["notion_page_id"] == "page-uuid-canon"

    # Pendente inserido
    pendentes = dje_db.fetch_dup_pendentes_for_canonical(dedup_dje_conn, 100)
    assert len(pendentes) == 1
    p = pendentes[0]
    assert p["duplicata_djen_id"] == 101
    assert "Leonardo (36129/DF)" in p["duplicata_destinatario"]
    assert "ACME LTDA" in p["duplicata_destinatario"]


def test_R1_6_par_real_trt10_detectado(dedup_dje_conn) -> None:
    """Par real TRT10 djen=527365047 e djen=527365146 (mesmo CNJ, mesma
    data, mesmo tipo, mesmo prefixo texto) → 2ª é detectada como
    duplicata da 1ª."""
    cnj = "00003388220245100016"
    data = "2026-02-10"
    tribunal = "TRT10"
    tipo = "Acórdão"
    texto = "PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRIBUNAL REGIONAL " * 30

    # Seed canônica (527365047) já enviada
    pub_canon = {
        "id": 527365047,
        "numeroprocessocommascara": cnj,
        "data_disponibilizacao": data,
        "siglaTribunal": tribunal,
        "tipoDocumento": tipo,
        "texto": texto,
    }
    chave = calcular_chave_para_publicacao(pub_canon)
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=527365047,
        cnj=cnj, data=data, tribunal=tribunal, tipo=tipo, texto=texto,
        notion_page_id="page-canonica-uuid", chave=chave,
    )

    # Detecta 527365146 como duplicata
    pub_dup = {**pub_canon, "id": 527365146}
    res = determinar_destino(pub_dup, dedup_dje_conn)
    assert res.tipo == TipoDestino.DUPLICATA_DE
    assert res.canonica["djen_id"] == 527365047


def test_R1_6_merge_partes_dedup_por_nome() -> None:
    j1 = json.dumps([{"nome": "ACME", "polo": "ATIVO"}])
    j2 = json.dumps([{"nome": "acme", "polo": "ATIVO"}, {"nome": "OUTRO"}])
    out = json.loads(_merge_partes(j1, [j2]))
    nomes = [p["nome"] for p in out]
    # Dedup case-insensitive: ACME aparece 1x; OUTRO entra
    assert len(nomes) == 2
    assert "ACME" in nomes
    assert "OUTRO" in nomes


def test_R1_6_merge_advogados_uniao_ordenada() -> None:
    """D-5 A: união dos multi-select da canônica + duplicatas, ordem alfabética."""
    canon_payload = json.dumps({
        "destinatarioadvogados": [
            {"advogado": {"numero_oab": "15523", "uf_oab": "DF"}},
        ]
    })
    dup_jsons = [
        json.dumps(["Leonardo (36129/DF)"]),
        json.dumps(["Vitor (48468/DF)"]),
    ]
    out = _merge_advogados(canon_payload, dup_jsons)
    assert out == [
        "Leonardo (36129/DF)",
        "Ricardo (15523/DF)",
        "Vitor (48468/DF)",
    ]


def test_R1_6_flush_chama_update_page_e_limpa_pendentes(
    dedup_dje_conn,
) -> None:
    """Flush bem-sucedido: PATCH /pages/{id} com Partes + Advogados +
    Duplicatas suprimidas (se schema permite); pendentes apagados."""
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=100,
        notion_page_id="page-uuid-100", chave="k1",
    )
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=101,
    )
    canonica_row = dict(dedup_dje_conn.execute(
        "SELECT * FROM publicacoes WHERE djen_id=100"
    ).fetchone())
    pub_dup = {
        "id": 101,
        "destinatarios": [{"nome": "ACME"}],
        "destinatarioadvogados": [
            {"advogado": {"numero_oab": "36129", "uf_oab": "DF"}}
        ],
    }
    marcar_como_duplicata(
        dedup_dje_conn,
        publicacao_duplicata=pub_dup,
        canonica_row=canonica_row,
        chave="k1",
    )
    # 1 pendente esperada
    assert dje_db.count_dup_pendentes(dedup_dje_conn) == 1

    client = MagicMock()
    client.update_page.return_value = {"id": "page-uuid-100"}

    outcome = flush_atualizacoes_canonicas(
        client=client, conn=dedup_dje_conn,
        schema_tem_duplicatas_suprimidas=True,
    )
    assert outcome.canonicas_atualizadas == 1
    assert outcome.canonicas_404 == 0

    # Notion update_page chamado com page_id correto e schemas esperados
    client.update_page.assert_called_once()
    args, kwargs = client.update_page.call_args
    assert args[0] == "page-uuid-100"
    props = args[1]
    assert "Partes" in props
    assert "Advogados intimados" in props
    # D-4: Status NÃO sobrescrito
    assert "Status" not in props
    assert "Duplicatas suprimidas" in props

    # Pendentes apagados após sucesso
    assert dje_db.count_dup_pendentes(dedup_dje_conn) == 0


def test_R1_6_flush_404_descarta_pendentes_d8(dedup_dje_conn) -> None:
    """D-8: canônica deletada manualmente do Notion → 404 → descarta
    pendentes silenciosamente + warning, sem bloquear outras canônicas."""
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=100,
        notion_page_id="page-deletada", chave="k1",
    )
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=101,
    )
    canonica_row = dict(dedup_dje_conn.execute(
        "SELECT * FROM publicacoes WHERE djen_id=100"
    ).fetchone())
    marcar_como_duplicata(
        dedup_dje_conn,
        publicacao_duplicata={"id": 101, "destinatarios": [], "destinatarioadvogados": []},
        canonica_row=canonica_row, chave="k1",
    )

    client = MagicMock()
    client.update_page.side_effect = NotionAPIError(404, "page not found")

    outcome = flush_atualizacoes_canonicas(client=client, conn=dedup_dje_conn)
    assert outcome.canonicas_404 == 1
    assert outcome.canonicas_atualizadas == 0
    # Pendentes limpos mesmo no 404
    assert dje_db.count_dup_pendentes(dedup_dje_conn) == 0


def test_R1_6_flush_sem_pendentes_nao_chama_api(dedup_dje_conn) -> None:
    client = MagicMock()
    outcome = flush_atualizacoes_canonicas(client=client, conn=dedup_dje_conn)
    assert outcome.canonicas_atualizadas == 0
    client.update_page.assert_not_called()


def test_R1_6_flush_omite_duplicatas_suprimidas_se_schema_nao_tem(
    dedup_dje_conn,
) -> None:
    """Se schema_tem_duplicatas_suprimidas=False, property NÃO entra no
    payload (evita 400 da Notion API)."""
    _seed_canonical_publicacao(
        dedup_dje_conn, djen_id=100,
        notion_page_id="page-uuid", chave="k1",
    )
    _seed_canonical_publicacao(dedup_dje_conn, djen_id=101)
    canonica_row = dict(dedup_dje_conn.execute(
        "SELECT * FROM publicacoes WHERE djen_id=100"
    ).fetchone())
    marcar_como_duplicata(
        dedup_dje_conn,
        publicacao_duplicata={"id": 101, "destinatarios": [], "destinatarioadvogados": []},
        canonica_row=canonica_row, chave="k1",
    )
    client = MagicMock()
    client.update_page.return_value = {"id": "page-uuid"}
    flush_atualizacoes_canonicas(
        client=client, conn=dedup_dje_conn,
        schema_tem_duplicatas_suprimidas=False,
    )
    args, _ = client.update_page.call_args
    props = args[1]
    assert "Duplicatas suprimidas" not in props
    # Mas Partes e Advogados sim
    assert "Partes" in props
    assert "Advogados intimados" in props


# ===========================================================================
# Wire — sync + dedup integrado
# ===========================================================================


@pytest.fixture
def cache_conn_round1(tmp_path):
    """Cache conn vazio (sem processos cadastrados) — checkbox marca True."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE records (
            base TEXT, page_id TEXT, data_json TEXT, updated_at REAL,
            PRIMARY KEY (base, page_id)
        )
        """,
    )
    conn.commit()
    yield conn
    conn.close()


def _client_returning_round1(page_ids: list[str]) -> MagicMock:
    """Mock NotionClient para testes wire."""
    client = MagicMock(spec=NotionClient)
    client.create_page_in_data_source.side_effect = [
        {"id": pid} for pid in page_ids
    ]
    client.update_page.side_effect = lambda page_id, props: {"id": page_id}
    return client


def test_R1_wire_par_real_so_envia_canonica_e_marca_duplicata(
    dedup_dje_conn, cache_conn_round1,
) -> None:
    """Cenário ponta a ponta: 2 pubs com mesma chave canônica → API
    cria página só pra 1ª; 2ª é marcada como duplicata sem chamar API."""
    cnj = "0001234-56.2024.5.10.0001"
    data = "2026-02-10"
    tribunal = "TRT10"
    tipo = "Acórdão"
    texto = "Texto canônico " * 50

    payload_base = {
        "id": 100,
        "hash": "hash-100",
        "siglaTribunal": tribunal,
        "data_disponibilizacao": data,
        "numeroprocessocommascara": cnj,
        "tipoDocumento": tipo,
        "tipoComunicacao": "Intimação",
        "texto": texto,
        "destinatarios": [{"nome": "ACME", "polo": "ATIVO"}],
        "destinatarioadvogados": [
            {"advogado": {"numero_oab": "15523", "uf_oab": "DF"}}
        ],
    }
    # 1ª pub (canônica)
    dje_db.insert_publicacao(
        dedup_dje_conn,
        djen_id=100, hash_="hash-100",
        oabs_escritorio="Ricardo (15523/DF)", oabs_externas="",
        numero_processo=cnj, data_disponibilizacao=data,
        sigla_tribunal=tribunal, payload=payload_base,
        mode=dje_db.CAPTURE_MODE_PADRAO,
    )
    # 2ª pub (duplicata) — mesmo hash NÃO funciona (UNIQUE), usar outro
    payload_dup = {**payload_base, "id": 101, "hash": "hash-101"}
    dje_db.insert_publicacao(
        dedup_dje_conn,
        djen_id=101, hash_="hash-101",
        oabs_escritorio="Leonardo (36129/DF)", oabs_externas="",
        numero_processo=cnj, data_disponibilizacao=data,
        sigla_tribunal=tribunal, payload=payload_dup,
        mode=dje_db.CAPTURE_MODE_PADRAO,
    )

    # 1ª chamada API → page-uuid-canon; 2ª NÃO acontece (dedup)
    client = _client_returning_round1(["page-uuid-canon"])
    out = sincronizar_pendentes(
        client=client,
        dje_conn=dedup_dje_conn,
        cache_conn=cache_conn_round1,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
    )
    # Sucesso: 1 enviada, 1 duplicata
    assert out.sent == 1
    assert out.duplicates_supprimidas == 1
    # Apenas 1 chamada de create
    assert client.create_page_in_data_source.call_count == 1
    # Update_page chamado 1x (flush da canônica)
    assert client.update_page.call_count == 1
    args, _ = client.update_page.call_args
    assert args[0] == "page-uuid-canon"

    # Estado do banco
    row100 = dedup_dje_conn.execute(
        "SELECT notion_page_id, dup_chave, dup_canonical_djen_id "
        "FROM publicacoes WHERE djen_id=100"
    ).fetchone()
    assert row100["notion_page_id"] == "page-uuid-canon"
    assert row100["dup_chave"] is not None
    assert row100["dup_canonical_djen_id"] is None  # canônica

    row101 = dedup_dje_conn.execute(
        "SELECT notion_page_id, dup_chave, dup_canonical_djen_id "
        "FROM publicacoes WHERE djen_id=101"
    ).fetchone()
    assert row101["notion_page_id"] == "page-uuid-canon"  # compartilha
    assert row101["dup_chave"] == row100["dup_chave"]
    assert row101["dup_canonical_djen_id"] == 100

    # Pendentes apagados após flush
    assert dje_db.count_dup_pendentes(dedup_dje_conn) == 0


def test_R1_wire_pub_sem_cnj_nao_passa_por_dedup(
    dedup_dje_conn, cache_conn_round1,
) -> None:
    """D-2: pub sem CNJ → SEM_DEDUP → envia direto sem persistir chave."""
    payload = {
        "id": 200,
        "hash": "h-200",
        "siglaTribunal": "TRT10",
        "data_disponibilizacao": "2026-02-10",
        # NB: numeroprocessocommascara ausente
        "numero_processo": None,
        "tipoDocumento": "Acórdão",
        "tipoComunicacao": "Intimação",
        "texto": "x",
        "destinatarios": [],
        "destinatarioadvogados": [],
    }
    dje_db.insert_publicacao(
        dedup_dje_conn,
        djen_id=200, hash_="h-200",
        oabs_escritorio="", oabs_externas="",
        numero_processo=None,
        data_disponibilizacao="2026-02-10",
        sigla_tribunal="TRT10", payload=payload,
        mode=dje_db.CAPTURE_MODE_PADRAO,
    )
    client = _client_returning_round1(["page-sem-dedup"])
    out = sincronizar_pendentes(
        client=client, dje_conn=dedup_dje_conn,
        cache_conn=cache_conn_round1,
        sleep_ms=lambda _: None, sleep=lambda _: None,
    )
    assert out.sent == 1
    assert out.duplicates_supprimidas == 0
    # Pub enviada mas SEM chave persistida
    row = dedup_dje_conn.execute(
        "SELECT notion_page_id, dup_chave FROM publicacoes WHERE djen_id=200"
    ).fetchone()
    assert row["notion_page_id"] == "page-sem-dedup"
    assert row["dup_chave"] is None


def test_R1_wire_outcome_inclui_canonicas_atualizadas(
    dedup_dje_conn, cache_conn_round1,
) -> None:
    """Outcome do sync inclui canonicas_atualizadas refletindo o flush."""
    cnj = "0001234-56.2024.5.10.0001"
    payload = {
        "id": 100, "hash": "h-100", "siglaTribunal": "TRT10",
        "data_disponibilizacao": "2026-02-10",
        "numeroprocessocommascara": cnj,
        "tipoDocumento": "Acórdão", "tipoComunicacao": "Intimação",
        "texto": "Texto", "destinatarios": [],
        "destinatarioadvogados": [],
    }
    dje_db.insert_publicacao(
        dedup_dje_conn, djen_id=100, hash_="h-100",
        oabs_escritorio="", oabs_externas="",
        numero_processo=cnj, data_disponibilizacao="2026-02-10",
        sigla_tribunal="TRT10", payload=payload,
        mode=dje_db.CAPTURE_MODE_PADRAO,
    )
    payload_dup = {**payload, "id": 101, "hash": "h-101"}
    dje_db.insert_publicacao(
        dedup_dje_conn, djen_id=101, hash_="h-101",
        oabs_escritorio="", oabs_externas="",
        numero_processo=cnj, data_disponibilizacao="2026-02-10",
        sigla_tribunal="TRT10", payload=payload_dup,
        mode=dje_db.CAPTURE_MODE_PADRAO,
    )
    client = _client_returning_round1(["page-canon"])
    out = sincronizar_pendentes(
        client=client, dje_conn=dedup_dje_conn,
        cache_conn=cache_conn_round1,
        sleep_ms=lambda _: None, sleep=lambda _: None,
    )
    assert out.canonicas_atualizadas == 1
    assert out.canonicas_404 == 0
