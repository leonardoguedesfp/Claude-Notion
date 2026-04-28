"""Fase 4 — picker de colunas + persistência por usuário.

Testes cobrem:
- Helpers ``get/set/clear_user_columns`` em ``cache.db`` (Componente 1).
- ``SchemaRegistry.colunas_visiveis(base, user_id)`` lendo meta_user_columns
  e fazendo drift protection (Componente 2).
- Helper público ``schemas.colunas_visiveis`` delegando ao registry
  (Componente 3).
- ``BaseTableModel`` aceita ``user_id`` e recalcula ``_cols`` em reload
  (Componente 4).
- ``BaseTablePage`` propaga ``user_id`` ao model (Componente 5).
- Botão "⋮ Colunas" + handlers (Componente 6).
- Header context menu "Esconder coluna" (Componente 7).

Arquivo separado de ``test_audit_smoke.py`` para que o resumo final
(`231+19 = 250+ passed`) seja imediato.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(
    not _PYSIDE6, reason="PySide6 not installed",
)


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "schemas"


def _audit_only_conn() -> sqlite3.Connection:
    """Conn com apenas init_audit_db aplicado (espelha helper de
    test_audit_smoke)."""
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_audit_db(conn)
    return conn


def _populated_conn(*labels: str) -> tuple[sqlite3.Connection, dict[str, str]]:
    """Conn com meta_schemas populado e mapa {label: data_source_id}."""
    from notion_bulk_edit.schema_parser import (
        compute_schema_hash, parse_to_schema_json,
    )
    from notion_rpadv.cache import db as cache_db

    conn = _audit_only_conn()
    dsid_by_label: dict[str, str] = {}
    for label in labels:
        path = _FIXTURES_DIR / f"{label.lower()}_raw.json"
        if not path.exists():
            pytest.skip(f"fixture {path} ausente")
        raw = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_to_schema_json(raw, label)
        dsid_by_label[label] = parsed["data_source_id"]
        cache_db.upsert_schema(
            conn, parsed["data_source_id"], label,
            parsed["title_property"],
            json.dumps(parsed, sort_keys=True, ensure_ascii=False),
            compute_schema_hash(parsed), 1700000000.0,
        )
    return conn, dsid_by_label


# ---------------------------------------------------------------------------
# Componente 1 — helpers em cache.db para meta_user_columns
# ---------------------------------------------------------------------------


def test_FASE4_set_and_get_user_columns_roundtrip() -> None:
    """Set → get retorna a mesma lista na mesma ordem."""
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    cache_db.set_user_columns(
        conn, "leonardo", "dsid-1", ["nome", "categoria", "tarefas"],
    )
    got = cache_db.get_user_columns(conn, "leonardo", "dsid-1")
    assert got == ["nome", "categoria", "tarefas"]


def test_FASE4_get_user_columns_returns_none_when_unset() -> None:
    """Sem entrada, get retorna None — caller cai no default."""
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    assert cache_db.get_user_columns(conn, "leonardo", "dsid-1") is None


def test_FASE4_set_user_columns_upsert_overwrites() -> None:
    """Dois sets para a mesma chave: o segundo prevalece."""
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    cache_db.set_user_columns(conn, "leo", "dsid", ["a", "b"])
    cache_db.set_user_columns(conn, "leo", "dsid", ["c"])
    assert cache_db.get_user_columns(conn, "leo", "dsid") == ["c"]


def test_FASE4_clear_user_columns_removes_entry() -> None:
    """Clear → próximo get retorna None."""
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    cache_db.set_user_columns(conn, "leo", "dsid", ["x"])
    cache_db.clear_user_columns(conn, "leo", "dsid")
    assert cache_db.get_user_columns(conn, "leo", "dsid") is None


def test_FASE4_set_user_columns_isolated_by_user_and_base() -> None:
    """2 users × 2 bases = 4 entradas independentes."""
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    cache_db.set_user_columns(conn, "leo", "dsA", ["a1"])
    cache_db.set_user_columns(conn, "leo", "dsB", ["b1"])
    cache_db.set_user_columns(conn, "deb", "dsA", ["a2"])
    cache_db.set_user_columns(conn, "deb", "dsB", ["b2"])
    assert cache_db.get_user_columns(conn, "leo", "dsA") == ["a1"]
    assert cache_db.get_user_columns(conn, "leo", "dsB") == ["b1"]
    assert cache_db.get_user_columns(conn, "deb", "dsA") == ["a2"]
    assert cache_db.get_user_columns(conn, "deb", "dsB") == ["b2"]


# ---------------------------------------------------------------------------
# Componente 2 — SchemaRegistry.colunas_visiveis(base, user_id)
# ---------------------------------------------------------------------------


def test_FASE4_registry_colunas_visiveis_no_user_returns_default() -> None:
    """Sem user_id, retorna baseado em default_visible do schema."""
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn, _ = _populated_conn("Catalogo")
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    cols = reg.colunas_visiveis("Catalogo")
    # Title sempre primeiro
    assert cols[0] == "nome"
    # System properties não devem entrar
    assert "criado_em" not in cols
    assert "atualizado_em" not in cols


def test_FASE4_registry_colunas_visiveis_with_user_returns_stored() -> None:
    """Com user_id e prefs salvas, retorna a lista do usuário na ordem."""
    from notion_bulk_edit.schema_registry import SchemaRegistry
    from notion_rpadv.cache import db as cache_db
    conn, dsids = _populated_conn("Catalogo")
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    cache_db.set_user_columns(
        conn, "leo", dsids["Catalogo"], ["categoria", "nome"],
    )
    cols = reg.colunas_visiveis("Catalogo", user_id="leo")
    assert cols == ["categoria", "nome"]


def test_FASE4_registry_colunas_visiveis_filters_drifted_slugs() -> None:
    """Prefs do usuário com slug ausente do schema → slug filtrado."""
    from notion_bulk_edit.schema_registry import SchemaRegistry
    from notion_rpadv.cache import db as cache_db
    conn, dsids = _populated_conn("Catalogo")
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    cache_db.set_user_columns(
        conn, "leo", dsids["Catalogo"],
        ["nome", "_slug_que_nao_existe", "categoria"],
    )
    cols = reg.colunas_visiveis("Catalogo", user_id="leo")
    assert "_slug_que_nao_existe" not in cols
    assert cols == ["nome", "categoria"]


def test_FASE4_registry_colunas_visiveis_falls_back_when_user_has_no_prefs() -> None:
    """User existe mas não tem entrada → fallback ao default."""
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn, _ = _populated_conn("Catalogo")
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    default = reg.colunas_visiveis("Catalogo")
    user_view = reg.colunas_visiveis("Catalogo", user_id="leo")
    assert user_view == default


def test_FASE4_registry_colunas_visiveis_unknown_base_returns_empty() -> None:
    """Base que não está no registry → lista vazia, sem crash."""
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    assert reg.colunas_visiveis("BaseInexistente") == []
    assert reg.colunas_visiveis("BaseInexistente", user_id="leo") == []


# ---------------------------------------------------------------------------
# Componente 3 — schemas.colunas_visiveis(base, user_id=None)
# ---------------------------------------------------------------------------


def test_FASE4_schemas_colunas_visiveis_delegates_to_registry() -> None:
    """Helper público sem user_id retorna o que o registry retorna."""
    from notion_bulk_edit.schemas import colunas_visiveis
    from notion_bulk_edit.schema_registry import get_schema_registry
    # conftest.py popula o singleton com fixtures.
    via_helper = colunas_visiveis("Catalogo")
    via_registry = get_schema_registry().colunas_visiveis("Catalogo")
    assert via_helper == via_registry


def test_FASE4_schemas_colunas_visiveis_with_user_id_propagates() -> None:
    """Chamada com user_id propaga para o registry."""
    from notion_bulk_edit.schemas import colunas_visiveis
    from notion_bulk_edit.schema_registry import get_schema_registry
    reg = get_schema_registry()
    # Sem prefs, com user_id deve retornar default (registry resolve fallback)
    via_helper = colunas_visiveis("Catalogo", user_id="leo-sem-prefs")
    via_registry = reg.colunas_visiveis("Catalogo", user_id="leo-sem-prefs")
    assert via_helper == via_registry


def test_FASE4_schemas_colunas_visiveis_returns_empty_when_no_registry() -> None:
    """Sem singleton inicializado → fallback gracioso (lista vazia)."""
    from notion_bulk_edit import schemas as schemas_mod
    import notion_bulk_edit.schema_registry as sr

    saved = sr._registry
    sr._registry = None
    try:
        assert schemas_mod.colunas_visiveis("Processos") == []
    finally:
        sr._registry = saved


# ---------------------------------------------------------------------------
# Componente 4 — BaseTableModel.__init__ aceita user_id
# ---------------------------------------------------------------------------


def _model_test_conn() -> sqlite3.Connection:
    """Conn com schema completo (cache+audit) para BaseTableModel."""
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_db(conn)
    return conn


@requires_pyside6
def test_FASE4_base_table_model_uses_user_id_for_cols() -> None:
    """Model com user_id e prefs salvas tem _cols na ordem do usuário."""
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel
    from notion_bulk_edit.schema_registry import get_schema_registry

    # Resolve o dsid de Catalogo via registry (singleton já populado pelo conftest)
    reg = get_schema_registry()
    dsid = reg._base_to_dsid["Catalogo"]

    conn = _model_test_conn()
    # O conftest popula o singleton com um audit_conn próprio. Para o picker
    # ler/gravar no mesmo lugar que o registry consulta, set_user_columns
    # precisa ir no audit_conn do registry.
    cache_db.set_user_columns(
        reg._audit_conn, "leo", dsid, ["categoria", "nome"],
    )
    try:
        model = BaseTableModel(
            "Catalogo", conn, audit_conn=reg._audit_conn, user_id="leo",
        )
        assert model.cols() == ["categoria", "nome"]
    finally:
        cache_db.clear_user_columns(reg._audit_conn, "leo", dsid)


@requires_pyside6
def test_FASE4_base_table_model_reload_picks_up_new_user_prefs() -> None:
    """Salvar nova pref + chamar reload → _cols reflete a mudança."""
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel
    from notion_bulk_edit.schema_registry import get_schema_registry

    reg = get_schema_registry()
    dsid = reg._base_to_dsid["Catalogo"]

    conn = _model_test_conn()
    try:
        model = BaseTableModel(
            "Catalogo", conn, audit_conn=reg._audit_conn, user_id="leo",
        )
        cols_before = model.cols()
        cache_db.set_user_columns(
            reg._audit_conn, "leo", dsid, ["nome"],
        )
        model.reload(preserve_dirty=True)
        cols_after = model.cols()
        assert cols_after == ["nome"]
        assert cols_after != cols_before
    finally:
        cache_db.clear_user_columns(reg._audit_conn, "leo", dsid)


@requires_pyside6
def test_FASE4_base_table_model_default_when_no_user_id() -> None:
    """user_id=None mantém comportamento legado (defaults do schema)."""
    from notion_rpadv.models.base_table_model import BaseTableModel
    from notion_bulk_edit.schema_registry import get_schema_registry
    reg = get_schema_registry()
    conn = _model_test_conn()
    model = BaseTableModel(
        "Catalogo", conn, audit_conn=reg._audit_conn,
    )
    expected = reg.colunas_visiveis("Catalogo")
    assert model.cols() == expected
    assert model._user_id is None


# ---------------------------------------------------------------------------
# Componente 5 — BaseTablePage propaga user_id ao model
# ---------------------------------------------------------------------------


def _make_page_conn() -> sqlite3.Connection:
    """In-memory cache+audit, igual ao _make_cache de test_v2_visual_bugs."""
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_db(conn)
    return conn


@requires_pyside6
def test_FASE4_base_table_page_propagates_user_id_to_model() -> None:
    """Smoke estrutural: ProcessosPage com user='leonardo' → model._user_id."""
    import sys
    from PySide6.QtWidgets import QApplication
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    QApplication.instance() or QApplication(sys.argv)

    conn = _make_page_conn()
    facade = NotionFacade("dummy", conn)
    page = ProcessosPage(
        conn=conn, token="dummy", user="leonardo", facade=facade,
    )
    assert page._model._user_id == "leonardo"


# ---------------------------------------------------------------------------
# Componente 6 — Picker button + handlers
# ---------------------------------------------------------------------------


@requires_pyside6
def test_FASE4_picker_button_present_in_toolbar() -> None:
    """Botão '⋮ Colunas' existe e tem texto correto."""
    import sys
    from PySide6.QtWidgets import QApplication
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    QApplication.instance() or QApplication(sys.argv)

    conn = _make_page_conn()
    facade = NotionFacade("dummy", conn)
    page = ProcessosPage(
        conn=conn, token="dummy", user="leonardo", facade=facade,
    )
    assert hasattr(page, "_cols_btn")
    assert "Colunas" in page._cols_btn.text()


@requires_pyside6
def test_FASE4_picker_handler_persists_visibility_change() -> None:
    """Toggle handler persiste em meta_user_columns e recarrega o model."""
    import sys
    from PySide6.QtWidgets import QApplication
    from notion_bulk_edit.config import DATA_SOURCES
    from notion_bulk_edit.schema_registry import get_schema_registry
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    QApplication.instance() or QApplication(sys.argv)

    reg = get_schema_registry()
    # Conftest popula o registry com um audit_conn separado. Para o handler
    # do picker enxergar o write feito pelos testes (e vice-versa), o audit
    # conn passado para a page TEM QUE SER o mesmo do registry.
    audit_conn = reg._audit_conn
    cache_conn = _make_page_conn()
    facade = NotionFacade("dummy", cache_conn)
    dsid = DATA_SOURCES["Processos"]
    cache_db.clear_user_columns(audit_conn, "leonardo", dsid)
    try:
        page = ProcessosPage(
            conn=cache_conn, token="dummy", user="leonardo",
            facade=facade, audit_conn=audit_conn,
        )
        # Snapshot antes
        cols_before = page._model.cols()
        # Pega um slug oculto para marcar como visível
        all_keys = list(reg.schema_for_base("Processos").keys())
        hidden = [k for k in all_keys if k not in cols_before]
        assert hidden, "fixture deveria ter pelo menos 1 coluna oculta"
        slug_to_show = hidden[0]

        handler = page._make_columns_picker_handler(slug_to_show)
        handler(True)  # check → adiciona

        # Persistido em meta_user_columns
        stored = cache_db.get_user_columns(audit_conn, "leonardo", dsid)
        assert stored is not None
        assert slug_to_show in stored
        # Model recarregou
        assert slug_to_show in page._model.cols()
    finally:
        cache_db.clear_user_columns(audit_conn, "leonardo", dsid)


@requires_pyside6
def test_FASE4_picker_handler_uncheck_removes_slug() -> None:
    """Toggle off remove o slug da lista."""
    import sys
    from PySide6.QtWidgets import QApplication
    from notion_bulk_edit.config import DATA_SOURCES
    from notion_bulk_edit.schema_registry import get_schema_registry
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    QApplication.instance() or QApplication(sys.argv)

    reg = get_schema_registry()
    audit_conn = reg._audit_conn
    cache_conn = _make_page_conn()
    facade = NotionFacade("dummy", cache_conn)
    dsid = DATA_SOURCES["Processos"]
    cache_db.clear_user_columns(audit_conn, "leonardo", dsid)
    try:
        page = ProcessosPage(
            conn=cache_conn, token="dummy", user="leonardo",
            facade=facade, audit_conn=audit_conn,
        )
        # Slug visível por default que NÃO é o título
        cols = page._model.cols()
        non_title = [c for c in cols if c != "numero_do_processo"]
        assert non_title, "esperado pelo menos 1 coluna não-título visível"
        slug_to_hide = non_title[0]

        handler = page._make_columns_picker_handler(slug_to_hide)
        handler(False)

        assert slug_to_hide not in page._model.cols()
    finally:
        cache_db.clear_user_columns(audit_conn, "leonardo", dsid)


@requires_pyside6
def test_FASE4_picker_reset_to_default_clears_prefs() -> None:
    """_reset_columns_to_default → linha removida e _cols volta ao default."""
    import sys
    from PySide6.QtWidgets import QApplication
    from notion_bulk_edit.config import DATA_SOURCES
    from notion_bulk_edit.schema_registry import get_schema_registry
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    QApplication.instance() or QApplication(sys.argv)

    reg = get_schema_registry()
    audit_conn = reg._audit_conn
    cache_conn = _make_page_conn()
    facade = NotionFacade("dummy", cache_conn)
    dsid = DATA_SOURCES["Processos"]
    cache_db.clear_user_columns(audit_conn, "leonardo", dsid)
    try:
        # Cria pref custom, depois reseta
        cache_db.set_user_columns(
            audit_conn, "leonardo", dsid, ["numero_do_processo"],
        )
        page = ProcessosPage(
            conn=cache_conn, token="dummy", user="leonardo",
            facade=facade, audit_conn=audit_conn,
        )
        assert page._model.cols() == ["numero_do_processo"]

        page._reset_columns_to_default()

        assert cache_db.get_user_columns(audit_conn, "leonardo", dsid) is None
        # Model voltou ao default — número de cols > 1
        assert len(page._model.cols()) > 1
    finally:
        cache_db.clear_user_columns(audit_conn, "leonardo", dsid)


# Nota: abertura do QMenu (``_open_columns_picker``) e construção do menu
# de header (``_on_header_context_menu`` no path não-título) entram em
# event loop modal via ``QMenu.exec`` — slot Qt não-pateável por
# ``unittest.mock``. Cobertura desses paths fica no smoke manual.
# O comportamento data-path (handlers, persistência, drift, reset) é
# coberto pelos testes acima.


# ---------------------------------------------------------------------------
# Componente 7 — Header context menu (paths não-modais)
# ---------------------------------------------------------------------------


@requires_pyside6
def test_FASE4_header_context_menu_hide_path_via_handler_equivalence() -> None:
    """O caminho 'esconder via context menu' é equivalente ao 'esconder via
    picker'. Garante que a closure usada pelo context menu (que dispara
    ``_make_columns_picker_handler(slug)(False)``) esconde a coluna."""
    import sys
    from PySide6.QtWidgets import QApplication
    from notion_bulk_edit.config import DATA_SOURCES
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    QApplication.instance() or QApplication(sys.argv)

    from notion_bulk_edit.schema_registry import get_schema_registry
    reg = get_schema_registry()
    audit_conn = reg._audit_conn
    cache_conn = _make_page_conn()
    facade = NotionFacade("dummy", cache_conn)
    dsid = DATA_SOURCES["Processos"]
    cache_db.clear_user_columns(audit_conn, "leonardo", dsid)
    try:
        page = ProcessosPage(
            conn=cache_conn, token="dummy", user="leonardo",
            facade=facade, audit_conn=audit_conn,
        )
        cols = page._model.cols()
        slug_target = cols[1]  # primeira coluna não-título
        # Esta é exatamente a expressão wireada como triggered.connect
        # do action "Esconder coluna…" dentro de _on_header_context_menu.
        page._make_columns_picker_handler(slug_target)(False)
        assert slug_target not in page._model.cols()
    finally:
        cache_db.clear_user_columns(audit_conn, "leonardo", dsid)


@requires_pyside6
def test_FASE4_header_context_menu_skips_title_column() -> None:
    """Clique direito no header da coluna do título → return early
    (QMenu não é instanciado)."""
    import sys
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication
    from unittest.mock import patch
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    QApplication.instance() or QApplication(sys.argv)

    conn = _make_page_conn()
    facade = NotionFacade("dummy", conn)
    page = ProcessosPage(
        conn=conn, token="dummy", user="leonardo", facade=facade,
    )
    header = page._table.horizontalHeader()
    # logicalIndexAt = 0 → coluna do título 'numero_do_processo'.
    with patch.object(header, "logicalIndexAt", return_value=0), \
            patch(
                "notion_rpadv.pages.base_table_page.QMenu",
            ) as MockQMenu:
        page._on_header_context_menu(QPoint(10, 5))
        # Title → return early antes de QMenu(self).
        assert not MockQMenu.called


@requires_pyside6
def test_FASE4_header_context_menu_invalid_section_noop() -> None:
    """Clique fora de qualquer section (logicalIndexAt < 0) → no-op."""
    import sys
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication
    from unittest.mock import patch
    from notion_rpadv.pages.processos import ProcessosPage
    from notion_rpadv.services.notion_facade import NotionFacade
    QApplication.instance() or QApplication(sys.argv)

    conn = _make_page_conn()
    facade = NotionFacade("dummy", conn)
    page = ProcessosPage(
        conn=conn, token="dummy", user="leonardo", facade=facade,
    )
    header = page._table.horizontalHeader()
    with patch.object(header, "logicalIndexAt", return_value=-1), \
            patch(
                "notion_rpadv.pages.base_table_page.QMenu",
            ) as MockQMenu:
        page._on_header_context_menu(QPoint(0, 0))
        assert not MockQMenu.called
