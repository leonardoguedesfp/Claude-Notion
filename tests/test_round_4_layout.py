"""Round 4 (29-abr-2026) — tests for editorial column layout + reset migration.

Cobre:
- ``notion_rpadv.layout_defaults`` (DEFAULT_LAYOUTS, helpers)
- ``cache_db.wipe_user_columns_if_layout_changed`` (migração one-shot)
- ``schema_registry.colunas_visiveis`` consumindo o layout editorial
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from notion_rpadv.cache import db as cache_db


_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "schemas"


def _audit_only_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_audit_db(conn)
    return conn


def _load_fixture(base: str) -> dict:
    path = _FIXTURES_DIR / f"{base.lower()}_raw.json"
    if not path.exists():
        pytest.skip(f"fixture ausente: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# layout_defaults: DEFAULT_LAYOUTS, default_visible_slugs, default_width
# ---------------------------------------------------------------------------


def test_R4_default_visible_slugs_clientes_in_spec_order() -> None:
    """Clientes: 7 slugs na ordem do spec do Round 4."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    assert default_visible_slugs("Clientes") == [
        "nome", "telefone", "processos", "e_mail",
        "data_de_aposentadoria", "data_de_ingresso_no_bb",
        "situacao_funcional",
    ]


def test_R4_default_visible_slugs_processos_in_spec_order() -> None:
    """Processos: 7 slugs na ordem do spec."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    assert default_visible_slugs("Processos") == [
        "numero_do_processo", "clientes", "fase",
        "tipo_de_processo", "tipo_de_acao", "instancia",
        "detalhamento_da_acao",
    ]


def test_R4_default_visible_slugs_tarefas_includes_round_4_props() -> None:
    """Tarefas: 10 slugs incluindo area e prioridade (props novas)."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    cols = default_visible_slugs("Tarefas")
    assert cols == [
        "tarefa", "tipo_de_tarefa", "cliente", "processo",
        "status", "area", "prioridade",
        "data_de_publicacao", "prazo_fatal", "responsavel",
    ]


