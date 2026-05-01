"""Testes do ``notion_rpadv.services.dje_exporter``: nome do arquivo,
versionamento, ordem de colunas, serialização JSON de arrays, conteúdo
da primeira linha."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Naming + versionamento
# ---------------------------------------------------------------------------


def test_format_filename_dd_mm_aa() -> None:
    """``Publicacoes_DJEN_{dd.mm.aa}_a_{dd.mm.aa}_v{N}.xlsx``."""
    from notion_rpadv.services.dje_exporter import format_filename
    name = format_filename(date(2026, 5, 1), date(2026, 5, 3), 1)
    assert name == "Publicacoes_DJEN_01.05.26_a_03.05.26_v1.xlsx"


def test_format_filename_intervalo_de_um_dia() -> None:
    """Quando intervalo = 1 dia (inicio == fim), formato preserva."""
    from notion_rpadv.services.dje_exporter import format_filename
    name = format_filename(date(2026, 5, 1), date(2026, 5, 1), 2)
    assert name == "Publicacoes_DJEN_01.05.26_a_01.05.26_v2.xlsx"


def test_next_version_v1_quando_vazio(tmp_path: Path) -> None:
    """Diretório vazio → próxima versão é 1."""
    from notion_rpadv.services.dje_exporter import next_version
    v = next_version(tmp_path, date(2026, 5, 1), date(2026, 5, 1))
    assert v == 1


def test_next_version_pula_v1_existente(tmp_path: Path) -> None:
    """v1 já existe → próximo é v2 (Round 7 case 6 do spec)."""
    from notion_rpadv.services.dje_exporter import (
        format_filename,
        next_version,
    )
    di, df = date(2026, 5, 1), date(2026, 5, 1)
    (tmp_path / format_filename(di, df, 1)).write_text("")
    v = next_version(tmp_path, di, df)
    assert v == 2


def test_next_version_pula_ate_achar_livre(tmp_path: Path) -> None:
    """v1, v2, v3 existem → v4."""
    from notion_rpadv.services.dje_exporter import (
        format_filename,
        next_version,
    )
    di, df = date(2026, 5, 1), date(2026, 5, 1)
    for v in (1, 2, 3):
        (tmp_path / format_filename(di, df, v)).write_text("")
    assert next_version(tmp_path, di, df) == 4


def test_next_version_diferente_intervalo_nao_colide(tmp_path: Path) -> None:
    """v1 do intervalo X não interfere com v1 do intervalo Y."""
    from notion_rpadv.services.dje_exporter import (
        format_filename,
        next_version,
    )
    other_di, other_df = date(2026, 4, 30), date(2026, 4, 30)
    (tmp_path / format_filename(other_di, other_df, 1)).write_text("")
    # Intervalo diferente → ainda v1.
    di, df = date(2026, 5, 1), date(2026, 5, 1)
    assert next_version(tmp_path, di, df) == 1


# ---------------------------------------------------------------------------
# write_publicacoes_xlsx — content tests (Round 7 case 5)
# ---------------------------------------------------------------------------


def _read_back(path: Path):
    from openpyxl import load_workbook
    return load_workbook(path)


def test_xlsx_aba_chamada_publicacoes(tmp_path: Path) -> None:
    """Aba única se chama 'Publicacoes' (sem acento — coerência com
    o nome do arquivo)."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    path = write_publicacoes_xlsx(
        rows=[],
        output_dir=tmp_path,
        data_inicio=date(2026, 5, 1),
        data_fim=date(2026, 5, 1),
    )
    wb = _read_back(path)
    assert wb.sheetnames == ["Publicacoes"]


def test_xlsx_advogado_consultado_eh_primeira_coluna(tmp_path: Path) -> None:
    """Round 7 spec: ``advogado_consultado`` é a 1ª coluna, mesmo
    sendo injetada por nós depois das chaves do JSON da API."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    rows = [{
        "id": 1, "hash": "abc", "texto": "publi 1",
        "advogado_consultado": "Leonardo (36129/DF)",
    }]
    path = write_publicacoes_xlsx(
        rows=rows,
        output_dir=tmp_path,
        data_inicio=date(2026, 5, 1),
        data_fim=date(2026, 5, 1),
    )
    wb = _read_back(path)
    ws = wb["Publicacoes"]
    assert ws.cell(row=1, column=1).value == "advogado_consultado"


def test_xlsx_header_em_negrito(tmp_path: Path) -> None:
    """Headers em bold pra destacar."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    rows = [{"advogado_consultado": "X", "id": 1}]
    path = write_publicacoes_xlsx(
        rows, tmp_path, date(2026, 5, 1), date(2026, 5, 1),
    )
    wb = _read_back(path)
    ws = wb["Publicacoes"]
    assert ws.cell(row=1, column=1).font.bold is True


