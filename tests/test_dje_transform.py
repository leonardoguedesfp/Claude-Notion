"""Round 7 Fase 2 — testes do ``notion_rpadv.services.dje_transform``.

26 cases F2-01..F2-26 do spec do operador, cobrindo dedup, regras A
e B de observacoes, strip de HTML, normalização de encoding misto,
ordenação e integração ponta-a-ponta.

Funções puras — sem Qt, sem rede, sem I/O. Testáveis isoladas."""
from __future__ import annotations

import logging

import pytest


# ---------------------------------------------------------------------------
# Helper de fixture: linha "normal" sem anomalias (passa todas as regras
# A e B). Cada teste sobrescreve só o que precisa.
# ---------------------------------------------------------------------------


def _row(**overrides):
    base = {
        "id": 1000,
        "hash": "abc123",
        "siglaTribunal": "TRT10",
        "data_disponibilizacao": "2026-04-30",
        "datadisponibilizacao": "30/04/2026",
        "numeroprocessocommascara": "0001234-56.2026.5.10.0003",
        "numero_processo": "00012345620265100003",
        "tipoComunicacao": "Intimação",
        "tipoDocumento": "Despacho",
        "nomeOrgao": "1ª Vara do Trabalho de Brasília",
        "idOrgao": 42,
        "nomeClasse": "Reclamação Trabalhista",
        "codigoClasse": 985,
        "numeroComunicacao": 7,
        "texto": "Texto da publicação",
        "link": "https://example.com/publicacao",
        "destinatarios": [],
        "destinatarioadvogados": [
            {"numero_oab": "15523", "uf_oab": "DF", "nome": "Ricardo"},
            {"numero_oab": "36129", "uf_oab": "DF", "nome": "Leonardo"},
        ],
        # Campos da Regra A no estado "normal" (não disparam observacoes)
        "ativo": True,
        "status": "P",
        "meio": "D",
        "meiocompleto": "Diário de Justiça Eletrônico Nacional",
        "motivo_cancelamento": None,
        "data_cancelamento": None,
        # Campo anotado pelo client F1 (entrada do dedup)
        "advogado_consultado": "Leonardo Guedes da Fonseca Passos (36129/DF)",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# F2-01..F2-04: Dedup por id
# ---------------------------------------------------------------------------


def test_F2_01_dedup_duas_linhas_mesmo_id_advogados_diferentes() -> None:
    """Duas linhas com mesmo id, advogados diferentes → 1 linha com
    advogados_consultados ordenado alfabeticamente, separados por '; '."""
    from notion_rpadv.services.dje_transform import dedup_by_id
    rows = [
        _row(id=42, advogado_consultado="Leonardo Guedes da Fonseca Passos (36129/DF)"),
        _row(id=42, advogado_consultado="Ricardo Luiz Rodrigues da Fonseca Passos (15523/DF)"),
    ]
    result = dedup_by_id(rows)
    assert len(result) == 1
    # Ordem alfabética: Leonardo... vem antes de Ricardo...
    assert result[0]["advogados_consultados"] == (
        "Leonardo Guedes da Fonseca Passos (36129/DF); "
        "Ricardo Luiz Rodrigues da Fonseca Passos (15523/DF)"
    )
    # advogado_consultado (singular) some.
    assert "advogado_consultado" not in result[0]


def test_F2_02_dedup_cinco_linhas_idem_preserva_outros_campos() -> None:
    """5 linhas com mesmo id, idênticas exceto advogado_consultado →
    1 linha com os outros campos preservados (da primeira ocorrência)."""
    from notion_rpadv.services.dje_transform import dedup_by_id
    advs = [
        "AdvA (100/DF)", "AdvB (200/DF)", "AdvC (300/DF)",
        "AdvD (400/DF)", "AdvE (500/DF)",
    ]
    rows = [_row(id=99, advogado_consultado=adv) for adv in advs]
    result = dedup_by_id(rows)
    assert len(result) == 1
    out = result[0]
    # Outros campos preservados (todos os 24 do _row, exceto advogado_consultado).
    assert out["id"] == 99
    assert out["hash"] == "abc123"
    assert out["siglaTribunal"] == "TRT10"
    assert out["nomeOrgao"] == "1ª Vara do Trabalho de Brasília"
    # advogados_consultados em ordem alfabética
    assert out["advogados_consultados"] == "; ".join(sorted(advs))


def test_F2_03_dedup_ids_unicos_preserva_todos() -> None:
    """Linhas com id único cada → todas preservadas, advogados_consultados
    com 1 nome cada."""
    from notion_rpadv.services.dje_transform import dedup_by_id
    rows = [
        _row(id=1, advogado_consultado="AdvA (100/DF)"),
        _row(id=2, advogado_consultado="AdvB (200/DF)"),
        _row(id=3, advogado_consultado="AdvC (300/DF)"),
    ]
    result = dedup_by_id(rows)
    assert len(result) == 3
    assert result[0]["advogados_consultados"] == "AdvA (100/DF)"
    assert result[1]["advogados_consultados"] == "AdvB (200/DF)"
    assert result[2]["advogados_consultados"] == "AdvC (300/DF)"


def test_F2_04_dedup_divergencia_em_outro_campo_loga_e_mantem_primeira(
    caplog,
) -> None:
    """Duplicatas com mesmo id mas campos divergentes (não-advogado) →
    warning no logger, primeira ocorrência mantida."""
    from notion_rpadv.services.dje_transform import dedup_by_id
    rows = [
        _row(id=77, texto="Texto A", advogado_consultado="AdvA (100/DF)"),
        _row(id=77, texto="Texto B (DIVERGENTE)", advogado_consultado="AdvB (200/DF)"),
    ]
    with caplog.at_level(logging.WARNING, logger="dje.transform"):
        result = dedup_by_id(rows)
    assert len(result) == 1
    # Primeira ocorrência mantida (texto A).
    assert result[0]["texto"] == "Texto A"
    # Logger emitiu warning citando o id e o campo divergente.
    msgs = " ".join(r.message for r in caplog.records)
    assert "77" in msgs
    assert "texto" in msgs


# ---------------------------------------------------------------------------
# F2-05..F2-08: Regra A — campos constantes que variaram
# ---------------------------------------------------------------------------


def test_F2_05_observacoes_ativo_false() -> None:
    """ativo=False → observacoes contém mensagem de inatividade."""
    from notion_rpadv.services.dje_transform import make_observacoes
    obs = make_observacoes(_row(ativo=False))
    assert "Publicação inativa" in obs
    assert "ativo=False" in obs


def test_F2_06_observacoes_status_diferente() -> None:
    """status='C' → mensagem cita o valor encontrado."""
    from notion_rpadv.services.dje_transform import make_observacoes
    obs = make_observacoes(_row(status="C"))
    assert "Status diferente do habitual" in obs
    assert "'C'" in obs
    assert "P" in obs  # esperado citado


def test_F2_07_observacoes_motivo_cancelamento() -> None:
    """motivo_cancelamento preenchido → mensagem traz o texto."""
    from notion_rpadv.services.dje_transform import make_observacoes
    obs = make_observacoes(_row(motivo_cancelamento="erro de envio"))
    assert "Motivo de cancelamento informado" in obs
    assert "erro de envio" in obs


def test_F2_08_observacoes_linha_normal_string_vazia() -> None:
    """Linha 100% normal → observacoes é string vazia (não None)."""
    from notion_rpadv.services.dje_transform import make_observacoes
    obs = make_observacoes(_row())
    assert obs == ""
    assert obs is not None


# ---------------------------------------------------------------------------
# F2-09..F2-13: Regra B — sócios em destinatarioadvogados
# ---------------------------------------------------------------------------


def test_F2_09_observacoes_so_ricardo_falta_leonardo() -> None:
    """Apenas Ricardo aparece → mensagem reporta falta de Leonardo."""
    from notion_rpadv.services.dje_transform import make_observacoes
    advs = [{"numero_oab": "15523", "uf_oab": "DF", "nome": "Ricardo"}]
    obs = make_observacoes(_row(destinatarioadvogados=advs))
    assert "Leonardo (36129/DF) não consta" in obs
    assert "Ricardo" not in obs.split("Leonardo")[0]  # só fala de Leonardo


def test_F2_10_observacoes_so_leonardo_falta_ricardo() -> None:
    """Apenas Leonardo aparece → mensagem reporta falta de Ricardo."""
    from notion_rpadv.services.dje_transform import make_observacoes
    advs = [{"numero_oab": "36129", "uf_oab": "DF", "nome": "Leonardo"}]
    obs = make_observacoes(_row(destinatarioadvogados=advs))
    assert "Ricardo (15523/DF) não consta" in obs


def test_F2_11_observacoes_nem_ricardo_nem_leonardo() -> None:
    """Nenhum dos dois → mensagem específica 'nem um nem outro'."""
    from notion_rpadv.services.dje_transform import make_observacoes
    advs = [
        {"numero_oab": "99999", "uf_oab": "DF", "nome": "Outro"},
    ]
    obs = make_observacoes(_row(destinatarioadvogados=advs))
    assert "Nem Ricardo (15523/DF) nem Leonardo (36129/DF)" in obs


def test_F2_12_observacoes_ambos_nao_dispara() -> None:
    """Ambos aparecem (default _row) → regra B não acrescenta nada."""
    from notion_rpadv.services.dje_transform import make_observacoes
    obs = make_observacoes(_row())
    assert obs == ""


def test_F2_13_observacoes_ricardo_em_outra_uf_conta_como_ausente() -> None:
    """Ricardo OAB 15523 mas UF≠DF → conta como ausência. Homônimo
    não é o nosso. Mesma lógica pra Leonardo."""
    from notion_rpadv.services.dje_transform import make_observacoes
    advs = [
        {"numero_oab": "15523", "uf_oab": "SP", "nome": "Outro Ricardo"},
        {"numero_oab": "36129", "uf_oab": "DF", "nome": "Leonardo"},
    ]
    obs = make_observacoes(_row(destinatarioadvogados=advs))
    assert "Ricardo (15523/DF) não consta" in obs


# ---------------------------------------------------------------------------
# F2-14: Composição A + B
# ---------------------------------------------------------------------------


def test_F2_14_observacoes_compoe_regra_a_e_b_em_ordem() -> None:
    """ativo=False E só Ricardo aparece → 2 mensagens unidas por
    ' | ', com Regra A primeiro, Regra B depois."""
    from notion_rpadv.services.dje_transform import make_observacoes
    advs = [{"numero_oab": "15523", "uf_oab": "DF", "nome": "Ricardo"}]
    obs = make_observacoes(_row(
        ativo=False, destinatarioadvogados=advs,
    ))
    parts = obs.split(" | ")
    assert len(parts) == 2
    assert "inativa" in parts[0]
    assert "Leonardo" in parts[1] and "não consta" in parts[1]


# ---------------------------------------------------------------------------
# F2-15..F2-20: Strip HTML
# ---------------------------------------------------------------------------


def test_F2_15_strip_html_br_simples() -> None:
    """<br> simples vira \\n na posição correta."""
    from notion_rpadv.services.dje_transform import strip_html
    out = strip_html("Linha 1<br>Linha 2<br>Linha 3")
    assert out == "Linha 1\nLinha 2\nLinha 3"


def test_F2_15_strip_html_br_variantes() -> None:
    """<br>, <br/>, <BR>, <br /> — todas viram \\n."""
    from notion_rpadv.services.dje_transform import strip_html
    out = strip_html("a<br>b<br/>c<BR>d<br />e")
    assert out == "a\nb\nc\nd\ne"


def test_F2_16_strip_html_anchor_preserva_url_visivel() -> None:
    """<a href="url">url</a> → resta o conteúdo (a URL como texto)."""
    from notion_rpadv.services.dje_transform import strip_html
    out = strip_html('Veja <a href="https://x.com">https://x.com</a> agora')
    assert out == "Veja https://x.com agora"


def test_F2_17_strip_html_tabela_celulas_separadas_por_espaco() -> None:
    """<table><tr><td>X</td><td>Y</td></tr></table> → 'X Y' (com
    quebra ao final do </tr>)."""
    from notion_rpadv.services.dje_transform import strip_html
    out = strip_html(
        "<table><tr><td>Cel1</td><td>Cel2</td></tr>"
        "<tr><td>Cel3</td><td>Cel4</td></tr></table>",
    )
    # Espaços entre células, quebras entre linhas, normalizado.
    assert "Cel1 Cel2" in out
    assert "Cel3 Cel4" in out
    # Linhas separadas por \n
    assert "\nCel3" in out


def test_F2_18_strip_html_entidades_decodificadas() -> None:
    """&amp;, &nbsp;, &aacute; → caracteres reais."""
    from notion_rpadv.services.dje_transform import strip_html
    out = strip_html("A&amp;B&nbsp;C&aacute;D")
    # &amp; → &; &nbsp; → \xa0 (no-break space); &aacute; → á
    assert "&" in out
    assert "á" in out


def test_F2_19_strip_html_texto_sem_tags_passa_intacto() -> None:
    """Texto puro (sem <>) passa sem alteração além do strip de
    espaços/quebras já normalizado."""
    from notion_rpadv.services.dje_transform import strip_html
    out = strip_html("Despacho proferido nos autos.")
    assert out == "Despacho proferido nos autos."


def test_F2_20_strip_html_vazio_ou_none() -> None:
    """Vazio ou None — não quebra."""
    from notion_rpadv.services.dje_transform import strip_html
    assert strip_html("") == ""
    assert strip_html(None) is None


# ---------------------------------------------------------------------------
# F2-21..F2-24: Normalização de encoding misto
# ---------------------------------------------------------------------------


def test_F2_21_normalizar_all_caps_com_acentos_minusculos() -> None:
    """'CUMPRIMENTO PROVISóRIO DE SENTENçA' → 'CUMPRIMENTO PROVISÓRIO DE SENTENÇA'."""
    from notion_rpadv.services.dje_transform import normalizar_encoding_misto
    out = normalizar_encoding_misto("CUMPRIMENTO PROVISóRIO DE SENTENçA")
    assert out == "CUMPRIMENTO PROVISÓRIO DE SENTENÇA"


def test_F2_22_normalizar_texto_natural_misto_intacto() -> None:
    """Texto natural com proporção < 70% maiúsculas → inalterado."""
    from notion_rpadv.services.dje_transform import normalizar_encoding_misto
    s = "Despacho proferido nos autos"
    assert normalizar_encoding_misto(s) == s


def test_F2_23_normalizar_aplicado_apenas_em_3_campos_via_pipeline() -> None:
    """Round 7 F2 spec: normalização rola SÓ em nomeOrgao, nomeClasse,
    tipoDocumento — não em ``texto``. Smoke ponta-a-ponta validando
    que ``texto`` com all-caps acentuado preserva os acentos minúsculos."""
    from notion_rpadv.services.dje_transform import transform_rows
    raw = [_row(
        id=1,
        nomeOrgao="VARA DO TRABALHO DE BRASíLIA",
        nomeClasse="REVISãO DE BENEFíCIO",
        tipoDocumento="DESPACHO PROFERIDO",
        texto="ALGUM TRECHO COM ó MINúSCULO ACENTUADO",
    )]
    rows, _cols = transform_rows(raw)
    assert rows[0]["nomeOrgao"] == "VARA DO TRABALHO DE BRASÍLIA"
    assert rows[0]["nomeClasse"] == "REVISÃO DE BENEFÍCIO"
    assert rows[0]["tipoDocumento"] == "DESPACHO PROFERIDO"
    # texto NÃO foi normalizado — preserva os acentos minúsculos como vieram
    # (corpo da publicação tem misturas legítimas; bug do upstream se
    # manifesta com mais frequência nos 3 campos curtos).
    assert "ó" in rows[0]["texto"]
    assert "ú" in rows[0]["texto"]


def test_F2_24_normalizar_vazio_ou_none() -> None:
    """Vazio ou None → não quebra."""
    from notion_rpadv.services.dje_transform import normalizar_encoding_misto
    assert normalizar_encoding_misto("") == ""
    assert normalizar_encoding_misto(None) is None


# ---------------------------------------------------------------------------
# F2-25: Ordenação
# ---------------------------------------------------------------------------


def test_F2_25_sort_por_tribunal_asc_data_desc() -> None:
    """Ordenação final: siglaTribunal ASC, depois data_disponibilizacao DESC."""
    from notion_rpadv.services.dje_transform import sort_rows
    rows = [
        {"siglaTribunal": "TRT10", "data_disponibilizacao": "2026-04-28", "x": 1},
        {"siglaTribunal": "STJ",   "data_disponibilizacao": "2026-04-29", "x": 2},
        {"siglaTribunal": "TRT10", "data_disponibilizacao": "2026-04-30", "x": 3},
        {"siglaTribunal": "STF",   "data_disponibilizacao": "2026-04-27", "x": 4},
        {"siglaTribunal": "STJ",   "data_disponibilizacao": "2026-04-30", "x": 5},
    ]
    out = sort_rows(rows)
    # Esperado:
    # STF 2026-04-27 (x=4)
    # STJ 2026-04-30 (x=5) → mais recente STJ vem antes
    # STJ 2026-04-29 (x=2)
    # TRT10 2026-04-30 (x=3)
    # TRT10 2026-04-28 (x=1)
    assert [r["x"] for r in out] == [4, 5, 2, 3, 1]


# ---------------------------------------------------------------------------
# F2-26: Integração ponta-a-ponta
# ---------------------------------------------------------------------------


def test_F2_26_integracao_dedup_observacoes_html_ordem_colunas() -> None:
    """Fixture com 10 itens (3 ids únicos, 7 duplicatas), 1 com anomalia
    A e 1 com anomalia B → 3 linhas finais, 20 colunas exatas, observacoes
    populado nas certas, texto sem HTML, ordem por tribunal+data."""
    from notion_rpadv.services.dje_transform import (
        CANONICAL_COLUMNS,
        transform_rows,
    )
    raw = [
        # id=1 (4 duplicatas, anomalia A: ativo=False)
        _row(id=1, ativo=False, siglaTribunal="STJ",
             data_disponibilizacao="2026-04-30",
             texto="Despacho<br>continuação<br>fim",
             advogado_consultado="AdvA (100/DF)"),
        _row(id=1, ativo=False, siglaTribunal="STJ",
             data_disponibilizacao="2026-04-30",
             texto="Despacho<br>continuação<br>fim",
             advogado_consultado="AdvB (200/DF)"),
        _row(id=1, ativo=False, siglaTribunal="STJ",
             data_disponibilizacao="2026-04-30",
             texto="Despacho<br>continuação<br>fim",
             advogado_consultado="AdvC (300/DF)"),
        _row(id=1, ativo=False, siglaTribunal="STJ",
             data_disponibilizacao="2026-04-30",
             texto="Despacho<br>continuação<br>fim",
             advogado_consultado="AdvD (400/DF)"),
        # id=2 (3 duplicatas, anomalia B: só Ricardo aparece)
        _row(id=2, siglaTribunal="TRT10",
             data_disponibilizacao="2026-04-29",
             destinatarioadvogados=[
                 {"numero_oab": "15523", "uf_oab": "DF", "nome": "R"},
             ],
             advogado_consultado="AdvE (500/DF)"),
        _row(id=2, siglaTribunal="TRT10",
             data_disponibilizacao="2026-04-29",
             destinatarioadvogados=[
                 {"numero_oab": "15523", "uf_oab": "DF", "nome": "R"},
             ],
             advogado_consultado="AdvF (600/DF)"),
        _row(id=2, siglaTribunal="TRT10",
             data_disponibilizacao="2026-04-29",
             destinatarioadvogados=[
                 {"numero_oab": "15523", "uf_oab": "DF", "nome": "R"},
             ],
             advogado_consultado="AdvG (700/DF)"),
        # id=3 (3 duplicatas, sem anomalia)
        _row(id=3, siglaTribunal="STJ",
             data_disponibilizacao="2026-04-28",
             advogado_consultado="AdvH (800/DF)"),
        _row(id=3, siglaTribunal="STJ",
             data_disponibilizacao="2026-04-28",
             advogado_consultado="AdvI (900/DF)"),
        _row(id=3, siglaTribunal="STJ",
             data_disponibilizacao="2026-04-28",
             advogado_consultado="AdvJ (1000/DF)"),
    ]
    rows, columns = transform_rows(raw)

    # 1) Dedup: 3 linhas finais
    assert len(rows) == 3

    # 2) 20 colunas em ordem canônica
    assert columns == CANONICAL_COLUMNS
    assert len(columns) == 20

    # 3) Ordem: STJ 2026-04-30 (id=1), STJ 2026-04-28 (id=3), TRT10 2026-04-29 (id=2)
    assert [r["id"] for r in rows] == [1, 3, 2]

    # 4) observacoes populado nas certas
    assert "inativa" in rows[0]["observacoes"]      # id=1 (anomalia A)
    assert rows[1]["observacoes"] == ""              # id=3 (sem anomalia)
    assert "Leonardo" in rows[2]["observacoes"]      # id=2 (anomalia B)
    assert "não consta" in rows[2]["observacoes"]

    # 5) texto sem HTML em id=1
    assert "<br>" not in rows[0]["texto"]
    assert "Despacho\ncontinuação\nfim" == rows[0]["texto"]

    # 6) advogados_consultados ordem alfabética e separados por "; "
    assert rows[0]["advogados_consultados"] == (
        "AdvA (100/DF); AdvB (200/DF); AdvC (300/DF); AdvD (400/DF)"
    )

    # 7) Colunas removidas não aparecem
    for dropped in ("ativo", "status", "meio", "meiocompleto",
                    "motivo_cancelamento", "data_cancelamento",
                    "advogado_consultado"):
        for r in rows:
            assert dropped not in r, f"{dropped} ainda presente em {r}"


# ---------------------------------------------------------------------------
# Smoke adicionais — defesa de payload variante (cobertura ≥ 95%)
# ---------------------------------------------------------------------------


def test_dedup_linha_sem_id_preserva_advogados_singular_to_plural() -> None:
    """Defesa: linha sem id não vai pra dedup; preserva como está,
    convertendo advogado_consultado (singular) em advogados_consultados
    (plural com 1 nome)."""
    from notion_rpadv.services.dje_transform import dedup_by_id
    rows = [{"hash": "x", "advogado_consultado": "AdvX (1/DF)"}]
    result = dedup_by_id(rows)
    assert len(result) == 1
    assert result[0]["advogados_consultados"] == "AdvX (1/DF)"
    assert "advogado_consultado" not in result[0]


def test_socios_destinatarioadvogados_nao_lista() -> None:
    """destinatarioadvogados não-lista (None, string, dict) → both False."""
    from notion_rpadv.services.dje_transform import _socios_presentes
    assert _socios_presentes(None) == (False, False)
    assert _socios_presentes("string") == (False, False)
    assert _socios_presentes({"oab": "15523"}) == (False, False)


def test_socios_destinatarioadvogados_item_nao_dict() -> None:
    """Items não-dict dentro da lista são ignorados (defesa)."""
    from notion_rpadv.services.dje_transform import _socios_presentes
    advs = ["string-malformada", 42, None,
            {"numero_oab": "15523", "uf_oab": "DF"}]
    assert _socios_presentes(advs) == (True, False)


def test_strip_html_normaliza_espacos_multiplos() -> None:
    """Espaços e tabs múltiplos colapsam pra 1; quebras múltiplas (3+)
    colapsam pra 2 (parágrafo)."""
    from notion_rpadv.services.dje_transform import strip_html
    out = strip_html("<p>A   B\t\tC</p><br><br><br>D")
    # Espaços/tabs colapsados; quebras múltiplas viram \n\n
    assert "A B C" in out
    assert "D" in out
    # No máximo 2 \n consecutivos
    assert "\n\n\n" not in out


def test_normalizar_string_sem_letras() -> None:
    """String só com números/símbolos — sem letras, sem mudança."""
    from notion_rpadv.services.dje_transform import normalizar_encoding_misto
    assert normalizar_encoding_misto("123 456 -.,") == "123 456 -.,"


def test_check_constants_meio_diferente() -> None:
    """meio ≠ 'D' dispara mensagem A."""
    from notion_rpadv.services.dje_transform import _check_constants
    msgs = _check_constants(_row(meio="X"))
    assert any("Meio diferente" in m for m in msgs)
    assert any("'X'" in m for m in msgs)


def test_check_constants_meiocompleto_diferente() -> None:
    """meiocompleto ≠ valor habitual dispara mensagem A."""
    from notion_rpadv.services.dje_transform import _check_constants
    msgs = _check_constants(_row(meiocompleto="Outro Diário"))
    assert any("Meio completo diferente" in m for m in msgs)
    assert any("Outro Diário" in m for m in msgs)


def test_check_constants_data_cancelamento() -> None:
    """data_cancelamento preenchida dispara mensagem A."""
    from notion_rpadv.services.dje_transform import _check_constants
    msgs = _check_constants(_row(data_cancelamento="2026-04-15"))
    assert any("Data de cancelamento" in m for m in msgs)


def test_check_constants_motivo_whitespace_only_nao_dispara() -> None:
    """motivo_cancelamento só com whitespace conta como vazio (não dispara)."""
    from notion_rpadv.services.dje_transform import _check_constants
    msgs = _check_constants(_row(motivo_cancelamento="   "))
    assert not any("Motivo de cancelamento" in m for m in msgs)


def test_canonical_columns_tem_20_entradas_unicas() -> None:
    """Sanity: schema canônico tem 20 colunas únicas, na ordem do spec."""
    from notion_rpadv.services.dje_transform import CANONICAL_COLUMNS
    assert len(CANONICAL_COLUMNS) == 20
    assert len(set(CANONICAL_COLUMNS)) == 20
    # Primeiras 2 colunas: as adições da F2.
    assert CANONICAL_COLUMNS[0] == "advogados_consultados"
    assert CANONICAL_COLUMNS[1] == "observacoes"


def test_dropped_columns_nao_intersecta_canonical() -> None:
    """Sanity: colunas removidas e schema canônico não compartilham nomes."""
    from notion_rpadv.services.dje_transform import (
        CANONICAL_COLUMNS,
        DROPPED_COLUMNS,
    )
    assert DROPPED_COLUMNS.isdisjoint(set(CANONICAL_COLUMNS))


def test_transform_rows_lista_vazia() -> None:
    """transform_rows([]) não quebra; retorna ([], CANONICAL_COLUMNS)."""
    from notion_rpadv.services.dje_transform import (
        CANONICAL_COLUMNS,
        transform_rows,
    )
    rows, cols = transform_rows([])
    assert rows == []
    assert cols == CANONICAL_COLUMNS


def test_sort_rows_chaves_ausentes_string_vazia() -> None:
    """Linhas sem siglaTribunal ou sem data_disponibilizacao ainda
    aparecem na ordenação (chave ausente vira string vazia, vão pro topo)."""
    from notion_rpadv.services.dje_transform import sort_rows
    rows = [
        {"siglaTribunal": "TRT10", "data_disponibilizacao": "2026-04-29", "x": 1},
        {"x": 2},  # sem campos de sort
        {"siglaTribunal": "STJ", "data_disponibilizacao": "2026-04-30", "x": 3},
    ]
    out = sort_rows(rows)
    # Sem campos → sigla="" vai pro topo, depois STJ, depois TRT10
    xs = [r["x"] for r in out]
    assert xs[0] == 2
    assert xs[1] == 3
    assert xs[2] == 1


def test_descstr_equality() -> None:
    """_DescStr.__eq__ smoke (otherwise unhit by sort path)."""
    from notion_rpadv.services.dje_transform import _DescStr
    a = _DescStr("x")
    b = _DescStr("x")
    c = _DescStr("y")
    assert a == b
    assert a != c
    assert a != "x"  # tipo diferente
