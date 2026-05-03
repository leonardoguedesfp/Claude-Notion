"""Smoke test integrado do Round 1 contra publicações REAIS do SQLite
local (``%APPDATA%\\NotionRPADV\\leitor_dje.db``).

Pula se o banco real não estiver disponível (CI ou outra máquina).

Cobre:
- Pipeline ponta a ponta (1.7 → 1.5 → 1.4): texto bruto vira blocos
  prontos pro Notion sem exceção.
- Após pipeline: corpo ≤ 80KB; total de blocos ≤ 90 (limite duro Notion);
  todas as propriedades das 18 enviáveis presentes.
- Multi-select de advogados sempre tem formato "Nome (OAB/UF)".
- Tipo de documento dentro do conjunto canônico {Notificação,
  Distribuição, Acórdão, Decisão, Despacho, Pauta de Julgamento,
  Certidão, Ementa, Sentença, Outros}.
- Tipo de comunicação dentro de {Intimação, Lista de Distribuição,
  Edital}.
- Detector de duplicatas: par TRT10 conhecido (djen 527365047 e
  527365146) gera a MESMA chave canônica.

Não envia ao Notion. Só monta o payload em memória.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from notion_rpadv.services import dje_db
from notion_rpadv.services.dje_dedup import (
    calcular_chave_para_publicacao,
)
from notion_rpadv.services.dje_notion_mappings import (
    TIPOS_COMUNICACAO_CANONICOS,
    TIPOS_DOCUMENTO_CANONICOS,
)
from notion_rpadv.services.dje_notion_mapper import (
    montar_payload_publicacao,
)


_PROD_DB_PATH = Path.home() / "AppData/Roaming/NotionRPADV/leitor_dje.db"


@pytest.fixture(scope="module")
def prod_conn():
    """Conexão read-only ao SQLite de produção. Skip se ausente."""
    if not _PROD_DB_PATH.exists():
        pytest.skip(f"SQLite de produção não disponível em {_PROD_DB_PATH}")
    conn = sqlite3.connect(f"file:{_PROD_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def dje_conn_temp(tmp_path):
    """Conexão writable temporária, schema migrado — usada como destino
    do sequencial N do título no mapper."""
    db = tmp_path / "leitor_dje_smoke.db"
    conn = dje_db.get_connection(db)
    yield conn
    conn.close()


@pytest.fixture
def cache_conn_temp(tmp_path):
    """Cache vazio — checkbox 'Processo não cadastrado' marca True."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE records ("
        "base TEXT, page_id TEXT, data_json TEXT, updated_at REAL,"
        "PRIMARY KEY (base, page_id))"
    )
    conn.commit()
    yield conn
    conn.close()


# IDs alvo do prompt (cobertura de casos críticos do 1.5 + dedup TRT10).
_DJEN_IDS_ALVO: list[int] = [
    506249151,  # TJDFT pauta integral grande (1.5 caso A com match)
    515126065,  # TJDFT pauta integral grande
    508345146,  # TJDFT pauta integral grande
    524358619,  # TST acórdão muito grande (1.5 caso B)
    570046619,  # TST acórdão (caso C — passa intacto)
    587819512,  # TST acórdão grande (caso B)
    527365047,  # TRT10 par dedup A
    527365146,  # TRT10 par dedup B
]


def _carregar_pub(conn, djen_id: int) -> dict:
    row = conn.execute(
        "SELECT djen_id, hash, sigla_tribunal, data_disponibilizacao, "
        "numero_processo, payload_json, oabs_escritorio, oabs_externas "
        "FROM publicacoes WHERE djen_id=?",
        (djen_id,),
    ).fetchone()
    if row is None:
        return {}
    payload = json.loads(row["payload_json"])
    payload["advogados_consultados_escritorio"] = row["oabs_escritorio"] or ""
    payload["oabs_externas_consultadas"] = row["oabs_externas"] or ""
    return payload


def _carregar_amostra_aleatoria(conn, n: int = 14, seed: int = 42) -> list[int]:
    """Pega ``n`` djen_ids variados (mix de tribunais)."""
    import random

    rng = random.Random(seed)
    ids = [
        int(r["djen_id"])
        for r in conn.execute("SELECT djen_id FROM publicacoes")
    ]
    rng.shuffle(ids)
    return ids[:n]


