"""Adapter shim em schemas.py — testes do proxy SCHEMAS.

Fase 1 introduziu o proxy ``SCHEMAS`` substituindo o dict literal hardcoded.
Fase 3 removeu a flag ``USE_DYNAMIC_SCHEMA``, ``DYNAMIC_BASES`` e o
``_LEGACY_SCHEMAS`` — proxy agora consulta o registry dinâmico direto, com
fallback para dict vazio quando o singleton não foi inicializado.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from notion_bulk_edit.schema_parser import (
    compute_schema_hash,
    parse_to_schema_json,
)
from notion_bulk_edit.schemas import (
    SCHEMAS,
    PropSpec,
    get_prop,
)
from notion_rpadv.cache import db as cache_db


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "schemas"


def _load_fixture(label: str) -> dict:
    path = _FIXTURES_DIR / f"{label.lower()}_raw.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _audit_only_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_audit_db(conn)
    return conn


@pytest.fixture
def reset_registry():
    """Limpa o singleton entre testes que mexem nele."""
    import notion_bulk_edit.schema_registry as sr
    saved = sr._registry
    yield
    sr._registry = saved


# --- Re-export de OptionSpec (PEP 562 lazy) ---


def test_FASE1_option_spec_re_exported_from_schemas() -> None:
    """OptionSpec acessível via schemas mas é o objeto canônico."""
    from notion_bulk_edit.schemas import OptionSpec as ReExported
    from notion_bulk_edit.schema_registry import OptionSpec as Canonical
    assert ReExported is Canonical


def test_FASE1_schemas_module_lazy_attr_raises_for_unknown() -> None:
    """__getattr__ não vira fallback genérico — só OptionSpec."""
    import notion_bulk_edit.schemas as schemas_mod
    with pytest.raises(AttributeError):
        _ = schemas_mod.AlgoQueNaoExiste


# --- _SchemasProxy ---


def test_FASE1_schemas_proxy_lists_4_known_bases() -> None:
    """SCHEMAS expõe as 4 bases canônicas."""
    bases = list(SCHEMAS)
    assert set(bases) == {"Processos", "Clientes", "Tarefas", "Catalogo"}
    assert len(SCHEMAS) == 4


def test_FASE1_schemas_proxy_keyerror_for_unknown_base() -> None:
    """SCHEMAS['Inexistente'] levanta KeyError."""
    with pytest.raises(KeyError):
        _ = SCHEMAS["Inexistente"]


def test_FASE3_schemas_proxy_uses_registry_when_initialized(
    reset_registry,
) -> None:
    """Fase 3: proxy lê do registry direto. Sem singleton, devolve {} para
    a base — não crasha."""
    from notion_bulk_edit.schema_registry import init_schema_registry
    conn = _audit_only_conn()
    raw = _load_fixture("Processos")
    parsed = parse_to_schema_json(raw, "Processos")
    schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    cache_db.upsert_schema(
        conn, parsed["data_source_id"], "Processos",
        parsed["title_property"], schema_json,
        compute_schema_hash(parsed), 1700000000.0,
    )
    init_schema_registry(conn)

    proc = SCHEMAS["Processos"]
    keys = set(proc.keys())
    assert "numero_do_processo" in keys
    spec = proc["numero_do_processo"]
    assert isinstance(spec, PropSpec)
    assert spec.tipo == "title"


def test_FASE3_schemas_proxy_empty_registry_returns_empty_mapping(
    reset_registry,
) -> None:
    """Fase 3: sem registry inicializado (cenário de testes unitários),
    SCHEMAS["Base"] devolve um Mapping vazio em vez de crashar."""
    import notion_bulk_edit.schema_registry as sr
    sr._registry = None
    proc = SCHEMAS["Processos"]
    assert len(proc) == 0
    # Lookup específico devolve None via get_prop
    assert get_prop("Processos", "qualquer") is None


# --- Helper get_prop ---


def test_FASE1_get_prop_routes_through_proxy(reset_registry) -> None:
    """get_prop usa SCHEMAS via Mapping API e devolve None para chave/base
    inexistentes (sem crash)."""
    from notion_bulk_edit.schema_registry import init_schema_registry
    conn = _audit_only_conn()
    raw = _load_fixture("Processos")
    parsed = parse_to_schema_json(raw, "Processos")
    schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    cache_db.upsert_schema(
        conn, parsed["data_source_id"], "Processos",
        parsed["title_property"], schema_json,
        compute_schema_hash(parsed), 1700000000.0,
    )
    init_schema_registry(conn)

    spec = get_prop("Processos", "numero_do_processo")
    assert spec is not None
    assert spec.tipo == "title"
    assert get_prop("Processos", "inexistente") is None
    assert get_prop("BaseInexistente", "qualquer") is None


# --- Boot wiring ---


def test_FASE1_init_schema_registry_called_on_main_window_boot() -> None:
    """app.py importa init_schema_registry no escopo correto.

    Smoke estrutural — garante que a chamada existe na MainWindow.__init__.
    Teste de runtime completo dependeria de PySide6 + mock pesado de
    NotionFacade/SyncManager; coberto pelos scripts validar_fase_*.py.
    """
    src = Path(__file__).resolve().parent.parent / "notion_rpadv" / "app.py"
    text = src.read_text(encoding="utf-8")
    assert "init_schema_registry(self._audit_conn)" in text
    assert "boot_refresh_all" in text
    # Fase 3: sem branch condicional de USE_DYNAMIC_SCHEMA
    assert "if bulk_config.USE_DYNAMIC_SCHEMA:" not in text
