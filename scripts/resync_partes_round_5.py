"""Round 5a (2026-05-04) — re-sync das pubs com Partes em JSON cru.

Diagnóstico: 530 das 1.608 canônicas no Notion têm a propriedade
``Partes`` em formato pré-Round-4 (``[{"comunicacao_id":..."}]``)
porque o flush das duplicatas em ``dje_dedup._merge_partes``
sobrescrevia a Partes correta com ``json.dumps(out)``. O fix do código
foi aplicado no commit Round 5a; este script atualiza as pubs já
entregues no Notion in-place via PATCH ``/v1/pages/{page_id}``.

Uso:
    python scripts/resync_partes_round_5.py [--dry-run]

Idempotente: se a Partes já está em formato legível ("Polo Ativo:" ou
"Polo Passivo:" no início), pula a pub.

Token: lido do keyring (mesma fonte do app PySide6 — sem ``token.txt``
neste setup).

CSV: usa o último ``📬 Publicações *.csv`` em ``docs/`` ou na raiz do
repo, fallback para ``%LOCALAPPDATA%\\Temp/``.

Rate limit: 350ms entre PATCH (NOTION_RATE_LIMIT_DELAY_MS), retry
exponencial em 429/500/502/503/504.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

# --- bootstrap path ---
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from notion_rpadv.services.dje_dedup import _merge_partes  # noqa: E402

# --- config ---
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
RATE_LIMIT_MS = 350
MAX_RETRIES = 5
BACKOFFS = (1.0, 2.0, 4.0, 8.0, 16.0)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

csv.field_size_limit(10 * 1024 * 1024)


# --- helpers ---


def _get_token() -> str:
    try:
        import keyring

        from notion_bulk_edit.config import KEYRING_SERVICE, KEYRING_USERNAME
    except ImportError as exc:
        raise SystemExit(f"keyring/notion_bulk_edit não disponível: {exc}")
    tok = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if not tok:
        raise SystemExit("Token Notion não encontrado no keyring.")
    return tok


def _localizar_csv() -> Path:
    """Procura o CSV mais recente entre `docs/`, raiz, e Temp."""
    pat = "📬 Publicações*.csv"
    candidatos: list[Path] = []
    candidatos.extend(sorted(_REPO.glob(pat)))
    candidatos.extend(sorted((_REPO / "docs").glob(pat)))
    temp = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp"
    if temp.exists():
        candidatos.extend(sorted(temp.glob(pat)))
    if not candidatos:
        raise SystemExit("Nenhum CSV '📬 Publicações *.csv' encontrado.")
    # mais recente por mtime
    candidatos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidatos[0]


def _localizar_sqlite() -> Path:
    p = Path(os.environ["APPDATA"]) / "NotionRPADV" / "leitor_dje.db"
    if not p.exists():
        raise SystemExit(f"SQLite não encontrado: {p}")
    return p


def _is_partes_json_cru(s: str) -> bool:
    """Identifica regressão Round 4: string começando com [ ou \\[ e
    contendo "comunicacao_id"."""
    if not s:
        return False
    s = s.strip()
    return (s.startswith("[{") or s.startswith("[ {") or s.startswith("\\[")) and "comunicacao_id" in s


def _is_partes_legivel(s: str) -> bool:
    if not s:
        return False
    return any(
        lbl in s for lbl in ("Polo Ativo:", "Polo Passivo:", "Terceiro Interessado:")
    )


def _reconstituir_partes(canon_djen: int, conn: sqlite3.Connection) -> str:
    """Roda o pipeline corrigido de _merge_partes para a canônica
    djen_id, considerando todas as duplicatas associadas."""
    canon_row = conn.execute(
        "SELECT payload_json FROM publicacoes WHERE djen_id=?",
        (canon_djen,),
    ).fetchone()
    if not canon_row or not canon_row["payload_json"]:
        return ""
    canon_dest = (json.loads(canon_row["payload_json"]) or {}).get("destinatarios") or []
    canon_partes_json = json.dumps(canon_dest, ensure_ascii=False, default=str)

    dup_rows = conn.execute(
        "SELECT payload_json FROM publicacoes WHERE dup_canonical_djen_id=?",
        (canon_djen,),
    ).fetchall()
    dup_partes_jsons: list[str] = []
    for dr in dup_rows:
        if not dr["payload_json"]:
            continue
        dup_dest = (json.loads(dr["payload_json"]) or {}).get("destinatarios") or []
        dup_partes_jsons.append(json.dumps(dup_dest, ensure_ascii=False, default=str))

    return _merge_partes(canon_partes_json, dup_partes_jsons)


def _patch_partes(page_id: str, partes_str: str, token: str) -> tuple[bool, str]:
    """Faz PATCH /v1/pages/{page_id} apenas com Partes. Retorna (ok, msg)."""
    url = f"{NOTION_API}/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    body = {
        "properties": {
            "Partes": {
                "rich_text": [
                    {"type": "text", "text": {"content": partes_str[:2000]}},
                ],
            },
        },
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.patch(url, headers=headers, json=body, timeout=30)
        except requests.RequestException as exc:
            if attempt + 1 >= MAX_RETRIES:
                return False, f"NETWORK: {exc}"
            time.sleep(BACKOFFS[attempt])
            continue

        if resp.status_code == 200:
            return True, "OK"
        if resp.status_code in RETRYABLE_STATUS and attempt + 1 < MAX_RETRIES:
            time.sleep(BACKOFFS[attempt])
            continue
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"

    return False, "MAX_RETRIES_EXCEEDED"


# --- main ---


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    csv_path = _localizar_csv()
    sqlite_path = _localizar_sqlite()
    token = _get_token()

    print(f"[Round 5a re-sync Partes] CSV: {csv_path.name}")
    print(f"[Round 5a re-sync Partes] SQLite: {sqlite_path}")
    print(f"[Round 5a re-sync Partes] Mode: {'DRY-RUN' if dry_run else 'LIVE'}")

    # 1. ler CSV, identificar candidatos (Partes JSON cru)
    candidatos: list[tuple[int, str]] = []  # (djen, partes_csv)
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            partes = (row.get("Partes") or "").strip()
            djen_str = (row.get("ID DJEN") or "").strip()
            if not djen_str.isdigit():
                continue
            if _is_partes_json_cru(partes):
                candidatos.append((int(djen_str), partes))
    print(f"[Round 5a re-sync Partes] Candidatos JSON cru: {len(candidatos)}")

    if not candidatos:
        print("[Round 5a re-sync Partes] Nada a fazer.")
        return 0

    # 2. abrir SQLite e mapear djen → page_id
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    djens = [d for d, _ in candidatos]
    placeholders = ",".join(["?"] * len(djens))
    cur = conn.execute(
        f"SELECT djen_id, notion_page_id FROM publicacoes "  # noqa: S608
        f"WHERE djen_id IN ({placeholders})",
        djens,
    )
    djen_to_page: dict[int, str] = {}
    for row in cur:
        if row["notion_page_id"]:
            djen_to_page[row["djen_id"]] = row["notion_page_id"]
    sem_page = [d for d in djens if d not in djen_to_page]
    if sem_page:
        print(
            f"[Round 5a re-sync Partes] AVISO: {len(sem_page)} djens sem "
            f"notion_page_id no SQLite — pulando: {sem_page[:5]}..."
        )

    # 3. para cada candidato com page_id, reconstitui Partes via pipeline
    #    corrigido e faz PATCH
    ok = 0
    erro = 0
    skip = 0
    erros_lista: list[tuple[int, str]] = []
    skip_lista: list[int] = []
    sleep_s = RATE_LIMIT_MS / 1000.0

    for idx, (djen, _partes_csv) in enumerate(candidatos, start=1):
        page_id = djen_to_page.get(djen)
        if not page_id:
            skip += 1
            skip_lista.append(djen)
            continue

        try:
            partes_str = _reconstituir_partes(djen, conn)
        except Exception as exc:  # noqa: BLE001
            erro += 1
            erros_lista.append((djen, f"RECONSTITUIR: {exc}"))
            print(f"  [{idx:>4}/{len(candidatos)}] djen={djen} ERRO: {exc}")
            continue

        if not _is_partes_legivel(partes_str):
            # Idempotente: se já legível (ou vazio), não envia
            skip += 1
            skip_lista.append(djen)
            print(
                f"  [{idx:>4}/{len(candidatos)}] djen={djen} SKIP "
                f"(já legível ou vazio: {partes_str[:60]!r})"
            )
            continue

        if dry_run:
            ok += 1
            print(
                f"  [{idx:>4}/{len(candidatos)}] djen={djen} DRY-RUN page={page_id[:8]}… "
                f"→ {partes_str.replace(chr(10), ' / ')[:80]!r}"
            )
            continue

        success, msg = _patch_partes(page_id, partes_str, token)
        if success:
            ok += 1
            print(
                f"  [{idx:>4}/{len(candidatos)}] djen={djen} OK page={page_id[:8]}…"
            )
        else:
            erro += 1
            erros_lista.append((djen, msg))
            print(
                f"  [{idx:>4}/{len(candidatos)}] djen={djen} ERRO: {msg}"
            )
        time.sleep(sleep_s)

    # 4. sumário
    print()
    print("=" * 70)
    print("[Round 5a re-sync Partes] SUMÁRIO")
    print(f"  Total candidatos no CSV: {len(candidatos)}")
    print(f"  OK (PATCH 200): {ok}")
    print(f"  Erro:            {erro}")
    print(f"  Skip:            {skip}")
    if erros_lista:
        print(f"  Djens com erro: {[d for d, _ in erros_lista[:10]]}")
        for d, m in erros_lista[:5]:
            print(f"    djen={d}: {m}")
    if skip_lista:
        print(f"  Djens skipped (primeiros 5): {skip_lista[:5]}")

    return 0 if erro == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
