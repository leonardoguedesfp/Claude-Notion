"""Testes do parser de input do Modo B (Componente 4).

Cobre:
- ``parse_string_cnjs``: separadores variados, dedup, formato inválido,
  DV inválido, vazio.
- ``parse_xlsx_cnjs``: com/sem cabeçalho, colunas extras ignoradas,
  vazio, células None ignoradas, abas adicionais ignoradas.

Sem dependência da API DataJud — parser é stateless e local.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from notion_rpadv.services.datajud_input_parser import (
    _validar_dv_cnj,
    parse_string_cnjs,
    parse_xlsx_cnjs,
)


# ---------------------------------------------------------------------------
# CNJs reais (DV verificado contra os 3 do Componente 2 + 1 extra)
# ---------------------------------------------------------------------------

CNJ_VALIDO_1 = "0000449-71.2025.5.10.0003"
CNJ_VALIDO_2 = "0000789-22.2019.5.10.0004"
CNJ_VALIDO_3 = "0016539-47.2015.8.07.0001"
CNJ_VALIDO_4 = "0010000-10.2020.5.10.0001"  # gerado abaixo no test_dv_helper

# CNJ com DV trocado intencionalmente (71 → 99) — formato OK, DV não bate.
CNJ_DV_INVALIDO = "0000449-99.2025.5.10.0003"


# ---------------------------------------------------------------------------
# Helper de DV (sanidade do algoritmo)
# ---------------------------------------------------------------------------


def test_dv_helper_aceita_3_cnjs_reais() -> None:
    """Os 3 CNJs reais usados no Componente 2 passam no DV."""
    assert _validar_dv_cnj("00004497120255100003") is True
    assert _validar_dv_cnj("00007892220195100004") is True
    assert _validar_dv_cnj("00165394720158070001") is True


def test_dv_helper_rejeita_dv_alterado() -> None:
    """Mudar 1 dígito do DV → falha."""
    assert _validar_dv_cnj("00004499920255100003") is False
    assert _validar_dv_cnj("00007899920195100004") is False


def test_dv_helper_rejeita_comprimento_errado() -> None:
    assert _validar_dv_cnj("123") is False
    assert _validar_dv_cnj("0" * 19) is False
    assert _validar_dv_cnj("0" * 21) is False


def test_dv_helper_rejeita_nao_numerico() -> None:
    assert _validar_dv_cnj("0000449-71.2025.5.10.0003") is False  # com máscara


# ---------------------------------------------------------------------------
# parse_string_cnjs
# ---------------------------------------------------------------------------


def test_parse_string_separadores_variados() -> None:
    """; , \\n, espaço, tab — todos aceitos."""
    texto = (
        f"{CNJ_VALIDO_1};{CNJ_VALIDO_2}\n{CNJ_VALIDO_3}, {CNJ_VALIDO_3}\t"
    )
    res = parse_string_cnjs(texto)
    # 3 CNJs distintos (CNJ_VALIDO_3 aparece duas vezes — deduplicado)
    assert len(res) == 3
    assert all(c.valido for c in res)
    assert {c.cnj_normalizado for c in res} == {CNJ_VALIDO_1, CNJ_VALIDO_2, CNJ_VALIDO_3}


def test_parse_string_dedup_preserva_ordem() -> None:
    """Dedup mantém a primeira ocorrência."""
    texto = f"{CNJ_VALIDO_2};{CNJ_VALIDO_1};{CNJ_VALIDO_2};{CNJ_VALIDO_3}"
    res = parse_string_cnjs(texto)
    assert len(res) == 3
    assert res[0].cnj_normalizado == CNJ_VALIDO_2
    assert res[1].cnj_normalizado == CNJ_VALIDO_1
    assert res[2].cnj_normalizado == CNJ_VALIDO_3


def test_parse_string_digito_verificador_invalido() -> None:
    """Formato OK + DV errado → ``valido=False`` com erro específico."""
    res = parse_string_cnjs(CNJ_DV_INVALIDO)
    assert len(res) == 1
    cnj = res[0]
    assert cnj.valido is False
    assert cnj.erro == "dígito verificador inválido"
    assert cnj.cnj_normalizado == ""           # não normaliza inválido
    assert cnj.cnj_20_digitos == "00004499920255100003"


def test_parse_string_formato_invalido() -> None:
    """< 20 dígitos / não-numérico → 'formato inválido'."""
    # 5 dígitos, 0 dígitos, 21 dígitos
    texto = "12345; abcdef ; 000044971202551000034"
    res = parse_string_cnjs(texto)
    assert len(res) == 3
    assert all(not c.valido for c in res)
    assert all(c.erro == "formato inválido" for c in res)


def test_parse_string_vazio_retorna_lista_vazia() -> None:
    assert parse_string_cnjs("") == []
    assert parse_string_cnjs("   ") == []
    assert parse_string_cnjs("\n\n;,") == []


def test_parse_string_aceita_com_e_sem_mascara() -> None:
    """Mesmo CNJ com e sem máscara é considerado o mesmo (dedup por
    20 dígitos)."""
    texto = f"{CNJ_VALIDO_1}; 00004497120255100003"
    res = parse_string_cnjs(texto)
    assert len(res) == 1
    assert res[0].cnj_normalizado == CNJ_VALIDO_1


def test_parse_string_validos_e_invalidos_misturados() -> None:
    """Resultado preserva ordem; flag ``valido`` distingue."""
    texto = (
        f"{CNJ_VALIDO_1}\n"
        f"123\n"
        f"{CNJ_VALIDO_2}\n"
        f"{CNJ_DV_INVALIDO}"
    )
    res = parse_string_cnjs(texto)
    assert len(res) == 4
    assert [c.valido for c in res] == [True, False, True, False]


# ---------------------------------------------------------------------------
# parse_xlsx_cnjs
# ---------------------------------------------------------------------------


def _criar_xlsx_temp(
    tmp_path: Path, valores_col_a: list[object], header: str | None = None,
    *, extra_cols: bool = False, abas_extras: bool = False,
) -> Path:
    """Helper: cria xlsx com lista na coluna A. Opcionalmente
    adiciona cabeçalho, colunas extras, ou abas extras."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    row = 1
    if header is not None:
        ws.cell(row=row, column=1, value=header)
        if extra_cols:
            ws.cell(row=row, column=2, value="comentário")
            ws.cell(row=row, column=3, value="cliente")
        row += 1
    for v in valores_col_a:
        ws.cell(row=row, column=1, value=v)
        if extra_cols:
            ws.cell(row=row, column=2, value="ruído")
        row += 1
    if abas_extras:
        ws2 = wb.create_sheet(title="OutraAba")
        ws2.cell(row=1, column=1, value=CNJ_VALIDO_4)  # NÃO deve aparecer
    out = tmp_path / "input.xlsx"
    wb.save(out)
    wb.close()
    return out


