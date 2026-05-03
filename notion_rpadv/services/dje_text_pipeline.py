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


# ===========================================================================
# 1.5 — Filtragem inteligente Pautas TJDFT + Truncamento simples
# ===========================================================================

#: Limite de bytes (chars) abaixo do qual a publicação passa intacta.
#: Acima disso, no caso A entra na filtragem; no caso B, em truncamento
#: simples + callout pra certidão oficial DJEN.
LIMITE_TRUNCAMENTO_BYTES: int = 80_000

#: Limite mínimo de tamanho pra disparar filtragem da pauta TJDFT.
#: Pautas curtas (single-process, < 5KB) não disparam — passam intactas.
PAUTA_FILTRO_MIN_BYTES: int = 5_000

#: Tipos canônicos (após 1.1) que disparam filtragem em pautas integrais.
PAUTA_TJDFT_TIPOS_DOC: frozenset[str] = frozenset({
    "Pauta de Julgamento",
    # Variantes pré-canônicas (caller pode passar bruto ou canônico).
    "PAUTA DE JULGAMENTOS",
})

#: 12 OABs do escritório com sufixo opcional ``-A``/``-S`` (Aprovado/Suplente).
#: Aceita 5 OU 6 dígitos (zeros à esquerda) — DJEN às vezes serializa
#: ``DF015523``, ``DF15523``, ``DF15523-A``, ``DF015523-A``.
_OAB_ESCRITORIO_RE: re.Pattern[str] = re.compile(
    r"\bDF\s*(?:0*15523|0*36129|0*48468|0*20120|0*38809|0*75799|"
    r"0*65089|0*81225|0*37654|0*39857|0*84703|0*79658)\b(?:-[A-Z])?",
    re.IGNORECASE,
)

#: Detecta o início de um bloco "Processo\n0000000-00.AAAA..." em pautas
#: TJDFT integrais (após pré-processamento). Sem capturar o CNJ inteiro
#: — só precisa da posição do início do bloco.
_PROCESSO_BLOCO_RE: re.Pattern[str] = re.compile(
    r"\nProcesso\n\d{7}-\d{2}\.\d{4}",
)


def deve_filtrar_pauta_tjdft(
    tribunal: str | None,
    tipo_documento: str | None,
    texto: str | None,
) -> bool:
    """``True`` se a publicação se qualifica pra filtragem inteligente
    (caso A do 1.5): tribunal=TJDFT + tipo=Pauta de Julgamento (canônico
    OU variante CAPS) + texto > 5000 chars.

    Pautas pequenas (single-process) e pautas de outros tribunais não
    disparam.
    """
    if not tribunal or not tipo_documento or not texto:
        return False
    return (
        str(tribunal).strip().upper() == "TJDFT"
        and str(tipo_documento).strip() in PAUTA_TJDFT_TIPOS_DOC
        and len(texto) > PAUTA_FILTRO_MIN_BYTES
    )


def filtrar_pauta_tjdft(texto: str) -> str | None:
    """Aplica filtragem inteligente em pauta TJDFT integral. Devolve:

    - ``texto filtrado`` (cabeçalho + apenas blocos com OAB escritório +
      nota explicativa) — caso normal.
    - ``texto compacto`` (cabeçalho + nota D-9) — caso 0 matches.
    - ``None`` — falha de parsing (caller faz fallback pra truncamento
      simples). Acontece se o regex de Processo não acha nenhum bloco
      (texto não está no formato esperado).
    """
    starts = [m.start() for m in _PROCESSO_BLOCO_RE.finditer(texto)]
    if not starts:
        return None  # parsing falhou — sai pro fallback caso B

    cabecalho = texto[: starts[0]].strip()
    starts_marcados = [*starts, len(texto)]
    blocos = [
        texto[starts_marcados[i]:starts_marcados[i + 1]]
        for i in range(len(starts_marcados) - 1)
    ]

    blocos_match = [b for b in blocos if _OAB_ESCRITORIO_RE.search(b)]

    if blocos_match:
        nota = (
            f"\n\n[Pauta filtrada automaticamente: "
            f"{len(blocos_match)} de {len(blocos)} processos pertencem ao escritório.]\n"
        )
        return cabecalho + nota + "".join(blocos_match)
    # D-9: nenhum processo do escritório. Mantém cabeçalho + nota.
    nota_d9 = (
        f"\n\n[0 processos do escritório nesta pauta de {len(blocos)} processos. "
        f"Pauta possivelmente capturada por menção tangencial. "
        f"Conteúdo integral disponível na certidão oficial.]\n"
    )
    return cabecalho + nota_d9


