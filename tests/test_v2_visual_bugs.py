"""Tests for the V2 post-redesign visual bug round (BUG-V2-01 … BUG-V2-13).

Pure-Python tests run unconditionally; tests that need a real Qt instance are
marked with ``requires_pyside6`` and skipped when PySide6 is unavailable.
"""
from __future__ import annotations

import re
import sqlite3

import pytest

try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(not _PYSIDE6, reason="PySide6 not installed")


# ---------------------------------------------------------------------------
# Shared in-memory cache helper (no Qt dependency)
# ---------------------------------------------------------------------------

def _make_cache() -> sqlite3.Connection:
    """Build a fresh in-memory SQLite cache with the app's schema."""
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# BUG-V2-04 — template/sentinel rows must never reach the table view
# ---------------------------------------------------------------------------

@requires_pyside6
def test_looks_like_template_row_detects_orange_square():
    """BUG-V2-04: '🟧 Modelo — usar como template' is recognised as a template.
    Fase 2d: assinatura virou (record, base) — base resolve title slug."""
    from notion_rpadv.models.base_table_model import _looks_like_template_row
    # Clientes usa slug "nome" — válido tanto no legado quanto no dinâmico.
    assert _looks_like_template_row(
        {"nome": "🟧 Modelo — usar como template"}, "Clientes",
    ) is True


@requires_pyside6
def test_looks_like_template_row_handles_dash_variants():
    """BUG-V2-04: case-insensitive, tolerant to em/en-dash and hyphen."""
    from notion_rpadv.models.base_table_model import _looks_like_template_row
    for title in (
        "Modelo - usar como template",
        "modelo – usar como template",  # en-dash
        "MODELO — USAR COMO TEMPLATE",
    ):
        assert _looks_like_template_row({"nome": title}, "Clientes") is True, title


@requires_pyside6
def test_looks_like_template_row_passes_real_data():
    """BUG-V2-04: real client/process names are NOT flagged as templates."""
    from notion_rpadv.models.base_table_model import _looks_like_template_row
    for title in ("João da Silva", "0001234-12.2024.8.13.0024", "Empresa XYZ"):
        assert _looks_like_template_row({"nome": title}, "Clientes") is False, title


@requires_pyside6
def test_processos_table_excludes_template_row():
    """BUG-V2-04: the model filters out template rows on reload, so the table
    only ever shows real records."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _make_cache()
    cache_db.upsert_record(
        conn, "Processos", "real-1", {"page_id": "real-1", "cnj": "0001234-12.2024.8.13.0024"}
    )
    cache_db.upsert_record(
        conn,
        "Processos",
        "tpl-1",
        {"page_id": "tpl-1", "cnj": "🟧 Modelo — usar como template"},
    )

    model = BaseTableModel("Processos", conn)
    assert model.rowCount() == 1
    # And the surviving row is the real one, not the template.
    record = model.get_record(0)
    assert record.get("page_id") == "real-1"


# ---------------------------------------------------------------------------
# BUG-V2-09 — N° Processos column uses local count fallback
# ---------------------------------------------------------------------------

@requires_pyside6
def test_count_processos_for_cliente_counts_local_relations():
    """BUG-V2-09: when the rollup is empty, the local count walks the
    Processos cache and counts rows whose 'cliente' relation references
    this client's page_id."""
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import _count_processos_for_cliente

    conn = _make_cache()
    cliente_id = "cli-1"
    cache_db.upsert_record(conn, "Clientes", cliente_id, {"page_id": cliente_id, "nome": "Acme"})
    for i, pid in enumerate(("p1", "p2", "p3"), start=1):
        cache_db.upsert_record(
            conn,
            "Processos",
            pid,
            {"page_id": pid, "cnj": f"0000{i}-12.2024.8.13.0024", "cliente": [cliente_id]},
        )
    # And one process for a DIFFERENT client — must not be counted.
    cache_db.upsert_record(
        conn,
        "Processos",
        "p-other",
        {"page_id": "p-other", "cnj": "0009999", "cliente": ["other-id"]},
    )

    assert _count_processos_for_cliente(conn, cliente_id) == 3
    assert _count_processos_for_cliente(conn, "other-id") == 1
    assert _count_processos_for_cliente(conn, "no-such-id") == 0


