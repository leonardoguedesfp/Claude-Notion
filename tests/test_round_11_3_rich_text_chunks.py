"""Round 11.3 (2026-05-14) — chunkagem da propriedade ``Texto`` em
múltiplos itens ``rich_text``.

Antes do Round 11.3 a integração gravava ``Texto`` como 1 único item
``rich_text`` truncado em ~2.000 chars + marcador ``[…]`` — 99% dos
acórdãos do TRT10 ficavam cortados, 90% do TST e 74% do TJDFT. Agora
a propriedade aceita até 100 itens × 1.990 chars = ~199.000 chars de
texto integral. Cobertura aqui:

- ``chunkar_para_rich_text`` em :mod:`notion_rpadv.services.dje_text_pipeline`.
- ``_texto_inline_prop`` em :mod:`notion_rpadv.services.dje_notion_mapper`.
"""
from __future__ import annotations

from notion_rpadv.services.dje_notion_mapper import _texto_inline_prop
from notion_rpadv.services.dje_text_pipeline import (
    RICH_TEXT_CHUNK_MAX_DEFAULT,
    RICH_TEXT_MAX_ITEMS_DEFAULT,
    TEXTO_INLINE_MARCADOR_DEFAULT,
    chunkar_para_rich_text,
)


# ---------------------------------------------------------------------------
# chunkar_para_rich_text — entradas degeneradas
# ---------------------------------------------------------------------------


def test_chunkar_texto_none_devolve_lista_vazia() -> None:
    assert chunkar_para_rich_text(None) == []


def test_chunkar_texto_vazio_devolve_lista_vazia() -> None:
    assert chunkar_para_rich_text("") == []


def test_chunkar_texto_curto_devolve_um_item_intacto() -> None:
    out = chunkar_para_rich_text("ABC do despacho.")
    assert len(out) == 1
    assert out[0] == {
        "type": "text",
        "text": {"content": "ABC do despacho."},
    }


def test_chunkar_texto_no_limite_exato_devolve_um_item() -> None:
    texto = "X" * RICH_TEXT_CHUNK_MAX_DEFAULT
    out = chunkar_para_rich_text(texto)
    assert len(out) == 1
    assert out[0]["text"]["content"] == texto


def test_chunkar_texto_um_char_acima_do_limite_devolve_dois_items() -> None:
    texto = "X" * (RICH_TEXT_CHUNK_MAX_DEFAULT + 1)
    out = chunkar_para_rich_text(texto)
    assert len(out) == 2
    # Concatenação reconstrói o original.
    assert "".join(it["text"]["content"] for it in out) == texto


# ---------------------------------------------------------------------------
# Cortes em fronteira natural
# ---------------------------------------------------------------------------


def test_chunkar_corta_em_paragrafo_quando_disponivel() -> None:
    bloco_a = "A" * 1900
    bloco_b = "B" * 1900
    texto = f"{bloco_a}\n\n{bloco_b}"
    out = chunkar_para_rich_text(texto)
    assert len(out) == 2
    # O \n\n acompanha o primeiro chunk (não duplica nem some).
    assert out[0]["text"]["content"].endswith("\n\n")
    assert out[1]["text"]["content"] == bloco_b
    # Reconstrução exata.
    assert "".join(it["text"]["content"] for it in out) == texto


def test_chunkar_corta_em_quebra_de_linha_quando_nao_ha_paragrafo() -> None:
    bloco_a = "A" * 1900
    bloco_b = "B" * 1900
    texto = f"{bloco_a}\n{bloco_b}"
    out = chunkar_para_rich_text(texto)
    assert len(out) == 2
    assert out[0]["text"]["content"].endswith("\n")
    assert "".join(it["text"]["content"] for it in out) == texto


def test_chunkar_corta_em_fim_de_frase_quando_nao_ha_quebra() -> None:
    # 1950 + 2 + 80 = 2032 chars: estoura chunk_max=1990.
    parte = "A" * 1950
    texto = f"{parte}. {'B' * 80}"
    out = chunkar_para_rich_text(texto)
    assert len(out) == 2
    # Primeiro chunk termina depois do ". " (espaço inclusive).
    assert out[0]["text"]["content"].endswith(". ")
    assert "".join(it["text"]["content"] for it in out) == texto


def test_chunkar_corta_em_espaco_quando_nao_ha_pontuacao() -> None:
    parte = "A" * 1900
    texto = f"{parte} {'B' * 200}"
    out = chunkar_para_rich_text(texto)
    assert len(out) == 2
    assert out[0]["text"]["content"].endswith(" ")
    assert "".join(it["text"]["content"] for it in out) == texto


