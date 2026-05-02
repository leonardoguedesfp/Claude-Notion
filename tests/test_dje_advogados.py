"""Testes da lista oficial ``ADVOGADOS`` em ``dje_advogados.py``.

Fase 2.1 (2026-05-01) reduziu a lista de 12 para 6 advogados ativos.
Os 6 desativados ficam comentados (não deletados) com cabeçalho explicativo —
caso operacional muda, descomenta-se a linha desejada.

Estes testes garantem:
- F21-13: contagem de advogados ativos = 6
- F21-14: as 6 OABs ativas estão presentes e corretas
- F21-15: as 6 OABs desativadas continuam no arquivo (linha comentada),
  protegendo contra deleção acidental.
"""
from __future__ import annotations

from pathlib import Path

OABS_ATIVAS = (
    "15523",  # Ricardo Luiz Rodrigues da Fonseca Passos
    "36129",  # Leonardo Guedes da Fonseca Passos
    "48468",  # Vitor Guedes da Fonseca Passos
    "20120",  # Cecília Maria Lapetina Chiaratto
    "38809",  # Samantha Lais Soares Mickievicz
    "75799",  # Deborah Nascimento de Castro
)

OABS_DESATIVADAS = (
    "65089",  # Juliana Vieira Gomes
    "81225",  # Juliana Chiaratto Batista
    "37654",  # Shirley Oliveira Pessoa
    "39857",  # Erika de Fatima Guedes Montalvan Rosa
    "84703",  # Maria Isabel Messias Conforti de Carvalho
    "79658",  # Cristiane Peixoto Guedes
)


def test_F21_13_lista_ativa_tem_6_entradas() -> None:
    """ADVOGADOS tem exatamente 6 entradas (Fase 2.1: era 12)."""
    from notion_rpadv.services.dje_advogados import ADVOGADOS
    assert len(ADVOGADOS) == 6


def test_F21_14_oabs_ativas_corretas() -> None:
    """As 6 OABs ativas correspondem aos sócios+colaboradores mantidos
    em 2026-05-01."""
    from notion_rpadv.services.dje_advogados import ADVOGADOS
    oabs_no_modulo = {a["oab"] for a in ADVOGADOS}
    assert oabs_no_modulo == set(OABS_ATIVAS), (
        f"OABs ativas inesperadas. esperado={set(OABS_ATIVAS)} "
        f"obtido={oabs_no_modulo}"
    )
    # Cada entrada também tem nome e UF=DF preenchidos.
    for adv in ADVOGADOS:
        assert adv["uf"] == "DF"
        assert adv["nome"].strip()


def test_F21_15_oabs_desativadas_preservadas_no_arquivo_comentado() -> None:
    """Regression check: as 6 OABs desativadas devem aparecer literalmente
    no source de ``dje_advogados.py`` (comentadas, não deletadas).

    Protege contra um cleanup futuro que remova as linhas — se o operador
    quiser reativar, o caminho oficial é descomentar a linha original."""
    # Resolve via __file__ pra ser robusto a diferenças de cwd.
    repo_root = Path(__file__).resolve().parent.parent
    src = (
        repo_root / "notion_rpadv" / "services" / "dje_advogados.py"
    ).read_text(encoding="utf-8")
    for oab in OABS_DESATIVADAS:
        assert oab in src, (
            f"OAB {oab} (desativada) não está mais no arquivo — "
            "linha pode ter sido deletada em vez de comentada."
        )
    # Garantia adicional: as 6 OABs desativadas aparecem em LINHAS
    # comentadas (começam com ``#`` antes da chave do dict).
    for oab in OABS_DESATIVADAS:
        # Procura padrão "# {"nome": ..., "oab": "<oab>"
        # — busca tolerante a espaços extras.
        linhas = [
            ln for ln in src.splitlines()
            if oab in ln
        ]
        assert linhas, f"OAB {oab} sumiu (já checado acima, mas pra clareza)"
        for ln in linhas:
            stripped = ln.strip()
            assert stripped.startswith("#"), (
                f"OAB {oab} apareceu em linha NÃO comentada: {ln!r}. "
                "Lista de desativados deve ficar comentada."
            )
