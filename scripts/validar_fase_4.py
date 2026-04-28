"""Fase 4 — picker de colunas + persistência por usuário: validação programática.

Roda end-to-end contra um audit.db em memória populado com a fixture de
``Processos``:

1. ``cache_db.get/set/clear_user_columns`` — CRUD básico em ``meta_user_columns``.
2. ``schema_registry.colunas_visiveis(base)`` — sem user_id retorna só
   ``default_visible=True`` ordenado.
3. ``schema_registry.colunas_visiveis(base, user_id=...)`` — com user_id e
   prefs salvas, retorna a lista do usuário na ordem armazenada.
4. ``schemas.colunas_visiveis(base, user_id=...)`` — helper público delega
   ao registry.
5. Drift protection — slugs órfãos da lista do usuário são filtrados.
6. ``clear_user_columns`` → fallback ao default.

Uso:
    python scripts/validar_fase_4.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> int:
    print()
    print("=== VALIDACAO FASE 4 ===")
    print()

    from notion_bulk_edit.schema_parser import (
        compute_schema_hash,
        parse_to_schema_json,
    )
    from notion_bulk_edit.schemas import colunas_visiveis as schemas_cv
    from notion_rpadv.cache import db as cache_db

    fixture = _PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "processos_raw.json"
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    parsed = parse_to_schema_json(raw, "Processos")
    dsid = parsed["data_source_id"]

    with tempfile.TemporaryDirectory(prefix="rpadv_fase4_") as tmp:
        db_path = Path(tmp) / "audit_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cache_db.init_audit_db(conn)
        cache_db.upsert_schema(
            conn, dsid, "Processos",
            parsed["title_property"],
            json.dumps(parsed, sort_keys=True, ensure_ascii=False),
            compute_schema_hash(parsed), 1700000000.0,
        )

        # 1. Helpers básicos: get/set/clear
        assert cache_db.get_user_columns(conn, "leonardo", dsid) is None, (
            "get_user_columns sem entrada deveria retornar None"
        )
        print("1) get_user_columns sem entrada -> None: OK")

        cache_db.set_user_columns(
            conn, "leonardo", dsid, ["numero_do_processo", "tribunal", "status"],
        )
        got = cache_db.get_user_columns(conn, "leonardo", dsid)
        assert got == ["numero_do_processo", "tribunal", "status"], (
            f"set/get roundtrip falhou: {got!r}"
        )
        print(f"2) set/get roundtrip: {got}")

        # Upsert
        cache_db.set_user_columns(
            conn, "leonardo", dsid, ["numero_do_processo", "fase"],
        )
        got2 = cache_db.get_user_columns(conn, "leonardo", dsid)
        assert got2 == ["numero_do_processo", "fase"], (
            f"upsert deveria ter substituído: {got2!r}"
        )
        print(f"3) set upsert sobrescreve: {got2}")

        # Isolamento per-user
        cache_db.set_user_columns(
            conn, "deborah", dsid, ["numero_do_processo", "tribunal"],
        )
        leo = cache_db.get_user_columns(conn, "leonardo", dsid)
        deb = cache_db.get_user_columns(conn, "deborah", dsid)
        assert leo == ["numero_do_processo", "fase"]
        assert deb == ["numero_do_processo", "tribunal"]
        print(f"4) per-user isolation: leo={leo}; deb={deb}")

        # 2. Registry: sem user_id → default
        # Inicializa o singleton apenas neste bloco — restaura ao final.
        import notion_bulk_edit.schema_registry as sr
        saved = sr._registry
        try:
            sr.init_schema_registry(conn)
            reg = sr.get_schema_registry()

            default = reg.colunas_visiveis("Processos")
            assert default and default[0] == "numero_do_processo", (
                f"default deveria começar pelo título: {default!r}"
            )
            # System properties não devem aparecer
            assert "criado_em" not in default
            assert "atualizado_em" not in default
            print(
                f"5) registry default ({len(default)} cols): "
                f"sem system properties, title em primeiro",
            )

            # 3. Registry: com user_id → prefs do usuário
            user_cols = reg.colunas_visiveis("Processos", user_id="leonardo")
            assert user_cols == ["numero_do_processo", "fase"], (
                f"prefs do leonardo: {user_cols!r}"
            )
            print(f"6) registry com user_id='leonardo': {user_cols}")

            # 4. Helper público delega ao registry
            via_helper = schemas_cv("Processos", user_id="leonardo")
            assert via_helper == user_cols, (
                f"helper público divergente: {via_helper!r} vs registry "
                f"{user_cols!r}"
            )
            print(f"7) schemas.colunas_visiveis delega ao registry: OK")

            # 5. Drift protection
            cache_db.set_user_columns(
                conn, "leonardo", dsid,
                ["numero_do_processo", "slug_inexistente", "tribunal"],
            )
            after_drift = reg.colunas_visiveis(
                "Processos", user_id="leonardo",
            )
            assert "slug_inexistente" not in after_drift
            assert after_drift == ["numero_do_processo", "tribunal"], (
                f"drift protection falhou: {after_drift!r}"
            )
            print(f"8) drift protection (slug órfão filtrado): {after_drift}")

            # 6. Clear → fallback ao default
            cache_db.clear_user_columns(conn, "leonardo", dsid)
            assert cache_db.get_user_columns(conn, "leonardo", dsid) is None
            after_clear = reg.colunas_visiveis(
                "Processos", user_id="leonardo",
            )
            assert after_clear == default, (
                "após clear, deveria voltar ao default"
            )
            print(f"9) clear -> fallback ao default ({len(after_clear)} cols)")
        finally:
            sr._registry = saved
            conn.close()

    print()
    print("OK: Fase 4 validada — picker de colunas + persistência por usuário.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
