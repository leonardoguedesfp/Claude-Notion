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
# Códigos TPU oficiais — Resolução CNJ 46/2007
#
# Verificados contra: TPU TST 08.02.2022; TJDFT andamentos;
# Portaria CNJ 116/2022. Smoke real do CNJ 0016539-47.2015.8.07.0001
# expôs que os códigos do spec inline original estavam invertidos
# (848 era tratado como cumprimento, mas é trânsito em julgado;
# 11009 era tratado como trânsito, mas é despacho).
# ---------------------------------------------------------------------------

COD_TRANSITO_EM_JULGADO: Final[int] = 848        # corrigido (spec dizia 11009)
COD_DESPACHO: Final[int] = 11009                 # NOVO — só usado em asserts/docs
COD_BAIXA_DEFINITIVA: Final[int] = 22
COD_ARQUIVAMENTO_DEFINITIVO: Final[int] = 246

# Sobrestamento: lista ampliada com códigos da TPU oficial.
# Removido 12092 (não consta na TPU; provavelmente erro do spec original).
COD_SOBRESTAMENTO: Final[frozenset[int]] = frozenset({
    11025,   # Suspensão ou Sobrestamento (genérico, TPU)
    12066,   # Sobrestamento subsidiário (não-precedentes qualificados)
    14978,   # Suspensão/Sobrestamento por decisão Presidente STJ – SIRDR
    14981,   # Suspensão/Sobrestamento Determinada por Controvérsia
})
COD_LEVANTAMENTO_SOBRESTAMENTO: Final[int] = 12067   # corrigido (spec dizia 11458)

# Liquidação: confirmados 471 e 11528. Outros aparecerão no smoke real;
# expandir conforme operador identifique.
COD_LIQUIDACAO: Final[frozenset[int]] = frozenset({
    471,    # Liquidação por Arbitramento
    11528,  # Liquidação Provisória por Cálculos (Justiça do Trabalho)
})

COD_SENTENCA: Final[int] = 219    # NÃO confirmado em fonte oficial; manter
                                   # como heurística e validar no smoke.

# ---------------------------------------------------------------------------
# Classes processuais que indicam fase Executiva
#
# Quando o processo é cadastrado como "Cumprimento de Sentença" no PJe/legacy,
# a classe.codigo é uma destas. Mais robusto que rastrear código de movimento
# (após a descoberta de que 848 não é cumprimento).
# ---------------------------------------------------------------------------

CLASSES_EXECUCAO: Final[frozenset[int]] = frozenset({
    159,    # Cumprimento de Sentença
    156,    # Cumprimento de Sentença contra a Fazenda Pública
    11538,  # Cumprimento de Sentença (Justiça do Trabalho)
    1111,   # Execução de Título Judicial
})


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

FASE_COGNITIVA: Final[str]           = "Cognitiva"
FASE_LIQUIDACAO_PENDENTE: Final[str] = "Liquidação pendente"
FASE_LIQUIDACAO: Final[str]          = "Liquidação de sentença"
FASE_EXECUTIVA: Final[str]           = "Executiva"
FASE_TJ_NAO_EXECUTAVEL: Final[str]   = "TJ - sentença não será executada"

INSTANCIA_1G: Final[str]  = "1º grau"
INSTANCIA_2G: Final[str]  = "2º grau"
INSTANCIA_TST: Final[str] = "TST"
INSTANCIA_STJ: Final[str] = "STJ"
INSTANCIA_STF: Final[str] = "STF"


# ---------------------------------------------------------------------------
# Vocabulários autoritativos do Notion (selects fechados)
#
# Fonte: schema vivo da base ⚖️ Processos. Qualquer função que emita
# valor para essas três propriedades DEVE garantir que o resultado
# pertence ao vocabulário — assertions no fim de derivar_fase,
# derivar_status e _instancia_canonica fazem essa proteção.
# ---------------------------------------------------------------------------

STATUS_VOCABULARIO_NOTION: Final[tuple[str, ...]] = (
    STATUS_ATIVO,
    STATUS_ARQUIVADO_PROVISORIAMENTE,
    STATUS_ARQUIVADO,
)

FASE_VOCABULARIO_NOTION: Final[tuple[str, ...]] = (
    FASE_COGNITIVA,
    FASE_EXECUTIVA,
    FASE_LIQUIDACAO_PENDENTE,
    FASE_LIQUIDACAO,
    FASE_TJ_NAO_EXECUTAVEL,
)

