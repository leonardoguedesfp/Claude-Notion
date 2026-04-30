"""Round 3b-2 — testes do override map + helpers de cor de chip.

A paleta de chip do app vem do override map em
``notion_rpadv.theme.colors_overrides`` (paleta brand do escritório),
não mais da paleta paralela ``NOTION_CHIP_PALETTE`` (estilo Notion web).
"""
from __future__ import annotations


def test_resolve_chip_color_known_override() -> None:
    """Override conhecido devolve ChipPalette da família correta."""
    from notion_rpadv.theme.tokens import LIGHT, resolve_chip_color

    pal = resolve_chip_color("Processos", "natureza", "Trabalhista")
    # Trabalhista → purple (área-foco do escritório, cor reservada).
    assert pal == LIGHT.chip_purple

    pal = resolve_chip_color("Processos", "natureza", "Cível")
    assert pal == LIGHT.chip_blue


def test_resolve_chip_color_unknown_falls_back_to_default() -> None:
    """Sem entry no override map → ChipPalette default (cinza neutro)."""
    from notion_rpadv.theme.tokens import LIGHT, resolve_chip_color

    pal = resolve_chip_color("Processos", "fase", "ValorInexistente")
    assert pal == LIGHT.chip_default

    # Base inexistente também cai em default.
    pal = resolve_chip_color("BaseInexistente", "x", "y")
    assert pal == LIGHT.chip_default


def test_resolve_chip_color_returns_brand_palette_only() -> None:
    """Toda família mapeada está nas 10 famílias brand de LIGHT.chip_*."""
    from notion_rpadv.theme.colors_overrides import OVERRIDES
    from notion_rpadv.theme.tokens import chip_palette

    valid_families = {
        "default", "blue", "purple", "green", "orange",
        "red", "yellow", "gray", "petrol", "pink",
    }
    # `amber` é alias técnico de orange em tokens.py — não usado em overrides.
    # `pink` adicionado no Round 4 pra Catalogo.categoria.
    for key, family in OVERRIDES.items():
        assert family in valid_families, (
            f"Override {key!r} → {family!r} não está nas 10 famílias brand."
        )
        # Também garante que chip_palette não cai em default por digitação.
        # (default é OK como override explícito; outras famílias não podem
        # cair em default por nome inválido.)
        if family != "default":
            pal = chip_palette(family)
            from notion_rpadv.theme.tokens import LIGHT
            assert pal != LIGHT.chip_default, (
                f"chip_palette({family!r}) caiu em default — nome inválido."
            )


def test_resolve_person_avatar_color_known_initials() -> None:
    """Iniciais conhecidas devolvem (bg, fg) sólidos prontos pra QColor."""
    from notion_rpadv.theme.tokens import resolve_person_avatar_color

    bg, fg = resolve_person_avatar_color("DM")  # Déborah → orange
    # bg vem de chip_orange.fg = #8B5028 (saturado, sólido)
    assert bg == "#8B5028"
    assert fg == "#EDEAE4"  # cream pro texto

    bg, fg = resolve_person_avatar_color("RP")  # Ricardo → purple
    assert bg == "#4B3E72"
    assert fg == "#EDEAE4"


def test_resolve_person_avatar_color_case_insensitive() -> None:
    """Lookup aceita caixa baixa / mista — tudo upper internamente."""
    from notion_rpadv.theme.tokens import resolve_person_avatar_color

    assert resolve_person_avatar_color("dm") == resolve_person_avatar_color("DM")
    assert resolve_person_avatar_color("Dm") == resolve_person_avatar_color("DM")


def test_resolve_person_avatar_color_unknown_falls_back_to_blue() -> None:
    """Iniciais desconhecidas caem em blue (família histórica do avatar)."""
    from notion_rpadv.theme.tokens import resolve_person_avatar_color

    bg, fg = resolve_person_avatar_color("ZZ")
    # blue: chip_blue.fg = #0C324D
    assert bg == "#0C324D"
    assert fg == "#EDEAE4"


