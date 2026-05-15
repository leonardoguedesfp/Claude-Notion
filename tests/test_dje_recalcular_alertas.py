"""Round 10 — testes do serviço ``dje_recalcular_alertas`` adaptado
pra 3 propriedades multi_select.

Cobertura:
- Decodificação das 3 propriedades atuais a partir de Page do Notion.
- Iteração só sobre publicações ``notion_page_id`` populado e ≠ SKIPPED.
- Idempotência: ``update_page`` é chamado APENAS quando há diff em
  qualquer das 3 propriedades.
- ``dry_run``: nada vai ao Notion mas o contador de "seriam atualizadas"
  reflete o diff calculado.
- ``always_update``: força escrita mesmo sem diff.
- Tolerância a payload corrompido — não derruba o pipeline.
- Pulo de pubs sem correspondência no Notion (page deletada externamente).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any
from unittest.mock import MagicMock

from notion_rpadv.services.dje_recalcular_alertas import (
    NOTION_SKIPPED_SENTINEL,
    PLACEHOLDER_OBSERVACOES,
    PROPS_DAS_TAGS,
    ResultadoRecalculo,
    _multi_select_payload,
    _reescrever_corpo_pagina,
    _tags_atuais_de_page,
    _tem_placeholder_observacoes,
    _texto_paragraphs,
    recalcular_alertas_publicacoes,
)


# ---------------------------------------------------------------------------
# Fixtures helper
# ---------------------------------------------------------------------------


def _abrir_dje_db_em_memoria() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE publicacoes (
            djen_id INTEGER PRIMARY KEY,
            hash TEXT,
            oabs_escritorio TEXT NOT NULL,
            oabs_externas TEXT,
            numero_processo TEXT,
            data_disponibilizacao TEXT NOT NULL,
            sigla_tribunal TEXT,
            payload_json TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            captured_in_mode TEXT NOT NULL,
            notion_page_id TEXT,
            notion_attempts INTEGER NOT NULL DEFAULT 0,
            notion_last_error TEXT
        )
        """,
    )
    conn.commit()
    return conn


def _abrir_cache_db_em_memoria() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE records (
            base TEXT NOT NULL,
            page_id TEXT NOT NULL,
            data_json TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (base, page_id)
        )
        """,
    )
    conn.commit()
    return conn


def _inserir_pub(
    dje_conn: sqlite3.Connection,
    *,
    djen_id: int,
    cnj: str,
    notion_page_id: str | None,
    payload: dict[str, Any],
    data_disp: str = "2026-04-15",
    sigla: str = "TRT10",
    oabs: str = "36129/DF",
) -> None:
    dje_conn.execute(
        """
        INSERT INTO publicacoes
            (djen_id, hash, oabs_escritorio, oabs_externas,
             numero_processo, data_disponibilizacao, sigla_tribunal,
             payload_json, captured_at, captured_in_mode,
             notion_page_id, notion_attempts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            djen_id, f"hash{djen_id}", oabs, "",
            cnj, data_disp, sigla,
            json.dumps(payload), "2026-04-15T10:00:00", "padrao",
            notion_page_id, 0,
        ),
    )
    dje_conn.commit()


def _inserir_processo(
    cache_conn: sqlite3.Connection,
    *,
    page_id: str,
    cnj: str,
    extras: dict[str, Any] | None = None,
) -> None:
    rec: dict[str, Any] = {"numero_do_processo": cnj}
    if extras:
        rec.update(extras)
    cache_conn.execute(
        "INSERT INTO records (base, page_id, data_json, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("Processos", page_id, json.dumps(rec), 1.0),
    )
    cache_conn.commit()


