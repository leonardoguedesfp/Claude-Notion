"""Tokens do design system RPADV traduzidos para Python.

Única fonte de verdade para cores e tipografia no app PySide6.
Nunca use hex hardcoded fora deste módulo.
"""
from __future__ import annotations

import re as _re
from dataclasses import dataclass
from typing import Final


# ---------------------------------------------------------------------------
# Chip palette
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChipPalette:
    bg: str
    fg: str


# ---------------------------------------------------------------------------
# Full palette
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Palette:
    # ------------------------------------------------------------------
    # Brand primitives
    # ------------------------------------------------------------------
    navy_base: str
    navy_dark: str
    navy_light: str
    petrol_base: str
    cream: str

    # ------------------------------------------------------------------
    # Surfaces
    # ------------------------------------------------------------------
    app_bg: str
    app_panel: str
    app_elevated: str
    app_sidebar: str
    app_sidebar_fg: str
    app_sidebar_fg_muted: str
    app_sidebar_hover: str
    app_sidebar_active: str

    # ------------------------------------------------------------------
    # Text / foreground
    # ------------------------------------------------------------------
    app_fg: str
    app_fg_muted: str
    app_fg_subtle: str
    app_fg_strong: str

    # ------------------------------------------------------------------
    # Borders
    # ------------------------------------------------------------------
    app_border: str
    app_border_strong: str
    app_divider: str

    # ------------------------------------------------------------------
    # Accent
    # ------------------------------------------------------------------
    app_accent: str
    app_accent_hover: str
    app_accent_soft: str
    app_accent_fg: str
    app_focus_ring: str

    # ------------------------------------------------------------------
    # Table rows
    # ------------------------------------------------------------------
    app_row_hover: str
    app_row_selected: str

    # ------------------------------------------------------------------
    # Status colours
    # ------------------------------------------------------------------
    app_success: str
    app_success_bg: str
    app_warning: str
    app_warning_bg: str
    app_danger: str
    app_danger_bg: str
    app_info: str
    app_info_bg: str

    # ------------------------------------------------------------------
    # Dirty-cell indicator
    # ------------------------------------------------------------------
    app_cell_dirty: str
    app_cell_dirty_border: str

    # ------------------------------------------------------------------
    # Chip colours (semantic name → bg/fg pair)
    # ------------------------------------------------------------------
    chip_default: ChipPalette
    chip_blue: ChipPalette
    chip_purple: ChipPalette
    chip_green: ChipPalette
    chip_orange: ChipPalette
    chip_red: ChipPalette
    chip_yellow: ChipPalette
    chip_gray: ChipPalette
    chip_petrol: ChipPalette
    chip_amber: ChipPalette


# ---------------------------------------------------------------------------
# Light palette
# ---------------------------------------------------------------------------

