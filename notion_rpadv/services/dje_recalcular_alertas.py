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

from notion_rpadv.services.dje_db import read_flag, set_flag
from notion_rpadv.services.dje_notion_mapper import lookup_processo_record
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
    chunkar_para_rich_text,
    preprocessar_texto_djen,
)

#: Flag em ``leitor_dje.db.app_flags`` que indica que o backfill
#: one-shot da limpeza do corpo (Round 11.4) já foi concluído com
#: sucesso nesta máquina. Quando a flag está setada (``"true"``), o
#: recálculo PULA a etapa de listar/apagar blocos do corpo —
#: protegendo qualquer bloco adicionado manualmente pelo operador
#: depois do backfill.
#:
#: Para forçar o backfill novamente (raro), basta passar
#: ``force_corpo=True`` para :func:`recalcular_alertas_publicacoes` ou
#: deletar a linha em ``app_flags``.
FLAG_CORPO_LIMPO_DONE: str = "round_11_4_corpo_limpo_done"

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
        total_corpo_reescrito: Round 11.2/11.4. Quantas pubs tiveram
            blocos do corpo da página apagados nesta rodada. Round 11.4
            (2026-05-14): o corpo deixou de ser populado pelo app —
            qualquer bloco encontrado é legado e some. Conta também em
            ``dry_run``.
        total_corpo_falhou: Round 11.2. Pubs em que a operação de
            apagar/listar blocos do corpo falhou. A propriedade
            ``Texto`` e as tags podem ter sido atualizadas mesmo assim.
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
# Round 11.4 (2026-05-14) — corpo da página é mantido vazio
#
# A propriedade ``Texto`` agora carrega o texto integral em até 100
# itens ``rich_text`` (Round 11.3, ~199.000 chars). O corpo da página
# deixou de ser populado — pubs novas saem com children vazios, e o
# backfill apaga blocos legados de pubs antigas. Sem ``append_block_children``
# nesta etapa, o que reduz o tempo do "Recalcular alertas" para a
# fração do custo anterior.
# ---------------------------------------------------------------------------


