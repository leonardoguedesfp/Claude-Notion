"""QObject worker thread para o recálculo das 3 propriedades de tags.

Round 10 (2026-05-07): antes do recálculo propriamente dito, o worker
**sincroniza** as bases ``Processos`` e ``Clientes`` do Notion para o
``cache.db`` local. Isso garante que mudanças manuais feitas no Notion
(ex.: edição de Vara, Fase, Partes adversas, vínculo de Cliente) sejam
refletidas nos alertas recalculados.

Roda ``recalcular_alertas_publicacoes`` em background pra não congelar
a UI.

Emite (em ordem):

1. ``sync_started(base: str)`` — começou a sync de uma base.
2. ``sync_total(base: str, total: int)`` — total de páginas a baixar.
3. ``sync_progress(base: str, processed: int, total: int)`` — durante
   download da base (cada 50 páginas).
4. ``sync_finished(base: str, added: int, existing: int, removed: int)`` —
   uma base concluída.
5. ``loading(int paginas_acumuladas)`` — durante o carregamento do
   estado atual de Publicações no Notion (já existente).
6. ``progress(int processadas, int total)`` — a cada iteração do
   recálculo (já existente).
7. ``finished(ResultadoRecalculo)`` — concluído com sucesso.
8. ``error(str)`` — exceção fatal em qualquer fase.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QObject, Signal

from notion_bulk_edit.notion_api import NotionClient

from notion_rpadv.cache.sync import sync_base_to_cache
from notion_rpadv.services.dje_recalcular_alertas import (
    DS_PUBLICACOES_DEFAULT,
    ResultadoRecalculo,
    recalcular_alertas_publicacoes,
)

#: Bases sincronizadas antes do recálculo, em ordem. Processos primeiro
#: (regras AC* dependem dele em massa), Clientes depois (regras AC04-AC06).
#: Catalogo e Tarefas não influenciam alertas.
BASES_SYNC_PREVIO: tuple[str, ...] = ("Processos", "Clientes")


class RecalculoAlertasWorker(QObject):
    """Worker stateless — ``run()`` é o único entry-point.

    Args:
        token: Notion API token.
        dje_path: caminho absoluto para o ``leitor_dje.db`` (string).
        cache_path: idem para ``cache.db``.
        dry_run: sem escrita no Notion (preview apenas).
        always_update: força ``update_page`` mesmo sem diff.
        limite: opcional — processa só N publicações.
        skip_sync: se ``True``, pula a fase de sync prévio (uso em
            testes ou quando o caller já sincronizou). Default
            ``False`` — sync sempre roda em produção.
    """

    # Fase 1 — sync prévio (Round 10)
    sync_started: Signal = Signal(str)              # base
    sync_total: Signal = Signal(str, int)           # base, total
    sync_progress: Signal = Signal(str, int, int)   # base, processado, total
    sync_finished: Signal = Signal(str, int, int, int)  # base, added, existing, removed

    # Fase 2 — recálculo (já existente)
    progress: Signal = Signal(int, int)             # processadas, total
    loading: Signal = Signal(int)                   # paginas_acumuladas

    # Resultado final
    finished: Signal = Signal(object)               # ResultadoRecalculo
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
        skip_sync: bool = False,
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
        self._skip_sync = skip_sync

    def run(self) -> None:
        """Executado no thread secundário. Sincroniza as bases necessárias,
        depois roda o recálculo. Captura qualquer exceção — emite ``error``.
        """
        dje_conn: sqlite3.Connection | None = None
        cache_conn: sqlite3.Connection | None = None
        try:
            dje_conn = sqlite3.connect(self._dje_path)
            dje_conn.row_factory = sqlite3.Row
            cache_conn = sqlite3.connect(self._cache_path)
            cache_conn.row_factory = sqlite3.Row
            client = NotionClient(self._token)

            # Fase 1 — sync prévio (Processos + Clientes)
            if not self._skip_sync:
                for base in BASES_SYNC_PREVIO:
                    self.sync_started.emit(base)

                    # Captura o total na callback pra emitir progress no
                    # formato (base, processed, total) que o slot espera.
                    total_pages: list[int] = [0]

                    def _on_total(n: int, _b: str = base) -> None:
                        total_pages[0] = n
                        self.sync_total.emit(_b, n)

                    def _on_progress(n: int, _b: str = base) -> None:
                        self.sync_progress.emit(_b, n, total_pages[0])

                    added, existing, removed = sync_base_to_cache(
                        client, cache_conn, base,
                        on_total=_on_total,
                        on_progress=_on_progress,
                    )
                    self.sync_finished.emit(base, added, existing, removed)

            # Fase 2 — recálculo
            def _on_recalc_progress(p: int, t: int) -> None:
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
                on_progress=_on_recalc_progress,
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


__all__ = ["RecalculoAlertasWorker", "BASES_SYNC_PREVIO"]
