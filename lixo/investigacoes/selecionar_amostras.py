"""Seleciona CNJs amostrais da auditoria DataJUD para investigar Turma+Relator.

Critérios (user request):
- TRT/10 2º grau OK + Notion tem Relator+Turma → 5 CNJs
- TST OK + Notion tem Relator+Turma STJ/TST → 3 CNJs
- STJ OK + Notion tem Relator+Turma STJ/TST → 2 CNJs
- TJDFT 2º grau (qualquer diag OK/Parcial) + Notion tem Relator+Turma → 3 CNJs
- Pista positiva (heurística atual detectou Turma): 2 CNJs específicos

Uso:
    python scripts/investigacoes/selecionar_amostras.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any


DATA_PATH = Path("scripts/investigacoes/_dados/auditoria_rows.json")
OUT_PATH = Path("scripts/investigacoes/_dados/amostras.json")

CNJ_PISTA_TJSP = "2275121-45.2025.8.26.0000"
CNJ_PISTA_TJSC = "5003942-75.2025.8.24.0020"


def _has_value(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    return bool(s) and s.lower() != "none"


def _matches(
    row: dict[str, Any],
    *,
    tribunal: str | None = None,
    instancia: str | None = None,
    diag_in: tuple[str, ...] | None = None,
    needs_turma_2g_notion: bool = False,
    needs_relator_2g_notion: bool = False,
    needs_turma_st_notion: bool = False,
    needs_relator_st_notion: bool = False,
) -> bool:
    if tribunal and (row.get("Tribunal ▸ atual") or "").strip() != tribunal:
        return False
    if instancia and (row.get("Instância ▸ atual") or "").strip() != instancia:
        return False
    if diag_in is not None:
        diag = (row.get("Diagnóstico") or "").strip()
        if diag not in diag_in:
            return False
    if needs_turma_2g_notion and not _has_value(row.get("Turma no 2º grau ▸ atual")):
        return False
    if needs_relator_2g_notion and not _has_value(row.get("Relator no 2º grau ▸ atual")):
        return False
    if needs_turma_st_notion and not _has_value(row.get("Turma no STJ/TST ▸ atual")):
        return False
    if needs_relator_st_notion and not _has_value(row.get("Relator no STJ/TST ▸ atual")):
        return False
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    with DATA_PATH.open(encoding="utf-8") as f:
        rows: list[dict[str, Any]] = json.load(f)

    # Determinismo
    rng = random.Random(20260505)

    # Resumo por tribunal/instância (sanity)
    print("=" * 60)
    print("RESUMO POR (Tribunal, Instância) com Diagnóstico OK")
    print("=" * 60)
    counts: dict[tuple[str, str], int] = {}
    for r in rows:
        if (r.get("Diagnóstico") or "").strip() == "OK":
            k = ((r.get("Tribunal ▸ atual") or "").strip(),
                 (r.get("Instância ▸ atual") or "").strip())
            counts[k] = counts.get(k, 0) + 1
    for (t, i), n in sorted(counts.items()):
        print(f"  {t!r:>15} | {i!r:>10}  → {n}")

    # Quantos com Notion populado (denominador de cada amostra)
    print()
    print("=" * 60)
    print("CANDIDATOS DISPONÍVEIS")
    print("=" * 60)

    candidatos = {
        "trt10_g2": [
            r for r in rows
            if _matches(r, tribunal="TRT/10", instancia="2º grau",
                        diag_in=("OK",),
                        needs_turma_2g_notion=True,
                        needs_relator_2g_notion=True)
        ],
        "tst": [
            r for r in rows
            if _matches(r, instancia="TST", diag_in=("OK",),
                        needs_turma_st_notion=True,
                        needs_relator_st_notion=True)
        ],
        "stj": [
            r for r in rows
            if _matches(r, instancia="STJ", diag_in=("OK",),
                        needs_turma_st_notion=True,
                        needs_relator_st_notion=True)
        ],
        "tjdft_g2": [
            r for r in rows
            if _matches(r, tribunal="TJDFT", instancia="2º grau",
                        diag_in=("OK", "Dados parciais"),
                        needs_turma_2g_notion=True,
                        needs_relator_2g_notion=True)
        ],
    }
    for k, v in candidatos.items():
        print(f"  {k}: {len(v)} candidatos")

    # Fallback: se algum grupo não tem candidato com ambos populados,
    # relaxa para apenas um deles.
    def _fallback_relator_only(criterio: dict[str, Any]) -> list[dict[str, Any]]:
        return [r for r in rows if _matches(r, **criterio)]

    if not candidatos["tst"]:
        print("  >>> tst sem candidatos com ambos; relaxando p/ apenas Relator OU Turma")
        candidatos["tst"] = _fallback_relator_only({
            "instancia": "TST", "diag_in": ("OK",),
            "needs_relator_st_notion": True,
        }) or _fallback_relator_only({
            "instancia": "TST", "diag_in": ("OK",),
            "needs_turma_st_notion": True,
        }) or _fallback_relator_only({
            "instancia": "TST", "diag_in": ("OK",),
        })
    if not candidatos["stj"]:
        print("  >>> stj sem candidatos com ambos; relaxando")
        candidatos["stj"] = _fallback_relator_only({
            "instancia": "STJ", "diag_in": ("OK",),
            "needs_relator_st_notion": True,
        }) or _fallback_relator_only({
            "instancia": "STJ", "diag_in": ("OK",),
            "needs_turma_st_notion": True,
        }) or _fallback_relator_only({
            "instancia": "STJ", "diag_in": ("OK",),
        })

    # Sortear N de cada
    target_n = {"trt10_g2": 5, "tst": 3, "stj": 2, "tjdft_g2": 3}
    amostras: dict[str, list[dict[str, Any]]] = {}
    for k, lista in candidatos.items():
        n_alvo = target_n[k]
        if len(lista) <= n_alvo:
            amostras[k] = lista
        else:
            amostras[k] = rng.sample(lista, n_alvo)

    # Pista positiva
    pista = [
        r for r in rows
        if (r.get("Número do processo ▸ atual") or "").strip()
           in (CNJ_PISTA_TJSP, CNJ_PISTA_TJSC)
    ]
    amostras["pista_positiva"] = pista

    # Saída
    print()
    print("=" * 60)
    print("AMOSTRA SELECIONADA")
    print("=" * 60)

    out: dict[str, list[dict[str, Any]]] = {}
    for k, lista in amostras.items():
        print(f"\n{k}: {len(lista)} processos")
        out_k: list[dict[str, Any]] = []
        for r in lista:
            cnj = (r.get("Número do processo ▸ atual") or "").strip()
            trib = (r.get("Tribunal ▸ atual") or "").strip()
            inst = (r.get("Instância ▸ atual") or "").strip()
            turma_2g = r.get("Turma no 2º grau ▸ atual")
            turma_st = r.get("Turma no STJ/TST ▸ atual")
            relator_2g = r.get("Relator no 2º grau ▸ atual")
            relator_st = r.get("Relator no STJ/TST ▸ atual")
            print(f"  {cnj}  |  {trib}/{inst}")
            print(f"     Turma 2g notion: {turma_2g}")
            print(f"     Turma ST notion: {turma_st}")
            print(f"     Relator 2g     : {relator_2g}")
            print(f"     Relator ST     : {relator_st}")
            out_k.append({
                "cnj":         cnj,
                "tribunal":    trib,
                "instancia":   inst,
                "turma_2g_notion":    turma_2g,
                "turma_st_notion":    turma_st,
                "relator_2g_notion":  relator_2g,
                "relator_st_notion":  relator_st,
                "diagnostico":        r.get("Diagnóstico"),
                "fontes_meta":        r.get("__datajud_meta"),
            })
        out[k] = out_k

    # Total de chamadas que serão feitas
    total_cnjs = sum(len(v) for v in out.values())
    print(f"\nTotal de CNJs amostrados: {total_cnjs}")
    # Cada CNJ gera N chamadas (1 por endpoint candidato)
    # TRT/10 G2 = 1 ep; TST = 2 eps (trt10 + tst se Tribunal!=TST, OU 1 se ==TST);
    # STJ = idem; TJDFT G2 = 1 ep; pista = 1 ep
    print(f"Chamadas estimadas (simplificando, ~1-2 por CNJ): {total_cnjs}-{total_cnjs*2}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nAmostras salvas em {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
