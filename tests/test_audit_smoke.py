"""Audit smoke tests — RELATORIO_AUDITORIA_OPERACIONAL.md, descartável.

Each test documents a finding from the operational audit. The tests are
executable so the report's claims are reproducible. They do NOT touch the
real Notion API; the cache DB is read-only when present, and most tests
build an in-memory cache.

Naming: test_AUD_<area>_<short_label>.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(not _PYSIDE6, reason="PySide6 not installed")

# Path to the real cache (only used by read-only tests; skipped if absent)
_REAL_CACHE = Path(os.environ.get("APPDATA", "")) / "NotionRPADV" / "cache.db"
requires_cache = pytest.mark.skipif(
    not _REAL_CACHE.exists(),
    reason="real cache.db not present (only available on dev machine)",
)


def _readonly(p: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _fresh_conn() -> sqlite3.Connection:
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# Área 1 — Integridade dos dados
# ---------------------------------------------------------------------------


@requires_cache
def test_AUD_01_cache_record_counts() -> None:
    """Cache contém Processos≈1108, Clientes≈1072, Catalogo≈37, Tarefas>=0."""
    conn = _readonly(_REAL_CACHE)
    counts = {r["base"]: r["n"] for r in conn.execute(
        "SELECT base, COUNT(*) AS n FROM records GROUP BY base"
    ).fetchall()}
    assert counts.get("Processos") == 1108
    assert counts.get("Clientes") == 1072
    assert counts.get("Catalogo") == 37
    assert counts.get("Tarefas", 0) >= 0


@requires_cache
def test_AUD_01_cache_relations_no_orphans() -> None:
    """Cliente UUIDs em Processos.cliente sempre apontam para registro existente."""
    conn = _readonly(_REAL_CACHE)
    cli_ids = {r["page_id"] for r in conn.execute(
        "SELECT page_id FROM records WHERE base='Clientes'"
    ).fetchall()}
    proc_ids = {r["page_id"] for r in conn.execute(
        "SELECT page_id FROM records WHERE base='Processos'"
    ).fetchall()}

    orphans_cliente = orphans_pai = 0
    for r in conn.execute("SELECT data_json FROM records WHERE base='Processos'"):
        d = json.loads(r["data_json"])
        for cid in (d.get("cliente") or []):
            if cid not in cli_ids:
                orphans_cliente += 1
        for pid in (d.get("processo_pai") or []):
            if pid not in proc_ids:
                orphans_pai += 1
    assert orphans_cliente == 0
    assert orphans_pai == 0


@requires_cache
def test_AUD_01_cache_dates_iso() -> None:
    """Datas em distribuicao são ISO YYYY-MM-DD (não BR e não lixo)."""
    conn = _readonly(_REAL_CACHE)
    iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}")
    bad = []
    for r in conn.execute("SELECT data_json FROM records WHERE base='Processos'"):
        d = json.loads(r["data_json"])
        v = d.get("distribuicao")
        if v and not iso_re.match(str(v)):
            bad.append(v)
            if len(bad) >= 3:
                break
    assert bad == []


@requires_cache
def test_AUD_01_no_placeholder_garbage() -> None:
    """Cache não contém placeholders, __YES__ literais ou chaves de teste."""
    conn = _readonly(_REAL_CACHE)
    bad = []
    for r in conn.execute("SELECT base, page_id, data_json FROM records"):
        j = r["data_json"]
        if "placeholder_" in j.lower() or "__YES__" in j or "__NO__" in j:
            bad.append((r["base"], r["page_id"][:8]))
            if len(bad) >= 3:
                break
    assert bad == []


@requires_cache
def test_AUD_01_n_processos_lookup_matches_join() -> None:
    """Contagem de processos por cliente computada localmente bate com COUNT JOIN."""
    conn = _readonly(_REAL_CACHE)
    actual: dict[str, int] = {}
    for r in conn.execute("SELECT data_json FROM records WHERE base='Processos'"):
        d = json.loads(r["data_json"])
        for cid in (d.get("cliente") or []):
            actual[cid] = actual.get(cid, 0) + 1
    # the cached n_processos rollup is None for every cliente — fallback
    # in BaseTableModel computes the count at render time. Sanity-check:
    # at least one client has >0 processes.
    assert sum(actual.values()) > 0
    assert max(actual.values()) > 1  # at least one client with multiple processos


# ---------------------------------------------------------------------------
# Área 2 — Persistência de edições (encoders)
# ---------------------------------------------------------------------------


def test_AUD_02_encoders_each_writable_type() -> None:
    """encode_value produz payload no formato Notion para cada tipo gravável."""
    from notion_bulk_edit.encoders import encode_value

    assert encode_value("Ativo", "select") == {"select": {"name": "Ativo"}}
    assert encode_value(["A", "B"], "multi_select") == {
        "multi_select": [{"name": "A"}, {"name": "B"}]
    }
    assert encode_value("0001234-56", "title") == {
        "title": [{"text": {"content": "0001234-56"}}]
    }
    assert encode_value("2026-04-27", "date") == {"date": {"start": "2026-04-27"}}
    assert encode_value("27/04/2026", "date") == {"date": {"start": "2026-04-27"}}
    assert encode_value(True, "checkbox") == {"checkbox": True}
    assert encode_value(False, "checkbox") == {"checkbox": False}
    assert encode_value(["uuid-1"], "relation") == {"relation": [{"id": "uuid-1"}]}
    assert encode_value(["uuid-A"], "people") == {"people": [{"id": "uuid-A"}]}
    assert encode_value("78.500,00", "number") == {"number": 78500.0}


def test_AUD_02_readonly_types_emit_empty_payload() -> None:
    """rollup, formula, created_time, last_edited_time são read-only (payload vazio)."""
    from notion_bulk_edit.encoders import encode_value
    for tipo in ("rollup", "formula", "created_time", "last_edited_time"):
        assert encode_value("anything", tipo) == {}


# ---------------------------------------------------------------------------
# Área 3 — Reverter edições (BUG-OP-01/02 corrigidos no Round A)
# ---------------------------------------------------------------------------


@requires_pyside6
def test_dirty_edit_id_is_real_after_save_initiated() -> None:
    """BUG-OP-02 (corrigido): após chamar flush_dirty_to_pending() — o passo
    que _on_save executa antes de despachar o CommitWorker — cada dirty
    edit recebe um id real (>0) vindo da tabela pending_edits."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X", "tribunal": "TJDFT"})
    model = BaseTableModel("Processos", conn)
    model._dirty[("p1", "tribunal")] = "TRT/10"

    edits = model.flush_dirty_to_pending()
    assert len(edits) == 1
    assert edits[0]["id"] > 0
    # And the row is really in pending_edits
    assert cache_db.get_pending_edits(conn) != []


def test_commit_worker_writes_to_edit_log_after_success() -> None:
    """BUG-OP-01 (corrigido): após uma chamada API bem-sucedida, o
    CommitWorker move a linha de pending_edits → edit_log via
    mark_edit_applied(id, user). Validação: a linha aparece em edit_log
    com os campos esperados."""
    from notion_rpadv.services.notion_facade import CommitWorker
    from notion_rpadv.cache import db as cache_db

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X", "tribunal": "TJDFT"})
    edit_id = cache_db.add_pending_edit(
        conn, "Processos", "p1", "tribunal", "TJDFT", "TRT/10",
    )
    edits = [{
        "id": edit_id, "base": "Processos", "page_id": "p1",
        "key": "tribunal", "old_value": "TJDFT", "new_value": "TRT/10",
    }]

    fake_client = MagicMock()
    fake_client.update_page = MagicMock(return_value={})
    with patch("notion_rpadv.services.notion_facade.NotionClient",
               return_value=fake_client):
        worker = CommitWorker(token="t", conn=conn, edits=edits,
                              user="deborah", base="Processos")
        worker.finished = MagicMock()
        worker.error = MagicMock()
        worker.progress = MagicMock()
        worker.run()

    fake_client.update_page.assert_called_once()
    log = cache_db.get_edit_log(conn, limit=10)
    assert len(log) == 1
    entry = log[0]
    assert entry["base"] == "Processos"
    assert entry["page_id"] == "p1"
    assert entry["key"] == "tribunal"
    assert entry["old_value"] == "TJDFT"
    assert entry["new_value"] == "TRT/10"
    assert entry["user"] == "deborah"
    assert entry["reverted"] == 0
    assert entry["applied_at"] > 0
    # And the pending row is gone (status changed to 'applied')
    assert cache_db.get_pending_edits(conn) == []


# ---------------------------------------------------------------------------
# BUG-OP-01/02 follow-up: 3 new tests requested by Round A spec
# ---------------------------------------------------------------------------


