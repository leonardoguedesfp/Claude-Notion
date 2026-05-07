"""Compara CSVs pré (17) vs pós (18) da migração Vara → nome do órgão.

Esperado:
  • 1.087 mudanças exatamente em 'Vara'
  • mesmas 1.087 linhas com bump em 'Atualizado em'
  • zero mudança nas demais 36 colunas
  • zero linha nova/sumida
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


PRE = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Local\Temp"
    r"\⚖️ Processos 78f11cd71d0d4a1e9df58be085e5bb33_all (17).csv"
)
POS = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Local\Temp"
    r"\⚖️ Processos 78f11cd71d0d4a1e9df58be085e5bb33_all (18).csv"
)


def _load(p: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with p.open(encoding="utf-8") as f:
        rd = csv.reader(f)
        headers = next(rd)
        headers[0] = headers[0].lstrip("﻿")
        out: dict[str, dict[str, str]] = {}
        for row in rd:
            if not row:
                continue
            cnj = row[0].strip()
            if not cnj:
                continue
            out[cnj] = {
                headers[i]: (row[i] if i < len(row) else "")
                for i in range(len(headers))
            }
    return headers, out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    print(f"PRE: {PRE.name}")
    print(f"POS: {POS.name}")
    print()

    h_pre, pre = _load(PRE)
    h_pos, pos = _load(POS)
    print(f"  PRE: {len(pre)} processos, {len(h_pre)} cols")
    print(f"  POS: {len(pos)} processos, {len(h_pos)} cols")
    print(f"  Δ:   {len(pos) - len(pre):+d}")

    cnjs_pre = set(pre)
    cnjs_pos = set(pos)
    if cnjs_pre - cnjs_pos:
        print(f"  ⚠ {len(cnjs_pre - cnjs_pos)} CNJ(s) sumiram")
        for c in list(cnjs_pre - cnjs_pos)[:5]:
            print(f"      {c}")
    if cnjs_pos - cnjs_pre:
        print(f"  ⚠ {len(cnjs_pos - cnjs_pre)} CNJ(s) novos (esperado 0)")

    headers = [h for h in h_pre if h in h_pos]
    drift: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    cnjs_comuns = sorted(cnjs_pre & cnjs_pos)
    for cnj in cnjs_comuns:
        rp, rq = pre[cnj], pos[cnj]
        for col in headers:
            v_pre = (rp.get(col) or "").strip()
            v_pos = (rq.get(col) or "").strip()
            if v_pre != v_pos:
                drift[col].append((cnj, v_pre, v_pos))

    print()
    print("=" * 70)
    print("Mudanças por coluna")
    print("=" * 70)
    print(f"\n{'COLUNA':<45}  {'#mudanças':>10}")
    print("-" * 60)
    for col in headers:
        n = len(drift.get(col, []))
        marker = ""
        if col == "Vara":
            marker = "  ← intencional (1.087 esperado)"
        elif col == "Atualizado em":
            marker = "  ← bump esperado"
        print(f"  {col:<45}  {n:>10}{marker}")

    inesperadas = [c for c in headers if c not in ("Vara", "Atualizado em") and drift.get(c)]
    print()
    print("=" * 70)
    print("INESPERADAS (fora de Vara e Atualizado em)")
    print("=" * 70)
    if not inesperadas:
        print("  ✓ Nenhuma. Todas as outras 36 colunas idênticas entre PRE e POS.")
    else:
        for col in inesperadas:
            items = drift[col]
            print(f"\n  Coluna {col!r}: {len(items)} mudança(s)")
            for cnj, vp, vq in items[:3]:
                print(f"    {cnj}")
                print(f"      pré: {vp[:90]!r}")
                print(f"      pós: {vq[:90]!r}")

    # Cruzamento Vara × Atualizado
    cnjs_vara = {c for c, _, _ in drift.get("Vara", [])}
    cnjs_atu = {c for c, _, _ in drift.get("Atualizado em", [])}
    print()
    print("=" * 70)
    print("Vara vs Atualizado em (devem coincidir)")
    print("=" * 70)
    print(f"  CNJs com Vara mudada:        {len(cnjs_vara)}")
    print(f"  CNJs com Atualizado mudado:  {len(cnjs_atu)}")
    print(f"  Interseção:                  {len(cnjs_vara & cnjs_atu)}")
    so_atu = cnjs_atu - cnjs_vara
    so_vara = cnjs_vara - cnjs_atu
    if so_atu:
        print(f"  ⚠ Atualizado mudou SEM Vara mudar: {len(so_atu)}")
        for c in sorted(so_atu)[:5]:
            print(f"      {c}")
    if so_vara:
        print(f"  ⚠ Vara mudou SEM Atualizado mudar: {len(so_vara)}")
        for c in sorted(so_vara)[:5]:
            print(f"      {c}")

    # Distribuição final do campo Vara em POS
    print()
    print("=" * 70)
    print("Distribuição de 'Vara' em POS")
    print("=" * 70)
    n_ord = n_nome = n_vazio = 0
    for cnj in cnjs_pos:
        v = (pos[cnj].get("Vara") or "").strip()
        if not v:
            n_vazio += 1
        elif v.isdigit():
            n_ord += 1
        else:
            n_nome += 1
    print(f"  ordinal: {n_ord}")
    print(f"  nome:    {n_nome}")
    print(f"  vazio:   {n_vazio}")

    print()
    print("=" * 70)
    print("VEREDITO")
    print("=" * 70)
    sucesso = (
        not (cnjs_pre - cnjs_pos)
        and not (cnjs_pos - cnjs_pre)
        and not inesperadas
        and not so_atu
        and not so_vara
        and len(cnjs_vara) == 1087
    )
    if sucesso:
        print(f"✓ Migração íntegra. {len(cnjs_vara)} Varas atualizadas, "
              "demais colunas intactas, mesmo conjunto de CNJs.")
        return 0
    if len(cnjs_vara) != 1087:
        print(f"⚠ Vara mudou em {len(cnjs_vara)} CNJs (esperado 1.087)")
    if inesperadas:
        print(f"⚠ Drift inesperado em {len(inesperadas)} coluna(s)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
