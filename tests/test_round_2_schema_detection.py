"""Testes do Round 2 — Tarefa 1: detecção dinâmica de capabilities
do schema da database 📬 Publicações no Notion (2026-05-03).

Cobre:
- ``NotionSchemaCapabilities.from_notion`` em sucesso (propriedade
  presente OU ausente).
- Fallback gracioso em erro de auth, rate limit, API genérica e
  erros inesperados.
- ``raw_property_names`` exposto pra debug.
- Wire no sync: ``sincronizar_pendentes`` faz auto-detect quando
  caller não passa flag explícito; respeita override quando passa.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from notion_bulk_edit.notion_api import (
    NotionAPIError,
    NotionAuthError,
    NotionClient,
    NotionRateLimitError,
)
from notion_rpadv.services import dje_db
from notion_rpadv.services.dje_notion_schema import (
    PROPERTY_DUPLICATAS_SUPRIMIDAS,
    NotionSchemaCapabilities,
)
from notion_rpadv.services.dje_notion_sync import sincronizar_pendentes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dje_conn(tmp_path: Path):
    """SQLite com schema completo (Round 1 migrations aplicadas)."""
    db = tmp_path / "leitor_dje.db"
    conn = dje_db.get_connection(db)
    yield conn
    conn.close()


@pytest.fixture
def cache_conn(tmp_path: Path):
    """Cache vazio."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE records ("
        "base TEXT, page_id TEXT, data_json TEXT, updated_at REAL,"
        "PRIMARY KEY (base, page_id))"
    )
    conn.commit()
    yield conn
    conn.close()


def _client_with_schema(properties: dict) -> MagicMock:
    """Mock NotionClient cujo ``get_data_source`` retorna ``properties``."""
    client = MagicMock(spec=NotionClient)
    client.get_data_source.return_value = {
        "object": "data_source",
        "id": "abc",
        "title": [{"plain_text": "📬 Publicações"}],
        "properties": properties,
    }
    return client


# ---------------------------------------------------------------------------
# Tarefa 1.1 — NotionSchemaCapabilities.from_notion (sucesso)
# ---------------------------------------------------------------------------


def test_R2_caps_detecta_propriedade_existente() -> None:
    """Schema contém 'Duplicatas suprimidas' → flag True."""
    client = _client_with_schema({
        "Identificação": {"type": "title"},
        PROPERTY_DUPLICATAS_SUPRIMIDAS: {"type": "rich_text"},
        "Status": {"type": "select"},
    })
    caps = NotionSchemaCapabilities.from_notion(client, "ds-id")
    assert caps.has_duplicatas_suprimidas is True
    assert PROPERTY_DUPLICATAS_SUPRIMIDAS in caps.raw_property_names
    assert "Status" in caps.raw_property_names
    client.get_data_source.assert_called_once_with("ds-id")


def test_R2_caps_detecta_propriedade_ausente() -> None:
    """Schema sem 'Duplicatas suprimidas' → flag False; raw_names ainda
    populados (debug)."""
    client = _client_with_schema({
        "Identificação": {"type": "title"},
        "Status": {"type": "select"},
        "Tipo de documento": {"type": "select"},
    })
    caps = NotionSchemaCapabilities.from_notion(client, "ds-id")
    assert caps.has_duplicatas_suprimidas is False
    assert PROPERTY_DUPLICATAS_SUPRIMIDAS not in caps.raw_property_names
    assert {"Identificação", "Status", "Tipo de documento"} <= caps.raw_property_names


def test_R2_caps_raw_property_names_e_frozen() -> None:
    """``raw_property_names`` é frozenset (imutável)."""
    client = _client_with_schema({"Status": {"type": "select"}})
    caps = NotionSchemaCapabilities.from_notion(client, "ds-id")
    assert isinstance(caps.raw_property_names, frozenset)


# ---------------------------------------------------------------------------
# Tarefa 1.1 — Fallback em erros
# ---------------------------------------------------------------------------


def test_R2_caps_fallback_em_auth_error(caplog) -> None:
    """NotionAuthError → fallback legacy (False) + warning."""
    client = MagicMock(spec=NotionClient)
    client.get_data_source.side_effect = NotionAuthError(
        "Token inválido ou sem permissão.",
    )
    with caplog.at_level("WARNING", logger="dje.notion.schema"):
        caps = NotionSchemaCapabilities.from_notion(client, "ds-id")
    assert caps.has_duplicatas_suprimidas is False
    assert caps.raw_property_names == frozenset()
    assert any("auth" in rec.message.lower() for rec in caplog.records)


def test_R2_caps_fallback_em_rate_limit(caplog) -> None:
    """NotionRateLimitError → fallback legacy (False) + warning."""
    client = MagicMock(spec=NotionClient)
    client.get_data_source.side_effect = NotionRateLimitError(
        429, "Rate limit atingido após 3 tentativas.",
    )
    with caplog.at_level("WARNING", logger="dje.notion.schema"):
        caps = NotionSchemaCapabilities.from_notion(client, "ds-id")
    assert caps.has_duplicatas_suprimidas is False
    assert any(
        "api" in rec.message.lower() or "fetch" in rec.message.lower()
        for rec in caplog.records
    )


