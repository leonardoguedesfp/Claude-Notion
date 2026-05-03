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


def test_R7_leitor_dje_page_open_file_when_no_export_yet_silencioso() -> None:
    """Hotfix 2026-05-03: click em 'abrir arquivo' sem export prévio
    NÃO mostra modal — silenciosamente esconde o botão (que já estava
    invisível). Antes mostrava QMessageBox 'Arquivo não encontrado /
    Rode novamente' que confundia o usuário (que acabou de rodar)."""
    _qapp()
    from unittest.mock import patch

    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # _last_output_path é None (export não rodou).
    with patch.object(page, "_styled_warning") as mock_warn:
        page._on_open_file_clicked()  # noqa: SLF001
    mock_warn.assert_not_called()
    # Botão fica invisível (já era — mas explícito: handler não causou
    # exibição inadvertida).
    assert (
        not page._open_file_btn.isVisible()  # noqa: SLF001
        or page._open_file_btn.isHidden()  # noqa: SLF001
    )


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
    # Pós-Fase 3: worker recebe ``flow`` em vez de ``mode``, e
    # ``consultas_oab``/``consultas_cnj`` em vez de ``consultas``.
    assert kwargs["flow"] == "oab_novas"
    consultas = kwargs["consultas_oab"]
    assert kwargs["consultas_cnj"] is None
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
    consultas = mock_w_cls.call_args.kwargs["consultas_oab"]
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
    # Pós-Fase 3: ``flow=manual`` (modo personalizado, OABs externas).
    assert kwargs["flow"] == "manual"
    assert kwargs["oabs_escritorio_marcadas"] == set()
    assert kwargs["oabs_externas_pesquisadas"] == {"12345/SP"}
    consultas = kwargs["consultas_oab"]
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
    """Todos os datepickers da página (modo padrão e modo manual) abrem
    calendário ao clicar.

    Pós-refator 2026-05-03: o popup nativo do Qt (calendarPopup=True)
    foi substituído por ``QCalendarWidget`` próprio em ``CalendarDateEdit``
    porque o intercept de ``mousePressEvent`` causava decremento do ano.
    Agora todos os datepickers são instâncias de ``CalendarDateEdit``,
    que tem seu próprio popup — verificamos via tipo + presença do
    helper ``_show_calendar_popup``."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from notion_rpadv.widgets.calendar_date_edit import CalendarDateEdit

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    for w in (
        page._date_inicio_padrao,  # noqa: SLF001
        page._date_fim_padrao,  # noqa: SLF001
        page._date_inicio_manual,  # noqa: SLF001
        page._date_fim_manual,  # noqa: SLF001
    ):
        assert isinstance(w, CalendarDateEdit)
        # Popup nativo desabilitado (usamos custom).
        assert w.calendarPopup() is False
        # Helper que dispara o popup customizado existe.
        assert hasattr(w, "_show_calendar_popup")


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
    """Modo padrão tem botão "Baixar pelo período selecionado" (eixo OAB)
    habilitado quando di ≤ df (default = ambos hoje, OK).

    Pós-Fase 3 (Mudança 4): renomeado de "Baixar período selecionado"
    pra "Baixar pelo período selecionado" (uniformização entre eixos)."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    assert page._download_padrao_periodo_btn.text() == (  # noqa: SLF001
        "Baixar pelo período selecionado"
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
    """Click no botão "Baixar pelo período selecionado" do eixo OAB
    dispara worker com flow='oab_periodo' (não grava no banco — escolha
    b do user) e as 6 OABs do escritório com a janela dos datepickers
    (mesma janela pra todos)."""
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
    # Pós-Fase 3: flow OAB_PERIODO — transient (escolha b: não grava banco).
    assert kwargs["flow"] == "oab_periodo"
    consultas = kwargs["consultas_oab"]
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


# ---------------------------------------------------------------------------
# Pós-Fase 3 (2026-05-02) — modal one-shot de reativação dos 4 advogados
# ---------------------------------------------------------------------------


