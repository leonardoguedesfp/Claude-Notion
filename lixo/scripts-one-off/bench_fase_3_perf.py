"""Benchmark: hotfix de performance da Fase 3.

Simula o hot path de QTableView (paint, data, flags) que chama
SCHEMAS["Base"]["key"] e get_prop(base, key) milhares de vezes por
sessão. Sem cache: ~4.65M chamadas a _dict_to_propspec em 102s
profilado em runtime real.

Roda 100k iterações simulando rendering de 1000 rows × 100 paints.
Esperado pós-fix:
- _dict_to_propspec: < 200 ncalls (37 props × 4 bases ~ 148)
- schema_for_base: cumtime < 0.5s mesmo com 100k calls
- get_prop: cumtime < 1s

Uso:
    python -m cProfile -o /tmp/bench.out scripts/bench_fase_3_perf.py
    python -c "import pstats; pstats.Stats('/tmp/bench.out').sort_stats('cumulative').print_stats(15)"
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
from notion_bulk_edit.schemas import SCHEMAS, get_prop  # noqa: E402
from notion_rpadv.cache.db import init_audit_db, upsert_schema  # noqa: E402


_FIXTURES = (
    ("Catalogo",  "79afc833-77e2-4574-98ba-ebed7bd7e66c"),
    ("Processos", "5e93b734-4043-4c89-a513-5e00a14081bb"),
    ("Clientes",  "939e5dcf-51bd-4ffa-a28e-0313899fd229"),
    ("Tarefas",   "3a8bb311-5c1b-42ac-a3b2-859b75911e91"),
)
_FIXTURES_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "schemas"


def _populate_registry(conn: sqlite3.Connection) -> None:
    init_audit_db(conn)
    for label, dsid in _FIXTURES:
        raw = json.loads(
            (_FIXTURES_DIR / f"{label.lower()}_raw.json").read_text(encoding="utf-8"),
        )
        parsed = parse_to_schema_json(raw, label)
        upsert_schema(
            conn,
            data_source_id=parsed.get("data_source_id") or dsid,
            base_label=label,
            title_property=parsed.get("title_property"),
            schema_json=json.dumps(parsed, sort_keys=True, ensure_ascii=False),
            schema_hash=compute_schema_hash(parsed),
            fetched_at=1700000000.0,
        )
    init_schema_registry(conn)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rpadv_bench_") as tmp:
        conn = sqlite3.connect(str(Path(tmp) / "audit.db"))
        conn.row_factory = sqlite3.Row
        _populate_registry(conn)

        # Hot path 1: SCHEMAS["Base"]["key"] — paint/data/flags fazem
        # isso por célula renderizada.
        # 100_000 iterações simula 1000 rows × 100 paints/scroll.
        N = 100_000
        for _ in range(N // 4):
            _ = SCHEMAS["Processos"]["status"]
            _ = SCHEMAS["Clientes"]["nome"]
            _ = SCHEMAS["Tarefas"]["tarefa"]
            _ = SCHEMAS["Catalogo"]["categoria"]

        # Hot path 2: get_prop por (base, key) — chamado por delegates.
        for _ in range(N // 4):
            _ = get_prop("Processos", "tribunal")
            _ = get_prop("Processos", "fase")
            _ = get_prop("Clientes", "uf")
            _ = get_prop("Tarefas", "status")

        # Hot path 3: iter sobre keys de uma base — colunas_visiveis equiv.
        for _ in range(N // 4):
            _ = list(SCHEMAS["Processos"])
            _ = list(SCHEMAS["Catalogo"])

        # Hot path 4: spec.cor_por_valor / target_base lookup
        for _ in range(N // 4):
            spec = SCHEMAS["Processos"]["tribunal"]
            _ = spec.cor_por_valor.get("TJDFT", "")
            spec2 = SCHEMAS["Processos"]["clientes"]
            _ = spec2.target_base

        print(f"Concluído: ~{N} iterações × 2 chamadas por iteração.")
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
