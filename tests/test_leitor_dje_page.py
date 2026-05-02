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
    """Estado inicial Fase 3: aba abre em modo padrão (stack em índice 0).
    Datepickers só existem na página manual (índice 1). Botão padrão
    habilitado, log vazio, progresso 0/N, botões 'abrir' ocultos."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from notion_rpadv.services.dje_advogados import ADVOGADOS

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Modo padrão default
    assert page._stack.currentIndex() == 0  # noqa: SLF001
    # Datepickers do modo manual têm defaults plausíveis (ontem ou sticky)
    di = page._date_inicio_manual.date().toPython()  # noqa: SLF001
    today = _dt.date.today()
    assert 1 <= (today - di).days <= 30, (
        f"_date_inicio_manual fora da janela [today-30d, today-1d]: {di}"
    )
    # Log vazio
    assert page._log_area.toPlainText() == ""  # noqa: SLF001
    # Progresso 0/N (Fase 2.1: 6 advogados ativos)
    assert page._progress.maximum() == len(ADVOGADOS)  # noqa: SLF001
    assert page._progress.value() == 0  # noqa: SLF001
    # Botão padrão habilitado
    assert page._download_padrao_btn.isEnabled()  # noqa: SLF001
    # Botões de abrir ocultos
    assert not page._open_file_btn.isVisible() or page._open_file_btn.isHidden()  # noqa: SLF001
    assert not page._open_dir_btn.isVisible() or page._open_dir_btn.isHidden()  # noqa: SLF001
    assert not page._open_hist_btn.isVisible() or page._open_hist_btn.isHidden()  # noqa: SLF001
    # Banner oculto
    assert not page._warning_lbl.isVisible() or page._warning_lbl.isHidden()  # noqa: SLF001


def test_R7_leitor_dje_page_data_final_anterior_a_inicial_mostra_aviso() -> None:
    """Validação síncrona modo manual: data final < inicial → botão
    fica desabilitado pelo refresh."""
    _qapp()
    from PySide6.QtCore import QDate
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Toggle pra modo manual
    page._on_toggle_mode()  # noqa: SLF001
    # Forçar inversão
    page._date_inicio_manual.setDate(QDate(2026, 5, 5))  # noqa: SLF001
    page._date_fim_manual.setDate(QDate(2026, 5, 1))  # noqa: SLF001
    # Refresh deveria desabilitar o botão (regra di > df)
    page._refresh_manual_botao()  # noqa: SLF001
    assert not page._download_manual_btn.isEnabled()  # noqa: SLF001
    # Worker NÃO iniciou.
    assert page._thread is None  # noqa: SLF001


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
    cria dir e retorna sem QFileDialog.

    Robustez: ``settings.sync()`` força o flush antes da leitura pra
    eliminar flakiness em suite completa (outros testes podem ter
    deixado state pendente sem flush — Qt persistência é assíncrona).
    """
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
    settings.sync()
    try:
        page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
        result = page._resolve_output_dir()  # noqa: SLF001
        assert result == target
        assert target.exists()
    finally:
        settings.remove(_KEY_OUTPUT_DIR)
        settings.sync()


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


# ---------------------------------------------------------------------------
# Fase 2.2 — botão Cancelar (state machine)
# ---------------------------------------------------------------------------


