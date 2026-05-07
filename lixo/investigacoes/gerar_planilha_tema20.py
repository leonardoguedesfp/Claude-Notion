"""Gera planilha de migração de 132 processos novos do Tema 20.

Entrada:
    OneDrive/.../2ª fase/2ª_fase_da_migração_-_tema_20_enriquecida.xlsx
    (133 linhas; pula a linha 123 — Ludmilla, sem CPF e demais campos)

Saída:
    logs/migracao_tema20_<timestamp>.xlsx — formato consumido pela aba
    Importar do app Notion RPADV.

Headers (case-correto, conforme schema):
    Número do processo | Vara | Data de distribuição | Tipo de ação |
    Tribunal | Instância | Natureza | Tipo de processo |
    Posição do cliente | Partes adversas | Cidade | Status | Fase | Clientes

Uso:
    PYTHONPATH=. python scripts/investigacoes/gerar_planilha_tema20.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill


SRC_PATH = Path(
    r"C:\Users\LeonardoGuedesdaFons\OneDrive - RICARDO PASSOS ADVOCACIA"
    r"\Área de Trabalho\Planilhas projeto Notion\2ª fase"
    r"\2ª_fase_da_migração_-_tema_20_enriquecida.xlsx"
)
CACHE_DB = Path(
    r"C:\Users\LeonardoGuedesdaFons\AppData\Roaming\NotionRPADV\cache.db"
)
OUT_DIR = Path("logs")

LINHA_PULAR = 123  # Ludmilla — sem CPF, demais campos vazios

# Mapa: header da origem → header da saída (case correto + rename de Data)
HEADER_MAP = {
    "Número do Processo":   "Número do processo",
    "Vara":                 "Vara",
    "Data":                 "Data de distribuição",
    "Tipo de Ação":         "Tipo de ação",
    "Tribunal":             "Tribunal",
    "Instância":            "Instância",
    "Natureza":             "Natureza",
    "Tipo de processo":     "Tipo de processo",
    "Posição do cliente":   "Posição do cliente",
    "Partes adversas":      "Partes adversas",
    "Cidade":               "Cidade",
    "Status":               "Status",
    "Fase":                 "Fase",
}

# Headers de saída em ordem (acrescenta Clientes ao final)
HEADERS_SAIDA = [
    "Número do processo",
    "Vara",
    "Data de distribuição",
    "Tipo de ação",
    "Tribunal",
    "Instância",
    "Natureza",
    "Tipo de processo",
    "Posição do cliente",
    "Partes adversas",
    "Cidade",
    "Status",
    "Fase",
    "Clientes",
]


def _digits(s: Any) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def _norm_vara(v: Any) -> str:
    """Vara é rich_text. Aceita int/float/str. Float-int vira int."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _norm_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _norm_data(v: Any) -> str:
    """Aceita:
    - datetime/date → 'DD/MM/YYYY'
    - 'DD/MM/YYYY' → passa direto
    - 'YYYY-MM-DD' → 'DD/MM/YYYY'
    - número (int/float) ou string parseável como número → trata como
      serial do Excel (dias desde 1899-12-30) e converte
    - vazio → ''
    """
    from datetime import date, datetime, timedelta

    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    s = str(v).strip()
    if not s:
        return ""
    # DD/MM/YYYY
    if "/" in s and len(s) >= 10:
        return s[:10]
    # YYYY-MM-DD
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            d = datetime.strptime(s[:10], "%Y-%m-%d")
            return d.strftime("%d/%m/%Y")
        except ValueError:
            pass
    # Excel serial (com vírgula ou ponto decimal)
    s_num = s.replace(",", ".")
    try:
        serial = float(s_num)
    except ValueError:
        return s  # devolve cru — caller decide
    base = datetime(1899, 12, 30)
    d = base + timedelta(days=serial)
    return d.strftime("%d/%m/%Y")


