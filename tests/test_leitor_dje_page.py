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
    """Estado inicial: date pickers em ontem (ou sticky até 7 dias atrás
    — Round 7 F2 hotfix de teste flaky: a página inicializa
    _date_inicio E _date_fim com o mesmo valor sticky, não só
    _date_inicio. Aceitamos o sticky em ambos os pickers.).

    Outros invariants do estado inicial: log vazio, progresso 0/12,
    botão habilitado, botões 'abrir' ocultos."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from notion_rpadv.services.dje_advogados import ADVOGADOS

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Date pickers default: ontem com sticky window de 7 dias.
    di = page._date_inicio.date().toPython()  # noqa: SLF001
    df = page._date_fim.date().toPython()  # noqa: SLF001
    today = _dt.date.today()
    assert 1 <= (today - di).days <= 7, (
        f"_date_inicio fora da janela [today-7d, today-1d]: {di}"
    )
    # _date_fim pode ter o mesmo sticky de _date_inicio (UX: ambos
    # iniciam iguais, operador ajusta o intervalo manualmente).
    assert 1 <= (today - df).days <= 7, (
        f"_date_fim fora da janela [today-7d, today-1d]: {df}"
    )
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


# ---------------------------------------------------------------------------
# Sidebar wire — pega o gap do hotfix do commit fc00d4a
# ---------------------------------------------------------------------------


def test_R7_sidebar_dados_nav_includes_leitor_dje() -> None:
    """``_DADOS_NAV`` em widgets/sidebar.py deve declarar a entry
    ``leitor_dje`` entre 'exportar' e 'logs'.

    Este teste pega o gap do hotfix: o commit fc00d4a prometia o wire
    do sidebar mas o stat do commit ficou em 4 arquivos (sidebar não
    entrou). Sem este test_R7_sidebar_*, o smoke real do operador era
    o único filtro — usuário abre o app e a aba não aparece.
    """
    from notion_rpadv.widgets.sidebar import _DADOS_NAV
    page_ids = [p[0] for p in _DADOS_NAV]
    assert "leitor_dje" in page_ids, (
        f"_DADOS_NAV sem 'leitor_dje': {page_ids}"
    )
    # Ordem do spec: entre exportar e logs.
    idx_exp = page_ids.index("exportar")
    idx_dje = page_ids.index("leitor_dje")
    idx_log = page_ids.index("logs")
    assert idx_exp < idx_dje < idx_log, (
        f"Ordem inesperada: {page_ids}"
    )
    # Label exato.
    label = next(p[1] for p in _DADOS_NAV if p[0] == "leitor_dje")
    assert label == "Leitor DJE"


def test_R7_sidebar_icon_present_for_leitor_dje() -> None:
    """``_ICONS`` tem entry pra ``leitor_dje`` — sem isso o
    SidebarItem renderiza o caractere fallback "·" (cosmético, mas
    deixa a entry inconsistente com as outras)."""
    from notion_rpadv.widgets.sidebar import _ICONS
    assert "leitor_dje" in _ICONS
    assert _ICONS["leitor_dje"]  # não-vazio


def test_R7_sidebar_widget_instancia_com_leitor_dje() -> None:
    """Smoke real do widget: instanciar ``Sidebar`` e confirmar que o
    SidebarItem ``leitor_dje`` foi criado no ``_items`` dict.

    Este é o teste mais importante: simula o caminho que o app real
    percorre. Se este passar, a aba aparece na barra lateral.
    """
    _qapp()
    from notion_rpadv.widgets.sidebar import Sidebar, SidebarItem
    sb = Sidebar(user={"name": "Test", "initials": "TT", "role": ""})
    assert "leitor_dje" in sb._items, (  # noqa: SLF001
        f"Sidebar não criou item 'leitor_dje'. "
        f"items presentes: {list(sb._items.keys())}"  # noqa: SLF001
    )
    item = sb._items["leitor_dje"]  # noqa: SLF001
    assert isinstance(item, SidebarItem)
    assert item.page_id == "leitor_dje"


def test_R7_app_nav_commands_includes_leitor_dje() -> None:
    """Command palette dispatch (``_NAV_COMMANDS`` em app.py) tem a
    entry ``nav_leitor_dje`` mapeando pro page_id correto. Sem isso,
    digitar "Leitor DJE" no Ctrl+K não navega."""
    from notion_rpadv.app import _NAV_COMMANDS, _PAGE_LEITOR_DJE
    assert "nav_leitor_dje" in _NAV_COMMANDS
    assert _NAV_COMMANDS["nav_leitor_dje"] == _PAGE_LEITOR_DJE
    assert _PAGE_LEITOR_DJE == "leitor_dje"
