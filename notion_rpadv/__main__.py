"""Entry point — python -m notion_rpadv"""
from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from notion_bulk_edit.config import APP_NAME, APP_VERSION
from notion_rpadv.app import MainWindow
from notion_rpadv.auth.login_window import LoginWindow
from notion_rpadv.auth.token_store import get_token
from notion_rpadv.theme.fonts import load_fonts

_SETTINGS_ORG = "RPADV"
_SETTINGS_APP = "NotionApp"
_KEY_LAST_USER = "last_user"
# §0.3: theme preference persisted across launches ("light"/"dark"/"auto").
_KEY_THEME_PREF = "theme_preference"
_VALID_THEMES = {"light", "dark", "auto"}


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Load custom fonts (Playfair Display, Nunito Sans, JetBrains Mono)
    load_fonts()

    # BUG-09: read persisted user from QSettings instead of hardcoding "deborah"
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    user_id: str = settings.value(_KEY_LAST_USER, "")

    # §0.3: read persisted theme; default to "auto" for first-run users so
    # the desktop app matches the OS scheme out of the box.
    theme_pref_raw = settings.value(_KEY_THEME_PREF, "auto")
    theme_pref: str = (
        str(theme_pref_raw) if str(theme_pref_raw) in _VALID_THEMES else "auto"
    )

    token: str | None = get_token()

    if not token or not user_id:
        login = LoginWindow()
        result = login.exec()
        if result != LoginWindow.DialogCode.Accepted:
            sys.exit(0)
        token = login.get_token()
        user_id = login.get_user()
        # BUG-09: persist for next launch
        settings.setValue(_KEY_LAST_USER, user_id)

    window = MainWindow(user_id=user_id, token=token, theme_pref=theme_pref)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
