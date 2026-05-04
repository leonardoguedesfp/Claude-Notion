"""Round 6 (2026-05-04) — testes das Regras de monitoramento (1-39 v8).

Cada commit do Passo D deste round adiciona testes para as regras
implementadas. Este arquivo cresce incrementalmente.

**Implementadas até o momento:**

- Tabela A: ``instancia_implicada(pub)``.
- Tabela B: ``fase_implicada(pub)``.
- Regras 14, 15 (subida e descida de instância).
- Regras 16, 17, 18 (impossibilidades categóricas — Tipo de documento
  × Proc.Instância).
- Regras 26, 27, 28 (fase desatualizada por classe).
"""
from __future__ import annotations

from notion_rpadv.services.dje_regras_v8 import (
    ALERTA_ACORDAO_EM_1GRAU,
    ALERTA_FASE_DESATUALIZADA_COGNITIVA,
    ALERTA_FASE_DESATUALIZADA_EXECUTIVA,
    ALERTA_FASE_DESATUALIZADA_LIQUIDACAO,
    ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA,
    ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA,
    ALERTA_PAUTA_EM_1GRAU,
    ALERTA_SENTENCA_EM_COLEGIADO,
    FASE_COGNITIVA,
    FASE_EXECUTIVA,
    FASE_LIQUIDACAO,
    INSTANCIA_PRIMEIRO_GRAU,
    INSTANCIA_SEGUNDO_GRAU,
    INSTANCIA_STJ,
    INSTANCIA_TST,
    aplicar_regras_monitoramento,
    aplicar_todas_regras,
    fase_implicada,
    instancia_implicada,
    regra_14_subida_nao_detectada,
    regra_15_descida_nao_detectada,
    regra_16_acordao_em_1grau,
    regra_17_sentenca_em_colegiado,
    regra_18_pauta_em_1grau,
    regra_26_fase_executiva_por_classe,
    regra_27_fase_liquidacao_por_classe,
    regra_28_fase_cognitiva_contradita_por_classe,
)


def _pub(**kwargs):
    base = {
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Decisão",
    }
    base.update(kwargs)
    return base


def _proc(instancia: str | None = None, **kwargs):
    rec: dict = {"page_id": "x"}
    if instancia is not None:
        rec["instancia"] = instancia
    rec.update(kwargs)
    return rec


# ===========================================================================
# Regra 16 — Acórdão em processo de 1º grau
# ===========================================================================


def test_R6_R16_dispara_acordao_em_1grau() -> None:
    pub = _pub(tipoDocumento="Acórdão")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    assert regra_16_acordao_em_1grau(pub, proc) == ALERTA_ACORDAO_EM_1GRAU


def test_R6_R16_dispara_para_ementa_canonizada() -> None:
    """'Ementa' canoniza para Acórdão? NÃO — Ementa é tipo distinto.
    Regra 16 só pega Acórdão estrito; Ementa não dispara aqui."""
    pub = _pub(tipoDocumento="Ementa")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    assert regra_16_acordao_em_1grau(pub, proc) is None


def test_R6_R16_nao_dispara_em_2grau() -> None:
    pub = _pub(tipoDocumento="Acórdão")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU)
    assert regra_16_acordao_em_1grau(pub, proc) is None


def test_R6_R16_nao_dispara_em_stj_tst_stf() -> None:
    pub = _pub(tipoDocumento="Acórdão")
    for inst in (INSTANCIA_TST, INSTANCIA_STJ, "STF"):
        proc = _proc(instancia=inst)
        assert regra_16_acordao_em_1grau(pub, proc) is None, f"{inst}"


def test_R6_R16_nao_dispara_sem_processo_cadastrado() -> None:
    pub = _pub(tipoDocumento="Acórdão")
    assert regra_16_acordao_em_1grau(pub, None) is None


def test_R6_R16_canonizacao_acordao_pos_round1() -> None:
    """Variantes brutas (ACORDAO, EMENTA / ACORDÃO) viram canônico Acórdão."""
    for bruto in ("ACORDAO", "EMENTA / ACORDÃO", "Acórdão"):
        pub = _pub(tipoDocumento=bruto)
        proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
        assert regra_16_acordao_em_1grau(pub, proc) == ALERTA_ACORDAO_EM_1GRAU, bruto


# ===========================================================================
# Regra 17 — Sentença em colegiado
# ===========================================================================