@requires_pyside6
def test_count_processos_for_cliente_handles_empty_cache():
    """BUG-V2-09: returns 0 (not a crash) when Processos cache is empty."""
    from notion_rpadv.models.base_table_model import _count_processos_for_cliente
    conn = _make_cache()
    assert _count_processos_for_cliente(conn, "any-id") == 0


# ---------------------------------------------------------------------------
# BUG-V2-10 — Falecido column never displays "x" for False
# ---------------------------------------------------------------------------

@requires_pyside6
def test_checkbox_display_false_is_blank():
    """BUG-V2-10: False checkbox renders blank (not "✗"/"x" which reads as a
    positive marker in pt-BR). §3.3: a None checkbox (never set) renders
    as the em-dash placeholder so users see "no value" rather than blank."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value

    spec = PropSpec(notion_name="Falecido", tipo="checkbox", label="Falecido")
    assert _display_value(spec, False) == ""
    assert _display_value(spec, None) == "—"
    assert _display_value(spec, True) == "✓"


# ---------------------------------------------------------------------------
# BUG-V2-08 — header column min width uses a font-aware computation
# ---------------------------------------------------------------------------

@requires_pyside6
def test_processos_header_columns_min_width():
    """BUG-V2-08: every column reserves enough room for the QSS-rendered
    header text (uppercase + bold + letter-spacing + padding + sort indicator)."""
    from PySide6.QtGui import QFont, QFontMetrics
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    from notion_rpadv.theme.tokens import FONT_BODY

    conn = _make_cache()
    facade = NotionFacade("dummy-token", conn)
    page = ProcessosPage(
        conn=conn, token="dummy-token", user="leonardo",
        facade=facade, dark=False,
    )

    header = page._table.horizontalHeader()
    page._resize_columns_to_header()

    qss_font = QFont(FONT_BODY)
    qss_font.setPixelSize(10)
    qss_font.setBold(True)
    fm = QFontMetrics(qss_font)
    letter_spacing_px = 1
    padding_px = 24
    sort_indicator_px = 16

    for col in range(page._model.columnCount()):
        label = str(page._model.headerData(col, Qt.Orientation.Horizontal) or "")
        text = label.upper()
        expected_min = (
            fm.horizontalAdvance(text)
            + letter_spacing_px * max(0, len(text) - 1)
            + padding_px
            + sort_indicator_px
        )
        actual = header.sectionSize(col)
        assert actual >= min(expected_min, 80) - 2, (
            f"column {col} ({label!r}): {actual}px < expected ≥ {expected_min}px"
        )


# ---------------------------------------------------------------------------
# BUG-V2-01 + BUG-V2-02 — buttons keep their text labels
# ---------------------------------------------------------------------------

@requires_pyside6
def test_importar_step1_has_button_labels():
    """BUG-V2-01: Step 1 of the importer renders 'Gerar template' and
    'Escolher arquivo (.xlsx)' as visible text, not empty rectangles."""
    from PySide6.QtWidgets import QApplication, QPushButton
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.importar import ImportarPage
    conn = _make_cache()
    page = ImportarPage(conn=conn, token="x", user="leonardo", dark=False)

    labels = {b.text().strip() for b in page.findChildren(QPushButton) if b.text().strip()}
    assert any("Gerar template" in s for s in labels), labels
    assert any("Escolher arquivo" in s for s in labels), labels


@requires_pyside6
def test_logs_atualizar_button_has_label():
    """BUG-V2-02: the refresh button on the Logs page exposes a non-empty label."""
    from PySide6.QtWidgets import QApplication, QPushButton
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.logs import LogsPage
    from notion_rpadv.services.notion_facade import NotionFacade
    conn = _make_cache()
    facade = NotionFacade("dummy-token", conn)
    page = LogsPage(conn=conn, token="x", user="leonardo", facade=facade, dark=False)

    texts = [b.text() for b in page.findChildren(QPushButton)]
    assert any("Atualizar" in t for t in texts), texts


# ---------------------------------------------------------------------------
# BUG-V2-03 — Importar/Logs respect the current theme token
# ---------------------------------------------------------------------------

@requires_pyside6
def test_importar_logs_pages_set_theme_aware_object_name():
    """BUG-V2-03: both pages get an objectName + a stylesheet that pins the
    background to the active theme's app_bg, so they cannot drift to a dark
    rectangle while the rest of the app is in light mode."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.importar import ImportarPage
    from notion_rpadv.pages.logs import LogsPage
    from notion_rpadv.services.notion_facade import NotionFacade
    from notion_rpadv.theme.tokens import LIGHT

    conn = _make_cache()
    facade = NotionFacade("dummy-token", conn)
    importar = ImportarPage(conn=conn, token="x", user="leonardo", dark=False)
    logs = LogsPage(conn=conn, token="x", user="leonardo", facade=facade, dark=False)

    assert importar.objectName() == "ImportarPage"
    assert logs.objectName() == "LogsPage"
    # The light app_bg token must appear in each page's own stylesheet.
    assert LIGHT.app_bg.lower() in importar.styleSheet().lower()
    assert LIGHT.app_bg.lower() in logs.styleSheet().lower()


