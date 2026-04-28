"""Tests for all 8 critical bugs in the Notion RPADV audit.

BUG-01: encode_value arg order
BUG-02: is_nao_editavel arity (flags)
BUG-03: flags() obrigatorio logic
BUG-04: _do_import actually calls Notion API
BUG-05: _all_rows vs _rows (full dataset vs preview)
BUG-06: filter handler body was pass (no-op)
BUG-07: commit_finished signal carries base, clear_dirty only for own base
BUG-08: config.py misleading comment + pathlib import order
"""
from __future__ import annotations

import ast
import pathlib
import sqlite3
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Marker for tests that require PySide6
try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(not _PYSIDE6, reason="PySide6 not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn() -> sqlite3.Connection:
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cache_db.init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# BUG-01: encode_value argument order — pure Python, no PySide6
# ---------------------------------------------------------------------------

class TestBug01EncodeValueArgOrder:
    def test_encode_select(self) -> None:
        from notion_bulk_edit.encoders import encode_value
        assert encode_value("Ativo", "select") == {"select": {"name": "Ativo"}}

    def test_encode_number(self) -> None:
        from notion_bulk_edit.encoders import encode_value
        assert encode_value(42.0, "number") == {"number": 42.0}

    def test_encode_checkbox(self) -> None:
        from notion_bulk_edit.encoders import encode_value
        assert encode_value(True, "checkbox") == {"checkbox": True}

    def test_encode_title(self) -> None:
        from notion_bulk_edit.encoders import encode_value
        r = encode_value("Hello", "title")
        assert "title" in r and r["title"][0]["text"]["content"] == "Hello"

    def test_encode_date(self) -> None:
        from notion_bulk_edit.encoders import encode_value
        r = encode_value("2026-04-27", "date")
        assert r["date"]["start"] == "2026-04-27"

    @requires_pyside6
    def test_commit_worker_sends_select_payload(self) -> None:
        from notion_rpadv.services.notion_facade import CommitWorker
        conn = _make_conn()
        edits = [{
            "id": 0, "base": "Processos", "page_id": "page-abc",
            "key": "status", "old_value": "Ativo", "new_value": "Arquivado",
        }]
        mock_client = MagicMock()
        mock_client.update_page.return_value = {}
        with patch("notion_rpadv.services.notion_facade.NotionClient", return_value=mock_client):
            CommitWorker("t", conn, edits, "deborah", "Processos").run()
        assert mock_client.update_page.called
        props = mock_client.update_page.call_args[0][1]
        assert "select" in props.get("Status", {}), f"Wrong payload: {props}"


# ---------------------------------------------------------------------------
# BUG-02 + BUG-03: is_nao_editavel + flags() — mixed
# ---------------------------------------------------------------------------

class TestBug02Bug03Flags:
    def test_is_nao_editavel_two_args(self) -> None:
        from notion_bulk_edit.schemas import is_nao_editavel
        assert is_nao_editavel("Processos", "status") is False

    def test_rollup_not_editable(self) -> None:
        from notion_bulk_edit.schemas import is_nao_editavel
        assert is_nao_editavel("Tarefas", "cliente") is True

    def test_single_arg_raises_typeerror(self) -> None:
        from notion_bulk_edit.schemas import is_nao_editavel
        with pytest.raises(TypeError):
            is_nao_editavel("status")  # type: ignore[call-arg]

    def test_obrigatorio_field_still_editable(self) -> None:
        """BUG-03: obrigatorio=True must not block editing."""
        from notion_bulk_edit.schemas import SCHEMAS, is_nao_editavel
        for key, spec in SCHEMAS.get("Processos", {}).items():
            if spec.obrigatorio and spec.editavel:
                assert not is_nao_editavel("Processos", key), (
                    f"'{key}' is obrigatorio+editavel but is_nao_editavel()=True — BUG-03"
                )

    @requires_pyside6
    def test_model_flags_editable_col(self) -> None:
        from PySide6.QtCore import Qt
        from notion_rpadv.models.base_table_model import BaseTableModel
        conn = _make_conn()
        model = BaseTableModel("Processos", conn)
        model._rows = [{"page_id": "p1", "status": "Ativo", "cnj": "123", "tribunal": "TJDFT",
                        "instancia": "1ª", "fase": "Conhecimento", "cliente": None,
                        "parte_contraria": None, "distribuicao": None, "valor_causa": None,
                        "responsavel": None, "tema955": False, "sobrestado_tj": False,
                        "sobrestado_irr": False}]
        try:
            col = model._cols.index("status")
        except ValueError:
            pytest.skip("status not visible")
        flags = model.flags(model.index(0, col))
        assert bool(flags & Qt.ItemFlag.ItemIsEditable), "status must be editable"

    @requires_pyside6
    def test_model_flags_rollup_not_editable(self) -> None:
        from PySide6.QtCore import Qt
        from notion_rpadv.models.base_table_model import BaseTableModel
        conn = _make_conn()
        model = BaseTableModel("Clientes", conn)
        model._rows = [{"page_id": "p1", "nome": "X", "cpf": "111", "email": None,
                        "telefone": None, "falecido": False, "cidade": None,
                        "cadastrado": None, "n_processos": None, "notas": None}]
        try:
            col = model._cols.index("n_processos")
        except ValueError:
            pytest.skip("n_processos not visible")
        flags = model.flags(model.index(0, col))
        assert not bool(flags & Qt.ItemFlag.ItemIsEditable), "n_processos (rollup) must NOT be editable"


# ---------------------------------------------------------------------------
# BUG-04 + BUG-05: importar.py — requires PySide6
# ---------------------------------------------------------------------------

class TestBug04Bug05Importar:
    @requires_pyside6
    def test_all_rows_populated_beyond_preview(self) -> None:
        import io
        import os
        import tempfile
        try:
            import openpyxl
        except ImportError:
            pytest.skip("openpyxl not installed")
        from notion_rpadv.pages.importar import _Step2Widget, _MAX_PREVIEW_ROWS
        from notion_rpadv.theme.tokens import LIGHT
        import sys
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication(sys.argv)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Tarefa", "Prazo fatal", "Status"])
        for i in range(25):
            ws.append([f"Tarefa {i}", "2026-01-01", "A fazer"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(buf.read())
            tmp = f.name
        try:
            w = _Step2Widget(LIGHT)
            w.load_file("Tarefas", tmp)
            assert len(w._rows) == _MAX_PREVIEW_ROWS, f"preview={len(w._rows)}"
            assert len(w._all_rows) == 25, f"all_rows={len(getattr(w, '_all_rows', []))}"
        finally:
            os.unlink(tmp)

    @requires_pyside6
    def test_do_import_calls_create_page(self) -> None:
        from notion_rpadv.pages.importar import ImportarPage
        import sys
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication(sys.argv)

        conn = _make_conn()
        page = ImportarPage(conn=conn, token="secret_test", user="deborah")
        page._step2._all_rows = [
            {"Tarefa": "X", "Prazo fatal": "2026-01-15", "Status": "A fazer"},
        ]
        page._step2._rows = page._step2._all_rows[:]

        mock_client = MagicMock()
        mock_client.create_page.return_value = {"id": "new"}
        with patch("notion_bulk_edit.notion_api.NotionClient", return_value=mock_client):
            page._do_import()

        assert mock_client.create_page.called, "create_page was never called — BUG-04"


# ---------------------------------------------------------------------------
# BUG-06: filter proxy — requires PySide6
# ---------------------------------------------------------------------------

class TestBug06FilterProxy:
    @requires_pyside6
    def test_set_col_filter_restricts_values(self) -> None:
        from notion_rpadv.models.filters import TableFilterProxy
        from notion_rpadv.models.base_table_model import BaseTableModel
        from notion_bulk_edit.schemas import SCHEMAS
        import sys
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication(sys.argv)

        conn = _make_conn()
        model = BaseTableModel("Processos", conn)
        proxy = TableFilterProxy()
        proxy.setSourceModel(model)

        try:
            col = model._cols.index("status")
        except ValueError:
            pytest.skip("status not visible")

        all_opts = set(SCHEMAS["Processos"]["status"].opcoes)
        subset = all_opts - {"Ativo"}
        proxy.set_col_filter(col, subset)
        assert proxy.get_active_col_filter(col) == subset

        proxy.set_col_filter(col, None)
        assert proxy.get_active_col_filter(col) is None


# ---------------------------------------------------------------------------
# BUG-07: commit_finished carries base — requires PySide6
# ---------------------------------------------------------------------------

class TestBug07CommitBase:
    @requires_pyside6
    def test_commit_worker_emits_base(self) -> None:
        from notion_rpadv.services.notion_facade import CommitWorker
        conn = _make_conn()
        worker = CommitWorker("token", conn, [], "deborah", "Processos")
        emitted: list[Any] = []
        # BUG-OP-03: signal shape is (base, results: list[dict]).
        worker.finished.connect(lambda b, results: emitted.append((b, results)))
        worker.run()
        assert len(emitted) == 1
        assert emitted[0][0] == "Processos", f"base should be 'Processos', got '{emitted[0][0]}'"
        # Empty edits → empty results list, but base still propagates.
        assert emitted[0][1] == []

    @requires_pyside6
    def test_clear_dirty_scoped_to_base(self) -> None:
        from notion_rpadv.pages.base_table_page import BaseTablePage
        from notion_rpadv.services.notion_facade import NotionFacade
        from notion_rpadv.cache.sync import SyncManager
        import sys
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication(sys.argv)

        conn = _make_conn()
        facade = NotionFacade("token", conn)
        sync = SyncManager("token", conn)
        page = BaseTablePage("Processos", conn, "token", "deborah", facade, sync)
        page._model._dirty = {("p1", "status"): "Ativo"}

        # BUG-OP-03: new signal shape (base, results) with per-cell dicts.
        success_result = [{
            "page_id": "p1", "key": "status", "edit_id": 0,
            "ok": True, "error": None,
        }]

        # Wrong base — must NOT clear
        page._on_commit_finished("Clientes", success_result)
        assert bool(page._model._dirty), "dirty cleared for wrong base — BUG-07"

        # Own base — must clear (success entry → cell goes clean)
        page._on_commit_finished("Processos", success_result)
        assert not bool(page._model._dirty), "dirty not cleared after own base commit"


# ---------------------------------------------------------------------------
# BUG-08: config.py pathlib at module top + comment — pure Python
# ---------------------------------------------------------------------------

class TestBug08Config:
    def test_pathlib_at_top(self) -> None:
        cfg = pathlib.Path(__file__).parent.parent / "notion_bulk_edit" / "config.py"
        tree = ast.parse(cfg.read_text())
        lines = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == "pathlib":
                        lines.append(node.lineno)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "pathlib":
                    lines.append(node.lineno)
        assert lines, "pathlib not imported at top level"
        assert min(lines) <= 15, f"pathlib import at line {min(lines)}, expected ≤ 15"

    def test_comment_clarifies_data_source(self) -> None:
        cfg = pathlib.Path(__file__).parent.parent / "notion_bulk_edit" / "config.py"
        assert "data_source" in cfg.read_text().lower()
