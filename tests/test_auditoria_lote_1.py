"""Tests for Round 1 / Lote 1 da auditoria do app.

Cobre 6 componentes (5 esforço S + 1 esforço L):
- C1: P1-005 + P2-008 — Dashboard "Tarefas críticas" inclui prazo == hoje.
- C2: P1-004 — CommitWorker tolera edit_id None / inválido.
- C3: P1-001 — Botão "+ Novo" + Ctrl+N + EmptyState.on_create removidos.
- C4: P0-001 — CnjDelegate / SucessorDelegate chamam setClipRect(option.rect).
- C5: P1-002 — Delegates re-bindam quando model._cols muda (modelReset).
- C6: P1-003 — MultiSelectEditor só aceita opções válidas do spec.
"""
from __future__ import annotations

import sqlite3

import pytest

try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(
    not _PYSIDE6, reason="PySide6 not installed",
)


def _make_conn() -> sqlite3.Connection:
    """In-memory cache+audit, espelhando _make_cache de outros testes."""
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# Componente 1 — P1-005 + P2-008: Dashboard "Tarefas críticas"
# ---------------------------------------------------------------------------


@requires_pyside6
def test_dashboard_critical_includes_today() -> None:
    """Tarefa com prazo_fatal == hoje (0 dias) deve contar como crítica.

    Antes do fix: `(self._days_remaining(...) or 999) <= 3` — 0 é falsy em
    Python, `0 or 999` avalia para 999, e 999 <= 3 é False. Tarefa
    silenciosamente NÃO era contada.
    """
    import sys
    from datetime import date
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.dashboard import DashboardPage

    conn = _make_conn()
    today_iso = date.today().isoformat()
    # 3 tarefas: prazo hoje, prazo +2 dias, prazo +10 dias.
    tarefas = [
        {"page_id": "t-1", "tarefa": "Hoje", "prazo_fatal": today_iso},
        {"page_id": "t-2", "tarefa": "Em 2 dias",
         "prazo_fatal": (date.today().toordinal() + 2)},
        {"page_id": "t-3", "tarefa": "Em 10 dias",
         "prazo_fatal": "2099-01-01"},
    ]
    # _days_remaining espera string ISO; ajusta t-2 para string ISO.
    from datetime import timedelta
    tarefas[1]["prazo_fatal"] = (
        date.today() + timedelta(days=2)
    ).isoformat()
    for t in tarefas:
        cache_db.upsert_record(conn, "Tarefas", t["page_id"], t)
    conn.commit()

    page = DashboardPage(conn=conn, user={"name": "Test"}, dark=False)
    page._load_stats()

    # Esperado: 2 críticas (hoje, +2 dias). +10 dias e 2099 ficam fora.
    valor = page._card_criticos._val_lbl.text()
    assert valor == "2", (
        f"Esperado 2 tarefas críticas (hoje + 2d); obtido {valor!r}. "
        "Tarefa de hoje provavelmente não foi contada (regressão de P1-005)."
    )


@requires_pyside6
def test_dashboard_days_remaining_called_once_per_task() -> None:
    """P2-008: _days_remaining é caro (parsea ISO date); deve ser chamado
    1× por tarefa, não 2× (antes o sum/comprehension chamava em cada
    branch do `and`)."""
    import sys
    from datetime import date
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.dashboard import DashboardPage

    conn = _make_conn()
    today_iso = date.today().isoformat()
    # 5 tarefas com mesma data
    for i in range(5):
        cache_db.upsert_record(
            conn, "Tarefas", f"t-{i}",
            {"page_id": f"t-{i}", "tarefa": f"T{i}", "prazo_fatal": today_iso},
        )
    conn.commit()

    page = DashboardPage(conn=conn, user={"name": "Test"}, dark=False)

    # Conta chamadas a _days_remaining (método estático).
    original = DashboardPage._days_remaining
    call_count = [0]

    def counting_wrapper(date_str):
        call_count[0] += 1
        return original(date_str)

    DashboardPage._days_remaining = staticmethod(counting_wrapper)
    try:
        page._load_stats()
    finally:
        DashboardPage._days_remaining = staticmethod(original)

    # 5 tarefas × 1 chamada = 5 (não 10).
    assert call_count[0] == 5, (
        f"_days_remaining foi chamado {call_count[0]} vezes para 5 tarefas; "
        "esperado 5 (P2-008 fundiu o duplo lookup)."
    )


# ---------------------------------------------------------------------------
# Componente 2 — P1-004: CommitWorker tolera edit_id inválido
# ---------------------------------------------------------------------------