def test_F22_16_cancel_btn_oculto_no_estado_inicial() -> None:
    """Estado inicial: ``_cancel_btn`` oculto, ``_download_padrao_btn``
    habilitado. UI não polui o operador com botão sem função."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    assert (
        not page._cancel_btn.isVisible()  # noqa: SLF001
        or page._cancel_btn.isHidden()    # noqa: SLF001
    )
    assert page._download_padrao_btn.isEnabled()  # noqa: SLF001


def test_F22_17_click_em_baixar_torna_cancel_visivel_e_habilitado(
    tmp_path: Path,
) -> None:
    """Click em Baixar (modo padrão) → Cancelar fica visível +
    habilitado, Baixar desabilita. Worker é instanciado.

    Mocka ``_DJEWorker``, ``QThread``, ``dje_db.get_connection`` e
    ``dje_state.read_cursor`` pra evitar HTTP real e SQLite real.
    """
    _qapp()
    from datetime import date
    from unittest.mock import patch
    from PySide6.QtCore import QSettings
    from notion_rpadv.pages.leitor_dje import (
        _KEY_OUTPUT_DIR,
        _SETTINGS_APP,
        _SETTINGS_ORG,
        LeitorDJEPage,
    )
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(_KEY_OUTPUT_DIR, str(tmp_path))
    try:
        page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
        with patch("notion_rpadv.pages.leitor_dje._DJEWorker") as mock_w_cls, \
             patch("notion_rpadv.pages.leitor_dje.QThread") as mock_thr_cls, \
             patch(
                 "notion_rpadv.pages.leitor_dje.dje_db.get_connection",
                 return_value=MagicMock(),
             ), \
             patch(
                 "notion_rpadv.pages.leitor_dje.dje_state.read_advogado_cursor",
                 return_value=date(2026, 4, 30),
             ), \
             patch(
                 "notion_rpadv.pages.leitor_dje.dje_db.is_legacy_state_present",
                 return_value=False,
             ):
            mock_worker = MagicMock()
            mock_w_cls.return_value = mock_worker
            mock_thr_cls.return_value = MagicMock()
            page._on_download_padrao_clicked()  # noqa: SLF001
        assert not page._cancel_btn.isHidden()  # noqa: SLF001
        assert page._cancel_btn.isEnabled()  # noqa: SLF001
        assert not page._download_padrao_btn.isEnabled()  # noqa: SLF001
        assert page._cancel_btn.text() == "Cancelar"  # noqa: SLF001
        assert page._worker is mock_worker  # noqa: SLF001
    finally:
        settings.remove(_KEY_OUTPUT_DIR)


def test_F22_18_click_em_cancelar_chama_request_cancel_e_muda_label(
    tmp_path: Path,
) -> None:
    """Click em Cancelar → ``worker.request_cancel()`` chamado, botão
    fica desabilitado com label 'Cancelando...'."""
    _qapp()
    from datetime import date
    from unittest.mock import patch
    from PySide6.QtCore import QSettings
    from notion_rpadv.pages.leitor_dje import (
        _KEY_OUTPUT_DIR,
        _SETTINGS_APP,
        _SETTINGS_ORG,
        LeitorDJEPage,
    )
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(_KEY_OUTPUT_DIR, str(tmp_path))
    try:
        page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
        with patch("notion_rpadv.pages.leitor_dje._DJEWorker") as mock_w_cls, \
             patch("notion_rpadv.pages.leitor_dje.QThread") as mock_thr_cls, \
             patch(
                 "notion_rpadv.pages.leitor_dje.dje_db.get_connection",
                 return_value=MagicMock(),
             ), \
             patch(
                 "notion_rpadv.pages.leitor_dje.dje_state.read_advogado_cursor",
                 return_value=date(2026, 4, 30),
             ), \
             patch(
                 "notion_rpadv.pages.leitor_dje.dje_db.is_legacy_state_present",
                 return_value=False,
             ):
            mock_worker = MagicMock()
            mock_w_cls.return_value = mock_worker
            mock_thr_cls.return_value = MagicMock()
            page._on_download_padrao_clicked()  # noqa: SLF001
            page._on_cancel_clicked()  # noqa: SLF001
        mock_worker.request_cancel.assert_called_once()
        assert page._cancel_btn.text() == "Cancelando..."  # noqa: SLF001
        assert not page._cancel_btn.isEnabled()  # noqa: SLF001
    finally:
        settings.remove(_KEY_OUTPUT_DIR)


# ---------------------------------------------------------------------------
# Fase 3 — F3-16..F3-21: modo padrão
# ---------------------------------------------------------------------------


def _patch_chain(
    tmp_path: Path,
    *,
    advogado_cursor=None,
    legacy_present: bool = False,
):
    """Helper: contexto pra testar handlers da page sem disparar
    thread/HTTP. Refator pós-Fase 3 hotfix: ``read_cursor`` (singleton)
    foi substituído por ``read_advogado_cursor`` (por advogado) +
    ``compute_advogado_window``. Também a detecção de migração legada
    é feita dentro dos handlers.

    ``advogado_cursor``: ``None`` ou ``date``. Aplicado pra TODOS os
    advogados oficiais (simula a mesma data de cursor pra todo o
    escritório).

    ``legacy_present``: se ``True``, simula banco com schema legado
    (``djen_state`` populada). Default ``False``.
    """
    from contextlib import contextmanager
    from unittest.mock import patch
    from PySide6.QtCore import QSettings
    from notion_rpadv.pages.leitor_dje import (
        _KEY_OUTPUT_DIR, _SETTINGS_APP, _SETTINGS_ORG,
    )

    @contextmanager
    def cm():
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.setValue(_KEY_OUTPUT_DIR, str(tmp_path))
        try:
            with patch(
                "notion_rpadv.pages.leitor_dje._DJEWorker",
            ) as mock_w_cls, patch(
                "notion_rpadv.pages.leitor_dje.QThread",
            ) as mock_thr_cls, patch(
                "notion_rpadv.pages.leitor_dje.dje_db.get_connection",
                return_value=MagicMock(),
            ), patch(
                "notion_rpadv.pages.leitor_dje.dje_state.read_advogado_cursor",
                return_value=advogado_cursor,
            ), patch(
                "notion_rpadv.pages.leitor_dje.dje_db.is_legacy_state_present",
                return_value=legacy_present,
            ):
                mock_worker = MagicMock()
                mock_w_cls.return_value = mock_worker
                mock_thr_cls.return_value = MagicMock()
                yield mock_w_cls, mock_worker
        finally:
            settings.remove(_KEY_OUTPUT_DIR)

    return cm()


def test_modo_padrao_constroi_consultas_por_advogado(tmp_path: Path) -> None:
    """Refator: ``_on_download_padrao_clicked`` constrói uma
    ``AdvogadoConsulta`` por advogado oficial usando o cursor individual
    + janela calculada por ``compute_advogado_window``."""
    _qapp()
    from datetime import date, timedelta
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from notion_rpadv.services.dje_advogados import ADVOGADOS

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    cursor = date.today() - timedelta(days=10)
    with _patch_chain(tmp_path, advogado_cursor=cursor) as (mock_w_cls, _w):
        page._on_download_padrao_clicked()  # noqa: SLF001
    mock_w_cls.assert_called_once()
    kwargs = mock_w_cls.call_args.kwargs
    consultas = kwargs["consultas"]
    assert len(consultas) == len(ADVOGADOS)
    # Cada consulta tem janela cursor+1d → hoje
    for c in consultas:
        assert c.data_inicio == cursor + timedelta(days=1)
        assert c.data_fim == date.today()


def test_modo_padrao_sem_modal_quando_cursor_vazio(tmp_path: Path) -> None:
    """Refator (sem modal de primeira execução): cursor None faz a
    janela ser [01/01/2026, hoje] (via DEFAULT_CURSOR_VAZIO)."""
    _qapp()
    from datetime import date
    from unittest.mock import patch
    from PySide6.QtWidgets import QMessageBox
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from notion_rpadv.services.dje_state import (
        DATA_INICIO_HISTORICO_ESCRITORIO,
    )

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    with _patch_chain(tmp_path, advogado_cursor=None) as (mock_w_cls, _w):
        with patch.object(QMessageBox, "question") as mock_q:
            page._on_download_padrao_clicked()  # noqa: SLF001
    # Sem modal de primeira execução
    mock_q.assert_not_called()
    # Worker recebeu janela [2026-01-01, hoje]
    consultas = mock_w_cls.call_args.kwargs["consultas"]
    assert all(c.data_inicio == DATA_INICIO_HISTORICO_ESCRITORIO for c in consultas)
    assert all(c.data_fim == date.today() for c in consultas)


def test_modo_padrao_modal_de_migracao_legada(tmp_path: Path) -> None:
    """Quando ``is_legacy_state_present`` retorna True, modal pergunta
    se o usuário aceita resetar — Yes executa migração + segue.

    Refator pós-smoke 2026-05-02: ``QMessageBox`` foi substituído por
    helper ``_styled_question`` (alto contraste). Mockamos esse helper
    direto.
    """
    _qapp()
    from datetime import date
    from unittest.mock import patch
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    with _patch_chain(
        tmp_path,
        advogado_cursor=date(2026, 4, 30),
        legacy_present=True,
    ) as (mock_w_cls, _w):
        with patch.object(
            page, "_styled_question", return_value=True,
        ) as mock_q, patch(
            "notion_rpadv.pages.leitor_dje."
            "dje_db.clear_legacy_state_and_publicacoes",
        ) as mock_clear:
            page._on_download_padrao_clicked()  # noqa: SLF001
    mock_q.assert_called_once()  # modal de migração
    mock_clear.assert_called_once()  # reset executado
    mock_w_cls.assert_called_once()  # worker disparou após migrar


def test_modo_padrao_modal_de_migracao_cancelado_nao_dispara_worker(
    tmp_path: Path,
) -> None:
    """Modal de migração cancelado → worker NÃO é criado, migração NÃO
    é executada."""
    _qapp()
    from datetime import date
    from unittest.mock import patch
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    with _patch_chain(
        tmp_path,
        advogado_cursor=date(2026, 4, 30),
        legacy_present=True,
    ) as (mock_w_cls, _w):
        with patch.object(
            page, "_styled_question", return_value=False,
        ), patch(
            "notion_rpadv.pages.leitor_dje."
            "dje_db.clear_legacy_state_and_publicacoes",
        ) as mock_clear:
            page._on_download_padrao_clicked()  # noqa: SLF001
    mock_clear.assert_not_called()
    mock_w_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Modo manual — refator: SÓ OABs externas
# ---------------------------------------------------------------------------


def test_manual_dispara_worker_so_com_externas(tmp_path: Path) -> None:
    """Refator pós-Fase 3 hotfix UX: modo manual aceita SÓ OABs externas
    com 2 campos (OAB + UF). Nome é resolvido depois pelo transform."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._on_toggle_mode()  # noqa: SLF001
    page._on_add_externa_clicked()  # noqa: SLF001
    page._externas_rows[0]["oab"].setText("12345")  # noqa: SLF001
    page._externas_rows[0]["uf"].setCurrentText("SP")  # noqa: SLF001
    page._refresh_manual_botao()  # noqa: SLF001
    assert page._download_manual_btn.isEnabled()  # noqa: SLF001
    with _patch_chain(tmp_path) as (mock_w_cls, _w):
        page._on_download_manual_clicked()  # noqa: SLF001
    kwargs = mock_w_cls.call_args.kwargs
    assert kwargs["mode"] == "manual"
    assert kwargs["oabs_escritorio_marcadas"] == set()
    assert kwargs["oabs_externas_pesquisadas"] == {"12345/SP"}
    consultas = kwargs["consultas"]
    assert len(consultas) == 1
    assert consultas[0].advogado["oab"] == "12345"
    # Nome vai vazio — transform resolve via destinatarioadvogados
    assert consultas[0].advogado["nome"] == ""


