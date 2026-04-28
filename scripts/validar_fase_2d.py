"""Fase 2d — Processos no schema dinâmico: validação programática.

Roda end-to-end:
1. Confirma flags ON e Processos em DYNAMIC_BASES.
2. Cria audit.db temporário, popula meta_schemas com fixture de Processos
   (recapturada após drop de 'Criado em 1' e 'Valor da causa').
3. Acessa SCHEMAS["Processos"] via proxy — confirma 37 chaves reais com
   slug do título 'numero_do_processo' e propriedades obsoletas ausentes.
4. Confirma _TITLE_KEY_BY_BASE["Processos"] == "numero_do_processo".
5. Spot check: Tribunal com 17 opções (incl. TRT/2), em-dash U+2014
   preservado em Tipo de ação.

Uso:
    python scripts/validar_fase_2d.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from notion_bulk_edit.schema_parser import (  # noqa: E402
    compute_schema_hash,
    parse_to_schema_json,
)
from notion_bulk_edit.schema_registry import init_schema_registry  # noqa: E402
from notion_bulk_edit.schemas import SCHEMAS  # noqa: E402
from notion_rpadv.cache.db import init_audit_db, upsert_schema  # noqa: E402
from notion_rpadv.models.base_table_model import _TITLE_KEY_BY_BASE  # noqa: E402


_FIXTURE = _PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "processos_raw.json"

_EXPECTED_TIPO_ACAO_COM_EM_DASH = (
    "Indenização — I",
    "Indenização — IR",
    "Indenização — RI",
    "Indenização — R",
    "Redução Salarial — HE",
    "Redução Salarial — PCS",
    "Descomissionamento — LS",
)
_OBSOLETE_KEYS = ("cnj", "valor_causa", "criado_em_1")


def main() -> int:
    print()
    print("=== VALIDACAO FASE 2D ===")
    print()

    # 1. Fase 3 removeu USE_DYNAMIC_SCHEMA/DYNAMIC_BASES — registry é fonte
    # única para as 4 bases.
    from notion_bulk_edit import config
    assert not hasattr(config, "USE_DYNAMIC_SCHEMA")
    assert not hasattr(config, "DYNAMIC_BASES")
    print("flags removidas (Fase 3): registry serve todas as 4 bases")

    # 2. Cache temporário + popular Processos
    with tempfile.TemporaryDirectory(prefix="rpadv_fase2d_") as tmp:
        db_path = Path(tmp) / "audit_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_audit_db(conn)

        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        parsed = parse_to_schema_json(raw, "Processos")
        schema_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        upsert_schema(
            conn, parsed["data_source_id"], "Processos",
            parsed["title_property"], schema_json,
            compute_schema_hash(parsed), 1700000000.0,
        )

        import notion_bulk_edit.schema_registry as sr
        saved = sr._registry
        try:
            init_schema_registry(conn)

            # 3. SCHEMAS via proxy — 37 chaves
            proc = SCHEMAS["Processos"]
            keys = set(proc.keys())
            print(f"SCHEMAS['Processos'] keys ({len(keys)}): "
                  f"{len(keys)} props (esperadas 37)")
            assert len(keys) == 37, f"esperado 37; obtido {len(keys)}"

            # 4. Title slug
            assert "numero_do_processo" in keys
            assert _TITLE_KEY_BY_BASE["Processos"] == "numero_do_processo"
            print(f"_TITLE_KEY_BY_BASE['Processos'] = "
                  f"{_TITLE_KEY_BY_BASE['Processos']!r}")

            # 5. Obsoletos ausentes
            for obsolete in _OBSOLETE_KEYS:
                assert obsolete not in keys, (
                    f"chave obsoleta {obsolete!r} ainda presente"
                )
            print(f"chaves obsoletas ausentes: {_OBSOLETE_KEYS}")

            # 6. Tribunal: 17 opções, TRT/2 incluído
            tribunal = proc["tribunal"]
            assert tribunal.tipo == "select"
            assert len(tribunal.opcoes) == 17, (
                f"tribunal: esperado 17 opcoes; obtido {len(tribunal.opcoes)}"
            )
            assert "TRT/10" in tribunal.opcoes
            assert "TRT/2" in tribunal.opcoes
            print(f"tribunal: {len(tribunal.opcoes)} opcoes (incl. TRT/2 e TRT/10)")

            # 7. Tipo de ação: 21 opções, em-dash U+2014 preservado em 7 valores
            tipo_acao = proc["tipo_de_acao"]
            assert tipo_acao.tipo == "multi_select"
            assert len(tipo_acao.opcoes) == 21
            for esperada in _EXPECTED_TIPO_ACAO_COM_EM_DASH:
                assert esperada in tipo_acao.opcoes, (
                    f"valor com em-dash ausente: {esperada!r}"
                )
            n_em_dash = sum(1 for o in tipo_acao.opcoes if "—" in o)
            print(f"tipo_de_acao: {len(tipo_acao.opcoes)} opcoes; "
                  f"{n_em_dash} com em-dash U+2014")

            # 8. Status: 3 opções
            status = proc["status"]
            assert status.tipo == "select"
            assert "Ativo" in status.opcoes
            assert "Arquivado" in status.opcoes
            assert "Arquivado provisoriamente (tema 955)" in status.opcoes
            print(f"status: {len(status.opcoes)} opcoes "
                  f"(Ativo / Arquivado / Arquivado prov.)")

            print()
            print("OK: Fase 2d validada programaticamente.")
        finally:
            sr._registry = saved
            conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
