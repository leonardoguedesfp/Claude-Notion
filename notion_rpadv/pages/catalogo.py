"""Catalogo page."""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QWidget

from notion_rpadv.pages.base_table_page import BaseTablePage
from notion_rpadv.services.notion_facade import NotionFacade


class CatalogoPage(BaseTablePage):
    """Table page for the Catalogo base."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        token: str,
        user: str,
        facade: NotionFacade,
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            base="Catalogo",
            conn=conn,
            token=token,
            user=user,
            facade=facade,
            dark=dark,
            parent=parent,
        )
