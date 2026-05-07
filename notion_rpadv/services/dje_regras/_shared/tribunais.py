"""Tabelas de Tribunal — natureza esperada (AC01) e mapeamento entre
formato Pub (sem barra) e formato Proc (com barra) (AC07, AC08).
"""
from __future__ import annotations

#: ``Pub.Tribunal`` trabalhistas — cobre TRT/TST. Disparam AC01 quando
#: ``Proc.natureza == Cível``.
TRIBUNAIS_TRABALHISTAS: frozenset[str] = frozenset({
    "TRT10", "TRT18", "TST",
})

#: ``Pub.Tribunal`` cíveis. STJ/STF ficam fora porque julgam ambas as
#: naturezas.
TRIBUNAIS_CIVEIS: frozenset[str] = frozenset({
    "TJDFT", "TJSP", "TJMG", "TJPR", "TJRJ", "TJRS",
    "TJSC", "TJBA", "TJMS", "TJGO",
    "TRF1",
})

#: Tribunais que ``Pub.Tribunal`` aceita mas ``Proc.tribunal`` ainda
#: **não** tem no vocabulário canônico — disparam AC07.
TRIBUNAIS_FORA_VOCABULARIO_PROC: frozenset[str] = frozenset({
    "TRT18",
    "TRF1",
})

#: ``Pub.Tribunal`` (sem barra) → ``Proc.tribunal`` (com barra em
#: TRT/N e TRF/N). Tribunais que usam o mesmo formato em ambos os
#: lados (TJDFT, TJSP, …, STJ, TST, STF) ficam fora — caem no
#: fallback ``return s`` em :func:`pub_trib_normalizado_para_proc`.
_PUB_TRIB_PARA_PROC: dict[str, str] = {
    "TRT10": "TRT/10",
    "TRT18": "TRT/18",
    "TRF1": "TRF/1",
}


def pub_trib_normalizado_para_proc(pub_tribunal: str | None) -> str | None:
    """Mapeia ``Pub.Tribunal`` para o formato canônico de
    ``Proc.tribunal``. Devolve ``None`` se a entrada for vazia.
    """
    if not pub_tribunal:
        return None
    s = str(pub_tribunal).strip().upper()
    return _PUB_TRIB_PARA_PROC.get(s, s)
