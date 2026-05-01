"""Página "Leitor DJE" — Fase 1.

Permite escolher um intervalo de datas (default: ontem) e baixar todas
as publicações do DJEN dos 12 advogados do escritório, empilhando
em um xlsx único na pasta configurada.

Trabalho pesado (HTTP + xlsx) roda em QThread+worker pra não congelar
a UI (mesmo padrão da ExportarPage do Round 4 e da DashboardPage).

A área de log replica em tempo real cada advogado processado, e a
barra de progresso avança 1/12 por advogado concluído.

Settings persistidos via QSettings (mesmo store de ``last_user``):
- ``leitor_dje/output_dir``: diretório escolhido pelo usuário (sticky)
- ``leitor_dje/last_inicio``: última data inicial usada (sticky pra UX)

Default de ``output_dir`` é o caminho do Leonardo no SharePoint do
escritório (spec); se não existir no PC corrente e não for criável,
o app abre QFileDialog na hora do primeiro export pra usuário escolher.
"""
from __future__ import annotations

import datetime as _dt
import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import (
    QDate,
    QObject,
    QSettings,
    QThread,
    QUrl,
    Qt,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from notion_rpadv.services.dje_advogados import (
    ADVOGADOS,
    Advogado,
    format_advogado_label,
)
from notion_rpadv.services.dje_client import (
    AdvogadoResult,
    DJEClient,
)
from notion_rpadv.services.dje_exporter import write_publicacoes_xlsx
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

logger = logging.getLogger("dje.page")


_SETTINGS_ORG: str = "RPADV"
_SETTINGS_APP: str = "NotionApp"
_KEY_OUTPUT_DIR: str = "leitor_dje/output_dir"
_KEY_LAST_INICIO: str = "leitor_dje/last_inicio"

# Default conforme spec do operador (Leonardo). Em outros PCs o caminho
# pode não existir; o app tenta criar no momento do export, e se falhar
# abre QFileDialog pra usuário escolher.
DEFAULT_OUTPUT_DIR: str = (
    r"C:\Users\LeonardoGuedesdaFons\RICARDO PASSOS ADVOCACIA"
    r"\RICARDO PASSOS - CLIENTES-N\Reclamações Trabalhistas"
    r"\Ferramentas\Leitor DJE"
)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class _DJEWorker(QObject):
    """Worker que roda fetch_all + xlsx em thread separada. Emite logs
    e progresso pra UI. Em sucesso, devolve o path do arquivo gerado
    e a lista de advogados que falharam (pode ser vazia)."""

    log: Signal = Signal(str)                                # mensagem de log
    progress: Signal = Signal(int, int)                      # (idx, total)
    finished: Signal = Signal(str, list, int)                # (path, errors, total_items)
    error: Signal = Signal(str)                              # erro fatal (não recuperável)

    def __init__(
        self,
        advogados: list[Advogado],
        data_inicio: _dt.date,
        data_fim: _dt.date,
        output_dir: Path,
    ) -> None:
        super().__init__()
        self._advogados = advogados
        self._data_inicio = data_inicio
        self._data_fim = data_fim
        self._output_dir = output_dir
        self._client: DJEClient | None = None

    def run(self) -> None:
        try:
            self._client = DJEClient()
            self.log.emit(
                f"Iniciando varredura — {self._data_inicio.isoformat()} a "
                f"{self._data_fim.isoformat()} ({len(self._advogados)} advogados).",
            )
            summary = self._client.fetch_all(
                self._advogados,
                self._data_inicio,
                self._data_fim,
                on_progress=self._emit_progress,
            )
            self.log.emit(
                f"Varredura concluída — {summary.total_items} publicações "
                f"coletadas no total.",
            )
            path = write_publicacoes_xlsx(
                summary.rows,
                self._output_dir,
                self._data_inicio,
                self._data_fim,
            )
            self.log.emit(f"Arquivo salvo: {path}")
            errors = [
                format_advogado_label(r.advogado) for r in summary.errors
            ]
            self.finished.emit(str(path), errors, summary.total_items)
        except Exception as exc:  # noqa: BLE001
            logger.exception("DJE: erro fatal no worker")
            self.error.emit(f"{type(exc).__name__}: {exc}")

    def _emit_progress(
        self, idx: int, total: int, result: AdvogadoResult,
    ) -> None:
        label = format_advogado_label(result.advogado)
        if result.erro is not None:
            self.log.emit(
                f"[{idx}/{total}] {label} — FALHA: {result.erro}",
            )
        else:
            self.log.emit(
                f"[{idx}/{total}] {label} — "
                f"{len(result.items)} publicações em "
                f"{result.paginas} página(s)",
            )
        self.progress.emit(idx, total)


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------


class LeitorDJEPage(QWidget):
    """Página do app — sidebar/_DADOS_NAV. UI mínima: 2 date pickers,
    botão Baixar, área de log read-only, barra de progresso, botões
    pós-export pra abrir arquivo/pasta."""

    toast_requested: Signal = Signal(str, str)  # mensagem, kind

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

        # Settings
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        # Path do último export bem-sucedido — alimenta os botões "abrir".
        self._last_output_path: Path | None = None

        # Worker/thread refs
        self._worker: _DJEWorker | None = None
        self._thread: QThread | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        p = self._p
        # WA_StyledBackground (BUG-007): bg cream renderiza no paint do Qt
        self.setObjectName("LeitorDJEPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#LeitorDJEPage {{ background-color: {p.app_bg}; }}",
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(SP_8, SP_6, SP_8, SP_6)
        root.setSpacing(SP_4)

        # Heading
        heading = QLabel("Leitor DJE")
        heading_font = QFont(FONT_DISPLAY)
        heading_font.setPixelSize(22)
        heading_font.setWeight(QFont.Weight(FW_BOLD))
        heading.setFont(heading_font)
        heading.setStyleSheet(
            f"color: {p.app_fg_strong}; background: transparent; border: none;",
        )
        root.addWidget(heading)

        sub = QLabel(
            "Baixa publicações do DJEN no intervalo escolhido pros 12 "
            "advogados do escritório (busca por OAB/DF) e gera um Excel "
            "único empilhando todos os resultados.",
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM2}px; "
            "background: transparent; border: none;",
        )
        root.addWidget(sub)

        # Date pickers — default: ontem
        date_row = QHBoxLayout()
        date_row.setContentsMargins(0, SP_4, 0, 0)
        date_row.setSpacing(SP_3)

        ontem = _dt.date.today() - _dt.timedelta(days=1)
        last_inicio_iso = self._settings.value(_KEY_LAST_INICIO, "")
        if last_inicio_iso:
            try:
                ontem_setting = _dt.date.fromisoformat(last_inicio_iso)
                # Só usa se for recente (≤ 7 dias). Senão volta pra ontem.
                if (_dt.date.today() - ontem_setting).days <= 7:
                    ontem = ontem_setting
            except ValueError:
                pass

        di_label = QLabel("Data inicial:")
        di_label.setStyleSheet(self._label_css())
        date_row.addWidget(di_label)
        self._date_inicio = QDateEdit()
        self._date_inicio.setCalendarPopup(True)
        self._date_inicio.setDisplayFormat("dd/MM/yyyy")
        self._date_inicio.setDate(QDate(ontem.year, ontem.month, ontem.day))
        self._date_inicio.setStyleSheet(self._date_edit_css())
        date_row.addWidget(self._date_inicio)

        df_label = QLabel("Data final:")
        df_label.setStyleSheet(self._label_css())
        date_row.addWidget(df_label)
        self._date_fim = QDateEdit()
        self._date_fim.setCalendarPopup(True)
        self._date_fim.setDisplayFormat("dd/MM/yyyy")
        self._date_fim.setDate(QDate(ontem.year, ontem.month, ontem.day))
        self._date_fim.setStyleSheet(self._date_edit_css())
        date_row.addWidget(self._date_fim)

        date_row.addStretch()
        root.addLayout(date_row)

        # Botão + status
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, SP_4, 0, 0)
        action_row.setSpacing(SP_3)

        self._download_btn = QPushButton("Baixar publicações")
        self._download_btn.setFixedHeight(36)
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {p.app_accent};
                color: {p.app_accent_fg};
                font-size: {FS_MD}px;
                font-weight: {FW_BOLD};
                border: none;
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{ background-color: {p.app_accent_hover}; }}
            QPushButton:disabled {{
                background-color: {p.app_border};
                color: {p.app_fg_subtle};
            }}
            """,
        )
        self._download_btn.clicked.connect(self._on_download_clicked)
        action_row.addWidget(self._download_btn)

        self._open_file_btn = QPushButton("Abrir arquivo gerado")
        self._open_file_btn.setVisible(False)
        self._open_file_btn.setStyleSheet(self._secondary_btn_css())
        self._open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_file_btn.clicked.connect(self._on_open_file_clicked)
        action_row.addWidget(self._open_file_btn)

        self._open_dir_btn = QPushButton("Abrir pasta")
        self._open_dir_btn.setVisible(False)
        self._open_dir_btn.setStyleSheet(self._secondary_btn_css())
        self._open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_dir_btn.clicked.connect(self._on_open_dir_clicked)
        action_row.addWidget(self._open_dir_btn)

        action_row.addStretch()
        root.addLayout(action_row)

        # Aviso amarelo (oculto até falha parcial)
        self._warning_lbl = QLabel("")
        self._warning_lbl.setWordWrap(True)
        self._warning_lbl.setStyleSheet(
            f"QLabel {{"
            f" background-color: {p.app_warning_bg};"
            f" color: {p.app_warning};"
            f" border-left: 4px solid {p.app_warning};"
            f" padding: {SP_2}px {SP_3}px;"
            f" border-radius: {RADIUS_MD}px;"
            f" font-size: {FS_SM2}px;"
            f" }}",
        )
        self._warning_lbl.setVisible(False)
        root.addWidget(self._warning_lbl)

        # Barra de progresso
        self._progress = QProgressBar()
        self._progress.setRange(0, len(ADVOGADOS))
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%v / %m advogados")
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                background-color: {p.app_panel};
                text-align: center;
                font-size: {FS_SM2}px;
                color: {p.app_fg_muted};
            }}
            QProgressBar::chunk {{
                background-color: {p.app_accent};
                border-radius: {RADIUS_MD}px;
            }}
            """,
        )
        root.addWidget(self._progress)

        # Área de log (read-only)
        self._log_area = QPlainTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMinimumHeight(220)
        self._log_area.setPlaceholderText(
            "Log da varredura aparecerá aqui após clicar em "
            "'Baixar publicações'.",
        )
        self._log_area.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {p.app_panel};
                color: {p.app_fg};
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                padding: {SP_2}px {SP_3}px;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
                font-size: {FS_SM2}px;
            }}
            """,
        )
        root.addWidget(self._log_area, stretch=1)

    # ------------------------------------------------------------------
    # CSS helpers
    # ------------------------------------------------------------------

    def _label_css(self) -> str:
        p = self._p
        return (
            f"QLabel {{"
            f" color: {p.app_fg};"
            f" font-size: {FS_MD}px;"
            f" background: transparent;"
            f" border: none;"
            f" }}"
        )

    def _date_edit_css(self) -> str:
        p = self._p
        return (
            f"QDateEdit {{"
            f" background-color: {p.app_panel};"
            f" color: {p.app_fg};"
            f" border: 1px solid {p.app_border};"
            f" border-radius: {RADIUS_MD}px;"
            f" padding: {SP_2}px {SP_3}px;"
            f" font-size: {FS_MD}px;"
            f" min-width: 120px;"
            f" }}"
        )

    def _secondary_btn_css(self) -> str:
        p = self._p
        return (
            f"QPushButton {{"
            f" background-color: transparent;"
            f" color: {p.app_fg};"
            f" border: 1px solid {p.app_border};"
            f" border-radius: {RADIUS_MD}px;"
            f" padding: 0 {SP_3}px;"
            f" font-size: {FS_SM2}px;"
            f" }}"
            f"QPushButton:hover {{ background: {p.app_row_hover}; }}"
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_download_clicked(self) -> None:
        if self._thread is not None:
            return  # idempotente: clique repetido durante varredura
        di = self._date_inicio.date().toPython()
        df = self._date_fim.date().toPython()
        if df < di:
            self._set_warning(
                "Data final é anterior à data inicial. Ajuste e tente novamente.",
            )
            return

        # Resolve output_dir: settings, default, ou QFileDialog se falhar mkdir.
        output_dir = self._resolve_output_dir()
        if output_dir is None:
            # Usuário cancelou o dialog — nada a fazer.
            return

        # Reset UI
        self._warning_lbl.setVisible(False)
        self._open_file_btn.setVisible(False)
        self._open_dir_btn.setVisible(False)
        self._log_area.clear()
        self._progress.setValue(0)
        self._progress.setRange(0, len(ADVOGADOS))
        self._download_btn.setEnabled(False)

        # Persiste última data inicial (sticky pra UX).
        self._settings.setValue(_KEY_LAST_INICIO, di.isoformat())

        # Lança worker
        thread = QThread(self)
        worker = _DJEWorker(
            advogados=list(ADVOGADOS),
            data_inicio=di,
            data_fim=df,
            output_dir=output_dir,
        )
        worker.moveToThread(thread)
        worker.log.connect(self._on_log_line)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        thread.started.connect(worker.run)
        # Cleanup chain
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_done)
        self._worker = worker
        self._thread = thread
        thread.start()

    def _resolve_output_dir(self) -> Path | None:
        """Tenta resolver o diretório de output:
        1. Settings (persistido)
        2. DEFAULT_OUTPUT_DIR (Leonardo)
        3. mkdir; se falhar, QFileDialog

        Retorna None se usuário cancelou QFileDialog.
        """
        candidate = self._settings.value(_KEY_OUTPUT_DIR, "") or DEFAULT_OUTPUT_DIR
        path = Path(candidate)
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except (OSError, PermissionError) as exc:
            logger.warning(
                "DJE: não consegui criar/acessar %s: %s. Pedindo path ao usuário.",
                path, exc,
            )
        # Fallback: dialog
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Escolha onde salvar o arquivo Excel",
            str(Path.home()),
        )
        if not chosen:
            return None
        chosen_path = Path(chosen)
        self._settings.setValue(_KEY_OUTPUT_DIR, str(chosen_path))
        return chosen_path

    def _on_log_line(self, line: str) -> None:
        self._log_area.appendPlainText(line)

    def _on_progress(self, idx: int, total: int) -> None:
        if self._progress.maximum() != total:
            self._progress.setRange(0, total)
        self._progress.setValue(idx)

    def _on_finished(
        self, path: str, errors: list, total_items: int,
    ) -> None:
        self._last_output_path = Path(path)
        self._open_file_btn.setVisible(True)
        self._open_dir_btn.setVisible(True)
        if errors:
            self._set_warning(
                "Atenção: o arquivo foi gerado MAS está incompleto. "
                f"Falha persistente em {len(errors)} advogado(s): "
                + ", ".join(errors)
                + ". Tente novamente mais tarde pra completar.",
            )
            self.toast_requested.emit(
                f"Snapshot DJE gerado com falha em {len(errors)} advogado(s).",
                "warning",
            )
        else:
            self.toast_requested.emit(
                f"Snapshot DJE gerado: {total_items} publicações.",
                "success",
            )

    def _on_error(self, msg: str) -> None:
        self._set_warning(f"Erro fatal: {msg}")
        self.toast_requested.emit(
            "Falha ao gerar snapshot DJE.", "error",
        )

    def _on_thread_done(self) -> None:
        self._thread = None
        self._worker = None
        self._download_btn.setEnabled(True)

    def _set_warning(self, msg: str) -> None:
        self._warning_lbl.setText(msg)
        self._warning_lbl.setVisible(True)

    def _on_open_file_clicked(self) -> None:
        if self._last_output_path is None or not self._last_output_path.exists():
            QMessageBox.warning(
                self, "Arquivo não encontrado",
                "O arquivo gerado não existe mais. Rode novamente.",
            )
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self._last_output_path)),
        )

    def _on_open_dir_clicked(self) -> None:
        if self._last_output_path is None:
            return
        target = self._last_output_path.parent
        if not target.exists():
            QMessageBox.warning(
                self, "Pasta não encontrada",
                "A pasta de destino não existe mais.",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
