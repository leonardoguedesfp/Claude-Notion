"""QObject worker thread para o recálculo de Alerta contadoria.

Roda ``recalcular_alertas_publicacoes`` em background pra não congelar
a UI durante os ~12 min de processamento de ~2.000 publicações.

Emite:
- ``progress(int processadas, int total)`` — a cada iteração
- ``finished(ResultadoRecalculo)`` — ao concluir com sucesso
- ``error(str)`` — em exceção fatal

Padrão espelha ``_DJEWorker`` do ``leitor_dje.py``: QObject + moveToThread,
para integração simples com o pattern existente da page.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from PySide6.QtCore import QObject, Signal

from notion_bulk_edit.notion_api import NotionClient

from notion_rpadv.services.dje_recalcular_alertas import (
    DS_PUBLICACOES_DEFAULT,
    ResultadoRecalculo,
    recalcular_alertas_publicacoes,
)


class RecalculoAlertasWorker(QObject):
    """Worker stateless — ``run()`` é o único entry-point.

    Args:
        token: Notion API token (lido do keyring pelo caller).
        dje_path: caminho absoluto para o ``leitor_dje.db`` (string).
            Usar string pra evitar problema de pickling se um dia rodar
            em multiprocessing.
        cache_path: idem para ``cache.db``.
        dry_run: sem escrita no Notion (preview apenas).
        always_update: força ``update_page`` mesmo sem diff.
        limite: opcional — processa só N publicações.
    """

    progress: Signal = Signal(int, int)         # (processadas, total)
    loading: Signal = Signal(int)               # (paginas_acumuladas)
    finished: Signal = Signal(object)           # ResultadoRecalculo
    error: Signal = Signal(str)

    def __init__(
        self,
        *,
        token: str,
        dje_path: str,
        cache_path: str,
        dry_run: bool = False,
        always_update: bool = False,
        limite: int | None = None,
        data_source_id: str = DS_PUBLICACOES_DEFAULT,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._token = token
        self._dje_path = dje_path
        self._cache_path = cache_path
        self._dry_run = dry_run
        self._always_update = always_update
        self._limite = limite
        self._data_source_id = data_source_id

    def run(self) -> None:
        """Executado no thread secundário. Abre conexões dedicadas
        (sqlite3 não pode compartilhar entre threads) e dispara o
        recálculo. Captura qualquer exceção — emite ``error``."""
        dje_conn: sqlite3.Connection | None = None
        cache_conn: sqlite3.Connection | None = None
        try:
            dje_conn = sqlite3.connect(self._dje_path)
            dje_conn.row_factory = sqlite3.Row
            cache_conn = sqlite3.connect(self._cache_path)
            cache_conn.row_factory = sqlite3.Row
            client = NotionClient(self._token)

            def _on_progress(p: int, t: int) -> None:
                self.progress.emit(p, t)

            def _on_loading(n: int) -> None:
                self.loading.emit(n)

            res: ResultadoRecalculo = recalcular_alertas_publicacoes(
                notion_client=client,
                dje_conn=dje_conn,
                cache_conn=cache_conn,
                data_source_id=self._data_source_id,
                dry_run=self._dry_run,
                always_update=self._always_update,
                limite=self._limite,
                on_progress=_on_progress,
                on_loading=_on_loading,
            )
            self.finished.emit(res)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if dje_conn is not None:
                dje_conn.close()
            if cache_conn is not None:
                cache_conn.close()


__all__ = ["RecalculoAlertasWorker"]
