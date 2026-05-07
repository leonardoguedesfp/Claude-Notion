"""Regras DJE — Round 10 (3 propriedades).

API pública::

    from notion_rpadv.services.dje_regras import (
        TagApp, VeredictoPub, aplicar_todas_regras,
    )

    veredicto = aplicar_todas_regras(pub, processo_record, cache_conn=conn)
    for prop, tags in veredicto.tags_por_propriedade().items():
        # prop ∈ {"Tarefa advogado", "Tarefa contadoria", "Alerta contadoria"}
        # tags são strings prontas (com sufixo " - App").
        ...

Histórico:

- Round 6 (2026-05-04): introdução das regras v8 num único módulo
  ``dje_regras_v8.py`` com 39 regras de monitoramento + 4 da camada
  base + 2 alertas técnicos. Single-multiselect ``Alerta contadoria
  (app)``.
- Round 10 (2026-05-07): refatoração em 3 propriedades, regras
  redistribuídas (4 camada base + 26 alerta contadoria) com códigos
  TA/TC/AC. Regras de baixo signal removidas (R1, R3, R10, R11×5,
  R28, R29, R30, R31, R32, R34, R36, R38, regra_texto_imprestavel).
  Hardcoding do sufixo ``" - App"`` em :class:`TagApp`.
"""
from __future__ import annotations

from .orquestrador import aplicar_todas_regras
from .tipos import (
    SUFIXO_APP,
    PropriedadeNotion,
    TagApp,
    VeredictoPub,
)

__all__ = [
    "PropriedadeNotion",
    "SUFIXO_APP",
    "TagApp",
    "VeredictoPub",
    "aplicar_todas_regras",
]
