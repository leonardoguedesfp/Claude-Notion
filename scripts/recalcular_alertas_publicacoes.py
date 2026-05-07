"""CLI: recalcula a propriedade ``Alerta contadoria (app)`` em todas
as publicações já enviadas ao Notion.

Útil quando:
- Uma regra do ``dje_regras_v8`` é corrigida (Round 8: bug de
  normalização assimétrica em Vara/Turma/Cidade/Relator).
- O cache local de Processos é atualizado (campos como ``vara``,
  ``fase``, ``status`` mudam) e os alertas das publicações antigas
  ficam desalinhados.
- Uma regra é desativada (Round 8: Capturar link externo) e queremos
  remover o alerta histórico das pubs.

Uso:
    # Preview — mostra quantas pubs mudariam, sem escrever no Notion
    PYTHONPATH=. python scripts/recalcular_alertas_publicacoes.py --dry-run

    # Recálculo idempotente (default) — escreve só onde houver diff
    PYTHONPATH=. python scripts/recalcular_alertas_publicacoes.py

    # Forçar reescrita em todas (mesmo sem diff) — útil pra rebuild
    PYTHONPATH=. python scripts/recalcular_alertas_publicacoes.py --always-update

    # Limitar a N pubs (rollout faseado / smoke):
    PYTHONPATH=. python scripts/recalcular_alertas_publicacoes.py --limite 50

Saída: relatório no stdout + arquivo JSON em
``logs/recalcular_alertas_<ts>.json`` com totais e amostra de diffs.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from notion_bulk_edit.notion_api import NotionClient
from notion_bulk_edit.token_store import get_token

from notion_rpadv.cache.db import get_cache_conn
from notion_rpadv.services.dje_db import get_db_path as get_dje_db_path
from notion_rpadv.services.dje_recalcular_alertas import (
    DS_PUBLICACOES_DEFAULT,
    recalcular_alertas_publicacoes,
)


LOGS_DIR = Path("logs")


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
        description="Recalcula Alerta contadoria das publicações Notion.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Calcula tudo mas NÃO escreve no Notion.",
    )
    parser.add_argument(
        "--always-update", action="store_true",
        help="Força update_page mesmo sem diff (sai da idempotência).",
    )
    parser.add_argument(
        "--limite", type=int, default=None,
        help="Processa só as N primeiras publicações.",
    )
    parser.add_argument(
        "--data-source-id", default=DS_PUBLICACOES_DEFAULT,
        help="UUID da data source Publicações no Notion.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Log debug.",
    )
    args = parser.parse_args()

    _setup_logging(args.verbose)

    # Token + cliente
    token = get_token()
    if not token:
        print("ERRO: token Notion não encontrado.", file=sys.stderr)
        return 1
    client = NotionClient(token)

    # Conexões
    dje_path = get_dje_db_path()
    print(f"leitor_dje.db: {dje_path}")
    if not dje_path.exists():
        print("ERRO: banco do leitor não existe.", file=sys.stderr)
        return 1
    dje_conn = sqlite3.connect(str(dje_path))
    dje_conn.row_factory = sqlite3.Row

    cache_conn = get_cache_conn()
    cache_conn.row_factory = sqlite3.Row

    # Fase 1 + 2: progress callback no console
    last_pct = -1

    def on_progress(processadas: int, total: int) -> None:
        nonlocal last_pct
        pct = (processadas * 100 // total) if total > 0 else 0
        if pct != last_pct and pct % 5 == 0:
            print(f"  [{processadas}/{total}] {pct}%")
            last_pct = pct

    print()
    print("=" * 60)
    print("Recálculo Alerta contadoria")
    print("=" * 60)
    print(f"  dry_run={args.dry_run}")
    print(f"  always_update={args.always_update}")
    print(f"  limite={args.limite or 'sem limite'}")
    print(f"  data_source_id={args.data_source_id}")
    print()

    res = recalcular_alertas_publicacoes(
        notion_client=client,
        dje_conn=dje_conn,
        cache_conn=cache_conn,
        data_source_id=args.data_source_id,
        dry_run=args.dry_run,
        always_update=args.always_update,
        limite=args.limite,
        on_progress=on_progress,
    )

    print()
    print("=" * 60)
    print("RESULTADO")
    print("=" * 60)
    print(f"  Pubs no banco (filtradas):     {res.total_no_banco:>5}")
    print(f"  Processadas:                   {res.total_processadas:>5}")
    print(f"  Atualizadas (com escrita):     {res.total_atualizadas:>5}")
    print(f"  Inalteradas (idempotente):     {res.total_inalteradas:>5}")
    print(f"  Puladas (sem page no Notion):  {res.total_pulados_sem_notion:>5}")
    print(f"  Puladas (payload corrompido):  {res.total_pulados_payload_invalido:>5}")
    print(f"  Erros (regras ou update_page): {res.total_erros:>5}")

    if res.diffs_amostra:
        print()
        print(f"AMOSTRA DE DIFFS (até {len(res.diffs_amostra)}):")
        for d in res.diffs_amostra[:10]:
            print(f"  {d['cnj']} ({d['page_id']})")
            if d["removidos"]:
                print(f"    - removidos:    {d['removidos']}")
            if d["adicionados"]:
                print(f"    + adicionados:  {d['adicionados']}")

    if res.erros:
        print()
        print(f"ERROS ({len(res.erros)}):")
        for e in res.erros[:10]:
            print(f"  djen_id={e['djen_id']} cnj={e['cnj']}")
            print(f"    {e['error'][:160]}")

    # Salva JSON do log completo
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    out_path = LOGS_DIR / f"recalcular_alertas_{ts}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(res), f, ensure_ascii=False, indent=2)
    print()
    print(f"Log: {out_path}")
    return 0 if res.total_erros == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