def test_commit_worker_handles_invalid_id_none() -> None:
    """edit_id = None não derruba o batch; edit é pulado e os outros
    continuam."""
    from notion_rpadv.services.notion_facade import CommitWorker
    from unittest.mock import MagicMock, patch

    conn = _make_conn()
    edits = [
        # Edit válido
        {"id": 1, "base": "Processos", "page_id": "p-1",
         "key": "status", "old_value": "Ativo", "new_value": "Arquivado"},
        # Edit com id None — antes derrubava o batch inteiro
        {"id": None, "base": "Processos", "page_id": "p-2",
         "key": "status", "old_value": "Ativo", "new_value": "Arquivado"},
        # Edit com id string vazio
        {"id": "", "base": "Processos", "page_id": "p-3",
         "key": "status", "old_value": "Ativo", "new_value": "Arquivado"},
        # Edit com id não-numérico
        {"id": "abc", "base": "Processos", "page_id": "p-4",
         "key": "status", "old_value": "Ativo", "new_value": "Arquivado"},
    ]
    worker = CommitWorker("token", conn, edits, "leonardo", "Processos")
    captured: list = []
    worker.finished.connect(lambda b, results: captured.append((b, results)))

    # Mock NotionClient.update_page para evitar HTTP real.
    mock_client = MagicMock()
    mock_client.update_page.return_value = None
    with patch(
        "notion_rpadv.services.notion_facade.NotionClient",
        return_value=mock_client,
    ):
        worker.run()

    assert len(captured) == 1, "finished signal não foi emitido"
    base, results = captured[0]
    assert base == "Processos"
    # Esperado: 4 results — todos chegam ao API mas com edit_id 0 quando
    # o id original era inválido. O loop NÃO deve crashar a meio.
    assert len(results) == 4, (
        f"Esperado 4 results (loop completo); obtido {len(results)}. "
        "Provável regressão de P1-004 — int(None) derrubou o loop."
    )


# ---------------------------------------------------------------------------
# Componente 3 — P1-001: Botão "+ Novo" removido
# ---------------------------------------------------------------------------


@requires_pyside6
def test_no_op_new_button_removed_from_toolbar() -> None:
    """BaseTablePage não deve mais expor o botão '+ Novo' até implementação
    real (P1-001 — opção A: esconder)."""
    import sys
    from PySide6.QtWidgets import QApplication, QPushButton
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade

    conn = _make_conn()
    facade = NotionFacade("dummy", conn)
    page = ProcessosPage(
        conn=conn, token="dummy", user="leonardo", facade=facade,
    )
    # Atributo _new_btn não deve mais existir
    assert not hasattr(page, "_new_btn"), (
        "Botão '+ Novo' (atributo _new_btn) não deveria existir mais "
        "(P1-001)."
    )
    # Defesa em profundidade: nenhum QPushButton com texto contendo 'Novo'.
    novos = [
        b for b in page.findChildren(QPushButton)
        if "Novo" in (b.text() or "")
    ]
    assert not novos, (
        f"Encontrado QPushButton com texto 'Novo': {[b.text() for b in novos]}"
    )


@requires_pyside6
def test_empty_state_no_create_button() -> None:
    """EmptyState não deve mais oferecer 'Criar primeiro registro' até
    implementação real."""
    import sys
    from PySide6.QtWidgets import QApplication, QPushButton
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.widgets.empty_state import EmptyState

    es = EmptyState(base_name="Processos", on_sync=lambda: None)
    botoes = [b.text() or "" for b in es.findChildren(QPushButton)]
    assert not any("Criar" in t for t in botoes), (
        f"EmptyState não deveria mais ter botão 'Criar primeiro registro'; "
        f"encontrado: {botoes}"
    )


def test_shortcut_registry_has_no_new_record_action() -> None:
    """Ctrl+N (action 'new_record') foi desregistrado do
    ShortcutRegistry."""
    from notion_rpadv.services.shortcuts_store import DEFAULT_SHORTCUTS
    assert "new_record" not in DEFAULT_SHORTCUTS, (
        "'new_record' (Ctrl+N) não deveria mais estar nos defaults do "
        "ShortcutRegistry — entry point removido em P1-001."
    )


# ---------------------------------------------------------------------------
# Componente 4 — P0-001: setClipRect nos delegates
# ---------------------------------------------------------------------------


