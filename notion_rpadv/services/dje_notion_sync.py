"""Sincronização de publicações DJEN → database 📬 Publicações no Notion
(Fase 5, 2026-05-03).

Fluxo (chamado após cada captura DJEN bem-sucedida em qualquer eixo
que grava no banco — ``oab_novas``, ``oab_periodo`` é transient e NÃO
chama, ``cnj_novas``):

1. ``fetch_pending_for_notion`` — pega publicações com
   ``notion_page_id IS NULL AND notion_attempts < 3``.
2. Pra cada uma:
   a. ``montar_payload_publicacao`` (mapper) — properties + children.
   b. ``client.create_page_in_data_source`` — cria a página.
   c. Em sucesso: ``mark_publicacao_sent_to_notion``.
   d. Em falha: ``mark_publicacao_notion_failure`` — increment attempts,
      grava erro, segue pra próxima.
3. Sleep ``NOTION_RATE_LIMIT_DELAY_MS`` entre cada chamada.
4. Em 429: backoff exponencial (1s, 2s, 4s) — máx 3 tentativas dentro
   da mesma execução; se persistir, conta como falha da publicação.

Cancelamento: aceita ``is_cancelled`` callback. Para entre publicações
(não no meio de uma chamada HTTP em retry). Items já enviados ficam
gravados.

UI: ``on_progress(idx, total)`` atualiza a barra. ``on_log(msg)``
emite linhas pro log da execução.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable

from notion_bulk_edit.notion_api import (
    NotionAPIError,
    NotionAuthError,
    NotionClient,
    NotionRateLimitError,
)
from notion_rpadv.services import dje_db
from notion_rpadv.services.dje_notion_constants import (
    NOTION_MAX_RETRY_ATTEMPTS,
    NOTION_PUBLICACOES_DATA_SOURCE_ID,
    NOTION_RATE_LIMIT_DELAY_MS,
    NOTION_RETRY_BACKOFFS_SECONDS,
)
from notion_rpadv.services.dje_notion_mapper import (
    montar_payload_publicacao,
)

logger = logging.getLogger("dje.notion.sync")


@dataclass
class NotionSyncOutcome:
    """Resultado consolidado da sync — usado pelo banner final."""

    sent: int = 0
    failed: int = 0
    stuck_after: int = 0  # publicações com 3+ falhas APÓS esta execução
    elapsed_seconds: float = 0.0
    cancelled: bool = False
    errors_sample: list[str] = field(default_factory=list)


def _sleep_ms(ms: int) -> None:
    time.sleep(ms / 1000.0)


def _create_page_with_retry(
    client: NotionClient,
    payload: dict,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Chama ``create_page_in_data_source`` com backoff em 429.

    Retorna ``page_id`` em sucesso. Levanta ``NotionAPIError`` (ou
    subclasse) na última falha. Backoff exponencial:
    ``NOTION_RETRY_BACKOFFS_SECONDS`` (1, 2, 4) entre tentativas; total
    de ``NOTION_MAX_RETRY_ATTEMPTS`` tentativas.

    O ``NotionClient`` interno já faz seu próprio retry em 429 antes de
    levantar — nosso retry aqui é um nível acima, pra cobrir 429
    persistente após o retry interno.
    """
    last_exc: Exception | None = None
    for attempt in range(1, NOTION_MAX_RETRY_ATTEMPTS + 1):
        try:
            response = client.create_page_in_data_source(
                NOTION_PUBLICACOES_DATA_SOURCE_ID,
                payload["properties"],
                payload.get("children"),
            )
            page_id = str(response.get("id") or "")
            if not page_id:
                raise NotionAPIError(
                    500,
                    "API Notion não retornou page_id na resposta",
                )
            return page_id
        except (NotionRateLimitError, NotionAPIError) as exc:
            last_exc = exc
            if attempt < NOTION_MAX_RETRY_ATTEMPTS:
                backoff = NOTION_RETRY_BACKOFFS_SECONDS[attempt - 1]
                logger.warning(
                    "Notion: tentativa %d/%d falhou (%s); backoff %.1fs",
                    attempt, NOTION_MAX_RETRY_ATTEMPTS, exc, backoff,
                )
                sleep(backoff)
                continue
            break
        except NotionAuthError:
            # Não retentamos token inválido — falha imediata, propaga
            # pra caller bloquear toda a sync.
            raise
    assert last_exc is not None  # invariante do loop
    raise last_exc