def test_R4_default_visible_slugs_catalogo_includes_observacoes() -> None:
    """Catalogo: 3 slugs incluindo observacoes (rich_text editorialmente
    visível, contrariando a heurística antiga de esconder rich_text)."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    assert default_visible_slugs("Catalogo") == [
        "nome", "categoria", "observacoes",
    ]


def test_R4_default_visible_slugs_unknown_base_returns_empty() -> None:
    """Base não coberta pelo layout → lista vazia (caller cai no fallback)."""
    from notion_rpadv.layout_defaults import default_visible_slugs
    assert default_visible_slugs("Inexistente") == []


def test_R4_default_width_returns_layout_value() -> None:
    """Slug conhecido retorna width do layout."""
    from notion_rpadv.layout_defaults import default_width
    assert default_width("Clientes", "nome") == 280
    assert default_width("Tarefas", "tarefa") == 280
    assert default_width("Tarefas", "responsavel") == 160
    assert default_width("Catalogo", "categoria") == 220


def test_R4_default_width_returns_none_for_unknown_slug() -> None:
    """Slug não no layout → None (caller usa piso de font metrics)."""
    from notion_rpadv.layout_defaults import default_width
    assert default_width("Clientes", "slug_qualquer") is None
    assert default_width("Inexistente", "nome") is None


def test_R4_default_layouts_widths_are_positive_ints() -> None:
    """Sanity: nenhuma largura negativa ou zero (quebraria QHeaderView)."""
    from notion_rpadv.layout_defaults import DEFAULT_LAYOUTS
    for base, items in DEFAULT_LAYOUTS.items():
        for slug, width in items:
            assert isinstance(width, int), f"{base}.{slug}: width não é int"
            assert width > 0, f"{base}.{slug}: width <= 0"


def test_R4_default_layouts_no_duplicate_slugs_per_base() -> None:
    """Sanity: cada slug aparece no máximo uma vez por base."""
    from notion_rpadv.layout_defaults import DEFAULT_LAYOUTS
    for base, items in DEFAULT_LAYOUTS.items():
        slugs = [s for s, _w in items]
        assert len(slugs) == len(set(slugs)), f"slug duplicado em {base}"


# ---------------------------------------------------------------------------
# wipe_user_columns_if_layout_changed
# ---------------------------------------------------------------------------


def test_R4_wipe_first_boot_with_no_version_meta_sets_version() -> None:
    """Sem meta.layout_version → wipe (vazio, retorna 0) + grava versão."""
    conn = _audit_only_conn()
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    assert deleted == 0  # nada pra apagar, mas grava versão
    row = conn.execute(
        "SELECT value FROM meta WHERE key='layout_version'",
    ).fetchone()
    assert row is not None
    assert row["value"] == "1"


def test_R4_wipe_first_boot_with_existing_prefs_wipes_them() -> None:
    """Sem meta.layout_version mas com prefs salvas → wipe efetivo."""
    conn = _audit_only_conn()
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a", "b"])
    cache_db.set_user_columns(conn, "deborah", "dsid-2", ["x"])
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    assert deleted == 2
    # prefs sumiram
    assert cache_db.get_user_columns(conn, "leo", "dsid-1") is None
    assert cache_db.get_user_columns(conn, "deborah", "dsid-2") is None


def test_R4_wipe_skips_when_version_matches() -> None:
    """Já estava na versão atual → no-op (retorna 0, prefs preservadas)."""
    conn = _audit_only_conn()
    cache_db.wipe_user_columns_if_layout_changed(conn, 1)  # primeiro boot
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a", "b"])
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    assert deleted == 0
    # prefs intactas
    assert cache_db.get_user_columns(conn, "leo", "dsid-1") == ["a", "b"]


def test_R4_wipe_runs_when_current_version_higher() -> None:
    """Versão armazenada < current → wipe + bump."""
    conn = _audit_only_conn()
    cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a"])
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 2)
    assert deleted == 1
    row = conn.execute(
        "SELECT value FROM meta WHERE key='layout_version'",
    ).fetchone()
    assert row["value"] == "2"


def test_R4_wipe_skips_when_current_version_lower() -> None:
    """Versão armazenada > current (downgrade) → no-op por segurança."""
    conn = _audit_only_conn()
    cache_db.wipe_user_columns_if_layout_changed(conn, 5)
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a"])
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 3)
    assert deleted == 0
    assert cache_db.get_user_columns(conn, "leo", "dsid-1") == ["a"]


def test_R4_wipe_handles_corrupted_version_value() -> None:
    """meta.layout_version corrompido (não-int) → trata como ausente, faz wipe."""
    conn = _audit_only_conn()
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('layout_version', 'corrupted')",
    )
    cache_db.set_user_columns(conn, "leo", "dsid-1", ["a"])
    conn.commit()
    deleted = cache_db.wipe_user_columns_if_layout_changed(conn, 1)
    assert deleted == 1


# ---------------------------------------------------------------------------
# schema_registry.colunas_visiveis using layout
# ---------------------------------------------------------------------------


def test_R4_colunas_visiveis_uses_editorial_layout_for_catalogo() -> None:
    """Sem user_id, base conhecida → retorna ordem do layout editorial."""
    if not (_FIXTURES_DIR / "catalogo_raw.json").exists():
        pytest.skip("fixture catalogo_raw.json ausente")
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    raw = _load_fixture("Catalogo")
    mock_client = MagicMock()
    mock_client.get_data_source.return_value = raw
    reg.refresh_from_api("Catalogo", raw["id"], mock_client)
    cols = reg.colunas_visiveis("Catalogo")
    assert cols == ["nome", "categoria", "observacoes"]


def test_R4_colunas_visiveis_filters_layout_slugs_not_in_schema() -> None:
    """Layout pode ter slug que ainda não chegou no schema (refresh
    pendente). Filtra silenciosamente em vez de retornar header sem PropSpec."""
    if not (_FIXTURES_DIR / "tarefas_raw.json").exists():
        pytest.skip("fixture tarefas_raw.json ausente")
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    raw = _load_fixture("Tarefas")
    mock_client = MagicMock()
    mock_client.get_data_source.return_value = raw
    reg.refresh_from_api("Tarefas", raw["id"], mock_client)
    cols = reg.colunas_visiveis("Tarefas")
    # area/prioridade não estão na fixture (props novas do Round 4); o
    # layout as inclui mas elas ficam filtradas até refresh pegar o schema novo.
    schema_keys = set(reg.schema_for_base("Tarefas").keys())
    for slug in cols:
        assert slug in schema_keys, f"slug {slug!r} retornado mas ausente do schema"


def test_R4_colunas_visiveis_falls_back_to_heuristic_for_unknown_base() -> None:
    """Base sem entry em DEFAULT_LAYOUTS → cai na heurística do schema_parser
    (default_visible=True ordenados por default_order). Garante que adicionar
    bases novas sem layout editorial não quebra o app."""
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    # Schema sintético com 3 props: title (default_visible) + select (default_visible)
    # + rich_text (default_visible=False).
    synthetic_schema = {
        "data_source_id": "dsid-syn",
        "base_label": "BaseSemLayout",
        "title_property": "Nome",
        "title_key": "nome",
        "properties": {
            "nome": {
                "notion_name": "Nome", "tipo": "title", "label": "Nome",
                "editavel": True, "obrigatorio": True, "opcoes": [],
                "default_visible": True, "default_order": 1,
                "target_data_source_id": "",
            },
            "tipo": {
                "notion_name": "Tipo", "tipo": "select", "label": "Tipo",
                "editavel": True, "obrigatorio": False, "opcoes": [],
                "default_visible": True, "default_order": 2,
                "target_data_source_id": "",
            },
            "notas": {
                "notion_name": "Notas", "tipo": "rich_text", "label": "Notas",
                "editavel": True, "obrigatorio": False, "opcoes": [],
                "default_visible": False, "default_order": 3,
                "target_data_source_id": "",
            },
        },
    }
    reg._schemas["BaseSemLayout"] = synthetic_schema  # noqa: SLF001
    reg._base_to_dsid["BaseSemLayout"] = "dsid-syn"  # noqa: SLF001
    cols = reg.colunas_visiveis("BaseSemLayout")
    assert cols == ["nome", "tipo"]  # heurística mantém: rich_text fora


# ---------------------------------------------------------------------------
# Frente 3b — frozen first column overlay (_BaseTableView)
# ---------------------------------------------------------------------------


def _qapp():
    """Singleton QApplication pra testes que instanciam widgets."""
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_view_with_dummy_model(n_cols: int):
    """Cria _BaseTableView + QStandardItemModel com n_cols colunas
    (incluindo título)."""
    _qapp()
    from PySide6.QtGui import QStandardItem, QStandardItemModel
    from notion_rpadv.pages.base_table_page import _BaseTableView
    from notion_rpadv.theme.tokens import LIGHT
    view = _BaseTableView(LIGHT)
    if n_cols == 0:
        return view, None
    model = QStandardItemModel()
    model.setColumnCount(n_cols)
    headers = [f"col_{i}" for i in range(n_cols)]
    model.setHorizontalHeaderLabels(headers)
    # 3 linhas dummy
    for r in range(3):
        items = [QStandardItem(f"r{r}c{c}") for c in range(n_cols)]
        model.appendRow(items)
    view.setModel(model)
    return view, model


def test_R4_frozen_overlay_exists_after_setmodel_with_multi_col() -> None:
    """Após setModel com 2+ cols, frozen overlay existe e não está oculto.
    (Usamos ``not isHidden()`` em vez de ``isVisible()`` porque o widget tree
    não está mostrado em testes headless — isVisible() consulta ancestrais.)"""
    view, model = _make_view_with_dummy_model(3)
    assert view._frozen is not None  # noqa: SLF001
    assert view._frozen.isHidden() is False  # noqa: SLF001
    assert view._frozen.model() is model  # noqa: SLF001


def test_R4_frozen_only_col0_visible() -> None:
    """No frozen, col 0 deve estar visível e cols 1+ escondidas."""
    view, _ = _make_view_with_dummy_model(4)
    assert view._frozen.isColumnHidden(0) is False  # noqa: SLF001
    for c in range(1, 4):
        assert view._frozen.isColumnHidden(c) is True, (  # noqa: SLF001
            f"col {c} deveria estar escondida no frozen"
        )


def test_R4_frozen_hidden_when_model_single_col() -> None:
    """Model com 1 coluna só — não há o que fixar; frozen fica oculto."""
    view, _ = _make_view_with_dummy_model(1)
    assert view._frozen.isHidden() is True  # noqa: SLF001


def test_R4_frozen_hidden_when_model_is_none() -> None:
    """Model None — frozen fica oculto, sem crash."""
    _qapp()
    from notion_rpadv.pages.base_table_page import _BaseTableView
    from notion_rpadv.theme.tokens import LIGHT
    view = _BaseTableView(LIGHT)
    view.setModel(None)
    assert view._frozen.isHidden() is True  # noqa: SLF001


def test_R4_frozen_shares_selection_model_with_main() -> None:
    """Selection é compartilhada — selecionar no main destaca no frozen."""
    view, _ = _make_view_with_dummy_model(3)
    assert view._frozen.selectionModel() is view.selectionModel()  # noqa: SLF001


def test_R4_frozen_vertical_scroll_synced_main_to_frozen() -> None:
    """Mover scroll vertical do main → frozen acompanha.

    Sem widget tree mostrado, scroll bars não têm range automático; force
    o range manualmente pra que setValue não seja clampado para 0.
    """
    view, _ = _make_view_with_dummy_model(3)
    main_sb = view.verticalScrollBar()
    frozen_sb = view._frozen.verticalScrollBar()  # noqa: SLF001
    main_sb.setRange(0, 10)
    frozen_sb.setRange(0, 10)
    main_sb.setValue(2)
    assert frozen_sb.value() == 2


def test_R4_frozen_vertical_scroll_synced_frozen_to_main() -> None:
    """Mover scroll vertical do frozen (raro, mas plausível via wheel
    quando hover sobre frozen) → main acompanha."""
    view, _ = _make_view_with_dummy_model(3)
    main_sb = view.verticalScrollBar()
    frozen_sb = view._frozen.verticalScrollBar()  # noqa: SLF001
    main_sb.setRange(0, 10)
    frozen_sb.setRange(0, 10)
    frozen_sb.setValue(1)
    assert main_sb.value() == 1


def test_R4_frozen_doubleclick_forwards_to_main_signal() -> None:
    """doubleClicked no frozen é re-emitido no signal doubleClicked do main
    pra que listeners (relation navigation, etc.) funcionem em ambas vistas."""
    view, model = _make_view_with_dummy_model(3)
    received = []
    view.doubleClicked.connect(lambda idx: received.append((idx.row(), idx.column())))
    # Emite manualmente (simula o duplo-clique sem GUI loop)
    idx = model.index(1, 0)
    view._frozen.doubleClicked.emit(idx)  # noqa: SLF001
    assert received == [(1, 0)]


def test_R4_frozen_setitemdelegate_propagates_to_overlay() -> None:
    """setItemDelegate no main aplica também no frozen pra que a renderização
    de chips/dirty/etc seja consistente."""
    _qapp()
    from PySide6.QtWidgets import QStyledItemDelegate
    from notion_rpadv.pages.base_table_page import _BaseTableView
    from notion_rpadv.theme.tokens import LIGHT
    view = _BaseTableView(LIGHT)
    delegate = QStyledItemDelegate(view)
    view.setItemDelegate(delegate)
    assert view._frozen.itemDelegate() is delegate  # noqa: SLF001


def test_R4_frozen_modelreset_reapplies_hidden_state() -> None:
    """Quando o model emite modelReset (ex: picker mudou colunas), frozen
    deve re-aplicar setColumnHidden(c, c != 0). Sem isso, picker
    poderia deixar coluna 1+ visível no frozen."""
    view, model = _make_view_with_dummy_model(4)
    # Sabotage: força col 1 visível no frozen
    view._frozen.setColumnHidden(1, False)  # noqa: SLF001
    assert view._frozen.isColumnHidden(1) is False  # noqa: SLF001
    # Emite modelReset — handler deve re-esconder cols 1+
    model.beginResetModel()
    model.endResetModel()
    assert view._frozen.isColumnHidden(1) is True  # noqa: SLF001


def test_R4_frozen_col0_width_synced_when_main_resized() -> None:
    """Resize manual da col 0 no main → frozen ajusta sua col 0 também."""
    view, _ = _make_view_with_dummy_model(3)
    view.setColumnWidth(0, 240)
    assert view._frozen.columnWidth(0) == 240  # noqa: SLF001

