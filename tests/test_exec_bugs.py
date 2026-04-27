"""Tests for BUG-EXEC-01 through BUG-EXEC-12.

Pure-Python tests run in CI; PySide6-dependent tests are marked and skipped.
"""
from __future__ import annotations

import json
import re
import sqlite3
import pytest

try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(not _PYSIDE6, reason="PySide6 not installed")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# BUG-EXEC-01: get_dirty_edits() returns dicts compatible with CommitWorker
# ---------------------------------------------------------------------------

@requires_pyside6
def test_get_dirty_edits_returns_dicts():
    """BUG-EXEC-01: get_dirty_edits() must return list[dict] not list[tuple]."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE records (base TEXT, page_id TEXT, data_json TEXT, updated_at REAL, "
        "PRIMARY KEY(base, page_id))"
    )
    rec = {"page_id": "pg-1", "nome": "Teste", "status": "Ativo"}
    conn.execute(
        "INSERT INTO records VALUES (?, ?, ?, ?)",
        ("Clientes", "pg-1", json.dumps(rec), 0.0),
    )
    conn.commit()

    from notion_rpadv.models.base_table_model import BaseTableModel
    model = BaseTableModel("Clientes", conn)

    # Simulate a dirty edit by calling setData
    idx = model.index(0, 0)
    if idx.isValid():
        model._dirty[("pg-1", "status")] = "Inativo"

    edits = model.get_dirty_edits()
    assert isinstance(edits, list)
    assert len(edits) == 1
    edit = edits[0]
    assert isinstance(edit, dict), f"Expected dict, got {type(edit)}"
    assert "base" in edit
    assert "page_id" in edit
    assert "key" in edit
    assert "new_value" in edit
    assert "old_value" in edit
    assert edit["page_id"] == "pg-1"
    assert edit["key"] == "status"
    assert edit["new_value"] == "Inativo"


@requires_pyside6
def test_get_dirty_edits_commit_worker_compatible():
    """BUG-EXEC-01: CommitWorker.run() can call edit.get(...) without AttributeError."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE records (base TEXT, page_id TEXT, data_json TEXT, updated_at REAL, "
        "PRIMARY KEY(base, page_id))"
    )
    rec = {"page_id": "pg-2", "nome": "Foo"}
    conn.execute(
        "INSERT INTO records VALUES (?, ?, ?, ?)",
        ("Clientes", "pg-2", json.dumps(rec), 0.0),
    )
    conn.commit()

    from notion_rpadv.models.base_table_model import BaseTableModel
    model = BaseTableModel("Clientes", conn)
    model._dirty[("pg-2", "nome")] = "Bar"

    edits = model.get_dirty_edits()
    for edit in edits:
        # This is what CommitWorker does — would crash with AttributeError on tuple
        page_id = edit.get("page_id", "")
        key = edit.get("key", "")
        new_value = edit.get("new_value")
        edit_id = int(edit.get("id", 0))
        assert page_id == "pg-2"
        assert key == "nome"
        assert new_value == "Bar"
        assert edit_id == 0


# ---------------------------------------------------------------------------
# BUG-EXEC-02: NOTION_USERS keys must be real UUID format
# ---------------------------------------------------------------------------

def test_notion_users_known_keys_are_uuids():
    """BUG-EXEC-02: Déborah, Leonardo, Ricardo keys must be real UUID format."""
    from notion_bulk_edit.config import NOTION_USERS

    known_names = {"Déborah", "Leonardo", "Ricardo"}
    for uid, data in NOTION_USERS.items():
        if data.get("name") in known_names:
            assert _UUID_RE.match(uid), (
                f"NOTION_USERS key for {data['name']} is not a UUID: {uid!r}"
            )


def test_notion_users_deborah_uuid():
    from notion_bulk_edit.config import NOTION_USERS
    assert "23fd872b-594c-8178-840c-00029746e827" in NOTION_USERS


def test_notion_users_leonardo_uuid():
    from notion_bulk_edit.config import NOTION_USERS
    assert "240d872b-594c-81f4-82e1-000212a926fc" in NOTION_USERS


def test_notion_users_ricardo_uuid():
    from notion_bulk_edit.config import NOTION_USERS
    assert "23fd872b-594c-814a-b7b8-00025b13b424" in NOTION_USERS


# ---------------------------------------------------------------------------
# BUG-EXEC-03: DashboardPage has refresh(), not reload()
# ---------------------------------------------------------------------------

@requires_pyside6
def test_dashboard_has_refresh_not_only_reload():
    """BUG-EXEC-03: DashboardPage must expose refresh() method."""
    from notion_rpadv.pages.dashboard import DashboardPage
    assert hasattr(DashboardPage, "refresh"), "DashboardPage missing refresh()"


# ---------------------------------------------------------------------------
# BUG-EXEC-04: shortcut persistence round-trip
# ---------------------------------------------------------------------------

