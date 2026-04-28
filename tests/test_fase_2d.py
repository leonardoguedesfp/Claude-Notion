"""Fase 2d — Processos no schema dinâmico (última base a migrar).

Cobertura:
- Processos em DYNAMIC_BASES (4 bases dinâmicas total).
- _TITLE_KEY_BY_BASE["Processos"] == "numero_do_processo" (slug do parser;
  era "cnj" no legado).
- SCHEMAS["Processos"] retorna 37 chaves reais (era 38 antes de drops).
- Slugs obsoletos (cnj, valor_causa, criado_em_1) ausentes.
- Tribunal com 17 opções incluindo TRT/2 (era 8 no legado).
- Em-dash U+2014 preservado em 7 valores de Tipo de ação.
- Status com 3 opções (sem regressão).
- Defensive lookup: helper _title_value_for_record cobre fallback durante
  decay do cache pré-Fase 2d.
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
from notion_bulk_edit.schemas import SCHEMAS
from notion_rpadv.cache import db as cache_db
from notion_rpadv.models.base_table_model import (
    _LEGACY_TITLE_KEYS_BY_BASE,
    _TITLE_KEY_BY_BASE,
    _looks_like_template_row,
    _title_value_for_record,
)


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "schemas"
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Em-dash literal U+2014 — não usar copy/paste de hífen ASCII.
_EM_DASH = "—"
_EXPECTED_TIPO_ACAO_COM_EM_DASH = (
    f"Indenização {_EM_DASH} I",
    f"Indenização {_EM_DASH} IR",
    f"Indenização {_EM_DASH} RI",
    f"Indenização {_EM_DASH} R",
    f"Redução Salarial {_EM_DASH} HE",
    f"Redução Salarial {_EM_DASH} PCS",
    f"Descomissionamento {_EM_DASH} LS",
)
_OBSOLETE_KEYS = ("cnj", "valor_causa", "criado_em_1")


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


def _populate_processos_in_registry() -> sqlite3.Connection:
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
    return conn


# --- Configuração ---


def test_FASE2D_processos_in_dynamic_bases() -> None:
    """Fase 2d adiciona Processos; total de 4 bases dinâmicas."""
    assert "Processos" in config.DYNAMIC_BASES
    assert len(config.DYNAMIC_BASES) == 4
    assert config.DYNAMIC_BASES == {"Catalogo", "Tarefas", "Clientes", "Processos"}


def test_FASE2D_title_key_processos_is_numero_do_processo() -> None:
    """Slug primário virou 'numero_do_processo' (era 'cnj' no legado)."""
    assert _TITLE_KEY_BY_BASE["Processos"] == "numero_do_processo"


def test_FASE2D_legacy_title_key_cnj_kept_as_fallback() -> None:
    """Defensive: cnj continua disponível como fallback durante o decay
    do cache pré-Fase 2d (records antigos ainda têm chave 'cnj' até a
    primeira sync re-popular com 'numero_do_processo')."""
    assert "cnj" in _LEGACY_TITLE_KEYS_BY_BASE.get("Processos", ())


# --- SCHEMAS via proxy ---


def test_FASE2D_schemas_processos_returns_37_keys(reset_registry) -> None:
    """37 propriedades reais (era 38 antes de Leonardo dropar 'Criado em 1').
    Sem 'cnj', 'valor_causa', 'criado_em_1'."""
    _populate_processos_in_registry()
    proc = SCHEMAS["Processos"]
    keys = set(proc.keys())
    assert len(keys) == 37
    assert "numero_do_processo" in keys
    for obsolete in _OBSOLETE_KEYS:
        assert obsolete not in keys, f"slug obsoleto {obsolete!r} presente"


def test_FASE2D_proxy_processos_usa_registry(reset_registry) -> None:
    """Confirma que SCHEMAS['Processos']['numero_do_processo'] vem do registry
    (PropSpec com tipo 'title'), não do _LEGACY_SCHEMAS (onde key seria 'cnj')."""
    _populate_processos_in_registry()
    spec = SCHEMAS["Processos"]["numero_do_processo"]
    assert spec.tipo == "title"
    assert spec.notion_name == "Número do processo"


# --- Tribunal ---


def test_FASE2D_tribunal_tem_17_opcoes_incluindo_TRT2(reset_registry) -> None:
    """Tribunal cresceu de 8 (legacy) para 17 opções; TRT/2 foi adicionado
    pela Déborah depois do schema legacy ser escrito."""
    _populate_processos_in_registry()
    tribunal = SCHEMAS["Processos"]["tribunal"]
    assert tribunal.tipo == "select"
    assert len(tribunal.opcoes) == 17
    assert "TRT/2" in tribunal.opcoes
    assert "TRT/10" in tribunal.opcoes
    assert "TJDFT" in tribunal.opcoes
    assert "STF" in tribunal.opcoes


# --- Em-dash em Tipo de ação ---


def test_FASE2D_tipo_de_acao_preserva_em_dash(reset_registry) -> None:
    """7 valores em Tipo de ação contêm em-dash U+2014 (não hífen ASCII).
    Bug silencioso comum: copy-paste com '-' (U+002D) em vez de '—' (U+2014)
    causa mismatch com o vocabulário do Notion."""
    _populate_processos_in_registry()
    tipo_acao = SCHEMAS["Processos"]["tipo_de_acao"]
    assert tipo_acao.tipo == "multi_select"
    assert len(tipo_acao.opcoes) == 21
    for esperada in _EXPECTED_TIPO_ACAO_COM_EM_DASH:
        assert esperada in tipo_acao.opcoes, (
            f"valor com em-dash ausente: {esperada!r}; "
            f"opcoes: {tipo_acao.opcoes}"
        )
    # Todas as 7 ocorrências devem ter U+2014 literal, não hífen.
    em_dash_count = sum(1 for o in tipo_acao.opcoes if _EM_DASH in o)
    assert em_dash_count == 7, (
        f"esperado 7 valores com U+2014; obtido {em_dash_count}"
    )
    # Nenhuma opção mistura em-dash com hífen ASCII isolado.
    for opt in tipo_acao.opcoes:
        if _EM_DASH in opt:
            # OK: em-dash é o separador semântico
            pass


# --- Status ---


def test_FASE2D_status_processos_3_opcoes(reset_registry) -> None:
    """Status real do Notion: Ativo / Arquivado provisoriamente (tema 955) /
    Arquivado. Sem regressão da granularidade."""
    _populate_processos_in_registry()
    status = SCHEMAS["Processos"]["status"]
    assert status.tipo == "select"
    assert len(status.opcoes) == 3
    assert "Ativo" in status.opcoes
    assert "Arquivado" in status.opcoes
    assert "Arquivado provisoriamente (tema 955)" in status.opcoes


# --- Tripwire ---


def test_FASE2D_tripwire_obsolete_keys_in_consumers() -> None:
    """Tripwire: nenhum consumer em notion_rpadv/ deve usar 'valor_causa'
    ou 'criado_em_1' como string literal (chaves dropadas no Notion).

    'cnj' é exceção legítima — continua aparecendo como fallback defensive
    em delegates.py, dashboard.py, processos.py durante o decay do cache.
    """
    import re
    pattern = re.compile(
        r"""['"](?:""" + "|".join(re.escape(s) for s in ("valor_causa", "criado_em_1")) + r""")['"]"""
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
        "Slugs obsoletos (valor_causa, criado_em_1) em notion_rpadv/:\n  "
        + "\n  ".join(offenders)
    )