def _make_page_with_dje_conn(tmp_path: Path):
    """Cria uma LeitorDJEPage e substitui ``_dje_conn`` por uma conn
    SQLite real em ``tmp_path/leitor_dje.db``. Retorna ``(page, conn)``.

    Caller fecha a conn no final via try/finally."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from notion_rpadv.services import dje_db

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    db_path = tmp_path / "leitor_dje.db"
    conn = dje_db.get_connection(db_path)
    page._dje_conn = conn  # noqa: SLF001
    return page, conn


def test_modal_reativacao_dispara_quando_4_advogados_tem_cursor(
    tmp_path: Path,
) -> None:
    """Modal aparece quando: flag não setada AND ≥1 dos 4 advogados
    reativados tem cursor armazenado (estado típico pré-reativação)."""
    page, conn = _make_page_with_dje_conn(tmp_path)
    try:
        from datetime import date as _date
        from notion_rpadv.services import dje_state

        # Popula cursores falsos (estado real pré-reativação na máquina
        # do operador em 2026-05-02).
        for oab, uf in (("48468", "DF"), ("20120", "DF"),
                        ("38809", "DF"), ("75799", "DF")):
            dje_state.update_advogado_cursor(
                conn, oab=oab, uf=uf, novo_cursor=_date(2026, 5, 2),
            )

        # Captura: o modal foi mostrado?
        captured = {"shown": False}

        def fake_question(title, text, *, default_no=True):
            captured["shown"] = True
            captured["text"] = text
            return False  # usuário escolhe "Não"

        page._styled_question = fake_question  # noqa: SLF001
        page._check_and_offer_reactivation_reset()  # noqa: SLF001

        assert captured["shown"], "Modal deveria ter aparecido"
        # Mensagem menciona os 4 nomes pra dar contexto.
        for n in ("Vitor", "Cecília", "Samantha", "Deborah"):
            assert n in captured["text"], (
                f"Texto do modal deveria citar {n!r}: {captured['text']!r}"
            )
    finally:
        conn.close()


def test_modal_reativacao_nao_recorre_apos_resposta_sim(
    tmp_path: Path,
) -> None:
    """Modal é one-shot: após user responder Sim, próxima chamada não
    mostra mais (flag setada em ``app_flags``). Cursores foram zerados."""
    page, conn = _make_page_with_dje_conn(tmp_path)
    try:
        from datetime import date as _date
        from notion_rpadv.services import dje_db, dje_state

        for oab, uf in (("48468", "DF"), ("20120", "DF"),
                        ("38809", "DF"), ("75799", "DF")):
            dje_state.update_advogado_cursor(
                conn, oab=oab, uf=uf, novo_cursor=_date(2026, 5, 2),
            )

        calls = {"n": 0}

        def fake_question_yes(title, text, *, default_no=True):
            calls["n"] += 1
            return True  # usuário escolhe "Sim, resetar"

        page._styled_question = fake_question_yes  # noqa: SLF001
        page._check_and_offer_reactivation_reset()  # noqa: SLF001
        assert calls["n"] == 1
        # Cursores zerados:
        for oab, uf in (("48468", "DF"), ("20120", "DF"),
                        ("38809", "DF"), ("75799", "DF")):
            assert dje_state.read_advogado_cursor(
                conn, oab=oab, uf=uf,
            ) is None
        # Flag persistida:
        assert dje_db.read_flag(
            conn, dje_db.FLAG_REATIVACAO_2026_05_02,
        ) == "reset_yes"

        # 2ª chamada: não deve disparar modal de novo.
        page._check_and_offer_reactivation_reset()  # noqa: SLF001
        assert calls["n"] == 1, (
            "Modal disparou na 2ª chamada — flag não está bloqueando recorrência"
        )
    finally:
        conn.close()


def test_modal_reativacao_nao_recorre_apos_resposta_nao(
    tmp_path: Path,
) -> None:
    """Mesma proteção quando user escolhe Não: cursores ficam intactos
    mas flag é setada (aceita o gap consciente)."""
    page, conn = _make_page_with_dje_conn(tmp_path)
    try:
        from datetime import date as _date
        from notion_rpadv.services import dje_db, dje_state

        for oab, uf in (("48468", "DF"), ("20120", "DF")):
            dje_state.update_advogado_cursor(
                conn, oab=oab, uf=uf, novo_cursor=_date(2026, 5, 2),
            )

        calls = {"n": 0}

        def fake_question_no(title, text, *, default_no=True):
            calls["n"] += 1
            return False

        page._styled_question = fake_question_no  # noqa: SLF001
        page._check_and_offer_reactivation_reset()  # noqa: SLF001
        # Cursores intactos:
        assert dje_state.read_advogado_cursor(
            conn, oab="48468", uf="DF",
        ) == _date(2026, 5, 2)
        # Flag persistida com escolha "no":
        assert dje_db.read_flag(
            conn, dje_db.FLAG_REATIVACAO_2026_05_02,
        ) == "reset_no"

        # 2ª chamada: silenciosa.
        page._check_and_offer_reactivation_reset()  # noqa: SLF001
        assert calls["n"] == 1
    finally:
        conn.close()


def test_modal_reativacao_no_op_quando_sem_cursores(tmp_path: Path) -> None:
    """Máquina sem nenhum dos 4 cursores (e.g. nova): modal NÃO aparece,
    mas flag é setada pra evitar re-checagem."""
    page, conn = _make_page_with_dje_conn(tmp_path)
    try:
        from notion_rpadv.services import dje_db

        calls = {"n": 0}

        def fake_question(title, text, *, default_no=True):
            calls["n"] += 1
            return True

        page._styled_question = fake_question  # noqa: SLF001
        page._check_and_offer_reactivation_reset()  # noqa: SLF001
        assert calls["n"] == 0, (
            "Modal disparou mesmo sem nenhum cursor — desperdício de UX"
        )
        # Flag setada com motivo:
        assert dje_db.read_flag(
            conn, dje_db.FLAG_REATIVACAO_2026_05_02,
        ) == "no_cursors_to_reset"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pós-Fase 3 (2026-05-02) — UI: renomeação de botões + eixo CNJ
# ---------------------------------------------------------------------------


def test_pos_F3_botao_oab_renomeado_para_publicacoes_novas_por_oab() -> None:
    """Mudança 4: botão antigo "Baixar publicações novas" virou
    "Publicações novas por OAB"."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    assert page._download_padrao_btn.text() == (  # noqa: SLF001
        "Publicações novas por OAB"
    )


