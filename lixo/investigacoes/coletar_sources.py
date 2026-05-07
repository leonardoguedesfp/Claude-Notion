"""Consulta DataJud e dump _source bruto para investigação Turma+Relator.

Faz UMA chamada por CNJ ao endpoint mais relevante para o grau alvo:
- TRT/10 2º grau → endpoint trt10 (retorna G1+G2)
- TST            → endpoint tst   (retorna SUP/GS)
- STJ            → endpoint stj   (retorna GS)
- TJDFT 2º grau  → endpoint tjdft (retorna G1+G2)
- Pista          → endpoint do tribunal cadastrado

Total de chamadas: 15 (dentro do orçamento da investigação).

Uso:
    DATAJUD_APIKEY=... python scripts/investigacoes/coletar_sources.py
    (sem env var, usa o APIKey público padrão do DataJudClient)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from notion_rpadv.services.datajud_client import (
    DataJudAPIError,
    DataJudClient,
    endpoint_de_tribunal,
)


AMOSTRAS_PATH = Path("scripts/investigacoes/_dados/amostras.json")
OUT_DIR = Path("scripts/investigacoes/_dados/sources")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _endpoint_alvo(tribunal: str, instancia: str) -> str | None:
    """Endpoint a chamar dado tribunal/instância cadastrado.

    Para STJ/TST, vai direto no tribunal superior (ignora endpoint do
    tribunal de origem) — o objetivo é inspecionar o _source do grau
    superior, e a chamada superior já o retorna.
    """
    if instancia == "STJ":
        return "stj"
    if instancia == "TST":
        return "tst"
    return endpoint_de_tribunal(tribunal)


def _slug(cnj: str) -> str:
    return cnj.replace("-", "_").replace(".", "_")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    with AMOSTRAS_PATH.open(encoding="utf-8") as f:
        amostras: dict[str, list[dict[str, Any]]] = json.load(f)

    client = DataJudClient()

    total_chamadas = 0
    resumo: list[dict[str, Any]] = []
    for grupo, lista in amostras.items():
        print(f"\n--- {grupo} ({len(lista)} CNJs) ---")
        for item in lista:
            cnj = item["cnj"]
            trib = item["tribunal"]
            inst = item["instancia"]
            ep = _endpoint_alvo(trib, inst)
            if ep is None:
                print(f"  [skip] {cnj} — endpoint indefinido (trib={trib})")
                continue
            print(f"  → {cnj} ({trib}/{inst}) → endpoint={ep}")
            try:
                sources = client.consultar(cnj, ep)
            except DataJudAPIError as exc:
                print(f"      ERRO: {exc}")
                resumo.append({
                    "grupo": grupo, "cnj": cnj, "tribunal": trib,
                    "instancia": inst, "endpoint": ep,
                    "n_sources": 0, "erro": str(exc),
                })
                total_chamadas += 1
                continue

            total_chamadas += 1

            print(f"      {len(sources)} _source(s)")
            for s in sources:
                print(f"        grau={s.get('grau')!r}  "
                      f"oj.nome={(s.get('orgaoJulgador') or {}).get('nome')!r}")

            # Salva em arquivo individual por CNJ
            slug = _slug(cnj)
            out_path = OUT_DIR / f"{grupo}__{slug}__{ep}.json"
            with out_path.open("w", encoding="utf-8") as f:
                json.dump({
                    "cnj":         cnj,
                    "tribunal":    trib,
                    "instancia":   inst,
                    "endpoint":    ep,
                    "n_sources":   len(sources),
                    "sources":     sources,
                    "notion": {
                        "turma_2g":   item.get("turma_2g_notion"),
                        "turma_st":   item.get("turma_st_notion"),
                        "relator_2g": item.get("relator_2g_notion"),
                        "relator_st": item.get("relator_st_notion"),
                    },
                }, f, ensure_ascii=False, indent=2)

            resumo.append({
                "grupo": grupo, "cnj": cnj, "tribunal": trib,
                "instancia": inst, "endpoint": ep,
                "n_sources": len(sources),
                "graus_retornados": [s.get("grau") for s in sources],
                "ojs_por_grau": [
                    {"grau": s.get("grau"),
                     "oj_nome": (s.get("orgaoJulgador") or {}).get("nome"),
                     "oj_codigo": (s.get("orgaoJulgador") or {}).get("codigo")}
                    for s in sources
                ],
                "out_file": str(out_path),
            })

    resumo_path = OUT_DIR / "_resumo.json"
    with resumo_path.open("w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    print(f"\nTotal de chamadas à API: {total_chamadas}")
    print(f"Resumo: {resumo_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
