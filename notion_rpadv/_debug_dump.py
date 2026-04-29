"""Round Auditoria 2026-04-29 — instrumentação temporária para diagnosticar
dark residual em Importar/Logs.

Este módulo é **temporário** — será removido no commit final da Etapa 1
após análise do dump capturado pelo usuário.

Uso (do prompt do usuário):

    $env:NOTION_DEBUG_DUMP=1
    python -m notion_rpadv
    # Navegar: Dashboard → Importar → Logs → Processos → Clientes → Configurações
    # Fechar.

O dump fica em ``./debug_dump.jsonl`` (raiz do projeto). Cada linha é um
objeto JSON com a árvore completa de QWidgets da página visitada.

A activação é via env var — zero impacto em runtime quando off.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QWidget


_DUMP_PATH = Path("debug_dump.jsonl")


def _palette_dict(palette: QPalette) -> dict[str, str]:
    """Captura cores das principais ColorRoles de uma QPalette."""
    roles = {
        "window":      QPalette.ColorRole.Window,
        "window_text": QPalette.ColorRole.WindowText,
        "base":        QPalette.ColorRole.Base,
        "alt_base":    QPalette.ColorRole.AlternateBase,
        "text":        QPalette.ColorRole.Text,
        "button":      QPalette.ColorRole.Button,
        "button_text": QPalette.ColorRole.ButtonText,
        "highlight":   QPalette.ColorRole.Highlight,
        "highlighted_text": QPalette.ColorRole.HighlightedText,
        "placeholder": QPalette.ColorRole.PlaceholderText,
    }
    out: dict[str, str] = {}
    for name, role in roles.items():
        try:
            color = palette.color(role)
            out[name] = color.name(color.NameFormat.HexArgb)
        except Exception:  # noqa: BLE001
            out[name] = "?"
    return out


def _widget_to_dict(widget: QWidget, depth: int) -> dict[str, Any]:
    """Captura estado visual + atributos de um QWidget."""
    parent = widget.parent()
    parent_class = type(parent).__name__ if parent else None
    parent_name = parent.objectName() if isinstance(parent, QWidget) else None

    # Stylesheet declarada (não a efetiva — Qt não expõe a efetiva diretamente).
    stylesheet = widget.styleSheet() or ""

    # Atributos relevantes pra paint behavior.
    attrs = {
        "auto_fill_background": widget.autoFillBackground(),
        "wa_styled_background": widget.testAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
        ),
        "wa_translucent_background": widget.testAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
        ),
        "wa_opaque_paint_event": widget.testAttribute(
            Qt.WidgetAttribute.WA_OpaquePaintEvent,
        ),
    }

    geom = widget.geometry()
    return {
        "depth": depth,
        "class": type(widget).__name__,
        "object_name": widget.objectName(),
        "parent_class": parent_class,
        "parent_object_name": parent_name,
        "geometry": {
            "x": geom.x(), "y": geom.y(),
            "w": geom.width(), "h": geom.height(),
        },
        "visible": widget.isVisible(),
        "stylesheet": stylesheet[:500],  # cap for sanity
        "stylesheet_full_len": len(stylesheet),
        "palette": _palette_dict(widget.palette()),
        "attrs": attrs,
    }


def _walk(widget: QWidget, depth: int = 0) -> Any:
    """DFS sobre widgets descendentes."""
    yield _widget_to_dict(widget, depth)
    for child in widget.children():
        if isinstance(child, QWidget):
            yield from _walk(child, depth + 1)


def dump_widget_tree(widget: QWidget | None, page_id: str, path: str | Path = _DUMP_PATH) -> None:
    """Escreve uma linha JSON em ``path`` com a árvore completa de
    ``widget`` + metadados.

    Idempotente: append-only — chame em cada navegação. Falha silenciosa
    se ``widget is None`` ou se houver IO error.
    """
    if widget is None:
        return
    try:
        tree = list(_walk(widget))
        entry = {
            "page_id": page_id,
            "page_class": type(widget).__name__,
            "timestamp": time.time(),
            "n_widgets": len(tree),
            "tree": tree,
        }
        path = Path(path)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        # Instrumentação não pode quebrar o app.
        print(f"[debug_dump] erro dumping {page_id}: {exc}")