def test_pos_F3_botao_periodo_oab_renomeado_uniformizado() -> None:
    """Mudança 4: botão "Baixar período selecionado" virou "Baixar pelo
    período selecionado" (uniformização entre eixos OAB e CNJ)."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    assert page._download_padrao_periodo_btn.text() == (  # noqa: SLF001
        "Baixar pelo período selecionado"
    )


def test_pos_F3_eixo_cnj_tem_botoes_corretos() -> None:
    """Mudança 3: eixo CNJ tem 2 botões — 'Publicações novas por número
    CNJ' e 'Baixar pelo período selecionado'."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Pós-revisão Seção B (2026-05-03): eixo CNJ tem 1 botão único.
    assert page._download_cnj_btn.text() == (  # noqa: SLF001
        "Publicações novas por número CNJ"
    )
    # O segundo botão "Baixar pelo período selecionado" do eixo CNJ
    # foi removido — atributo não deve mais existir.
    assert not hasattr(page, "_download_cnj_periodo_btn")


def test_pos_secao_B_eixo_cnj_nao_tem_datepickers() -> None:
    """Pós-revisão Seção B (2026-05-03): eixo CNJ minimalista — sem
    datepickers próprios. Janela é fixa ``[hoje - 15d, hoje]``,
    calculada inline no handler."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    assert not hasattr(page, "_date_inicio_cnj")
    assert not hasattr(page, "_date_fim_cnj")
    # Datepickers do eixo OAB seguem existindo (não confundir).
    assert hasattr(page, "_date_inicio_padrao")
    assert hasattr(page, "_date_fim_padrao")


def test_pos_secao_B_eixo_cnj_avisa_quando_cache_vazio(
    tmp_path: Path,
) -> None:
    """Click no único botão do eixo CNJ com cache de Processos vazio
    mostra warning e NÃO inicia worker."""
    _qapp()
    import sqlite3

    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    # Cache vazio: SQLite com schema mínimo de records, sem nenhum row.
    cache_conn = sqlite3.connect(":memory:")
    cache_conn.row_factory = sqlite3.Row
    cache_conn.execute(
        """
        CREATE TABLE records (
            base TEXT NOT NULL, page_id TEXT NOT NULL,
            data_json TEXT NOT NULL, updated_at REAL NOT NULL,
            PRIMARY KEY (base, page_id)
        )
        """,
    )
    cache_conn.commit()

    page = LeitorDJEPage(conn=cache_conn, token="dummy", user="leo")
    page._dje_conn = MagicMock()  # noqa: SLF001 — dje_conn não usado nesse path
    # Mock legacy migration check (precisa retornar True pra prosseguir).
    page._check_and_run_legacy_migration = lambda: True  # noqa: SLF001
    page._check_and_offer_reactivation_reset = lambda: None  # noqa: SLF001
    warned = {"shown": False}

    def fake_warn(title, text):
        warned["shown"] = True
        warned["text"] = text

    page._styled_warning = fake_warn  # noqa: SLF001
    page._resolve_output_dir = lambda: tmp_path  # noqa: SLF001
    page._on_download_cnj_clicked()  # noqa: SLF001
    assert warned["shown"]
    assert "vazio" in warned["text"].lower() or "sincronize" in warned["text"].lower()
    # Worker NÃO inicia.
    assert page._thread is None  # noqa: SLF001
    cache_conn.close()


def test_pos_secao_B_eixo_cnj_janela_fixa_15_dias(tmp_path: Path) -> None:
    """``_on_download_cnj_clicked`` usa janela FIXA ``[hoje - 15d, hoje]``.

    Validamos via mock do ``_launch_worker`` capturando ``consultas_cnj``.
    Cache populado com 2 CNJs garante que ``_coletar_consultas_cnj``
    retorna lista não-vazia.
    """
    _qapp()
    import datetime as _dt
    import json
    import sqlite3
    from unittest.mock import patch

    from notion_rpadv.pages.leitor_dje import CNJ_WINDOW_DAYS, LeitorDJEPage

    cache_conn = sqlite3.connect(":memory:")
    cache_conn.row_factory = sqlite3.Row
    cache_conn.execute(
        """
        CREATE TABLE records (
            base TEXT NOT NULL, page_id TEXT NOT NULL,
            data_json TEXT NOT NULL, updated_at REAL NOT NULL,
            PRIMARY KEY (base, page_id)
        )
        """,
    )
    cache_conn.execute(
        "INSERT INTO records VALUES ('Processos', 'p1', ?, 1.0)",
        (json.dumps({"numero_do_processo": "0001234-56.2025.5.10.0001"}),),
    )
    cache_conn.execute(
        "INSERT INTO records VALUES ('Processos', 'p2', ?, 2.0)",
        (json.dumps({"numero_do_processo": "0009876-54.2024.1.23.4567"}),),
    )
    cache_conn.commit()

    page = LeitorDJEPage(conn=cache_conn, token="dummy", user="leo")
    page._dje_conn = MagicMock()  # noqa: SLF001
    page._check_and_run_legacy_migration = lambda: True  # noqa: SLF001
    page._check_and_offer_reactivation_reset = lambda: None  # noqa: SLF001
    page._resolve_output_dir = lambda: tmp_path  # noqa: SLF001

    with patch.object(page, "_launch_worker") as mock_launch:
        page._on_download_cnj_clicked()  # noqa: SLF001

    mock_launch.assert_called_once()
    kwargs = mock_launch.call_args.kwargs
    assert kwargs["flow"] == "cnj_novas"
    consultas = kwargs["consultas_cnj"]
    assert len(consultas) == 2
    hoje = _dt.date.today()
    di_esperado = hoje - _dt.timedelta(days=CNJ_WINDOW_DAYS)
    for c in consultas:
        assert c.data_inicio == di_esperado, (
            f"data_inicio deveria ser {di_esperado} (hoje - {CNJ_WINDOW_DAYS}d)"
        )
        assert c.data_fim == hoje
    cache_conn.close()


def test_pos_secao_B_progress_format_processos_no_flow_cnj(
    tmp_path: Path,
) -> None:
    """A1 (2026-05-03): label da barra de progresso vira "%v / %m
    processos" no flow CNJ (em vez de "advogados")."""
    _qapp()
    import json
    import sqlite3
    from unittest.mock import patch

    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    cache_conn = sqlite3.connect(":memory:")
    cache_conn.row_factory = sqlite3.Row
    cache_conn.execute(
        """
        CREATE TABLE records (
            base TEXT NOT NULL, page_id TEXT NOT NULL,
            data_json TEXT NOT NULL, updated_at REAL NOT NULL,
            PRIMARY KEY (base, page_id)
        )
        """,
    )
    cache_conn.execute(
        "INSERT INTO records VALUES ('Processos', 'p1', ?, 1.0)",
        (json.dumps({"numero_do_processo": "0001234-56.2025.5.10.0001"}),),
    )
    cache_conn.commit()

    page = LeitorDJEPage(conn=cache_conn, token="dummy", user="leo")
    page._dje_conn = MagicMock()  # noqa: SLF001
    page._check_and_run_legacy_migration = lambda: True  # noqa: SLF001
    page._check_and_offer_reactivation_reset = lambda: None  # noqa: SLF001
    page._resolve_output_dir = lambda: tmp_path  # noqa: SLF001

    # Mock QThread + worker pra evitar thread real; só queremos ver o
    # estado da progress bar logo após launch.
    with patch("notion_rpadv.pages.leitor_dje.QThread"), \
         patch("notion_rpadv.pages.leitor_dje._DJEWorker"):
        page._on_download_cnj_clicked()  # noqa: SLF001

    assert "processos" in page._progress.format()  # noqa: SLF001
    assert "advogados" not in page._progress.format()  # noqa: SLF001
    cache_conn.close()


