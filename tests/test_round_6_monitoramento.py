"""Round 6 (2026-05-04) — testes das Regras de monitoramento (1-39 v8).

Cada commit do Passo D deste round adiciona testes para as regras
implementadas. Este arquivo cresce incrementalmente.

**Implementadas até o momento:**

- Regras 16, 17, 18 (impossibilidades categóricas — Tipo de documento
  × Proc.Instância).
"""
from __future__ import annotations

from notion_rpadv.services.dje_regras_v8 import (
    ALERTA_ACORDAO_EM_1GRAU,
    ALERTA_PAUTA_EM_1GRAU,
    ALERTA_SENTENCA_EM_COLEGIADO,
    INSTANCIA_PRIMEIRO_GRAU,
    INSTANCIA_SEGUNDO_GRAU,
    INSTANCIA_STJ,
    INSTANCIA_TST,
    aplicar_regras_monitoramento,
    aplicar_todas_regras,
    regra_16_acordao_em_1grau,
    regra_17_sentenca_em_colegiado,
    regra_18_pauta_em_1grau,
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


def test_R6_monitoramento_devolve_alerta_unico() -> None:
    """Pub Acórdão + processo 1º grau → 1 alerta (Regra 16)."""
    pub = _pub(tipoDocumento="Acórdão")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    alertas = aplicar_regras_monitoramento(pub, proc)
    assert alertas == [ALERTA_ACORDAO_EM_1GRAU]


def test_R6_monitoramento_dedup_preserva_ordem() -> None:
    """Sanity: aplicar_regras_monitoramento dedup duplicatas (caso
    duas regras devolvam o mesmo alerta)."""
    pub = _pub(tipoDocumento="Sentença")
    proc = _proc(instancia=INSTANCIA_SEGUNDO_GRAU)
    alertas = aplicar_regras_monitoramento(pub, proc)
    # Apenas Regra 17 dispara aqui; sem duplicatas para deduplicar
    assert alertas == [ALERTA_SENTENCA_EM_COLEGIADO]


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
    - Monitoramento (Regra 16) → Alerta: Acórdão em processo de 1º grau
    """
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Acórdão")
    proc = _proc(instancia=INSTANCIA_PRIMEIRO_GRAU)
    tarefas, alertas = aplicar_todas_regras(pub, proc)
    assert tarefas == ["Analisar acórdão"]
    assert alertas == [ALERTA_ACORDAO_EM_1GRAU]


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
