"""Tests for Round 2 / Lote 2 da auditoria do app.

Cobre 8 componentes (7 esforço S + 1 esforço M):
- C1: P2-006 — código morto em floating_save._animate (sem teste novo —
  validação visual / smoke).
- C2: P2-004 — SyncWorker.deleteLater (sem teste novo — observabilidade
  via profiler, smoke confia na mudança semântica).
- C3: P2-003 — error toasts com dismiss manual (auto_dismiss flag).
- C4: P3-004 — atalhos Ctrl+K (picker) e Ctrl+B (sidebar toggle).
- C5: P3-002 — ABORTADO. Auditoria classificou
  ``_count_processos_for_cliente`` como inerte, mas há caller ativo em
  ``base_table_model.py:346`` (fallback BUG-V2-09 para rollup vazio
  do Notion). Removeria funcionalidade. Backlog desatualizado.
- C6: P2-002 — cache de DisplayRole no model.
- C7: P2-001 — cache de count de processos por cliente (se atacado).
- C8: P3-003 — flash visual em scroll (não atacado se não reproduzido).

Componentes 1, 2 e 8 são essencialmente sem teste novo — cobertura por
smoke manual + propriedades semânticas.
"""
from __future__ import annotations

import pytest

try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(
    not _PYSIDE6, reason="PySide6 not installed",
)


# ---------------------------------------------------------------------------
# C3 — P2-003: error toasts não auto-dismissam
# ---------------------------------------------------------------------------


@requires_pyside6
def test_toast_error_kind_disables_auto_dismiss() -> None:
    """Toast com kind='error' tem _auto_dismiss=False — usuário precisa
    clicar × para fechar."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.widgets.toast import Toast

    toast = Toast("Erro de sync", kind="error")
    assert toast._auto_dismiss is False, (
        "Toast de erro deveria ter _auto_dismiss=False (P2-003)."
    )


@requires_pyside6
def test_toast_non_error_kinds_keep_auto_dismiss() -> None:
    """Toasts info/success/warning mantêm auto-dismiss de 4s."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.widgets.toast import Toast

    for kind in ("info", "success", "warning"):
        toast = Toast(f"msg {kind}", kind=kind)
        assert toast._auto_dismiss is True, (
            f"Toast de {kind!r} deveria ter _auto_dismiss=True; mudança "
            "do P2-003 é restrita a 'error'."
        )


@requires_pyside6
def test_toast_error_slide_in_does_not_start_timer() -> None:
    """Quando kind='error', slide_in não dispara o timer de auto-dismiss."""
    import sys
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.widgets.toast import Toast

    toast = Toast("Erro", kind="error")
    # Mock parent-less é OK — slide_in não exige parent para o teste do
    # timer state. Forçamos um QPoint qualquer.
    toast.slide_in(QPoint(0, 0))
    assert toast._timer.isActive() is False, (
        "Timer de auto-dismiss não deveria estar ativo para toast de erro."
    )
    # Cleanup
    toast.deleteLater()


@requires_pyside6
def test_toast_info_slide_in_starts_timer() -> None:
    """Quando kind='info', slide_in dispara o timer normalmente."""
    import sys
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.widgets.toast import Toast

    toast = Toast("Info", kind="info")
    toast.slide_in(QPoint(0, 0))
    assert toast._timer.isActive() is True, (
        "Timer de auto-dismiss deveria estar ativo para toast de info."
    )
    toast._timer.stop()
    toast.deleteLater()


# ---------------------------------------------------------------------------
# C4 — P3-004: atalhos Ctrl+Shift+K (picker) e Ctrl+B (sidebar)
# ---------------------------------------------------------------------------


def test_default_shortcuts_include_picker_and_sidebar() -> None:
    """DEFAULT_SHORTCUTS contém os 2 novos atalhos do Lote 2."""
    from notion_rpadv.services.shortcuts_store import DEFAULT_SHORTCUTS

    assert DEFAULT_SHORTCUTS.get("open_columns_picker") == "Ctrl+Shift+K", (
        "Esperado Ctrl+Shift+K para open_columns_picker (Ctrl+K já estava "
        "em uso por 'search' / command palette)."
    )
    assert DEFAULT_SHORTCUTS.get("toggle_sidebar") == "Ctrl+B"


def test_default_shortcuts_picker_does_not_clobber_search() -> None:
    """Garantir que 'search' (Ctrl+K) continua sendo o atalho de paleta —
    o picker NÃO deve usar Ctrl+K puro (decisão divergente do briefing
    para evitar conflito)."""
    from notion_rpadv.services.shortcuts_store import DEFAULT_SHORTCUTS

    assert DEFAULT_SHORTCUTS.get("search") == "Ctrl+K"
    assert DEFAULT_SHORTCUTS.get("open_columns_picker") != "Ctrl+K"


