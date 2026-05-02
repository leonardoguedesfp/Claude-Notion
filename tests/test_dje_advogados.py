"""Testes da lista oficial ``ADVOGADOS`` em ``dje_advogados.py``.

Histórico:
- Fase 2.1 (2026-05-01): lista reduzida de 12 → 6.
- Pós-smoke real do refator watermark-por-advogado (02/05/2026): lista
  reduzida de 6 → 2 (Ricardo + Leonardo) por sobrecarga 429 da API DJEN
  em janelas longas. Reativar quando watermark estiver consolidado e
  volume diário sem 429.

Os advogados desativados ficam comentados (não deletados) com cabeçalho
explicativo — caso operacional muda, descomenta-se a linha desejada.

Estes testes garantem:
- contagem de advogados ativos
- OABs ativas presentes e corretas
- OABs desativadas continuam no arquivo (linha comentada), protegendo
  contra deleção acidental.
"""
from __future__ import annotations

from pathlib import Path

OABS_ATIVAS = (
    "15523",  # Ricardo Luiz Rodrigues da Fonseca Passos
    "36129",  # Leonardo Guedes da Fonseca Passos
)

OABS_DESATIVADAS = (
    # Desativadas no pós-smoke do refator watermark-por-advogado:
    "48468",  # Vitor Guedes da Fonseca Passos
    "20120",  # Cecília Maria Lapetina Chiaratto
    "38809",  # Samantha Lais Soares Mickievicz
    "75799",  # Deborah Nascimento de Castro
    # Desativadas antes (Fase 2.1):
    "65089",  # Juliana Vieira Gomes
    "81225",  # Juliana Chiaratto Batista
    "37654",  # Shirley Oliveira Pessoa
    "39857",  # Erika de Fatima Guedes Montalvan Rosa
    "84703",  # Maria Isabel Messias Conforti de Carvalho
    "79658",  # Cristiane Peixoto Guedes
)


def test_lista_ativa_tem_2_entradas_pos_smoke_refator() -> None:
    """ADVOGADOS tem exatamente 2 entradas após smoke do refator
    watermark-por-advogado (Ricardo + Leonardo)."""
    from notion_rpadv.services.dje_advogados import ADVOGADOS
    assert len(ADVOGADOS) == 2


def test_oabs_ativas_corretas() -> None:
    """As 2 OABs ativas atuais: Ricardo (15523/DF) + Leonardo (36129/DF)."""
    from notion_rpadv.services.dje_advogados import ADVOGADOS
    oabs_no_modulo = {a["oab"] for a in ADVOGADOS}
    assert oabs_no_modulo == set(OABS_ATIVAS), (
        f"OABs ativas inesperadas. esperado={set(OABS_ATIVAS)} "
        f"obtido={oabs_no_modulo}"
    )
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
