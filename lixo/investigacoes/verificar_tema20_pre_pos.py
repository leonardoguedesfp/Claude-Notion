"""Valida a migração Tema 20 comparando os 4 CSVs:

    Processos (15) → Processos (16)   [esperado: +132 novos, antigos intactos]
    Clientes  (1)  → Clientes  (2)    [esperado: 0 mudanças significativas]

Saída: relatório no stdout — diferenças por coluna, listas de CNJs novos
e quaisquer drifts inesperados.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PRE_PRO = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Local\Temp"
    r"\⚖️ Processos 78f11cd71d0d4a1e9df58be085e5bb33_all (15).csv"
)
POS_PRO = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Local\Temp"
    r"\⚖️ Processos 78f11cd71d0d4a1e9df58be085e5bb33_all (16).csv"
)
PRE_CLI = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Local\Temp"
    r"\👥 Clientes b015580ad07943a3a57c9e021c2a4615_all (1).csv"
)
POS_CLI = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Local\Temp"
    r"\👥 Clientes b015580ad07943a3a57c9e021c2a4615_all (2).csv"
)
LOGS_DIR = Path("logs")


def _load(path: Path, key_col: str = "Número do processo") -> tuple[list[str], dict[str, dict[str, str]]]:
    with path.open(encoding="utf-8") as f:
        rd = csv.reader(f)
        headers = next(rd)
        headers[0] = headers[0].lstrip("﻿")
        out: dict[str, dict[str, str]] = {}
        for row in rd:
            if not row:
                continue
            d = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
            chave = (d.get(key_col) or "").strip()
            if not chave:
                continue
            out[chave] = d
    return headers, out


def _carregar_cnjs_migracao() -> set[str]:
    """CNJs criados pela migração (lê os JSONs de resultado)."""
    cnjs: set[str] = set()
    for prev in LOGS_DIR.glob("migracao_tema20_resultado_*.json"):
        try:
            with prev.open(encoding="utf-8") as f:
                d = json.load(f)
            for r in d.get("resultados", []):
                if r.get("ok") and r.get("cnj"):
                    cnjs.add(r["cnj"])
        except (OSError, json.JSONDecodeError):
            continue
    return cnjs


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    print("=" * 72)
    print("PROCESSOS — pre (15) vs pos (16)")
    print("=" * 72)
    h_pre, pre = _load(PRE_PRO)
    h_pos, pos = _load(POS_PRO)
    print(f"  PRE: {len(pre)} processos")
    print(f"  POS: {len(pos)} processos")
    print(f"  Δ:   {len(pos) - len(pre):+d}")

    cnjs_pre = set(pre)
    cnjs_pos = set(pos)
    novos = cnjs_pos - cnjs_pre
    sumiram = cnjs_pre - cnjs_pos
    comuns = cnjs_pre & cnjs_pos

    print(f"\n  Novos (em POS, não em PRE): {len(novos)}")
    print(f"  Sumidos (em PRE, não em POS): {len(sumiram)}")
    if sumiram:
        print("  ⚠ ALGUM PROCESSO SUMIU:")
        for c in sorted(sumiram)[:10]:
            print(f"      {c}")

    # Cruza os 132 novos com o registro da migração
    cnjs_migracao = _carregar_cnjs_migracao()
    print(f"\n  Esperados (registro do script): {len(cnjs_migracao)}")
    fora_esperado = novos - cnjs_migracao
    nao_apareceu = cnjs_migracao - novos
    if fora_esperado:
        print(f"  ⚠ Novos NÃO esperados (criados por outra fonte?): {len(fora_esperado)}")
        for c in sorted(fora_esperado)[:5]:
            print(f"      {c}")
    if nao_apareceu:
        print(f"  ⚠ Esperados que NÃO apareceram no CSV: {len(nao_apareceu)}")
        for c in sorted(nao_apareceu)[:5]:
            print(f"      {c}")
    if not fora_esperado and not nao_apareceu:
        print(f"  ✓ Os {len(novos)} novos CNJs no CSV batem 1:1 com a migração")

    # Drift nos antigos (1108)
    headers_comuns = [h for h in h_pre if h in h_pos]
    drift: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for cnj in comuns:
        rp, rq = pre[cnj], pos[cnj]
        for col in headers_comuns:
            v_pre = (rp.get(col) or "").strip()
            v_pos = (rq.get(col) or "").strip()
            if v_pre != v_pos:
                drift[col].append((cnj, v_pre, v_pos))

    print(f"\n  Antigos comparados: {len(comuns)}")
    print(f"  Colunas com drift: {len(drift)}")
    for col, items in sorted(drift.items(), key=lambda kv: -len(kv[1])):
        marker = ""
        if col == "Atualizado em":
            marker = "  ← bump esperado p/ clientes que ganharam back-ref"
        print(f"\n    {col!r}: {len(items)} mudança(s){marker}")
        for cnj, vp, vq in items[:3]:
            print(f"      {cnj}")
            print(f"        pré: {vp[:90]!r}")
            print(f"        pós: {vq[:90]!r}")
        if len(items) > 3:
            print(f"      … (+{len(items) - 3} mais)")

    inesperadas = [c for c in headers_comuns if c not in ("Atualizado em",) and drift.get(c)]
    print()
    if not inesperadas:
        print("  ✓ Nenhuma alteração inesperada nos 1.108 antigos.")
    else:
        print(f"  ⚠ {len(inesperadas)} coluna(s) com drift inesperado nos antigos:")
        for c in inesperadas:
            print(f"      {c}: {len(drift[c])}")

    # ----------------------------------------------------------------
    print()
    print("=" * 72)
    print("CLIENTES — pre (1) vs pos (2)")
    print("=" * 72)
    h_pre_c, pre_c = _load(PRE_CLI, key_col="Nome")
    h_pos_c, pos_c = _load(POS_CLI, key_col="Nome")
    print(f"  PRE: {len(pre_c)} clientes")
    print(f"  POS: {len(pos_c)} clientes")
    print(f"  Δ:   {len(pos_c) - len(pre_c):+d}")

    nomes_pre = set(pre_c)
    nomes_pos = set(pos_c)
    cli_novos = nomes_pos - nomes_pre
    cli_sumiram = nomes_pre - nomes_pos
    cli_comuns = nomes_pre & nomes_pos
    if cli_novos:
        print(f"  ⚠ Clientes NOVOS: {len(cli_novos)}")
        for n in sorted(cli_novos)[:5]:
            print(f"      {n}")
    if cli_sumiram:
        print(f"  ⚠ Clientes SUMIDOS: {len(cli_sumiram)}")
        for n in sorted(cli_sumiram)[:5]:
            print(f"      {n}")

    headers_c_comuns = [h for h in h_pre_c if h in h_pos_c]
    drift_c: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for nome in cli_comuns:
        rp, rq = pre_c[nome], pos_c[nome]
        for col in headers_c_comuns:
            v_pre = (rp.get(col) or "").strip()
            v_pos = (rq.get(col) or "").strip()
            if v_pre != v_pos:
                drift_c[col].append((nome, v_pre, v_pos))

    print(f"\n  Comparados: {len(cli_comuns)}")
    print(f"  Colunas com drift: {len(drift_c)}")
    for col, items in sorted(drift_c.items(), key=lambda kv: -len(kv[1])):
        marker = ""
        if col == "Atualizado em":
            marker = "  ← bump esperado p/ clientes que ganharam back-ref"
        elif col == "Processos":
            marker = "  ← back-ref auto-populada pelo Notion ao criar Processo"
        print(f"\n    {col!r}: {len(items)} mudança(s){marker}")
        for nome, vp, vq in items[:3]:
            print(f"      {nome}")
            # pra Processos a string é longa; mostra só primeiros UUIDs
            print(f"        pré: {vp[:90]!r}")
            print(f"        pós: {vq[:90]!r}")
        if len(items) > 3:
            print(f"      … (+{len(items) - 3} mais)")

    inesperadas_c = [
        c for c in headers_c_comuns
        if c not in ("Atualizado em", "Processos") and drift_c.get(c)
    ]
    print()
    if not inesperadas_c:
        print("  ✓ Nenhuma alteração inesperada nos clientes além de Processos / Atualizado em.")
    else:
        print(f"  ⚠ {len(inesperadas_c)} coluna(s) inesperada(s):")
        for c in inesperadas_c:
            print(f"      {c}: {len(drift_c[c])}")

    # ----------------------------------------------------------------
    print()
    print("=" * 72)
    print("VEREDITO")
    print("=" * 72)
    sucesso = (
        not sumiram
        and not fora_esperado
        and not nao_apareceu
        and not inesperadas
        and not cli_novos
        and not cli_sumiram
        and not inesperadas_c
    )
    if sucesso:
        print("✓ Migração íntegra: 132 processos novos exatamente como esperado;")
        print("  zero drift em colunas inesperadas; clientes preservados.")
    else:
        print("⚠ Verificar listagens acima.")
    return 0 if sucesso else 1


if __name__ == "__main__":
    raise SystemExit(main())
