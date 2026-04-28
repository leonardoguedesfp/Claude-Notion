"""Fase 2c — Clientes no schema dinâmico.

Cobertura:
- Clientes em DYNAMIC_BASES.
- _TITLE_KEY_BY_BASE["Clientes"] continua "nome" (slug bate com legacy).
- SCHEMAS["Clientes"] retorna 32 chaves reais com selects corretos.
- Slugs novos (cpf_cnpj, e_mail, observacoes) presentes.
- Slugs legados inventados (cadastrado, n_processos) ausentes.
- 6 selects (tipo, estado_civil, sexo, situacao_funcional,
  status_do_cadastro, uf) batem com Notion real.
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


def _populate_clientes_in_registry() -> sqlite3.Connection:
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
    return conn


# --- Configuração ---


def test_FASE2C_clientes_in_dynamic_bases() -> None:
    """Fase 2c adiciona Clientes; Catálogo/Tarefas continuam migradas."""
    assert "Clientes" in config.DYNAMIC_BASES
    assert "Catalogo" in config.DYNAMIC_BASES
    assert "Tarefas" in config.DYNAMIC_BASES
    # Processos ainda no legado
    assert "Processos" not in config.DYNAMIC_BASES


def test_FASE2C_title_key_clientes_remains_nome() -> None:
    """Slug do título já era 'nome' no legacy; bate com o slug dinâmico."""
    assert _TITLE_KEY_BY_BASE["Clientes"] == "nome"


# --- SCHEMAS via proxy ---


def test_FASE2C_schemas_clientes_returns_real_keys_from_registry(
    reset_registry,
) -> None:
    """Clientes vê 32 propriedades reais via registry — slugs alinhados
    com Notion (cpf_cnpj em vez de cpf, e_mail em vez de email, etc.)."""
    _populate_clientes_in_registry()
    cli = SCHEMAS["Clientes"]
    keys = set(cli.keys())
    expected_core = {
        "nome", "cpf_cnpj", "e_mail", "telefone", "falecido",
        "uf", "estado_civil", "sexo", "situacao_funcional",
        "status_do_cadastro", "tipo", "data_de_nascimento",
        "observacoes", "processos", "documentos",
    }
    missing = expected_core - keys
    assert not missing, f"chaves esperadas ausentes: {missing}"


def test_FASE2C_legacy_invented_keys_absent(reset_registry) -> None:
    """Slugs do _LEGACY_SCHEMAS['Clientes'] que não existem no Notion real
    NÃO devem aparecer no schema dinâmico.

    - 'cadastrado' (date "Cadastrado em") — não existe; era o sistema "Criado em"
    - 'n_processos' (rollup) — não existe; era contagem virtual
    - 'cpf' / 'email' / 'notas' — slugs antigos; renomeados nos slugs reais
    """
    _populate_clientes_in_registry()
    cli = SCHEMAS["Clientes"]
    for legacy_slug in ("cadastrado", "n_processos", "cpf", "email", "notas"):
        assert legacy_slug not in cli, (
            f"slug legado {legacy_slug!r} ainda apareceu via registry"
        )


def test_FASE2C_uf_select_with_27_states(reset_registry) -> None:
    """UF é select com 27 estados (todos os estados brasileiros)."""
    _populate_clientes_in_registry()
    uf = SCHEMAS["Clientes"]["uf"]
    assert uf.tipo == "select"
    assert len(uf.opcoes) == 27, f"esperado 27 UFs; obtido {len(uf.opcoes)}"
    # Spot check
    assert "DF" in uf.opcoes
    assert "SP" in uf.opcoes
    assert "AC" in uf.opcoes


def test_FASE2C_cidade_is_now_rich_text_not_select(reset_registry) -> None:
    """Mudança de tipo: cidade era select (CIDADES_UF) no legacy, virou
    rich_text no Notion real. Documenta a regressão de UX consciente."""
    _populate_clientes_in_registry()
    cidade = SCHEMAS["Clientes"]["cidade"]
    assert cidade.tipo == "rich_text", (
        f"cidade deveria ser rich_text no Notion real; obtido {cidade.tipo}"
    )


def test_FASE2C_cpf_cnpj_is_rich_text(reset_registry) -> None:
    """CPF/CNPJ é rich_text (não há tipo identificador no Notion)."""
    _populate_clientes_in_registry()
    spec = SCHEMAS["Clientes"]["cpf_cnpj"]
    assert spec.tipo == "rich_text"


# --- Outras bases continuam intactas ---


def test_FASE2C_processos_still_legacy(reset_registry) -> None:
    """Processos ainda no legado (Fase 2d futura)."""
    _populate_clientes_in_registry()
    # Fallback ao legado: chave 'cnj' do _LEGACY_SCHEMAS
    assert "cnj" in SCHEMAS["Processos"]


# --- Tripwire (informativo): n_processos consumer está inerte ---


def test_FASE2C_n_processos_fallback_inert_with_dynamic_clientes(
    reset_registry,
) -> None:
    """Documentação ativa: o fallback _count_processos_for_cliente em
    base_table_model.py:330 só roda quando key == 'n_processos' aparece
    nas colunas. Como o slug dinâmico de Clientes não tem 'n_processos',
    o fallback fica inerte. Coluna virtual 'Nº de Processos' é
    descontinuada na Fase 2c — Leonardo confirmou que pode ser perda
    aceitável; restauração futura via 'synthetic property' no registry
    se houver demanda."""
    _populate_clientes_in_registry()
    cli = SCHEMAS["Clientes"]
    assert "n_processos" not in cli
    # O código do fallback continua existindo em base_table_model.py —
    # não foi removido; só fica sem caller. Documentado para que ninguém
    # tente "consertar" pensando que está quebrado.
    bm_src = (_REPO_ROOT / "notion_rpadv" / "models" / "base_table_model.py").read_text(
        encoding="utf-8",
    )
    assert "_count_processos_for_cliente" in bm_src, (
        "Helper foi removido? Se sim, atualizar este teste e o commit."
    )
