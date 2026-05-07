"""Reset operacional pré-Round 10 (2026-05-07).

O que faz:
    1. Backup dos 3 SQLite (``cache.db.bak-round10``,
       ``audit.db.bak-round10``, ``leitor_dje.db.bak-round10``) na pasta
       ``%APPDATA%/NotionRPADV/``.
    2. Zera o estado do **leitor DJE** em ``leitor_dje.db``:
       - ``DELETE FROM publicacoes`` (todas as ~2.270 pubs já capturadas)
       - ``DELETE FROM djen_state`` (cursor legado — geralmente vazio)
       - ``DELETE FROM dup_pendentes`` (dedup pendente)
       - ``UPDATE djen_advogado_state SET ultimo_cursor=NULL,
         last_run=NULL`` (cursores por OAB voltam pra "primeira execução")
    3. **Não toca** em ``cache.db`` (Processos, Clientes, Tarefas,
       Catalogo são preservados).
    4. **Não toca** em ``audit.db`` (edit_log, pending_edits e schemas
       cacheados pertencem ao bulk-edit, sem relação com DJE).
    5. Move ``logs/*`` (exceto ``datajud_*`` que custou 26min pra gerar)
       pra ``archive/round-9/`` no diretório do projeto.
    6. **Não** apaga publicações no Notion via API. O Leonardo faz isso
       manualmente na UI antes de rodar o app pela primeira vez pós-reset.

Idempotência:
    O reset registra ``round_10_reset_done`` em ``app_flags``. Re-execução
    sem ``--force`` mostra mensagem e sai sem mexer em nada.

CLI::

    PYTHONPATH=. python scripts/reset_para_round_10.py [--dry-run]
                                                       [--force]
                                                       [--no-archive-logs]

``--dry-run``        : mostra o que faria sem escrever.
``--force``          : ignora a flag de idempotência e roda novamente
                       (refaz backup + reset + arquivamento de logs).
``--no-archive-logs``: pula a fase 5 (arquivos em ``logs/`` ficam onde
                       estão).
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from notion_bulk_edit.config import get_cache_dir
from notion_rpadv.services.dje_db import get_db_path as get_dje_db_path

logger = logging.getLogger("dje.reset_round_10")

#: Marcador em ``app_flags`` que sinaliza "reset Round 10 já foi feito".
FLAG_RESET_DONE: str = "round_10_reset_done"

#: Sufixo dos backups gerados pelo reset.
BACKUP_SUFFIX: str = ".bak-round10"

#: Subdiretório onde logs antigos vão parar (relativo ao project root).
ARCHIVE_DIR: str = "archive/round-9"

#: Prefixos de arquivos em ``logs/`` que devem ser preservados (não
#: arquivados) — DataJUD custou 26min pra gerar.
LOGS_PRESERVAR_PREFIXOS: tuple[str, ...] = ("datajud_",)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


def fazer_backup(*, dry_run: bool) -> list[Path]:
    """Copia ``cache.db``, ``audit.db`` e ``leitor_dje.db`` pra
    ``<arquivo>.bak-round10``. Sobrescreve backups antigos com o
    mesmo nome (--force re-roda). Devolve a lista de paths gerados.
    """
    cache_dir = get_cache_dir()
    candidatos = [
        cache_dir / "cache.db",
        cache_dir / "audit.db",
        get_dje_db_path(),
    ]
    backups: list[Path] = []
    for src in candidatos:
        if not src.exists():
            logger.info("  pulando %s (não existe)", src)
            continue
        dst = src.with_name(src.name + BACKUP_SUFFIX)
        if dry_run:
            logger.info("  [dry-run] copiaria %s → %s", src, dst)
        else:
            shutil.copy2(src, dst)
            logger.info("  backup %s → %s (%d bytes)",
                        src.name, dst.name, dst.stat().st_size)
        backups.append(dst)
    return backups


# ---------------------------------------------------------------------------
# Reset do leitor_dje.db
# ---------------------------------------------------------------------------


def reset_leitor_dje(*, dry_run: bool) -> dict[str, int]:
    """Limpa publicacoes + cursores + duplicatas. Devolve mapa
    ``{tabela: linhas_afetadas}``.
    """
    dje_path = get_dje_db_path()
    if not dje_path.exists():
        logger.warning("  leitor_dje.db não existe — nada a fazer")
        return {}

    conn = sqlite3.connect(str(dje_path))
    conn.row_factory = sqlite3.Row
    afetadas: dict[str, int] = {}
    try:
        # Counts pré-reset
        cnt_pubs = conn.execute("SELECT COUNT(*) FROM publicacoes").fetchone()[0]
        cnt_dup = conn.execute("SELECT COUNT(*) FROM dup_pendentes").fetchone()[0]
        cnt_djen_state = conn.execute("SELECT COUNT(*) FROM djen_state").fetchone()[0]
        cnt_advs = conn.execute(
            "SELECT COUNT(*) FROM djen_advogado_state",
        ).fetchone()[0]
        afetadas = {
            "publicacoes": cnt_pubs,
            "dup_pendentes": cnt_dup,
            "djen_state": cnt_djen_state,
            "djen_advogado_state_cursores": cnt_advs,
        }

        if dry_run:
            logger.info("  [dry-run] %d pubs, %d dups, %d djen_state, "
                        "%d cursores OAB seriam zerados",
                        cnt_pubs, cnt_dup, cnt_djen_state, cnt_advs)
            return afetadas

        with conn:
            conn.execute("DELETE FROM publicacoes")
            conn.execute("DELETE FROM dup_pendentes")
            conn.execute("DELETE FROM djen_state")
            conn.execute(
                "UPDATE djen_advogado_state "
                "SET ultimo_cursor = NULL, last_run = NULL",
            )
        logger.info(
            "  apagadas %d pubs, %d dups, %d djen_state; "
            "cursores zerados em %d OABs",
            cnt_pubs, cnt_dup, cnt_djen_state, cnt_advs,
        )
        return afetadas
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Arquivamento de logs antigos
# ---------------------------------------------------------------------------


def arquivar_logs_antigos(
    *,
    project_root: Path,
    dry_run: bool,
) -> list[Path]:
    """Move ``logs/*`` (exceto prefixos preservados) pra
    ``archive/round-9/``. Cria o destino se necessário. Devolve a
    lista de paths movidos.
    """
    logs_dir = project_root / "logs"
    if not logs_dir.exists():
        logger.info("  pulando — pasta logs/ não existe")
        return []

    archive_dir = project_root / ARCHIVE_DIR
    movidos: list[Path] = []

    if not dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)

    for entry in sorted(logs_dir.iterdir()):
        if not entry.is_file():
            continue
        if any(entry.name.startswith(p) for p in LOGS_PRESERVAR_PREFIXOS):
            logger.debug("  preservando %s (prefixo na lista)", entry.name)
            continue
        dst = archive_dir / entry.name
        if dry_run:
            logger.info("  [dry-run] moveria %s → %s", entry.name, dst)
            movidos.append(dst)
        else:
            shutil.move(str(entry), str(dst))
            logger.info("  movido %s → %s", entry.name, dst)
            movidos.append(dst)
    return movidos


# ---------------------------------------------------------------------------
# Idempotência via app_flags
# ---------------------------------------------------------------------------


def ja_foi_executado() -> tuple[bool, str | None]:
    """Verifica se ``app_flags.round_10_reset_done`` já está setado.
    Devolve ``(executado, set_at)`` — ``set_at`` é ``None`` se nunca
    rodou.
    """
    dje_path = get_dje_db_path()
    if not dje_path.exists():
        return (False, None)
    conn = sqlite3.connect(str(dje_path))
    try:
        row = conn.execute(
            "SELECT value, set_at FROM app_flags WHERE key = ?",
            (FLAG_RESET_DONE,),
        ).fetchone()
        if row and row[0] == "1":
            return (True, str(row[1]) if row[1] is not None else None)
        return (False, None)
    except sqlite3.OperationalError:
        # Tabela não existe ainda — primeira execução do app.
        return (False, None)
    finally:
        conn.close()


def marcar_executado() -> None:
    """Grava (ou atualiza) a flag de idempotência."""
    dje_path = get_dje_db_path()
    if not dje_path.exists():
        return
    conn = sqlite3.connect(str(dje_path))
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        with conn:
            conn.execute(
                "INSERT INTO app_flags (key, value, set_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "                                 set_at = excluded.set_at",
                (FLAG_RESET_DONE, "1", ts),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser(
        description=(
            "Reset operacional pré-Round 10: backup + zera leitor_dje.db "
            "+ arquiva logs/. Cache.db e audit.db são preservados."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Mostra o que seria feito sem escrever nada.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Ignora a flag de idempotência e roda novamente.",
    )
    parser.add_argument(
        "--no-archive-logs", action="store_true",
        help="Pula a fase de arquivamento de logs.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Logs em nível DEBUG.",
    )
    args = parser.parse_args()

    _setup_logging(args.verbose)

    print("=" * 60)
    print("Reset operacional Round 10")
    print("=" * 60)

    # Idempotência
    ja, set_at = ja_foi_executado()
    if ja and not args.force:
        print(
            f"\nReset Round 10 já foi executado em {set_at or '?'}.\n"
            "Use --force pra rodar novamente, ou --dry-run pra inspeção."
        )
        return 0
    if ja and args.force:
        print(f"\n[--force] Reset anterior em {set_at or '?'} — re-executando.")

    # Fase 1: backup
    print("\n[1/4] Backup dos SQLite (cache.db, audit.db, leitor_dje.db)…")
    fazer_backup(dry_run=args.dry_run)

    # Fase 2: reset leitor_dje.db
    print("\n[2/4] Reset leitor_dje.db…")
    afetadas = reset_leitor_dje(dry_run=args.dry_run)

    # Fase 3: arquivamento de logs
    if args.no_archive_logs:
        print("\n[3/4] Arquivamento de logs/* PULADO (--no-archive-logs).")
    else:
        print("\n[3/4] Arquivamento de logs/* (exceto datajud_*)…")
        # ``project_root`` = cwd, assumido = repo root
        arquivar_logs_antigos(
            project_root=Path.cwd(),
            dry_run=args.dry_run,
        )

    # Fase 4: marcar como executado
    print("\n[4/4] Marcando flag de idempotência…")
    if not args.dry_run:
        marcar_executado()
        print("  app_flags.round_10_reset_done = '1' (com timestamp)")
    else:
        print("  [dry-run] flag NÃO foi marcada")

    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)
    if args.dry_run:
        print("  Modo dry-run — nada foi escrito.")
    print(f"  Pubs zeradas:        {afetadas.get('publicacoes', 0):>5}")
    print(f"  Dup pendentes:       {afetadas.get('dup_pendentes', 0):>5}")
    print(f"  Djen state legado:   {afetadas.get('djen_state', 0):>5}")
    print(
        f"  Cursores OAB:        "
        f"{afetadas.get('djen_advogado_state_cursores', 0):>5}",
    )
    print("\n  Próximo passo: o usuário apaga publicações no Notion via UI")
    print("  e roda o app pra capturar do zero contra o histórico DJEN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
