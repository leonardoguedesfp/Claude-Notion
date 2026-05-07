"""Extratores e normalizadores de Pub.Órgão — usados por AC15-AC20.

A inteligência aqui é capturar Cidade, Vara, Turma e Relator do nome
livre do órgão (ex.: ``"14ª Vara do Trabalho de Brasília - DF"``) e
normalizar pra comparação tolerante com o que está em
``Proc.cidade / vara / turma / relator``.
"""
from __future__ import annotations

import re

from .constantes import (
    INSTANCIA_SEGUNDO_GRAU,
    INSTANCIA_STF,
    INSTANCIA_STJ,
    INSTANCIA_TST,
)

# ---------------------------------------------------------------------------
# Cidade e Vara (1º grau)
# ---------------------------------------------------------------------------

#: Vara de 1º grau com cidade explícita: ``Nª Vara X de Cidade [- UF]``.
#: Captura: (1) prefixo "Nª Vara X", (2) cidade.
_RX_VARA_COM_CIDADE = re.compile(
    r"^(\d+ª\s*Vara\s+(?:do Trabalho|Cível|da Fazenda(?:\s+Pública)?|"
    r"de Família|Criminal|de Execuções|do Juizado|de Execução Fiscal))"
    r"\s+de\s+([A-ZÀ-Ú][A-Za-zà-úÀ-Ú\s]+?)(?:\s*-\s*[A-Z]{2})?\s*$",
    re.IGNORECASE,
)

#: Vara sem cidade (fallback) — só captura o "Nª Vara X" pra normalização.
_RX_VARA_PREFIXO = re.compile(
    r"^(\d+ª\s*Vara\s+(?:do Trabalho|Cível|da Fazenda(?:\s+Pública)?|"
    r"de Família|Criminal|de Execuções|do Juizado|de Execução Fiscal))",
    re.IGNORECASE,
)


def extrair_cidade_do_orgao(orgao: str | None) -> str | None:
    """Extrai cidade do nome do Órgão se for do padrão ``Nª Vara X de
    Cidade [- UF]``. Devolve cidade em title-case ou ``None``.
    """
    if not orgao:
        return None
    m = _RX_VARA_COM_CIDADE.match(orgao.strip())
    if m:
        cidade = m.group(2).strip()
        cidade = re.sub(r"\s+", " ", cidade)
        return cidade
    return None


def normalizar_vara(orgao: str | None) -> str | None:
    """Devolve só o prefixo ``Nª Vara X`` do nome do Órgão, em formato
    canônico title-case com espaços normalizados. Devolve ``None`` se
    não bater no padrão.
    """
    if not orgao:
        return None
    m = _RX_VARA_PREFIXO.match(orgao.strip())
    if m:
        prefix = m.group(1).strip()
        prefix = re.sub(r"\s+", " ", prefix)
        return prefix
    return None


# ---------------------------------------------------------------------------
# Turma / Câmara (≥ 2º grau)
# ---------------------------------------------------------------------------

#: Turma/Câmara de 2º grau ou superior. Aceita ``5ª Turma``, ``5ª Turma
#: Cível``, ``2ª Câmara``, eventualmente seguidas de qualificadores
#: como "de Direito" etc.
_RX_TURMA_CAMARA_NUMERADA = re.compile(
    r"^(\d+ª\s*(?:Turma|Câmara)(?:\s*Cível)?(?:\s+(?:de|do)\s+\S+)*)\s*$",
    re.IGNORECASE,
)


def extrair_turma_camara(orgao: str | None) -> str | None:
    """Devolve string da Turma/Câmara (ex: ``"2ª Turma"``,
    ``"6ª Turma Cível"``) ou ``None``.
    """
    if not orgao:
        return None
    m = _RX_TURMA_CAMARA_NUMERADA.match(orgao.strip())
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    return None


