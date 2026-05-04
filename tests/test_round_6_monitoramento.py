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
    ALERTA_ATIVIDADE_EM_PROCESSO_ARQUIVADO,
    ALERTA_CAPTURAR_LINK_EXTERNO,
    ALERTA_CAPTURAR_NUMERACAO_STF,
    ALERTA_CAPTURAR_NUMERACAO_STJ_TST,
    ALERTA_CONFERIR_NATUREZA_PROCESSO,
    ALERTA_CONFERIR_SENTENCA_FASE_POS_COGNITIVA,
    ALERTA_CONFERIR_TIPO_PROCESSO,
    ALERTA_CONFERIR_TRIBUNAL_ORIGEM,
    ALERTA_FASE_DESATUALIZADA_COGNITIVA,
    ALERTA_FASE_DESATUALIZADA_EXECUTIVA,
    ALERTA_FASE_DESATUALIZADA_LIQUIDACAO,
    ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA,
    ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA,
    ALERTA_PARTE_ADVERSA_BB,
    ALERTA_PARTE_ADVERSA_BB_CONSORCIOS,
    ALERTA_PARTE_ADVERSA_BRADESCO_SAUDE,
    ALERTA_PARTE_ADVERSA_CASSI,
    ALERTA_PARTE_ADVERSA_PREVI,
    ALERTA_PAUTA_EM_1GRAU,
    ALERTA_PAUTA_EM_PROCESSO_ARQUIVADO,
    ALERTA_PROCESSO_NAO_CADASTRADO,
    ALERTA_RECURSO_AUTONOMO_SEM_PROCESSO_PAI,
    ALERTA_SENTENCA_EM_COLEGIADO,
    ALERTA_TEXTO_IMPRESTAVEL,
    ALERTA_TRANSITO_PENDENTE,
    ALERTA_TRIBUNAL_FORA_VOCABULARIO,
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
    regra_2_capturar_numeracao_stj_tst,
    regra_3_capturar_numeracao_stf,
    regra_4_natureza_inconsistente_com_tribunal,
    regra_5_natureza_inconsistente_com_classe,
    regra_6_recurso_autonomo_cadastrado_como_principal,
    regra_11_partes_adversas_ausentes,
    regra_12_tribunal_fora_vocabulario,
    regra_13_conferir_tribunal_origem,
    regra_14_subida_nao_detectada,
    regra_15_descida_nao_detectada,
    regra_16_acordao_em_1grau,
    regra_17_sentenca_em_colegiado,
    regra_18_pauta_em_1grau,
    regra_26_fase_executiva_por_classe,
    regra_27_fase_liquidacao_por_classe,
    regra_28_fase_cognitiva_contradita_por_classe,
    regra_29_sentenca_em_fase_pos_cognitiva,
    regra_30_pauta_em_processo_arquivado,
    regra_31_atividade_em_processo_arquivado,
    regra_35_transito_pendente,
    regra_38_capturar_link_externo,
    regra_39_recurso_autonomo_sem_processo_pai,
    regra_processo_nao_cadastrado,
    regra_texto_imprestavel,
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


def test_R6_todas_regras_sem_cadastro_intimacao_decisao_dispara_so_proc_nao_cad() -> None:
    """Pub Intimação + Decisão sem cadastro: camada base não dispara,
    Regras 14-18, 26-28, 35 exigem cadastro, mas o alerta operacional
    'Processo não cadastrado' dispara — única exceção."""
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Decisão")
    tarefas, alertas = aplicar_todas_regras(pub, None)
    assert tarefas == []
    assert alertas == [ALERTA_PROCESSO_NAO_CADASTRADO]


def test_R6_todas_regras_lista_distribuicao_sem_cadastro_so_camada_base() -> None:
    """Pub Lista de Distribuição sem cadastro:
    - Camada base (Regra 40): Tarefa 'Nada para fazer' + Alerta
      'Processo/recurso distribuído'.
    - 'Processo não cadastrado' NÃO dispara (refinamento v8 — distribuição
      tem sinal próprio).
    """
    pub = _pub(tipoComunicacao="Lista de Distribuição", tipoDocumento="Distribuição")
    tarefas, alertas = aplicar_todas_regras(pub, None)
    assert tarefas == ["Nada para fazer"]
    assert "Processo/recurso distribuído" in alertas
    assert ALERTA_PROCESSO_NAO_CADASTRADO not in alertas


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


# ===========================================================================
# Regra 35 — Trânsito em julgado pendente
# ===========================================================================