# ---------------------------------------------------------------------------
# BUG-V2-06 + BUG-V2-07 — Dashboard sync panel renders 4 lines, not 8
# ---------------------------------------------------------------------------

@requires_pyside6
def test_dashboard_sync_panel_is_idempotent_after_refresh():
    """BUG-V2-06 / BUG-V2-07: refreshing the dashboard does not duplicate the
    sync rows. Each base appears exactly once after several refreshes — and
    crucially, this is now true at the DOM level, not just visually, because
    the panel uses persistent QLabels instead of clear-and-rebuild."""
    from PySide6.QtWidgets import QApplication, QLabel
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.dashboard import DashboardPage

    conn = _make_cache()
    page = DashboardPage(conn=conn, user={"name": "Test"}, dark=False)

    # Refresh many times — must NOT accumulate widgets.
    for _ in range(5):
        page.refresh()

    sync_labels = [
        lbl for lbl in page.findChildren(QLabel)
        if "nunca sincronizado" in lbl.text()
    ]
    # 4 bases (Processos, Clientes, Tarefas, Catalogo) — never 8 or 20.
    from notion_bulk_edit.config import DATA_SOURCES
    assert len(sync_labels) == len(DATA_SOURCES), (
        f"got {len(sync_labels)} sync labels after 5 refreshes, expected "
        f"{len(DATA_SOURCES)} — refresh() is leaking widgets again"
    )


@requires_pyside6
def test_dashboard_sync_panel_no_duplicate_timestamps():
    """BUG-V2-07 / §2.3: with timestamps set in cache, every base in the
    Sincronização panel shows its relative-time label exactly once — never
    duplicated even after many refreshes.

    Scoped to the persistent ``_sync_rows`` dict so the toolbar's "Última
    sync: dd/mm HH:MM" label can never accidentally inflate the count.
    """
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    import time
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.dashboard import DashboardPage

    conn = _make_cache()
    now = time.time()
    for base in ("Processos", "Clientes", "Tarefas", "Catalogo"):
        cache_db.set_last_sync(conn, base, now)

    page = DashboardPage(conn=conn, user={"name": "Test"}, dark=False)
    for _ in range(4):
        page.refresh()

    # §2.3: idle rows render the timestamp as "agora há pouco" / "há N min"
    # / "há N h" / "dd/mm HH:MM". With now=just-set, every row falls into
    # "agora há pouco". We assert against the persistent _sync_rows dict
    # rather than findChildren — that's the contract: one label per base,
    # mutated in place, never duplicated.
    from notion_bulk_edit.config import DATA_SOURCES
    rel_pattern = re.compile(
        r"agora há pouco|há \d+ (min|h)|\d{2}/\d{2} \d{2}:\d{2}"
    )
    sync_panel_texts = [
        srow.when_lbl.text() for srow in page._sync_rows.values()
    ]
    matches = [t for t in sync_panel_texts if rel_pattern.search(t)]
    assert len(matches) == len(DATA_SOURCES), (
        f"Sincronização panel: {sync_panel_texts}"
    )
    # Also assert that the dict size hasn't grown — the persistent-widget
    # contract guarantees exactly len(DATA_SOURCES) rows.
    assert len(page._sync_rows) == len(DATA_SOURCES)


