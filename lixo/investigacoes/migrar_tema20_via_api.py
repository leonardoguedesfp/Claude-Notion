"""Migração direta via API Notion (contorna bug do importar.py do app).

Por que existe:
    O ``importar.py`` do app chama ``client.create_page(db_id, ...)``
    (método legado, payload ``parent.database_id``). A API Notion
    versão 2025-09-03 exige ``parent.data_source_id`` para criar
    páginas — o legado falha silenciosamente, e o app pega no
    ``except Exception`` e marca como erro. Resultado: 0/132 importados.

    Este script chama ``create_page_in_data_source`` direto, que envia
    ``parent.data_source_id``, conforme a API atual.

Modos:
    --limite N    cria só as primeiras N linhas (default 1, modo teste)
    --tudo        cria todas as 132

Uso:
    PYTHONPATH=. python scripts/investigacoes/migrar_tema20_via_api.py --limite 1
    PYTHONPATH=. python scripts/investigacoes/migrar_tema20_via_api.py --tudo

Saída:
    logs/migracao_tema20_resultado_<ts>.json
        - por linha: page_id criado OU mensagem de erro
        - resumo final: total OK / total falha
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl

from notion_bulk_edit.config import DATA_SOURCES
from notion_bulk_edit.encoders import encode_value
from notion_bulk_edit.notion_api import NotionClient
from notion_bulk_edit.schemas import SCHEMAS
from notion_bulk_edit.token_store import get_token


PLANILHA = Path("logs/migracao_tema20_2026-05-06-1553.xlsx")
OUT_DIR = Path("logs")


def _build_properties(
    row_dict: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Espelha o loop do importar.py: itera schema → encode_value.

    Diferente do app, não engole exceptions silenciosamente; deixa
    propagar para o caller decidir.
    """
    props: dict[str, Any] = {}
    for prop_key, spec in schema.items():
        if not spec.editavel:
            continue
        v = row_dict.get(spec.notion_name)
        if v is None:
            v = row_dict.get(spec.label)
        if v is None:
            v = row_dict.get(prop_key)
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        encoded = encode_value(v, spec.tipo)
        if encoded is not None:
            props[spec.notion_name] = encoded
    return props


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--limite", type=int, default=1)
    grp.add_argument("--tudo", action="store_true")
    args = parser.parse_args()

    # Inicializa schema registry (precisa do audit.db)
    import sqlite3
    from notion_bulk_edit.schema_registry import init_schema_registry
    audit_db = (
        Path.home()
        / "AppData" / "Roaming" / "NotionRPADV" / "audit.db"
    )
    audit_conn = sqlite3.connect(str(audit_db))
    audit_conn.row_factory = sqlite3.Row
    init_schema_registry(audit_conn=audit_conn)
    schema = dict(SCHEMAS["Processos"])
    print(f"Schema Processos: {len(schema)} propriedades")

    # Token + client
    token = get_token()
    if not token:
        print("ERRO: token Notion não encontrado")
        return 1
    client = NotionClient(token)
    data_source_id = DATA_SOURCES["Processos"]
    print(f"data_source_id: {data_source_id}")

    # Lê a planilha
    print(f"Lendo: {PLANILHA}")
    wb = openpyxl.load_workbook(PLANILHA, read_only=True, data_only=True)
    ws = wb["Processos"]
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(c) if c else "" for c in rows[0]]
    data_rows = [
        {headers[i]: r[i] for i in range(len(headers)) if i < len(r)}
        for r in rows[1:]
    ]
    wb.close()
    print(f"  {len(data_rows)} linhas")

    # Dedup: lê logs de resultados anteriores p/ pular CNJs já criados.
    # Evita criar duplicatas se o script for rodado mais de uma vez.
    ja_criados: dict[str, str] = {}  # cnj → page_id
    for prev in OUT_DIR.glob("migracao_tema20_resultado_*.json"):
        try:
            with prev.open(encoding="utf-8") as f:
                d = json.load(f)
            for r in d.get("resultados", []):
                if r.get("ok") and r.get("cnj") and r.get("page_id"):
                    ja_criados[r["cnj"]] = r["page_id"]
        except (OSError, json.JSONDecodeError):
            continue
    if ja_criados:
        print(f"De-dup: {len(ja_criados)} CNJ(s) já criado(s) em runs anteriores → vão ser pulados")

    # Filtra rows ainda pendentes
    pendentes = [r for r in data_rows if r.get("Número do processo") not in ja_criados]
    n_pendente = len(pendentes)
    print(f"  {n_pendente} pendente(s) de {len(data_rows)} total")

    n_alvo = n_pendente if args.tudo else min(args.limite, n_pendente)
    print(f"\nVou criar {n_alvo} processo(s).")
    if not args.tudo:
        print(f"(modo teste — para criar todos, rode com --tudo)")
    print()

    data_rows = pendentes

    resultados: list[dict[str, Any]] = []
    n_ok = 0
    n_err = 0

    for i, row_dict in enumerate(data_rows[:n_alvo], start=1):
        cnj = row_dict.get("Número do processo", "?")
        try:
            props = _build_properties(row_dict, schema)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i:>3}/{n_alvo}] {cnj}  ENCODE ERROR: {exc}")
            resultados.append({
                "cnj": cnj, "ok": False, "erro": f"encode: {exc}",
            })
            n_err += 1
            continue

        try:
            result = client.create_page_in_data_source(
                data_source_id, props,
            )
            page_id = result.get("id", "")
            print(f"  [{i:>3}/{n_alvo}] {cnj}  → {page_id}")
            resultados.append({
                "cnj": cnj, "ok": True, "page_id": page_id,
            })
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            print(f"  [{i:>3}/{n_alvo}] {cnj}  ERRO: {msg[:200]}")
            resultados.append({
                "cnj": cnj, "ok": False,
                "erro": msg, "props_enviadas": props,
            })
            n_err += 1
            # Para no primeiro erro: não queremos criar 131 duplicatas
            # se algo está sistemicamente errado.
            print()
            print(f"⚠ Parando no primeiro erro para evitar lixo. "
                  f"{n_ok} criado(s), {n_err} falha(s).")
            break

    # Salva resultado
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    out_path = OUT_DIR / f"migracao_tema20_resultado_{ts}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({
            "modo": "tudo" if args.tudo else f"limite={args.limite}",
            "n_alvo": n_alvo,
            "n_ok": n_ok,
            "n_err": n_err,
            "resultados": resultados,
        }, f, ensure_ascii=False, indent=2)

    print()
    print(f"Resultado: OK={n_ok}  ERR={n_err}")
    print(f"Log salvo: {out_path}")
    return 0 if n_err == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