def test_parse_xlsx_com_cabecalho(tmp_path: Path) -> None:
    """A1='cnj' (cabeçalho); demais linhas são CNJs válidos."""
    out = _criar_xlsx_temp(
        tmp_path,
        valores_col_a=[CNJ_VALIDO_1, CNJ_VALIDO_2, CNJ_VALIDO_3],
        header="cnj",
    )
    res = parse_xlsx_cnjs(out)
    assert len(res) == 3
    assert all(c.valido for c in res)
    assert [c.cnj_normalizado for c in res] == [
        CNJ_VALIDO_1, CNJ_VALIDO_2, CNJ_VALIDO_3,
    ]


def test_parse_xlsx_com_cabecalho_variantes(tmp_path: Path) -> None:
    """Variações de cabeçalho: 'CNJ', 'Número do processo', 'Processo'."""
    for cab in ("CNJ", "Número do processo", "Processo", "número"):
        out = _criar_xlsx_temp(
            tmp_path, valores_col_a=[CNJ_VALIDO_1], header=cab,
        )
        res = parse_xlsx_cnjs(out)
        assert len(res) == 1, f"falha com header={cab!r}"
        assert res[0].valido


def test_parse_xlsx_sem_cabecalho(tmp_path: Path) -> None:
    """A1 contém um CNJ válido (não é header) — não pula."""
    out = _criar_xlsx_temp(
        tmp_path,
        valores_col_a=[CNJ_VALIDO_1, CNJ_VALIDO_2],
        header=None,
    )
    res = parse_xlsx_cnjs(out)
    assert len(res) == 2
    assert res[0].cnj_normalizado == CNJ_VALIDO_1
    assert res[1].cnj_normalizado == CNJ_VALIDO_2