def truncar_corpo_simples(
    texto: str,
    *,
    limite: int = LIMITE_TRUNCAMENTO_BYTES,
) -> tuple[str, bool]:
    """Truncamento simples pra textos > ``limite`` bytes. Tenta cortar
    em ``\\n`` próximo do limite (janela de 200 chars) — se não achar,
    corta cru. Devolve ``(texto_truncado, foi_truncado)``."""
    if len(texto) <= limite:
        return texto, False
    janela_inicio = max(0, limite - 200)
    janela = texto[janela_inicio:limite]
    ultima_quebra = janela.rfind("\n")
    if ultima_quebra >= 0:
        ponto_corte = janela_inicio + ultima_quebra
    else:
        ponto_corte = limite
    return texto[:ponto_corte].rstrip(), True


def _callout_certidao(qtd_chars: int, hash_djen: str) -> dict:
    """Block callout amarelo com ícone ⚠ apontando pra certidão oficial DJEN
    quando o corpo foi truncado."""
    url_certidao = (
        f"https://comunicaapi.pje.jus.br/api/v1/comunicacao/{hash_djen}/certidao"
    )
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "⚠"},  # ⚠ (warning)
            "color": "yellow_background",
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": (
                            f"Texto truncado em {qtd_chars:,} caracteres. "
                            f"Conteúdo integral em PDF assinado: "
                        ),
                    },
                },
                {
                    "type": "text",
                    "text": {
                        "content": "Abrir certidão oficial DJEN",
                        "link": {"url": url_certidao},
                    },
                },
            ],
        },
    }


def aplicar_caso_15(
    *,
    tribunal: str | None,
    tipo_documento: str | None,
    texto: str | None,
    hash_djen: str | None,
) -> tuple[str, list[dict]]:
    """Pipeline completa do estágio 2 da text pipeline.

    Recebe texto JÁ pré-processado (1.7) e devolve:

    - ``texto_para_corpo``: texto que vai pro split em blocos (1.4).
      Pode ser o original (publicação curta), filtrado (caso A) ou
      truncado (caso B).
    - ``blocos_callout``: lista (vazia ou 1 bloco) com callout
      "abrir certidão" — anexar AO FIM dos blocos do corpo. Caso A
      filtrado não emite callout (filtragem é suficiente). Caso B
      sempre emite.

    ``hash_djen`` é usado pra montar a URL da certidão. ``None`` ou vazio
    desabilita o link mas mantém o callout texto-only.
    """
    if not texto:
        return "", []
    s = str(texto)

    if deve_filtrar_pauta_tjdft(tribunal, tipo_documento, s):
        filtrado = filtrar_pauta_tjdft(s)
        if filtrado is not None:
            logger.info(
                "DJE.text.pipeline: pauta TJDFT filtrada (%d → %d chars)",
                len(s), len(filtrado),
            )
            return filtrado, []
        # Parsing falhou — segue pro caso B
        logger.warning(
            "DJE.text.pipeline: pauta TJDFT sem blocos Processo "
            "detectáveis — caindo pra truncamento simples",
        )

    truncado, foi_truncado = truncar_corpo_simples(s)
    if foi_truncado:
        logger.info(
            "DJE.text.pipeline: corpo truncado (%d → %d chars) — anexando "
            "callout pra certidão",
            len(s), len(truncado),
        )
        callout = _callout_certidao(len(truncado), hash_djen or "")
        return truncado, [callout]

    return s, []