def ordinal_de_turma(valor: str | None) -> int | None:
    """Extrai o ordinal numérico (int) do conteúdo de Turma. Aceita
    ``"5ª Turma"``, ``"5ª Turma Cível"``, ``"5"``, ``"5.0"`` (float-
    string de migração antiga). Devolve ``None`` quando o valor é vazio
    ou não tem dígitos extraíveis.

    Implementação: ``(?<!\\d)(\\d+)(?!\\d)`` (lookbehind/lookahead por
    não-dígito), porque ``\\b\\d+\\b`` em Unicode NÃO casa entre ``2``
    e ``ª`` (ambos são word chars).
    """
    if not valor:
        return None
    s = str(valor).strip()
    if not s:
        return None
    m = re.search(r"(?<!\d)(\d+)(?!\d)", s)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Relator (Desembargador, Juiz Convocado, Ministro)
# ---------------------------------------------------------------------------

#: Relator no Pub.Órgão.
_RX_RELATOR = re.compile(
    r"^\s*(?:Gabinete\s+(?:do|da)\s+)?"
    r"(Desembargador[a]?|Juiz[a]?\s+Convocad[oa]|Ministr[oa])"
    r"\s+(.+?)\s*$",
    re.IGNORECASE,
)

#: Prefixos de tratamento que aparecem em Pub.Órgão e em
#: ``Proc.relator_*``. Removidos pra comparação simétrica.
_RX_PREFIXO_RELATOR = re.compile(
    r"^\s*(?:Gabinete\s+(?:do|da)\s+)?"
    r"(?:Desembargador[a]?\.?|Des\.?|"
    r"Juiz[a]?\s+Convocad[oa]|"
    r"Ministr[oa]\.?|Min\.?)\s+",
    re.IGNORECASE,
)


def extrair_relator(orgao: str | None) -> str | None:
    """Devolve o nome do relator do Pub.Órgão se for do padrão
    ``Desembargador/Juiz Convocado/Ministro NOME``. Devolve ``None``
    se não bater.
    """
    if not orgao:
        return None
    m = _RX_RELATOR.match(orgao.strip())
    if m:
        nome = m.group(2).strip()
        nome = re.sub(r"\s+", " ", nome)
        return nome
    return None


def normalizar_nome_relator(valor: str | None) -> str | None:
    """Devolve o nome do relator sem prefixo de tratamento.

    Aceita variações comuns que podem aparecer tanto em ``Pub.Órgão``
    quanto em ``Proc.relator_no_*``:

    - ``"Desembargadora ELKE DORIS JUST"`` → ``"ELKE DORIS JUST"``
    - ``"Des. Joaquim"``                   → ``"Joaquim"``
    - ``"Gabinete da Desembargadora X"``   → ``"X"``
    - ``"Ministro Marco Aurélio"``         → ``"Marco Aurélio"``
    - ``"ELKE DORIS JUST"`` (sem prefixo)  → ``"ELKE DORIS JUST"``
    - ``""`` ou ``None``                   → ``None``
    """
    if not valor:
        return None
    s = str(valor).strip()
    if not s:
        return None
    s = _RX_PREFIXO_RELATOR.sub("", s).strip()
    if not s:
        return None
    return re.sub(r"\s+", " ", s)


# ---------------------------------------------------------------------------
# Mapping Proc.instancia → nome do campo de Turma/Relator no record
# ---------------------------------------------------------------------------

def campo_turma_para_instancia(instancia: str) -> str | None:
    """Mapeia ``Proc.instancia`` → nome do campo ``turma_no_*``."""
    return {
        INSTANCIA_SEGUNDO_GRAU: "turma_no_2o_grau",
        INSTANCIA_TST: "turma_no_stj_tst",
        INSTANCIA_STJ: "turma_no_stj_tst",
        INSTANCIA_STF: "turma_no_stf",
    }.get(instancia)


def campo_relator_para_instancia(instancia: str) -> str | None:
    """Mapeia ``Proc.instancia`` → nome do campo ``relator_no_*``."""
    return {
        INSTANCIA_SEGUNDO_GRAU: "relator_no_2o_grau",
        INSTANCIA_TST: "relator_no_stj_tst",
        INSTANCIA_STJ: "relator_no_stj_tst",
        INSTANCIA_STF: "relator_no_stf",
    }.get(instancia)