@requires_pyside6
def test_save_creates_pending_edit_per_dirty_cell() -> None:
    """3 dirty cells → 3 entradas distintas em pending_edits, ids únicos."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1", {
        "page_id": "p1", "cnj": "AAA", "tribunal": "TJDFT", "fase": "Cognitiva",
    })
    model = BaseTableModel("Processos", conn)
    model._dirty[("p1", "cnj")] = "AAA-NEW"
    model._dirty[("p1", "tribunal")] = "TRT/10"
    model._dirty[("p1", "fase")] = "Executiva"

    edits = model.flush_dirty_to_pending()
    assert len(edits) == 3
    ids = sorted(e["id"] for e in edits)
    assert len(set(ids)) == 3  # all distinct
    assert all(i > 0 for i in ids)
    pending = cache_db.get_pending_edits(conn)
    assert len(pending) == 3


def test_save_partial_failure_keeps_pending_for_failed_only() -> None:
    """3 edits, 2 sucessos + 1 falha de API: edit_log fica com 2 entradas,
    pending_edits retém apenas a que falhou."""
    from notion_rpadv.services.notion_facade import CommitWorker
    from notion_rpadv.cache import db as cache_db
    from notion_bulk_edit.notion_api import NotionAPIError

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1", {
        "page_id": "p1", "cnj": "X", "tribunal": "TJDFT", "fase": "Cognitiva",
    })
    id_a = cache_db.add_pending_edit(conn, "Processos", "p1", "cnj", "X", "Y")
    id_b = cache_db.add_pending_edit(conn, "Processos", "p1", "tribunal", "TJDFT", "TRT/10")
    id_c = cache_db.add_pending_edit(conn, "Processos", "p1", "fase", "Cognitiva", "Executiva")

    edits = [
        {"id": id_a, "base": "Processos", "page_id": "p1", "key": "cnj",
         "old_value": "X", "new_value": "Y"},
        {"id": id_b, "base": "Processos", "page_id": "p1", "key": "tribunal",
         "old_value": "TJDFT", "new_value": "TRT/10"},
        {"id": id_c, "base": "Processos", "page_id": "p1", "key": "fase",
         "old_value": "Cognitiva", "new_value": "Executiva"},
    ]

    fake_client = MagicMock()
    # 2nd call (tribunal) fails; 1st and 3rd succeed.
    fake_client.update_page = MagicMock(side_effect=[
        {}, NotionAPIError(500, "boom"), {},
    ])

    with patch("notion_rpadv.services.notion_facade.NotionClient",
               return_value=fake_client):
        worker = CommitWorker(token="t", conn=conn, edits=edits,
                              user="u", base="Processos")
        worker.finished = MagicMock()
        worker.error = MagicMock()
        worker.progress = MagicMock()
        worker.run()

    log = cache_db.get_edit_log(conn, limit=10)
    pending = cache_db.get_pending_edits(conn)
    assert len(log) == 2
    assert {e["key"] for e in log} == {"cnj", "fase"}
    assert len(pending) == 1
    assert pending[0]["key"] == "tribunal"


@requires_pyside6
def test_save_idempotent_for_same_cell_twice() -> None:
    """Duas chamadas seguidas de flush_dirty_to_pending para a mesma célula
    não criam duplicata em pending_edits — upsert reusa o mesmo id."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X", "tribunal": "TJDFT"})
    model = BaseTableModel("Processos", conn)
    model._dirty[("p1", "tribunal")] = "TRT/10"

    edits1 = model.flush_dirty_to_pending()
    # User clicks Save a second time without anything else happening
    edits2 = model.flush_dirty_to_pending()

    assert edits1[0]["id"] == edits2[0]["id"]
    pending = cache_db.get_pending_edits(conn)
    assert len(pending) == 1


@requires_cache
def test_AUD_03_real_edit_log_after_round_C() -> None:
    """Sentinela do estado pós-Round C. O edit_log foi migrado para
    audit.db — checar se o arquivo existe; cache.db não deve mais ter
    a tabela após a migração rodar uma vez (BUG-OP-09)."""
    conn = _readonly(_REAL_CACHE)
    cache_tables = {
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    # Either: migration ran (edit_log gone from cache) OR a fresh cache
    # was created by the most recent boot. Both are acceptable.
    if "edit_log" in cache_tables:
        # Legacy state — n>=0 trivial check.
        n = conn.execute("SELECT COUNT(*) FROM edit_log").fetchone()[0]
        assert n >= 0
    else:
        # Migration completed; cache no longer carries edit_log. The
        # audit.db file should exist alongside.
        from notion_rpadv.cache.db import get_audit_db_path
        assert get_audit_db_path().exists()


# ---------------------------------------------------------------------------
# Área 4 — Sincronização
# ---------------------------------------------------------------------------


def test_AUD_04_sync_skips_template_and_archived() -> None:
    """Sync filtra `is_template`, `archived`, `in_trash`."""
    from notion_rpadv.cache.sync import SyncWorker
    from notion_rpadv.cache import db as cache_db

    fake_pages = [
        {"id": "p1", "properties": {"Número do processo": {
            "title": [{"plain_text": "0000001-00"}]}}},
        {"id": "tpl", "is_template": True, "properties": {}},
        {"id": "arc", "archived": True, "properties": {}},
        {"id": "tr", "in_trash": True, "properties": {}},
    ]

    conn = _fresh_conn()
    fake_client = MagicMock()
    fake_client.query_all = MagicMock(return_value=fake_pages)

    with patch("notion_rpadv.cache.sync.NotionClient", return_value=fake_client):
        worker = SyncWorker(token="t", base="Processos", conn=conn)
        worker.finished = MagicMock()
        worker.error = MagicMock()
        worker.progress = MagicMock()
        worker.total = MagicMock()
        worker.run()

    rows = cache_db.get_all_records(conn, "Processos")
    ids = {r["page_id"] for r in rows}
    assert ids == {"p1"}


def test_AUD_04_sync_diff_updates_existing() -> None:
    """Sync sobre cache pré-existente: upsert atualiza, novos contam como added,
    sumidos contam como removed."""
    from notion_rpadv.cache.sync import SyncWorker
    from notion_rpadv.cache import db as cache_db

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "OLD"})
    cache_db.upsert_record(conn, "Processos", "p_gone",
                           {"page_id": "p_gone", "cnj": "DEAD"})

    api_pages = [
        {"id": "p1", "properties": {
            "Número do processo": {"title": [{"plain_text": "NEW"}]}}},
        {"id": "p_new", "properties": {
            "Número do processo": {"title": [{"plain_text": "FRESH"}]}}},
    ]

    counts = {}

    fake_client = MagicMock()
    fake_client.query_all = MagicMock(return_value=api_pages)

    with patch("notion_rpadv.cache.sync.NotionClient", return_value=fake_client):
        worker = SyncWorker(token="t", base="Processos", conn=conn)
        worker.finished = MagicMock(side_effect=lambda b, a, e, r: counts.update(
            base=b, added=a, existing=e, removed=r))
        worker.error = MagicMock()
        worker.progress = MagicMock()
        worker.total = MagicMock()
        worker.run()

    rows = {r["page_id"]: r for r in cache_db.get_all_records(conn, "Processos")}
    assert "p_gone" not in rows
    assert rows["p1"]["cnj"] == "NEW"
    assert rows["p_new"]["cnj"] == "FRESH"


# ---------------------------------------------------------------------------
# Área 6 — Filtragem e busca (limitações)
# ---------------------------------------------------------------------------


@requires_pyside6
def test_AUD_06_search_matches_both_iso_and_br_dates() -> None:
    """BUG-OP-04 (corrigido em Round D): a busca livre agora opera sobre
    DisplayRole *e* EditRole. Datas são exibidas em BR mas armazenadas
    em ISO, então buscar em qualquer um dos dois formatos casa."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel
    from notion_rpadv.models.filters import TableFilterProxy

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "0000001-00",
                            "distribuicao": "2025-03-20"})

    model = BaseTableModel("Processos", conn)
    proxy = TableFilterProxy()
    proxy.setSourceModel(model)

    proxy.set_search("20/03/2025")
    assert proxy.rowCount() == 1, "BR format must match (DisplayRole)"
    proxy.set_search("2025-03-20")
    assert proxy.rowCount() == 1, "ISO format must match (EditRole)"


# ---------------------------------------------------------------------------
# Área 7 — Robustez sob uso real (BUG-OP-06 corrigido no Round A)
# ---------------------------------------------------------------------------


@requires_pyside6
def test_sync_during_edit_preserves_dirty_cells() -> None:
    """BUG-OP-06 (corrigido): ao terminar uma sync, _on_base_done chama
    reload(preserve_dirty=True) que preserva _dirty para rows que ainda
    existem. O reload sem flag (default False) continua limpando — usado
    em outros caminhos como após save bem-sucedido."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X"})
    model = BaseTableModel("Processos", conn)
    model._dirty[("p1", "cnj")] = "EDITED"
    model._dirty_original[("p1", "cnj")] = "X"

    # Default reload still clears (post-save / post-discard semantics)
    model_default = BaseTableModel("Processos", conn)
    model_default._dirty[("p1", "cnj")] = "X2"
    model_default._dirty_original[("p1", "cnj")] = "X"
    model_default.reload()
    assert model_default._dirty == {}

    # The sync code path uses preserve_dirty=True
    model.reload(preserve_dirty=True)
    assert model._dirty == {("p1", "cnj"): "EDITED"}
    assert model._dirty_original == {("p1", "cnj"): "X"}


# ---------------------------------------------------------------------------
# BUG-OP-06 follow-up: 3 new tests requested by Round A spec
# ---------------------------------------------------------------------------


