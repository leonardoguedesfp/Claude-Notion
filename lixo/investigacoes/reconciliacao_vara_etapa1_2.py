"""Reconciliação Vara × Órgão — Etapas 1, 2 e 3.

Etapa 1: inventariar Processos via Notion API → processos_inventario.json
Etapa 2: inventariar Publicações via Notion API → publicacoes_inventario.json
Etapa 3: filtrar Órgão de 1º grau e reportar distribuição (PARAR aqui)

Cache: pula chamadas se os arquivos já existem.
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from notion_bulk_edit.notion_api import NotionClient
from notion_bulk_edit.token_store import get_token


DS_PROCESSOS = "5e93b734-4043-4c89-a513-5e00a14081bb"
DS_PUBLICACOES = "78070780-8ff2-4532-8f78-9e078967f191"

OUT_DIR = Path("scripts/investigacoes/_dados/reconciliacao_vara")
PROC_PATH = OUT_DIR / "processos_inventario.json"
PUB_PATH = OUT_DIR / "publicacoes_inventario.json"

THROTTLE = 0.34  # ~3 req/s


# ---------------------------------------------------------------------------
# Helpers de extração de propriedades Notion
# ---------------------------------------------------------------------------


def _title(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    arr = block.get("title") or []
    return "".join(t.get("plain_text", "") for t in arr if isinstance(t, dict))


def _rich_text(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    arr = block.get("rich_text") or []
    return "".join(t.get("plain_text", "") for t in arr if isinstance(t, dict))


def _select(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    sel = block.get("select")
    if isinstance(sel, dict):
        return sel.get("name") or ""
    return ""


def _date(block: Any) -> str | None:
    if not isinstance(block, dict):
        return None
    d = block.get("date")
    if isinstance(d, dict):
        return d.get("start")
    return None


def _relation(block: Any) -> list[str]:
    if not isinstance(block, dict):
        return []
    arr = block.get("relation") or []
    return [r.get("id", "") for r in arr if isinstance(r, dict)]


# ---------------------------------------------------------------------------
# Etapa 1
# ---------------------------------------------------------------------------


def etapa1(client: NotionClient) -> list[dict[str, Any]]:
    if PROC_PATH.exists():
        print(f"  [cache] {PROC_PATH}")
        with PROC_PATH.open(encoding="utf-8") as f:
            return json.load(f)

    print("  Querying Processos data source…")
    cursor: str | None = None
    out: list[dict[str, Any]] = []
    n_chamadas = 0
    while True:
        page = client.query_database(DS_PROCESSOS, start_cursor=cursor)
        n_chamadas += 1
        for r in page.get("results", []):
            props = r.get("properties", {})
            out.append({
                "uuid": r.get("id", ""),
                "cnj": _title(props.get("Número do processo")),
                "tribunal": _select(props.get("Tribunal")),
                "instancia": _select(props.get("Instância")),
                "cidade": _rich_text(props.get("Cidade")),
                "vara_atual": _rich_text(props.get("Vara")),
                "tipo_de_processo": _select(props.get("Tipo de processo")),
            })
        if not page.get("has_more"):
            break
        cursor = page.get("next_cursor")
        time.sleep(THROTTLE)
    print(f"  {len(out)} processos em {n_chamadas} chamadas")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with PROC_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  → {PROC_PATH}")
    return out


# ---------------------------------------------------------------------------
# Etapa 2
# ---------------------------------------------------------------------------


def etapa2(client: NotionClient) -> list[dict[str, Any]]:
    if PUB_PATH.exists():
        print(f"  [cache] {PUB_PATH}")
        with PUB_PATH.open(encoding="utf-8") as f:
            return json.load(f)

    print("  Querying Publicações data source…")
    cursor: str | None = None
    out: list[dict[str, Any]] = []
    n_chamadas = 0
    while True:
        page = client.query_database(DS_PUBLICACOES, start_cursor=cursor)
        n_chamadas += 1
        for r in page.get("results", []):
            props = r.get("properties", {})
            out.append({
                "uuid": r.get("id", ""),
                "id_djen": _rich_text(props.get("ID DJEN")) or _title(props.get("ID DJEN")),
                "tribunal": _select(props.get("Tribunal")),
                "orgao": _rich_text(props.get("Órgão")),
                "tipo_de_comunicacao": _select(props.get("Tipo de comunicação")),
                "data_disponibilizacao": _date(props.get("Data de disponibilização")),
                "processo_uuids": _relation(props.get("Processo")),
            })
        if not page.get("has_more"):
            break
        cursor = page.get("next_cursor")
        time.sleep(THROTTLE)
    print(f"  {len(out)} publicações em {n_chamadas} chamadas")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with PUB_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  → {PUB_PATH}")
    return out


# ---------------------------------------------------------------------------
# Etapa 3 — filtro
# ---------------------------------------------------------------------------

# Aceita: "Nº Vara …", "Nº Juizado …" (com ª/º opcional)
RE_ACEITA = re.compile(r"^\s*\d+\s*[ºª]\s+(Vara|Juizado)", re.IGNORECASE)
# Rejeita explicitamente
PALAVRAS_REJEITA = (
    "Turma", "Câmara", "Camara", "Seção", "Secao",
    "Gabinete", "Plenário", "Plenario",
    "Presidência", "Presidencia",
    "Vice-Presidência", "Vice-Presidencia",
    "Unidade de Processamento", "Corregedoria",
)


def classificar_orgao(orgao: str) -> str:
    """Retorna 'aceita', 'rejeita', 'ambiguo' ou 'vazio'."""
    if not orgao or not orgao.strip():
        return "vazio"
    s = orgao.strip()
    # Rejeita palavras explícitas primeiro (evita "5ª Vara da X Turma")
    for p in PALAVRAS_REJEITA:
        if p.lower() in s.lower():
            return "rejeita"
    if RE_ACEITA.match(s):
        return "aceita"
    return "ambiguo"


def etapa3(pubs: list[dict[str, Any]]) -> dict[str, Any]:
    print()
    print("=" * 72)
    print("ETAPA 3 — Filtro de Órgão de 1º grau")
    print("=" * 72)

    # Distribuição global
    todos = Counter(p["orgao"].strip() for p in pubs if p["orgao"])
    print(f"\nTotal publicações com Órgão preenchido: {sum(todos.values())}")
    print(f"Valores distintos de Órgão: {len(todos)}")

    print("\nTop 30 valores distintos de Órgão (com contagem):")
    for orgao, n in todos.most_common(30):
        print(f"  {n:>5}  {orgao!r}")

    # Classificação
    bucket: dict[str, list[str]] = {"aceita": [], "rejeita": [], "ambiguo": [], "vazio": []}
    for p in pubs:
        orgao = (p.get("orgao") or "").strip()
        cls = classificar_orgao(orgao)
        bucket[cls].append(orgao)

    print()
    print("Resumo por classe:")
    print(f"  aceita  : {len(bucket['aceita']):>5} pubs  ({len(set(bucket['aceita']))} valores distintos)")
    print(f"  rejeita : {len(bucket['rejeita']):>5} pubs  ({len(set(bucket['rejeita']))} valores distintos)")
    print(f"  ambiguo : {len(bucket['ambiguo']):>5} pubs  ({len(set(bucket['ambiguo']))} valores distintos)")
    print(f"  vazio   : {len(bucket['vazio']):>5} pubs")

    # Lista completa dos ambíguos (até 50 distintos)
    ambiguos_distintos = Counter(bucket["ambiguo"])
    print()
    print(f"AMBÍGUOS — até 50 valores distintos (total {len(ambiguos_distintos)} distintos):")
    for orgao, n in ambiguos_distintos.most_common(50):
        print(f"  {n:>5}  {orgao!r}")

    # Amostras de aceita e rejeita pra sanity
    print()
    print("Amostras de ACEITA (até 15 distintos):")
    aceita_distintos = Counter(bucket["aceita"])
    for orgao, n in aceita_distintos.most_common(15):
        print(f"  {n:>5}  {orgao!r}")
    print()
    print("Amostras de REJEITA (até 15 distintos):")
    rejeita_distintos = Counter(bucket["rejeita"])
    for orgao, n in rejeita_distintos.most_common(15):
        print(f"  {n:>5}  {orgao!r}")

    return {
        "total_pubs": len(pubs),
        "n_aceita": len(bucket["aceita"]),
        "n_rejeita": len(bucket["rejeita"]),
        "n_ambiguo": len(bucket["ambiguo"]),
        "n_vazio": len(bucket["vazio"]),
        "ambiguos_distintos": dict(ambiguos_distintos),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    token = get_token()
    if not token:
        print("ERRO: token Notion não encontrado")
        return 1
    client = NotionClient(token)

    print("=" * 72)
    print("ETAPA 1 — Inventariar Processos")
    print("=" * 72)
    processos = etapa1(client)
    print(f"  total: {len(processos)} processos")

    print()
    print("=" * 72)
    print("ETAPA 2 — Inventariar Publicações")
    print("=" * 72)
    pubs = etapa2(client)
    print(f"  total: {len(pubs)} publicações")
    n_com_relation = sum(1 for p in pubs if p.get("processo_uuids"))
    print(f"  com relation a Processo: {n_com_relation}")
    print(f"  sem relation:            {len(pubs) - n_com_relation}")

    etapa3(pubs)

    print()
    print("=" * 72)
    print("PARADA — Etapa 3 concluída. Aguardando aprovação dos critérios.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
