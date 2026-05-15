"""Testes do ``notion_rpadv.services.dje_notion_mapper`` (Fase 5,
2026-05-03).

Cobre:
- Mapeamento das 18 propriedades enviáveis (2 ficam de fora: Cliente
  é Rollup, Certidão é Formula).
- Truncamento de Texto em 2000 chars + corpo em blocos.
- Lookup do Processo no cache local (Relation).
- Cruzamento de advogados do escritório no multi-select.
- Checkboxes "Processo não cadastrado" e "Advogados não cadastrados".
- Sequencial N do título.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from notion_rpadv.services import dje_db
from notion_rpadv.services.dje_notion_mapper import (
    _advogados_escritorio_em_destinatarios,
    _build_corpo_blocks,
    _split_paragraph_at_limit,
    _truncate_with_ellipsis,
    listar_processos_lookup,
    lookup_processo_page_id,
    montar_payload_publicacao,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dje_conn(tmp_path: Path):
    db = tmp_path / "leitor_dje.db"
    conn = dje_db.get_connection(db)
    yield conn
    conn.close()


@pytest.fixture
def cache_conn(tmp_path: Path):
    """Cache em memória com schema mínimo de records (mesmo do
    cache.db real)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE records (
            base TEXT NOT NULL, page_id TEXT NOT NULL,
            data_json TEXT NOT NULL, updated_at REAL NOT NULL,
            PRIMARY KEY (base, page_id)
        )
        """,
    )
    conn.commit()
    yield conn
    conn.close()


def _seed_processo(cache_conn, page_id: str, numero: str) -> None:
    cache_conn.execute(
        "INSERT INTO records (base, page_id, data_json, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("Processos", page_id,
         json.dumps({"numero_do_processo": numero}), 0.0),
    )
    cache_conn.commit()


def _publicacao_basica(**overrides) -> dict:
    base = {
        "id": 1001,
        "hash": "h-abc-123",
        "siglaTribunal": "TRT10",
        "data_disponibilizacao": "2026-04-30",
        "numeroprocessocommascara": "0001234-56.2025.5.10.0001",
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "Vara do Trabalho de Brasília",
        "nomeClasse": "Reclamação Trabalhista",
        "texto": "Texto curto da publicação.",
        "link": "https://comunicaapi.pje.jus.br/abc",
        "destinatarios": [
            {"nome": "ACME LTDA", "polo": "PASSIVO"},
        ],
        "destinatarioadvogados": [
            {"advogado": {
                "numero_oab": "15523",
                "uf_oab": "DF",
                "nome": "RICARDO LUIZ RODRIGUES DA FONSECA PASSOS",
            }},
        ],
        "observacoes": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Helpers atômicos
# ---------------------------------------------------------------------------


def test_truncate_with_ellipsis_no_corte() -> None:
    assert _truncate_with_ellipsis("abc", 10) == "abc"
    assert _truncate_with_ellipsis("abcdefghij", 10) == "abcdefghij"


def test_truncate_with_ellipsis_corta() -> None:
    out = _truncate_with_ellipsis("a" * 100, 10)
    assert len(out) == 10
    assert out.endswith("...")


def test_split_paragraph_at_limit_pequeno_passa_direto() -> None:
    chunks = _split_paragraph_at_limit("texto curto", 2000)
    assert chunks == ["texto curto"]


def test_split_paragraph_at_limit_quebra_em_chunks() -> None:
    """Texto > limit é quebrado em N chunks."""
    text = "a" * 5000
    chunks = _split_paragraph_at_limit(text, 2000)
    assert len(chunks) == 3
    # Soma de chars (descontando espaços de quebra) ~= original
    assert sum(len(c) for c in chunks) >= len(text) - len(chunks)


def test_advogados_escritorio_em_destinatarios_so_internos() -> None:
    """Cruzamento: só os 12 do escritório aparecem; externos ignorados."""
    destinatarios = [
        {"advogado": {"numero_oab": "15523", "uf_oab": "DF", "nome": "X"}},
        {"advogado": {"numero_oab": "99999", "uf_oab": "SP", "nome": "Y"}},
        {"advogado": {"numero_oab": "36129", "uf_oab": "DF", "nome": "Z"}},
    ]
    tags = _advogados_escritorio_em_destinatarios(destinatarios)
    assert "Ricardo (15523/DF)" in tags
    assert "Leonardo (36129/DF)" in tags
    assert len(tags) == 2  # externo (99999/SP) descartado


def test_advogados_escritorio_em_destinatarios_lista_vazia() -> None:
    assert _advogados_escritorio_em_destinatarios([]) == []
    assert _advogados_escritorio_em_destinatarios(None) == []


def test_advogados_escritorio_dedup_quando_mesma_oab_aparece_2x() -> None:
    """Mesmo advogado listado duas vezes (caso patológico do DJEN) entra
    1x só na tag list."""
    destinatarios = [
        {"advogado": {"numero_oab": "15523", "uf_oab": "DF", "nome": "X"}},
        {"advogado": {"numero_oab": "15523", "uf_oab": "DF", "nome": "X"}},
    ]
    tags = _advogados_escritorio_em_destinatarios(destinatarios)
    assert tags == ["Ricardo (15523/DF)"]


# ---------------------------------------------------------------------------
# Lookup do Processo
# ---------------------------------------------------------------------------


def test_lookup_processo_match_encontra_page_id(cache_conn) -> None:
    _seed_processo(cache_conn, "page-uuid-1", "0001234-56.2025.5.10.0001")
    pid = lookup_processo_page_id(
        cache_conn, "0001234-56.2025.5.10.0001",
    )
    assert pid == "page-uuid-1"


def test_lookup_processo_sem_match_retorna_none(cache_conn) -> None:
    _seed_processo(cache_conn, "page-uuid-1", "0001234-56.2025.5.10.0001")
    pid = lookup_processo_page_id(cache_conn, "9999999-99.9999.9.99.9999")
    assert pid is None


def test_lookup_processo_normaliza_cnj_de_ambos_lados(cache_conn) -> None:
    """CNJ sem máscara no cache + CNJ com máscara na publicação ainda
    matcheiam após normalização."""
    _seed_processo(cache_conn, "page-2", "00012345620255100001")
    pid = lookup_processo_page_id(
        cache_conn, "0001234-56.2025.5.10.0001",
    )
    assert pid == "page-2"


def test_lookup_processo_invalido_retorna_none(cache_conn) -> None:
    """Numeração pré-CNJ ou string vazia → None (sem crash)."""
    assert lookup_processo_page_id(cache_conn, None) is None
    assert lookup_processo_page_id(cache_conn, "") is None
    assert lookup_processo_page_id(cache_conn, "numero antigo") is None


def test_listar_processos_lookup_dict(cache_conn) -> None:
    """``listar_processos_lookup`` retorna dict cnj→page_id pra speedups."""
    _seed_processo(cache_conn, "p1", "0000001-00.2024.1.00.0001")
    _seed_processo(cache_conn, "p2", "0000002-00.2024.1.00.0002")
    out = listar_processos_lookup(cache_conn)
    assert out == {
        "0000001-00.2024.1.00.0001": "p1",
        "0000002-00.2024.1.00.0002": "p2",
    }


# ---------------------------------------------------------------------------
# Corpo da página
# ---------------------------------------------------------------------------


def test_build_corpo_tem_2_secoes() -> None:
    """Com observações: heading 'Texto da publicação' + paragraph(s) +
    heading 'Observações' + paragraph(s)."""
    blocks = _build_corpo_blocks("Texto curto.", "Obs A")
    types = [b["type"] for b in blocks]
    assert types[0] == "heading_2"
    assert types[1] == "paragraph"
    # Round 11.2 — heading "Observações" só aparece se obs_pre não vazio.
    headings = [b for b in blocks if b["type"] == "heading_2"]
    assert len(headings) == 2
    assert any(
        "Observações" in h["heading_2"]["rich_text"][0]["text"]["content"]
        for h in headings
    )


def test_build_corpo_texto_grande_quebra_em_paragrafos_multiplos() -> None:
    """Texto > 2000 chars vira múltiplos blocos paragraph."""
    texto = ("a" * 3000) + "\n\n" + ("b" * 3000)
    blocks = _build_corpo_blocks(texto, None)
    paragraphs = [b for b in blocks if b["type"] == "paragraph"]
    # Pelo menos 4 paragraphs (2 por seção a + 2 por seção b).
    assert len(paragraphs) >= 4


def test_build_corpo_observacoes_vazia_omite_secao() -> None:
    """Round 11.2 — quando não há observações automáticas, o builder
    NÃO emite o heading 'Observações' nem o quote placeholder
    'Sem observações automáticas pra esta publicação.'.
    """
    blocks = _build_corpo_blocks("Texto.", None)
    # Nenhum quote/placeholder
    quotes = [b for b in blocks if b["type"] == "quote"]
    assert quotes == []
    # Único heading_2 é o da seção "Texto da publicação"
    headings = [b for b in blocks if b["type"] == "heading_2"]
    assert len(headings) == 1
    assert (
        "Texto da publicação"
        in headings[0]["heading_2"]["rich_text"][0]["text"]["content"]
    )


def test_build_corpo_texto_vazio_emite_placeholder_de_texto() -> None:
    """Round 11.2 — quando texto e observações são vazios: emite só o
    heading 'Texto da publicação' + paragraph '(texto vazio)'. Sem
    seção 'Observações'.
    """
    blocks = _build_corpo_blocks("", "")
    paragraphs = [b for b in blocks if b["type"] == "paragraph"]
    assert any(
        "(texto vazio)" in p["paragraph"]["rich_text"][0]["text"]["content"]
        for p in paragraphs
    )
    quotes = [b for b in blocks if b["type"] == "quote"]
    assert quotes == []


# ---------------------------------------------------------------------------
# montar_payload_publicacao — caso happy path
# ---------------------------------------------------------------------------


def test_payload_happy_path_18_propriedades(dje_conn, cache_conn) -> None:
    """Caso típico: processo cadastrado + 1 advogado do escritório.
    Round 4.6 removeu o checkbox 'Processo não cadastrado' e Round 4.3+4.4
    adicionou os multi-selects 'Tarefa sugerida' e 'Alerta contadoria'.
    Round 9 (2026-05-07) adicionou snapshot 'Fase' e 'Instância' — agora
    são 21 propriedades enviáveis."""
    _seed_processo(cache_conn, "page-proc-1", "0001234-56.2025.5.10.0001")
    pub = _publicacao_basica()
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    props = payload["properties"]
    expected_keys = {
        "Identificação", "Data de disponibilização", "Tribunal",
        "Processo", "Órgão", "Tipo de comunicação", "Tipo de documento",
        "Classe", "Texto", "Link", "Status", "Advogados intimados",
        "Observações", "Partes", "Hash", "ID DJEN",
        "Advogados não cadastrados",
        # Round 10 (2026-05-07) — 3 propriedades multi_select.
        "Tarefa advogado", "Tarefa contadoria", "Alerta contadoria",
        # Round 9 (2026-05-07) — snapshot histórico de fase/instância.
        "Fase", "Instância",
    }
    assert set(props.keys()) == expected_keys
    # Round 4.6: checkbox 'Processo não cadastrado' não existe mais.
    assert "Processo não cadastrado" not in props
    # Relation com 1 page_id
    assert props["Processo"]["relation"] == [{"id": "page-proc-1"}]
    # Multi-select com Ricardo
    nomes = [t["name"] for t in props["Advogados intimados"]["multi_select"]]
    assert nomes == ["Ricardo (15523/DF)"]
    # Status sempre "Nova"
    assert props["Status"]["select"]["name"] == "Nova"
    # Round 11.4 (2026-05-14): corpo da página é mantido vazio.
    # O texto integral vive na propriedade Texto (até 199k chars em
    # múltiplos itens rich_text).
    assert payload["children"] == []


def test_payload_processo_nao_cadastrado_marca_alerta(
    dje_conn, cache_conn,
) -> None:
    """Round 10 (2026-05-07): o sinalizador 'Processo não cadastrado'
    vive em ``Alerta contadoria`` como AC26. Não dispara em pubs de
    distribuição (TC01 já cobre).
    """
    pub = _publicacao_basica(numeroprocessocommascara="9999999-99.9999.9.99.9999")
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    props = payload["properties"]
    # Checkbox antigo NÃO está mais no payload.
    assert "Processo não cadastrado" not in props
    # As 3 propriedades novas estão presentes.
    assert "Tarefa advogado" in props
    assert "Tarefa contadoria" in props
    assert "Alerta contadoria" in props
    # Relation continua vazia (sem cadastro).
    assert props["Processo"]["relation"] == []


def test_payload_advogados_nao_cadastrados_so_externos(
    dje_conn, cache_conn,
) -> None:
    """Destinatários só com OABs externas → checkbox TRUE +
    multi-select vazio."""
    pub = _publicacao_basica(
        destinatarioadvogados=[
            {"advogado": {
                "numero_oab": "99999", "uf_oab": "SP", "nome": "EXT",
            }},
        ],
    )
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    props = payload["properties"]
    assert props["Advogados não cadastrados"]["checkbox"] is True
    assert props["Advogados intimados"]["multi_select"] == []


def test_payload_destinatarios_vazia_nao_marca_advogados_nao_cadastrados(
    dje_conn, cache_conn,
) -> None:
    """Lista vazia (sem nenhum destinatário) NÃO marca o checkbox —
    distinção do spec D20."""
    pub = _publicacao_basica(destinatarioadvogados=[])
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    assert payload["properties"]["Advogados não cadastrados"]["checkbox"] is False


def test_payload_titulo_sequencial_incrementa(dje_conn, cache_conn) -> None:
    """Título incorpora N sequencial — 2ª publicação no mesmo dia/tribunal
    vira ___2."""
    pub1 = _publicacao_basica(id=1)
    payload1 = montar_payload_publicacao(
        pub1, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    titulo1 = payload1["properties"]["Identificação"]["title"][0]["text"]["content"]
    assert titulo1 == "TRT10___2026-04-30___1"

    # Insere uma pub no banco e marca como enviada — proxima vira ___2.
    dje_conn.execute(
        "INSERT INTO publicacoes (djen_id, hash, oabs_escritorio, "
        "oabs_externas, numero_processo, data_disponibilizacao, "
        "sigla_tribunal, payload_json, captured_at, captured_in_mode, "
        "notion_page_id) VALUES (1, 'h1', '', '', NULL, '2026-04-30', "
        "'TRT10', '{}', '2026-04-30T10:00:00', 'padrao', 'page-uuid-1')",
    )
    dje_conn.commit()
    pub2 = _publicacao_basica(id=2)
    payload2 = montar_payload_publicacao(
        pub2, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    titulo2 = payload2["properties"]["Identificação"]["title"][0]["text"]["content"]
    assert titulo2 == "TRT10___2026-04-30___2"


def test_payload_texto_grande_vira_multiplos_itens_rich_text(
    dje_conn, cache_conn,
) -> None:
    """Round 11.3 — texto > 2000 chars vira múltiplos itens rich_text
    na propriedade 'Texto' (cada item ≤ 1990 chars, total reconstrói o
    texto original). Antes: 1 item truncado em 2000 com marcador
    '[…]'. Agora: até 100 itens × 1990 = ~199k chars suportados.

    Round 11.4 — corpo da página fica vazio; o texto vive só na
    propriedade.
    """
    texto_grande = "X" * 5000
    pub = _publicacao_basica(texto=texto_grande)
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    rich_text = payload["properties"]["Texto"]["rich_text"]
    # 5000 / 1990 ≈ 3 itens (sem espaços, corta cru no chunk_max).
    assert len(rich_text) >= 3
    # Cada item respeita o limite duro da API.
    for item in rich_text:
        assert len(item["text"]["content"]) <= 2000
    # Concatenação reproduz o texto original na íntegra (sem marcador
    # de truncamento — cabe nos 199k chars).
    reconstruido = "".join(it["text"]["content"] for it in rich_text)
    assert reconstruido == texto_grande
    # Round 11.4: corpo permanece vazio.
    assert payload["children"] == []


def test_payload_status_sempre_nova(dje_conn, cache_conn) -> None:
    """Status na criação é sempre "Nova" — não sobrescreve, app só cria."""
    pub = _publicacao_basica()
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    assert payload["properties"]["Status"]["select"]["name"] == "Nova"


def test_payload_meta_inclui_titulo_e_djen_id(dje_conn, cache_conn) -> None:
    """``_meta`` é dict com info pra logging; não vai pra API Notion."""
    pub = _publicacao_basica(id=42)
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    meta = payload["_meta"]
    assert meta["djen_id"] == 42
    assert meta["sigla_tribunal"] == "TRT10"
    assert "TRT10___2026-04-30___" in meta["titulo"]


# ---------------------------------------------------------------------------
# Round 9 (2026-05-07) — Snapshot Fase + Instância nas Publicações
# ---------------------------------------------------------------------------


def _seed_processo_completo(
    cache_conn, page_id: str, numero: str,
    fase: str | None = None, instancia: str | None = None,
) -> None:
    data = {"numero_do_processo": numero}
    if fase is not None:
        data["fase"] = fase
    if instancia is not None:
        data["instancia"] = instancia
    cache_conn.execute(
        "INSERT INTO records (base, page_id, data_json, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("Processos", page_id, json.dumps(data), 0.0),
    )
    cache_conn.commit()


def test_R9_payload_inclui_fase_e_instancia_do_cache(
    dje_conn, cache_conn,
) -> None:
    """Sem notion_client: usa Fase e Instância direto do cache."""
    _seed_processo_completo(
        cache_conn, "page-proc-1", "0001234-56.2025.5.10.0001",
        fase="Executiva", instancia="1º grau",
    )
    pub = _publicacao_basica()
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    props = payload["properties"]
    assert props["Fase"]["select"] == {"name": "Executiva"}
    assert props["Instância"]["select"] == {"name": "1º grau"}


def test_R9_payload_fase_instancia_vazias_quando_processo_nao_cadastrado(
    dje_conn, cache_conn,
) -> None:
    """Pub.Processo não cadastrado → Fase e Instância vazias."""
    pub = _publicacao_basica()
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    props = payload["properties"]
    assert props["Fase"]["select"] is None
    assert props["Instância"]["select"] is None


def test_R9_payload_fase_invalida_fica_vazia(
    dje_conn, cache_conn,
) -> None:
    """Fase fora do vocabulário não é gravada (vai vazia)."""
    _seed_processo_completo(
        cache_conn, "page-proc-1", "0001234-56.2025.5.10.0001",
        fase="VALOR_FORA_DO_SELECT", instancia="1º grau",
    )
    pub = _publicacao_basica()
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
    )
    props = payload["properties"]
    assert props["Fase"]["select"] is None
    assert props["Instância"]["select"] == {"name": "1º grau"}


def test_R9_payload_pull_live_atualiza_cache_e_payload(
    dje_conn, cache_conn,
) -> None:
    """Quando notion_client é fornecido, pull live atualiza cache E
    payload com o estado mais recente do Notion."""
    from unittest.mock import MagicMock

    # Cache tem fase="Cognitiva", mas Notion live mudou pra "Executiva"
    _seed_processo_completo(
        cache_conn, "page-proc-1", "0001234-56.2025.5.10.0001",
        fase="Cognitiva", instancia="1º grau",
    )

    fake_client = MagicMock()
    fake_client.get_page.return_value = {
        "id": "page-proc-1",
        "properties": {
            "Fase": {"type": "select", "select": {"name": "Executiva"}},
            "Instância": {
                "type": "select", "select": {"name": "2º grau"},
            },
        },
    }

    pub = _publicacao_basica()
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
        notion_client=fake_client,
    )

    # Payload reflete o live (não o stale do cache)
    assert payload["properties"]["Fase"]["select"] == {"name": "Executiva"}
    assert payload["properties"]["Instância"]["select"] == {"name": "2º grau"}

    # Cache também foi atualizado
    row = cache_conn.execute(
        "SELECT data_json FROM records WHERE base='Processos' AND page_id=?",
        ("page-proc-1",),
    ).fetchone()
    cache_data = json.loads(row["data_json"])
    assert cache_data["fase"] == "Executiva"
    assert cache_data["instancia"] == "2º grau"


def test_R9_payload_pull_live_falha_silenciosa_mantem_cache(
    dje_conn, cache_conn,
) -> None:
    """Se get_page levantar exceção, mantém valor do cache (não bloqueia)."""
    from unittest.mock import MagicMock

    _seed_processo_completo(
        cache_conn, "page-proc-1", "0001234-56.2025.5.10.0001",
        fase="Cognitiva", instancia="1º grau",
    )

    fake_client = MagicMock()
    fake_client.get_page.side_effect = ConnectionError("rede caiu")

    pub = _publicacao_basica()
    payload = montar_payload_publicacao(
        pub, dje_conn=dje_conn, cache_conn=cache_conn,
        notion_client=fake_client,
    )
    # Fallback: usa o que tinha no cache
    assert payload["properties"]["Fase"]["select"] == {"name": "Cognitiva"}
    assert payload["properties"]["Instância"]["select"] == {"name": "1º grau"}
