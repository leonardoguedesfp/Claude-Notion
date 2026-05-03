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
import sqlite3
from typing import Any

from notion_rpadv.services import dje_db
from notion_rpadv.services.dje_notion_constants import (
    NOTION_BLOCK_TEXT_LIMIT,
    NOTION_TEXTO_INLINE_LIMIT,
)
from notion_rpadv.services.dje_processos import _normaliza_cnj

logger = logging.getLogger("dje.notion.mapper")


# ---------------------------------------------------------------------------
# Lista canônica das OABs do escritório (12 — 6 ativas + 6 desativadas).
# Fase 5: o multi-select "Advogados intimados" da database aceita TAGS pré-
# criadas no Notion. Cruzamos com TODAS as 12 (não só as ativas) porque
# publicações antigas no banco podem conter advogados desativados.
# ---------------------------------------------------------------------------


_OABS_ESCRITORIO_TAGS: dict[str, str] = {
    # OAB normalizada → tag exibida no multi-select do Notion (primeiro nome).
    "15523/DF": "Ricardo",
    "36129/DF": "Leonardo",
    "48468/DF": "Vitor",
    "20120/DF": "Cecília",
    "38809/DF": "Samantha",
    "75799/DF": "Deborah",
    "65089/DF": "Juliana Vieira",
    "81225/DF": "Juliana Chiaratto",
    "37654/DF": "Shirley",
    "39857/DF": "Erika",
    "84703/DF": "Maria Isabel",
    "79658/DF": "Cristiane",
}


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
    """Monta a lista de blocos do corpo da página: heading "Texto da
    publicação" + parágrafos + heading "Observações" + observações ou
    placeholder."""
    blocks: list[dict[str, Any]] = []
    blocks.append(_heading2_block("Texto da publicação"))
    texto = (texto_completo or "").strip()
    if not texto:
        blocks.append(_paragraph_block("(texto vazio)"))
    else:
        # Quebra por parágrafos (linha em branco) e depois cada parágrafo
        # em chunks ≤ NOTION_BLOCK_TEXT_LIMIT.
        for paragrafo in texto.split("\n\n"):
            paragrafo = paragrafo.strip()
            if not paragrafo:
                continue
            for chunk in _split_paragraph_at_limit(
                paragrafo, NOTION_BLOCK_TEXT_LIMIT,
            ):
                blocks.append(_paragraph_block(chunk))

    blocks.append(_heading2_block("Observações"))
    obs = (observacoes or "").strip()
    if obs:
        for chunk in _split_paragraph_at_limit(obs, NOTION_BLOCK_TEXT_LIMIT):
            blocks.append(_paragraph_block(chunk))
    else:
        blocks.append(
            _quote_block("Sem observações automáticas pra esta publicação."),
        )
    return blocks


# ---------------------------------------------------------------------------
# Lookup do processo no cache local (Relation)
# ---------------------------------------------------------------------------


