"""Round 5b (2026-05-04) — testes de regressão para Frente B.

Garante que o pipeline de pré-processamento de texto remove TODAS as
variantes de ``<br>`` antes de entregar ao Notion.

Histórico desta frente:
- Relatório de anatomia pós-Round-4 (commit 0299354) reportou
  "regressão `<br>` literal residual no Texto" baseado em inspeção MCP
  de 5 pubs sample.
- Round 5b investigou: o conteúdo REAL no Notion (verificado via API
  REST direta em GET /v1/pages/{id}) tem ``\\n``, NÃO ``<br>``. O MCP
  server do Notion renderiza ``\\n`` como ``<br>`` em alguns lugares
  do enhanced-markdown — artefato de exibição, não conteúdo real.
- Conclusão: **a regressão NÃO existe**. O Round 4.5 (commit afddba4)
  já tratou o caso corretamente. Esta frente fecha sem fix de código.
- Estes testes formalizam o invariante: nenhuma forma de ``<br>``
  pode chegar ao Texto inline final.

Cobertura:
- Sentinela djen=494748109 (TRT10 Notif com trailer) — fixture com
  payload bruto idêntico ao SQLite.
- Sentinela djen=573369859 (TRT10 Acórdão com trailer).
- Sentinela djen=496542520 (TRT10 Lista, texto com `<br>` inline).
- Sentinela djen=524038068 (TJDFT Ata 57, texto extenso pós-filtro).
- Variantes XHTML (já cobertas em test_round_4 mas reforçadas aqui
  pra ficar tudo no mesmo arquivo do Round 5b).
"""
from __future__ import annotations

import re

from notion_rpadv.services.dje_text_pipeline import (
    preprocessar_texto_djen,
    truncar_texto_inline,
)

# Regex que detecta QUALQUER variante de tag br case-insensitive
_BR_DETECT = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _assert_no_br(texto: str, contexto: str = "") -> None:
    """Asserção forte: nenhuma forma de <br> está no texto."""
    matches = _BR_DETECT.findall(texto)
    assert not matches, (
        f"Encontrado <br> literal em {contexto}: matches={matches!r}, "
        f"texto[:200]={texto[:200]!r}"
    )
    # Também: nenhum <br substring (cobre <br ou <br anything>)
    assert "<br" not in texto.lower(), (
        f"Substring '<br' encontrada em {contexto}: texto[:200]={texto[:200]!r}"
    )


# ---------- Cluster 1: TRT10 Notif djen=494748109 (trailer 4 <br>) ----------


def test_R5b_trt10_notif_494748109_sem_br_no_inline():
    """Payload extraído do SQLite real. Trailer original tem 4 <br>:
    ``...Juiz do Trabalho Titular<br><br>Intimado(s) / Citado(s)<br>
    - BANCO DO BRASIL SA<br>``. Após pipeline + truncar_inline,
    NENHUM <br> residual.
    """
    texto_bruto = (
        "PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRT10 18ª Vara… "
        "Decisão conferida pela Diretora Ana Carolina Macena Barros. "
        "BRASILIA/DF, 19 de dezembro de 2025. JONATHAN QUINTAO JACOB "
        "Juiz do Trabalho Titular<br><br>Intimado(s) / Citado(s)<br>"
        " - BANCO DO BRASIL SA<br>"
    )
    assert texto_bruto.count("<br>") == 4

    texto_pre = preprocessar_texto_djen(texto_bruto)
    _assert_no_br(texto_pre, "preprocessar djen=494748109")

    inline = truncar_texto_inline(texto_pre, limite=2000)
    _assert_no_br(inline, "truncar_inline djen=494748109")
    # Trailer continua presente, com \n
    assert "Intimado(s) / Citado(s)" in inline
    assert "\n" in inline


# ---------- Cluster 2: TRT10 Acórdão (trailer + corpo longo) ----------


def test_R5b_trt10_acordao_573369859_sem_br_no_inline():
    """TRT10 Acórdão: trailer também tem <br>. Confirma que o pipeline
    funciona em texto > 2000 chars (truncamento ativo)."""
    texto_bruto = (
        "PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRT10 2ª TURMA " * 50  # padding pra >2000
        + "ACÓRDÃO 2.ª TURMA/2026 Assinado digitalmente. "
        "ELKE DORIS JUST Desembargadora Relatora DECLARAÇÃO DE VOTO "
        "BRASILIA/DF, 30 de março de 2026. ANA PAULA ASSUNCAO RODRIGUES, "
        "Servidor de Secretaria<br><br>Intimado(s) / Citado(s)<br>"
        " - ZULEIDE MALHEIROS DA FRANCA DA SILVA<br>"
    )

    texto_pre = preprocessar_texto_djen(texto_bruto)
    _assert_no_br(texto_pre, "preprocessar djen=573369859")

    inline = truncar_texto_inline(texto_pre, limite=2000)
    _assert_no_br(inline, "truncar_inline djen=573369859")
    assert len(inline) <= 2000


