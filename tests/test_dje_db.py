"""Fase 3 — testes do ``notion_rpadv.services.dje_db``.

Cases F3-01..F3-06 do spec: schema, pragmas, INSERT OR IGNORE, UNIQUE
constraint, índices em uso.

Usa SQLite em arquivo temporário (não ``:memory:``) pra que os pragmas
WAL e os índices sejam efetivamente exercitados — ``:memory:`` ignora
WAL silenciosamente.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from notion_rpadv.services import dje_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Arquivo SQLite temporário com nome canônico."""
    return tmp_path / "leitor_dje.db"


def _payload(djen_id: int = 100, **overrides) -> dict:
    """Payload mínimo de uma publicação (sem chaves derivadas)."""
    base = {
        "id": djen_id,
        "hash": f"hash{djen_id:04d}",
        "siglaTribunal": "TRT10",
        "data_disponibilizacao": "2026-04-30",
        "numero_processo": "00012345620265100003",
        "tipoComunicacao": "Intimação",
        "destinatarioadvogados": [],
    }
    base.update(overrides)
    return base


def _insert_kwargs(djen_id: int = 100, **overrides) -> dict:
    """Kwargs minimalistas pra ``insert_publicacao``."""
    base = {
        "djen_id": djen_id,
        "hash_": f"hash{djen_id:04d}",
        "oabs_escritorio": "Ricardo (15523/DF); Leonardo (36129/DF)",
        "oabs_externas": "",
        "numero_processo": "00012345620265100003",
        "data_disponibilizacao": "2026-04-30",
        "sigla_tribunal": "TRT10",
        "payload": _payload(djen_id),
        "mode": dje_db.CAPTURE_MODE_PADRAO,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# F3-01..F3-06: Schema, pragmas, índices
# ---------------------------------------------------------------------------


def test_F3_01_init_em_dir_vazio_cria_tabelas_e_pragmas(
    db_path: Path,
) -> None:
    """F3-01: init em diretório vazio cria as 2 tabelas + pragmas."""
    assert not db_path.exists()
    conn = dje_db.get_connection(db_path)
    try:
        # Tabelas existentes
        tables = {
            row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )
        }
        assert "djen_state" in tables
        assert "publicacoes" in tables
        # Pragmas
        assert (
            conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
            == "wal"
        )
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        # synchronous=NORMAL = código 1
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
    finally:
        conn.close()
    assert db_path.exists()


def test_F3_02_init_em_banco_existente_nao_derruba_dados(
    db_path: Path,
) -> None:
    """F3-02: init no banco já existente é idempotente — preserva dados."""
    conn1 = dje_db.get_connection(db_path)
    try:
        dje_db.insert_publicacao(conn1, **_insert_kwargs(djen_id=42))
        conn1.commit()
    finally:
        conn1.close()

    # Reabre via get_connection — deve invocar init_db de novo, idempotente.
    conn2 = dje_db.get_connection(db_path)
    try:
        n = dje_db.count_publicacoes(conn2)
        assert n == 1
        rows = dje_db.fetch_all_publicacoes(conn2)
        assert rows[0]["id"] == 42
    finally:
        conn2.close()


def test_F3_03_djen_state_so_aceita_uma_linha(db_path: Path) -> None:
    """F3-03: tentar inserir 2 linhas em djen_state levanta CHECK."""
    conn = dje_db.get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO djen_state (id, ultimo_cursor, last_run) "
            "VALUES (1, '2026-04-30', '2026-04-30T10:00:00')",
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO djen_state (id, ultimo_cursor, last_run) "
                "VALUES (2, '2026-05-01', '2026-05-01T10:00:00')",
            )
    finally:
        conn.close()


def test_F3_04_insert_or_ignore_djen_id_duplicado_retorna_false(
    db_path: Path,
) -> None:
    """F3-04: INSERT OR IGNORE em djen_id duplicado não levanta;
    retorna False (rowcount=0)."""
    conn = dje_db.get_connection(db_path)
    try:
        first = dje_db.insert_publicacao(conn, **_insert_kwargs(djen_id=99))
        second = dje_db.insert_publicacao(conn, **_insert_kwargs(djen_id=99))
        conn.commit()
        assert first is True
        assert second is False
        assert dje_db.count_publicacoes(conn) == 1
    finally:
        conn.close()