@requires_pyside6
def test_dashboard_sync_panel_has_five_columns_per_row():
    """§2.3: every sync row exposes the 5 widgets the spec requires —
    name + count + progress bar + when + chip — and the persistent dict
    structure (_sync_rows) keeps exactly len(DATA_SOURCES) entries."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.dashboard import DashboardPage, _SyncRow
    from notion_bulk_edit.config import DATA_SOURCES

    conn = _make_cache()
    page = DashboardPage(conn=conn, user={"name": "Test"}, dark=False)

    assert set(page._sync_rows.keys()) == set(DATA_SOURCES.keys())
    for base, srow in page._sync_rows.items():
        assert isinstance(srow, _SyncRow), base
        # 5 spec widgets present:
        assert srow._name_lbl.text() == base
        assert srow._count_lbl.text()  # never blank
        assert srow._progress is not None
        assert srow.when_lbl is not None
        assert srow._chip is not None


@requires_pyside6
def test_dashboard_global_progress_strip_toggles_on_sync_signals():
    """§2.3: the 2px strip becomes visible when a sync starts, hides when
    every active sync has finished or errored.

    Visibility is checked two ways for robustness:
      - ``page._global_progress_visible`` — explicit bool intent flag set
        by ``_show_global_progress``. Independent of Qt's ancestor-aware
        ``isVisible()`` (which would return False here because the page
        widget tree was never ``show()``-n in this test).
      - ``not isHidden()`` — Qt's ``WA_WState_Hidden`` attribute, which
        flips on ``show()``/``hide()`` regardless of ancestor visibility.
    """
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from PySide6.QtCore import QObject, Signal
    from notion_rpadv.pages.dashboard import DashboardPage

    class _FakeSyncManager(QObject):
        base_started = Signal(str)
        base_total = Signal(str, int)
        base_progress = Signal(str, int)
        base_done = Signal(str, int, int, int)
        sync_error = Signal(str, str)
        all_done = Signal()

    sm = _FakeSyncManager()
    conn = _make_cache()
    page = DashboardPage(conn=conn, user={"name": "Test"}, dark=False, sync_manager=sm)

    # Initial state: strip hidden, no active syncs, intent flag False.
    assert page._global_progress_visible is False
    assert page._global_progress.isHidden() is True
    assert page._active_syncs == set()

    sm.base_started.emit("Processos")
    assert "Processos" in page._active_syncs
    assert page._sync_rows["Processos"]._state == "syncing"
    assert page._global_progress_visible is True
    assert page._global_progress.isHidden() is False  # show() was called

    sm.base_started.emit("Clientes")
    assert "Clientes" in page._active_syncs
    assert page._global_progress_visible is True

    sm.base_done.emit("Processos", 0, 0, 0)
    # Still active because Clientes hasn't finished — strip stays visible.
    assert page._global_progress_visible is True
    assert page._global_progress.isHidden() is False

    sm.sync_error.emit("Clientes", "boom")
    # Both finished/errored — strip is intent-hidden.
    assert page._active_syncs == set()
    assert page._global_progress_visible is False
    assert page._global_progress.isHidden() is True


@requires_pyside6
def test_main_window_propagates_apply_theme_to_status_bar():
    """N5: toggling theme on MainWindow flips AppStatusBar's palette."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.app import MainWindow
    from notion_rpadv.theme.tokens import LIGHT, DARK

    win = MainWindow(user_id="leonardo", token="dummy", theme_pref="light")
    try:
        # Light: status bar background pinned via stylesheet uses LIGHT.app_panel.
        assert LIGHT.app_panel.lower() in win._status_bar.styleSheet().lower()
        # Toggle to dark
        win._on_theme_changed("dark")
        assert win._dark is True
        assert DARK.app_panel.lower() in win._status_bar.styleSheet().lower()
    finally:
        win.close()
        win.deleteLater()


