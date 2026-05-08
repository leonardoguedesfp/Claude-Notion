"""Smoke tests do ``RecalculoAlertasWorker`` Round 10.

Foco em invariantes da API pública (signals, constantes, kwarg
``skip_sync``). O fluxo end-to-end é coberto por smoke manual no app
real — mockar QObject + 4 signals da fase de sync + 2 da fase de
recálculo seria caro e frágil.
"""
from __future__ import annotations

from notion_rpadv.services.dje_recalculo_worker import (
    BASES_SYNC_PREVIO,
    RecalculoAlertasWorker,
)


def test_bases_sync_previo_inclui_processos_e_clientes() -> None:
    """As bases que influenciam alertas (Processos, Clientes) são
    sincronizadas antes do recálculo. Catalogo e Tarefas ficam fora
    intencionalmente — não afetam regras."""
    assert BASES_SYNC_PREVIO == ("Processos", "Clientes")


def test_bases_sync_previo_e_tupla_imutavel() -> None:
    """Detecta regressão pra list mutável."""
    assert isinstance(BASES_SYNC_PREVIO, tuple)


def test_worker_expoe_signals_da_fase_de_sync() -> None:
    """Round 10 — worker ganhou 4 signals novos pra UI acompanhar a
    sync prévia."""
    sig_names = (
        "sync_started",
        "sync_total",
        "sync_progress",
        "sync_finished",
    )
    for name in sig_names:
        assert hasattr(RecalculoAlertasWorker, name), (
            f"signal {name!r} ausente no RecalculoAlertasWorker"
        )


def test_worker_preserva_signals_da_fase_de_recalculo() -> None:
    """Os signals da fase de recálculo (loading, progress, finished,
    error) seguem expostos — não foram removidos no Round 10."""
    for name in ("loading", "progress", "finished", "error"):
        assert hasattr(RecalculoAlertasWorker, name), (
            f"signal {name!r} ausente no RecalculoAlertasWorker"
        )


def test_worker_aceita_skip_sync_kwarg() -> None:
    """``skip_sync=True`` permite testes/CLI pular a fase de sync.
    Default é ``False`` — em produção sempre sincroniza."""
    w = RecalculoAlertasWorker(
        token="x", dje_path="dje.db", cache_path="cache.db",
        skip_sync=True,
    )
    assert w._skip_sync is True

    w2 = RecalculoAlertasWorker(
        token="x", dje_path="dje.db", cache_path="cache.db",
    )
    assert w2._skip_sync is False