def test_R2_caps_fallback_em_api_error(caplog) -> None:
    """NotionAPIError genérico (500, etc.) → fallback legacy."""
    client = MagicMock(spec=NotionClient)
    client.get_data_source.side_effect = NotionAPIError(500, "internal error")
    with caplog.at_level("WARNING", logger="dje.notion.schema"):
        caps = NotionSchemaCapabilities.from_notion(client, "ds-id")
    assert caps.has_duplicatas_suprimidas is False


def test_R2_caps_fallback_em_excecao_inesperada(caplog) -> None:
    """Exceção não-tipada (network, parse error etc.) também não derruba."""
    client = MagicMock(spec=NotionClient)
    client.get_data_source.side_effect = ValueError("unexpected")
    with caplog.at_level("WARNING", logger="dje.notion.schema"):
        caps = NotionSchemaCapabilities.from_notion(client, "ds-id")
    assert caps.has_duplicatas_suprimidas is False
    assert any("inesperado" in rec.message.lower() for rec in caplog.records)


def test_R2_caps_fallback_em_response_sem_properties() -> None:
    """Response com schema malformado (sem 'properties' dict) → vazio."""
    client = MagicMock(spec=NotionClient)
    client.get_data_source.return_value = {"object": "data_source"}  # sem 'properties'
    caps = NotionSchemaCapabilities.from_notion(client, "ds-id")
    assert caps.has_duplicatas_suprimidas is False
    assert caps.raw_property_names == frozenset()


def test_R2_caps_legacy_fallback_estatico() -> None:
    """``legacy_fallback()`` é o estado-zero estável."""
    caps = NotionSchemaCapabilities.legacy_fallback()
    assert caps.has_duplicatas_suprimidas is False
    assert caps.raw_property_names == frozenset()


# ---------------------------------------------------------------------------
# Tarefa 1.2 — Wire no sync (auto-detect quando flag não passado)
# ---------------------------------------------------------------------------


def test_R2_sync_auto_detect_chama_get_data_source(dje_conn, cache_conn) -> None:
    """Default ``schema_tem_duplicatas_suprimidas=None`` → sync chama
    ``get_data_source`` UMA vez no startup."""
    client = MagicMock(spec=NotionClient)
    client.get_data_source.return_value = {
        "object": "data_source",
        "properties": {PROPERTY_DUPLICATAS_SUPRIMIDAS: {"type": "rich_text"}},
    }
    sincronizar_pendentes(
        client=client, dje_conn=dje_conn, cache_conn=cache_conn,
        sleep_ms=lambda _: None, sleep=lambda _: None,
    )
    # 1 chamada de detecção; sem publicações pendentes → 0 create_page
    client.get_data_source.assert_called_once()


def test_R2_sync_auto_detect_passa_para_flush(dje_conn, cache_conn) -> None:
    """Flag detectado é propagado pro flush. Cenário: 1 canônica + 1
    duplicata → flush é chamado com flag True."""
    client = MagicMock(spec=NotionClient)
    client.get_data_source.return_value = {
        "object": "data_source",
        "properties": {
            "Identificação": {"type": "title"},
            PROPERTY_DUPLICATAS_SUPRIMIDAS: {"type": "rich_text"},
        },
    }
    client.create_page_in_data_source.return_value = {"id": "page-canon"}
    client.update_page.return_value = {"id": "page-canon"}

    cnj = "0001234-56.2024.5.10.0001"
    payload_a = {
        "id": 100, "hash": "h-100", "siglaTribunal": "TRT10",
        "data_disponibilizacao": "2026-02-10",
        "numeroprocessocommascara": cnj,
        "tipoDocumento": "Acórdão", "tipoComunicacao": "Intimação",
        "texto": "Texto.", "destinatarios": [],
        "destinatarioadvogados": [],
    }
    dje_db.insert_publicacao(
        dje_conn, djen_id=100, hash_="h-100",
        oabs_escritorio="", oabs_externas="",
        numero_processo=cnj, data_disponibilizacao="2026-02-10",
        sigla_tribunal="TRT10", payload=payload_a,
        mode=dje_db.CAPTURE_MODE_PADRAO,
    )
    payload_b = {**payload_a, "id": 101, "hash": "h-101"}
    dje_db.insert_publicacao(
        dje_conn, djen_id=101, hash_="h-101",
        oabs_escritorio="", oabs_externas="",
        numero_processo=cnj, data_disponibilizacao="2026-02-10",
        sigla_tribunal="TRT10", payload=payload_b,
        mode=dje_db.CAPTURE_MODE_PADRAO,
    )

    sincronizar_pendentes(
        client=client, dje_conn=dje_conn, cache_conn=cache_conn,
        sleep_ms=lambda _: None, sleep=lambda _: None,
    )

    # Update_page foi chamado e o payload incluiu "Duplicatas suprimidas"
    # (porque schema_caps detectou a propriedade)
    assert client.update_page.call_count == 1
    args, _ = client.update_page.call_args
    props_atualizadas = args[1]
    assert PROPERTY_DUPLICATAS_SUPRIMIDAS in props_atualizadas