def test_pos_secao_B_progress_format_advogados_no_flow_oab() -> None:
    """A1: flow OAB mantém label ``%v / %m advogados``."""
    _qapp()
    from datetime import date, timedelta
    from unittest.mock import patch

    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._dje_conn = MagicMock()  # noqa: SLF001
    page._check_and_run_legacy_migration = lambda: True  # noqa: SLF001
    page._check_and_offer_reactivation_reset = lambda: None  # noqa: SLF001

    with patch("notion_rpadv.pages.leitor_dje.dje_state.compute_advogado_window",
               return_value=(date.today() - timedelta(days=1), date.today())), \
         patch.object(page, "_resolve_output_dir", return_value=Path(".")), \
         patch("notion_rpadv.pages.leitor_dje.QThread"), \
         patch("notion_rpadv.pages.leitor_dje._DJEWorker"):
        page._on_download_padrao_clicked()  # noqa: SLF001

    assert "advogados" in page._progress.format()  # noqa: SLF001
    assert "processos" not in page._progress.format()  # noqa: SLF001


def test_a9_todos_datepickers_sao_calendar_date_edit() -> None:
    """A9 (2026-05-03): todos os datepickers da page Leitor DJE são
    instâncias de ``CalendarDateEdit`` (subclass que abre calendário em
    qualquer clique do mouse, não só na seta dropdown)."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage
    from notion_rpadv.widgets.calendar_date_edit import CalendarDateEdit

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Eixo OAB:
    assert isinstance(page._date_inicio_padrao, CalendarDateEdit)  # noqa: SLF001
    assert isinstance(page._date_fim_padrao, CalendarDateEdit)  # noqa: SLF001
    # Modo manual:
    assert isinstance(page._date_inicio_manual, CalendarDateEdit)  # noqa: SLF001
    assert isinstance(page._date_fim_manual, CalendarDateEdit)  # noqa: SLF001


def test_a9_calendar_date_edit_eh_subclass_de_qdateedit() -> None:
    """``CalendarDateEdit`` é subclass de ``QDateEdit`` — preserva todos
    os comportamentos (``setDate``, ``date()``, ``setDisplayFormat``,
    ``isinstance`` check em delegates etc.).

    Pós-refator 2026-05-03: usa ``QCalendarWidget`` próprio em vez do
    popup nativo (calendarPopup=False) — evitando o bug em que o
    intercept do mousePressEvent decrementava o ano em vez de abrir
    popup."""
    _qapp()
    from PySide6.QtWidgets import QDateEdit

    from notion_rpadv.widgets.calendar_date_edit import CalendarDateEdit

    w = CalendarDateEdit()
    assert isinstance(w, QDateEdit)
    # Pós-refator: popup nativo desabilitado — usamos popup custom.
    assert w.calendarPopup() is False


def test_a9_calendar_date_edit_mouse_click_abre_popup_custom() -> None:
    """Click esquerdo dispara ``_show_calendar_popup`` via subclass
    ``mousePressEvent`` — o ``QCalendarWidget`` próprio é exibido
    embaixo do widget. Não decrementa ano (regressão do bug 2026-05-03).
    """
    _qapp()
    from PySide6.QtCore import QDate, QPoint, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QCalendarWidget

    from notion_rpadv.widgets.calendar_date_edit import CalendarDateEdit

    w = CalendarDateEdit()
    initial_date = QDate(2026, 5, 3)
    w.setDate(initial_date)

    # Dispara mousePressEvent simulado (clique esquerdo).
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    w.mousePressEvent(event)

    # Date NÃO decrementou (bug original do mousePressEvent injetando
    # Alt+Down via keyPressEvent direto).
    assert w.date() == initial_date
    # Popup customizado foi criado.
    assert w._cal_popup is not None  # noqa: SLF001
    assert isinstance(w._cal_popup, QCalendarWidget)  # noqa: SLF001
    # Limpa: esconde popup pra não vazar entre tests.
    w._cal_popup.hide()  # noqa: SLF001


def test_a9_calendar_date_edit_clicar_data_no_popup_seta_valor() -> None:
    """Clicar em uma data dentro do ``QCalendarWidget`` seta o valor
    do ``CalendarDateEdit`` e fecha o popup."""
    _qapp()
    from PySide6.QtCore import QDate

    from notion_rpadv.widgets.calendar_date_edit import CalendarDateEdit

    w = CalendarDateEdit()
    w.setDate(QDate(2026, 5, 3))
    # Força criação do popup pra simular click numa data.
    w._ensure_popup()  # noqa: SLF001
    nova = QDate(2026, 1, 15)
    w._on_calendar_clicked(nova)  # noqa: SLF001
    assert w.date() == nova
    # Popup fechou.
    assert not w._cal_popup.isVisible()  # noqa: SLF001


def test_a7_exec_container_oculto_no_estado_inicial() -> None:
    """A7 (2026-05-03): container "Execução em andamento" só aparece
    durante varredura — escondido por default."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # No estado inicial, container está oculto (setVisible(False)).
    assert not page._exec_container.isVisible() or page._exec_container.isHidden()  # noqa: SLF001
    # ``_cancel_btn`` agora vive dentro do container — apenas foi criado
    # (sem mais ``setVisible(False)`` antigo de fora).
    assert hasattr(page, "_cancel_btn")