def test_parse_color_hex_format() -> None:
    """Hex #RRGGBB → (r, g, b, 255)."""
    from notion_rpadv.theme.tokens import parse_color

    assert parse_color("#104063") == (0x10, 0x40, 0x63, 255)
    assert parse_color("#EDEAE4") == (0xED, 0xEA, 0xE4, 255)
    assert parse_color("#000000") == (0, 0, 0, 255)
    assert parse_color("#FFFFFF") == (255, 255, 255, 255)


def test_parse_color_rgba_format() -> None:
    """rgba(R,G,B,A) → (r, g, b, int(A*255))."""
    from notion_rpadv.theme.tokens import parse_color

    assert parse_color("rgba(16,64,99,0.10)") == (16, 64, 99, 26)
    assert parse_color("rgba(16, 64, 99, 0.10)") == (16, 64, 99, 26)  # whitespace
    assert parse_color("rgb(16,64,99)") == (16, 64, 99, 255)  # sem alpha
    assert parse_color("rgba(255,255,255,1.0)") == (255, 255, 255, 255)


def test_parse_color_invalid_raises() -> None:
    """String malformada → ValueError, não crash silencioso."""
    import pytest

    from notion_rpadv.theme.tokens import parse_color

    with pytest.raises(ValueError):
        parse_color("not a color")
    with pytest.raises(ValueError):
        parse_color("#XYZ")  # hex inválido (não 7 chars)


def test_parse_color_works_on_brand_palette() -> None:
    """Todos os bg/fg de LIGHT.chip_* são parseáveis sem erro."""
    from notion_rpadv.theme.tokens import LIGHT, parse_color

    for chip in (
        LIGHT.chip_default, LIGHT.chip_blue, LIGHT.chip_purple,
        LIGHT.chip_green, LIGHT.chip_orange, LIGHT.chip_red,
        LIGHT.chip_yellow, LIGHT.chip_gray, LIGHT.chip_petrol,
        LIGHT.chip_amber, LIGHT.chip_pink,
    ):
        # Não levanta:
        parse_color(chip.bg)
        parse_color(chip.fg)


def test_overrides_use_only_brand_families() -> None:
    """Toda família referenciada em OVERRIDES é uma das 10 brand."""
    from notion_rpadv.theme.colors_overrides import OVERRIDES

    valid = {
        "default", "blue", "purple", "green", "orange",
        "red", "yellow", "gray", "petrol", "pink",
    }
    used = set(OVERRIDES.values())
    invalid = used - valid
    assert not invalid, (
        f"Famílias inválidas em OVERRIDES: {invalid!r}. Usar só as 10 brand."
    )


def test_person_chip_colors_use_only_brand_families() -> None:
    """Toda família referenciada em PERSON_CHIP_COLORS é uma das 9 brand,
    excluindo `red` (reservado pra crítico) e `default` (regra/padrão)."""
    from notion_rpadv.theme.colors_overrides import PERSON_CHIP_COLORS

    valid_for_avatar = {
        "blue", "purple", "green", "orange",
        "yellow", "gray", "petrol",
    }
    used = set(PERSON_CHIP_COLORS.values())
    invalid = used - valid_for_avatar
    assert not invalid, (
        f"Famílias inválidas em PERSON_CHIP_COLORS: {invalid!r}. "
        f"`red` e `default` ficam reservadas — uso indevido pra avatar."
    )


def test_overrides_have_no_orphan_keys() -> None:
    """Sanity: chaves do override têm shape correto (3-tuple não-vazio)."""
    from notion_rpadv.theme.colors_overrides import OVERRIDES

    for key in OVERRIDES:
        assert isinstance(key, tuple) and len(key) == 3, (
            f"Chave {key!r} malformada — esperado (base, prop_key, value)."
        )
        base, prop_key, value = key
        assert base, f"base vazio em {key!r}"
        assert prop_key, f"prop_key vazio em {key!r}"
        assert value, f"value vazio em {key!r}"


# ---------------------------------------------------------------------------
# Regressão: API antiga removida no Round 3b-2
# ---------------------------------------------------------------------------


