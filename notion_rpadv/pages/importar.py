"""Import page — 3-step stepper for Excel import."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from notion_bulk_edit.config import DATA_SOURCES
from notion_rpadv.theme.tokens import (
    FONT_DISPLAY,
    FS_MD,
    FS_SM,
    FS_SM2,
    FW_BOLD,
    FW_MEDIUM,
    LIGHT,
    Palette,
    RADIUS_MD,
    SP_2,
    SP_3,
    SP_4,
    SP_6,
    SP_8,
)

_BASES = list(DATA_SOURCES.keys())
_MAX_PREVIEW_ROWS = 20
_STEP_LABELS = ["Selecionar", "Pré-visualizar", "Resultado"]


# ---------------------------------------------------------------------------
# Stepper indicator
# ---------------------------------------------------------------------------

class _StepperWidget(QWidget):
    """Horizontal stepper: 3 circles connected by lines, current step highlighted."""

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self._current = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._circles: list[QLabel] = []
        self._lines: list[QFrame] = []

        for i, step_label in enumerate(_STEP_LABELS):
            circle = QLabel(str(i + 1))
            circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            circle.setFixedSize(32, 32)
            self._circles.append(circle)

            col = QVBoxLayout()
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col.setSpacing(SP_2)
            col.addWidget(circle, alignment=Qt.AlignmentFlag.AlignHCenter)

            lbl = QLabel(step_label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {p.app_fg_muted}; font-size: {FS_SM}px; background: transparent; border: none;"
            )
            col.addWidget(lbl)

            layout.addLayout(col)

            if i < len(_STEP_LABELS) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFixedHeight(2)
                line.setFixedWidth(80)
                self._lines.append(line)
                layout.addWidget(line, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._refresh()

    def set_step(self, step: int) -> None:
        self._current = step
        self._refresh()

    def _refresh(self) -> None:
        p = self._p
        for i, circle in enumerate(self._circles):
            if i < self._current:
                bg, fg = p.app_success, p.app_accent_fg
                border = "none"
            elif i == self._current:
                bg, fg = p.app_accent, p.app_accent_fg
                border = "none"
            else:
                bg, fg = "transparent", p.app_fg_muted
                border = f"2px solid {p.app_border_strong}"
            circle.setStyleSheet(
                f"""
                QLabel {{
                    color: {fg};
                    font-size: {FS_SM2}px;
                    font-weight: {FW_BOLD};
                    background-color: {bg};
                    border: {border};
                    border-radius: 16px;
                }}
                """
            )
        for i, line in enumerate(self._lines):
            color = p.app_success if i < self._current - 1 else (
                p.app_accent if i < self._current else p.app_border
            )
            line.setStyleSheet(f"background-color: {color}; border: none;")


# ---------------------------------------------------------------------------
# Step 1: Select base + file
# ---------------------------------------------------------------------------

class _Step1Widget(QWidget):
    next_clicked: Signal = Signal()

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self._file_path: str = ""
        self._build_ui(p)

    @property
    def selected_base(self) -> str:
        return self._base_combo.currentText()

    @property
    def file_path(self) -> str:
        return self._file_path

    def _build_ui(self, p: Palette) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, SP_4, 0, SP_4)
        layout.setSpacing(SP_4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Base selection
        base_lbl = QLabel("Base de dados")
        base_lbl.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM}px; font-weight: {FW_MEDIUM}; background: transparent; border: none;"
        )
        layout.addWidget(base_lbl)

        self._base_combo = QComboBox()
        self._base_combo.setFixedHeight(36)
        for base in _BASES:
            self._base_combo.addItem(base)
        self._base_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: {p.app_bg};
                color: {p.app_fg};
                font-size: {FS_MD}px;
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
                padding: 0 {SP_3}px;
            }}
            QComboBox:focus {{ border-color: {p.app_accent}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            """
        )
        layout.addWidget(self._base_combo)
        layout.addSpacing(SP_2)

        # Template + file buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(SP_3)

        # BUG-V2-01: explicit text labels on plain QPushButton (no icon-only),
        # named "BtnSecondary" so the global QSS rule paints them legibly in
        # both themes — the inline QPushButton stylesheet was rendering text
        # the same colour as the background after theme toggles.
        self._template_btn = self._make_secondary_btn("Gerar template", p)
        self._template_btn.setObjectName("BtnSecondary")
        self._template_btn.clicked.connect(self._on_generate_template)
        btn_row.addWidget(self._template_btn)

        self._file_btn = self._make_secondary_btn("Escolher arquivo (.xlsx)", p)
        self._file_btn.setObjectName("BtnSecondary")
        self._file_btn.clicked.connect(self._on_choose_file)
        btn_row.addWidget(self._file_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._file_label = QLabel("Nenhum arquivo selecionado")
        self._file_label.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM}px; background: transparent; border: none;"
        )
        layout.addWidget(self._file_label)
        layout.addStretch()

        # Next button
        next_row = QHBoxLayout()
        next_row.addStretch()
        self._next_btn = self._make_primary_btn("Próximo →", p)
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self.next_clicked)
        next_row.addWidget(self._next_btn)
        layout.addLayout(next_row)

    def _on_generate_template(self) -> None:
        base = self.selected_base
        dest, _ = QFileDialog.getSaveFileName(
            self, "Salvar template", f"template_{base.lower()}.xlsx",
            "Excel (*.xlsx)"
        )
        if dest:
            try:
                from notion_bulk_edit.gerar_template import gerar_template
                gerar_template(base, dest)
            except Exception as exc:  # noqa: BLE001
                self._file_label.setText(f"Erro ao gerar template: {exc}")

    def _on_choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar planilha", "", "Excel (*.xlsx *.xls)"
        )
        if path:
            self._file_path = path
            self._file_label.setText(f"Arquivo: {Path(path).name}")
            self._next_btn.setEnabled(True)

    def _make_primary_btn(self, text: str, p: Palette) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {p.app_accent};
                color: {p.app_accent_fg};
                font-size: {FS_SM2}px; font-weight: {FW_BOLD};
                border: none; border-radius: {RADIUS_MD}px; padding: 0 {SP_4}px;
            }}
            QPushButton:hover {{ background-color: {p.app_accent_hover}; }}
            QPushButton:disabled {{ background-color: {p.app_border}; color: {p.app_fg_subtle}; }}
            """
        )
        return btn

    def _make_secondary_btn(self, text: str, p: Palette) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: transparent;
                color: {p.app_fg};
                font-size: {FS_SM2}px; font-weight: {FW_MEDIUM};
                border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px; padding: 0 {SP_3}px;
            }}
            QPushButton:hover {{ background-color: {p.app_row_hover}; }}
            """
        )
        return btn