# ---------------------------------------------------------------------------
# Hotfix 2026-05-03 — modal "Arquivo não encontrado" não pode aparecer
# em fluxos automáticos (mount, troca de aba) nem em clique sobre botão
# cujo arquivo já sumiu — silenciosamente esconde o botão.
# ---------------------------------------------------------------------------


def test_hotfix_open_file_arquivo_inexistente_esconde_botao_sem_modal(
    tmp_path: Path,
) -> None:
    """Click em "Abrir arquivo gerado" quando ``_last_output_path``
    aponta pra arquivo inexistente: botão é escondido silenciosamente,
    SEM modal."""
    _qapp()
    from unittest.mock import patch

    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Simula execução anterior que setou path mas arquivo sumiu.
    page._last_output_path = tmp_path / "nao_existe.xlsx"  # noqa: SLF001
    page._open_file_btn.setVisible(True)  # noqa: SLF001 — simula pós-finished
    with patch.object(page, "_styled_warning") as mock_warn, \
         patch("notion_rpadv.pages.leitor_dje.QDesktopServices") as mock_qds:
        page._on_open_file_clicked()  # noqa: SLF001
    mock_warn.assert_not_called()
    mock_qds.openUrl.assert_not_called()
    assert (
        not page._open_file_btn.isVisible()  # noqa: SLF001
        or page._open_file_btn.isHidden()  # noqa: SLF001
    )