def lookup_processo_page_id(
    cache_conn: sqlite3.Connection,
    numero_processo_com_mascara: str | None,
) -> str | None:
    """Procura a página de Processos no cache local cujo
    ``numero_do_processo`` bate com a publicação. Comparação CNJ-tolerante:
    ambos os lados são normalizados via ``_normaliza_cnj`` antes do match.

    Retorna ``page_id`` (UUID Notion) ou ``None`` se não achou.
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
            return str(row["page_id"])
    return None


# ---------------------------------------------------------------------------
# Cruzamento de advogados do escritório → tags
# ---------------------------------------------------------------------------


def _advogados_escritorio_em_destinatarios(
    destinatarioadvogados: Any,
) -> list[str]:
    """Retorna a lista de tags (nomes do escritório) que aparecem em
    ``destinatarioadvogados`` da publicação. Externos são desprezados.

    A estrutura real do DJEN tem ``numero_oab``/``uf_oab`` aninhados em
    ``entry["advogado"]`` (descoberta do smoke da Fase 2.2); aqui
    fazemos lookup com fallback no nível raiz pra fixtures legacy."""
    tags: list[str] = []
    if not isinstance(destinatarioadvogados, list):
        return tags
    seen: set[str] = set()
    for entry in destinatarioadvogados:
        if not isinstance(entry, dict):
            continue
        adv = (
            entry.get("advogado")
            if isinstance(entry.get("advogado"), dict)
            else entry
        )
        oab_raw = str(adv.get("numero_oab") or "").strip()
        oab_digits = "".join(c for c in oab_raw if c.isdigit())
        uf = str(adv.get("uf_oab") or "").strip().upper()
        if not oab_digits or not uf:
            continue
        oab_uf = f"{oab_digits}/{uf}"
        if oab_uf in _OABS_ESCRITORIO_TAGS and oab_uf not in seen:
            seen.add(oab_uf)
            tags.append(_OABS_ESCRITORIO_TAGS[oab_uf])
    return tags


def _tem_advogados_no_payload(destinatarioadvogados: Any) -> bool:
    """``destinatarioadvogados`` é lista não-vazia de dicts? Usado pra
    distinguir "lista de destinatários vazia" (não marca checkbox) de
    "tinha lista mas só com externos" (marca checkbox).
    """
    return (
        isinstance(destinatarioadvogados, list)
        and any(isinstance(e, dict) for e in destinatarioadvogados)
    )


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
    processo_page_id = lookup_processo_page_id(cache_conn, numero_processo)
    processo_nao_cadastrado = processo_page_id is None

    advogados_tags = _advogados_escritorio_em_destinatarios(
        publicacao.get("destinatarioadvogados"),
    )
    tinha_destinatarios = _tem_advogados_no_payload(
        publicacao.get("destinatarioadvogados"),
    )
    # "Advogados não cadastrados" só dispara quando havia destinatários
    # mas NENHUM era do escritório — distinção do spec D20 entre
    # "lista vazia" (não marca) e "lista só com externos" (marca).
    advogados_nao_cadastrados = (
        tinha_destinatarios and len(advogados_tags) == 0
    )

    # Partes (destinatarios é lista de dicts no DJEN). Serializa JSON
    # truncado pra caber em rich_text inline.
    destinatarios_raw = publicacao.get("destinatarios")
    if isinstance(destinatarios_raw, (list, dict)):
        destinatarios_str = json.dumps(
            destinatarios_raw, ensure_ascii=False,
        )
    else:
        destinatarios_str = str(destinatarios_raw or "")

    properties: dict[str, Any] = {
        "Identificação": _title_prop(titulo),
        "Data de disponibilização": _date_prop(data_disp),
        "Tribunal": _select_prop(sigla if sigla and sigla != "N/A" else None),
        "Processo": _relation_prop(
            [processo_page_id] if processo_page_id else [],
        ),
        "Órgão": _rich_text_prop(publicacao.get("nomeOrgao")),
        "Tipo de comunicação": _select_prop(publicacao.get("tipoComunicacao")),
        "Tipo de documento": _select_prop(publicacao.get("tipoDocumento")),
        "Classe": _rich_text_prop(publicacao.get("nomeClasse")),
        "Texto": _rich_text_prop(publicacao.get("texto")),
        "Link": _url_prop(publicacao.get("link")),
        "Status": _select_prop("Nova"),
        "Advogados intimados": _multi_select_prop(advogados_tags),
        "Observações": _rich_text_prop(publicacao.get("observacoes")),
        "Partes": _rich_text_prop(destinatarios_str),
        "Hash": _rich_text_prop(publicacao.get("hash")),
        "ID DJEN": _number_prop(publicacao.get("id")),
        "Processo não cadastrado": _checkbox_prop(processo_nao_cadastrado),
        "Advogados não cadastrados": _checkbox_prop(advogados_nao_cadastrados),
    }

    children = _build_corpo_blocks(
        publicacao.get("texto"),
        publicacao.get("observacoes"),
    )

    return {
        "properties": properties,
        "children": children,
        # Metadados úteis pro caller logar — não fazem parte do body Notion.
        "_meta": {
            "titulo": titulo,
            "djen_id": publicacao.get("id"),
            "sigla_tribunal": sigla,
            "processo_nao_cadastrado": processo_nao_cadastrado,
            "advogados_nao_cadastrados": advogados_nao_cadastrados,
            "advogados_tags": advogados_tags,
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
