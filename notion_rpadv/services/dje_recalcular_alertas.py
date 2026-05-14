"""Recálculo idempotente das 3 propriedades de tags em 📬 Publicações.

Round 10 (2026-05-07) generalizou o serviço — antes recalculava só
``Alerta contadoria (app)``; agora recalcula simultaneamente
``Tarefa advogado``, ``Tarefa contadoria`` e ``Alerta contadoria``,
porque as três passaram a ser populadas automaticamente pelas regras
do app.

Por que existe:
    Os alertas/tarefas de cada publicação ficam **congelados** no
    momento da criação da página no Notion (gravados como
    multi_select). Quando uma regra é corrigida ou quando o estado
    do cache de Processos muda, as publicações antigas continuam com
    o valor calculado na criação. Este serviço re-aplica
    ``aplicar_todas_regras`` em todas as publicações armazenadas
    localmente em ``leitor_dje.db`` (que têm ``notion_page_id``
    populado) e sincroniza as 3 propriedades — sem mexer em Status,
    Fase, Instância, ou qualquer outra coluna.

Fluxo:
    1. ``query_all`` na data source 📬 Publicações → mapa
       ``page_id → {prop: set(tags_atuais)}``.
    2. Itera ``publicacoes`` no ``leitor_dje.db`` que têm
       ``notion_page_id IS NOT NULL AND ≠ 'SKIPPED'``.
    3. Para cada uma: decodifica ``payload_json``, faz
       ``lookup_processo_record(cache_conn, cnj)``, aplica as regras
       Round 10, produz veredicto.
    4. Compara as 3 propriedades com o estado atual. Se alguma
       diverge, faz ``update_page`` escrevendo as 3 propriedades.
       Se as 3 batem, nada — idempotente.

Mantém ``--dry-run`` pra preview e ``--always-update`` pra forçar
escrita mesmo quando nada mudou.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from notion_bulk_edit.notion_api import NotionClient

from notion_rpadv.services.dje_notion_mapper import (
    _build_corpo_blocks_full,
    lookup_processo_record,
)
from notion_rpadv.services.dje_notion_mappings import (
    mapear_tipo_comunicacao,
    mapear_tipo_documento,
)
from notion_rpadv.services.dje_regras import (
    PropriedadeNotion,
    VeredictoPub,
    aplicar_todas_regras,
)
from notion_rpadv.services.dje_text_limpeza import limpar_cabecalho_trailer
from notion_rpadv.services.dje_text_pipeline import (
    preprocessar_texto_djen,
    truncar_texto_inline,
)

#: Texto exato do placeholder "Observações" emitido pelo app antes do
#: Round 11.2. Usado pelo backfill para detectar pubs antigas que ainda
#: têm o heading "Observações" + o quote vazio no corpo da página.
PLACEHOLDER_OBSERVACOES: str = (
    "Sem observações automáticas pra esta publicação."
)

#: Limite de blocos por chamada `append_block_children` — o Notion
#: aceita até 100; usamos 90 para alinhar com
#: ``LIMITE_BLOCOS_INICIAIS`` em ``dje_text_pipeline``.
APPEND_CHUNK: int = 90

logger = logging.getLogger("dje.recalcular_alertas")

#: Data source UUID da database 📬 Publicações no Notion.
DS_PUBLICACOES_DEFAULT: str = "78070780-8ff2-4532-8f78-9e078967f191"

#: As 3 propriedades multi_select que o recálculo sincroniza. Os nomes
#: aqui têm que bater **exatamente** com os do schema do Notion.
PROPS_DAS_TAGS: tuple[PropriedadeNotion, ...] = (
    "Tarefa advogado",
    "Tarefa contadoria",
    "Alerta contadoria",
)

#: Sentinela usada em ``publicacoes.notion_page_id`` para marcar pubs
#: que foram intencionalmente puladas no envio.
NOTION_SKIPPED_SENTINEL: str = "SKIPPED"


@dataclass
class ResultadoRecalculo:
    """Saída de :func:`recalcular_alertas_publicacoes`.

    Atributos:
        total_no_banco: total de pubs em ``publicacoes`` com
            ``notion_page_id`` populado e ≠ SKIPPED.
        total_processadas: quantas tiveram tags computadas.
        total_atualizadas: quantas tiveram alguma das 3 propriedades
            (ou ``Texto``, Round 11) sobrescrita. Em
            ``always_update=False``, só conta as que realmente mudaram.
        total_inalteradas: tags + Texto calculados batem com os atuais —
            update pulado.
        total_pulados_sem_notion: pubs com ``notion_page_id`` no banco
            mas que não foram encontradas no query da data source.
        total_pulados_payload_invalido: payload_json corrompido.
        total_erros: chamadas a ``update_page`` que falharam.
        total_texto_limpo: Round 11. Quantas pubs tiveram o ``Texto``
            sobrescrito pela limpeza (subconjunto de
            ``total_atualizadas``).
        total_corpo_reescrito: Round 11.2. Quantas pubs tiveram os
            blocos do corpo da página reescritos (limpeza dos blocos
            + remoção do placeholder "Sem observações…"). Conta também
            em ``dry_run``.
        total_corpo_falhou: Round 11.2. Pubs em que a reescrita do
            corpo falhou (list/delete/append). A propriedade ``Texto``
            e as tags podem ter sido atualizadas mesmo assim.
        erros: detalhes (até 50) das falhas.
        diffs_amostra: amostra (até 20) dos diffs por propriedade.
    """

    total_no_banco: int = 0
    total_processadas: int = 0
    total_atualizadas: int = 0
    total_inalteradas: int = 0
    total_pulados_sem_notion: int = 0
    total_pulados_payload_invalido: int = 0
    total_erros: int = 0
    total_texto_limpo: int = 0
    total_corpo_reescrito: int = 0
    total_corpo_falhou: int = 0
    erros: list[dict[str, str]] = field(default_factory=list)
    diffs_amostra: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _multi_select_payload(tags: list[str]) -> dict[str, Any]:
    """Constrói o payload Notion ``multi_select`` para uma propriedade
    do app. Lista vazia limpa a propriedade.
    """
    return {"multi_select": [{"name": t} for t in tags]}


def _tags_atuais_de_page(
    page: dict[str, Any],
) -> dict[PropriedadeNotion, list[str]]:
    """Extrai as 3 listas de multi_select de uma página do Notion.
    Devolve mapa ``{prop: [tag_completa, ...]}``; ``[]`` quando vazia
    ou ausente.
    """
    props = page.get("properties") or {}
    out: dict[PropriedadeNotion, list[str]] = {}
    for prop in PROPS_DAS_TAGS:
        bloco = props.get(prop) or {}
        items = bloco.get("multi_select") or []
        out[prop] = [
            str(it.get("name") or "")
            for it in items
            if isinstance(it, dict) and it.get("name")
        ]
    return out


def _texto_atual_de_page(page: dict[str, Any]) -> str:
    """Extrai o texto da propriedade ``Texto`` (rich_text) de uma page
    do Notion. Vazio quando ausente.

    Round 11 — usado pelo backfill de limpeza para comparar com o texto
    recém-limpo e decidir se vale chamar ``update_page``.
    """
    props = page.get("properties") or {}
    bloco = props.get("Texto") or {}
    rt = bloco.get("rich_text") or []
    return "".join(
        str(it.get("plain_text") or it.get("text", {}).get("content", ""))
        for it in rt if isinstance(it, dict)
    )


def _carregar_estado_atual_notion(
    client: NotionClient,
    *,
    data_source_id: str = DS_PUBLICACOES_DEFAULT,
    on_progress: Callable[[int], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Faz ``query_all`` na data source de Publicações e devolve mapa
    ``page_id → {"tags": {prop: [..]}, "texto": str}``.

    Round 11 — adicionado ``texto`` ao estado pra comparar com o texto
    limpo durante o backfill de limpeza. Custo de memória ~3-4 MB
    (2.000 chars × ~1.800 pubs).
    """
    pages = client.query_all(
        data_source_id, on_progress=on_progress,
    )
    out: dict[str, dict[str, Any]] = {}
    for page in pages:
        page_id = page.get("id") or ""
        if not page_id:
            continue
        out[page_id] = {
            "tags": _tags_atuais_de_page(page),
            "texto": _texto_atual_de_page(page),
        }
    return out


