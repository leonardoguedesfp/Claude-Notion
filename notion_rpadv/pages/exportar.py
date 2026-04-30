"""Round 4 Frente 4 — página "Exportar dados".

Permite ao usuário gerar um xlsx de snapshot completo das 4 bases (ou
um subconjunto). UI mínima: 4 checkboxes pra selecionar bases (todas
marcadas por default), botão "Exportar", e uma área de status que mostra
progresso durante o fetch + write e o resultado final (sucesso ou erro).

Trabalho pesado (fetch da API + openpyxl write) roda num QThread+worker
pra não congelar a UI. Worker emite sinais de progresso, finished e
error que o main thread consome pra atualizar a label de status.

Decisões já tomadas no spec: sem agendamento automático, sem upload
para SharePoint, sem filtros de registros, sem cor nas células, sem
restrição de acesso. UI deliberadamente espartana.

Acesso via menu (Ações no command palette) — _PAGE_EXPORTAR é
registrado no MainWindow junto com os outros pages utilitários
(Importar, Logs, Config).
"""
from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from notion_bulk_edit.config import DATA_SOURCES
from notion_rpadv.theme.tokens import (
    FONT_DISPLAY,
    FS_MD,
    FS_SM2,
    FW_BOLD,
    LIGHT,
    Palette,
    RADIUS_MD,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
    SP_8,
)


_BASE_DISPLAY: dict[str, str] = {
    "Clientes":  "👥 Clientes",
    "Processos": "⚖️ Processos",
    "Tarefas":   "🎯 Tarefas",
    "Catalogo":  "📚 Catálogo de Tarefas",
}

# Ordem de exibição (mantém ordem do spec).
_BASE_ORDER: list[str] = ["Clientes", "Processos", "Tarefas", "Catalogo"]


class _ExportWorker(QObject):
    """Worker em QThread que executa export_snapshot. Emite progresso por
    base + phase pra UI atualizar a label de status."""

    progress: Signal = Signal(str, str, int, int)  # base, phase, count, total
    finished: Signal = Signal(object)              # ExportResult
    error: Signal = Signal(str)                    # mensagem

    def __init__(self, token: str, bases: list[str], dest_path: str) -> None:
        super().__init__()
        self._token = token
        self._bases = bases
        self._dest_path = dest_path

    def run(self) -> None:
        try:
            from notion_rpadv.services.snapshot_exporter import export_snapshot
            result = export_snapshot(
                token=self._token,
                bases=self._bases,
                dest_path=self._dest_path,
                on_progress=self._emit_progress,
            )
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"{type(exc).__name__}: {exc}")

    def _emit_progress(
        self, base: str, phase: str, count: int, total: int,
    ) -> None:
        self.progress.emit(base, phase, count, total)


