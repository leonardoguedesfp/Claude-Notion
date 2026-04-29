"""Round simplificação chip palette (Lote 1): testes da paleta
``NOTION_CHIP_PALETTE`` + ``chip_colors_for`` + ``hex_to_color_name``
em ``notion_rpadv.theme.notion_colors``.

Antes do round, o ``_contrasting_text_color`` em ``delegates.py`` retornava
preto OU branco binário baseado em luminância. Resultado: texto preto
sobre fundo azul claro ficava agressivo. Substituído por mapa explícito
de pares (bg_light, fg_dark) por nome de cor do Notion — fundo claro +
texto escuro saturado da MESMA família.
"""
from __future__ import annotations


def test_chip_colors_known_notion_color() -> None:
    """Para cor conhecida do Notion, retorna par (bg, fg) específico
    da família, não preto/branco binário."""
    from notion_rpadv.theme.notion_colors import chip_colors_for

    bg, fg = chip_colors_for("blue")
    assert bg.lower() == "#d3e5ef", (
        f"Background do chip 'blue' deveria ser azul claro (#D3E5EF); "
        f"obtido {bg!r}."
    )
    assert fg.lower() == "#0b4a6f", (
        f"Texto do chip 'blue' deveria ser azul escuro saturado "
        f"(#0B4A6F), não preto puro nem branco; obtido {fg!r}."
    )
    # Garantir que não é o binário antigo
    assert fg.lower() not in ("#000000", "#111111", "#fafafa", "#ffffff"), (
        "Cor do texto não pode ser o binário preto/branco do "
        "_contrasting_text_color (substituído neste round)."
    )


def test_chip_colors_unknown_falls_back_to_default() -> None:
    """Cor desconhecida cai em 'default' (cinza neutro), sem crash."""
    from notion_rpadv.theme.notion_colors import chip_colors_for

    bg, fg = chip_colors_for("teal_inexistente")
    # default = ("#E0E0E0", "#37352F")
    assert bg.lower() == "#e0e0e0"
    assert fg.lower() == "#37352f"


def test_chip_colors_all_notion_families_present() -> None:
    """Todas as 10 cores nominais do Notion devem ter par na paleta."""
    from notion_rpadv.theme.notion_colors import (
        NOTION_CHIP_PALETTE, NOTION_COLOR_TO_HEX,
    )

    for color_name in NOTION_COLOR_TO_HEX:
        assert color_name in NOTION_CHIP_PALETTE, (
            f"Cor {color_name!r} está em NOTION_COLOR_TO_HEX mas não "
            "tem par em NOTION_CHIP_PALETTE — chip vai cair em "
            "'default' (cinza) silenciosamente."
        )


def test_chip_palette_pairs_are_hex_strings() -> None:
    """Cada par é (bg_hex, fg_hex) com formato #RRGGBB."""
    from notion_rpadv.theme.notion_colors import NOTION_CHIP_PALETTE

    for color_name, pair in NOTION_CHIP_PALETTE.items():
        assert isinstance(pair, tuple) and len(pair) == 2, (
            f"{color_name}: par malformado, esperado (bg, fg)."
        )
        bg, fg = pair
        for label, val in (("bg", bg), ("fg", fg)):
            assert val.startswith("#") and len(val) == 7, (
                f"{color_name}.{label}: hex inválido {val!r}, "
                "esperado #RRGGBB."
            )


def test_hex_to_color_name_round_trip() -> None:
    """``hex_to_color_name(color_to_hex(name)) == name`` para todas as
    cores conhecidas."""
    from notion_rpadv.theme.notion_colors import (
        NOTION_COLOR_TO_HEX, color_to_hex, hex_to_color_name,
    )

    for name in NOTION_COLOR_TO_HEX:
        assert hex_to_color_name(color_to_hex(name)) == name, (
            f"Round-trip falhou para {name!r}: "
            f"color_to_hex → {color_to_hex(name)!r}, "
            f"hex_to_color_name → {hex_to_color_name(color_to_hex(name))!r}."
        )


def test_hex_to_color_name_case_insensitive() -> None:
    """Lookup deve aceitar hex em qualquer caixa (#2196F3 ou #2196f3)."""
    from notion_rpadv.theme.notion_colors import hex_to_color_name

    assert hex_to_color_name("#2196F3") == "blue"
    assert hex_to_color_name("#2196f3") == "blue"
    assert hex_to_color_name("") == "default"
    assert hex_to_color_name("#XYZ123") == "default"


def test_hex_to_color_name_unknown_returns_default() -> None:
    """Hex que não bate com nenhuma cor conhecida → 'default'."""
    from notion_rpadv.theme.notion_colors import hex_to_color_name

    assert hex_to_color_name("#123456") == "default"
    assert hex_to_color_name("#ABCDEF") == "default"


def test_contrasting_text_color_helper_removed() -> None:
    """O helper ``_contrasting_text_color`` foi removido de delegates.py
    e de multi_select_editor.py — não voltar."""
    from notion_rpadv.models import delegates as dmod
    from notion_rpadv.widgets import multi_select_editor as mse

    assert not hasattr(dmod, "_contrasting_text_color"), (
        "_contrasting_text_color foi removido de delegates.py — "
        "voltar é regressão para o binário preto/branco."
    )
    assert not hasattr(mse, "_contrasting_text_color"), (
        "_contrasting_text_color foi removido de multi_select_editor.py."
    )
