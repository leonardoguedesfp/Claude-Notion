"""Fase 2a — Catálogo no schema dinâmico: validação programática.

Substitui o smoke manual do overnight. Roda end-to-end:
1. Confirma flags ON e Catálogo em DYNAMIC_BASES.
2. Cria audit.db temporário, popula meta_schemas com fixture do Catálogo,
   inicializa o registry singleton.
3. Acessa SCHEMAS["Catalogo"] via proxy — confirma 5 chaves reais e que
   as 4 inventadas (area, tempo_estimado, responsavel_padrao, revisado)
   não aparecem.
4. Confirma _TITLE_KEY_BY_BASE["Catalogo"] == "nome".
5. Confirma colunas_visiveis("Catalogo") via legacy helper.

NÃO toca em audit.db de produção (%APPDATA%/NotionRPADV/audit.db). NÃO
faz chamadas reais à API — só lê fixtures committadas.

Uso:
    python scripts/validar_fase_2a.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

# Garante que o root do projeto esteja no sys.path quando rodando de scripts/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from notion_bulk_edit.schema_parser import (  # noqa: E402
    compute_schema_hash,
    parse_to_schema_json,
)
from notion_bulk_edit.schema_registry import init_schema_registry  # noqa: E402
from notion_bulk_edit.schemas import SCHEMAS, colunas_visiveis  # noqa: E402
from notion_rpadv.cache.db import init_audit_db, upsert_schema  # noqa: E402
from notion_rpadv.models.base_table_model import _TITLE_KEY_BY_BASE  # noqa: E402


_FIXTURE = _PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "catalogo_raw.json"

_EXPECTED_KEYS = {"nome", "categoria", "prazo", "observacoes", "tarefas"}
_INVENTED_KEYS = ("area", "tempo_estimado", "responsavel_padrao", "revisado")


def main() -> int:
    print()
    print("=== VALIDACAO FASE 2A ===")
    print()

    # 1. Fase 3 removeu USE_DYNAMIC_SCHEMA e DYNAMIC_BASES — registry é
    # fonte única para todas as 4 bases. Validamos que o cleanup foi feito.
    from notion_bulk_edit import config
    assert not hasattr(config, "USE_DYNAMIC_SCHEMA")
    assert not hasattr(config, "DYNAMIC_BASES")
    print("flags removidas (Fase 3): registry serve todas as bases")

    # 2. Cache temporário + popular Catálogo
    with tempfile.TemporaryDirectory(prefix="rpadv_fase2a_") as tmp:
        db_path = Path(tmp) / "audit_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_audit_db(conn)

        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        parsed = parse_to_schema_json(raw, "Catalogo")
        schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        upsert_schema(
            conn, parsed["data_source_id"], "Catalogo",
            parsed["title_property"], schema_json,
            compute_schema_hash(parsed), 1700000000.0,
        )

        # Inicializa singleton — substitui qualquer instância prévia
        import notion_bulk_edit.schema_registry as sr
        saved = sr._registry
        try:
            init_schema_registry(conn)

            # 3. SCHEMAS via proxy
            cat = SCHEMAS["Catalogo"]
            keys = set(cat.keys())
            print(f"SCHEMAS['Catalogo'] keys ({len(keys)}): {sorted(keys)}")
            for k in _EXPECTED_KEYS:
                assert k in keys, f"chave real {k!r} ausente do registry"
            for k in _INVENTED_KEYS:
                assert k not in keys, (
                    f"chave inventada {k!r} ainda presente — ainda vindo do legado?"
                )

            # 4. _TITLE_KEY_BY_BASE
            print(f"_TITLE_KEY_BY_BASE['Catalogo'] = {_TITLE_KEY_BY_BASE['Catalogo']!r}")
            assert _TITLE_KEY_BY_BASE["Catalogo"] == "nome"

            # 5. colunas_visiveis legacy helper
            cols = colunas_visiveis("Catalogo")
            print(f"colunas_visiveis('Catalogo') = {cols}")
            # Nota: helper legacy filtra por largura_col != '0'. No registry
            # dinamico, PropSpec.largura_col tem default '10%' (vem do _dict_to_propspec
            # em schema_registry.py), entao TODAS as 5 chaves devem aparecer.
            # Se viesse algo errado, alguma chave sumiria.
            assert len(cols) == len(keys), (
                f"colunas_visiveis filtrou {len(keys) - len(cols)} chaves "
                "inesperadamente — verificar largura_col defaults"
            )

            # 6. Spot check: opcoes de categoria
            cat_spec = cat["categoria"]
            print(f"categoria.tipo = {cat_spec.tipo}, "
                  f"opcoes ({len(cat_spec.opcoes)}) = {cat_spec.opcoes}")
            assert cat_spec.tipo == "select"
            assert "Peças processuais" in cat_spec.opcoes

            print()
            print("OK: Fase 2a validada programaticamente.")
        finally:
            sr._registry = saved
            conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
