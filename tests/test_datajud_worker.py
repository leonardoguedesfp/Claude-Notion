"""Testes do worker DataJUD (Componente 5).

Cobre signals, contagem por diagnóstico, cancelamento, chamada única
ao writer, e tratamento de erro fatal.

Mock pattern: ``MagicMock(spec=DataJudClient)`` + ``monkeypatch`` no
``enriquecer`` para retornar ``ResultadoEnriquecimento`` controlado
sem chamada à API real.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from notion_rpadv.services.datajud_client import DataJudClient
from notion_rpadv.services.datajud_enricher import (
    DIAG_NAO_ENCONTRADO,
    DIAG_OK,
    DIAG_PARCIAL,
    DIAG_STF,
    ResultadoEnriquecimento,
)
from notion_rpadv.services.datajud_worker import (
    DataJudWorker,
    adaptar_cache_para_enricher,
)


# ---------------------------------------------------------------------------
# Fixtures comuns
# ---------------------------------------------------------------------------


@dataclass
class _SpecMock:
    notion_name: str
    tipo: str = "rich_text"
    label: str = ""
    editavel: bool = True
    obrigatorio: bool = False
    opcoes: tuple[str, ...] = field(default_factory=tuple)


def _schema_minimo() -> dict[str, _SpecMock]:
    return {
        "numero_do_processo": _SpecMock("Número do processo", "title"),
        "tribunal":           _SpecMock("Tribunal", "select"),
        "instancia":          _SpecMock("Instância", "select"),
        "vara":               _SpecMock("Vara"),
    }


def _proc_cache(page_id: str, cnj: str, tribunal: str = "TRT/10",
                instancia: str = "1º grau") -> dict[str, Any]:
    return {
        "page_id":             page_id,
        "numero_do_processo":  cnj,
        "tribunal":            tribunal,
        "instancia":           instancia,
    }


def _resultado_factory(diagnostico: str, page_id: str = "p1",
                       cnj: str = "0000000-00.0000.0.00.0000",
                       ) -> ResultadoEnriquecimento:
    return ResultadoEnriquecimento(
        numero_cnj=cnj,
        page_id=page_id,
        diagnostico=diagnostico,
        propriedades_sugeridas={},
        fontes_tribunal=[],
        movimentos_brutos_por_grau={},
    )


def _make_worker(
    processos: list[dict[str, Any]],
    output_path: Path,
    schema: dict[str, _SpecMock] | None = None,
    max_workers: int = 4,
) -> DataJudWorker:
    """Factory devolve mock por chamada — comportamento espelha o
    cenário real onde cada thread do pool tem seu próprio client."""
    def _factory() -> DataJudClient:
        return MagicMock(spec=DataJudClient)

    return DataJudWorker(
        processos=processos,
        client_factory=_factory,
        schema=schema or _schema_minimo(),
        output_path=output_path,
        max_workers=max_workers,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def test_adapter_converte_slugs_para_notion_names() -> None:
    """``numero_do_processo`` (slug) → ``"Número do processo"`` (notion_name)."""
    proc_cache = {
        "page_id":             "abc",
        "numero_do_processo":  "0000123-45.2024.5.10.0001",
        "tribunal":            "TRT/10",
        "instancia":           "1º grau",
        "vara":                "13",
    }
    out = adaptar_cache_para_enricher(proc_cache, _schema_minimo())
    assert out["Número do processo"] == "0000123-45.2024.5.10.0001"
    assert out["Tribunal"] == "TRT/10"
    assert out["Instância"] == "1º grau"
    assert out["Vara"] == "13"
    # page_id preservado
    assert out["page_id"] == "abc"


def test_adapter_preserva_chaves_nao_mapeadas() -> None:
    """Chaves do cache que não estão no schema (ex.: page_id) ficam preservadas."""
    proc_cache = {
        "page_id":     "abc",
        "campo_extra": "valor",
        "tribunal":    "TJDFT",
    }
    out = adaptar_cache_para_enricher(proc_cache, _schema_minimo())
    assert out["page_id"] == "abc"
    assert out["campo_extra"] == "valor"
    assert out["Tribunal"] == "TJDFT"


# ---------------------------------------------------------------------------
# 1) total + progress emitidos em ordem
# ---------------------------------------------------------------------------


def test_worker_emite_total_e_progress_em_ordem(tmp_path: Path) -> None:
    processos = [
        _proc_cache("p1", "0000123-45.2024.5.10.0001"),
        _proc_cache("p2", "0000234-56.2024.5.10.0002"),
        _proc_cache("p3", "0000345-67.2024.5.10.0003"),
    ]
    worker = _make_worker(processos, tmp_path / "out.xlsx")

    total_calls: list[int] = []
    progress_calls: list[tuple[int, str]] = []
    worker.total.connect(lambda n: total_calls.append(n))
    worker.progress.connect(
        lambda count, cnj: progress_calls.append((count, cnj)),
    )

    fakes = [
        _resultado_factory(DIAG_OK, "p1", "0000123-45.2024.5.10.0001"),
        _resultado_factory(DIAG_OK, "p2", "0000234-56.2024.5.10.0002"),
        _resultado_factory(DIAG_OK, "p3", "0000345-67.2024.5.10.0003"),
    ]
    with patch(
        "notion_rpadv.services.datajud_worker.enriquecer",
        side_effect=fakes,
    ):
        worker.run()

    assert total_calls == [3]
    # progress.count vai de 1 a 3, cumulativo (ordem dos resultados pode
    # variar com paralelismo, mas count é monotônico).
    counts = [c for c, _cnj in progress_calls]
    assert counts == [1, 2, 3]
    cnjs_emitidos = {cnj for _c, cnj in progress_calls}
    assert cnjs_emitidos == {
        "0000123-45.2024.5.10.0001",
        "0000234-56.2024.5.10.0002",
        "0000345-67.2024.5.10.0003",
    }


# ---------------------------------------------------------------------------
# 2) finished com contagens corretas por diagnóstico
# ---------------------------------------------------------------------------


def test_worker_emite_finished_com_contagens_corretas(tmp_path: Path) -> None:
    """OK + Dados parciais + Não encontrado + STF + Tribunal não suportado +
    Erro: ... — buckets do signal finished são (ok, parciais, erros, nao_encontrados)."""
    processos = [_proc_cache(f"p{i}", f"000000{i}-00.0000.0.00.0000")
                 for i in range(1, 7)]
    worker = _make_worker(processos, tmp_path / "out.xlsx")

    fakes = [
        _resultado_factory(DIAG_OK,                "p1"),
        _resultado_factory(DIAG_OK,                "p2"),
        _resultado_factory(DIAG_PARCIAL,           "p3"),
        _resultado_factory(DIAG_NAO_ENCONTRADO,    "p4"),
        _resultado_factory(DIAG_STF,               "p5"),
        _resultado_factory("Erro: HTTP 503",       "p6"),
    ]

    finished_payload: list[tuple[Any, ...]] = []
    worker.finished.connect(lambda *args: finished_payload.append(args))

    with patch(
        "notion_rpadv.services.datajud_worker.enriquecer",
        side_effect=fakes,
    ):
        worker.run()

    assert len(finished_payload) == 1
    output_path, ok, parciais, erros, nao_encontrados = finished_payload[0]
    assert output_path == str(tmp_path / "out.xlsx")
    assert ok == 2               # 2 OK
    assert parciais == 1         # 1 Dados parciais
    assert erros == 1            # 1 Erro: HTTP 503
    assert nao_encontrados == 2  # 1 Não encontrado + 1 STF não coberto


# ---------------------------------------------------------------------------
# 3) cancelamento para o processamento
# ---------------------------------------------------------------------------


def test_worker_cancelamento_para_processamento(tmp_path: Path) -> None:
    """cancel() seta a flag; run() emite cancelled e termina antes de
    processar todos os CNJs."""
    processos = [_proc_cache(f"p{i}", f"000000{i}-00.0000.0.00.0000")
                 for i in range(1, 11)]  # 10 processos
    worker = _make_worker(processos, tmp_path / "out.xlsx", max_workers=1)

    cancel_event = threading.Event()
    cancelled_emitted = threading.Event()
    finished_emitted = threading.Event()
    progress_count = 0

    def on_progress(count: int, _cnj: str) -> None:
        nonlocal progress_count
        progress_count = count
        if count == 2:
            # Após 2 processados, cancela
            worker.cancel()
            cancel_event.set()

    worker.progress.connect(on_progress)
    worker.cancelled.connect(lambda: cancelled_emitted.set())
    worker.finished.connect(lambda *_: finished_emitted.set())

    fake_resultado = _resultado_factory(DIAG_OK, "px")
    with patch(
        "notion_rpadv.services.datajud_worker.enriquecer",
        return_value=fake_resultado,
    ):
        worker.run()

    assert worker.is_cancelled()
    assert cancelled_emitted.is_set()
    # finished ainda é emitido (com totais parciais)
    assert finished_emitted.is_set()
    # Não chegou aos 10 (cancelou em 2; com max_workers=1 a serialização
    # é estrita, mas pode haver até 1 ciclo extra antes do cancel
    # propagar)
    assert progress_count < 10


# ---------------------------------------------------------------------------
# 4) Erro fatal (writer falha) → signal error, finished NÃO emitido
# ---------------------------------------------------------------------------


def test_worker_propaga_erro_fatal_via_signal_error(tmp_path: Path) -> None:
    """Quando ``gerar_xlsx`` levanta, ``error`` é emitido e ``finished`` não."""
    processos = [_proc_cache("p1", "0000123-45.2024.5.10.0001")]
    worker = _make_worker(processos, tmp_path / "out.xlsx")

    finished_calls: list[Any] = []
    error_calls: list[str] = []
    worker.finished.connect(lambda *_: finished_calls.append(_))
    worker.error.connect(lambda msg: error_calls.append(msg))

    fake_resultado = _resultado_factory(DIAG_OK, "p1")
    with patch(
        "notion_rpadv.services.datajud_worker.enriquecer",
        return_value=fake_resultado,
    ), patch(
        "notion_rpadv.services.datajud_worker.gerar_xlsx",
        side_effect=OSError("disco cheio"),
    ):
        worker.run()

    assert error_calls
    assert "disco cheio" in error_calls[0]
    assert not finished_calls


# ---------------------------------------------------------------------------
# 5) gerar_xlsx chamado uma vez no final
# ---------------------------------------------------------------------------


def test_worker_chama_gerar_xlsx_uma_vez_no_final(tmp_path: Path) -> None:
    processos = [
        _proc_cache("p1", "0000123-45.2024.5.10.0001"),
        _proc_cache("p2", "0000234-56.2024.5.10.0002"),
    ]
    worker = _make_worker(processos, tmp_path / "out.xlsx")

    fakes = [
        _resultado_factory(DIAG_OK, "p1"),
        _resultado_factory(DIAG_OK, "p2"),
    ]
    with patch(
        "notion_rpadv.services.datajud_worker.enriquecer",
        side_effect=fakes,
    ), patch(
        "notion_rpadv.services.datajud_worker.gerar_xlsx",
    ) as mock_gerar:
        worker.run()

    assert mock_gerar.call_count == 1
    args, kwargs = mock_gerar.call_args
    # Posicional: lista de resultados
    resultados_arg = args[0] if args else kwargs.get("resultados")
    assert resultados_arg is not None
    assert len(resultados_arg) == 2
    # Caller passa output_path correto
    assert kwargs.get("output_path") == tmp_path / "out.xlsx"
    # Schema é encaminhado
    assert "schema" in kwargs
    # processos_cache indexado por page_id
    pc = kwargs.get("processos_cache") or {}
    assert "p1" in pc
    assert "p2" in pc


# ---------------------------------------------------------------------------
# 6) max_workers default 4
# ---------------------------------------------------------------------------


def test_worker_max_workers_4_default(tmp_path: Path) -> None:
    """Construtor sem ``max_workers`` usa 4."""
    worker = DataJudWorker(
        processos=[],
        client_factory=lambda: MagicMock(spec=DataJudClient),
        schema=_schema_minimo(),
        output_path=tmp_path / "out.xlsx",
    )
    assert worker._max_workers == 4


def test_worker_chama_factory_uma_vez_por_thread(tmp_path: Path) -> None:
    """Como o ThreadPoolExecutor reusa threads, factory é chamada no
    máximo ``max_workers`` vezes — não ``len(processos)``. Confirma
    que clients são reutilizados via threading.local."""
    processos = [_proc_cache(f"p{i}", f"000000{i}-00.0000.0.00.0000")
                 for i in range(1, 11)]  # 10 processos
    factory_calls: list[None] = []

    def _factory() -> DataJudClient:
        factory_calls.append(None)
        return MagicMock(spec=DataJudClient)

    worker = DataJudWorker(
        processos=processos,
        client_factory=_factory,
        schema=_schema_minimo(),
        output_path=tmp_path / "out.xlsx",
        max_workers=4,
    )

    fake_resultado = _resultado_factory(DIAG_OK, "px")
    with patch(
        "notion_rpadv.services.datajud_worker.enriquecer",
        return_value=fake_resultado,
    ):
        worker.run()

    # No máximo 4 (max_workers); pode ser menos se o pool reusou
    # threads aggressivamente. Crucial: nunca == 10 (1 por processo).
    assert len(factory_calls) <= 4
    # E pelo menos 1 (fluxo OK)
    assert len(factory_calls) >= 1


# ---------------------------------------------------------------------------
# 7) Lista vazia ainda emite finished com zeros
# ---------------------------------------------------------------------------


def test_worker_cancel_retorna_imediatamente(tmp_path: Path) -> None:
    """``cancel()`` não pode aguardar workers — só seta a Event.
    Mesmo com workers em execução, retorna em < 100ms.

    Cenário: 100 processos no pool, ``enriquecer`` mockado pra
    bloquear num ``threading.Event`` (simula trabalho HTTP em curso).
    O ``cancel()`` é cronometrado: tempo entre o clique e o retorno.
    Workers terminam quando o barrier é liberado.
    """
    import time

    processos = [
        _proc_cache(f"p{i}", f"{i:07d}-00.0000.0.00.0000")
        for i in range(100)
    ]
    worker = _make_worker(processos, tmp_path / "out.xlsx", max_workers=4)

    barrier = threading.Event()

    def _slow_enriquecer(*_a: Any, **_k: Any) -> Any:
        barrier.wait(timeout=10.0)
        return _resultado_factory(DIAG_OK, "px")

    # ``run`` em thread Python pura (sem QThread) — basta pra exercitar
    # o ThreadPoolExecutor interno do worker.
    runner = threading.Thread(target=worker.run, daemon=True)

    with patch(
        "notion_rpadv.services.datajud_worker.enriquecer",
        side_effect=_slow_enriquecer,
    ), patch(
        "notion_rpadv.services.datajud_worker.gerar_xlsx",
    ):
        runner.start()
        # Espera o pool pegar pelo menos um future (eles vão bloquear
        # no barrier — timeout de polling pequeno garante CI estável).
        time.sleep(0.2)

        # Cronometra o cancel.
        t0 = time.perf_counter()
        worker.cancel()
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 100, (
            f"cancel() levou {elapsed_ms:.1f}ms; deve retornar em <100ms"
        )
        assert worker.is_cancelled()

        # Libera os workers presos no barrier; runner vai finalizar
        # normalmente (com gerar_xlsx mockado).
        barrier.set()
        runner.join(timeout=10.0)
        assert not runner.is_alive(), "runner não terminou após cancel"


def test_worker_lista_vazia_emite_finished_com_zeros(tmp_path: Path) -> None:
    worker = _make_worker([], tmp_path / "out.xlsx")
    finished_payload: list[tuple[Any, ...]] = []
    worker.finished.connect(lambda *args: finished_payload.append(args))

    with patch("notion_rpadv.services.datajud_worker.gerar_xlsx"):
        worker.run()

    assert len(finished_payload) == 1
    _path, ok, parciais, erros, naoenc = finished_payload[0]
    assert (ok, parciais, erros, naoenc) == (0, 0, 0, 0)
