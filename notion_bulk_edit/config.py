"""Configurações centrais do escritório RPADV.

Token do Notion é gerenciado pelo keyring (Windows Credential Manager).
O CLI legado e o app desktop leem do mesmo keyring — um único token por máquina.
"""
from __future__ import annotations

import os
import pathlib  # BUG-31: moved to top (was E402 at line 87)
from typing import Final

# ---------------------------------------------------------------------------
# Keyring — acesso pelo auth/token_store.py; não importe keyring aqui diretamente
# ---------------------------------------------------------------------------

KEYRING_SERVICE: Final = "NotionRPADV"
KEYRING_USERNAME: Final = "notion_token"

# ---------------------------------------------------------------------------
# IDs das bases Notion (data_source_ids — igual ao database UUID da URL).
# Obtenha via a URL da base no Notion: notion.so/{workspace}/{database-uuid}
# BUG-08: estes são data_source_ids, passados diretamente para /data_sources/{id}/query
# ---------------------------------------------------------------------------

DATA_SOURCES: Final[dict[str, str]] = {
    # BUG-N3: These are data_source_ids (same UUID as the Notion database URL).
    # They are passed directly to /data_sources/{id}/query (API 2025-09-03).
    # Empirically validated: Processos returned 1108 pages in production.
    # To regenerate: GET https://api.notion.com/v1/databases/{ID} → id field.
    # See tests/test_endpoint_data_source.py for the integration smoke test.
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
    # UUIDs obtained via GET https://api.notion.com/v1/users
    "23fd872b-594c-8178-840c-00029746e827": {"name": "Déborah",  "initials": "DM", "role": "Administradora"},
    "240d872b-594c-81f4-82e1-000212a926fc": {"name": "Leonardo", "initials": "LV", "role": "Sócio em formação"},
    "23fd872b-594c-814a-b7b8-00025b13b424": {"name": "Ricardo",  "initials": "RP", "role": "Sócio fundador"},
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
NOTION_VERSION: Final  = "2025-09-03"

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

# ---------------------------------------------------------------------------
# Schema dinâmico (Fases 1+)
# ---------------------------------------------------------------------------

# Fase 1 — adapter shim em schemas.py: quando False, o SCHEMAS proxy devolve
# sempre o conteúdo legado hardcoded; quando True, lê do registry dinâmico
# para as bases listadas em DYNAMIC_BASES. Ativado na Fase 2a (Catálogo).
# Removida na Fase 3 (assumido sempre on).
USE_DYNAMIC_SCHEMA: bool = True

# Fase 2 — granularidade por base. Bases ausentes caem no _LEGACY_SCHEMAS
# mesmo com USE_DYNAMIC_SCHEMA=True. Permite migração base-a-base.
# Fase 2a: Catálogo (resolve BUG-OP-08).
# Fase 2b: Tarefas (resolve STATUS_TAREFA hardcoded — Notion agora tem
#   campo Status real com opções Pendente/Concluída).
# Fase 2c: Clientes (32 props; slugs alinhados — cpf→cpf_cnpj, email→e_mail,
#   notas→observacoes; cidade vira rich_text; coluna virtual n_processos
#   é descontinuada).
# Fase 2d adiciona Processos. Fase 3 remove granularidade.
DYNAMIC_BASES: set[str] = {"Catalogo", "Tarefas", "Clientes"}
