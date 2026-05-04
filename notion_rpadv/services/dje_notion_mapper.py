"""Mapeamento de uma publicação DJEN → payload da database 📬 Publicações
do Notion (Fase 5, 2026-05-03).

A database tem 20 propriedades; mapeamos 18 delas (2 são automáticas:
``Cliente`` é Rollup do Processo, ``Certidão`` é Formula do Hash). O
texto completo da publicação vai pro CORPO DA PÁGINA em blocos
``paragraph`` quebrados a cada 2000 chars (limite Notion por bloco).

Constantes operacionais (data source IDs, limites, rate-limit, retry)
ficam em ``dje_notion_constants``.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from typing import Any

from notion_rpadv.services import dje_db
from notion_rpadv.services.dje_notion_constants import (
    NOTION_TEXTO_INLINE_LIMIT,
)
from notion_rpadv.services.dje_notion_mappings import (
    formatar_advogados_intimados,
    formatar_partes,
    mapear_tipo_comunicacao,
    mapear_tipo_documento,
    normalizar_classe,
    tinha_destinatarios_advogados,
)
from notion_rpadv.services.dje_processos import _normaliza_cnj
from notion_rpadv.services.dje_text_pipeline import (
    aplicar_caso_15,
    preprocessar_texto_djen,
    quebrar_em_blocos,
    truncar_texto_inline,
)

logger = logging.getLogger("dje.notion.mapper")


# ---------------------------------------------------------------------------
# Helpers de formatação (Notion API JSON shapes)
# ---------------------------------------------------------------------------


def _truncate_with_ellipsis(text: str, limit: int) -> str:
    """Trunca em ``limit`` caracteres, adicionando ``...`` se cortou."""
    s = str(text or "")
    if len(s) <= limit:
        return s
    return s[: max(limit - 3, 0)] + "..."


def _title_prop(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": text}}]}


def _rich_text_prop(text: str | None) -> dict[str, Any]:
    """Rich text property — tolera None (gera lista vazia)."""
    s = (text or "").strip()
    if not s:
        return {"rich_text": []}
    truncated = _truncate_with_ellipsis(s, NOTION_TEXTO_INLINE_LIMIT)
    return {
        "rich_text": [{"type": "text", "text": {"content": truncated}}],
    }


def _texto_inline_prop(texto_pre: str | None) -> dict[str, Any]:
    """Property "Texto" — usa truncar_texto_inline (1.8) com corte em
    fronteira de palavra e marcador " […]"."""
    if not texto_pre:
        return {"rich_text": []}
    truncado = truncar_texto_inline(texto_pre, limite=NOTION_TEXTO_INLINE_LIMIT)
    return {
        "rich_text": [{"type": "text", "text": {"content": truncado}}],
    }


def _select_prop(name: str | None) -> dict[str, Any]:
    """Select property — None vira ``{"select": None}`` (limpa seleção)."""
    if not name:
        return {"select": None}
    return {"select": {"name": str(name)}}


def _multi_select_prop(names: list[str]) -> dict[str, Any]:
    return {"multi_select": [{"name": n} for n in names]}


def _date_prop(iso_date: str | None) -> dict[str, Any]:
    if not iso_date:
        return {"date": None}
    return {"date": {"start": str(iso_date)}}


def _number_prop(n: Any) -> dict[str, Any]:
    if n is None:
        return {"number": None}
    try:
        return {"number": int(n)}
    except (TypeError, ValueError):
        return {"number": None}


def _url_prop(u: str | None) -> dict[str, Any]:
    if not u:
        return {"url": None}
    return {"url": str(u)}


def _checkbox_prop(b: bool) -> dict[str, Any]:
    return {"checkbox": bool(b)}


def _relation_prop(page_ids: list[str]) -> dict[str, Any]:
    return {"relation": [{"id": pid} for pid in page_ids]}


# ---------------------------------------------------------------------------
# Blocos do corpo da página (children)
# ---------------------------------------------------------------------------


def _heading2_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _paragraph_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _quote_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "quote",
        "quote": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _split_paragraph_at_limit(text: str, limit: int) -> list[str]:
    """Quebra um parágrafo em chunks ≤ ``limit`` chars cada. Tenta quebrar
    em separadores naturais (espaço, ponto) próximo ao limite — se não,
    corta cru."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    pos = 0
    while pos < len(text):
        end = min(pos + limit, len(text))
        if end == len(text):
            chunks.append(text[pos:end])
            break
        # Tenta cortar em espaço dentro dos últimos 50 chars do limite.
        cut = text.rfind(" ", pos, end)
        if cut <= pos + limit - 50:
            cut = end  # sem espaço próximo: corta cru
        chunks.append(text[pos:cut])
        pos = cut + (1 if cut < len(text) and text[cut] == " " else 0)
    return chunks