def test_F3_05_hash_duplicado_com_djen_id_diferente_levanta(
    db_path: Path,
) -> None:
    """F3-05: INSERT OR IGNORE só ignora conflito na PK (djen_id).
    Hash UNIQUE colide com djen_id distinto → IntegrityError."""
    conn = dje_db.get_connection(db_path)
    try:
        ok = dje_db.insert_publicacao(
            conn,
            **_insert_kwargs(djen_id=10, hash_="HASH-XYZ"),
        )
        assert ok is True
        # djen_id diferente, mesmo hash → conflito UNIQUE no hash
        with pytest.raises(sqlite3.IntegrityError):
            dje_db.insert_publicacao(
                conn,
                **_insert_kwargs(djen_id=11, hash_="HASH-XYZ"),
            )
    finally:
        conn.close()


def test_F3_06_indice_data_eh_usado_em_query_range(db_path: Path) -> None:
    """F3-06: SELECT por data_disponibilizacao usa o índice criado.

    EXPLAIN QUERY PLAN deve mencionar idx_pub_data ou ``USING INDEX``.
    """
    conn = dje_db.get_connection(db_path)
    try:
        # Insere algumas linhas pra o planner ter razões pra usar index.
        for i in range(5):
            dje_db.insert_publicacao(
                conn,
                **_insert_kwargs(
                    djen_id=200 + i,
                    data_disponibilizacao=f"2026-04-{20 + i:02d}",
                ),
            )
        conn.commit()
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM publicacoes "
            "WHERE data_disponibilizacao BETWEEN ? AND ?",
            ("2026-04-20", "2026-04-25"),
        ).fetchall()
        plan_text = " ".join(str(row["detail"]) for row in plan).lower()
        assert "idx_pub_data" in plan_text or "using index" in plan_text
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers extras: fetch_all e fetch_by_ids respeitam ordem
# ---------------------------------------------------------------------------


def test_fetch_all_publicacoes_ordena_data_desc_tribunal_asc(
    db_path: Path,
) -> None:
    """fetch_all retorna por data DESC, depois sigla ASC."""
    conn = dje_db.get_connection(db_path)
    try:
        dje_db.insert_publicacao(
            conn,
            **_insert_kwargs(
                djen_id=1, data_disponibilizacao="2026-04-29",
                sigla_tribunal="TRT10",
            ),
        )
        dje_db.insert_publicacao(
            conn,
            **_insert_kwargs(
                djen_id=2, data_disponibilizacao="2026-04-30",
                sigla_tribunal="TRT15",
            ),
        )
        dje_db.insert_publicacao(
            conn,
            **_insert_kwargs(
                djen_id=3, data_disponibilizacao="2026-04-30",
                sigla_tribunal="TRT01",
            ),
        )
        conn.commit()
        rows = dje_db.fetch_all_publicacoes(conn)
        assert [r["id"] for r in rows] == [3, 2, 1]
    finally:
        conn.close()


def test_fetch_publicacoes_by_ids_subset_correto(db_path: Path) -> None:
    """fetch_by_ids retorna só os ids pedidos, com payload mesclado."""
    conn = dje_db.get_connection(db_path)
    try:
        for i in (1, 2, 3):
            dje_db.insert_publicacao(conn, **_insert_kwargs(djen_id=i))
        conn.commit()
        subset = dje_db.fetch_publicacoes_by_ids(conn, [1, 3])
        ids = {r["id"] for r in subset}
        assert ids == {1, 3}
        # Cada subset row tem as 2 colunas derivadas
        for r in subset:
            assert "advogados_consultados_escritorio" in r
            assert "oabs_externas_consultadas" in r
    finally:
        conn.close()