def _make_notion_page(
    page_id: str,
    *,
    tarefa_advogado: list[str] | None = None,
    tarefa_contadoria: list[str] | None = None,
    alerta_contadoria: list[str] | None = None,
    texto: str | None = None,
) -> dict[str, Any]:
    """Mock no formato Page Notion com as 3 propriedades multi_select.

    Round 11 — opcional ``texto`` simula a propriedade ``Texto`` (rich_text)
    pra testes de backfill da limpeza/corpo.
    """
    page: dict[str, Any] = {
        "id": page_id,
        "properties": {
            "Tarefa advogado": {
                "multi_select": [
                    {"name": t} for t in (tarefa_advogado or [])
                ],
            },
            "Tarefa contadoria": {
                "multi_select": [
                    {"name": t} for t in (tarefa_contadoria or [])
                ],
            },
            "Alerta contadoria": {
                "multi_select": [
                    {"name": t} for t in (alerta_contadoria or [])
                ],
            },
        },
    }
    if texto is not None:
        page["properties"]["Texto"] = {
            "rich_text": [
                {"plain_text": texto, "text": {"content": texto}},
            ] if texto else [],
        }
    return page


# ---------------------------------------------------------------------------
# Round 11.2 — helpers de blocos do corpo
# ---------------------------------------------------------------------------


def _bloco_paragraph(content: str) -> dict[str, Any]:
    """Constrói um block paragraph no formato que a API Notion devolve."""
    return {
        "object": "block",
        "id": f"blk-{abs(hash(content)) % 1_000_000}",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "plain_text": content,
                    "text": {"content": content},
                },
            ],
        },
    }


def _bloco_heading2(content: str) -> dict[str, Any]:
    return {
        "object": "block",
        "id": f"hd-{abs(hash(content)) % 1_000_000}",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [
                {
                    "plain_text": content,
                    "text": {"content": content},
                },
            ],
        },
    }


