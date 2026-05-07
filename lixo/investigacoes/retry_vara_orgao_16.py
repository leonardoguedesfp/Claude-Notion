"""Retry da migração Vara → nome do órgão para os 16 CNJs que falharam
silenciosamente na aba Importar do app.

Usa update_page direto via NotionClient — mesma estratégia que destravou
a Tema 20 quando o create_page do app estava quebrado.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from notion_bulk_edit.encoders import encode_value
from notion_bulk_edit.notion_api import NotionClient
from notion_bulk_edit.token_store import get_token


# Os 16 não-migrados, identificados pela diff PRE(17) vs POS(18)
ALVO: list[tuple[str, str, str]] = [
    # (cnj, page_id_provável, valor_alvo) — page_id resolvido via inventário
]

CNJS_ALVO = [
    ("0000364-48.2026.5.10.0004", "4ª Vara do Trabalho de Brasília - DF"),
    ("0019231-19.2015.8.07.0001", "6ª Vara Cível de Brasília"),
    ("0022746-28.2016.8.07.0001", "6ª Vara Cível de Brasília"),
    ("0708850-56.2025.8.07.0001", "6ª Vara Cível de Brasília"),
    ("0709127-53.2017.8.07.0001", "6ª Vara Cível de Brasília"),
    ("0721527-65.2018.8.07.0001", "6ª Vara Cível de Brasília"),
    ("0001419-27.2023.5.10.0008", "6ª Vara do Trabalho de Brasília - DF"),
    ("0000401-63.2026.5.10.0008", "8ª Vara do Trabalho de Brasília - DF"),
    ("0000407-70.2026.5.10.0008", "8ª Vara do Trabalho de Brasília - DF"),
    ("0722580-81.2018.8.07.0001", "9ª Vara Cível de Brasília"),
    ("0730524-71.2017.8.07.0001", "9ª Vara Cível de Brasília"),
    ("0001361-50.2025.5.10.0009", "9ª Vara do Trabalho de Brasília - DF"),
    ("0000154-21.2022.5.10.0009", "9ª Vara do Trabalho de Brasília - DF"),
    ("0000300-57.2025.5.10.0009", "9ª Vara do Trabalho de Brasília - DF"),
    ("0000308-68.2024.5.10.0009", "9ª Vara do Trabalho de Brasília - DF"),
    ("0000356-56.2026.5.10.0009", "9ª Vara do Trabalho de Brasília - DF"),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    inv = Path("scripts/investigacoes/_dados/reconciliacao_vara/processos_inventario.json")
    with inv.open(encoding="utf-8") as f:
        cnj_to_pid = {p["cnj"]: p["uuid"] for p in json.load(f) if p.get("cnj")}

    token = get_token()
    if not token:
        print("ERRO: token não disponível")
        return 1
    client = NotionClient(token)

    print(f"Retry Vara→Órgão para {len(CNJS_ALVO)} CNJs")
    print()
    n_ok = 0
    n_err = 0
    log: list[dict[str, str]] = []
    for i, (cnj, alvo) in enumerate(CNJS_ALVO, start=1):
        pid = cnj_to_pid.get(cnj)
        if not pid:
            print(f"  [{i:>2}/16] {cnj}  ERRO: page_id não encontrado")
            n_err += 1
            log.append({"cnj": cnj, "ok": False, "erro": "page_id não encontrado"})
            continue
        props = {"Vara": encode_value(alvo, "rich_text")}
        try:
            client.update_page(pid, props)
            print(f"  [{i:>2}/16] {cnj}  → {alvo!r}  ✓")
            n_ok += 1
            log.append({"cnj": cnj, "ok": True, "page_id": pid, "alvo": alvo})
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i:>2}/16] {cnj}  ERRO: {exc}")
            n_err += 1
            log.append({"cnj": cnj, "ok": False, "erro": str(exc), "page_id": pid})

    print()
    print(f"OK={n_ok}  ERR={n_err}")

    out = Path("logs") / f"retry_vara_orgao_{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump({"n_ok": n_ok, "n_err": n_err, "log": log}, f, ensure_ascii=False, indent=2)
    print(f"Log: {out}")
    return 0 if n_err == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