@requires_pyside6
def test_toggle_sidebar_handler_flips_visibility() -> None:
    """MainWindow._toggle_sidebar inverte sidebar.isVisible()."""
    import sys
    from PySide6.QtWidgets import QApplication, QWidget
    QApplication.instance() or QApplication(sys.argv)

    # Stub mínimo de "MainWindow-like" para testar o handler isolado.
    class _FakeMainWindow:
        def __init__(self):
            self._sidebar = QWidget()
            self._sidebar.setVisible(True)

        # Importa o método como standalone (será bound).
        from notion_rpadv.app import MainWindow
        _toggle_sidebar = MainWindow._toggle_sidebar

    fake = _FakeMainWindow()
    assert fake._sidebar.isVisible() is True
    fake._toggle_sidebar()
    assert fake._sidebar.isVisible() is False
    fake._toggle_sidebar()
    assert fake._sidebar.isVisible() is True


# ---------------------------------------------------------------------------
# C6 — P2-002: cache de DisplayRole no model
# ---------------------------------------------------------------------------


def _make_model_conn():
    """In-memory cache+audit."""
    import sqlite3
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_db(conn)
    return conn


@requires_pyside6
def test_model_display_cache_populates_on_first_data_call() -> None:
    """A primeira chamada de data(DisplayRole) popula o cache. Chamadas
    subsequentes para a mesma célula vêm do cache."""
    import sys
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _make_model_conn()
    cache_db.upsert_record(
        conn, "Clientes", "c-1",
        {"page_id": "c-1", "nome": "Joao Teste"},
    )
    model = BaseTableModel("Clientes", conn)
    # Cache vazio inicialmente
    assert model._display_cache == {}

    # Primeira chamada popula
    idx = model.index(0, 0)
    val1 = model.data(idx, Qt.ItemDataRole.DisplayRole)
    assert (0, 0) in model._display_cache
    assert model._display_cache[(0, 0)] == val1

    # Segunda chamada vem do cache (mesmo valor, sem recomputar)
    val2 = model.data(idx, Qt.ItemDataRole.DisplayRole)
    assert val2 == val1


@requires_pyside6
def test_model_display_cache_invalidated_on_reload() -> None:
    """``model.reload()`` limpa o cache — rows e cols podem ter mudado."""
    import sys
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _make_model_conn()
    cache_db.upsert_record(
        conn, "Clientes", "c-1",
        {"page_id": "c-1", "nome": "Original"},
    )
    model = BaseTableModel("Clientes", conn)
    model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    assert model._display_cache != {}

    # Reload limpa
    model.reload()
    assert model._display_cache == {}


@requires_pyside6
def test_model_display_cache_invalidated_on_setdata() -> None:
    """``setData`` em uma célula invalida o cache só dessa célula."""
    import sys
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _make_model_conn()
    cache_db.upsert_record(
        conn, "Clientes", "c-1",
        {"page_id": "c-1", "nome": "X", "e_mail": "a@b.com"},
    )
    model = BaseTableModel("Clientes", conn)
    cols = model.cols()

    # Popula cache em duas colunas
    for col_idx in range(min(2, len(cols))):
        model.data(model.index(0, col_idx), Qt.ItemDataRole.DisplayRole)
    populated = dict(model._display_cache)
    assert len(populated) >= 1

    # setData numa célula
    model.setData(model.index(0, 0), "Novo", Qt.ItemDataRole.EditRole)
    # Célula (0,0) saiu do cache
    assert (0, 0) not in model._display_cache
    # Outras células permanecem (se havia mais de uma)
    if (0, 1) in populated:
        assert (0, 1) in model._display_cache


@requires_pyside6
def test_model_foreground_role_uses_display_cache() -> None:
    """ForegroundRole chama data(DisplayRole) recursivamente — esse
    caminho também aproveita o cache."""
    import sys
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _make_model_conn()
    cache_db.upsert_record(
        conn, "Clientes", "c-1",
        {"page_id": "c-1", "nome": "X"},
    )
    model = BaseTableModel("Clientes", conn)
    idx = model.index(0, 0)
    # Limpar cache pra começar do zero
    model._display_cache.clear()

    # Pedir ForegroundRole — ele faz self.data(idx, DisplayRole)
    # internamente, o que popula o cache.
    model.data(idx, Qt.ItemDataRole.ForegroundRole)
    assert (0, 0) in model._display_cache, (
        "ForegroundRole chama data(DisplayRole) e deveria popular cache."
    )


# ---------------------------------------------------------------------------
# C7 — P2-001: cache de count de processos por cliente
# ---------------------------------------------------------------------------


