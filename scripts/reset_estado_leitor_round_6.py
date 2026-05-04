"""Round 6 (2026-05-04) — Reset do estado persistente do leitor de DJE.

Trunca todas as tabelas de ``leitor_dje.db`` para forçar a próxima
execução do app a refazer o histórico do zero. Necessário antes de
re-ingerir publicações com as regras v8.

**Tabelas afetadas:**

- ``publicacoes`` — todas as publicações capturadas (incluindo as
  já enviadas ao Notion). Não confundir com a database 📬 Publicações
  no Notion (que deve ser limpa manualmente — fora do escopo deste
  script).
- ``dup_pendentes`` — fila de duplicatas a serem flushadas.
- ``djen_advogado_state`` — cursor por OAB; após reset, próxima
  execução refaz o histórico desde o início.
- ``djen_state`` — cursor singleton legado (Fase 3).
- ``app_flags`` — flags one-shot (ex: ``notion_primeira_carga_v1``,
  ``reativacao_4_advogados_2026_05_02_treated``).

**Cache do Notion (`cache.db`)**: NÃO é afetado. Esse cache contém
Processos, Clientes, Catálogo e Tarefas — necessários para as regras
de monitoramento da v8 cruzarem ``Pub × Proc``.

Uso:
    python scripts/reset_estado_leitor_round_6.py [--dry-run]

``--dry-run``: apenas conta linhas em cada tabela e mostra o que
seria apagado, sem modificar.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


_TABELAS_A_TRUNCAR: tuple[str, ...] = (
    "publicacoes",
    "dup_pendentes",
    "djen_advogado_state",
    "djen_state",
    "app_flags",
)


def _localizar_db() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit(
            "Variável de ambiente APPDATA não definida (esperado no Windows)."
        )
    p = Path(appdata) / "NotionRPADV" / "leitor_dje.db"
    if not p.exists():
        raise SystemExit(f"SQLite não encontrado: {p}")
    return p


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    db = _localizar_db()
    print(f"[Round 6 reset] DB: {db}")
    print(f"[Round 6 reset] Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    print()

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    # 1. Conta linhas atuais
    counts_antes: dict[str, int] = {}
    print("Tabelas a truncar e contagem atual:")
    for t in _TABELAS_A_TRUNCAR:
        try:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()  # noqa: S608
            counts_antes[t] = int(row["n"])
        except sqlite3.OperationalError as exc:
            print(f"  {t:<26}  (tabela não existe — pulando: {exc})")
            counts_antes[t] = -1
            continue
        print(f"  {t:<26}  {counts_antes[t]:>6} linhas")

    if dry_run:
        print()
        print("[DRY-RUN] nada foi modificado. Rode sem --dry-run para aplicar.")
        return 0

    # 2. DELETE em cada tabela (não DROP — preserva schema)
    print()
    print("Aplicando DELETE em cada tabela...")
    cur = conn.cursor()
    for t in _TABELAS_A_TRUNCAR:
        if counts_antes.get(t, -1) < 0:
            continue
        cur.execute(f"DELETE FROM {t}")  # noqa: S608
        print(f"  {t:<26}  → {cur.rowcount} linhas removidas")

    # 3. VACUUM pra liberar espaço
    print()
    print("Executando VACUUM...")
    conn.commit()
    conn.execute("VACUUM")

    # 4. Confere contagens pós-reset
    print()
    print("Contagens após reset:")
    for t in _TABELAS_A_TRUNCAR:
        if counts_antes.get(t, -1) < 0:
            continue
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()  # noqa: S608
        depois = int(row["n"])
        marker = "✓" if depois == 0 else "⚠"
        print(f"  {marker} {t:<26}  {depois} linhas")

    print()
    print("[Round 6 reset] Concluído.")
    print()
    print("PRÓXIMOS PASSOS (manuais — não automatizados por este script):")
    print()
    print("  1. Apagar todas as 1.608 páginas em 📬 Publicações no Notion")
    print("     (UI manual, archive em massa via 'Selecionar todos').")
    print("  2. Esvaziar a lixeira do Notion (UI manual — não autorizado")
    print("     via API por motivos de segurança).")
    print("  3. Verificar (manualmente, no Notion) que a 📬 Publicações")
    print("     está vazia (zero páginas + lixeira esvaziada).")
    print("  4. Rodar o app para recapturar publicações desde o início")
    print("     com as regras v8 já implementadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