def test_insert_mode_invalido_levanta(db_path: Path) -> None:
    """Mode fora de 'padrao'/'manual' → ValueError antes do SQL."""
    conn = dje_db.get_connection(db_path)
    try:
        with pytest.raises(ValueError, match="mode inválido"):
            dje_db.insert_publicacao(
                conn, **_insert_kwargs(djen_id=1, mode="invalid"),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pós-Fase 3 (2026-05-02) — app_flags one-shot
# ---------------------------------------------------------------------------


def test_app_flags_read_inexistente_retorna_none(db_path: Path) -> None:
    """``read_flag`` em chave inexistente retorna ``None`` (não levanta)."""
    conn = dje_db.get_connection(db_path)
    try:
        assert dje_db.read_flag(conn, "chave_que_nao_existe") is None
    finally:
        conn.close()


def test_app_flags_set_e_read_persiste(db_path: Path) -> None:
    """``set_flag`` insere; ``read_flag`` recupera o valor exato."""
    conn = dje_db.get_connection(db_path)
    try:
        dje_db.set_flag(conn, "minha_flag", "yes")
        assert dje_db.read_flag(conn, "minha_flag") == "yes"
    finally:
        conn.close()


def test_app_flags_set_atualiza_valor_existente(db_path: Path) -> None:
    """``set_flag`` 2× na mesma chave faz upsert (não duplica linha)."""
    conn = dje_db.get_connection(db_path)
    try:
        dje_db.set_flag(conn, "k", "v1")
        dje_db.set_flag(conn, "k", "v2")
        assert dje_db.read_flag(conn, "k") == "v2"
        # Sanity: 1 row só na tabela.
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM app_flags WHERE key='k'"
        ).fetchone()["n"]
        assert n == 1
    finally:
        conn.close()


def test_app_flags_persistem_entre_conexoes(db_path: Path) -> None:
    """Flag persiste em disco — outra conexão lê o mesmo valor."""
    conn1 = dje_db.get_connection(db_path)
    try:
        dje_db.set_flag(
            conn1, dje_db.FLAG_REATIVACAO_2026_05_02, "treated",
        )
    finally:
        conn1.close()
    conn2 = dje_db.get_connection(db_path)
    try:
        assert dje_db.read_flag(
            conn2, dje_db.FLAG_REATIVACAO_2026_05_02,
        ) == "treated"
    finally:
        conn2.close()


# ---------------------------------------------------------------------------
# Fase 5 (2026-05-03) — Notion sync columns + helpers
# ---------------------------------------------------------------------------


def test_F5_init_cria_colunas_notion(db_path: Path) -> None:
    """Banco novo (init from scratch) já vem com as 3 colunas Notion."""
    conn = dje_db.get_connection(db_path)
    try:
        cols = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(publicacoes)"
            ).fetchall()
        }
        assert "notion_page_id" in cols
        assert "notion_attempts" in cols
        assert "notion_last_error" in cols
    finally:
        conn.close()


def test_F5_migration_idempotente_em_banco_pre_fase_5(db_path: Path) -> None:
    """Banco antigo (sem as 3 colunas Notion): ALTER TABLE adiciona;
    chamar de novo é no-op (idempotente)."""
    # Cria banco "antigo" com schema sem as colunas Notion.
    legacy_conn = sqlite3.connect(str(db_path))
    legacy_conn.execute(
        """
        CREATE TABLE publicacoes (
            djen_id INTEGER PRIMARY KEY,
            hash TEXT UNIQUE NOT NULL,
            oabs_escritorio TEXT NOT NULL,
            oabs_externas TEXT,
            numero_processo TEXT,
            data_disponibilizacao TEXT NOT NULL,
            sigla_tribunal TEXT,
            payload_json TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            captured_in_mode TEXT NOT NULL CHECK (
                captured_in_mode IN ('padrao', 'manual')
            )
        )
        """,
    )
    legacy_conn.commit()
    legacy_conn.close()

    # 1ª abertura via get_connection: migração roda.
    conn = dje_db.get_connection(db_path)
    try:
        cols = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(publicacoes)"
            ).fetchall()
        }
        assert "notion_page_id" in cols
        assert "notion_attempts" in cols
        assert "notion_last_error" in cols
        # Default value de attempts é 0.
        dje_db.insert_publicacao(conn, **_insert_kwargs(djen_id=1))
        row = conn.execute(
            "SELECT notion_page_id, notion_attempts, notion_last_error "
            "FROM publicacoes WHERE djen_id = 1"
        ).fetchone()
        assert row["notion_page_id"] is None
        assert row["notion_attempts"] == 0
        assert row["notion_last_error"] is None
    finally:
        conn.close()

    # 2ª abertura: idempotente — não levanta nem duplica.
    conn2 = dje_db.get_connection(db_path)
    conn2.close()


