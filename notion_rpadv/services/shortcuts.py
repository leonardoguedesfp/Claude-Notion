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
        # BUG-OP-07: start from defaults and overlay the user's saved JSON
        # so customised key sequences survive a restart. New defaults
        # introduced in future versions still appear because they were
        # placed in the dict before the override merge.
        self._bindings: dict[str, str] = dict(DEFAULT_SHORTCUTS)
        try:
            user_overrides = load_user_shortcuts()
        except Exception:  # noqa: BLE001
            # load_user_shortcuts itself swallows json errors and returns
            # defaults; this except is a belt-and-braces guard against any
            # future change that lets exceptions escape.
            user_overrides = dict(DEFAULT_SHORTCUTS)
        # `load_user_shortcuts()` already returns the merged dict, but we
        # apply it on top so a hand-mocked ``load_user_shortcuts`` that
        # returns only overrides also works.
        self._bindings.update(user_overrides)
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

        BUG-OP-07: prefer ``setKey()`` on the existing ``QShortcut`` so the
        signal connections survive — destroying and recreating would lose
        any external ``activated`` connections set via ``add_handler``.
        Falls back to recreate-from-scratch when no live shortcut exists
        yet (e.g. the first call for an action only registered later).

        If the action has no handler registered it is still stored so that
        ``get_bindings()`` returns an accurate map.
        """
        self._bindings[action] = new_sequence
        existing = self._shortcuts.get(action)
        if existing is not None:
            key_seq = QKeySequence(new_sequence)
            if key_seq.isEmpty():
                # Refuse to install an empty/invalid sequence; disable
                # instead of leaving the QShortcut in a broken state.
                existing.setEnabled(False)
                return
            existing.setKey(key_seq)
            existing.setEnabled(True)
            return
        # No live shortcut yet — create one if there is a handler.
        if action in self._handlers:
            self._create_shortcut(action, new_sequence)

    def get_bindings(self) -> dict[str, str]:
        """Return a copy of the current action → key-sequence mapping."""
        return dict(self._bindings)

    def get_binding(self, action: str) -> str:
        """Return the current key sequence string for *action*, or empty."""
        return self._bindings.get(action, "")

    def update_binding(self, action: str, new_sequence: str) -> None:
        """BUG-OP-07: alias for ``update_shortcut`` matching the spec name
        used by callers in MainWindow that don't care about the QShortcut
        plumbing detail."""
        self.update_shortcut(action, new_sequence)

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
