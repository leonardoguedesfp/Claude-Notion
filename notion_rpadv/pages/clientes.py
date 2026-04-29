"""Clientes page."""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QWidget

from notion_rpadv.cache.sync import SyncManager
from notion_rpadv.models.delegates import SucessorDelegate
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
        audit_conn: sqlite3.Connection | None = None,
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
            audit_conn=audit_conn,
        )
        # P1-002 (Lote 1): cachear instância única do delegate evita criar
        # um QObject novo a cada modelReset. Reapontamos ela em
        # _install_delegates.
        self._sucessor_delegate = SucessorDelegate(self._table)
        # §3.7: render "Sucessor de" with the ↳ Name (†) chip-rel treatment.
        self._install_delegates()
        # Re-bind quando _cols muda (picker da Fase 4 + sync). Sem isso, o
        # delegate fica preso no índice antigo e pinta dado errado depois
        # do usuário esconder/mostrar colunas.
        self._model.modelReset.connect(self._install_delegates)

    def _install_delegates(self) -> None:
        """P1-002 (Lote 1): re-resolve índice de 'sucessor_de' a partir
        do estado atual de ``_cols`` e instala o delegate cacheado nessa
        coluna. Limpa qualquer binding antigo para que o delegate não
        pinte na coluna errada após o picker mudar a ordem."""
        # Limpa todos os bindings da tabela — barato (Qt seta None).
        col_count = self._table.model().columnCount() if self._table.model() else 0
        for col_idx in range(col_count):
            self._table.setItemDelegateForColumn(col_idx, None)
        # Fase 4: lê cols do model (respeita user prefs em meta_user_columns).
        cols = self._model.cols()
        if "sucessor_de" in cols:
            sd_col = cols.index("sucessor_de")
            self._table.setItemDelegateForColumn(sd_col, self._sucessor_delegate)
