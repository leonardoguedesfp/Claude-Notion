"""Fase 3 — cleanup do _LEGACY_SCHEMAS e flags: validação programática.

Confirma que:
1. Flags USE_DYNAMIC_SCHEMA e DYNAMIC_BASES foram removidas de config.
2. _LEGACY_SCHEMAS, vocabulários hardcoded e mapas de cor foram removidos
   de schemas.py.
3. Defensive helpers (_LEGACY_TITLE_KEYS_BY_BASE, _title_value_for_record)
   foram removidos de base_table_model.py.
4. As 4 bases continuam acessíveis via SCHEMAS proxy.
5. cor_por_valor populado em runtime via notion_colors.

Uso:
    python scripts/validar_fase_3.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> int:
    print()
    print("=== VALIDACAO FASE 3 ===")
    print()

    # 1. Flags removidas de config
    from notion_bulk_edit import config
    assert not hasattr(config, "USE_DYNAMIC_SCHEMA"), (
        "flag USE_DYNAMIC_SCHEMA não foi removida"
    )
    assert not hasattr(config, "DYNAMIC_BASES"), (
        "DYNAMIC_BASES não foi removido"
    )
    print("flags USE_DYNAMIC_SCHEMA + DYNAMIC_BASES: removidas")

    # 2. _LEGACY_SCHEMAS e amigos removidos de schemas
    import notion_bulk_edit.schemas as schemas_mod
    legacy_attrs = (
        "_LEGACY_SCHEMAS",
        "TRIBUNAIS", "FASES", "STATUS_PROC", "INSTANCIAS",
        "PRIORIDADES", "STATUS_TAREFA", "CATEGORIAS_CATALOGO",
        "AREAS_CATALOGO", "CIDADES_UF",
        "_COR_TRIBUNAL", "_COR_FASE", "_COR_STATUS_PROC",
        "_COR_INSTANCIA", "_COR_PRIORIDADE", "_COR_STATUS_TAREFA",
        "_COR_CATEGORIA", "_COR_AREA",
    )
    for attr in legacy_attrs:
        assert not hasattr(schemas_mod, attr), (
            f"atributo legado {attr!r} ainda em schemas.py"
        )
    print(f"_LEGACY_SCHEMAS + {len(legacy_attrs) - 1} símbolos legados: removidos")

    # 3. Defensive helpers removidos de base_table_model
    from notion_rpadv.models import base_table_model as bt
    assert not hasattr(bt, "_LEGACY_TITLE_KEYS_BY_BASE"), (
        "_LEGACY_TITLE_KEYS_BY_BASE não foi removido"
    )
    assert not hasattr(bt, "_title_value_for_record"), (
        "_title_value_for_record não foi removido"
    )
    print("defensive helpers (_LEGACY_TITLE_KEYS_BY_BASE, "
          "_title_value_for_record): removidos")

    # 4. SCHEMAS proxy ainda expõe as 4 bases canônicas
    from notion_bulk_edit.schemas import SCHEMAS
    assert set(SCHEMAS) == {"Processos", "Clientes", "Tarefas", "Catalogo"}
    print(f"SCHEMAS bases: {sorted(SCHEMAS)}")

    # 5. cor_por_valor populado via notion_colors quando registry inicializado
    import json
    import sqlite3
    import tempfile
    from notion_bulk_edit.schema_parser import (
        compute_schema_hash, parse_to_schema_json,
    )
    from notion_bulk_edit.schema_registry import init_schema_registry
    from notion_rpadv.cache.db import init_audit_db, upsert_schema

    fixture = _PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "processos_raw.json"
    with tempfile.TemporaryDirectory(prefix="rpadv_fase3_") as tmp:
        db_path = Path(tmp) / "audit_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_audit_db(conn)

        raw = json.loads(fixture.read_text(encoding="utf-8"))
        parsed = parse_to_schema_json(raw, "Processos")
        upsert_schema(
            conn, parsed["data_source_id"], "Processos",
            parsed["title_property"],
            json.dumps(parsed, sort_keys=True, ensure_ascii=False),
            compute_schema_hash(parsed), 1700000000.0,
        )

        import notion_bulk_edit.schema_registry as sr
        saved = sr._registry
        try:
            init_schema_registry(conn)
            tribunal = SCHEMAS["Processos"]["tribunal"]
            assert tribunal.cor_por_valor, (
                "cor_por_valor vazio — esperado populado via notion_colors"
            )
            n_cores = len(tribunal.cor_por_valor)
            sample = list(tribunal.cor_por_valor.items())[:3]
            print(f"tribunal.cor_por_valor: {n_cores} entries; "
                  f"sample = {sample}")
            for hex_color in tribunal.cor_por_valor.values():
                assert hex_color.startswith("#"), (
                    f"cor não é hex: {hex_color!r}"
                )

            # 6. target_base resolvido via DATA_SOURCES (relation lookup)
            clientes_rel = SCHEMAS["Processos"]["clientes"]
            assert clientes_rel.tipo == "relation"
            assert clientes_rel.target_base == "Clientes", (
                f"target_base esperado 'Clientes'; obtido "
                f"{clientes_rel.target_base!r}"
            )
            print(f"clientes.target_base = {clientes_rel.target_base!r}")
        finally:
            sr._registry = saved
            conn.close()

    print()
    print("OK: Fase 3 validada — cleanup completo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