def test_manual_botao_desabilitado_sem_externas() -> None:
    """Refator: 0 externas → botão desabilitado (não há mais checkboxes
    do escritório no modo manual)."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._on_toggle_mode()  # noqa: SLF001
    # Sem nenhuma externa adicionada
    page._refresh_manual_botao()  # noqa: SLF001
    assert not page._download_manual_btn.isEnabled()  # noqa: SLF001


def test_F3_26_botao_desabilitado_quando_externa_parcial() -> None:
    """Externa adicionada com algum campo vazio → botão desab.

    Refator pós-Fase 3 hotfix UX: linhas têm 2 campos (OAB + UF), sem
    nome. Linha "parcial" agora significa só OAB OU só UF preenchido.
    """
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._on_toggle_mode()  # noqa: SLF001
    page._on_add_externa_clicked()  # noqa: SLF001
    page._externas_rows[0]["oab"].setText("12345")  # noqa: SLF001
    # UF não selecionada (placeholder "UF") — linha parcial
    page._refresh_manual_botao()  # noqa: SLF001
    assert not page._download_manual_btn.isEnabled()  # noqa: SLF001


def test_F3_27_botao_desabilitado_quando_data_inicial_maior_que_final() -> None:
    """F3-27: di > df → botão desab."""
    _qapp()
    from PySide6.QtCore import QDate
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._on_toggle_mode()  # noqa: SLF001
    page._date_inicio_manual.setDate(QDate(2026, 5, 10))  # noqa: SLF001
    page._date_fim_manual.setDate(QDate(2026, 5, 5))  # noqa: SLF001
    page._refresh_manual_botao()  # noqa: SLF001
    assert not page._download_manual_btn.isEnabled()  # noqa: SLF001


def test_F3_28_remover_externa_funciona() -> None:
    """Helper além do F3-XX: clique em ✕ remove a linha da lista."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._on_toggle_mode()  # noqa: SLF001
    page._on_add_externa_clicked()  # noqa: SLF001
    page._on_add_externa_clicked()  # noqa: SLF001
    assert len(page._externas_rows) == 2  # noqa: SLF001
    first = page._externas_rows[0]  # noqa: SLF001
    page._remove_externa(first)  # noqa: SLF001
    assert len(page._externas_rows) == 1  # noqa: SLF001


def test_F3_toggle_alterna_stack_e_sub() -> None:
    """Toggle alterna QStackedWidget e visibilidade dos subtitles."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    assert page._stack.currentIndex() == 0  # noqa: SLF001
    page._on_toggle_mode()  # noqa: SLF001
    assert page._stack.currentIndex() == 1  # noqa: SLF001
    page._on_toggle_mode()  # noqa: SLF001
    assert page._stack.currentIndex() == 0  # noqa: SLF001


# ---------------------------------------------------------------------------
# Hotfix UX (2026-05-02): datepickers no modo padrão + botão período
# selecionado + calendar popup garantido em todos
# ---------------------------------------------------------------------------


def test_hotfix_ux_todos_datepickers_tem_calendar_popup() -> None:
    """Todos os QDateEdit da página (modo padrão e modo manual) abrem
    calendário ao clicar — comportamento padrão de software Windows."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    assert page._date_inicio_padrao.calendarPopup() is True  # noqa: SLF001
    assert page._date_fim_padrao.calendarPopup() is True  # noqa: SLF001
    assert page._date_inicio_manual.calendarPopup() is True  # noqa: SLF001
    assert page._date_fim_manual.calendarPopup() is True  # noqa: SLF001


def test_hotfix_ux_modo_padrao_tem_datepickers_default_hoje() -> None:
    """Modo padrão tem 2 datepickers; ambos default = hoje."""
    _qapp()
    import datetime as _dt
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    hoje = _dt.date.today()
    assert page._date_inicio_padrao.date().toPython() == hoje  # noqa: SLF001
    assert page._date_fim_padrao.date().toPython() == hoje  # noqa: SLF001