def test_F5_count_pending_inicialmente_igual_total(db_path: Path) -> None:
    """Inserções novas vão pra notion_page_id=NULL → contam como pendentes."""
    conn = dje_db.get_connection(db_path)
    try:
        for i in range(1, 4):
            dje_db.insert_publicacao(conn, **_insert_kwargs(djen_id=i))
        assert dje_db.count_publicacoes_pending_notion(conn) == 3
        assert dje_db.count_publicacoes_sent_to_notion(conn) == 0
    finally:
        conn.close()


def test_F5_mark_sent_atualiza_page_id_e_decrementa_pending(
    db_path: Path,
) -> None:
    """``mark_publicacao_sent_to_notion`` move uma pub de pendente pra
    enviada."""
    conn = dje_db.get_connection(db_path)
    try:
        dje_db.insert_publicacao(conn, **_insert_kwargs(djen_id=1))
        assert dje_db.count_publicacoes_pending_notion(conn) == 1
        dje_db.mark_publicacao_sent_to_notion(conn, 1, "page-uuid-001")
        assert dje_db.count_publicacoes_pending_notion(conn) == 0
        assert dje_db.count_publicacoes_sent_to_notion(conn) == 1
        row = conn.execute(
            "SELECT notion_page_id FROM publicacoes WHERE djen_id=1"
        ).fetchone()
        assert row["notion_page_id"] == "page-uuid-001"
    finally:
        conn.close()


def test_F5_mark_failure_incrementa_attempts_e_grava_erro(
    db_path: Path,
) -> None:
    """``mark_publicacao_notion_failure`` incrementa attempts +1 e
    grava ``notion_last_error``. Após 3 falhas, deixa de ser elegível
    pra ``fetch_pending_for_notion``."""
    conn = dje_db.get_connection(db_path)
    try:
        dje_db.insert_publicacao(conn, **_insert_kwargs(djen_id=1))
        # 1ª falha
        dje_db.mark_publicacao_notion_failure(conn, 1, "HTTP 500: oops")
        row = conn.execute(
            "SELECT notion_attempts, notion_last_error FROM publicacoes "
            "WHERE djen_id=1"
        ).fetchone()
        assert row["notion_attempts"] == 1
        assert "500" in row["notion_last_error"]
        assert dje_db.count_publicacoes_pending_notion(conn) == 1
        # 2ª e 3ª falhas
        dje_db.mark_publicacao_notion_failure(conn, 1, "HTTP 502")
        dje_db.mark_publicacao_notion_failure(conn, 1, "HTTP 503")
        # Após 3 falhas: NÃO está em pending, ESTÁ em failed.
        assert dje_db.count_publicacoes_pending_notion(conn) == 0
        assert dje_db.count_publicacoes_failed_notion(conn) == 1
        # ``fetch_pending_for_notion`` (default) NÃO retorna a presa.
        assert dje_db.fetch_pending_for_notion(conn) == []
        # Mas ``include_failed=True`` retorna.
        assert len(
            dje_db.fetch_pending_for_notion(conn, include_failed=True)
        ) == 1
    finally:
        conn.close()


def test_F5_mark_all_pending_skipped_aplica_sentinela(db_path: Path) -> None:
    """``mark_all_pending_notion_skipped`` marca pendentes (NULL) com
    SKIPPED — ramo "Só novas a partir de hoje" do modal."""
    conn = dje_db.get_connection(db_path)
    try:
        for i in range(1, 4):
            dje_db.insert_publicacao(conn, **_insert_kwargs(djen_id=i))
        # Marca uma como já enviada — não deve ser tocada.
        dje_db.mark_publicacao_sent_to_notion(conn, 2, "page-real-uuid")
        affected = dje_db.mark_all_pending_notion_skipped(conn)
        assert affected == 2  # só pubs 1 e 3
        # A pub 2 (já enviada) não foi tocada.
        row2 = conn.execute(
            "SELECT notion_page_id FROM publicacoes WHERE djen_id=2"
        ).fetchone()
        assert row2["notion_page_id"] == "page-real-uuid"
        # As outras 2 viraram SKIPPED.
        for djen_id in (1, 3):
            row = conn.execute(
                "SELECT notion_page_id FROM publicacoes WHERE djen_id=?",
                (djen_id,),
            ).fetchone()
            assert row["notion_page_id"] == dje_db.NOTION_SKIPPED_SENTINEL
    finally:
        conn.close()


