"""Constantes operacionais da integração Notion ↔ Leitor DJE (Fase 5,
2026-05-03).

Database 📬 Publicações já existe no Notion do escritório dentro da
página-mãe "🏛️ Ricardo Passos Advocacia — Sistema Jurídico". Os IDs
abaixo são os ``data_source_id`` (mesmos UUIDs usados no
endpoint ``/v1/data_sources/{id}/query``).
"""
from __future__ import annotations

from typing import Final

# Data source IDs — extraídos da URL da database e do data source query.
NOTION_PUBLICACOES_DATA_SOURCE_ID: Final[str] = (
    "78070780-8ff2-4532-8f78-9e078967f191"
)
NOTION_PROCESSOS_DATA_SOURCE_ID: Final[str] = (
    "5e93b734-4043-4c89-a513-5e00a14081bb"
)

# Rate limit — Notion permite ~3 req/s por integração; usar 350ms entre
# chamadas pra ficar com margem confortável.
NOTION_RATE_LIMIT_DELAY_MS: Final[int] = 350

# Retry policy: 3 tentativas totais (1 inicial + 2 retries) com backoff
# exponencial em 429. Após 3 falhas em uma chamada específica, marca a
# publicação como falha e segue. ``notion_attempts`` no banco persiste
# entre execuções — uma publicação que falhar 3 vezes total (em
# execuções diferentes) fica "presa" e aparece no botão "Tentar reenviar
# falhas".
NOTION_MAX_RETRY_ATTEMPTS: Final[int] = 3
NOTION_RETRY_BACKOFFS_SECONDS: Final[tuple[float, ...]] = (1.0, 2.0, 4.0)

# Limite de chars em rich_text inline (propriedade) e em block (corpo).
# Notion oficialmente aceita 2000 chars por rich_text item.
NOTION_TEXTO_INLINE_LIMIT: Final[int] = 2000
NOTION_BLOCK_TEXT_LIMIT: Final[int] = 2000
