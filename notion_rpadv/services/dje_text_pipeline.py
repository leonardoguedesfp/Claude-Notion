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


# ===========================================================================
# 1.4 — Block split com detecção de seções lógicas
# ===========================================================================

#: Limite duro de blocos por chamada na API Notion: 100. Usamos 90 pra
#: deixar margem (overflow é enviado via ``append_block_children``).
LIMITE_BLOCOS_INICIAIS: int = 90

#: Tamanho-alvo (chars) ao agrupar parágrafos em um bloco paragraph.
#: Folga até o limite duro de 2000 do Notion permite escrever buffers
#: confortáveis sem rodar atrás do limite.
TAMANHO_PARAGRAFO_ALVO: int = 1500

#: Limite duro do Notion API por bloco rich_text.
NOTION_BLOCK_HARD_LIMIT: int = 2000

#: Heurística de detecção de seções lógicas — palavras-chave que aparecem
#: SOZINHAS na linha (mark + start + end com possível espaço) em
#: acórdãos/decisões/sentenças. Case-insensitive. Pode capturar falsos
#: positivos em pautas (que repetem "VOTO" como tag), por isso é usada
#: apenas como heurística — quando não detecta seções, faz fallback pra
#: agrupamento por parágrafos.
_SECOES_LOGICAS_RE: re.Pattern[str] = re.compile(
    r"^(EMENTA|RELATÓRIO|RELATORIO|VOTO|DISPOSITIVO|"
    r"CONCLUSÃO|CONCLUSAO|ACÓRDÃO|ACORDAO|"
    r"FUNDAMENTAÇÃO|FUNDAMENTACAO)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _heading3_block(titulo: str) -> dict:
    """Bloco heading_3 com o título da seção em uppercase canônico."""
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [
                {"type": "text", "text": {"content": titulo}},
            ],
        },
    }


def _paragraph_block(content: str) -> dict:
    """Bloco paragraph — chama-se DEPOIS de garantir que ``content`` cabe
    em ``NOTION_BLOCK_HARD_LIMIT`` chars."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": content}},
            ],
        },
    }


def _split_chunk_em_palavra(texto: str, limite: int) -> list[str]:
    """Divide ``texto`` em chunks ≤ ``limite`` chars cada, preferindo
    cortar em ``\\n`` ou espaço próximo do limite (janela de 80 chars).
    Sem espaço/quebra próximo: corta cru."""
    if len(texto) <= limite:
        return [texto]
    out: list[str] = []
    pos = 0
    while pos < len(texto):
        end = min(pos + limite, len(texto))
        if end == len(texto):
            out.append(texto[pos:end])
            break
        # Tenta cortar em \n primeiro (preferido), depois espaço.
        janela_inicio = max(pos, end - 80)
        janela = texto[janela_inicio:end]
        cut_rel = janela.rfind("\n")
        if cut_rel < 0:
            cut_rel = janela.rfind(" ")
        if cut_rel >= 0:
            cut_abs = janela_inicio + cut_rel
            out.append(texto[pos:cut_abs])
            pos = cut_abs + 1  # pula o separador
        else:
            out.append(texto[pos:end])
            pos = end
    return [c for c in out if c]


def _agrupar_em_paragrafos(texto: str) -> list[dict]:
    """Recebe texto sem heading e devolve lista de blocos paragraph
    agrupando parágrafos consecutivos até ~``TAMANHO_PARAGRAFO_ALVO``.

    Parágrafos longos (>= NOTION_BLOCK_HARD_LIMIT) são SPLIT em múltiplos
    blocos sem perda de conteúdo. Vazio devolve lista vazia.
    """
    if not texto:
        return []
    paragrafos_brutos = re.split(r"\n\s*\n", texto)
    blocos: list[dict] = []
    buffer: list[str] = []
    buffer_len = 0

    def _flush_buffer() -> None:
        nonlocal buffer, buffer_len
        if not buffer:
            return
        joined = "\n\n".join(buffer)
        for chunk in _split_chunk_em_palavra(joined, NOTION_BLOCK_HARD_LIMIT):
            if chunk.strip():
                blocos.append(_paragraph_block(chunk))
        buffer = []
        buffer_len = 0

    for p in paragrafos_brutos:
        p = p.strip()
        if not p:
            continue
        # Parágrafo único maior que o alvo? Flusha buffer e emite isolado
        # (ainda sujeito a split em chunks de ≤ NOTION_BLOCK_HARD_LIMIT).
        if len(p) >= TAMANHO_PARAGRAFO_ALVO:
            _flush_buffer()
            for chunk in _split_chunk_em_palavra(p, NOTION_BLOCK_HARD_LIMIT):
                if chunk.strip():
                    blocos.append(_paragraph_block(chunk))
            continue
        # Caberia no buffer atual?
        if buffer_len + len(p) + 2 > TAMANHO_PARAGRAFO_ALVO and buffer:
            _flush_buffer()
        buffer.append(p)
        buffer_len += len(p) + 2

    _flush_buffer()
    return blocos


def _detectar_secoes(texto: str) -> list[tuple[str | None, str]]:
    """Devolve ``[(titulo_uppercase_ou_None, conteudo), ...]`` segmentando
    pelas seções lógicas detectadas. Lista vazia → não detectou nenhuma
    (caller faz fallback pra agrupamento por parágrafos)."""
    matches = list(_SECOES_LOGICAS_RE.finditer(texto))
    if not matches:
        return []
    secoes: list[tuple[str | None, str]] = []
    # Preâmbulo (texto antes da 1ª seção)
    if matches[0].start() > 0:
        preambulo = texto[: matches[0].start()].strip()
        if preambulo:
            secoes.append((None, preambulo))
    for i, m in enumerate(matches):
        titulo = m.group(0).strip().upper()
        ini = m.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        conteudo = texto[ini:fim].strip()
        if conteudo:
            secoes.append((titulo, conteudo))
    return secoes


def quebrar_em_blocos(texto: str | None) -> list[dict]:
    """Recebe texto puro (já pré-processado por 1.7) e devolve lista de
    blocos Notion (heading_3 quando há seções detectadas + paragraphs).

    Se nenhuma seção é detectada, agrupa diretamente em parágrafos sem
    headings.

    Vazio → lista vazia. Caller é responsável por adicionar blocos
    "wrapper" (heading_2 "Texto da publicação", "Observações", etc.)
    em volta destes.
    """
    if not texto:
        return []
    s = str(texto)
    secoes = _detectar_secoes(s)
    if not secoes:
        return _agrupar_em_paragrafos(s)
    blocos: list[dict] = []
    for titulo, conteudo in secoes:
        if titulo:
            blocos.append(_heading3_block(titulo))
        blocos.extend(_agrupar_em_paragrafos(conteudo))
    return blocos
