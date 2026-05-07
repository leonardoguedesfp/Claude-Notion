"""Shim de compatibilidade — Round 10 (2026-05-07).

A implementação das regras DJE foi movida para o pacote
:mod:`notion_rpadv.services.dje_regras` (camada base + 26 regras de
Alerta contadoria + tipos ``TagApp`` e ``VeredictoPub``).

Este arquivo continua existindo apenas para que imports legados
``from notion_rpadv.services.dje_regras_v8 import aplicar_todas_regras``
não quebrem instantaneamente. A intenção é remover este shim no
Round 11.

Observação: a *signature* de :func:`aplicar_todas_regras` mudou no
Round 10 — passou a devolver :class:`VeredictoPub` em vez de
``tuple[list[str], list[str]]``. Imports de constantes antigas
(``ALERTA_*``, ``TAREFA_*``, etc.) **não** são re-exportados; a
maioria não tem mais correspondente vivo após a remoção das regras
deprecadas.
"""
from __future__ import annotations

import warnings

from notion_rpadv.services.dje_regras import (
    SUFIXO_APP,
    PropriedadeNotion,
    TagApp,
    VeredictoPub,
    aplicar_todas_regras,
)

warnings.warn(
    "Importe de notion_rpadv.services.dje_regras diretamente; este shim "
    "(notion_rpadv.services.dje_regras_v8) some no Round 11.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "PropriedadeNotion",
    "SUFIXO_APP",
    "TagApp",
    "VeredictoPub",
    "aplicar_todas_regras",
]