def test_R6_R17_dispara_sentenca_em_2grau() -> None:
    pub = _pub(tipoDocumento="Sentença")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU)
    assert regra_17_sentenca_em_colegiado(pub, proc) == ALERTA_SENTENCA_EM_COLEGIADO


def test_R6_R17_dispara_em_tst_stj_stf() -> None:
    pub = _pub(tipoDocumento="Sentença")
    for inst in (INSTANCIA_TST, INSTANCIA_STJ, "STF"):
        proc = _proc(instancia=inst)
        assert regra_17_sentenca_em_colegiado(pub, proc) == ALERTA_SENTENCA_EM_COLEGIADO, inst


def test_R6_R17_nao_dispara_em_1grau() -> None:
    pub = _pub(tipoDocumento="Sentença")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    assert regra_17_sentenca_em_colegiado(pub, proc) is None


def test_R6_R17_nao_dispara_para_outros_tipos() -> None:
    """Acórdão, Decisão, Despacho, Pauta — não disparam Regra 17."""
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU)
    for tipo in ("Acórdão", "Decisão", "Despacho", "Pauta de Julgamento", "Ementa"):
        pub = _pub(tipoDocumento=tipo)
        assert regra_17_sentenca_em_colegiado(pub, proc) is None, tipo


def test_R6_R17_nao_dispara_sem_processo_cadastrado() -> None:
    pub = _pub(tipoDocumento="Sentença")
    assert regra_17_sentenca_em_colegiado(pub, None) is None


# ===========================================================================
# Regra 18 — Pauta de Julgamento em 1º grau
# ===========================================================================


def test_R6_R18_dispara_pauta_em_1grau() -> None:
    pub = _pub(tipoComunicacao="Edital", tipoDocumento="Pauta de Julgamento")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    assert regra_18_pauta_em_1grau(pub, proc) == ALERTA_PAUTA_EM_1GRAU


def test_R6_R18_dispara_intimacao_pauta_tjdft_em_1grau() -> None:
    """TJDFT pauta presencial individual (Tipo comunicação=Intimação)
    também dispara Regra 18 se cadastro estiver em 1º grau."""
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Pauta de Julgamento")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    assert regra_18_pauta_em_1grau(pub, proc) == ALERTA_PAUTA_EM_1GRAU


def test_R6_R18_nao_dispara_em_2grau() -> None:
    pub = _pub(tipoDocumento="Pauta de Julgamento")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU)
    assert regra_18_pauta_em_1grau(pub, proc) is None


def test_R6_R18_nao_dispara_para_outros_tipos() -> None:
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    for tipo in ("Acórdão", "Decisão", "Sentença", "Despacho", "Notificação"):
        pub = _pub(tipoDocumento=tipo)
        assert regra_18_pauta_em_1grau(pub, proc) is None, tipo


# ===========================================================================
# aplicar_regras_monitoramento — orquestrador
# ===========================================================================


def test_R6_monitoramento_devolve_lista_vazia_sem_dispar() -> None:
    """Pub Decisão + processo em 1º grau → nenhuma regra dispara."""
    pub = _pub(tipoDocumento="Decisão")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    assert aplicar_regras_monitoramento(pub, proc) == []


def test_R6_monitoramento_acordao_em_1grau_dispara_subida_e_acordao() -> None:
    """Pub Acórdão + processo 1º grau dispara Regra 14 (subida) E
    Regra 16 (impossibilidade categórica)."""
    pub = _pub(tipoDocumento="Acórdão")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    alertas = aplicar_regras_monitoramento(pub, proc)
    assert ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA in alertas
    assert ALERTA_ACORDAO_EM_1GRAU in alertas
    # Ordem: Regra 14 vem antes da 16 na avaliação
    assert alertas.index(ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA) < alertas.index(
        ALERTA_ACORDAO_EM_1GRAU
    )


def test_R6_monitoramento_sentenca_em_2grau_dispara_descida_e_sentenca() -> None:
    """Pub Sentença + processo 2º grau dispara Regra 15 (descida — Sentença
    não é classe filtrada) E Regra 17 (impossibilidade)."""
    pub = _pub(tipoDocumento="Sentença", nomeClasse="PROCEDIMENTO COMUM CÍVEL")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU)
    alertas = aplicar_regras_monitoramento(pub, proc)
    assert ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA in alertas
    assert ALERTA_SENTENCA_EM_COLEGIADO in alertas
    # Ordem: sem duplicatas
    assert len(alertas) == len(set(alertas))


