"""Backfill — popula ``Fase`` e ``Instância`` (snapshot) nas
publicações já criadas em 📬 Publicações no Notion.

Por que existe (Round 9, 2026-05-07):
    O snapshot Fase + Instância nas publicações é uma feature nova.
    As ~1.681 publicações criadas antes do Round 9 não têm essas duas
    propriedades populadas. Este script faz o backfill: itera as
    publicações, para cada uma força um pull live do Processo
    correspondente, e atualiza só ``Fase`` e ``Instância`` no Notion.

Idempotente — só escreve quando há diferença real entre o estado atual
da Pub no Notion e o valor (live) do Processo.

Uso:
    # Preview
    PYTHONPATH=. python scripts/backfill_snapshot_publicacoes.py --dry-run

    # Aplicar
    PYTHONPATH=. python scripts/backfill_snapshot_publicacoes.py

    # Rollout faseado
    PYTHONPATH=. python scripts/backfill_snapshot_publicacoes.py --limite 50

Saída: relatório no stdout + log JSON em
``logs/backfill_snapshot_<ts>.json`` com totais e amostra de diffs.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from notion_bulk_edit.config import get_cache_db_path
from notion_bulk_edit.notion_api import NotionClient
from notion_bulk_edit.token_store import get_token

from notion_rpadv.cache import db as cache_db
from notion_rpadv.services.dje_db import get_db_path as get_dje_db_path
from notion_rpadv.services.dje_notion_mapper import lookup_processo_record


logger = logging.getLogger("dje.backfill_snapshot")

#: Data source UUID da database 📬 Publicações no Notion.
DS_PUBLICACOES_DEFAULT: str = "78070780-8ff2-4532-8f78-9e078967f191"

#: Vocabulários canônicos (espelham o multi-select do Notion). Valores
#: fora dessas listas são tratados como vazios — não escritos.
_FASE_VOCAB: frozenset[str] = frozenset({
    "Cognitiva",
    "Executiva",
    "Liquidação pendente",
    "Liquidação de sentença",
    "TJ - sentença não será executada",
})
_INSTANCIA_VOCAB: frozenset[str] = frozenset({
    "1º grau", "2º grau", "TST", "STJ", "STF",
})

LOGS_DIR = Path("logs")


@dataclass
class ResultadoBackfill:
    total_pubs_no_notion: int = 0
    total_processadas: int = 0
    total_atualizadas: int = 0
    total_inalteradas: int = 0
    total_sem_processo_relacionado: int = 0
    total_processo_nao_no_cache: int = 0
    total_erros: int = 0
    erros: list[dict[str, str]] = field(default_factory=list)
    diffs_amostra: list[dict[str, Any]] = field(default_factory=list)


def _select_prop(name: str | None) -> dict[str, Any]:
    if not name:
        return {"select": None}
    return {"select": {"name": name}}


def _select_atual(page: dict[str, Any], prop_name: str) -> str | None:
    """Lê o valor atual da propriedade select da página Notion."""
    props = page.get("properties") or {}
    bloco = props.get(prop_name) or {}
    sel = bloco.get("select")
    if isinstance(sel, dict):
        nome = sel.get("name")
        if isinstance(nome, str):
            return nome
    return None


def _processo_relation_id(page: dict[str, Any]) -> str | None:
    """Lê o page_id do processo relacionado pela propriedade Processo."""
    props = page.get("properties") or {}
    bloco = props.get("Processo") or {}
    arr = bloco.get("relation") or []
    for item in arr:
        if isinstance(item, dict):
            pid = item.get("id")
            if pid:
                return str(pid)
    return None


def _fase_instancia_de_proc(
    proc_record: dict[str, Any],
) -> tuple[str | None, str | None]:
    fase = proc_record.get("fase")
    inst = proc_record.get("instancia")
    fase_val = fase if isinstance(fase, str) and fase in _FASE_VOCAB else None
    inst_val = inst if isinstance(inst, str) and inst in _INSTANCIA_VOCAB else None
    return fase_val, inst_val


def backfill_snapshot_publicacoes(
    *,
    notion_client: NotionClient,
    dje_conn: sqlite3.Connection,
    cache_conn: sqlite3.Connection,
    data_source_id: str = DS_PUBLICACOES_DEFAULT,
    dry_run: bool = False,
    limite: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> ResultadoBackfill:
    """Faz backfill de Fase + Instância em publicações existentes.

    1. ``query_all`` em 📬 Publicações.
    2. Para cada Pub, lê page_id do Processo relacionado.
    3. ``client.get_page`` no Processo → fase + instância live.
    4. Atualiza cache.db em paralelo (best-effort).
    5. Se valor diverge do que está na Pub no Notion, ``update_page``
       só com Fase + Instância.
    """
    res = ResultadoBackfill()

    logger.info("Carregando publicações da data source %s…", data_source_id)
    pubs = notion_client.query_all(data_source_id)
    res.total_pubs_no_notion = len(pubs)
    logger.info("  %d publicações", len(pubs))

    if limite is not None:
        pubs = pubs[:limite]

    total = len(pubs)
    for i, page in enumerate(pubs, start=1):
        if on_progress:
            on_progress(i, total)

        page_id = page.get("id")
        if not isinstance(page_id, str) or not page_id:
            continue

        proc_page_id = _processo_relation_id(page)
        if not proc_page_id:
            res.total_sem_processo_relacionado += 1
            continue

        # Pull live do processo → atualiza cache
        try:
            proc_page = notion_client.get_page(proc_page_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_page(%s) falhou: %s", proc_page_id, exc)
            res.total_erros += 1
            if len(res.erros) < 50:
                res.erros.append({
                    "pub_page_id": page_id,
                    "proc_page_id": proc_page_id,
                    "error": f"get_page: {exc}",
                })
            continue

        proc_props = proc_page.get("properties") or {}

        # Decode local
        from notion_bulk_edit.encoders import decode_value
        fase_live: Any = None
        inst_live: Any = None
        bloco_fase = proc_props.get("Fase")
        if isinstance(bloco_fase, dict):
            try:
                fase_live = decode_value(bloco_fase, "select")
            except Exception:  # noqa: BLE001
                fase_live = None
        bloco_inst = proc_props.get("Instância")
        if isinstance(bloco_inst, dict):
            try:
                inst_live = decode_value(bloco_inst, "select")
            except Exception:  # noqa: BLE001
                inst_live = None

        # Atualiza cache (best-effort)
        try:
            existing_row = cache_conn.execute(
                "SELECT data_json FROM records WHERE base='Processos' AND page_id=?",
                (proc_page_id,),
            ).fetchone()
            if existing_row is not None:
                existing = json.loads(existing_row["data_json"])
                existing["fase"] = fase_live
                existing["instancia"] = inst_live
                cache_db.upsert_record(
                    cache_conn, "Processos", proc_page_id, existing,
                )
        except Exception:  # noqa: BLE001
            pass

        # Valida vocabulário
        fase_target = (
            fase_live
            if isinstance(fase_live, str) and fase_live in _FASE_VOCAB
            else None
        )
        inst_target = (
            inst_live
            if isinstance(inst_live, str) and inst_live in _INSTANCIA_VOCAB
            else None
        )

        # Estado atual da Pub no Notion
        fase_atual = _select_atual(page, "Fase")
        inst_atual = _select_atual(page, "Instância")

        res.total_processadas += 1

        if fase_atual == fase_target and inst_atual == inst_target:
            res.total_inalteradas += 1
            continue

        if len(res.diffs_amostra) < 20:
            res.diffs_amostra.append({
                "pub_page_id": page_id,
                "proc_page_id": proc_page_id,
                "fase_antes": fase_atual,
                "fase_depois": fase_target,
                "inst_antes": inst_atual,
                "inst_depois": inst_target,
            })

        if dry_run:
            res.total_atualizadas += 1
            continue

        try:
            notion_client.update_page(
                page_id,
                {
                    "Fase": _select_prop(fase_target),
                    "Instância": _select_prop(inst_target),
                },
            )
            res.total_atualizadas += 1
        except Exception as exc:  # noqa: BLE001
            res.total_erros += 1
            if len(res.erros) < 50:
                res.erros.append({
                    "pub_page_id": page_id,
                    "proc_page_id": proc_page_id,
                    "error": f"update_page: {exc}",
                })

    return res


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser(
        description=(
            "Backfill de Fase + Instância (snapshot) nas publicações Notion."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Calcula tudo mas NÃO escreve no Notion.",
    )
    parser.add_argument(
        "--limite", type=int, default=None,
        help="Processa só as N primeiras publicações.",
    )
    parser.add_argument(
        "--data-source-id", default=DS_PUBLICACOES_DEFAULT,
        help="UUID da data source 📬 Publicações.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    token = get_token()
    if not token:
        print("ERRO: token Notion não encontrado.", file=sys.stderr)
        return 1
    client = NotionClient(token)

    dje_path = get_dje_db_path()
    if not dje_path.exists():
        print(f"ERRO: leitor_dje.db não existe em {dje_path}.", file=sys.stderr)
        return 1
    dje_conn = sqlite3.connect(str(dje_path))
    dje_conn.row_factory = sqlite3.Row

    cache_conn = sqlite3.connect(str(get_cache_db_path()))
    cache_conn.row_factory = sqlite3.Row

    last_pct = -1

    def on_progress(p: int, t: int) -> None:
        nonlocal last_pct
        pct = (p * 100 // t) if t > 0 else 0
        if pct != last_pct and pct % 5 == 0:
            print(f"  [{p}/{t}] {pct}%")
            last_pct = pct

    print("=" * 60)
    print("Backfill snapshot Fase + Instância nas publicações")
    print("=" * 60)
    print(f"  dry_run={args.dry_run}  limite={args.limite}")
    print()

    res = backfill_snapshot_publicacoes(
        notion_client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        data_source_id=args.data_source_id,
        dry_run=args.dry_run,
        limite=args.limite,
        on_progress=on_progress,
    )

    print()
    print("=" * 60)
    print("RESULTADO")
    print("=" * 60)
    print(f"  Pubs no Notion:                   {res.total_pubs_no_notion:>5}")
    print(f"  Processadas:                       {res.total_processadas:>5}")
    print(f"  Atualizadas:                       {res.total_atualizadas:>5}")
    print(f"  Inalteradas (idempotente):         {res.total_inalteradas:>5}")
    print(f"  Sem Processo relacionado:          {res.total_sem_processo_relacionado:>5}")
    print(f"  Erros:                             {res.total_erros:>5}")

    if res.diffs_amostra:
        print()
        print(f"AMOSTRA DE DIFFS (até {len(res.diffs_amostra)}):")
        for d in res.diffs_amostra[:5]:
            print(f"  {d['pub_page_id']}")
            print(
                f"    fase: {d['fase_antes']!r:30} → {d['fase_depois']!r}",
            )
            print(
                f"    inst: {d['inst_antes']!r:30} → {d['inst_depois']!r}",
            )

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    out_path = LOGS_DIR / f"backfill_snapshot_{ts}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(res), f, ensure_ascii=False, indent=2)
    print(f"\nLog: {out_path}")
    return 0 if res.total_erros == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
