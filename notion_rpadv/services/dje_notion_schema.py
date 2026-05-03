"""Detecção dinâmica de capabilities do schema da database 📬 Publicações
no Notion (Round 2, 2026-05-03).

Substitui o opt-in manual ``schema_tem_duplicatas_suprimidas=False``
introduzido no Round 1 por **detecção automática** no startup da
sessão de sync. O app consulta o schema do data source via
``GET /v1/data_sources/{id}`` e descobre quais propriedades opcionais
existem.

Erros de rede/auth NÃO derrubam o sync: caem em fallback gracioso pra
``False`` em todas as capabilities + warning, mantendo paridade com
o comportamento legacy.

Uso típico (no UI worker, antes de chamar ``sincronizar_pendentes``):

```python
from notion_rpadv.services.dje_notion_constants import (
    NOTION_PUBLICACOES_DATA_SOURCE_ID,
)
from notion_rpadv.services.dje_notion_schema import NotionSchemaCapabilities

caps = NotionSchemaCapabilities.from_notion(
    client, NOTION_PUBLICACOES_DATA_SOURCE_ID,
)
sincronizar_pendentes(
    client=client, dje_conn=conn, cache_conn=cache_conn,
    schema_tem_duplicatas_suprimidas=caps.has_duplicatas_suprimidas,
)
```

Cache: 1 fetch por sessão. Não persiste em SQLite. Se o usuário criar
ou remover propriedades no meio da sessão (raro), basta reiniciar o
app pra re-detectar.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from notion_bulk_edit.notion_api import (
    NotionAPIError,
    NotionAuthError,
    NotionClient,
    NotionRateLimitError,
)

logger = logging.getLogger("dje.notion.schema")


# ---------------------------------------------------------------------------
# Nome canônico da propriedade detectada (Round 2)
# ---------------------------------------------------------------------------

#: Nome exato da propriedade rich_text "Duplicatas suprimidas" no Notion
#: (criada manualmente pelo usuário entre Round 1 e Round 2). Bumpe esta
#: constante se o nome mudar — todas as detecções e payloads usam ela.
PROPERTY_DUPLICATAS_SUPRIMIDAS: str = "Duplicatas suprimidas"


# ---------------------------------------------------------------------------
# Estrutura de capabilities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NotionSchemaCapabilities:
    """Reflete o que o schema atual da database 📬 Publicações suporta.

    Os flags são populados via ``from_notion`` no startup da sessão.
    Em qualquer erro de detecção, todos os flags caem para ``False``
    (modo legacy) e a sessão segue sem bloqueio.

    ``raw_property_names``: snapshot do conjunto completo de nomes de
    propriedade do schema, exposto pra debug/log e pra futuras
    detecções (ex: ``has_pdf_documento``, ``has_origem``, etc.).
    """

    has_duplicatas_suprimidas: bool = False
    raw_property_names: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def legacy_fallback(cls) -> "NotionSchemaCapabilities":
        """Capabilities mínimas — usadas como fallback em erro ou em
        contextos sem cliente Notion (testes locais)."""
        return cls()

    @classmethod
    def from_notion(
        cls,
        client: NotionClient,
        data_source_id: str,
    ) -> "NotionSchemaCapabilities":
        """1 fetch ao Notion (``GET /v1/data_sources/{id}``) pra
        descobrir quais propriedades existem. Em qualquer erro
        (auth, rate limit, network, payload malformado), devolve
        ``legacy_fallback()`` + warning no log.

        Não levanta — falha é absorvida pra não bloquear o sync.
        """
        try:
            properties = _fetch_property_names(client, data_source_id)
        except NotionAuthError as exc:
            logger.warning(
                "DJE.notion.schema: falha de auth ao detectar capabilities "
                "(%s). Modo legacy ativo: flush não populará "
                "%r. Verifique o token Notion.",
                exc, PROPERTY_DUPLICATAS_SUPRIMIDAS,
            )
            return cls.legacy_fallback()
        except (NotionRateLimitError, NotionAPIError) as exc:
            logger.warning(
                "DJE.notion.schema: falha de API ao detectar capabilities "
                "(%s). Modo legacy ativo: flush não populará %r.",
                exc, PROPERTY_DUPLICATAS_SUPRIMIDAS,
            )
            return cls.legacy_fallback()
        except Exception as exc:  # noqa: BLE001
            # Catch-all defensivo — qualquer erro inesperado (ex:
            # response sem campo "properties") cai no fallback.
            logger.warning(
                "DJE.notion.schema: erro inesperado ao detectar "
                "capabilities (%s). Modo legacy ativo.",
                exc,
            )
            return cls.legacy_fallback()

        caps = cls(
            has_duplicatas_suprimidas=(
                PROPERTY_DUPLICATAS_SUPRIMIDAS in properties
            ),
            raw_property_names=frozenset(properties),
        )
        logger.info(
            "DJE.notion.schema: capabilities detectadas — "
            "has_duplicatas_suprimidas=%s (total %d propriedades)",
            caps.has_duplicatas_suprimidas, len(caps.raw_property_names),
        )
        return caps


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _fetch_property_names(
    client: NotionClient,
    data_source_id: str,
) -> set[str]:
    """Retorna o conjunto de nomes de propriedade do schema do data
    source. Levanta as exceções tipadas do ``NotionClient`` em falha
    (caller absorve)."""
    response: dict[str, Any] = client.get_data_source(data_source_id)
    properties = response.get("properties")
    if not isinstance(properties, dict):
        # Schema malformado — devolve set vazio (vai cair em legacy).
        logger.warning(
            "DJE.notion.schema: response sem 'properties' dict — "
            "fallback pra legacy",
        )
        return set()
    return set(properties.keys())
