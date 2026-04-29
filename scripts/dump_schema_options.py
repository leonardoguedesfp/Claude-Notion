"""Round 3b-2 — dump das opções de select/multi_select de cada base.

Lê audit.db.meta_schemas (cache local do schema dinâmico, populado pelo boot
do app). Imprime, para cada base, todas as propriedades select/multi_select
com seus valores. Usado para cruzar com os mapas decididos pelo Claude
Design e completar colors_overrides.py.

Uso:
    python scripts/dump_schema_options.py

Lê de %APPDATA%/NotionRPADV/audit.db (ou ~/.notionrpadv no Linux/Mac).
Não toca a Notion API — só inspeciona o cache local.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notion_bulk_edit.config import get_cache_dir


def main() -> int:
    audit_path = get_cache_dir() / "audit.db"
    if not audit_path.exists():
        print(f"audit.db não encontrado em {audit_path}", file=sys.stderr)
        print("Rode o app pelo menos uma vez para popular o cache.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(audit_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT base_label, schema_json FROM meta_schemas ORDER BY base_label",
    ).fetchall()
    conn.close()

    if not rows:
        print("meta_schemas vazia — schema_registry ainda não rodou refresh.")
        return 1

    for row in rows:
        base = row["base_label"]
        schema = json.loads(row["schema_json"])
        properties = schema.get("properties", {})

        print(f"\n{'=' * 60}")
        print(f"Base: {base}")
        print(f"{'=' * 60}")

        for slug_key, prop in properties.items():
            tipo = prop.get("tipo", "?")
            if tipo not in ("select", "multi_select", "checkbox"):
                continue

            label = prop.get("label", slug_key)
            print(f"\n  [{tipo:12}] {slug_key} — \"{label}\"")

            opcoes = prop.get("opcoes", [])
            if not opcoes:
                print("    (sem opções)")
                continue
            for opt in opcoes:
                name = opt.get("name", "")
                color = opt.get("color", "default")
                print(f"    - {name!r:40} (cor Notion: {color})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