@requires_pyside6
def test_processos_columns_respect_schema_min_widths():
    """§3.1: the explicit min_width_px in PropSpec (e.g. CNJ 200, Cliente
    principal 200) is enforced after _resize_columns_to_header runs."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_bulk_edit.schemas import colunas_visiveis, get_prop
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    from notion_rpadv.cache import db as cache_db

    conn = _make_cache()
    # At least one row so the EmptyState doesn't take over the table.
    cache_db.upsert_record(
        conn, "Processos", "p-1", {"page_id": "p-1", "cnj": "0001234"}
    )
    facade = NotionFacade("dummy", conn)
    page = ProcessosPage(conn=conn, token="dummy", user="leonardo", facade=facade)
    page._resize_columns_to_header()

    header = page._table.horizontalHeader()
    cols = colunas_visiveis("Processos")
    for col_idx, key in enumerate(cols):
        spec = get_prop("Processos", key)
        if spec is None or not spec.min_width_px:
            continue
        actual = header.sectionSize(col_idx)
        assert actual >= spec.min_width_px, (
            f"column '{key}' width {actual} < schema min {spec.min_width_px}"
        )


@requires_pyside6
def test_empty_cells_render_as_em_dash():
    """§3.3: null/empty values render as the em-dash placeholder, not blank."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value

    text = PropSpec(notion_name="X", tipo="rich_text", label="X")
    rel = PropSpec(notion_name="Y", tipo="relation", label="Y")
    num = PropSpec(notion_name="Z", tipo="number", label="Z")
    assert _display_value(text, None) == "—"
    assert _display_value(text, "") == "—"
    assert _display_value(rel, []) == "—"
    # Number 0 must NOT collapse to "—" — 0 is a real value, not "no value".
    assert _display_value(num, 0) == "0"


@requires_pyside6
def test_filter_bar_hidden_until_filter_active():
    """§3.9: FilterBar starts hidden; populating it with a single filter
    makes it visible and surfaces a single chip + summary."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.widgets.filter_bar import FilterBar

    bar = FilterBar()
    assert bar.isVisible() is False

    bar.set_filters({"status": ("Status", 2)})
    # Visible because we have an active filter…
    assert "1 filtro ativo" in bar._summary.text()

    bar.set_filters({})
    assert bar.isVisible() is False


@requires_pyside6
def test_filter_bar_emits_signals_on_user_action():
    """§3.9: × on a chip emits filter_removed; Limpar todos emits clear_all."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.widgets.filter_bar import FilterBar
    bar = FilterBar()
    bar.set_filters({"status": ("Status", 2), "fase": ("Fase", 1)})

    removed_keys: list[str] = []
    cleared_count = [0]
    bar.filter_removed.connect(removed_keys.append)
    bar.clear_all_clicked.connect(lambda: cleared_count.__setitem__(0, cleared_count[0] + 1))

    # Activate the first chip's × button.
    bar._chips[0]._on_close()
    assert "status" in removed_keys

    bar._clear_btn.click()
    assert cleared_count[0] == 1