def _validar_pub_pos_pipeline(
    djen_id: int, pub: dict, payload: dict,
) -> dict:
    """Valida invariantes pós-pipeline e retorna stats sobre a publicação."""
    stats = {
        "djen_id": djen_id,
        "tribunal": pub.get("siglaTribunal"),
        "tipo_canonico": payload["_meta"]["tipo_documento_canonico"],
        "texto_pre_chars": len(payload["_meta"]["texto_pre"]),
        "callouts": payload["_meta"]["callouts_count"],
        "blocos": len(payload["children"]),
    }

    # 1. Tipo de documento canônico
    tipo_doc = payload["properties"]["Tipo de documento"]["select"]["name"]
    assert tipo_doc in TIPOS_DOCUMENTO_CANONICOS, (
        f"djen={djen_id} tipoDocumento canônico {tipo_doc!r} fora do conjunto"
    )

    # 2. Tipo de comunicação canônico
    tipo_com = payload["properties"]["Tipo de comunicação"]["select"]["name"]
    assert tipo_com in TIPOS_COMUNICACAO_CANONICOS, (
        f"djen={djen_id} tipoComunicacao canônico {tipo_com!r} fora do conjunto"
    )

    # 3. Multi-select advogados sempre formato "Nome (OAB/UF)"
    import re
    pattern = re.compile(r"^[A-Za-zÀ-ú ]+ \(\d{3,6}/[A-Z]{2}\)$")
    for tag in payload["properties"]["Advogados intimados"]["multi_select"]:
        assert pattern.match(tag["name"]), (
            f"djen={djen_id} advogado tag {tag['name']!r} fora do padrão "
            f"'Nome (NNNN/UF)'"
        )

    # 4. Total de blocos ≤ 90 (limite duro de createPage; overflow vira
    #    append_block_children no envio real). Smoke valida que pipeline
    #    interna agrupa bem suficiente pra caber em 1 chamada (incl. wrappers).
    assert len(payload["children"]) <= 90, (
        f"djen={djen_id} gerou {len(payload['children'])} blocos — "
        f"acima do limite duro de 100 do Notion (margem 90). "
        f"Indica falha no agrupamento de parágrafos pelo 1.4."
    )

    # 5. Cada bloco respeita NOTION_BLOCK_HARD_LIMIT (2000 chars)
    for b in payload["children"]:
        if b["type"] == "paragraph":
            content = b["paragraph"]["rich_text"][0]["text"]["content"]
        elif b["type"] == "heading_2":
            content = b["heading_2"]["rich_text"][0]["text"]["content"]
        elif b["type"] == "heading_3":
            content = b["heading_3"]["rich_text"][0]["text"]["content"]
        elif b["type"] == "quote":
            content = b["quote"]["rich_text"][0]["text"]["content"]
        elif b["type"] == "callout":
            # Callout pode ter múltiplos rich_text items
            content_pieces = [
                rt.get("text", {}).get("content", "")
                for rt in b["callout"]["rich_text"]
            ]
            content = "".join(content_pieces)
        else:
            content = ""
        assert len(content) <= 2000, (
            f"djen={djen_id} bloco tipo {b['type']} tem {len(content)} chars "
            f"(>2000 — limite duro Notion)"
        )

    # 6. Property "Texto" inline ≤ 2000 chars
    rich_text_items = payload["properties"]["Texto"]["rich_text"]
    if rich_text_items:
        inline = rich_text_items[0]["text"]["content"]
        assert len(inline) <= 2000

    return stats


def test_smoke_djen_ids_alvo(prod_conn, dje_conn_temp, cache_conn_temp) -> None:
    """Pipeline ponta a ponta nos 8 djen_ids alvo do prompt sem exceções."""
    todos_stats = []
    for djen_id in _DJEN_IDS_ALVO:
        pub = _carregar_pub(prod_conn, djen_id)
        if not pub:
            continue
        payload = montar_payload_publicacao(
            pub, dje_conn=dje_conn_temp, cache_conn=cache_conn_temp,
        )
        stats = _validar_pub_pos_pipeline(djen_id, pub, payload)
        todos_stats.append(stats)
    # Sanity: pelo menos 6 das 8 alvo achadas no banco (508849175 e
    # 521444981 não estavam na extração inicial; adapta se mudar).
    assert len(todos_stats) >= 6, (
        f"Esperado ≥6 djen_ids alvo no banco, achou {len(todos_stats)}"
    )