# ===========================================================================
# aplicar_todas_regras — composição camada base + monitoramento
# ===========================================================================


def test_R6_todas_regras_camada_base_so() -> None:
    """Pub Intimação + Sentença + processo em 1º grau:
    - Camada base (Regra 42) → Tarefa: Analisar sentença
    - Monitoramento (Regra 17 não dispara em 1º grau)
    Resultado: tarefa Analisar sentença + zero alertas.
    """
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Sentença")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    tarefas, alertas = aplicar_todas_regras(pub, proc)
    assert tarefas == ["Analisar sentença"]
    assert alertas == []


def test_R6_todas_regras_composicao_alerta_monitoramento() -> None:
    """Pub Intimação + Acórdão + processo em 1º grau:
    - Camada base (Regra 43) → Tarefa: Analisar acórdão
    - Monitoramento Regra 14 → Alerta: Instância desatualizada (subida)
    - Monitoramento Regra 16 → Alerta: Acórdão em processo de 1º grau
    """
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Acórdão")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    tarefas, alertas = aplicar_todas_regras(pub, proc)
    assert tarefas == ["Analisar acórdão"]
    assert ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA in alertas
    assert ALERTA_ACORDAO_EM_1GRAU in alertas


def test_R6_todas_regras_pauta_em_1grau_dispara_2_alertas() -> None:
    """Pub Edital + Pauta de Julgamento + processo em 1º grau:
    - Camada base (Regra 41) → Tarefa: Nada para fazer + Alerta:
      Incluir julgamento no controle
    - Monitoramento (Regra 18) → Alerta adicional: Pauta em processo
      de 1º grau
    Resultado: 2 alertas, dedup preservando ordem (camada base primeiro).
    """
    pub = _pub(tipoComunicacao="Edital", tipoDocumento="Pauta de Julgamento")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    tarefas, alertas = aplicar_todas_regras(pub, proc)
    assert tarefas == ["Nada para fazer"]
    # Alertas: camada base + monitoramento, sem duplicatas
    assert "Incluir julgamento no controle" in alertas
    assert ALERTA_PAUTA_EM_1GRAU in alertas
    # Ordem: camada base vem antes
    assert alertas.index("Incluir julgamento no controle") < alertas.index(
        ALERTA_PAUTA_EM_1GRAU
    )


def test_R6_todas_regras_sem_cadastro_nem_camada_nem_monitor() -> None:
    """Pub Intimação + Decisão sem cadastro: camada base não dispara,
    monitoramento exige processo_record para todas as regras 16-18."""
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Decisão")
    tarefas, alertas = aplicar_todas_regras(pub, None)
    assert tarefas == []
    assert alertas == []


# ===========================================================================
# Tabela A — instancia_implicada(pub)
# ===========================================================================


def test_R6_tabA_tribunal_stj_tst_stf() -> None:
    """Tribunal STJ/TST/STF tem prioridade total sobre Órgão e Tipo."""
    assert instancia_implicada({"siglaTribunal": "STJ"}) == INSTANCIA_STJ
    assert instancia_implicada({"siglaTribunal": "TST"}) == INSTANCIA_TST
    assert instancia_implicada({"siglaTribunal": "STF"}) == "STF"


def test_R6_tabA_sentenca_implica_1grau() -> None:
    pub = {"siglaTribunal": "TJDFT", "tipoDocumento": "Sentença"}
    assert instancia_implicada(pub) == INSTANCIA_PRIMEIRO_GRAU


def test_R6_tabA_acordao_implica_2grau() -> None:
    pub = {"siglaTribunal": "TJDFT", "tipoDocumento": "Acórdão"}
    assert instancia_implicada(pub) == INSTANCIA_SEGUNDO_GRAU


def test_R6_tabA_orgao_vara_trabalho_implica_1grau() -> None:
    pub = {"siglaTribunal": "TRT10", "nomeOrgao": "18ª Vara do Trabalho de Brasília - DF"}
    assert instancia_implicada(pub) == INSTANCIA_PRIMEIRO_GRAU


def test_R6_tabA_orgao_vara_civel_implica_1grau() -> None:
    pub = {"siglaTribunal": "TJDFT", "nomeOrgao": "9ª Vara Cível de Brasília"}
    assert instancia_implicada(pub) == INSTANCIA_PRIMEIRO_GRAU


