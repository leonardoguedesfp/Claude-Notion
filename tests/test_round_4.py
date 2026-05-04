"""Testes do Round 4 — fixes pré-Round 5 da pipeline DJE × Notion (2026-05-03).

Cobre:

- 4.1 Reformatar `Partes` (Polo Ativo / Polo Passivo / Terceiro Interessado)
- 4.2 Normalizar `Classe` via `MAPA_NOMECLASSE`
- 4.3 Auto-`Tarefa sugerida` (6 regras multi-select)
- 4.4 Auto-`Alerta contadoria` (5 regras multi-select)
- 4.5 Teste de regressão para `<br>` literal residual no Texto inline
- 4.6 Mapper deixa de gravar checkbox `Processo não cadastrado`

Os testes do mapper ponta a ponta (montar_payload_publicacao) ficam em
``tests/test_dje_notion_mapper.py``; aqui isolamos as funções novas.
"""
from __future__ import annotations

from notion_rpadv.services.dje_notion_mappings import (
    MAPA_NOMECLASSE,
    PARTES_INLINE_LIMIT,
    POLO_LABEL,
    formatar_partes,
    normalizar_classe,
)


# ===========================================================================
# 4.1 — Reformatar Partes
# ===========================================================================


def test_R4_1_partes_pub_trabalhista_normal() -> None:
    """1 Ativo + 1 Passivo (caso TRT10 djen=494748109)."""
    destinatarios = [
        {"comunicacao_id": 494748109, "nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"comunicacao_id": 494748109, "nome": "DENITA GOMES GUIMARAES", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    assert out == (
        "Polo Ativo: DENITA GOMES GUIMARAES\n"
        "Polo Passivo: BANCO DO BRASIL SA"
    )


def test_R4_1_partes_stj_3_destinatarios_com_papel() -> None:
    """STJ tem prefixo numérico + papel real entre parênteses no nome.
    A formatação genérica deste Round agrupa por polo A/P; o papel real
    fica no próprio nome (não é extraído pra label)."""
    destinatarios = [
        {"nome": "1. CAIXA DE PREVIDENCIA - PREVI (AGRAVANTE)", "polo": "A"},
        {"nome": "2. ALEX DOS SANTOS SABINO (AGRAVADO)", "polo": "P"},
        {"nome": "3. BANCO DO BRASIL SA (INTERESSADO)", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    # Ativo agrupa AGRAVANTE + INTERESSADO (ambos polo A)
    assert "Polo Ativo: 1. CAIXA DE PREVIDENCIA - PREVI (AGRAVANTE), 3. BANCO DO BRASIL SA (INTERESSADO)" in out
    assert "Polo Passivo: 2. ALEX DOS SANTOS SABINO (AGRAVADO)" in out


def test_R4_1_partes_multiplos_nomes_mesmo_polo() -> None:
    """TRT10 com 2 reclamantes (polo A) — separa por vírgula."""
    destinatarios = [
        {"nome": "RECLAMANTE 1", "polo": "A"},
        {"nome": "RECLAMANTE 2", "polo": "A"},
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},
    ]
    out = formatar_partes(destinatarios)
    assert out == (
        "Polo Ativo: RECLAMANTE 1, RECLAMANTE 2\n"
        "Polo Passivo: BANCO DO BRASIL SA"
    )


def test_R4_1_partes_sem_destinatarios() -> None:
    assert formatar_partes([]) == ""
    assert formatar_partes(None) == ""
    assert formatar_partes("not-a-list") == ""


def test_R4_1_partes_terceiro_interessado() -> None:
    """Polo T mapeia pra 'Terceiro Interessado'."""
    destinatarios = [
        {"nome": "AUTOR", "polo": "A"},
        {"nome": "RÉU", "polo": "P"},
        {"nome": "AMICUS CURIAE", "polo": "T"},
    ]
    out = formatar_partes(destinatarios)
    assert out == (
        "Polo Ativo: AUTOR\n"
        "Polo Passivo: RÉU\n"
        "Terceiro Interessado: AMICUS CURIAE"
    )


def test_R4_1_partes_polo_desconhecido_fallback() -> None:
    """Polo fora de A/P/T cai no fallback 'Polo {valor}'."""
    destinatarios = [
        {"nome": "X", "polo": "Z"},  # Z desconhecido
    ]
    assert formatar_partes(destinatarios) == "Polo Z: X"


def test_R4_1_partes_ordem_fixa_apt() -> None:
    """Ordem A → P → T mesmo se vierem invertidos no payload."""
    destinatarios = [
        {"nome": "TERC", "polo": "T"},
        {"nome": "RÉU", "polo": "P"},
        {"nome": "AUTOR", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    linhas = out.split("\n")
    assert linhas[0].startswith("Polo Ativo: ")
    assert linhas[1].startswith("Polo Passivo: ")
    assert linhas[2].startswith("Terceiro Interessado: ")


def test_R4_1_partes_dedup_nome_repetido_mesmo_polo() -> None:
    """Mesmo nome no mesmo polo (artefato do DJEN) entra 1 vez só."""
    destinatarios = [
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},  # duplicata
        {"nome": "AUTOR", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    assert out == "Polo Ativo: AUTOR\nPolo Passivo: BANCO DO BRASIL SA"


def test_R4_1_partes_truncamento_em_2000_chars() -> None:
    """Output total ≤ 2000 chars; corte preserva nomes inteiros + marcador."""
    nomes = [f"NOME ABCD EFGH IJKL {i}" for i in range(200)]
    destinatarios = [{"nome": n, "polo": "A"} for n in nomes]
    out = formatar_partes(destinatarios)
    assert len(out) <= PARTES_INLINE_LIMIT
    assert out.endswith("…")
    # Não deve cortar no meio de um nome
    assert "NOME ABCD EFGH IJKL 0" in out


def test_R4_1_partes_nome_vazio_e_descartado() -> None:
    destinatarios = [
        {"nome": "", "polo": "A"},
        {"nome": "VALIDO", "polo": "P"},
    ]
    assert formatar_partes(destinatarios) == "Polo Passivo: VALIDO"


def test_R4_1_partes_polo_label_constante_canonica() -> None:
    """Sanity: tabela POLO_LABEL tem A/P/T."""
    assert POLO_LABEL["A"] == "Polo Ativo"
    assert POLO_LABEL["P"] == "Polo Passivo"
    assert POLO_LABEL["T"] == "Terceiro Interessado"


# ===========================================================================
# 4.2 — Normalização de Classe (casing torto)
# ===========================================================================


def test_R4_2_classe_top_5_acervo_canonizadas() -> None:
    """Top 5 classes do acervo Round 3 vêm com casing torto e são
    canonizadas para CAPS uniforme com acentos corretos."""
    assert normalizar_classe("AçãO TRABALHISTA - RITO ORDINáRIO") == (
        "AÇÃO TRABALHISTA - RITO ORDINÁRIO"
    )
    assert normalizar_classe("RECURSO ORDINáRIO TRABALHISTA") == (
        "RECURSO ORDINÁRIO TRABALHISTA"
    )
    assert normalizar_classe("CUMPRIMENTO DE SENTENçA") == (
        "CUMPRIMENTO DE SENTENÇA"
    )
    assert normalizar_classe("AGRAVO DE PETIçãO") == "AGRAVO DE PETIÇÃO"
    assert normalizar_classe("PROCEDIMENTO COMUM CíVEL") == (
        "PROCEDIMENTO COMUM CÍVEL"
    )


def test_R4_2_classe_ja_em_caps_passa_intacta() -> None:
    """Classes já em CAPS corretas (8 do acervo) NÃO entram no mapa,
    fallback preserva o cru. Testa: RECURSO ESPECIAL, AGRAVO DE
    INSTRUMENTO, RECURSO DE REVISTA, etc."""
    intactas = [
        "RECURSO ESPECIAL",
        "AGRAVO DE INSTRUMENTO",
        "AGRAVO EM RECURSO ESPECIAL",
        "AGRAVO DE INSTRUMENTO EM RECURSO DE REVISTA",
        "RECURSO DE REVISTA COM AGRAVO",
        "AGRAVO",
        "RECURSO DE REVISTA",
        "AGRAVO REGIMENTAL TRABALHISTA",
    ]
    for c in intactas:
        assert normalizar_classe(c) == c


def test_R4_2_classe_nao_mapeada_passa_intacta() -> None:
    """Classe nova/futura não listada no mapa: fallback preserva o
    valor cru (não aplica .upper() cego — pode haver classes futuras
    bem formatadas)."""
    classe_nova = "NOVA CLASSE INVENTADA - ALGO"
    assert normalizar_classe(classe_nova) == classe_nova
    # Mesmo casing não convencional fica intocado
    classe_titlecase = "Tipo de Ação Customizado"
    assert normalizar_classe(classe_titlecase) == classe_titlecase


def test_R4_2_classe_titlecase_explicita_no_mapa() -> None:
    """O caso de title case observado em produção
    ('Procedimento do Juizado Especial da Fazenda Pública') está
    no mapa pra ficar consistente com o resto (CAPS uniforme)."""
    out = normalizar_classe("Procedimento do Juizado Especial da Fazenda Pública")
    assert out == "PROCEDIMENTO DO JUIZADO ESPECIAL DA FAZENDA PÚBLICA"


def test_R4_2_classe_none_e_vazio() -> None:
    assert normalizar_classe(None) == ""
    assert normalizar_classe("") == ""
    assert normalizar_classe("   ") == ""


def test_R4_2_classe_strip_aplicado() -> None:
    """Whitespace nas pontas não atrapalha lookup."""
    assert normalizar_classe("  AçãO TRABALHISTA - RITO ORDINáRIO  ") == (
        "AÇÃO TRABALHISTA - RITO ORDINÁRIO"
    )


def test_R4_2_mapa_consistente_chave_diferente_do_valor() -> None:
    """Sanity: para todas as entradas do MAPA_NOMECLASSE, a saída é
    diferente da entrada (senão, a entrada é redundante)."""
    for chave, valor in MAPA_NOMECLASSE.items():
        assert chave != valor, (
            f"Entrada redundante: {chave!r} mapeia pra ela mesma"
        )
