"""Processos page."""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QWidget

from notion_bulk_edit.schemas import colunas_visiveis
from notion_rpadv.cache.sync import SyncManager
from notion_rpadv.models.delegates import CnjDelegate
from notion_rpadv.pages.base_table_page import BaseTablePage
from notion_rpadv.services.notion_facade import NotionFacade


class ProcessosPage(BaseTablePage):
    """Table page for the Processos base."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        token: str,
        user: str,
        facade: NotionFacade,
        sync_manager: SyncManager | None = None,
        dark: bool = False,
        parent: QWidget | None = None,
        audit_conn: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__(
            base="Processos",
            conn=conn,
            token=token,
            user=user,
            facade=facade,
            sync_manager=sync_manager,
            dark=dark,
            parent=parent,
            audit_conn=audit_conn,
        )
        # §3.8: install the CNJ-specific delegate on the CNJ column so rows
        # with a `processo_pai` render the parent CNJ inline (↳ ABOVE own).
        cols = colunas_visiveis("Processos")
        if "cnj" in cols:
            cnj_col = cols.index("cnj")
            self._table.setItemDelegateForColumn(cnj_col, CnjDelegate(self._table))
