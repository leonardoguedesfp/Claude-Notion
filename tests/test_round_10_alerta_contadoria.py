"""Testes das 26 regras de Alerta contadoria do Round 10 — AC01 a AC26.

Cada regra tem ao menos um caso positivo e um negativo. Regras que
emitem a mesma tag_base (AC04+AC05, AC15+AC16, AC17+AC18) são testadas
separadamente — a deduplicação em :class:`VeredictoPub` é coberta em
``test_round_10_orquestrador.py``.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from notion_rpadv.services.dje_regras import alerta_contadoria as ac


# ---------------------------------------------------------------------------
# Fixture de cache.db em memória (pra AC04, AC05, AC06)
# ---------------------------------------------------------------------------


@pytest.fixture
def cache_conn_clientes() -> sqlite3.Connection:
    """Conexão SQLite em memória populada com 3 clientes do escritório
    (page_ids ``c1``, ``c2``, ``c3``).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE records (base TEXT, page_id TEXT, data_json TEXT)",
    )
    rows = [
        ("Clientes", "c1", json.dumps({"nome": "MARIA SILVA SANTOS"})),
        ("Clientes", "c2", json.dumps({"nome": "JOÃO PEREIRA"})),
        ("Clientes", "c3", json.dumps({"nome": "ANA D'ARC OLIVEIRA"})),
    ]
    conn.executemany(
        "INSERT INTO records (base, page_id, data_json) VALUES (?, ?, ?)",
        rows,
    )
    return conn


def _load_indice(cache_conn: sqlite3.Connection) -> dict[str, str]:
    from notion_rpadv.services.dje_regras._shared.matching_clientes import (
        carregar_indice_clientes,
    )
    return carregar_indice_clientes(cache_conn)


# ===========================================================================
# AC01 — Natureza × Tribunal
# ===========================================================================


def test_ac01_trt_em_processo_civel_dispara() -> None:
    pub = {"siglaTribunal": "TRT10"}
    proc = {"natureza": "Cível"}
    t = ac.regra_ac01_natureza_x_tribunal(pub, proc)
    assert t is not None
    assert t.regra == "AC01"
    assert t.tag == "Conferir natureza do processo - App"


def test_ac01_tjdft_em_processo_trabalhista_dispara() -> None:
    pub = {"siglaTribunal": "TJDFT"}
    proc = {"natureza": "Trabalhista"}
    assert ac.regra_ac01_natureza_x_tribunal(pub, proc) is not None


def test_ac01_stj_nao_dispara() -> None:
    """STJ julga ambas as naturezas — fora do escopo da regra."""
    pub = {"siglaTribunal": "STJ"}
    proc = {"natureza": "Cível"}
    assert ac.regra_ac01_natureza_x_tribunal(pub, proc) is None


def test_ac01_natureza_vazia_nao_dispara() -> None:
    pub = {"siglaTribunal": "TRT10"}
    proc = {"natureza": ""}
    assert ac.regra_ac01_natureza_x_tribunal(pub, proc) is None


# ===========================================================================
# AC02 — Natureza × Classe
# ===========================================================================


def test_ac02_classe_trabalhista_em_civel_dispara() -> None:
    pub = {"nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO"}
    proc = {"natureza": "Cível"}
    t = ac.regra_ac02_natureza_x_classe(pub, proc)
    assert t is not None
    assert t.regra == "AC02"


def test_ac02_classe_civel_em_trabalhista_dispara() -> None:
    pub = {"nomeClasse": "PROCEDIMENTO COMUM CÍVEL"}
    proc = {"natureza": "Trabalhista"}
    assert ac.regra_ac02_natureza_x_classe(pub, proc) is not None


def test_ac02_classe_ambigua_nao_dispara() -> None:
    """RECURSO ESPECIAL pode ser de qualquer natureza — herda do principal."""
    pub = {"nomeClasse": "RECURSO ESPECIAL"}
    proc = {"natureza": "Trabalhista"}
    assert ac.regra_ac02_natureza_x_classe(pub, proc) is None


# ===========================================================================
# AC03 — Recurso autônomo cadastrado como Principal
# ===========================================================================


def test_ac03_ai_strito_em_principal_dispara() -> None:
    pub = {"nomeClasse": "AGRAVO DE INSTRUMENTO"}
    proc = {"tipo_de_processo": "Principal"}
    t = ac.regra_ac03_recurso_autonomo_como_principal(pub, proc)
    assert t is not None
    assert t.regra == "AC03"
    assert t.tag == "Conferir tipo de processo - App"