def _bloco_quote(content: str) -> dict[str, Any]:
    return {
        "object": "block",
        "id": f"qt-{abs(hash(content)) % 1_000_000}",
        "type": "quote",
        "quote": {
            "rich_text": [
                {
                    "plain_text": content,
                    "text": {"content": content},
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def test_props_das_tags_lista_3_nomes() -> None:
    assert PROPS_DAS_TAGS == (
        "Tarefa advogado", "Tarefa contadoria", "Alerta contadoria",
    )


def test_tags_atuais_de_page_extrai_3_props() -> None:
    page = _make_notion_page(
        "p1",
        tarefa_advogado=["Analisar acórdão - App"],
        tarefa_contadoria=[],
        alerta_contadoria=["Vara desatualizada - App"],
    )
    out = _tags_atuais_de_page(page)
    assert out == {
        "Tarefa advogado": ["Analisar acórdão - App"],
        "Tarefa contadoria": [],
        "Alerta contadoria": ["Vara desatualizada - App"],
    }


def test_tags_atuais_de_page_props_ausentes_viram_listas_vazias() -> None:
    page = {"id": "p1", "properties": {}}
    out = _tags_atuais_de_page(page)
    assert out == {
        "Tarefa advogado": [], "Tarefa contadoria": [], "Alerta contadoria": [],
    }


def test_multi_select_payload_formato_notion() -> None:
    payload = _multi_select_payload(["A", "B"])
    assert payload == {"multi_select": [{"name": "A"}, {"name": "B"}]}


# ---------------------------------------------------------------------------
# Recálculo end-to-end
# ---------------------------------------------------------------------------


def test_recalculo_idempotente_quando_3_props_iguais() -> None:
    """Pub com tags computadas == atuais nas 3 props → NÃO chama
    update_page."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()

    _inserir_pub(
        dje,
        djen_id=1,
        cnj="0001736-51.2016.5.10.0014",
        notion_page_id="page-1",
        payload={
            "tipoComunicacao": "Intimação",
            "tipoDocumento": "Decisão",
            "siglaTribunal": "TRT10",
            "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
            "numeroprocessocommascara": "0001736-51.2016.5.10.0014",
            "nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
        },
    )
    _inserir_processo(
        cache,
        page_id="proc-1",
        cnj="0001736-51.2016.5.10.0014",
        extras={
            "tribunal": "TRT/10",
            "instancia": "1º grau",
            "vara": "14ª Vara do Trabalho de Brasília - DF",
            "cidade": "Brasília - DF",
            "fase": "Cognitiva",
            "natureza": "Trabalhista",
            "tipo_de_processo": "Principal",
        },
    )

    client = MagicMock()
    client.query_all.return_value = [_make_notion_page("page-1")]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        skip_corpo=True,
    )

    assert res.total_no_banco == 1
    assert res.total_processadas == 1
    assert res.total_atualizadas == 0
    assert res.total_inalteradas == 1
    client.update_page.assert_not_called()


def test_recalculo_atualiza_quando_diff_em_qualquer_prop() -> None:
    """Diff em ``Alerta contadoria`` (Fase executiva) → escreve as 3
    props no update_page."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()

    _inserir_pub(
        dje,
        djen_id=1,
        cnj="0001736-51.2016.5.10.0014",
        notion_page_id="page-1",
        payload={
            "tipoComunicacao": "Intimação",
            "tipoDocumento": "Decisão",
            "siglaTribunal": "TRT10",
            "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
            "numeroprocessocommascara": "0001736-51.2016.5.10.0014",
            "nomeClasse": "CUMPRIMENTO DE SENTENÇA",
        },
    )
    _inserir_processo(
        cache, page_id="proc-1", cnj="0001736-51.2016.5.10.0014",
        extras={
            "tribunal": "TRT/10", "instancia": "1º grau",
            "vara": "14ª Vara do Trabalho de Brasília - DF",
            "fase": "Cognitiva",
            "data_do_transito_em_julgado_cognitiva": "2024-01-01",
        },
    )

    client = MagicMock()
    client.query_all.return_value = [_make_notion_page("page-1")]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        skip_corpo=True,
    )

    assert res.total_atualizadas == 1
    assert res.total_inalteradas == 0
    client.update_page.assert_called_once()
    page_id_arg, props_arg = client.update_page.call_args[0]
    assert page_id_arg == "page-1"
    # As 3 propriedades estão presentes no payload do update.
    for prop in PROPS_DAS_TAGS:
        assert prop in props_arg
    nomes_alerta = [
        it["name"] for it in props_arg["Alerta contadoria"]["multi_select"]
    ]
    assert "Fase desatualizada (executiva) - App" in nomes_alerta


def test_recalculo_dry_run_nao_chama_update() -> None:
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje, djen_id=1, cnj="00000010020265100001",
        notion_page_id="page-1",
        payload={
            "tipoComunicacao": "Intimação",
            "tipoDocumento": "Decisão",
            "siglaTribunal": "TRT10",
            "nomeOrgao": "1ª Vara do Trabalho de Brasília - DF",
            "numeroprocessocommascara": "0000001-00.2026.5.10.0001",
            "nomeClasse": "CUMPRIMENTO DE SENTENÇA",
        },
    )
    _inserir_processo(
        cache, page_id="proc-1", cnj="00000010020265100001",
        extras={"instancia": "1º grau", "fase": "Cognitiva",
                "data_do_transito_em_julgado_cognitiva": "2024-01-01"},
    )
    client = MagicMock()
    client.query_all.return_value = [_make_notion_page("page-1")]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache, dry_run=True,
    )

    assert res.total_atualizadas == 1
    client.update_page.assert_not_called()


def test_recalculo_always_update_escreve_mesmo_sem_diff() -> None:
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje, djen_id=1, cnj="00000010020265100001",
        notion_page_id="page-1",
        payload={
            "tipoComunicacao": "Intimação",
            "tipoDocumento": "Decisão",
            "siglaTribunal": "TRT10",
            "nomeOrgao": "1ª Vara do Trabalho de Brasília - DF",
            "numeroprocessocommascara": "0000001-00.2026.5.10.0001",
        },
    )
    _inserir_processo(
        cache, page_id="proc-1", cnj="00000010020265100001",
        extras={"instancia": "1º grau",
                "vara": "1ª Vara do Trabalho de Brasília - DF",
                "tribunal": "TRT/10"},
    )
    client = MagicMock()
    client.query_all.return_value = [_make_notion_page("page-1")]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        always_update=True,
    )

    assert res.total_atualizadas == 1
    client.update_page.assert_called_once()


def test_recalculo_pula_pubs_skipped() -> None:
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje, djen_id=1, cnj="000100020265100001",
        notion_page_id=NOTION_SKIPPED_SENTINEL,
        payload={"tipoComunicacao": "Intimação"},
    )
    _inserir_pub(
        dje, djen_id=2, cnj="000200020265100002",
        notion_page_id=None,
        payload={"tipoComunicacao": "Intimação"},
    )

    client = MagicMock()
    client.query_all.return_value = []

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        skip_corpo=True,
    )
    assert res.total_no_banco == 0
    assert res.total_processadas == 0


