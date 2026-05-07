"""Vocabulários canônicos de Processos (lê e compara campos do
``processo_record`` recuperado de ``cache.db``)."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Proc.instancia
# ---------------------------------------------------------------------------

INSTANCIA_PRIMEIRO_GRAU: str = "1º grau"
INSTANCIA_SEGUNDO_GRAU: str = "2º grau"
INSTANCIA_TST: str = "TST"
INSTANCIA_STJ: str = "STJ"
INSTANCIA_STF: str = "STF"

#: Instâncias colegiadas (≥ 2º grau). Sentença num cadastro nessas
#: instâncias é categoricamente impossível (AC13).
INSTANCIAS_COLEGIADAS: frozenset[str] = frozenset({
    INSTANCIA_SEGUNDO_GRAU,
    INSTANCIA_TST,
    INSTANCIA_STJ,
    INSTANCIA_STF,
})

#: Ranking monotônico para comparação de instâncias (AC10/AC11). TST e
#: STJ ficam no mesmo nível (3) porque são paralelos: um trabalhista,
#: outro cível. STF é o teto.
RANK_INSTANCIA: dict[str, int] = {
    INSTANCIA_PRIMEIRO_GRAU: 1,
    INSTANCIA_SEGUNDO_GRAU: 2,
    INSTANCIA_TST: 3,
    INSTANCIA_STJ: 3,
    INSTANCIA_STF: 4,
}


# ---------------------------------------------------------------------------
# Proc.fase
# ---------------------------------------------------------------------------

FASE_COGNITIVA: str = "Cognitiva"
FASE_LIQUIDACAO: str = "Liquidação de sentença"
FASE_LIQUIDACAO_PENDENTE: str = "Liquidação pendente"
FASE_EXECUTIVA: str = "Executiva"


# ---------------------------------------------------------------------------
# Proc.natureza
# ---------------------------------------------------------------------------

NATUREZA_TRABALHISTA: str = "Trabalhista"
NATUREZA_CIVEL: str = "Cível"


# ---------------------------------------------------------------------------
# Proc.tipo_de_processo
# ---------------------------------------------------------------------------

TIPO_PROCESSO_PRINCIPAL: str = "Principal"
TIPO_PROCESSO_RECURSO_AUTONOMO: str = "Recurso autônomo"
TIPO_PROCESSO_RECLAMACAO: str = "Reclamação constitucional"
TIPO_PROCESSO_INCIDENTE: str = "Incidente"

#: Tipos de processo que NÃO são "Principal" — exigem ``processo_pai``
#: pela AC25.
TIPOS_PROCESSO_DEPENDENTES: frozenset[str] = frozenset({
    TIPO_PROCESSO_RECURSO_AUTONOMO,
    TIPO_PROCESSO_RECLAMACAO,
    TIPO_PROCESSO_INCIDENTE,
})
