"""Shortcut persistence — pure Python, no PySide6 dependency."""
from __future__ import annotations

import json
import pathlib

DEFAULT_SHORTCUTS: dict[str, str] = {
    "search": "Ctrl+K",
    # P1-001 (Lote 1): "new_record" (Ctrl+N) removido até existir
    # implementação real de criação inline. Reintroduzir junto com a
    # feature, sem rebind de usuários antigos (load_user_shortcuts dropa
    # entries que não existem mais nos defaults).
    "save": "Ctrl+S",
    "discard": "Escape",
    "refresh": "F5",
    "toggle_theme": "Ctrl+Shift+T",
    "nav_processos": "Ctrl+1",
    "nav_clientes": "Ctrl+2",
    "nav_tarefas": "Ctrl+3",
    "nav_catalogo": "Ctrl+4",
    # P3-004 (Lote 2): atalhos novos. Alt+K para o picker de colunas —
    # Ctrl+K era o desejo original mas estava em uso por "search"
    # (command palette). Ctrl+Shift+K (primeira tentativa) colidia com
    # o Notion desktop ("Pesquisa por Atalho") que fica aberto em
    # paralelo no fluxo do escritório. Alt+K e familia Alt+letra
    # raramente colidem com outros apps porque são reservados para
    # mnemonicos de menu.
    "open_columns_picker": "Alt+K",
    "toggle_sidebar": "Ctrl+B",
}


def _shortcuts_file() -> pathlib.Path:
    from notion_bulk_edit.config import get_cache_dir
    return get_cache_dir() / "shortcuts.json"


def load_user_shortcuts() -> dict[str, str]:
    """Load user-customised shortcuts from disk, falling back to defaults."""
    path = _shortcuts_file()
    if not path.exists():
        return dict(DEFAULT_SHORTCUTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_SHORTCUTS)
        if isinstance(data, dict):
            merged.update({k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)})
        return merged
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_SHORTCUTS)


def save_user_shortcuts(bindings: dict[str, str]) -> None:
    """Persist user-customised shortcuts to disk.

    BUG-OP-07: write to a temp file and rename so a crash mid-write doesn't
    leave the JSON half-written and unparseable on the next boot.
    """
    import os
    path = _shortcuts_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(bindings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)