def test_recalculo_pula_payload_invalido() -> None:
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    dje.execute(
        """
        INSERT INTO publicacoes
            (djen_id, hash, oabs_escritorio, oabs_externas,
             numero_processo, data_disponibilizacao, sigla_tribunal,
             payload_json, captured_at, captured_in_mode,
             notion_page_id, notion_attempts)
        VALUES (1, 'h', 'OAB', '', 'CNJ', '2026-01-01', 'TRT10',
                '{not_json',  -- INVÁLIDO
                '2026-01-01', 'padrao', 'page-1', 0)
        """,
    )
    dje.commit()

    client = MagicMock()
    client.query_all.return_value = [_make_notion_page("page-1")]
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        skip_corpo=True,
    )
    assert res.total_pulados_payload_invalido == 1
    assert res.total_processadas == 0
    client.update_page.assert_not_called()


def test_recalculo_pula_pub_sem_correspondencia_no_notion() -> None:
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje, djen_id=1, cnj="00000010020265100001",
        notion_page_id="page-fantasma",
        payload={
            "tipoComunicacao": "Intimação",
            "tipoDocumento": "Decisão",
            "siglaTribunal": "TRT10",
        },
    )
    client = MagicMock()
    client.query_all.return_value = []
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        skip_corpo=True,
    )
    assert res.total_pulados_sem_notion == 1
    client.update_page.assert_not_called()