def test_parse_xlsx_colunas_extras_ignoradas(tmp_path: Path) -> None:
    """Colunas B, C, D... são ignoradas pelo parser."""
    out = _criar_xlsx_temp(
        tmp_path,
        valores_col_a=[CNJ_VALIDO_1, CNJ_VALIDO_2],
        header="cnj",
        extra_cols=True,
    )
    res = parse_xlsx_cnjs(out)
    assert len(res) == 2
    assert all(c.valido for c in res)


def test_parse_xlsx_vazio_retorna_lista_vazia(tmp_path: Path) -> None:
    """xlsx sem dados nem cabeçalho → []."""
    out = _criar_xlsx_temp(tmp_path, valores_col_a=[], header=None)
    res = parse_xlsx_cnjs(out)
    assert res == []


def test_parse_xlsx_apenas_cabecalho_retorna_lista_vazia(tmp_path: Path) -> None:
    """xlsx com só A1='cnj' (sem dados) → []."""
    out = _criar_xlsx_temp(tmp_path, valores_col_a=[], header="cnj")
    res = parse_xlsx_cnjs(out)
    assert res == []


def test_parse_xlsx_celulas_None_ignoradas(tmp_path: Path) -> None:
    """Linhas em branco entre CNJs são ignoradas (None vira skip)."""
    out = _criar_xlsx_temp(
        tmp_path,
        valores_col_a=[CNJ_VALIDO_1, None, CNJ_VALIDO_2, None, None, CNJ_VALIDO_3],
        header="cnj",
    )
    res = parse_xlsx_cnjs(out)
    assert len(res) == 3
    assert [c.cnj_normalizado for c in res] == [
        CNJ_VALIDO_1, CNJ_VALIDO_2, CNJ_VALIDO_3,
    ]


def test_parse_xlsx_aba_diferente_da_primeira_ignorada(tmp_path: Path) -> None:
    """Só a 1ª aba é lida. CNJs em outras abas são ignorados."""
    out = _criar_xlsx_temp(
        tmp_path,
        valores_col_a=[CNJ_VALIDO_1, CNJ_VALIDO_2],
        header="cnj",
        abas_extras=True,
    )
    res = parse_xlsx_cnjs(out)
    cnjs = {c.cnj_normalizado for c in res}
    assert cnjs == {CNJ_VALIDO_1, CNJ_VALIDO_2}
    assert CNJ_VALIDO_4 not in cnjs


def test_parse_xlsx_arquivo_inexistente_levanta(tmp_path: Path) -> None:
    """FileNotFoundError pra path inexistente — caller decide UX."""
    import pytest as _pt
    with _pt.raises(FileNotFoundError):
        parse_xlsx_cnjs(tmp_path / "nao_existe.xlsx")


def test_parse_xlsx_invalidos_e_validos_misturados(tmp_path: Path) -> None:
    """Linhas inválidas viram CnjValidado(valido=False, erro=...)."""
    out = _criar_xlsx_temp(
        tmp_path,
        valores_col_a=[CNJ_VALIDO_1, "12345", CNJ_DV_INVALIDO, CNJ_VALIDO_2],
        header="CNJ",
    )
    res = parse_xlsx_cnjs(out)
    assert len(res) == 4
    assert [c.valido for c in res] == [True, False, False, True]
    assert res[1].erro == "formato inválido"
    assert res[2].erro == "dígito verificador inválido"
