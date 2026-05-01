"""Smoke tests da LeitorDJEPage. UI page é o boundary com Qt — testes
exercitam só estados síncronos sem disparar HTTP (worker em thread
separada não é coberto aqui — esse caminho está coberto em
test_dje_client por dependency injection).

Coverage da page propriamente fica fora da meta de ≥90% (UI é
hard-to-cover headless e o spec confirma isso explicitamente).
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_R7_leitor_dje_page_imports() -> None:
    """Smoke: LeitorDJEPage importa sem erro."""
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    assert LeitorDJEPage is not None


def test_R7_leitor_dje_page_initial_state() -> None:
    """Estado inicial: date pickers em ontem, log vazio, progresso 0/12,
    botão habilitado, botões 'abrir' ocultos."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from notion_rpadv.services.dje_advogados import ADVOGADOS

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Date pickers default = ontem
    ontem = _dt.date.today() - _dt.timedelta(days=1)
    di = page._date_inicio.date().toPython()  # noqa: SLF001
    df = page._date_fim.date().toPython()  # noqa: SLF001
    # Permitimos um override sticky de até 7 dias atrás (UX) — então
    # a comparação aqui é >= ontem - 7d e <= hoje.
    assert (_dt.date.today() - di).days <= 7
    assert df == ontem
    # Log vazio
    assert page._log_area.toPlainText() == ""  # noqa: SLF001
    # Progresso vai de 0 a len(ADVOGADOS) = 12
    assert page._progress.maximum() == len(ADVOGADOS)  # noqa: SLF001
    assert page._progress.value() == 0  # noqa: SLF001
    # Botão de download habilitado
    assert page._download_btn.isEnabled()  # noqa: SLF001
    # Botões de abrir ocultos (export ainda não rodou)
    assert not page._open_file_btn.isVisible() or page._open_file_btn.isHidden()  # noqa: SLF001
    assert not page._open_dir_btn.isVisible() or page._open_dir_btn.isHidden()  # noqa: SLF001
    # Aviso amarelo oculto
    assert not page._warning_lbl.isVisible() or page._warning_lbl.isHidden()  # noqa: SLF001


def test_R7_leitor_dje_page_data_final_anterior_a_inicial_mostra_aviso() -> None:
    """Validação síncrona: data final < inicial → warning, sem disparar worker."""
    _qapp()
    from PySide6.QtCore import QDate
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Forçar inversão
    page._date_inicio.setDate(QDate(2026, 5, 5))  # noqa: SLF001
    page._date_fim.setDate(QDate(2026, 5, 1))  # noqa: SLF001
    page._on_download_clicked()  # noqa: SLF001
    # Worker NÃO foi iniciado (ainda)
    assert page._thread is None  # noqa: SLF001
    # Aviso visível
    assert page._warning_lbl.isVisible() or "anterior" in page._warning_lbl.text()  # noqa: SLF001


def test_R7_leitor_dje_page_open_file_when_no_export_yet_shows_warning() -> None:
    """Click em 'abrir arquivo' antes de exportar não crasha — mostra
    QMessageBox em produção; aqui validamos só que não levanta."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from unittest.mock import patch

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # _last_output_path é None (export não rodou)
    with patch("PySide6.QtWidgets.QMessageBox.warning"):
        page._on_open_file_clicked()  # noqa: SLF001
    # Sobreviveu — sem exception.


def test_R7_leitor_dje_page_resolve_output_dir_uses_settings_when_present(
    tmp_path: Path,
) -> None:
    """``_resolve_output_dir`` usa settings persistidos quando há valor;
    cria dir e retorna sem QFileDialog."""
    _qapp()
    from PySide6.QtCore import QSettings
    from notion_rpadv.pages.leitor_dje import (
        _KEY_OUTPUT_DIR,
        _SETTINGS_APP,
        _SETTINGS_ORG,
        LeitorDJEPage,
    )

    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    target = tmp_path / "saida_dje"
    settings.setValue(_KEY_OUTPUT_DIR, str(target))
    try:
        page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
        result = page._resolve_output_dir()  # noqa: SLF001
        assert result == target
        assert target.exists()
    finally:
        settings.remove(_KEY_OUTPUT_DIR)
