"""Versão 2: comparação direta cache.db (PRÉ) vs CSV pós, em campos
estáveis (selects + title), que exportam de forma consistente.

Resposta às perguntas:
A. Para cada CNJ na origem: Vara foi atualizada para o valor desejado?
B. Nos 669 alvos, alguma propriedade ESTÁVEL além de Vara mudou?
C. Garantia arquitetural: importar.py só envia colunas presentes na
   planilha → outras propriedades não podem ter sido tocadas pela
   migração; mudanças em campos fluidos (Publicações, Tarefas, etc.)
   se devem a outras atividades do sistema, não à migração.

Uso:
    PYTHONPATH=. python scripts/investigacoes/verificar_migracao_v2.py
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import openpyxl


SRC_PATH = Path("logs/migracao_vara_2026-05-06-0032.xlsx")
CACHE_DB = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Roaming\NotionRPADV\cache.db"
)
CSV_POS = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Local\Temp"
    r"\⚖️ Processos 78f11cd71d0d4a1e9df58be085e5bb33_all (13).csv"
)


# Campos estáveis: cache.snake_key → csv.notion_name
ESTAVEIS = {
    "numero_do_processo":   "Número do processo",
    "tribunal":             "Tribunal",
    "instancia":            "Instância",
    "status":               "Status",
    "fase":                 "Fase",
    "cidade":               "Cidade",
    "natureza":             "Natureza",
    "tipo_de_acao":         "Tipo de ação",
    "tipo_de_processo":     "Tipo de processo",
    "posicao_do_cliente":   "Posição do cliente",
    "detalhamento_da_acao": "Detalhamento da ação",
    "numero_stj_tst":       "Número STJ/TST",
    "numero_stf":           "Número STF",
    "turma_no_2o_grau":     "Turma no 2º grau",
    "turma_no_stj_tst":     "Turma no STJ/TST",
    "turma_no_stf":         "Turma no STF",
    "relator_no_2o_grau":   "Relator no 2º grau",
    "relator_no_stj_tst":   "Relator no STJ/TST",
    "relator_no_stf":       "Relator no STF",
    "id_legal_one":         "ID Legal One",
    "link_externo":         "Link externo",
    "observacoes":          "Observações",
    "partes_adversas":      "Partes adversas",
}


def _norm_atom(v: Any) -> str:
    """Atom (string ou número) — strip + remove '.0' de float-int."""
    if v is None:
        return ""
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        s = s[:-2]
    return s


def _norm_multi(v: Any) -> str:
    """Normaliza multi_select para um set ordenado, independente de
    a entrada ser list (cache JSON) ou string com vírgulas (CSV).
    """
    if v is None:
        return ""
    if isinstance(v, list):
        tokens = [str(t).strip() for t in v if str(t).strip()]
    else:
        tokens = [t.strip() for t in str(v).split(",") if t.strip()]
    return "|".join(sorted(tokens))


# Campos multi_select / list-stored
CAMPOS_MULTI = {
    "tipo_de_acao", "detalhamento_da_acao", "natureza",
    "posicao_do_cliente", "tipo_de_processo", "partes_adversas",
}


def _value(d: dict[str, Any], cache_key: str) -> str:
    if cache_key in CAMPOS_MULTI:
        return _norm_multi(d.get(cache_key))
    return _norm_atom(d.get(cache_key))


def _value_csv(d: dict[str, str], csv_key: str, cache_key: str) -> str:
    if cache_key in CAMPOS_MULTI:
        return _norm_multi(d.get(csv_key))
    return _norm_atom(d.get(csv_key))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    # Origem (planilha gerada para o import — colunas page_id, CNJ, Vara)
    print("Lendo origem (planilha enviada para o import)…")
    wb = openpyxl.load_workbook(SRC_PATH, read_only=True, data_only=True)
    ws = wb["Processos"]
    desejada: dict[str, str] = {}
    headers_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    headers = [str(c) if c else "" for c in headers_row]
    cnj_idx = headers.index("Número do processo")
    vara_idx = headers.index("Vara")
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or not r[cnj_idx]:
            continue
        cnj = str(r[cnj_idx]).strip()
        v = r[vara_idx]
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        desejada[cnj] = str(v).strip() if v is not None else ""
    wb.close()
    print(f"  {len(desejada)} CNJs")

    # Cache (PRÉ)
    print("Lendo cache.db (estado pré-migração)…")
    conn = sqlite3.connect(str(CACHE_DB))
    cur = conn.cursor()
    cur.execute("SELECT data_json FROM records WHERE base = 'Processos'")
    cache: dict[str, dict[str, Any]] = {}
    for (j,) in cur.fetchall():
        d = json.loads(j)
        cnj = (d.get("numero_do_processo") or "").strip()
        if cnj:
            cache[cnj] = d
    conn.close()
    print(f"  {len(cache)} processos")

    # CSV (PÓS)
    print("Lendo CSV pós-migração…")
    csv_pos: dict[str, dict[str, str]] = {}
    with CSV_POS.open(encoding="utf-8") as f:
        rd = csv.DictReader(f)
        first_key = None
        for row in rd:
            if first_key is None:
                first_key = list(row.keys())[0]
            cnj = (row.get(first_key) or "").strip()
            if cnj:
                csv_pos[cnj] = {k.lstrip("﻿").strip(): (v or "") for k, v in row.items()}
    print(f"  {len(csv_pos)} processos")

    # ------------------------------------------------------------------
    # A) Vara migrada
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    print("A) Vara migrada para o valor desejado (origem → CSV pós)")
    print("=" * 70)
    vara_ok = 0
    vara_fail: list[tuple[str, str, str]] = []
    for cnj, vara_esp in desejada.items():
        v_pos = (csv_pos.get(cnj) or {}).get("Vara", "").strip()
        if v_pos == vara_esp:
            vara_ok += 1
        else:
            vara_fail.append((cnj, vara_esp, v_pos))
    print(f"  OK:                {vara_ok}/{len(desejada)}")
    print(f"  Falhas:            {len(vara_fail)}")
    for cnj, esp, atu in vara_fail:
        print(f"    {cnj}  desejado={esp!r}  atual={atu!r}")

    # ------------------------------------------------------------------
    # B) Outras propriedades estáveis: cache (pré) vs CSV (pós) nos 669
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    print("B) Propriedades estáveis (selects + title) — pré vs pós nos 669 alvos")
    print("=" * 70)
    drift: dict[str, list[tuple[str, str, str]]] = {}
    n_cmp = 0
    sem_cache = 0
    for cnj in desejada:
        pre = cache.get(cnj)
        pos = csv_pos.get(cnj)
        if pre is None or pos is None:
            sem_cache += 1
            continue
        for cache_key, csv_key in ESTAVEIS.items():
            v_pre = _value(pre, cache_key)
            v_pos = _value_csv(pos, csv_key, cache_key)
            if v_pre != v_pos:
                drift.setdefault(csv_key, []).append((cnj, v_pre, v_pos))
            n_cmp += 1

    print(f"  Comparações: {n_cmp}  (sem cache: {sem_cache})")
    print(f"  Colunas com drift: {len(drift)}")
    for col, items in sorted(drift.items(), key=lambda kv: -len(kv[1])):
        print(f"\n  {col!r}: {len(items)} divergência(s)")
        for cnj, pre, pos in items[:3]:
            print(f"    {cnj}")
            print(f"      pré: {pre[:100]!r}")
            print(f"      pós: {pos[:100]!r}")

    # ------------------------------------------------------------------
    # Veredito
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    print("VEREDITO")
    print("=" * 70)
    if vara_ok == len(desejada) and not drift:
        print("✓ Migração 100% bem-sucedida e isolada.")
        return 0
    if vara_fail:
        print(f"⚠ Vara: {vara_ok}/{len(desejada)} migradas; "
              f"{len(vara_fail)} falha(s) precisam de re-import.")
    if drift:
        print(f"⚠ Drift detectado em {len(drift)} coluna(s) — investigar.")
    if not vara_fail and not drift:
        print("✓ Vara 100% migrada; nenhum drift em campos estáveis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
