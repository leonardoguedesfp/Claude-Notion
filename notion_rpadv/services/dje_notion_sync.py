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
from notion_rpadv.services.dje_dedup import (
    TipoDestino,
    determinar_destino,
    flush_atualizacoes_canonicas,
    marcar_como_canonica,
    marcar_como_duplicata,
)
from notion_rpadv.services.dje_notion_constants import (
    NOTION_MAX_RETRY_ATTEMPTS,
    NOTION_PUBLICACOES_DATA_SOURCE_ID,
    NOTION_RATE_LIMIT_DELAY_MS,
    NOTION_RETRY_BACKOFFS_SECONDS,
)
from notion_rpadv.services.dje_notion_mapper import (
    montar_payload_publicacao,
)
from notion_rpadv.services.dje_notion_schema import (
    NotionSchemaCapabilities,
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
    # Round 1: estatísticas do dedup (1.6)
    duplicates_supprimidas: int = 0  # publicações detectadas como duplicatas (sem nova página)
    canonicas_atualizadas: int = 0   # canônicas que receberam flush de pendentes
    canonicas_404: int = 0           # canônicas deletadas manualmente do Notion (D-8)


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
    schema_tem_duplicatas_suprimidas: bool | None = None,
    schema_caps: NotionSchemaCapabilities | None = None,
) -> NotionSyncOutcome:
    """Loop principal de sincronização. Single-threaded — caller que
    queira rodar em thread separada deve chamar daqui dentro do
    ``QObject.run`` do worker.

    ``sleep_ms``/``sleep`` injetáveis pra teste determinístico (sem
    espera real).

    ``schema_tem_duplicatas_suprimidas``: 3 casos:

    - ``None`` (default): faz **detecção dinâmica** via
      ``NotionSchemaCapabilities.from_notion`` no startup (1 fetch ao
      Notion). Round 2 (2026-05-03) — substitui o opt-in manual.
    - ``True`` / ``False`` explícito: caller força o valor — útil pra
      testes ou pra evitar o fetch quando capabilities já foram
      pré-detectadas (passa via ``schema_caps`` em vez disso).

    ``schema_caps``: alternativa ao primeiro parâmetro. Caller que já
    tem uma instância de ``NotionSchemaCapabilities`` (ex: detectada
    no startup do app uma vez por sessão) pode passar aqui pra evitar
    fetch duplicado. Tem precedência sobre ``schema_tem_duplicatas_suprimidas``.
    """
    inicio = time.monotonic()
    outcome = NotionSyncOutcome()

    # Round 2 — resolve o flag de "Duplicatas suprimidas" antes do loop.
    # Precedência: schema_caps > schema_tem_duplicatas_suprimidas (explicit) >
    # auto-detect.
    if schema_caps is not None:
        flush_dups_flag = schema_caps.has_duplicatas_suprimidas
    elif schema_tem_duplicatas_suprimidas is not None:
        flush_dups_flag = schema_tem_duplicatas_suprimidas
    else:
        caps_detected = NotionSchemaCapabilities.from_notion(
            client, NOTION_PUBLICACOES_DATA_SOURCE_ID,
        )
        flush_dups_flag = caps_detected.has_duplicatas_suprimidas
        if on_log is not None:
            on_log(
                f"Notion: schema capabilities detectadas "
                f"(has_duplicatas_suprimidas={flush_dups_flag})",
            )

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

        djen_id = int(pub.get("id") or 0)
        if djen_id == 0:
            # Defesa: row sem ``id`` não conseguimos rastrear no banco.
            outcome.failed += 1
            if on_log is not None:
                on_log("Notion: pulada — publicação sem ``id`` no payload.")
            if on_progress is not None:
                on_progress(idx, total)
            continue

        # Round 1 (1.6): detecção de duplicata ANTES da chamada API.
        # SEM_DEDUP (CNJ ausente, D-2) → envia normal sem persistir chave.
        # NOVA_CANONICA → envia normal + persiste chave após sucesso.
        # DUPLICATA_DE → não chama API, marca + insere em dup_pendentes.
        try:
            destino = determinar_destino(pub, dje_conn)
        except Exception as exc:  # noqa: BLE001
            # Falha do detector NÃO bloqueia o envio — degrada pra
            # comportamento legacy (cria página sem dedup).
            logger.warning(
                "DJE.sync: falha no detector de duplicatas em djen=%d: %s "
                "— enviando sem dedup",
                djen_id, exc,
            )
            destino = None

        if destino is not None and destino.tipo == TipoDestino.DUPLICATA_DE:
            try:
                marcar_como_duplicata(
                    dje_conn,
                    publicacao_duplicata=pub,
                    canonica_row=destino.canonica,
                    chave=destino.chave,
                )
                outcome.duplicates_supprimidas += 1
                if on_log is not None:
                    canon_djen = destino.canonica["djen_id"]
                    on_log(
                        f"Notion: ↳ djen={djen_id} é duplicata da canônica "
                        f"djen={canon_djen} (suprimida sem nova página)",
                    )
            except Exception as exc:  # noqa: BLE001
                outcome.failed += 1
                err_msg = f"{type(exc).__name__}: {exc}"
                dje_db.mark_publicacao_notion_failure(dje_conn, djen_id, err_msg)
                if on_log is not None:
                    on_log(
                        f"Notion: ⚠ falha ao marcar djen={djen_id} como "
                        f"duplicata: {err_msg}",
                    )
            if on_progress is not None:
                on_progress(idx, total)
            continue  # próxima pub — sem rate-limit (sem chamada API)

        # Aqui é envio normal (NOVA_CANONICA ou SEM_DEDUP).
        if not first_request:
            sleep_ms(NOTION_RATE_LIMIT_DELAY_MS)
        first_request = False

        try:
            payload = montar_payload_publicacao(
                pub, dje_conn=dje_conn, cache_conn=cache_conn,
            )
            page_id = _create_page_with_retry(
                client, payload, sleep=sleep,
            )
            dje_db.mark_publicacao_sent_to_notion(dje_conn, djen_id, page_id)
            # Persiste chave apenas se a pub teve chave gerada (NOVA_CANONICA).
            if destino is not None and destino.tipo == TipoDestino.NOVA_CANONICA:
                marcar_como_canonica(
                    dje_conn, djen_id=djen_id, chave=destino.chave,
                )
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

    # Round 1: flush das atualizações de canônicas com pendentes.
    # Idempotente: se nada pendente, no-op. Não conta nos rate-limits do
    # loop principal (chama na own thread). ``flush_dups_flag`` foi
    # resolvido no início (auto-detect ou explicit, ver Round 2).
    try:
        flush_outcome = flush_atualizacoes_canonicas(
            client=client,
            conn=dje_conn,
            schema_tem_duplicatas_suprimidas=flush_dups_flag,
            on_log=on_log,
        )
        outcome.canonicas_atualizadas = flush_outcome.canonicas_atualizadas
        outcome.canonicas_404 = flush_outcome.canonicas_404
        outcome.errors_sample.extend(flush_outcome.erros_sample)
    except NotionAuthError as exc:
        outcome.errors_sample.append(f"AUTH (flush): {exc}")
        if on_log is not None:
            on_log(f"Notion: ⚠ flush abortado por token inválido: {exc}")
    except Exception as exc:  # noqa: BLE001
        # Flush é best-effort — falha não compromete pubs já enviadas.
        logger.warning("DJE.sync: falha no flush de canônicas: %s", exc)
        if on_log is not None:
            on_log(f"Notion: ⚠ flush de canônicas falhou: {exc}")

    outcome.stuck_after = dje_db.count_publicacoes_failed_notion(dje_conn)
    outcome.elapsed_seconds = time.monotonic() - inicio
    if on_log is not None:
        partes_resumo = [
            f"{outcome.sent} enviadas",
            f"{outcome.duplicates_supprimidas} duplicatas suprimidas",
            f"{outcome.failed} falharam",
            f"{outcome.stuck_after} presas",
        ]
        on_log(
            f"Notion: envio concluído — {', '.join(partes_resumo)} "
            f"(em {outcome.elapsed_seconds:.1f}s)",
        )
    return outcome