LIGHT: Final[Palette] = Palette(
    # Brand primitives
    navy_base="#104063",
    navy_dark="#0C324D",
    navy_light="#F5F7F9",
    petrol_base="#395A5A",
    cream="#EDEAE4",

    # Surfaces
    app_bg="#EDEAE4",
    app_panel="#FFFFFF",
    app_elevated="#FFFFFF",
    app_sidebar="#0C324D",
    app_sidebar_fg="#EDEAE4",
    app_sidebar_fg_muted="rgba(237,234,228,0.60)",
    app_sidebar_hover="rgba(237,234,228,0.08)",
    app_sidebar_active="rgba(237,234,228,0.14)",

    # Text
    app_fg="#142430",
    app_fg_muted="#3F4751",
    app_fg_subtle="#6F6B68",
    app_fg_strong="#0A0F14",

    # Borders
    app_border="#CAD5DD",
    app_border_strong="#9FB3C1",
    app_divider="rgba(20,36,48,0.06)",

    # Accent
    app_accent="#104063",
    app_accent_hover="#0C324D",
    app_accent_soft="rgba(16,64,99,0.08)",
    app_accent_fg="#FFFFFF",
    app_focus_ring="rgba(16,64,99,0.40)",

    # Table rows
    app_row_hover="rgba(57,90,90,0.04)",
    app_row_selected="rgba(16,64,99,0.06)",

    # Status
    app_success="#3F6E55",
    app_success_bg="rgba(63,110,85,0.10)",
    app_warning="#B58A3F",
    app_warning_bg="rgba(181,138,63,0.10)",
    app_danger="#9A3B3B",
    app_danger_bg="rgba(154,59,59,0.10)",
    app_info="#3B627F",
    app_info_bg="rgba(59,98,127,0.10)",

    # Dirty cell
    app_cell_dirty="rgba(181,138,63,0.14)",
    app_cell_dirty_border="#B58A3F",

    # Chips
    chip_default=ChipPalette(bg="rgba(20,36,48,0.06)",   fg="#142430"),
    chip_blue=ChipPalette(   bg="rgba(16,64,99,0.10)",   fg="#0C324D"),
    chip_purple=ChipPalette( bg="rgba(89,70,137,0.12)",  fg="#4B3E72"),
    chip_green=ChipPalette(  bg="rgba(63,110,85,0.12)",  fg="#2F5640"),
    chip_orange=ChipPalette( bg="rgba(181,110,63,0.14)", fg="#8B5028"),
    chip_red=ChipPalette(    bg="rgba(154,59,59,0.12)",  fg="#7A2E2E"),
    chip_yellow=ChipPalette( bg="rgba(181,138,63,0.16)", fg="#7A5C28"),
    chip_gray=ChipPalette(   bg="rgba(111,107,104,0.14)",fg="#4A4744"),
    chip_petrol=ChipPalette( bg="rgba(57,90,90,0.12)",   fg="#2C4646"),
    chip_amber=ChipPalette(  bg="rgba(181,110,63,0.14)", fg="#8B5028"),
)


# Round 3a: paleta DARK removida. App roda exclusivamente em modo claro
# (LIGHT) independente do tema do sistema operacional. Histórico do
# stylesheet escuro foi removido junto com qss_dark.py e o aparato de
# state machine em app.py (theme_pref / _resolve_dark / etc).


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

FONT_DISPLAY: Final = "Playfair Display"
FONT_BODY: Final    = "Nunito Sans"
FONT_MONO: Final    = "JetBrains Mono"

FONT_BODY_FALLBACK:    Final = f'"{FONT_BODY}", "Segoe UI", "Avenir Next", Arial, sans-serif'
FONT_DISPLAY_FALLBACK: Final = f'"{FONT_DISPLAY}", "Cormorant Garamond", Georgia, serif'
FONT_MONO_FALLBACK:    Final = f'"{FONT_MONO}", "Consolas", "Courier New", monospace'

# Font weights
FW_LIGHT:   Final = 300
FW_REGULAR: Final = 400
FW_MEDIUM:  Final = 500
FW_SEMIBOLD: Final = 600
FW_BOLD:    Final = 700

# Font sizes (px)
FS_2XS: Final = 9
FS_XS:  Final = 10
FS_SM:  Final = 11
FS_SM2: Final = 12
FS_MD:  Final = 13
FS_LG:  Final = 14
FS_XL:  Final = 16
FS_2XL: Final = 18
FS_3XL: Final = 22
FS_4XL: Final = 26
FS_5XL: Final = 36
FS_6XL: Final = 44

# Spacing (px — 4-point grid)
SP_1: Final = 4
SP_2: Final = 8
SP_3: Final = 12
SP_4: Final = 16
SP_5: Final = 20
SP_6: Final = 24
SP_8: Final = 32
SP_10: Final = 40
SP_12: Final = 48

