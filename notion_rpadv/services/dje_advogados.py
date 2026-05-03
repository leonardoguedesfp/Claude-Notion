"""Lista oficial dos advogados consultados pelo Leitor DJE.

Editar este arquivo (Python module) é o caminho de update — sem UI de admin.
Mesmo critério dos ``USUARIOS_LOCAIS`` em ``notion_bulk_edit/config.py``.

A chave canônica de busca é a OAB (numeroOab + ufOab) — não nome
do advogado, que é matching parcial sensível a acento. Todos têm
registro DF.

ATENÇÃO: alterações na lista exigem ajuste paralelo nos testes
``test_dje_client.test_advogados_lista_completa`` e em
``test_dje_advogados`` (regression check da quantidade e dos comentários
preservados). A Regra B do ``dje_transform`` (sócios sentinela = Ricardo
+ Leonardo) NÃO depende desta lista — é hardcoded à parte.
"""
from __future__ import annotations

from typing import Final, TypedDict


class Advogado(TypedDict):
    """Estrutura mínima por advogado."""

    nome: str
    oab: str
    uf: str


# Lista oficial de advogados consultados.
# OAB sem ponto (a API do DJEN exige dígitos puros).
# Para reativar um desativado, descomentar a linha desejada.
#
# 2026-05-02 (pós-Fase 3): reativação dos 4 desativados (Vitor, Cecília,
# Samantha, Deborah). Os cursores deles em ``djen_advogado_state`` estavam
# em 02/05/2026 mas eram FALSOS (não houve smoke de sucesso pra eles); a
# UI agora detecta essa condição na 1ª execução pós-reativação e oferece
# modal de reset dos cursores (zera pra NULL → janela natural reconstrói
# desde 01/01/2026). Ver ``leitor_dje._check_and_offer_reactivation_reset``.
REACTIVATED_2026_05_02_OABS: Final[tuple[tuple[str, str], ...]] = (
    ("48468", "DF"),  # Vitor Guedes da Fonseca Passos
    ("20120", "DF"),  # Cecília Maria Lapetina Chiaratto
    ("38809", "DF"),  # Samantha Lais Soares Mickievicz
    ("75799", "DF"),  # Deborah Nascimento de Castro
)

ADVOGADOS: Final[list[Advogado]] = [
    {"nome": "Ricardo Luiz Rodrigues da Fonseca Passos", "oab": "15523", "uf": "DF"},
    {"nome": "Leonardo Guedes da Fonseca Passos",        "oab": "36129", "uf": "DF"},
    {"nome": "Vitor Guedes da Fonseca Passos",           "oab": "48468", "uf": "DF"},
    {"nome": "Cecília Maria Lapetina Chiaratto",         "oab": "20120", "uf": "DF"},
    {"nome": "Samantha Lais Soares Mickievicz",          "oab": "38809", "uf": "DF"},
    {"nome": "Deborah Nascimento de Castro",             "oab": "75799", "uf": "DF"},
    # ---
    # Desativados antes (Fase 2.1, 2026-05-01).
    # {"nome": "Juliana Vieira Gomes",                     "oab": "65089", "uf": "DF"},
    # {"nome": "Juliana Chiaratto Batista",                "oab": "81225", "uf": "DF"},
    # {"nome": "Shirley Oliveira Pessoa",                  "oab": "37654", "uf": "DF"},
    # {"nome": "Erika de Fatima Guedes Montalvan Rosa",    "oab": "39857", "uf": "DF"},
    # {"nome": "Maria Isabel Messias Conforti de Carvalho", "oab": "84703", "uf": "DF"},
    # {"nome": "Cristiane Peixoto Guedes",                 "oab": "79658", "uf": "DF"},
]


def format_advogado_label(adv: Advogado) -> str:
    """Formato canônico pra coluna ``advogado_consultado`` do xlsx:
    ``"Nome Completo (OAB/UF)"`` quando há nome,
    ``"OAB/UF"`` (puro) quando ``nome == ""``. Fonte única do critério
    — usado pelo client e pelos testes.

    Nome vazio acontece em modo manual (refator pós-Fase 3 hotfix UX):
    o usuário só digita OAB+UF e o nome real é resolvido pelo
    ``dje_transform.split_advogados_columns`` quando o resultado da API
    traz ``destinatarioadvogados`` com a OAB pesquisada — vira
    ``"FULANO DE TAL (OAB/UF)"`` no Excel. Pesquisas sem retorno
    permanecem com label ``"OAB/UF"`` puro (não há de onde extrair nome).
    """
    nome = (adv.get("nome") or "").strip()
    base = f"{adv['oab']}/{adv['uf']}"
    if not nome:
        return base
    return f"{nome} ({base})"
