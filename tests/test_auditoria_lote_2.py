"""Tests for Round 2 / Lote 2 da auditoria do app.

Cobre 8 componentes (7 esforço S + 1 esforço M):
- C1: P2-006 — código morto em floating_save._animate (sem teste novo —
  validação visual / smoke).
- C2: P2-004 — SyncWorker.deleteLater (sem teste novo — observabilidade
  via profiler, smoke confia na mudança semântica).
- C3: P2-003 — error toasts com dismiss manual (auto_dismiss flag).
- C4: P3-004 — atalhos Ctrl+K (picker) e Ctrl+B (sidebar toggle).
- C5: P3-002 — _count_processos_for_cliente helper inerte removido.
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
