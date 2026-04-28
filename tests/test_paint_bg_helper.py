"""Hotfix paint ghosts (Lote 1): testes do helper _paint_background_only.

Garante que o helper:
1. Zera ``opt.text`` antes de chamar ``super().paint`` — proteção contra
   regressão do bug em que ``super().paint(painter, option, index)``
   pintava o texto bruto (ex: "Cognitiva") por baixo dos chips
   arredondados, deixando a letra final vazando à direita.
2. Remove ``HasDisplay`` da ``opt.features`` para que o paint padrão de
   Qt não considere texto como dado de display.
3. É invocado pelos call-sites em CnjDelegate e PropDelegate (verificação
   estática via inspect.getsource — paint via mock é frágil em PySide6).
"""
from __future__ import annotations

import inspect

import pytest

try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(
    not _PYSIDE6, reason="PySide6 not installed",
)


@requires_pyside6
def test_background_only_zeros_text() -> None:
    """O helper modifica a cópia do option de modo a zerar o texto antes
    de delegar ao paint da classe pai.

    Como o ``super(type(delegate), delegate).paint(painter, opt, index)``
    em Qt rejeita MagicMock como painter, capturamos o ``opt`` mutado
    interceptando ``QStyledItemDelegate.paint`` (alvo da resolução do
    super para subclasses que herdam direto dele) e validando o estado
    de ``opt.text`` / ``opt.features`` no momento da invocação.

    Usamos uma subclasse trivial de QStyledItemDelegate em vez do tipo
    base — ``super(QStyledItemDelegate, delegate)`` resolveria para
    QAbstractItemDelegate (pure virtual). Subclasse → resolve para
    QStyledItemDelegate como esperado.
    """
    import sys
    from unittest.mock import patch
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import (
        QApplication, QStyleOptionViewItem, QStyledItemDelegate,
    )
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.models.delegates import _paint_background_only

    class _StubDelegate(QStyledItemDelegate):
        pass

    delegate = _StubDelegate()

    option = QStyleOptionViewItem()
    option.text = "exemplo-que-nao-deveria-ser-pintado"

    captured: dict[str, object] = {}

    def fake_paint(self, painter, opt, index):  # type: ignore[no-redef]
        captured["text"] = opt.text
        captured["has_display"] = bool(
            opt.features & QStyleOptionViewItem.ViewItemFeature.HasDisplay,
        )

    with patch.object(QStyledItemDelegate, "paint", fake_paint):
        _paint_background_only(None, option, QModelIndex(), delegate)

    assert captured.get("text") == "", (
        f"opt.text deveria ser vazia no super().paint; obtido "
        f"{captured.get('text')!r}. Regressão do hotfix paint ghosts."
    )
    assert captured.get("has_display") is False, (
        "opt.features.HasDisplay deveria ser removida antes do "
        "super().paint."
    )


@requires_pyside6
def test_cnj_delegate_uses_paint_background_only() -> None:
    """Verificação estática: CnjDelegate.paint chama
    _paint_background_only no caminho de two-line render."""
    from notion_rpadv.models.delegates import CnjDelegate

    src = inspect.getsource(CnjDelegate.paint)
    assert "_paint_background_only" in src, (
        "CnjDelegate.paint deveria usar _paint_background_only para o "
        "background do two-line render (hotfix paint ghosts)."
    )


@requires_pyside6
def test_prop_delegate_uses_paint_background_only() -> None:
    """Verificação estática: PropDelegate.paint usa
    _paint_background_only nos paths de chip (relation + select/multi)."""
    from notion_rpadv.models.delegates import PropDelegate

    src = inspect.getsource(PropDelegate.paint)
    # Deve aparecer pelo menos 2 vezes — uma no path de relation e
    # outra no path de select/multi_select.
    count = src.count("_paint_background_only")
    assert count >= 2, (
        f"PropDelegate.paint deveria usar _paint_background_only ao menos "
        f"2 vezes (relation + select/multi); obtido {count}."
    )


@requires_pyside6
def test_helper_preserves_alternating_row_via_init_style_option() -> None:
    """initStyleOption deve ser chamado pelo helper para popular
    palette/state — sem isso, alternating row não pinta corretamente."""
    from notion_rpadv.models.delegates import _paint_background_only

    src = inspect.getsource(_paint_background_only)
    assert "initStyleOption" in src, (
        "Helper deve chamar delegate.initStyleOption(opt, index) "
        "ANTES de zerar opt.text — sem isso, alternating row "
        "highlight pode não pintar."
    )
    # Ordem importa: initStyleOption depois zerar opt.text (o método
    # repopula o text se chamado depois).
    init_pos = src.find("initStyleOption")
    text_zero_pos = src.find('opt.text = ""')
    assert 0 < init_pos < text_zero_pos, (
        "Ordem incorreta: ``opt.text = \"\"`` deve vir DEPOIS de "
        "initStyleOption (que repopula opt.text se chamado depois)."
    )
