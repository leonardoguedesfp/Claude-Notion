"""Testes do ``notion_rpadv.services.dje_notion_sync`` (Fase 5,
2026-05-03).

Cobre o loop de sincronização DJEN→Notion:
- Sucesso: cria página, persiste page_id, conta como sent.
- Falha 1ª: incrementa attempts, grava last_error, não conta como sent.
- Falha 3ª: publicação fica "presa" (não retentada na próxima execução
  por default).
- Rate-limit: sleep 350ms entre chamadas.
- Cancelamento: para entre publicações.
- NotionAuthError: aborta loop completo (token quebrado).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from notion_bulk_edit.notion_api import (
    NotionAPIError,
    NotionAuthError,
    NotionClient,
    NotionRateLimitError,
)
from notion_rpadv.services import dje_db
from notion_rpadv.services.dje_notion_sync import (
    sincronizar_pendentes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dje_conn(tmp_path: Path):
    db = tmp_path / "leitor_dje.db"
    conn = dje_db.get_connection(db)
    yield conn
    conn.close()


@pytest.fixture
def cache_conn(tmp_path: Path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE records (
            base TEXT, page_id TEXT, data_json TEXT, updated_at REAL,
            PRIMARY KEY (base, page_id)
        )
        """,
    )
    conn.commit()
    yield conn
    conn.close()


def _seed_publicacao(dje_conn, djen_id: int, **overrides) -> None:
    base = {
        "djen_id": djen_id,
        "hash_": f"h-{djen_id}",
        "oabs_escritorio": "Ricardo (15523/DF)",
        "oabs_externas": "",
        "numero_processo": "0000001-00.2025.5.10.0001",
        "data_disponibilizacao": "2026-04-30",
        "sigla_tribunal": "TRT10",
        "payload": {
            "id": djen_id,
            "hash": f"h-{djen_id}",
            "siglaTribunal": "TRT10",
            "data_disponibilizacao": "2026-04-30",
            "destinatarioadvogados": [],
        },
        "mode": "padrao",
    }
    base.update(overrides)
    dje_db.insert_publicacao(dje_conn, **base)


def _client_returning(page_ids: list[str]) -> MagicMock:
    """Mock NotionClient que retorna um page_id em cada call."""
    client = MagicMock(spec=NotionClient)
    client.create_page_in_data_source.side_effect = [
        {"id": pid} for pid in page_ids
    ]
    return client


def _client_raising(exc: Exception, calls: int = 99) -> MagicMock:
    """Mock que levanta a exception nas N chamadas."""
    client = MagicMock(spec=NotionClient)
    client.create_page_in_data_source.side_effect = [exc] * calls
    return client


# ---------------------------------------------------------------------------
# Caso vazio
# ---------------------------------------------------------------------------


def test_sync_sem_pendentes_retorna_zerado(dje_conn, cache_conn) -> None:
    """Banco sem publicações pendentes → outcome zerado, NÃO chama API."""
    client = MagicMock(spec=NotionClient)
    out = sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
    )
    assert out.sent == 0
    assert out.failed == 0
    client.create_page_in_data_source.assert_not_called()


# ---------------------------------------------------------------------------
# Sucesso
# ---------------------------------------------------------------------------


def test_sync_sucesso_persiste_page_id(dje_conn, cache_conn) -> None:
    """Após chamada com sucesso, ``notion_page_id`` é gravado no banco
    e ``sent`` incrementa."""
    _seed_publicacao(dje_conn, 1)
    client = _client_returning(["page-uuid-001"])
    out = sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
    )
    assert out.sent == 1
    assert out.failed == 0
    row = dje_conn.execute(
        "SELECT notion_page_id FROM publicacoes WHERE djen_id=1"
    ).fetchone()
    assert row["notion_page_id"] == "page-uuid-001"


def test_sync_multiplas_pubs_envia_todas(dje_conn, cache_conn) -> None:
    """N publicações pendentes → N chamadas, N page_ids gravados."""
    for i in range(1, 4):
        _seed_publicacao(dje_conn, i)
    client = _client_returning(["uuid-1", "uuid-2", "uuid-3"])
    out = sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
    )
    assert out.sent == 3
    assert client.create_page_in_data_source.call_count == 3


# ---------------------------------------------------------------------------
# Falha
# ---------------------------------------------------------------------------


def test_sync_falha_grava_attempts_e_last_error(dje_conn, cache_conn) -> None:
    """1ª falha incrementa ``notion_attempts`` em 1 e grava
    ``notion_last_error``; pub continua na fila pra próxima execução."""
    _seed_publicacao(dje_conn, 1)
    client = _client_raising(NotionAPIError(500, "internal error"))
    out = sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
    )
    assert out.sent == 0
    assert out.failed == 1
    row = dje_conn.execute(
        "SELECT notion_attempts, notion_last_error, notion_page_id "
        "FROM publicacoes WHERE djen_id=1"
    ).fetchone()
    # Após retry interno do nosso ``_create_page_with_retry``, attempts
    # aumenta em 1 (não 3 — incrementamos uma vez por publicação, não
    # por retry interno).
    assert row["notion_attempts"] == 1
    assert "internal error" in (row["notion_last_error"] or "")
    assert row["notion_page_id"] is None


