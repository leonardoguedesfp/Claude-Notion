"""Fase 1 — schema dinâmico: testes do adapter shim em schemas.py.

Cobre:
- USE_DYNAMIC_SCHEMA default False
- DYNAMIC_BASES default vazio
- SCHEMAS proxy: flag off → legado; flag on + base não mapeada → legado;
  flag on + base mapeada + registry populado → registry
- OptionSpec re-exportado (lazy via PEP 562)
- _BaseSchemaProxy fallback silencioso quando registry não inicializado
- Boot wiring (init_schema_registry chamado pelo MainWindow)

Não roda contra a API real. Usa fixtures da Fase 0 capturadas em
``tests/fixtures/schemas/*_raw.json``.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from notion_bulk_edit import config
from notion_bulk_edit.schema_parser import (
    compute_schema_hash,
    parse_to_schema_json,
)
from notion_bulk_edit.schemas import (
    SCHEMAS,
    PropSpec,
    _LEGACY_SCHEMAS,
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
def reset_flags():
    """Garante que os testes não vazem flags entre eles."""
    saved_use = config.USE_DYNAMIC_SCHEMA
    saved_bases = set(config.DYNAMIC_BASES)
    yield
    config.USE_DYNAMIC_SCHEMA = saved_use
    config.DYNAMIC_BASES = saved_bases


@pytest.fixture
def reset_registry():
    """Limpa o singleton entre testes que mexem nele."""
    import notion_bulk_edit.schema_registry as sr
    saved = sr._registry
    yield
    sr._registry = saved


# --- Componente 3: USE_DYNAMIC_SCHEMA + DYNAMIC_BASES (estado atual) ---
#
# A Fase 2a virou o default — flag ON e Catálogo na whitelist. Estes testes
# documentam o estado atual de config.py e servem como tripwire: alguém
# revertendo a flag ou removendo Catálogo precisa também atualizar aqui.


def test_FASE2A_use_dynamic_schema_is_active() -> None:
    """Fase 2a: flag global ON (era False na Fase 1; ativada agora)."""
    assert config.USE_DYNAMIC_SCHEMA is True


def test_FASE2A_dynamic_bases_contains_only_catalogo() -> None:
    """Fase 2a: só Catálogo migrado. Outras 3 entram nas Fases 2b/2c/2d."""
    assert config.DYNAMIC_BASES == {"Catalogo"}


# --- Componente 1: OptionSpec re-export lazy ---


def test_FASE1_option_spec_re_exported_from_schemas() -> None:
    """Componente 1: OptionSpec acessível via schemas mas é o objeto canônico."""
    from notion_bulk_edit.schemas import OptionSpec as ReExported
    from notion_bulk_edit.schema_registry import OptionSpec as Canonical
    assert ReExported is Canonical


def test_FASE1_schemas_module_lazy_attr_raises_for_unknown() -> None:
    """Componente 1: __getattr__ não vira fallback genérico — só OptionSpec."""
    import notion_bulk_edit.schemas as schemas_mod
    with pytest.raises(AttributeError):
        _ = schemas_mod.AlgoQueNaoExiste


# --- Componente 2: SCHEMAS proxy ---


def test_FASE1_schemas_proxy_lists_4_known_bases() -> None:
    """Componente 2: SCHEMAS exibe as 4 bases canônicas, mesmo com flag off."""
    bases = list(SCHEMAS)
    assert set(bases) == {"Processos", "Clientes", "Tarefas", "Catalogo"}
    assert len(SCHEMAS) == 4


def test_FASE1_schemas_proxy_flag_off_uses_legacy(reset_flags) -> None:
    """Componente 2: flag off → SCHEMAS retorna do _LEGACY_SCHEMAS hardcoded."""
    config.USE_DYNAMIC_SCHEMA = False
    spec_proxy = SCHEMAS["Processos"]["cnj"]
    spec_legacy = _LEGACY_SCHEMAS["Processos"]["cnj"]
    assert spec_proxy is spec_legacy


def test_FASE1_schemas_proxy_flag_on_empty_registry_falls_back(
    reset_flags, reset_registry,
) -> None:
    """Componente 2: flag on + base mapeada mas registry vazio → fallback legado."""
    import notion_bulk_edit.schema_registry as sr
    sr._registry = None  # singleton não inicializado
    config.USE_DYNAMIC_SCHEMA = True
    config.DYNAMIC_BASES = {"Processos"}
    # Não deve lançar exceção — fallback silencioso
    spec_proxy = SCHEMAS["Processos"]["cnj"]
    spec_legacy = _LEGACY_SCHEMAS["Processos"]["cnj"]
    assert spec_proxy is spec_legacy


def test_FASE1_schemas_proxy_flag_on_uses_registry(
    reset_flags, reset_registry,
) -> None:
    """Componente 2: flag on + base mapeada + registry populado → registry vence.

    Confirma que o slug dinâmico ('numero_do_processo') está disponível e
    que NÃO é o mesmo objeto Python do legado ('cnj').
    """
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

    config.USE_DYNAMIC_SCHEMA = True
    config.DYNAMIC_BASES = {"Processos"}

    proc = SCHEMAS["Processos"]
    keys = set(proc.keys())
    # Slug dinâmico vindo do parser, não a chave legada.
    assert "numero_do_processo" in keys
    spec = proc["numero_do_processo"]
    assert isinstance(spec, PropSpec)
    assert spec.tipo == "title"
    assert spec.notion_name == "Número do processo"


def test_FASE1_schemas_proxy_flag_on_other_base_still_legacy(
    reset_flags, reset_registry,
) -> None:
    """Componente 2: flag on mas base FORA de DYNAMIC_BASES continua no legado."""
    from notion_bulk_edit.schema_registry import init_schema_registry
    conn = _audit_only_conn()
    raw = _load_fixture("Clientes")
    parsed = parse_to_schema_json(raw, "Clientes")
    schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    cache_db.upsert_schema(
        conn, parsed["data_source_id"], "Clientes",
        parsed["title_property"], schema_json,
        compute_schema_hash(parsed), 1700000000.0,
    )
    init_schema_registry(conn)

    config.USE_DYNAMIC_SCHEMA = True
    # Apenas Processos virou dinâmica; Clientes não.
    config.DYNAMIC_BASES = {"Processos"}

    spec_proxy = SCHEMAS["Clientes"]["cnj" if False else "nome"]  # legado tem 'nome'
    spec_legacy = _LEGACY_SCHEMAS["Clientes"]["nome"]
    assert spec_proxy is spec_legacy


def test_FASE1_schemas_proxy_keyerror_for_unknown_base() -> None:
    """Componente 2: SCHEMAS['Inexistente'] levanta KeyError, não retorna proxy vazio."""
    with pytest.raises(KeyError):
        _ = SCHEMAS["Inexistente"]


def test_FASE1_get_prop_routes_through_proxy(reset_flags) -> None:
    """Componente 2: helpers públicos (get_prop) usam o proxy, não o legado direto.

    Smoke: garante que get_prop continua funcionando via Mapping API
    (.get(base, {}).get(key)) com o novo proxy.
    """
    config.USE_DYNAMIC_SCHEMA = False
    spec = get_prop("Processos", "cnj")
    assert spec is not None
    assert spec.tipo == "title"
    assert get_prop("Processos", "inexistente") is None
    assert get_prop("BaseInexistente", "qualquer") is None


# --- Componente 4: boot wiring ---


def test_FASE1_init_schema_registry_called_on_main_window_boot() -> None:
    """Componente 4: app.py importa init_schema_registry no escopo correto.

    Smoke estrutural — garante que a chamada existe na MainWindow.__init__.
    Teste de runtime completo dependeria de PySide6 + mock pesado de
    NotionFacade/SyncManager; deixamos para o validar_fase_0/2a empíricos.
    """
    src = Path(__file__).resolve().parent.parent / "notion_rpadv" / "app.py"
    text = src.read_text(encoding="utf-8")
    assert "init_schema_registry(self._audit_conn)" in text
    assert "boot_refresh_all" in text
    assert "if bulk_config.USE_DYNAMIC_SCHEMA:" in text
