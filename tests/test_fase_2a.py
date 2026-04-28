"""Fase 2a — Catálogo no schema dinâmico.

Cobertura:
- Componente 1 (já em test_schemas_proxy.py): flags ON + Catalogo em DYNAMIC_BASES.
- Componente 3: _TITLE_KEY_BY_BASE["Catalogo"] == "nome".
- Componente 4: app.py filtra DATA_SOURCES por DYNAMIC_BASES no boot.
- Componente 5: tripwire — propriedades inventadas (area, tempo_estimado,
  responsavel_padrao, revisado) não vazam para consumers fora do
  _LEGACY_SCHEMAS.
- Componente 6: SCHEMAS["Catalogo"] retorna 5 chaves reais quando registry
  está populado.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from notion_bulk_edit import config
from notion_bulk_edit.schema_parser import (
    compute_schema_hash,
    parse_to_schema_json,
)
from notion_bulk_edit.schemas import SCHEMAS
from notion_rpadv.cache import db as cache_db
from notion_rpadv.models.base_table_model import _TITLE_KEY_BY_BASE


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "schemas"
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Chaves inventadas que aparecem no _LEGACY_SCHEMAS["Catalogo"] mas não existem
# no Notion real. A Fase 2a ativa o registry para Catálogo; estas chaves não
# devem ter consumers fora de schemas.py.
_CATALOGO_INVENTED_KEYS: tuple[str, ...] = (
    "tempo_estimado", "responsavel_padrao", "revisado",
)
# "area" é só sufixo comum demais para grep — ignorado no tripwire.


@pytest.fixture
def reset_registry():
    import notion_bulk_edit.schema_registry as sr
    saved = sr._registry
    yield
    sr._registry = saved


def _load_fixture(label: str) -> dict:
    return json.loads((_FIXTURES_DIR / f"{label.lower()}_raw.json").read_text(encoding="utf-8"))


def _audit_only_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_audit_db(conn)
    return conn


def _populate_catalogo_in_registry() -> sqlite3.Connection:
    """Helper: cria audit conn, popula meta_schemas com fixture do Catálogo,
    e inicializa o registry singleton."""
    from notion_bulk_edit.schema_registry import init_schema_registry
    conn = _audit_only_conn()
    raw = _load_fixture("Catalogo")
    parsed = parse_to_schema_json(raw, "Catalogo")
    schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    cache_db.upsert_schema(
        conn, parsed["data_source_id"], "Catalogo",
        parsed["title_property"], schema_json,
        compute_schema_hash(parsed), 1700000000.0,
    )
    init_schema_registry(conn)
    return conn


# --- Componente 3: _TITLE_KEY_BY_BASE ---


def test_FASE2A_title_key_for_catalogo_is_nome() -> None:
    """Catálogo agora usa o slug 'nome' (parser dinâmico), não 'titulo' (legado)."""
    assert _TITLE_KEY_BY_BASE["Catalogo"] == "nome"


def test_FASE2A_title_key_clientes_unchanged() -> None:
    """Clientes manteve slug 'nome' (já alinhado entre legado e dinâmico).
    Processos virou 'numero_do_processo' na Fase 2d (ver test_FASE2D_*).
    Tarefas virou 'tarefa' na Fase 2b (ver test_FASE2B_*)."""
    assert _TITLE_KEY_BY_BASE["Clientes"] == "nome"


# --- Componente 4: boot wiring (sem filtro DYNAMIC_BASES após Fase 3) ---


def test_FASE2A_app_boot_calls_boot_refresh_all() -> None:
    """app.py chama boot_refresh_all com DATA_SOURCES no boot.

    Fase 3 removeu o filtro DYNAMIC_BASES — todas as 4 bases são dinâmicas
    e refrescam no boot.
    """
    src = (_REPO_ROOT / "notion_rpadv" / "app.py").read_text(encoding="utf-8")
    assert "boot_refresh_all(" in src
    assert "init_schema_registry(self._audit_conn)" in src


# --- Componente 5: tripwire — props inventadas removidas do código ---


def test_FASE2A_invented_keys_absent_from_code() -> None:
    """Tripwire Fase 3: as chaves inventadas que existiam no _LEGACY_SCHEMAS
    do Catálogo (já removido na Fase 3) NÃO devem aparecer em lugar nenhum
    de notion_rpadv/ ou notion_bulk_edit/. Schema dinâmico é fonte única."""
    pattern = re.compile(
        r"""['"](?:""" + "|".join(_CATALOGO_INVENTED_KEYS) + r""")['"]"""
    )
    offenders: list[str] = []
    for sub in ("notion_rpadv", "notion_bulk_edit"):
        root = _REPO_ROOT / sub
        for fp in root.rglob("*.py"):
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for m in pattern.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                offenders.append(f"{fp.relative_to(_REPO_ROOT)}:{line_no} → {m.group(0)}")
    assert offenders == [], (
        "Chaves inventadas do schema legado de Catálogo presentes em código:\n  "
        + "\n  ".join(offenders)
    )


# --- Componente 6: SCHEMAS['Catalogo'] do registry dinâmico ---


def test_FASE2A_schemas_catalogo_returns_real_keys_from_registry(
    reset_registry,
) -> None:
    """SCHEMAS['Catalogo'] (com flag ON + Catálogo em DYNAMIC_BASES + registry
    populado) retorna as 5 chaves reais do Notion, não as inventadas."""
    _populate_catalogo_in_registry()
    cat = SCHEMAS["Catalogo"]
    keys = set(cat.keys())
    expected = {"nome", "categoria", "prazo", "observacoes", "tarefas"}
    assert expected.issubset(keys), (
        f"Faltam chaves reais. Esperado ⊇ {expected}, obtido: {keys}"
    )
    # Chaves inventadas não podem aparecer
    for inventada in ("tempo_estimado", "responsavel_padrao", "revisado"):
        assert inventada not in keys, (
            f"Chave inventada {inventada!r} ainda apareceu via registry: {keys}"
        )


def test_FASE2A_catalogo_categoria_options_match_real_notion(
    reset_registry,
) -> None:
    """As 4 opções reais de Categoria batem (sem inventar nada)."""
    _populate_catalogo_in_registry()
    spec = SCHEMAS["Catalogo"]["categoria"]
    assert spec.tipo == "select"
    expected_options = {
        "Peças processuais", "Outras tarefas jurídicas",
        "Administrativo", "Diversos",
    }
    assert set(spec.opcoes) == expected_options


def test_FASE2A_outras_bases_via_registry_quando_populadas(
    reset_registry,
) -> None:
    """Fase 3: todas as 4 bases servem do registry. Se apenas Catálogo
    estiver populado, as outras retornam mapping vazio em vez de cair
    no _LEGACY_SCHEMAS (que não existe mais)."""
    _populate_catalogo_in_registry()  # popula só Catálogo
    # Outras 3 bases sem registry específico → empty mapping (sem crash)
    assert len(SCHEMAS["Processos"]) == 0
    assert len(SCHEMAS["Tarefas"]) == 0
    assert len(SCHEMAS["Clientes"]) == 0
    # Catálogo populado funciona
    assert "nome" in SCHEMAS["Catalogo"]