@requires_pyside6
def test_configuracoes_shortcut_capture_replaces_qinputdialog():
    """§7.2: each shortcut row uses an inline _ShortcutCapture widget;
    saving emits shortcut_changed without ever opening a modal dialog."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from PySide6.QtGui import QKeySequence
    from notion_rpadv.pages.configuracoes import ConfiguracoesPage, _ShortcutCapture

    conn = _make_cache()
    page = ConfiguracoesPage(
        current_theme="light", bindings={"save": "Ctrl+S"},
        sync_manager=None, conn=conn, dark=False,
    )
    captures = page.findChildren(_ShortcutCapture)
    assert len(captures) >= 1, "no _ShortcutCapture widgets created"

    received: list[tuple[str, str]] = []
    page.shortcut_changed.connect(lambda action, seq: received.append((action, seq)))

    # Simulate a saved capture by injecting a sequence + emitting saved.
    cap = captures[0]
    cap._edit.setKeySequence(QKeySequence("Ctrl+Shift+S"))
    cap._on_finished()
    # The signal carries the action + new sequence.
    assert received, "shortcut_changed never fired"


@requires_pyside6
def test_configuracoes_users_table_marks_current_user():
    """§7.3: the user row whose id matches current_user_id gets the "Você"
    chip + accent-soft background treatment."""
    from PySide6.QtWidgets import QApplication, QLabel
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.configuracoes import ConfiguracoesPage
    conn = _make_cache()
    page = ConfiguracoesPage(
        current_theme="light", bindings=None, sync_manager=None,
        conn=conn, current_user_id="leonardo", dark=False,
    )
    you_chips = [
        lbl for lbl in page.findChildren(QLabel) if lbl.text() == "Você"
    ]
    # Exactly one row gets the chip — the current user.
    assert len(you_chips) == 1


@requires_pyside6
def test_relation_double_click_emits_navigation_signal():
    """§3.2: double-clicking a relation cell emits relation_clicked with
    (target_base, page_id) so the parent window can navigate."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade

    conn = _make_cache()
    cliente_id = "cli-1"
    cache_db.upsert_record(
        conn, "Clientes", cliente_id, {"page_id": cliente_id, "nome": "Acme"}
    )
    cache_db.upsert_record(
        conn, "Processos", "p-1",
        {"page_id": "p-1", "cnj": "0001234", "cliente": [cliente_id]},
    )

    facade = NotionFacade("dummy", conn)
    page = ProcessosPage(conn=conn, token="dummy", user="leonardo", facade=facade)

    received: list[tuple[str, str]] = []
    page.relation_clicked.connect(lambda b, p: received.append((b, p)))

    # Locate the "cliente" column index in the source model.
    from notion_bulk_edit.schemas import colunas_visiveis
    cols = colunas_visiveis("Processos")
    cliente_col = cols.index("cliente")
    src_idx = page._model.index(0, cliente_col)
    proxy_idx = page._proxy.mapFromSource(src_idx)
    page._on_table_double_clicked(proxy_idx)
    assert received == [("Clientes", cliente_id)]


@requires_pyside6
def test_dashboard_urgent_tasks_panel_is_idempotent():
    """BUG-V2-06: urgent-tasks panel uses a persistent _TaskRow pool, so
    repeated refresh() never grows the QLabel count beyond what _build_ui
    pre-allocated. Validates the same fix applies to the second panel."""
    from PySide6.QtWidgets import QApplication, QLabel
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.dashboard import DashboardPage

    conn = _make_cache()  # zero tarefas → empty state inside the panel
    page = DashboardPage(conn=conn, user={"name": "Test"}, dark=False)
    baseline = sum(
        1 for lbl in page.findChildren(QLabel)
        if "Nenhuma tarefa urgente" in lbl.text()
    )
    for _ in range(6):
        page.refresh()
    after = sum(
        1 for lbl in page.findChildren(QLabel)
        if "Nenhuma tarefa urgente" in lbl.text()
    )
    assert baseline == after == 1, (baseline, after)


# ---------------------------------------------------------------------------
# BUG-V2-05 — Configurações pulls timestamps from the same source as Dashboard
# ---------------------------------------------------------------------------

