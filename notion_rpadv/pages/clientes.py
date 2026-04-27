"""Clientes page."""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QWidget

from notion_rpadv.cache.sync import SyncManager
from notion_rpadv.pages.base_table_page import BaseTablePage
from notion_rpadv.services.notion_facade import NotionFacade


class ClientesPage(BaseTablePage):
    """Table page for the Clientes base."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        token: str,
        user: str,
        facade: NotionFacade,
        sync_manager: SyncManager | None = None,
        dark: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            base="Clientes",
            conn=conn,
            token=token,
            user=user,
            facade=facade,
            sync_manager=sync_manager,
            dark=dark,
            parent=parent,
        )
