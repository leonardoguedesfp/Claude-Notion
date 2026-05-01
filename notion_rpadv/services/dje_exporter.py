"""Writer xlsx pras publicações DJEN coletadas pelo ``dje_client``.

Fase 1: empilha todas as linhas em uma única aba ``Publicacoes``.
Não deduplica, não traduz nomes de coluna, não converte tipos.
Arrays viram JSON string com ``ensure_ascii=False`` (preserva acentos
em destinatários, advogados de outros polos, etc.).

Naming: ``Publicacoes_DJEN_{dd.mm.aa_inicio}_a_{dd.mm.aa_fim}_v{N}.xlsx``.
Versão auto-incrementa pra nunca sobrescrever — útil quando o operador
roda a mesma data 2× no mesmo dia (refinou critério).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

logger = logging.getLogger("dje.exporter")

SHEET_NAME: str = "Publicacoes"
ANNOTATION_COLUMN: str = "advogado_consultado"


def format_filename(
    data_inicio: date, data_fim: date, version: int,
) -> str:
    """``Publicacoes_DJEN_{dd.mm.aa}_a_{dd.mm.aa}_v{N}.xlsx``."""
    di = data_inicio.strftime("%d.%m.%y")
    df = data_fim.strftime("%d.%m.%y")
    return f"Publicacoes_DJEN_{di}_a_{df}_v{version}.xlsx"


def next_version(
    output_dir: Path, data_inicio: date, data_fim: date,
) -> int:
    """Próxima versão livre pra esse intervalo. v1 quando nada existe;
    v2/v3/... quando arquivos anteriores presentes."""
    v = 1
    while (output_dir / format_filename(data_inicio, data_fim, v)).exists():
        v += 1
    return v


def _resolve_columns(rows: list[dict[str, Any]]) -> list[str]:
    """Ordem de colunas: ``advogado_consultado`` primeiro, depois as
    chaves do JSON da API na ordem em que aparecem no PRIMEIRO item
    retornado (defesa contra schemas que misturam ordem entre chamadas).

    Itens posteriores podem ter chaves novas (defesa contra mudanças do
    DJEN) — essas vão pro fim da lista, na ordem de aparição.
    """
    if not rows:
        return [ANNOTATION_COLUMN]
    seen: set[str] = {ANNOTATION_COLUMN}
    columns: list[str] = [ANNOTATION_COLUMN]
    # Primeiro item dita a ordem principal das chaves do JSON.
    for k in rows[0].keys():
        if k not in seen:
            columns.append(k)
            seen.add(k)
    # Itens subsequentes contribuem só com chaves novas, no final.
    for row in rows[1:]:
        for k in row.keys():
            if k not in seen:
                columns.append(k)
                seen.add(k)
    return columns


def _serialize_cell(value: Any) -> Any:
    """Converte valor decoded pra algo que openpyxl aceita.
    Listas/dicts → JSON string com ensure_ascii=False (preserva acentos).
    None → None (célula vazia). Demais → passa direto."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_publicacoes_xlsx(
    rows: list[dict[str, Any]],
    output_dir: Path,
    data_inicio: date,
    data_fim: date,
) -> Path:
    """Escreve o xlsx no diretório informado, com versionamento
    automático. Retorna o ``Path`` final do arquivo.

    ``output_dir`` é criado se não existir (mas se o caller esperou
    fallback de QFileDialog quando ``output_dir`` é inacessível,
    deve ter resolvido isso ANTES de chamar — esta função só faz
    mkdir simples, sem prompt).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    version = next_version(output_dir, data_inicio, data_fim)
    path = output_dir / format_filename(data_inicio, data_fim, version)

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    columns = _resolve_columns(rows)

    # Header em negrito
    bold = Font(bold=True)
    for col_idx, name in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = bold

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        for col_idx, key in enumerate(columns, start=1):
            value = _serialize_cell(row.get(key))
            if value is not None:
                ws.cell(row=row_idx, column=col_idx, value=value)

    wb.save(path)
    logger.info(
        "DJE: xlsx salvo em %s (%d linhas, %d colunas)",
        path, len(rows), len(columns),
    )
    return path
