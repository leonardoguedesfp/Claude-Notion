"""Frozensets de classes CNJ usadas pelas regras AC02, AC11, AC21, AC22,
AC23. Uppercase canônico — comparações sempre passam o lado da Pub por
``.upper()``.
"""
from __future__ import annotations

#: Classes que indicam fase de liquidação (AC22).
CLASSES_LIQUIDACAO: frozenset[str] = frozenset({
    "LIQUIDAÇÃO POR ARBITRAMENTO",
    "LIQUIDAÇÃO PROVISÓRIA POR ARBITRAMENTO",
    "LIQUIDAÇÃO DE SENTENÇA PELO PROCEDIMENTO COMUM",
})

#: Classes que indicam fase executiva (AC21). Inclui Agravo de Petição
#: (CLT 897) por ser recurso típico dentro da fase executiva.
CLASSES_EXECUTIVAS: frozenset[str] = frozenset({
    "CUMPRIMENTO DE SENTENÇA",
    "CUMPRIMENTO PROVISÓRIO DE SENTENÇA",
    "EXECUÇÃO DE TÍTULO EXTRAJUDICIAL",
    "EXECUÇÃO PROVISÓRIA EM AUTOS SUPLEMENTARES",
    "AGRAVO DE PETIÇÃO",
})

#: Classes de **distribuição inicial** (AC23). Recursos em fase
#: avançada ficam fora — a "data de distribuição" no nosso cadastro
#: é a inicial do processo, não a recursal.
CLASSES_DISTRIBUICAO_INICIAL: frozenset[str] = frozenset({
    "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
    "AÇÃO TRABALHISTA - RITO SUMARÍSSIMO",
    "PROCEDIMENTO COMUM CÍVEL",
    "PROCEDIMENTO DO JUIZADO ESPECIAL CÍVEL",
    "JUIZADO ESPECIAL DA FAZENDA PÚBLICA",
})

#: Classes que SÓ existem em justiça trabalhista (AC02).
CLASSES_TRABALHISTAS: frozenset[str] = frozenset({
    "AÇÃO TRABALHISTA - RITO ORDINÁRIO",
    "AÇÃO TRABALHISTA - RITO SUMARÍSSIMO",
    "RECURSO ORDINÁRIO TRABALHISTA",
    "RECURSO ORDINÁRIO - RITO SUMARÍSSIMO",
    "AGRAVO DE PETIÇÃO",
    "AGRAVO REGIMENTAL TRABALHISTA",
    "RECURSO DE REVISTA",
    "RECURSO DE REVISTA COM AGRAVO",
    "AGRAVO DE INSTRUMENTO EM RECURSO DE REVISTA",
})

#: Classes que SÓ existem em justiça cível (AC02).
CLASSES_CIVEIS: frozenset[str] = frozenset({
    "PROCEDIMENTO COMUM CÍVEL",
    "EMBARGOS DE DECLARAÇÃO CÍVEL",
    "APELAÇÃO CÍVEL",
    "AGRAVO INTERNO CÍVEL",
    "PROCEDIMENTO DO JUIZADO ESPECIAL CÍVEL",
    "JUIZADO ESPECIAL DA FAZENDA PÚBLICA",
    "INVENTÁRIO",
    "PETIÇÃO CÍVEL",
})
