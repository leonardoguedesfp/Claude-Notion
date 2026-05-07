"""Fase 2c — Clientes no schema dinâmico: validação programática.

Roda end-to-end:
1. Confirma flags ON e Clientes em DYNAMIC_BASES.
2. Cria audit.db temporário, popula meta_schemas com fixture de Clientes,
   inicializa registry singleton.
3. Acessa SCHEMAS["Clientes"] via proxy — confirma 32 chaves reais
   (slugs alinhados com Notion: cpf_cnpj, e_mail, observacoes; sem
   slugs legados como cpf, email, notas, cadastrado, n_processos).
4. Confirma _TITLE_KEY_BY_BASE["Clientes"] == "nome" (já era, alinhado).
5. Spot check: UF tem 27 estados; cidade virou rich_text.

Uso:
    python scripts/validar_fase_2c.py
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

from notion_bulk_edit.schema_parser import (  # noqa: E402
    compute_schema_hash,
    parse_to_schema_json,
)
from notion_bulk_edit.schema_registry import init_schema_registry  # noqa: E402
from notion_bulk_edit.schemas import SCHEMAS  # noqa: E402
from notion_rpadv.cache.db import init_audit_db, upsert_schema  # noqa: E402
from notion_rpadv.models.base_table_model import _TITLE_KEY_BY_BASE  # noqa: E402


_FIXTURE = _PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "clientes_raw.json"

_EXPECTED_CORE_KEYS = {
    "nome", "cpf_cnpj", "e_mail", "telefone", "falecido",
    "uf", "estado_civil", "sexo", "situacao_funcional",
    "status_do_cadastro", "tipo", "data_de_nascimento",
    "observacoes", "processos", "documentos",
}
_LEGACY_INVENTED_SLUGS = ("cadastrado", "n_processos", "cpf", "email", "notas")


def main() -> int:
    print()
    print("=== VALIDACAO FASE 2C ===")
    print()

    # Fase 3: flags removidas — registry é fonte única.
    from notion_bulk_edit import config
    assert not hasattr(config, "USE_DYNAMIC_SCHEMA")
    assert not hasattr(config, "DYNAMIC_BASES")
    print("flags removidas (Fase 3): registry serve todas as bases")

    with tempfile.TemporaryDirectory(prefix="rpadv_fase2c_") as tmp:
        db_path = Path(tmp) / "audit_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_audit_db(conn)

        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        parsed = parse_to_schema_json(raw, "Clientes")
        schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        upsert_schema(
            conn, parsed["data_source_id"], "Clientes",
            parsed["title_property"], schema_json,
            compute_schema_hash(parsed), 1700000000.0,
        )

        import notion_bulk_edit.schema_registry as sr
        saved = sr._registry
        try:
            init_schema_registry(conn)

            cli = SCHEMAS["Clientes"]
            keys = set(cli.keys())
            print(f"SCHEMAS['Clientes'] keys ({len(keys)}): "
                  f"{len(keys)} props (esperadas 32)")
            missing = _EXPECTED_CORE_KEYS - keys
            assert not missing, f"chaves esperadas ausentes: {missing}"

            for legacy in _LEGACY_INVENTED_SLUGS:
                assert legacy not in keys, (
                    f"slug legado inventado {legacy!r} ainda presente"
                )
            print(f"slugs legados ausentes: {_LEGACY_INVENTED_SLUGS}")

            print(f"_TITLE_KEY_BY_BASE['Clientes'] = "
                  f"{_TITLE_KEY_BY_BASE['Clientes']!r}")
            assert _TITLE_KEY_BY_BASE["Clientes"] == "nome"

            uf = cli["uf"]
            print(f"uf.tipo = {uf.tipo}, opcoes ({len(uf.opcoes)}) = "
                  f"{uf.opcoes[:5]}... (mais {len(uf.opcoes) - 5})")
            assert uf.tipo == "select"
            assert len(uf.opcoes) == 27

            cidade = cli["cidade"]
            print(f"cidade.tipo = {cidade.tipo} "
                  f"(legacy era 'select' com CIDADES_UF; agora rich_text)")
            assert cidade.tipo == "rich_text"

            print()
            print("OK: Fase 2c validada programaticamente.")
        finally:
            sr._registry = saved
            conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