# ---------- Cluster 3: TRT10 Lista (texto curto com <br> inline) ----------


def test_R5b_trt10_lista_496542520_sem_br_no_inline():
    """Lista TRT10 tem padrão diferente: ``<br>`` no meio do texto, não
    só no trailer."""
    texto_bruto = (
        'Processo 0001969-51.2025.5.10.0008 distribuído para 8ª Vara '
        'do Trabalho de Brasília - DF na data 26/12/2025 <br> Para '
        'maiores informações, clique no link a seguir: <a href="https://'
        'pje.trt10.jus.br/pjekz/visualizacao/x">visualizar</a>'
    )

    texto_pre = preprocessar_texto_djen(texto_bruto)
    _assert_no_br(texto_pre, "preprocessar djen=496542520")

    inline = truncar_texto_inline(texto_pre, limite=2000)
    _assert_no_br(inline, "truncar_inline djen=496542520")
    assert "Para maiores informações" in inline


# ---------- Cluster 4: TJDFT Ata 57 (lista de CNJs + JULGADOS) ----------


def test_R5b_tjdft_ata_524038068_sem_br_no_inline():
    """Atas TJDFT pós-filtro 4.5b têm <br> nas separações da lista de
    CNJs JULGADOS. Confirma que TODOS são removidos."""
    # Trecho representativo da Ata 1ª TCV (djen=524038068).
    texto_bruto = (
        "Poder Judiciário da União<br>TRIBUNAL DE JUSTIÇA DO DF<br>"
        "1ª Turma Cível<br>1ª Sessão Ordinária Virtual - 1TCV "
        "(período 21 a 28/1/2026)<br><br>Ata da 1ª Sessão Ordinária "
        "Virtual da Primeira Turma Cível...<br>"
        " JULGADOS<br>0718822-04.2022.8.07.0018<br>"
        " 0709948-05.2023.8.07.0015<br> 0744299-49.2023.8.07.0000<br>"
    )

    texto_pre = preprocessar_texto_djen(texto_bruto)
    _assert_no_br(texto_pre, "preprocessar djen=524038068")

    inline = truncar_texto_inline(texto_pre, limite=2000)
    _assert_no_br(inline, "truncar_inline djen=524038068")
    assert "JULGADOS" in inline
    assert "0718822-04.2022.8.07.0018" in inline


# ---------- Variantes XHTML, escape duplo, case ----------


def test_R5b_variantes_br_todas_removidas():
    """Cobertura final: todas as formas conhecidas de <br> são
    removidas pelo pipeline (sentinela do _BR_RE)."""
    texto = (
        "linha1<br>linha2<br/>linha3<br />linha4<BR>linha5<Br />linha6"
        "<BR/>linha7<BR  />linha8\\<br\\>linha9"
    )
    out = preprocessar_texto_djen(texto)
    _assert_no_br(out, "variantes XHTML")
    # 9 linhas separadas (escape duplo \\<br\\> também é tratado)
    assert "linha1" in out
    assert "linha9" in out


def test_R5b_inline_truncamento_nao_introduz_br():
    """Edge case: o truncamento de inline sobre texto > 2000 chars
    não pode reintroduzir <br>."""
    texto_pre = "x" * 1990 + " conteúdo final <br> ainda mais"
    # Esse texto NÃO passou por preprocessar (cenário hipotético —
    # preprocessar removeria o <br>). Mas o truncar_texto_inline
    # NÃO é responsável por sanitizar, ele só corta.
    # Aqui validamos que o caminho normal (preprocessar → truncar)
    # nunca deixa <br>.
    texto_pre_clean = preprocessar_texto_djen(texto_pre)
    _assert_no_br(texto_pre_clean, "preprocessar truncamento")
    inline = truncar_texto_inline(texto_pre_clean, limite=2000)
    _assert_no_br(inline, "truncar_inline truncamento")


# ---------- Sanity: integração com observações ----------


def test_R5b_observacoes_tambem_sem_br():
    """Observações automáticas (`payload.observacoes`) também passam
    pelo preprocessador no _build_corpo_blocks_full."""
    obs_bruto = "Sócio sentinela ausente.<br>Verificar manualmente.<br/>"
    obs_pre = preprocessar_texto_djen(obs_bruto)
    _assert_no_br(obs_pre, "observações")
    assert "Sócio sentinela ausente." in obs_pre
    assert "Verificar manualmente." in obs_pre
