"""Testes da lista oficial ``ADVOGADOS`` em ``dje_advogados.py``.

Histórico:
- Fase 2.1 (2026-05-01): lista reduzida de 12 → 6.
- Pós-smoke real do refator watermark-por-advogado (02/05/2026): lista
  reduzida de 6 → 2 (Ricardo + Leonardo) por sobrecarga 429 da API DJEN
  em janelas longas.
- Pós-Fase 3 (2026-05-02): reativados Vitor, Cecília, Samantha, Deborah
  (de volta a 6 advogados). Cursores falsos desses 4 são tratados via
  modal one-shot na 1ª execução pós-reativação (ver
  ``leitor_dje._check_and_offer_reactivation_reset``).

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
    # Reativados em 2026-05-02 (pós-Fase 3):
    "48468",  # Vitor Guedes da Fonseca Passos
    "20120",  # Cecília Maria Lapetina Chiaratto
    "38809",  # Samantha Lais Soares Mickievicz
    "75799",  # Deborah Nascimento de Castro
)

OABS_DESATIVADAS = (
    # Desativadas antes (Fase 2.1):
    "65089",  # Juliana Vieira Gomes
    "81225",  # Juliana Chiaratto Batista
    "37654",  # Shirley Oliveira Pessoa
    "39857",  # Erika de Fatima Guedes Montalvan Rosa
    "84703",  # Maria Isabel Messias Conforti de Carvalho
    "79658",  # Cristiane Peixoto Guedes
)


def test_lista_ativa_tem_6_entradas_pos_reativacao() -> None:
    """ADVOGADOS tem exatamente 6 entradas após reativação dos 4 sócios
    em 2026-05-02 (Ricardo + Leonardo + Vitor + Cecília + Samantha +
    Deborah)."""
    from notion_rpadv.services.dje_advogados import ADVOGADOS
    assert len(ADVOGADOS) == 6


def test_oabs_ativas_corretas() -> None:
    """As 6 OABs ativas atuais."""
    from notion_rpadv.services.dje_advogados import ADVOGADOS
    oabs_no_modulo = {a["oab"] for a in ADVOGADOS}
    assert oabs_no_modulo == set(OABS_ATIVAS), (
        f"OABs ativas inesperadas. esperado={set(OABS_ATIVAS)} "
        f"obtido={oabs_no_modulo}"
    )
    for adv in ADVOGADOS:
        assert adv["uf"] == "DF"
        assert adv["nome"].strip()


def test_reactivated_2026_05_02_oabs_subset_of_ativas() -> None:
    """``REACTIVATED_2026_05_02_OABS`` deve listar exatamente os 4 advogados
    reativados em 2026-05-02 — todos ativos no momento (subset de
    ``ADVOGADOS``). Esta tupla alimenta o modal de reset na UI."""
    from notion_rpadv.services.dje_advogados import (
        ADVOGADOS,
        REACTIVATED_2026_05_02_OABS,
    )
    assert len(REACTIVATED_2026_05_02_OABS) == 4
    oabs_ativas = {(a["oab"], a["uf"]) for a in ADVOGADOS}
    for oab_uf in REACTIVATED_2026_05_02_OABS:
        assert oab_uf in oabs_ativas, (
            f"OAB reativada {oab_uf} não está na lista ativa — "
            "REACTIVATED_2026_05_02_OABS desincronizada com ADVOGADOS"
        )
    # Especificamente os 4 esperados (regression contra renomeação acidental):
    assert set(REACTIVATED_2026_05_02_OABS) == {
        ("48468", "DF"),  # Vitor
        ("20120", "DF"),  # Cecília
        ("38809", "DF"),  # Samantha
        ("75799", "DF"),  # Deborah
    }


def test_F21_15_oabs_desativadas_preservadas_no_arquivo_comentado() -> None:
    """Regression check: as OABs desativadas (Fase 2.1) devem aparecer
    literalmente no source de ``dje_advogados.py`` (comentadas, não
    deletadas).

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
    # Garantia adicional: as OABs desativadas aparecem em LINHAS
    # comentadas (começam com ``#`` antes da chave do dict).
    for oab in OABS_DESATIVADAS:
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
