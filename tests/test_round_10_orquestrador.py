"""Testes do orquestrador do Round 10 — :func:`aplicar_todas_regras`.

Foco em **coexistência** entre as 3 propriedades e dedup de tags
emitidas por regras diferentes mas com o mesmo ``tag_base``.

Casos sentinela obrigatórios (do prompt original):
- TC×AC: Lista de Distribuição com vara divergente
- TA×AC: Sentença em proc 2º grau
- AC×AC: STJ + proc 1º grau (AC09 + AC10)
- AC26: Pub sem proc, fora de distribuição
"""
from __future__ import annotations

from notion_rpadv.services.dje_regras import aplicar_todas_regras


def _bases_de(tags) -> list[str]:
    return [t.tag_base for t in tags]


def _regras_de(tags) -> list[str]:
    return [t.regra for t in tags]


# ---------------------------------------------------------------------------
# Coexistência TC × AC
# ---------------------------------------------------------------------------


def test_sentinela_distribuicao_com_vara_divergente() -> None:
    """Pub Lista de Distribuição cuja Pub.Órgão revele vara diferente
    da cadastrada → ``Tarefa contadoria`` contém TC01 E
    ``Alerta contadoria`` contém AC18."""
    pub = {
        "siglaTribunal": "TRT10",
        "tipoComunicacao": "Lista de Distribuição",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
        "nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
    }
    proc = {
        "instancia": "1º grau",
        "vara": "3ª Vara do Trabalho de Brasília",
        "cidade": "Brasília - DF",
        "tribunal": "TRT/10",
    }
    v = aplicar_todas_regras(pub, proc)
    assert "TC01" in _regras_de(v.tarefa_contadoria)
    assert "AC18" in _regras_de(v.alerta_contadoria)
    assert "Processo/recurso distribuído - App" in [
        t.tag for t in v.tarefa_contadoria
    ]
    assert "Vara desatualizada - App" in [t.tag for t in v.alerta_contadoria]


# ---------------------------------------------------------------------------
# Coexistência TA × AC
# ---------------------------------------------------------------------------


def test_sentinela_sentenca_em_proc_2grau() -> None:
    """Pub Sentença em Intimação + Proc.instancia=2º grau →
    ``Tarefa advogado`` contém TA01 E ``Alerta contadoria`` contém AC13."""
    pub = {
        "siglaTribunal": "TRT10",
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Sentença",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
        "nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
    }
    proc = {"instancia": "2º grau"}
    v = aplicar_todas_regras(pub, proc)
    assert "TA01" in _regras_de(v.tarefa_advogado)
    assert "AC13" in _regras_de(v.alerta_contadoria)


# ---------------------------------------------------------------------------
# Coexistência AC × AC (STJ + 1º grau)
# ---------------------------------------------------------------------------


def test_sentinela_pub_stj_proc_1grau() -> None:
    """Pub do STJ + processo cadastrado em 1º grau → AC09 (capturar
    numeração STJ) E AC10 (instância subiu)."""
    pub = {
        "siglaTribunal": "STJ",
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "Ministro Marco Aurélio",
        "nomeClasse": "RECURSO ESPECIAL",
    }
    proc = {"instancia": "1º grau", "numero_stj": ""}
    v = aplicar_todas_regras(pub, proc)
    regras = _regras_de(v.alerta_contadoria)
    assert "AC09" in regras
    assert "AC10" in regras


# ---------------------------------------------------------------------------
# Pub sem processo + não-distribuição → AC26
# ---------------------------------------------------------------------------


def test_sentinela_pub_sem_proc_intimacao_despacho() -> None:
    pub = {
        "siglaTribunal": "TRT10",
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Despacho",
    }
    v = aplicar_todas_regras(pub, processo_record=None)
    assert "AC26" in _regras_de(v.alerta_contadoria)
    assert "Processo não cadastrado - App" in [
        t.tag for t in v.alerta_contadoria
    ]


# ---------------------------------------------------------------------------
# Dedup — múltiplas regras emitindo a mesma tag_base
# ---------------------------------------------------------------------------


def test_dedup_cidade_desatualizada_so_aparece_uma_vez() -> None:
    """AC15 e AC16 podem ambos disparar em cenário transicional, mas
    a tag final no Notion é única (dedup por tag_base no
    VeredictoPub)."""
    # Esse cenário específico: Cidade extraída ≠ Proc.cidade populada.
    # Apenas AC16 dispara (AC15 cobre vazio). Confirma que não há
    # vazamento de duas instâncias.
    pub = {"nomeOrgao": "14ª Vara do Trabalho de Goiânia - GO"}
    proc = {"cidade": "Brasília - DF"}
    v = aplicar_todas_regras(pub, proc)
    bases = _bases_de(v.alerta_contadoria)
    assert bases.count("Cidade desatualizada") == 1


# ---------------------------------------------------------------------------
# Empty case — pub limpa em proc cadastrado bem
# ---------------------------------------------------------------------------


def test_pub_normal_sem_problemas_devolve_veredicto_vazio() -> None:
    """Pub de Despacho em Intimação, processo cadastrado coerente —
    nenhuma regra dispara."""
    pub = {
        "siglaTribunal": "TRT10",
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "14ª Vara do Trabalho de Brasília - DF",
        "nomeClasse": "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
    }
    proc = {
        "instancia": "1º grau",
        "vara": "14ª Vara do Trabalho",
        "cidade": "Brasília - DF",
        "tribunal": "TRT/10",
        "natureza": "Trabalhista",
        "tipo_de_processo": "Principal",
        "fase": "Cognitiva",
    }
    v = aplicar_todas_regras(pub, proc)
    assert v.tarefa_advogado == []
    assert v.tarefa_contadoria == []
    assert v.alerta_contadoria == []


def test_tags_por_propriedade_pronto_pra_payload() -> None:
    """O método utilitário entrega listas de strings com sufixo já
    aplicado — pronto pra serializar em multi_select."""
    pub = {"tipoComunicacao": "Intimação", "tipoDocumento": "Sentença"}
    v = aplicar_todas_regras(pub, processo_record=None)
    pacote = v.tags_por_propriedade()
    assert pacote["Tarefa advogado"] == ["Analisar sentença - App"]
    assert pacote["Tarefa contadoria"] == []
    # AC26 dispara porque processo não cadastrado e não é distribuição
    assert "Processo não cadastrado - App" in pacote["Alerta contadoria"]