# Nota: teste de paint via MagicMock(painter) é inviável porque PySide6
# valida tipo do argumento em ``super().paint(painter, option, index)``
# e rejeita MagicMock. Testes de assinatura via inspect.getsource cobrem
# regressão suficiente para o Round 1; validação visual fica no smoke
# manual.


# Round simplificação CnjDelegate (Lote 1): CnjDelegate foi REMOVIDO
# da hierarquia de delegates. O teste antigo
# ``test_cnj_delegate_setclip_in_source`` perdeu sentido junto com a
# classe — o Round 1 aplicou setClipRect lá, o hotfix v2 reescreveu
# tudo via initStyleOption, e este round descartou a coluna two-line.
# Coluna numero_do_processo agora cai no PropDelegate default.


@requires_pyside6
def test_cnj_delegate_class_removed() -> None:
    """Round simplificação (Lote 1): garantir que CnjDelegate não voltou
    acidentalmente. Hierarquia processual é vista pela coluna 'Processo
    pai' (relation, picker da Fase 4)."""
    from notion_rpadv.models import delegates as dmod
    assert not hasattr(dmod, "CnjDelegate"), (
        "CnjDelegate foi removido neste round — voltar a ter regride "
        "a decisão de design (two-line redundante com coluna Processo "
        "pai) e o bug de scroll ghost."
    )


@requires_pyside6
def test_sucessor_delegate_setclip_in_source() -> None:
    """Verificação estática: source de SucessorDelegate.paint contém
    setClipRect."""
    import inspect
    from notion_rpadv.models.delegates import SucessorDelegate

    src = inspect.getsource(SucessorDelegate.paint)
    assert "setClipRect" in src, (
        "SucessorDelegate.paint deve chamar painter.setClipRect (P0-001)."
    )


# ---------------------------------------------------------------------------
# Componente 5 — P1-002: re-bind de delegates em modelReset
# ---------------------------------------------------------------------------


@requires_pyside6
def test_clientes_delegate_rebinds_on_modelreset() -> None:
    """Quando _cols muda (picker da Fase 4), SucessorDelegate deve ficar
    no novo índice de 'sucessor_de', não no antigo."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_bulk_edit.config import DATA_SOURCES
    from notion_bulk_edit.schema_registry import get_schema_registry
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.delegates import SucessorDelegate
    from notion_rpadv.pages.clientes import ClientesPage
    from notion_rpadv.services.notion_facade import NotionFacade

    reg = get_schema_registry()
    audit_conn = reg._audit_conn
    cache_conn = _make_conn()
    facade = NotionFacade("dummy", cache_conn)
    dsid = DATA_SOURCES["Clientes"]
    cache_db.clear_user_columns(audit_conn, "leonardo", dsid)
    try:
        page = ClientesPage(
            conn=cache_conn, token="dummy", user="leonardo",
            facade=facade, audit_conn=audit_conn,
        )
        cols_before = page._model.cols()
        idx_before = cols_before.index("sucessor_de")
        # Confirma delegate está no índice esperado
        d_before = page._table.itemDelegateForColumn(idx_before)
        assert isinstance(d_before, SucessorDelegate), (
            f"Delegate ANTES deveria ser SucessorDelegate em col {idx_before}; "
            f"obtido {type(d_before).__name__}"
        )

        # Simula o picker escondendo "sucedido_por" (vem antes de
        # "sucessor_de" no default), o que faz "sucessor_de" deslizar
        # 1 índice para a esquerda.
        new_cols = [c for c in cols_before if c != "sucedido_por"]
        cache_db.set_user_columns(audit_conn, "leonardo", dsid, new_cols)
        page._model.reload(preserve_dirty=True)

        cols_after = page._model.cols()
        idx_after = cols_after.index("sucessor_de")
        assert idx_after != idx_before, (
            "Pré-condição do teste: novo índice deveria diferir do antigo "
            "(picker mudou ordem)."
        )
        d_after = page._table.itemDelegateForColumn(idx_after)
        assert isinstance(d_after, SucessorDelegate), (
            f"Delegate DEPOIS deveria estar em col {idx_after} "
            f"(novo índice de 'sucessor_de'); obtido "
            f"{type(d_after).__name__}. Regressão P1-002."
        )
        # Defesa: o índice ANTIGO (que agora aponta para outra coluna) NÃO
        # deveria mais ter SucessorDelegate.
        d_old_pos = page._table.itemDelegateForColumn(idx_before)
        assert not isinstance(d_old_pos, SucessorDelegate), (
            f"Delegate antigo continuou na coluna {idx_before} (que "
            "agora é outra coluna). P1-002 não foi corrigido."
        )
    finally:
        cache_db.clear_user_columns(audit_conn, "leonardo", dsid)


@requires_pyside6
def test_processos_no_specific_delegate_on_title_column() -> None:
    """Round simplificação CnjDelegate (Lote 1): a coluna do título em
    Processos NÃO recebe mais delegate específico. Cai no PropDelegate
    global (default) que pinta o CNJ em font default sem two-line. Sem
    CnjDelegate, ProcessosPage também não tem mais ``_install_delegates``
    nem ``_cnj_delegate``."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade

    cache_conn = _make_conn()
    facade = NotionFacade("dummy", cache_conn)
    page = ProcessosPage(
        conn=cache_conn, token="dummy", user="leonardo", facade=facade,
    )
    assert not hasattr(page, "_cnj_delegate"), (
        "ProcessosPage._cnj_delegate não deveria mais existir "
        "(CnjDelegate foi removido)."
    )
    assert not hasattr(page, "_install_delegates"), (
        "ProcessosPage._install_delegates só fazia sentido para o "
        "re-bind do CnjDelegate; sem ele, deve ser removido."
    )