def test_ac03_ai_em_resp_nao_dispara() -> None:
    """AI EM RESP não é AI strito sensu — tramita nos autos do principal."""
    pub = {"nomeClasse": "AGRAVO DE INSTRUMENTO EM RECURSO ESPECIAL"}
    proc = {"tipo_de_processo": "Principal"}
    assert ac.regra_ac03_recurso_autonomo_como_principal(pub, proc) is None


def test_ac03_ai_em_recurso_autonomo_nao_dispara() -> None:
    """Cadastro correto: AI strito + tipo Recurso autônomo."""
    pub = {"nomeClasse": "AGRAVO DE INSTRUMENTO"}
    proc = {"tipo_de_processo": "Recurso autônomo"}
    assert ac.regra_ac03_recurso_autonomo_como_principal(pub, proc) is None


# ===========================================================================
# AC04 / AC05 / AC06 — Cliente
# ===========================================================================


def test_ac04_cliente_pub_fora_da_relation_dispara(
    cache_conn_clientes: sqlite3.Connection,
) -> None:
    indice = _load_indice(cache_conn_clientes)
    pub = {"destinatarios": [{"nome": "MARIA SILVA SANTOS", "polo": "A"}]}
    proc = {"tipo_de_processo": "Principal", "clientes": []}
    t = ac.regra_ac04_cliente_fora_relation(pub, proc, indice_clientes=indice)
    assert t is not None
    assert t.regra == "AC04"
    assert t.tag == "Vincular cliente ao processo - App"


def test_ac04_cliente_ja_em_proc_clientes_nao_dispara(
    cache_conn_clientes: sqlite3.Connection,
) -> None:
    indice = _load_indice(cache_conn_clientes)
    pub = {"destinatarios": [{"nome": "MARIA SILVA SANTOS", "polo": "A"}]}
    proc = {"tipo_de_processo": "Principal", "clientes": ["c1"]}
    assert ac.regra_ac04_cliente_fora_relation(pub, proc, indice_clientes=indice) is None


def test_ac04_recurso_autonomo_nao_dispara(
    cache_conn_clientes: sqlite3.Connection,
) -> None:
    indice = _load_indice(cache_conn_clientes)
    pub = {"destinatarios": [{"nome": "MARIA SILVA SANTOS", "polo": "A"}]}
    proc = {"tipo_de_processo": "Recurso autônomo", "clientes": []}
    assert ac.regra_ac04_cliente_fora_relation(pub, proc, indice_clientes=indice) is None


def test_ac05_litisconsorcio_nao_refletido_dispara(
    cache_conn_clientes: sqlite3.Connection,
) -> None:
    indice = _load_indice(cache_conn_clientes)
    pub = {"destinatarios": [
        {"nome": "MARIA SILVA SANTOS", "polo": "A"},
        {"nome": "JOÃO PEREIRA SOUZA", "polo": "A"},
    ]}
    proc = {"tipo_de_processo": "Principal", "clientes": ["c1"]}
    t = ac.regra_ac05_litisconsorcio_nao_refletido(
        pub, proc, indice_clientes=indice,
    )
    assert t is not None
    assert t.regra == "AC05"


def test_ac06_cliente_cadastrado_nao_aparece_dispara(
    cache_conn_clientes: sqlite3.Connection,
) -> None:
    indice = _load_indice(cache_conn_clientes)
    pub = {"destinatarios": [{"nome": "OUTRO QUALQUER NAO CADASTRADO", "polo": "A"}]}
    proc = {"tipo_de_processo": "Principal", "clientes": ["c1"]}
    t = ac.regra_ac06_cliente_cadastrado_nao_aparece(
        pub, proc, indice_clientes=indice,
    )
    assert t is not None
    assert t.regra == "AC06"
    assert t.tag == "Conferir vinculação cliente-processo - App"


def test_ac06_cliente_cadastrado_aparece_nao_dispara(
    cache_conn_clientes: sqlite3.Connection,
) -> None:
    indice = _load_indice(cache_conn_clientes)
    pub = {"destinatarios": [{"nome": "MARIA SILVA SANTOS", "polo": "A"}]}
    proc = {"tipo_de_processo": "Principal", "clientes": ["c1"]}
    assert ac.regra_ac06_cliente_cadastrado_nao_aparece(
        pub, proc, indice_clientes=indice,
    ) is None