def _apagar_corpo_pagina(
    client: NotionClient,
    blocos_atuais: list[dict[str, Any]],
) -> None:
    """Apaga todos os blocos legados do corpo da página.

    Operação destrutiva — qualquer edição manual feita diretamente nos
    blocos do corpo é perdida. Comentários do Notion e propriedades da
    página são preservados.

    Levanta a exceção da chamada Notion que falhar — caller decide o
    que fazer (logar, marcar como falha, seguir).
    """
    for bloco in blocos_atuais:
        bid = bloco.get("id") if isinstance(bloco, dict) else None
        if bid:
            client.delete_block(str(bid))


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
    force_corpo: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
    on_loading: Callable[[int], None] | None = None,
) -> ResultadoRecalculo:
    """Recalcula e sincroniza as 3 propriedades de tags
    (``Tarefa advogado``, ``Tarefa contadoria``, ``Alerta contadoria``)
    + a propriedade ``Texto`` em múltiplos itens ``rich_text`` (Round
    11/11.3) + apaga blocos legados do corpo da página (Round 11.4) em
    todas as publicações já enviadas ao Notion.

    A etapa de corpo é **one-shot por máquina**: na primeira passada
    bem-sucedida (sem falhas, sem ``--limite``, sem ``--dry-run``,
    sem ``skip_corpo``), a flag :data:`FLAG_CORPO_LIMPO_DONE` é
    gravada em ``app_flags`` e as próximas execuções pulam a etapa
    completamente — preservando qualquer bloco adicionado manualmente
    pelo operador depois disso.

    Args:
        notion_client: cliente Notion autenticado.
        dje_conn: conexão para ``leitor_dje.db``.
        cache_conn: conexão para ``cache.db``.
        data_source_id: UUID da data source 📬 Publicações.
        dry_run: calcula tudo mas não chama ``update_page`` nem
            ``delete_block``. Não marca a flag de corpo limpo.
        always_update: força ``update_page`` mesmo sem diff em tags ou
            Texto (rebuild histórico). A limpeza do corpo só ocorre
            quando há blocos legados para apagar — ``always_update``
            não cria trabalho extra para corpos já vazios.
        limite: processa só as N primeiras pubs. Não marca a flag de
            corpo limpo (passada parcial).
        skip_corpo: pula a etapa de listar/apagar blocos do corpo da
            página. Útil pra re-rodar só as tags + Texto quando o
            backfill de blocos estiver com problema. Não marca a flag.
        force_corpo: força a etapa do corpo mesmo se a flag
            :data:`FLAG_CORPO_LIMPO_DONE` já estiver setada. Usar
            quando o operador adicionou blocos legados manualmente e
            quer rerodar o backfill.
        on_progress: callback ``(processadas, total)``.
        on_loading: callback ``(n_paginas_acumuladas)`` durante o
            carregamento do estado atual.

    Returns:
        :class:`ResultadoRecalculo` com contadores e amostra de diffs.
    """
    resultado = ResultadoRecalculo()

    # Round 11.4 — flag one-shot: se o backfill do corpo já foi
    # concluído nesta máquina, pular toda a etapa de listar/apagar
    # blocos. ``force_corpo`` quebra o opt-out (raro). ``skip_corpo``
    # é o opt-out manual desta execução.
    corpo_limpo_done = read_flag(dje_conn, FLAG_CORPO_LIMPO_DONE) == "true"
    pular_etapa_corpo = skip_corpo or (corpo_limpo_done and not force_corpo)
    if corpo_limpo_done and not force_corpo:
        logger.info(
            "Round 11.4: flag '%s' setada — pulando etapa de corpo. "
            "Use force_corpo=True para re-rodar.",
            FLAG_CORPO_LIMPO_DONE,
        )

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
        # Round 11.3 — propriedade Texto agora aceita até 100 itens
        # rich_text (≈ 199.000 chars). Mesma chunkagem do mapper de
        # criação. ``texto_limpo_inline`` é a string concatenada
        # equivalente — usada pra detecção de diff vs estado atual.
        texto_chunks_novos = chunkar_para_rich_text(texto_limpo_full)
        texto_limpo_inline = "".join(
            c["text"]["content"] for c in texto_chunks_novos
        )

        # Round 11.4 — corpo da página deve permanecer vazio. Lista os
        # blocos atuais; qualquer bloco existente é legado (heading
        # "Texto da publicação", paragraphs do texto, callouts, heading
        # "Observações" com placeholder…) e será apagado nesta passada.
        # Pubs novas já saem sem corpo desde a criação. ``skip_corpo=True``
        # desliga toda a etapa (útil pra re-rodar só tags + Texto se o
        # delete em loop estiver com problema).
        corpo_precisa_limpar = False
        blocos_atuais: list[dict[str, Any]] = []
        n_blocos_atuais = 0
        if not pular_etapa_corpo:
            try:
                blocos_atuais = notion_client.list_all_block_children(
                    notion_page_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "djen_id=%s falha list_block_children: %s", djen_id, exc,
                )
                blocos_atuais = []
            n_blocos_atuais = len(blocos_atuais)
            if blocos_atuais:
                corpo_precisa_limpar = True

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
        if corpo_precisa_limpar:
            mudou = True
            diffs_por_prop["Corpo"] = {
                "blocos_legados_apagados": [str(n_blocos_atuais)],
                "removidos": [],
                "adicionados": [],
            }

        if mudou and len(resultado.diffs_amostra) < 20:
            resultado.diffs_amostra.append({
                "cnj": cnj,
                "page_id": notion_page_id,
                "diffs": diffs_por_prop,
            })

        if not mudou and not always_update:
            resultado.total_inalteradas += 1
            continue

        if dry_run:
            resultado.total_atualizadas += 1
            if texto_mudou:
                resultado.total_texto_limpo += 1
            if corpo_precisa_limpar:
                resultado.total_corpo_reescrito += 1
            continue

        # Update real — escreve as 3 propriedades de tags + Texto (se mudou).
        # Round 11.4: a limpeza do corpo é só ``delete_block`` em loop
        # (sem append). Falha aqui não desfaz o update das propriedades
        # — ambas são best-effort.
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
                update_props["Texto"] = {"rich_text": texto_chunks_novos}
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

        if corpo_precisa_limpar:
            try:
                _apagar_corpo_pagina(notion_client, blocos_atuais)
                resultado.total_corpo_reescrito += 1
                houve_alguma_escrita = True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "djen_id=%s falha ao apagar corpo legado: %s",
                    djen_id, exc,
                )
                resultado.total_corpo_falhou += 1
                if len(resultado.erros) < 50:
                    resultado.erros.append({
                        "djen_id": str(djen_id), "page_id": notion_page_id,
                        "cnj": cnj, "error": f"apagar_corpo: {exc}",
                    })

        if houve_alguma_escrita:
            resultado.total_atualizadas += 1

    # Round 11.4 — marca a flag one-shot quando a passada cobriu a
    # base inteira sem falhas e a etapa de corpo não foi pulada. A
    # partir daqui, próximas execuções pulam a etapa por completo
    # (sem listar/apagar blocos), preservando edições manuais que o
    # operador venha a fazer no corpo das pubs.
    pode_marcar_flag = (
        not pular_etapa_corpo
        and not dry_run
        and limite is None
        and resultado.total_corpo_falhou == 0
        and not corpo_limpo_done
    )
    if pode_marcar_flag:
        try:
            set_flag(dje_conn, FLAG_CORPO_LIMPO_DONE, "true")
            dje_conn.commit()
            logger.info(
                "Round 11.4: flag '%s' setada — backfill do corpo "
                "concluído. Próximas execuções pulam a etapa.",
                FLAG_CORPO_LIMPO_DONE,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Round 11.4: falha ao setar flag '%s': %s. Próxima "
                "execução vai re-rodar o backfill (idempotente, "
                "trabalho extra mínimo).",
                FLAG_CORPO_LIMPO_DONE, exc,
            )

    return resultado