# ---------------------------------------------------------------------------
# Step 2: Preview + validation
# ---------------------------------------------------------------------------

class _Step2Widget(QWidget):
    back_clicked: Signal = Signal()
    import_clicked: Signal = Signal()

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self._rows: list[dict[str, Any]] = []
        self._errors: list[str] = []
        # §5.3 row state tracking: index → "err" | "warn" | "ok"
        self._row_states: dict[int, str] = {}
        self._build_ui(p)

    def load_file(self, base: str, file_path: str) -> None:
        self._rows = []
        # BUG-05: store ALL rows separately from the preview slice
        self._all_rows: list[dict[str, Any]] = []
        self._errors = []
        self._row_states = {}
        try:
            import openpyxl  # type: ignore[import]
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                self._errors.append("Planilha vazia ou inválida.")
                self._update_table([], [])
                return
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                self._errors.append("Planilha sem dados.")
                self._update_table([], [])
                return
            headers = [str(c) if c is not None else "" for c in rows[0]]
            all_data_rows = rows[1:]
            preview_rows = all_data_rows[:_MAX_PREVIEW_ROWS]

            from notion_bulk_edit.validators import validar_linha
            all_row_dicts: list[dict[str, Any]] = []
            error_rows: list[int] = []

            for i, row in enumerate(all_data_rows):
                row_dict = {headers[j]: row[j] for j in range(len(headers)) if j < len(row)}
                all_row_dicts.append(row_dict)
                if i < _MAX_PREVIEW_ROWS:
                    try:
                        errs = validar_linha(base, row_dict)
                        for err in errs:
                            self._errors.append(f"Linha {i + 2}: [{err.campo}] {err.mensagem}")
                        if errs:
                            error_rows.append(i)
                            self._row_states[i] = "err"
                        else:
                            self._row_states[i] = "ok"
                    except Exception:  # noqa: BLE001
                        self._row_states[i] = "ok"

            # BUG-05: _rows = preview only; _all_rows = full dataset
            self._rows = all_row_dicts[:_MAX_PREVIEW_ROWS]
            self._all_rows = all_row_dicts
            self._update_table(headers, preview_rows, error_rows)
            wb.close()
        except ImportError:
            self._errors.append("Instale 'openpyxl' para importar planilhas Excel.")
            self._update_table([], [])
        except Exception as exc:  # noqa: BLE001
            self._errors.append(f"Erro ao ler arquivo: {exc}")
            self._update_table([], [])

        self._update_errors()

    def _update_table(
        self,
        headers: list[str],
        rows: list[Any],
        error_rows: list[int] | None = None,
    ) -> None:
        if error_rows is None:
            error_rows = []
        self._table.clear()
        self._table.setRowCount(len(rows))
        # §5.3 add "Validação" column at end
        col_count = len(headers) + 1
        self._table.setColumnCount(col_count)
        self._table.setHorizontalHeaderLabels([*headers, "Validação"])
        p = self._p

        # §5.3 row colors
        _BG: dict[str, str] = {
            "err":  p.app_danger_bg,
            "warn": p.app_warning_bg,
            "ok":   "transparent",
        }
        _CHIP: dict[str, tuple[str, str]] = {
            "err":  (p.app_danger,  "Erro"),
            "warn": (p.app_warning, "Conflito"),
            "ok":   (p.app_success, "✓ OK"),
        }

        for ri, row in enumerate(rows):
            state = self._row_states.get(ri, "ok")
            bg_color = _BG.get(state, "transparent")
            for ci, cell in enumerate(row):
                item = QTableWidgetItem(str(cell) if cell is not None else "")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if bg_color != "transparent":
                    item.setBackground(QColor(bg_color))
                self._table.setItem(ri, ci, item)

            # Validation chip in last column
            chip_color, chip_text = _CHIP.get(state, (p.app_fg_subtle, "—"))
            chip_item = QTableWidgetItem(chip_text)
            chip_item.setFlags(chip_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            chip_item.setForeground(QColor(chip_color))
            if bg_color != "transparent":
                chip_item.setBackground(QColor(bg_color))
            self._table.setItem(ri, len(headers), chip_item)

        self._table.resizeColumnsToContents()

    def _update_errors(self) -> None:
        n_err = sum(1 for s in self._row_states.values() if s == "err")
        n_ok = sum(1 for s in self._row_states.values() if s == "ok")
        n_total = len(self._row_states)

        # §5.2 summary banner
        if n_err > 0:
            banner_text = (
                f"{n_err} linha(s) com erro · {n_ok} prontas para importar"
                " — as linhas com erro serão puladas"
            )
            self._banner.setText(banner_text)
            self._banner.setVisible(True)
        elif n_total > 0:
            self._banner.setText(f"{n_ok} linhas prontas para importar")
            self._banner.setVisible(True)
        else:
            self._banner.setVisible(False)

        # Detailed error list (hidden when banner shows summary)
        if self._errors:
            text = "\n".join(self._errors[:10])
            self._error_lbl.setText(text)
            self._error_lbl.setVisible(True)
        else:
            self._error_lbl.setVisible(False)

    def _build_ui(self, p: Palette) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, SP_4, 0, SP_4)
        layout.setSpacing(SP_3)

        # §5.2 summary banner (hidden until load_file)
        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setVisible(False)
        self._banner.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_warning};
                font-size: {FS_SM2}px;
                font-weight: {FW_MEDIUM};
                background-color: {p.app_warning_bg};
                border-radius: {RADIUS_MD}px;
                padding: {SP_2}px {SP_3}px;
                border: none;
            }}
            """
        )
        layout.addWidget(self._banner)

        preview_lbl = QLabel(f"Pré-visualização (até {_MAX_PREVIEW_ROWS} linhas)")
        preview_lbl.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM}px; font-weight: {FW_MEDIUM}; background: transparent; border: none;"
        )
        layout.addWidget(preview_lbl)

        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {p.app_panel};
                alternate-background-color: {p.app_row_hover};
                color: {p.app_fg};
                font-size: {FS_MD}px;
                border: 1px solid {p.app_border};
                border-radius: {RADIUS_MD}px;
            }}
            """
        )
        layout.addWidget(self._table)

        self._error_lbl = QLabel()
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setVisible(False)
        self._error_lbl.setStyleSheet(
            f"""
            QLabel {{
                color: {p.app_danger};
                font-size: {FS_SM}px;
                background-color: {p.app_danger_bg};
                border-radius: {RADIUS_MD}px;
                padding: {SP_2}px {SP_3}px;
                border: none;
            }}
            """
        )
        layout.addWidget(self._error_lbl)

        nav_row = QHBoxLayout()
        back_btn = QPushButton("← Voltar")
        back_btn.setFixedHeight(36)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent; color: {p.app_fg};
                border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px; font-size: {FS_SM2}px;
            }}
            QPushButton:hover {{ background: {p.app_row_hover}; }}
            """
        )
        back_btn.clicked.connect(self.back_clicked)
        nav_row.addWidget(back_btn)
        nav_row.addStretch()

        self._import_btn = QPushButton("Importar →")
        self._import_btn.setFixedHeight(36)
        self._import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {p.app_accent}; color: {p.app_accent_fg};
                border: none; border-radius: {RADIUS_MD}px;
                padding: 0 {SP_4}px; font-size: {FS_SM2}px; font-weight: {FW_BOLD};
            }}
            QPushButton:hover {{ background-color: {p.app_accent_hover}; }}
            """
        )
        self._import_btn.clicked.connect(self.import_clicked)
        nav_row.addWidget(self._import_btn)
        layout.addLayout(nav_row)