def test_sync_3_falhas_publicacao_fica_presa(dje_conn, cache_conn) -> None:
    """Após 3 execuções falhadas, publicação fica fora do
    ``fetch_pending_for_notion`` (presa em ``failed``)."""
    _seed_publicacao(dje_conn, 1)
    client = _client_raising(NotionAPIError(500, "boom"))
    # 3 execuções = 3 tentativas (uma por execução).
    for _ in range(3):
        sincronizar_pendentes(
            client=client,
            dje_conn=dje_conn,
            cache_conn=cache_conn,
            sleep_ms=lambda _: None,
            sleep=lambda _: None,
        )
    # Total: attempts == 3, fica presa.
    row = dje_conn.execute(
        "SELECT notion_attempts FROM publicacoes WHERE djen_id=1"
    ).fetchone()
    assert row["notion_attempts"] == 3
    assert dje_db.count_publicacoes_pending_notion(dje_conn) == 0
    assert dje_db.count_publicacoes_failed_notion(dje_conn) == 1


def test_sync_falha_uma_pub_continua_proximas(dje_conn, cache_conn) -> None:
    """Pub 1 falha mas pubs 2 e 3 enviam normalmente — falha não aborta
    o loop."""
    for i in range(1, 4):
        _seed_publicacao(dje_conn, i)
    client = MagicMock(spec=NotionClient)
    client.create_page_in_data_source.side_effect = [
        NotionAPIError(500, "fail"),
        NotionAPIError(500, "fail"),  # retry 1
        NotionAPIError(500, "fail"),  # retry 2 — esgota e levanta
        {"id": "uuid-2"},
        {"id": "uuid-3"},
    ]
    out = sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
    )
    assert out.sent == 2
    assert out.failed == 1


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


def test_sync_aplica_rate_limit_entre_chamadas(dje_conn, cache_conn) -> None:
    """Sleep de 350ms entre chamadas (não antes da 1ª)."""
    for i in range(1, 4):
        _seed_publicacao(dje_conn, i)
    client = _client_returning(["u1", "u2", "u3"])
    sleeps_ms: list[int] = []
    sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda ms: sleeps_ms.append(ms),
        sleep=lambda _: None,
    )
    # 3 publicações → 2 sleeps (entre 1-2 e 2-3).
    assert sleeps_ms == [350, 350]


# ---------------------------------------------------------------------------
# Auth error
# ---------------------------------------------------------------------------


def test_sync_auth_error_aborta_loop(dje_conn, cache_conn) -> None:
    """``NotionAuthError`` numa publicação → para tudo, não tenta o resto."""
    for i in range(1, 4):
        _seed_publicacao(dje_conn, i)
    client = _client_raising(NotionAuthError("Token expirado"))
    out = sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
    )
    # Apenas 1 chamada feita (a 1ª — abortou após auth error).
    assert client.create_page_in_data_source.call_count == 1
    assert out.sent == 0
    assert out.failed == 1


# ---------------------------------------------------------------------------
# Cancelamento
# ---------------------------------------------------------------------------


def test_sync_cancelamento_entre_publicacoes(dje_conn, cache_conn) -> None:
    """``is_cancelled()`` retornando True faz parar entre publicações.
    Items já enviados ficam preservados."""
    for i in range(1, 5):
        _seed_publicacao(dje_conn, i)
    client = _client_returning(["u1", "u2", "u3", "u4"])

    n_calls = {"v": 0}
    def _is_cancelled():
        return n_calls["v"] >= 2

    def _on_progress(idx, total):
        n_calls["v"] = idx

    out = sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
        is_cancelled=_is_cancelled,
        on_progress=_on_progress,
    )
    assert out.cancelled is True
    # Cancelou entre pub 2 e 3 → 2 enviadas.
    assert out.sent == 2
    assert client.create_page_in_data_source.call_count == 2


# ---------------------------------------------------------------------------
# Retry interno em 429
# ---------------------------------------------------------------------------


def test_sync_429_seguido_de_sucesso_no_retry(dje_conn, cache_conn) -> None:
    """1º request retorna 429, 2º retorna sucesso → publicação enviada
    sem contar como falha."""
    _seed_publicacao(dje_conn, 1)
    client = MagicMock(spec=NotionClient)
    client.create_page_in_data_source.side_effect = [
        NotionRateLimitError(429, "rate limit"),
        {"id": "page-recuperada"},
    ]
    out = sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
    )
    assert out.sent == 1
    assert out.failed == 0
    row = dje_conn.execute(
        "SELECT notion_page_id, notion_attempts FROM publicacoes "
        "WHERE djen_id=1"
    ).fetchone()
    assert row["notion_page_id"] == "page-recuperada"
    # attempts permanece 0 (retry interno não conta como falha do
    # ponto de vista do banco).
    assert row["notion_attempts"] == 0


# ---------------------------------------------------------------------------
# Resposta sem page_id é tratada como falha
# ---------------------------------------------------------------------------


def test_sync_resposta_sem_page_id_eh_falha(dje_conn, cache_conn) -> None:
    """Se a API por algum motivo retorna body sem ``id``, conta como
    falha (não persiste page_id vazio)."""
    _seed_publicacao(dje_conn, 1)
    client = MagicMock(spec=NotionClient)
    client.create_page_in_data_source.side_effect = [
        {},  # sem 'id'
        {},  # retry
        {},  # retry final
    ]
    out = sincronizar_pendentes(
        client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        sleep_ms=lambda _: None,
        sleep=lambda _: None,
    )
    assert out.sent == 0
    assert out.failed == 1