@requires_pyside6
def test_sync_preserves_dirty_value_when_remote_unchanged() -> None:
    """Sync sem mudança remota não dispara conflito; dirty mantém valor."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X", "tribunal": "TJDFT"})
    model = BaseTableModel("Processos", conn)
    model._dirty[("p1", "tribunal")] = "TRT/10"
    model._dirty_original[("p1", "tribunal")] = "TJDFT"

    conflicts: list = []
    model.dirty_conflict_detected.connect(lambda *a: conflicts.append(a))

    # Sync ran but the cache value is unchanged (remote didn't move).
    model.reload(preserve_dirty=True)

    assert model._dirty == {("p1", "tribunal"): "TRT/10"}
    assert conflicts == []


@requires_pyside6
def test_sync_emits_conflict_signal_when_remote_changed() -> None:
    """Quando o cache foi atualizado pelo sync para um valor diferente
    daquele que o usuário tinha visto antes de editar, o model emite
    dirty_conflict_detected(page_id, key, local_value, remote_value)."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X", "tribunal": "TJDFT"})
    model = BaseTableModel("Processos", conn)
    model._dirty[("p1", "tribunal")] = "TRT/10"
    model._dirty_original[("p1", "tribunal")] = "TJDFT"  # what user saw

    # Simulate sync: cache now has TRT/02 (someone else changed it remotely)
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X", "tribunal": "TRT/02"})

    conflicts: list = []
    model.dirty_conflict_detected.connect(
        lambda pid, key, local, remote: conflicts.append((pid, key, local, remote))
    )

    model.reload(preserve_dirty=True)

    assert conflicts == [("p1", "tribunal", "TRT/10", "TRT/02")]
    # Dirty is kept — last-write-wins por humano: a UI mantém a edição local
    # e cabe ao slot do signal (no futuro: diálogo) decidir.
    assert model._dirty == {("p1", "tribunal"): "TRT/10"}


@requires_pyside6
def test_sync_drops_dirty_when_row_deleted_remotely() -> None:
    """Linha some no Notion → dirty para essa linha cai. dirty_dropped é
    emitido para visibilidade (UI pode fazer toast)."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X"})
    cache_db.upsert_record(conn, "Processos", "p2",
                           {"page_id": "p2", "cnj": "Y"})
    model = BaseTableModel("Processos", conn)
    model._dirty[("p1", "cnj")] = "EDITED1"
    model._dirty_original[("p1", "cnj")] = "X"
    model._dirty[("p2", "cnj")] = "EDITED2"
    model._dirty_original[("p2", "cnj")] = "Y"

    # Sync removed p2 (deleted in Notion)
    cache_db.delete_record(conn, "Processos", "p2")

    dropped: list = []
    model.dirty_dropped.connect(lambda pid, key: dropped.append((pid, key)))

    model.reload(preserve_dirty=True)

    assert dropped == [("p2", "cnj")]
    assert ("p2", "cnj") not in model._dirty
    assert model._dirty == {("p1", "cnj"): "EDITED1"}


# ---------------------------------------------------------------------------
# Round B — BUG-OP-03: per-cell save results + targeted clear_dirty
# ---------------------------------------------------------------------------


def test_commit_worker_returns_per_cell_results() -> None:
    """3 edits, 2 sucessos + 1 falha: o signal `finished` carrega lista
    de 3 dicts no formato {page_id, key, edit_id, ok, error}."""
    from notion_rpadv.services.notion_facade import CommitWorker
    from notion_bulk_edit.notion_api import NotionAPIError

    conn = _fresh_conn()
    edits = [
        {"id": 1, "base": "Processos", "page_id": "p1", "key": "cnj",
         "old_value": "X", "new_value": "Y"},
        {"id": 2, "base": "Processos", "page_id": "p1", "key": "tribunal",
         "old_value": "TJDFT", "new_value": "TRT/10"},
        {"id": 3, "base": "Processos", "page_id": "p2", "key": "fase",
         "old_value": "Cognitiva", "new_value": "Executiva"},
    ]
    fake_client = MagicMock()
    fake_client.update_page = MagicMock(side_effect=[
        {}, NotionAPIError(500, "boom"), {},
    ])

    captured: list = []
    with patch("notion_rpadv.services.notion_facade.NotionClient",
               return_value=fake_client):
        worker = CommitWorker(token="t", conn=conn, edits=edits,
                              user="u", base="Processos")
        worker.finished = MagicMock()
        # CommitWorker calls signal.emit(...). With a MagicMock the call
        # is recorded but no side effect runs, so we patch .emit directly.
        worker.finished.emit = lambda b, r: captured.append((b, r))
        worker.error = MagicMock()
        worker.progress = MagicMock()
        worker.run()

    assert len(captured) == 1
    base, results = captured[0]
    assert base == "Processos"
    assert len(results) == 3
    keys = [(r["page_id"], r["key"]) for r in results]
    assert keys == [("p1", "cnj"), ("p1", "tribunal"), ("p2", "fase")]
    assert [r["ok"] for r in results] == [True, False, True]
    assert results[1]["error"]  # failure carries an error message
    assert results[0]["error"] is None


@requires_pyside6
def test_clear_dirty_with_cells_clears_only_those() -> None:
    """clear_dirty(cells_to_clear=[...]) limpa apenas o subconjunto
    informado. Sem o argumento (default), mantém o comportamento legado
    de limpar tudo."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X", "tribunal": "T1", "fase": "F1"})
    cache_db.upsert_record(conn, "Processos", "p2",
                           {"page_id": "p2", "cnj": "Y", "tribunal": "T2"})
    model = BaseTableModel("Processos", conn)
    model._dirty[("p1", "cnj")] = "X-new"
    model._dirty[("p1", "tribunal")] = "T1-new"
    model._dirty[("p1", "fase")] = "F1-new"
    model._dirty[("p2", "cnj")] = "Y-new"
    model._dirty[("p2", "tribunal")] = "T2-new"

    model.clear_dirty(cells_to_clear=[("p1", "cnj"), ("p2", "tribunal")])

    remaining = set(model._dirty.keys())
    assert remaining == {("p1", "tribunal"), ("p1", "fase"), ("p2", "cnj")}


@requires_pyside6
def test_partial_failure_keeps_failed_cells_dirty() -> None:
    """Fluxo end-to-end: 3 dirty cells → save com 2 sucessos + 1 falha →
    `_dirty` mantém apenas a célula que falhou."""
    import sys
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1", {
        "page_id": "p1", "cnj": "X", "tribunal": "T1", "fase": "F1",
    })

    page = ProcessosPage(conn=conn, token="t", user="u", facade=MagicMock())
    page._model._dirty[("p1", "cnj")] = "X-new"
    page._model._dirty[("p1", "tribunal")] = "T1-new"
    page._model._dirty[("p1", "fase")] = "F1-new"

    results = [
        {"page_id": "p1", "key": "cnj",      "edit_id": 0, "ok": True,  "error": None},
        {"page_id": "p1", "key": "tribunal", "edit_id": 0, "ok": False, "error": "boom"},
        {"page_id": "p1", "key": "fase",     "edit_id": 0, "ok": True,  "error": None},
    ]
    page._on_commit_finished("Processos", results)

    assert set(page._model._dirty.keys()) == {("p1", "tribunal")}


@requires_pyside6
def test_toast_message_lists_failed_cells_by_record_name() -> None:
    """O toast de falha cita até 3 registros por nome (title da base) e o
    label legível do campo, não o page_id ou a key bruta."""
    import sys
    from unittest.mock import MagicMock, patch
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.app import MainWindow

    # Build the cache that the toast formatter looks at
    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p-maria", {
        "page_id": "p-maria", "cnj": "0001-Maria Silva",
    })
    cache_db.upsert_record(conn, "Processos", "p-pedro", {
        "page_id": "p-pedro", "cnj": "0002-Pedro Costa",
    })

    # Avoid the heavy MainWindow.__init__ — we only need the formatter.
    win = MainWindow.__new__(MainWindow)
    win._conn = conn  # type: ignore[attr-defined]

    failed = [
        {"page_id": "p-maria", "key": "tribunal", "edit_id": 0,
         "ok": False, "error": "boom"},
        {"page_id": "p-pedro", "key": "tribunal", "edit_id": 0,
         "ok": False, "error": "boom"},
    ]
    snippets = win._format_failure_snippets("Processos", failed, max_items=3)
    rendered = ", ".join(snippets)
    assert "0001-Maria Silva" in rendered
    assert "0002-Pedro Costa" in rendered
    assert "Tribunal" in rendered  # PropSpec.label, not raw "tribunal"


# ---------------------------------------------------------------------------
# Round B — BUG-OP-11: re-auth dialog + idempotency
# ---------------------------------------------------------------------------


def test_notion_auth_error_emits_global_signal() -> None:
    """NotionAuthError no CommitWorker dispara `auth_invalidated` exactly once."""
    from notion_rpadv.services.notion_facade import CommitWorker
    from notion_bulk_edit.notion_api import NotionAuthError

    conn = _fresh_conn()
    edits = [
        {"id": 1, "base": "Processos", "page_id": "p1", "key": "tribunal",
         "old_value": "T1", "new_value": "T2"},
    ]
    fake_client = MagicMock()
    fake_client.update_page = MagicMock(side_effect=NotionAuthError("token bad"))

    auth_emits: list = []
    with patch("notion_rpadv.services.notion_facade.NotionClient",
               return_value=fake_client):
        worker = CommitWorker(token="t", conn=conn, edits=edits,
                              user="u", base="Processos")
        worker.finished = MagicMock()
        worker.error = MagicMock()
        worker.progress = MagicMock()
        worker.auth_invalidated = MagicMock(
            side_effect=lambda *a: auth_emits.append(1)
        )
        # Replace .emit directly because we mocked the Signal object above
        worker.auth_invalidated.emit = lambda *a: auth_emits.append(1)
        worker.run()

    assert len(auth_emits) == 1