# ---------------------------------------------------------------------------
# Componente 6 — P1-003: MultiSelectEditor
# ---------------------------------------------------------------------------


@requires_pyside6
def test_multi_select_editor_only_accepts_valid_options() -> None:
    """MultiSelectEditor descarta valores que não estão em spec.opcoes —
    impede typo do usuário criar opção fantasma no Notion."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.widgets.multi_select_editor import MultiSelectEditor

    spec = PropSpec(
        notion_name="Tipo",
        tipo="multi_select",
        label="Tipo",
        opcoes=("A", "B", "C", "D", "Banco do Brasil"),
    )
    editor = MultiSelectEditor(spec)
    editor.set_values(["Banco do Brasil", "OPCAO_INVALIDA", "B"])
    got = editor.values()
    assert "OPCAO_INVALIDA" not in got, (
        f"Editor aceitou valor fora do spec: {got!r}"
    )
    assert set(got) == {"Banco do Brasil", "B"}


@requires_pyside6
def test_multi_select_editor_preserves_spec_order() -> None:
    """values() retorna na ordem do spec.opcoes, não na ordem que o
    usuário marcou."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.widgets.multi_select_editor import MultiSelectEditor

    spec = PropSpec(
        notion_name="X",
        tipo="multi_select",
        label="X",
        opcoes=("Alpha", "Bravo", "Charlie", "Delta"),
    )
    editor = MultiSelectEditor(spec)
    # Usuário marca em ordem aleatória
    editor.set_values(["Charlie", "Alpha"])
    got = editor.values()
    # Ordem deve ser do spec, não da entrada
    assert got == ["Alpha", "Charlie"], (
        f"values() não preservou ordem do spec.opcoes: {got!r}"
    )


@requires_pyside6
def test_multi_select_editor_empty_initial_state() -> None:
    """Editor sem valores tem values() == []."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.widgets.multi_select_editor import MultiSelectEditor

    spec = PropSpec(
        notion_name="X", tipo="multi_select", label="X",
        opcoes=("A", "B"),
    )
    editor = MultiSelectEditor(spec)
    assert editor.values() == []


@requires_pyside6
def test_delegates_uses_multi_select_editor_for_multi_select() -> None:
    """PropDelegate.createEditor agora retorna MultiSelectEditor (não
    QLineEdit) para tipo multi_select."""
    import sys
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import (
        QApplication, QStyleOptionViewItem, QWidget,
    )
    QApplication.instance() or QApplication(sys.argv)

    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.delegates import PropDelegate
    from notion_rpadv.widgets.multi_select_editor import MultiSelectEditor

    delegate = PropDelegate()
    spec = PropSpec(
        notion_name="Tipo", tipo="multi_select", label="Tipo",
        opcoes=("A", "B"),
    )
    # Mock _get_spec_from_index para devolver o spec sem precisar de model.
    from notion_rpadv.models import delegates as dmod
    original = dmod._get_spec_from_index
    dmod._get_spec_from_index = lambda idx: spec
    try:
        parent = QWidget()  # QWidget real, não MagicMock
        editor = delegate.createEditor(
            parent, QStyleOptionViewItem(), QModelIndex(),
        )
        assert isinstance(editor, MultiSelectEditor), (
            f"createEditor deveria devolver MultiSelectEditor para "
            f"multi_select; obtido {type(editor).__name__}"
        )
    finally:
        dmod._get_spec_from_index = original