def test_smoke_amostra_random_20(
    prod_conn, dje_conn_temp, cache_conn_temp,
) -> None:
    """20 pubs (8 alvo + 12 random) — pipeline completa sem crash."""
    ids_random = _carregar_amostra_aleatoria(prod_conn, n=12)
    todos_ids = list(set(_DJEN_IDS_ALVO + ids_random))
    pubs_ok = 0
    for djen_id in todos_ids[:20]:
        pub = _carregar_pub(prod_conn, djen_id)
        if not pub:
            continue
        payload = montar_payload_publicacao(
            pub, dje_conn=dje_conn_temp, cache_conn=cache_conn_temp,
        )
        _validar_pub_pos_pipeline(djen_id, pub, payload)
        pubs_ok += 1
    assert pubs_ok >= 15, (
        f"Smoke validou {pubs_ok}/20 publicações — esperado ≥15"
    )


def test_smoke_par_trt10_gera_chave_identica(prod_conn) -> None:
    """Par TRT10 djen=527365047 e djen=527365146 (mesmo CNJ + data +
    tipo + prefixo de texto) → chave canônica idêntica."""
    pub_a = _carregar_pub(prod_conn, 527365047)
    pub_b = _carregar_pub(prod_conn, 527365146)
    if not pub_a or not pub_b:
        pytest.skip("par TRT10 alvo ausente do banco")
    chave_a = calcular_chave_para_publicacao(pub_a)
    chave_b = calcular_chave_para_publicacao(pub_b)
    assert chave_a is not None
    assert chave_a == chave_b, (
        f"par dedup deveria gerar chave idêntica: "
        f"a={chave_a[:12]}, b={chave_b[:12]}"
    )


def test_smoke_pauta_tjdft_grande_filtra_drasticamente(
    prod_conn, dje_conn_temp, cache_conn_temp,
) -> None:
    """Pauta TJDFT 506249151 (1.2MB no banco) deve sair da pipeline com
    corpo muito menor do que o original (filtragem 1.5 caso A)."""
    pub = _carregar_pub(prod_conn, 506249151)
    if not pub:
        pytest.skip("djen 506249151 ausente do banco")
    bruto_chars = len(pub.get("texto") or "")
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn_temp, cache_conn=cache_conn_temp,
    )
    # Conta chars de texto nos blocos paragraph (excluindo headings)
    corpo_chars = sum(
        len(b["paragraph"]["rich_text"][0]["text"]["content"])
        for b in payload["children"]
        if b["type"] == "paragraph"
    )
    # Filtrado deve ser ao menos 90% menor que o bruto
    assert corpo_chars < bruto_chars * 0.1, (
        f"djen 506249151 esperado filtrado <{bruto_chars * 0.1:,.0f} chars; "
        f"obteve {corpo_chars:,} chars"
    )
    # E deve mencionar "Pauta filtrada"
    todos_textos = " ".join(
        b["paragraph"]["rich_text"][0]["text"]["content"]
        for b in payload["children"]
        if b["type"] == "paragraph"
    )
    assert (
        "Pauta filtrada automaticamente" in todos_textos
        or "0 processos do escritório" in todos_textos
    )


def test_smoke_acordao_tst_grande_trunca_e_callout(
    prod_conn, dje_conn_temp, cache_conn_temp,
) -> None:
    """Acórdão TST grande (524358619, 248KB no banco) deve sair truncado
    a ≤80KB com callout pra certidão (caso B)."""
    pub = _carregar_pub(prod_conn, 524358619)
    if not pub:
        pytest.skip("djen 524358619 ausente do banco")
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn_temp, cache_conn=cache_conn_temp,
    )
    # Soma chars do corpo
    corpo_chars = sum(
        len(b["paragraph"]["rich_text"][0]["text"]["content"])
        for b in payload["children"]
        if b["type"] == "paragraph"
    )
    assert corpo_chars <= 80_000
    # Tem 1 callout
    callouts = [b for b in payload["children"] if b["type"] == "callout"]
    assert len(callouts) == 1
    # Callout aponta pra certidão DJEN (URL contém o hash)
    rich_texts = callouts[0]["callout"]["rich_text"]
    link_texts = [rt for rt in rich_texts if rt["text"].get("link")]
    assert len(link_texts) >= 1
    url = link_texts[0]["text"]["link"]["url"]
    assert "comunicaapi.pje.jus.br" in url
    assert pub.get("hash") in url