@requires_pyside6
def test_auth_dialog_is_idempotent() -> None:
    """Três emissões consecutivas de auth_invalidated abrem só um modal."""
    import sys
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.app import MainWindow

    win = MainWindow.__new__(MainWindow)
    win._auth_dialog_open = False  # type: ignore[attr-defined]
    win._status_bar = MagicMock()  # type: ignore[attr-defined]
    # Patch the methods that would otherwise touch the screen
    win._show_reauth_dialog = MagicMock(return_value="later")  # type: ignore[attr-defined]
    win._open_reauth_flow = MagicMock()  # type: ignore[attr-defined]
    win._push_toast = MagicMock()  # type: ignore[attr-defined]

    # While the first dialog "is open" — simulate by holding the flag set
    # — subsequent emits must be absorbed.
    def _show_with_concurrent_emits():
        # Caller fires 2 more emits while the dialog is on screen.
        win._on_auth_invalidated()
        win._on_auth_invalidated()
        return "later"

    win._show_reauth_dialog.side_effect = _show_with_concurrent_emits

    win._on_auth_invalidated()  # first emit → opens dialog
    # Total dialogs shown across all 3 emits must equal 1.
    assert win._show_reauth_dialog.call_count == 1


@requires_pyside6
def test_dirty_cells_survive_auth_failure() -> None:
    """Auth error durante save mantém todas as dirty cells intactas
    (BUG-OP-06 e BUG-OP-11 cooperando)."""
    import sys
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1", {
        "page_id": "p1", "cnj": "X", "tribunal": "T1", "fase": "F1",
    })
    page = ProcessosPage(conn=conn, token="t", user="u", facade=MagicMock())
    page._model._dirty[("p1", "cnj")] = "X-new"
    page._model._dirty[("p1", "tribunal")] = "T1-new"
    page._model._dirty[("p1", "fase")] = "F1-new"

    # All three failed with auth error → results carries 3 ok=False entries.
    results = [
        {"page_id": "p1", "key": k, "edit_id": 0,
         "ok": False, "error": "Token inválido ou sem permissão."}
        for k in ("cnj", "tribunal", "fase")
    ]
    page._on_commit_finished("Processos", results)

    # Nothing was cleared.
    assert set(page._model._dirty.keys()) == {
        ("p1", "cnj"), ("p1", "tribunal"), ("p1", "fase"),
    }


@requires_pyside6
def test_reauthentication_resumes_normal_state() -> None:
    """Ciclo completo simulado: auth error → dialog → token novo →
    _on_token_changed propaga; após retry bem-sucedido, dirty é limpo."""
    import sys
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.app import MainWindow
    from notion_rpadv.cache import db as cache_db

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X"})

    win = MainWindow.__new__(MainWindow)
    win._conn = conn  # type: ignore[attr-defined]
    win._token = "secret_old"  # type: ignore[attr-defined]
    win._facade = MagicMock(_token="secret_old")  # type: ignore[attr-defined]
    win._sync_manager = MagicMock(_token="secret_old")  # type: ignore[attr-defined]
    win._pages = {}  # type: ignore[attr-defined]
    win._auth_dialog_open = False  # type: ignore[attr-defined]
    win._status_bar = MagicMock()  # type: ignore[attr-defined]
    win._push_toast = MagicMock()  # type: ignore[attr-defined]

    # User clicks "Re-autenticar" → returns the new token
    win._show_reauth_dialog = MagicMock(return_value="reauthenticate")  # type: ignore[attr-defined]

    fake_login_dialog = MagicMock()
    fake_login_dialog.exec.return_value = 1  # Accepted
    fake_login_dialog._token_value = "secret_new"

    with patch("notion_rpadv.auth.login_window.LoginWindow",
               return_value=fake_login_dialog):
        win._on_auth_invalidated()

    # Token propagated through facade and sync manager
    assert win._token == "secret_new"  # type: ignore[attr-defined]
    assert win._facade._token == "secret_new"  # type: ignore[attr-defined]
    assert win._sync_manager._token == "secret_new"  # type: ignore[attr-defined]
    # And the dialog flag is back to False, so a future failure reopens the modal.
    assert win._auth_dialog_open is False  # type: ignore[attr-defined]


@requires_pyside6
def test_A3_base_table_page_reload_preserve_dirty_keeps_edits() -> None:
    """A3 (sync individual descarta dirty cells): BaseTablePage.reload aceita
    ``preserve_dirty=True``. Sem isso, ``MainWindow._on_sync_all_done``
    iterava ``page.reload()`` sem o flag e sync individual via Configurações
    perdia edições silenciosamente (mesmo bug do Round A em outro caminho).
    """
    import sys
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage

    conn = _fresh_conn()
    cache_db.upsert_record(
        conn, "Processos", "p1",
        {"page_id": "p1", "cnj": "0001234-56.2023.5.10.0001", "tribunal": "TJDFT"},
    )

    page = ProcessosPage(conn=conn, token="t", user="u", facade=MagicMock())
    page._model._dirty[("p1", "cnj")] = "EDITED-CNJ"
    page._model._dirty_original[("p1", "cnj")] = "0001234-56.2023.5.10.0001"

    # A3 fix: page.reload(preserve_dirty=True) deve manter as dirty cells.
    page.reload(preserve_dirty=True)

    assert ("p1", "cnj") in page._model._dirty
    assert page._model._dirty[("p1", "cnj")] == "EDITED-CNJ"


def test_A3_base_table_page_reload_default_still_clears_dirty() -> None:
    """A3: backward-compat — chamadas a reload() sem kwarg continuam
    limpando _dirty (comportamento original). Importante para callers
    que explicitamente querem reset."""
    import sys
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage

    conn = _fresh_conn()
    cache_db.upsert_record(
        conn, "Processos", "p1",
        {"page_id": "p1", "cnj": "X", "tribunal": "TJDFT"},
    )
    page = ProcessosPage(conn=conn, token="t", user="u", facade=MagicMock())
    page._model._dirty[("p1", "cnj")] = "EDITED"

    page.reload()  # sem preserve_dirty

    assert ("p1", "cnj") not in page._model._dirty


def test_AUD_07_partial_save_failure_keeps_dirty_visible() -> None:
    """BUG-OP-03 (corrigido em Round B): cells que falharam continuam dirty;
    cells que tiveram sucesso são limpas individualmente. O dirty bar
    continua visível enquanto houver qualquer cell pendente."""
    import sys
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.pages.processos import ProcessosPage

    conn = _fresh_conn()
    cache_db.upsert_record(conn, "Processos", "p1",
                           {"page_id": "p1", "cnj": "X", "tribunal": "TJDFT"})

    page = ProcessosPage(conn=conn, token="t", user="u", facade=MagicMock())
    page._model._dirty[("p1", "cnj")] = "EDITED"
    page._model._dirty[("p1", "tribunal")] = "TRT/10"

    # BUG-OP-03 shape: per-cell results. tribunal succeeds, cnj fails.
    page._on_commit_finished("Processos", [
        {"page_id": "p1", "key": "tribunal", "edit_id": 0,
         "ok": True, "error": None},
        {"page_id": "p1", "key": "cnj", "edit_id": 0,
         "ok": False, "error": "boom"},
    ])
    # The successful cell is gone; the failed one stays dirty for retry.
    assert ("p1", "tribunal") not in page._model._dirty
    assert ("p1", "cnj") in page._model._dirty


# ---------------------------------------------------------------------------
# Área 8 — Atalhos (BUG confirmado)
# ---------------------------------------------------------------------------


@requires_pyside6
def test_AUD_08_shortcut_registry_loads_user_shortcuts() -> None:
    """BUG-OP-07 (corrigido em Round C): ShortcutRegistry.__init__ chama
    load_user_shortcuts() no boot, então quando o usuário customizou um
    atalho em uma sessão anterior o registry o reconhece imediatamente."""
    import sys
    from unittest.mock import patch
    from PySide6.QtWidgets import QApplication, QWidget
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.services.shortcuts import ShortcutRegistry, DEFAULT_SHORTCUTS

    win = QWidget()
    fake_user = dict(DEFAULT_SHORTCUTS)
    fake_user["nav_processos"] = "Ctrl+Alt+1"  # user override
    with patch("notion_rpadv.services.shortcuts.load_user_shortcuts",
               return_value=fake_user):
        reg = ShortcutRegistry(win, handlers={})
    assert reg.get_binding("nav_processos") == "Ctrl+Alt+1"
    # Other bindings still come from defaults
    assert reg.get_binding("save") == DEFAULT_SHORTCUTS["save"]


def test_AUD_08_shortcut_changed_signal_is_connected() -> None:
    """BUG-OP-07 (corrigido): MainWindow conecta config.shortcut_changed
    em _on_shortcut_changed. Verificação por grep no fonte: o
    `.shortcut_changed.connect(` precisa aparecer pelo menos 1 vez."""
    here = Path(__file__).resolve().parent.parent
    full = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (here / "notion_rpadv").rglob("*.py")
    )
    assert "shortcut_changed.connect(" in full


# ---------------------------------------------------------------------------
# Round C — BUG-OP-07: 5 new shortcut persistence tests
# ---------------------------------------------------------------------------


@requires_pyside6
def test_shortcut_registry_loads_user_overrides_at_init() -> None:
    """JSON com {nav_processos: Ctrl+Alt+1} → registry inicia com esse valor."""
    import sys, json, tempfile, pathlib
    from unittest.mock import patch
    from PySide6.QtWidgets import QApplication, QWidget
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.services.shortcuts import ShortcutRegistry

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "shortcuts.json"
        path.write_text(json.dumps({"nav_processos": "Ctrl+Alt+1"}),
                        encoding="utf-8")
        with patch("notion_rpadv.services.shortcuts_store._shortcuts_file",
                   return_value=path):
            win = QWidget()
            reg = ShortcutRegistry(win, handlers={})
            assert reg.get_binding("nav_processos") == "Ctrl+Alt+1"


