"""Fase 2b — Tarefas no schema dinâmico.

Cobertura:
- Tarefas em DYNAMIC_BASES.
- _TITLE_KEY_BY_BASE["Tarefas"] == "tarefa" (slug do parser; era "titulo").
- SCHEMAS["Tarefas"] retorna do registry com 20 chaves reais.
- Status presente como select com ('Pendente', 'Concluída').
- Em-dash em opções preservado (n/a em Tarefas, mas heurística geral).
- Tripwire: labels legados (A fazer, Em andamento, Aguardando) não
  aparecem em consumers fora do _LEGACY_SCHEMAS.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from notion_bulk_edit.schema_parser import (
    compute_schema_hash,
    parse_to_schema_json,
)
from notion_bulk_edit.schemas import SCHEMAS
from notion_rpadv.cache import db as cache_db
from notion_rpadv.models.base_table_model import _TITLE_KEY_BY_BASE


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "schemas"
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Labels que existiam no STATUS_TAREFA legado mas não estão no Notion real.
# Esses não devem ter consumers em código de produção fora de schemas.py.
_LEGACY_STATUS_TAREFA_LABELS: tuple[str, ...] = (
    "A fazer", "Em andamento", "Aguardando",
)


@pytest.fixture
def reset_registry():
    import notion_bulk_edit.schema_registry as sr
    saved = sr._registry
    yield
    sr._registry = saved


def _load_fixture(label: str) -> dict:
    return json.loads(
        (_FIXTURES_DIR / f"{label.lower()}_raw.json").read_text(encoding="utf-8"),
    )


def _audit_only_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cache_db.init_audit_db(conn)
    return conn


def _populate_tarefas_in_registry() -> sqlite3.Connection:
    from notion_bulk_edit.schema_registry import init_schema_registry
    conn = _audit_only_conn()
    raw = _load_fixture("Tarefas")
    parsed = parse_to_schema_json(raw, "Tarefas")
    schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    cache_db.upsert_schema(
        conn, parsed["data_source_id"], "Tarefas",
        parsed["title_property"], schema_json,
        compute_schema_hash(parsed), 1700000000.0,
    )
    init_schema_registry(conn)
    return conn


# --- Configuração ---


def test_FASE2B_title_key_tarefas_is_tarefa_redundancy() -> None:
    """Sanity: Tarefas migrada para schema dinâmico (Fase 2b).
    Fase 3 removeu DYNAMIC_BASES — todas as 4 bases são dinâmicas agora."""
    # Mantido apenas como documento histórico; teste real do slug está abaixo.
    assert _TITLE_KEY_BY_BASE.get("Tarefas") == "tarefa"


def test_FASE2B_title_key_tarefas_is_tarefa() -> None:
    """Slug dinâmico do título: parser slugifica 'Tarefa' → 'tarefa'."""
    assert _TITLE_KEY_BY_BASE["Tarefas"] == "tarefa"


# --- SCHEMAS via proxy ---


def test_FASE2B_schemas_tarefas_returns_real_keys_from_registry(
    reset_registry,
) -> None:
    """SCHEMAS['Tarefas'] retorna chaves reais — incluindo o novo Status."""
    _populate_tarefas_in_registry()
    tar = SCHEMAS["Tarefas"]
    keys = set(tar.keys())
    expected_core = {
        "tarefa", "status", "descricao", "prazo_fatal",
        "data_de_protocolo", "responsavel", "processo", "tipo_de_tarefa",
        "cliente", "tribunal",
    }
    missing = expected_core - keys
    assert not missing, (
        f"Chaves esperadas ausentes: {missing}. Encontradas: {sorted(keys)}"
    )


def test_FASE2B_status_options_pendente_e_concluida(reset_registry) -> None:
    """Status do Notion real: select com Pendente e Concluída."""
    _populate_tarefas_in_registry()
    spec = SCHEMAS["Tarefas"]["status"]
    assert spec.tipo == "select", f"Status deveria ser select; obtido {spec.tipo}"
    assert "Pendente" in spec.opcoes
    assert "Concluída" in spec.opcoes


def test_FASE2B_legacy_status_labels_not_in_dynamic_options(
    reset_registry,
) -> None:
    """Labels legados (A fazer, Em andamento, Aguardando) NÃO aparecem
    nas opções do registry dinâmico — Notion real só tem 2 valores."""
    _populate_tarefas_in_registry()
    spec = SCHEMAS["Tarefas"]["status"]
    for legacy in _LEGACY_STATUS_TAREFA_LABELS:
        assert legacy not in spec.opcoes, (
            f"Label legado {legacy!r} apareceu nas opções dinâmicas: {spec.opcoes}"
        )


# --- Tripwire: consumers de labels legados ---


def test_FASE2B_tripwire_legacy_status_labels_not_in_consumers() -> None:
    """Tripwire: nenhum arquivo de produção em notion_rpadv/ pode ter
    string literal de label legado de Tarefas Status. Os 4 hits sabidos
    são todos exemplos em docstring (filters.py) e status de sync no
    dashboard ('Pendente' isolado é OK porque é o status do sync, não
    do schema de Tarefas).

    Para evitar flakiness: a heurística olha apenas labels exclusivos do
    legado (A fazer, Em andamento, Aguardando) — 'Pendente' e 'Concluída'
    são o vocabulário real e podem aparecer livremente.
    """
    pattern = re.compile(
        r"""['"](?:""" + "|".join(re.escape(s) for s in _LEGACY_STATUS_TAREFA_LABELS) + r""")['"]"""
    )
    offenders: list[str] = []
    for sub in ("notion_rpadv",):
        root = _REPO_ROOT / sub
        for fp in root.rglob("*.py"):
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for m in pattern.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                offenders.append(f"{fp.relative_to(_REPO_ROOT)}:{line_no} → {m.group(0)}")
    assert offenders == [], (
        "Labels legados de Tarefas Status apareceram em código de produção:\n  "
        + "\n  ".join(offenders)
    )


# --- Outras bases continuam intactas ---


def test_FASE2B_outras_bases_via_registry_quando_populadas(
    reset_registry,
) -> None:
    """Fase 3: todas as 4 bases servem do registry. Quando só Tarefas está
    populada, as outras retornam mapping vazio (sem _LEGACY_SCHEMAS)."""
    _populate_tarefas_in_registry()  # popula só Tarefas
    assert len(SCHEMAS["Catalogo"]) == 0
    assert len(SCHEMAS["Clientes"]) == 0
    assert len(SCHEMAS["Processos"]) == 0
    # Tarefas populada funciona
    assert "tarefa" in SCHEMAS["Tarefas"]
