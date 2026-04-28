"""Fase 3 — schema dinâmico: mapeamento de cores nominais do Notion para hex.

A API Notion entrega cores como strings nominais ('blue', 'purple',
'red', 'default', etc.). Este mapa traduz para os hex usados em chips
coloridos no QSS e no rendering de delegates.

Substitui os mapas hardcoded `_COR_TRIBUNAL`, `_COR_FASE`, etc. que
viviam em `notion_bulk_edit/schemas.py` antes da Fase 3.

Notas de UX:
- Os tons são aproximações dos defaults visuais do Notion web. Cada
  PropSpec.cor_por_valor é populado em runtime via _dict_to_propspec
  (em schema_registry.py) lendo a cor nominal do registry.
- Se a Déborah/Ricardo quiserem cores específicas que divergem do
  Notion para uma propriedade, isso é fora de escopo desta fase —
  override fica em um arquivo separado (labels/colors_overrides.py)
  em fase futura, se houver demanda.
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
    silenciosamente — chip aparece, sem crash.
    """
    return NOTION_COLOR_TO_HEX.get(notion_color, NOTION_COLOR_TO_HEX["default"])
