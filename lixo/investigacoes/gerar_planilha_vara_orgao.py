"""Gera XLSX de migração Vara → nome completo do órgão.

Entrada:
    OneDrive/.../2ª fase/2ª fase da migração - Varas.xlsx
    (aba 'Tabela', colunas: CNJ | Vara atual | Órgão proposto)

Saída:
    logs/migracao_vara_orgao_<ts>.xlsx
    Headers: page_id | Número do processo | Vara
    onde Vara = 'Órgão proposto' (ex.: '10ª Vara Cível de Brasília')

Page_id resolvido via inventário em
    scripts/investigacoes/_dados/reconciliacao_vara/processos_inventario.json
(que já cobre os 1.241 processos lidos do Notion).

Uso:
    PYTHONPATH=. python scripts/investigacoes/gerar_planilha_vara_orgao.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill


SRC = Path(
    r"C:\Users\LeonardoGuedesdaFons\OneDrive - RICARDO PASSOS ADVOCACIA"
    r"\Área de Trabalho\Planilhas projeto Notion\2ª fase"
    r"\2ª fase da migração - Varas.xlsx"
)
INV = Path(
    "scripts/investigacoes/_dados/reconciliacao_vara/processos_inventario.json"
)
OUT_DIR = Path("logs")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    print(f"Lendo origem: {SRC.name}")
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb["Tabela"]
    rows: list[tuple[str, str]] = []  # (cnj, orgao)
    for ri, r in enumerate(ws.iter_rows(values_only=True), start=1):
        if ri == 1:
            continue
        if not r or not r[0]:
            continue
        cnj = str(r[0]).strip()
        orgao = str(r[2]).strip() if r[2] is not None else ""
        if not orgao:
            continue
        rows.append((cnj, orgao))
    wb.close()
    print(f"  {len(rows)} linhas com Órgão proposto")

    print(f"Lendo inventário: {INV}")
    with INV.open(encoding="utf-8") as f:
        inv = json.load(f)
    cnj_to_pageid: dict[str, str] = {
        p["cnj"]: p["uuid"] for p in inv if p.get("cnj") and p.get("uuid")
    }
    print(f"  {len(cnj_to_pageid)} CNJ → page_id")

    matched: list[tuple[str, str, str]] = []  # page_id, cnj, orgao
    missing: list[tuple[str, str]] = []        # cnj, orgao
    for cnj, orgao in rows:
        pid = cnj_to_pageid.get(cnj)
        if pid:
            matched.append((pid, cnj, orgao))
        else:
            missing.append((cnj, orgao))
    print(f"  matched: {len(matched)}  /  missing: {len(missing)}")

    # ------------------------------------------------------------------
    # Gera XLSX
    # ------------------------------------------------------------------
    out = openpyxl.Workbook()
    main_ws = out.active
    if main_ws is None:
        print("ERRO: workbook sem sheet ativa")
        return 1
    main_ws.title = "Processos"

    header_font = Font(color="FFFFFF", bold=True, size=10)
    header_fill = PatternFill("solid", fgColor="1F4E79")
    center = Alignment(horizontal="center", vertical="center")

    headers = ["page_id", "Número do processo", "Vara"]
    for col_idx, h in enumerate(headers, start=1):
        cell = main_ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
    main_ws.column_dimensions["A"].width = 38
    main_ws.column_dimensions["B"].width = 28
    main_ws.column_dimensions["C"].width = 50  # nome de órgão é longo

    for ri, (pid, cnj, orgao) in enumerate(matched, start=2):
        main_ws.cell(row=ri, column=1, value=pid)
        main_ws.cell(row=ri, column=2, value=cnj)
        main_ws.cell(row=ri, column=3, value=orgao)
    main_ws.freeze_panes = "A2"

    if missing:
        ws_miss = out.create_sheet("CNJs sem page_id")
        ws_miss.cell(row=1, column=1, value="CNJ").font = header_font
        ws_miss.cell(row=1, column=1).fill = header_fill
        ws_miss.cell(row=1, column=2, value="Órgão proposto").font = header_font
        ws_miss.cell(row=1, column=2).fill = header_fill
        ws_miss.column_dimensions["A"].width = 28
        ws_miss.column_dimensions["B"].width = 50
        for ri, (cnj, orgao) in enumerate(missing, start=2):
            ws_miss.cell(row=ri, column=1, value=cnj)
            ws_miss.cell(row=ri, column=2, value=orgao)

    ws_inst = out.create_sheet("Instruções")
    ws_inst.column_dimensions["A"].width = 100
    titulo = Font(bold=True, size=13, color="1F4E79")
    sub = Font(bold=True, size=10)
    norm = Font(size=10)
    italic = Font(italic=True, size=9, color="595959")
    inst: list[tuple[str, Any]] = [
        ("Migração Vara → nome completo do órgão (1.087 processos)", titulo),
        ("", norm),
        ("Antes de importar:", sub),
        (
            "1. (recomendado) Exporte um snapshot atual da base Processos "
            "em CSV para servir de baseline da verificação pré/pós.",
            norm,
        ),
        ("", norm),
        ("Importar:", sub),
        ("2. Aba Importar planilha → Base 'Processos'.", norm),
        ("3. Escolher arquivo (.xlsx) → selecione esta planilha.", norm),
        (
            f"4. Confirme no banner: '{len(matched)} linhas prontas para importar'.",
            norm,
        ),
        ("5. Clique em Importar →. Aguarde a tela de Resultado.", norm),
        ("", norm),
        ("Detalhes:", sub),
        (
            "• Os 1.087 processos já existem (resolvido por page_id) — "
            "vamos UPDATE, não CREATE. O bug do create_page do app não "
            "atinge esta migração.",
            norm,
        ),
        (
            "• Vara é rich_text (texto livre). Aceita 'Indenização — I' "
            "ou '10ª Vara Cível de Brasília' indistintamente — nenhum "
            "schema sync prévio é necessário.",
            norm,
        ),
        (
            "• Esperado mudar 1.087 valores em 'Vara' + bumpar "
            "'Atualizado em' nos mesmos. Outras 36 colunas: zero alteração.",
            norm,
        ),
        ("", norm),
        (f"Origem: {SRC.name}", italic),
        (
            f"Linhas a importar: {len(matched)}  |  CNJs sem page_id: {len(missing)}",
            italic,
        ),
        (f"Gerada em: {datetime.now().strftime('%Y-%m-%d %H:%M')}", italic),
    ]
    for ri, (txt, fnt) in enumerate(inst, start=1):
        cell = ws_inst.cell(row=ri, column=1, value=txt)
        cell.font = fnt
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws_inst.row_dimensions[ri].height = 18 if ri > 1 else 24

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H%M")
    out_path = OUT_DIR / f"migracao_vara_orgao_{ts}.xlsx"
    out.save(str(out_path))
    print(f"\nGerada: {out_path}")
    print(f"  Aba 'Processos': {len(matched)} linhas prontas")
    if missing:
        print(f"  Aba 'CNJs sem page_id': {len(missing)} para revisão")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