def test_legacy_chip_colors_for_removed() -> None:
    """``chip_colors_for`` foi removido — não voltar."""
    import notion_rpadv.theme.notion_colors as nc

    assert not hasattr(nc, "chip_colors_for"), (
        "chip_colors_for foi removido no Round 3b-2 — paleta brand "
        "vence sobre cores do Notion. Voltar é regressão."
    )


def test_legacy_hex_to_color_name_removed() -> None:
    """``hex_to_color_name`` foi removido."""
    import notion_rpadv.theme.notion_colors as nc

    assert not hasattr(nc, "hex_to_color_name"), (
        "hex_to_color_name foi removido no Round 3b-2."
    )


def test_legacy_notion_chip_palette_removed() -> None:
    """``NOTION_CHIP_PALETTE`` foi removido."""
    import notion_rpadv.theme.notion_colors as nc

    assert not hasattr(nc, "NOTION_CHIP_PALETTE"), (
        "NOTION_CHIP_PALETTE foi removido — rendering agora usa "
        "OVERRIDES + paleta brand."
    )


def test_color_to_hex_kept_for_diagnostics() -> None:
    """``color_to_hex`` permanece — é usado por schema_registry pra
    popular PropSpec.cor_por_valor (diagnóstico, não rendering).
    """
    from notion_rpadv.theme.notion_colors import color_to_hex

    # API segue funcionando como antes.
    assert color_to_hex("blue") == "#2196F3"
    assert color_to_hex("default") == "#E0E0E0"
    assert color_to_hex("inexistente") == "#E0E0E0"  # fallback default


# ---------------------------------------------------------------------------
# Round 3b-2 hotfix: regressão do QColor(rgba_string) preto
# ---------------------------------------------------------------------------


def test_qcolor_does_not_parse_rgba_string() -> None:
    """Documenta o motivo da existência de ``parse_color``: QColor do Qt
    NÃO parseia ``"rgba(R,G,B,A)"`` strings — o construtor cai num QColor
    inválido (renderiza preto). Antes do Round 3b-2, este bug deixava
    chips de relação (coluna Clientes, Processo pai etc.) com fundo preto
    e texto navy quase ilegível.

    Se este teste algum dia falhar (= QColor passou a aceitar rgba), o
    workaround do parse_color pode ser simplificado — mas até lá, todo
    QColor que recebe ``LIGHT.app_*`` que seja rgba precisa passar por
    ``parse_color`` antes.
    """
    from PySide6.QtGui import QColor

    qc = QColor("rgba(16,64,99,0.08)")
    assert not qc.isValid(), (
        "QColor passou a aceitar rgba strings — workaround do parse_color "
        "pode ser simplificado em delegates.py / pages/importar.py."
    )


def test_no_qcolor_with_rgba_token_in_prod_code() -> None:
    """Regressão do Round 3b-2: nenhum arquivo de prod faz
    ``QColor(LIGHT.app_<rgba_token>)`` sem passar por ``parse_color`` antes.
    Padrão proibido: ``QColor(LIGHT.app_accent_soft)`` ou
    ``QColor(p.app_warning_bg)`` direto, porque essas constantes são rgba
    strings e Qt cai em preto inválido (BUG #2 e #3 do round).
    """
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    prod_dirs = [repo_root / "notion_rpadv"]

    rgba_tokens = (
        "app_accent_soft",
        "app_warning_bg",
        "app_danger_bg",
        "app_success_bg",
        "app_info_bg",
        "app_row_hover",
        "app_row_selected",
        "app_cell_dirty",
        "app_divider",
        "app_sidebar_hover",
        "app_sidebar_active",
        "app_sidebar_fg_muted",
        "app_focus_ring",
    )
    pattern = re.compile(
        r"QColor\(\s*(?:LIGHT|p|self\._p)\.(" + "|".join(rgba_tokens) + r")\b",
    )

    offenders: list[str] = []
    for d in prod_dirs:
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    offenders.append(f"{py.relative_to(repo_root)}:{line_no}: {line.strip()}")

    assert not offenders, (
        "QColor(rgba_token) sem parse_color — vai renderizar preto.\n"
        + "\n".join(offenders)
    )
