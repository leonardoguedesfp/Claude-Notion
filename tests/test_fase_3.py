"""Fase 3 — cleanup do _LEGACY_SCHEMAS e flags.

Esta fase remove:
- USE_DYNAMIC_SCHEMA e DYNAMIC_BASES de config
- _LEGACY_SCHEMAS, vocabulários hardcoded e mapas de cor de schemas.py
- _LEGACY_TITLE_KEYS_BY_BASE e _title_value_for_record de
  base_table_model.py
- Fallbacks legados em delegates, dashboard, processos, validators e app

Adiciona:
- notion_rpadv/theme/notion_colors.py (mapeamento Notion → hex)
- _dict_to_propspec popula cor_por_valor e target_base
- target_data_source_id capturado no parser para resolver target_base
  via DATA_SOURCES
"""
from __future__ import annotations

from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent


# --- Componente 1: flags removidas ---


def test_FASE3_use_dynamic_schema_flag_removed() -> None:
    """USE_DYNAMIC_SCHEMA não existe mais em config."""
    from notion_bulk_edit import config
    assert not hasattr(config, "USE_DYNAMIC_SCHEMA")


def test_FASE3_dynamic_bases_removed() -> None:
    """DYNAMIC_BASES não existe mais em config."""
    from notion_bulk_edit import config
    assert not hasattr(config, "DYNAMIC_BASES")


# --- Componente 2: _LEGACY_SCHEMAS e amigos removidos ---


def test_FASE3_legacy_schemas_removed() -> None:
    """_LEGACY_SCHEMAS dict literal hardcoded foi removido."""
    import notion_bulk_edit.schemas as schemas_mod
    assert not hasattr(schemas_mod, "_LEGACY_SCHEMAS")


def test_FASE3_hardcoded_vocabularios_removed() -> None:
    """Vocabulários TRIBUNAIS, FASES, etc. foram removidos."""
    import notion_bulk_edit.schemas as schemas_mod
    legacy_vocabs = (
        "TRIBUNAIS", "FASES", "STATUS_PROC", "INSTANCIAS",
        "PRIORIDADES", "STATUS_TAREFA", "CATEGORIAS_CATALOGO",
        "AREAS_CATALOGO", "CIDADES_UF",
    )
    for vocab in legacy_vocabs:
        assert not hasattr(schemas_mod, vocab), (
            f"{vocab} ainda em schemas.py"
        )


def test_FASE3_legacy_color_maps_removed() -> None:
    """Mapas de cor _COR_TRIBUNAL etc. foram removidos."""
    import notion_bulk_edit.schemas as schemas_mod
    color_maps = (
        "_COR_TRIBUNAL", "_COR_FASE", "_COR_STATUS_PROC",
        "_COR_INSTANCIA", "_COR_PRIORIDADE", "_COR_STATUS_TAREFA",
        "_COR_CATEGORIA", "_COR_AREA",
    )
    for cmap in color_maps:
        assert not hasattr(schemas_mod, cmap), (
            f"{cmap} ainda em schemas.py"
        )


def test_FASE3_schemas_py_drastically_smaller() -> None:
    """Sanity: schemas.py encolheu drasticamente após remover legado.
    Antes: ~594 linhas. Depois: ~160 linhas."""
    src = _REPO_ROOT / "notion_bulk_edit" / "schemas.py"
    n_lines = len(src.read_text(encoding="utf-8").splitlines())
    assert n_lines < 200, (
        f"schemas.py tem {n_lines} linhas — esperado < 200 após cleanup"
    )


# --- Componente 3: defensive helpers removidos ---


def test_FASE3_legacy_title_keys_by_base_removed() -> None:
    """Helper de fallback _LEGACY_TITLE_KEYS_BY_BASE foi removido."""
    from notion_rpadv.models import base_table_model as bt
    assert not hasattr(bt, "_LEGACY_TITLE_KEYS_BY_BASE")


def test_FASE3_title_value_for_record_helper_removed() -> None:
    """Helper _title_value_for_record foi removido."""
    from notion_rpadv.models import base_table_model as bt
    assert not hasattr(bt, "_title_value_for_record")