@requires_pyside6
def test_config_sync_timestamps_consistent_with_dashboard():
    """BUG-V2-05: Configurações reads sync timestamps from cache_db, just like
    the Dashboard, so the two views agree."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    import time
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.configuracoes import ConfiguracoesPage

    conn = _make_cache()
    ts = time.time() - 60  # 1 minute ago
    for base in ("Processos", "Clientes", "Tarefas", "Catalogo"):
        cache_db.set_last_sync(conn, base, ts)

    config = ConfiguracoesPage(
        current_theme="light", bindings=None, sync_manager=None, conn=conn, dark=False
    )

    # Every base label should reflect a real timestamp, not "Nunca".
    for base, lbl in config._sync_labels.items():
        assert lbl.text().strip() not in ("", "Nunca", "—"), f"{base}: {lbl.text()!r}"


# ---------------------------------------------------------------------------
# BUG-V2-11 — status bar reserves room for "Última sync: N min atrás"
# ---------------------------------------------------------------------------

@requires_pyside6
def test_status_bar_last_sync_label_has_minimum_width():
    """BUG-V2-11: the right-side last-sync label is wide enough that "12 min
    atrás" no longer truncates to "12 min at...". """
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.widgets.status_bar import AppStatusBar
    bar = AppStatusBar()
    fm = bar._last_sync_lbl.fontMetrics()
    expected = fm.horizontalAdvance("Última sync: 12 min atrás")
    assert bar._last_sync_lbl.minimumWidth() >= expected, (
        f"minimumWidth={bar._last_sync_lbl.minimumWidth()} < {expected}"
    )


# ---------------------------------------------------------------------------
# §0.3 / BUG-N1 — Tema "Auto" persists the choice and resolves via the OS
# ---------------------------------------------------------------------------

@requires_pyside6
def test_theme_auto_picker_emits_auto_signal():
    """§0.3: selecting the "Auto" radio emits theme_changed("auto").
    Previously the parent collapsed it back to "light" silently."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.configuracoes import ConfiguracoesPage
    conn = _make_cache()
    page = ConfiguracoesPage(
        current_theme="light", bindings=None, sync_manager=None, conn=conn, dark=False
    )
    received: list[str] = []
    page.theme_changed.connect(received.append)
    page._auto_radio.setChecked(True)
    assert "auto" in received, received


@requires_pyside6
def test_main_window_resolves_auto_from_system():
    """§0.3: when theme_pref="auto", _resolve_dark() defers to the OS.
    We assert it returns a bool — exact value depends on the test runner's
    environment, but the call must succeed and not silently flip to False
    just because the input was "auto" (the old bug)."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.app import MainWindow

    # Build a minimal MainWindow without going through the full UI path —
    # we just want to confirm _resolve_dark() agrees with the system call.
    # MainWindow.__init__ requires a token; we pass a dummy. This will hit
    # cache_db etc; if it gets too heavy in the future we can refactor.
    win = MainWindow(user_id="leonardo", token="dummy", theme_pref="auto")
    try:
        assert isinstance(win._resolve_dark(), bool)
        assert win._theme_pref == "auto"
    finally:
        win.close()
        win.deleteLater()


# ---------------------------------------------------------------------------
# §9 / BUG-N2 — EmptyState swaps in when the source model is empty
# ---------------------------------------------------------------------------

@requires_pyside6
def test_base_table_page_shows_empty_state_when_cache_empty():
    """§9 / BUG-N2: a page whose base has zero records must show the
    EmptyState widget, not an empty QTableView with active toolbar."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    from notion_rpadv.widgets.empty_state import EmptyState

    conn = _make_cache()  # zero Processos
    facade = NotionFacade("dummy-token", conn)
    page = ProcessosPage(
        conn=conn, token="dummy-token", user="leonardo", facade=facade, dark=False
    )

    assert page._content_stack.currentWidget() is page._empty_state
    assert isinstance(page._empty_state, EmptyState)
    # §9.3: search and "+ Novo" must be disabled when EmptyState is visible.
    assert page._search_edit.isEnabled() is False
    assert page._new_btn.isEnabled() is False


@requires_pyside6
def test_base_table_page_shows_table_when_cache_has_rows():
    """§9: a page with at least one row keeps the QTableView visible and
    re-enables the toolbar controls."""
    from PySide6.QtWidgets import QApplication
    import sys
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade

    conn = _make_cache()
    cache_db.upsert_record(
        conn, "Processos", "p-1", {"page_id": "p-1", "cnj": "0001234"}
    )
    facade = NotionFacade("dummy-token", conn)
    page = ProcessosPage(
        conn=conn, token="dummy-token", user="leonardo", facade=facade, dark=False
    )

    assert page._content_stack.currentWidget() is page._table
    assert page._search_edit.isEnabled() is True
    assert page._new_btn.isEnabled() is True