def test_R6_R35_dispara_cumprimento_sem_transito() -> None:
    pub = _pub(nomeClasse="CUMPRIMENTO DE SENTENÇA")
    proc = _proc(
        instancia="1º grau",
        data_do_transito_em_julgado_cognitiva=None,
        data_do_transito_em_julgado_executiva=None,
    )
    assert regra_35_transito_pendente(pub, proc) == ALERTA_TRANSITO_PENDENTE


def test_R6_R35_NAO_dispara_em_provisorio() -> None:
    """Cumprimento PROVISÓRIO está antes do trânsito por design."""
    pub = _pub(nomeClasse="CUMPRIMENTO PROVISÓRIO DE SENTENÇA")
    proc = _proc(
        instancia="1º grau",
        data_do_transito_em_julgado_cognitiva=None,
        data_do_transito_em_julgado_executiva=None,
    )
    assert regra_35_transito_pendente(pub, proc) is None


def test_R6_R35_nao_dispara_se_data_presente() -> None:
    pub = _pub(nomeClasse="CUMPRIMENTO DE SENTENÇA")
    proc = _proc(
        instancia="1º grau",
        data_do_transito_em_julgado_cognitiva="2024-12-10",
        data_do_transito_em_julgado_executiva=None,
    )
    assert regra_35_transito_pendente(pub, proc) is None


def test_R6_R35_nao_dispara_para_classe_diferente() -> None:
    pub = _pub(nomeClasse="PROCEDIMENTO COMUM CÍVEL")
    proc = _proc(
        instancia="1º grau",
        data_do_transito_em_julgado_cognitiva=None,
        data_do_transito_em_julgado_executiva=None,
    )
    assert regra_35_transito_pendente(pub, proc) is None


def test_R6_R35_nao_dispara_sem_processo_cadastrado() -> None:
    pub = _pub(nomeClasse="CUMPRIMENTO DE SENTENÇA")
    assert regra_35_transito_pendente(pub, None) is None


# ===========================================================================
# Regra 11 — Partes adversas típicas ausentes
# ===========================================================================


def _pub_com_destinatarios(*nomes_polos):
    return _pub(destinatarios=[{"nome": nome, "polo": polo} for nome, polo in nomes_polos])


def test_R6_R11_dispara_BB_ausente() -> None:
    pub = _pub_com_destinatarios(("BANCO DO BRASIL SA", "P"), ("AUTOR FULANO", "A"))
    proc = _proc(partes_adversas=[])
    alertas = regra_11_partes_adversas_ausentes(pub, proc)
    assert ALERTA_PARTE_ADVERSA_BB in alertas


def test_R6_R11_NAO_dispara_BB_ja_cadastrado() -> None:
    pub = _pub_com_destinatarios(("BANCO DO BRASIL SA", "P"), ("AUTOR", "A"))
    proc = _proc(partes_adversas=["Banco do Brasil"])
    alertas = regra_11_partes_adversas_ausentes(pub, proc)
    assert ALERTA_PARTE_ADVERSA_BB not in alertas


def test_R6_R11_dispara_PREVI_via_caixa_de_previdencia() -> None:
    pub = _pub_com_destinatarios(
        ("CAIXA DE PREVIDENCIA DOS FUNCIONARIOS DO BANCO DO BRASIL", "P"),
        ("AUTOR", "A"),
    )
    proc = _proc(partes_adversas=[])
    alertas = regra_11_partes_adversas_ausentes(pub, proc)
    assert ALERTA_PARTE_ADVERSA_PREVI in alertas


def test_R6_R11_dispara_CASSI() -> None:
    pub = _pub_com_destinatarios(("CASSI - CAIXA DE ASSISTÊNCIA", "P"), ("AUTOR", "A"))
    proc = _proc(partes_adversas=[])
    alertas = regra_11_partes_adversas_ausentes(pub, proc)
    assert ALERTA_PARTE_ADVERSA_CASSI in alertas


def test_R6_R11_dispara_bradesco_saude() -> None:
    pub = _pub_com_destinatarios(("BRADESCO SAÚDE S.A.", "P"), ("AUTOR", "A"))
    proc = _proc(partes_adversas=[])
    alertas = regra_11_partes_adversas_ausentes(pub, proc)
    assert ALERTA_PARTE_ADVERSA_BRADESCO_SAUDE in alertas


def test_R6_R11_dispara_BB_consorcios() -> None:
    pub = _pub_com_destinatarios(
        ("BB ADMINISTRADORA DE CONSÓRCIOS S.A.", "P"),
        ("AUTOR", "A"),
    )
    proc = _proc(partes_adversas=[])
    alertas = regra_11_partes_adversas_ausentes(pub, proc)
    assert ALERTA_PARTE_ADVERSA_BB_CONSORCIOS in alertas


