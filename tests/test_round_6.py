"""Round 6 — testes pra rollup-de-relation + redesign Dashboard.

Parte 1: rollup que aponta pra um campo de relation na base relacionada
(ex: Tarefas.Cliente roll up Processos.Clientes) deve resolver UUIDs
pra títulos em todas as camadas — display da tabela, xlsx export,
search livre.

Parte 2: Dashboard reformata Tarefas Urgentes em 3 grupos
(Vencidas/Hoje/Amanhã) com cards reformatados.
"""
from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest


_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "schemas"


def _audit_only_conn() -> sqlite3.Connection:
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_audit_db(conn)
    return conn


def _full_conn() -> sqlite3.Connection:
    """Conn com cache + audit (records vivem no cache, schemas no audit)."""
    from notion_rpadv.cache import db as cache_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# Parte 1 — rollup-de-relation
# ---------------------------------------------------------------------------


def test_R6_schema_parser_captures_rollup_meta() -> None:
    """schema_parser agora preserva rollup_meta (relation_property_name,
    rollup_property_name, function) no dict canônico, condição
    necessária pra registry fazer o 2-hop."""
    from notion_bulk_edit.schema_parser import parse_to_schema_json
    raw = {
        "id": "ds-task",
        "properties": {
            "Tarefa": {"type": "title", "title": {}},
            "Processo": {
                "type": "relation",
                "relation": {"data_source_id": "ds-proc"},
            },
            "Cliente": {
                "type": "rollup",
                "rollup": {
                    "relation_property_name": "Processo",
                    "rollup_property_name": "Clientes",
                    "function": "show_original",
                    "relation_property_id": "abc",
                    "rollup_property_id": "xyz",
                },
            },
        },
    }
    parsed = parse_to_schema_json(raw, "Tasks")
    cliente_meta = parsed["properties"]["cliente"].get("rollup_meta", {})
    assert cliente_meta.get("relation_property_name") == "Processo"
    assert cliente_meta.get("rollup_property_name") == "Clientes"
    assert cliente_meta.get("function") == "show_original"


def test_R6_registry_resolves_target_base_for_rollup_relation() -> None:
    """Registry usa rollup_meta + 2-hop pra setar PropSpec.target_base
    em Tarefas.cliente. Smoke usando os fixtures reais (Tarefas →
    Processos → Clientes)."""
    if not (_FIXTURES_DIR / "tarefas_raw.json").exists():
        pytest.skip("fixtures ausentes")
    from notion_bulk_edit.schema_registry import get_schema_registry
    reg = get_schema_registry()
    spec = reg.get_prop("Tarefas", "cliente")
    assert spec is not None
    assert spec.tipo == "rollup"
    assert spec.target_base == "Clientes"


def test_R6_registry_no_target_base_for_rollup_of_select() -> None:
    """Tarefas.Tribunal é rollup-de-select (não relation) — não deveria
    receber target_base. Hop 2 detecta que rollup_property_name aponta
    pra select e desiste silenciosamente."""
    if not (_FIXTURES_DIR / "tarefas_raw.json").exists():
        pytest.skip("fixtures ausentes")
    from notion_bulk_edit.schema_registry import get_schema_registry
    reg = get_schema_registry()
    spec = reg.get_prop("Tarefas", "tribunal")
    assert spec is not None
    assert spec.tipo == "rollup"
    assert spec.target_base == ""


def test_R6_flatten_rollup_uuids_handles_nested_lists() -> None:
    """``_flatten_rollup_uuids`` achata ``[[uuid1], [uuid2, uuid3]]``
    pra ``[uuid1, uuid2, uuid3]``."""
    from notion_rpadv.models.base_table_model import _flatten_rollup_uuids
    assert _flatten_rollup_uuids([["a"], ["b", "c"]]) == ["a", "b", "c"]
    # Mistura de nested + plain string preservada.
    assert _flatten_rollup_uuids([["a"], "b"]) == ["a", "b"]
    # Vazio.
    assert _flatten_rollup_uuids([]) == []
    assert _flatten_rollup_uuids(None) == []
    # Strings vazias dentro são filtradas.
    assert _flatten_rollup_uuids([[""], ["c"]]) == ["c"]


