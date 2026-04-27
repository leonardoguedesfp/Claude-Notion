"""Entry point — python -m notion_rpadv"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from notion_bulk_edit.config import APP_NAME, APP_VERSION
from notion_rpadv.app import MainWindow
from notion_rpadv.auth.login_window import LoginWindow
from notion_rpadv.auth.token_store import get_token, has_token
from notion_rpadv.theme.fonts import load_fonts


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Load custom fonts (Playfair Display, Nunito Sans, JetBrains Mono)
    load_fonts()

    # Check for stored token; if missing show login dialog
    token: str | None = get_token()
    user_id: str = "deborah"  # last-used user; TODO persist in settings

    if not token:
        login = LoginWindow()
        result = login.exec()
        if result != LoginWindow.DialogCode.Accepted:
            sys.exit(0)
        token = login.get_token()
        user_id = login.get_user()

    window = MainWindow(user_id=user_id, token=token)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