def test_R6_R11_dispara_multiplos_simultaneamente() -> None:
    """Pub com BB + PREVI ausentes em Proc.Partes adversas dispara 2."""
    pub = _pub_com_destinatarios(
        ("BANCO DO BRASIL SA", "P"),
        ("CAIXA DE PREVIDENCIA DOS FUNCIONARIOS DO BANCO DO BRASIL", "P"),
        ("AUTOR", "A"),
    )
    proc = _proc(partes_adversas=[])
    alertas = regra_11_partes_adversas_ausentes(pub, proc)
    assert ALERTA_PARTE_ADVERSA_BB in alertas
    assert ALERTA_PARTE_ADVERSA_PREVI in alertas
    assert len(alertas) == 2


def test_R6_R11_NAO_dispara_sem_processo_cadastrado() -> None:
    pub = _pub_com_destinatarios(("BANCO DO BRASIL SA", "P"), ("AUTOR", "A"))
    assert regra_11_partes_adversas_ausentes(pub, None) == []


# ===========================================================================
# Texto imprestável (alerta técnico mantido do Round 4.4)
# ===========================================================================


def test_R6_texto_imprestavel_tjgo_indisponivel() -> None:
    pub = _pub(texto="ARQUIVOS DIGITAIS INDISPONÍVEIS (NÃO SÃO DO TIPO PÚBLICO)")
    assert regra_texto_imprestavel(pub, _proc()) == ALERTA_TEXTO_IMPRESTAVEL


def test_R6_texto_imprestavel_intime_se_minimalista() -> None:
    pub = _pub(texto="Intime-se.")
    assert regra_texto_imprestavel(pub, _proc()) == ALERTA_TEXTO_IMPRESTAVEL


def test_R6_texto_imprestavel_trt10_so_id_sem_cnj() -> None:
    pub = _pub(
        texto=(
            "Tomar ciência do(a) Intimação de ID 8217f34.\n\n"
            "Intimado(s) / Citado(s)\n - I.S.L.A."
        ),
    )
    assert regra_texto_imprestavel(pub, _proc()) == ALERTA_TEXTO_IMPRESTAVEL


def test_R6_texto_imprestavel_NAO_dispara_em_despacho_curto_legitimo() -> None:
    pub = _pub(texto="Despacho curto: defiro o pedido. Intime-se.")
    assert regra_texto_imprestavel(pub, _proc()) is None


def test_R6_texto_imprestavel_funciona_sem_cadastro() -> None:
    """Alerta técnico não depende de Proc cadastrado."""
    pub = _pub(texto="Intime-se.")
    assert regra_texto_imprestavel(pub, None) == ALERTA_TEXTO_IMPRESTAVEL


# ===========================================================================
# Processo não cadastrado (alerta operacional refinado v8)
# ===========================================================================


def test_R6_processo_nao_cadastrado_dispara_em_intimacao_decisao() -> None:
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Decisão")
    assert regra_processo_nao_cadastrado(pub, None) == ALERTA_PROCESSO_NAO_CADASTRADO


def test_R6_processo_nao_cadastrado_NAO_dispara_em_lista_distribuicao() -> None:
    """Refinamento v8 X.5: distribuições já têm sinal certo da Camada
    base ('Processo/recurso distribuído') — não duplicar com este alerta."""
    pub = _pub(tipoComunicacao="Lista de Distribuição", tipoDocumento="Distribuição")
    assert regra_processo_nao_cadastrado(pub, None) is None


def test_R6_processo_nao_cadastrado_NAO_dispara_em_intimacao_distribuicao() -> None:
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Distribuição")
    assert regra_processo_nao_cadastrado(pub, None) is None


def test_R6_processo_nao_cadastrado_NAO_dispara_se_processo_cadastrado() -> None:
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Decisão")
    assert regra_processo_nao_cadastrado(pub, _proc()) is None


# ===========================================================================
# Round 7a — Regra 2: Capturar numeração STJ/TST
# ===========================================================================


def test_R7a_R2_dispara_pub_stj_proc_sem_numero() -> None:
    pub = _pub(siglaTribunal="STJ")
    proc = _proc(instancia=INSTANCIA_STJ, numero_stj_tst="")
    assert regra_2_capturar_numeracao_stj_tst(pub, proc) == ALERTA_CAPTURAR_NUMERACAO_STJ_TST


def test_R7a_R2_dispara_pub_tst_proc_sem_numero() -> None:
    pub = _pub(siglaTribunal="TST")
    proc = _proc(instancia=INSTANCIA_TST, numero_stj_tst="")
    assert regra_2_capturar_numeracao_stj_tst(pub, proc) == ALERTA_CAPTURAR_NUMERACAO_STJ_TST


