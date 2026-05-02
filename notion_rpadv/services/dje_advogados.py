"""Lista canônica dos 12 advogados do escritório Ricardo Passos Advocacia
para busca de publicações no DJEN.

Editar este arquivo (Python module) é o caminho de update na Fase 1
do Leitor DJE — sem UI de admin. Mesmo critério dos `USUARIOS_LOCAIS`
em `notion_bulk_edit/config.py`.

A chave canônica de busca é a OAB (numeroOab + ufOab) — não nome
do advogado, que é matching parcial sensível a acento. Todos os 12
têm registro DF.
"""
from __future__ import annotations

from typing import Final, TypedDict


class Advogado(TypedDict):
    """Estrutura mínima por advogado."""

    nome: str
    oab: str
    uf: str


# OAB sem ponto (a API do DJEN exige dígitos puros).
ADVOGADOS: Final[list[Advogado]] = [
    {"nome": "Ricardo Luiz Rodrigues da Fonseca Passos", "oab": "15523", "uf": "DF"},
    {"nome": "Leonardo Guedes da Fonseca Passos",        "oab": "36129", "uf": "DF"},
    {"nome": "Vitor Guedes da Fonseca Passos",           "oab": "48468", "uf": "DF"},
    {"nome": "Cecília Maria Lapetina Chiaratto",         "oab": "20120", "uf": "DF"},
    {"nome": "Samantha Lais Soares Mickievicz",          "oab": "38809", "uf": "DF"},
    {"nome": "Juliana Vieira Gomes",                     "oab": "65089", "uf": "DF"},
    {"nome": "Juliana Chiaratto Batista",                "oab": "81225", "uf": "DF"},
    {"nome": "Deborah Nascimento de Castro",             "oab": "75799", "uf": "DF"},
    {"nome": "Shirley Oliveira Pessoa",                  "oab": "37654", "uf": "DF"},
    {"nome": "Erika de Fatima Guedes Montalvan Rosa",    "oab": "39857", "uf": "DF"},
    {"nome": "Maria Isabel Messias Conforti de Carvalho", "oab": "84703", "uf": "DF"},
    {"nome": "Cristiane Peixoto Guedes",                 "oab": "79658", "uf": "DF"},
]


def format_advogado_label(adv: Advogado) -> str:
    """Formato canônico pra coluna ``advogado_consultado`` do xlsx:
    ``"Nome Completo (OAB/UF)"``. Fonte única do critério — usado
    pelo client e pelos testes."""
    return f"{adv['nome']} ({adv['oab']}/{adv['uf']})"