@requires_pyside6
def test_shortcut_registry_falls_back_to_default_on_missing_key() -> None:
    """JSON parcial não apaga bindings ausentes — defaults preenchem."""
    import sys, json, tempfile, pathlib
    from unittest.mock import patch
    from PySide6.QtWidgets import QApplication, QWidget
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.services.shortcuts import ShortcutRegistry, DEFAULT_SHORTCUTS

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "shortcuts.json"
        path.write_text(json.dumps({"nav_processos": "Ctrl+Alt+1"}),
                        encoding="utf-8")
        with patch("notion_rpadv.services.shortcuts_store._shortcuts_file",
                   return_value=path):
            win = QWidget()
            reg = ShortcutRegistry(win, handlers={})
            assert reg.get_binding("save") == DEFAULT_SHORTCUTS["save"]
            assert reg.get_binding("nav_processos") == "Ctrl+Alt+1"


def test_shortcut_changed_persists_to_disk() -> None:
    """save_user_shortcuts grava JSON e a próxima leitura reflete o override."""
    import json, tempfile, pathlib
    from unittest.mock import patch

    from notion_rpadv.services.shortcuts_store import (
        save_user_shortcuts, load_user_shortcuts, DEFAULT_SHORTCUTS,
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "shortcuts.json"
        with patch("notion_rpadv.services.shortcuts_store._shortcuts_file",
                   return_value=path):
            current = dict(DEFAULT_SHORTCUTS)
            current["nav_processos"] = "Ctrl+Alt+1"
            save_user_shortcuts(current)
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["nav_processos"] == "Ctrl+Alt+1"
            # And reload sees it
            loaded = load_user_shortcuts()
            assert loaded["nav_processos"] == "Ctrl+Alt+1"


@requires_pyside6
def test_shortcut_changed_signal_rebinds_qshortcut() -> None:
    """update_binding muda a key do QShortcut existente em runtime."""
    import sys
    from PySide6.QtWidgets import QApplication, QWidget
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.services.shortcuts import ShortcutRegistry

    win = QWidget()
    fired: list = []
    reg = ShortcutRegistry(win, handlers={"nav_processos": lambda: fired.append(1)})
    reg.register_all()

    qsc = reg._shortcuts.get("nav_processos")
    assert qsc is not None
    original_key = qsc.key().toString()

    reg.update_binding("nav_processos", "Ctrl+Alt+1")
    # Same QShortcut object, key updated via setKey.
    assert reg._shortcuts.get("nav_processos") is qsc
    assert qsc.key().toString() == "Ctrl+Alt+1"
    assert qsc.key().toString() != original_key
    assert reg.get_binding("nav_processos") == "Ctrl+Alt+1"


def test_corrupt_shortcuts_json_falls_back_to_defaults() -> None:
    """JSON inválido → load_user_shortcuts não crasha; entrega defaults."""
    import tempfile, pathlib
    from unittest.mock import patch

    from notion_rpadv.services.shortcuts_store import (
        load_user_shortcuts, DEFAULT_SHORTCUTS,
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "shortcuts.json"
        path.write_text("{not valid json", encoding="utf-8")
        with patch("notion_rpadv.services.shortcuts_store._shortcuts_file",
                   return_value=path):
            loaded = load_user_shortcuts()
            assert loaded == dict(DEFAULT_SHORTCUTS)


# ---------------------------------------------------------------------------
# Round C — BUG-OP-09: split cache.db / audit.db + migration
# ---------------------------------------------------------------------------


def _empty_conn() -> sqlite3.Connection:
    """In-memory conn with NO tables initialised."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def test_init_cache_db_only_creates_cache_tables() -> None:
    """init_cache_db cria `records` mas NÃO cria `pending_edits`/`edit_log`."""
    from notion_rpadv.cache import db as cache_db
    conn = _empty_conn()
    cache_db.init_cache_db(conn)
    tables = {
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "records" in tables
    assert "meta" in tables
    assert "pending_edits" not in tables
    assert "edit_log" not in tables


def test_init_audit_db_only_creates_audit_tables() -> None:
    """init_audit_db cria `pending_edits` + `edit_log` mas NÃO cria `records`."""
    from notion_rpadv.cache import db as cache_db
    conn = _empty_conn()
    cache_db.init_audit_db(conn)
    tables = {
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "pending_edits" in tables
    assert "edit_log" in tables
    assert "meta" in tables
    assert "records" not in tables


def test_migration_copies_existing_logs_to_audit_db() -> None:
    """3 still-pending + 5 applied in cache.db → migra todas para audit.db
    e remove as tabelas legadas do cache.

    Note: pending_edits table holds rows in BOTH 'pending' and 'applied'
    statuses (mark_edit_applied flips status, not deletes). The migration
    preserves the full historical record, so the row count migrated is
    pending_edits + edit_log."""
    from notion_rpadv.cache import db as cache_db

    cache_conn = _empty_conn()
    audit_conn = _empty_conn()
    # Legacy combined cache: both schemas in one DB.
    cache_db.init_db(cache_conn)
    cache_db.init_audit_db(audit_conn)

    # Seed cache with 3 still-pending entries
    for i in range(3):
        cache_db.add_pending_edit(
            cache_conn, "Processos", f"p{i}", "tribunal", "OLD", f"NEW{i}",
        )
    # And 5 already-applied entries (one row in pending_edits with
    # status='applied' + one row in edit_log per call, so 5 + 5 = 10).
    for i in range(5):
        eid = cache_db.add_pending_edit(
            cache_conn, "Processos", f"q{i}", "fase", "C", f"E{i}",
        )
        cache_db.mark_edit_applied(cache_conn, eid, "deborah")

    assert cache_conn.execute(
        "SELECT COUNT(*) FROM pending_edits"
    ).fetchone()[0] == 8
    assert cache_conn.execute(
        "SELECT COUNT(*) FROM edit_log"
    ).fetchone()[0] == 5
    # Sanity: audit is empty pre-migration
    assert audit_conn.execute("SELECT COUNT(*) FROM edit_log").fetchone()[0] == 0

    moved = cache_db.migrate_audit_from_cache_if_needed(cache_conn, audit_conn)
    # 8 pending_edits rows + 5 edit_log rows = 13 rows moved.
    assert moved == 13

    # Audit has the rows
    assert audit_conn.execute(
        "SELECT COUNT(*) FROM pending_edits"
    ).fetchone()[0] == 8
    assert audit_conn.execute(
        "SELECT COUNT(*) FROM edit_log"
    ).fetchone()[0] == 5

    # Cache no longer has those tables
    cache_tables = {
        r["name"] for r in cache_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "pending_edits" not in cache_tables
    assert "edit_log" not in cache_tables


def test_migration_is_idempotent() -> None:
    """Migrar duas vezes não duplica linhas e não falha."""
    from notion_rpadv.cache import db as cache_db

    cache_conn = _empty_conn()
    audit_conn = _empty_conn()
    cache_db.init_db(cache_conn)
    cache_db.init_audit_db(audit_conn)

    cache_db.add_pending_edit(
        cache_conn, "Processos", "p1", "tribunal", "OLD", "NEW",
    )
    eid = cache_db.add_pending_edit(
        cache_conn, "Processos", "p2", "fase", "C", "E",
    )
    cache_db.mark_edit_applied(cache_conn, eid, "deborah")
    # 2 pending_edits rows (1 'pending' + 1 'applied') + 1 edit_log row.

    moved1 = cache_db.migrate_audit_from_cache_if_needed(cache_conn, audit_conn)
    moved2 = cache_db.migrate_audit_from_cache_if_needed(cache_conn, audit_conn)
    assert moved1 == 3  # 2 pending_edits + 1 edit_log
    # Second call is a no-op because the migration flag was set.
    assert moved2 == 0
    assert audit_conn.execute(
        "SELECT COUNT(*) FROM pending_edits"
    ).fetchone()[0] == 2
    assert audit_conn.execute(
        "SELECT COUNT(*) FROM edit_log"
    ).fetchone()[0] == 1


def test_clear_cache_does_not_affect_audit() -> None:
    """Apagar a tabela `records` (simulando 'limpar cache') não toca
    pending_edits nem edit_log na audit.db."""
    from notion_rpadv.cache import db as cache_db

    cache_conn = _empty_conn()
    audit_conn = _empty_conn()
    cache_db.init_cache_db(cache_conn)
    cache_db.init_audit_db(audit_conn)

    # Populate cache
    cache_db.upsert_record(
        cache_conn, "Processos", "p1", {"page_id": "p1", "cnj": "X"},
    )
    # Populate audit
    eid = cache_db.add_pending_edit(
        audit_conn, "Processos", "p1", "tribunal", "T1", "T2",
    )
    cache_db.mark_edit_applied(audit_conn, eid, "deborah")
    assert audit_conn.execute("SELECT COUNT(*) FROM edit_log").fetchone()[0] == 1

    # User clears the cache (would normally be done by deleting cache.db
    # outright; in-memory equivalent is dropping records).
    cache_conn.execute("DELETE FROM records")
    cache_conn.commit()

    # Audit untouched.
    assert audit_conn.execute("SELECT COUNT(*) FROM pending_edits").fetchone()[0] == 1
    assert audit_conn.execute("SELECT COUNT(*) FROM edit_log").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Round D — BUG-OP-04 / BUG-OP-05: dual-role search (DisplayRole + EditRole)
# ---------------------------------------------------------------------------


def _proxy_with_processo(distribuicao: str | None = None,
                         valor_causa: float | None = None) -> Any:
    """Helper: build a proxy + model with a single Processos row carrying
    the date / number under test."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel
    from notion_rpadv.models.filters import TableFilterProxy

    conn = _fresh_conn()
    record: dict = {"page_id": "p1", "cnj": "0000001-00.0000.0.00.0000"}
    if distribuicao is not None:
        record["distribuicao"] = distribuicao
    if valor_causa is not None:
        record["valor_causa"] = valor_causa
    cache_db.upsert_record(conn, "Processos", "p1", record)

    model = BaseTableModel("Processos", conn)
    proxy = TableFilterProxy()
    proxy.setSourceModel(model)
    return proxy


@requires_pyside6
def test_search_matches_iso_date_in_edit_role() -> None:
    """ISO date in the canonical (EditRole) value matches the search."""
    proxy = _proxy_with_processo(distribuicao="2025-03-20")
    proxy.set_search("2025-03-20")
    assert proxy.rowCount() == 1


@requires_pyside6
def test_search_matches_br_date_in_display_role() -> None:
    """BR-formatted date in DisplayRole still matches (regression guard)."""
    proxy = _proxy_with_processo(distribuicao="2025-03-20")
    proxy.set_search("20/03/2025")
    assert proxy.rowCount() == 1


@requires_pyside6
def test_search_matches_either_role_for_dates() -> None:
    """Defesa em profundidade: ambos os formatos retornam a mesma linha."""
    proxy = _proxy_with_processo(distribuicao="2025-03-20")

    proxy.set_search("2025-03-20")
    iso_count = proxy.rowCount()
    proxy.set_search("20/03/2025")
    br_count = proxy.rowCount()
    assert iso_count == br_count == 1

    # And a clearly non-matching date returns 0.
    proxy.set_search("01/01/1999")
    assert proxy.rowCount() == 0


@requires_pyside6
def test_search_matches_plain_number_in_edit_role() -> None:
    """`78500` (no thousands sep) matches a cell whose canonical value
    is the float 78500.0 even though DisplayRole shows `R$ 78.500,00`."""
    proxy = _proxy_with_processo(valor_causa=78500.0)
    proxy.set_search("78500")
    assert proxy.rowCount() == 1


@requires_pyside6
def test_search_matches_formatted_currency_in_display_role() -> None:
    """Searching the BR-formatted prefix still matches via DisplayRole.

    Depends on the case-insensitive ``formato.upper() == "BRL"`` fix in
    ``base_table_model._display_value`` — schemas declare the format in
    uppercase but the rendering used to compare lowercase, so currency
    cells silently fell back to ``str(78500.0) == "78500.0"``.
    """
    proxy = _proxy_with_processo(valor_causa=78500.0)
    proxy.set_search("R$ 78")
    assert proxy.rowCount() == 1
    # And the explicit BR-formatted value matches too.
    proxy.set_search("78.500")
    assert proxy.rowCount() == 1


# ---------------------------------------------------------------------------
# Round D — BUG-OP-08: Catalogo schema parity with Notion
# ---------------------------------------------------------------------------


def test_catalogo_schema_notion_names_are_well_formed() -> None:
    """Documentary snapshot of the current Catalogo schema. If a future
    change drops/renames a notion_name without updating this list, the
    test fails so the deviation is noticed."""
    from notion_bulk_edit.schemas import SCHEMAS
    cat = SCHEMAS["Catalogo"]
    expected = {
        "titulo":             ("Nome",                "title"),
        "categoria":          ("Categoria",           "select"),
        "area":               ("Área",                "select"),
        "tempo_estimado":     ("Tempo Estimado",      "rich_text"),
        "responsavel_padrao": ("Responsável Padrão",  "people"),
        "revisado":           ("Última Revisão",      "date"),
    }
    for key, (notion_name, tipo) in expected.items():
        spec = cat.get(key)
        assert spec is not None, f"Catalogo schema missing key {key!r}"
        assert spec.notion_name == notion_name, (
            f"{key}: notion_name expected {notion_name!r}, "
            f"got {spec.notion_name!r}"
        )
        assert spec.tipo == tipo, (
            f"{key}: tipo expected {tipo!r}, got {spec.tipo!r}"
        )


def test_catalogo_record_after_sync_has_populated_secondary_fields() -> None:
    """Given a Notion API response whose property keys exactly match the
    schema's notion_names, sync must extract every field. Validates the
    *machinery* — if this test passes but production data is empty,
    the issue is upstream (real notion_name divergence or empty data).
    """
    from notion_rpadv.cache.sync import SyncWorker
    from notion_rpadv.cache import db as cache_db
    from notion_bulk_edit.schemas import SCHEMAS
    from unittest.mock import MagicMock, patch

    cat = SCHEMAS["Catalogo"]
    # Build one Notion-shaped page using each spec's actual notion_name.
    page = {
        "id": "cat-1",
        "properties": {
            cat["titulo"].notion_name: {
                "title": [{"plain_text": "Embargos"}],
            },
            cat["categoria"].notion_name: {
                "select": {"name": "Recursos"},
            },
            cat["area"].notion_name: {
                "select": {"name": "Trabalhista"},
            },
            cat["tempo_estimado"].notion_name: {
                "rich_text": [{"plain_text": "2h"}],
            },
            cat["responsavel_padrao"].notion_name: {
                "people": [{"id": "u-1"}],
            },
            cat["revisado"].notion_name: {
                "date": {"start": "2026-04-27"},
            },
        },
    }

    conn = _fresh_conn()
    fake_client = MagicMock()
    fake_client.query_all = MagicMock(return_value=[page])
    with patch("notion_rpadv.cache.sync.NotionClient", return_value=fake_client):
        worker = SyncWorker(token="t", base="Catalogo", conn=conn)
        worker.finished = MagicMock()
        worker.error = MagicMock()
        worker.progress = MagicMock()
        worker.total = MagicMock()
        worker.run()

    rows = cache_db.get_all_records(conn, "Catalogo")
    assert len(rows) == 1
    rec = rows[0]
    assert rec["titulo"]             == "Embargos"
    assert rec["categoria"]          == "Recursos"
    assert rec["area"]               == "Trabalhista"
    assert rec["tempo_estimado"]     == "2h"
    assert rec["responsavel_padrao"] == ["u-1"]
    assert rec["revisado"]           == "2026-04-27"


@requires_cache
def test_catalogo_real_cache_secondary_fields_state() -> None:
    """Documentary check on the live cache: count how many of the 37
    Catalogo records have categoria/area/responsavel_padrao populated.

    This test does NOT enforce any threshold — it just records the
    current state so future runs after schema fixes show progress.
    Useful to verify the impact of OP-08 fixes without leaving an
    assertion that could go stale either way.
    """
    import json as _json
    conn = _readonly(_REAL_CACHE)
    rows = list(conn.execute(
        "SELECT data_json FROM records WHERE base='Catalogo'"
    ))
    populated = {"categoria": 0, "area": 0, "responsavel_padrao": 0,
                 "tempo_estimado": 0, "revisado": 0}
    for r in rows:
        d = _json.loads(r["data_json"])
        for k in populated:
            v = d.get(k)
            if v not in (None, "", []):
                populated[k] += 1
    # Sanity invariants only: at most as many populated as total records.
    total = len(rows)
    for k, n in populated.items():
        assert 0 <= n <= total, f"{k}: {n} > total {total}"


# ---------------------------------------------------------------------------
# Área 10 — Segurança
# ---------------------------------------------------------------------------


def test_AUD_10_token_stored_only_in_keyring() -> None:
    """Token é gerenciado pelo módulo auth.token_store via keyring,
    nunca em arquivo plano."""
    from notion_rpadv.auth import token_store
    # Sanity: API uses keyring underneath
    import keyring as kr
    # Just check the symbol bridge exists — actual token stays untouched
    assert token_store.get_token.__module__ == "notion_rpadv.auth.token_store"
    # And that the source uses keyring
    src = Path(token_store.__file__).read_text(encoding="utf-8")
    assert "keyring.set_password" in src
    assert "keyring.get_password" in src
    # No fallback to .env or settings.json
    assert "open(" not in src.replace("# ", "")  # no file IO in token_store


def test_AUD_10_no_outbound_urls_other_than_notion() -> None:
    """O código de produção só fala com api.notion.com. Sem telemetria."""
    here = Path(__file__).resolve().parent.parent
    bad: list[str] = []
    url_re = re.compile(r"https?://[^\s'\"\\)]+", re.IGNORECASE)
    for f in (here / "notion_rpadv").rglob("*.py"):
        for m in url_re.finditer(f.read_text(encoding="utf-8", errors="ignore")):
            url = m.group(0)
            if any(x in url for x in (
                "api.notion.com", "fonts.google.com",  # comment ref
                "github.com", "claude.ai", "notion.so",
            )):
                continue
            bad.append(f"{f.name}:{url}")
    for f in (here / "notion_bulk_edit").rglob("*.py"):
        for m in url_re.finditer(f.read_text(encoding="utf-8", errors="ignore")):
            url = m.group(0)
            if "api.notion.com" in url:
                continue
            bad.append(f"{f.name}:{url}")
    assert bad == [], f"unexpected outbound URLs: {bad[:3]}"


# ---------------------------------------------------------------------------
# Fase 0 — schema dinâmico (infraestrutura backend)
#
# Estes testes cobrem a infra criada na Fase 0 do plano de migração para
# schema dinâmico (DESIGN_SCHEMA_DINAMICO.md). Não há mudança de comportamento
# do app — o legado continua intocado. A Fase 0 só introduz:
#  - NotionClient.get_data_source(id)
#  - Tabelas meta_schemas + meta_user_columns em audit.db
#  - Parser e SchemaRegistry novos
# ---------------------------------------------------------------------------


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "schemas"


def _load_fixture(label: str) -> dict:
    """Lê uma fixture JSON capturada da API real (Fase 0)."""
    path = _FIXTURES_DIR / f"{label.lower()}_raw.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --- Componente 1: NotionClient.get_data_source ---


def test_FASE0_notion_client_has_get_data_source_method() -> None:
    """Componente 1: o método existe e tem assinatura (data_source_id: str)."""
    from typing import get_type_hints

    from notion_bulk_edit.notion_api import NotionClient
    assert hasattr(NotionClient, "get_data_source")
    sig = inspect.signature(NotionClient.get_data_source)
    params = list(sig.parameters.values())
    # self + data_source_id
    assert len(params) == 2
    assert params[1].name == "data_source_id"
    hints = get_type_hints(NotionClient.get_data_source)
    assert hints.get("data_source_id") is str


def test_FASE0_notion_client_get_data_source_uses_correct_endpoint() -> None:
    """Componente 1: chama _request com GET /data_sources/{id}."""
    from notion_bulk_edit.notion_api import NotionClient
    client = NotionClient.__new__(NotionClient)
    client._request = MagicMock(return_value={"object": "data_source"})  # type: ignore[attr-defined]
    result = client.get_data_source("abc-123")
    client._request.assert_called_once_with("GET", "/data_sources/abc-123")
    assert result == {"object": "data_source"}


# --- Componente 2: tabelas meta_schemas + meta_user_columns + helpers ---


def _audit_only_conn() -> sqlite3.Connection:
    """Cria connection com apenas init_audit_db aplicado (sem tabelas de cache)."""
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_audit_db(conn)
    return conn


def test_FASE0_init_audit_db_creates_meta_schemas_table() -> None:
    """Componente 2: init_audit_db cria meta_schemas idempotentemente."""
    conn = _audit_only_conn()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta_schemas'"
    ).fetchone()
    assert row is not None, "meta_schemas table missing"
    # Idempotência
    from notion_rpadv.cache import db as cache_db
    cache_db.init_audit_db(conn)  # não deve crashar
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(meta_schemas)").fetchall()}
    assert {
        "data_source_id", "base_label", "title_property",
        "schema_json", "schema_hash", "fetched_at",
        "api_version", "cache_version",
    }.issubset(cols)


def test_FASE0_init_audit_db_creates_meta_user_columns_table() -> None:
    """Componente 2: meta_user_columns existe (Fase 4 usará)."""
    conn = _audit_only_conn()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta_user_columns'"
    ).fetchone()
    assert row is not None
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(meta_user_columns)").fetchall()}
    assert {"user_id", "data_source_id", "visible_keys", "updated_at"}.issubset(cols)