def test_R7a_R2_NAO_dispara_se_numero_existe() -> None:
    pub = _pub(siglaTribunal="STJ")
    proc = _proc(instancia=INSTANCIA_STJ, numero_stj_tst="REsp 123456/DF")
    assert regra_2_capturar_numeracao_stj_tst(pub, proc) is None


def test_R7a_R2_NAO_dispara_para_tribunal_local() -> None:
    pub = _pub(siglaTribunal="TJDFT")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, numero_stj_tst="")
    assert regra_2_capturar_numeracao_stj_tst(pub, proc) is None


def test_R7a_R2_NAO_dispara_sem_processo_cadastrado() -> None:
    pub = _pub(siglaTribunal="STJ")
    assert regra_2_capturar_numeracao_stj_tst(pub, None) is None


# ===========================================================================
# Round 7a — Regra 3: Capturar numeração STF
# ===========================================================================


def test_R7a_R3_dispara_pub_stf_proc_sem_numero() -> None:
    pub = _pub(siglaTribunal="STF")
    proc = _proc(instancia="STF", numero_stf="")
    assert regra_3_capturar_numeracao_stf(pub, proc) == ALERTA_CAPTURAR_NUMERACAO_STF


def test_R7a_R3_NAO_dispara_se_numero_existe() -> None:
    pub = _pub(siglaTribunal="STF")
    proc = _proc(instancia="STF", numero_stf="RE 1234567")
    assert regra_3_capturar_numeracao_stf(pub, proc) is None


def test_R7a_R3_NAO_dispara_para_outros_tribunais() -> None:
    """STJ não dispara Regra 3 (essa é só STF)."""
    pub = _pub(siglaTribunal="STJ")
    proc = _proc(instancia=INSTANCIA_STJ, numero_stf="")
    assert regra_3_capturar_numeracao_stf(pub, proc) is None


def test_R7a_R3_NAO_dispara_sem_processo_cadastrado() -> None:
    pub = _pub(siglaTribunal="STF")
    assert regra_3_capturar_numeracao_stf(pub, None) is None


# ===========================================================================
# Round 7a — Regra 12: Tribunal fora do vocabulário
# ===========================================================================


def test_R7a_R12_dispara_TRT18() -> None:
    """TRT18 não está no select de Proc.tribunal canônico."""
    pub = _pub(siglaTribunal="TRT18")
    assert regra_12_tribunal_fora_vocabulario(pub, _proc()) == ALERTA_TRIBUNAL_FORA_VOCABULARIO


def test_R7a_R12_dispara_TRF1() -> None:
    pub = _pub(siglaTribunal="TRF1")
    assert regra_12_tribunal_fora_vocabulario(pub, _proc()) == ALERTA_TRIBUNAL_FORA_VOCABULARIO


def test_R7a_R12_NAO_dispara_para_tribunais_canonicos() -> None:
    for trib in ("TRT10", "TJDFT", "STJ", "TST", "STF", "TJSP", "TJRJ"):
        pub = _pub(siglaTribunal=trib)
        assert regra_12_tribunal_fora_vocabulario(pub, _proc()) is None, trib


def test_R7a_R12_dispara_independente_de_processo_cadastrado() -> None:
    """Regra 12 sinaliza vocabulário, dispara mesmo sem cadastro."""
    pub = _pub(siglaTribunal="TRT18")
    assert regra_12_tribunal_fora_vocabulario(pub, None) == ALERTA_TRIBUNAL_FORA_VOCABULARIO


# ===========================================================================
# Round 7a — Regra 13: Verificação de origem em 1ª instância
# ===========================================================================


def test_R7a_R13_dispara_pub_trt10_proc_tjdft() -> None:
    """Pub vem do TRT10 mas Proc cadastrado como TJDFT em 1º grau —
    indica vinculação errada."""
    pub = _pub(siglaTribunal="TRT10")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, tribunal="TJDFT")
    assert regra_13_conferir_tribunal_origem(pub, proc) == ALERTA_CONFERIR_TRIBUNAL_ORIGEM


def test_R7a_R13_NAO_dispara_se_tribunais_coincidem_via_normalizacao() -> None:
    """Pub.siglaTribunal=TRT10 e Proc.tribunal=TRT/10 são equivalentes."""
    pub = _pub(siglaTribunal="TRT10")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, tribunal="TRT/10")
    assert regra_13_conferir_tribunal_origem(pub, proc) is None


