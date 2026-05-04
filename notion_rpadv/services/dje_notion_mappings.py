"""Mapeamentos canônicos DJEN→Notion (Round 1, 2026-05-03).

Centraliza 3 grupos de mapeamentos usados pelo envio de publicações pra
database 📬 Publicações:

1. **Tipo de documento** (1.1) — 34 variantes → 10 canônicas + Outros.
   Necessário porque o DJEN devolve grafias inconsistentes ("Acórdão" /
   "ACORDAO" / "EMENTA / ACORDÃO"); o Notion tem propriedade Select com
   opções fixas.
2. **Tipo de comunicação** (1.2) — 3 variantes → 3 canônicas (apenas
   correção de casing em "Lista de distribuição" → "Lista de Distribuição").
3. **Advogados intimados** (1.3) — cruzamento OAB+UF do escritório
   (12 OABs: 6 ativas + 6 desativadas) com formato canônico
   ``"Nome (OAB/UF)"`` no Multi-select. Externos são desprezados.

Decisões consolidadas (D-1, D-7) tratadas aqui:
- D-1: ``tipoDocumento`` null/vazio → "Outros".
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("dje.notion.mappings")


# ---------------------------------------------------------------------------
# 1.1 — Tipo de documento
# ---------------------------------------------------------------------------

#: Conjunto canônico de valores aceitos pelo Select "Tipo de documento" no
#: Notion. Tudo que o DJEN devolve é normalizado para um destes (ou "Outros").
TIPOS_DOCUMENTO_CANONICOS: frozenset[str] = frozenset({
    "Notificação",
    "Distribuição",
    "Acórdão",
    "Decisão",
    "Despacho",
    "Pauta de Julgamento",
    "Certidão",
    "Ementa",
    "Sentença",
    "Outros",
})


#: Tabela de mapeamento das variantes do DJEN → canônico. Cobre as 34
#: variantes vistas em produção (jan-mai/2026, 2141 publicações). Variantes
#: não listadas caem em "Outros" (D-1).
MAPA_TIPO_DOCUMENTO: dict[str, str] = {
    # Notificação
    "Notificação": "Notificação",

    # Distribuição
    "Distribuição": "Distribuição",
    "ATA DE DISTRIBUIÇÃO": "Distribuição",

    # Acórdão (variantes de casing + conjunções)
    "Acórdão": "Acórdão",
    "ACORDAO": "Acórdão",
    "EMENTA / ACORDÃO": "Acórdão",

    # Decisão
    "Decisão": "Decisão",
    "DECISÃO MONOCRÁTICA": "Decisão",
    "DESPACHO / DECISÃO": "Decisão",
    "DESPACHO/DECISÃO": "Decisão",

    # Despacho (incl. atos ordinatórios e VISTAs processuais)
    "Despacho": "Despacho",
    "Conclusão": "Despacho",
    "Ato ordinatório": "Despacho",
    "VISTA à(s) parte(s) embargada(s) para impugnação dos Embargos de Declaração (EDcl)": "Despacho",
    "VISTA à(s) parte(s) agravada(s) para impugnação do Agravo Interno (AgInt)": "Despacho",
    "VISTA à(s) parte(s) recorrida(s) para contrarrazões de Recurso Extraordinário (RE)": "Despacho",
    "VISTA à(s) parte(s) embargada(s) para impugnação": "Despacho",
    "VISTA à(s) parte(s) agravada(s) para resposta": "Despacho",

    # Pauta de Julgamento (incl. aditamentos e intimação de pauta)
    "Pauta de Julgamento": "Pauta de Julgamento",
    "PAUTA DE JULGAMENTOS": "Pauta de Julgamento",
    "Aditamento à Pauta de Julgamento": "Pauta de Julgamento",
    "ADITAMENTO À PAUTA DE JULGAMENTOS": "Pauta de Julgamento",
    "Intimação de pauta": "Pauta de Julgamento",

    # Certidão
    "Certidão": "Certidão",

    # Ementa
    "Ementa": "Ementa",

    # Sentença
    "Sentença": "Sentença",

    # Outros (catch-all explícito + casos especiais)
    "Intimação": "Outros",
    "Audiência": "Outros",
    "57": "Outros",
    "Outros": "Outros",
    "Agravo de Instrumento": "Outros",
    "AGRAVO EM RECURSO ESPECIAL - CÍVEL": "Outros",
    "Contrarrazões Agravo": "Outros",
    "Contrarrazões RE": "Outros",
}


def mapear_tipo_documento(valor_djen: str | None) -> str:
    """Mapeia ``valor_djen`` (tipoDocumento bruto da API) para canônico
    do Select Notion. ``None`` ou string vazia → "Outros" (D-1)."""
    if not valor_djen:
        return "Outros"
    return MAPA_TIPO_DOCUMENTO.get(str(valor_djen).strip(), "Outros")


# ---------------------------------------------------------------------------
# 1.2 — Tipo de comunicação
# ---------------------------------------------------------------------------

#: Canônicas aceitas pelo Select "Tipo de comunicação" no Notion.
TIPOS_COMUNICACAO_CANONICOS: frozenset[str] = frozenset({
    "Intimação",
    "Lista de Distribuição",
    "Edital",
})


#: Mapeamento DJEN→Notion. Apenas correção de casing na "Lista de
#: distribuição" (DJEN escreve com 'd' minúsculo; Notion canônico é
#: "D" maiúsculo). Round 6 (2026-05-04): mapa também aceita o canônico
#: como entrada (idempotência) — necessário porque algumas regras já
#: rodam após o mapeamento e podem re-passar o valor canônico.
MAPA_TIPO_COMUNICACAO: dict[str, str] = {
    "Intimação": "Intimação",
    "Lista de distribuição": "Lista de Distribuição",
    "Lista de Distribuição": "Lista de Distribuição",
    "Edital": "Edital",
}


def mapear_tipo_comunicacao(valor_djen: str | None) -> str:
    """Mapeia ``valor_djen`` (tipoComunicacao bruto) para canônico do Select.

    ``None``/vazio ou variante não mapeada → "Intimação" (default razoável,
    com warning). Cobre 100% do inventário de produção.
    """
    if not valor_djen:
        logger.warning(
            "DJE.notion.mappings: tipoComunicacao vazio — usando default 'Intimação'",
        )
        return "Intimação"
    s = str(valor_djen).strip()
    canonico = MAPA_TIPO_COMUNICACAO.get(s)
    if canonico is None:
        logger.warning(
            "DJE.notion.mappings: tipoComunicacao desconhecido %r — "
            "usando default 'Intimação'",
            s,
        )
        return "Intimação"
    return canonico


# ---------------------------------------------------------------------------
# 1.3 — Advogados do escritório (Multi-select)
# ---------------------------------------------------------------------------

#: 12 OABs do escritório (6 ativas + 6 desativadas). Cruzamento por
#: ``"<OAB>/<UF>"`` (UF uppercase, OAB sem zeros à esquerda) →
#: rótulo canônico exibido no Multi-select do Notion.
#:
#: Formato do rótulo: ``"PrimeiroNome (OAB/UF)"`` — o nome curto traz
#: contexto humano e a OAB/UF garante unicidade entre homônimos
#: ("Juliana Vieira" e "Juliana Chiaratto"). Padrão definido no Round 1
#: (substitui o formato antigo só com primeiro nome).
ADVOGADOS_ESCRITORIO: dict[str, str] = {
    # Ativos (Fase 4 reativou os 4)
    "15523/DF": "Ricardo (15523/DF)",
    "36129/DF": "Leonardo (36129/DF)",
    "48468/DF": "Vitor (48468/DF)",
    "20120/DF": "Cecília (20120/DF)",
    "38809/DF": "Samantha (38809/DF)",
    "75799/DF": "Deborah (75799/DF)",
    # Desativados (Fase 2.1) — pubs antigas no banco podem trazer qualquer um
    "65089/DF": "Juliana Vieira (65089/DF)",
    "81225/DF": "Juliana Chiaratto (81225/DF)",
    "37654/DF": "Shirley (37654/DF)",
    "39857/DF": "Erika (39857/DF)",
    "84703/DF": "Maria Isabel (84703/DF)",
    "79658/DF": "Cristiane (79658/DF)",
}


def _normaliza_chave_oab(numero_oab: str | None, uf_oab: str | None) -> str | None:
    """``("036129", "df")`` → ``"36129/DF"``. ``None``/vazio → ``None``.

    Strip de zeros à esquerda + uppercase da UF. Tolerante a inputs
    incompletos (devolve None, sem levantar)."""
    if not numero_oab or not uf_oab:
        return None
    digits = "".join(c for c in str(numero_oab) if c.isdigit()).lstrip("0")
    uf = str(uf_oab).strip().upper()
    if not digits or not uf:
        return None
    return f"{digits}/{uf}"


def formatar_advogados_intimados(
    destinatarioadvogados: Any,
) -> list[str]:
    """Recebe ``destinatarioadvogados`` do JSON DJEN; devolve lista de
    rótulos do Multi-select pro Notion.

    Filtra: só OABs do escritório (12). Externos são desprezados.
    Dedup: mesma OAB que aparece 2x (padrão patológico DJEN) entra 1 só.
    Ordem: alfabética dos rótulos (estável entre execuções).

    Estrutura esperada por entry (descoberta do smoke da Fase 2.2):
    ``{"advogado": {"numero_oab": "...", "uf_oab": "...", ...}, ...}``.
    Fallback (entries legacy) também olha no nível raiz da entry.
    """
    if not isinstance(destinatarioadvogados, list):
        return []
    seen: set[str] = set()
    for entry in destinatarioadvogados:
        if not isinstance(entry, dict):
            continue
        adv = (
            entry.get("advogado")
            if isinstance(entry.get("advogado"), dict)
            else entry
        )
        chave = _normaliza_chave_oab(
            adv.get("numero_oab"),
            adv.get("uf_oab"),
        )
        if chave is None:
            continue
        rotulo = ADVOGADOS_ESCRITORIO.get(chave)
        if rotulo is not None:
            seen.add(rotulo)
    return sorted(seen)


def tinha_destinatarios_advogados(destinatarioadvogados: Any) -> bool:
    """``True`` se ``destinatarioadvogados`` é lista não-vazia de dicts.
    Usado pra distinguir "lista vazia" (não marca checkbox "Advogados não
    cadastrados") de "lista só com externos" (marca o checkbox)."""
    return (
        isinstance(destinatarioadvogados, list)
        and any(isinstance(e, dict) for e in destinatarioadvogados)
    )


# ---------------------------------------------------------------------------
# Round 4.2 — Normalização de nomeClasse (casing torto do DJEN)
# ---------------------------------------------------------------------------

#: Tabela de canonização do ``nomeClasse`` do DJEN. As 22 variantes com
#: casing torto vistas em produção (vogais acentuadas em maiúsculas
#: viraram minúsculas — ex: ``AçãO`` em vez de ``AÇÃO``) mais 1 caso em
#: title case (``Procedimento do Juizado Especial da Fazenda Pública``)
#: mapeiam para CAPS uniforme. As 8 já em CAPS corretas ficam fora do
#: mapa: o fallback de ``normalizar_classe`` preserva o valor cru.
#:
#: Cobertura: 31 variantes do acervo Round 3 (2.152 publicações).
#: Classes futuras não listadas passam pelo fallback (preservar cru),
#: evitando regressão se uma classe nova vier bem formatada.
MAPA_NOMECLASSE: dict[str, str] = {
    # Casing torto (DJEN serializa "AçãO" em vez de "AÇÃO")
    "AçãO TRABALHISTA - RITO ORDINáRIO": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
    "RECURSO ORDINáRIO TRABALHISTA": "RECURSO ORDINÁRIO TRABALHISTA",
    "CUMPRIMENTO DE SENTENçA": "CUMPRIMENTO DE SENTENÇA",
    "AGRAVO DE PETIçãO": "AGRAVO DE PETIÇÃO",
    "PROCEDIMENTO COMUM CíVEL": "PROCEDIMENTO COMUM CÍVEL",
    "EMBARGOS DE DECLARAçãO CíVEL": "EMBARGOS DE DECLARAÇÃO CÍVEL",
    "CUMPRIMENTO PROVISóRIO DE SENTENçA": "CUMPRIMENTO PROVISÓRIO DE SENTENÇA",
    "APELAçãO CíVEL": "APELAÇÃO CÍVEL",
    "LIQUIDAçãO POR ARBITRAMENTO": "LIQUIDAÇÃO POR ARBITRAMENTO",
    "LIQUIDAçãO DE SENTENçA PELO PROCEDIMENTO COMUM": (
        "LIQUIDAÇÃO DE SENTENÇA PELO PROCEDIMENTO COMUM"
    ),
    "AçãO TRABALHISTA - RITO SUMARíSSIMO": "AÇÃO TRABALHISTA - RITO SUMARÍSSIMO",
    "AGRAVO INTERNO CíVEL": "AGRAVO INTERNO CÍVEL",
    "EMBARGOS DE DIVERGêNCIA EM RECURSO ESPECIAL": (
        "EMBARGOS DE DIVERGÊNCIA EM RECURSO ESPECIAL"
    ),
    "PROCEDIMENTO DO JUIZADO ESPECIAL CíVEL": "PROCEDIMENTO DO JUIZADO ESPECIAL CÍVEL",
    "RECURSO ORDINáRIO - RITO SUMARíSSIMO": "RECURSO ORDINÁRIO - RITO SUMARÍSSIMO",
    "LIQUIDAçãO PROVISóRIA POR ARBITRAMENTO": "LIQUIDAÇÃO PROVISÓRIA POR ARBITRAMENTO",
    "EXECUçãO PROVISóRIA EM AUTOS SUPLEMENTARES": (
        "EXECUÇÃO PROVISÓRIA EM AUTOS SUPLEMENTARES"
    ),
    "CONFLITO DE COMPETêNCIA": "CONFLITO DE COMPETÊNCIA",
    "PETIçãO CíVEL": "PETIÇÃO CÍVEL",
    "EXECUçãO DE TíTULO EXTRAJUDICIAL": "EXECUÇÃO DE TÍTULO EXTRAJUDICIAL",
    "INVENTáRIO": "INVENTÁRIO",
    # Title case → CAPS (apenas 1 caso visto em produção)
    "Procedimento do Juizado Especial da Fazenda Pública": (
        "PROCEDIMENTO DO JUIZADO ESPECIAL DA FAZENDA PÚBLICA"
    ),
    # NOTE: classes já em CAPS corretas (RECURSO ESPECIAL, AGRAVO,
    # AGRAVO DE INSTRUMENTO, RECURSO DE REVISTA, etc.) NÃO entram no
    # mapa — passam pelo fallback que preserva o valor cru.
    # TODO: revisar quando aparecerem novas variantes (volume diário
    # esperado: ~17 pubs/dia; provável encontrar classes novas conforme
    # a base cresce).
}


def normalizar_classe(valor: str | None) -> str:
    """Devolve o ``nomeClasse`` canonizado (CAPS uniforme com acentos
    corretos) usando ``MAPA_NOMECLASSE``. Variantes não listadas
    passam intactas — preserva valor cru pra evitar regressão em
    classes futuras que venham bem formatadas.

    ``None`` ou string vazia → ``""``.
    """
    if not valor:
        return ""
    s = str(valor).strip()
    return MAPA_NOMECLASSE.get(s, s)


# ---------------------------------------------------------------------------
# Round 4 — Formatação de Partes (Polo Ativo / Passivo / Terceiro)
# ---------------------------------------------------------------------------

#: Mapeamento canônico de polos do DJEN → label legível para a propriedade
#: ``Partes`` da database 📬 Publicações. Polos não listados caem no
#: fallback ``Polo {valor}`` (defesa contra casos desconhecidos).
POLO_LABEL: dict[str, str] = {
    "A": "Polo Ativo",
    "P": "Polo Passivo",
    "T": "Terceiro Interessado",
}

#: Ordem de exibição fixa: Ativo → Passivo → Terceiro. Polos fora dessa
#: ordem aparecem depois, na ordem de primeira aparição no payload.
POLO_ORDEM_CANONICA: tuple[str, ...] = ("A", "P", "T")

#: Limite Notion para rich_text inline em uma propriedade.
PARTES_INLINE_LIMIT: int = 2000
PARTES_TRUNCAMENTO_MARCADOR: str = "…"


def formatar_partes(destinatarios: Any) -> str:
    """Recebe ``destinatarios`` (lista de dicts do DJEN com ``nome`` e
    ``polo``) e devolve string formatada legível para a propriedade
    ``Partes`` no Notion.

    Formato:

    ::

        Polo Ativo: NOME 1, NOME 2
        Polo Passivo: NOME 3
        Terceiro Interessado: NOME 4

    Regras:

    - Mapeamento ``A`` → ``Polo Ativo``, ``P`` → ``Polo Passivo``,
      ``T`` → ``Terceiro Interessado``. Polos desconhecidos:
      ``Polo {valor}`` como fallback defensivo.
    - Múltiplos nomes no mesmo polo: separados por vírgula, ordem de
      aparição preservada, dedup por nome (case-sensitive).
    - Ordem entre polos: Ativo, Passivo, Terceiro Interessado. Polos
      não-canônicos vêm depois na ordem de primeira aparição.
    - Cada polo em uma linha, separador ``\\n`` entre linhas.
    - Truncamento defensivo: se o output total exceder
      ``PARTES_INLINE_LIMIT`` (2000), corta nome a nome no último
      polo até caber e anexa ``…`` como marcador.
    - Lista vazia, ``None``, ou destinatários sem ``nome`` → string
      vazia (não JSON, não ``"null"``).
    """
    if not isinstance(destinatarios, list) or not destinatarios:
        return ""

    by_polo: dict[str, list[str]] = {}
    polos_ordem_aparicao: list[str] = []
    for entry in destinatarios:
        if not isinstance(entry, dict):
            continue
        nome = str(entry.get("nome") or "").strip()
        if not nome:
            continue
        polo = str(entry.get("polo") or "").strip().upper() or "?"
        if polo not in by_polo:
            by_polo[polo] = []
            polos_ordem_aparicao.append(polo)
        if nome not in by_polo[polo]:
            by_polo[polo].append(nome)

    if not by_polo:
        return ""

    canonicos_presentes = [p for p in POLO_ORDEM_CANONICA if p in by_polo]
    nao_canonicos = [
        p for p in polos_ordem_aparicao if p not in POLO_ORDEM_CANONICA
    ]
    polos_ordenados = canonicos_presentes + nao_canonicos

    linhas: list[str] = []
    truncado = False

    for polo in polos_ordenados:
        if truncado:
            break
        label = POLO_LABEL.get(polo, f"Polo {polo}")
        nomes_acumulados: list[str] = []
        for nome in by_polo[polo]:
            tentativa = nomes_acumulados + [nome]
            linha_tentativa = f"{label}: {', '.join(tentativa)}"
            outras = "\n".join(linhas)
            sep = "\n" if linhas else ""
            tamanho_total = (
                len(outras) + len(sep) + len(linha_tentativa)
                + len(PARTES_TRUNCAMENTO_MARCADOR)
            )
            if tamanho_total > PARTES_INLINE_LIMIT:
                truncado = True
                break
            nomes_acumulados.append(nome)
        if nomes_acumulados:
            linhas.append(f"{label}: {', '.join(nomes_acumulados)}")
            if len(nomes_acumulados) < len(by_polo[polo]):
                truncado = True
        elif truncado:
            # Não coube nem o primeiro nome deste polo
            pass

    out = "\n".join(linhas)
    if truncado:
        out = out + PARTES_TRUNCAMENTO_MARCADOR
    return out[:PARTES_INLINE_LIMIT]