# ---------------------------------------------------------------------------
# Step 3: Result
# ---------------------------------------------------------------------------

class _Step3Widget(QWidget):
    close_clicked: Signal = Signal()

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self._build_ui(p)

    def show_result(self, rows_imported: int, errors: int) -> None:
        if errors == 0:
            icon = "✓"
            title = "Importação concluída"
            color = self._p.app_success
        else:
            icon = "⚠"
            title = "Importação com erros"
            color = self._p.app_warning

        self._icon_lbl.setText(icon)
        self._icon_lbl.setStyleSheet(
            f"QLabel {{ color: {color}; font-size: 48px; background: transparent; border: none; }}"
        )
        self._title_lbl.setText(title)
        self._detail_lbl.setText(
            f"{rows_imported} registro(s) importado(s)"
            + (f", {errors} erro(s)" if errors else "")
        )

    def _build_ui(self, p: Palette) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, SP_6, 0, SP_4)
        layout.setSpacing(SP_4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self._icon_lbl = QLabel("✓")
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet(
            f"QLabel {{ color: {p.app_success}; font-size: 48px; background: transparent; border: none; }}"
        )
        layout.addWidget(self._icon_lbl)

        self._title_lbl = QLabel("Importação concluída")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont(FONT_DISPLAY)
        title_font.setPixelSize(20)
        title_font.setWeight(QFont.Weight(FW_BOLD))
        self._title_lbl.setFont(title_font)
        self._title_lbl.setStyleSheet(
            f"color: {p.app_fg_strong}; background: transparent; border: none;"
        )
        layout.addWidget(self._title_lbl)

        self._detail_lbl = QLabel("0 registros importados")
        self._detail_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_lbl.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_MD}px; background: transparent; border: none;"
        )
        layout.addWidget(self._detail_lbl)
        layout.addStretch()

        close_btn = QPushButton("Fechar")
        close_btn.setFixedHeight(36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {p.app_accent}; color: {p.app_accent_fg};
                border: none; border-radius: {RADIUS_MD}px;
                padding: 0 {SP_6}px; font-size: {FS_SM2}px; font-weight: {FW_BOLD};
            }}
            QPushButton:hover {{ background-color: {p.app_accent_hover}; }}
            """
        )
        close_btn.clicked.connect(self.close_clicked)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignHCenter)


# ---------------------------------------------------------------------------
# ImportarPage
# ---------------------------------------------------------------------------

class ImportarPage(QWidget):
    """3-step import wizard for Excel files into Notion bases."""

    import_done: Signal = Signal(str, int)  # base, rows_imported

    def __init__(
        self,
        conn: sqlite3.Connection,
        token: str,
        user: str,
        parent: QWidget | None = None,
    ) -> None:
        # Round 3a: kwarg dark removido — paleta única LIGHT.
        super().__init__(parent)
        self._conn = conn
        self._token = token
        self._user = user
        self._p: Palette = LIGHT
        self._current_step: int = 0

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    # Round 3a: apply_theme removido — paleta única LIGHT.

    def _build_ui(self) -> None:
        p = self._p
        # BUG-V2-03: pin the page background to the theme token so the page
        # cannot accidentally render dark when the rest of the app is light
        # (or vice-versa) regardless of which global QSS is active.
        self.setObjectName("ImportarPage")
        self.setStyleSheet(
            f"QWidget#ImportarPage {{ background-color: {p.app_bg}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(SP_8, SP_6, SP_8, SP_6)
        root.setSpacing(SP_6)

        # BUG-V2-12: use the semantic strong-text token so the heading flips
        # cream-on-navy in dark mode instead of staying low-contrast navy.
        # N5: kept as ``self._heading`` so apply_theme can recolour it.
        self._heading = QLabel("Importar Dados")
        heading_font = QFont(FONT_DISPLAY)
        heading_font.setPixelSize(22)
        heading_font.setWeight(QFont.Weight(FW_BOLD))
        self._heading.setFont(heading_font)
        self._heading.setStyleSheet(
            f"color: {p.app_fg_strong}; background: transparent; border: none;"
        )
        root.addWidget(self._heading)

        # Stepper
        self._stepper = _StepperWidget(p)
        root.addWidget(self._stepper)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {p.app_border}; border: none;")
        root.addWidget(div)

        # Steps container (stacked manually)
        self._step1 = _Step1Widget(p)
        self._step2 = _Step2Widget(p)
        self._step3 = _Step3Widget(p)

        for w in (self._step1, self._step2, self._step3):
            root.addWidget(w)

        # Connect step signals
        self._step1.next_clicked.connect(self._go_step2)
        self._step2.back_clicked.connect(self._go_step1)
        self._step2.import_clicked.connect(self._do_import)
        self._step3.close_clicked.connect(self._go_step1)

        self._show_step(0)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _show_step(self, step: int) -> None:
        self._current_step = step
        self._stepper.set_step(step)
        self._step1.setVisible(step == 0)
        self._step2.setVisible(step == 1)
        self._step3.setVisible(step == 2)

    def _go_step1(self) -> None:
        self._show_step(0)

    def _go_step2(self) -> None:
        base = self._step1.selected_base
        file_path = self._step1.file_path
        if not file_path:
            return
        self._step2.load_file(base, file_path)
        self._show_step(1)

    def _do_import(self) -> None:
        base = self._step1.selected_base
        # BUG-05: use _all_rows (full dataset) instead of preview-only _rows
        all_rows = getattr(self._step2, "_all_rows", self._step2._rows)
        errors = 0
        imported = 0

        try:
            from notion_bulk_edit.notion_api import NotionClient
            from notion_bulk_edit.schemas import SCHEMAS
            from notion_bulk_edit.encoders import encode_value
            from notion_bulk_edit.config import DATA_SOURCES

            client = NotionClient(self._token)
            schema = SCHEMAS.get(base, {})
            db_id = DATA_SOURCES.get(base, "")

            for row_dict in all_rows:
                try:
                    # Build Notion properties payload from this row
                    properties: dict = {}
                    for prop_key, spec in schema.items():
                        if not spec.editavel:
                            continue
                        # BUG-N1: explicit None checks preserve falsy values (False, 0)
                        v = row_dict.get(spec.notion_name)
                        if v is None:
                            v = row_dict.get(spec.label)
                        if v is None:
                            v = row_dict.get(prop_key)
                        value = v
                        if value is None:
                            continue
                        try:
                            encoded = encode_value(value, spec.tipo)
                            if encoded is not None:
                                properties[spec.notion_name] = encoded
                        except Exception:  # noqa: BLE001
                            pass

                    if properties and db_id:
                        # BUG-N1: update existing page if page_id present, else create
                        row_page_id = row_dict.get("page_id")
                        if row_page_id:
                            client.update_page(row_page_id, properties)
                        else:
                            client.create_page(db_id, properties)
                        imported += 1
                    elif not db_id:
                        errors += 1
                except Exception:  # noqa: BLE001
                    errors += 1
        except Exception:  # noqa: BLE001
            errors = len(all_rows)

        self._step3.show_result(imported, errors)
        self._show_step(2)
        self.import_done.emit(base, imported)
