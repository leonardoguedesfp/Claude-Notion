"""Testes do Round 4 — fixes pré-Round 5 da pipeline DJE × Notion (2026-05-03).

Cobre as frentes do Round 4 que **continuam ativas** após o Round 6:

- 4.1 Reformatar `Partes` (Polo Ativo / Polo Passivo / Terceiro Interessado)
- 4.2 Normalizar `Classe` via `MAPA_NOMECLASSE`
- 4.5 Teste de regressão para `<br>` literal residual no Texto inline
- 4.6 Mapper deixa de gravar checkbox `Processo não cadastrado`

**Round 6 (2026-05-04) — frentes removidas deste arquivo:**

- 4.3 Auto-`Tarefa sugerida` (6 regras antigas) — substituídas pela Camada
  base v8 (Regras 40-43) em ``test_round_6.py``.
- 4.4 Auto-`Alerta contadoria` (5 regras antigas) — substituídas pelas
  39 regras de monitoramento v8 (Regras 1-39) em ``test_round_6.py``.

Os testes do mapper ponta a ponta (montar_payload_publicacao) ficam em
``tests/test_dje_notion_mapper.py``.
"""
from __future__ import annotations

from notion_rpadv.services.dje_notion_mappings import (
    MAPA_NOMECLASSE,
    PARTES_INLINE_LIMIT,
    POLO_LABEL,
    formatar_partes,
    normalizar_classe,
)


# ===========================================================================
# 4.1 — Reformatar Partes
# ===========================================================================


