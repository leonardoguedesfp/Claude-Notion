"""Pipeline de transformação do texto da publicação DJEN antes de enviar
ao Notion (Round 1, 2026-05-03).

A pipeline encadeia 4 estágios na seguinte ordem (importante!):

1. **Pré-processador HTML** (1.7) — texto bruto do DJEN → texto puro.
   Decodifica entidades HTML, converte ``<br>`` em ``\\n``, simplifica
   ``<a>`` → ``"Texto (URL)"``, remove tags residuais, normaliza
   espaços/quebras.

2. **Filtragem / truncamento** (1.5) — texto puro → texto pra corpo da
   página + blocos callout opcionais. Aplica filtragem inteligente em
   pautas TJDFT integrais (caso A) ou truncamento simples + callout
   "abrir certidão" (caso B).

3. **Block split com seções lógicas** (1.4) — texto pra corpo →
   lista de blocos Notion (heading_3 por seção + paragraph quebrado em
   chunks ≤ 2000 chars).

4. **Truncamento inline** (1.8) — texto puro → string ≤ 2000 chars
   pra propriedade "Texto" da página, cortada em fronteira de palavra.

Estágios 1 e 4 operam sobre o texto puro; 2 e 3 operam sobre o texto
direcionado pra corpo da página.
"""
from __future__ import annotations

import html as html_module
import logging
import re

logger = logging.getLogger("dje.text.pipeline")


# ===========================================================================
# 1.7 — Pré-processador HTML
# ===========================================================================

# Casamento de tags individuais. Patterns simples (não cobrem HTML
# arbitrário malformado, mas suficientes pra publicações DJE em produção
# que usam ``<p>``, ``<span>``, ``<br>`` e ``<a>`` predominantemente).
_A_TAG_RE: re.Pattern[str] = re.compile(
    r'<a\s+[^>]*?href="([^"]+)"[^>]*?>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_BR_RE: re.Pattern[str] = re.compile(
    r"<br\s*/?>",
    re.IGNORECASE,
)
_TAG_RESIDUAL_RE: re.Pattern[str] = re.compile(r"<[^>]+>")
_ESPACOS_MULTIPLOS_RE: re.Pattern[str] = re.compile(r" +")
_QUEBRAS_MULTIPLAS_RE: re.Pattern[str] = re.compile(r"\n{3,}")


def preprocessar_texto_djen(texto_bruto: str | None) -> str:
    """Recebe texto bruto do DJEN (com HTML, entities e escape duplo) e
    devolve texto puro normalizado.

    Pipeline:

    1. ``html.unescape`` (D-6): ``&amp;`` → ``&``, ``&nbsp;`` → ``\\xa0``, etc.
    2. Desfaz escape duplo (``\\<`` → ``<``, ``\\>`` → ``>``).
    3. ``<br>`` / ``<br />`` → ``\\n``.
    4. ``<a href="X">Y</a>`` → ``"Y"`` se ``Y == X``, senão ``"Y (X)"``.
    5. Tags residuais removidas.
    6. Espaços múltiplos colapsados; quebras 3+ → 2.
    7. Strip nas pontas.

    ``None`` ou string vazia → ``""`` (sem levantar).
    """
    if not texto_bruto:
        return ""
    s = str(texto_bruto)

    # 1. Decodifica entidades HTML
    s = html_module.unescape(s)

    # 2. Desfaz escape duplo
    s = s.replace("\\<", "<").replace("\\>", ">")

    # 3. <br> → \n (antes de simplificar <a>, pra que links com <br> dentro
    #    sejam tratados — embora não sejam comuns em DJEN)
    s = _BR_RE.sub("\n", s)

    # 4. <a href="X">Y</a> → "Y" se Y == X, senão "Y (X)"
    def _converter_link(m: re.Match[str]) -> str:
        href = m.group(1)
        # Texto interno pode ter tags aninhadas (ex: <a><strong>X</strong></a>);
        # remove tags antes de comparar com a href.
        texto_interno = _TAG_RESIDUAL_RE.sub("", m.group(2)).strip()
        if not texto_interno:
            return href
        if texto_interno == href:
            return texto_interno
        return f"{texto_interno} ({href})"

    s = _A_TAG_RE.sub(_converter_link, s)

    # 5. Tags residuais
    s = _TAG_RESIDUAL_RE.sub("", s)

    # 6. Normaliza espaços e quebras
    s = _ESPACOS_MULTIPLOS_RE.sub(" ", s)
    s = _QUEBRAS_MULTIPLAS_RE.sub("\n\n", s)

    # Substitui non-breaking space (\xa0 do html.unescape) por espaço comum.
    s = s.replace("\xa0", " ")

    # Re-normaliza espaços após substituição do nbsp.
    s = _ESPACOS_MULTIPLOS_RE.sub(" ", s)

    return s.strip()


# ===========================================================================
# 1.8 — Truncamento limpo do campo Texto inline
# ===========================================================================

#: Limite oficial Notion pra rich_text inline em uma propriedade.
TEXTO_INLINE_LIMIT_DEFAULT: int = 2000
TEXTO_INLINE_MARCADOR_DEFAULT: str = " […]"


def truncar_texto_inline(
    texto: str | None,
    *,
    limite: int = TEXTO_INLINE_LIMIT_DEFAULT,
    marcador: str = TEXTO_INLINE_MARCADOR_DEFAULT,
) -> str:
    """Trunca ``texto`` em até ``limite`` caracteres preservando fronteira
    de palavra (último espaço dentro de uma janela de busca antes do
    corte). Adiciona ``marcador`` no fim se houve corte.

    ``None`` ou string vazia → ``""``. Texto já dentro do limite passa
    intacto.

    O marcador conta dentro do limite (output total ≤ ``limite``).
    """
    if not texto:
        return ""
    s = str(texto)
    if len(s) <= limite:
        return s

    corte_max = limite - len(marcador)
    if corte_max <= 0:
        # Marcador maior que o limite — sem espaço pra cortar bonito.
        return s[:limite]

    janela_inicio = max(0, corte_max - 50)
    janela = s[janela_inicio:corte_max]
    ultimo_espaco = janela.rfind(" ")
    if ultimo_espaco >= 0:
        ponto_corte = janela_inicio + ultimo_espaco
    else:
        ponto_corte = corte_max
    return s[:ponto_corte].rstrip() + marcador