def test_ac06_match_tolerante_acento(
    cache_conn_clientes: sqlite3.Connection,
) -> None:
    """JOÃO no cadastro vs JOAO na pub deve casar (sem acento)."""
    indice = _load_indice(cache_conn_clientes)
    pub = {"destinatarios": [{"nome": "JOAO PEREIRA SOUZA", "polo": "A"}]}
    proc = {"tipo_de_processo": "Principal", "clientes": ["c2"]}
    assert ac.regra_ac06_cliente_cadastrado_nao_aparece(
        pub, proc, indice_clientes=indice,
    ) is None


# ===========================================================================
# AC07 / AC08 — Tribunal
# ===========================================================================


def test_ac07_trt18_dispara() -> None:
    pub = {"siglaTribunal": "TRT18"}
    t = ac.regra_ac07_tribunal_fora_vocabulario(pub, None)
    assert t is not None
    assert t.regra == "AC07"
    assert t.tag == "Tribunal fora do vocabulário - App"


def test_ac07_trt10_nao_dispara() -> None:
    pub = {"siglaTribunal": "TRT10"}
    assert ac.regra_ac07_tribunal_fora_vocabulario(pub, None) is None


def test_ac08_pub_trt_proc_tjdft_em_1grau_dispara() -> None:
    pub = {"siglaTribunal": "TRT10"}
    proc = {"instancia": "1º grau", "tribunal": "TJDFT"}
    t = ac.regra_ac08_conferir_tribunal_origem(pub, proc)
    assert t is not None
    assert t.regra == "AC08"


def test_ac08_acima_de_1grau_nao_dispara() -> None:
    pub = {"siglaTribunal": "STJ"}
    proc = {"instancia": "STJ", "tribunal": "TJDFT"}
    assert ac.regra_ac08_conferir_tribunal_origem(pub, proc) is None


def test_ac08_trt10_proc_trt10_canonico_nao_dispara() -> None:
    """Pub.TRT10 normaliza pra ``TRT/10``, igual ao Proc — não dispara."""
    pub = {"siglaTribunal": "TRT10"}
    proc = {"instancia": "1º grau", "tribunal": "TRT/10"}
    assert ac.regra_ac08_conferir_tribunal_origem(pub, proc) is None


# ===========================================================================
# AC09 — Capturar STJ
# ===========================================================================


def test_ac09_pub_stj_proc_sem_numero_dispara() -> None:
    pub = {"siglaTribunal": "STJ"}
    proc = {"numero_stj": ""}
    t = ac.regra_ac09_capturar_numeracao_stj(pub, proc)
    assert t is not None
    assert t.regra == "AC09"
    assert t.tag == "Capturar numeração STJ - App"


def test_ac09_proc_ja_tem_numero_nao_dispara() -> None:
    pub = {"siglaTribunal": "STJ"}
    proc = {"numero_stj": "REsp 12345/DF"}
    assert ac.regra_ac09_capturar_numeracao_stj(pub, proc) is None


def test_ac09_pub_tst_nao_dispara() -> None:
    """TST não atribui numeração nova — fora do escopo (Round 9)."""
    pub = {"siglaTribunal": "TST"}
    proc = {"numero_stj": ""}
    assert ac.regra_ac09_capturar_numeracao_stj(pub, proc) is None


# ===========================================================================
# AC10 / AC11 — Subida / Descida
# ===========================================================================


def test_ac10_pub_stj_proc_1grau_dispara() -> None:
    pub = {"siglaTribunal": "STJ"}
    proc = {"instancia": "1º grau"}
    t = ac.regra_ac10_subida_nao_detectada(pub, proc)
    assert t is not None
    assert t.regra == "AC10"
    assert t.tag == "Instância desatualizada (subida) - App"


def test_ac10_mesma_instancia_nao_dispara() -> None:
    pub = {"siglaTribunal": "STJ"}
    proc = {"instancia": "STJ"}
    assert ac.regra_ac10_subida_nao_detectada(pub, proc) is None


def test_ac11_descida_real_dispara() -> None:
    pub = {
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília",
        "nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
    }
    proc = {"instancia": "STJ"}
    t = ac.regra_ac11_descida_nao_detectada(pub, proc)
    assert t is not None
    assert t.regra == "AC11"


def test_ac11_cumprimento_de_sentenca_em_1grau_nao_dispara() -> None:
    """Cumprimento na origem é descida legítima — não dispara."""
    pub = {
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília",
        "nomeClasse": "CUMPRIMENTO DE SENTENÇA",
    }
    proc = {"instancia": "STJ"}
    assert ac.regra_ac11_descida_nao_detectada(pub, proc) is None