def test_R7a_R13_NAO_dispara_em_2grau_ou_superior() -> None:
    """Em 2º grau/superior, tribunal pode divergir do de origem (recurso)."""
    pub = _pub(siglaTribunal="STJ")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU, tribunal="TJDFT")
    assert regra_13_conferir_tribunal_origem(pub, proc) is None


def test_R7a_R13_NAO_dispara_se_proc_tribunal_vazio() -> None:
    """Cadastro sem tribunal → não dispara (sem base de comparação)."""
    pub = _pub(siglaTribunal="TJDFT")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, tribunal="")
    assert regra_13_conferir_tribunal_origem(pub, proc) is None


def test_R7a_R13_NAO_dispara_sem_processo_cadastrado() -> None:
    pub = _pub(siglaTribunal="TRT10")
    assert regra_13_conferir_tribunal_origem(pub, None) is None


# ===========================================================================
# Composição Round 7a — múltiplas regras simultâneas
# ===========================================================================


def test_R7a_composicao_pub_stj_proc_2grau_dispara_2_alertas() -> None:
    """Pub STJ + processo em 2º grau (TJDFT) sem numero_stj_tst:
    - Regra 2 (Capturar numeração STJ/TST)
    - Regra 14 (Subida não detectada — 2º grau → STJ)
    """
    pub = _pub(siglaTribunal="STJ", tipoDocumento="Decisão")
    proc = _proc(
        instancia=INSTANCIA_SEGUNDO_GRAU,
        tribunal="TJDFT",
        numero_stj_tst="",
    )
    alertas = aplicar_regras_monitoramento(pub, proc)
    assert ALERTA_CAPTURAR_NUMERACAO_STJ_TST in alertas
    assert ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA in alertas


def test_R7a_composicao_pub_trt18_dispara_so_tribunal_fora_vocab() -> None:
    """Pub TRT18 sem cadastro:
    - Regra 12 (Tribunal fora do vocabulário) — dispara mesmo sem cadastro
    - Processo não cadastrado — dispara (Intimação Notificação não é distribuição)
    """
    pub = _pub(siglaTribunal="TRT18", tipoComunicacao="Intimação", tipoDocumento="Notificação")
    alertas = aplicar_regras_monitoramento(pub, None)
    assert ALERTA_TRIBUNAL_FORA_VOCABULARIO in alertas
    assert ALERTA_PROCESSO_NAO_CADASTRADO in alertas


# ===========================================================================
# Round 7b — Regra 4: Natureza inconsistente com Tribunal
# ===========================================================================


def test_R7b_R4_dispara_trt_proc_civel() -> None:
    pub = _pub(siglaTribunal="TRT10")
    proc = _proc(natureza="Cível")
    assert regra_4_natureza_inconsistente_com_tribunal(pub, proc) == ALERTA_CONFERIR_NATUREZA_PROCESSO


def test_R7b_R4_dispara_tjdft_proc_trabalhista() -> None:
    pub = _pub(siglaTribunal="TJDFT")
    proc = _proc(natureza="Trabalhista")
    assert regra_4_natureza_inconsistente_com_tribunal(pub, proc) == ALERTA_CONFERIR_NATUREZA_PROCESSO


def test_R7b_R4_NAO_dispara_se_consistente() -> None:
    """TRT trabalhista, TJDFT cível — ambos consistentes."""
    assert regra_4_natureza_inconsistente_com_tribunal(_pub(siglaTribunal="TRT10"), _proc(natureza="Trabalhista")) is None
    assert regra_4_natureza_inconsistente_com_tribunal(_pub(siglaTribunal="TJDFT"), _proc(natureza="Cível")) is None


def test_R7b_R4_NAO_dispara_para_stj_stf() -> None:
    """STJ/STF julgam ambas as naturezas — não dispara."""
    assert regra_4_natureza_inconsistente_com_tribunal(_pub(siglaTribunal="STJ"), _proc(natureza="Trabalhista")) is None
    assert regra_4_natureza_inconsistente_com_tribunal(_pub(siglaTribunal="STJ"), _proc(natureza="Cível")) is None
    assert regra_4_natureza_inconsistente_com_tribunal(_pub(siglaTribunal="STF"), _proc(natureza="Cível")) is None


def test_R7b_R4_NAO_dispara_se_natureza_vazia() -> None:
    """Cadastro sem natureza definida → não dispara."""
    pub = _pub(siglaTribunal="TRT10")
    assert regra_4_natureza_inconsistente_com_tribunal(pub, _proc(natureza="")) is None


# ===========================================================================
# Round 7b — Regra 5: Natureza inconsistente com Classe
# ===========================================================================