def test_shortcuts_persist_round_trip(tmp_path, monkeypatch):
    """BUG-EXEC-04: save_user_shortcuts() / load_user_shortcuts() round-trip."""
    import notion_rpadv.services.shortcuts_store as sc_mod

    monkeypatch.setattr(
        sc_mod, "_shortcuts_file", lambda: tmp_path / "shortcuts.json"
    )

    bindings = {"search": "Ctrl+P", "save": "Ctrl+Shift+S"}
    sc_mod.save_user_shortcuts(bindings)

    loaded = sc_mod.load_user_shortcuts()
    assert loaded["search"] == "Ctrl+P"
    assert loaded["save"] == "Ctrl+Shift+S"
    # Other defaults preserved
    assert "refresh" in loaded


def test_load_shortcuts_falls_back_to_defaults(tmp_path, monkeypatch):
    """BUG-EXEC-04: load_user_shortcuts() returns defaults when file missing."""
    import notion_rpadv.services.shortcuts_store as sc_mod
    from notion_rpadv.services.shortcuts_store import DEFAULT_SHORTCUTS

    monkeypatch.setattr(
        sc_mod, "_shortcuts_file", lambda: tmp_path / "nonexistent.json"
    )
    loaded = sc_mod.load_user_shortcuts()
    assert loaded == DEFAULT_SHORTCUTS


def test_load_shortcuts_ignores_corrupt_file(tmp_path, monkeypatch):
    """BUG-EXEC-04: corrupt JSON falls back to defaults silently."""
    import notion_rpadv.services.shortcuts_store as sc_mod
    from notion_rpadv.services.shortcuts_store import DEFAULT_SHORTCUTS

    bad_file = tmp_path / "shortcuts.json"
    bad_file.write_text("not valid json", encoding="utf-8")
    monkeypatch.setattr(sc_mod, "_shortcuts_file", lambda: bad_file)

    loaded = sc_mod.load_user_shortcuts()
    assert loaded == DEFAULT_SHORTCUTS


# ---------------------------------------------------------------------------
# BUG-EXEC-06: search placeholder must not use Mac glyph
# ---------------------------------------------------------------------------

def test_no_mac_glyph_in_search_placeholder():
    """BUG-EXEC-06: search box placeholder uses Ctrl+K not ⌘K."""
    import pathlib
    src = pathlib.Path("/home/claude/repo/notion_rpadv/pages/base_table_page.py").read_text()
    assert "⌘K" not in src, "Mac-specific ⌘K glyph found in base_table_page.py"
    assert "Ctrl+K" in src or "Pesquisar" in src


# ---------------------------------------------------------------------------
# BUG-EXEC-08: rollup array display
# ---------------------------------------------------------------------------

@requires_pyside6
def test_display_value_rollup_list():
    """BUG-EXEC-08: rollup with list value renders as comma-joined string."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value

    spec = PropSpec(notion_name="X", tipo="rollup", label="X")
    result = _display_value(spec, ["Alpha", "Beta", "Gamma"])
    assert result == "Alpha, Beta, Gamma"


@requires_pyside6
def test_display_value_rollup_empty_list():
    """BUG-EXEC-08: rollup with empty list renders as empty string."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value

    spec = PropSpec(notion_name="X", tipo="rollup", label="X")
    assert _display_value(spec, []) == ""


@requires_pyside6
def test_display_value_generic_list():
    """BUG-EXEC-08: any unknown tipo with list renders as comma-joined, not repr."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value

    spec = PropSpec(notion_name="X", tipo="formula", label="X")
    result = _display_value(spec, ["A", "B"])
    assert result == "A, B"
    assert "[" not in result  # must not contain Python list repr brackets


# ---------------------------------------------------------------------------
# BUG-EXEC-09: invalidateRowsFilter() usage
# ---------------------------------------------------------------------------

def test_filters_use_invalidate_rows_filter():
    """BUG-EXEC-09: filters.py must not call invalidateFilter() (deprecated)."""
    import pathlib
    src = pathlib.Path("/home/claude/repo/notion_rpadv/models/filters.py").read_text()
    # Must NOT use bare invalidateFilter()
    # invalidateRowsFilter is the correct PySide6 6.x API
    assert "invalidateFilter()" not in src, (
        "filters.py still calls deprecated invalidateFilter()"
    )
    assert "invalidateRowsFilter()" in src


# ---------------------------------------------------------------------------
# BUG-EXEC-11: no _BACKDROP_COLOR dead code in modal.py
# ---------------------------------------------------------------------------

def test_modal_no_backdrop_color_dead_code():
    """BUG-EXEC-11: _BACKDROP_COLOR variable must be removed from modal.py."""
    import pathlib
    src = pathlib.Path("/home/claude/repo/notion_rpadv/widgets/modal.py").read_text()
    assert "_BACKDROP_COLOR" not in src, (
        "_BACKDROP_COLOR dead variable still present in modal.py"
    )
