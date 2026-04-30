"""Round 4 (29-abr-2026) — tests for editorial column layout + reset migration.

Cobre:
- ``notion_rpadv.layout_defaults`` (DEFAULT_LAYOUTS, helpers)
- ``cache_db.wipe_user_columns_if_layout_changed`` (migração one-shot)
- ``schema_registry.colunas_visiveis`` consumindo o layout editorial
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from notion_rpadv.cache import db as cache_db


_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "schemas"


def _audit_only_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_audit_db(conn)
    return conn


def _load_fixture(base: str) -> dict:
    path = _FIXTURES_DIR / f"{base.lower()}_raw.json"
    if not path.exists():
        pytest.skip(f"fixture ausente: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# layout_defaults: DEFAULT_LAYOUTS, default_visible_slugs, default_width
# ---------------------------------------------------------------------------


def test_R4_default_visible_slugs_clientes_in_spec_order() -> None:
    """Clientes: 7 slugs na ordem do spec do Round 4."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    assert default_visible_slugs("Clientes") == [
        "nome", "telefone", "processos", "e_mail",
        "data_de_aposentadoria", "data_de_ingresso_no_bb",
        "situacao_funcional",
    ]


def test_R4_default_visible_slugs_processos_in_spec_order() -> None:
    """Processos: 7 slugs na ordem do spec."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    assert default_visible_slugs("Processos") == [
        "numero_do_processo", "clientes", "fase",
        "tipo_de_processo", "tipo_de_acao", "instancia",
        "detalhamento_da_acao",
    ]


def test_R4_default_visible_slugs_tarefas_includes_round_4_props() -> None:
    """Tarefas: 10 slugs incluindo area e prioridade (props novas)."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    cols = default_visible_slugs("Tarefas")
    assert cols == [
        "tarefa", "tipo_de_tarefa", "cliente", "processo",
        "status", "area", "prioridade",
        "data_de_publicacao", "prazo_fatal", "responsavel",
    ]


def test_R4_default_visible_slugs_catalogo_includes_observacoes() -> None:
    """Catalogo: 3 slugs incluindo observacoes (rich_text editorialmente
    visível, contrariando a heurística antiga de esconder rich_text)."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    assert default_visible_slugs("Catalogo") == [
        "nome", "categoria", "observacoes",
    ]


def test_R4_default_visible_slugs_unknown_base_returns_empty() -> None:
    """Base não coberta pelo layout → lista vazia (caller cai no fallback)."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    assert default_visible_slugs("Inexistente") == []


def test_R4_default_width_returns_layout_value() -> None:
    """Slug conhecido retorna width do layout."""
    from notion_rpadv.layout_defaults import default_width
    assert default_width("Clientes", "nome") == 280
    assert default_width("Tarefas", "tarefa") == 280
    assert default_width("Tarefas", "responsavel") == 160
    assert default_width("Catalogo", "categoria") == 220


def test_R4_default_width_returns_none_for_unknown_slug() -> None:
    """Slug não no layout → None (caller usa piso de font metrics)."""
    from notion_rpadv.layout_defaults import default_width
    assert default_width("Clientes", "slug_qualquer") is None
    assert default_width("Inexistente", "nome") is None


def test_R4_default_layouts_widths_are_positive_ints() -> None:
    """Sanity: nenhuma largura negativa ou zero (quebraria QHeaderView)."""
    from notion_rpadv.layout_defaults import DEFAULT_LAYOUTS
    for base, items in DEFAULT_LAYOUTS.items():
        for slug, width in items:
            assert isinstance(width, int), f"{base}.{slug}: width não é int"
            assert width > 0, f"{base}.{slug}: width <= 0"


def test_R4_default_layouts_no_duplicate_slugs_per_base() -> None:
    """Sanity: cada slug aparece no máximo uma vez por base."""
    from notion_rpadv.layout_defaults import DEFAULT_LAYOUTS
    for base, items in DEFAULT_LAYOUTS.items():
        slugs = [s for s, _w in items]
        assert len(slugs) == len(set(slugs)), f"slug duplicado em {base}"


# ---------------------------------------------------------------------------
# wipe_user_columns_if_layout_changed
# ---------------------------------------------------------------------------


def test_R4_wipe_first_boot_with_no_version_meta_sets_version() -> None:
    """Sem meta.layout_version → wipe (vazio, retorna 0) + grava versão."""
    conn = _audit_only_conn()
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    assert deleted == 0  # nada pra apagar, mas grava versão
    row = conn.execute(
        "SELECT value FROM meta WHERE key='layout_version'",
    ).fetchone()
    assert row is not None
    assert row["value"] == "1"


def test_R4_wipe_first_boot_with_existing_prefs_wipes_them() -> None:
    """Sem meta.layout_version mas com prefs salvas → wipe efetivo."""
    conn = _audit_only_conn()
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a", "b"])
    cache_db.set_user_columns(conn, "deborah", "dsid-2", ["x"])
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    assert deleted == 2
    # prefs sumiram
    assert cache_db.get_user_columns(conn, "leo", "dsid-1") is None
    assert cache_db.get_user_columns(conn, "deborah", "dsid-2") is None