def test_R7b_R5_dispara_classe_trabalhista_proc_civel() -> None:
    pub = _pub(nomeClasse="AÇÃO TRABALHISTA - RITO ORDINÁRIO")
    proc = _proc(natureza="Cível")
    assert regra_5_natureza_inconsistente_com_classe(pub, proc) == ALERTA_CONFERIR_NATUREZA_PROCESSO


def test_R7b_R5_dispara_classe_civel_proc_trabalhista() -> None:
    pub = _pub(nomeClasse="PROCEDIMENTO COMUM CÍVEL")
    proc = _proc(natureza="Trabalhista")
    assert regra_5_natureza_inconsistente_com_classe(pub, proc) == ALERTA_CONFERIR_NATUREZA_PROCESSO


def test_R7b_R5_NAO_dispara_se_consistente() -> None:
    assert regra_5_natureza_inconsistente_com_classe(
        _pub(nomeClasse="AGRAVO DE PETIÇÃO"), _proc(natureza="Trabalhista"),
    ) is None
    assert regra_5_natureza_inconsistente_com_classe(
        _pub(nomeClasse="APELAÇÃO CÍVEL"), _proc(natureza="Cível"),
    ) is None


def test_R7b_R5_NAO_dispara_para_classes_ambiguas() -> None:
    """RESP, AI sem qualif, AGRAVO simples, CUMPRIMENTO — ambíguas, herdam."""
    classes_ambiguas = [
        "RECURSO ESPECIAL",
        "AGRAVO DE INSTRUMENTO",
        "AGRAVO",
        "CUMPRIMENTO DE SENTENÇA",
        "AGRAVO EM RECURSO ESPECIAL",
        "AGRAVO DE INSTRUMENTO EM RECURSO ESPECIAL",
        "CONFLITO DE COMPETÊNCIA",
    ]
    for c in classes_ambiguas:
        # Mesmo com natureza arbitrária, ambíguas não disparam
        assert regra_5_natureza_inconsistente_com_classe(
            _pub(nomeClasse=c), _proc(natureza="Trabalhista"),
        ) is None, c
        assert regra_5_natureza_inconsistente_com_classe(
            _pub(nomeClasse=c), _proc(natureza="Cível"),
        ) is None, c


# ===========================================================================
# Round 7b — Regra 6: Recurso autônomo cadastrado como Principal
# ===========================================================================


def test_R7b_R6_dispara_AI_estrita_em_proc_principal() -> None:
    pub = _pub(nomeClasse="AGRAVO DE INSTRUMENTO")
    proc = _proc(tipo_de_processo="Principal")
    assert regra_6_recurso_autonomo_cadastrado_como_principal(pub, proc) == ALERTA_CONFERIR_TIPO_PROCESSO


def test_R7b_R6_NAO_dispara_para_AI_em_RESP_ou_RR() -> None:
    """AI em RESP/RR não cria registro próprio (decisão administrativa
    do escritório); fica no principal."""
    for c in ("AGRAVO DE INSTRUMENTO EM RECURSO ESPECIAL", "AGRAVO DE INSTRUMENTO EM RECURSO DE REVISTA"):
        pub = _pub(nomeClasse=c)
        assert regra_6_recurso_autonomo_cadastrado_como_principal(pub, _proc(tipo_de_processo="Principal")) is None, c


def test_R7b_R6_NAO_dispara_se_proc_ja_recurso_autonomo() -> None:
    pub = _pub(nomeClasse="AGRAVO DE INSTRUMENTO")
    proc = _proc(tipo_de_processo="Recurso autônomo")
    assert regra_6_recurso_autonomo_cadastrado_como_principal(pub, proc) is None


def test_R7b_R6_NAO_dispara_para_outras_classes_recursais() -> None:
    """Apelação, RESP, RO Trabalhista — não criam registro próprio."""
    for c in ("APELAÇÃO CÍVEL", "RECURSO ESPECIAL", "RECURSO ORDINÁRIO TRABALHISTA"):
        pub = _pub(nomeClasse=c)
        assert regra_6_recurso_autonomo_cadastrado_como_principal(pub, _proc(tipo_de_processo="Principal")) is None, c


# ===========================================================================
# Round 7b — Regra 39: Recurso autônomo sem processo pai
# ===========================================================================


def test_R7b_R39_dispara_recurso_autonomo_sem_pai() -> None:
    proc = _proc(tipo_de_processo="Recurso autônomo", processo_pai=[])
    assert regra_39_recurso_autonomo_sem_processo_pai(_pub(), proc) == ALERTA_RECURSO_AUTONOMO_SEM_PROCESSO_PAI