@requires_pyside6
def test_clientes_model_builds_processos_count_cache_on_reload() -> None:
    """Em base='Clientes', _processos_count_cache é populado em reload
    a partir de uma única varredura de Processos. Outras bases têm cache
    vazio."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _make_model_conn()
    # 3 processos: 2 ligados a cliente c1, 1 a cliente c2.
    cache_db.upsert_record(conn, "Processos", "p-1",
                           {"page_id": "p-1", "clientes": ["c1"]})
    cache_db.upsert_record(conn, "Processos", "p-2",
                           {"page_id": "p-2", "clientes": ["c1"]})
    cache_db.upsert_record(conn, "Processos", "p-3",
                           {"page_id": "p-3", "clientes": ["c2"]})
    # 2 clientes
    cache_db.upsert_record(conn, "Clientes", "c1",
                           {"page_id": "c1", "nome": "Alpha"})
    cache_db.upsert_record(conn, "Clientes", "c2",
                           {"page_id": "c2", "nome": "Beta"})

    model_clientes = BaseTableModel("Clientes", conn)
    assert model_clientes._processos_count_cache == {"c1": 2, "c2": 1}

    # Modelo de outra base não deve popular
    model_processos = BaseTableModel("Processos", conn)
    assert model_processos._processos_count_cache == {}


@requires_pyside6
def test_clientes_model_count_cache_reflects_legacy_slug() -> None:
    """O helper aceita tanto 'clientes' (slug Fase 0+) quanto 'cliente'
    (legado) para tolerância durante migração."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import _build_processos_count_cache

    conn = _make_model_conn()
    # Mistura: um processo com slug legado, outro com slug novo.
    cache_db.upsert_record(conn, "Processos", "p-old",
                           {"page_id": "p-old", "cliente": ["c1"]})
    cache_db.upsert_record(conn, "Processos", "p-new",
                           {"page_id": "p-new", "clientes": ["c1"]})

    counts = _build_processos_count_cache(conn)
    assert counts == {"c1": 2}, (
        f"Esperado c1: 2 (1 via 'cliente' legado + 1 via 'clientes' novo); "
        f"obtido {counts!r}."
    )


@requires_pyside6
def test_clientes_model_count_cache_no_double_count_mixed_slugs() -> None:
    """Se a MESMA linha tem 'clientes' e 'cliente' apontando para o
    MESMO id (raríssimo mas possível), conta uma vez só."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import _build_processos_count_cache

    conn = _make_model_conn()
    cache_db.upsert_record(
        conn, "Processos", "p-mixed",
        {"page_id": "p-mixed", "clientes": ["c1"], "cliente": ["c1"]},
    )
    counts = _build_processos_count_cache(conn)
    assert counts == {"c1": 1}, (
        "Mesma linha com slug duplicado para o mesmo cliente deveria "
        f"contar 1 vez. Obtido {counts!r}."
    )


@requires_pyside6
def test_clientes_model_count_cache_invalidated_on_reload() -> None:
    """Quando Processos muda externamente e o model de Clientes faz
    reload, o cache é repopulado."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _make_model_conn()
    cache_db.upsert_record(conn, "Processos", "p-1",
                           {"page_id": "p-1", "clientes": ["c1"]})
    cache_db.upsert_record(conn, "Clientes", "c1",
                           {"page_id": "c1", "nome": "X"})

    model = BaseTableModel("Clientes", conn)
    assert model._processos_count_cache == {"c1": 1}

    # Adiciona mais 1 processo de c1 EXTERNAMENTE — cache fica stale.
    cache_db.upsert_record(conn, "Processos", "p-2",
                           {"page_id": "p-2", "clientes": ["c1"]})
    # Cache ainda tem o valor antigo
    assert model._processos_count_cache == {"c1": 1}

    # reload() repopula
    model.reload()
    assert model._processos_count_cache == {"c1": 2}


def test_shortcut_labels_include_new_actions() -> None:
    """Configurações e ShortcutsModal expõem labels para os 2 atalhos."""
    from notion_rpadv.pages.configuracoes import _SHORTCUT_LABELS
    from notion_rpadv.widgets.shortcuts_modal import (
        _ACTION_LABELS, _ACTION_SECTIONS,
    )

    for key in ("open_columns_picker", "toggle_sidebar"):
        assert key in _SHORTCUT_LABELS, (
            f"{key!r} ausente em configuracoes._SHORTCUT_LABELS — "
            "tabela de atalhos da página Configurações não vai mostrar."
        )
        assert key in _ACTION_LABELS, (
            f"{key!r} ausente em shortcuts_modal._ACTION_LABELS."
        )
        assert key in _ACTION_SECTIONS, (
            f"{key!r} ausente em shortcuts_modal._ACTION_SECTIONS."
        )