def _iter_publicacoes_enviadas(
    dje_conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Lê todas as publicações em ``publicacoes`` que estão no Notion."""
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


def _veredicto_para_dict(
    v: VeredictoPub,
) -> dict[PropriedadeNotion, list[str]]:
    """Atalho — adapta ``VeredictoPub.tags_por_propriedade()`` para o
    shape interno desta função (idêntico, só fixa o tipo)."""
    return v.tags_por_propriedade()


# ---------------------------------------------------------------------------
# Round 11.2 — backfill do corpo da página
# ---------------------------------------------------------------------------


def _texto_de_rich_text(rich_text: list[Any]) -> str:
    """Concatena o texto plano de uma lista ``rich_text`` da API Notion
    (cobre os 2 shapes: ``plain_text`` retornado pela API e
    ``text.content`` que escrevemos)."""
    out: list[str] = []
    for it in rich_text:
        if not isinstance(it, dict):
            continue
        plain = it.get("plain_text")
        if plain:
            out.append(str(plain))
            continue
        content = (it.get("text") or {}).get("content")
        if content:
            out.append(str(content))
    return "".join(out)


def _texto_paragraphs(blocos: list[dict[str, Any]]) -> str:
    """Concatena o texto plano de todos os blocos ``paragraph`` na ordem
    em que aparecem, separados por ``\\n\\n``. Ignora demais tipos
    (heading, callout, quote)."""
    pedacos: list[str] = []
    for b in blocos:
        if not isinstance(b, dict) or b.get("type") != "paragraph":
            continue
        rt = (b.get("paragraph") or {}).get("rich_text") or []
        texto = _texto_de_rich_text(rt)
        if texto:
            pedacos.append(texto)
    return "\n\n".join(pedacos)


def _tem_placeholder_observacoes(blocos: list[dict[str, Any]]) -> bool:
    """``True`` se algum bloco ``quote`` no corpo contém o texto exato
    do placeholder antigo "Sem observações automáticas…"."""
    for b in blocos:
        if not isinstance(b, dict) or b.get("type") != "quote":
            continue
        rt = (b.get("quote") or {}).get("rich_text") or []
        if _texto_de_rich_text(rt).strip() == PLACEHOLDER_OBSERVACOES:
            return True
    return False


def _reescrever_corpo_pagina(
    client: NotionClient,
    page_id: str,
    *,
    blocos_atuais: list[dict[str, Any]],
    novos_blocos: list[dict[str, Any]],
) -> None:
    """Apaga todos os blocos atuais do corpo e anexa os novos.

    Operação destrutiva — qualquer edição manual feita nos blocos do
    corpo da página é perdida. Comentários do Notion (que ficam fora dos
    blocos) e propriedades da página são preservados.

    Levanta a exceção da chamada Notion que falhar — caller decide o
    que fazer (logar, abortar a pub, seguir).
    """
    for bloco in blocos_atuais:
        bid = bloco.get("id") if isinstance(bloco, dict) else None
        if bid:
            client.delete_block(str(bid))
    for i in range(0, len(novos_blocos), APPEND_CHUNK):
        chunk = novos_blocos[i:i + APPEND_CHUNK]
        if chunk:
            client.append_block_children(page_id, chunk)


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
    skip_corpo: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
    on_loading: Callable[[int], None] | None = None,
) -> ResultadoRecalculo:
    """Recalcula e sincroniza as 3 propriedades de tags
    (``Tarefa advogado``, ``Tarefa contadoria``, ``Alerta contadoria``)
    + a propriedade ``Texto`` (Round 11) + os blocos do corpo da
    página (Round 11.2) em todas as publicações já enviadas ao Notion.

    Args:
        notion_client: cliente Notion autenticado.
        dje_conn: conexão para ``leitor_dje.db``.
        cache_conn: conexão para ``cache.db``.
        data_source_id: UUID da data source 📬 Publicações.
        dry_run: calcula tudo mas não chama ``update_page``,
            ``delete_block`` ou ``append_block_children``.
        always_update: força escrita mesmo sem diff (rebuild histórico).
            Reescreve corpo + propriedades de toda pub processada.
        limite: processa só as N primeiras pubs.
        skip_corpo: pula a etapa de reescrita dos blocos do corpo da
            página (Round 11.2). Útil pra re-rodar só as tags + Texto
            quando houver problema com o backfill de blocos.
        on_progress: callback ``(processadas, total)``.
        on_loading: callback ``(n_paginas_acumuladas)`` durante o
            carregamento do estado atual.

    Returns:
        :class:`ResultadoRecalculo` com contadores e amostra de diffs.
    """
    resultado = ResultadoRecalculo()

    # Fase 1: estado atual no Notion
    logger.info(
        "Carregando estado atual do Notion (data source %s)…",
        data_source_id,
    )
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
    logger.info(
        "  %d publicações em %s para processar",
        len(rows), "publicacoes",
    )

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

        # Mescla campos extras esperados pelas regras (mesmo shape de
        # fetch_pending_for_notion).
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

        # Aplica regras Round 10
        try:
            veredicto = aplicar_todas_regras(
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
        tags_novas = _veredicto_para_dict(veredicto)

        if notion_page_id not in estado_atual:
            resultado.total_pulados_sem_notion += 1
            continue

        estado_pub = estado_atual[notion_page_id]
        tags_atuais = estado_pub["tags"]
        texto_atual_notion = estado_pub["texto"]

        # Round 11 — calcula texto limpo a partir do payload original.
        # A função aplica bypass por tipo (Distribuição, Pauta, Edital,
        # Certidão, Lista) e por padrão (notifico_eproc, texto_imprestavel)
        # e devolve texto cru nos fallbacks.
        sigla = payload.get("siglaTribunal") or row["sigla_tribunal"] or ""
        tipo_doc_canonico = mapear_tipo_documento(payload.get("tipoDocumento"))
        tipo_com_canonico = mapear_tipo_comunicacao(payload.get("tipoComunicacao"))
        texto_pre_html = preprocessar_texto_djen(payload.get("texto"))
        texto_limpo_full, _limpeza_diag = limpar_cabecalho_trailer(
            texto_pre_html,
            tribunal=sigla,
            tipo_documento=tipo_doc_canonico,
            tipo_comunicacao=tipo_com_canonico,
        )
        # Mesma transformação que o mapper aplica antes de gravar:
        # trunca em 2000 chars com word-boundary.
        texto_limpo_inline = truncar_texto_inline(texto_limpo_full)

        # Round 11.2 — calcula blocos esperados do corpo (mesma pipeline
        # do mapper de criação) e lista os blocos atuais para detectar
        # se vale a pena reescrever. ``skip_corpo=True`` desliga toda
        # essa etapa (útil pra re-rodar só tags + Texto se o backfill
        # de blocos der problema).
        corpo_precisa_reescrever = False
        novos_blocos: list[dict[str, Any]] = []
        blocos_atuais: list[dict[str, Any]] = []
        chars_paragraphs_antes = 0
        chars_paragraphs_depois = 0
        tem_placeholder_atual = False
        if not skip_corpo:
            publicacao_para_corpo = dict(payload)
            publicacao_para_corpo["texto"] = texto_limpo_full
            try:
                novos_blocos, _texto_pre_corpo, _callouts_corpo = (
                    _build_corpo_blocks_full(
                        publicacao_para_corpo,
                        tipo_documento_canonico=tipo_doc_canonico,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "djen_id=%s falha ao montar novos blocos: %s",
                    djen_id, exc,
                )
                novos_blocos = []
            try:
                blocos_atuais = notion_client.list_all_block_children(
                    notion_page_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "djen_id=%s falha list_block_children: %s", djen_id, exc,
                )
                blocos_atuais = []
            else:
                texto_atual_paragraphs = _texto_paragraphs(blocos_atuais)
                texto_esperado_paragraphs = _texto_paragraphs(novos_blocos)
                chars_paragraphs_antes = len(texto_atual_paragraphs)
                chars_paragraphs_depois = len(texto_esperado_paragraphs)
                tem_placeholder_atual = _tem_placeholder_observacoes(
                    blocos_atuais,
                )
                if (
                    texto_atual_paragraphs.strip()
                    != texto_esperado_paragraphs.strip()
                    or tem_placeholder_atual
                ):
                    corpo_precisa_reescrever = True

        # Detecta diff em qualquer das 3 propriedades + Texto + Corpo
        mudou = False
        diffs_por_prop: dict[str, dict[str, list[str]]] = {}
        for prop in PROPS_DAS_TAGS:
            atuais_set = set(tags_atuais.get(prop, []))
            novas_set = set(tags_novas.get(prop, []))
            if atuais_set != novas_set:
                mudou = True
                diffs_por_prop[prop] = {
                    "antes": sorted(atuais_set),
                    "depois": sorted(novas_set),
                    "removidos": sorted(atuais_set - novas_set),
                    "adicionados": sorted(novas_set - atuais_set),
                }
        texto_mudou = texto_limpo_inline.strip() != texto_atual_notion.strip()
        if texto_mudou:
            mudou = True
            diffs_por_prop["Texto"] = {
                "chars_antes": [str(len(texto_atual_notion))],
                "chars_depois": [str(len(texto_limpo_inline))],
                "removidos": [],
                "adicionados": [],
            }
        if corpo_precisa_reescrever:
            mudou = True
            diffs_por_prop["Corpo"] = {
                "chars_paragraphs_antes": [str(chars_paragraphs_antes)],
                "chars_paragraphs_depois": [str(chars_paragraphs_depois)],
                "tem_placeholder_observacoes": [str(tem_placeholder_atual)],
                "removidos": [],
                "adicionados": [],
            }

        if mudou and len(resultado.diffs_amostra) < 20:
            resultado.diffs_amostra.append({
                "cnj": cnj,
                "page_id": notion_page_id,
                "diffs": diffs_por_prop,
            })

        # ``always_update`` força reescrita também do corpo (quando
        # disponível) — útil pra rebuild histórico após mudança em
        # ``_build_corpo_blocks_full``.
        if always_update and not skip_corpo and novos_blocos:
            corpo_precisa_reescrever = True

        if not mudou and not always_update:
            resultado.total_inalteradas += 1
            continue

        if dry_run:
            resultado.total_atualizadas += 1
            if texto_mudou:
                resultado.total_texto_limpo += 1
            if corpo_precisa_reescrever:
                resultado.total_corpo_reescrito += 1
            continue

        # Update real — escreve as 3 propriedades de tags + Texto (se mudou).
        # Round 11.2: reescrita dos blocos do corpo é uma chamada
        # separada (delete em loop + append em chunks). Falha em uma das
        # duas etapas não desfaz a outra — ambas são best-effort.
        props_mudou = (
            any(prop in diffs_por_prop for prop in PROPS_DAS_TAGS)
            or texto_mudou
            or always_update
        )
        houve_alguma_escrita = False

        if props_mudou:
            update_props: dict[str, Any] = {
                prop: _multi_select_payload(tags_novas.get(prop, []))
                for prop in PROPS_DAS_TAGS
            }
            if texto_mudou or always_update:
                update_props["Texto"] = {
                    "rich_text": [
                        {"type": "text", "text": {"content": texto_limpo_inline}}
                    ] if texto_limpo_inline else [],
                }
            try:
                notion_client.update_page(notion_page_id, update_props)
                houve_alguma_escrita = True
                if texto_mudou:
                    resultado.total_texto_limpo += 1
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

        if corpo_precisa_reescrever and novos_blocos:
            try:
                _reescrever_corpo_pagina(
                    notion_client, notion_page_id,
                    blocos_atuais=blocos_atuais,
                    novos_blocos=novos_blocos,
                )
                resultado.total_corpo_reescrito += 1
                houve_alguma_escrita = True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "djen_id=%s falha reescrita do corpo: %s", djen_id, exc,
                )
                resultado.total_corpo_falhou += 1
                if len(resultado.erros) < 50:
                    resultado.erros.append({
                        "djen_id": str(djen_id), "page_id": notion_page_id,
                        "cnj": cnj, "error": f"reescrever_corpo: {exc}",
                    })

        if houve_alguma_escrita:
            resultado.total_atualizadas += 1

    return resultado
