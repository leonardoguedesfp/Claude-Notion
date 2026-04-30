"""Fase 0 — schema dinâmico: parser de resposta da API Notion → estrutura canônica.

Converte o objeto data_source devolvido por
``GET /v1/data_sources/{id}`` em um dict canônico que será serializado
como JSON em ``audit.db.meta_schemas.schema_json``.

A estrutura canônica é descrita em DESIGN_SCHEMA_DINAMICO.md §3.3.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)

# Tipos cuja edição inline é desabilitada por default.
# Tipos novos da API Notion (status, button, unique_id, verification, …)
# entram aqui automaticamente até termos editor próprio.
_NON_EDITABLE_TIPOS: frozenset[str] = frozenset({
    "rollup", "formula",
    "created_time", "last_edited_time",
    "created_by", "last_edited_by",
    "unique_id", "button", "verification",
})

# Tipos que aparecem como visíveis no padrão "tabela limpa".
# Heurística: title + selects + datas + booleans + URL/email/phone.
# multi_select e rich_text ficam ocultos por default (poluem visualmente).
_DEFAULT_VISIBLE_TIPOS: frozenset[str] = frozenset({
    "title", "select", "date", "checkbox",
    "email", "phone_number", "url",
})

# Limite de relações visíveis por padrão (as 3 primeiras na ordem do schema).
_MAX_DEFAULT_VISIBLE_RELATIONS = 3


def slugify_key(notion_name: str) -> str:
    """Converte o nome de propriedade do Notion em uma key Python canônica.

    Regras:
      - lowercase
      - NFKD + filtro ASCII (remove acentos: "Número" → "Numero")
      - tudo que não for [a-z0-9] vira underscore
      - underscores múltiplos colapsam em um
      - sem underscore inicial/final

    Exemplos:
      "Número do processo"   → "numero_do_processo"
      "Tipo de ação"         → "tipo_de_acao"
      "CPF/CNPJ"             → "cpf_cnpj"
      "Sobrestado - IRR 20"  → "sobrestado_irr_20"
      "Tema 955 — Sobrestado" (em-dash U+2014) → "tema_955_sobrestado"
    """
    # Decompõe acentos: "ã" → "a"+"~"; descarta combining marks
    decomposed = unicodedata.normalize("NFKD", notion_name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    # Substitui qualquer não-alfanumérico por underscore; colapsa runs
    slug = re.sub(r"[^a-z0-9]+", "_", lowered)
    return slug.strip("_")


def compute_schema_hash(schema_dict: dict[str, Any]) -> str:
    """SHA-256 hex do JSON canônico (sort_keys=True, ensure_ascii=False).

    Usado para detecção de drift: dois schemas idênticos têm o mesmo hash
    independente da ordem das chaves no dict de origem.
    """
    canonical = json.dumps(schema_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_options(prop_block: dict[str, Any], tipo: str) -> list[dict[str, str]]:
    """Extrai opcoes [{name, color}] de selects e multi-selects.

    Para outros tipos retorna lista vazia (parser homogeneizando o shape).
    """
    if tipo not in ("select", "multi_select"):
        return []
    inner = prop_block.get(tipo, {})
    raw_options = inner.get("options", [])
    return [
        {
            "name": opt.get("name", ""),
            "color": opt.get("color", "default"),
        }
        for opt in raw_options
    ]


def _is_editavel(tipo: str) -> bool:
    """Editabilidade default para um tipo."""
    if tipo in _NON_EDITABLE_TIPOS:
        return False
    # 'relation' é editável em princípio, mas o app ainda não tem picker
    # (ver delegates._NON_EDITABLE_TIPOS). Não negar aqui — o registry/UI
    # decide. O legado já trata relation como readonly via outro caminho.
    return True


def _is_default_visible(
    tipo: str, relation_seen_so_far: int,
) -> bool:
    """Heurística de visibilidade default.

    - title e tipos do conjunto _DEFAULT_VISIBLE_TIPOS sempre True.
    - relation: True para as 3 primeiras na ordem do schema.
    - demais (multi_select, rich_text, number, people, rollup, created_*, …): False.
    """
    if tipo == "title":
        return True
    if tipo in _DEFAULT_VISIBLE_TIPOS:
        return True
    if tipo == "relation":
        return relation_seen_so_far < _MAX_DEFAULT_VISIBLE_RELATIONS
    return False


def parse_to_schema_json(raw: dict[str, Any], base_label: str) -> dict[str, Any]:
    """Converte resposta da API Notion em estrutura canônica.

    Args:
        raw: dict retornado por NotionClient.get_data_source(id). Esperado:
            {"object": "data_source", "id": "...", "properties": {...}}.
        base_label: rótulo curto da base ("Processos", "Catalogo", etc.).

    Returns:
        Dict com chaves data_source_id, base_label, title_property,
        title_key, properties. A chave "properties" é um dict
        {slug_key: prop_dict} preservando a ordem do dict de entrada,
        com title forçado em primeira posição (default_order=1).

    Tipos desconhecidos não crasham — viram entries readonly + invisíveis,
    com warning no logger.
    """
    data_source_id = raw.get("id", "")
    raw_properties: dict[str, dict[str, Any]] = raw.get("properties", {})

    # Localiza a property do tipo title primeiro — vai ser default_order=1
    title_notion_name: str | None = None
    title_key: str | None = None
    for notion_name, block in raw_properties.items():
        if block.get("type") == "title":
            title_notion_name = notion_name
            title_key = slugify_key(notion_name)
            break

    parsed_properties: dict[str, dict[str, Any]] = {}
    relation_count = 0
    order_counter = 1  # title = 1; demais começam em 2

    # Helper para construir um entry parseado
    def _build_entry(
        notion_name: str, block: dict[str, Any], order: int,
    ) -> dict[str, Any]:
        nonlocal relation_count
        tipo = block.get("type", "unknown")
        if tipo == "unknown" or tipo not in _KNOWN_TIPOS:
            logger.warning(
                "Tipo desconhecido %r em propriedade %r (base %s); tratado como readonly.",
                tipo, notion_name, base_label,
            )
        opcoes = _parse_options(block, tipo)
        # default_visible para relation depende de quantas relations já vimos
        if tipo == "relation":
            visible = _is_default_visible(tipo, relation_count)
            relation_count += 1
        else:
            visible = _is_default_visible(tipo, 0)
        # Tipo desconhecido: sempre readonly + invisível, ignora heurísticas
        if tipo not in _KNOWN_TIPOS:
            editavel = False
            visible = False
        else:
            editavel = _is_editavel(tipo)
        # Fase 3: capturar data_source_id da relation para o registry
        # resolver target_base depois (lookup reverso em DATA_SOURCES).
        # Sem isso, _on_table_double_clicked em Processos não sabe para qual
        # base navegar (PropSpec.target_base ficaria vazio).
        target_data_source_id = ""
        if tipo == "relation":
            rel_block = block.get("relation", {}) or {}
            target_data_source_id = rel_block.get("data_source_id", "") or ""
        # Round 6 Parte 1: captura metadata de rollup. O registry usa
        # ``relation_property_name`` + ``rollup_property_name`` pra fazer
        # a resolução 2-hop e descobrir o target_base de rollups que
        # apontam pra um campo relation na base relacionada (ex:
        # Tarefas.Cliente roll up Processos.Clientes → Clientes).
        # Sem isso o display mostra UUIDs em vez de nomes.
        rollup_meta: dict[str, str] = {}
        if tipo == "rollup":
            rb = block.get("rollup", {}) or {}
            rollup_meta = {
                "relation_property_name": rb.get("relation_property_name") or "",
                "rollup_property_name":   rb.get("rollup_property_name") or "",
                "function":               rb.get("function") or "",
            }
        return {
            "notion_name": notion_name,
            "tipo": tipo,
            "label": notion_name,
            "editavel": editavel,
            "obrigatorio": tipo == "title",
            "opcoes": opcoes,
            "default_visible": visible,
            "default_order": order,
            "target_data_source_id": target_data_source_id,
            "rollup_meta": rollup_meta,
        }

    # Title primeiro (se existe)
    if title_notion_name is not None and title_key is not None:
        parsed_properties[title_key] = _build_entry(
            title_notion_name, raw_properties[title_notion_name], order_counter,
        )
        order_counter += 1

    # Demais properties na ordem da API
    for notion_name, block in raw_properties.items():
        if notion_name == title_notion_name:
            continue
        key = slugify_key(notion_name)
        if not key:
            logger.warning(
                "Propriedade %r gerou slug vazio; pulando.", notion_name,
            )
            continue
        if key in parsed_properties:
            # Colisão de slug — possível em casos extremos. Adiciona sufixo
            # numérico para preservar ambas as propriedades sem perda de dado.
            suffix = 2
            while f"{key}_{suffix}" in parsed_properties:
                suffix += 1
            logger.warning(
                "Colisão de slug %r para %r; usando %r.",
                key, notion_name, f"{key}_{suffix}",
            )
            key = f"{key}_{suffix}"
        parsed_properties[key] = _build_entry(notion_name, block, order_counter)
        order_counter += 1

    return {
        "data_source_id": data_source_id,
        "base_label": base_label,
        "title_property": title_notion_name,
        "title_key": title_key,
        "properties": parsed_properties,
    }


# Conjunto de tipos que o parser sabe lidar nativamente. Tipos fora dessa
# lista entram como readonly + invisível, com warning.
_KNOWN_TIPOS: frozenset[str] = frozenset({
    "title", "rich_text", "number", "select", "multi_select",
    "date", "people", "checkbox", "relation", "rollup", "formula",
    "url", "email", "phone_number",
    "created_time", "last_edited_time", "created_by", "last_edited_by",
    "files", "status", "unique_id", "button", "verification",
})
