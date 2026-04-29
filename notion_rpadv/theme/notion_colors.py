"""Fase 3 — schema dinâmico: mapeamento de cores nominais do Notion para hex.

A API Notion entrega cores como strings nominais ('blue', 'purple',
'red', 'default', etc.). Este mapa traduz para hex sólido. Usado por
``schema_registry._dict_to_propspec`` pra popular ``PropSpec.cor_por_valor``
(diagnóstico — preserva o que veio do Notion).

Round 3b-2: a paleta paralela ``NOTION_CHIP_PALETTE`` + helpers
``chip_colors_for`` / ``hex_to_color_name`` foram removidos. Rendering de
chip agora consome ``notion_rpadv.theme.colors_overrides`` + paleta brand
via ``tokens.resolve_chip_color``. ``cor_por_valor`` permanece populado
mas não é mais consumido pra cor visual — só pra diagnóstico/inspeção
("qual cor está configurada no Notion pra este valor").
"""
from __future__ import annotations

# Cor nominal do Notion → hex (#RRGGBB).
# Cobre os 10 valores que a API Notion expõe em propriedades de select
# e multi_select. Mantém 'default' como cinza neutro — Notion entrega
# 'default' para opções sem cor explícita.
NOTION_COLOR_TO_HEX: dict[str, str] = {
    "default":  "#E0E0E0",  # cinza neutro (chip sem cor explícita)
    "gray":     "#9E9E9E",
    "brown":    "#795548",
    "orange":   "#FF9800",
    "yellow":   "#FFD600",
    "green":    "#4CAF50",
    "blue":     "#2196F3",
    "purple":   "#9C27B0",
    "pink":     "#EC407A",
    "red":      "#F44336",
}


def color_to_hex(notion_color: str) -> str:
    """Devolve hex correspondente a uma cor nominal do Notion.

    Cores desconhecidas (futuras adições da API) caem no default cinza
    silenciosamente — diagnóstico segue funcionando, sem crash.
    """
    return NOTION_COLOR_TO_HEX.get(notion_color, NOTION_COLOR_TO_HEX["default"])