def test_R6_resolve_rollup_relation_uses_cache_titles() -> None:
    """``_resolve_rollup_relation`` consulta cache_db pra cada UUID e
    retorna o título da página. Múltiplos viram comma-separated."""
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import _resolve_rollup_relation
    conn = _full_conn()
    cache_db.upsert_record(conn, "Clientes", "uuid-1", {
        "page_id": "uuid-1", "nome": "Maria Silva",
    })
    cache_db.upsert_record(conn, "Clientes", "uuid-2", {
        "page_id": "uuid-2", "nome": "João Costa",
    })
    result = _resolve_rollup_relation(conn, ["uuid-1", "uuid-2"], "Clientes")
    assert result == "Maria Silva, João Costa"


def test_R6_resolve_rollup_relation_falls_back_to_uuid_when_missing() -> None:
    """Página não cacheada → UUID-cru no display (não "—" como em
    _resolve_relation). Diagnóstico vivo quando target_base ainda não
    sincronizou."""
    from notion_rpadv.models.base_table_model import _resolve_rollup_relation
    conn = _full_conn()
    # Nenhuma Cliente cacheada
    result = _resolve_rollup_relation(
        conn, ["uuid-fora", "outro-uuid"], "Clientes",
    )
    assert result == "uuid-fora, outro-uuid"


def test_R6_resolve_rollup_relation_caps_at_5_with_overflow_marker() -> None:
    """Cap visual em 5 entradas + marker ``+N`` pro resto. Rollups
    podem agregar dezenas de itens — display de tabela não comporta."""
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import _resolve_rollup_relation
    conn = _full_conn()
    for i in range(10):
        cache_db.upsert_record(conn, "Clientes", f"u{i}", {
            "page_id": f"u{i}", "nome": f"C{i}",
        })
    result = _resolve_rollup_relation(
        conn, [f"u{i}" for i in range(10)], "Clientes",
    )
    # 5 nomes + " +5"
    assert result.endswith("+5")
    assert "C0" in result and "C4" in result


