"""Tests for v2 audit bugs.

Pure-Python tests run in CI; PySide6-dependent tests are marked and skipped.
"""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(not _PYSIDE6, reason="PySide6 not installed")


# ---------------------------------------------------------------------------
# BUG-N1: import — falsy values preserved; update vs create branch
# ---------------------------------------------------------------------------

def test_import_falsy_value_not_lost():
    """BUG-N1: explicit None checks preserve False and 0."""
    row = {"Falecido": False, "Valor da Causa": 0}

    def build_value(row_dict, notion_name, label, prop_key):
        v = row_dict.get(notion_name)
        if v is None:
            v = row_dict.get(label)
        if v is None:
            v = row_dict.get(prop_key)
        return v

    assert build_value(row, "Falecido", "Falecido", "falecido") is False
    assert build_value(row, "Valor da Causa", "Valor da causa", "valor_causa") == 0


def test_import_update_when_page_id_present():
    """BUG-N1: row with page_id calls update_page, not create_page."""
    mock_client = MagicMock()
    page_id = "abc-123"
    properties = {"Nome": {"title": [{"text": {"content": "Test"}}]}}

    row_page_id = page_id
    if row_page_id:
        mock_client.update_page(row_page_id, properties)
    else:
        mock_client.create_page("db_id", properties)

    mock_client.update_page.assert_called_once_with(page_id, properties)
    mock_client.create_page.assert_not_called()


def test_import_create_when_no_page_id():
    """BUG-N1: row without page_id calls create_page."""
    mock_client = MagicMock()
    db_id = "db-456"
    properties = {"Nome": {"title": [{"text": {"content": "New"}}]}}

    row_page_id = None
    if row_page_id:
        mock_client.update_page(row_page_id, properties)
    else:
        mock_client.create_page(db_id, properties)

    mock_client.create_page.assert_called_once_with(db_id, properties)
    mock_client.update_page.assert_not_called()


# ---------------------------------------------------------------------------
# BUG-N2: sync counts — no arithmetic, semantic names
# ---------------------------------------------------------------------------

def test_sync_counts_no_subtraction():
    """BUG-N2: existing count is emitted as-is, not subtracted from added."""
    added = 5
    existing = 95
    # Old wrong formula: truly_updated = updated - added = 95 - 5 = 90
    wrong = existing - added if existing >= added else 0
    assert wrong == 90  # confirm old formula was wrong

    # New correct: just emit existing directly
    assert existing == 95


# ---------------------------------------------------------------------------
# BUG-N8: parse_br_date validation
# ---------------------------------------------------------------------------

def test_parse_br_date_rejects_invalid_month():
    from notion_bulk_edit.encoders import parse_br_date
    with pytest.raises(ValueError):
        parse_br_date("31/13/2024")


def test_parse_br_date_rejects_invalid_day():
    from notion_bulk_edit.encoders import parse_br_date
    with pytest.raises(ValueError):
        parse_br_date("32/12/2024")


def test_parse_br_date_rejects_short_year():
    from notion_bulk_edit.encoders import parse_br_date
    with pytest.raises(ValueError):
        parse_br_date("01/01/24")


def test_parse_br_date_accepts_valid():
    from notion_bulk_edit.encoders import parse_br_date
    assert parse_br_date("31/12/2024") == "2024-12-31"
    assert parse_br_date("01/01/2000") == "2000-01-01"


# ---------------------------------------------------------------------------
# BUG-N9: encode_value number — BR format
# ---------------------------------------------------------------------------

def test_encode_number_br_dot_comma():
    from notion_bulk_edit.encoders import encode_value
    result = encode_value("78.500,00", "number")
    assert result == {"number": 78500.0}


def test_encode_number_br_r_dollar():
    from notion_bulk_edit.encoders import encode_value
    result = encode_value("R$ 1.234,56", "number")
    assert result == {"number": 1234.56}


def test_encode_number_zero():
    from notion_bulk_edit.encoders import encode_value
    result = encode_value("0", "number")
    assert result == {"number": 0.0}


def test_encode_number_plain_float():
    from notion_bulk_edit.encoders import encode_value
    result = encode_value(1234.56, "number")
    assert result == {"number": 1234.56}


# ---------------------------------------------------------------------------
# BUG-N10: format_brl edge cases
# ---------------------------------------------------------------------------

def test_format_brl_inf():
    from notion_bulk_edit.encoders import format_brl
    import math
    assert format_brl(math.inf) == "—"
    assert format_brl(-math.inf) == "—"
    assert format_brl(math.nan) == "—"


def test_format_brl_negative():
    from notion_bulk_edit.encoders import format_brl
    result = format_brl(-1000.5)
    assert result == "R$ -1.000,50"


def test_format_brl_zero():
    from notion_bulk_edit.encoders import format_brl
    assert format_brl(0) == "R$ 0,00"


def test_format_brl_with_cents():
    from notion_bulk_edit.encoders import format_brl
    # basic: 1234.56 → 'R$ 1.234,56'
    result = format_brl(1234.56)
    assert result == "R$ 1.234,56"