# ===========================================================================
# AC12 / AC13 / AC14 — Impossibilidades categóricas
# ===========================================================================


def test_ac12_acordao_em_1grau_dispara() -> None:
    pub = {"tipoDocumento": "Acórdão"}
    proc = {"instancia": "1º grau"}
    t = ac.regra_ac12_acordao_em_1grau(pub, proc)
    assert t is not None
    assert t.regra == "AC12"


def test_ac12_acordao_em_2grau_nao_dispara() -> None:
    pub = {"tipoDocumento": "Acórdão"}
    proc = {"instancia": "2º grau"}
    assert ac.regra_ac12_acordao_em_1grau(pub, proc) is None


def test_ac13_sentenca_em_2grau_dispara() -> None:
    pub = {"tipoDocumento": "Sentença"}
    proc = {"instancia": "2º grau"}
    t = ac.regra_ac13_sentenca_em_colegiado(pub, proc)
    assert t is not None
    assert t.regra == "AC13"


def test_ac13_sentenca_em_1grau_nao_dispara() -> None:
    pub = {"tipoDocumento": "Sentença"}
    proc = {"instancia": "1º grau"}
    assert ac.regra_ac13_sentenca_em_colegiado(pub, proc) is None


def test_ac14_pauta_em_1grau_dispara() -> None:
    pub = {"tipoDocumento": "Pauta de Julgamento"}
    proc = {"instancia": "1º grau"}
    t = ac.regra_ac14_pauta_em_1grau(pub, proc)
    assert t is not None
    assert t.regra == "AC14"


# ===========================================================================
# AC15 / AC16 — Cidade
# ===========================================================================


def test_ac15_cidade_extraivel_e_proc_vazia_dispara() -> None:
    pub = {"nomeOrgao": "14ª Vara do Trabalho de Brasília - DF"}
    proc = {"cidade": ""}
    t = ac.regra_ac15_cidade_faltando(pub, proc)
    assert t is not None
    assert t.regra == "AC15"
    assert t.tag == "Cidade desatualizada - App"


def test_ac15_proc_populada_nao_dispara() -> None:
    """AC15 cobre só vazio. AC16 cobre divergência."""
    pub = {"nomeOrgao": "14ª Vara do Trabalho de Brasília - DF"}
    proc = {"cidade": "Brasília"}
    assert ac.regra_ac15_cidade_faltando(pub, proc) is None


def test_ac16_cidade_divergente_dispara() -> None:
    pub = {"nomeOrgao": "14ª Vara do Trabalho de Goiânia - GO"}
    proc = {"cidade": "Brasília - DF"}
    t = ac.regra_ac16_cidade_divergente(pub, proc)
    assert t is not None
    assert t.regra == "AC16"


def test_ac16_mesma_cidade_com_uf_nao_dispara() -> None:
    """Tolera sufixo "- UF" simétrico nos dois lados."""
    pub = {"nomeOrgao": "14ª Vara do Trabalho de Brasília - DF"}
    proc = {"cidade": "Brasília - DF"}
    assert ac.regra_ac16_cidade_divergente(pub, proc) is None


def test_ac16_cidade_proc_vazia_nao_dispara() -> None:
    """Vazio é AC15; não duplicar."""
    pub = {"nomeOrgao": "14ª Vara do Trabalho de Brasília - DF"}
    proc = {"cidade": ""}
    assert ac.regra_ac16_cidade_divergente(pub, proc) is None


# ===========================================================================
# AC17 / AC18 — Vara (1º grau)
# ===========================================================================


def test_ac17_vara_proc_vazia_dispara() -> None:
    pub = {
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
    }
    proc = {"instancia": "1º grau", "vara": ""}
    t = ac.regra_ac17_vara_faltando(pub, proc)
    assert t is not None
    assert t.regra == "AC17"


def test_ac17_em_2grau_nao_dispara() -> None:
    pub = {"nomeOrgao": "14ª Vara do Trabalho"}
    proc = {"instancia": "2º grau", "vara": ""}
    assert ac.regra_ac17_vara_faltando(pub, proc) is None


def test_ac18_vara_divergente_dispara() -> None:
    pub = {
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
    }
    proc = {"instancia": "1º grau", "vara": "3ª Vara do Trabalho"}
    t = ac.regra_ac18_vara_divergente(pub, proc)
    assert t is not None
    assert t.regra == "AC18"


