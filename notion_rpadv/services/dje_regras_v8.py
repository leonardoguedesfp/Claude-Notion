"""Regras v8 (Round 6, 2026-05-04) — Camada base + monitoramento.

Implementa as 43 regras descritas em
``anatomia-processos-vs-publicacoes-v8.md``:

- **Camada base (Regras 40-43)**: matriz Tipo de comunicação × Tipo
  de documento define o par ``(Tarefa sugerida, Alerta contadoria)``
  inicial de cada publicação.

- **Regras de monitoramento (1-39)**: cruzam a publicação com o
  registro de Processos cadastrados e ADICIONAM alertas quando há
  divergência detectada.

A composição funciona assim::

    tarefas_base, alertas_base = aplicar_camada_base(pub)
    alertas_monitor = aplicar_regras_monitoramento(pub, proc, ...)
    alertas_finais = alertas_base + alertas_monitor   # dedup preservando ordem

As constantes neste módulo refletem **exatamente** as opções do
multi-select no schema do Notion (data source
``78070780-8ff2-4532-8f78-9e078967f191``). Bumpe se renomear opções
no Notion.
"""
from __future__ import annotations

from typing import Any

from notion_rpadv.services.dje_notion_mappings import (
    mapear_tipo_comunicacao,
    mapear_tipo_documento,
)

# ---------------------------------------------------------------------------
# Tarefa sugerida (app) — 3 valores no schema do Notion
# ---------------------------------------------------------------------------

TAREFA_ANALISAR_ACORDAO: str = "Analisar acórdão"
TAREFA_ANALISAR_SENTENCA: str = "Analisar sentença"
TAREFA_NADA_PARA_FAZER: str = "Nada para fazer"

#: Conjunto fechado de tarefas que o app pode atribuir automaticamente.
TAREFAS_VALIDAS: frozenset[str] = frozenset({
    TAREFA_ANALISAR_ACORDAO,
    TAREFA_ANALISAR_SENTENCA,
    TAREFA_NADA_PARA_FAZER,
})


# ---------------------------------------------------------------------------
# Alerta contadoria (app) — 41 valores no schema do Notion
# ---------------------------------------------------------------------------

# Camada base — Regras 40 e 41
ALERTA_PROCESSO_RECURSO_DISTRIBUIDO: str = "Processo/recurso distribuído"
ALERTA_INCLUIR_JULGAMENTO_NO_CONTROLE: str = "Incluir julgamento no controle"

# Os demais 39 alertas (correspondendo às Regras 1-39) serão re-introduzidos
# em commits subsequentes deste Round 6, à medida que as regras forem
# implementadas. Por ora apenas as constantes da Camada base são usadas.


# ---------------------------------------------------------------------------
# Camada base (Regras 40-43)
# ---------------------------------------------------------------------------


def aplicar_camada_base(
    publicacao: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Aplica a matriz Tipo de comunicação × Tipo de documento (Regras
    40-43 da v8) e devolve ``(tarefas, alertas)`` como listas
    ordenadas e sem duplicatas.

    A matriz canônica (Seção VII.* do doc v8):

    +------------------------+----------------------+----------------------+----------------------------------+
    | Tipo de comunicação    | Tipo de documento    | Tarefa sugerida      | Alerta contadoria                |
    +========================+======================+======================+==================================+
    | Lista de Distribuição  | (qualquer)           | Nada para fazer      | Processo/recurso distribuído     |
    +------------------------+----------------------+----------------------+----------------------------------+
    | Intimação              | Distribuição         | Nada para fazer      | Processo/recurso distribuído     |
    +------------------------+----------------------+----------------------+----------------------------------+
    | Edital                 | Pauta de Julgamento  | Nada para fazer      | Incluir julgamento no controle   |
    +------------------------+----------------------+----------------------+----------------------------------+
    | Intimação              | Pauta de Julgamento  | Nada para fazer      | Incluir julgamento no controle   |
    +------------------------+----------------------+----------------------+----------------------------------+
    | Intimação              | Sentença             | Analisar sentença    | —                                |
    +------------------------+----------------------+----------------------+----------------------------------+
    | Intimação              | Acórdão              | Analisar acórdão     | —                                |
    +------------------------+----------------------+----------------------+----------------------------------+
    | Intimação              | Ementa               | Analisar acórdão     | —                                |
    +------------------------+----------------------+----------------------+----------------------------------+
    | Edital                 | Outros               | —                    | —                                |
    +------------------------+----------------------+----------------------+----------------------------------+
    | Intimação              | (Decisão / Despacho  | —                    | —                                |
    |                        | / Notificação /      |                      |                                  |
    |                        | Certidão / Outros)   |                      |                                  |
    +------------------------+----------------------+----------------------+----------------------------------+

    Combinações marcadas com "—" não recebem tarefa/alerta automático
    da camada base; ficam disponíveis para regras de monitoramento
    adicionarem alertas quando aplicável.

    Os tipos canônicos vêm dos mapeamentos do Round 1 (1.1) — variantes
    brutas do DJEN como ``"PAUTA DE JULGAMENTOS"`` ou ``"ATA DE
    DISTRIBUIÇÃO"`` já chegam normalizados.
    """
    tipo_com = mapear_tipo_comunicacao(publicacao.get("tipoComunicacao"))
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))

    # Regra 40 — Distribuição (Lista de Distribuição qualquer doc OR
    # Intimação + Distribuição)
    if tipo_com == "Lista de Distribuição":
        return [TAREFA_NADA_PARA_FAZER], [ALERTA_PROCESSO_RECURSO_DISTRIBUIDO]
    if tipo_com == "Intimação" and tipo_doc == "Distribuição":
        return [TAREFA_NADA_PARA_FAZER], [ALERTA_PROCESSO_RECURSO_DISTRIBUIDO]

    # Regra 41 — Pauta de Julgamento (Edital ou Intimação)
    if tipo_doc == "Pauta de Julgamento":
        return [TAREFA_NADA_PARA_FAZER], [ALERTA_INCLUIR_JULGAMENTO_NO_CONTROLE]

    # Regra 42 — Sentença (apenas Intimação)
    if tipo_com == "Intimação" and tipo_doc == "Sentença":
        return [TAREFA_ANALISAR_SENTENCA], []

    # Regra 43 — Acórdão e Ementa (apenas Intimação)
    if tipo_com == "Intimação" and tipo_doc in {"Acórdão", "Ementa"}:
        return [TAREFA_ANALISAR_ACORDAO], []

    # Demais combinações — sem default
    return [], []


# ---------------------------------------------------------------------------
# Regras de monitoramento (1-39) — placeholder
# ---------------------------------------------------------------------------


def aplicar_regras_monitoramento(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
    *,
    cache_conn: Any = None,  # sqlite3.Connection (opt) — para cruzamentos
) -> list[str]:
    """Aplica as Regras 1-39 (monitoramento) e devolve a lista de
    alertas adicionais que dispararam.

    Round 6 — placeholder: as regras serão implementadas em commits
    incrementais por seção (I-VI). Por ora devolve lista vazia.

    Composição com a camada base é responsabilidade do caller (mapper):
    o conjunto final de alertas é a união ``alertas_base ∪
    alertas_monitor`` deduplicada preservando ordem.
    """
    return []


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------


def aplicar_todas_regras(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
    *,
    cache_conn: Any = None,
) -> tuple[list[str], list[str]]:
    """Aplica camada base + monitoramento e devolve ``(tarefas,
    alertas)`` finais.

    Tarefas vêm exclusivamente da camada base (Regras 40-43 da v8 não
    competem entre si — uma pub cai em no máximo uma linha da matriz,
    e cada linha atribui no máximo 1 tarefa). Alertas combinam camada
    base + monitoramento, preservando ordem da primeira aparição.
    """
    tarefas, alertas_base = aplicar_camada_base(publicacao)
    alertas_monitor = aplicar_regras_monitoramento(
        publicacao, processo_record, cache_conn=cache_conn,
    )
    alertas: list[str] = []
    seen: set[str] = set()
    for a in (*alertas_base, *alertas_monitor):
        if a not in seen:
            seen.add(a)
            alertas.append(a)
    return tarefas, alertas