def test_R6_tabA_orgao_juizado_implica_1grau() -> None:
    pub = {"siglaTribunal": "TJDFT", "nomeOrgao": "1º Juizado Especial Cível"}
    assert instancia_implicada(pub) == INSTANCIA_PRIMEIRO_GRAU


def test_R6_tabA_orgao_desembargador_implica_2grau() -> None:
    pub = {"siglaTribunal": "TRT10", "nomeOrgao": "Desembargador João da Silva"}
    assert instancia_implicada(pub) == INSTANCIA_SEGUNDO_GRAU


def test_R6_tabA_orgao_turma_camara_implica_2grau() -> None:
    pub = {"siglaTribunal": "TJDFT", "nomeOrgao": "1ª Turma Cível"}
    assert instancia_implicada(pub) == INSTANCIA_SEGUNDO_GRAU
    pub2 = {"siglaTribunal": "TRT10", "nomeOrgao": "2ª Turma"}
    assert instancia_implicada(pub2) == INSTANCIA_SEGUNDO_GRAU


def test_R6_tabA_inconclusivo_devolve_none() -> None:
    """Sem tribunal STJ/TST/STF, sem tipo Sentença/Acórdão, e Órgão
    sem match (ex: TJSP que vem como 'Processo X - Y' sem Órgão
    formal)."""
    pub = {"siglaTribunal": "TJSP", "tipoDocumento": "Decisão", "nomeOrgao": ""}
    assert instancia_implicada(pub) is None


# ===========================================================================
# Tabela B — fase_implicada(pub)
# ===========================================================================


def test_R6_tabB_classes_cognitivas_implicam_cognitiva() -> None:
    casos = [
        "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
        "PROCEDIMENTO COMUM CÍVEL",
        "INVENTÁRIO",
        "PETIÇÃO CÍVEL",
    ]
    for classe in casos:
        pub = {"nomeClasse": classe}
        assert fase_implicada(pub) == FASE_COGNITIVA, classe


def test_R6_tabB_classes_liquidacao_implicam_liquidacao() -> None:
    casos = [
        "LIQUIDAÇÃO POR ARBITRAMENTO",
        "LIQUIDAÇÃO PROVISÓRIA POR ARBITRAMENTO",
        "LIQUIDAÇÃO DE SENTENÇA PELO PROCEDIMENTO COMUM",
    ]
    for classe in casos:
        pub = {"nomeClasse": classe}
        assert fase_implicada(pub) == FASE_LIQUIDACAO, classe


def test_R6_tabB_classes_executivas_implicam_executiva() -> None:
    casos = [
        "CUMPRIMENTO DE SENTENÇA",
        "CUMPRIMENTO PROVISÓRIO DE SENTENÇA",
        "EXECUÇÃO DE TÍTULO EXTRAJUDICIAL",
        "AGRAVO DE PETIÇÃO",
    ]
    for classe in casos:
        pub = {"nomeClasse": classe}
        assert fase_implicada(pub) == FASE_EXECUTIVA, classe


def test_R6_tabB_classes_recursais_devolvem_none() -> None:
    """Recursos não-AP herdam fase do principal — devolve None."""
    casos = [
        "RECURSO ESPECIAL",
        "AGRAVO DE INSTRUMENTO",
        "EMBARGOS DE DECLARAÇÃO CÍVEL",
        "APELAÇÃO CÍVEL",
    ]
    for classe in casos:
        pub = {"nomeClasse": classe}
        assert fase_implicada(pub) is None, classe


# ===========================================================================
# Regra 14 — Subida não detectada
# ===========================================================================


def test_R6_R14_subida_stj_processo_2grau() -> None:
    pub = _pub(siglaTribunal="STJ", tipoDocumento="Decisão")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU)
    assert regra_14_subida_nao_detectada(pub, proc) == ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA


def test_R6_R14_subida_tst_processo_1grau() -> None:
    pub = _pub(siglaTribunal="TST", tipoDocumento="Decisão")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    assert regra_14_subida_nao_detectada(pub, proc) == ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA


def test_R6_R14_subida_acordao_em_1grau_dispara() -> None:
    """Pub Acórdão em TJDFT (2º grau) com cadastro em 1º grau →
    Tabela A diz 2º grau → Regra 14 dispara."""
    pub = _pub(siglaTribunal="TJDFT", tipoDocumento="Acórdão")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    assert regra_14_subida_nao_detectada(pub, proc) == ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA


def test_R6_R14_nao_dispara_se_iguais() -> None:
    pub = _pub(siglaTribunal="STJ", tipoDocumento="Decisão")
    proc = _proc(instancia=INSTANCIA_STJ)
    assert regra_14_subida_nao_detectada(pub, proc) is None


def test_R6_R14_nao_dispara_se_pub_inconclusiva() -> None:
    """Pub sem signal claro (instancia_implicada = None) → não dispara."""
    pub = _pub(siglaTribunal="TJSP", tipoDocumento="Decisão", nomeOrgao="")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    assert regra_14_subida_nao_detectada(pub, proc) is None


# ===========================================================================
# Regra 15 — Descida não detectada
# ===========================================================================


def test_R6_R15_descida_dispara() -> None:
    """Pub TJDFT (2º grau) Decisão + processo cadastrado em STJ → descida."""
    pub = _pub(siglaTribunal="TJDFT", tipoDocumento="Acórdão")
    proc = _proc(instancia=INSTANCIA_STJ)
    assert regra_15_descida_nao_detectada(pub, proc) == ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA


def test_R6_R15_filtro_cumprimento_nao_dispara() -> None:
    """Cumprimento de sentença em 1º grau é descida LEGÍTIMA — não dispara."""
    pub = _pub(
        siglaTribunal="TRT10",
        nomeOrgao="18ª Vara do Trabalho",
        nomeClasse="CUMPRIMENTO DE SENTENÇA",
        tipoDocumento="Notificação",
    )
    proc = _proc(instancia=INSTANCIA_TST)
    assert regra_15_descida_nao_detectada(pub, proc) is None


def test_R6_R15_filtro_liquidacao_nao_dispara() -> None:
    pub = _pub(
        siglaTribunal="TRT10",
        nomeOrgao="18ª Vara do Trabalho",
        nomeClasse="LIQUIDAÇÃO POR ARBITRAMENTO",
        tipoDocumento="Notificação",
    )
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU)
    assert regra_15_descida_nao_detectada(pub, proc) is None


def test_R6_R15_nao_dispara_se_iguais_ou_subida() -> None:
    pub = _pub(siglaTribunal="STJ", tipoDocumento="Decisão")
    assert regra_15_descida_nao_detectada(pub, _proc(instancia=INSTANCIA_STJ)) is None
    assert regra_15_descida_nao_detectada(pub, _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)) is None


# ===========================================================================
# Regra 26 — Fase executiva por classe
# ===========================================================================


def test_R6_R26_dispara_cumprimento_em_proc_cognitiva() -> None:
    pub = _pub(nomeClasse="CUMPRIMENTO DE SENTENÇA")
    proc = _proc(instancia="1º grau", fase=FASE_COGNITIVA)
    assert regra_26_fase_executiva_por_classe(pub, proc) == ALERTA_FASE_DESATUALIZADA_EXECUTIVA


def test_R6_R26_dispara_agravo_peticao() -> None:
    """AGRAVO DE PETIÇÃO é recurso DENTRO da fase executiva (CLT 897)."""
    pub = _pub(nomeClasse="AGRAVO DE PETIÇÃO")
    proc = _proc(instancia="1º grau", fase=FASE_COGNITIVA)
    assert regra_26_fase_executiva_por_classe(pub, proc) == ALERTA_FASE_DESATUALIZADA_EXECUTIVA


def test_R6_R26_nao_dispara_se_proc_executiva() -> None:
    pub = _pub(nomeClasse="CUMPRIMENTO DE SENTENÇA")
    proc = _proc(instancia="1º grau", fase=FASE_EXECUTIVA)
    assert regra_26_fase_executiva_por_classe(pub, proc) is None


def test_R6_R26_nao_dispara_para_classe_nao_executiva() -> None:
    pub = _pub(nomeClasse="PROCEDIMENTO COMUM CÍVEL")
    proc = _proc(instancia="1º grau", fase=FASE_COGNITIVA)
    assert regra_26_fase_executiva_por_classe(pub, proc) is None


# ===========================================================================
# Regra 27 — Fase liquidação por classe
# ===========================================================================


def test_R6_R27_dispara_liquidacao_em_proc_cognitiva() -> None:
    pub = _pub(nomeClasse="LIQUIDAÇÃO POR ARBITRAMENTO")
    proc = _proc(instancia="1º grau", fase=FASE_COGNITIVA)
    assert regra_27_fase_liquidacao_por_classe(pub, proc) == ALERTA_FASE_DESATUALIZADA_LIQUIDACAO