def test_ac18_mesma_vara_canonica_nao_dispara() -> None:
    pub = {
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
    }
    proc = {"instancia": "1º grau", "vara": "14ª Vara do Trabalho de Brasília"}
    assert ac.regra_ac18_vara_divergente(pub, proc) is None


def test_ac18_proc_com_ordinal_nu_dispara() -> None:
    """Cadastro com ordinal puro ("14") não bate canonicamente —
    força revisão pra migrar pro formato canônico."""
    pub = {
        "siglaTribunal": "TRT10",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
    }
    proc = {"instancia": "1º grau", "vara": "14"}
    t = ac.regra_ac18_vara_divergente(pub, proc)
    assert t is not None


# ===========================================================================
# AC19 / AC20 — Turma e Relator (≥ 2º grau)
# ===========================================================================


def test_ac19_turma_proc_vazia_dispara() -> None:
    pub = {
        "siglaTribunal": "TRT10",
        "nomeOrgao": "5ª Turma",
    }
    proc = {"instancia": "2º grau", "turma_no_2o_grau": ""}
    t = ac.regra_ac19_turma_desatualizada(pub, proc)
    assert t is not None
    assert t.regra == "AC19"


def test_ac19_turma_ordinal_diferente_dispara() -> None:
    pub = {
        "siglaTribunal": "TRT10",
        "nomeOrgao": "5ª Turma",
    }
    proc = {"instancia": "2º grau", "turma_no_2o_grau": "3ª Turma Cível"}
    assert ac.regra_ac19_turma_desatualizada(pub, proc) is not None


def test_ac19_turma_ordinal_igual_com_sufixo_diferente_nao_dispara() -> None:
    pub = {
        "siglaTribunal": "TRT10",
        "nomeOrgao": "5ª Turma",
    }
    proc = {"instancia": "2º grau", "turma_no_2o_grau": "5ª Turma Cível"}
    assert ac.regra_ac19_turma_desatualizada(pub, proc) is None


def test_ac19_turma_float_string_legacy_nao_dispara() -> None:
    """Cadastro com formato 5.0 (resíduo de migração antiga) — ordinal
    extraído é 5, igual ao Pub."""
    pub = {
        "siglaTribunal": "TRT10",
        "nomeOrgao": "5ª Turma",
    }
    proc = {"instancia": "2º grau", "turma_no_2o_grau": "5.0"}
    assert ac.regra_ac19_turma_desatualizada(pub, proc) is None


def test_ac20_relator_proc_vazia_dispara() -> None:
    pub = {
        "siglaTribunal": "TRT10",
        "nomeOrgao": "Desembargadora ELKE DORIS JUST",
    }
    proc = {"instancia": "2º grau", "relator_no_2o_grau": ""}
    t = ac.regra_ac20_relator_desatualizado(pub, proc)
    assert t is not None
    assert t.regra == "AC20"


def test_ac20_relator_simetrico_com_prefixo_nao_dispara() -> None:
    """Pub tem "Desembargadora X", Proc tem "Des. X" — após
    normalização ambos são "X"."""
    pub = {
        "siglaTribunal": "TRT10",
        "nomeOrgao": "Desembargadora ELKE DORIS JUST",
    }
    proc = {"instancia": "2º grau", "relator_no_2o_grau": "Des. ELKE DORIS JUST"}
    assert ac.regra_ac20_relator_desatualizado(pub, proc) is None


# ===========================================================================
# AC21 / AC22 — Fase desatualizada
# ===========================================================================


def test_ac21_cumprimento_em_proc_cognitivo_dispara() -> None:
    pub = {"nomeClasse": "CUMPRIMENTO DE SENTENÇA"}
    proc = {"fase": "Cognitiva"}
    t = ac.regra_ac21_fase_executiva(pub, proc)
    assert t is not None
    assert t.regra == "AC21"


def test_ac21_cumprimento_em_executivo_nao_dispara() -> None:
    pub = {"nomeClasse": "CUMPRIMENTO DE SENTENÇA"}
    proc = {"fase": "Executiva"}
    assert ac.regra_ac21_fase_executiva(pub, proc) is None


def test_ac22_liquidacao_em_proc_cognitivo_dispara() -> None:
    pub = {"nomeClasse": "LIQUIDAÇÃO POR ARBITRAMENTO"}
    proc = {"fase": "Cognitiva"}
    t = ac.regra_ac22_fase_liquidacao(pub, proc)
    assert t is not None
    assert t.regra == "AC22"