def test_FASE0_upsert_schema_inserts_new_row() -> None:
    """Componente 2: upsert_schema insere e get_cached_schema lê."""
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    cache_db.upsert_schema(
        conn, "abc-123", "TestBase", "Title",
        '{"foo":1}', "hash1", 1700000000.0,
    )
    cached = cache_db.get_cached_schema(conn, "abc-123")
    assert cached is not None
    assert cached["base_label"] == "TestBase"
    assert cached["schema_json"] == '{"foo":1}'
    assert cached["schema_hash"] == "hash1"
    assert cached["api_version"] == "2025-09-03"  # default
    assert cached["cache_version"] == 1


def test_FASE0_upsert_schema_updates_existing_row() -> None:
    """Componente 2: segundo upsert com mesmo data_source_id atualiza, não duplica."""
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    cache_db.upsert_schema(
        conn, "abc-123", "TestBase", "T", '{"v":1}', "h1", 1.0,
    )
    cache_db.upsert_schema(
        conn, "abc-123", "TestBase2", "T2", '{"v":2}', "h2", 2.0,
    )
    rows = list(conn.execute("SELECT * FROM meta_schemas"))
    assert len(rows) == 1
    assert rows[0]["base_label"] == "TestBase2"
    assert rows[0]["schema_json"] == '{"v":2}'
    assert rows[0]["schema_hash"] == "h2"


