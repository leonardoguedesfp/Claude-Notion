"""Round 6 (2026-05-04) — testes da Camada base (Regras 40-43 v8).

Cobre a matriz Tipo de comunicação × Tipo de documento conforme
``anatomia-processos-vs-publicacoes-v8.md`` Seção VII.
"""
from __future__ import annotations

from notion_rpadv.services.dje_regras_v8 import (
    ALERTA_INCLUIR_JULGAMENTO_NO_CONTROLE,
    ALERTA_PROCESSO_RECURSO_DISTRIBUIDO,
    TAREFA_ANALISAR_ACORDAO,
    TAREFA_ANALISAR_SENTENCA,
    TAREFA_NADA_PARA_FAZER,
    aplicar_camada_base,
)


def _pub(**kwargs):
    """Helper: monta payload mínimo para teste de camada base."""
    base = {
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Notificação",
    }
    base.update(kwargs)
    return base


# ===========================================================================
# Regra 40 — Distribuição
# ===========================================================================


def test_R6_40_lista_distribuicao_qualquer_tipo_doc() -> None:
    """Lista de Distribuição com qualquer Tipo de documento dispara Regra 40."""
    casos = [
        "Distribuição",
        "Outros",
        "Notificação",
    ]
    for tipo_doc in casos:
        pub = _pub(tipoComunicacao="Lista de Distribuição", tipoDocumento=tipo_doc)
        tarefas, alertas = aplicar_camada_base(pub)
        assert tarefas == [TAREFA_NADA_PARA_FAZER], f"{tipo_doc!r}: {tarefas}"
        assert alertas == [ALERTA_PROCESSO_RECURSO_DISTRIBUIDO], f"{tipo_doc!r}: {alertas}"


def test_R6_40_intimacao_distribuicao_dispara_distribuicao() -> None:
    """Intimação + tipo de documento Distribuição dispara Regra 40
    (caso STJ ATA DE DISTRIBUIÇÃO canonizado para Distribuição)."""
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Distribuição")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == [TAREFA_NADA_PARA_FAZER]
    assert alertas == [ALERTA_PROCESSO_RECURSO_DISTRIBUIDO]


def test_R6_40_intimacao_distribuicao_via_canonizacao_ata() -> None:
    """Tipo bruto 'ATA DE DISTRIBUIÇÃO' canoniza para 'Distribuição'."""
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="ATA DE DISTRIBUIÇÃO")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == [TAREFA_NADA_PARA_FAZER]
    assert alertas == [ALERTA_PROCESSO_RECURSO_DISTRIBUIDO]


# ===========================================================================
# Regra 41 — Pauta de Julgamento
# ===========================================================================


def test_R6_41_edital_pauta_dispara_julgamento() -> None:
    """Edital + Pauta de Julgamento → Regra 41."""
    pub = _pub(tipoComunicacao="Edital", tipoDocumento="Pauta de Julgamento")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == [TAREFA_NADA_PARA_FAZER]
    assert alertas == [ALERTA_INCLUIR_JULGAMENTO_NO_CONTROLE]


def test_R6_41_intimacao_pauta_dispara_julgamento() -> None:
    """Intimação + Pauta de Julgamento → Regra 41 (TJDFT pauta presencial
    individual, casos antes em 'Intimação de pauta')."""
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Pauta de Julgamento")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == [TAREFA_NADA_PARA_FAZER]
    assert alertas == [ALERTA_INCLUIR_JULGAMENTO_NO_CONTROLE]


def test_R6_41_aditamento_pauta_via_canonizacao() -> None:
    """ADITAMENTO À PAUTA DE JULGAMENTOS canoniza para Pauta de Julgamento."""
    pub = _pub(tipoComunicacao="Edital", tipoDocumento="ADITAMENTO À PAUTA DE JULGAMENTOS")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == [TAREFA_NADA_PARA_FAZER]
    assert alertas == [ALERTA_INCLUIR_JULGAMENTO_NO_CONTROLE]


# ===========================================================================
# Regra 42 — Sentença
# ===========================================================================


def test_R6_42_intimacao_sentenca_dispara_analisar_sentenca() -> None:
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Sentença")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == [TAREFA_ANALISAR_SENTENCA]
    assert alertas == []  # camada base não emite alerta para sentença