def test_R2_sync_caller_pode_forcar_false_skip_detect(
    dje_conn, cache_conn,
) -> None:
    """Caller que passa ``False`` explícito → NÃO faz fetch (poupa 1 call)."""
    client = MagicMock(spec=NotionClient)
    sincronizar_pendentes(
        client=client, dje_conn=dje_conn, cache_conn=cache_conn,
        sleep_ms=lambda _: None, sleep=lambda _: None,
        schema_tem_duplicatas_suprimidas=False,
    )
    # Caller forçou False → sem detect.
    client.get_data_source.assert_not_called()


def test_R2_sync_caller_pode_forcar_true_skip_detect(
    dje_conn, cache_conn,
) -> None:
    """Caller que passa ``True`` explícito → NÃO faz fetch."""
    client = MagicMock(spec=NotionClient)
    sincronizar_pendentes(
        client=client, dje_conn=dje_conn, cache_conn=cache_conn,
        sleep_ms=lambda _: None, sleep=lambda _: None,
        schema_tem_duplicatas_suprimidas=True,
    )
    client.get_data_source.assert_not_called()


def test_R2_sync_caller_passa_schema_caps_skip_detect(
    dje_conn, cache_conn,
) -> None:
    """Caller que passa ``schema_caps`` pré-detectado → NÃO faz fetch
    no sync (escolha pra app que detecta uma vez no startup)."""
    client = MagicMock(spec=NotionClient)
    caps = NotionSchemaCapabilities(
        has_duplicatas_suprimidas=True,
        raw_property_names=frozenset({PROPERTY_DUPLICATAS_SUPRIMIDAS}),
    )
    sincronizar_pendentes(
        client=client, dje_conn=dje_conn, cache_conn=cache_conn,
        sleep_ms=lambda _: None, sleep=lambda _: None,
        schema_caps=caps,
    )
    client.get_data_source.assert_not_called()


def test_R2_sync_auto_detect_falha_de_api_nao_derruba(
    dje_conn, cache_conn, caplog,
) -> None:
    """Se detecção falha (ex: 500), sync NÃO crasha — degrada pra
    legacy (flag=False) e segue normal."""
    client = MagicMock(spec=NotionClient)
    client.get_data_source.side_effect = NotionAPIError(500, "boom")
    with caplog.at_level("WARNING"):
        out = sincronizar_pendentes(
            client=client, dje_conn=dje_conn, cache_conn=cache_conn,
            sleep_ms=lambda _: None, sleep=lambda _: None,
        )
    # Sync segue (sem pendentes → 0 sent / 0 failed).
    assert out.sent == 0
    assert out.failed == 0
    # Warning sobre fallback foi logado.
    assert any(
        "legacy" in rec.message.lower() or "api" in rec.message.lower()
        for rec in caplog.records
    )


def test_R2_smoke_real_notion_has_duplicatas_suprimidas() -> None:
    """Smoke contra o Notion real: a propriedade 'Duplicatas suprimidas'
    foi criada manualmente entre Round 1 e Round 2.

    Skip se o token Notion não estiver no keyring (CI ou outra máquina).
    Skip também se a chamada falhar — o foco é confirmar a detecção
    positiva quando há credenciais válidas.
    """
    try:
        from notion_rpadv.auth.token_store import get_token
    except ImportError:
        pytest.skip("notion_rpadv.auth.token_store indisponível")

    try:
        token = get_token()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Token Notion não disponível: {exc}")

    if not token:
        pytest.skip("Token Notion vazio (keyring sem credencial configurada)")

    from notion_rpadv.services.dje_notion_constants import (
        NOTION_PUBLICACOES_DATA_SOURCE_ID,
    )
    client = NotionClient(token)
    caps = NotionSchemaCapabilities.from_notion(
        client, NOTION_PUBLICACOES_DATA_SOURCE_ID,
    )

    # Se detecção devolveu vazio mesmo com token, é offline ou outro erro
    # transitório — skip pra não falhar CI/outras máquinas.
    if not caps.raw_property_names:
        pytest.skip(
            "Detecção devolveu vazio — provavelmente offline, auth falhou "
            "ou data source ID divergente",
        )
    assert caps.has_duplicatas_suprimidas is True, (
        f"Esperado a propriedade {PROPERTY_DUPLICATAS_SUPRIMIDAS!r} estar "
        f"criada no Notion (Round 2 pré-requisito). Propriedades atuais: "
        f"{sorted(caps.raw_property_names)}"
    )
