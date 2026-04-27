"""Global keyboard shortcut registry."""
from __future__ import annotations

from typing import Callable, Any

from PySide6.QtCore import QObject
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

from notion_rpadv.services.shortcuts_store import (  # noqa: F401  (re-export)
    DEFAULT_SHORTCUTS,
    load_user_shortcuts,
    save_user_shortcuts,
)


class ShortcutRegistry(QObject):
    """Registers and manages global keyboard shortcuts on a main window widget.

    Usage::

        registry = ShortcutRegistry(
            window=main_window,
            handlers={
                "save": main_window.save_changes,
                "refresh": main_window.refresh,
                ...
            },
        )
        registry.register_all()

    After registration, shortcuts can be updated at runtime::

        registry.update_shortcut("save", "Ctrl+Shift+S")
    """

    def __init__(
        self,
        window: QObject,
        handlers: dict[str, Callable[[], Any]],
    ) -> None:
        super().__init__(window)
        if not isinstance(window, QWidget):
            raise TypeError(
                f"ShortcutRegistry requires a QWidget as 'window', got {type(window).__name__}"
            )
        self._window: QWidget = window
        self._handlers: dict[str, Callable[[], Any]] = handlers
        # Maps action name → current key-sequence string.
        self._bindings: dict[str, str] = dict(DEFAULT_SHORTCUTS)
        # Maps action name → live QShortcut instance.
        self._shortcuts: dict[str, QShortcut] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_all(self) -> None:
        """Create (or recreate) QShortcut instances for every action that has a handler."""
        for action, sequence in self._bindings.items():
            self._create_shortcut(action, sequence)

    def update_shortcut(self, action: str, new_sequence: str) -> None:
        """Change the key binding for *action* at runtime.

        If the action has no handler registered it is still stored so that
        ``get_bindings()`` returns an accurate map.
        """
        self._bindings[action] = new_sequence
        # Destroy the old QShortcut if present.
        old = self._shortcuts.pop(action, None)
        if old is not None:
            old.setEnabled(False)
            old.deleteLater()
        # Only create a new one if there is a handler.
        if action in self._handlers:
            self._create_shortcut(action, new_sequence)

    def get_bindings(self) -> dict[str, str]:
        """Return a copy of the current action → key-sequence mapping."""
        return dict(self._bindings)

    def set_enabled(self, action: str, enabled: bool) -> None:
        """Enable or disable a registered shortcut without removing it."""
        sc = self._shortcuts.get(action)
        if sc is not None:
            sc.setEnabled(enabled)

    def unregister(self, action: str) -> None:
        """Remove a shortcut entirely (both handler and QShortcut)."""
        sc = self._shortcuts.pop(action, None)
        if sc is not None:
            sc.setEnabled(False)
            sc.deleteLater()
        self._handlers.pop(action, None)

    def add_handler(self, action: str, handler: Callable[[], Any]) -> None:
        """Register (or replace) a handler for *action* and activate its shortcut."""
        self._handlers[action] = handler
        sequence = self._bindings.get(action, "")
        if sequence:
            # Remove old shortcut first.
            old = self._shortcuts.pop(action, None)
            if old is not None:
                old.setEnabled(False)
                old.deleteLater()
            self._create_shortcut(action, sequence)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_shortcut(self, action: str, sequence: str) -> None:
        """Build and store a QShortcut for *action* with the given *sequence*.

        If *sequence* is empty or invalid, or if there is no handler for the
        action, no QShortcut is created.
        """
        if not sequence:
            return
        handler = self._handlers.get(action)
        if handler is None:
            # Store the binding but don't create a widget-level shortcut.
            return

        key_seq = QKeySequence(sequence)
        if key_seq.isEmpty():
            return

        sc = QShortcut(key_seq, self._window)
        sc.setContext(
            # Application-wide so it works even when a child widget has focus.
            # Use WindowShortcut if you want it scoped to the window only.
            sc.context()  # Qt.ShortcutContext.WindowShortcut by default
        )
        sc.activated.connect(handler)
        self._shortcuts[action] = sc
