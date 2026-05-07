"""Round 8 — testes do serviço ``dje_recalcular_alertas``.

Cobertura:
- Decodificação de alertas atuais a partir de Page do Notion.
- Iteração só sobre publicações ``notion_page_id`` populado e ≠ SKIPPED.
- Idempotência: ``update_page`` é chamado APENAS quando os alertas
  computados diferem dos atuais.
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
    PROP_ALERTA_CONTADORIA,
    ResultadoRecalculo,
    _alertas_atuais_de_page,
    _multi_select_payload,
    recalcular_alertas_publicacoes,
)


# ---------------------------------------------------------------------------
# Fixtures helper
# ---------------------------------------------------------------------------


def _abrir_dje_db_em_memoria() -> sqlite3.Connection:
    """Cria um leitor_dje.db em memória com a tabela ``publicacoes``
    mínima necessária pelo serviço."""
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
    """Cria um cache.db em memória com a tabela ``records`` mínima."""
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
    page_id: str, alertas: list[str],
) -> dict[str, Any]:
    """Mock no formato Page Notion com a propriedade Alerta contadoria."""
    return {
        "id": page_id,
        "properties": {
            PROP_ALERTA_CONTADORIA: {
                "multi_select": [{"name": a} for a in alertas],
            },
        },
    }


# ---------------------------------------------------------------------------
# Testes de helpers
# ---------------------------------------------------------------------------


def test_alertas_atuais_de_page_extrai_multi_select() -> None:
    page = _make_notion_page(
        "p1", ["Vara desatualizada", "Conferir tribunal de origem"],
    )
    assert _alertas_atuais_de_page(page) == [
        "Vara desatualizada", "Conferir tribunal de origem",
    ]


def test_alertas_atuais_de_page_propriedade_ausente_retorna_vazio() -> None:
    page = {"id": "p1", "properties": {}}
    assert _alertas_atuais_de_page(page) == []


def test_alertas_atuais_de_page_multi_select_vazio() -> None:
    page = _make_notion_page("p1", [])
    assert _alertas_atuais_de_page(page) == []


def test_multi_select_payload_formato_notion() -> None:
    payload = _multi_select_payload(["A", "B"])
    assert payload == {
        "multi_select": [{"name": "A"}, {"name": "B"}],
    }


# ---------------------------------------------------------------------------
# Testes do recalculo end-to-end (com cliente Notion mockado)
# ---------------------------------------------------------------------------


def test_recalculo_idempotente_quando_alertas_iguais() -> None:
    """Pub com alertas computados == atuais no Notion → NÃO chama
    update_page. ``total_inalteradas`` reflete."""
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
            "cidade": "Brasília",
            "fase": "Executiva",
            "natureza": "Trabalhista",
            "tipo_de_processo": "Principal",
            "partes_adversas": ["Banco do Brasil"],
        },
    )

    client = MagicMock()
    # query_all retorna a página com os MESMOS alertas que serão
    # computados (lista vazia neste caso — pub é Intimação Decisão
    # sem nada que dispare).
    client.query_all.return_value = [_make_notion_page("page-1", [])]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )

    assert res.total_no_banco == 1
    assert res.total_processadas == 1
    assert res.total_atualizadas == 0
    assert res.total_inalteradas == 1
    client.update_page.assert_not_called()


def test_recalculo_atualiza_quando_diff() -> None:
    """Pub onde os alertas atuais diferem dos computados → chama
    update_page com a propriedade correta."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()

    # Pub com classe AGRAVO DE PETIÇÃO → fase implicada Executiva
    # Proc.fase = Cognitiva → dispara Regra 26 (Fase desatualizada
    # executiva).
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
        cache,
        page_id="proc-1",
        cnj="0001736-51.2016.5.10.0014",
        extras={
            "tribunal": "TRT/10",
            "instancia": "1º grau",
            "vara": "14ª Vara do Trabalho de Brasília - DF",
            "fase": "Cognitiva",
            "data_do_transito_em_julgado_cognitiva": "2024-01-01",
        },
    )

    client = MagicMock()
    # No Notion atualmente: sem alertas. Computado vai trazer
    # "Fase desatualizada (executiva)".
    client.query_all.return_value = [_make_notion_page("page-1", [])]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )

    assert res.total_atualizadas == 1
    assert res.total_inalteradas == 0
    client.update_page.assert_called_once()
    page_id_arg, props_arg = client.update_page.call_args[0]
    assert page_id_arg == "page-1"
    assert PROP_ALERTA_CONTADORIA in props_arg
    nomes = [
        it["name"]
        for it in props_arg[PROP_ALERTA_CONTADORIA]["multi_select"]
    ]
    assert "Fase desatualizada (executiva)" in nomes


def test_recalculo_dry_run_nao_chama_update() -> None:
    """``dry_run=True`` calcula diff mas não escreve no Notion."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje,
        djen_id=1,
        cnj="0000001-00.2026.5.10.0001",
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
        cache,
        page_id="proc-1",
        cnj="0000001-00.2026.5.10.0001",
        extras={"instancia": "1º grau", "fase": "Cognitiva",
                "data_do_transito_em_julgado_cognitiva": "2024-01-01"},
    )
    client = MagicMock()
    client.query_all.return_value = [_make_notion_page("page-1", [])]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        dry_run=True,
    )

    assert res.total_atualizadas == 1  # "seria atualizada"
    client.update_page.assert_not_called()


def test_recalculo_always_update_escreve_mesmo_sem_diff() -> None:
    """``always_update=True`` ignora idempotência e força escrita."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje,
        djen_id=1,
        cnj="0000001-00.2026.5.10.0001",
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
        cache, page_id="proc-1",
        cnj="0000001-00.2026.5.10.0001",
        extras={"instancia": "1º grau",
                "vara": "1ª Vara do Trabalho de Brasília - DF"},
    )
    client = MagicMock()
    client.query_all.return_value = [_make_notion_page("page-1", [])]

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        always_update=True,
    )

    # Os alertas computados são os mesmos que os atuais (ambos vazios
    # nesse caso) — sem ``always_update`` seria idempotente; com a
    # flag, força escrita mesmo assim.
    assert res.total_atualizadas == 1
    client.update_page.assert_called_once()