INSTANCIA_VOCABULARIO_NOTION: Final[tuple[str, ...]] = (
    INSTANCIA_1G,
    INSTANCIA_2G,
    INSTANCIA_TST,
    INSTANCIA_STJ,
    INSTANCIA_STF,
)


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
#   "22? VARA C?VEL DE BRAS?LIA"    (encoding latin1 corrompido na API:
#                                    'ª'/'í' viram '?'. Visto no smoke
#                                    real do CNJ 0016539-47.2015.8.07.0001)
#   "Vara n. 13"                    (Vara antes do número)
_VARA_PATTERNS: tuple[re.Pattern[str], ...] = (
    # TRT trabalhista: "<num>A VT" (ex.: " 13A VT DE BRASILIA")
    re.compile(r"(\d+)\s*A\.?\s+VT\b", re.IGNORECASE),
    # Cível/comum: aceita ª/º/a/A/? (ou nada) entre número e "Vara".
    # `?` cobre encoding corrompido pela API DataJud (ª/í → ?).
    re.compile(r"(\d+)\s*[ªºA?]?\s*Vara", re.IGNORECASE),
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


def parse_data_compacta(raw: Any) -> str | None:
    """Aceita formato compacto da API (``"20210522081424"``) ou ISO
    (``"2021-05-22T08:14:24..."``) e devolve 'YYYY-MM-DD'.

    Reutilizável por ``derivar_data_distribuicao`` e
    ``derivar_data_transito_cognitiva`` — ambas leem strings de data
    do mesmo formato heterogêneo.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def derivar_data_distribuicao(
    menor_grau_source: dict[str, Any] | None,
) -> str | None:
    """Extrai ``dataAjuizamento`` do menor grau como ISO 'YYYY-MM-DD'."""
    if not menor_grau_source:
        return None
    return parse_data_compacta(menor_grau_source.get("dataAjuizamento"))


def derivar_data_transito_cognitiva(
    sources_por_grau: dict[str, dict[str, Any]],
) -> str | None:
    """Procura mov. ``COD_TRANSITO_EM_JULGADO`` (848) no menor grau
    primeiro (G1), fallback G2, depois GS. Retorna 'YYYY-MM-DD' ou None.

    Política: trânsito cognitivo é o do processo principal (cognição),
    que tipicamente acontece no G1 ou G2. Iteração ascendente respeita
    isso. Cód 848 substituiu 11009 (que era tratado erroneamente como
    trânsito mas é Despacho).
    """
    for grau_chave in ("G1", "G2", "GS"):
        src = sources_por_grau.get(grau_chave)
        if src is None:
            continue
        movs = src.get("movimentos") or []
        if not isinstance(movs, list):
            continue
        for m in movs:
            if not isinstance(m, dict):
                continue
            if m.get("codigo") == COD_TRANSITO_EM_JULGADO:
                data = parse_data_compacta(m.get("dataHora"))
                if data is not None:
                    return data
    return None


def derivar_status(source_maior_grau: dict[str, Any] | None) -> str:
    """Status canônico do Notion — sentinela de Tema 955 via complementos.

    Heurísticas (ordem de prioridade):

    1. **Tema 955**: presença de mov. ∈ ``COD_SOBRESTAMENTO``
       com ``complementosTabelados[].nome`` ou ``.descricao``
       contendo "tema 955", **sem** mov. subsequente
       ``COD_LEVANTAMENTO_SOBRESTAMENTO`` (12067) → "Arquivado
       provisoriamente (tema 955)". Itera movimentos ordenados por
       ``dataHora`` para garantir ordem cronológica correta — não
       confiar na ordem de inserção da API.

    2. Arquivamento definitivo (246) ou baixa definitiva (22) →
       "Arquivado".

    3. Senão → "Ativo".

    LIMITAÇÃO TEMA 955: O DataJud só consegue detectar sobrestamento
    por Tema 955 quando o movimento original (cód TPU
    11025/12066/14978/14981 com complemento "Tema 955") está presente
    nos dados retornados pela API. Para processos sobrestados antes
    da plena adoção do DataJud (~2018-2020), esse movimento pode
    estar ausente, e o enricher sugerirá "Arquivado" em vez de
    "Arquivado provisoriamente (tema 955)". Tratar como divergência
    esperada, não erro do enricher.
    """
    if source_maior_grau is None:
        return STATUS_ATIVO

    movimentos_raw = source_maior_grau.get("movimentos") or []
    if not isinstance(movimentos_raw, list):
        movimentos_raw = []
    movimentos: list[dict[str, Any]] = [
        m for m in movimentos_raw if isinstance(m, dict)
    ]
    if not movimentos:
        return STATUS_ATIVO

    movs_ordenados = sorted(
        movimentos,
        key=lambda m: str(m.get("dataHora") or ""),
    )

    sobrestado_tema_955 = False
    for m in movs_ordenados:
        cod = m.get("codigo")
        if cod in COD_SOBRESTAMENTO:
            comps = m.get("complementosTabelados") or []
            if not isinstance(comps, list):
                comps = []
            comps_text = " ".join(
                (str(c.get("nome", "")) + " " + str(c.get("descricao", "")))
                for c in comps if isinstance(c, dict)
            ).lower()
            if "tema 955" in comps_text:
                sobrestado_tema_955 = True
        elif cod == COD_LEVANTAMENTO_SOBRESTAMENTO:
            sobrestado_tema_955 = False

    if sobrestado_tema_955:
        resultado = STATUS_ARQUIVADO_PROVISORIAMENTE
    else:
        cods_movs = {m.get("codigo") for m in movs_ordenados}
        if cods_movs & {COD_BAIXA_DEFINITIVA, COD_ARQUIVAMENTO_DEFINITIVO}:
            resultado = STATUS_ARQUIVADO
        else:
            resultado = STATUS_ATIVO

    assert resultado in STATUS_VOCABULARIO_NOTION, (
        f"derivar_status emitiu valor fora do vocabulário Notion: {resultado!r}"
    )
    return resultado


def derivar_fase(source_maior_grau: dict[str, Any] | None) -> str:
    """Fase canônica do Notion via classe processual + códigos de movimento.

    Heurística (prioridade descendente):

    1. ``classe.codigo`` ∈ ``CLASSES_EXECUCAO`` (159, 156, 11538, 1111)
       → "Executiva". Mais robusto que rastrear código de movimento —
       a classe processual é a fonte canônica para "Cumprimento de
       Sentença" no PJe.

    2. Algum mov com cód em ``COD_LIQUIDACAO`` → "Liquidação de sentença".

    3. ``COD_SENTENCA`` (219) E ``COD_TRANSITO_EM_JULGADO`` (848)
       presentes E sem cumprimento/liquidação → "Liquidação pendente"
       (sentença transitada mas liquidação não iniciada).

    4. Default: "Cognitiva" (processo em curso; vocabulário Notion não
       distingue mais finamente).

    "TJ - sentença não será executada" existe no vocabulário Notion mas
    não é detectável pela API (depende de natureza da decisão); fica
    fora do output automático.
    """
    if source_maior_grau is None:
        return FASE_COGNITIVA

    classe = source_maior_grau.get("classe") or {}
    classe_cod = classe.get("codigo") if isinstance(classe, dict) else None

    movimentos_raw = source_maior_grau.get("movimentos") or []
    if not isinstance(movimentos_raw, list):
        movimentos_raw = []
    cods_movs: set[int] = set()
    for m in movimentos_raw:
        if isinstance(m, dict):
            c = m.get("codigo")
            if isinstance(c, int):
                cods_movs.add(c)

    if classe_cod in CLASSES_EXECUCAO:
        resultado = FASE_EXECUTIVA
    elif cods_movs & COD_LIQUIDACAO:
        resultado = FASE_LIQUIDACAO
    elif (
        COD_SENTENCA in cods_movs
        and COD_TRANSITO_EM_JULGADO in cods_movs
    ):
        resultado = FASE_LIQUIDACAO_PENDENTE
    else:
        resultado = FASE_COGNITIVA

    assert resultado in FASE_VOCABULARIO_NOTION, (
        f"derivar_fase emitiu valor fora do vocabulário Notion: {resultado!r}"
    )
    return resultado


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

    # Indexa sources por grau (com SUP→GS normalizado), anotando o
    # endpoint de origem. Endpoint é necessário downstream para
    # distinguir GS-stj de GS-tst (Número STJ/TST, Turma STJ/TST).
    por_grau: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    fontes_com_hit: list[str] = []
    for ep, sources in results.items():
        if sources:
            fontes_com_hit.append(ep)
        for src in sources:
            grau_raw = str(src.get("grau") or "").strip()
            if not grau_raw:
                continue
            chave = "GS" if grau_raw in ("GS", "SUP") else grau_raw
            por_grau.setdefault(chave, []).append((ep, src))

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

    propriedades = _aplicar_regras(
        por_grau, processo_notion=processo_notion, cnj=cnj,
    )

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


# SUP é como o TST representa o grau superior (decidido empiricamente
# no smoke real do CNJ 0000789-22.2019.5.10.0004). Tratado como
# sinônimo de GS pra simplificar consumidores downstream.
_GRAU_RANK: Final[dict[str, int]] = {"G1": 0, "G2": 1, "GS": 2, "SUP": 2}


def sources_por_grau(
    sources: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Normaliza lista de ``_source`` em dict ``grau → primeiro source``.

    SUP é normalizado para GS (TST usa SUP em vez de GS). Quando o
    mesmo grau aparece mais de uma vez, mantém o primeiro (a API
    raramente retorna duplicatas; quando ocorre, costumam ser cópias
    do mesmo registro com timestamps diferentes).

    Útil para alimentar funções derivar_* que consomem source único
    por grau. Função pública — pode ser usada pelo writer xlsx no
    Componente 3.
    """
    out: dict[str, dict[str, Any]] = {}
    for src in sources:
        if not isinstance(src, dict):
            continue
        grau_raw = str(src.get("grau") or "").strip()
        if not grau_raw:
            continue
        chave = "GS" if grau_raw in ("GS", "SUP") else grau_raw
        if chave not in out:
            out[chave] = src
    return out


def _grau_alvo(processo_notion: dict[str, Any]) -> str:
    """Mapeia ``Instância`` cadastrada no Notion para o grau DataJud
    correspondente. É a fonte da verdade para o "maior grau" das
    REGRAS_ORIGEM — não o maior grau retornado pela API.

    Decisão arquitetural: o cadastro Notion é o oráculo da Instância
    atual do processo. A API DataJud retorna registros históricos de
    todos os graus (G1 cognitivo + G2 acórdão + ...), mas o "estado
    atual" (Status, Fase) deve ser lido do grau que o operador
    cadastrou. Se o cadastro estiver desatualizado, o operador
    atualiza manualmente — o enricher não tenta adivinhar.
    """
    instancia = (processo_notion.get("Instância") or "").strip()
    if instancia == INSTANCIA_1G:
        return "G1"
    if instancia == INSTANCIA_2G:
        return "G2"
    if instancia in (INSTANCIA_TST, INSTANCIA_STJ, INSTANCIA_STF):
        return "GS"
    return "G1"  # fallback conservador para Instância vazia/desconhecida


def _aplicar_regras(
    por_grau: dict[str, list[tuple[str, dict[str, Any]]]],
    *,
    processo_notion: dict[str, Any],
    cnj: str,
) -> dict[str, Any]:
    """Itera REGRAS_ORIGEM e preenche cada propriedade conforme a regra.

    "Maior grau" segue o cadastro Notion (via ``_grau_alvo``), não o
    maior grau retornado pela API. Decisão arquitetural deliberada:
    Status/Fase/Instância refletem o estado atual conforme cadastro,
    não o histórico.

    "Menor grau" é G1; quando ausente (caso atípico), faz fallback
    para o menor grau efetivamente disponível.
    """
    if not por_grau:
        return _propriedades_vazias()

    # Maior grau guiado pelo cadastro Notion. Se o cadastro indica
    # "1º grau" mas a API só retornou G2, _resolve_grau cai no fallback.
    grau_alvo_cadastro = _grau_alvo(processo_notion)
    maior_grau = _resolve_grau(grau_alvo_cadastro, por_grau)

    # Menor grau é G1 quando disponível; senão o menor existente.
    if "G1" in por_grau:
        menor_grau: str | None = "G1"
    else:
        graus_ordenados = sorted(
            (g for g in por_grau if g in _GRAU_RANK),
            key=lambda g: _GRAU_RANK[g],
        )
        menor_grau = graus_ordenados[0] if graus_ordenados else None

    if menor_grau is None:
        return _propriedades_vazias()

    def _primeiro(grau: str | None) -> tuple[str, dict[str, Any]] | None:
        if grau is None:
            return None
        items = por_grau.get(grau) or []
        return items[0] if items else None

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

    # View grau→source para derivar_data_transito_cognitiva (helper
    # iterando G1 → G2 → GS na ordem cronológica de cognição).
    sources_view: dict[str, dict[str, Any]] = {}
    for grau in ("G1", "G2", "GS"):
        s = _primeiro(grau)
        if s is not None:
            sources_view[grau] = s[1]

    out: dict[str, Any] = _propriedades_vazias()

    # 1. Número do processo (qualquer; usa menor grau)
    if menor_src is not None:
        np = menor_src[1].get("numeroProcesso")
        out["Número do processo"] = str(np) if np else None

    # 2. Tribunal (menor grau, com mapeamento DataJud → Notion)
    if menor_src is not None:
        trib_dj = str(menor_src[1].get("tribunal") or "").strip()
        if trib_dj:
            mapeado = DATAJUD_TRIBUNAL_TO_NOTION.get(trib_dj)
            if mapeado is None:
                logger.warning(
                    "DataJUD: tribunal não mapeado: %r (CNJ %s)",
                    trib_dj, cnj,
                )
                out["Tribunal"] = trib_dj
            else:
                out["Tribunal"] = mapeado

    # 3. Instância (grau alvo conforme cadastro Notion)
    if maior_src is not None and maior_grau is not None:
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

    # 7. Trânsito cognitivo (G1 → G2 → GS; cód 848)
    out["Data do trânsito em julgado (cognitiva)"] = (
        derivar_data_transito_cognitiva(sources_view)
    )

    # 8. Status (grau alvo do cadastro)
    out["Status"] = derivar_status(maior_src[1] if maior_src else None)

    # 9. Fase (grau alvo do cadastro; via classe + códigos)
    out["Fase"] = derivar_fase(maior_src[1] if maior_src else None)

    # 10. Número STJ/TST (específico — só GS-stj/tst)
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


def _resolve_grau(
    grau_alvo: str,
    por_grau: dict[str, list[tuple[str, dict[str, Any]]]],
) -> str | None:
    """Resolve o grau efetivo: usa ``grau_alvo`` se disponível na API;
    senão faz fallback para o maior grau efetivamente retornado.

    Garante que Status/Fase/Instância sempre tenham um source pra
    consumir, mesmo quando o cadastro Notion está desatualizado e
    a API só conhece outros graus do processo.
    """
    if grau_alvo in por_grau:
        return grau_alvo
    graus_disponiveis = sorted(
        (g for g in por_grau if g in _GRAU_RANK),
        key=lambda g: _GRAU_RANK[g],
    )
    return graus_disponiveis[-1] if graus_disponiveis else None


def _instancia_canonica(
    grau: str,
    endpoint: str,
    source: dict[str, Any],
) -> str | None:
    """Mapeia ``(grau, endpoint)`` para a Instância canônica do Notion.

    G1 → "1º grau"; G2 → "2º grau"; GS → STJ/TST/STF conforme endpoint
    de origem (ou source.tribunal como fallback pra GS atípicos em
    endpoint TJ/TRT).

    Retorna None apenas em GS atípico não-resolvível. Garante invariante
    de vocabulário Notion via assertion.
    """
    resultado: str | None = None
    if grau == "G1":
        resultado = INSTANCIA_1G
    elif grau == "G2":
        resultado = INSTANCIA_2G
    elif grau == "GS":
        if endpoint == "stj":
            resultado = INSTANCIA_STJ
        elif endpoint == "tst":
            resultado = INSTANCIA_TST
        else:
            # GS num endpoint TJ/TRT — atípico; tenta source.tribunal.
            trib = str(source.get("tribunal") or "").upper()
            if trib == "STJ":
                resultado = INSTANCIA_STJ
            elif trib == "TST":
                resultado = INSTANCIA_TST
            elif trib == "STF":
                resultado = INSTANCIA_STF
    assert resultado is None or resultado in INSTANCIA_VOCABULARIO_NOTION, (
        f"_instancia_canonica emitiu valor fora do vocabulário Notion: {resultado!r}"
    )
    return resultado