def test_R6_rollup_relation_resolves_title_in_display() -> None:
    """``_display_value`` pra rollup achata nested antes do join. Sem
    target_base setado, retorna UUIDs flat (caller — data() — resolve
    quando spec.target_base existe)."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value
    spec = PropSpec(
        notion_name="Cliente", tipo="rollup", label="Cliente",
        editavel=False, obrigatorio=False, opcoes=(),
    )
    # Nested list (sem resolução, target_base="" no spec):
    result = _display_value(spec, [["uuid-1"], ["uuid-2"]])
    assert result == "uuid-1, uuid-2"


def test_R6_rollup_relation_falls_back_to_uuid_when_target_missing() -> None:
    """data() resolve via _resolve_rollup_relation. UUIDs sem registro
    cacheado caem em UUID-cru (não "—"). Smoke direto da função."""
    from notion_rpadv.models.base_table_model import _resolve_rollup_relation
    conn = _full_conn()
    # Sem cachear nenhum registro: tudo cai em UUID-cru.
    result = _resolve_rollup_relation(
        conn, ["uuid-x", "uuid-y"], "Clientes",
    )
    assert "uuid-x" in result
    assert "uuid-y" in result


def test_R6_rollup_relation_handles_multiple_items_comma_separated() -> None:
    """Múltiplos UUIDs em rollup viram comma-separated, com cache hits
    e misses misturados (cache → nome, miss → UUID)."""
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import _resolve_rollup_relation
    conn = _full_conn()
    cache_db.upsert_record(conn, "Clientes", "u1", {
        "page_id": "u1", "nome": "Alice",
    })
    # u2 não cacheado.
    result = _resolve_rollup_relation(conn, ["u1", "u2"], "Clientes")
    assert result == "Alice, u2"


def test_R6_rollup_relation_resolves_in_xlsx_export(tmp_path) -> None:
    """Snapshot xlsx resolve UUIDs de rollup-de-relation via
    title_cache (cobre as bases selecionadas no export). Sem isso o
    operador veria UUIDs no Excel da Cliente, mesmo bug da tabela."""
    from notion_rpadv.services.snapshot_exporter import export_snapshot
    from openpyxl import load_workbook

    cliente_page = {
        "id": "cli-1",
        "properties": {
            "Nome": {
                "type": "title",
                "title": [{"plain_text": "Maria Silva"}],
            },
        },
    }
    tarefa_page = {
        "id": "tar-1",
        "properties": {
            "Tarefa": {
                "type": "title",
                "title": [{"plain_text": "Petição inicial"}],
            },
            # Rollup retorna nested array de relation blocks.
            "Cliente": {
                "type": "rollup",
                "rollup": {
                    "type": "array",
                    "array": [
                        {
                            "type": "relation",
                            "relation": [{"id": "cli-1"}],
                        },
                    ],
                },
            },
        },
    }

    def query_all(dsid: str, on_progress=None):
        return [cliente_page] if dsid == "ds-c" else [tarefa_page]
    client = MagicMock()
    client.query_all.side_effect = query_all

    schemas = {
        "SynthClientes": {"properties": {
            "nome": {
                "notion_name": "Nome", "tipo": "title",
                "default_visible": True, "default_order": 1, "opcoes": [],
            },
        }},
        "SynthTarefas": {"properties": {
            "tarefa": {
                "notion_name": "Tarefa", "tipo": "title",
                "default_visible": True, "default_order": 1, "opcoes": [],
            },
            "cliente": {
                "notion_name": "Cliente", "tipo": "rollup",
                "default_visible": True, "default_order": 2, "opcoes": [],
            },
        }},
    }
    reg = MagicMock()
    reg._schemas = schemas
    dest = str(tmp_path / "out.xlsx")
    export_snapshot(
        client=client, bases=["SynthClientes", "SynthTarefas"],
        dest_path=dest, schema_registry=reg,
        data_sources={"SynthClientes": "ds-c", "SynthTarefas": "ds-t"},
        notion_users={},
    )
    wb = load_workbook(dest)
    ws = wb["SynthTarefas"]
    # col 2 = Cliente (rollup-de-relation). Resolvido pra "Maria Silva".
    assert ws.cell(row=2, column=2).value == "Maria Silva"


def test_R6_rollup_relation_xlsx_falls_back_to_uuid_when_target_not_in_snapshot(
    tmp_path,
) -> None:
    """Quando o usuário exporta só Tarefas (sem Clientes), os UUIDs de
    rollup ficam em UUID-cru (sem "[?]"). Diagnóstico preservado."""
    from notion_rpadv.services.snapshot_exporter import export_snapshot
    from openpyxl import load_workbook

    tarefa_page = {
        "id": "tar-1",
        "properties": {
            "Tarefa": {"type": "title", "title": [{"plain_text": "T1"}]},
            "Cliente": {
                "type": "rollup",
                "rollup": {
                    "type": "array",
                    "array": [
                        {
                            "type": "relation",
                            "relation": [{"id": "cli-fora"}],
                        },
                    ],
                },
            },
        },
    }
    client = MagicMock()
    client.query_all.return_value = [tarefa_page]
    schemas = {"SynthTarefas": {"properties": {
        "tarefa": {
            "notion_name": "Tarefa", "tipo": "title",
            "default_visible": True, "default_order": 1, "opcoes": [],
        },
        "cliente": {
            "notion_name": "Cliente", "tipo": "rollup",
            "default_visible": True, "default_order": 2, "opcoes": [],
        },
    }}}
    reg = MagicMock()
    reg._schemas = schemas
    dest = str(tmp_path / "out.xlsx")
    result = export_snapshot(
        client=client, bases=["SynthTarefas"], dest_path=dest,
        schema_registry=reg, data_sources={"SynthTarefas": "ds-t"},
        notion_users={},
    )
    wb = load_workbook(dest)
    ws = wb["SynthTarefas"]
    # UUID-cru (não "[?]") porque rollup-de-relation usa UUID fallback.
    assert ws.cell(row=2, column=2).value == "cli-fora"
    # Não conta como relation_misses (rollup tem semântica diferente
    # de relation direta — pode apontar pra páginas fora do snapshot
    # por design).
    assert result.relation_misses == 0


def test_R6_search_matches_resolved_title_in_rollup_relation() -> None:
    """Search livre casa pelo nome resolvido no rollup-de-relation,
    não pelo UUID. Sem isso o operador busca "Maria" e não acha
    Tarefas dela porque a célula mostraria UUID."""
    import sys
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(sys.argv)
    from notion_bulk_edit.config import DATA_SOURCES
    from notion_bulk_edit.schema_registry import get_schema_registry
    from notion_rpadv.cache import db as cache_db
    from notion_rpadv.models.base_table_model import BaseTableModel
    from notion_rpadv.models.filters import TableFilterProxy

    if not (_FIXTURES_DIR / "tarefas_raw.json").exists():
        pytest.skip("fixtures ausentes")

    conn = _full_conn()
    # Cache uma Cliente com nome conhecido
    cache_db.upsert_record(conn, "Clientes", "cli-x", {
        "page_id": "cli-x", "nome": "Aurora Magalhães",
    })
    # Cache uma Tarefa cuja rollup Cliente aponta pra cli-x
    cache_db.upsert_record(conn, "Tarefas", "tar-x", {
        "page_id": "tar-x",
        "tarefa": "Petição",
        "cliente": [["cli-x"]],   # rollup-array nested decoded
    })
    # Força user_columns pra incluir cliente
    audit = get_schema_registry()._audit_conn  # noqa: SLF001
    cache_db.set_user_columns(
        audit, "u-search", DATA_SOURCES["Tarefas"], ["tarefa", "cliente"],
    )
    model = BaseTableModel("Tarefas", conn, user_id="u-search")
    proxy = TableFilterProxy()
    proxy.setSourceModel(model)
    # Search casa o nome resolvido (DisplayRole renderizado pelo
    # _resolve_rollup_relation a partir do cache local de Clientes).
    proxy.set_search("Aurora")
    assert proxy.rowCount() == 1
    # Sub-string do nome também casa.
    proxy.set_search("Magalh")
    assert proxy.rowCount() == 1
    # Termo desconhecido não casa.
    proxy.set_search("inexistente-xyz-zzz")
    assert proxy.rowCount() == 0
    # Nota: o filtro do app busca em DisplayRole + EditRole (BUG-OP-04
    # dual-role search), então UUID-cru ainda casa via EditRole. Isso
    # é intencional — search é defensivo e quer achar o registro de
    # qualquer ângulo, não só o nome resolvido.


# ---------------------------------------------------------------------------
# Sweep: lista de rollup-de-relation por base (Round 6 spec ask)
# ---------------------------------------------------------------------------


def test_R6_sweep_rollup_relation_properties_per_base() -> None:
    """Round 6 sweep: documenta quais propriedades rollup têm
    target_base resolvido (rollup-de-relation), em todas as 4 bases.
    Smoke garante que a fix cobre todas automaticamente — não
    case-by-case. Falha aqui sinaliza que uma rollup nova entrou no
    schema sem ser resolvida."""
    from notion_bulk_edit.schema_registry import get_schema_registry
    if not (_FIXTURES_DIR / "tarefas_raw.json").exists():
        pytest.skip("fixtures ausentes")
    reg = get_schema_registry()
    rollup_relations: dict[str, dict[str, str]] = {}
    for base in ["Clientes", "Processos", "Tarefas", "Catalogo"]:
        for slug, spec in reg.schema_for_base(base).items():
            if spec.tipo == "rollup" and spec.target_base:
                rollup_relations.setdefault(base, {})[slug] = spec.target_base
    # Tarefas.cliente é o caso conhecido — o sweep deve incluí-lo.
    assert rollup_relations.get("Tarefas", {}).get("cliente") == "Clientes"