def test_FASE3_looks_like_template_row_signature_reverted() -> None:
    """Assinatura de _looks_like_template_row voltou para (record, title_key)
    após cleanup do defensive lookup."""
    import inspect
    from notion_rpadv.models.base_table_model import _looks_like_template_row
    sig = inspect.signature(_looks_like_template_row)
    params = list(sig.parameters.keys())
    assert params == ["record", "title_key"], (
        f"esperado [record, title_key]; obtido {params}"
    )


# --- Componente 4: notion_colors.py + cor_por_valor populado ---


def test_FASE3_notion_colors_module_exists() -> None:
    """Mapeamento Notion → hex em notion_rpadv/theme/notion_colors.py."""
    from notion_rpadv.theme.notion_colors import (
        NOTION_COLOR_TO_HEX,
        color_to_hex,
    )
    # Cores básicas do Notion
    for c in ("default", "blue", "purple", "red", "green"):
        assert c in NOTION_COLOR_TO_HEX
    # Função fallback para cores desconhecidas
    assert color_to_hex("cor_desconhecida_xyz").startswith("#")
    assert color_to_hex("blue") == NOTION_COLOR_TO_HEX["blue"]


def test_FASE3_propspec_includes_cor_por_valor_from_registry() -> None:
    """cor_por_valor é populado em runtime por _dict_to_propspec usando
    notion_colors. Schema dinâmico passa cores reais do Notion."""
    from notion_bulk_edit.schemas import SCHEMAS
    tribunal = SCHEMAS["Processos"]["tribunal"]
    assert tribunal.cor_por_valor, "cor_por_valor vazio"
    # Todas as cores são hex (#RRGGBB)
    for value, hex_color in tribunal.cor_por_valor.items():
        assert hex_color.startswith("#"), f"{value!r} → {hex_color!r}"
        assert len(hex_color) == 7  # #RRGGBB


def test_FASE3_propspec_target_base_resolved_for_relations() -> None:
    """target_base é populado via lookup reverso em DATA_SOURCES.
    Sem isso, _on_table_double_clicked em Processos não navega."""
    from notion_bulk_edit.schemas import SCHEMAS
    clientes = SCHEMAS["Processos"]["clientes"]
    assert clientes.tipo == "relation"
    assert clientes.target_base == "Clientes"


# --- Comportamento global ---


def test_FASE3_4_bases_still_accessible() -> None:
    """SCHEMAS proxy ainda expõe as 4 bases canônicas."""
    from notion_bulk_edit.schemas import SCHEMAS
    assert set(SCHEMAS) == {"Processos", "Clientes", "Tarefas", "Catalogo"}


def test_FASE3_schemas_proxy_simplified() -> None:
    """O método _backing do proxy não tem mais branch condicional para
    flag USE_DYNAMIC_SCHEMA — sempre tenta o registry. Validação por
    inspeção do source (apenas linhas de código, não docstrings/comentários)."""
    src = (_REPO_ROOT / "notion_bulk_edit" / "schemas.py").read_text(
        encoding="utf-8",
    )
    # Lista as linhas e remove docstrings + comentários para checar
    # apenas referências de código ativo.
    code_lines = []
    in_docstring = False
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            # Toggle simples — funciona para docstrings de módulo neste arquivo.
            count = stripped.count('"""') + stripped.count("'''")
            if count % 2 == 1:
                in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)
    # Em código ativo, nenhum dos símbolos legados aparece.
    assert "config.USE_DYNAMIC_SCHEMA" not in code
    assert "config.DYNAMIC_BASES" not in code
    # _LEGACY_SCHEMAS só aparece em comentário "antes virou _LEGACY_SCHEMAS"
    # — não como atribuição/uso. A assertion mais robusta é checar que não
    # há `_LEGACY_SCHEMAS = ` (definição):
    assert "_LEGACY_SCHEMAS = " not in code
    assert "_LEGACY_SCHEMAS:" not in code  # type annotation


def test_FASE3_app_boot_calls_boot_refresh_all_unconditional() -> None:
    """app.py não filtra mais data_sources_to_refresh por DYNAMIC_BASES;
    boot_refresh_all roda com DATA_SOURCES completo."""
    src = (_REPO_ROOT / "notion_rpadv" / "app.py").read_text(encoding="utf-8")
    # Filtro removido
    assert "data_sources_to_refresh" not in src
    assert "if base in bulk_config.DYNAMIC_BASES" not in src
    # boot_refresh_all ainda lá
    assert "boot_refresh_all(" in src
    assert "init_schema_registry(self._audit_conn)" in src