def _build_corpo_blocks(
    texto_completo: str | None,
    observacoes: str | None,
) -> list[dict[str, Any]]:
    """LEGACY: monta lista de blocos do corpo (heading "Texto da
    publicação" + texto + heading "Observações" + obs/placeholder)
    SEM aplicar a filtragem 1.5 (que precisa de tribunal+tipo). Usa
    pipeline simplificada: 1.7 (preprocessar) + 1.4 (quebrar_em_blocos).

    Caller que precise da pipeline completa (com filtragem TJDFT e
    callouts) deve chamar ``montar_payload_publicacao`` (que orquestra
    todos os estágios)."""
    blocks: list[dict[str, Any]] = []
    blocks.append(_heading2_block("Texto da publicação"))
    texto_pre = preprocessar_texto_djen(texto_completo)
    blocos_texto = quebrar_em_blocos(texto_pre) if texto_pre else []
    if not blocos_texto:
        blocos_texto = [_paragraph_block("(texto vazio)")]
    blocks.extend(blocos_texto)

    blocks.append(_heading2_block("Observações"))
    obs_pre = preprocessar_texto_djen(observacoes) if observacoes else ""
    if obs_pre:
        blocks.extend(quebrar_em_blocos(obs_pre))
    else:
        blocks.append(
            _quote_block("Sem observações automáticas pra esta publicação."),
        )
    return blocks


