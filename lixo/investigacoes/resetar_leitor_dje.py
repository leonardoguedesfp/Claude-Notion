"""Reset completo do estado do Leitor DJE para forçar re-captura
do ciclo completo (DJEN → regras → SQLite → Notion).

Operações:
  1. Backup do .db (leitor_dje.db.bak-pre-reset-<ts>)
  2. DELETE FROM publicacoes  (apaga 2270 — força re-fetch DJEN)
  3. DELETE FROM dup_pendentes (residuais)
  4. UPDATE djen_advogado_state SET ultimo_cursor=NULL, last_run=NULL
     (cursor NULL → DEFAULT_CURSOR_VAZIO=2025-12-31 → janela [01/01/2026, hoje])
  5. Mantém intactos: app_flags, djen_state, lista de advogados (em código)
  6. Imprime contagens antes/depois

Reversível: restaurar o .bak no mesmo caminho.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


DB = Path.home() / "AppData" / "Roaming" / "NotionRPADV" / "leitor_dje.db"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    if not DB.exists():
        print(f"ERRO: {DB} não existe")
        return 1

    # 1. Backup
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    bak = DB.with_suffix(DB.suffix + f".bak-pre-reset-{ts}")
    print(f"Backup: {DB} → {bak.name}")
    shutil.copy2(DB, bak)
    # também copia -shm e -wal se existirem (WAL mode)
    for ext in ("-shm", "-wal"):
        src = DB.with_name(DB.name + ext)
        if src.exists():
            dst = bak.with_name(bak.name + ext)
            shutil.copy2(src, dst)
            print(f"  + {src.name} → {dst.name}")
    print(f"  tamanho .db: {bak.stat().st_size:,} bytes")

    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()

    # Estado antes
    print()
    print("=" * 60)
    print("ANTES")
    print("=" * 60)
    for tab in ("publicacoes", "dup_pendentes", "djen_advogado_state",
                "djen_state", "app_flags"):
        cur.execute(f'SELECT COUNT(*) FROM "{tab}"')
        n = cur.fetchone()[0]
        print(f"  {tab}: {n}")

    # Operações
    print()
    print("=" * 60)
    print("EXECUTANDO RESET")
    print("=" * 60)

    cur.execute("DELETE FROM publicacoes")
    print(f"  publicacoes: {cur.rowcount} linhas removidas")

    cur.execute("DELETE FROM dup_pendentes")
    print(f"  dup_pendentes: {cur.rowcount} linhas removidas")

    cur.execute(
        "UPDATE djen_advogado_state "
        "SET ultimo_cursor = NULL, last_run = NULL"
    )
    print(f"  djen_advogado_state: {cur.rowcount} cursores zerados")

    conn.commit()

    # VACUUM pra encolher o arquivo (opcional, mas barato)
    cur.execute("VACUUM")
    print("  VACUUM executado (compacta o arquivo)")

    # Estado depois
    print()
    print("=" * 60)
    print("DEPOIS")
    print("=" * 60)
    for tab in ("publicacoes", "dup_pendentes", "djen_advogado_state",
                "djen_state", "app_flags"):
        cur.execute(f'SELECT COUNT(*) FROM "{tab}"')
        n = cur.fetchone()[0]
        print(f"  {tab}: {n}")

    # djen_advogado_state — confirma que cursores estão NULL
    cur.execute(
        "SELECT numero_oab, uf_oab, ultimo_cursor, last_run "
        "FROM djen_advogado_state ORDER BY numero_oab"
    )
    print()
    print("Estado final dos advogados:")
    for r in cur.fetchall():
        print(f"  OAB {r[0]}/{r[1]}  cursor={r[2]!r}  last_run={r[3]!r}")

    # app_flags preservado
    cur.execute("SELECT key, value FROM app_flags")
    print()
    print("app_flags (preservado):")
    for r in cur.fetchall():
        print(f"  {r[0]} = {r[1]!r}")

    conn.close()
    print()
    print("=" * 60)
    print("Pronto. Pode rodar o app → Leitor DJE → 'Baixar publicações novas'.")
    print(f"Reverter: restaurar {bak.name}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