def sincronizar_pendentes(
    *,
    client: NotionClient,
    dje_conn: sqlite3.Connection,
    cache_conn: sqlite3.Connection,
    on_progress: Callable[[int, int], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    sleep_ms: Callable[[int], None] = _sleep_ms,
    sleep: Callable[[float], None] = time.sleep,
) -> NotionSyncOutcome:
    """Loop principal de sincronização. Single-threaded — caller que
    queira rodar em thread separada deve chamar daqui dentro do
    ``QObject.run`` do worker.

    ``sleep_ms``/``sleep`` injetáveis pra teste determinístico (sem
    espera real).
    """
    inicio = time.monotonic()
    outcome = NotionSyncOutcome()

    pendentes = dje_db.fetch_pending_for_notion(dje_conn)
    total = len(pendentes)
    if total == 0:
        if on_log is not None:
            on_log("Notion: nenhuma publicação pendente pra envio.")
        outcome.elapsed_seconds = time.monotonic() - inicio
        return outcome

    if on_log is not None:
        on_log(f"Notion: iniciando envio de {total} publicação(ões)...")

    first_request = True
    for idx, pub in enumerate(pendentes, start=1):
        if is_cancelled is not None and is_cancelled():
            outcome.cancelled = True
            if on_log is not None:
                on_log("Notion: envio cancelado pelo usuário.")
            break

        if not first_request:
            sleep_ms(NOTION_RATE_LIMIT_DELAY_MS)
        first_request = False

        djen_id = int(pub.get("id") or 0)
        if djen_id == 0:
            # Defesa: row sem ``id`` não conseguimos rastrear no banco.
            outcome.failed += 1
            if on_log is not None:
                on_log("Notion: pulada — publicação sem ``id`` no payload.")
            if on_progress is not None:
                on_progress(idx, total)
            continue

        try:
            payload = montar_payload_publicacao(
                pub, dje_conn=dje_conn, cache_conn=cache_conn,
            )
            page_id = _create_page_with_retry(
                client, payload, sleep=sleep,
            )
            dje_db.mark_publicacao_sent_to_notion(dje_conn, djen_id, page_id)
            outcome.sent += 1
            if on_log is not None:
                titulo = payload["_meta"]["titulo"]
                on_log(f"Notion: ✓ {titulo} → {page_id[:8]}…")
        except NotionAuthError as exc:
            # Token ruim — para tudo, propaga pro caller que levanta
            # banner de re-auth.
            outcome.failed += 1
            outcome.errors_sample.append(f"AUTH: {exc}")
            dje_db.mark_publicacao_notion_failure(
                dje_conn, djen_id, f"AUTH: {exc}",
            )
            if on_log is not None:
                on_log(f"Notion: ⚠ token Notion inválido — abortando: {exc}")
            break
        except Exception as exc:  # noqa: BLE001
            outcome.failed += 1
            err_msg = f"{type(exc).__name__}: {exc}"
            dje_db.mark_publicacao_notion_failure(dje_conn, djen_id, err_msg)
            if len(outcome.errors_sample) < 5:
                outcome.errors_sample.append(err_msg)
            if on_log is not None:
                on_log(f"Notion: ⚠ falha em djen_id={djen_id}: {err_msg}")

        if on_progress is not None:
            on_progress(idx, total)

    outcome.stuck_after = dje_db.count_publicacoes_failed_notion(dje_conn)
    outcome.elapsed_seconds = time.monotonic() - inicio
    if on_log is not None:
        on_log(
            f"Notion: envio concluído — {outcome.sent} enviadas, "
            f"{outcome.failed} falharam, {outcome.stuck_after} presas "
            f"(em {outcome.elapsed_seconds:.1f}s)",
        )
    return outcome
