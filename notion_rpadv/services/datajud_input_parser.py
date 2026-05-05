"""Parser de input do Modo B da feature DataJUD (Componente 4).

O Modo B aceita uma lista manual de CNJs digitada/colada pelo usuário
(string com separadores variados — ponto-e-vírgula, vírgula, quebra de
linha, espaço) ou anexada via xlsx (1 CNJ por linha na coluna A da
primeira aba).

Para cada CNJ, valida:

1. **Formato**: 20 dígitos com ou sem máscara
   ``NNNNNNN-DD.AAAA.J.TT.OOOO``.

2. **Dígito verificador**: módulo 97 conforme Resolução CNJ 65/2008.
   Algoritmo: rearranjando o número para
   ``NNNNNNN AAAA J TT OOOO`` (18 dígitos sem o DV) e calculando
   ``(N * 100 + DV) mod 97 == 1``. Se o resto não for 1, o DV está
   inválido.

Saída uniforme entre os dois caminhos: ``list[CnjValidado]``.
``CnjValidado.valido = False`` carrega ``erro`` legível
(``"formato inválido"`` ou ``"dígito verificador inválido"``);
``CnjValidado.valido = True`` carrega o ``cnj_normalizado`` com máscara
e os 20 dígitos brutos.

Não acessa rede; não toca SQLite. Stateless.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from notion_rpadv.services.datajud_enricher import formatar_cnj_com_mascara

logger = logging.getLogger("datajud.input_parser")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Separadores aceitos no Modo B em string: ; , quebra de linha, tab,
# espaço (qualquer whitespace). O regex inclui todas as variantes.
_SEPARADORES_RE: Final[re.Pattern[str]] = re.compile(r"[;,\s]+")

# Cabeçalhos comuns que devem ser ignorados na linha 1 do xlsx.
_CABECALHOS_CNJ: Final[frozenset[str]] = frozenset({
    "cnj", "número", "numero", "n", "nº", "n°",
    "número do processo", "numero do processo",
    "processo", "número cnj", "numero cnj",
})


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass
class CnjValidado:
    """Resultado da validação de um CNJ.

    Attributes:
        cnj_normalizado: CNJ com máscara
            ``NNNNNNN-DD.AAAA.J.TT.OOOO`` quando válido. String vazia
            se a entrada não for normalizável.
        cnj_20_digitos: 20 dígitos sem máscara, quando extraíveis.
            String vazia caso contrário.
        valido: True se passou em formato + DV.
        erro: ``None`` quando ``valido``; senão string descritiva
            (``"formato inválido"`` ou ``"dígito verificador inválido"``).
    """

    cnj_normalizado: str
    cnj_20_digitos: str
    valido: bool
    erro: str | None


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------


def _validar_dv_cnj(digits_20: str) -> bool:
    """Verifica o dígito verificador de um CNJ (módulo 97, Res. 65/2008).

    O CNJ formato canônico é::

        NNNNNNN-DD.AAAA.J.TT.OOOO

    onde DD são os 2 dígitos verificadores. O algoritmo:

    1. Reordena para ``NNNNNNN AAAA J TT OOOO`` (18 dígitos, sem o DV).
    2. Calcula ``valor = int(NNNNNNN AAAA J TT OOOO)``.
    3. CNJ é válido se ``(valor * 100 + DD) mod 97 == 1``.

    Args:
        digits_20: string com exatamente 20 dígitos (sem máscara).

    Returns:
        True se DV é válido. False caso contrário (incl. comprimento
        diferente de 20 ou caracteres não-numéricos).
    """
    if len(digits_20) != 20 or not digits_20.isdigit():
        return False
    sequencial = digits_20[:7]    # NNNNNNN
    dv         = digits_20[7:9]    # DD (verificador)
    ano        = digits_20[9:13]   # AAAA
    justica    = digits_20[13]      # J
    tribunal   = digits_20[14:16]  # TT
    origem     = digits_20[16:20]  # OOOO
    n_sem_dv = int(sequencial + ano + justica + tribunal + origem)
    return (n_sem_dv * 100 + int(dv)) % 97 == 1


def _validar_um(token: str) -> CnjValidado:
    """Valida um único token (string já trim) → ``CnjValidado``."""
    raw = token.strip()
    digits = "".join(ch for ch in raw if ch.isdigit())

    if len(digits) != 20:
        return CnjValidado(
            cnj_normalizado="",
            cnj_20_digitos=digits,
            valido=False,
            erro="formato inválido",
        )

    if not _validar_dv_cnj(digits):
        return CnjValidado(
            cnj_normalizado="",
            cnj_20_digitos=digits,
            valido=False,
            erro="dígito verificador inválido",
        )

    mascarado = formatar_cnj_com_mascara(digits) or ""
    return CnjValidado(
        cnj_normalizado=mascarado,
        cnj_20_digitos=digits,
        valido=True,
        erro=None,
    )


# ---------------------------------------------------------------------------
# Parsing — string colada
# ---------------------------------------------------------------------------


def parse_string_cnjs(texto: str) -> list[CnjValidado]:
    """Parser do Modo B — string colada.

    Aceita ``;``, ``,``, quebra de linha, tab e espaço como separadores
    (qualquer combinação). Deduplica preservando ordem da primeira
    ocorrência (chave de dedup = 20 dígitos do CNJ; tokens com formato
    inválido são deduplicados pelo trim do raw).

    Args:
        texto: input cru do usuário (textarea, clipboard, etc.).

    Returns:
        Lista ``CnjValidado`` na ordem de aparição. Vazia se o input
        não tem nenhum token significativo.
    """
    if not texto:
        return []

    tokens = [t.strip() for t in _SEPARADORES_RE.split(texto) if t.strip()]
    if not tokens:
        return []

    seen: set[str] = set()
    out: list[CnjValidado] = []
    for tok in tokens:
        validado = _validar_um(tok)
        chave = validado.cnj_20_digitos or tok.strip().lower()
        if chave in seen:
            continue
        seen.add(chave)
        out.append(validado)
    return out


# ---------------------------------------------------------------------------
# Parsing — upload xlsx
# ---------------------------------------------------------------------------


def _eh_cabecalho(valor: Any) -> bool:
    """Heurística: célula da linha 1 contendo um termo conhecido de
    cabeçalho ('cnj', 'número', etc.) marca a linha como header e é
    ignorada."""
    if not isinstance(valor, str):
        return False
    norm = valor.strip().lower()
    return norm in _CABECALHOS_CNJ


def parse_xlsx_cnjs(path: Path) -> list[CnjValidado]:
    """Parser do Modo B — anexo xlsx.

    Lê **coluna A da primeira aba**. Linha 1 é tratada como cabeçalho
    se a célula A1 contiver um termo conhecido (``"cnj"``, ``"CNJ"``,
    ``"número"``, etc., case-insensitive). Caso contrário, A1 é
    tratada como dado.

    Células ``None`` (linhas em branco) são ignoradas. Outras colunas
    da planilha são ignoradas — só lemos coluna A. Outras abas
    também são ignoradas — só a primeira.

    Lê com ``read_only=True, data_only=True`` para preservar memória
    em planilhas grandes e ler resultados de fórmulas (não fórmulas
    cruas).

    Args:
        path: caminho absoluto do arquivo xlsx.

    Returns:
        Lista ``CnjValidado`` na ordem das linhas, dedupliplicada
        (mesma política de ``parse_string_cnjs``).

    Raises:
        FileNotFoundError: ``path`` não existe.
        Exceções do openpyxl propagam (arquivo corrompido, formato
        inválido) — caller decide como reportar ao usuário.
    """
    from openpyxl import load_workbook

    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    try:
        # Primeira aba (a API do openpyxl preserva ordem de criação).
        if not wb.sheetnames:
            return []
        ws = wb[wb.sheetnames[0]]

        rows_iter = ws.iter_rows(min_col=1, max_col=1, values_only=True)
        valores: list[Any] = []
        for row in rows_iter:
            if not row:
                continue
            valor = row[0]
            if valor is None:
                continue
            valores.append(valor)
    finally:
        wb.close()

    if not valores:
        return []

    # Trata header: pula a primeira célula se for cabeçalho conhecido.
    inicio = 1 if _eh_cabecalho(valores[0]) else 0
    valores_dado = valores[inicio:]

    # Reaproveita a política de dedup do parser de string transformando
    # cada célula em token e usando a mesma rotina.
    seen: set[str] = set()
    out: list[CnjValidado] = []
    for v in valores_dado:
        token = str(v).strip()
        if not token:
            continue
        validado = _validar_um(token)
        chave = validado.cnj_20_digitos or token.lower()
        if chave in seen:
            continue
        seen.add(chave)
        out.append(validado)
    return out
