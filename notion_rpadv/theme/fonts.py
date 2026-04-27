"""Carregamento das fontes do design system via QFontDatabase.

Fontes utilizadas:
  - Playfair Display  (display/headings, serif)
  - Nunito Sans       (body/UI, sans-serif)
  - JetBrains Mono    (mono, code)

Download manual das fontes (colocar em assets/fonts/):
  Playfair Display : https://fonts.google.com/specimen/Playfair+Display
  Nunito Sans      : https://fonts.google.com/specimen/Nunito+Sans
  JetBrains Mono   : https://fonts.google.com/specimen/JetBrains+Mono

Estrutura esperada dentro de assets/fonts/:
  fonts/
    NunitoSans/
      NunitoSans-Light.ttf          (weight 300)
      NunitoSans-Regular.ttf        (weight 400)
      NunitoSans-Medium.ttf         (weight 500)
      NunitoSans-SemiBold.ttf       (weight 600)
      NunitoSans-Bold.ttf           (weight 700)
    PlayfairDisplay/
      PlayfairDisplay-Regular.ttf   (weight 400)
      PlayfairDisplay-Medium.ttf    (weight 500)
      PlayfairDisplay-SemiBold.ttf  (weight 600)
      PlayfairDisplay-Bold.ttf      (weight 700)
    JetBrainsMono/
      JetBrainsMono-Regular.ttf     (weight 400)
      JetBrainsMono-Medium.ttf      (weight 500)
      JetBrainsMono-Bold.ttf        (weight 700)

Se os arquivos não existirem, as fontes do sistema são usadas como fallback
sem lançar exceções.
"""
from __future__ import annotations

