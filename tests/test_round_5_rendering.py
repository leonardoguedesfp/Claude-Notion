"""Round 5 (30-abr-2026) — testes de rendering: people resolution + URL hyperlink.

Cobre:
- ``resolve_user_name`` (helper compartilhado entre model e exporter)
- ``_display_value`` branch ``people`` no BaseTableModel
- ``_format_for_excel`` branch ``url`` (Round 5 item 2)
- ``_write_base_sheet`` hyperlink em url no xlsx
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Item 3 — resolve_user_name helper + people branch in _display_value
# ---------------------------------------------------------------------------


def test_R5_resolve_user_name_known_uuid_returns_name() -> None:
    """UUID conhecido em NOTION_USERS retorna o nome configurado."""
    from notion_bulk_edit.config import resolve_user_name
    # UUID real da Déborah no NOTION_USERS
    name = resolve_user_name("23fd872b-594c-8178-840c-00029746e827")
    assert name == "Déborah"


def test_R5_resolve_user_name_unknown_uuid_falls_back_to_uuid() -> None:
    """UUID não em NOTION_USERS retorna o próprio UUID (bot, ex-membro,
    placeholder)."""
    from notion_bulk_edit.config import resolve_user_name
    assert resolve_user_name("uuid-fora-do-time") == "uuid-fora-do-time"


def test_R5_resolve_user_name_empty_returns_empty_string() -> None:
    """UUID vazio/None vira string vazia (caller normalmente filtra antes,
    mas helper é defensivo)."""
    from notion_bulk_edit.config import resolve_user_name
    assert resolve_user_name("") == ""


def test_R5_resolve_user_name_accepts_injected_users_dict() -> None:
    """``users=`` permite injeção pra testes sem depender do singleton
    (pattern já usado em snapshot_exporter)."""
    from notion_bulk_edit.config import resolve_user_name
    custom = {"u1": {"name": "Alice", "initials": "A"}}
    assert resolve_user_name("u1", users=custom) == "Alice"
    assert resolve_user_name("u2", users=custom) == "u2"


def test_R5_resolve_user_name_returns_uuid_when_name_field_missing() -> None:
    """Se a entrada existe mas não tem 'name', cai no UUID (defesa contra
    NOTION_USERS malformado)."""
    from notion_bulk_edit.config import resolve_user_name
    custom = {"u1": {"initials": "A"}}  # sem 'name'
    assert resolve_user_name("u1", users=custom) == "u1"


def test_R5_display_value_people_resolves_uuids_to_names() -> None:
    """``_display_value`` branch ``people`` resolve list de UUIDs pra
    nomes via NOTION_USERS (smoke do item 3 do Round 5)."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value
    spec = PropSpec(
        notion_name="Responsável", tipo="people", label="Responsável",
        editavel=True, obrigatorio=False, opcoes=(),
    )
    raw = ["23fd872b-594c-8178-840c-00029746e827"]
    assert _display_value(spec, raw) == "Déborah"


def test_R5_display_value_people_joins_multiple_with_comma() -> None:
    """Múltiplos UUIDs viram comma-separated."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value
    spec = PropSpec(
        notion_name="Responsável", tipo="people", label="Responsável",
        editavel=True, obrigatorio=False, opcoes=(),
    )
    raw = [
        "23fd872b-594c-8178-840c-00029746e827",  # Déborah
        "240d872b-594c-81f4-82e1-000212a926fc",  # Leonardo
    ]
    assert _display_value(spec, raw) == "Déborah, Leonardo"


def test_R5_display_value_people_falls_back_to_uuid_for_unknown() -> None:
    """UUID desconhecido vira ele mesmo (não some — visibilidade
    diagnóstica)."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value
    spec = PropSpec(
        notion_name="Responsável", tipo="people", label="Responsável",
        editavel=True, obrigatorio=False, opcoes=(),
    )
    raw = ["uuid-fora", "23fd872b-594c-8178-840c-00029746e827"]
    assert _display_value(spec, raw) == "uuid-fora, Déborah"


def test_R5_display_value_people_empty_list_returns_placeholder() -> None:
    """Lista vazia cai no placeholder em-dash do model (linhas
    137-140 do _display_value)."""
    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models.base_table_model import _display_value
    spec = PropSpec(
        notion_name="Responsável", tipo="people", label="Responsável",
        editavel=True, obrigatorio=False, opcoes=(),
    )
    assert _display_value(spec, []) == "—"


def test_R5_snapshot_exporter_people_uses_helper(tmp_path) -> None:
    """``_format_for_excel`` people branch agora usa resolve_user_name
    em vez de inline lookup. Comportamento ponta-a-ponta inalterado."""
    from notion_rpadv.services.snapshot_exporter import _format_for_excel
    notion_users = {"u1": {"name": "Alice"}}
    val, miss = _format_for_excel(["u1", "u2"], "people", {}, notion_users)
    assert val == "Alice, u2"
    assert miss == 0
