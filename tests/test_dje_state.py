"""Testes do ``notion_rpadv.services.dje_state`` (refator pós-Fase 3
hotfix watermark integrity, 2026-05-02).

Cursor passou de SINGLETON pra POR ADVOGADO. Cada advogado tem seu
próprio ``ultimo_cursor`` em ``djen_advogado_state``. Testa:
- read/update por advogado, com anti-regressão
- ``read_all_advogados_state`` agrega state de todos
- ``compute_advogado_window`` traduz cursor → janela individual
- ``DEFAULT_CURSOR_VAZIO`` faz a 1ª janela ser ``[2026-01-01, hoje]``
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from notion_rpadv.services import dje_db, dje_state


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "leitor_dje.db"
    c = dje_db.get_connection(db)
    yield c
    c.close()


def _adv(oab: str = "36129", uf: str = "DF", nome: str = "X") -> dict:
    return {"nome": nome, "oab": oab, "uf": uf}


# ---------------------------------------------------------------------------
# Cursor por advogado
# ---------------------------------------------------------------------------


def test_read_advogado_cursor_em_banco_vazio_retorna_none(conn) -> None:
    """Sem nenhuma linha em ``djen_advogado_state`` → None."""
    assert dje_state.read_advogado_cursor(conn, oab="15523", uf="DF") is None


def test_update_advogado_cursor_cria_linha(conn) -> None:
    """Upsert em advogado novo cria a linha."""
    ok = dje_state.update_advogado_cursor(
        conn, oab="36129", uf="DF",
        novo_cursor=date(2026, 4, 30),
        last_run=datetime(2026, 4, 30, 14, 0, 0),
    )
    assert ok is True
    assert (
        dje_state.read_advogado_cursor(conn, oab="36129", uf="DF")
        == date(2026, 4, 30)
    )


def test_update_advogado_cursor_atualiza_linha_existente(conn) -> None:
    """Upsert avança o cursor de um advogado já registrado."""
    dje_state.update_advogado_cursor(
        conn, oab="36129", uf="DF",
        novo_cursor=date(2026, 4, 1),
    )
    ok = dje_state.update_advogado_cursor(
        conn, oab="36129", uf="DF",
        novo_cursor=date(2026, 4, 30),
    )
    assert ok is True
    assert (
        dje_state.read_advogado_cursor(conn, oab="36129", uf="DF")
        == date(2026, 4, 30)
    )


def test_advogado_cursor_nunca_regride(conn, caplog) -> None:
    """Tentar voltar pra data anterior é ignorado (warning, não levanta)."""
    import logging

    dje_state.update_advogado_cursor(
        conn, oab="15523", uf="DF",
        novo_cursor=date(2026, 4, 30),
    )
    with caplog.at_level(logging.WARNING, logger="dje.state"):
        ok = dje_state.update_advogado_cursor(
            conn, oab="15523", uf="DF",
            novo_cursor=date(2026, 4, 1),
        )
    assert ok is False
    assert (
        dje_state.read_advogado_cursor(conn, oab="15523", uf="DF")
        == date(2026, 4, 30)
    )
    assert any("não regride" in r.message for r in caplog.records)


def test_advogados_independentes(conn) -> None:
    """Cursor de um advogado não afeta o outro — chave (oab, uf)."""
    dje_state.update_advogado_cursor(
        conn, oab="15523", uf="DF", novo_cursor=date(2026, 4, 30),
    )
    dje_state.update_advogado_cursor(
        conn, oab="36129", uf="DF", novo_cursor=date(2026, 1, 15),
    )
    assert dje_state.read_advogado_cursor(
        conn, oab="15523", uf="DF",
    ) == date(2026, 4, 30)
    assert dje_state.read_advogado_cursor(
        conn, oab="36129", uf="DF",
    ) == date(2026, 1, 15)


# ---------------------------------------------------------------------------
# read_all_advogados_state
# ---------------------------------------------------------------------------


def test_read_all_advogados_state_agrega(conn) -> None:
    dje_state.update_advogado_cursor(
        conn, oab="15523", uf="DF",
        novo_cursor=date(2026, 4, 30),
        last_run=datetime(2026, 4, 30, 12, 0, 0),
    )
    dje_state.update_advogado_cursor(
        conn, oab="36129", uf="DF",
        novo_cursor=date(2026, 4, 25),
        last_run=datetime(2026, 4, 30, 12, 0, 0),
    )
    state = dje_state.read_all_advogados_state(conn)
    assert len(state) == 2
    assert state[("15523", "DF")]["ultimo_cursor"] == date(2026, 4, 30)
    assert state[("36129", "DF")]["ultimo_cursor"] == date(2026, 4, 25)


# ---------------------------------------------------------------------------
# compute_advogado_window
# ---------------------------------------------------------------------------


def test_compute_advogado_window_cursor_vazio_traz_2026_01_01(conn) -> None:
    """Cursor None → DEFAULT_CURSOR_VAZIO + 1d = 01/01/2026."""
    di, df = dje_state.compute_advogado_window(
        conn, _adv(oab="36129"),
        data_fim=date(2026, 4, 30),
    )
    assert di == date(2026, 1, 1)
    assert df == date(2026, 4, 30)


def test_compute_advogado_window_cursor_existente(conn) -> None:
    """Cursor existente → cursor + 1d."""
    dje_state.update_advogado_cursor(
        conn, oab="36129", uf="DF", novo_cursor=date(2026, 4, 25),
    )
    di, df = dje_state.compute_advogado_window(
        conn, _adv(oab="36129"),
        data_fim=date(2026, 4, 30),
    )
    assert di == date(2026, 4, 26)
    assert df == date(2026, 4, 30)


def test_compute_advogado_window_cursor_no_presente_clamp(conn) -> None:
    """Cursor = data_fim → janela [data_fim, data_fim]."""
    dje_state.update_advogado_cursor(
        conn, oab="36129", uf="DF", novo_cursor=date(2026, 4, 30),
    )
    di, df = dje_state.compute_advogado_window(
        conn, _adv(oab="36129"),
        data_fim=date(2026, 4, 30),
    )
    assert di == date(2026, 4, 30)
    assert df == date(2026, 4, 30)


def test_default_cursor_vazio_constante() -> None:
    """``DEFAULT_CURSOR_VAZIO`` é exatamente 1 dia antes da carga histórica."""
    assert (
        dje_state.DEFAULT_CURSOR_VAZIO + timedelta(days=1)
        == dje_state.DATA_INICIO_HISTORICO_ESCRITORIO
    )
    assert dje_state.DATA_INICIO_HISTORICO_ESCRITORIO == date(2026, 1, 1)


# ---------------------------------------------------------------------------
# Migração legada
# ---------------------------------------------------------------------------


def test_is_legacy_state_present_true_quando_djen_state_populada(
    conn,
) -> None:
    """Banco legado: ``djen_state`` tem 1 linha + ``djen_advogado_state``
    vazia → migration trigger."""
    conn.execute(
        "INSERT INTO djen_state (id, ultimo_cursor, last_run) "
        "VALUES (1, '2026-04-30', '2026-04-30T10:00:00')",
    )
    conn.commit()
    assert dje_db.is_legacy_state_present(conn) is True


def test_is_legacy_state_present_false_quando_advogado_state_populada(
    conn,
) -> None:
    """Migração já rodou: ``djen_advogado_state`` tem linhas → não é legado."""
    conn.execute(
        "INSERT INTO djen_state (id, ultimo_cursor, last_run) "
        "VALUES (1, '2026-04-30', '2026-04-30T10:00:00')",
    )
    dje_state.update_advogado_cursor(
        conn, oab="36129", uf="DF", novo_cursor=date(2026, 4, 30),
    )
    assert dje_db.is_legacy_state_present(conn) is False


def test_clear_legacy_state_zera_djen_state_e_publicacoes(conn) -> None:
    """Reset honesto: drop djen_state + publicacoes."""
    conn.execute(
        "INSERT INTO djen_state (id, ultimo_cursor, last_run) "
        "VALUES (1, '2026-04-30', '2026-04-30T10:00:00')",
    )
    dje_db.insert_publicacao(
        conn, djen_id=1, hash_="h1", oabs_escritorio="X (1/DF)",
        oabs_externas="", numero_processo=None,
        data_disponibilizacao="2026-04-30",
        sigla_tribunal="TRT10", payload={"id": 1}, mode="padrao",
    )
    conn.commit()
    assert dje_db.count_publicacoes(conn) == 1

    dje_db.clear_legacy_state_and_publicacoes(conn)
    assert dje_db.count_publicacoes(conn) == 0
    assert dje_db.is_legacy_state_present(conn) is False


# ---------------------------------------------------------------------------
# Pós-Fase 3 (2026-05-02) — reset_advogado_cursores
# ---------------------------------------------------------------------------


def test_reset_advogado_cursores_zera_cursor_e_last_run(conn) -> None:
    """Após reset, cursor e last_run viram None — próxima execução parte
    de DEFAULT_CURSOR_VAZIO (= 2025-12-31)."""
    dje_state.update_advogado_cursor(
        conn, oab="48468", uf="DF", novo_cursor=date(2026, 5, 2),
    )
    assert dje_state.read_advogado_cursor(
        conn, oab="48468", uf="DF",
    ) == date(2026, 5, 2)
    affected = dje_state.reset_advogado_cursores(conn, [("48468", "DF")])
    assert affected == 1
    assert dje_state.read_advogado_cursor(
        conn, oab="48468", uf="DF",
    ) is None
    assert dje_state.read_advogado_last_run(
        conn, oab="48468", uf="DF",
    ) is None


def test_reset_advogado_cursores_sem_estado_ainda_retorna_zero(conn) -> None:
    """Resetar advogado que nunca teve cursor → rowcount=0 (no-op)."""
    affected = dje_state.reset_advogado_cursores(conn, [("99999", "DF")])
    assert affected == 0


def test_reset_advogado_cursores_so_afeta_oabs_pedidas(conn) -> None:
    """Reset não toca cursores de outros advogados não listados."""
    dje_state.update_advogado_cursor(
        conn, oab="15523", uf="DF", novo_cursor=date(2026, 4, 30),
    )
    dje_state.update_advogado_cursor(
        conn, oab="48468", uf="DF", novo_cursor=date(2026, 5, 2),
    )
    dje_state.reset_advogado_cursores(conn, [("48468", "DF")])
    # Ricardo (15523) intocado:
    assert dje_state.read_advogado_cursor(
        conn, oab="15523", uf="DF",
    ) == date(2026, 4, 30)
    # Vitor (48468) zerado:
    assert dje_state.read_advogado_cursor(
        conn, oab="48468", uf="DF",
    ) is None


def test_reset_advogado_cursores_lista_vazia_retorna_zero(conn) -> None:
    """Lista vazia → no-op (não levanta SQL inválido)."""
    affected = dje_state.reset_advogado_cursores(conn, [])
    assert affected == 0


def test_reset_advogado_cursores_nao_apaga_publicacoes(conn) -> None:
    """Reset SÓ mexe em ``djen_advogado_state`` — publicações capturadas
    permanecem (ON CONFLICT cuida da dedup na próxima execução)."""
    dje_state.update_advogado_cursor(
        conn, oab="48468", uf="DF", novo_cursor=date(2026, 5, 2),
    )
    dje_db.insert_publicacao(
        conn, djen_id=42, hash_="hh",
        oabs_escritorio="Vitor (48468/DF)", oabs_externas="",
        numero_processo=None, data_disponibilizacao="2026-04-15",
        sigla_tribunal="TRT10", payload={"id": 42}, mode="padrao",
    )
    conn.commit()
    n_pre = dje_db.count_publicacoes(conn)
    dje_state.reset_advogado_cursores(conn, [("48468", "DF")])
    assert dje_db.count_publicacoes(conn) == n_pre


# ---------------------------------------------------------------------------
# Pós-revisão Seção B (2026-05-03): ``compute_oldest_cursor_window`` foi
# removida. O eixo CNJ agora usa janela fixa ``[hoje - 15d, hoje]``,
# calculada inline em ``leitor_dje._on_download_cnj_clicked``. Os tests
# desse comportamento vivem em ``test_leitor_dje_page``.
# ---------------------------------------------------------------------------
