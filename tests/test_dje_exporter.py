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


def test_xlsx_advogados_consultados_eh_primeira_coluna(tmp_path: Path) -> None:
    """Round 7 Fase 2: ``advogados_consultados`` (plural) é a 1ª coluna
    do schema canônico. F1 era ``advogado_consultado`` (singular) — F2
    rebatizou via dedup pra plural com lista de nomes do escritório
    intimados na mesma publicação."""
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
    assert ws.cell(row=1, column=1).value == "advogados_consultados"
    # Valor da linha 2 col 1: nome do advogado (plural com 1 entrada).
    assert ws.cell(row=2, column=1).value == "Leonardo (36129/DF)"


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
    viram JSON string com ensure_ascii=False (acentos preservados).
    F2: agora dentro do schema canônico (cols 18 e 19)."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    rows = [{
        "advogado_consultado": "X",
        "id": 1,
        "destinatarios": [
            {"nome": "Luís Fernando", "polo": "ATIVO"},
            {"nome": "Mariana Souza", "polo": "PASSIVO"},
        ],
        "destinatarioadvogados": [
            {"numero_oab": "12345", "uf_oab": "DF", "nome": "X"},
        ],
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
    assert parsed_advs[0]["numero_oab"] == "12345"
    # ensure_ascii=False — acentos literais (não \\u).
    assert "Luís" in dest_value


def test_xlsx_schema_canonico_20_colunas_em_ordem_fixa(tmp_path: Path) -> None:
    """Round 7 Fase 2: schema canônico de 20 colunas em ordem fixa
    (CANONICAL_COLUMNS), independente do payload de entrada.

    Substitui o teste F1 ``test_xlsx_preserva_ordem_colunas_do_primeiro_item``
    que assertava schema-agnóstico. F2 trava o contrato: caller passa
    rows brutos do client, exporter aplica transform e escreve as 20
    colunas em ordem fixa.
    """
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    from notion_rpadv.services.dje_transform import CANONICAL_COLUMNS
    rows = [{
        "id":            1,
        "hash":          "abc",
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Intimação",
        "advogado_consultado": "X (1/DF)",
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
    # 20 colunas exatas, na ordem do schema canônico.
    assert headers == CANONICAL_COLUMNS
    # Garantia: ``advogados_consultados`` e ``observacoes`` são as 2
    # primeiras (adições da Fase 2).
    assert headers[0] == "advogados_consultados"
    assert headers[1] == "observacoes"


def test_xlsx_chaves_extras_no_payload_sao_ignoradas(tmp_path: Path) -> None:
    """Round 7 Fase 2: schema canônico filtra chaves novas que possam
    aparecer no payload do DJEN — só as 20 do CANONICAL_COLUMNS entram
    no xlsx.

    Substitui o teste F1 ``test_xlsx_chaves_novas_em_items_subsequentes``
    que validava o oposto (auto-include de chaves novas) — comportamento
    desejado da F1 mas explícito como anti-padrão na F2 (schema é
    contrato).
    """
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    from notion_rpadv.services.dje_transform import CANONICAL_COLUMNS
    rows = [
        {"advogado_consultado": "X", "id": 1, "hash": "a", "extra_inesperado": "novo"},
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
    assert headers == CANONICAL_COLUMNS
    assert "extra_inesperado" not in headers


def test_xlsx_lista_vazia_gera_arquivo_so_com_header(tmp_path: Path) -> None:
    """0 publicações → arquivo gerado mesmo assim com header completo
    (20 colunas do schema canônico F2). Operador vê que rodou, sem
    confundir com erro."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    from notion_rpadv.services.dje_transform import CANONICAL_COLUMNS
    path = write_publicacoes_xlsx(
        rows=[],
        output_dir=tmp_path,
        data_inicio=date(2026, 5, 1),
        data_fim=date(2026, 5, 1),
    )
    assert path.exists()
    wb = _read_back(path)
    ws = wb["Publicacoes"]
    # F2: 1ª col é advogados_consultados (era advogado_consultado no F1)
    assert ws.cell(row=1, column=1).value == "advogados_consultados"
    # Header completo do schema canônico.
    headers = [
        ws.cell(row=1, column=c).value
        for c in range(1, ws.max_column + 1)
    ]
    assert headers == CANONICAL_COLUMNS
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


def test_xlsx_none_em_campo_canonico_vira_celula_vazia(tmp_path: Path) -> None:
    """Valor None em campo do schema canônico vira célula vazia (não
    string 'None'). F2: testa via campo ``link`` que está no schema
    canônico (col 17) — F1 testava com chave fora do schema (que agora
    seria filtrada pelo transform)."""
    from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
    rows = [{
        "advogado_consultado": "X",
        "id": 1,
        "link": None,  # campo canônico mas com valor None
    }]
    path = write_publicacoes_xlsx(
        rows, tmp_path, date(2026, 5, 1), date(2026, 5, 1),
    )
    wb = _read_back(path)
    ws = wb["Publicacoes"]
    headers = [
        ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)
    ]
    idx = headers.index("link") + 1
    assert ws.cell(row=2, column=idx).value is None
