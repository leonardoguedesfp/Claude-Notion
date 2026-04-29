"""Processos page."""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QWidget

from notion_rpadv.cache.sync import SyncManager
from notion_rpadv.pages.base_table_page import BaseTablePage
from notion_rpadv.services.notion_facade import NotionFacade


class ProcessosPage(BaseTablePage):
    """Table page for the Processos base.

    Round simplificação CnjDelegate (Lote 1): a coluna ``numero_do_processo``
    não tem mais delegate específico. O CnjDelegate antigo desenhava
    layout two-line (↳ parent_cnj em cima do own_cnj) quando a linha
    tinha ``processo_pai`` resolvido — informação que já é visível pela
    coluna "Processo pai" (relation, oculta por default no picker da
    Fase 4). PropDelegate (default) renderiza o CNJ próprio em font
    default. Hierarquia processual é vista pela coluna Processo pai
    (que ainda fica clicável via double-click → navega para o pai).
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        token: str,
        user: str,
        facade: NotionFacade,
        sync_manager: SyncManager | None = None,
        parent: QWidget | None = None,
        audit_conn: sqlite3.Connection | None = None,
    ) -> None:
        # Round 3a: kwarg dark removido — paleta única LIGHT.
        super().__init__(
            base="Processos",
            conn=conn,
            token=token,
            user=user,
            facade=facade,
            sync_manager=sync_manager,
            parent=parent,
            audit_conn=audit_conn,
        )