def test_R4_wipe_skips_when_version_matches() -> None:
    """Já estava na versão atual → no-op (retorna 0, prefs preservadas)."""
    conn = _audit_only_conn()
    cache_db.wipe_user_columns_if_layout_changed(conn, 1)  # primeiro boot
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a", "b"])
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    assert deleted == 0
    # prefs intactas
    assert cache_db.get_user_columns(conn, "leo", "dsid-1") == ["a", "b"]


def test_R4_wipe_runs_when_current_version_higher() -> None:
    """Versão armazenada < current → wipe + bump."""
    conn = _audit_only_conn()
    cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a"])
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 2)
    assert deleted == 1
    row = conn.execute(
        "SELECT value FROM meta WHERE key='layout_version'",
    ).fetchone()
    assert row["value"] == "2"


def test_R4_wipe_skips_when_current_version_lower() -> None:
    """Versão armazenada > current (downgrade) → no-op por segurança."""
    conn = _audit_only_conn()
    cache_db.wipe_user_columns_if_layout_changed(conn, 5)
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a"])
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 3)
    assert deleted == 0
    assert cache_db.get_user_columns(conn, "leo", "dsid-1") == ["a"]


def test_R4_wipe_handles_corrupted_version_value() -> None:
    """meta.layout_version corrompido (não-int) → trata como ausente, faz wipe."""
    conn = _audit_only_conn()
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('layout_version', 'corrupted')",
    )
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a"])
    conn.commit()
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    assert deleted == 1


# ---------------------------------------------------------------------------
# schema_registry.colunas_visiveis using layout
# ---------------------------------------------------------------------------


def test_R4_colunas_visiveis_uses_editorial_layout_for_catalogo() -> None:
    """Sem user_id, base conhecida → retorna ordem do layout editorial."""
    if not (_FIXTURES_DIR / "catalogo_raw.json").exists():
        pytest.skip("fixture catalogo_raw.json ausente")
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    raw = _load_fixture("Catalogo")
    mock_client = MagicMock()
    mock_client.get_data_source.return_value = raw
    reg.refresh_from_api("Catalogo", raw["id"], mock_client)
    cols = reg.colunas_visiveis("Catalogo")
    assert cols == ["nome", "categoria", "observacoes"]


def test_R4_colunas_visiveis_filters_layout_slugs_not_in_schema() -> None:
    """Layout pode ter slug que ainda não chegou no schema (refresh
    pendente). Filtra silenciosamente em vez de retornar header sem PropSpec."""
    if not (_FIXTURES_DIR / "tarefas_raw.json").exists():
        pytest.skip("fixture tarefas_raw.json ausente")
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    raw = _load_fixture("Tarefas")
    mock_client = MagicMock()
    mock_client.get_data_source.return_value = raw
    reg.refresh_from_api("Tarefas", raw["id"], mock_client)
    cols = reg.colunas_visiveis("Tarefas")
    # area/prioridade não estão na fixture (props novas do Round 4); o
    # layout as inclui mas elas ficam filtradas até refresh pegar o schema novo.
    schema_keys = set(reg.schema_for_base("Tarefas").keys())
    for slug in cols:
        assert slug in schema_keys, f"slug {slug!r} retornado mas ausente do schema"


def test_R4_colunas_visiveis_falls_back_to_heuristic_for_unknown_base() -> None:
    """Base sem entry em DEFAULT_LAYOUTS → cai na heurística do schema_parser
    (default_visible=True ordenados por default_order). Garante que adicionar
    bases novas sem layout editorial não quebra o app."""
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    # Schema sintético com 3 props: title (default_visible) + select (default_visible)
    # + rich_text (default_visible=False).
    synthetic_schema = {
        "data_source_id": "dsid-syn",
        "base_label": "BaseSemLayout",
        "title_property": "Nome",
        "title_key": "nome",
        "properties": {
            "nome": {
                "notion_name": "Nome", "tipo": "title", "label": "Nome",
                "editavel": True, "obrigatorio": True, "opcoes": [],
                "default_visible": True, "default_order": 1,
                "target_data_source_id": "",
            },
            "tipo": {
                "notion_name": "Tipo", "tipo": "select", "label": "Tipo",
                "editavel": True, "obrigatorio": False, "opcoes": [],
                "default_visible": True, "default_order": 2,
                "target_data_source_id": "",
            },
            "notas": {
                "notion_name": "Notas", "tipo": "rich_text", "label": "Notas",
                "editavel": True, "obrigatorio": False, "opcoes": [],
                "default_visible": False, "default_order": 3,
                "target_data_source_id": "",
            },
        },
    }
    reg._schemas["BaseSemLayout"] = synthetic_schema  # noqa: SLF001
    reg._base_to_dsid["BaseSemLayout"] = "dsid-syn"  # noqa: SLF001
    cols = reg.colunas_visiveis("BaseSemLayout")
    assert cols == ["nome", "tipo"]  # heurística mantém: rich_text fora
