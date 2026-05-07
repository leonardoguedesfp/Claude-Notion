"""Lista as colunas da planilha de auditoria DataJUD e dump em JSON
para escolher CNJs amostrais por tribunal/instância.

Uso:
    python scripts/investigacoes/inspecionar_auditoria.py

Investigação Turma+Relator (2026-05-05). Não é parte do build; pode ser
removido ao final da investigação.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import openpyxl


PATH = Path("logs/datajud_consulta_2026-05-05-1529.xlsx")
OUT_DIR = Path("scripts/investigacoes/_dados")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    wb = openpyxl.load_workbook(PATH, read_only=True, data_only=True)
    ws = wb["DataJUD"]

    rows_iter = ws.iter_rows(values_only=True)
    headers = list(next(rows_iter))
    headers_str = [str(h) if h is not None else "" for h in headers]

    print("HEADERS:")
    for i, h in enumerate(headers_str, start=1):
        print(f"  {i:3d}: {h!r}")

    # Dump cada linha como dict
    rows_data: list[dict[str, Any]] = []
    for row in rows_iter:
        d: dict[str, Any] = {}
        for i, v in enumerate(row):
            if i < len(headers_str):
                d[headers_str[i]] = v
        rows_data.append(d)

    print(f"\nTotal linhas: {len(rows_data)}")

    out_path = OUT_DIR / "auditoria_rows.json"
    with out_path.open("w", encoding="utf-8") as f:
        # converter datetimes/etc para str
        def _safe(o: Any) -> Any:
            if o is None or isinstance(o, (str, int, float, bool)):
                return o
            return str(o)

        rows_clean = [{k: _safe(v) for k, v in r.items()} for r in rows_data]
        json.dump(rows_clean, f, ensure_ascii=False, indent=2)
    print(f"\nDump salvo em {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
