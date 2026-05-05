"""Testes do ``notion_rpadv.services.datajud_enricher``: roteamento de
endpoints, regras de origem por propriedade, heurísticas de status/fase/
trânsito, comportamento tolerante (Dados parciais, Não encontrado, Erro).

Sem chamada real à API: ``consultar_multi`` é mockado via
``MagicMock(spec=DataJudClient)``. Fixtures JSON em
``tests/fixtures/datajud/`` simulam respostas de cada endpoint.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from notion_rpadv.services.datajud_client import DataJudAPIError, DataJudClient
from notion_rpadv.services.datajud_enricher import (
    DIAG_NAO_ENCONTRADO,
    DIAG_OK,
    DIAG_PARCIAL,
    DIAG_STF,
    DIAG_TRIBUNAL_NS,
    FASE_COGNITIVA,
    FASE_EXECUTIVA,
    INSTANCIA_2G,
    INSTANCIA_TST,
    REGRAS_ORIGEM,
    STATUS_ARQUIVADO,
    STATUS_ARQUIVADO_PROVISORIAMENTE,
    STATUS_ATIVO,
    derivar_relator,
    derivar_status,
    derivar_transito_cognitiva,
    derivar_turma_g2,
    derivar_vara,
    endpoints_candidatos,
    enriquecer,
)


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------


_FIXTURES_DIR: Path = (
    Path(__file__).resolve().parent / "fixtures" / "datajud"
)


def _load_fixture(name: str) -> dict[str, list[dict[str, Any]]]:
    """Carrega fixture JSON (formato dict[endpoint, list[_source]])."""
    raw = json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))
    # Remove eventual chave "_comment" sem afetar tipagem
    return {k: v for k, v in raw.items() if k != "_comment"}


def _mock_client(
    consulta_result: dict[str, list[dict[str, Any]]] | None = None,
    raises: Exception | None = None,
) -> MagicMock:
    """Cria mock de ``DataJudClient`` com ``consultar_multi`` pré-config.

    Quando ``raises`` for setado, qualquer chamada de ``consultar_multi``
    levanta a exceção (testa caminho ``Erro: <detalhe>`` do enricher).
    Caso contrário, devolve apenas as keys da fixture que foram pedidas
    (espelha o comportamento real).
    """
    client = MagicMock(spec=DataJudClient)
    if raises is not None:
        client.consultar_multi.side_effect = raises
    else:
        result_full = consulta_result or {}

        def _fake(cnj: str, eps: list[str], **_: Any) -> dict[str, list[dict[str, Any]]]:
            return {ep: result_full.get(ep, []) for ep in eps}

        client.consultar_multi.side_effect = _fake
    return client


def _processo(
    *, tribunal: str, instancia: str, cnj: str = "0001234-56.2024.5.10.0013",
    **extra: Any,
) -> dict[str, Any]:
    """Constrói dict de processo do cache no formato consumido por ``enriquecer``."""
    base: dict[str, Any] = {
        "Número do processo": cnj,
        "Tribunal":           tribunal,
        "Instância":          instancia,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# 1) endpoints_candidatos — para cada instância
# ---------------------------------------------------------------------------


def test_endpoints_candidatos_para_cada_instancia() -> None:
    """Mapeamento canônico de instância para endpoints candidatos."""
    # 1º grau no TJDFT → [tjdft]
    assert endpoints_candidatos(_processo(tribunal="TJDFT", instancia="1º grau")) == ["tjdft"]
    # 2º grau no TRT/10 → [trt10]
    assert endpoints_candidatos(_processo(tribunal="TRT/10", instancia="2º grau")) == ["trt10"]
    # TST a partir do TRT/10 → [trt10, tst]
    assert endpoints_candidatos(_processo(tribunal="TRT/10", instancia="TST")) == ["trt10", "tst"]
    # TST a partir do TST (dedup) → [tst]
    assert endpoints_candidatos(_processo(tribunal="TST", instancia="TST")) == ["tst"]
    # STJ a partir do TJDFT → [tjdft, stj]
    assert endpoints_candidatos(_processo(tribunal="TJDFT", instancia="STJ")) == ["tjdft", "stj"]
    # STJ a partir do STJ (dedup) → [stj]
    assert endpoints_candidatos(_processo(tribunal="STJ", instancia="STJ")) == ["stj"]


# ---------------------------------------------------------------------------
# 2) endpoints_candidatos — Outro retorna vazio
# ---------------------------------------------------------------------------


def test_endpoints_candidatos_outro_retorna_vazio() -> None:
    """Tribunal == 'Outro' (ou string vazia, ou não mapeado) → []."""
    assert endpoints_candidatos(_processo(tribunal="Outro", instancia="1º grau")) == []
    assert endpoints_candidatos(_processo(tribunal="", instancia="1º grau")) == []
    assert endpoints_candidatos(_processo(tribunal="TRIBUNAL_INEXISTENTE", instancia="1º grau")) == []


# ---------------------------------------------------------------------------
# 3) endpoints_candidatos — STF retorna vazio
# ---------------------------------------------------------------------------


def test_endpoints_candidatos_stf_retorna_vazio() -> None:
    """STF não tem endpoint público — sempre []."""
    assert endpoints_candidatos(_processo(tribunal="TJDFT", instancia="STF")) == []
    assert endpoints_candidatos(_processo(tribunal="STF",   instancia="STF")) == []


# ---------------------------------------------------------------------------
# 4) Tribunal vem do menor grau (com mapeamento DataJud → Notion)
# ---------------------------------------------------------------------------


def test_tribunal_vem_do_menor_grau() -> None:
    """Em processo com G1 e G2, Tribunal sugerido vem do G1.

    Memória do projeto: 'Tribunal sempre registra o juízo de origem
    de primeiro grau e nunca muda'. O mapeamento DataJud→Notion
    converte 'TRT10' (sem barra) para 'TRT/10' (com barra).
    """
    result = _load_fixture("trt10_g2_subiu_tst.json")
    client = _mock_client(consulta_result=result)
    res = enriquecer(
        _processo(tribunal="TRT/10", instancia="TST"),
        client=client,
    )
    # G1 do trt10 tem tribunal="TRT10" → mapeado pra "TRT/10"
    assert res.propriedades_sugeridas["Tribunal"] == "TRT/10"


# ---------------------------------------------------------------------------
# 5) Status vem do maior grau
# ---------------------------------------------------------------------------


def test_status_vem_do_maior_grau() -> None:
    """Status aplicado sobre movimentos do MAIOR grau encontrado.

    No TRT10 com G1+G2 e GS no TST, os movimentos do GS (TST) são os
    consumidos por derivar_status. Como o fixture não tem mov. de
    arquivamento/sobrestamento no GS, status = Ativo (mesmo que G1
    tenha trânsito em julgado registrado).
    """
    result = _load_fixture("trt10_g2_subiu_tst.json")
    client = _mock_client(consulta_result=result)
    res = enriquecer(
        _processo(tribunal="TRT/10", instancia="TST"),
        client=client,
    )
    # GS no TST é o maior grau; sem arquivamento/sobrestamento → Ativo
    assert res.propriedades_sugeridas["Status"] == STATUS_ATIVO


def test_status_arquivado_quando_maior_grau_tem_baixa_definitiva() -> None:
    """G1 do TJDFT com mov. 246 (Arquivamento Definitivo) e 22
    (Baixa Definitiva) → status 'Arquivado'."""
    result = _load_fixture("tjdft_g1_arquivado.json")
    client = _mock_client(consulta_result=result)
    res = enriquecer(
        _processo(tribunal="TJDFT", instancia="1º grau"),
        client=client,
    )
    assert res.propriedades_sugeridas["Status"] == STATUS_ARQUIVADO


# ---------------------------------------------------------------------------
# 6) Trânsito cognitiva: menor grau com fallback ao maior
# ---------------------------------------------------------------------------


def test_transito_cognitiva_menor_grau_com_fallback() -> None:
    """Mov. 11009 (Trânsito) presente no G1 → derivado direto.
    Quando ausente no G1, fallback pro grau maior."""
    # Caso 1: trânsito no menor grau
    result = _load_fixture("trt10_g2_subiu_tst.json")
    client = _mock_client(consulta_result=result)
    res = enriquecer(
        _processo(tribunal="TRT/10", instancia="TST"),
        client=client,
    )
    # Fixture trt10_g2_subiu_tst.json tem mov. 11009 no G1 (2024-08-15)
    assert res.propriedades_sugeridas["Data do trânsito em julgado (cognitiva)"] == "2024-08-15"

    # Caso 2: helper unitário com fallback
    movs_menor: list[dict[str, Any]] = [
        {"codigo": 26, "dataHora": "2023-01-01T08:00:00.000Z"},
    ]
    movs_maior: list[dict[str, Any]] = [
        {"codigo": 11009, "dataHora": "2024-09-30T18:00:00.000Z"},
    ]
    assert derivar_transito_cognitiva(movs_menor, movs_maior) == "2024-09-30"

    # Caso 3: ausente em ambos → None
    assert derivar_transito_cognitiva(
        [{"codigo": 26}], [{"codigo": 219}],
    ) is None


# ---------------------------------------------------------------------------
# 7) Relator marcado como baixa confiança na tabela de regras
# ---------------------------------------------------------------------------


def test_relator_marcado_baixa_confianca() -> None:
    """REGRAS_ORIGEM lista os 2 relatores com confianca == 'baixa';
    todas as outras 12 propriedades têm confianca == 'alta'."""
    baixa = {r.nome_notion for r in REGRAS_ORIGEM if r.confianca == "baixa"}
    assert baixa == {"Relator no 2º grau", "Relator no STJ/TST"}

    alta = {r.nome_notion for r in REGRAS_ORIGEM if r.confianca == "alta"}
    assert len(alta) == 12
    assert "Status" in alta
    assert "Tribunal" in alta


# ---------------------------------------------------------------------------
# 8) Dados parciais: 1 endpoint com hit, outro vazio
# ---------------------------------------------------------------------------


def test_dados_parciais_quando_um_endpoint_vazio() -> None:
    """Processo no TRT/10 instância TST: consulta trt10 + tst.
    trt10 retorna G1+G2; tst retorna []. Diagnóstico = Dados parciais.
    Ainda assim o enricher devolve as propriedades do que conseguiu."""
    result = _load_fixture("trt10_g2_subiu_tst.json")
    # Zera o tst → endpoint consultado mas sem hit
    result["tst"] = []
    client = _mock_client(consulta_result=result)
    res = enriquecer(
        _processo(tribunal="TRT/10", instancia="TST"),
        client=client,
    )
    assert res.diagnostico == DIAG_PARCIAL
    # trt10 deu hit: fontes inclui apenas trt10
    assert res.fontes_tribunal == ["trt10"]
    # Mas propriedades derivadas do menor/maior grau encontrado (G1, G2)
    assert res.propriedades_sugeridas["Tribunal"] == "TRT/10"
    assert res.propriedades_sugeridas["Instância"] == INSTANCIA_2G  # G2 é o maior disponível
    # Sem GS de stj/tst → Número STJ/TST e Turma STJ/TST ficam None
    assert res.propriedades_sugeridas["Número STJ/TST"] is None
    assert res.propriedades_sugeridas["Turma no STJ/TST"] is None


# ---------------------------------------------------------------------------
# 9) Não encontrado quando todos endpoints retornam vazio
# ---------------------------------------------------------------------------


def test_nao_encontrado_quando_todos_endpoints_vazios() -> None:
    """Todos os endpoints retornam lista vazia → Não encontrado.
    Propriedades vazias (todas as 14 keys com None)."""
    result = _load_fixture("nao_encontrado.json")  # {"trt10": []}
    client = _mock_client(consulta_result=result)
    res = enriquecer(
        _processo(tribunal="TRT/10", instancia="1º grau"),
        client=client,
    )
    assert res.diagnostico == DIAG_NAO_ENCONTRADO
    assert res.fontes_tribunal == []
    assert all(v is None for v in res.propriedades_sugeridas.values())
    # Mas todas as 14 keys estão presentes (caller pode iterar com confiança)
    assert len(res.propriedades_sugeridas) == 14


# ---------------------------------------------------------------------------
# 10) Processo que subiu ao TST consulta 2 endpoints
# ---------------------------------------------------------------------------


def test_processo_que_subiu_ao_tst_consulta_dois_endpoints() -> None:
    """Tribunal=TRT/10 + Instância=TST → consultar_multi recebe ['trt10', 'tst'].
    Diagnóstico OK quando ambos têm hit. Instância no resultado = TST
    (vem do GS no endpoint tst)."""
    result = _load_fixture("trt10_g2_subiu_tst.json")
    client = _mock_client(consulta_result=result)
    res = enriquecer(
        _processo(tribunal="TRT/10", instancia="TST"),
        client=client,
    )
    # Verifica que os 2 endpoints foram consultados
    client.consultar_multi.assert_called_once()
    args = client.consultar_multi.call_args
    eps_chamados = args.args[1]
    assert eps_chamados == ["trt10", "tst"]

    # E o diagnóstico é OK porque ambos tiveram hit
    assert res.diagnostico == DIAG_OK
    assert set(res.fontes_tribunal) == {"trt10", "tst"}
    # Instância derivada do GS no endpoint tst → "TST"
    assert res.propriedades_sugeridas["Instância"] == INSTANCIA_TST


# ---------------------------------------------------------------------------
# 11) Status "Arquivado provisoriamente (tema 955)" — sentinela
# ---------------------------------------------------------------------------


def test_status_arquivado_provisoriamente_tema_955_ainda_funciona() -> None:
    """Heurística sentinela: sobrestamento (mov. 12092) sem
    levantamento (mov. 11458) posterior → Status =
    'Arquivado provisoriamente (tema 955)'.

    Esta heurística continua válida no campo Status mesmo sem o
    checkbox 'Tema 955 — Sobrestado' no escopo da Fase 1.
    """
    result = _load_fixture("tjdft_g1_tema_955.json")
    client = _mock_client(consulta_result=result)
    res = enriquecer(
        _processo(tribunal="TJDFT", instancia="1º grau"),
        client=client,
    )
    assert res.propriedades_sugeridas["Status"] == STATUS_ARQUIVADO_PROVISORIAMENTE


# ---------------------------------------------------------------------------
# Testes auxiliares — caminhos de erro e helpers individuais
# ---------------------------------------------------------------------------


def test_diagnostico_stf_quando_instancia_stf() -> None:
    """STF como instância → 'STF não coberto', sem chamada HTTP."""
    client = _mock_client()
    res = enriquecer(
        _processo(tribunal="TJDFT", instancia="STF"),
        client=client,
    )
    assert res.diagnostico == DIAG_STF
    client.consultar_multi.assert_not_called()


def test_diagnostico_tribunal_nao_suportado_quando_outro() -> None:
    """Tribunal=Outro → 'Tribunal não suportado', sem chamada HTTP."""
    client = _mock_client()
    res = enriquecer(
        _processo(tribunal="Outro", instancia="1º grau"),
        client=client,
    )
    assert res.diagnostico == DIAG_TRIBUNAL_NS
    client.consultar_multi.assert_not_called()


def test_diagnostico_erro_quando_client_levanta_excecao() -> None:
    """DataJudAPIError → diagnóstico 'Erro: <detalhe>' truncado a 120 chars."""
    client = _mock_client(raises=DataJudAPIError(503, "serviço indisponível"))
    res = enriquecer(
        _processo(tribunal="TJDFT", instancia="1º grau"),
        client=client,
    )
    assert res.diagnostico.startswith("Erro:")
    assert "503" in res.diagnostico
    assert all(v is None for v in res.propriedades_sugeridas.values())


def test_diagnostico_ok_no_caso_simples() -> None:
    """1 endpoint, 1 grau, hit → OK."""
    result = _load_fixture("trt10_g1_simples.json")
    client = _mock_client(consulta_result=result)
    res = enriquecer(
        _processo(tribunal="TRT/10", instancia="1º grau"),
        client=client,
    )
    assert res.diagnostico == DIAG_OK
    assert res.propriedades_sugeridas["Tribunal"] == "TRT/10"
    assert res.propriedades_sugeridas["Vara"] == "13"
    assert res.propriedades_sugeridas["Cidade"] == "Brasília"
    assert res.propriedades_sugeridas["Data de distribuição"] == "2024-01-01"
    assert res.propriedades_sugeridas["Fase"] == FASE_COGNITIVA  # só sentença, sem cumprimento


# ---------------------------------------------------------------------------
# Helpers individuais
# ---------------------------------------------------------------------------


def test_derivar_vara_aceita_variacoes_de_formato() -> None:
    """Padrões reconhecidos: TRT (' 13A VT'), TJDFT ('13ª Vara'), e similares."""
    assert derivar_vara({"nome": " 13A VT DE BRASILIA"}) == "13"
    assert derivar_vara({"nome": "13ª Vara Cível de Brasília"}) == "13"
    assert derivar_vara({"nome": "13a Vara"}) == "13"
    assert derivar_vara({"nome": "VARA ÚNICA"}) is None  # sem número
    assert derivar_vara({"nome": ""}) is None
    assert derivar_vara(None) is None


def test_derivar_turma_g2_aceita_turma_e_camara() -> None:
    """5ª Turma / 1ª Câmara → número. Gabinete (sem ordinal) → None."""
    assert derivar_turma_g2({"nome": "5ª Turma Cível"}) == "5"
    assert derivar_turma_g2({"nome": "1ª Turma"}) == "1"
    assert derivar_turma_g2({"nome": "3ª CAMARA"}) == "3"
    assert derivar_turma_g2({"nome": "GABINETE DO DESEMBARGADOR DORIVAL BORGES"}) is None
    assert derivar_turma_g2(None) is None


def test_derivar_status_sem_movimentos_retorna_ativo() -> None:
    """Lista vazia de movimentos → Ativo (default)."""
    assert derivar_status([]) == STATUS_ATIVO


def test_derivar_status_levantamento_apos_sobrestamento_retorna_ativo() -> None:
    """Sobrestamento (12092) seguido de levantamento (11458) → Ativo."""
    movs: list[dict[str, Any]] = [
        {"codigo": 26},
        {"codigo": 12092},
        {"codigo": 11458},
        {"codigo": 51},
    ]
    assert derivar_status(movs) == STATUS_ATIVO


def test_derivar_relator_extrai_de_complementos_tabelados() -> None:
    """complementosTabelados[].descricao contendo 'relator' → nome."""
    movs: list[dict[str, Any]] = [
        {
            "codigo": 123,
            "complementosTabelados": [
                {
                    "codigo": 5,
                    "valor": 99,
                    "nome": "Maria Aparecida Vieira",
                    "descricao": "tipo_de_relator",
                },
            ],
        },
    ]
    assert derivar_relator(movs) == "Maria Aparecida Vieira"
    # Sem complementos com "relator" → None
    assert derivar_relator([{"codigo": 26}]) is None


def test_cidade_ibge_desconhecido_loga_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """IBGE não cadastrado dispara WARNING no namespace datajud.enricher
    com formato 'cidade IBGE desconhecida: %d (CNJ %s)'."""
    import logging
    caplog.set_level(logging.WARNING, logger="datajud.enricher")

    from notion_rpadv.services.datajud_enricher import derivar_cidade
    cidade = derivar_cidade(9999999, cnj="0000000-00.0000.0.00.0000")

    assert cidade is None
    assert any(
        "cidade IBGE desconhecida: 9999999" in rec.message
        for rec in caplog.records
        if rec.name == "datajud.enricher"
    )


def test_propriedades_sugeridas_sempre_tem_14_keys() -> None:
    """Mesmo em diagnóstico de erro, as 14 keys das REGRAS_ORIGEM
    estão presentes em propriedades_sugeridas (com None)."""
    client = _mock_client(raises=DataJudAPIError(500, "boom"))
    res = enriquecer(
        _processo(tribunal="TJDFT", instancia="1º grau"),
        client=client,
    )
    nomes_esperados = {r.nome_notion for r in REGRAS_ORIGEM}
    assert set(res.propriedades_sugeridas.keys()) == nomes_esperados


def test_fase_executiva_quando_movimentos_tem_cumprimento() -> None:
    """Mov. 848 (Cumprimento) no maior grau → Fase Executiva."""
    movs: list[dict[str, Any]] = [
        {"codigo": 26},
        {"codigo": 219},  # sentença
        {"codigo": 11009},  # trânsito
        {"codigo": 848},  # cumprimento
    ]
    from notion_rpadv.services.datajud_enricher import derivar_fase
    assert derivar_fase(movs) == FASE_EXECUTIVA