def test_F5_reset_failed_attempts_volta_pra_fila(db_path: Path) -> None:
    """``reset_notion_failed_attempts`` zera attempts das publicações
    presas em 3+, voltando elas pra ``fetch_pending_for_notion``."""
    conn = dje_db.get_connection(db_path)
    try:
        dje_db.insert_publicacao(conn, **_insert_kwargs(djen_id=1))
        # Força 3 falhas.
        for err in ("E1", "E2", "E3"):
            dje_db.mark_publicacao_notion_failure(conn, 1, err)
        assert dje_db.count_publicacoes_failed_notion(conn) == 1
        affected = dje_db.reset_notion_failed_attempts(conn)
        assert affected == 1
        assert dje_db.count_publicacoes_failed_notion(conn) == 0
        assert dje_db.count_publicacoes_pending_notion(conn) == 1
        # ``notion_last_error`` também foi limpo.
        row = conn.execute(
            "SELECT notion_attempts, notion_last_error FROM publicacoes "
            "WHERE djen_id=1"
        ).fetchone()
        assert row["notion_attempts"] == 0
        assert row["notion_last_error"] is None
    finally:
        conn.close()


def test_F5_count_sequencial_titulo(db_path: Path) -> None:
    """``count_sequencial_titulo`` calcula N+1 contando pubs já enviadas
    com mesma combinação tribunal+data."""
    conn = dje_db.get_connection(db_path)
    try:
        # 3 pubs no mesmo dia/tribunal; 1 já enviada, 1 SKIPPED, 1 pendente.
        for i in (1, 2, 3):
            dje_db.insert_publicacao(
                conn, **_insert_kwargs(
                    djen_id=i, sigla_tribunal="TRT10",
                    data_disponibilizacao="2026-04-30",
                ),
            )
        # Inicialmente: 0 enviadas → próxima = 1
        assert dje_db.count_sequencial_titulo(
            conn, "TRT10", "2026-04-30",
        ) == 1
        # 1 enviada → próxima = 2
        dje_db.mark_publicacao_sent_to_notion(conn, 1, "page-1")
        assert dje_db.count_sequencial_titulo(
            conn, "TRT10", "2026-04-30",
        ) == 2
        # SKIPPED não conta
        conn.execute(
            "UPDATE publicacoes SET notion_page_id=? WHERE djen_id=2",
            (dje_db.NOTION_SKIPPED_SENTINEL,),
        )
        conn.commit()
        assert dje_db.count_sequencial_titulo(
            conn, "TRT10", "2026-04-30",
        ) == 2
        # Combinação diferente: 0 enviadas
        assert dje_db.count_sequencial_titulo(
            conn, "STJ", "2026-04-30",
        ) == 1
    finally:
        conn.close()


def test_F5_fetch_pending_ordem_por_data_e_id(db_path: Path) -> None:
    """``fetch_pending_for_notion`` retorna pendentes em ordem
    cronológica (data ASC, djen_id ASC)."""
    conn = dje_db.get_connection(db_path)
    try:
        # Insere fora de ordem: djen_id=3 com data antiga, 1 com data nova.
        dje_db.insert_publicacao(
            conn, **_insert_kwargs(
                djen_id=3, data_disponibilizacao="2026-04-15",
            ),
        )
        dje_db.insert_publicacao(
            conn, **_insert_kwargs(
                djen_id=1, data_disponibilizacao="2026-04-30",
            ),
        )
        dje_db.insert_publicacao(
            conn, **_insert_kwargs(
                djen_id=2, data_disponibilizacao="2026-04-15",
            ),
        )
        pendentes = dje_db.fetch_pending_for_notion(conn)
        ids = [p["id"] for p in pendentes]
        # Primeiro 04-15: djen_id 2 e 3 (ordem por id ASC); depois 04-30: djen_id 1.
        assert ids == [2, 3, 1]
    finally:
        conn.close()


def test_F5_flag_notion_primeira_carga_constante_existe() -> None:
    """``FLAG_NOTION_PRIMEIRA_CARGA`` é uma string canônica usada como
    chave em ``app_flags``."""
    assert dje_db.FLAG_NOTION_PRIMEIRA_CARGA == "notion_primeira_carga_v1"
    assert dje_db.NOTION_SKIPPED_SENTINEL == "SKIPPED"