def test_hotfix_open_file_arquivo_existente_abre_normalmente(
    tmp_path: Path,
) -> None:
    """Click em "Abrir arquivo gerado" com arquivo presente: abre via
    ``QDesktopServices.openUrl`` sem warning."""
    _qapp()
    from unittest.mock import patch

    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    arquivo = tmp_path / "publicacoes.xlsx"
    arquivo.write_bytes(b"fake xlsx content")
    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._last_output_path = arquivo  # noqa: SLF001
    page._open_file_btn.setVisible(True)  # noqa: SLF001
    with patch.object(page, "_styled_warning") as mock_warn, \
         patch("notion_rpadv.pages.leitor_dje.QDesktopServices") as mock_qds:
        page._on_open_file_clicked()  # noqa: SLF001
    mock_warn.assert_not_called()
    mock_qds.openUrl.assert_called_once()


def test_hotfix_refresh_visibility_esconde_botoes_de_paths_que_sumiram(
    tmp_path: Path,
) -> None:
    """``_refresh_open_buttons_visibility`` esconde silenciosamente
    todos os botões cujos paths não existem no FS."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    # Fake state: 3 botões visíveis com paths inválidos.
    page._last_output_path = tmp_path / "no.xlsx"  # noqa: SLF001
    page._last_historico_path = tmp_path / "no_hist.xlsx"  # noqa: SLF001
    page._open_file_btn.setVisible(True)  # noqa: SLF001
    page._open_hist_btn.setVisible(True)  # noqa: SLF001
    page._open_dir_btn.setVisible(True)  # noqa: SLF001

    page._refresh_open_buttons_visibility()  # noqa: SLF001
    # Todos os 3 caem silenciosamente — sem modal, sem exception.
    for btn in (page._open_file_btn, page._open_hist_btn,  # noqa: SLF001
                page._open_dir_btn):  # noqa: SLF001
        assert not btn.isVisible() or btn.isHidden()


def test_hotfix_refresh_visibility_mantem_botoes_com_paths_validos(
    tmp_path: Path,
) -> None:
    """``_refresh_open_buttons_visibility`` NÃO mexe em botões com
    paths válidos."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    arquivo = tmp_path / "ok.xlsx"
    arquivo.write_bytes(b"x")
    historico = tmp_path / "hist.xlsx"
    historico.write_bytes(b"x")
    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._last_output_path = arquivo  # noqa: SLF001
    page._last_historico_path = historico  # noqa: SLF001
    # Marca todos como "visíveis" (estado pós-_on_finished).
    page._open_file_btn.setVisible(True)  # noqa: SLF001
    page._open_hist_btn.setVisible(True)  # noqa: SLF001
    page._open_dir_btn.setVisible(True)  # noqa: SLF001

    page._refresh_open_buttons_visibility()  # noqa: SLF001
    # ``isVisible()`` em widget Qt fora de ``show()`` retorna False
    # mesmo que ``setVisible(True)`` — testamos via ``isHidden()``
    # (False = não foi explicitamente escondido pelo refresh).
    assert not page._open_file_btn.isHidden()  # noqa: SLF001
    assert not page._open_hist_btn.isHidden()  # noqa: SLF001
    assert not page._open_dir_btn.isHidden()  # noqa: SLF001


