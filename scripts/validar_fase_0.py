"""Fase 0 — schema dinâmico: validação empírica end-to-end.

Roda manualmente após implementar a infra. Bate na API real, popula
audit.db de teste em diretório temporário, lista propriedades.
NÃO toca em audit.db de produção (%APPDATA%/NotionRPADV/audit.db).

Uso:
    python scripts/validar_fase_0.py

Pré-requisito: token Notion no Windows Credential Manager via keyring,
service "NotionRPADV", username "notion_token".

Saída esperada:
- 4 reports (Catalogo, Processos, Clientes, Tarefas) tipo "initial"
- meta_schemas no DB de teste com 4 linhas
- spot check das opções de Categoria (Catálogo) e Tribunal (Processos)
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

# Garante que o root do projeto esteja no sys.path quando rodando de scripts/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import keyring  # noqa: E402

from notion_bulk_edit.notion_api import NotionClient  # noqa: E402
from notion_bulk_edit.schema_registry import (  # noqa: E402
    boot_refresh_all,
    init_schema_registry,
)
from notion_rpadv.cache.db import init_audit_db  # noqa: E402


# IDs reais — mesmos de DATA_SOURCES em config.py
DATA_SOURCES = {
    "Catalogo":  "79afc833-77e2-4574-98ba-ebed7bd7e66c",
    "Processos": "5e93b734-4043-4c89-a513-5e00a14081bb",
    "Clientes":  "939e5dcf-51bd-4ffa-a28e-0313899fd229",
    "Tarefas":   "3a8bb311-5c1b-42ac-a3b2-859b75911e91",
}


def main() -> int:
    token = keyring.get_password("NotionRPADV", "notion_token")
    if not token:
        print(
            "ERRO: token nao encontrado. Configure no Credential Manager "
            "(service NotionRPADV, username notion_token).",
            file=sys.stderr,
        )
        return 1

    client = NotionClient(token)

    with tempfile.TemporaryDirectory(prefix="rpadv_fase0_") as tmp:
        db_path = Path(tmp) / "audit_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_audit_db(conn)

        registry = init_schema_registry(conn)
        reports = boot_refresh_all(client, registry, DATA_SOURCES)

        print()
        print("=== VALIDACAO FASE 0 ===")
        print()
        for r in reports:
            print(f"{r.base}: {r.kind}")
            if r.kind in ("initial", "changed"):
                schema = registry.schema_for_base(r.base)
                first_keys = list(schema.keys())[:5]
                print(f"  propriedades ({len(schema)}): {first_keys}...")

        print()
        print(f"bases conhecidas pelo registry: {registry.bases()}")
        n_meta = conn.execute("SELECT COUNT(*) FROM meta_schemas").fetchone()[0]
        print(f"meta_schemas no DB: {n_meta}")

        print()
        # Spot checks
        cat_vocab = registry.vocabulario("Catalogo", "categoria")
        print(f"Catalogo.categoria.opcoes: {cat_vocab}")
        proc_vocab = registry.vocabulario("Processos", "tribunal")
        print(f"Processos.tribunal.opcoes (primeiras 5): {proc_vocab[:5]}")
        cli_vocab = registry.vocabulario("Clientes", "uf")
        print(f"Clientes.uf.opcoes (primeiras 5 de {len(cli_vocab)}): {cli_vocab[:5]}")

        print()
        # Spot check de tipo desconhecido eventual
        for base in registry.bases():
            schema = registry.schema_for_base(base)
            unsupported = [
                (k, s.tipo) for k, s in schema.items()
                if s.tipo not in {
                    "title", "rich_text", "number", "select", "multi_select",
                    "date", "people", "checkbox", "relation", "rollup",
                    "url", "email", "phone_number",
                    "created_time", "last_edited_time",
                }
            ]
            if unsupported:
                print(f"  {base} — tipos nao listados como conhecidos: {unsupported}")

        # Cleanup explicito da connection antes de sair do TemporaryDirectory
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
