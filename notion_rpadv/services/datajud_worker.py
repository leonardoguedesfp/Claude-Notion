"""Worker QThread da feature DataJUD (Componente 5).

Espelha ``notion_rpadv/cache/sync.py:SyncWorker``: ``QObject`` com
signals típicos do Qt (``total``, ``progress``, ``finished``, ``error``)
para integração com ``QThread`` na UI.

Diferenças vs ``SyncWorker``:

- **Paralelismo**: usa ``ThreadPoolExecutor(max_workers=4)`` para
  processar múltiplos CNJs concorrentemente. Cada worker chama
  ``enricher.enriquecer(processo, client=client)``. O ``_throttle()``
  do client é por instância — 4 workers × 2s sleep agregam ≈ 2 req/s
  efetivos (DataJud não tem rate limit oficial publicado; aceitável).

- **Cancelamento**: ``cancel()`` seta uma flag (``threading.Event``).
  Workers em execução terminam o ciclo HTTP atual (não interrompe
  request em curso); pendentes não-iniciados são cancelados via
  ``executor.shutdown(wait=False, cancel_futures=True)``. Resultados
  parciais coletados até o cancelamento são enviados ao writer e a
  planilha é gerada com o que houve.

- **Adapter cache → enricher**: o cache (``cache_db.records``)
  armazena registros com chaves slug (``"numero_do_processo"``); o
  enricher consome chaves ``notion_name`` (``"Número do processo"``).
  O worker faz a conversão antes de chamar ``enriquecer``.

- **Diagnóstico → contagem**: o signal ``finished`` carrega 4 inteiros:
  ``ok`` (DIAG_OK), ``parciais`` (DIAG_PARCIAL), ``erros`` (qualquer
  ``"Erro: ..."``), ``nao_encontrados`` (DIAG_NAO_ENCONTRADO,
  DIAG_STF, DIAG_TRIBUNAL_NS — agrupados como "não enriquecido").

Não toca SQLite. Não escreve no Notion. Stateless por instância;
descartável após ``run()``.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from notion_rpadv.services.datajud_client import DataJudClient
from notion_rpadv.services.datajud_enricher import (
    DIAG_NAO_ENCONTRADO,
    DIAG_OK,
    DIAG_PARCIAL,
    DIAG_STF,
    DIAG_TRIBUNAL_NS,
    ResultadoEnriquecimento,
    enriquecer,
)
from notion_rpadv.services.datajud_xlsx_writer import gerar_xlsx

logger = logging.getLogger("datajud.worker")


# ---------------------------------------------------------------------------
# Adapter cache → enricher
# ---------------------------------------------------------------------------


def _slug_to_notion_name(schema: dict[str, Any]) -> dict[str, str]:
    """Mapa ``chave_slug → notion_name`` para conversão do cache."""
    return {
        chave: getattr(spec, "notion_name", "")
        for chave, spec in schema.items()
        if getattr(spec, "notion_name", "")
    }


def adaptar_cache_para_enricher(
    proc_cache: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Converte registro do cache (chaves slug) para o formato esperado
    pelo ``enriquecer`` (chaves ``notion_name``).

    Preserva ``page_id`` e quaisquer outras chaves não-mapeadas
    (defensivo contra o schema evoluir).
    """
    slug_to_nn = _slug_to_notion_name(schema)
    out: dict[str, Any] = {}
    for chave, valor in proc_cache.items():
        nn = slug_to_nn.get(chave)
        if nn:
            out[nn] = valor
        else:
            # Preserva chaves especiais (page_id) e outras não-mapeadas.
            out[chave] = valor
    return out


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class DataJudWorker(QObject):
    """Worker do DataJUD para execução em ``QThread``.

    Emits:
        total(n: int)                    — emitido uma vez no início
                                           com o total de CNJs.
        progress(count: int, cnj: str)   — emitido a cada CNJ concluído.
                                           ``count`` é cumulativo
                                           (1, 2, ..., n).
        finished(output_path: str, ok: int, parciais: int, erros: int,
                 nao_encontrados: int) — emitido após gravar o xlsx.
                                          ``output_path`` é a string do
                                          path absoluto.
        error(message: str)              — erro fatal não-recuperável
                                           (ex.: falha ao gravar xlsx).
                                           ``finished`` NÃO é emitido
                                           quando ``error`` é.
        cancelled()                      — emitido se ``cancel()`` foi
                                           chamado durante a execução.
                                           ``finished`` AINDA é emitido
                                           depois (com totais parciais),
                                           porque a planilha já foi
                                           gerada com o que houve até
                                           o cancelamento.

    Args:
        processos: lista de registros do cache (cada dict com chaves
            slug do schema + ``page_id``). Worker faz a conversão pra
            ``notion_name`` internamente.
        client: instância de ``DataJudClient`` reutilizada pelos 4
            threads (rate limit aplicado por instância).
        schema: schema da base Processos (``dict[chave_slug, PropSpec]``).
        output_path: caminho absoluto da planilha de saída.
        max_workers: tamanho do pool (default 4 — empírico, ~2 req/s
            agregados com o throttle do client).
    """

    total: Signal     = Signal(int)
    progress: Signal  = Signal(int, str)
    finished: Signal  = Signal(str, int, int, int, int)
    error: Signal     = Signal(str)
    cancelled: Signal = Signal()

    def __init__(
        self,
        processos: list[dict[str, Any]],
        client: DataJudClient,
        schema: dict[str, Any],
        output_path: Path,
        max_workers: int = 4,
    ) -> None:
        super().__init__()
        self._processos = processos
        self._client = client
        self._schema = schema
        self._output_path = output_path
        self._max_workers = max_workers
        self._cancel_event = threading.Event()

    @Slot()
    def cancel(self) -> None:
        """Sinaliza cancelamento.

        Workers em execução terminam o ciclo HTTP atual; pendentes não
        iniciados são cancelados. Ao final, a planilha é gerada com
        os resultados coletados até o cancelamento.
        """
        logger.info("DataJUD worker: cancelamento solicitado")
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @Slot()
    def run(self) -> None:
        """Loop principal — chamado pelo ``QThread.started`` signal."""
        try:
            self._run_impl()
        except Exception as exc:  # noqa: BLE001
            logger.exception("DataJUD worker: erro fatal")
            self.error.emit(f"Erro fatal: {exc}")

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _run_impl(self) -> None:
        n = len(self._processos)
        self.total.emit(n)

        if n == 0:
            # Caminho degenerado: sem processos, nem chama o pool —
            # emite finished com zeros.
            self._gerar_xlsx_e_emitir_finished([])
            return

        resultados: list[ResultadoEnriquecimento | None] = [None] * n
        processed = 0
        executor = ThreadPoolExecutor(max_workers=self._max_workers)
        try:
            future_to_idx: dict[Future[ResultadoEnriquecimento], int] = {}
            for i, proc_cache in enumerate(self._processos):
                if self._cancel_event.is_set():
                    break
                proc_enricher = adaptar_cache_para_enricher(
                    proc_cache, self._schema,
                )
                fut = executor.submit(self._processar_um, proc_enricher, i)
                future_to_idx[fut] = i

            for fut in as_completed(future_to_idx):
                if self._cancel_event.is_set():
                    # Cancela pendentes; ainda processa o que já voltou.
                    executor.shutdown(wait=False, cancel_futures=True)
                idx = future_to_idx[fut]
                try:
                    res = fut.result()
                except Exception as exc:  # noqa: BLE001
                    cnj = str(
                        self._processos[idx].get("numero_do_processo")
                        or "?"
                    )
                    page_id = str(self._processos[idx].get("page_id") or "")
                    res = ResultadoEnriquecimento(
                        numero_cnj=cnj,
                        page_id=page_id,
                        diagnostico=f"Erro: {exc}"[:120],
                        propriedades_sugeridas={},
                        fontes_tribunal=[],
                        movimentos_brutos_por_grau={},
                    )
                resultados[idx] = res
                processed += 1
                self.progress.emit(processed, res.numero_cnj)

                if self._cancel_event.is_set():
                    break
        finally:
            executor.shutdown(wait=True)

        if self._cancel_event.is_set():
            self.cancelled.emit()

        resultados_validos = [r for r in resultados if r is not None]
        self._gerar_xlsx_e_emitir_finished(resultados_validos)

    def _processar_um(
        self, proc_enricher: dict[str, Any], idx: int,
    ) -> ResultadoEnriquecimento:
        """Chamado por cada thread do pool — wrapper sobre ``enriquecer``."""
        return enriquecer(proc_enricher, client=self._client)

    def _gerar_xlsx_e_emitir_finished(
        self, resultados: list[ResultadoEnriquecimento],
    ) -> None:
        """Conta diagnósticos, chama o writer, emite ``finished``."""
        ok = parciais = erros = nao_encontrados = 0
        for r in resultados:
            d = r.diagnostico
            if d == DIAG_OK:
                ok += 1
            elif d == DIAG_PARCIAL:
                parciais += 1
            elif d in (DIAG_NAO_ENCONTRADO, DIAG_STF, DIAG_TRIBUNAL_NS):
                nao_encontrados += 1
            elif d.startswith("Erro:"):
                erros += 1
            else:
                # Diagnóstico desconhecido — agrupa em erros pra não
                # esconder problemas inesperados.
                erros += 1

        # Indexa cache original (slugs) por page_id pro writer
        processos_cache: dict[str, dict[str, Any]] = {}
        for proc in self._processos:
            pid = str(proc.get("page_id") or "")
            if pid:
                processos_cache[pid] = proc

        try:
            gerar_xlsx(
                resultados,
                processos_cache=processos_cache,
                schema=self._schema,
                output_path=self._output_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("DataJUD worker: erro ao gerar xlsx")
            self.error.emit(f"Erro ao gerar planilha: {exc}")
            return

        self.finished.emit(
            str(self._output_path),
            ok, parciais, erros, nao_encontrados,
        )
