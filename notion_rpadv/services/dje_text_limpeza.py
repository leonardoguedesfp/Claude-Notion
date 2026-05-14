"""Limpeza de cabeçalho e trailer do `Texto` de publicações DJEN antes
de gravar no Notion (Round 11, 2026-05-13).

A função :func:`limpar_cabecalho_trailer` remove preâmbulos redundantes
(que repetem `Tribunal`, `Órgão`, `Classe`, `Partes` já estruturados nas
demais propriedades da pub) e trailers cerimoniais (assinaturas, listas
`Intimado(s) / Citado(s)`), preservando o corpo decisório útil.

Decisões de design (estudo empírico em ``docs/design/limpeza-texto-
publicacoes.md`` — n = 173 pubs):

- **Bypass por tipo:** `Distribuição`, `Pauta de Julgamento`, `Edital`
  e `Certidão` (e qualquer pub com `tipoComunicacao` em
  `{Lista de Distribuição, Edital}`) não são tocadas — o "ruído" é o
  conteúdo. ``49/173`` da amostra.
- **Bypass por padrão:** `Notifico o destinatário que os autos...`
  (TJRJ migração eproc) e `ARQUIVOS DIGITAIS INDISPONÍVEIS` (texto
  imprestável) recebem diagnóstico próprio e ficam intactos.
- **Marcadores unificados:** lista única para todas as famílias de
  tribunal, com `linha própria` específica para STJ/TJDFT.
- **Defesa contra falso positivo:** marcador casado a menos de 80 chars
  do início → ignorar (texto já começa com o "marcador", não há
  cabeçalho a remover).
- **Trailer no meio do texto:** se a posição do marcador de fim cair em
  menos de 70% do texto, ignorar (referência interna legítima).
- **Fallback:** quando nada casa, devolver texto cru. Limpeza preserva
  conteúdo por padrão.

Cobertura observada na amostra (n = 121 não-bypass):

| Família | Cobertura |
|---|---|
| TRF | 100% |
| TJDFT | 91% |
| Trabalhista | 86% |
| TJ-estadual | 71% |
| STJ | 55% |

Token savings projetado: ~125k tokens por rodada completa do
classificador (1.833 pubs × média ~19% de chars removidos).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Tipos de `Tipo de documento` que recebem bypass total (texto inteiro é
#: dado útil — limpar arrisca apagar conteúdo).
TIPOS_BYPASS_DOC: frozenset[str] = frozenset({
    "Distribuição",
    "Pauta de Julgamento",
    "Edital",
    "Certidão",
})

#: Tipos de `Tipo de comunicação` que recebem bypass total.
TIPOS_BYPASS_COM: frozenset[str] = frozenset({
    "Lista de Distribuição",
    "Edital",
})

#: Comprimento mínimo de cabeçalho aceito. Marcadores casados antes
#: dessa posição são descartados (texto começa direto com o marcador,
#: não há cabeçalho real a remover).
CABECALHO_MIN_CHARS: int = 80

#: O trailer só é cortado se a posição do marcador estiver depois desse
#: percentual do texto total. Defesa contra remoção de ocorrências
#: legítimas no meio do despacho.
TRAILER_POSICAO_MIN_PCT: float = 0.7

#: Tamanho-limite para considerar uma pub "texto imprestável" — abaixo
#: disso + presença do padrão `ARQUIVOS DIGITAIS INDISPONÍVEIS`.
TEXTO_IMPRESTAVEL_LIMITE: int = 200


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

#: Padrão TJRJ migração para eproc — bypass total.
RX_NOTIFICO_EPROC: re.Pattern[str] = re.compile(
    r"^\s*Notifico o destinat[áa]rio que os autos\b",
    re.IGNORECASE,
)

#: Texto imprestável (TJGO) — bypass total + diagnóstico.
RX_TEXTO_IMPRESTAVEL: re.Pattern[str] = re.compile(
    r"\bARQUIVOS\s+DIGITAIS\s+INDISPON[ÍI]VEIS\b",
    re.IGNORECASE,
)

#: CSS inline residual no início do texto (TJSC, TJRS). O DJEN às vezes
#: retorna o CSS junto do texto puro — escapou da limpeza HTML do
#: ``preprocessar_texto_djen``. Padrão observado:
#: ``body{ padding: 10px; font-family: ... }; #divHeader{ ... }; #divBody{ ... }``.
RX_CSS_LEAK: re.Pattern[str] = re.compile(
    r"^\s*body\s*\{[^}]*\}\s*;?\s*"
    r"(?:#div[A-Za-z_]+\s*\{[^}]*\}\s*;?\s*)*",
    re.IGNORECASE,
)

#: Quebras de linha 3+ consecutivas → 2 (preserva parágrafos).
RX_QUEBRAS_MULTIPLAS: re.Pattern[str] = re.compile(r"\n{3,}")

#: Espaços múltiplos (não-quebra) → 1 espaço.
RX_ESPACOS_MULTIPLOS: re.Pattern[str] = re.compile(r"[ \t]{2,}")

#: Caracteres de controle Unicode U+2400–U+243F ("Control Pictures") —
#: defesa do Round 2.1 contra mojibake.
RX_CONTROLE_UNICODE: re.Pattern[str] = re.compile(r"[␀-␿]")


#: Lista ordenada de marcadores de início do corpo útil. A ordem importa
#: apenas para o registro do diagnóstico (`marcador_inicio_casado`); a
#: posição final é a primeira ocorrência de qualquer marcador.
#:
#: Marcadores em "linha própria" (`\nMARCADOR\n`) vêm antes dos genéricos
#: porque, em pubs longas (STJ, TJDFT), são mais específicos e menos
#: propensos a falso positivo.
#:
#: **Round 11.1 (hotfix 13/05/2026):** os marcadores genéricos
#: ``DESPACHO/DECISÃO/SENTENÇA/ACÓRDÃO/EMENTA/RELATÓRIO`` são
#: **case-sensitive** (uppercase puro). O DJEN sempre traz esses
#: marcadores em maiúsculas; ocorrências minúsculas (``decisão.``,
#: ``acórdão recorrido``) são sempre referências internas no corpo —
#: aceitá-las gerava corte indevido em pubs que começavam direto pelo
#: dispositivo (e.g., ``"Sendo assim, CONHEÇO..."`` cortado em
#: ``"decisão."`` no meio do parágrafo). Antes da v11.1, ~3 pubs em
#: 1.833 (0,16%) ficaram com o dispositivo cortado. Após o fix essas
#: pubs caem em fallback (preservam o texto cru).
MARCADORES_INICIO: tuple[tuple[re.Pattern[str], str], ...] = (
    # Específicos — combinações de palavras conhecidas no início do corpo.
    # Mantêm re.I porque a frase composta inteira é específica o bastante.
    (re.compile(r"\bINTIMA[ÇC][ÃA]O\s*-\s*ATO\s+ORDINAT[ÓO]RIO\b", re.I),
     "INTIMAÇÃO - ATO ORDINATÓRIO"),
    (re.compile(r"\bATO\s+ORDINAT[ÓO]RIO\b", re.I),
     "ATO ORDINATÓRIO"),
    (re.compile(r"\bINTIMA[ÇC][ÃA]O\s+Fica\b", re.I),
     "INTIMAÇÃO Fica"),
    (re.compile(r"\bCERTID[ÃA]O\s+E\s+CONCLUS[ÃA]O\b", re.I),
     "CERTIDÃO E CONCLUSÃO"),
    # Marcadores em linha própria — uppercase puro (DJEN sempre maiúsculo)
    (re.compile(r"(?:^|\n)\s*ACÓRDÃO\s*\n"),
     "ACÓRDÃO (linha)"),
    (re.compile(r"(?:^|\n)\s*DECISÃO\s*\n"),
     "DECISÃO (linha)"),
    (re.compile(r"(?:^|\n)\s*SENTENÇA\s*\n"),
     "SENTENÇA (linha)"),
    (re.compile(r"(?:^|\n)\s*EMENTA\s*\n"),
     "EMENTA (linha)"),
    # Genéricos — uppercase puro (re.I removido no Round 11.1)
    (re.compile(r"\bDESPACHO\b"), "DESPACHO"),
    (re.compile(r"\bDECISÃO\b"), "DECISÃO"),
    (re.compile(r"\bSENTENÇA\b"), "SENTENÇA"),
    (re.compile(r"\bACÓRDÃO\b"), "ACÓRDÃO"),
    (re.compile(r"\bEMENTA\b"), "EMENTA"),
    (re.compile(r"\bRELATÓRIO\b"), "RELATÓRIO"),
    # Vistos pode aparecer "Vistos" ou "VISTOS" — re.I aqui é OK porque
    # "vistos" minúsculo no meio de despacho é raro.
    (re.compile(r"\bVistos[,.\s]", re.I), "Vistos"),
)


#: Lista de marcadores de trailer. A posição usada é a do **último**
#: marcador encontrado (mais provável de ser o fim de fato).
MARCADORES_FIM: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bIntimado\(s\)\s*/\s*Citado\(s\)", re.I),
     "Intimado(s)/Citado(s)"),
    (re.compile(r"\bAssinatura\s+(digital|eletr[ôo]nica)\b", re.I),
     "Assinatura digital/eletrônica"),
    (re.compile(r"\bDocumento assinado digitalmente\b", re.I),
     "Documento assinado digitalmente"),
    (re.compile(r"\bDOCUMENTO ASSINADO\b", re.I),
     "DOCUMENTO ASSINADO"),
    (re.compile(r"\bPublique-se[,.]", re.I),
     "Publique-se"),
    (re.compile(r"comunica\.pje\.jus\.br/Processo/", re.I),
     "URL comunica.pje"),
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DiagnosticoLimpeza:
    """Estrutura emitida em `_meta.limpeza_diag` de cada pub.

    Permite auditoria pós-execução via SQL no `leitor_dje.db` (a chave
    `limpeza_diag` é persistida em `publicacoes.payload_json` quando o
    caller injeta).
    """
    cabecalho_removido: bool = False
    fallback_aplicado: bool = False
    chars_removidos_inicio: int = 0
    chars_removidos_fim: int = 0
    marcador_inicio_casado: str | None = None
    marcador_fim_casado: str | None = None
    bypass_motivo: str | None = None     # None | "tipo" | "notifico_eproc" | "texto_imprestavel"
    texto_imprestavel: bool = False
    hash_pos_limpeza: str = ""
    normalizacoes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers de normalização
# ---------------------------------------------------------------------------


def _normalizar_basico(texto: str, diag: DiagnosticoLimpeza) -> str:
    """Normaliza texto antes da busca de marcadores. Roda sempre, mesmo
    nos caminhos de bypass."""
    s = texto

    # CSS leak no início (TJSC/TJRS) — só remove se realmente bate
    novo = RX_CSS_LEAK.sub("", s, count=1)
    if novo != s:
        diag.normalizacoes.append("css_leak_removido")
        s = novo

    # Caracteres de controle U+2400–U+243F
    if RX_CONTROLE_UNICODE.search(s):
        s = RX_CONTROLE_UNICODE.sub("", s)
        diag.normalizacoes.append("controle_unicode_removido")

    # Espaços múltiplos → 1
    s2 = RX_ESPACOS_MULTIPLOS.sub(" ", s)
    if s2 != s:
        diag.normalizacoes.append("espacos_colapsados")
        s = s2

    # Quebras 3+ → 2
    s2 = RX_QUEBRAS_MULTIPLAS.sub("\n\n", s)
    if s2 != s:
        diag.normalizacoes.append("quebras_colapsadas")
        s = s2

    return s.strip()


def _achar_primeiro_marcador(
    texto: str,
) -> tuple[int | None, str | None]:
    """Devolve (posição, label) do primeiro marcador de início que casa
    no texto. ``(None, None)`` quando nenhum casa.
    """
    pos_min: int | None = None
    label_min: str | None = None
    for rx, label in MARCADORES_INICIO:
        m = rx.search(texto)
        if m is None:
            continue
        if pos_min is None or m.start() < pos_min:
            pos_min = m.start()
            label_min = label
    return (pos_min, label_min)


def _achar_ultimo_marcador_fim(
    texto: str,
) -> tuple[int, str | None]:
    """Devolve (posição, label) do último marcador de fim encontrado no
    texto. Posição ``-1`` quando nenhum casa.
    """
    pos_max = -1
    label_max: str | None = None
    for rx, label in MARCADORES_FIM:
        for m in rx.finditer(texto):
            if m.start() > pos_max:
                pos_max = m.start()
                label_max = label
    return (pos_max, label_max)


def _limpar_trailer(texto: str, diag: DiagnosticoLimpeza) -> str:
    """Aplica corte de trailer com defesa contra "trailer no meio do
    texto"."""
    pos, label = _achar_ultimo_marcador_fim(texto)
    if pos < 0:
        return texto
    # Defesa: trailer precisa estar nos últimos 30% do texto.
    if pos < len(texto) * TRAILER_POSICAO_MIN_PCT:
        diag.marcador_fim_casado = f"{label} (ignorado: meio do texto)"
        return texto
    texto_limpo = texto[:pos].rstrip()
    diag.marcador_fim_casado = label
    diag.chars_removidos_fim = len(texto) - len(texto_limpo)
    return texto_limpo