# Border radius (px)
RADIUS_SM: Final = 2
RADIUS_MD: Final = 4
RADIUS_LG: Final = 6
RADIUS_XL: Final = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def chip_palette(color: str) -> ChipPalette:
    """Return the bg/fg ChipPalette for a given semantic colour name.

    Recognised names: blue, purple, green, orange, red, yellow, gray,
    petrol, amber.  Unknown names fall back to chip_default.

    Round 3a: parâmetro ``dark`` removido junto com a paleta DARK — sempre
    usa LIGHT.
    """
    p: Palette = LIGHT
    mapping: dict[str, ChipPalette] = {
        "blue":   p.chip_blue,
        "purple": p.chip_purple,
        "green":  p.chip_green,
        "orange": p.chip_orange,
        "red":    p.chip_red,
        "yellow": p.chip_yellow,
        "gray":   p.chip_gray,
        "grey":   p.chip_gray,
        "petrol": p.chip_petrol,
        "amber":  p.chip_amber,
    }
    return mapping.get(color, p.chip_default)


# ---------------------------------------------------------------------------
# Round 3b-2: override-driven chip color resolution
# ---------------------------------------------------------------------------

_RGBA_RE = _re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)",
    _re.IGNORECASE,
)


def parse_color(s: str) -> tuple[int, int, int, int]:
    """Parse ``"#RRGGBB"`` ou ``"rgba(R,G,B,A)"`` em tupla ``(r, g, b, a)``
    com cada componente em ``[0, 255]``.

    Útil pra construir ``QColor`` a partir das strings da paleta brand
    (que mistura formatos: ``LIGHT.chip_*.bg`` é rgba, ``LIGHT.chip_*.fg`` é
    hex sólido). Mantido sem import de Qt — pure Python — pra não acoplar
    o módulo de tokens à Qt.
    """
    s = s.strip()
    if s.startswith("#") and len(s) == 7:
        r = int(s[1:3], 16)
        g = int(s[3:5], 16)
        b = int(s[5:7], 16)
        return r, g, b, 255
    m = _RGBA_RE.match(s)
    if m:
        r = int(m.group(1))
        g = int(m.group(2))
        b = int(m.group(3))
        a_str = m.group(4)
        a = int(round(float(a_str) * 255)) if a_str else 255
        return r, g, b, a
    raise ValueError(f"Cor inválida: {s!r}")


def resolve_chip_color(base: str, prop_key: str, value: str) -> ChipPalette:
    """Resolve a cor de chip pra um valor de propriedade via override map.

    Consulta ``colors_overrides.OVERRIDES`` por ``(base, prop_key, value)``.
    Sem entrada → ``chip_default`` (cinza neutro). Com entrada → pega o
    nome da família e retorna o ``ChipPalette`` correspondente em ``LIGHT``.

    A cor que o Notion configurou pra opção é IGNORADA — fonte da verdade
    visual é o override map (paleta brand do escritório).
    """
    # Import adiado pra evitar ciclo (colors_overrides usa só constants).
    from notion_rpadv.theme.colors_overrides import OVERRIDES
    family = OVERRIDES.get((base, prop_key, value))
    if family is None:
        return LIGHT.chip_default
    return chip_palette(family)


def resolve_person_avatar_color(initials: str) -> tuple[str, str]:
    """Resolve cores do avatar de PersonChip a partir das iniciais.

    Retorna ``(bg_hex, fg_hex)`` — ambos sólidos, prontos pra ``QColor``.
    O avatar é círculo preenchido (não chip translúcido), então usamos
    ``ChipPalette.fg`` como bg sólido (cor escura saturada) + cream como
    fg do texto (iniciais em branco-creme legíveis sobre todas as 7
    famílias usáveis).

    Iniciais desconhecidas caem em ``"blue"`` (família histórica do
    avatar — bg ``#0C324D`` matches o navy original).
    """
    from notion_rpadv.theme.colors_overrides import PERSON_CHIP_COLORS
    family = PERSON_CHIP_COLORS.get(initials.upper(), "blue")
    pal = chip_palette(family)
    return pal.fg, "#EDEAE4"