def _build_corpo_blocks_full(
    publicacao: dict[str, Any],
    *,
    tipo_documento_canonico: str,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """Pipeline completa de blocos do corpo da página (1.7 → 1.5 → 1.4).

    Retorna:

    - ``children``: lista pronta de blocos (heading_2 wrappers + filtrado/
      truncado + callout opcional + observações).
    - ``texto_pre``: texto após pré-processamento HTML — útil pra dedup
      (chave canônica usa este string) e pra inline "Texto" property.
    - ``callouts``: blocos callout que foram anexados (geralmente 0 ou 1).
      Exposto separadamente em ``_meta`` pra debug.
    """
    texto_bruto = publicacao.get("texto")
    tribunal = publicacao.get("siglaTribunal") or ""
    hash_djen = publicacao.get("hash") or ""
    # Round 4.5 frente 2 — passa tipoDocumento bruto e CNJ pro filtro de
    # Ata TJDFT tipo "57" (que vira "Outros" canônico, então o filtro
    # precisa do bruto).
    tipo_documento_bruto = publicacao.get("tipoDocumento")
    cnj_escritorio = (
        publicacao.get("numeroprocessocommascara")
        or publicacao.get("numero_processo")
        or None
    )

    texto_pre = preprocessar_texto_djen(texto_bruto)
    texto_corpo, callouts = aplicar_caso_15(
        tribunal=tribunal,
        tipo_documento=tipo_documento_canonico,
        texto=texto_pre,
        hash_djen=hash_djen,
        tipo_documento_bruto=tipo_documento_bruto,
        cnj_escritorio=cnj_escritorio,
    )

    blocos_texto = quebrar_em_blocos(texto_corpo) if texto_corpo else []
    if not blocos_texto:
        blocos_texto = [_paragraph_block("(texto vazio)")]

    children: list[dict[str, Any]] = [_heading2_block("Texto da publicação")]
    children.extend(blocos_texto)
    children.extend(callouts)

    children.append(_heading2_block("Observações"))
    obs_pre = preprocessar_texto_djen(publicacao.get("observacoes"))
    if obs_pre:
        children.extend(quebrar_em_blocos(obs_pre))
    else:
        children.append(
            _quote_block("Sem observações automáticas pra esta publicação."),
        )

    return children, texto_pre, callouts


# ---------------------------------------------------------------------------
# Lookup do processo no cache local (Relation)
# ---------------------------------------------------------------------------


def lookup_processo_record(
    cache_conn: sqlite3.Connection,
    numero_processo_com_mascara: str | None,
) -> dict[str, Any] | None:
    """Procura o record completo do Processo cadastrado em ⚖️ Processos
    no cache local. Comparação CNJ-tolerante (ambos os lados normalizados
    via ``_normaliza_cnj``).

    Retorna o dict do record (com chave ``page_id`` adicionada) ou
    ``None`` se não achou. Usado pelo Round 4.4 (regras de alerta
    contadoria precisam de ``instancia``, ``data_do_transito_em_julgado_*``
    etc.).
    """
    target = _normaliza_cnj(str(numero_processo_com_mascara or ""))
    if target is None:
        return None
    rows = cache_conn.execute(
        "SELECT page_id, data_json FROM records WHERE base = ?",
        ("Processos",),
    ).fetchall()
    for row in rows:
        try:
            rec = json.loads(row["data_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        candidato = _normaliza_cnj(str(rec.get("numero_do_processo") or ""))
        if candidato == target:
            rec["page_id"] = str(row["page_id"])
            return rec
    return None


def lookup_processo_page_id(
    cache_conn: sqlite3.Connection,
    numero_processo_com_mascara: str | None,
) -> str | None:
    """Procura apenas o ``page_id`` do Processo cadastrado. Wrapper sobre
    ``lookup_processo_record`` mantido pra retro-compatibilidade com
    testes/callers que só precisam do UUID."""
    rec = lookup_processo_record(cache_conn, numero_processo_com_mascara)
    return rec["page_id"] if rec else None


# ---------------------------------------------------------------------------
# Cruzamento de advogados do escritório → tags
#
# Round 1 (2026-05-03): movido pra ``dje_notion_mappings``. Os aliases
# abaixo preservam compatibilidade com testes/legacy callers que
# importavam os nomes privados originais. Use as funções públicas
# ``formatar_advogados_intimados`` / ``tinha_destinatarios_advogados``
# em código novo.
# ---------------------------------------------------------------------------


_advogados_escritorio_em_destinatarios = formatar_advogados_intimados
_tem_advogados_no_payload = tinha_destinatarios_advogados


# ---------------------------------------------------------------------------
# Round 4.5 frente 1 — Auto-Status na criação da página
# ---------------------------------------------------------------------------

#: Status default na criação. Round 1 sempre gravou "Nova"; Round 4.5
#: introduz exceções específicas (vide ``_calcular_status_inicial``).
STATUS_DEFAULT_CRIACAO: str = "Nova"

#: Status auto pra publicações que não exigem ação (Listas de
#: Distribuição em tribunais trabalhistas com Processo cadastrado).
#: Opção EXISTENTE no select do Notion — não criar nova.
STATUS_NADA_PARA_FAZER: str = "Nada para fazer"

#: Tribunais que recebem auto-Status "Nada para fazer" para Listas de
#: Distribuição com Processo cadastrado. Trabalhistas (TRT10, TST)
#: porque a Lista é só comunicação burocrática de distribuição —
#: a ação substantiva virá em pubs subsequentes (Despacho, Acórdão).
_TRIBUNAIS_LISTA_AUTO_TRIADA: frozenset[str] = frozenset({"TRT10", "TST"})


def _calcular_status_inicial(
    *,
    tipo_comunicacao_canonico: str,
    sigla_tribunal: str,
    processo_record: dict[str, Any] | None,
) -> str:
    """Decide o Status inicial da página recém-criada.

    Round 4.5 frente 1 (P1-1 da auditoria):
    Auto-``Nada para fazer`` quando todas as condições batem:
    - tipo de comunicação canônico = ``Lista de Distribuição``
    - tribunal IN (TRT10, TST) — trabalhistas
    - processo cadastrado em ⚖️ Processos

    Caso contrário: ``Nova`` (default) — operador trata manualmente.

    Esta função roda APENAS na criação da página (nunca em update),
    portanto não há risco de sobrescrever Status já modificado pelo
    operador. Defesa em profundidade: caller só chama daqui no
    ``montar_payload_publicacao`` (criação), nunca em fluxos de update.
    """
    sigla = (sigla_tribunal or "").strip().upper()
    if (
        tipo_comunicacao_canonico == "Lista de Distribuição"
        and sigla in _TRIBUNAIS_LISTA_AUTO_TRIADA
        and processo_record is not None
    ):
        return STATUS_NADA_PARA_FAZER
    return STATUS_DEFAULT_CRIACAO


# ---------------------------------------------------------------------------
# Round 4.4 — Auto-Alerta contadoria (5 regras multi-select)
# ---------------------------------------------------------------------------

#: Alertas canônicos do Round 4.4. Strings exatas que vão pro multi-select
#: ``Alerta contadoria`` no Notion. Bumpe se renomear opções no Notion.
ALERTA_PROCESSO_NAO_CADASTRADO: str = "Processo não cadastrado"
ALERTA_INSTANCIA_DESATUALIZADA: str = "Instância desatualizada"
ALERTA_TRANSITO_PENDENTE: str = "Trânsito em julgado pendente"
ALERTA_TEXTO_IMPRESTAVEL: str = "Texto imprestável"
ALERTA_PAUTA_PRESENCIAL_SEM_INSCRICAO: str = "Pauta presencial sem inscrição"


def _texto_e_imprestavel(texto: str) -> bool:
    """Detecção conservadora de texto imprestável — apenas as classes
    conhecidas vistas em produção. NÃO dispara em despachos breves
    legítimos.

    Classes detectadas:
    - TJGO: ``"ARQUIVOS DIGITAIS INDISPONÍVEIS (NÃO SÃO DO TIPO PÚBLICO)"``.
    - Despachos minimalistas: ``"Intime-se."``, ``"Intimem-se."``.
    - TRT10 só com referência a ID: ``"Tomar ciência do(a) Intimação de ID..."`` SEM CNJ no texto.
    """
    if not texto:
        return False
    t = texto.strip()
    if "ARQUIVOS DIGITAIS INDISPONÍVEIS" in t:
        return True
    if t in ("Intime-se.", "Intimem-se."):
        return True
    if "Tomar ciência" in t and "Intimação de ID" in t:
        # Verifica se há CNJ no texto (formato 0000000-00.0000)
        if not re.search(r"\d{7}-\d{2}", t):
            return True
    return False


def _aplicar_regras_alerta_contadoria(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> list[str]:
    """Aplica as 5 regras do Round 4.4 e retorna lista de alertas que
    dispararam (multi-select aceita múltiplos).

    Regras:

    1. ``Processo não cadastrado``: ``processo_record is None``.
    2. ``Instância desatualizada``: tribunal da pub IN (TST, STJ, STF) E
       processo cadastrado E ``instancia`` IN ("1º grau", "2º grau").
    3. ``Trânsito em julgado pendente``: ``nomeClasse`` contém
       "CUMPRIMENTO" (sem "PROVISÓRIO" — D3) E processo cadastrado E
       ambos ``data_do_transito_em_julgado_cognitiva`` e
       ``data_do_transito_em_julgado_executiva`` vazios.
    4. ``Texto imprestável``: texto < 200 chars E é uma classe conhecida
       de imprestabilidade (vide ``_texto_e_imprestavel``).
    5. ``Pauta presencial sem inscrição``: tipo canônico Pauta de
       Julgamento E texto contém "PRESENCIAL" ou "Sala de Sessão".
    """
    alertas: list[str] = []

    # 1. Processo não cadastrado
    if processo_record is None:
        alertas.append(ALERTA_PROCESSO_NAO_CADASTRADO)

    # 2. Instância desatualizada
    if processo_record is not None:
        sigla = (publicacao.get("siglaTribunal") or "").strip().upper()
        instancia = (processo_record.get("instancia") or "").strip()
        if sigla in {"TST", "STJ", "STF"} and instancia in {"1º grau", "2º grau"}:
            alertas.append(ALERTA_INSTANCIA_DESATUALIZADA)

    # 3. Trânsito em julgado pendente
    nome_classe = (publicacao.get("nomeClasse") or "").upper()
    if (
        "CUMPRIMENTO" in nome_classe
        and "PROVISÓRIO" not in nome_classe  # D3: exclui provisório
        and processo_record is not None
    ):
        t_cog = processo_record.get("data_do_transito_em_julgado_cognitiva")
        t_exec = processo_record.get("data_do_transito_em_julgado_executiva")
        if not t_cog and not t_exec:
            alertas.append(ALERTA_TRANSITO_PENDENTE)

    # 4. Texto imprestável
    texto = publicacao.get("texto") or ""
    if len(texto) < 200 and _texto_e_imprestavel(texto):
        alertas.append(ALERTA_TEXTO_IMPRESTAVEL)

    # 5. Pauta presencial sem inscrição
    tipo_canon = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_canon == "Pauta de Julgamento":
        texto_upper = texto.upper()
        if "PRESENCIAL" in texto_upper or "SALA DE SESSÃO" in texto_upper:
            alertas.append(ALERTA_PAUTA_PRESENCIAL_SEM_INSCRICAO)

    return alertas


# ---------------------------------------------------------------------------
# Round 4.3 — Auto-Tarefa sugerida (6 regras multi-select)
# ---------------------------------------------------------------------------

#: Nomes EXATOS das tarefas no 📚 Catálogo de Tarefas. Bumpe se renomear.
TAREFA_D03_ANALISE_ACORDAO: str = "D.03 Análise de acórdão"
TAREFA_D02_ANALISE_SENTENCA: str = "D.02 Análise de sentença"
TAREFA_D01_ANALISE_PUBLICACAO: str = "D.01 Análise de publicação"
TAREFA_E01_CADASTRO: str = "E.01 Cadastro de cliente/processo"
TAREFA_E02_ATUALIZAR_DADOS: str = "E.02 Atualizar dados no sistema"
TAREFA_E04_INSCRICAO_SUSTENTACAO: str = "E.04 Inscrição para sustentação oral"


def _aplicar_regras_tarefa_sugerida(
    publicacao: dict[str, Any],
    *,
    processo_record: dict[str, Any] | None,
    alertas_disparados: list[str],
) -> list[str]:
    """Aplica as 6 regras do Round 4.3 e retorna lista (deduped) de
    tarefas sugeridas. Multi-select aceita múltiplas (D2: sem
    precedência — pub Acórdão + Pauta soma D.03 + E.04).

    Regras:

    1. ``D.03 Análise de acórdão``: tipoDocumento canônico IN (Acórdão, Ementa).
    2. ``D.02 Análise de sentença``: tipoDocumento canônico = Sentença.
    3. ``D.01 Análise de publicação``: tipoDocumento canônico IN
       (Notificação, Decisão, Despacho, Certidão, Outros, Distribuição)
       E NÃO disparou D.02 nem D.03 (default genérico).
    4. ``E.01 Cadastro de cliente/processo``: ``processo_record is None``.
    5. ``E.02 Atualizar dados no sistema``: tipoDocumento bruto =
       "ATA DE DISTRIBUIÇÃO" OU disparou alerta "Instância desatualizada".
    6. ``E.04 Inscrição para sustentação oral``: tipoDocumento canônico
       = Pauta de Julgamento.

    Ordem de saída segue a numeração das tarefas (D.01 < D.02 < D.03 <
    E.01 < E.02 < E.04) — facilita teste e leitura no Notion.
    """
    tarefas: set[str] = set()
    tipo_canon = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    tipo_bruto = (publicacao.get("tipoDocumento") or "").strip()

    # 1. D.03
    if tipo_canon in {"Acórdão", "Ementa"}:
        tarefas.add(TAREFA_D03_ANALISE_ACORDAO)

    # 2. D.02
    if tipo_canon == "Sentença":
        tarefas.add(TAREFA_D02_ANALISE_SENTENCA)

    # 3. D.01 — só se nem D.02 nem D.03 dispararam
    has_d02_d03 = (
        TAREFA_D02_ANALISE_SENTENCA in tarefas
        or TAREFA_D03_ANALISE_ACORDAO in tarefas
    )
    if not has_d02_d03 and tipo_canon in {
        "Notificação", "Decisão", "Despacho",
        "Certidão", "Outros", "Distribuição",
    }:
        tarefas.add(TAREFA_D01_ANALISE_PUBLICACAO)

    # 4. E.01
    if processo_record is None:
        tarefas.add(TAREFA_E01_CADASTRO)

    # 5. E.02
    if (
        tipo_bruto == "ATA DE DISTRIBUIÇÃO"
        or ALERTA_INSTANCIA_DESATUALIZADA in alertas_disparados
    ):
        tarefas.add(TAREFA_E02_ATUALIZAR_DADOS)

    # 6. E.04
    if tipo_canon == "Pauta de Julgamento":
        tarefas.add(TAREFA_E04_INSCRICAO_SUSTENTACAO)

    # Ordem estável: ordena por código (D.01 < D.02 < D.03 < E.01 < E.02 < E.04)
    return sorted(tarefas)


# ---------------------------------------------------------------------------
# Orquestrador público
# ---------------------------------------------------------------------------


def montar_payload_publicacao(
    publicacao: dict[str, Any],
    *,
    dje_conn: sqlite3.Connection,
    cache_conn: sqlite3.Connection,
) -> dict[str, Any]:
    """Constrói o payload completo (``properties`` + ``children``) pra
    chamada ``POST /v1/pages`` na database 📬 Publicações.

    ``publicacao`` é o dict retornado por
    ``dje_db.fetch_pending_for_notion`` — payload do DJEN mesclado com
    ``advogados_consultados_escritorio`` e ``oabs_externas_consultadas``.

    ``dje_conn`` é usado pra calcular o sequencial N do título (consulta
    publicações já enviadas com mesma combinação tribunal+data).

    ``cache_conn`` é usado pra lookup do Processo no cache local.
    """
    sigla = str(publicacao.get("siglaTribunal") or "").strip() or "N/A"
    data_disp = str(publicacao.get("data_disponibilizacao") or "").strip()
    seq_n = dje_db.count_sequencial_titulo(dje_conn, sigla, data_disp)
    titulo = f"{sigla}___{data_disp}___{seq_n}"

    numero_processo = (
        publicacao.get("numeroprocessocommascara")
        or publicacao.get("numero_processo")
    )
    # Round 4.4/4.6: cruzamento com cache de Processos retorna o record
    # completo (instancia, data_transito_*, etc.) pra alimentar as
    # regras de Alerta contadoria. O page_id é só uma das chaves do
    # record. Round 4.6 remove o checkbox "Processo não cadastrado" do
    # payload — a info passa a viver em Alerta contadoria.
    processo_record = lookup_processo_record(cache_conn, numero_processo)
    processo_page_id = (
        processo_record["page_id"] if processo_record else None
    )
    processo_nao_cadastrado = processo_record is None

    advogados_tags = formatar_advogados_intimados(
        publicacao.get("destinatarioadvogados"),
    )
    tinha_destinatarios = tinha_destinatarios_advogados(
        publicacao.get("destinatarioadvogados"),
    )
    # "Advogados não cadastrados" só dispara quando havia destinatários
    # mas NENHUM era do escritório — distinção do spec D20 entre
    # "lista vazia" (não marca) e "lista só com externos" (marca).
    advogados_nao_cadastrados = (
        tinha_destinatarios and len(advogados_tags) == 0
    )

    # Round 4 (4.1): Partes formatado como "Polo Ativo: X / Polo Passivo: Y"
    # — substitui o JSON cru ilegível da Fase 5/Round 1.
    partes_str = formatar_partes(publicacao.get("destinatarios"))

    tipo_documento_canonico = mapear_tipo_documento(
        publicacao.get("tipoDocumento"),
    )
    tipo_comunicacao_canonico = mapear_tipo_comunicacao(
        publicacao.get("tipoComunicacao"),
    )

    children, texto_pre, callouts = _build_corpo_blocks_full(
        publicacao, tipo_documento_canonico=tipo_documento_canonico,
    )

    # Round 4.4: aplica regras de Alerta contadoria.
    alertas_contadoria = _aplicar_regras_alerta_contadoria(
        publicacao, processo_record,
    )
    # Round 4.3: aplica regras de Tarefa sugerida (depende dos alertas
    # disparados — E.02 dispara em "Instância desatualizada").
    tarefas_sugeridas = _aplicar_regras_tarefa_sugerida(
        publicacao,
        processo_record=processo_record,
        alertas_disparados=alertas_contadoria,
    )
    # Round 4.5 frente 1: Status inicial pode virar "Nada para fazer"
    # em casos óbvios (Listas TRT10/TST com Processo cadastrado).
    status_inicial = _calcular_status_inicial(
        tipo_comunicacao_canonico=tipo_comunicacao_canonico,
        sigla_tribunal=sigla,
        processo_record=processo_record,
    )

    properties: dict[str, Any] = {
        "Identificação": _title_prop(titulo),
        "Data de disponibilização": _date_prop(data_disp),
        "Tribunal": _select_prop(sigla if sigla and sigla != "N/A" else None),
        "Processo": _relation_prop(
            [processo_page_id] if processo_page_id else [],
        ),
        "Órgão": _rich_text_prop(publicacao.get("nomeOrgao")),
        "Tipo de comunicação": _select_prop(tipo_comunicacao_canonico),
        "Tipo de documento": _select_prop(tipo_documento_canonico),
        "Classe": _rich_text_prop(
            normalizar_classe(publicacao.get("nomeClasse")),
        ),
        "Texto": _texto_inline_prop(texto_pre),
        "Link": _url_prop(publicacao.get("link")),
        "Status": _select_prop(status_inicial),
        "Advogados intimados": _multi_select_prop(advogados_tags),
        "Observações": _rich_text_prop(publicacao.get("observacoes")),
        "Partes": _rich_text_prop(partes_str),
        "Hash": _rich_text_prop(publicacao.get("hash")),
        "ID DJEN": _number_prop(publicacao.get("id")),
        # Round 4.6: checkbox "Processo não cadastrado" SAIU. A info passa
        # a viver em "Alerta contadoria" — quando o usuário dropar a
        # coluna do Notion, payloads futuros ainda funcionam.
        "Advogados não cadastrados": _checkbox_prop(advogados_nao_cadastrados),
        # Round 4.3 + 4.4 — multi-selects
        "Tarefa sugerida": _multi_select_prop(tarefas_sugeridas),
        "Alerta contadoria": _multi_select_prop(alertas_contadoria),
    }

    return {
        "properties": properties,
        "children": children,
        # Metadados úteis pro caller logar/fazer dedup — NÃO fazem parte
        # do body Notion. ``texto_pre`` e ``tipo_documento_canonico``
        # são usados pelo módulo de dedup pra computar a chave canônica.
        "_meta": {
            "titulo": titulo,
            "djen_id": publicacao.get("id"),
            "sigla_tribunal": sigla,
            "tipo_documento_canonico": tipo_documento_canonico,
            "tipo_comunicacao_canonico": tipo_comunicacao_canonico,
            "texto_pre": texto_pre,
            "callouts_count": len(callouts),
            "processo_nao_cadastrado": processo_nao_cadastrado,
            "advogados_nao_cadastrados": advogados_nao_cadastrados,
            "advogados_tags": advogados_tags,
            "tarefas_sugeridas": tarefas_sugeridas,
            "alertas_contadoria": alertas_contadoria,
        },
    }


# Conveniência pra caller que só precisa do lookup — exposta pra UI testar.
def listar_processos_lookup(
    cache_conn: sqlite3.Connection,
) -> dict[str, str]:
    """Pré-construi um dict ``{cnj_normalizado: page_id}`` pra speedups
    quando vamos enviar muitas publicações de uma vez. Caller pode usar
    isso em vez de chamar ``lookup_processo_page_id`` por publicação.

    Atualmente NÃO é usado pelo sync (que faz lookup por publicação),
    mas exposto pra futuras otimizações."""
    out: dict[str, str] = {}
    rows = cache_conn.execute(
        "SELECT page_id, data_json FROM records WHERE base = ?",
        ("Processos",),
    ).fetchall()
    for row in rows:
        try:
            rec = json.loads(row["data_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        canon = _normaliza_cnj(str(rec.get("numero_do_processo") or ""))
        if canon is not None:
            out[canon] = str(row["page_id"])
    return out
