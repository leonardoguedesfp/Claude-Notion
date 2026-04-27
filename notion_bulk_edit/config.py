"""Configurações centrais do escritório RPADV.

Token do Notion é gerenciado pelo keyring (Windows Credential Manager).
O CLI legado e o app desktop leem do mesmo keyring — um único token por máquina.
"""
from __future__ import annotations

import os
from typing import Final

# ---------------------------------------------------------------------------
# Keyring — acesso pelo auth/token_store.py; não importe keyring aqui diretamente
# ---------------------------------------------------------------------------

KEYRING_SERVICE: Final = "NotionRPADV"
KEYRING_USERNAME: Final = "notion_token"

# ---------------------------------------------------------------------------
# IDs das bases Notion (configure com os IDs reais do workspace RPADV)
# Obtenha via: GET https://api.notion.com/v1/databases  ou URL da base no Notion
# Formato: 32 hex chars sem hífens ou com hífens UUID.
# ---------------------------------------------------------------------------

DATA_SOURCES: Final[dict[str, str]] = {
    "Processos": os.getenv("NOTION_DB_PROCESSOS", "5e93b734-4043-4c89-a513-5e00a14081bb"),
    "Clientes":  os.getenv("NOTION_DB_CLIENTES",  "939e5dcf-51bd-4ffa-a28e-0313899fd229"),
    "Tarefas":   os.getenv("NOTION_DB_TAREFAS",   "3a8bb311-5c1b-42ac-a3b2-859b75911e91"),
    "Catalogo":  os.getenv("NOTION_DB_CATALOGO",  "79afc833-77e2-4574-98ba-ebed7bd7e66c"),
}

# Nome amigável → nome da planilha Excel (para importar/exportar)
SHEET_NAMES: Final[dict[str, str]] = {
    "Processos": "Processos",
    "Clientes":  "Clientes",
    "Tarefas":   "Tarefas",
    "Catalogo":  "Catálogo",
}

# ---------------------------------------------------------------------------
# Usuários do escritório  (ID Notion real → dados locais)
# Obtenha os IDs via: GET https://api.notion.com/v1/users
# ---------------------------------------------------------------------------

NOTION_USERS: Final[dict[str, dict[str, str]]] = {
    # "notion_user_id": { "name": "...", "initials": "...", "role": "..." }
    "DEBORAH_NOTION_ID":  {"name": "Déborah",  "initials": "DM", "role": "Administradora"},
    "LEONARDO_NOTION_ID": {"name": "Leonardo", "initials": "LV", "role": "Sócio em formação"},
    "RICARDO_NOTION_ID":  {"name": "Ricardo",  "initials": "RP", "role": "Sócio fundador"},
    "MARIANA_NOTION_ID":  {"name": "Mariana",  "initials": "MS", "role": "Advogada"},
    "CARLA_NOTION_ID":    {"name": "Carla",    "initials": "CB", "role": "Estagiária"},
}

# Usuários que podem fazer login no app (ids locais)
USUARIOS_AUTORIZADOS: Final[list[str]] = ["deborah", "leonardo"]

# Usuários locais (para exibição e registro de log; não são IDs Notion)
USUARIOS_LOCAIS: Final[dict[str, dict[str, str]]] = {
    "deborah":  {"name": "Déborah",  "initials": "DM", "role": "Administradora"},
    "leonardo": {"name": "Leonardo", "initials": "LV", "role": "Sócio em formação"},
    "ricardo":  {"name": "Ricardo",  "initials": "RP", "role": "Sócio fundador"},
    "mariana":  {"name": "Mariana",  "initials": "MS", "role": "Advogada"},
    "carla":    {"name": "Carla",    "initials": "CB", "role": "Estagiária"},
}

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

NOTION_API_BASE: Final = "https://api.notion.com/v1"
NOTION_VERSION: Final  = "2022-06-28"

# Rate limit — Notion permite ~3 req/s por integração
RATE_LIMIT_RPS: Final[float] = 3.0

# Valor sentinela para limpar uma propriedade (usado no CLI legado)
SENTINEL_CLEAR: Final = "__CLEAR__"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

APP_NAME: Final    = "Notion RPADV"
APP_VERSION: Final = "0.4.2"
APP_BUILD: Final   = "2026.04"

# Caminho do cache SQLite
import pathlib

def get_cache_dir() -> pathlib.Path:
    """Retorna %APPDATA%\\NotionRPADV no Windows; ~/.notionrpadv no Linux/Mac."""
    base = pathlib.Path(os.getenv("APPDATA", "~")).expanduser()
    cache = base / "NotionRPADV"
    cache.mkdir(parents=True, exist_ok=True)
    return cache

def get_cache_db_path() -> pathlib.Path:
    return get_cache_dir() / "cache.db"

# Staleness threshold — cache mais antigo que isto sugere refresh
CACHE_STALE_HOURS: Final = 2
