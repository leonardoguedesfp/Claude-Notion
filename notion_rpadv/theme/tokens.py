"""Tokens do design system RPADV traduzidos para Python.

Única fonte de verdade para cores e tipografia no app PySide6.
Nunca use hex hardcoded fora deste módulo.
"""
from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Dark palette
# ---------------------------------------------------------------------------

DARK: Final[Palette] = Palette(
    # Brand primitives (same across themes)
    navy_base="#104063",
    navy_dark="#0C324D",
    navy_light="#F5F7F9",
    petrol_base="#395A5A",
    cream="#EDEAE4",

    # §0.2 Surfaces — V2 spec: bg #142430, panels #1A2D3D, sidebar #0A1F2D
    app_bg="#142430",
    app_panel="#1A2D3D",
    app_elevated="#243444",
    app_sidebar="#0A1F2D",
    app_sidebar_fg="rgba(232,228,221,0.95)",
    app_sidebar_fg_muted="rgba(232,228,221,0.55)",
    app_sidebar_hover="rgba(232,228,221,0.07)",
    app_sidebar_active="rgba(90,146,186,0.20)",

    # §0.2 Text — cream base #E8E4DD
    app_fg="rgba(232,228,221,0.95)",
    app_fg_muted="rgba(232,228,221,0.72)",
    app_fg_subtle="rgba(232,228,221,0.48)",
    app_fg_strong="#E8E4DD",

    # Borders
    app_border="rgba(232,228,221,0.10)",
    app_border_strong="rgba(232,228,221,0.20)",
    app_divider="rgba(232,228,221,0.06)",

    # §0.2 Accent — brighter blue for darker surfaces
    app_accent="#5A92BA",
    app_accent_hover="#6DA4C8",
    app_accent_soft="rgba(90,146,186,0.16)",
    app_accent_fg="#FFFFFF",
    app_focus_ring="rgba(90,146,186,0.45)",

    # Table rows
    app_row_hover="rgba(90,146,186,0.08)",
    app_row_selected="rgba(90,146,186,0.14)",

    # Status
    app_success="#6FA487",
    app_success_bg="rgba(111,164,135,0.12)",
    app_warning="#D9B26B",
    app_warning_bg="rgba(217,178,107,0.12)",
    app_danger="#D17777",
    app_danger_bg="rgba(209,119,119,0.12)",
    app_info="#6A9FBC",
    app_info_bg="rgba(106,159,188,0.12)",

    # §4.4 Dirty cell — V2 dark: warmer yellow with higher opacity
    app_cell_dirty="rgba(255,217,90,0.18)",
    app_cell_dirty_border="#D9B26B",

    # Chips — desaturated for dark surfaces (§0.2)
    chip_default=ChipPalette(bg="rgba(232,228,221,0.09)",  fg="rgba(232,228,221,0.88)"),
    chip_blue=ChipPalette(   bg="rgba(90,146,186,0.18)",   fg="#A8C8DF"),
    chip_purple=ChipPalette( bg="rgba(136,110,196,0.18)",  fg="#C0AAEE"),
    chip_green=ChipPalette(  bg="rgba(111,164,135,0.16)",  fg="#A0D4B8"),
    chip_orange=ChipPalette( bg="rgba(217,138,79,0.18)",   fg="#E0A870"),
    chip_red=ChipPalette(    bg="rgba(209,119,119,0.18)",  fg="#E8A0A0"),
    chip_yellow=ChipPalette( bg="rgba(217,178,107,0.18)",  fg="#E0C880"),
    chip_gray=ChipPalette(   bg="rgba(160,156,152,0.16)",  fg="#C8C4C0"),
    chip_petrol=ChipPalette( bg="rgba(89,140,140,0.18)",   fg="#88C0C0"),
    chip_amber=ChipPalette(  bg="rgba(217,138,79,0.18)",   fg="#E0A870"),
)


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

def chip_palette(color: str, dark: bool = False) -> ChipPalette:
    """Return the bg/fg ChipPalette for a given semantic colour name.

    Recognised names: blue, purple, green, orange, red, yellow, gray,
    petrol, amber.  Unknown names fall back to chip_default.
    """
    p: Palette = DARK if dark else LIGHT
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