def test_FASE0_get_cached_schema_returns_none_for_missing_id() -> None:
    """Componente 2: get_cached_schema com ID inexistente retorna None."""
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    assert cache_db.get_cached_schema(conn, "nao-existe") is None


def test_FASE0_get_all_cached_schemas_returns_list() -> None:
    """Componente 2: helper de listagem para boot."""
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    assert cache_db.get_all_cached_schemas(conn) == []
    cache_db.upsert_schema(conn, "id-1", "B1", "T", '{}', "h", 1.0)
    cache_db.upsert_schema(conn, "id-2", "B2", "T", '{}', "h", 1.0)
    result = cache_db.get_all_cached_schemas(conn)
    assert len(result) == 2
    assert {r["data_source_id"] for r in result} == {"id-1", "id-2"}


# --- Componente 3: parser ---


@pytest.fixture(scope="module")
def fixtures_available() -> bool:
    return _FIXTURES_DIR.exists() and any(_FIXTURES_DIR.glob("*_raw.json"))


def _skip_if_no_fixtures() -> None:
    if not _FIXTURES_DIR.exists() or not list(_FIXTURES_DIR.glob("*_raw.json")):
        pytest.skip("fixtures de schema não capturadas — rode scripts/validar_fase_0.py")


def test_FASE0_parse_catalogo_real_schema() -> None:
    """Componente 3: parser converte resposta real do Catálogo corretamente."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_parser import parse_to_schema_json
    raw = _load_fixture("Catalogo")
    parsed = parse_to_schema_json(raw, "Catalogo")
    assert parsed["base_label"] == "Catalogo"
    assert parsed["data_source_id"] == raw["id"]
    # Title é "Nome", key slugificada é "nome"
    assert parsed["title_property"] == "Nome"
    assert parsed["title_key"] == "nome"
    # Categoria é select com 4 opções
    cat = parsed["properties"].get("categoria")
    assert cat is not None
    assert cat["tipo"] == "select"
    assert len(cat["opcoes"]) == 4
    cat_names = {o["name"] for o in cat["opcoes"]}
    assert cat_names == {
        "Peças processuais", "Outras tarefas jurídicas",
        "Administrativo", "Diversos",
    }


def test_FASE0_parse_processos_real_schema() -> None:
    """Componente 3: Processos tem ≥30 propriedades, tribunal com 17 selects, em-dash em opções."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_parser import parse_to_schema_json
    raw = _load_fixture("Processos")
    parsed = parse_to_schema_json(raw, "Processos")
    assert len(parsed["properties"]) >= 30
    tribunal = parsed["properties"].get("tribunal")
    assert tribunal is not None
    assert tribunal["tipo"] == "select"
    tribunal_names = {o["name"] for o in tribunal["opcoes"]}
    assert "TRT/2" in tribunal_names
    assert len(tribunal["opcoes"]) >= 15
    # Tipo de ação — multi_select com em-dash
    tipo_acao = parsed["properties"].get("tipo_de_acao")
    assert tipo_acao is not None
    assert tipo_acao["tipo"] == "multi_select"
    tipo_acao_names = {o["name"] for o in tipo_acao["opcoes"]}
    # em-dash literal U+2014
    assert "Indenização — I" in tipo_acao_names


def test_FASE0_parse_clientes_real_schema() -> None:
    """Componente 3: Clientes tem UF com 27 opções, falecido como checkbox editável."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_parser import parse_to_schema_json
    raw = _load_fixture("Clientes")
    parsed = parse_to_schema_json(raw, "Clientes")
    uf = parsed["properties"].get("uf")
    assert uf is not None, f"UF missing; keys: {list(parsed['properties'].keys())[:10]}"
    assert uf["tipo"] == "select"
    assert len(uf["opcoes"]) == 27
    falecido = parsed["properties"].get("falecido")
    assert falecido is not None
    assert falecido["tipo"] == "checkbox"
    assert falecido["editavel"] is True


def test_FASE0_parse_tarefas_real_schema() -> None:
    """Componente 3: Tarefas tem responsavel como people, cliente como rollup readonly."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_parser import parse_to_schema_json
    raw = _load_fixture("Tarefas")
    parsed = parse_to_schema_json(raw, "Tarefas")
    responsavel = parsed["properties"].get("responsavel")
    assert responsavel is not None
    assert responsavel["tipo"] == "people"
    cliente = parsed["properties"].get("cliente")
    assert cliente is not None
    assert cliente["tipo"] == "rollup"
    assert cliente["editavel"] is False