def _hash_curto(texto: str) -> str:
    """SHA1 dos primeiros 16 hex chars do texto — usado para idempotência
    no recálculo."""
    return hashlib.sha1(texto.encode("utf-8", errors="replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def limpar_cabecalho_trailer(
    texto: str | None,
    *,
    tribunal: str | None = None,
    tipo_documento: str | None = None,
    tipo_comunicacao: str | None = None,
) -> tuple[str, DiagnosticoLimpeza]:
    """Remove cabeçalho redundante e trailer cerimonial do texto da
    publicação, devolvendo ``(texto_limpo, diagnóstico)``.

    Args:
        texto: conteúdo bruto da publicação (já passou por
            `preprocessar_texto_djen`).
        tribunal: sigla canônica de `Pub.Tribunal` (TRT10, STJ, TJDFT…).
        tipo_documento: tipo canônico de `Pub.Tipo de documento`
            (Despacho, Decisão, Acórdão…).
        tipo_comunicacao: tipo canônico de `Pub.Tipo de comunicação`
            (Intimação, Edital, Lista de Distribuição).

    Returns:
        Tupla ``(texto_limpo, DiagnosticoLimpeza)``. Em qualquer caminho
        de bypass ou fallback, ``texto_limpo`` é o texto **após
        normalização básica** (CSS leak removido, espaços/quebras
        colapsados) mas sem corte de cabeçalho/trailer.

    A função é **pura** — não lê arquivos, não acessa rede. Aceita
    ``None`` em qualquer kwarg sem levantar.
    """
    diag = DiagnosticoLimpeza()

    if not texto:
        diag.hash_pos_limpeza = _hash_curto("")
        return ("", diag)

    s = str(texto)

    # ----- 0. Bypass por tipo -----
    if (
        (tipo_documento and tipo_documento in TIPOS_BYPASS_DOC)
        or (tipo_comunicacao and tipo_comunicacao in TIPOS_BYPASS_COM)
    ):
        # Mesmo no bypass, a normalização básica roda — corrige CSS leak
        # e espaços absurdos sem mudar o conteúdo decisório.
        s = _normalizar_basico(s, diag)
        diag.bypass_motivo = "tipo"
        diag.hash_pos_limpeza = _hash_curto(s)
        return (s, diag)

    # ----- 1. Normalização básica (sempre) -----
    s = _normalizar_basico(s, diag)

    # ----- 2. Bypass por padrão de texto -----
    if RX_NOTIFICO_EPROC.match(s):
        diag.bypass_motivo = "notifico_eproc"
        diag.hash_pos_limpeza = _hash_curto(s)
        return (s, diag)

    if RX_TEXTO_IMPRESTAVEL.search(s) and len(s) < TEXTO_IMPRESTAVEL_LIMITE:
        diag.bypass_motivo = "texto_imprestavel"
        diag.texto_imprestavel = True
        diag.hash_pos_limpeza = _hash_curto(s)
        return (s, diag)

    # ----- 3. Procurar primeiro marcador de início -----
    pos_inicio, marcador = _achar_primeiro_marcador(s)

    # ----- 4. Defesa: marcador colado no início -----
    if pos_inicio is not None and pos_inicio < CABECALHO_MIN_CHARS:
        # Texto começa direto com (ou perto de) o marcador — não há
        # cabeçalho a remover. Aplica só trailer.
        diag.fallback_aplicado = True
        diag.marcador_inicio_casado = f"{marcador} (descartado: prematuro)"
        s = _limpar_trailer(s, diag)
        diag.hash_pos_limpeza = _hash_curto(s)
        return (s, diag)

    # ----- 5. Fallback: nenhum marcador casou -----
    if pos_inicio is None:
        diag.fallback_aplicado = True
        s = _limpar_trailer(s, diag)
        diag.hash_pos_limpeza = _hash_curto(s)
        return (s, diag)

    # ----- 6. Cortar cabeçalho -----
    s_sem_cab = s[pos_inicio:]
    diag.cabecalho_removido = True
    diag.chars_removidos_inicio = pos_inicio
    diag.marcador_inicio_casado = marcador

    # ----- 7. Limpar trailer -----
    s_final = _limpar_trailer(s_sem_cab, diag)
    diag.hash_pos_limpeza = _hash_curto(s_final)
    return (s_final, diag)


__all__ = [
    "CABECALHO_MIN_CHARS",
    "DiagnosticoLimpeza",
    "MARCADORES_FIM",
    "MARCADORES_INICIO",
    "TIPOS_BYPASS_COM",
    "TIPOS_BYPASS_DOC",
    "TRAILER_POSICAO_MIN_PCT",
    "limpar_cabecalho_trailer",
]
