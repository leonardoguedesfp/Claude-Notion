"""Smoke tests da DataJUDPage. UI page é o boundary com Qt — testes
exercitam estados síncronos sem disparar HTTP (worker em thread
separada já é coberto em test_datajud_worker).

Coverage da page propriamente fica fora da meta de ≥90% (UI é
hard-to-cover headless).
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


def _qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# ---------------------------------------------------------------------------
# 1) Página renderiza sem erro
# ---------------------------------------------------------------------------


def test_pagina_renderiza_sem_erro() -> None:
    """Smoke: DataJUDPage importa e instancia sem crash."""
    _qapp()
    from notion_rpadv.pages.datajud import DataJUDPage

    conn = MagicMock()
    # cache_db.get_all_records é chamado em _refresh_modo_a_estimativa.
    # MagicMock vai falhar — preciso interceptar antes do __init__.
    with _patch_cache_records([]):
        page = DataJUDPage(conn=conn, token="dummy")
    assert page is not None
    # Estado inicial: Modo A (stack interno em índice 0)
    assert page._stack_modos.currentIndex() == 0  # noqa: SLF001


# ---------------------------------------------------------------------------
# 2) Alternância Modo A ↔ Modo B
# ---------------------------------------------------------------------------


def test_alternancia_modo_a_modo_b() -> None:
    """Clicar no link superior alterna entre Modo A e Modo B."""
    _qapp()
    from notion_rpadv.pages.datajud import DataJUDPage

    with _patch_cache_records([]):
        page = DataJUDPage(conn=MagicMock(), token="dummy")
    # Estado inicial: Modo A
    assert page._stack_modos.currentIndex() == 0  # noqa: SLF001
    assert "lista manual" in page._link_modo.text().lower()  # noqa: SLF001

    # Click no link → Modo B
    page._link_modo.click()  # noqa: SLF001
    assert page._stack_modos.currentIndex() == 1  # noqa: SLF001
    # Modo B começa no Step 1 (primeiro do container interno)
    assert page._modo_b_container.currentIndex() == 0  # noqa: SLF001
    assert "varredura" in page._link_modo.text().lower()  # noqa: SLF001

    # Click novamente → volta pro Modo A
    page._link_modo.click()  # noqa: SLF001
    assert page._stack_modos.currentIndex() == 0  # noqa: SLF001


# ---------------------------------------------------------------------------
# 3) Modo B Step 1 — avança com CNJs válidos
# ---------------------------------------------------------------------------


def test_modo_b_step1_avanca_com_cnjs_validos() -> None:
    """Cola CNJ válido no textarea → botão 'Avançar' habilita."""
    _qapp()
    from notion_rpadv.pages.datajud import DataJUDPage

    with _patch_cache_records([]):
        page = DataJUDPage(conn=MagicMock(), token="dummy")

    page._link_modo.click()  # vai pra Modo B  # noqa: SLF001
    step1 = page._step1  # noqa: SLF001
    assert step1._avancar_btn.isEnabled() is False  # noqa: SLF001

    # Cola CNJ válido (do Componente 2)
    step1._textarea.setPlainText("0000449-71.2025.5.10.0003")  # noqa: SLF001

    assert step1._avancar_btn.isEnabled() is True  # noqa: SLF001
    assert len(step1._cnjs) == 1  # noqa: SLF001
    assert step1._cnjs[0].valido is True  # noqa: SLF001


# ---------------------------------------------------------------------------
# 4) Modo B Step 1 — bloqueia avanço sem CNJs válidos
# ---------------------------------------------------------------------------


def test_modo_b_step1_bloqueia_avanco_sem_cnjs_validos() -> None:
    """Texto com tudo inválido → 'Avançar' fica desabilitado."""
    _qapp()
    from notion_rpadv.pages.datajud import DataJUDPage

    with _patch_cache_records([]):
        page = DataJUDPage(conn=MagicMock(), token="dummy")

    page._link_modo.click()  # noqa: SLF001
    step1 = page._step1  # noqa: SLF001

    # Cola lixo
    step1._textarea.setPlainText("12345; abc; xyz")  # noqa: SLF001
    assert step1._avancar_btn.isEnabled() is False  # noqa: SLF001
    # Status mostra que tem inválidos
    assert "inválido" in step1._status_label.text().lower()  # noqa: SLF001


# ---------------------------------------------------------------------------
# 5) Página integrada ao MainWindow — sidebar e command palette
# ---------------------------------------------------------------------------


def test_pagina_integrada_ao_main_window() -> None:
    """Verifica que sidebar e app.py acolheram a aba DataJUD:
    item 'datajud' na _DADOS_NAV, ícone configurado, e
    nav_datajud em _NAV_COMMANDS do app."""
    from notion_rpadv.widgets.sidebar import _DADOS_NAV, _ICONS
    page_ids_dados = [t[0] for t in _DADOS_NAV]
    assert "datajud" in page_ids_dados, (
        f"sidebar._DADOS_NAV não tem 'datajud': {page_ids_dados}"
    )
    assert _ICONS.get("datajud") == "🔎"

    # app.py — nav_datajud → _PAGE_DATAJUD
    from notion_rpadv.app import _NAV_COMMANDS, _PAGE_DATAJUD
    assert _NAV_COMMANDS.get("nav_datajud") == _PAGE_DATAJUD
    assert _PAGE_DATAJUD == "datajud"


def test_sidebar_renderiza_com_item_datajud() -> None:
    """Smoke: Sidebar instancia o SidebarItem 'datajud'."""
    _qapp()
    from notion_rpadv.widgets.sidebar import Sidebar
    sb = Sidebar(user={"name": "leo", "initials": "LV", "role": ""})
    assert "datajud" in sb._items  # noqa: SLF001
    item = sb._items["datajud"]  # noqa: SLF001
    assert item.page_id == "datajud"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _patch_cache_records(records: list[dict]):
    """Intercepta cache_db.get_all_records pra evitar acesso a SQLite."""
    with patch(
        "notion_rpadv.pages.datajud.cache_db.get_all_records",
        return_value=records,
    ):
        yield
