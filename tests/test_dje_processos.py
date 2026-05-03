"""Testes do ``notion_rpadv.services.dje_processos`` (eixo CNJ — pós-Fase 3,
2026-05-02).

Origem dos CNJs: cache local da base "Processos" do Notion (
``notion_rpadv.cache.db.get_all_records(conn, 'Processos')``). O serviço
extrai/normaliza/dedup/ordena os CNJs e retorna pra UI/worker do eixo CNJ.

Testa em fixture com SQLite em memória populada com records mock; não
mexe em rede ou na API real do Notion.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Fixture: cache em memória com schema mínimo de records
# ---------------------------------------------------------------------------


def _seed_records(records: list[dict[str, Any]]) -> sqlite3.Connection:
    """Cria conexão in-memory + schema mínimo de records + insere."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE records (
            base TEXT NOT NULL,
            page_id TEXT NOT NULL,
            data_json TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (base, page_id)
        )
        """,
    )
    for i, rec in enumerate(records):
        conn.execute(
            "INSERT INTO records (base, page_id, data_json, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("Processos", f"page-{i}", json.dumps(rec), float(i)),
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_listar_cnjs_retorna_lista_vazia_quando_cache_vazio() -> None:
    """Cache sem nenhum record → lista vazia (caller avisa o user)."""
    from notion_rpadv.services.dje_processos import listar_cnjs_do_escritorio
    conn = _seed_records([])
    try:
        assert listar_cnjs_do_escritorio(conn) == []
    finally:
        conn.close()


def test_listar_cnjs_extrai_numero_do_processo_decodificado() -> None:
    """Cache com 2 records válidos → 2 CNJs ordenados."""
    from notion_rpadv.services.dje_processos import listar_cnjs_do_escritorio
    records = [
        {"numero_do_processo": "0123456-78.2024.1.23.4567"},
        {"numero_do_processo": "0001234-56.2025.5.10.0001"},
    ]
    conn = _seed_records(records)
    try:
        cnjs = listar_cnjs_do_escritorio(conn)
        assert cnjs == [
            "0001234-56.2025.5.10.0001",
            "0123456-78.2024.1.23.4567",
        ]
    finally:
        conn.close()


def test_listar_cnjs_dedup_mesma_numeracao() -> None:
    """Records com mesma ``numero_do_processo`` são colapsados em 1 CNJ."""
    from notion_rpadv.services.dje_processos import listar_cnjs_do_escritorio
    records = [
        {"numero_do_processo": "0123456-78.2024.1.23.4567"},
        {"numero_do_processo": "0123456-78.2024.1.23.4567"},  # dup
        {"numero_do_processo": "0123456-78.2024.1.23.4567"},  # dup
    ]
    conn = _seed_records(records)
    try:
        assert listar_cnjs_do_escritorio(conn) == [
            "0123456-78.2024.1.23.4567",
        ]
    finally:
        conn.close()


def test_listar_cnjs_normaliza_20_digitos_puros_em_mascara() -> None:
    """CNJ digitado sem máscara (20 dígitos) é normalizado pra forma
    canônica com máscara."""
    from notion_rpadv.services.dje_processos import listar_cnjs_do_escritorio
    records = [
        {"numero_do_processo": "01234567820241234567"},  # 20 dígitos puros
    ]
    conn = _seed_records(records)
    try:
        cnjs = listar_cnjs_do_escritorio(conn)
        assert cnjs == ["0123456-78.2024.1.23.4567"]
    finally:
        conn.close()


def test_listar_cnjs_descarta_pre_cnj_e_strings_invalidas() -> None:
    """Numeração pré-CNJ (sem 20 dígitos completos) ou strings fora de
    padrão são silenciosamente descartadas."""
    from notion_rpadv.services.dje_processos import listar_cnjs_do_escritorio
    records = [
        {"numero_do_processo": "0123456-78.2024.1.23.4567"},  # válido
        {"numero_do_processo": "abc123 numeração antiga"},     # inválido
        {"numero_do_processo": "12345"},                        # curto demais
        {"numero_do_processo": ""},                              # vazio
        {"numero_do_processo": None},                            # None
    ]
    conn = _seed_records(records)
    try:
        cnjs = listar_cnjs_do_escritorio(conn)
        assert cnjs == ["0123456-78.2024.1.23.4567"]
    finally:
        conn.close()


def test_listar_cnjs_record_sem_chave_numero_do_processo() -> None:
    """Record sem ``numero_do_processo`` (defesa contra schema variante)
    é descartado silenciosamente."""
    from notion_rpadv.services.dje_processos import listar_cnjs_do_escritorio
    records = [
        {"nome": "Cliente X", "outra_coisa": 42},  # sem numero_do_processo
        {"numero_do_processo": "0123456-78.2024.1.23.4567"},
    ]
    conn = _seed_records(records)
    try:
        cnjs = listar_cnjs_do_escritorio(conn)
        assert cnjs == ["0123456-78.2024.1.23.4567"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helper interno _normaliza_cnj — sanity checks isolados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0123456-78.2024.1.23.4567", "0123456-78.2024.1.23.4567"),  # já mascarado
        ("01234567820241234567", "0123456-78.2024.1.23.4567"),         # 20 dígitos puros
        ("0123456-78.2024.1.23.4567 ", "0123456-78.2024.1.23.4567"),  # whitespace trim
        ("", None),
        ("abc", None),
        ("123", None),
        ("12345678901234567890123", None),  # > 20 dígitos
    ],
)
def test_normaliza_cnj_casos_extremos(raw, expected) -> None:
    from notion_rpadv.services.dje_processos import _normaliza_cnj
    assert _normaliza_cnj(raw) == expected