import logging
import pathlib
from typing import Sequence

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from notion_rpadv.theme.tokens import (
    FONT_BODY,
    FONT_DISPLAY,
    FONT_MONO,
    FW_REGULAR,
    FS_MD,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------

ASSETS_DIR: pathlib.Path = pathlib.Path(__file__).parent.parent / "assets"
FONTS_DIR: pathlib.Path  = ASSETS_DIR / "fonts"

# Ordered list of (relative_path, description) pairs for all font files.
# Paths are relative to FONTS_DIR.
_FONT_FILES: Sequence[tuple[str, str]] = (
    # Nunito Sans
    ("NunitoSans/NunitoSans-Light.ttf",    "Nunito Sans Light"),
    ("NunitoSans/NunitoSans-Regular.ttf",  "Nunito Sans Regular"),
    ("NunitoSans/NunitoSans-Medium.ttf",   "Nunito Sans Medium"),
    ("NunitoSans/NunitoSans-SemiBold.ttf", "Nunito Sans SemiBold"),
    ("NunitoSans/NunitoSans-Bold.ttf",     "Nunito Sans Bold"),
    # Playfair Display
    ("PlayfairDisplay/PlayfairDisplay-Regular.ttf",  "Playfair Display Regular"),
    ("PlayfairDisplay/PlayfairDisplay-Medium.ttf",   "Playfair Display Medium"),
    ("PlayfairDisplay/PlayfairDisplay-SemiBold.ttf", "Playfair Display SemiBold"),
    ("PlayfairDisplay/PlayfairDisplay-Bold.ttf",     "Playfair Display Bold"),
    # JetBrains Mono
    ("JetBrainsMono/JetBrainsMono-Regular.ttf", "JetBrains Mono Regular"),
    ("JetBrainsMono/JetBrainsMono-Medium.ttf",  "JetBrains Mono Medium"),
    ("JetBrainsMono/JetBrainsMono-Bold.ttf",    "JetBrains Mono Bold"),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_fonts() -> None:
    """Registra Playfair Display, Nunito Sans e JetBrains Mono no QFontDatabase.

    Itera sobre todos os arquivos .ttf definidos em ``_FONT_FILES``.  Arquivos
    ausentes são silenciosamente ignorados (apenas um aviso de debug é emitido)
    para que o app funcione mesmo sem as fontes instaladas.

    Deve ser chamado **uma vez**, após a criação de ``QApplication`` e antes de
    criar qualquer widget.
    """
    loaded = 0
    missing = 0

    for relative, description in _FONT_FILES:
        path = FONTS_DIR / relative
        if not path.is_file():
            _log.debug("Fonte não encontrada (fallback do sistema): %s", path)
            missing += 1
            continue

        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            _log.warning(
                "QFontDatabase rejeitou o arquivo de fonte: %s (%s)",
                path,
                description,
            )
        else:
            _log.debug("Fonte carregada: %s (id=%d)", description, font_id)
            loaded += 1

    if missing == len(_FONT_FILES):
        _log.info(
            "Nenhum arquivo de fonte encontrado em %s — usando fontes do sistema.",
            FONTS_DIR,
        )
    elif loaded:
        _log.info(
            "Design system: %d fonte(s) carregada(s), %d não encontrada(s).",
            loaded,
            missing,
        )


def set_app_font(app: QApplication) -> None:
    """Define a fonte padrão do app como Nunito Sans 13 px (Regular).

    Chame esta função depois de ``load_fonts()`` para que o QFontDatabase já
    tenha as fontes registradas antes da resolução do nome.
    """
    font = body_font(size=FS_MD, weight=FW_REGULAR)
    app.setFont(font)


# ---------------------------------------------------------------------------
# Font constructors
# ---------------------------------------------------------------------------

def display_font(size: int = 22, weight: int = FW_REGULAR) -> QFont:
    """Retorna um QFont para headings/display (Playfair Display, serif).

    Parâmetros
    ----------
    size:
        Tamanho em pixels (padrão: 22 px = FS_3XL).
    weight:
        Peso da fonte — use as constantes FW_* de tokens.py (padrão: 400).
    """
    font = QFont(FONT_DISPLAY)
    font.setPixelSize(size)
    font.setWeight(_qt_weight(weight))
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
    )
    return font


def body_font(size: int = FS_MD, weight: int = FW_REGULAR) -> QFont:
    """Retorna um QFont para texto de UI (Nunito Sans, sans-serif).

    Parâmetros
    ----------
    size:
        Tamanho em pixels (padrão: 13 px = FS_MD).
    weight:
        Peso da fonte — use as constantes FW_* de tokens.py (padrão: 400).
    """
    font = QFont(FONT_BODY)
    font.setPixelSize(size)
    font.setWeight(_qt_weight(weight))
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
    )
    return font


def mono_font(size: int = 12, weight: int = FW_REGULAR) -> QFont:
    """Retorna um QFont monoespaçado (JetBrains Mono).

    Parâmetros
    ----------
    size:
        Tamanho em pixels (padrão: 12 px).
    weight:
        Peso da fonte — use as constantes FW_* de tokens.py (padrão: 400).
    """
    font = QFont(FONT_MONO)
    font.setPixelSize(size)
    font.setWeight(_qt_weight(weight))
    font.setFixedPitch(True)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
    )
    return font


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _qt_weight(css_weight: int) -> QFont.Weight:
    """Converte um peso CSS numérico (300-900) para QFont.Weight.

    Qt usa sua própria enumeração; este mapeamento cobre os valores usados
    no design system RPADV.
    """
    mapping: dict[int, QFont.Weight] = {
        100: QFont.Weight.Thin,
        200: QFont.Weight.ExtraLight,
        300: QFont.Weight.Light,
        400: QFont.Weight.Normal,
        500: QFont.Weight.Medium,
        600: QFont.Weight.DemiBold,
        700: QFont.Weight.Bold,
        800: QFont.Weight.ExtraBold,
        900: QFont.Weight.Black,
    }
    # Snap to nearest recognised weight
    if css_weight in mapping:
        return mapping[css_weight]
    nearest = min(mapping.keys(), key=lambda k: abs(k - css_weight))
    return mapping[nearest]