def test_R7b_R39_dispara_reclamacao_sem_pai() -> None:
    proc = _proc(tipo_de_processo="Reclamação constitucional", processo_pai=None)
    assert regra_39_recurso_autonomo_sem_processo_pai(_pub(), proc) == ALERTA_RECURSO_AUTONOMO_SEM_PROCESSO_PAI


def test_R7b_R39_dispara_incidente_sem_pai() -> None:
    proc = _proc(tipo_de_processo="Incidente", processo_pai="")
    assert regra_39_recurso_autonomo_sem_processo_pai(_pub(), proc) == ALERTA_RECURSO_AUTONOMO_SEM_PROCESSO_PAI


def test_R7b_R39_NAO_dispara_se_principal() -> None:
    proc = _proc(tipo_de_processo="Principal", processo_pai=[])
    assert regra_39_recurso_autonomo_sem_processo_pai(_pub(), proc) is None


def test_R7b_R39_NAO_dispara_se_pai_populado() -> None:
    proc = _proc(tipo_de_processo="Recurso autônomo", processo_pai=["page-id-pai"])
    assert regra_39_recurso_autonomo_sem_processo_pai(_pub(), proc) is None


def test_R7b_R39_NAO_dispara_sem_processo_cadastrado() -> None:
    assert regra_39_recurso_autonomo_sem_processo_pai(_pub(), None) is None


# ===========================================================================
# Composição Round 7b — Regra 6 + 39 simultâneas
# ===========================================================================


def test_R7b_composicao_AI_principal_sem_pai_dispara_R6_apenas() -> None:
    """Regra 6 dispara (Principal), mas Regra 39 só dispara para
    Recurso autônomo/Reclamação/Incidente — Principal não."""
    pub = _pub(nomeClasse="AGRAVO DE INSTRUMENTO")
    proc = _proc(tipo_de_processo="Principal", processo_pai=[])
    alertas = aplicar_regras_monitoramento(pub, proc)
    assert ALERTA_CONFERIR_TIPO_PROCESSO in alertas
    assert ALERTA_RECURSO_AUTONOMO_SEM_PROCESSO_PAI not in alertas


def test_R7b_composicao_AI_recurso_autonomo_sem_pai_dispara_R39() -> None:
    """Regra 6 NÃO dispara (já é Recurso autônomo, OK) mas Regra 39
    dispara (sem processo pai)."""
    pub = _pub(nomeClasse="AGRAVO DE INSTRUMENTO")
    proc = _proc(tipo_de_processo="Recurso autônomo", processo_pai=[])
    alertas = aplicar_regras_monitoramento(pub, proc)
    assert ALERTA_CONFERIR_TIPO_PROCESSO not in alertas
    assert ALERTA_RECURSO_AUTONOMO_SEM_PROCESSO_PAI in alertas


# ===========================================================================
# Round 7c — Regra 29: Sentença em fase pós-cognitiva
# ===========================================================================


def test_R7c_R29_dispara_sentenca_em_fase_executiva() -> None:
    pub = _pub(tipoDocumento="Sentença")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, fase=FASE_EXECUTIVA)
    assert regra_29_sentenca_em_fase_pos_cognitiva(pub, proc) == ALERTA_CONFERIR_SENTENCA_FASE_POS_COGNITIVA


def test_R7c_R29_dispara_sentenca_em_fase_liquidacao() -> None:
    pub = _pub(tipoDocumento="Sentença")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, fase=FASE_LIQUIDACAO)
    assert regra_29_sentenca_em_fase_pos_cognitiva(pub, proc) == ALERTA_CONFERIR_SENTENCA_FASE_POS_COGNITIVA


def test_R7c_R29_NAO_dispara_em_fase_cognitiva() -> None:
    pub = _pub(tipoDocumento="Sentença")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, fase=FASE_COGNITIVA)
    assert regra_29_sentenca_em_fase_pos_cognitiva(pub, proc) is None


def test_R7c_R29_NAO_dispara_para_outros_tipos() -> None:
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, fase=FASE_EXECUTIVA)
    for tipo in ("Acórdão", "Decisão", "Despacho", "Pauta de Julgamento"):
        pub = _pub(tipoDocumento=tipo)
        assert regra_29_sentenca_em_fase_pos_cognitiva(pub, proc) is None, tipo


# ===========================================================================
# Round 7c — Regra 30: Pauta em processo arquivado
# ===========================================================================