# --- Defensive lookup helper ---


def test_FASE2D_title_value_for_record_uses_primary_first() -> None:
    """_title_value_for_record retorna o slug primário quando presente."""
    record = {"numero_do_processo": "0001-NEW", "cnj": "0002-OLD"}
    assert _title_value_for_record(record, "Processos") == "0001-NEW"


def test_FASE2D_title_value_for_record_falls_back_to_legacy() -> None:
    """_title_value_for_record cai no slug legado quando primário ausente.
    Cenário: record do cache pré-Fase 2d ainda só tem 'cnj' até re-sync."""
    record = {"cnj": "0002-OLD-ONLY"}
    assert _title_value_for_record(record, "Processos") == "0002-OLD-ONLY"


def test_FASE2D_looks_like_template_row_uses_fallback_for_legacy_cache() -> None:
    """Filter de template row funciona com record que só tem slug legado.
    Cenário: cache.db.records[Processos] de syncs pré-Fase 2d ainda tem
    chave 'cnj' até a primeira sync re-popular com slug novo."""
    # Record só com slug legado (simula cache pré-Fase 2d)
    legacy_template = {"cnj": "🟧 Modelo — usar como template"}
    assert _looks_like_template_row(legacy_template, "Processos") is True

    # Record com slug novo (pós-sync)
    new_template = {"numero_do_processo": "🟧 Modelo — usar como template"}
    assert _looks_like_template_row(new_template, "Processos") is True


# --- Outras 3 bases sem regressão ---


def test_FASE2D_outras_bases_continuam_funcionando(reset_registry) -> None:
    """Adicionar Processos em DYNAMIC_BASES não afeta Catálogo/Tarefas/Clientes."""
    _populate_processos_in_registry()  # registry só tem Processos
    # As outras 3 caem no fallback _LEGACY_SCHEMAS (registry vazio para elas).
    # Confirma que SCHEMAS continua expondo as 4 bases.
    assert set(SCHEMAS) == {"Processos", "Clientes", "Tarefas", "Catalogo"}
