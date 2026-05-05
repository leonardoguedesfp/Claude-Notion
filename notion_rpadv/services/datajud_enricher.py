"""Enricher do DataJud — heurísticas de mesclagem multi-grau.

Recebe um par ``(processo_notion, client)``, decide quais endpoints
consultar (via ``endpoints_candidatos``), executa via
``client.consultar_multi``, agrega ``_source`` por grau (G1/G2/GS) e
devolve as 14 propriedades sugeridas + diagnóstico operacional.

Sem efeitos colaterais: NÃO escreve no Notion, NÃO toca SQLite.
Stateless por chamada.

Tabela de RegraOrigem (decisão arquitetural fixa, vide spec do
Componente 2 da feat/datajud-fase-1):

| nome_notion                            | grau           | confianca |
|----------------------------------------|----------------|-----------|
| Número do processo                     | qualquer       | alta      |
| Tribunal                               | menor          | alta      |
| Instância                              | maior          | alta      |
| Vara                                   | menor          | alta      |
| Cidade                                 | menor          | alta      |
| Data de distribuição                   | menor          | alta      |
| Data do trânsito em julgado (cognitiva)| menor (fallback maior) | alta |
| Status                                 | maior          | alta      |
| Fase                                   | maior          | alta      |
| Número STJ/TST                         | STJ ou TST     | alta      |
| Turma no 2º grau                       | G2             | alta      |
| Turma no STJ/TST                       | STJ ou TST     | alta      |
| Relator no 2º grau                     | G2             | **baixa** |
| Relator no STJ/TST                     | STJ ou TST     | **baixa** |

"baixa" = revisão humana obrigatória; o writer xlsx pinta amarelo.

Cidade: derivada de ``orgaoJulgador.codigoMunicipioIBGE`` (não regex
sobre nome). Cidade desconhecida loga WARNING no namespace
``datajud.enricher`` e devolve None — não bloqueia outras propriedades.

Tribunal: vem do menor grau. Memória do projeto: "Tribunal sempre
registra o juízo de origem de primeiro grau e nunca muda".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Final, Literal

from notion_rpadv.services.datajud_client import (
    DataJudAPIError,
    DataJudClient,
    endpoint_de_tribunal,
)

logger = logging.getLogger("datajud.enricher")


# ---------------------------------------------------------------------------
# Códigos TPU (Tabela Processual Unificada — CNJ Resolução 46/2007)
# ---------------------------------------------------------------------------

COD_TRANSITO: Final[int] = 11009
COD_ARQUIVAMENTO_DEFINITIVO: Final[int] = 246
COD_BAIXA_DEFINITIVA: Final[int] = 22
COD_SOBRESTAMENTO: Final[frozenset[int]] = frozenset({12092, 12066})
COD_LEVANTAMENTO_SOBRESTAMENTO: Final[int] = 11458
COD_CUMPRIMENTO: Final[int] = 848
COD_RPV: Final[int] = 123
COD_PRECATORIO: Final[int] = 61
COD_LIQUIDACAO: Final[int] = 471
COD_SENTENCA: Final[int] = 219


# ---------------------------------------------------------------------------
# Mapeamentos Notion ↔ DataJud
# ---------------------------------------------------------------------------

# DataJud retorna ``_source.tribunal`` em formato sem "/" (e.g. "TRT10").
# O Notion usa formatos com "/" para os TRTs (e.g. "TRT/10"). Mapa
# espelha o ``TRIB_ENDPOINT`` do client mas indexado pelo lado DataJud.
DATAJUD_TRIBUNAL_TO_NOTION: Final[dict[str, str]] = {
    "TJDFT": "TJDFT",
    "TRT10": "TRT/10",
    "TRT2":  "TRT/2",
    "TST":   "TST",
    "STJ":   "STJ",
    "TJSP":  "TJSP",
    "TJRJ":  "TJRJ",
    "TJRS":  "TJRS",
    "TJBA":  "TJBA",
    "TJMG":  "TJMG",
    "TJSC":  "TJSC",
    "TJPR":  "TJPR",
    "TJMS":  "TJMS",
    "TJES":  "TJES",
    "TJGO":  "TJGO",
}

# Cidades por código IBGE. Começa em Brasília; novas cidades aparecem
# como WARNING no smoke real e o operador atualiza este dict.
CIDADE_POR_IBGE: dict[int, str] = {
    5300108: "Brasília",
}


# ---------------------------------------------------------------------------
# Constantes canônicas (espelham vocabulário Notion da base Processos)
# ---------------------------------------------------------------------------

STATUS_ATIVO: Final[str]                     = "Ativo"
STATUS_ARQUIVADO_PROVISORIAMENTE: Final[str] = "Arquivado provisoriamente (tema 955)"
STATUS_ARQUIVADO: Final[str]                 = "Arquivado"

FASE_COGNITIVA: Final[str]  = "Cognitiva"
FASE_LIQUIDACAO: Final[str] = "Liquidação de sentença"
FASE_EXECUTIVA: Final[str]  = "Executiva"

INSTANCIA_1G: Final[str]  = "1º grau"
INSTANCIA_2G: Final[str]  = "2º grau"
INSTANCIA_TST: Final[str] = "TST"
INSTANCIA_STJ: Final[str] = "STJ"
INSTANCIA_STF: Final[str] = "STF"


# ---------------------------------------------------------------------------
# Diagnósticos (valores literais do campo ``diagnostico`` no resultado)
# ---------------------------------------------------------------------------

DIAG_OK: Final[str]              = "OK"
DIAG_NAO_ENCONTRADO: Final[str]  = "Não encontrado"
DIAG_STF: Final[str]             = "STF não coberto"
DIAG_TRIBUNAL_NS: Final[str]     = "Tribunal não suportado"
DIAG_PARCIAL: Final[str]         = "Dados parciais"

# "Erro: <detalhe>" — string com prefixo, valor variável.


# ---------------------------------------------------------------------------
# Tabela de RegraOrigem
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegraOrigem:
    """Regra de origem por propriedade enriquecida.

    ``grau_preferido``:
        - "menor": menor grau disponível (G1 → G2 → GS, preferindo G1)
        - "maior": maior grau disponível (preferindo GS)
        - "qualquer": qualquer grau disponível (default = menor)
        - "especifico": ver ``grau_especifico``

    ``grau_especifico`` é usado quando ``grau_preferido == "especifico"``:
        - "G2": grau G2 puro
        - "STJ ou TST": GS originado dos endpoints "stj" ou "tst"
          (distingue de outros GS atípicos)

    ``confianca``:
        - "alta": derivação determinística pela API
        - "baixa": heurística parcial; revisão humana obrigatória.
          Writer xlsx pinta header/célula amarelo.
    """

    nome_notion: str
    grau_preferido: Literal["menor", "maior", "qualquer", "especifico"]
    grau_especifico: str | None = None
    confianca: Literal["alta", "baixa"] = "alta"


REGRAS_ORIGEM: Final[tuple[RegraOrigem, ...]] = (
    RegraOrigem("Número do processo",                       "qualquer"),
    RegraOrigem("Tribunal",                                 "menor"),
    RegraOrigem("Instância",                                "maior"),
    RegraOrigem("Vara",                                     "menor"),
    RegraOrigem("Cidade",                                   "menor"),
    RegraOrigem("Data de distribuição",                     "menor"),
    RegraOrigem("Data do trânsito em julgado (cognitiva)",  "menor"),
    RegraOrigem("Status",                                   "maior"),
    RegraOrigem("Fase",                                     "maior"),
    RegraOrigem("Número STJ/TST",                           "especifico", "STJ ou TST"),
    RegraOrigem("Turma no 2º grau",                         "especifico", "G2"),
    RegraOrigem("Turma no STJ/TST",                         "especifico", "STJ ou TST"),
    RegraOrigem("Relator no 2º grau",                       "especifico", "G2",         "baixa"),
    RegraOrigem("Relator no STJ/TST",                       "especifico", "STJ ou TST", "baixa"),
)


# ---------------------------------------------------------------------------
# Endpoints candidatos (decisão de roteamento)
# ---------------------------------------------------------------------------


def endpoints_candidatos(processo_notion: dict[str, Any]) -> list[str]:
    """Decide quais endpoints DataJud consultar para um processo.

    Regras (vide spec):
    - 1º grau / 2º grau → [endpoint_do_tribunal]
    - TST              → [endpoint_do_tribunal, "tst"] (dedup se Tribunal == TST)
    - STJ              → [endpoint_do_tribunal, "stj"] (dedup se Tribunal == STJ)
    - STF              → [] (sem endpoint público)
    - Tribunal == "Outro" ou não mapeado → [] (Tribunal não suportado)
    """
    tribunal = (processo_notion.get("Tribunal") or "").strip()
    instancia = (processo_notion.get("Instância") or "").strip()

    if instancia == INSTANCIA_STF:
        return []

    base = endpoint_de_tribunal(tribunal)
    if base is None:
        return []

    eps: list[str] = [base]
    if instancia == INSTANCIA_STJ and "stj" not in eps:
        eps.append("stj")
    elif instancia == INSTANCIA_TST and "tst" not in eps:
        eps.append("tst")
    return eps


# ---------------------------------------------------------------------------
# Heurísticas (auxiliares)
# ---------------------------------------------------------------------------

# Vara: extrai número ordinal de variações:
#   " 13A VT DE BRASILIA"           (TRT, com space prefixado)
#   "13ª Vara Cível de Brasília"    (TJDFT, com ª)
#   "13a Vara"                      (lowercase a, sem ª)
#   "Vara n. 13"                    (Vara antes do número)
_VARA_PATTERNS: tuple[re.Pattern[str], ...] = (
    # TRT trabalhista: "<num>A VT" (ex.: " 13A VT DE BRASILIA")
    re.compile(r"(\d+)\s*A\.?\s+VT\b", re.IGNORECASE),
    # Cível/comum: aceita ª/º/a/A (ou nada) entre número e "Vara".
    # IGNORECASE deixa [ªºA] casar lowercase também.
    re.compile(r"(\d+)\s*[ªºA]?\s*Vara", re.IGNORECASE),
    # "Vara nº 13", "Vara 13"
    re.compile(r"\bVara\s*(?:n[º°]?\.?\s*)?(\d+)", re.IGNORECASE),
)


def derivar_vara(orgao_julgador_menor: dict[str, Any] | None) -> str | None:
    """Extrai número ordinal da vara a partir do nome do órgão julgador
    do menor grau. Retorna string com o número (sem prefixo "ª")
    para casar com o formato cadastrado no Notion (que usa número puro).

    Nome reconhecido em:
    - " 13A VT DE BRASILIA" (TRT)
    - "13ª Vara Cível de Brasília" (TJDFT)
    - "13a Vara"
    - Nomes que não casam padrão → retorna None.
    """
    if not orgao_julgador_menor:
        return None
    nome = str(orgao_julgador_menor.get("nome") or "").strip()
    if not nome:
        return None
    for pat in _VARA_PATTERNS:
        m = pat.search(nome)
        if m:
            return m.group(1)
    return None


def derivar_cidade(
    codigo_municipio_ibge: int | None,
    *,
    cnj: str | None = None,
) -> str | None:
    """Mapeia código IBGE → nome de cidade no formato Notion.

    IBGE não cadastrado loga WARNING (`datajud.enricher`) e retorna None
    — Cidade fica vazia mas as outras propriedades são derivadas
    normalmente. Operador adiciona ao ``CIDADE_POR_IBGE`` na próxima
    iteração.
    """
    if codigo_municipio_ibge is None:
        return None
    cidade = CIDADE_POR_IBGE.get(codigo_municipio_ibge)
    if cidade is None:
        if cnj:
            logger.warning(
                "cidade IBGE desconhecida: %d (CNJ %s)",
                codigo_municipio_ibge, cnj,
            )
        else:
            logger.warning("cidade IBGE desconhecida: %d", codigo_municipio_ibge)
    return cidade


# Turma: extrai número ordinal de "5ª Turma Cível" / "1ª Turma" / "3ª CAMARA".
_TURMA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(\d+)\s*[ªº]?\s*(?:Turma|Câmara|CAMARA)", re.IGNORECASE),
)


def derivar_turma_g2(orgao_julgador: dict[str, Any] | None) -> str | None:
    """Extrai número da Turma a partir do nome do órgão julgador.

    Funciona pra G2 (TJ/TRT) e GS (STJ/TST formato "5ª Turma").
    Para órgãos que são gabinetes individuais (e.g.
    "GABINETE DO DESEMBARGADOR DORIVAL BORGES"), retorna None — o
    relator vem por outro caminho (``derivar_relator``).
    """
    if not orgao_julgador:
        return None
    nome = str(orgao_julgador.get("nome") or "").strip()
    if not nome:
        return None
    for pat in _TURMA_PATTERNS:
        m = pat.search(nome)
        if m:
            return m.group(1)
    return None


def derivar_data_distribuicao(
    menor_grau_source: dict[str, Any] | None,
) -> str | None:
    """Extrai ``dataAjuizamento`` do menor grau como ISO 'YYYY-MM-DD'.

    Aceita formato compacto da API (``"20210522081424"``) e ISO
    (``"2021-05-22T08:14:24..."``).
    """
    if not menor_grau_source:
        return None
    raw = str(menor_grau_source.get("dataAjuizamento") or "").strip()
    if not raw:
        return None
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    return None


def derivar_transito_cognitiva(
    movimentos_menor: list[dict[str, Any]],
    movimentos_maior: list[dict[str, Any]],
) -> str | None:
    """Procura mov. ``COD_TRANSITO`` (11009) no menor grau primeiro,
    fallback no maior grau. Retorna ISO 'YYYY-MM-DD' ou None.
    """
    for movs in (movimentos_menor, movimentos_maior):
        for m in movs:
            if m.get("codigo") == COD_TRANSITO:
                dh = str(m.get("dataHora") or "")
                if len(dh) >= 10:
                    return dh[:10]
    return None


def derivar_status(movimentos_maior: list[dict[str, Any]]) -> str:
    """Status canônico do Notion — sentinela de "Tema 955" preservada.

    Heurísticas (ordem de prioridade):
    1. Sobrestamento (mov. 12092/12066) sem levantamento posterior
       (mov. 11458) → "Arquivado provisoriamente (tema 955)".
    2. Arquivamento definitivo (mov. 246) ou baixa definitiva (mov. 22)
       sem indicação de reativação → "Arquivado".
    3. Senão → "Ativo".

    Importante: este campo continua válido mesmo que o checkbox
    "Tema 955 — Sobrestado" não esteja no escopo de enriquecimento.
    Status e o checkbox são propriedades distintas no Notion.
    """
    cods: list[int] = []
    for m in movimentos_maior:
        c = m.get("codigo")
        if isinstance(c, int):
            cods.append(c)
    if not cods:
        return STATUS_ATIVO
    last_sobrestamento = -1
    last_levantamento  = -1
    last_arq           = -1
    for i, c in enumerate(cods):
        if c in COD_SOBRESTAMENTO:
            last_sobrestamento = i
        if c == COD_LEVANTAMENTO_SOBRESTAMENTO:
            last_levantamento = i
        if c in (COD_ARQUIVAMENTO_DEFINITIVO, COD_BAIXA_DEFINITIVA):
            last_arq = i
    if last_sobrestamento > last_levantamento:
        return STATUS_ARQUIVADO_PROVISORIAMENTE
    if last_arq >= 0:
        return STATUS_ARQUIVADO
    return STATUS_ATIVO


def derivar_fase(movimentos_maior: list[dict[str, Any]]) -> str:
    """Fase canônica do Notion. Prioridade descendente:
    Executiva → Liquidação → Cognitiva.

    - Cumprimento (848) / RPV (123) / Precatório (61) → Executiva
    - Liquidação (471) → Liquidação de sentença
    - Senão → Cognitiva (default — sentença ainda em fase cognitiva,
      ou processo só com despachos/distribuição)
    """
    cods: set[int] = set()
    for m in movimentos_maior:
        c = m.get("codigo")
        if isinstance(c, int):
            cods.add(c)
    if any(c in cods for c in (COD_CUMPRIMENTO, COD_RPV, COD_PRECATORIO)):
        return FASE_EXECUTIVA
    if COD_LIQUIDACAO in cods:
        return FASE_LIQUIDACAO
    return FASE_COGNITIVA


def derivar_relator(movimentos: list[dict[str, Any]]) -> str | None:
    """Procura nome do relator em ``complementosTabelados``.

    Heurística parcial — marca-se como BAIXA confiança em ``REGRAS_ORIGEM``.
    A API não tem campo dedicado pra "relator atual"; o nome aparece
    em movimentos de "Atribuição de relator" (e similares) através
    de complementos com descrição contendo "relator". Pode haver
    múltiplos (mudança de relator) — esta heurística retorna o
    PRIMEIRO encontrado, e o operador valida via aba Importar.
    """
    for m in movimentos:
        comps = m.get("complementosTabelados")
        if not isinstance(comps, list):
            continue
        for c in comps:
            if not isinstance(c, dict):
                continue
            desc = str(c.get("descricao") or "").lower()
            if "relator" in desc:
                nome = c.get("nome")
                if isinstance(nome, str) and nome.strip():
                    return nome.strip()
    return None


# ---------------------------------------------------------------------------
# Resultado do enriquecimento
# ---------------------------------------------------------------------------


@dataclass
class ResultadoEnriquecimento:
    """Saída de ``enriquecer()``.

    Attributes:
        numero_cnj: CNJ do processo consultado (do Notion).
        diagnostico: ``OK`` | ``Não encontrado`` | ``STF não coberto`` |
            ``Tribunal não suportado`` | ``Dados parciais`` | ``Erro: <detalhe>``.
        propriedades_sugeridas: dict ``nome_notion → valor`` para as
            14 propriedades enriquecidas. Valores ``None`` quando não
            derivável (writer xlsx interpreta como "não tocar célula").
            Sempre inclui as 14 keys (mesmo em diagnóstico de erro,
            todas com ``None``) — facilita iteração defensiva no caller.
        fontes_tribunal: lista de endpoints DataJud que retornaram ≥1 hit
            (auditoria; vai pra coluna ``__datajud_meta`` do xlsx).
        movimentos_brutos_por_grau: ``grau → list[movimento]`` agregando
            movimentos de todos os ``_source`` daquele grau (auditoria).
    """

    numero_cnj: str
    diagnostico: str
    propriedades_sugeridas: dict[str, Any]
    fontes_tribunal: list[str]
    movimentos_brutos_por_grau: dict[str, list[dict[str, Any]]]


# ---------------------------------------------------------------------------
# enriquecer (função pública principal)
# ---------------------------------------------------------------------------


def enriquecer(
    processo_notion: dict[str, Any],
    *,
    client: DataJudClient,
) -> ResultadoEnriquecimento:
    """Para cada processo cadastrado no Notion, decide endpoints DataJud,
    executa as consultas via ``client.consultar_multi``, e mescla
    resultados conforme ``REGRAS_ORIGEM``.

    Tolerante:
    - Endpoint vazio mas outro com hit → diagnóstico ``Dados parciais``.
    - Todos endpoints vazios → ``Não encontrado``.
    - Exceção HTTP em qualquer endpoint → ``Erro: <detalhe>``,
      propriedades vazias.

    Args:
        processo_notion: dict do cache decodificado, com chaves do Notion
            (``Tribunal``, ``Instância``, ``Número do processo``, etc.).
        client: instância de ``DataJudClient`` (vem do worker; reuso
            de session HTTP).

    Returns:
        ``ResultadoEnriquecimento`` — sempre populado, mesmo em erro.
    """
    cnj = str(processo_notion.get("Número do processo") or "").strip()

    eps = endpoints_candidatos(processo_notion)
    if not eps:
        tribunal = (processo_notion.get("Tribunal") or "").strip()
        instancia = (processo_notion.get("Instância") or "").strip()
        if instancia == INSTANCIA_STF or tribunal == "STF":
            diag = DIAG_STF
        else:
            diag = DIAG_TRIBUNAL_NS
        return ResultadoEnriquecimento(
            numero_cnj=cnj,
            diagnostico=diag,
            propriedades_sugeridas=_propriedades_vazias(),
            fontes_tribunal=[],
            movimentos_brutos_por_grau={},
        )

    try:
        results = client.consultar_multi(cnj, eps)
    except DataJudAPIError as exc:
        return ResultadoEnriquecimento(
            numero_cnj=cnj,
            diagnostico=f"Erro: {str(exc)[:120]}",
            propriedades_sugeridas=_propriedades_vazias(),
            fontes_tribunal=[],
            movimentos_brutos_por_grau={},
        )

    # Indexa sources por grau, anotando o endpoint de origem.
    por_grau: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    fontes_com_hit: list[str] = []
    for ep, sources in results.items():
        if sources:
            fontes_com_hit.append(ep)
        for src in sources:
            grau = str(src.get("grau") or "").strip()
            if not grau:
                continue
            por_grau.setdefault(grau, []).append((ep, src))

    if not por_grau:
        return ResultadoEnriquecimento(
            numero_cnj=cnj,
            diagnostico=DIAG_NAO_ENCONTRADO,
            propriedades_sugeridas=_propriedades_vazias(),
            fontes_tribunal=[],
            movimentos_brutos_por_grau={},
        )

    todos_eps_hit = len(fontes_com_hit) == len(eps)
    diag = DIAG_OK if todos_eps_hit else DIAG_PARCIAL

    propriedades = _aplicar_regras(por_grau, cnj=cnj)

    movs_brutos: dict[str, list[dict[str, Any]]] = {}
    for grau, items in por_grau.items():
        all_movs: list[dict[str, Any]] = []
        for _ep, src in items:
            ms = src.get("movimentos") or []
            if isinstance(ms, list):
                all_movs.extend(m for m in ms if isinstance(m, dict))
        movs_brutos[grau] = all_movs

    return ResultadoEnriquecimento(
        numero_cnj=cnj,
        diagnostico=diag,
        propriedades_sugeridas=propriedades,
        fontes_tribunal=fontes_com_hit,
        movimentos_brutos_por_grau=movs_brutos,
    )


# ---------------------------------------------------------------------------
# Internos: aplicação das REGRAS_ORIGEM
# ---------------------------------------------------------------------------


def _propriedades_vazias() -> dict[str, Any]:
    """14 keys com None — output base de qualquer caminho de erro."""
    return {r.nome_notion: None for r in REGRAS_ORIGEM}


_GRAU_RANK: Final[dict[str, int]] = {"G1": 0, "G2": 1, "GS": 2}


def _aplicar_regras(
    por_grau: dict[str, list[tuple[str, dict[str, Any]]]],
    *,
    cnj: str,
) -> dict[str, Any]:
    """Itera REGRAS_ORIGEM e preenche cada propriedade conforme a regra.

    Indexa source único (primeiro) por grau pra simplificar; payloads
    com 2 sources mesmo grau são raros e os campos derivados (Vara,
    Cidade) são iguais entre eles.
    """
    graus_disponiveis = sorted(
        (g for g in por_grau if g in _GRAU_RANK),
        key=lambda g: _GRAU_RANK[g],
    )
    if not graus_disponiveis:
        return _propriedades_vazias()
    menor_grau = graus_disponiveis[0]
    maior_grau = graus_disponiveis[-1]

    def _primeiro(grau: str) -> tuple[str, dict[str, Any]] | None:
        items = por_grau.get(grau) or []
        return items[0] if items else None

    def _movs(grau: str) -> list[dict[str, Any]]:
        items = por_grau.get(grau) or []
        out: list[dict[str, Any]] = []
        for _ep, src in items:
            ms = src.get("movimentos") or []
            if isinstance(ms, list):
                out.extend(m for m in ms if isinstance(m, dict))
        return out

    def _stj_tst_source() -> tuple[str, dict[str, Any]] | None:
        """GS originado de endpoint stj/tst (distingue de GS atípicos)."""
        items_gs = por_grau.get("GS") or []
        for ep, src in items_gs:
            if ep in ("stj", "tst"):
                return (ep, src)
        return None

    menor_src = _primeiro(menor_grau)
    maior_src = _primeiro(maior_grau)
    g2_src = _primeiro("G2")
    stj_tst_src = _stj_tst_source()

    movs_menor = _movs(menor_grau)
    movs_maior = _movs(maior_grau)

    out: dict[str, Any] = _propriedades_vazias()

    # 1. Número do processo (qualquer)
    if menor_src is not None:
        np = menor_src[1].get("numeroProcesso")
        out["Número do processo"] = str(np) if np else None

    # 2. Tribunal (menor grau, com mapeamento DataJud → Notion)
    if menor_src is not None:
        trib_dj = str(menor_src[1].get("tribunal") or "").strip()
        if trib_dj:
            out["Tribunal"] = DATAJUD_TRIBUNAL_TO_NOTION.get(trib_dj, trib_dj)

    # 3. Instância (maior grau, mapeada via grau + endpoint)
    if maior_src is not None:
        out["Instância"] = _instancia_canonica(
            maior_grau, maior_src[0], maior_src[1],
        )

    # 4. Vara (menor grau)
    if menor_src is not None:
        out["Vara"] = derivar_vara(menor_src[1].get("orgaoJulgador"))

    # 5. Cidade (menor grau, via codigoMunicipioIBGE)
    if menor_src is not None:
        oj = menor_src[1].get("orgaoJulgador") or {}
        ibge_raw = oj.get("codigoMunicipioIBGE") if isinstance(oj, dict) else None
        ibge_int: int | None = None
        if isinstance(ibge_raw, int):
            ibge_int = ibge_raw
        elif isinstance(ibge_raw, str) and ibge_raw.isdigit():
            ibge_int = int(ibge_raw)
        out["Cidade"] = derivar_cidade(ibge_int, cnj=cnj)

    # 6. Data de distribuição (menor grau)
    if menor_src is not None:
        out["Data de distribuição"] = derivar_data_distribuicao(menor_src[1])

    # 7. Trânsito cognitiva (menor → fallback maior)
    out["Data do trânsito em julgado (cognitiva)"] = derivar_transito_cognitiva(
        movs_menor, movs_maior,
    )

    # 8. Status (maior grau)
    out["Status"] = derivar_status(movs_maior)

    # 9. Fase (maior grau)
    out["Fase"] = derivar_fase(movs_maior)

    # 10. Número STJ/TST (específico)
    if stj_tst_src is not None:
        np = stj_tst_src[1].get("numeroProcesso")
        out["Número STJ/TST"] = str(np) if np else None

    # 11. Turma 2º grau
    if g2_src is not None:
        out["Turma no 2º grau"] = derivar_turma_g2(g2_src[1].get("orgaoJulgador"))

    # 12. Turma STJ/TST
    if stj_tst_src is not None:
        out["Turma no STJ/TST"] = derivar_turma_g2(stj_tst_src[1].get("orgaoJulgador"))

    # 13. Relator 2º grau (BAIXA)
    if g2_src is not None:
        movs_g2_raw = g2_src[1].get("movimentos") or []
        movs_g2: list[dict[str, Any]] = (
            [m for m in movs_g2_raw if isinstance(m, dict)]
            if isinstance(movs_g2_raw, list)
            else []
        )
        out["Relator no 2º grau"] = derivar_relator(movs_g2)

    # 14. Relator STJ/TST (BAIXA)
    if stj_tst_src is not None:
        movs_st_raw = stj_tst_src[1].get("movimentos") or []
        movs_st: list[dict[str, Any]] = (
            [m for m in movs_st_raw if isinstance(m, dict)]
            if isinstance(movs_st_raw, list)
            else []
        )
        out["Relator no STJ/TST"] = derivar_relator(movs_st)

    return out


def _instancia_canonica(
    grau: str,
    endpoint: str,
    source: dict[str, Any],
) -> str | None:
    """Mapeia ``(grau, endpoint)`` para a Instância canônica do Notion.

    G1 → "1º grau"; G2 → "2º grau"; GS → STJ/TST/STF conforme endpoint
    de origem (ou source.tribunal como fallback pra GS atípicos em
    endpoint TJ/TRT).
    """
    if grau == "G1":
        return INSTANCIA_1G
    if grau == "G2":
        return INSTANCIA_2G
    if grau == "GS":
        if endpoint == "stj":
            return INSTANCIA_STJ
        if endpoint == "tst":
            return INSTANCIA_TST
        # GS num endpoint TJ/TRT — atípico; tenta source.tribunal.
        trib = str(source.get("tribunal") or "").upper()
        if trib == "STJ":
            return INSTANCIA_STJ
        if trib == "TST":
            return INSTANCIA_TST
        if trib == "STF":
            return INSTANCIA_STF
    return None
