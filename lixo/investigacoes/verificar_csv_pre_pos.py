"""Compara dois CSVs do Notion (mesma DB, formatos idênticos):
PRÉ-migração (14) vs PÓS-migração (13).

Pergunta: a DB está íntegra? Ou seja, mudou apenas o que esperávamos
(Vara nos 669 alvos + Atualizado em desses mesmos), e o resto está igual?

Saída:
- Resumo por coluna: quantas linhas mudaram, com amostra das primeiras
- Listagem dos CNJs com mudança em qualquer coluna inesperada
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


PRE  = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Local\Temp"
    r"\⚖️ Processos 78f11cd71d0d4a1e9df58be085e5bb33_all (14).csv"
)
POS  = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Local\Temp"
    r"\⚖️ Processos 78f11cd71d0d4a1e9df58be085e5bb33_all (13).csv"
)


def _load(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    """Lê CSV → (headers, dict CNJ → row dict)."""
    with path.open(encoding="utf-8") as f:
        rd = csv.reader(f)
        headers = next(rd)
        # Strip BOM da primeira coluna
        headers[0] = headers[0].lstrip("﻿")
        out: dict[str, dict[str, str]] = {}
        for row in rd:
            if not row:
                continue
            cnj = row[0].strip()
            if not cnj:
                continue
            d = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
            out[cnj] = d
    return headers, out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    print(f"PRE: {PRE.name}")
    print(f"POS: {POS.name}")
    print()

    h_pre, pre = _load(PRE)
    h_pos, pos = _load(POS)
    print(f"  PRE: {len(pre)} processos, {len(h_pre)} colunas")
    print(f"  POS: {len(pos)} processos, {len(h_pos)} colunas")

    # Sanidade: mesmas colunas?
    if h_pre != h_pos:
        print("  ⚠ Headers diferentes:")
        diff_only_pre = set(h_pre) - set(h_pos)
        diff_only_pos = set(h_pos) - set(h_pre)
        if diff_only_pre:
            print(f"    só em PRE: {diff_only_pre}")
        if diff_only_pos:
            print(f"    só em POS: {diff_only_pos}")

    headers = [h for h in h_pre if h in h_pos]

    # Sanidade: CNJs presentes em ambos?
    cnjs_pre = set(pre)
    cnjs_pos = set(pos)
    print(f"  CNJs em ambos: {len(cnjs_pre & cnjs_pos)}")
    if cnjs_pre - cnjs_pos:
        print(f"  ⚠ CNJs apenas em PRE: {len(cnjs_pre - cnjs_pos)}")
        for c in list(cnjs_pre - cnjs_pos)[:5]:
            print(f"      {c}")
    if cnjs_pos - cnjs_pre:
        print(f"  ⚠ CNJs apenas em POS: {len(cnjs_pos - cnjs_pre)}")
        for c in list(cnjs_pos - cnjs_pre)[:5]:
            print(f"      {c}")

    # ------------------------------------------------------------------
    # Comparação coluna por coluna
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    print("Mudanças por coluna (PRE → POS), ignorando linhas iguais")
    print("=" * 70)
    drift: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    cnjs_comuns = sorted(cnjs_pre & cnjs_pos)
    for cnj in cnjs_comuns:
        rp, rq = pre[cnj], pos[cnj]
        for col in headers:
            v_pre = (rp.get(col) or "").strip()
            v_pos = (rq.get(col) or "").strip()
            if v_pre != v_pos:
                drift[col].append((cnj, v_pre, v_pos))

    print(f"\n{'COLUNA':<45}  {'#mudanças':>10}")
    print("-" * 60)
    for col in headers:
        n = len(drift.get(col, []))
        marker = ""
        if col == "Vara":
            marker = "  ← intencional (migração)"
        elif col == "Atualizado em":
            marker = "  ← bump esperado pelo update"
        elif col in ("Publicações",):
            marker = "  ← pode mudar por sync do leitor"
        print(f"  {col:<45}  {n:>10}{marker}")

    # ------------------------------------------------------------------
    # Foco: outras colunas (não Vara, não Atualizado em) mudaram?
    # ------------------------------------------------------------------
    inesperadas = [
        c for c in headers
        if c not in ("Vara", "Atualizado em") and drift.get(c)
    ]
    print()
    print("=" * 70)
    print("Mudanças INESPERADAS (fora de Vara e Atualizado em)")
    print("=" * 70)
    if not inesperadas:
        print("  ✓ Nenhuma. Todas as outras colunas estão idênticas entre PRE e POS.")
    else:
        for col in inesperadas:
            items = drift[col]
            print(f"\n  Coluna {col!r}: {len(items)} mudança(s)")
            for cnj, vp, vq in items[:3]:
                print(f"    {cnj}")
                print(f"      pré: {vp[:120]!r}")
                print(f"      pós: {vq[:120]!r}")
            if len(items) > 3:
                print(f"    … (+{len(items) - 3} mais)")

    # ------------------------------------------------------------------
    # Cruzamento: mudanças em Vara batem com migração esperada?
    # ------------------------------------------------------------------
    vara_drift = drift.get("Vara", [])
    atu_drift = drift.get("Atualizado em", [])
    print()
    print("=" * 70)
    print("Vara vs Atualizado em (deveriam coincidir nos 669 alvos)")
    print("=" * 70)
    cnjs_vara_mudou = {c for c, _, _ in vara_drift}
    cnjs_atu_mudou = {c for c, _, _ in atu_drift}
    print(f"  CNJs com Vara mudada:        {len(cnjs_vara_mudou)}")
    print(f"  CNJs com Atualizado mudado:  {len(cnjs_atu_mudou)}")
    print(f"  Interseção:                  {len(cnjs_vara_mudou & cnjs_atu_mudou)}")
    so_atu = cnjs_atu_mudou - cnjs_vara_mudou
    so_vara = cnjs_vara_mudou - cnjs_atu_mudou
    if so_atu:
        print(f"  ⚠ Atualizado mudou SEM Vara mudar: {len(so_atu)}")
        for c in sorted(so_atu)[:5]:
            print(f"      {c}")
    if so_vara:
        print(f"  ⚠ Vara mudou SEM Atualizado mudar: {len(so_vara)}")
        for c in sorted(so_vara)[:5]:
            print(f"      {c}")

    # ------------------------------------------------------------------
    # Veredito
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    print("VEREDITO")
    print("=" * 70)
    if not inesperadas and not so_atu and not so_vara:
        print("✓ DB ÍNTEGRA. Mudanças isoladas exatamente em Vara + "
              "Atualizado em, no mesmo conjunto de processos.")
        return 0
    print("⚠ Há mudanças além do esperado — verificar listas acima.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