def test_R7c_R30_dispara_pauta_em_arquivado() -> None:
    pub = _pub(tipoDocumento="Pauta de Julgamento")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU, status="Arquivado")
    assert regra_30_pauta_em_processo_arquivado(pub, proc) == ALERTA_PAUTA_EM_PROCESSO_ARQUIVADO


def test_R7c_R30_NAO_dispara_em_ativo() -> None:
    pub = _pub(tipoDocumento="Pauta de Julgamento")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU, status="Ativo")
    assert regra_30_pauta_em_processo_arquivado(pub, proc) is None


def test_R7c_R30_NAO_dispara_em_arquivado_tema955() -> None:
    """Match exato em 'Arquivado' — não pega 'Arquivado provisoriamente
    (tema 955)' (esses retomarão atividade quando o tema for julgado)."""
    pub = _pub(tipoDocumento="Pauta de Julgamento")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU, status="Arquivado provisoriamente (tema 955)")
    assert regra_30_pauta_em_processo_arquivado(pub, proc) is None


def test_R7c_R30_NAO_dispara_para_outros_tipos() -> None:
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU, status="Arquivado")
    for tipo in ("Acórdão", "Decisão", "Sentença", "Despacho"):
        pub = _pub(tipoDocumento=tipo)
        assert regra_30_pauta_em_processo_arquivado(pub, proc) is None, tipo


# ===========================================================================
# Round 7c — Regra 31: Atividade em processo arquivado
# ===========================================================================


def test_R7c_R31_dispara_qualquer_pub_em_arquivado() -> None:
    """Heurística: qualquer atividade em processo arquivado é suspeita."""
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU, status="Arquivado")
    for tipo in ("Acórdão", "Decisão", "Despacho", "Notificação"):
        pub = _pub(tipoDocumento=tipo)
        assert regra_31_atividade_em_processo_arquivado(pub, proc) == ALERTA_ATIVIDADE_EM_PROCESSO_ARQUIVADO, tipo


def test_R7c_R31_NAO_dispara_em_ativo() -> None:
    proc = _proc(status="Ativo")
    assert regra_31_atividade_em_processo_arquivado(_pub(), proc) is None


def test_R7c_R31_NAO_dispara_em_arquivado_tema955() -> None:
    proc = _proc(status="Arquivado provisoriamente (tema 955)")
    assert regra_31_atividade_em_processo_arquivado(_pub(), proc) is None


def test_R7c_R31_NAO_dispara_sem_processo_cadastrado() -> None:
    assert regra_31_atividade_em_processo_arquivado(_pub(), None) is None


# ===========================================================================
# Round 7c — Regra 38: Capturar link externo
# ===========================================================================


def test_R7c_R38_dispara_link_proc_vazio_pub_populado() -> None:
    pub = _pub(link="https://pje.trt10.jus.br/pjekz/...")
    proc = _proc(link_externo="")
    assert regra_38_capturar_link_externo(pub, proc) == ALERTA_CAPTURAR_LINK_EXTERNO


def test_R7c_R38_NAO_dispara_se_proc_link_populado() -> None:
    pub = _pub(link="https://pje.trt10.jus.br/")
    proc = _proc(link_externo="https://existing.example.com/proc")
    assert regra_38_capturar_link_externo(pub, proc) is None


def test_R7c_R38_NAO_dispara_se_pub_link_vazio() -> None:
    pub = _pub(link="")
    proc = _proc(link_externo="")
    assert regra_38_capturar_link_externo(pub, proc) is None


def test_R7c_R38_NAO_dispara_sem_processo_cadastrado() -> None:
    pub = _pub(link="https://pje.trt10.jus.br/")
    assert regra_38_capturar_link_externo(pub, None) is None


# ===========================================================================
# Composição Round 7c — Pauta em arquivado dispara R30 + R31 + camada base
# ===========================================================================


def test_R7c_composicao_pauta_arquivado_dispara_R30_R31_R41() -> None:
    """Pauta de Julgamento em processo arquivado:
    - Camada base (Regra 41) → Tarefa: Nada para fazer + Alerta: Incluir julgamento
    - Regra 30 → Pauta em processo arquivado
    - Regra 31 → Atividade em processo arquivado
    """
    pub = _pub(
        tipoComunicacao="Edital",
        tipoDocumento="Pauta de Julgamento",
    )
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU, status="Arquivado")
    tarefas, alertas = aplicar_todas_regras(pub, proc)
    assert tarefas == ["Nada para fazer"]
    assert "Incluir julgamento no controle" in alertas  # camada base R41
    assert ALERTA_PAUTA_EM_PROCESSO_ARQUIVADO in alertas
    assert ALERTA_ATIVIDADE_EM_PROCESSO_ARQUIVADO in alertas
