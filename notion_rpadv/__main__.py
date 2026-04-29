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

# Round 3a: chave "theme_preference" foi descontinuada junto com o modo
# escuro. Usuários que já têm a chave gravada em QSettings de versões
# anteriores não veem nada — o app simplesmente não lê mais essa chave.
# Não há migração explícita: ignorar é mais seguro que escrever defaults.


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Load custom fonts (Playfair Display, Nunito Sans, JetBrains Mono)
    load_fonts()

    # BUG-09: read persisted user from QSettings instead of hardcoding "deborah"
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    user_id: str = settings.value(_KEY_LAST_USER, "")

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

    # Round 3a: kwarg theme_pref removido — MainWindow só aceita user_id e token.
    window = MainWindow(user_id=user_id, token=token)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