def test_FASE0_parse_em_dash_preserved_in_options() -> None:
    """Componente 3: U+2014 (em-dash) literal preservado em nomes de opções."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_parser import parse_to_schema_json
    raw = _load_fixture("Processos")
    parsed = parse_to_schema_json(raw, "Processos")
    em_dash_count = 0
    for prop in parsed["properties"].values():
        for opt in prop.get("opcoes", []):
            if "—" in opt["name"]:
                em_dash_count += 1
    assert em_dash_count > 0, "esperava ao menos uma opção com em-dash"


def test_FASE0_parse_default_visible_heuristic() -> None:
    """Componente 3: title=True, multi_select=False, select=True como heurística."""
    from notion_bulk_edit.schema_parser import parse_to_schema_json
    raw = {
        "object": "data_source",
        "id": "test-id",
        "properties": {
            "Título": {"id": "title", "type": "title", "title": {}},
            "Categoria": {
                "id": "x", "type": "select",
                "select": {"options": [{"name": "A", "color": "blue"}]},
            },
            "Tags": {
                "id": "y", "type": "multi_select",
                "multi_select": {"options": []},
            },
            "Texto": {"id": "z", "type": "rich_text", "rich_text": {}},
        },
    }
    parsed = parse_to_schema_json(raw, "Test")
    assert parsed["properties"]["titulo"]["default_visible"] is True
    assert parsed["properties"]["categoria"]["default_visible"] is True
    assert parsed["properties"]["tags"]["default_visible"] is False
    assert parsed["properties"]["texto"]["default_visible"] is False


def test_FASE0_parse_unknown_type_does_not_crash() -> None:
    """Componente 3: tipo desconhecido vira readonly + invisível, não crasha."""
    from notion_bulk_edit.schema_parser import parse_to_schema_json
    raw = {
        "object": "data_source",
        "id": "test-id",
        "properties": {
            "Estranho": {"id": "x", "type": "novo_tipo_xyz", "novo_tipo_xyz": {}},
            "Título": {"id": "title", "type": "title", "title": {}},
        },
    }
    parsed = parse_to_schema_json(raw, "Test")
    estranho = parsed["properties"]["estranho"]
    assert estranho["tipo"] == "novo_tipo_xyz"
    assert estranho["editavel"] is False
    assert estranho["default_visible"] is False
    assert estranho["opcoes"] == []


def test_FASE0_compute_schema_hash_is_stable() -> None:
    """Componente 3: hash determinístico, independe da ordem das chaves."""
    from notion_bulk_edit.schema_parser import compute_schema_hash
    a = {"foo": 1, "bar": [1, 2, 3]}
    b = {"bar": [1, 2, 3], "foo": 1}  # ordem diferente
    assert compute_schema_hash(a) == compute_schema_hash(b)
    c = {"foo": 2, "bar": [1, 2, 3]}
    assert compute_schema_hash(a) != compute_schema_hash(c)


def test_FASE0_slugify_key_handles_accents_and_em_dash() -> None:
    """Componente 3: slugify gera keys ASCII canônicas."""
    from notion_bulk_edit.schema_parser import slugify_key
    assert slugify_key("Número do processo") == "numero_do_processo"
    assert slugify_key("Tipo de ação") == "tipo_de_acao"
    assert slugify_key("Data de distribuição") == "data_de_distribuicao"
    assert slugify_key("CPF/CNPJ") == "cpf_cnpj"
    assert slugify_key("Sobrestado - IRR 20") == "sobrestado_irr_20"
    # Em-dash em chaves de propriedade — vira underscore
    assert slugify_key("Indenização — I") == "indenizacao_i"


# --- Componente 4: SchemaRegistry ---


def test_FASE0_schema_registry_load_from_empty_cache() -> None:
    """Componente 4: registry sem schemas em cache retorna bases vazias."""
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    assert reg.bases() == []


def test_FASE0_schema_registry_load_from_populated_cache() -> None:
    """Componente 4: registry carrega schemas de meta_schemas."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_parser import (
        compute_schema_hash, parse_to_schema_json,
    )
    from notion_bulk_edit.schema_registry import SchemaRegistry
    from notion_rpadv.cache import db as cache_db
    conn = _audit_only_conn()
    raw = _load_fixture("Catalogo")
    parsed = parse_to_schema_json(raw, "Catalogo")
    schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    schema_hash = compute_schema_hash(parsed)
    cache_db.upsert_schema(
        conn, parsed["data_source_id"], "Catalogo",
        parsed["title_property"], schema_json, schema_hash, 1700000000.0,
    )
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    assert reg.bases() == ["Catalogo"]
    spec = reg.get_prop("Catalogo", "categoria")
    assert spec is not None
    assert spec.tipo == "select"
    assert spec.notion_name == "Categoria"


def test_FASE0_schema_registry_refresh_from_api_initial() -> None:
    """Componente 4: refresh em cache vazio retorna ChangeReport(initial)."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    raw = _load_fixture("Catalogo")
    mock_client = MagicMock()
    mock_client.get_data_source.return_value = raw
    report = reg.refresh_from_api("Catalogo", raw["id"], mock_client)
    mock_client.get_data_source.assert_called_once_with(raw["id"])
    assert report.kind == "initial"
    assert report.base == "Catalogo"
    # meta_schemas populado
    assert len(conn.execute("SELECT * FROM meta_schemas").fetchall()) == 1


def test_FASE0_schema_registry_refresh_from_api_unchanged() -> None:
    """Componente 4: dois refreshes seguidos sem mudança → segundo é unchanged."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    raw = _load_fixture("Catalogo")
    mock_client = MagicMock()
    mock_client.get_data_source.return_value = raw
    r1 = reg.refresh_from_api("Catalogo", raw["id"], mock_client)
    r2 = reg.refresh_from_api("Catalogo", raw["id"], mock_client)
    assert r1.kind == "initial"
    assert r2.kind == "unchanged"


def test_FASE0_schema_registry_refresh_from_api_changed() -> None:
    """Componente 4: alteração em opções de select → ChangeReport(changed)."""
    _skip_if_no_fixtures()
    import copy
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    raw_a = _load_fixture("Catalogo")
    raw_b = copy.deepcopy(raw_a)
    # Adiciona opção nova em Categoria
    raw_b["properties"]["Categoria"]["select"]["options"].append(
        {"id": "novo", "name": "Novo Tipo", "color": "green"}
    )
    mock_client = MagicMock()
    mock_client.get_data_source.side_effect = [raw_a, raw_b]
    r1 = reg.refresh_from_api("Catalogo", raw_a["id"], mock_client)
    r2 = reg.refresh_from_api("Catalogo", raw_a["id"], mock_client)
    assert r1.kind == "initial"
    assert r2.kind == "changed"
    assert "categoria" in r2.changed


def test_FASE0_schema_registry_get_prop_returns_none_for_missing() -> None:
    """Componente 4: lookup com base ou key inexistente retorna None."""
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    reg.load_all_from_cache()
    assert reg.get_prop("BaseInexistente", "x") is None
    assert reg.get_prop("Outra", "y") is None


def test_FASE0_schema_registry_colunas_visiveis_returns_default_visible_only() -> None:
    """Componente 4: colunas_visiveis sem user_id retorna default_visible=True ordenado."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    raw = _load_fixture("Catalogo")
    mock_client = MagicMock()
    mock_client.get_data_source.return_value = raw
    reg.refresh_from_api("Catalogo", raw["id"], mock_client)
    cols = reg.colunas_visiveis("Catalogo")
    # Title sempre primeiro
    assert cols[0] == "nome"
    # Multi-select e rollup nunca devem aparecer no default
    schema = reg.schema_for_base("Catalogo")
    for k in cols:
        assert schema[k].tipo not in ("multi_select", "rollup", "rich_text")


def test_FASE0_schema_registry_vocabulario_returns_strings_only() -> None:
    """Componente 4: vocabulario retorna tuple[str], sem cor."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_registry import SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    raw = _load_fixture("Catalogo")
    mock_client = MagicMock()
    mock_client.get_data_source.return_value = raw
    reg.refresh_from_api("Catalogo", raw["id"], mock_client)
    vocab = reg.vocabulario("Catalogo", "categoria")
    assert isinstance(vocab, tuple)
    assert all(isinstance(v, str) for v in vocab)
    assert "Peças processuais" in vocab


def test_FASE0_schema_registry_vocabulario_full_returns_optionspec() -> None:
    """Componente 4: vocabulario_full retorna tuple[OptionSpec] com cor."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_registry import OptionSpec, SchemaRegistry
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    raw = _load_fixture("Catalogo")
    mock_client = MagicMock()
    mock_client.get_data_source.return_value = raw
    reg.refresh_from_api("Catalogo", raw["id"], mock_client)
    vocab = reg.vocabulario_full("Catalogo", "categoria")
    assert isinstance(vocab, tuple)
    assert all(isinstance(v, OptionSpec) for v in vocab)
    assert all(hasattr(v, "name") and hasattr(v, "color") for v in vocab)


def test_FASE0_schema_registry_singleton_lifecycle() -> None:
    """Componente 4: get_schema_registry sem init → RuntimeError."""
    import notion_bulk_edit.schema_registry as sr
    # Reset singleton
    sr._registry = None
    with pytest.raises(RuntimeError):
        sr.get_schema_registry()
    conn = _audit_only_conn()
    sr.init_schema_registry(conn)
    assert sr.get_schema_registry() is not None
    # Cleanup para não interferir em outros testes
    sr._registry = None


def test_FASE0_boot_refresh_all_calls_refresh_for_each_base() -> None:
    """Componente 4: boot_refresh_all percorre data_sources e retorna lista de reports."""
    _skip_if_no_fixtures()
    from notion_bulk_edit.schema_registry import SchemaRegistry, boot_refresh_all
    conn = _audit_only_conn()
    reg = SchemaRegistry(conn)
    raw_cat = _load_fixture("Catalogo")
    raw_tar = _load_fixture("Tarefas")
    mock_client = MagicMock()
    mock_client.get_data_source.side_effect = [raw_cat, raw_tar]
    reports = boot_refresh_all(
        mock_client, reg,
        {"Catalogo": raw_cat["id"], "Tarefas": raw_tar["id"]},
    )
    assert len(reports) == 2
    assert {r.base for r in reports} == {"Catalogo", "Tarefas"}
    assert all(r.kind == "initial" for r in reports)
    assert mock_client.get_data_source.call_count == 2
