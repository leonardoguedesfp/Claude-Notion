"""Hotfix paint ghosts v2 (Lote 1): testes do override de
``initStyleOption`` em PropDelegate / SucessorDelegate.

Substitui ``test_paint_bg_helper.py`` (v1, removido). O helper externo
``_paint_background_only`` do v1 era furado: zerava ``opt.text`` em
cópia, mas Qt internamente chamava ``initStyleOption`` de novo dentro
do ``QStyledItemDelegate.paint``, repopulando o text e mantendo o
ghost.

A solução real é fazer override do próprio ``initStyleOption`` (que é
virtual). Quando Qt chama internamente, cai no override que zera o
text nas condições corretas.

Round simplificação CnjDelegate (Lote 1): CnjDelegate foi removido
junto com seu override. Coluna numero_do_processo agora usa
PropDelegate default — texto pintado normalmente.

Os testes abaixo validam as 2 implementações remanescentes do override:
- PropDelegate zera para tipos chip (relation/select/multi_select).
- PropDelegate preserva para tipos default (rich_text, number, date).
- SucessorDelegate zera só quando há valor (preserva placeholder "—").
"""
from __future__ import annotations

import pytest

try:
    import PySide6  # noqa: F401
    _PYSIDE6 = True
except ImportError:
    _PYSIDE6 = False

requires_pyside6 = pytest.mark.skipif(
    not _PYSIDE6, reason="PySide6 not installed",
)


# ---------------------------------------------------------------------------
# PropDelegate.initStyleOption
# ---------------------------------------------------------------------------


@requires_pyside6
def test_propdelegate_initstyleoption_zeros_text_for_chip_types() -> None:
    """Para tipos que pintam chips (relation, select, multi_select), o
    override zera ``option.text`` antes de Qt pintar — sem isso, o
    chip arredondado deixa a letra final do texto bruto vazando à
    direita."""
    import sys
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
    QApplication.instance() or QApplication(sys.argv)

    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models import delegates as dmod
    from notion_rpadv.models.delegates import PropDelegate

    delegate = PropDelegate()

    for tipo in ("relation", "select", "multi_select"):
        spec = PropSpec(
            notion_name="X", tipo=tipo, label="X",
            opcoes=("A", "B"),
        )
        original = dmod._get_spec_from_index
        dmod._get_spec_from_index = lambda idx, _spec=spec: _spec
        try:
            opt = QStyleOptionViewItem()
            opt.text = "valor-bruto"
            delegate.initStyleOption(opt, QModelIndex())
            assert opt.text == "", (
                f"PropDelegate.initStyleOption deveria zerar text para "
                f"tipo {tipo!r}; obtido {opt.text!r}."
            )
            assert not (
                opt.features
                & QStyleOptionViewItem.ViewItemFeature.HasDisplay
            ), (
                f"HasDisplay deveria ser removida para tipo {tipo!r}."
            )
        finally:
            dmod._get_spec_from_index = original


@requires_pyside6
def test_propdelegate_initstyleoption_preserves_text_for_default_types() -> None:
    """Para tipos sem chip (rich_text, number, date, etc.), o override
    NÃO zera o text. Qt pode então pintar normalmente."""
    import sys
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
    QApplication.instance() or QApplication(sys.argv)

    from notion_bulk_edit.schemas import PropSpec
    from notion_rpadv.models import delegates as dmod
    from notion_rpadv.models.delegates import PropDelegate

    delegate = PropDelegate()

    for tipo in ("rich_text", "number", "date", "checkbox", "title"):
        spec = PropSpec(notion_name="X", tipo=tipo, label="X")
        original = dmod._get_spec_from_index
        dmod._get_spec_from_index = lambda idx, _spec=spec: _spec
        try:
            opt = QStyleOptionViewItem()
            opt.text = "preserve-me"
            delegate.initStyleOption(opt, QModelIndex())
            # super().initStyleOption pode reescrever via index.data;
            # com QModelIndex inválido nada é populado. O importante é:
            # NÃO foi explicitamente zerado pelo nosso override.
            assert opt.text == "preserve-me", (
                f"Tipo {tipo!r}: text foi zerado quando não deveria. "
                "Override só pode zerar para tipos chip."
            )
        finally:
            dmod._get_spec_from_index = original