# ===========================================================================
# Regra 43 — Acórdão e Ementa
# ===========================================================================


def test_R6_43_intimacao_acordao_dispara_analisar_acordao() -> None:
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Acórdão")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == [TAREFA_ANALISAR_ACORDAO]
    assert alertas == []


def test_R6_43_intimacao_ementa_dispara_analisar_acordao() -> None:
    """Ementa também produz Analisar acórdão (mesma tarefa unificada)."""
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Ementa")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == [TAREFA_ANALISAR_ACORDAO]
    assert alertas == []


def test_R6_43_canonizacao_ementa_acordao() -> None:
    """Variantes brutas viram Acórdão ou Ementa pós Round 1.1."""
    casos = [
        ("EMENTA / ACORDÃO", "Acórdão"),
        ("ACORDAO", "Acórdão"),
        ("Acórdão", "Acórdão"),
    ]
    for bruto, _esperado_canon in casos:
        pub = _pub(tipoComunicacao="Intimação", tipoDocumento=bruto)
        tarefas, alertas = aplicar_camada_base(pub)
        assert tarefas == [TAREFA_ANALISAR_ACORDAO], f"{bruto!r}: {tarefas}"
        assert alertas == [], f"{bruto!r}: {alertas}"


# ===========================================================================
# Combinações sem default
# ===========================================================================


def test_R6_camada_base_intimacao_decisao_sem_default() -> None:
    """Intimação + Decisão: nenhuma tarefa nem alerta automático na camada
    base (regras de monitoramento podem adicionar)."""
    pub = _pub(tipoComunicacao="Intimação", tipoDocumento="Decisão")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == []
    assert alertas == []


def test_R6_camada_base_intimacao_outros_documentos_sem_default() -> None:
    """Demais Tipos de documento sob Intimação (Despacho, Notificação,
    Certidão, Outros) também sem default."""
    casos = ["Despacho", "Notificação", "Certidão", "Outros"]
    for tipo_doc in casos:
        pub = _pub(tipoComunicacao="Intimação", tipoDocumento=tipo_doc)
        tarefas, alertas = aplicar_camada_base(pub)
        assert tarefas == [], f"{tipo_doc!r}: {tarefas}"
        assert alertas == [], f"{tipo_doc!r}: {alertas}"


def test_R6_camada_base_edital_outros_sem_default() -> None:
    """Edital com tipo de documento que não é Pauta de Julgamento (ex:
    Atas TJDFT canonizadas como 'Outros')."""
    pub = _pub(tipoComunicacao="Edital", tipoDocumento="Outros")
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == []
    assert alertas == []


def test_R6_camada_base_publicacao_sem_tipos_definidos() -> None:
    """Pub sem tipoComunicacao ou tipoDocumento → mapeamento devolve
    valores fallback ('—' ou similar) e camada base não dispara nada."""
    pub = {}  # sem chaves
    tarefas, alertas = aplicar_camada_base(pub)
    assert tarefas == []
    assert alertas == []


# ===========================================================================
# Sanity: schema do Notion alinhado
# ===========================================================================


def test_R6_constantes_alinhadas_com_schema_notion() -> None:
    """As constantes deste módulo devem corresponder EXATAMENTE aos
    valores no select do Notion (data source 78070780-...).

    Schema atual (confirmado via MCP em 04/05/2026):
    - Tarefa sugerida (app): {Analisar acórdão, Analisar sentença,
      Nada para fazer}
    - Alerta contadoria (app) inclui (entre outros 39): Processo/recurso
      distribuído, Incluir julgamento no controle.
    """
    assert TAREFA_ANALISAR_ACORDAO == "Analisar acórdão"
    assert TAREFA_ANALISAR_SENTENCA == "Analisar sentença"
    assert TAREFA_NADA_PARA_FAZER == "Nada para fazer"
    assert ALERTA_PROCESSO_RECURSO_DISTRIBUIDO == "Processo/recurso distribuído"
    assert ALERTA_INCLUIR_JULGAMENTO_NO_CONTROLE == "Incluir julgamento no controle"