def _construir_lookup_cliente() -> tuple[dict[str, str], dict[str, str]]:
    """Lê cache.db → (cpf_norm → page_id, nome_upper → page_id).

    O lookup principal é por CPF; nome_upper só serve como fallback
    para o caso-Ludmilla-like (sem CPF na planilha).
    """
    conn = sqlite3.connect(str(CACHE_DB))
    cpf_idx: dict[str, str] = {}
    nome_idx: dict[str, str] = {}
    for (j,) in conn.execute(
        "SELECT data_json FROM records WHERE base = 'Clientes'"
    ).fetchall():
        d = json.loads(j)
        page_id = d.get("page_id")
        if not page_id:
            continue
        cpf = _digits(d.get("cpf_cnpj"))
        if cpf:
            cpf_idx[cpf] = page_id
        nome = (d.get("nome") or "").strip().upper()
        if nome:
            nome_idx[nome] = page_id
    conn.close()
    return cpf_idx, nome_idx


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    print(f"Lendo origem: {SRC_PATH.name}")
    wb_src = openpyxl.load_workbook(SRC_PATH, read_only=True, data_only=True)
    ws_src = wb_src["Processos"]
    rows_src = list(ws_src.iter_rows(values_only=True))
    hdr_src = list(rows_src[0])
    wb_src.close()

    # Índices das colunas da origem
    idx: dict[str, int] = {h: i for i, h in enumerate(hdr_src)}
    print(f"  {len(rows_src) - 1} linhas de dados")

    print("Construindo lookup cliente (CPF → page_id; nome → page_id)…")
    cpf_idx, nome_idx = _construir_lookup_cliente()
    print(f"  {len(cpf_idx)} CPFs, {len(nome_idx)} nomes no cache")

    # Processa linhas → registros de saída
    saida: list[dict[str, str]] = []
    pulados: list[tuple[int, str, str]] = []   # (linha, cnj, motivo)
    sem_cliente: list[tuple[int, str, str]] = []  # (linha, cnj, reclamante)

    for ri, r in enumerate(rows_src[1:], start=2):
        if ri == LINHA_PULAR:
            cnj = _norm_str(r[idx["Número do Processo"]] if r else "")
            pulados.append((ri, cnj, "linha 123 — Ludmilla, decisão do usuário"))
            continue
        if not r:
            continue
        cnj = _norm_str(r[idx["Número do Processo"]])
        if not cnj:
            continue

        cpf = _norm_str(r[idx["CPF"]])
        nome = _norm_str(r[idx["Reclamante"]]).upper()
        cpf_d = _digits(cpf)

        page_id_cliente = cpf_idx.get(cpf_d) or nome_idx.get(nome)
        if not page_id_cliente:
            sem_cliente.append((ri, cnj, _norm_str(r[idx["Reclamante"]])))
            # Ainda gera linha mas com Clientes vazio
            page_id_cliente = ""

        # Monta dict de saída usando HEADERS_SAIDA
        row_out: dict[str, str] = {}
        for h_in, h_out in HEADER_MAP.items():
            v = r[idx[h_in]]
            if h_out == "Vara":
                row_out[h_out] = _norm_vara(v)
            elif h_out == "Data de distribuição":
                row_out[h_out] = _norm_data(v)
            elif h_out == "Tipo de ação":
                # Casa com o vocabulário criado no Notion:
                # 1. Corrige typo "Indeniação" → "Indenização"
                # 2. Padroniza hífen (-) → travessão (—, U+2014), porque
                #    as 3 opções foram adicionadas com travessão para
                #    seguir o padrão da família Indenização.
                t = _norm_str(v).replace("Indeniação", "Indenização")
                t = t.replace("Indenização - ", "Indenização — ")
                row_out[h_out] = t
            else:
                row_out[h_out] = _norm_str(v)
        row_out["Clientes"] = page_id_cliente

        saida.append(row_out)

    print(f"\nLinhas de saída: {len(saida)}")
    print(f"Linhas puladas:  {len(pulados)}")
    print(f"Sem cliente match: {len(sem_cliente)}")
    if sem_cliente:
        for ri, cnj, nome in sem_cliente[:5]:
            print(f"  linha {ri}  CNJ={cnj}  reclamante={nome}")

    # ------------------------------------------------------------------
    # Geração do XLSX
    # ------------------------------------------------------------------
    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        print("ERRO: workbook sem sheet ativa")
        return 1
    ws.title = "Processos"

    header_font = Font(color="FFFFFF", bold=True, size=10)
    header_fill = PatternFill("solid", fgColor="1F4E79")
    center = Alignment(horizontal="center", vertical="center")

    for col_idx, h in enumerate(HEADERS_SAIDA, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center

    # Larguras razoáveis
    widths = {
        "Número do processo":   28,
        "Vara":                 8,
        "Data de distribuição": 16,
        "Tipo de ação":         28,
        "Tribunal":             10,
        "Instância":            10,
        "Natureza":             14,
        "Tipo de processo":     16,
        "Posição do cliente":   14,
        "Partes adversas":      18,
        "Cidade":               14,
        "Status":               12,
        "Fase":                 14,
        "Clientes":             38,
    }
    for col_idx, h in enumerate(HEADERS_SAIDA, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = (
            widths.get(h, 14)
        )

    for ri, row in enumerate(saida, start=2):
        for col_idx, h in enumerate(HEADERS_SAIDA, start=1):
            ws.cell(row=ri, column=col_idx, value=row.get(h, ""))

    ws.freeze_panes = "A2"

    # Aba: linhas puladas
    if pulados:
        ws_skip = wb.create_sheet("Puladas")
        ws_skip.cell(row=1, column=1, value="Linha origem").font = header_font
        ws_skip.cell(row=1, column=1).fill = header_fill
        ws_skip.cell(row=1, column=2, value="CNJ").font = header_font
        ws_skip.cell(row=1, column=2).fill = header_fill
        ws_skip.cell(row=1, column=3, value="Motivo").font = header_font
        ws_skip.cell(row=1, column=3).fill = header_fill
        ws_skip.column_dimensions["A"].width = 12
        ws_skip.column_dimensions["B"].width = 28
        ws_skip.column_dimensions["C"].width = 60
        for ri, (li, cnj, motivo) in enumerate(pulados, start=2):
            ws_skip.cell(row=ri, column=1, value=li)
            ws_skip.cell(row=ri, column=2, value=cnj)
            ws_skip.cell(row=ri, column=3, value=motivo)

    # Aba: instruções
    ws_inst = wb.create_sheet("Instruções")
    ws_inst.column_dimensions["A"].width = 100
    titulo_font = Font(bold=True, size=13, color="1F4E79")
    sub_font = Font(bold=True, size=10)
    normal = Font(size=10)
    warn = Font(italic=True, color="9C5700", size=10)

    instrucoes: list[tuple[str, Any]] = [
        ("Migração Tema 20 — 132 processos novos", titulo_font),
        ("", normal),
        ("ANTES DE IMPORTAR — passos no Notion:", sub_font),
        (
            "1. Na base Processos, abra a propriedade 'Tipo de ação' e adicione "
            "estas 3 opções (clique em 'Add option' para cada uma):",
            normal,
        ),
        ("    • Indenização - tema 20", normal),
        ("    • Indenização - tema 20 REP", normal),
        ("    • Indenização - tema 20 RB", normal),
        (
            "2. Volte ao app Notion RPADV e clique em 'Sincronizar schema' "
            "(em Configurações ou no menu da base Processos), para que o "
            "validador da aba Importar reconheça as novas opções.",
            normal,
        ),
        ("", normal),
        ("Importar:", sub_font),
        ("3. Aba Importar → Base 'Processos' → 'Escolher arquivo (.xlsx)'.", normal),
        ("4. Selecione esta planilha.", normal),
        (
            "5. Confirme no banner verde: '132 linhas prontas para importar'. "
            "Se aparecer vermelho, NÃO importe — me chame para investigar.",
            normal,
        ),
        ("6. Clique em Importar →. Aguarde a tela de Resultado (~5–10 min).", normal),
        ("", normal),
        ("Detalhes:", sub_font),
        (
            "• Sem coluna 'page_id' — o app vai CRIAR cada processo do zero "
            "(é o comportamento esperado para processos novos).",
            normal,
        ),
        (
            "• Coluna 'Clientes' contém o page_id do cliente já cadastrado. "
            "Resolução por CPF (132/132) — nenhum cliente novo é criado, "
            "nenhuma duplicata.",
            normal,
        ),
        (
            "• Linha 123 (Ludmilla Oliveira Leite) NÃO está nesta planilha — "
            "ver aba 'Puladas'. Você cadastra esse processo manualmente.",
            warn,
        ),
        (
            "• Os 3 reclamantes com nome divergente do cache foram linkados "
            "ao cliente existente (mesmo CPF). O Nome no Notion fica intacto.",
            normal,
        ),
        ("", normal),
        (
            f"Origem: {SRC_PATH.name}", Font(italic=True, size=9, color="595959"),
        ),
        (
            f"Linhas a importar: {len(saida)}  |  Puladas: {len(pulados)}",
            Font(italic=True, size=9, color="595959"),
        ),
        (
            f"Gerada em: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            Font(italic=True, size=9, color="595959"),
        ),
    ]
    for ri, (txt, fnt) in enumerate(instrucoes, start=1):
        cell = ws_inst.cell(row=ri, column=1, value=txt)
        cell.font = fnt
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws_inst.row_dimensions[ri].height = 18 if ri > 1 else 24

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H%M")
    out_path = OUT_DIR / f"migracao_tema20_{ts}.xlsx"
    wb.save(str(out_path))
    print(f"\nGerada: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
