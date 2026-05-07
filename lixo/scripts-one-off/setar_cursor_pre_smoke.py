"""Round 6 (2026-05-04) — Setar cursor das 6 OABs ativas para data
recente, antes do smoke test.

Após ``scripts/reset_estado_leitor_round_6.py``, todos os 6 cursores
em ``djen_advogado_state`` ficam NULL. Em ``dje_state.py``, NULL é
tratado como ``DEFAULT_CURSOR_VAZIO = 2025-12-31`` — fazendo a
próxima execução do "Baixar publicações novas" cobrir
``[2026-01-01, hoje]`` (~125 dias × 6 advogados ≈ 2.000 publicações).
Inunda o smoke test.

Solução: pré-setar cursor para ``hoje - N dias`` antes da captura.
A próxima janela vira ``[hoje - N + 1d, hoje]``.

**Bug-fix (2026-05-04, segunda iteração)**: o reset apaga também
``app_flags``, removendo ``FLAG_REATIVACAO_2026_05_02``. Quando o
app abre, esse flag ausente combinado com cursores não-NULL nos 4
advogados reativados (Vitor 48468, Cecília 20120, Samantha 38809,
Deborah 75799) faz disparar o modal "Reativação detectada". Se o
operador clicar "Sim, resetar" (default seria "Não" mas a UX é
confusa), os 4 cursores que este script setou são **zerados**. Após
o cancelamento, a captura cobre ``[2026-01-01, hoje]`` para esses
4 — exatamente o que queríamos evitar.

Fix: este script agora também grava ``FLAG_REATIVACAO_2026_05_02 =
"skipped_by_smoke_setup"`` para que o modal não dispare durante
o smoke. A flag tem semântica idêntica a ``"reset_no"`` (= modal
tratado, cursores mantidos).

Uso:
    python scripts/setar_cursor_pre_smoke.py --dias-atras 7 [--dry-run]

Com ``--dias-atras 7`` em 04/05 (segunda): janela 27/04 → 04/05
cobre ter 28/04 + qua 29/04 + qui 30/04 + sex 02/05 + seg 04/05 =
5 dias úteis (sex 01/05 é feriado). ~50-200 pubs estimadas.

Usa API pública ``dje_state.update_advogado_cursor()`` (com guard
anti-regressão) e ``dje_db.set_flag()``. Não escreve SQL bruto.
Idempotente: rodar múltiplas vezes não causa efeito além do mesmo
estado.

Read-only sobre ``publicacoes`` (não toca neste módulo).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

# --- bootstrap path ---
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from notion_rpadv.services import dje_db, dje_state  # noqa: E402
from notion_rpadv.services.dje_advogados import ADVOGADOS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dias-atras", type=int, default=7,
        help=(
            "Quantidade de dias antes de hoje para definir o cursor. "
            "Default 7 (cobre 5 dias úteis em janela típica)."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Exibe o que seria mudado sem aplicar.",
    )
    args = parser.parse_args()

    if args.dias_atras < 1:
        raise SystemExit("--dias-atras deve ser >= 1.")

    hoje = date.today()
    novo_cursor = hoje - timedelta(days=args.dias_atras)

    print(f"[setar cursor pré-smoke] Hoje: {hoje.isoformat()}")
    print(f"[setar cursor pré-smoke] Novo cursor: {novo_cursor.isoformat()}")
    print(
        f"[setar cursor pré-smoke] Janela esperada na próxima captura: "
        f"[{(novo_cursor + timedelta(days=1)).isoformat()}, "
        f"{hoje.isoformat()}]"
    )
    print(f"[setar cursor pré-smoke] Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"[setar cursor pré-smoke] OABs alvo: {len(ADVOGADOS)} ativas")
    print()

    # 1. Conexão (não inicializa schema — assume reset já rodou)
    db_path = dje_db.get_db_path()
    if not db_path.exists():
        raise SystemExit(f"SQLite não encontrado: {db_path}")
    print(f"[setar cursor pré-smoke] DB: {db_path}")
    print()

    conn = dje_db.get_connection(db_path)

    # 2. Para cada OAB ativa, ler cursor atual e aplicar/simular
    aplicados = 0
    pulados = 0
    for adv in ADVOGADOS:
        oab, uf = adv["oab"], adv["uf"]
        nome = adv.get("nome", "—")
        cursor_atual = dje_state.read_advogado_cursor(conn, oab=oab, uf=uf)
        atual_str = cursor_atual.isoformat() if cursor_atual else "NULL"

        prefixo = f"  {nome[:40]:<40} {oab}/{uf}"

        # Idempotência: se já está em uma data >= novo_cursor, pula.
        if cursor_atual is not None and cursor_atual >= novo_cursor:
            print(
                f"{prefixo}  cursor atual={atual_str} ≥ alvo "
                f"({novo_cursor.isoformat()}) — sem alteração"
            )
            pulados += 1
            continue

        if args.dry_run:
            print(
                f"{prefixo}  cursor atual={atual_str} → {novo_cursor.isoformat()} (DRY-RUN)"
            )
            aplicados += 1
            continue

        ok = dje_state.update_advogado_cursor(
            conn, oab=oab, uf=uf, novo_cursor=novo_cursor,
        )
        marker = "✓" if ok else "✗ (regressão recusada)"
        print(
            f"{prefixo}  {atual_str} → {novo_cursor.isoformat()}  {marker}"
        )
        if ok:
            aplicados += 1
        else:
            pulados += 1

    # 3. Seta FLAG_REATIVACAO_2026_05_02 para impedir modal de reativação
    #    de zerar os cursores que acabamos de definir.
    print()
    print("[setar cursor pré-smoke] Setando FLAG_REATIVACAO preventiva...")
    flag_atual = dje_db.read_flag(conn, dje_db.FLAG_REATIVACAO_2026_05_02)
    if flag_atual is not None:
        print(
            f"  flag '{dje_db.FLAG_REATIVACAO_2026_05_02}' já = "
            f"{flag_atual!r} — sem alteração"
        )
    elif args.dry_run:
        print(
            f"  flag '{dje_db.FLAG_REATIVACAO_2026_05_02}' "
            f"→ 'skipped_by_smoke_setup' (DRY-RUN)"
        )
    else:
        dje_db.set_flag(
            conn, dje_db.FLAG_REATIVACAO_2026_05_02, "skipped_by_smoke_setup",
        )
        print(
            f"  flag '{dje_db.FLAG_REATIVACAO_2026_05_02}' "
            "→ 'skipped_by_smoke_setup'  ✓"
        )

    if not args.dry_run:
        conn.commit()

    print()
    print("=" * 70)
    print("[setar cursor pré-smoke] SUMÁRIO")
    print(f"  Cursores aplicados: {aplicados}")
    print(f"  Cursores pulados:   {pulados}")
    print(
        f"  Flag reativação:    "
        f"{'já tinha valor — não sobrescrito' if flag_atual is not None else 'setada agora'}"
    )

    if not args.dry_run and aplicados > 0:
        print()
        print("PRÓXIMOS PASSOS:")
        print()
        print("  1. Abrir o app PySide6 (python -m notion_rpadv).")
        print("  2. Login (se necessário).")
        print("  3. Clicar 'Baixar publicações novas'.")
        print(
            f"     Janela calculada será [{(novo_cursor + timedelta(days=1)).isoformat()}, "
            f"{hoje.isoformat()}] para cada advogado."
        )
        print("  4. Aguardar sync com Notion completar.")
        print(
            "  5. Rodar: .venv\\Scripts\\python.exe scripts/inspecionar_smoke_v8.py --verbose"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