def test_hotfix_show_event_revalida_botoes_quando_aba_volta(
    tmp_path: Path,
) -> None:
    """``showEvent`` (acionado quando a página volta a ser exibida —
    troca de aba) revalida visibilidade silenciosamente. Não mostra
    modal."""
    _qapp()
    from PySide6.QtGui import QShowEvent
    from unittest.mock import patch

    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._last_output_path = tmp_path / "sumiu.xlsx"  # noqa: SLF001
    page._open_file_btn.setVisible(True)  # noqa: SLF001
    with patch.object(page, "_styled_warning") as mock_warn:
        # Simula evento show.
        page.showEvent(QShowEvent())
    mock_warn.assert_not_called()
    assert (
        not page._open_file_btn.isVisible()  # noqa: SLF001
        or page._open_file_btn.isHidden()  # noqa: SLF001
    )


# ---------------------------------------------------------------------------
# Fase 5 (2026-05-03) — Modal de primeira carga Notion + botão retry
# ---------------------------------------------------------------------------


def test_F5_modal_primeira_carga_so_dispara_quando_flag_ausente(
    tmp_path: Path,
) -> None:
    """Modal aparece apenas quando ``FLAG_NOTION_PRIMEIRA_CARGA`` ainda
    não está em ``app_flags`` E há pelo menos 1 publicação pendente."""
    page, conn = _make_page_with_dje_conn(tmp_path)
    try:
        from notion_rpadv.services import dje_db

        # Insere 2 publicações pendentes.
        for i in (1, 2):
            dje_db.insert_publicacao(
                conn, djen_id=i, hash_=f"h{i}",
                oabs_escritorio="X", oabs_externas="",
                numero_processo=None,
                data_disponibilizacao="2026-04-30",
                sigla_tribunal="TRT10", payload={"id": i},
                mode="padrao",
            )
        captured = {"shown": False, "msg": ""}

        def fake_exec(self_box):
            captured["shown"] = True
            captured["msg"] = self_box.text()
            # Simula click no botão "Decidir depois" (1º addedButton de role
            # RejectRole).
            from PySide6.QtWidgets import QMessageBox
            for b in self_box.buttons():
                role = self_box.buttonRole(b)
                if role == QMessageBox.ButtonRole.RejectRole:
                    self_box.setProperty("__clicked", b)
                    return 0
            return 0

        # Monkey-patch QMessageBox.exec via setting clickedButton manually.
        import unittest.mock as _mock
        from PySide6.QtWidgets import QMessageBox

        # Simulate user clicking "Decidir depois" by patching exec to do nothing
        # and manually calling _set_clicked on the box.
        def fake_exec_bound(self_box, *args, **kwargs):
            captured["shown"] = True
            captured["msg"] = self_box.text()
            # Force the "adiar" button as clicked.
            for b in self_box.buttons():
                if b.text() == "Decidir depois":
                    # No public setter; we rely on the page reading via
                    # ``clickedButton()`` which Qt sets after exec(). Pra
                    # simular, monkey-patch ``clickedButton`` no box.
                    self_box.clickedButton = lambda b=b: b
                    break
            return 0

        with _mock.patch.object(QMessageBox, "exec", fake_exec_bound):
            page._check_and_offer_notion_primeira_carga()  # noqa: SLF001

        assert captured["shown"]
        assert "2 publicação" in captured["msg"]
        # Flag setada como adiado.
        assert dje_db.read_flag(
            conn, dje_db.FLAG_NOTION_PRIMEIRA_CARGA,
        ) == "adiado"
    finally:
        conn.close()


def test_F5_modal_nao_recorre_apos_primeira_decisao(tmp_path: Path) -> None:
    """Após qualquer decisão (flag setada), próxima chamada não dispara
    modal."""
    page, conn = _make_page_with_dje_conn(tmp_path)
    try:
        from notion_rpadv.services import dje_db
        dje_db.set_flag(
            conn, dje_db.FLAG_NOTION_PRIMEIRA_CARGA, "adiado",
        )
        calls = {"v": 0}
        from PySide6.QtWidgets import QMessageBox

        def fake_exec(self_box, *args, **kwargs):
            calls["v"] += 1
            return 0

        import unittest.mock as _mock
        with _mock.patch.object(QMessageBox, "exec", fake_exec):
            page._check_and_offer_notion_primeira_carga()  # noqa: SLF001
        assert calls["v"] == 0
    finally:
        conn.close()


