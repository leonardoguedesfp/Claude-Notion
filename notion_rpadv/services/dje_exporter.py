"""Writer xlsx pras publicações DJEN coletadas pelo ``dje_client``.

Fase 2: pipeline ``dje_transform.transform_rows`` é aplicado ANTES da
escrita — dedup por id, observacoes derivadas das regras A+B, strip
de HTML em ``texto``, normalização de encoding misto em campos
all-caps, drop de 6 colunas redundantes, sort por tribunal+data,
schema canônico de 20 colunas em ordem fixa.

Caller (UI page) continua passando rows brutos do client (formato F1
com ``advogado_consultado`` singular por linha) — toda transformação
é interna ao writer.

Naming: ``Publicacoes_DJEN_{dd.mm.aa_inicio}_a_{dd.mm.aa_fim}_v{N}.xlsx``.
Versão auto-incrementa pra nunca sobrescrever — útil quando o operador
roda a mesma data 2× no mesmo dia (refinou critério).

Fase 2.1 (2026-05-01): defesa em 2 camadas contra ``IllegalCharacterError``
do openpyxl:

1. **Defesa primária** (no ``dje_transform``): sanitiza top-level
   strings antes da escrita (``sanitize_for_xlsx`` no ``_enrich_row``).

2. **Defesa secundária** (aqui):
   - ``_serialize_cell`` aplica ``sanitize_for_xlsx`` na string final
     PÓS-JSON — captura caracteres aninhados em ``destinatarios``
     (lista de dicts) que escaparam da defesa primária.
   - ``write_publicacoes_xlsx`` ganha try/except por linha. Se uma
     célula da linha N falhar, a linha N inteira é pulada (não meia
     linha quebrada) e contabilizada em ``ExportResult.skipped``.
     Demais linhas seguem.

Contrato de retorno mudou em Fase 2.1: ``write_publicacoes_xlsx`` agora
retorna ``ExportResult(path, skipped)`` em vez de ``Path``. Único caller
em produção (``pages/leitor_dje._DJEWorker.run``) consome o NamedTuple
e propaga ``skipped_count`` pra UI exibir banner final composto.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

from openpyxl import Workbook
from openpyxl.styles import Font

from notion_rpadv.services.dje_transform import sanitize_for_xlsx

logger = logging.getLogger("dje.exporter")

SHEET_NAME: str = "Publicacoes"
ANNOTATION_COLUMN: str = "advogado_consultado"


class SkippedRow(NamedTuple):
    """Linha pulada na escrita do xlsx (Fase 2.1)."""

    source_idx: int   # 1-based index na lista processed_rows
    row_id: Any       # ``row['id']`` se existir, senão None
    error: str        # ``str(exc)`` truncado pra log


class ExportResult(NamedTuple):
    """Resultado de ``write_publicacoes_xlsx`` (Fase 2.1).

    ``path``: caminho final do arquivo gerado.
    ``skipped``: linhas que falharam ao escrever — vazio em sucesso total.
    Caller pode iterar pra exibir detalhes ou usar ``len(skipped)`` pra
    banner final.
    """

    path: Path
    skipped: list[SkippedRow]


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

    - Listas/dicts → JSON string com ensure_ascii=False (preserva acentos)
      → sanitiza string final via ``sanitize_for_xlsx`` (Fase 2.1: defesa
      secundária pra control chars aninhados em ``destinatarios``).
    - Strings → sanitiza (idempotente — defesa em depth se transform
      foi pulado por algum motivo).
    - None → None (célula vazia).
    - Demais → passa direto.
    """
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return sanitize_for_xlsx(json.dumps(value, ensure_ascii=False))
    if isinstance(value, str):
        return sanitize_for_xlsx(value)
    return value


def write_publicacoes_xlsx(
    rows: list[dict[str, Any]],
    output_dir: Path,
    data_inicio: date,
    data_fim: date,
) -> ExportResult:
    """Escreve o xlsx no diretório informado, com versionamento
    automático. Retorna ``ExportResult(path, skipped)``.

    ``output_dir`` é criado se não existir (mas se o caller esperou
    fallback de QFileDialog quando ``output_dir`` é inacessível,
    deve ter resolvido isso ANTES de chamar — esta função só faz
    mkdir simples, sem prompt).

    Fase 2: aplica ``dje_transform.transform_rows`` antes de escrever
    — dedup por id, observacoes A+B, strip HTML, normalização de
    encoding, drop de colunas redundantes, sort, schema canônico de
    20 colunas. Caller continua passando rows brutos do client.

    Fase 2.1: try/except por linha. Célula que falhar (e.g.
    ``IllegalCharacterError`` que escapou da defesa primária) faz a
    linha INTEIRA ser pulada — não meia linha quebrada — e
    contabilizada em ``result.skipped``. Demais linhas seguem normalmente.
    """
    # Round 7 Fase 2: pipeline de transform aplicado antes da escrita.
    from notion_rpadv.services.dje_transform import transform_rows
    processed_rows, columns = transform_rows(rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    version = next_version(output_dir, data_inicio, data_fim)
    path = output_dir / format_filename(data_inicio, data_fim, version)

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    # Header em negrito (schema canônico do F2: 20 colunas em ordem fixa)
    bold = Font(bold=True)
    for col_idx, name in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = bold

    # Data rows — só campos do schema canônico (chaves extras nas rows
    # processadas são ignoradas; defesa contra payload variante).
    skipped: list[SkippedRow] = []
    written_row_idx = 1  # row 1 = header
    for source_idx, row in enumerate(processed_rows, start=1):
        # Próximo slot disponível. Se a linha falhar, NÃO avança —
        # a próxima linha (sucesso) sobrescreve as células zeradas
        # do rollback, mantendo o arquivo sem gaps.
        target_row_idx = written_row_idx + 1
        cells_set: list[int] = []
        write_error: Exception | None = None
        for col_idx, key in enumerate(columns, start=1):
            value = _serialize_cell(row.get(key))
            if value is None:
                continue
            try:
                ws.cell(row=target_row_idx, column=col_idx, value=value)
                cells_set.append(col_idx)
            except Exception as exc:  # noqa: BLE001
                write_error = exc
                break
        if write_error is not None:
            # Rollback: zera as células parcialmente escritas.
            for c in cells_set:
                ws.cell(row=target_row_idx, column=c).value = None
            sk = SkippedRow(
                source_idx=source_idx,
                row_id=row.get("id"),
                error=str(write_error)[:200],
            )
            skipped.append(sk)
            logger.warning(
                "DJE: linha pulada na escrita: source_idx=%d id=%r erro=%s",
                sk.source_idx, sk.row_id, sk.error,
            )
        else:
            written_row_idx = target_row_idx

    wb.save(path)
    logger.info(
        "DJE: xlsx salvo em %s (%d linhas escritas, %d colunas) — "
        "raw=%d → deduped=%d, %d puladas",
        path, written_row_idx - 1, len(columns),
        len(rows), len(processed_rows), len(skipped),
    )
    return ExportResult(path=path, skipped=skipped)
