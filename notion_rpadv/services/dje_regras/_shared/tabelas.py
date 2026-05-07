"""Tabela A do doc canônico — ``instancia_implicada(Pub)``.

Inferida em runtime a partir de Pub.Tribunal + Pub.Tipo de documento +
Pub.Órgão. Usada por AC10 (subida), AC11 (descida), e implicitamente
pelas AC15-AC20 (extração de cidade/vara/turma/relator quando o
órgão revela a instância).
"""
from __future__ import annotations

import re
from typing import Any

from notion_rpadv.services.dje_notion_mappings import mapear_tipo_documento

from .constantes import (
    INSTANCIA_PRIMEIRO_GRAU,
    INSTANCIA_SEGUNDO_GRAU,
    INSTANCIA_STF,
    INSTANCIA_STJ,
    INSTANCIA_TST,
)

# ---------------------------------------------------------------------------
# Regex de Órgão pra inferência de instância
# ---------------------------------------------------------------------------

_RX_VARA_TRABALHO = re.compile(r"\d+ª\s*Vara do Trabalho", re.IGNORECASE)
_RX_VARA_CIVEL = re.compile(r"\d+ª\s*Vara Cível", re.IGNORECASE)
_RX_VARA_FAZENDA = re.compile(r"Vara da Fazenda", re.IGNORECASE)
_RX_JUIZADO = re.compile(r"Juizado", re.IGNORECASE)
_RX_DESEMBARGADOR = re.compile(r"^\s*Desembargador[a]?\b", re.IGNORECASE)
_RX_JUIZ_CONVOCADO = re.compile(r"^\s*Juiz[a]?\s+Convocad[oa]\b", re.IGNORECASE)
_RX_TURMA_CAMARA = re.compile(
    r"\d+ª\s*(Turma|Câmara)(\s*Cível)?\s*$", re.IGNORECASE,
)


def instancia_implicada(publicacao: dict[str, Any]) -> str | None:
    """Tabela A — infere a instância da publicação.

    Devolve uma das 5 strings canônicas (1º grau, 2º grau, TST, STJ,
    STF) ou ``None`` se a inferência não der signal claro.

    Ordem de prioridade (mais específico → mais genérico):

    1. Tribunal STJ/TST/STF: instância = própria sigla.
    2. Tipo de documento Sentença → 1º grau.
    3. Tipo de documento Acórdão / Ementa / Pauta de Julgamento →
       2º grau (ato colegiado).
    4. Órgão match Vara do Trabalho/Cível/Fazenda/Juizado → 1º grau.
    5. Órgão match Desembargador/Juiz Convocado/Turma/Câmara → 2º grau.
    6. Caso contrário → ``None``.
    """
    sigla = (publicacao.get("siglaTribunal") or "").strip().upper()
    if sigla == "STF":
        return INSTANCIA_STF
    if sigla == "STJ":
        return INSTANCIA_STJ
    if sigla == "TST":
        return INSTANCIA_TST

    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc == "Sentença":
        return INSTANCIA_PRIMEIRO_GRAU
    if tipo_doc in ("Acórdão", "Ementa", "Pauta de Julgamento"):
        return INSTANCIA_SEGUNDO_GRAU

    orgao = (publicacao.get("nomeOrgao") or "").strip()
    if not orgao:
        return None
    if (
        _RX_VARA_TRABALHO.search(orgao)
        or _RX_VARA_CIVEL.search(orgao)
        or _RX_VARA_FAZENDA.search(orgao)
        or _RX_JUIZADO.search(orgao)
    ):
        return INSTANCIA_PRIMEIRO_GRAU
    if (
        _RX_DESEMBARGADOR.search(orgao)
        or _RX_JUIZ_CONVOCADO.search(orgao)
        or _RX_TURMA_CAMARA.search(orgao)
    ):
        return INSTANCIA_SEGUNDO_GRAU
    return None