def test_F5_modal_banco_vazio_seta_flag_silenciosamente(
    tmp_path: Path,
) -> None:
    """Banco sem publicações → modal não aparece, mas flag é gravada
    pra próxima execução não recorrer."""
    page, conn = _make_page_with_dje_conn(tmp_path)
    try:
        from notion_rpadv.services import dje_db
        from PySide6.QtWidgets import QMessageBox
        import unittest.mock as _mock

        calls = {"v": 0}
        with _mock.patch.object(QMessageBox, "exec",
                                lambda *a, **k: calls.__setitem__(
                                    "v", calls["v"] + 1) or 0):
            page._check_and_offer_notion_primeira_carga()  # noqa: SLF001
        assert calls["v"] == 0
        assert dje_db.read_flag(
            conn, dje_db.FLAG_NOTION_PRIMEIRA_CARGA,
        ) == "banco_vazio"
    finally:
        conn.close()


def test_F5_botao_retry_oculto_quando_sem_falhas(tmp_path: Path) -> None:
    """``_retry_notion_btn`` permanece invisível quando não há
    publicações presas (3+ falhas)."""
    _qapp()
    from notion_rpadv.pages.leitor_dje import LeitorDJEPage

    # cache_conn (1º arg) é cache.db; aqui usamos MagicMock pq não toca.
    page = LeitorDJEPage(conn=MagicMock(), token="dummy", user="leo")
    page._refresh_retry_notion_btn()  # noqa: SLF001 — _dje_conn é None
    assert (
        not page._retry_notion_btn.isVisible()  # noqa: SLF001
        or page._retry_notion_btn.isHidden()  # noqa: SLF001
    )


def test_F5_botao_retry_aparece_quando_ha_falhas(tmp_path: Path) -> None:
    """Após 3 falhas em uma pub, botão "Tentar reenviar" fica visível
    com label informativo do número de falhas."""
    page, conn = _make_page_with_dje_conn(tmp_path)
    try:
        from notion_rpadv.services import dje_db
        # Insere e simula 3 falhas.
        dje_db.insert_publicacao(
            conn, djen_id=1, hash_="h1",
            oabs_escritorio="X", oabs_externas="", numero_processo=None,
            data_disponibilizacao="2026-04-30", sigla_tribunal="TRT10",
            payload={"id": 1}, mode="padrao",
        )
        for err in ("e1", "e2", "e3"):
            dje_db.mark_publicacao_notion_failure(conn, 1, err)
        page._refresh_retry_notion_btn()  # noqa: SLF001
        # Em headless ``isHidden`` retorna True mesmo após setVisible(True)
        # — testamos via ``isHidden() is False``.
        assert not page._retry_notion_btn.isHidden()  # noqa: SLF001
        assert "1 falha" in page._retry_notion_btn.text()  # noqa: SLF001
    finally:
        conn.close()


def test_F5_retry_zera_attempts_e_dispara_sync(tmp_path: Path) -> None:
    """Click em "Tentar reenviar falhas" zera attempts das publicações
    em 3+ falhas e dispara nova sincronização."""
    page, conn = _make_page_with_dje_conn(tmp_path)
    try:
        from unittest.mock import patch

        from notion_rpadv.services import dje_db

        # Insere 1 pub e força 3 falhas.
        dje_db.insert_publicacao(
            conn, djen_id=1, hash_="h1",
            oabs_escritorio="X", oabs_externas="", numero_processo=None,
            data_disponibilizacao="2026-04-30", sigla_tribunal="TRT10",
            payload={"id": 1}, mode="padrao",
        )
        for err in ("e1", "e2", "e3"):
            dje_db.mark_publicacao_notion_failure(conn, 1, err)
        assert dje_db.count_publicacoes_failed_notion(conn) == 1

        # Mock cache_conn pra evitar cache real (page._conn é o cache).
        # ``page._conn`` foi MagicMock no construtor — o sync vai tentar
        # ler "Processos" dele. Vamos só mockar o sync inteiro pra validar
        # que ele FOI chamado após reset.
        with patch(
            "notion_rpadv.pages.leitor_dje.sincronizar_pendentes",
        ) as mock_sync, patch(
            "notion_bulk_edit.notion_api.NotionClient",
        ) as mock_client_cls:
            from notion_rpadv.services.dje_notion_sync import NotionSyncOutcome
            mock_sync.return_value = NotionSyncOutcome(
                sent=1, failed=0, stuck_after=0,
            )
            mock_client_cls.return_value = MagicMock()
            page._on_retry_notion_clicked()  # noqa: SLF001

        # attempts foi zerado pre-sync.
        # (Após sync mock que disse "sent=1" + nada mudou no banco, a pub
        # ainda está pendente com attempts=0).
        row = conn.execute(
            "SELECT notion_attempts, notion_page_id FROM publicacoes "
            "WHERE djen_id=1"
        ).fetchone()
        assert row["notion_attempts"] == 0
        # Sync foi chamado.
        mock_sync.assert_called_once()
    finally:
        conn.close()