def test_ac22_liquidacao_em_proc_liquidando_nao_dispara() -> None:
    pub = {"nomeClasse": "LIQUIDAÇÃO POR ARBITRAMENTO"}
    proc = {"fase": "Liquidação pendente"}
    assert ac.regra_ac22_fase_liquidacao(pub, proc) is None


# ===========================================================================
# AC23 — Capturar data de distribuição
# ===========================================================================


def test_ac23_distribuicao_inicial_sem_data_dispara() -> None:
    pub = {
        "tipoDocumento": "Distribuição",
        "nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
    }
    proc = {"data_de_distribuicao": None}
    t = ac.regra_ac23_capturar_data_distribuicao(pub, proc)
    assert t is not None
    assert t.regra == "AC23"


def test_ac23_recurso_em_distribuicao_nao_dispara() -> None:
    pub = {
        "tipoDocumento": "Distribuição",
        "nomeClasse": "AGRAVO DE PETIÇÃO",
    }
    proc = {"data_de_distribuicao": None}
    assert ac.regra_ac23_capturar_data_distribuicao(pub, proc) is None


# ===========================================================================
# AC24 — Trânsito em julgado pendente
# ===========================================================================


def test_ac24_cumprimento_definitivo_sem_transito_dispara() -> None:
    pub = {"nomeClasse": "CUMPRIMENTO DE SENTENÇA"}
    proc: dict[str, Any] = {
        "data_do_transito_em_julgado_cognitiva": None,
        "data_do_transito_em_julgado_executiva": None,
    }
    t = ac.regra_ac24_transito_pendente(pub, proc)
    assert t is not None
    assert t.regra == "AC24"


def test_ac24_cumprimento_provisorio_nao_dispara() -> None:
    pub = {"nomeClasse": "CUMPRIMENTO PROVISÓRIO DE SENTENÇA"}
    proc: dict[str, Any] = {
        "data_do_transito_em_julgado_cognitiva": None,
        "data_do_transito_em_julgado_executiva": None,
    }
    assert ac.regra_ac24_transito_pendente(pub, proc) is None


def test_ac24_proc_com_transito_nao_dispara() -> None:
    pub = {"nomeClasse": "CUMPRIMENTO DE SENTENÇA"}
    proc = {"data_do_transito_em_julgado_cognitiva": "2025-01-01"}
    assert ac.regra_ac24_transito_pendente(pub, proc) is None


# ===========================================================================
# AC25 — Recurso autônomo sem processo pai
# ===========================================================================


def test_ac25_recurso_autonomo_sem_pai_dispara() -> None:
    proc = {"tipo_de_processo": "Recurso autônomo", "processo_pai": None}
    t = ac.regra_ac25_recurso_autonomo_sem_pai({}, proc)
    assert t is not None
    assert t.regra == "AC25"


def test_ac25_recurso_autonomo_com_pai_nao_dispara() -> None:
    proc = {
        "tipo_de_processo": "Recurso autônomo",
        "processo_pai": ["page-id-do-principal"],
    }
    assert ac.regra_ac25_recurso_autonomo_sem_pai({}, proc) is None


def test_ac25_principal_nao_dispara() -> None:
    proc = {"tipo_de_processo": "Principal", "processo_pai": None}
    assert ac.regra_ac25_recurso_autonomo_sem_pai({}, proc) is None


# ===========================================================================
# AC26 — Processo não cadastrado (filtra distribuições)
# ===========================================================================


def test_ac26_pub_sem_proc_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Despacho"}
    t = ac.regra_ac26_processo_nao_cadastrado(pub, processo_record=None)
    assert t is not None
    assert t.regra == "AC26"
    assert t.tag == "Processo não cadastrado - App"


def test_ac26_pub_com_proc_nao_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Despacho"}
    assert ac.regra_ac26_processo_nao_cadastrado(pub, processo_record={}) is None


def test_ac26_lista_de_distribuicao_sem_proc_nao_dispara() -> None:
    """TC01 já cobre — não duplicar."""
    pub = {"tipoComunicacao": "Lista de Distribuição", "tipoDocumento": ""}
    assert ac.regra_ac26_processo_nao_cadastrado(pub, processo_record=None) is None


def test_ac26_intimacao_distribuicao_sem_proc_nao_dispara() -> None:
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Distribuição"}
    assert ac.regra_ac26_processo_nao_cadastrado(pub, processo_record=None) is None