def test_xlsx_serializa_arrays_como_json(tmp_path: Path) -> None:
    """Round 7 spec: arrays (destinatarios, destinatarioadvogados)
    viram JSON string com ensure_ascii=False (acentos preservados)."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    rows = [{
        "advogado_consultado": "X",
        "id": 1,
        "destinatarios": [
            {"nome": "Luís Fernando", "polo": "ATIVO"},
            {"nome": "Mariana Souza", "polo": "PASSIVO"},
        ],
        "destinatarioadvogados": ["12345/DF", "67890/SP"],
    }]
    path = write_publicacoes_xlsx(
        rows, tmp_path, date(2026, 5, 1), date(2026, 5, 1),
    )
    wb = _read_back(path)
    ws = wb["Publicacoes"]
    headers = [
        ws.cell(row=1, column=c).value
        for c in range(1, ws.max_column + 1)
    ]
    dest_idx = headers.index("destinatarios") + 1
    advs_idx = headers.index("destinatarioadvogados") + 1
    dest_value = ws.cell(row=2, column=dest_idx).value
    advs_value = ws.cell(row=2, column=advs_idx).value
    # JSON string parseável (não Python repr)
    parsed_dest = json.loads(dest_value)
    parsed_advs = json.loads(advs_value)
    assert parsed_dest[0]["nome"] == "Luís Fernando"
    assert parsed_advs == ["12345/DF", "67890/SP"]
    # ensure_ascii=False — acentos literais (não ú).
    assert "Luís" in dest_value


def test_xlsx_preserva_ordem_colunas_do_primeiro_item(tmp_path: Path) -> None:
    """Round 7 spec: colunas seguem a ordem do JSON do PRIMEIRO item
    retornado, com ``advogado_consultado`` à frente."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    rows = [{
        "id":            1,
        "hash":          "abc",
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Intimação",
        "advogado_consultado": "X (1/DF)",  # injetado, vai pra frente
    }]
    path = write_publicacoes_xlsx(
        rows, tmp_path, date(2026, 5, 1), date(2026, 5, 1),
    )
    wb = _read_back(path)
    ws = wb["Publicacoes"]
    headers = [
        ws.cell(row=1, column=c).value
        for c in range(1, ws.max_column + 1)
    ]
    # Primeira coluna sempre é a anotação.
    assert headers[0] == "advogado_consultado"
    # Restante na ordem do JSON original (id, hash, sigla, tipo).
    assert headers[1:] == ["id", "hash", "siglaTribunal", "tipoDocumento"]


def test_xlsx_chaves_novas_em_items_subsequentes(tmp_path: Path) -> None:
    """Defesa: se item N tem chave que item 1 não tinha, ela vai pro
    final da lista de colunas (não some)."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    rows = [
        {"advogado_consultado": "X", "id": 1, "hash": "a"},
        {"advogado_consultado": "X", "id": 2, "hash": "b", "extra": "novo"},
    ]
    path = write_publicacoes_xlsx(
        rows, tmp_path, date(2026, 5, 1), date(2026, 5, 1),
    )
    wb = _read_back(path)
    ws = wb["Publicacoes"]
    headers = [
        ws.cell(row=1, column=c).value
        for c in range(1, ws.max_column + 1)
    ]
    assert "extra" in headers
    # Linha 1 (item original): coluna 'extra' fica vazia
    extra_idx = headers.index("extra") + 1
    assert ws.cell(row=2, column=extra_idx).value is None
    # Linha 2 (item novo): coluna 'extra' tem o valor
    assert ws.cell(row=3, column=extra_idx).value == "novo"


def test_xlsx_lista_vazia_gera_arquivo_so_com_header(tmp_path: Path) -> None:
    """0 publicações → arquivo gerado mesmo assim com só o header
    ``advogado_consultado``. Operador vê que rodou, sem confundir
    com erro."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    path = write_publicacoes_xlsx(
        rows=[],
        output_dir=tmp_path,
        data_inicio=date(2026, 5, 1),
        data_fim=date(2026, 5, 1),
    )
    assert path.exists()
    wb = _read_back(path)
    ws = wb["Publicacoes"]
    assert ws.cell(row=1, column=1).value == "advogado_consultado"
    # Sem linhas de dados.
    assert ws.cell(row=2, column=1).value is None


def test_xlsx_versionamento_em_2_runs_consecutivas(tmp_path: Path) -> None:
    """Round 7 spec case 6: rodar 2× o mesmo intervalo → v2 no segundo."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    di, df = date(2026, 5, 1), date(2026, 5, 1)
    p1 = write_publicacoes_xlsx([], tmp_path, di, df)
    p2 = write_publicacoes_xlsx([], tmp_path, di, df)
    assert p1.name.endswith("_v1.xlsx")
    assert p2.name.endswith("_v2.xlsx")
    # Ambos sobrevivem (não sobrescreveu)
    assert p1.exists()
    assert p2.exists()


def test_xlsx_cria_diretorio_se_nao_existir(tmp_path: Path) -> None:
    """write_publicacoes_xlsx faz mkdir(parents=True) — caller pode
    passar caminho sob diretório que ainda não foi criado."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    target = tmp_path / "subdir1" / "subdir2"
    assert not target.exists()
    write_publicacoes_xlsx(
        [], target, date(2026, 5, 1), date(2026, 5, 1),
    )
    assert target.exists()


def test_xlsx_none_vira_celula_vazia(tmp_path: Path) -> None:
    """Valor None no JSON original vira célula vazia (não 'None' string)."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    rows = [{
        "advogado_consultado": "X",
        "id": 1,
        "campo_opcional": None,
    }]
    path = write_publicacoes_xlsx(
        rows, tmp_path, date(2026, 5, 1), date(2026, 5, 1),
    )
    wb = _read_back(path)
    ws = wb["Publicacoes"]
    headers = [
        ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)
    ]
    idx = headers.index("campo_opcional") + 1
    assert ws.cell(row=2, column=idx).value is None