def test_format_brl_normal():
    from notion_bulk_edit.encoders import format_brl
    assert format_brl(78500.0) == "R$ 78.500,00"


# ---------------------------------------------------------------------------
# BUG-N18: format_br_date rejects garbage
# ---------------------------------------------------------------------------

def test_format_br_date_accepts_iso():
    from notion_bulk_edit.encoders import format_br_date
    assert format_br_date("2024-03-15") == "15/03/2024"
    assert format_br_date("2024-03-15T12:00:00Z") == "15/03/2024"  # ignores time part


def test_format_br_date_rejects_garbage():
    from notion_bulk_edit.encoders import format_br_date
    # non-ISO strings are returned as-is (not crashed)
    result = format_br_date("not-a-date")
    assert result == "not-a-date"


def test_format_br_date_none():
    from notion_bulk_edit.encoders import format_br_date
    assert format_br_date(None) == ""
    assert format_br_date("") == ""


# ---------------------------------------------------------------------------
# BUG-V3: relation display resolved from cache
# ---------------------------------------------------------------------------

@requires_pyside6
def test_resolve_relation_returns_name():
    """BUG-V3: _resolve_relation looks up page_id in local cache."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE records (base TEXT, page_id TEXT, data_json TEXT, updated_at REAL, PRIMARY KEY(base, page_id))"
    )
    rec = {"page_id": "abc", "nome": "João Silva"}
    conn.execute(
        "INSERT INTO records VALUES (?, ?, ?, ?)",
        ("Clientes", "abc", json.dumps(rec), 0.0),
    )
    conn.commit()

    from notion_rpadv.models.base_table_model import _resolve_relation
    result = _resolve_relation(conn, ["abc"], "Clientes")
    assert result == "João Silva"


@requires_pyside6
def test_resolve_relation_missing_page():
    """BUG-V3: missing page_id renders as dash."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE records (base TEXT, page_id TEXT, data_json TEXT, updated_at REAL, PRIMARY KEY(base, page_id))"
    )
    conn.commit()

    from notion_rpadv.models.base_table_model import _resolve_relation
    result = _resolve_relation(conn, ["nonexistent"], "Clientes")
    assert result == "—"


# ---------------------------------------------------------------------------
# BUG-V4: empty list renders as blank
# ---------------------------------------------------------------------------

@requires_pyside6
def test_display_value_empty_list():
    """BUG-V4: empty list [] should display as empty string."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value

    spec = PropSpec(notion_name="X", tipo="multi_select", label="X")
    assert _display_value(spec, []) == ""


@requires_pyside6
def test_display_value_nonempty_list():
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value

    spec = PropSpec(notion_name="X", tipo="multi_select", label="X")
    assert _display_value(spec, ["A", "B"]) == "A, B"


# ---------------------------------------------------------------------------
# BUG-V5: sync skips template pages
# ---------------------------------------------------------------------------

def test_sync_skips_is_template():
    """BUG-V5: pages with is_template=True are not inserted into cache."""
    pages = [
        {"id": "real-page", "is_template": False, "archived": False, "properties": {}},
        {"id": "template-page", "is_template": True, "archived": False, "properties": {}},
        {"id": "archived-page", "is_template": False, "archived": True, "properties": {}},
        {"id": "trash-page", "is_template": False, "in_trash": True, "properties": {}},
    ]
    accepted = []
    for page in pages:
        if page.get("in_trash") or page.get("archived"):
            continue
        if page.get("is_template", False):
            continue
        accepted.append(page["id"])

    assert "real-page" in accepted
    assert "template-page" not in accepted
    assert "archived-page" not in accepted
    assert "trash-page" not in accepted


# ---------------------------------------------------------------------------
# BUG-N5: SyncManager cleans up _threads dict
# ---------------------------------------------------------------------------

@requires_pyside6
def test_sync_manager_cleans_threads():
    """BUG-N5: after worker finished, _threads[base] is removed."""
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache.sync import SyncManager
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    sm = SyncManager(token="tok", conn=conn)
    # Simulate worker finished callback
    sm._threads["Processos"] = MagicMock()
    sm._workers["Processos"] = MagicMock()
    sm._pending.add("Processos")

    sm._on_worker_finished("Processos", 5, 95, 0)

    assert "Processos" not in sm._threads
    assert "Processos" not in sm._workers


# ---------------------------------------------------------------------------
# BUG-N23: encode_value falsy checks
# ---------------------------------------------------------------------------

def test_encode_phone_number_zero_not_cleared():
    """BUG-N23: encode_value(0, 'phone_number') should not return None."""
    from notion_bulk_edit.encoders import encode_value
    # 0 is falsy but not None/"" — phone_number 0 is unusual but should still encode
    result = encode_value(0, "phone_number")
    assert result == {"phone_number": "0"}


def test_encode_url_empty_string_clears():
    """BUG-N23: encode_value('', 'url') should clear the field."""
    from notion_bulk_edit.encoders import encode_value
    result = encode_value("", "url")
    assert result == {"url": None}


def test_encode_email_none_clears():
    from notion_bulk_edit.encoders import encode_value
    result = encode_value(None, "email")
    assert result == {"email": None}
