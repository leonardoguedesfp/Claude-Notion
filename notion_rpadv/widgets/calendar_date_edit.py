"""``CalendarDateEdit``: ``QDateEdit`` com popup de ``QCalendarWidget``
custom que abre em qualquer clique do mouse.

Motivação (smoke real, 2026-05-03): operadores reportaram que clicar
no campo de data não abria o calendário, e o ``mousePressEvent`` que
interceptava com ``keyPressEvent(Alt+Down)`` decrementava o ano em vez
de abrir popup (caminho de ``QDateTimeEdit`` no Qt difere quando o
event vem direto de ``keyPressEvent`` vs do dispatcher de shortcuts).

Esta versão usa ``QCalendarWidget`` próprio, controlado pela subclass:

- ``setCalendarPopup(False)`` desabilita o popup nativo do Qt — assim
  não há risco de 2 popups concorrentes nem comportamento ambíguo
  entre teclado e mouse.
- Clique esquerdo em qualquer parte do widget abre o popup customizado.
- Click numa data no calendário seta o valor e fecha o popup.
- Edição por teclado (Tab pra entrar, setas pra incrementar/decrementar
  seções) continua funcionando — preservamos o ``mousePressEvent`` do
  super() em outros botões.

Aplicação: substitui ``QDateEdit`` em qualquer lugar do app onde haja
seleção de data — usar este sempre por uniformidade.
"""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFocusEvent, QMouseEvent
from PySide6.QtWidgets import QCalendarWidget, QDateEdit, QWidget


class CalendarDateEdit(QDateEdit):
    """``QDateEdit`` que abre um ``QCalendarWidget`` em qualquer clique."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Desabilita o popup nativo do Qt — usamos o nosso pra evitar
        # conflito entre dispatchers de eventos.
        self.setCalendarPopup(False)
        # Cursor pointer reforça visualmente que o widget é clicável.
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cal_popup: QCalendarWidget | None = None

    def _ensure_popup(self) -> QCalendarWidget:
        """Lazy-inicializa o ``QCalendarWidget`` popup. Tem que ser lazy
        pra evitar criar widget Qt antes do ``QApplication`` estar pronto
        (importante pra testes que importam o módulo sem ainda ter um
        ``QApplication``)."""
        if self._cal_popup is None:
            cal = QCalendarWidget()
            # ``Qt.Popup`` faz o widget se comportar como menu/popup:
            # fecha automaticamente quando o foco é perdido (clique fora).
            cal.setWindowFlags(Qt.WindowType.Popup)
            cal.setGridVisible(True)
            cal.setVerticalHeaderFormat(
                QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader,
            )
            cal.clicked.connect(self._on_calendar_clicked)
            cal.activated.connect(self._on_calendar_clicked)
            self._cal_popup = cal
        return self._cal_popup

    def _on_calendar_clicked(self, qdate: QDate) -> None:
        """Click em uma data: aplica o valor + fecha o popup."""
        self.setDate(qdate)
        if self._cal_popup is not None:
            self._cal_popup.hide()

    def _show_calendar_popup(self) -> None:
        """Posiciona o popup logo abaixo do campo e exibe. Usa
        ``mapToGlobal`` pra cair no lugar certo independente do
        layout pai."""
        cal = self._ensure_popup()
        cal.setSelectedDate(self.date())
        # Posiciona embaixo do widget. Usar o canto inferior-esquerdo
        # da bbox do próprio QDateEdit em coordenadas globais.
        global_pos = self.mapToGlobal(self.rect().bottomLeft())
        cal.move(global_pos)
        cal.show()
        cal.raise_()
        cal.activateWindow()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Botão esquerdo abre o popup; outros botões caem no super()."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_calendar_popup()
            event.accept()
            return
        super().mousePressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        """Foco via TAB também abre o popup pro fluxo de teclado ficar
        consistente com o de mouse."""
        super().focusInEvent(event)
        if event.reason() == Qt.FocusReason.TabFocusReason:
            self._show_calendar_popup()
