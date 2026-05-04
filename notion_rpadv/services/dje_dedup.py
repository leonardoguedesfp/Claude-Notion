"""Detecção e atualização de duplicatas DJEN no envio ao Notion
(Round 1, fix 1.6, 2026-05-03).

**Problema**: a API DJEN às vezes retorna 2+ publicações distintas (com
``djen_id`` próprios) referindo ao MESMO ato processual — tipicamente
quando uma intimação tem múltiplos polos como destinatário, gerando 1
"comunicação" por polo. Antes da Fase 5 essas duplicatas viram páginas
separadas no Notion, poluindo a base.

**Solução**: detector pré-envio com chave canônica
``sha256(CNJ|data|tribunal|tipo_canonico|texto[:500])``. Se já há uma
canônica enviada com a mesma chave, a publicação atual é marcada como
duplicata: NÃO cria nova página, atualiza a canônica com novos dados
(merge de Partes + Advogados intimados, append em "Duplicatas
suprimidas").

**Decisões consolidadas relevantes**:
- D-2: CNJ ausente → não deduplica (chave = None → envia direto).
- D-3 opção B: acumula em ``dup_pendentes``, 1 PATCH no fim do batch
  (vs. atualizar inline a cada duplicata, que estouraria rate-limit).
- D-4: Status da canônica NÃO é alterado pelo flush (preserva triagem
  manual do usuário).
- D-5 opção A: Multi-select advogados é UNIÃO (canônica + duplicata).
- D-7: canônica = primeira na ordem ``data_disponibilizacao ASC,
  djen_id ASC`` que já tem ``notion_page_id`` válido.
- D-8: canônica deletada manualmente do Notion (404 no PATCH) →
  warning + descarta pendentes; não bloqueia outras canônicas.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from notion_bulk_edit.notion_api import (
    NotionAPIError,
    NotionAuthError,
    NotionClient,
)
from notion_rpadv.services import dje_db
from notion_rpadv.services.dje_notion_mappings import (
    formatar_advogados_intimados,
    formatar_partes,
    mapear_tipo_documento,
)
from notion_rpadv.services.dje_text_pipeline import preprocessar_texto_djen

logger = logging.getLogger("dje.notion.dedup")


# ---------------------------------------------------------------------------
# Resultado da detecção
# ---------------------------------------------------------------------------


class TipoDestino:
    """Enum lite (string constants) com os 3 destinos possíveis."""

    NOVA_CANONICA = "nova_canonica"
    DUPLICATA_DE = "duplicata_de"
    SEM_DEDUP = "sem_dedup"


@dataclass
class ResultadoDedup:
    """Saída de ``determinar_destino``: o que fazer com a publicação."""

    tipo: str  # TipoDestino.NOVA_CANONICA / DUPLICATA_DE / SEM_DEDUP
    chave: str | None = None  # SHA-256 ou None se SEM_DEDUP
    canonica: dict[str, Any] | None = None  # row da canônica em DUPLICATA_DE


# ---------------------------------------------------------------------------
# Computação da chave canônica
# ---------------------------------------------------------------------------


def calcular_chave_canonica(
    *,
    numero_processo: str | None,
    data_disponibilizacao: str | None,
    tribunal: str | None,
    tipo_documento_canonico: str | None,
    texto_pre_processado: str | None,
) -> str | None:
    """Devolve SHA-256 hex da chave; ``None`` se ``numero_processo`` está
    ausente (D-2: sem CNJ não deduplica).

    Critério: ``CNJ|data|tribunal|tipo_canonico|texto_pre[:500]``. Texto
    truncado nos primeiros 500 chars dá um "fingerprint" razoável da
    publicação sem ser sensível a destinatários (que aparecem mais
    adiante no texto e diferem entre duplicatas).

    ``tipo_documento_canonico`` deve ser o resultado de
    ``mapear_tipo_documento`` (NÃO o bruto do DJEN), pra que variantes
    de casing tenham mesma chave.
    """
    if not numero_processo:
        return None
    base = (
        f"{numero_processo}|{data_disponibilizacao or ''}|"
        f"{tribunal or ''}|{tipo_documento_canonico or 'Outros'}|"
        f"{(texto_pre_processado or '')[:500]}"
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def calcular_chave_para_publicacao(publicacao: dict[str, Any]) -> str | None:
    """Helper conveniente: aplica preprocess HTML e mapping internamente
    e devolve a chave canônica da publicação.

    Útil pra chamar do sync sem precisar conhecer a pipeline interna.
    """
    numero = (
        publicacao.get("numeroprocessocommascara")
        or publicacao.get("numero_processo")
    )
    if not numero:
        return None
    texto_pre = preprocessar_texto_djen(publicacao.get("texto"))
    tipo_canonico = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    return calcular_chave_canonica(
        numero_processo=numero,
        data_disponibilizacao=publicacao.get("data_disponibilizacao"),
        tribunal=publicacao.get("siglaTribunal"),
        tipo_documento_canonico=tipo_canonico,
        texto_pre_processado=texto_pre,
    )


# ---------------------------------------------------------------------------
# Detecção pré-envio
# ---------------------------------------------------------------------------


def determinar_destino(
    publicacao: dict[str, Any],
    conn: sqlite3.Connection,
) -> ResultadoDedup:
    """Decide o destino da publicação ANTES da chamada à API Notion.

    Retorna ``ResultadoDedup`` com:
    - ``tipo = SEM_DEDUP`` se CNJ ausente (D-2). ``chave`` é None. Caller
      envia normalmente sem persistir chave.
    - ``tipo = DUPLICATA_DE`` se já há canônica com mesma chave já
      enviada. ``canonica`` é a row da canônica. Caller NÃO chama API,
      faz mark/insert via ``marcar_como_duplicata``.
    - ``tipo = NOVA_CANONICA`` caso contrário. ``chave`` é o hex SHA-256.
      Caller envia normalmente; após sucesso chama
      ``marcar_como_canonica`` pra persistir a chave (futuras duplicatas
      vão acha-la).
    """
    chave = calcular_chave_para_publicacao(publicacao)
    if chave is None:
        return ResultadoDedup(tipo=TipoDestino.SEM_DEDUP)
    canonica = dje_db.find_canonical_by_chave(conn, chave)
    if canonica is not None:
        return ResultadoDedup(
            tipo=TipoDestino.DUPLICATA_DE,
            chave=chave,
            canonica=canonica,
        )
    return ResultadoDedup(tipo=TipoDestino.NOVA_CANONICA, chave=chave)


# ---------------------------------------------------------------------------
# Persistência pós-detecção
# ---------------------------------------------------------------------------


def _extract_destinatario_descritor(publicacao: dict[str, Any]) -> str:
    """Constrói uma string curta identificando o "destinatário" da
    publicação pra coluna ``Duplicatas suprimidas``. Combina
    advogados intimados (se houver) + parte/destinatário (se nome
    presente) — suficiente pra distinguir polos numa intimação.

    Output exemplo: ``"Leonardo (36129/DF) — BANCO X"`` ou ``"BANCO X"``
    quando não há advogado do escritório, ou ``"n/d"`` se ambos vazios.
    """
    advogados = formatar_advogados_intimados(
        publicacao.get("destinatarioadvogados")
    )
    destinatarios = publicacao.get("destinatarios") or []
    nome_parte = ""
    if isinstance(destinatarios, list) and destinatarios:
        primeiro = destinatarios[0]
        if isinstance(primeiro, dict):
            nome_parte = str(primeiro.get("nome") or "").strip()
        elif isinstance(primeiro, str):
            nome_parte = primeiro.strip()
    partes = []
    if advogados:
        partes.append(", ".join(advogados))
    if nome_parte:
        partes.append(nome_parte)
    return " — ".join(partes) if partes else "n/d"


def marcar_como_canonica(
    conn: sqlite3.Connection,
    *,
    djen_id: int,
    chave: str,
) -> None:
    """Após sucesso ao criar a página da canônica, persiste ``dup_chave``
    pra que duplicatas posteriores consigam achá-la em
    ``find_canonical_by_chave``."""
    dje_db.mark_publicacao_dup_chave(conn, djen_id, chave)


def marcar_como_duplicata(
    conn: sqlite3.Connection,
    *,
    publicacao_duplicata: dict[str, Any],
    canonica_row: dict[str, Any],
    chave: str,
) -> None:
    """Marca a publicação atual como duplicata da canônica:

    1. Atualiza colunas em ``publicacoes``: ``dup_chave``,
       ``dup_canonical_djen_id``, ``notion_page_id`` (= page_id da
       canônica). NÃO chama API Notion aqui — flush é separado.
    2. Insere linha em ``dup_pendentes`` com ``duplicata_destinatario``
       e payload das partes/advogados serializado em JSON.

    Caller (sync) chama ``flush_atualizacoes_canonicas`` no fim do batch
    pra propagar essas atualizações ao Notion.
    """
    duplicata_djen_id = int(publicacao_duplicata.get("id") or 0)
    canonical_djen_id = int(canonica_row["djen_id"])
    canonical_page_id = str(canonica_row["notion_page_id"])

    dje_db.mark_publicacao_as_duplicate(
        conn,
        duplicata_djen_id=duplicata_djen_id,
        canonical_djen_id=canonical_djen_id,
        canonical_notion_page_id=canonical_page_id,
        chave=chave,
    )

    # Serializa o que precisa ser combinado no Notion update.
    descritor = _extract_destinatario_descritor(publicacao_duplicata)
    partes_raw = publicacao_duplicata.get("destinatarios") or []
    partes_json = json.dumps(partes_raw, ensure_ascii=False, default=str)
    advogados_tags = formatar_advogados_intimados(
        publicacao_duplicata.get("destinatarioadvogados")
    )
    advogados_json = json.dumps(advogados_tags, ensure_ascii=False)

    dje_db.insert_dup_pendente(
        conn,
        canonical_djen_id=canonical_djen_id,
        duplicata_djen_id=duplicata_djen_id,
        duplicata_destinatario=descritor,
        duplicata_partes_json=partes_json,
        duplicata_advogados_json=advogados_json,
    )

    logger.info(
        "DJE.dedup: djen=%d marcada como duplicata da canônica %d "
        "(page %s); pendente de flush",
        duplicata_djen_id, canonical_djen_id, canonical_page_id[:8],
    )


# ---------------------------------------------------------------------------
# Flush — atualiza canônicas no Notion ao fim do batch
# ---------------------------------------------------------------------------


@dataclass
class FlushOutcome:
    """Resultado do flush — usado pelo banner final."""

    canonicas_atualizadas: int = 0
    canonicas_404: int = 0  # canônicas deletadas manualmente do Notion (D-8)
    falhas_outras: int = 0
    erros_sample: list[str] = field(default_factory=list)


def _merge_partes(
    partes_canonica_json: str | None,
    partes_duplicatas_json: list[str],
) -> str:
    """União de destinatários (canônica + duplicatas), dedup por nome
    case-insensitive. Output é a string formatada pelo
    ``formatar_partes`` (Round 4.1 — "Polo Ativo: ... / Polo Passivo:
    ..."), pronta pra ir direto na property "Partes".

    Round 5a (2026-05-04): antes este merge devolvia ``json.dumps(out)``
    (JSON cru), o que sobrescrevia o output do ``formatar_partes`` no
    PATCH do flush das duplicatas — gerando 530 pubs canônicas com
    Partes em formato pré-Round-4. Agora roteia pelo mesmo formatter
    do mapper original.
    """
    out: list[Any] = []
    seen_nomes: set[str] = set()

    def _ingest(j: str | None) -> None:
        if not j:
            return
        try:
            arr = json.loads(j)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(arr, list):
            return
        for item in arr:
            if not isinstance(item, dict):
                continue
            nome = str(item.get("nome") or "").strip().lower()
            if not nome or nome in seen_nomes:
                continue
            seen_nomes.add(nome)
            out.append(item)

    _ingest(partes_canonica_json)
    for j in partes_duplicatas_json:
        _ingest(j)
    return formatar_partes(out)


def _merge_advogados(
    canonica_payload_json: str | None,
    duplicatas_advogados_jsons: list[str],
) -> list[str]:
    """União dos multi-select tags (canônica + duplicatas), ordenada
    alfabeticamente. ``canonica_payload_json`` é o ``payload_json`` da
    canônica (DJEN dict completo), de onde extraímos
    ``destinatarioadvogados``. As duplicatas vêm já como lista JSON
    de tags."""
    seen: set[str] = set()
    if canonica_payload_json:
        try:
            payload = json.loads(canonica_payload_json)
            tags = formatar_advogados_intimados(
                payload.get("destinatarioadvogados")
            )
            seen.update(tags)
        except (json.JSONDecodeError, TypeError):
            pass
    for j in duplicatas_advogados_jsons:
        try:
            tags = json.loads(j)
            if isinstance(tags, list):
                seen.update(str(t) for t in tags)
        except (json.JSONDecodeError, TypeError):
            continue
    return sorted(seen)


def _build_update_payload(
    canonica_row: dict[str, Any],
    pendentes: list[dict[str, Any]],
    *,
    schema_tem_duplicatas_suprimidas: bool,
) -> dict[str, Any]:
    """Monta o dict de properties pra ``update_page`` da canônica."""
    partes_merged = _merge_partes(
        # Original Partes da canônica é o JSON dos destinatários;
        # extrai do payload_json.
        json.dumps(
            json.loads(canonica_row["payload_json"]).get("destinatarios"),
            ensure_ascii=False,
            default=str,
        ) if canonica_row.get("payload_json") else None,
        [p["duplicata_partes_json"] for p in pendentes],
    )
    advogados_merged = _merge_advogados(
        canonica_row.get("payload_json"),
        [p["duplicata_advogados_json"] for p in pendentes],
    )

    properties: dict[str, Any] = {
        "Partes": {
            "rich_text": [
                {"type": "text", "text": {"content": partes_merged[:2000]}},
            ],
        },
        "Advogados intimados": {
            "multi_select": [{"name": n} for n in advogados_merged],
        },
        # NB: Status NÃO é tocado (D-4) — preserva triagem manual.
    }

    if schema_tem_duplicatas_suprimidas:
        suprimidas_text = "\n".join(
            f"djen={p['duplicata_djen_id']} ({p['duplicata_destinatario']})"
            for p in pendentes
        )
        properties["Duplicatas suprimidas"] = {
            "rich_text": [
                {"type": "text", "text": {"content": suprimidas_text[:2000]}},
            ],
        }
    return properties


def flush_atualizacoes_canonicas(
    *,
    client: NotionClient,
    conn: sqlite3.Connection,
    schema_tem_duplicatas_suprimidas: bool = False,
    on_log: Any = None,  # Callable[[str], None] | None
) -> FlushOutcome:
    """Para cada canônica com pendentes, faz 1 update no Notion mesclando
    Partes + Advogados intimados + (se schema tiver) Duplicatas
    suprimidas. Limpa ``dup_pendentes`` em sucesso ou em 404 (D-8).

    Importante: NÃO altera Status da canônica (D-4).
    """
    outcome = FlushOutcome()
    canonicas_ids = dje_db.fetch_canonicas_com_pendentes(conn)
    if not canonicas_ids:
        return outcome

    if on_log is not None:
        on_log(
            f"Notion dedup: {len(canonicas_ids)} canônica(s) com pendentes — "
            f"atualizando…",
        )

    for canonical_djen_id in canonicas_ids:
        canonica_row = conn.execute(
            "SELECT djen_id, notion_page_id, payload_json "
            "FROM publicacoes WHERE djen_id = ?",
            (canonical_djen_id,),
        ).fetchone()
        if canonica_row is None or not canonica_row["notion_page_id"]:
            # Canônica desapareceu do banco ou não tem page_id —
            # impossível atualizar. Limpa pendentes pra não ficar preso.
            logger.warning(
                "DJE.dedup: canônica djen=%d sem page_id — descartando pendentes",
                canonical_djen_id,
            )
            dje_db.delete_dup_pendentes_for_canonical(conn, canonical_djen_id)
            outcome.falhas_outras += 1
            continue

        pendentes = dje_db.fetch_dup_pendentes_for_canonical(
            conn, canonical_djen_id,
        )
        if not pendentes:
            continue

        page_id = str(canonica_row["notion_page_id"])
        try:
            properties = _build_update_payload(
                dict(canonica_row),
                pendentes,
                schema_tem_duplicatas_suprimidas=schema_tem_duplicatas_suprimidas,
            )
            client.update_page(page_id, properties)
            dje_db.delete_dup_pendentes_for_canonical(conn, canonical_djen_id)
            outcome.canonicas_atualizadas += 1
            if on_log is not None:
                on_log(
                    f"Notion dedup: ✓ canônica djen={canonical_djen_id} "
                    f"atualizada com {len(pendentes)} duplicata(s)",
                )
        except NotionAuthError:
            # Token quebrado — para tudo, propaga
            raise
        except NotionAPIError as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            if exc.status_code == 404:
                # D-8: canônica deletada manualmente do Notion
                outcome.canonicas_404 += 1
                logger.warning(
                    "DJE.dedup: canônica djen=%d (page %s) retornou 404 — "
                    "provavelmente deletada manualmente do Notion. "
                    "Descartando %d pendente(s).",
                    canonical_djen_id, page_id[:8], len(pendentes),
                )
                if on_log is not None:
                    on_log(
                        f"Notion dedup: ⚠ canônica djen={canonical_djen_id} "
                        f"deletada do Notion — descartando {len(pendentes)} "
                        f"pendente(s)",
                    )
                dje_db.delete_dup_pendentes_for_canonical(conn, canonical_djen_id)
            else:
                outcome.falhas_outras += 1
                if len(outcome.erros_sample) < 5:
                    outcome.erros_sample.append(err_msg)
                logger.warning(
                    "DJE.dedup: falha ao atualizar canônica djen=%d: %s",
                    canonical_djen_id, err_msg,
                )
                if on_log is not None:
                    on_log(
                        f"Notion dedup: ⚠ falha em djen={canonical_djen_id}: "
                        f"{err_msg}",
                    )

    if on_log is not None:
        on_log(
            f"Notion dedup: flush concluído — {outcome.canonicas_atualizadas} "
            f"atualizadas, {outcome.canonicas_404} 404 (deletadas), "
            f"{outcome.falhas_outras} outras falhas",
        )
    return outcome