def test_R6_R27_nao_dispara_se_proc_liquidacao() -> None:
    pub = _pub(nomeClasse="LIQUIDAÇÃO DE SENTENÇA PELO PROCEDIMENTO COMUM")
    proc = _proc(instancia="1º grau", fase=FASE_LIQUIDACAO)
    assert regra_27_fase_liquidacao_por_classe(pub, proc) is None


def test_R6_R27_nao_dispara_se_proc_liquidacao_pendente() -> None:
    """'Liquidação pendente' também é considerada fase de liquidação."""
    pub = _pub(nomeClasse="LIQUIDAÇÃO POR ARBITRAMENTO")
    proc = _proc(instancia="1º grau", fase="Liquidação pendente")
    assert regra_27_fase_liquidacao_por_classe(pub, proc) is None


# ===========================================================================
# Regra 28 — Fase cognitiva contradita por classe avançada
# ===========================================================================


def test_R6_R28_dispara_cognitiva_em_proc_executiva() -> None:
    pub = _pub(nomeClasse="AÇÃO TRABALHISTA - RITO ORDINÁRIO")
    proc = _proc(instancia="1º grau", fase=FASE_EXECUTIVA)
    assert regra_28_fase_cognitiva_contradita_por_classe(pub, proc) == ALERTA_FASE_DESATUALIZADA_COGNITIVA


def test_R6_R28_dispara_cognitiva_em_proc_liquidacao() -> None:
    pub = _pub(nomeClasse="PROCEDIMENTO COMUM CÍVEL")
    proc = _proc(instancia="1º grau", fase=FASE_LIQUIDACAO)
    assert regra_28_fase_cognitiva_contradita_por_classe(pub, proc) == ALERTA_FASE_DESATUALIZADA_COGNITIVA


def test_R6_R28_nao_dispara_se_proc_cognitiva() -> None:
    pub = _pub(nomeClasse="PROCEDIMENTO COMUM CÍVEL")
    proc = _proc(instancia="1º grau", fase=FASE_COGNITIVA)
    assert regra_28_fase_cognitiva_contradita_por_classe(pub, proc) is None


def test_R6_R28_nao_dispara_para_classe_nao_cognitiva() -> None:
    pub = _pub(nomeClasse="CUMPRIMENTO DE SENTENÇA")
    proc = _proc(instancia="1º grau", fase=FASE_EXECUTIVA)
    assert regra_28_fase_cognitiva_contradita_por_classe(pub, proc) is None


# ===========================================================================
# Composição — múltiplas regras simultâneas
# ===========================================================================


def test_R6_composicao_acordao_em_1grau_dispara_3_alertas() -> None:
    """Pub Acórdão TJDFT em proc cadastrado como 1º grau cognitiva
    dispara: Regra 14 (subida), Regra 16 (acórdão em 1º grau).

    Não dispara fase executiva/liquidação/cognitiva (Acórdão não é
    classe que define fase pela Tabela B)."""
    pub = _pub(
        siglaTribunal="TJDFT",
        tipoDocumento="Acórdão",
        nomeClasse="APELAÇÃO CÍVEL",
        nomeOrgao="1ª Turma Cível",
    )
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, fase=FASE_COGNITIVA)
    alertas = aplicar_regras_monitoramento(pub, proc)
    assert ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA in alertas
    assert ALERTA_ACORDAO_EM_1GRAU in alertas
    assert ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA not in alertas
    assert ALERTA_FASE_DESATUALIZADA_COGNITIVA not in alertas


def test_R6_composicao_cumprimento_em_proc_2grau_cognitiva() -> None:
    """Cumprimento + cadastro 2º grau cognitiva: descida filtrada
    (cumprimento é descida legítima — Regra 15 silencia), mas Regra 26
    (fase executiva) dispara."""
    pub = _pub(
        siglaTribunal="TRT10",
        nomeOrgao="18ª Vara do Trabalho",
        nomeClasse="CUMPRIMENTO DE SENTENÇA",
        tipoDocumento="Notificação",
    )
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU, fase=FASE_COGNITIVA)
    alertas = aplicar_regras_monitoramento(pub, proc)
    assert ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA not in alertas  # filtrado
    assert ALERTA_FASE_DESATUALIZADA_EXECUTIVA in alertas