def test_recalculo_pula_pubs_skipped() -> None:
    """Pubs com ``notion_page_id = 'SKIPPED'`` ficam fora do iterador."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje, djen_id=1, cnj="0001-00.2026.5.10.0001",
        notion_page_id=NOTION_SKIPPED_SENTINEL,
        payload={"tipoComunicacao": "Intimação"},
    )
    _inserir_pub(
        dje, djen_id=2, cnj="0002-00.2026.5.10.0002",
        notion_page_id=None,  # pendente, ainda não enviada
        payload={"tipoComunicacao": "Intimação"},
    )

    client = MagicMock()
    client.query_all.return_value = []

    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )
    assert res.total_no_banco == 0
    assert res.total_processadas == 0


def test_recalculo_pula_payload_invalido() -> None:
    """Linhas com ``payload_json`` corrompido contam mas não derrubam
    o pipeline."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    # Insere payload inválido manualmente
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
    client.query_all.return_value = [_make_notion_page("page-1", [])]
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )
    assert res.total_pulados_payload_invalido == 1
    assert res.total_processadas == 0
    client.update_page.assert_not_called()


def test_recalculo_pula_pub_sem_correspondencia_no_notion() -> None:
    """Pub no banco com page_id que não aparece no query_all (page
    apagada externamente). Conta como 'pulada sem notion'."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje, djen_id=1, cnj="0000001-00.2026.5.10.0001",
        notion_page_id="page-fantasma",
        payload={
            "tipoComunicacao": "Intimação",
            "tipoDocumento": "Decisão",
            "siglaTribunal": "TRT10",
        },
    )
    client = MagicMock()
    client.query_all.return_value = []  # Notion não retorna nada
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )
    assert res.total_pulados_sem_notion == 1
    client.update_page.assert_not_called()


def test_recalculo_diff_amostrado_no_resultado() -> None:
    """Quando há diff, o resultado inclui amostra com antes/depois."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    _inserir_pub(
        dje, djen_id=1, cnj="0000001-00.2026.5.10.0001",
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
        cache, page_id="proc-1", cnj="0000001-00.2026.5.10.0001",
        extras={"instancia": "1º grau",
                "vara": "1ª Vara do Trabalho de Brasília - DF",
                "fase": "Cognitiva",
                "data_do_transito_em_julgado_cognitiva": "2024-01-01"},
    )
    client = MagicMock()
    # Estado atual no Notion tem alerta antigo "Vara desatualizada"
    # (falso-positivo da regra antiga). Após recálculo (Round 8):
    # alerta correto é "Fase desatualizada (executiva)".
    client.query_all.return_value = [
        _make_notion_page("page-1", ["Vara desatualizada"]),
    ]
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
    )
    assert res.total_atualizadas == 1
    assert len(res.diffs_amostra) == 1
    diff = res.diffs_amostra[0]
    assert diff["page_id"] == "page-1"
    assert "Vara desatualizada" in diff["removidos"]
    assert "Fase desatualizada (executiva)" in diff["adicionados"]


def test_recalculo_callback_progresso_chamado() -> None:
    """Callback ``on_progress`` é invocado a cada iteração."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    for i in range(3):
        _inserir_pub(
            dje, djen_id=i+1, cnj=f"0000{i+1}-00.2026.5.10.0001",
            notion_page_id=f"page-{i+1}",
            payload={"tipoComunicacao": "Intimação",
                     "tipoDocumento": "Decisão",
                     "siglaTribunal": "TRT10"},
        )
    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page(f"page-{i+1}", []) for i in range(3)
    ]
    chamadas: list[tuple[int, int]] = []
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        on_progress=lambda p, t: chamadas.append((p, t)),
    )
    assert res.total_no_banco == 3
    assert chamadas == [(1, 3), (2, 3), (3, 3)]


def test_recalculo_limite_processa_subset() -> None:
    """``limite=N`` processa só as N primeiras publicações."""
    dje = _abrir_dje_db_em_memoria()
    cache = _abrir_cache_db_em_memoria()
    for i in range(5):
        _inserir_pub(
            dje, djen_id=i+1, cnj=f"0000{i+1}-00.2026.5.10.0001",
            notion_page_id=f"page-{i+1}",
            payload={"tipoComunicacao": "Intimação",
                     "tipoDocumento": "Decisão",
                     "siglaTribunal": "TRT10"},
        )
    client = MagicMock()
    client.query_all.return_value = [
        _make_notion_page(f"page-{i+1}", []) for i in range(5)
    ]
    res = recalcular_alertas_publicacoes(
        notion_client=client, dje_conn=dje, cache_conn=cache,
        limite=2,
    )
    assert res.total_no_banco == 2
    assert res.total_processadas == 2


def test_recalculo_resultado_dataclass_default() -> None:
    """``ResultadoRecalculo`` tem todos os contadores em zero por
    default e listas vazias."""
    r = ResultadoRecalculo()
    assert r.total_no_banco == 0
    assert r.total_processadas == 0
    assert r.total_atualizadas == 0
    assert r.total_inalteradas == 0
    assert r.total_pulados_sem_notion == 0
    assert r.total_pulados_payload_invalido == 0
    assert r.total_erros == 0
    assert r.erros == []
    assert r.diffs_amostra == []
