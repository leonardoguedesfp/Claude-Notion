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

Round simplificação chip palette (Lote 1):
- Antes: chips usavam o hex "saturado" (NOTION_COLOR_TO_HEX) como fundo
  e ``_contrasting_text_color`` retornava preto OU branco binário.
  Resultado: texto preto sobre azul saturado #2196F3 ficava agressivo,
  pouco elegante.
- Agora: ``NOTION_CHIP_PALETTE`` define um par (bg_light, fg_dark) por
  cor — fundo claro + texto escuro saturado da MESMA família. Espelha
  o estilo de chips do Notion web. ``chip_colors_for(name)`` é a API
  pública. Para callers que só têm hex (cor_por_valor armazena hex
  desde a Fase 3), ``hex_to_color_name(hex_str)`` faz lookup reverso.
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


# Round simplificação chip palette (Lote 1): paleta especializada para
# chips renderizados em delegates / MultiSelectEditor. Cada cor é um par
# (bg_light, fg_dark) — fundo claro tonal + texto escuro saturado da
# mesma família. Espelha o estilo "chips do Notion web" e supera o
# binário preto/branco do _contrasting_text_color anterior.
#
# Otimizado para tema light (fundos claros sobre tabela cream). Em tema
# dark a paleta é razoavelmente legível também — um round dedicado
# pode diferenciar mais tarde se houver demanda.
NOTION_CHIP_PALETTE: dict[str, tuple[str, str]] = {
    "default":  ("#E0E0E0", "#37352F"),  # cinza neutro
    "gray":     ("#E3E2E0", "#32302C"),
    "brown":    ("#EEE0DA", "#5C3B2E"),
    "orange":   ("#FADEC9", "#854E1A"),
    "yellow":   ("#FDECC8", "#854610"),
    "green":    ("#DBEDDB", "#1F5026"),
    "blue":     ("#D3E5EF", "#0B4A6F"),
    "purple":   ("#E8DEEE", "#492B6B"),
    "pink":     ("#F5E0E9", "#8C2A4D"),
    "red":      ("#FFE2DD", "#8B1A0E"),
}


def chip_colors_for(notion_color: str) -> tuple[str, str]:
    """Devolve (bg_hex, fg_hex) para uma cor nominal do Notion.

    Cores desconhecidas caem em ``default`` silenciosamente — chip
    aparece em cinza neutro sem crash.
    """
    return NOTION_CHIP_PALETTE.get(
        notion_color, NOTION_CHIP_PALETTE["default"],
    )


# Mapa reverso hex → nome, derivado de NOTION_COLOR_TO_HEX. Mantido em
# memória global para evitar lookup quadrático em hot path de paint.
_HEX_TO_NAME: dict[str, str] = {
    h.upper(): name for name, h in NOTION_COLOR_TO_HEX.items()
}


def hex_to_color_name(hex_color: str) -> str:
    """Inverso de ``color_to_hex``: dado o hex, devolve o nome do
    Notion correspondente, ou ``"default"`` se não bater.

    Útil para callers que armazenam ``cor_por_valor`` como hex (default
    desde Fase 3) e precisam consultar a paleta de chip por nome.
    """
    if not hex_color:
        return "default"
    return _HEX_TO_NAME.get(hex_color.upper(), "default")