class ExportarPage(QWidget):
    """Página de exportação. 4 checkboxes + botão + status."""

    toast_requested: Signal = Signal(str, str)  # message, kind

    def __init__(
        self,
        conn: sqlite3.Connection,
        token: str,
        user: str,
        parent: QWidget | None = None,
        audit_conn: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._audit_conn = audit_conn or conn
        self._token = token
        self._user = user
        self._p: Palette = LIGHT

        self._checkboxes: dict[str, QCheckBox] = {}
        self._status_lbl: QLabel | None = None
        self._export_btn: QPushButton | None = None

        # Worker/thread refs (mantidos pra evitar GC mid-export)
        self._worker: _ExportWorker | None = None
        self._thread: QThread | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        p = self._p
        # BUG-007 (auditoria 2026-04-29): WA_StyledBackground é obrigatório
        # em QWidget plain — sem ele o stylesheet processa a palette mas o
        # paintEvent não pinta o bg, e a página vaza pra cor default do Qt.
        self.setObjectName("ExportarPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#ExportarPage {{ background-color: {p.app_bg}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(SP_8, SP_6, SP_8, SP_6)
        root.setSpacing(SP_4)

        # Heading
        heading = QLabel("Exportar dados")
        heading_font = QFont(FONT_DISPLAY)
        heading_font.setPixelSize(22)
        heading_font.setWeight(QFont.Weight(FW_BOLD))
        heading.setFont(heading_font)
        heading.setStyleSheet(
            f"color: {p.app_fg_strong}; background: transparent; border: none;"
        )
        root.addWidget(heading)

        sub = QLabel(
            "Gere um snapshot em Excel (.xlsx) com o estado atual das bases "
            "selecionadas. Uma aba por base, mais uma aba auxiliar com "
            "metadados e legenda. O snapshot reflete o estado no momento da "
            "geração e não é atualizado em tempo real.",
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM2}px; "
            "background: transparent; border: none;",
        )
        root.addWidget(sub)

        # Checkboxes — todas marcadas por default
        cb_label = QLabel("Selecione as bases a exportar:")
        cb_label.setStyleSheet(
            f"color: {p.app_fg}; font-size: {FS_MD}px; font-weight: {FW_BOLD}; "
            "background: transparent; border: none; "
            f"margin-top: {SP_4}px;",
        )
        root.addWidget(cb_label)

        for base in _BASE_ORDER:
            if base not in DATA_SOURCES:
                continue
            cb = QCheckBox(_BASE_DISPLAY.get(base, base))
            cb.setChecked(True)
            # Round 4 hotfix: NÃO sobrescrever ``QCheckBox::indicator`` size
            # sem definir ``image`` pros estados :checked/:unchecked. No
            # Windows, fixar width/height invalida o rendering nativo do ✓
            # do Qt e o checkbox vira um quadrado sólido sem indicador.
            # Smoke do operador (Round 4 pós-merge): ✓ ausente até clique.
            # Solução: deixar o indicator no default Qt — só estiliza o
            # texto/padding/background do QCheckBox em si.
            cb.setStyleSheet(
                f"QCheckBox {{ color: {p.app_fg}; font-size: {FS_MD}px; "
                f"padding: {SP_2}px {SP_3}px; background: transparent; }}",
            )
            self._checkboxes[base] = cb
            root.addWidget(cb)

        # Action row: botão + status
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, SP_4, 0, 0)
        action_row.setSpacing(SP_3)

        self._export_btn = QPushButton("Exportar")
        self._export_btn.setObjectName("BtnPrimary")
        self._export_btn.setFixedHeight(36)
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setStyleSheet(
            f"""
            QPushButton#BtnPrimary {{
                background-color: {p.app_accent}; color: {p.app_accent_fg};
                font-size: {FS_MD}px; font-weight: {FW_BOLD};
                border: none; border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton#BtnPrimary:hover {{
                background-color: {p.app_accent_hover};
            }}
            QPushButton#BtnPrimary:disabled {{
                background-color: {p.app_border}; color: {p.app_fg_subtle};
            }}
            """,
        )
        self._export_btn.clicked.connect(self._on_export_clicked)
        action_row.addWidget(self._export_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM2}px; "
            "background: transparent; border: none;",
        )
        action_row.addWidget(self._status_lbl, stretch=1)

        root.addLayout(action_row)
        root.addStretch()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _collect_bases(self) -> list[str]:
        """Lista de bases atualmente marcadas, na ordem do spec
        (``_BASE_ORDER``). Extraído como método pra ser testável sem
        clique em botão e pra centralizar o critério de "base
        selecionada"."""
        return [
            b for b in _BASE_ORDER
            if b in self._checkboxes and self._checkboxes[b].isChecked()
        ]

    def _on_export_clicked(self) -> None:
        if self._thread is not None:
            # Já tem export rodando — guard idempotente.
            return
        bases = self._collect_bases()
        if not bases:
            # Round 4 hotfix: emite toast também (não só status label)
            # pra que o feedback fique visível mesmo se a label estiver
            # fora da viewport. Mensagem amigável em vez do ValueError
            # genérico que viria do exporter caso o guard fosse furado.
            self._set_status(
                "Selecione pelo menos uma base.", kind="warning",
            )
            self.toast_requested.emit(
                "Selecione pelo menos uma base.", "warning",
            )
            return

        # Diálogo de save com timestamp default
        ts = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
        default_name = f"notion-snapshot-{ts}.xlsx"
        default_dir = str(Path.home() / "Downloads")
        dest, _filter = QFileDialog.getSaveFileName(
            self,
            "Salvar snapshot como",
            f"{default_dir}/{default_name}",
            "Excel (*.xlsx)",
        )
        if not dest:
            return

        # Lança worker em thread separada
        self._set_status("Iniciando exportação...", kind="info")
        if self._export_btn is not None:
            self._export_btn.setEnabled(False)

        thread = QThread(self)
        worker = _ExportWorker(self._token, bases, dest)
        worker.moveToThread(thread)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_export_finished)
        worker.error.connect(self._on_export_error)
        thread.started.connect(worker.run)
        # Cleanup chain: depois de finished/error, encerra thread + GC
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_done)
        self._worker = worker
        self._thread = thread
        thread.start()

    def _on_progress(
        self, base: str, phase: str, count: int, total: int,
    ) -> None:
        if phase == "fetch":
            self._set_status(
                f"Lendo {base}: {count} registros...", kind="info",
            )
        else:  # write
            if total > 0:
                self._set_status(
                    f"Escrevendo {base}: {count}/{total} linhas...",
                    kind="info",
                )
            else:
                self._set_status(f"Escrevendo {base}...", kind="info")

    def _on_export_finished(self, result: Any) -> None:
        total = sum(result.counts.values())
        msg = (
            f"Exportação concluída: {total} registros em "
            f"{result.duration_seconds:.1f}s. Arquivo: {result.dest_path}"
        )
        if result.relation_misses > 0:
            msg += (
                f" (atenção: {result.relation_misses} relations "
                "apontaram pra páginas fora do snapshot, "
                "renderizadas como '[?]')"
            )
        self._set_status(msg, kind="success")
        self.toast_requested.emit("Snapshot gerado.", "success")

    def _on_export_error(self, msg: str) -> None:
        self._set_status(f"Falha na exportação: {msg}", kind="error")
        self.toast_requested.emit("Falha ao gerar snapshot.", "error")

    def _on_thread_done(self) -> None:
        self._thread = None
        self._worker = None
        if self._export_btn is not None:
            self._export_btn.setEnabled(True)

    def _set_status(self, msg: str, kind: str = "info") -> None:
        if self._status_lbl is None:
            return
        p = self._p
        color_map = {
            "info":    p.app_fg_muted,
            "success": p.app_success,
            "warning": p.app_warning,
            "error":   p.app_danger,
        }
        color = color_map.get(kind, p.app_fg_muted)
        self._status_lbl.setStyleSheet(
            f"color: {color}; font-size: {FS_SM2}px; "
            "background: transparent; border: none;",
        )
        self._status_lbl.setText(msg)
