"""Pytest conftest — fixtures globais.

Fase 3: o registry dinâmico é a única fonte de schemas (sem
``_LEGACY_SCHEMAS`` como fallback). Para testes unitários funcionarem
sem cada um precisar inicializar o singleton, esta fixture autouse
popula o registry com as 4 fixtures committadas em
``tests/fixtures/schemas/`` antes de cada teste.

Implicações:
- Testes que precisam do schema dinâmico para rodar (acessar SCHEMAS,
  get_prop, colunas_visiveis) funcionam direto.
- Testes que precisam de um registry vazio (validar fallback "{}")
  podem zerar com ``import notion_bulk_edit.schema_registry as sr;
  sr._registry = None`` no início do teste.
- Custo: 4 chamadas a parse_to_schema_json + upsert + load por teste.
  Mais de 200 testes × ~3ms = ~600ms total. Aceitável.
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
from notion_rpadv.cache import db as cache_db


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "schemas"
_BASES_AND_DSIDS: list[tuple[str, str]] = [
    ("Catalogo",  "79afc833-77e2-4574-98ba-ebed7bd7e66c"),
    ("Processos", "5e93b734-4043-4c89-a513-5e00a14081bb"),
    ("Clientes",  "939e5dcf-51bd-4ffa-a28e-0313899fd229"),
    ("Tarefas",   "3a8bb311-5c1b-42ac-a3b2-859b75911e91"),
]


@pytest.fixture(autouse=True)
def _populate_schema_registry_with_fixtures():
    """Popula o singleton do SchemaRegistry com fixtures reais antes
    de cada teste. Substitui qualquer estado anterior do singleton.

    Após o teste, restaura o singleton ao estado pré-fixture (não
    necessariamente None — outros testes podem ter populado de outra
    forma; a invariante é que cada teste começa do mesmo ponto).
    """
    from notion_bulk_edit.schema_registry import init_schema_registry
    import notion_bulk_edit.schema_registry as sr

    saved = sr._registry

    # Setup: cria audit conn em memória e popula com as 4 fixtures
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_audit_db(conn)
    for label, dsid in _BASES_AND_DSIDS:
        fixture_path = _FIXTURES_DIR / f"{label.lower()}_raw.json"
        if not fixture_path.exists():
            continue
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        # Sobrescreve o ID se necessário (fixtures têm o real)
        parsed = parse_to_schema_json(raw, label)
        cache_db.upsert_schema(
            conn,
            data_source_id=parsed.get("data_source_id") or dsid,
            base_label=label,
            title_property=parsed.get("title_property"),
            schema_json=json.dumps(parsed, sort_keys=True, ensure_ascii=False),
            schema_hash=compute_schema_hash(parsed),
            fetched_at=1700000000.0,
        )
    init_schema_registry(conn)

    yield

    # Teardown: restaura singleton ao estado anterior
    sr._registry = saved
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass
