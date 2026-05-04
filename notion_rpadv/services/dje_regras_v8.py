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

import re
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

# Regras 14-15 — instância desatualizada (subida/descida)
ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA: str = "Instância desatualizada (subida)"
ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA: str = "Instância desatualizada (descida)"

# Regras 16-18 — impossibilidades categóricas (Tipo de documento × Proc.Instância)
ALERTA_ACORDAO_EM_1GRAU: str = "Acórdão em processo de 1º grau"
ALERTA_SENTENCA_EM_COLEGIADO: str = "Sentença em processo de colegiado"
ALERTA_PAUTA_EM_1GRAU: str = "Pauta em processo de 1º grau"

# Regras 26-28 — fase desatualizada (Pub.Classe × Proc.Fase)
ALERTA_FASE_DESATUALIZADA_EXECUTIVA: str = "Fase desatualizada (executiva)"
ALERTA_FASE_DESATUALIZADA_LIQUIDACAO: str = "Fase desatualizada (liquidação)"
ALERTA_FASE_DESATUALIZADA_COGNITIVA: str = "Fase desatualizada (cognitiva)"

# Regra 35 — Trânsito em julgado pendente (mantido do Round 4.4)
ALERTA_TRANSITO_PENDENTE: str = "Trânsito em julgado pendente"

# Regra 11 — Partes adversas típicas ausentes (5 alertas distintos)
ALERTA_PARTE_ADVERSA_BB: str = "Banco do Brasil ausente em partes adversas"
ALERTA_PARTE_ADVERSA_PREVI: str = "PREVI ausente em partes adversas"
ALERTA_PARTE_ADVERSA_CASSI: str = "CASSI ausente em partes adversas"
ALERTA_PARTE_ADVERSA_BRADESCO_SAUDE: str = "Bradesco Saúde ausente em partes adversas"
ALERTA_PARTE_ADVERSA_BB_CONSORCIOS: str = "BB Adm. Consórcios ausente em partes adversas"

# Alertas mantidos do Round 4 (técnicos/operacionais — sem número no doc v8)
ALERTA_PROCESSO_NAO_CADASTRADO: str = "Processo não cadastrado"
ALERTA_TEXTO_IMPRESTAVEL: str = "Texto imprestável"

# Os demais 24 alertas (Regras 1-10, 12-13, 19-25, 29-34, 36-39) serão
# re-introduzidos em commits subsequentes deste Round 6.

# ---------------------------------------------------------------------------
# Vocabulário canônico de Proc.Instância (para regras de cruzamento)
# ---------------------------------------------------------------------------

INSTANCIA_PRIMEIRO_GRAU: str = "1º grau"
INSTANCIA_SEGUNDO_GRAU: str = "2º grau"
INSTANCIA_TST: str = "TST"
INSTANCIA_STJ: str = "STJ"
INSTANCIA_STF: str = "STF"

#: Instâncias colegiadas (≥ 2º grau) — qualquer ato de Sentença
#: cadastrado nelas indica inconsistência (Regra 17).
INSTANCIAS_COLEGIADAS: frozenset[str] = frozenset({
    INSTANCIA_SEGUNDO_GRAU,
    INSTANCIA_TST,
    INSTANCIA_STJ,
    INSTANCIA_STF,
})


# ---------------------------------------------------------------------------
# Tabela A — instancia_implicada(Pub)
# ---------------------------------------------------------------------------

# Ranking numérico para comparação monotônica (Regras 14, 15).
# TST e STJ ficam no mesmo nível (3) porque são paralelos: um trabalhista,
# outro cível. STF é o teto absoluto.
_RANK_INSTANCIA: dict[str, int] = {
    INSTANCIA_PRIMEIRO_GRAU: 1,
    INSTANCIA_SEGUNDO_GRAU: 2,
    INSTANCIA_TST: 3,
    INSTANCIA_STJ: 3,
    INSTANCIA_STF: 4,
}

# Regex de Órgão para inferência de instância. Casamento case-insensitive.
_RX_VARA_TRABALHO = re.compile(r"\d+ª\s*Vara do Trabalho", re.IGNORECASE)
_RX_VARA_CIVEL = re.compile(r"\d+ª\s*Vara Cível", re.IGNORECASE)
_RX_VARA_FAZENDA = re.compile(r"Vara da Fazenda", re.IGNORECASE)
_RX_JUIZADO = re.compile(r"Juizado", re.IGNORECASE)
_RX_DESEMBARGADOR = re.compile(r"^\s*Desembargador[a]?\b", re.IGNORECASE)
_RX_JUIZ_CONVOCADO = re.compile(r"^\s*Juiz[a]?\s+Convocad[oa]\b", re.IGNORECASE)
_RX_TURMA_CAMARA = re.compile(r"\d+ª\s*(Turma|Câmara)(\s*Cível)?\s*$", re.IGNORECASE)


def instancia_implicada(publicacao: dict[str, Any]) -> str | None:
    """Tabela A da v8 — infere a instância da publicação a partir de
    Tribunal, Tipo de documento e Órgão.

    Devolve uma das 5 strings canônicas (1º grau, 2º grau, TST, STJ,
    STF) ou ``None`` se a inferência não der signal claro.

    Ordem de prioridade (mais específico → mais genérico):

    1. Tribunal STJ/TST/STF: instância = própria sigla.
    2. Tipo de documento Sentença → 1º grau (sentença é ato singular).
    3. Tipo de documento Acórdão ou Pauta de Julgamento → 2º grau
       (atos colegiados; valor padrão "2º grau" — o tribunal preciso
       sai pelo Tribunal acima quando for STJ/TST/STF).
    4. Órgão match Vara do Trabalho/Cível/Fazenda/Juizado → 1º grau.
    5. Órgão match Desembargador/Juiz Convocado/Turma/Câmara → 2º grau.
    6. Caso contrário → ``None`` (inferência não conclusiva — não
       dispara regras de monitoramento que dependem dela).

    Quando inferências contradizem (ex: Vara do Trabalho com Acórdão),
    o tipo de documento DOMINA — Regras 16-18 já capturam esses casos
    como impossibilidades categóricas.
    """
    sigla = (publicacao.get("siglaTribunal") or "").strip().upper()
    if sigla == "STF":
        return INSTANCIA_STF
    if sigla == "STJ":
        return INSTANCIA_STJ
    if sigla == "TST":
        return INSTANCIA_TST

    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc == "Sentença":
        return INSTANCIA_PRIMEIRO_GRAU
    if tipo_doc in ("Acórdão", "Ementa", "Pauta de Julgamento"):
        return INSTANCIA_SEGUNDO_GRAU

    orgao = (publicacao.get("nomeOrgao") or "").strip()
    if not orgao:
        return None
    if (
        _RX_VARA_TRABALHO.search(orgao)
        or _RX_VARA_CIVEL.search(orgao)
        or _RX_VARA_FAZENDA.search(orgao)
        or _RX_JUIZADO.search(orgao)
    ):
        return INSTANCIA_PRIMEIRO_GRAU
    if (
        _RX_DESEMBARGADOR.search(orgao)
        or _RX_JUIZ_CONVOCADO.search(orgao)
        or _RX_TURMA_CAMARA.search(orgao)
    ):
        return INSTANCIA_SEGUNDO_GRAU
    return None


# ---------------------------------------------------------------------------
# Tabela B — fase_implicada(Pub)
# ---------------------------------------------------------------------------

FASE_COGNITIVA: str = "Cognitiva"
FASE_LIQUIDACAO: str = "Liquidação de sentença"
FASE_LIQUIDACAO_PENDENTE: str = "Liquidação pendente"
FASE_EXECUTIVA: str = "Executiva"

#: Classes que indicam fase cognitiva (peças iniciais do processo).
_CLASSES_COGNITIVAS: frozenset[str] = frozenset({
    "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
    "AÇÃO TRABALHISTA - RITO SUMARÍSSIMO",
    "PROCEDIMENTO COMUM CÍVEL",
    "PROCEDIMENTO DO JUIZADO ESPECIAL CÍVEL",
    "JUIZADO ESPECIAL DA FAZENDA PÚBLICA",
    "INVENTÁRIO",
    "PETIÇÃO CÍVEL",
})

#: Classes que indicam fase de liquidação.
_CLASSES_LIQUIDACAO: frozenset[str] = frozenset({
    "LIQUIDAÇÃO POR ARBITRAMENTO",
    "LIQUIDAÇÃO PROVISÓRIA POR ARBITRAMENTO",
    "LIQUIDAÇÃO DE SENTENÇA PELO PROCEDIMENTO COMUM",
})

#: Classes que indicam fase executiva.
_CLASSES_EXECUTIVAS: frozenset[str] = frozenset({
    "CUMPRIMENTO DE SENTENÇA",
    "CUMPRIMENTO PROVISÓRIO DE SENTENÇA",
    "EXECUÇÃO DE TÍTULO EXTRAJUDICIAL",
    "EXECUÇÃO PROVISÓRIA EM AUTOS SUPLEMENTARES",
    "AGRAVO DE PETIÇÃO",  # CLT 897 — recurso dentro da executiva
})


def fase_implicada(publicacao: dict[str, Any]) -> str | None:
    """Tabela B da v8 — infere a fase processual a partir de Pub.Classe.

    Devolve ``Cognitiva``, ``Liquidação de sentença`` ou ``Executiva``
    quando a classe é discriminante; ``None`` quando a classe é
    recurso não-AP ou outro ato que herda fase do principal.
    """
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if not classe:
        return None
    if classe in _CLASSES_COGNITIVAS:
        return FASE_COGNITIVA
    if classe in _CLASSES_LIQUIDACAO:
        return FASE_LIQUIDACAO
    if classe in _CLASSES_EXECUTIVAS:
        return FASE_EXECUTIVA
    return None


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


def regra_14_subida_nao_detectada(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Regra 14 — Subida de instância não detectada no cadastro.

    - Condições: ``instancia_implicada(Pub)`` > ``Proc.Instância`` no
      ranking (1º grau < 2º grau < TST/STJ < STF).
    - Alerta: ``Instância desatualizada (subida)``.
    - Explicação: o processo subiu (foi para tribunal superior ou
      colegiado), mas o cadastro não acompanhou. Substitui o antigo
      "Instância desatualizada" do Round 4 — mais preciso.
    """
    if processo_record is None:
        return None
    instancia_pub = instancia_implicada(publicacao)
    if instancia_pub is None:
        return None
    instancia_proc = (processo_record.get("instancia") or "").strip()
    if not instancia_proc:
        return None
    rank_pub = _RANK_INSTANCIA.get(instancia_pub)
    rank_proc = _RANK_INSTANCIA.get(instancia_proc)
    if rank_pub is None or rank_proc is None:
        return None
    if rank_pub > rank_proc:
        return ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA
    return None


def regra_15_descida_nao_detectada(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Regra 15 — Descida/devolução não detectada no cadastro.

    - Condições: ``instancia_implicada(Pub)`` < ``Proc.Instância`` E
      ``Pub.Classe`` NÃO é cumprimento/liquidação (essas classes em
      1ª instância são descida legítima — processo voltou para vara
      executar acórdão; não é erro de cadastro).
    - Alerta: ``Instância desatualizada (descida)``.
    - Explicação: filtro de classes evita falsos positivos sistemáticos
      quando o processo retorna legitimamente para 1º grau.
    """
    if processo_record is None:
        return None
    instancia_pub = instancia_implicada(publicacao)
    if instancia_pub is None:
        return None
    instancia_proc = (processo_record.get("instancia") or "").strip()
    if not instancia_proc:
        return None
    rank_pub = _RANK_INSTANCIA.get(instancia_pub)
    rank_proc = _RANK_INSTANCIA.get(instancia_proc)
    if rank_pub is None or rank_proc is None:
        return None
    if rank_pub >= rank_proc:
        return None
    # Filtro: cumprimento/liquidação em 1ª instância é descida legítima
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if (
        classe in _CLASSES_EXECUTIVAS
        or classe in _CLASSES_LIQUIDACAO
    ):
        return None
    return ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA


def regra_16_acordao_em_1grau(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Regra 16 — Acórdão em 1º grau (categoricamente impossível).

    - Condições: Pub.Tipo de documento canônico = Acórdão **e**
      Proc.Instância = "1º grau".
    - Alerta: ``Acórdão em processo de 1º grau``.
    - Explicação: acórdão é ato de colegiado; juízo singular não emite.
      Se a publicação traz acórdão, a instância cadastrada está abaixo
      da real — operador deve conferir o cadastro.
    """
    if processo_record is None:
        return None
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc != "Acórdão":
        return None
    instancia = (processo_record.get("instancia") or "").strip()
    if instancia == INSTANCIA_PRIMEIRO_GRAU:
        return ALERTA_ACORDAO_EM_1GRAU
    return None


def regra_17_sentenca_em_colegiado(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Regra 17 — Sentença em colegiado (categoricamente impossível).

    - Condições: Pub.Tipo de documento canônico = Sentença **e**
      Proc.Instância em {2º grau, TST, STJ, STF}.
    - Alerta: ``Sentença em processo de colegiado``.
    - Explicação: sentença é ato de juiz singular; colegiado emite
      acórdão. Se a publicação traz sentença, a instância cadastrada
      está acima da real (provavelmente o processo voltou para 1º
      grau e o cadastro não acompanhou).
    """
    if processo_record is None:
        return None
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc != "Sentença":
        return None
    instancia = (processo_record.get("instancia") or "").strip()
    if instancia in INSTANCIAS_COLEGIADAS:
        return ALERTA_SENTENCA_EM_COLEGIADO
    return None


def regra_18_pauta_em_1grau(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Regra 18 — Pauta de Julgamento em 1º grau (categoricamente impossível).

    - Condições: Pub.Tipo de documento canônico = Pauta de Julgamento
      **e** Proc.Instância = "1º grau".
    - Alerta: ``Pauta em processo de 1º grau``.
    - Explicação: pauta de julgamento só existe em colegiado.
    """
    if processo_record is None:
        return None
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc != "Pauta de Julgamento":
        return None
    instancia = (processo_record.get("instancia") or "").strip()
    if instancia == INSTANCIA_PRIMEIRO_GRAU:
        return ALERTA_PAUTA_EM_1GRAU
    return None


def regra_26_fase_executiva_por_classe(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Regra 26 — Fase executiva confirmada por classe.

    - Condições: Pub.Classe em {CUMPRIMENTO DE SENTENÇA,
      CUMPRIMENTO PROVISÓRIO DE SENTENÇA, EXECUÇÃO DE TÍTULO
      EXTRAJUDICIAL, EXECUÇÃO PROVISÓRIA EM AUTOS SUPLEMENTARES,
      AGRAVO DE PETIÇÃO} **e** Proc.Fase ≠ Executiva.
    - Alerta: ``Fase desatualizada (executiva)``.
    - Explicação: a classe da publicação determina a fase com certeza —
      se diverge da cadastrada, cadastro está errado. 234 candidatos
      no universo atual.
    """
    if processo_record is None:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if classe not in _CLASSES_EXECUTIVAS:
        return None
    fase_proc = (processo_record.get("fase") or "").strip()
    if fase_proc != FASE_EXECUTIVA:
        return ALERTA_FASE_DESATUALIZADA_EXECUTIVA
    return None


def regra_27_fase_liquidacao_por_classe(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Regra 27 — Fase liquidação confirmada por classe.

    - Condições: Pub.Classe em {LIQUIDAÇÃO POR ARBITRAMENTO,
      LIQUIDAÇÃO PROVISÓRIA POR ARBITRAMENTO, LIQUIDAÇÃO DE SENTENÇA
      PELO PROCEDIMENTO COMUM} **e** Proc.Fase NÃO em {Liquidação
      pendente, Liquidação de sentença}.
    - Alerta: ``Fase desatualizada (liquidação)``.
    - Explicação: análoga à Regra 26. 43 candidatos no universo.
    """
    if processo_record is None:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if classe not in _CLASSES_LIQUIDACAO:
        return None
    fase_proc = (processo_record.get("fase") or "").strip()
    if fase_proc not in (FASE_LIQUIDACAO, FASE_LIQUIDACAO_PENDENTE):
        return ALERTA_FASE_DESATUALIZADA_LIQUIDACAO
    return None


def regra_35_transito_pendente(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Regra 35 — Trânsito cognitivo pendente.

    - Condições: Pub.Classe = "CUMPRIMENTO DE SENTENÇA" (não inclui
      CUMPRIMENTO PROVISÓRIO) **e** Proc.Data do trânsito em julgado
      (cognitiva) vazia.
    - Alerta: ``Trânsito em julgado pendente`` (mantido do Round 4.4).
    - Explicação: cumprimento definitivo só roda após trânsito da fase
      cognitiva. 100% dos 71 alertas vivos do Round 4 tinham
      classe=CUMPRIMENTO DE SENTENÇA. Mantém alerta sem alteração.
    """
    if processo_record is None:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    # Cumprimento DEFINITIVO apenas — provisório é antes do trânsito
    if classe != "CUMPRIMENTO DE SENTENÇA":
        return None
    t_cog = processo_record.get("data_do_transito_em_julgado_cognitiva")
    t_exec = processo_record.get("data_do_transito_em_julgado_executiva")
    if not t_cog and not t_exec:
        return ALERTA_TRANSITO_PENDENTE
    return None


# ---------------------------------------------------------------------------
# Regra 11 — Partes adversas típicas ausentes
# ---------------------------------------------------------------------------

#: Tabela de mapeamento: substring em Pub.Partes → (item esperado em
#: Proc.Partes adversas, alerta a disparar). Cada match em Pub.Partes
#: que não tem entrada correspondente em Proc.Partes adversas dispara
#: o alerta. 5 alertas distintos (decisão de design da v8 X.5).
_PARTES_ADVERSAS_TIPICAS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # (substrings em Pub.Partes; nome canônico em Proc.Partes adversas; alerta)
    (
        ("BANCO DO BRASIL S/A", "BANCO DO BRASIL S.A.", "BANCO DO BRASIL SA", "BANCO DO BRASIL"),
        "Banco do Brasil",
        ALERTA_PARTE_ADVERSA_BB,
    ),
    (
        (
            "CAIXA DE PREVIDENCIA DOS FUNC",
            "CAIXA DE PREVIDÊNCIA DOS FUNC",
            "PREVI",
        ),
        "PREVI",
        ALERTA_PARTE_ADVERSA_PREVI,
    ),
    (
        ("CASSI",),
        "CASSI",
        ALERTA_PARTE_ADVERSA_CASSI,
    ),
    (
        ("BRADESCO SAÚDE", "BRADESCO SAUDE", "BRADESCO SEGUROS"),
        "Bradesco Saúde",
        ALERTA_PARTE_ADVERSA_BRADESCO_SAUDE,
    ),
    (
        ("BB ADMINISTRADORA DE CONSÓRCIOS", "BB ADMINISTRADORA DE CONSORCIOS"),
        "BB Adm. Consórcios",
        ALERTA_PARTE_ADVERSA_BB_CONSORCIOS,
    ),
)


def _normalizar_partes_adversas_proc(
    processo_record: dict[str, Any],
) -> set[str]:
    """Lê ``Proc.Partes adversas`` (lista canônica) e devolve set
    normalizado em uppercase para comparação."""
    raw = processo_record.get("partes_adversas") or []
    if isinstance(raw, str):
        # Pode vir como string com vírgulas (ex: rollup ou import bruto)
        raw = [p.strip() for p in raw.split(",")]
    out: set[str] = set()
    for item in raw:
        s = str(item).strip().upper()
        if s:
            out.add(s)
    return out


def _texto_partes_pub(publicacao: dict[str, Any]) -> str:
    """Junta nomes dos destinatários da Pub em uma string única
    uppercase para busca por substring."""
    destinatarios = publicacao.get("destinatarios") or []
    nomes: list[str] = []
    for d in destinatarios:
        if isinstance(d, dict):
            nome = str(d.get("nome") or "").strip()
            if nome:
                nomes.append(nome)
    return " | ".join(nomes).upper()


def regra_11_partes_adversas_ausentes(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> list[str]:
    """Regra 11 — Parte adversa típica ausente do cadastro.

    Para cada parte adversa do catálogo do escritório (BB, PREVI, CASSI,
    Bradesco Saúde, BB Adm. Consórcios) que aparece em ``Pub.Partes`` mas
    NÃO está em ``Proc.Partes adversas``, dispara o alerta correspondente.
    Pode disparar múltiplos alertas (até 5) em uma única publicação.
    """
    if processo_record is None:
        return []
    texto = _texto_partes_pub(publicacao)
    if not texto:
        return []
    proc_partes = _normalizar_partes_adversas_proc(processo_record)

    alertas: list[str] = []
    for substrings, canonico, alerta in _PARTES_ADVERSAS_TIPICAS:
        # Match em Pub.Partes
        if not any(sub in texto for sub in substrings):
            continue
        # Já está em Proc.Partes adversas?
        canon_upper = canonico.upper()
        if canon_upper in proc_partes:
            continue
        # Heurística adicional: alguns nomes em Proc.Partes podem usar
        # variantes (ex: "BANCO DO BRASIL" sem S/A). Aceita se substring
        # aparece em alguma das partes cadastradas.
        if any(canon_upper in p or p in canon_upper for p in proc_partes if p):
            continue
        alertas.append(alerta)
    return alertas


# ---------------------------------------------------------------------------
# Alertas mantidos do Round 4 (sem número formal na v8)
# ---------------------------------------------------------------------------


def _texto_e_imprestavel(texto: str) -> bool:
    """Detecção conservadora de texto imprestável — apenas as classes
    conhecidas vistas em produção. NÃO dispara em despachos breves
    legítimos.

    Classes detectadas:
    - TJGO: ``"ARQUIVOS DIGITAIS INDISPONÍVEIS (NÃO SÃO DO TIPO PÚBLICO)"``.
    - Despachos minimalistas: ``"Intime-se."``, ``"Intimem-se."``.
    - TRT10 só com referência a ID: ``"Tomar ciência do(a) Intimação de
      ID..."`` SEM CNJ no texto.
    """
    if not texto:
        return False
    t = texto.strip()
    if "ARQUIVOS DIGITAIS INDISPONÍVEIS" in t:
        return True
    if t in ("Intime-se.", "Intimem-se."):
        return True
    if "Tomar ciência" in t and "Intimação de ID" in t:
        if not re.search(r"\d{7}-\d{2}", t):
            return True
    return False


def regra_texto_imprestavel(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Alerta técnico — texto imprestável para análise (mantido do
    Round 4.4). Não corresponde a nenhuma Regra numerada do doc v8;
    é classificação de qualidade do conteúdo recebido do DJEN.

    Independe de ``processo_record`` — é alerta puro sobre o conteúdo
    da publicação.
    """
    texto = publicacao.get("texto") or ""
    if len(texto) < 200 and _texto_e_imprestavel(texto):
        return ALERTA_TEXTO_IMPRESTAVEL
    return None


def regra_processo_nao_cadastrado(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Alerta operacional — processo da publicação não está cadastrado
    em ⚖️ Processos.

    Refinamento da v8 (X.5): este alerta dispara apenas em pubs que
    **não** são distribuição. Distribuições (Lista de Distribuição
    qualquer doc, ou Intimação + Distribuição) já recebem
    ``Processo/recurso distribuído`` da Camada base (Regra 40), que é
    a forma correta de sinalizar "cadastrar este processo" no fluxo
    novo. Disparar os dois redundantemente polui o multi-select.
    """
    if processo_record is not None:
        return None
    # Filtra: distribuições já têm o sinal certo da Camada base
    tipo_com = mapear_tipo_comunicacao(publicacao.get("tipoComunicacao"))
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_com == "Lista de Distribuição":
        return None
    if tipo_com == "Intimação" and tipo_doc == "Distribuição":
        return None
    return ALERTA_PROCESSO_NAO_CADASTRADO


def regra_28_fase_cognitiva_contradita_por_classe(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> str | None:
    """Regra 28 — Fase cognitiva contradita por classe avançada.

    - Condições: Pub.Classe em classes cognitivas (AÇÃO TRABALHISTA -
      RITO ORDINÁRIO/SUMARÍSSIMO, PROCEDIMENTO COMUM CÍVEL, JUIZADO
      ESPECIAL CÍVEL/FAZENDA PÚBLICA, PETIÇÃO CÍVEL, INVENTÁRIO) **e**
      Proc.Fase em {Executiva, Liquidação de sentença}.
    - Alerta: ``Fase desatualizada (cognitiva)``.
    - Explicação: atos cognitivos em processo cadastrado como
      executivo/liquidação indicam retrocesso de fase ou cadastro
      errado.
    """
    if processo_record is None:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if classe not in _CLASSES_COGNITIVAS:
        return None
    fase_proc = (processo_record.get("fase") or "").strip()
    if fase_proc in (FASE_EXECUTIVA, FASE_LIQUIDACAO):
        return ALERTA_FASE_DESATUALIZADA_COGNITIVA
    return None


def aplicar_regras_monitoramento(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
    *,
    cache_conn: Any = None,  # sqlite3.Connection (opt) — para cruzamentos
) -> list[str]:
    """Aplica as Regras 1-39 (monitoramento) e devolve a lista de
    alertas adicionais que dispararam, deduplicada e em ordem
    determinística.

    As regras de monitoramento ADICIONAM alertas ao conjunto produzido
    pela camada base — não substituem.

    Round 6 — implementadas até o momento:

    - Regras 14, 15 (subida e descida de instância).
    - Regras 16, 17, 18 (impossibilidades categóricas).
    - Regras 26, 27, 28 (fase desatualizada por classe).
    - Regra 11 (partes adversas típicas ausentes — 5 alertas).
    - Regra 35 (trânsito cognitivo pendente).
    - Alerta técnico Texto imprestável (sem número formal na v8).
    - Alerta operacional Processo não cadastrado (refinado: não
      dispara em distribuições, que já têm Camada base).

    Pendentes (a serem acrescentadas em commits subsequentes):

    - Regras 1-3 (Identificação e numeração).
    - Regras 4-6 (Classificação processual).
    - Regras 7-9 (Cliente do escritório).
    - Regras 10 (Posição do cliente).
    - Regras 12-13 (Tribunal).
    - Regras 19-25 (Cidade, Vara, Turma, Relator).
    - Regras 29-34, 36-39 (demais de Estado processual + outros).
    """
    candidatos: list[str | None] = [
        regra_14_subida_nao_detectada(publicacao, processo_record),
        regra_15_descida_nao_detectada(publicacao, processo_record),
        regra_16_acordao_em_1grau(publicacao, processo_record),
        regra_17_sentenca_em_colegiado(publicacao, processo_record),
        regra_18_pauta_em_1grau(publicacao, processo_record),
        regra_26_fase_executiva_por_classe(publicacao, processo_record),
        regra_27_fase_liquidacao_por_classe(publicacao, processo_record),
        regra_28_fase_cognitiva_contradita_por_classe(publicacao, processo_record),
        regra_35_transito_pendente(publicacao, processo_record),
        regra_texto_imprestavel(publicacao, processo_record),
        regra_processo_nao_cadastrado(publicacao, processo_record),
    ]
    # Regra 11 devolve lista — espalha individualmente
    candidatos.extend(regra_11_partes_adversas_ausentes(publicacao, processo_record))

    alertas: list[str] = []
    seen: set[str] = set()
    for alerta in candidatos:
        if alerta is None or alerta in seen:
            continue
        seen.add(alerta)
        alertas.append(alerta)
    return alertas


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
