"""Fase 2b — Tarefas no schema dinâmico: validação programática.

Substitui o smoke manual no overnight. Roda end-to-end:
1. Confirma flags ON e Tarefas em DYNAMIC_BASES.
2. Cria audit.db temporário, popula meta_schemas com fixture de Tarefas,
   inicializa registry singleton.
3. Acessa SCHEMAS["Tarefas"] via proxy — confirma 20 chaves reais
   (incluindo Status novo) e que labels legados (A fazer, Em andamento,
   Aguardando) NÃO aparecem nas opções de Status.
4. Confirma _TITLE_KEY_BY_BASE["Tarefas"] == "tarefa".
5. Spot check: opções de Status batem com Notion real (Pendente, Concluída).

NÃO toca em audit.db de produção. NÃO faz chamadas reais à API — só lê
fixture committada (tarefas_raw.json).

Uso:
    python scripts/validar_fase_2b.py
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


_FIXTURE = _PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "tarefas_raw.json"

_EXPECTED_CORE_KEYS = {
    "tarefa", "status", "descricao", "prazo_fatal",
    "data_de_protocolo", "responsavel", "processo", "tipo_de_tarefa",
    "cliente", "tribunal",
}
_LEGACY_STATUS_LABELS = ("A fazer", "Em andamento", "Aguardando")


def main() -> int:
    print()
    print("=== VALIDACAO FASE 2B ===")
    print()

    # 1. Fase 3 removeu USE_DYNAMIC_SCHEMA/DYNAMIC_BASES — registry é fonte
    # única. Validamos que o cleanup foi feito.
    from notion_bulk_edit import config
    assert not hasattr(config, "USE_DYNAMIC_SCHEMA")
    assert not hasattr(config, "DYNAMIC_BASES")
    print("flags removidas (Fase 3): registry serve todas as bases")

    # 2. Cache temporário + popular Tarefas
    with tempfile.TemporaryDirectory(prefix="rpadv_fase2b_") as tmp:
        db_path = Path(tmp) / "audit_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_audit_db(conn)

        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        parsed = parse_to_schema_json(raw, "Tarefas")
        schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        upsert_schema(
            conn, parsed["data_source_id"], "Tarefas",
            parsed["title_property"], schema_json,
            compute_schema_hash(parsed), 1700000000.0,
        )

        import notion_bulk_edit.schema_registry as sr
        saved = sr._registry
        try:
            init_schema_registry(conn)

            # 3. SCHEMAS via proxy
            tar = SCHEMAS["Tarefas"]
            keys = set(tar.keys())
            print(f"SCHEMAS['Tarefas'] keys ({len(keys)}): {sorted(keys)}")
            missing = _EXPECTED_CORE_KEYS - keys
            assert not missing, f"chaves esperadas ausentes: {missing}"

            # 4. _TITLE_KEY_BY_BASE
            print(f"_TITLE_KEY_BY_BASE['Tarefas'] = "
                  f"{_TITLE_KEY_BY_BASE['Tarefas']!r}")
            assert _TITLE_KEY_BY_BASE["Tarefas"] == "tarefa"

            # 5. Status: select com Pendente/Concluída
            status_spec = tar["status"]
            print(f"status.tipo = {status_spec.tipo}, "
                  f"opcoes = {status_spec.opcoes}")
            assert status_spec.tipo == "select"
            assert "Pendente" in status_spec.opcoes
            assert "Concluída" in status_spec.opcoes

            # 6. Labels legados não aparecem
            for legacy in _LEGACY_STATUS_LABELS:
                assert legacy not in status_spec.opcoes, (
                    f"label legado {legacy!r} ainda nas opcoes — "
                    "fixture nao foi atualizada?"
                )
            print(f"labels legados ausentes: {_LEGACY_STATUS_LABELS} — OK")

            print()
            print("OK: Fase 2b validada programaticamente.")
        finally:
            sr._registry = saved
            conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