def test_R4_1_partes_pub_trabalhista_normal() -> None:
    """1 Ativo + 1 Passivo (caso TRT10 djen=494748109)."""
    destinatarios = [
        {"comunicacao_id": 494748109, "nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"comunicacao_id": 494748109, "nome": "DENITA GOMES GUIMARAES", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    assert out == "Polo Ativo: DENITA GOMES GUIMARAES\nPolo Passivo: BANCO DO BRASIL SA"


def test_R4_1_partes_stj_3_destinatarios_com_papel() -> None:
    """STJ djen=549681949 — papel real entre parênteses no nome."""
    destinatarios = [
        {"comunicacao_id": 549681949, "nome": "1. CAIXA DE PREVIDENCIA (AGRAVANTE)", "polo": "A"},
        {"comunicacao_id": 549681949, "nome": "2. ALEX DOS SANTOS SABINO (AGRAVADO)", "polo": "P"},
        {"comunicacao_id": 549681949, "nome": "3. BANCO DO BRASIL SA (INTERESSADO)", "polo": "T"},
    ]
    out = formatar_partes(destinatarios)
    assert "Polo Ativo: 1. CAIXA DE PREVIDENCIA (AGRAVANTE)" in out
    assert "Polo Passivo: 2. ALEX DOS SANTOS SABINO (AGRAVADO)" in out
    assert "Terceiro Interessado: 3. BANCO DO BRASIL SA (INTERESSADO)" in out


def test_R4_1_partes_multiplos_nomes_mesmo_polo() -> None:
    """Polo A com 3 nomes — separados por vírgula, ordem preservada."""
    destinatarios = [
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"nome": "GISELE CRISTINE", "polo": "A"},
        {"nome": "MARIA CRISTINA", "polo": "A"},
        {"nome": "UNIÃO FEDERAL", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    assert (
        "Polo Ativo: GISELE CRISTINE, MARIA CRISTINA, UNIÃO FEDERAL\n"
        "Polo Passivo: BANCO DO BRASIL SA"
    ) == out


def test_R4_1_partes_sem_destinatarios() -> None:
    """Lista vazia → string vazia (sem JSON, sem 'null')."""
    assert formatar_partes([]) == ""
    assert formatar_partes(None) == ""


def test_R4_1_partes_terceiro_interessado() -> None:
    """Polo T → 'Terceiro Interessado:'"""
    destinatarios = [
        {"nome": "AUTOR", "polo": "A"},
        {"nome": "TERCEIRO", "polo": "T"},
    ]
    out = formatar_partes(destinatarios)
    assert "Polo Ativo: AUTOR" in out
    assert "Terceiro Interessado: TERCEIRO" in out


def test_R4_1_partes_polo_desconhecido_fallback() -> None:
    """Polo fora de A/P/T → fallback 'Polo {valor}'."""
    destinatarios = [
        {"nome": "X", "polo": "Z"},
    ]
    out = formatar_partes(destinatarios)
    assert out == "Polo Z: X"


def test_R4_1_partes_ordem_fixa_apt() -> None:
    """Ordem de saída: Ativo, Passivo, Terceiro — independente da ordem de entrada."""
    destinatarios = [
        {"nome": "T1", "polo": "T"},
        {"nome": "P1", "polo": "P"},
        {"nome": "A1", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    linhas = out.split("\n")
    assert linhas[0].startswith("Polo Ativo:")
    assert linhas[1].startswith("Polo Passivo:")
    assert linhas[2].startswith("Terceiro Interessado:")


def test_R4_1_partes_dedup_nome_repetido_mesmo_polo() -> None:
    """Nome igual aparecendo 2x no mesmo polo → 1 vez no output."""
    destinatarios = [
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},
    ]
    out = formatar_partes(destinatarios)
    assert out.count("BANCO DO BRASIL SA") == 1


def test_R4_1_partes_truncamento_em_2000_chars() -> None:
    """Output total ≤ 2000 chars; corte preserva nomes inteiros + marcador."""
    nomes = [f"NOME ABCD EFGH IJKL {i}" for i in range(200)]
    destinatarios = [{"nome": n, "polo": "A"} for n in nomes]
    out = formatar_partes(destinatarios)
    assert len(out) <= PARTES_INLINE_LIMIT
    assert out.endswith("…")
    # Não deve cortar no meio de um nome
    assert "NOME ABCD EFGH IJKL 0" in out


def test_R4_1_partes_nome_vazio_e_descartado() -> None:
    """Destinatário com nome vazio é ignorado."""
    destinatarios = [
        {"nome": "", "polo": "A"},
        {"nome": "REAL", "polo": "P"},
    ]
    out = formatar_partes(destinatarios)
    assert out == "Polo Passivo: REAL"


def test_R4_1_partes_polo_label_constante_canonica() -> None:
    """Sanity check do dicionário de labels."""
    assert POLO_LABEL["A"] == "Polo Ativo"
    assert POLO_LABEL["P"] == "Polo Passivo"
    assert POLO_LABEL["T"] == "Terceiro Interessado"


# ===========================================================================
# 4.2 — Normalizar Classe
# ===========================================================================


def test_R4_2_classe_top_5_acervo_canonizadas() -> None:
    """As 5 classes mais frequentes do acervo (acumulam ~95%) são canonizadas."""
    casos = [
        ("AçãO TRABALHISTA - RITO ORDINáRIO", "AÇÃO TRABALHISTA - RITO ORDINÁRIO"),
        ("RECURSO ORDINáRIO TRABALHISTA", "RECURSO ORDINÁRIO TRABALHISTA"),
        ("CUMPRIMENTO DE SENTENçA", "CUMPRIMENTO DE SENTENÇA"),
        ("AGRAVO DE PETIçãO", "AGRAVO DE PETIÇÃO"),
        ("RECURSO ESPECIAL", "RECURSO ESPECIAL"),  # já em CAPS, passa intacto
    ]
    for cru, esperado in casos:
        assert normalizar_classe(cru) == esperado, f"{cru!r} → esperado {esperado!r}"


def test_R4_2_classe_ja_em_caps_passa_intacta() -> None:
    """Classes que JÁ vêm CAPS uniformes passam intactas."""
    casos = [
        "AGRAVO DE INSTRUMENTO",
        "PROCEDIMENTO COMUM CÍVEL",
        "EMBARGOS DE DECLARAÇÃO CÍVEL",
        "APELAÇÃO CÍVEL",
    ]
    for caps in casos:
        assert normalizar_classe(caps) == caps


def test_R4_2_classe_nao_mapeada_passa_intacta() -> None:
    """Classes fora do mapa são preservadas (não fazemos `.upper()` cego)."""
    cru = "Petição Excêntrica - Rito Inexistente"
    assert normalizar_classe(cru) == cru


def test_R4_2_classe_titlecase_explicita_no_mapa() -> None:
    """Caso especial: classes em title case mapeadas explicitamente."""
    # Liquidação de Sentença pelo Procedimento Comum aparece com casing variável
    if "Liquidação de Sentença pelo Procedimento Comum" in MAPA_NOMECLASSE:
        out = normalizar_classe("Liquidação de Sentença pelo Procedimento Comum")
        assert out == MAPA_NOMECLASSE["Liquidação de Sentença pelo Procedimento Comum"]


def test_R4_2_classe_none_e_vazio() -> None:
    """None ou vazia → string vazia."""
    assert normalizar_classe(None) == ""
    assert normalizar_classe("") == ""


def test_R4_2_classe_strip_aplicado() -> None:
    """Espaços laterais removidos antes de normalizar."""
    out = normalizar_classe("  AçãO TRABALHISTA - RITO ORDINáRIO  ")
    assert out == "AÇÃO TRABALHISTA - RITO ORDINÁRIO"


def test_R4_2_mapa_consistente_chave_diferente_do_valor() -> None:
    """Sanity: toda entrada do mapa tem chave ≠ valor (senão é ruído)."""
    for chave, valor in MAPA_NOMECLASSE.items():
        assert chave != valor, f"Entrada redundante: {chave!r}"


# ===========================================================================
# 4.5 — Teste de regressão: <br> literal residual no Texto inline
# ===========================================================================


def test_R4_5_preprocessador_limpa_br_no_trailer_djen_494748109() -> None:
    """Caso djen=494748109 do acervo Round 3 (TRT10 Notificação): texto
    bruto tem 4 ``<br>`` no trailer ``...Juiz do Trabalho Titular<br><br>
    Intimado(s) / Citado(s)<br> - {nome}<br>``. O pré-processador 1.7
    do Round 1 deve remover TODOS — nenhum ``<br>`` literal pode chegar
    ao texto inline entregue ao Notion.

    Round 5b (2026-05-04) confirmou que pubs reais no Notion não têm
    ``<br>`` literal — o pipeline funciona. Este teste é o invariante."""
    from notion_rpadv.services.dje_text_pipeline import (
        preprocessar_texto_djen,
        truncar_texto_inline,
    )

    # Reproduz o trailer exato visto em produção em djen=494748109.
    texto_bruto = (
        "PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRT10 18ª Vara… "
        "Decisão conferida pela Diretora Ana Carolina Macena Barros. "
        "BRASILIA/DF, 19 de dezembro de 2025. JONATHAN QUINTAO JACOB "
        "Juiz do Trabalho Titular<br><br>Intimado(s) / Citado(s)<br>"
        " - BANCO DO BRASIL SA<br>"
    )
    assert texto_bruto.count("<br>") == 4

    texto_pre = preprocessar_texto_djen(texto_bruto)
    assert "<br>" not in texto_pre
    assert "<br" not in texto_pre.lower()  # sanity total

    # Truncamento inline também não introduz <br>.
    inline = truncar_texto_inline(texto_pre, limite=2000)
    assert "<br>" not in inline
    # Trailer continua presente, só com \n em vez de <br>.
    assert "Intimado(s) / Citado(s)" in inline
    assert "BANCO DO BRASIL SA" in inline


def test_R4_5_preprocessador_limpa_br_variantes_xhtml() -> None:
    """Variantes <br/>, <br />, <BR>, <Br /> também são removidas."""
    from notion_rpadv.services.dje_text_pipeline import preprocessar_texto_djen

    texto = "linha1<br>linha2<br/>linha3<br />linha4<BR>linha5<Br />linha6"
    out = preprocessar_texto_djen(texto)
    assert "<br" not in out.lower()
    # Cada <br> virou \n; ENV: o normalizador colapsa 3+ \n em 2, mas
    # 6 linhas separadas por 5 \n permanecem como 5 \n.
    assert out.count("\n") >= 4


# ===========================================================================
# 4.6 — Mapper deixou de gravar checkbox 'Processo não cadastrado'
# (Round 6: o multi-select Alerta contadoria (app) será populado pela
# Regra 40 — `Processo/recurso distribuído` — para distribuições, e por
# uma regra de monitoramento futura para outros casos. Por ora, o teste
# valida apenas a ausência do checkbox no payload.)
# ===========================================================================


def test_R4_6_mapper_nao_grava_checkbox_processo_nao_cadastrado() -> None:
    """Verifica explicitamente que o checkbox foi removido do payload
    em ambos os cenários (cadastrado / não-cadastrado)."""
    import sqlite3
    from pathlib import Path
    import tempfile

    from notion_rpadv.services import dje_db
    from notion_rpadv.services.dje_notion_mapper import montar_payload_publicacao

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "leitor_dje.db"
        dje_conn = dje_db.get_connection(db_path)

        cache_conn = sqlite3.connect(":memory:")
        cache_conn.row_factory = sqlite3.Row
        cache_conn.execute(
            "CREATE TABLE records ("
            "base TEXT, page_id TEXT, data_json TEXT, updated_at REAL,"
            "PRIMARY KEY (base, page_id))"
        )

        pub = {
            "id": 1, "hash": "h", "siglaTribunal": "TRT10",
            "data_disponibilizacao": "2026-01-01",
            "numeroprocessocommascara": "0001234-56.2025.5.10.0001",
            "tipoDocumento": "Notificação", "tipoComunicacao": "Intimação",
            "texto": "Texto.", "destinatarios": [], "destinatarioadvogados": [],
        }
        # Sem cadastro
        payload = montar_payload_publicacao(
            pub, dje_conn=dje_conn, cache_conn=cache_conn,
        )
        # Checkbox antigo NÃO está no payload (Round 4.6 manteve, Round 6
        # mantém também — schema do Notion sequer tem mais essa coluna).
        assert "Processo não cadastrado" not in payload["properties"]
        # E o multi-select Alerta contadoria (app) está presente (vazio
        # neste estado intermediário do Round 6 — vai ser populado pela
        # Camada base + monitoramento em commits subsequentes).
        assert "Alerta contadoria (app)" in payload["properties"]

        dje_conn.close()
        cache_conn.close()
