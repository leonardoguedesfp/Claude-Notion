"""Recálculo idempotente da propriedade ``Alerta contadoria (app)``
nas publicações já criadas em 📬 Publicações no Notion.

Por que existe (Round 8, 2026-05-06):
    Os alertas de cada publicação ficam **congelados** no momento
    da criação da página no Notion (gravados como multi_select).
    Quando uma regra é corrigida (Round 8: bug de normalização
    assimétrica em Vara/Turma/Cidade/Relator) ou quando o estado do
    cache de Processos muda, as publicações antigas continuam com o
    valor calculado na criação.

    Este serviço re-aplica ``aplicar_todas_regras`` em todas as
    publicações armazenadas localmente em ``leitor_dje.db`` (que têm
    ``notion_page_id`` populado, indicando que foram enviadas) e
    sincroniza só a propriedade ``Alerta contadoria (app)`` — sem
    mexer em Status, Tarefa sugerida, ou qualquer outra coluna.

Fluxo:
    1. ``query_all`` na data source 📬 Publicações → mapa
       ``page_id → set(alertas_atuais)``. Custa ~17 chamadas pra 1.681
       publicações (page_size=100).
    2. Itera ``publicacoes`` no ``leitor_dje.db`` que têm
       ``notion_page_id IS NOT NULL AND ≠ 'SKIPPED'``.
    3. Para cada uma: decodifica ``payload_json``, faz
       ``lookup_processo_record(cache_conn, cnj)``, aplica as regras
       v8 (com a ortografia atual do código), produz set de alertas
       novos.
    4. Compara com os atuais. Se diferente, faz
       ``client.update_page(page_id, {"Alerta contadoria (app)":
       multi_select(...)})``. Se igual, nada — idempotente.

Mantém ``--dry-run`` pra preview e ``--always-update`` pra forçar
escrita mesmo quando nada mudou (útil pra rebuild histórico).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from notion_bulk_edit.notion_api import NotionClient

from notion_rpadv.services.dje_notion_mapper import lookup_processo_record
from notion_rpadv.services.dje_regras_v8 import aplicar_todas_regras


logger = logging.getLogger("dje.recalcular_alertas")

#: Data source UUID da database 📬 Publicações no Notion. Mesmo valor
#: usado por ``dje_notion_worker`` para criar páginas.
DS_PUBLICACOES_DEFAULT: str = "78070780-8ff2-4532-8f78-9e078967f191"

#: Nome da propriedade no Notion (case-sensitive). Espelha
#: ``dje_notion_mapper._multi_select_prop`` no payload de criação.
PROP_ALERTA_CONTADORIA: str = "Alerta contadoria (app)"

#: Sentinela usada em ``publicacoes.notion_page_id`` para marcar pubs
#: que foram intencionalmente puladas no envio (não têm página real
#: no Notion). Espelha ``dje_db.NOTION_SKIPPED_SENTINEL``.
NOTION_SKIPPED_SENTINEL: str = "SKIPPED"


@dataclass
class ResultadoRecalculo:
    """Saída da função ``recalcular_alertas_publicacoes``.

    Atributos:
        total_no_banco: total de pubs em ``publicacoes`` com
            ``notion_page_id`` populado e ≠ SKIPPED.
        total_processadas: quantas tiveram alertas computados (pulou
            as que falharam o decode do payload, etc.).
        total_atualizadas: quantas tiveram a propriedade Notion
            sobrescrita. Quando ``always_update=False``, esse número
            corresponde só às que realmente mudaram.
        total_inalteradas: alertas calculados batem com os atuais —
            update pulado.
        total_pulados_sem_notion: pubs com ``notion_page_id`` no banco
            mas que não foram encontradas no query da data source
            (page deletada/arquivada externamente).
        total_pulados_payload_invalido: pubs com ``payload_json``
            corrompido (não decodificável).
        total_erros: chamadas a ``update_page`` que levantaram exceção.
        erros: detalhes (até 50) das chamadas que falharam.
        diffs_amostra: amostra (até 20) dos diffs calculados — útil
            para auditoria e dry-run.
    """

    total_no_banco: int = 0
    total_processadas: int = 0
    total_atualizadas: int = 0
    total_inalteradas: int = 0
    total_pulados_sem_notion: int = 0
    total_pulados_payload_invalido: int = 0
    total_erros: int = 0
    erros: list[dict[str, str]] = field(default_factory=list)
    diffs_amostra: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _multi_select_payload(alertas: list[str]) -> dict[str, Any]:
    """Constrói o payload Notion ``multi_select`` para a propriedade
    ``Alerta contadoria (app)``.
    """
    return {"multi_select": [{"name": a} for a in alertas]}


def _alertas_atuais_de_page(page: dict[str, Any]) -> list[str]:
    """Extrai a lista atual de alertas (multi-select) de uma página
    do Notion. Devolve lista preservando ordem; ``[]`` quando vazia.
    """
    props = page.get("properties") or {}
    bloco = props.get(PROP_ALERTA_CONTADORIA) or {}
    items = bloco.get("multi_select") or []
    return [
        str(it.get("name") or "")
        for it in items
        if isinstance(it, dict) and it.get("name")
    ]


def _carregar_estado_atual_notion(
    client: NotionClient,
    *,
    data_source_id: str = DS_PUBLICACOES_DEFAULT,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, list[str]]:
    """Faz ``query_all`` na data source de Publicações e devolve mapa
    ``page_id → alertas_atuais``.

    Usa o callback ``on_progress`` (se fornecido) com o total acumulado
    a cada batch — útil pra UI mostrar barra de progresso da fase de
    leitura.
    """
    pages = client.query_all(
        data_source_id, on_progress=on_progress,
    )
    out: dict[str, list[str]] = {}
    for page in pages:
        page_id = page.get("id") or ""
        if not page_id:
            continue
        out[page_id] = _alertas_atuais_de_page(page)
    return out


def _iter_publicacoes_enviadas(
    dje_conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Lê todas as publicações em ``publicacoes`` que estão no Notion
    (``notion_page_id`` não-NULL e ≠ ``SKIPPED``) e devolve lista de
    dicts com payload mesclado a ``advogados_consultados_escritorio``
    (mesmo shape do ``fetch_pending_for_notion``).
    """
    rows = dje_conn.execute(
        """
        SELECT djen_id, hash, oabs_escritorio, oabs_externas,
               numero_processo, data_disponibilizacao, sigla_tribunal,
               payload_json, captured_at, captured_in_mode,
               notion_page_id, notion_attempts, notion_last_error
        FROM publicacoes
        WHERE notion_page_id IS NOT NULL
          AND notion_page_id != ?
        ORDER BY data_disponibilizacao ASC, djen_id ASC
        """,
        (NOTION_SKIPPED_SENTINEL,),
    ).fetchall()
    return list(rows)


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def recalcular_alertas_publicacoes(
    *,
    notion_client: NotionClient,
    dje_conn: sqlite3.Connection,
    cache_conn: sqlite3.Connection,
    data_source_id: str = DS_PUBLICACOES_DEFAULT,
    dry_run: bool = False,
    always_update: bool = False,
    limite: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    on_loading: Callable[[int], None] | None = None,
) -> ResultadoRecalculo:
    """Recalcula e sincroniza ``Alerta contadoria (app)`` para todas
    as publicações já enviadas ao Notion.

    Args:
        notion_client: cliente Notion autenticado.
        dje_conn: conexão para ``leitor_dje.db`` (lê ``publicacoes``).
        cache_conn: conexão para ``cache.db`` (lê base ``Processos``).
        data_source_id: UUID da data source 📬 Publicações no Notion.
        dry_run: se ``True``, calcula tudo mas NÃO chama
            ``update_page``. Use para preview.
        always_update: se ``True``, escreve sempre (mesmo quando os
            alertas calculados são iguais aos atuais). Default
            ``False`` mantém idempotência ao bumpar ``Atualizado em``
            apenas quando há mudança real.
        limite: opcional — processa só as N primeiras publicações.
            Útil para testes e rollouts faseados.
        on_progress: callback ``(processadas, total)`` chamado a cada
            iteração — para UI ou CLI.
        on_loading: callback ``(n_paginas_acumuladas)`` chamado durante
            a fase 1 (query do Notion para obter estado atual). Útil
            pra UI mostrar spinner com contador.

    Returns:
        ``ResultadoRecalculo`` com contadores e amostra de diffs.
    """
    resultado = ResultadoRecalculo()

    # Fase 1: estado atual no Notion (1 query batched)
    logger.info("Carregando estado atual do Notion (data source %s)…",
                data_source_id)
    estado_atual = _carregar_estado_atual_notion(
        notion_client, data_source_id=data_source_id,
        on_progress=on_loading,
    )
    logger.info("  %d páginas carregadas", len(estado_atual))

    # Fase 2: itera local
    rows = _iter_publicacoes_enviadas(dje_conn)
    if limite is not None:
        rows = rows[:limite]
    resultado.total_no_banco = len(rows)
    logger.info("  %d publicações em %s para processar",
                len(rows), "publicacoes")

    for i, row in enumerate(rows, start=1):
        if on_progress:
            on_progress(i, len(rows))

        notion_page_id = str(row["notion_page_id"] or "")
        cnj = str(row["numero_processo"] or "")
        djen_id = row["djen_id"]

        # Decodifica payload
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "djen_id=%s payload inválido: %s", djen_id, exc,
            )
            resultado.total_pulados_payload_invalido += 1
            continue

        # Mescla campos extras esperados pelas regras (mesmo shape
        # de fetch_pending_for_notion, pra reuso de regras 7-10
        # que dependem de oabs/advogados).
        payload["advogados_consultados_escritorio"] = (
            row["oabs_escritorio"] or ""
        )
        payload["oabs_externas_consultadas"] = row["oabs_externas"] or ""
        if row["data_disponibilizacao"] and not payload.get(
            "data_disponibilizacao",
        ):
            payload["data_disponibilizacao"] = row["data_disponibilizacao"]

        # Lookup do processo no cache
        processo_record = lookup_processo_record(cache_conn, cnj)

        # Aplica regras v8 (versão atual = pós-fix Round 8)
        try:
            _, alertas_novos = aplicar_todas_regras(
                payload, processo_record, cache_conn=cache_conn,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "djen_id=%s erro ao aplicar regras: %s", djen_id, exc,
            )
            resultado.total_erros += 1
            if len(resultado.erros) < 50:
                resultado.erros.append({
                    "djen_id": str(djen_id), "page_id": notion_page_id,
                    "cnj": cnj, "error": f"regras: {exc}",
                })
            continue

        resultado.total_processadas += 1

        # Estado atual no Notion (pode não existir se a página foi
        # apagada/arquivada externamente)
        if notion_page_id not in estado_atual:
            resultado.total_pulados_sem_notion += 1
            continue

        alertas_atuais = estado_atual[notion_page_id]
        alertas_novos_set = set(alertas_novos)
        alertas_atuais_set = set(alertas_atuais)
        mudou = alertas_atuais_set != alertas_novos_set

        # Coleta amostra de diffs (até 20)
        if mudou and len(resultado.diffs_amostra) < 20:
            resultado.diffs_amostra.append({
                "cnj": cnj,
                "page_id": notion_page_id,
                "antes": sorted(alertas_atuais_set),
                "depois": sorted(alertas_novos_set),
                "removidos": sorted(alertas_atuais_set - alertas_novos_set),
                "adicionados": sorted(alertas_novos_set - alertas_atuais_set),
            })

        if not mudou and not always_update:
            resultado.total_inalteradas += 1
            continue

        if dry_run:
            # Em dry-run conta como atualização "que seria feita"
            resultado.total_atualizadas += 1
            continue

        # Update real
        try:
            notion_client.update_page(
                notion_page_id,
                {PROP_ALERTA_CONTADORIA: _multi_select_payload(alertas_novos)},
            )
            resultado.total_atualizadas += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "djen_id=%s falha update_page: %s", djen_id, exc,
            )
            resultado.total_erros += 1
            if len(resultado.erros) < 50:
                resultado.erros.append({
                    "djen_id": str(djen_id), "page_id": notion_page_id,
                    "cnj": cnj, "error": f"update_page: {exc}",
                })

    return resultado