def test_recalculo_diff_amostrado_inclui_diffs_por_propriedade() -> None:
    """Quando há diff, a amostra carrega o diff por propriedade."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje, djen_id=1, cnj="00000010020265100001",
        notion_page_id="page-1",
        payload={
            "tipoComunicacao": "Intimação",
            "tipoDocumento": "Decisão",
            "siglaTribunal": "TRT10",
            "nomeOrgao": "1ª Vara do Trabalho de Brasília - DF",
            "numeroprocessocommascara": "0000001-00.2026.5.10.0001",
            "nomeClasse": "CUMPRIMENTO DE SENTENÇA",
        },
    )
    _inserir_processo(
        cache, page_id="proc-1", cnj="00000010020265100001",
        extras={"instancia": "1º grau",
                "vara": "1ª Vara do Trabalho de Brasília - DF",
                "fase": "Cognitiva",
                "data_do_transito_em_julgado_cognitiva": "2024-01-01"},
    )
    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page(
            "page-1",
            alerta_contadoria=["Vara desatualizada - App"],
        ),
    ]
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        skip_corpo=True,
    )
    assert res.total_atualizadas == 1
    assert len(res.diffs_amostra) == 1
    diff = res.diffs_amostra[0]
    assert diff["page_id"] == "page-1"
    diffs_por_prop = diff["diffs"]
    assert "Alerta contadoria" in diffs_por_prop
    assert "Vara desatualizada - App" in diffs_por_prop["Alerta contadoria"]["removidos"]
    assert "Fase desatualizada (executiva) - App" in (
        diffs_por_prop["Alerta contadoria"]["adicionados"]
    )


def test_recalculo_callback_progresso_chamado() -> None:
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    for i in range(3):
        _inserir_pub(
            dje, djen_id=i+1, cnj=f"0000{i+1}0020265100001",
            notion_page_id=f"page-{i+1}",
            payload={"tipoComunicacao": "Intimação",
                     "tipoDocumento": "Decisão",
                     "siglaTribunal": "TRT10"},
        )
    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page(f"page-{i+1}") for i in range(3)
    ]
    chamadas: list[tuple[int, int]] = []
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        on_progress=lambda p, t: chamadas.append((p, t)),
    )
    assert res.total_no_banco == 3
    assert chamadas == [(1, 3), (2, 3), (3, 3)]


def test_recalculo_limite_processa_subset() -> None:
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    for i in range(5):
        _inserir_pub(
            dje, djen_id=i+1, cnj=f"0000{i+1}0020265100001",
            notion_page_id=f"page-{i+1}",
            payload={"tipoComunicacao": "Intimação",
                     "tipoDocumento": "Decisão",
                     "siglaTribunal": "TRT10"},
        )
    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page(f"page-{i+1}") for i in range(5)
    ]
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        limite=2,
    )
    assert res.total_no_banco == 2
    assert res.total_processadas == 2


def test_resultado_dataclass_default() -> None:
    r = ResultadoRecalculo()
    assert r.total_no_banco == 0
    assert r.total_processadas == 0
    assert r.total_atualizadas == 0
    assert r.total_inalteradas == 0
    assert r.total_pulados_sem_notion == 0
    assert r.total_pulados_payload_invalido == 0
    assert r.total_erros == 0
    assert r.total_corpo_reescrito == 0
    assert r.total_corpo_falhou == 0
    assert r.erros == []
    assert r.diffs_amostra == []


# ---------------------------------------------------------------------------
# Round 11.2 — Helpers do backfill de corpo
# ---------------------------------------------------------------------------


def test_texto_paragraphs_concatena_paragraphs_em_ordem() -> None:
    blocos = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph("Primeiro paragrafo."),
        _bloco_paragraph("Segundo paragrafo."),
    ]
    out = _texto_paragraphs(blocos)
    assert out == "Primeiro paragrafo.\n\nSegundo paragrafo."


def test_texto_paragraphs_ignora_heading_e_quote() -> None:
    blocos = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph("Útil."),
        _bloco_heading2("Observações"),
        _bloco_quote("Sem observações automáticas pra esta publicação."),
    ]
    assert _texto_paragraphs(blocos) == "Útil."


def test_texto_paragraphs_lida_com_lista_vazia() -> None:
    assert _texto_paragraphs([]) == ""


def test_tem_placeholder_observacoes_detecta_quote_exato() -> None:
    blocos = [
        _bloco_heading2("Observações"),
        _bloco_quote(PLACEHOLDER_OBSERVACOES),
    ]
    assert _tem_placeholder_observacoes(blocos) is True


def test_tem_placeholder_observacoes_falso_para_quote_diferente() -> None:
    blocos = [_bloco_quote("Outra anotação qualquer.")]
    assert _tem_placeholder_observacoes(blocos) is False


def test_tem_placeholder_observacoes_falso_quando_nao_ha_quote() -> None:
    blocos = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph("Conteúdo."),
    ]
    assert _tem_placeholder_observacoes(blocos) is False


# ---------------------------------------------------------------------------
# Round 11.2 — _reescrever_corpo_pagina
# ---------------------------------------------------------------------------


def test_reescrever_corpo_apaga_e_anexa_em_chunks() -> None:
    """Apaga 1× por bloco existente; anexa em chunks de até 90."""
    client = MagicMock()
    blocos_atuais = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph("Velho 1."),
        _bloco_paragraph("Velho 2."),
    ]
    novos_blocos = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph("Novo 1."),
    ]
    _reescrever_corpo_pagina(
        client, "page-X",
        blocos_atuais=blocos_atuais,
        novos_blocos=novos_blocos,
    )
    assert client.delete_block.call_count == 3
    deleted_ids = [c[0][0] for c in client.delete_block.call_args_list]
    assert deleted_ids == [b["id"] for b in blocos_atuais]
    client.append_block_children.assert_called_once_with(
        "page-X", novos_blocos,
    )


def test_reescrever_corpo_chunking_com_mais_de_90_blocos() -> None:
    client = MagicMock()
    novos_blocos = [_bloco_paragraph(f"L{i}") for i in range(95)]
    _reescrever_corpo_pagina(
        client, "page-X", blocos_atuais=[], novos_blocos=novos_blocos,
    )
    assert client.append_block_children.call_count == 2
    chunk1 = client.append_block_children.call_args_list[0][0][1]
    chunk2 = client.append_block_children.call_args_list[1][0][1]
    assert len(chunk1) == 90
    assert len(chunk2) == 5


# ---------------------------------------------------------------------------
# Round 11.2 — recálculo end-to-end com backfill de corpo
# ---------------------------------------------------------------------------


def _payload_intimacao_curta(texto: str) -> dict[str, Any]:
    """Payload alinhado com ``test_recalculo_idempotente_quando_3_props_iguais``
    (provadamente sem alertas quando o processo cadastrado bate). Texto
    começa com ``INTIMAÇÃO Fica`` (pos 0 < ``CABECALHO_MIN_CHARS``) →
    ``limpar_cabecalho_trailer`` cai em fallback e devolve o texto cru,
    deixando a comparação previsível.
    """
    return {
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Decisão",
        "siglaTribunal": "TRT10",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
        "numeroprocessocommascara": "0001736-51.2016.5.10.0014",
        "nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
        "texto": texto,
    }


def _seed_processo_consistente(
    cache_conn: sqlite3.Connection,
    *,
    page_id: str = "proc-1",
    cnj: str = "0001736-51.2016.5.10.0014",
) -> None:
    """Cadastra um Processo cujo schema bate com ``_payload_intimacao_curta``
    — sem disparar alertas de Cidade/Vara/Tribunal/Instância/Fase. Mesmo
    layout usado em ``test_recalculo_idempotente_quando_3_props_iguais``.
    """
    _inserir_processo(
        cache_conn,
        page_id=page_id,
        cnj=cnj,
        extras={
            "tribunal": "TRT/10",
            "instancia": "1º grau",
            "vara": "14ª Vara do Trabalho de Brasília - DF",
            "cidade": "Brasília - DF",
            "fase": "Cognitiva",
            "natureza": "Trabalhista",
            "tipo_de_processo": "Principal",
        },
    )


def _setup_pub_e_processo_consistentes(
    texto: str = "INTIMAÇÃO Fica V. Sa. intimado do despacho.",
    *,
    djen_id: int = 1,
    notion_page_id: str = "page-1",
    cnj: str = "0001736-51.2016.5.10.0014",
    proc_page_id: str = "proc-1",
) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    """Cria DBs em memória + insere uma pub + processo cadastrado
    consistente (sem disparar nenhum alerta). Atalho para os testes do
    backfill de corpo focarem no que importa.
    """
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje, djen_id=djen_id, cnj=cnj,
        notion_page_id=notion_page_id,
        payload=_payload_intimacao_curta(texto),
    )
    _seed_processo_consistente(cache, page_id=proc_page_id, cnj=cnj)
    return dje, cache


def test_corpo_idempotente_quando_paragraphs_e_propriedades_batem() -> None:
    """Sem placeholder, paragraphs idênticos ao esperado, tags+texto
    sem diff → nem ``delete_block`` nem ``append_block_children`` é
    chamado e ``total_inalteradas`` incrementa.
    """
    texto = "INTIMAÇÃO Fica V. Sa. intimado do despacho."
    dje, cache = _setup_pub_e_processo_consistentes(texto)

    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page("page-1", texto=texto),
    ]
    client.list_all_block_children.return_value = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph(texto),
    ]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )

    assert res.total_processadas == 1
    assert res.total_atualizadas == 0
    assert res.total_inalteradas == 1
    assert res.total_corpo_reescrito == 0
    client.update_page.assert_not_called()
    client.delete_block.assert_not_called()
    client.append_block_children.assert_not_called()


def test_corpo_reescreve_quando_placeholder_observacoes_presente() -> None:
    """Texto da propriedade e dos paragraphs já está limpo, mas o corpo
    ainda termina com heading 'Observações' + quote placeholder
    legacy → reescreve só o corpo, sem chamar ``update_page``.
    """
    texto = "INTIMAÇÃO Fica V. Sa. intimado do despacho."
    dje, cache = _setup_pub_e_processo_consistentes(texto)

    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page("page-1", texto=texto),
    ]
    client.list_all_block_children.return_value = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph(texto),
        _bloco_heading2("Observações"),
        _bloco_quote(PLACEHOLDER_OBSERVACOES),
    ]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )

    assert res.total_atualizadas == 1
    assert res.total_corpo_reescrito == 1
    assert res.total_corpo_falhou == 0
    # Tags + texto não mudaram → nada de update_page.
    client.update_page.assert_not_called()
    # Apaga os 4 blocos atuais.
    assert client.delete_block.call_count == 4
    # Anexa os novos (heading + paragraph, sem heading "Observações").
    client.append_block_children.assert_called_once()
    page_arg, novos = client.append_block_children.call_args[0]
    assert page_arg == "page-1"
    types = [b["type"] for b in novos]
    assert types == ["heading_2", "paragraph"]
    assert all(b["type"] != "quote" for b in novos)


def test_corpo_reescreve_quando_paragraphs_diferem_do_esperado() -> None:
    """Corpo antigo tem texto cru pré-limpeza; novos blocos refletem
    texto limpo → reescreve.
    """
    texto_limpo = "INTIMAÇÃO Fica V. Sa. intimado do despacho."
    dje, cache = _setup_pub_e_processo_consistentes(texto_limpo)

    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page("page-1", texto=texto_limpo),
    ]
    client.list_all_block_children.return_value = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph(
            "PODER JUDICIÁRIO sujo... "
            "INTIMAÇÃO Fica V. Sa. intimado do despacho.",
        ),
    ]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )

    assert res.total_corpo_reescrito == 1
    assert client.delete_block.call_count == 2
    client.append_block_children.assert_called_once()


def test_corpo_dry_run_nao_chama_delete_nem_append() -> None:
    texto = "INTIMAÇÃO Fica V. Sa. intimado do despacho."
    dje, cache = _setup_pub_e_processo_consistentes(texto)

    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page("page-1", texto=texto),
    ]
    client.list_all_block_children.return_value = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph(texto),
        _bloco_heading2("Observações"),
        _bloco_quote(PLACEHOLDER_OBSERVACOES),
    ]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        dry_run=True,
    )

    assert res.total_corpo_reescrito == 1  # contado mesmo em dry-run
    client.delete_block.assert_not_called()
    client.append_block_children.assert_not_called()


def test_corpo_skip_corpo_pula_etapa_inteira() -> None:
    dje, cache = _setup_pub_e_processo_consistentes("Texto qualquer.")

    client = MagicMock()
    client.query_all.return_value = [_make_notion_page("page-1")]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        skip_corpo=True,
    )

    assert res.total_corpo_reescrito == 0
    client.list_all_block_children.assert_not_called()
    client.delete_block.assert_not_called()
    client.append_block_children.assert_not_called()


def test_corpo_falha_em_delete_loga_e_segue_pipeline() -> None:
    """Quando ``delete_block`` falha, conta em ``total_corpo_falhou`` e
    insere em ``erros``. As demais pubs do batch continuam sendo
    processadas.
    """
    texto = "INTIMAÇÃO Fica V. Sa. intimado do despacho."
    dje, cache = _setup_pub_e_processo_consistentes(texto)
    # Segunda pub do batch, processo próprio para evitar AC26.
    _inserir_pub(
        dje, djen_id=2, cnj="0001737-51.2016.5.10.0015",
        notion_page_id="page-2",
        payload={
            **_payload_intimacao_curta(texto),
            "numeroprocessocommascara": "0001737-51.2016.5.10.0015",
        },
    )
    _seed_processo_consistente(
        cache, page_id="proc-2", cnj="0001737-51.2016.5.10.0015",
    )

    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page("page-1", texto=texto),
        _make_notion_page("page-2", texto=texto),
    ]
    client.list_all_block_children.return_value = [
        _bloco_heading2("Texto da publicação"),
        _bloco_paragraph("texto antigo sujo"),
    ]
    client.delete_block.side_effect = [
        RuntimeError("boom"),  # falha no primeiro delete da page-1
        None, None,            # deletes da page-2
    ]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )

    assert res.total_processadas == 2
    assert res.total_corpo_falhou == 1
    assert res.total_corpo_reescrito == 1
    assert any(
        "reescrever_corpo" in e["error"] for e in res.erros
    )


# ---------------------------------------------------------------------------
# Round 11.3 — backfill da propriedade Texto em múltiplos rich_text
# ---------------------------------------------------------------------------


def test_texto_pub_longa_pre_round_11_3_vira_multiplos_chunks() -> None:
    """Pub longa que ANTES gravava 1 item ``rich_text`` truncado em
    ~2.000 chars com '[…]'. O backfill deve detectar diff (texto
    integral != texto truncado) e reescrever a propriedade ``Texto``
    com múltiplos itens preservando o conteúdo na íntegra.
    """
    cabecalho = "INTIMAÇÃO Fica V. Sa. intimado.\n\n"
    # ~5.400 chars de corpo — sobra muito do limite de 2.000.
    corpo = ("Lorem ipsum dolor sit amet. " * 200).rstrip()
    texto_integral = cabecalho + corpo

    dje, cache = _setup_pub_e_processo_consistentes(texto_integral)

    # Estado atual no Notion: 1 item truncado em ~2.000 chars com
    # marcador "[…]" (comportamento pré-Round 11.3).
    texto_truncado_atual = texto_integral[:1995] + " […]"
    page = _make_notion_page("page-1")
    page["properties"]["Texto"] = {
        "rich_text": [
            {
                "plain_text": texto_truncado_atual,
                "text": {"content": texto_truncado_atual},
            },
        ],
    }

    client = MagicMock()
    client.query_all.return_value = [page]
    # Corpo da página vazio simplifica o teste — a reescrita de blocos
    # já está coberta nos testes de Round 11.2.
    client.list_all_block_children.return_value = []

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )

    assert res.total_atualizadas == 1
    assert res.total_texto_limpo == 1
    # update_page foi chamado com Texto contendo múltiplos chunks.
    update_calls = [
        c for c in client.update_page.call_args_list
        if "Texto" in c[0][1]
    ]
    assert len(update_calls) == 1
    chunks = update_calls[0][0][1]["Texto"]["rich_text"]
    assert len(chunks) >= 2
    # Cada item respeita o limite duro da API Notion.
    for it in chunks:
        assert len(it["text"]["content"]) <= 2000
    # Reconstrução exata: texto integral aparece na propriedade.
    reconstruido = "".join(c["text"]["content"] for c in chunks)
    assert reconstruido == texto_integral


def test_texto_pub_longa_idempotente_se_chunks_atuais_batem() -> None:
    """Pub longa cujo estado atual no Notion JÁ está em múltiplos
    chunks reconstruindo o texto integral — sem diff, sem update da
    propriedade Texto.
    """
    cabecalho = "INTIMAÇÃO Fica V. Sa. intimado.\n\n"
    corpo = ("Lorem ipsum dolor sit amet. " * 200).rstrip()
    texto_integral = cabecalho + corpo

    dje, cache = _setup_pub_e_processo_consistentes(texto_integral)

    # Estado atual: chunks reproduzem texto_integral exatamente.
    from notion_rpadv.services.dje_text_pipeline import (
        chunkar_para_rich_text,
    )
    chunks_atuais = chunkar_para_rich_text(texto_integral)
    page = _make_notion_page("page-1")
    page["properties"]["Texto"] = {
        "rich_text": [
            {
                "plain_text": c["text"]["content"],
                "text": c["text"],
            }
            for c in chunks_atuais
        ],
    }

    client = MagicMock()
    client.query_all.return_value = [page]
    # Corpo da página simulado consistente com os blocos esperados —
    # texto_paragraphs do esperado bate com o atual.
    from notion_rpadv.services.dje_notion_mapper import (
        _build_corpo_blocks_full,
    )
    pub_payload = {
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Decisão",
        "siglaTribunal": "TRT10",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
        "numeroprocessocommascara": "0001736-51.2016.5.10.0014",
        "nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
        "texto": texto_integral,
    }
    blocos_esperados, _, _ = _build_corpo_blocks_full(
        pub_payload, tipo_documento_canonico="Decisão",
    )
    # Adapta os blocos ao formato com id (como vêm da API Notion).
    for i, b in enumerate(blocos_esperados):
        b["id"] = f"sim-blk-{i}"
    client.list_all_block_children.return_value = blocos_esperados

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )

    assert res.total_inalteradas == 1
    assert res.total_texto_limpo == 0
    assert res.total_corpo_reescrito == 0
    client.update_page.assert_not_called()
    client.delete_block.assert_not_called()
    client.append_block_children.assert_not_called()