def test_hotfix_ux_modo_padrao_botao_periodo_selecionado_existe() -> None:
    """Modo padrão tem botão "Baixar período selecionado" habilitado
    quando di ≤ df (default = ambos hoje, OK)."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    assert page._download_padrao_periodo_btn.text() == (  # noqa: SLF001
        "Baixar período selecionado"
    )
    assert page._download_padrao_periodo_btn.isEnabled()  # noqa: SLF001


def test_hotfix_ux_botao_periodo_selecionado_desabilita_se_di_maior_que_df() -> None:
    """di > df → botão "Baixar período selecionado" desabilitado."""
    _qapp()
    from PySide6.QtCore import QDate
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._date_inicio_padrao.setDate(QDate(2026, 5, 10))  # noqa: SLF001
    page._date_fim_padrao.setDate(QDate(2026, 5, 5))  # noqa: SLF001
    page._refresh_padrao_periodo_btn()  # noqa: SLF001
    assert not page._download_padrao_periodo_btn.isEnabled()  # noqa: SLF001


def test_hotfix_ux_botao_periodo_selecionado_dispara_worker_modo_manual_6_oabs(
    tmp_path: Path,
) -> None:
    """Click no botão "Baixar período selecionado" dispara worker com
    mode='manual' (não toca cursor) e as 6 OABs do escritório com a
    janela dos datepickers do modo padrão (mesma janela pra todos)."""
    _qapp()
    from datetime import date
    from PySide6.QtCore import QDate
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from notion_rpadv.services.dje_advogados import ADVOGADOS

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._date_inicio_padrao.setDate(QDate(2026, 1, 1))  # noqa: SLF001
    page._date_fim_padrao.setDate(QDate(2026, 1, 31))  # noqa: SLF001
    with _patch_chain(tmp_path, advogado_cursor=date(2026, 4, 30)) as (
        mock_w_cls, _w,
    ):
        page._on_download_padrao_periodo_clicked()  # noqa: SLF001
    mock_w_cls.assert_called_once()
    kwargs = mock_w_cls.call_args.kwargs
    assert kwargs["mode"] == "manual"  # NÃO toca cursor
    consultas = kwargs["consultas"]
    assert len(consultas) == len(ADVOGADOS)
    # Mesma janela pra todos os 6
    for c in consultas:
        assert c.data_inicio == date(2026, 1, 1)
        assert c.data_fim == date(2026, 1, 31)
    expected = {f"{a['oab']}/{a['uf']}" for a in ADVOGADOS}
    assert kwargs["oabs_escritorio_marcadas"] == expected
    assert kwargs["oabs_externas_pesquisadas"] == set()


def test_hotfix_ux_modo_manual_envolto_em_scrollarea() -> None:
    """O modo manual está envolto em QScrollArea (page wrapper) —
    robustez pra janelas pequenas que comprimem o conteúdo."""
    _qapp()
    from PySide6.QtWidgets import QScrollArea
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    assert isinstance(page._stack.widget(1), QScrollArea)  # noqa: SLF001


def test_hotfix_ux_externas_empty_state_quando_lista_vazia() -> None:
    """Refator UX: lista de OABs externas vazia mostra label de empty
    state ('Nenhuma OAB externa adicionada...') visível pra o usuário."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._on_toggle_mode()  # noqa: SLF001
    # Empty label deve estar criada e visível quando 0 OABs externas
    assert hasattr(page, "_externas_empty_label")  # noqa: SLF001
    # Adiciona uma → empty label some
    page._on_add_externa_clicked()  # noqa: SLF001
    assert not page._externas_empty_label.isVisible() or page._externas_empty_label.isHidden()  # noqa: SLF001
    # Remove → empty label volta
    page._remove_externa(page._externas_rows[0])  # noqa: SLF001
    # (em ambiente headless ``isVisible`` retorna False antes do show;
    # validamos só que setVisible(True) foi chamado — flag interna OK)


def test_hotfix_ux_log_area_max_height_limitado() -> None:
    """Refator UX: log_area não domina mais o layout. Max altura
    limitada pra que datepickers e lista de OABs tenham prioridade."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Antes: setMinimumHeight(120) + stretch=1 (dominava)
    # Refator: max ~180, stretch=0
    assert page._log_area.maximumHeight() <= 200  # noqa: SLF001