def test_chunkar_corta_cru_quando_nao_ha_separador_natural() -> None:
    texto = "X" * (RICH_TEXT_CHUNK_MAX_DEFAULT * 2 + 100)
    out = chunkar_para_rich_text(texto)
    assert len(out) == 3
    # Reconstrução perfeita (sem perda de chars).
    assert "".join(it["text"]["content"] for it in out) == texto
    # Cada item respeita o limite.
    for it in out:
        assert len(it["text"]["content"]) <= RICH_TEXT_CHUNK_MAX_DEFAULT


# ---------------------------------------------------------------------------
# Limites e overflow
# ---------------------------------------------------------------------------


def test_chunkar_respeita_chunk_max_em_todos_os_items() -> None:
    texto = "palavra " * 5000  # ~40k chars
    out = chunkar_para_rich_text(texto)
    for it in out:
        assert len(it["text"]["content"]) <= RICH_TEXT_CHUNK_MAX_DEFAULT


def test_chunkar_overflow_acima_de_max_items_marca_ultimo_item() -> None:
    """Texto > 100 × 1990 chars: último item ganha marcador ``[…]``
    (análogo ao truncar_texto_inline antigo, mas aplicado só em
    overflow real)."""
    texto = "X" * (RICH_TEXT_CHUNK_MAX_DEFAULT * RICH_TEXT_MAX_ITEMS_DEFAULT + 500)
    out = chunkar_para_rich_text(texto)
    assert len(out) == RICH_TEXT_MAX_ITEMS_DEFAULT
    assert out[-1]["text"]["content"].endswith(TEXTO_INLINE_MARCADOR_DEFAULT)
    # Cada item ainda respeita chunk_max.
    for it in out:
        assert len(it["text"]["content"]) <= RICH_TEXT_CHUNK_MAX_DEFAULT


def test_chunkar_sem_overflow_nao_inclui_marcador() -> None:
    """Texto que cabe nos 100 itens NÃO recebe marcador ``[…]``."""
    texto = "X" * (RICH_TEXT_CHUNK_MAX_DEFAULT * 2)
    out = chunkar_para_rich_text(texto)
    assert len(out) == 2
    for it in out:
        assert not it["text"]["content"].endswith(
            TEXTO_INLINE_MARCADOR_DEFAULT,
        )


# ---------------------------------------------------------------------------
# Reconstrução fiel — propriedade chave
# ---------------------------------------------------------------------------


def test_chunkar_reconstroi_texto_original_em_caso_realista() -> None:
    """Acórdão sintético: cabeçalho + parágrafos longos + dispositivo.
    A concatenação tem que reproduzir o texto byte-a-byte.
    """
    paragrafos = []
    for i in range(20):
        # Cada parágrafo ~500 chars, total ~10k.
        paragrafos.append(f"Parágrafo {i}: " + ("lorem ipsum " * 40))
    texto = "\n\n".join(paragrafos)
    out = chunkar_para_rich_text(texto)
    assert "".join(it["text"]["content"] for it in out) == texto


def test_chunkar_formato_de_cada_item_e_compativel_com_api_notion() -> None:
    out = chunkar_para_rich_text("conteúdo arbitrário")
    assert len(out) == 1
    assert set(out[0].keys()) == {"type", "text"}
    assert out[0]["type"] == "text"
    assert set(out[0]["text"].keys()) == {"content"}


# ---------------------------------------------------------------------------
# Integração com _texto_inline_prop
# ---------------------------------------------------------------------------


def test_texto_inline_prop_devolve_rich_text_vazio_para_none() -> None:
    assert _texto_inline_prop(None) == {"rich_text": []}


def test_texto_inline_prop_devolve_rich_text_vazio_para_string_vazia() -> None:
    assert _texto_inline_prop("") == {"rich_text": []}


def test_texto_inline_prop_texto_curto_um_item() -> None:
    prop = _texto_inline_prop("Texto curto.")
    assert prop == {
        "rich_text": [
            {"type": "text", "text": {"content": "Texto curto."}},
        ],
    }


def test_texto_inline_prop_texto_longo_multiplos_items() -> None:
    """Texto > 1990 chars vira múltiplos itens — a chave do Round 11.3."""
    texto = "X" * 5000
    prop = _texto_inline_prop(texto)
    assert len(prop["rich_text"]) >= 3
    # Cada item respeita o limite duro da API.
    for item in prop["rich_text"]:
        assert len(item["text"]["content"]) <= 2000
    # Reconstrução exata.
    reconstruido = "".join(
        it["text"]["content"] for it in prop["rich_text"]
    )
    assert reconstruido == texto