@requires_pyside6
def test_propdelegate_initstyleoption_no_spec_preserves_text() -> None:
    """Sem spec resolvido (ex: índice fora do schema), preserva o
    comportamento padrão de Qt — não zera nada."""
    import sys
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.models import delegates as dmod
    from notion_rpadv.models.delegates import PropDelegate

    delegate = PropDelegate()
    original = dmod._get_spec_from_index
    dmod._get_spec_from_index = lambda idx: None
    try:
        opt = QStyleOptionViewItem()
        opt.text = "fallback"
        delegate.initStyleOption(opt, QModelIndex())
        assert opt.text == "fallback"
    finally:
        dmod._get_spec_from_index = original


# Round simplificação CnjDelegate (Lote 1): CnjDelegate foi REMOVIDO
# da hierarquia. O teste antigo de initStyleOption do CnjDelegate
# perdeu sentido. Coluna numero_do_processo agora cai no PropDelegate
# default — initStyleOption padrão do Qt pinta texto normalmente
# (preserva cabeçalho, tipo de conteúdo, etc.).


# ---------------------------------------------------------------------------
# SucessorDelegate.initStyleOption — zera só quando há valor
# ---------------------------------------------------------------------------


@requires_pyside6
def test_sucessordelegate_initstyleoption_zeros_when_value_present() -> None:
    """SucessorDelegate zera quando há valor real ('João' etc.) via
    valor populado pelo super().initStyleOption."""
    import sys
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.models.delegates import SucessorDelegate

    delegate = SucessorDelegate()

    # SucessorDelegate.initStyleOption lê index.data(DisplayRole). Como
    # QModelIndex() é inválido, retorna None — nosso teste precisa de
    # uma model trivial que devolva um valor real para o display role.
    from PySide6.QtCore import QAbstractListModel, Qt

    class _StubModel(QAbstractListModel):
        def __init__(self, value):
            super().__init__()
            self._value = value

        def rowCount(self, parent=QModelIndex()):  # type: ignore[override]
            return 1

        def data(self, index, role=Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
            if role == Qt.ItemDataRole.DisplayRole:
                return self._value
            return None

    model = _StubModel("João da Silva")
    idx = model.index(0)
    opt = QStyleOptionViewItem()
    delegate.initStyleOption(opt, idx)
    assert opt.text == "", (
        f"Com valor real, SucessorDelegate.initStyleOption deveria "
        f"zerar text; obtido {opt.text!r}."
    )


@requires_pyside6
def test_sucessordelegate_initstyleoption_preserves_when_placeholder() -> None:
    """SucessorDelegate preserva text quando display é vazio ou '—'."""
    import sys
    from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
    QApplication.instance() or QApplication(sys.argv)

    from notion_rpadv.models.delegates import SucessorDelegate

    delegate = SucessorDelegate()

    class _StubModel(QAbstractListModel):
        def __init__(self, value):
            super().__init__()
            self._value = value

        def rowCount(self, parent=QModelIndex()):  # type: ignore[override]
            return 1

        def data(self, index, role=Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
            if role == Qt.ItemDataRole.DisplayRole:
                return self._value
            return None

    for placeholder in ("—", "", None):
        model = _StubModel(placeholder)
        idx = model.index(0)
        opt = QStyleOptionViewItem()
        # super().initStyleOption pode popular o text via DisplayRole.
        # Importante: nosso override NÃO deve zerar para placeholder.
        delegate.initStyleOption(opt, idx)
        # Para placeholder None/"" o super().initStyleOption não popula
        # (text vazio). Para "—" o super popula com "—". Em ambos os
        # casos, NÃO foi forçado a vazio pelo nosso override.
        if placeholder == "—":
            assert opt.text == "—", (
                "Para placeholder '—', SucessorDelegate deveria "
                "preservar para Qt pintar o placeholder normalmente."
            )


# ---------------------------------------------------------------------------
# Verificação estática — _paint_background_only foi removido
# ---------------------------------------------------------------------------


def test_paint_background_only_helper_removed() -> None:
    """O helper ``_paint_background_only`` do v1 era furado e foi
    removido no v2 — fica garantido que não voltou."""
    from notion_rpadv.models import delegates as dmod
    assert not hasattr(dmod, "_paint_background_only"), (
        "Helper _paint_background_only foi removido no hotfix v2 — "
        "voltar a usar é regressão (Qt repopula opt.text via "
        "initStyleOption interno)."
    )
