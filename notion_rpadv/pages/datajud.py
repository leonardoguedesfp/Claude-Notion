"""Página DataJUD CNJ (Componente 6).

UI espelha estrutura de ``pages/leitor_dje.py`` (header + alternância
de modo via QStackedWidget interno) e o wizard 3 passos do
``pages/importar.py`` para o Modo B.

Modo A — Varredura completa:
    Lê todos os processos de ``cache_db.records['Processos']``,
    estima tempo, abre QFileDialog para destino e dispara um
    ``DataJudWorker`` em QThread.

Modo B — Lista manual:
    Wizard 3 passos:
      1. textarea (cole CNJs separados) + botão "Anexar planilha xlsx".
         Validação via ``parse_string_cnjs`` ou ``parse_xlsx_cnjs``.
      2. preview com chip verde/vermelho por linha.
      3. progress + resultado idêntico ao Modo A.

Pra integração com a aba Importar existente, esta página NÃO escreve
no Notion — gera planilha xlsx que o operador revisa e importa
manualmente.
"""
from __future__ import annotations

import datetime as _dt
import logging
import sqlite3
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QSettings,
    QThread,
    QUrl,
    Qt,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from notion_rpadv.cache import db as cache_db
from notion_rpadv.services.datajud_client import DataJudClient
from notion_rpadv.services.datajud_input_parser import (
    CnjValidado,
    parse_string_cnjs,
    parse_xlsx_cnjs,
)
from notion_rpadv.services.datajud_worker import DataJudWorker
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
    SP_3,
    SP_4,
    SP_6,
    SP_8,
)

logger = logging.getLogger("datajud.page")


_SETTINGS_ORG: str = "RPADV"
_SETTINGS_APP: str = "NotionApp"
_KEY_OUTPUT_DIR: str = "datajud/output_dir"

# Estimativa: ~2s por CNJ no client + paralelismo ~4. Tempo efetivo
# por CNJ varia entre ~0.5s (otimista — cache aquecido, sem retry) e
# ~2s (pessimista — retry em 429/503).
_TEMPO_OTIMISTA_S: float = 0.5
_TEMPO_PESSIMISTA_S: float = 2.0

_BASE_PROCESSOS: str = "Processos"


def _estimar_tempo_minutos(n: int) -> tuple[int, int]:
    """Devolve faixa (otimista, pessimista) em minutos para ``n`` CNJs."""
    if n <= 0:
        return (0, 0)
    return (
        max(1, int(n * _TEMPO_OTIMISTA_S / 60)),
        max(1, int(n * _TEMPO_PESSIMISTA_S / 60)),
    )


def _output_default_filename() -> str:
    ts = _dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    return f"datajud_consulta_{ts}.xlsx"


# ---------------------------------------------------------------------------
# Modo A — Varredura completa
# ---------------------------------------------------------------------------


class _ModoAWidget(QWidget):
    iniciar_clicked: Signal = Signal(str)  # output_path
    cancelar_clicked: Signal = Signal()

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self._build_ui()

    def _build_ui(self) -> None:
        p = self._p
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, SP_4, 0, SP_4)
        layout.setSpacing(SP_4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._info_label = QLabel(
            "Vai consultar a API DataJud do CNJ para os processos "
            "cadastrados na base ⚖️ Processos.",
        )
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet(
            f"color: {p.app_fg}; font-size: {FS_MD}px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._info_label)

        self._estim_label = QLabel("")
        self._estim_label.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM}px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._estim_label)

        # Botões
        btn_row = QHBoxLayout()
        self._iniciar_btn = QPushButton("Selecionar destino e iniciar")
        self._iniciar_btn.setFixedHeight(36)
        self._iniciar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._iniciar_btn.setStyleSheet(
            f"QPushButton {{ background-color: {p.app_accent}; color: {p.app_accent_fg}; "
            f"font-size: {FS_SM2}px; font-weight: {FW_BOLD}; border: none; "
            f"border-radius: {RADIUS_MD}px; padding: 0 {SP_4}px; }}"
            f"QPushButton:hover {{ background-color: {p.app_accent_hover}; }}"
            f"QPushButton:disabled {{ background-color: {p.app_border}; color: {p.app_fg_subtle}; }}"
        )
        self._iniciar_btn.clicked.connect(self._on_iniciar)
        btn_row.addWidget(self._iniciar_btn)

        self._cancelar_btn = QPushButton("Cancelar")
        self._cancelar_btn.setFixedHeight(36)
        self._cancelar_btn.setVisible(False)
        self._cancelar_btn.clicked.connect(self.cancelar_clicked)
        btn_row.addWidget(self._cancelar_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMinimum(0)
        layout.addWidget(self._progress)

        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)

        layout.addStretch()

    def set_total_processos(self, n: int) -> None:
        if n == 0:
            self._info_label.setText(
                "Nenhum processo encontrado em ⚖️ Processos. "
                "Sincronize o cache antes de continuar.",
            )
            self._iniciar_btn.setEnabled(False)
            return
        otim, pess = _estimar_tempo_minutos(n)
        self._info_label.setText(
            f"Vai consultar a API DataJud do CNJ para {n} processos "
            f"da base ⚖️ Processos.",
        )
        self._estim_label.setText(f"Tempo estimado: ~{otim}–{pess} min.")
        self._iniciar_btn.setEnabled(True)

    def set_progresso(self, count: int, total: int, cnj: str) -> None:
        self._progress.setMaximum(max(total, 1))
        self._progress.setValue(count)
        self._progress_label.setText(
            f"Consultando processo {count} de {total} — CNJ {cnj}",
        )

    def set_em_execucao(self, em_exec: bool) -> None:
        self._iniciar_btn.setVisible(not em_exec)
        self._cancelar_btn.setVisible(em_exec)
        self._progress.setVisible(em_exec)
        self._progress_label.setVisible(em_exec)

    def _on_iniciar(self) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        sticky = str(s.value(_KEY_OUTPUT_DIR, ""))
        default_path = (
            str(Path(sticky) / _output_default_filename())
            if sticky else _output_default_filename()
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar planilha DataJUD", default_path, "Excel (*.xlsx)",
        )
        if path:
            s.setValue(_KEY_OUTPUT_DIR, str(Path(path).parent))
            self.iniciar_clicked.emit(path)


# ---------------------------------------------------------------------------
# Modo B — Wizard 3 passos
# ---------------------------------------------------------------------------


class _ModoBStep1(QWidget):
    avancar_clicked: Signal = Signal(list)  # list[CnjValidado]

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self._cnjs: list[CnjValidado] = []
        self._build_ui()

    def _build_ui(self) -> None:
        p = self._p
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, SP_4, 0, SP_4)
        layout.setSpacing(SP_4)

        layout.addWidget(QLabel(
            "Cole CNJs (um por linha, ou separados por ;) "
            "ou anexe uma planilha:",
        ))

        self._textarea = QTextEdit()
        self._textarea.setPlaceholderText(
            "0000123-45.2024.5.10.0001\n0000234-56.2024.5.10.0002",
        )
        self._textarea.setMinimumHeight(140)
        self._textarea.textChanged.connect(self._on_input_changed)
        layout.addWidget(self._textarea)

        btn_row = QHBoxLayout()
        self._anexar_btn = QPushButton("Anexar planilha xlsx")
        self._anexar_btn.clicked.connect(self._on_anexar)
        btn_row.addWidget(self._anexar_btn)
        btn_row.addStretch()
        self._avancar_btn = QPushButton("Avançar →")
        self._avancar_btn.setEnabled(False)
        self._avancar_btn.clicked.connect(self._on_avancar)
        btn_row.addWidget(self._avancar_btn)
        layout.addLayout(btn_row)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM}px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._status_label)
        layout.addStretch()

    def _on_input_changed(self) -> None:
        texto = self._textarea.toPlainText()
        self._cnjs = parse_string_cnjs(texto)
        self._atualizar_status()

    def _on_anexar(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Selecionar planilha", "", "Excel (*.xlsx)",
        )
        if not path_str:
            return
        try:
            cnjs = parse_xlsx_cnjs(Path(path_str))
        except Exception as exc:  # noqa: BLE001
            self._status_label.setText(f"Erro ao ler arquivo: {exc}")
            return
        self._cnjs = cnjs
        # Espelha conteúdo no textarea pra usuário ver
        self._textarea.blockSignals(True)
        self._textarea.setPlainText(
            "\n".join(c.cnj_normalizado or c.cnj_20_digitos for c in cnjs)
        )
        self._textarea.blockSignals(False)
        self._atualizar_status()

    def _atualizar_status(self) -> None:
        validos = sum(1 for c in self._cnjs if c.valido)
        invalidos = len(self._cnjs) - validos
        if validos > 0:
            self._status_label.setText(
                f"{validos} válido(s), {invalidos} inválido(s).",
            )
            self._avancar_btn.setEnabled(True)
        elif self._cnjs:
            self._status_label.setText(
                f"Nenhum CNJ válido (todos os {invalidos} são inválidos).",
            )
            self._avancar_btn.setEnabled(False)
        else:
            self._status_label.setText("")
            self._avancar_btn.setEnabled(False)

    def _on_avancar(self) -> None:
        self.avancar_clicked.emit(self._cnjs)


class _ModoBStep2(QWidget):
    voltar_clicked: Signal = Signal()
    confirmar_clicked: Signal = Signal(str)  # output_path

    def __init__(self, p: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._p = p
        self._cnjs_validos: list[CnjValidado] = []
        self._build_ui()

    def _build_ui(self) -> None:
        p = self._p
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, SP_4, 0, SP_4)
        layout.setSpacing(SP_4)

        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setStyleSheet(
            f"color: {p.app_fg}; font-size: {FS_MD}px; font-weight: {FW_MEDIUM}; "
            f"background-color: {p.app_warning_bg}; border-radius: {RADIUS_MD}px; "
            f"padding: {SP_3}px; border: none;"
        )
        layout.addWidget(self._banner)

        self._lista = QListWidget()
        layout.addWidget(self._lista)

        nav_row = QHBoxLayout()
        voltar_btn = QPushButton("← Voltar")
        voltar_btn.clicked.connect(self.voltar_clicked)
        nav_row.addWidget(voltar_btn)
        nav_row.addStretch()
        self._confirmar_btn = QPushButton("Confirmar e iniciar →")
        self._confirmar_btn.clicked.connect(self._on_confirmar)
        nav_row.addWidget(self._confirmar_btn)
        layout.addLayout(nav_row)

    def carregar(self, cnjs: list[CnjValidado]) -> None:
        self._lista.clear()
        validos = []
        invalidos = 0
        for c in cnjs:
            if c.valido:
                validos.append(c)
                texto = f"✓ {c.cnj_normalizado}"
            else:
                invalidos += 1
                texto = (
                    f"✗ {c.cnj_20_digitos or '(sem dígitos)'} "
                    f"— {c.erro}"
                )
            item = QListWidgetItem(texto)
            self._lista.addItem(item)
        self._cnjs_validos = validos
        self._banner.setText(
            f"{len(validos)} válido(s), {invalidos} inválido(s). "
            "Apenas válidos serão consultados.",
        )
        self._confirmar_btn.setEnabled(len(validos) > 0)

    def cnjs_validos(self) -> list[CnjValidado]:
        return list(self._cnjs_validos)

    def _on_confirmar(self) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        sticky = str(s.value(_KEY_OUTPUT_DIR, ""))
        default_path = (
            str(Path(sticky) / _output_default_filename())
            if sticky else _output_default_filename()
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar planilha DataJUD", default_path, "Excel (*.xlsx)",
        )
        if path:
            s.setValue(_KEY_OUTPUT_DIR, str(Path(path).parent))
            self.confirmar_clicked.emit(path)


# ---------------------------------------------------------------------------
# DataJUDPage
# ---------------------------------------------------------------------------


class DataJUDPage(QWidget):
    """Aba 'DataJUD CNJ' do app — gera planilha xlsx de revisão humana
    a partir de consultas à API pública DataJud do CNJ.

    Args:
        conn: ``sqlite3.Connection`` para o cache (``cache_db.records``).
        token: token Notion (não usado diretamente nesta página, mas
            é parte do contrato comum das pages).
        schema_registry: registry singleton (opcional). Quando None,
            a página tenta carregar via ``notion_bulk_edit.schemas.SCHEMAS``.

    Signals:
        toast_requested(message, kind): repassado ao MainWindow.
    """

    toast_requested: Signal = Signal(str, str)

    def __init__(
        self,
        conn: sqlite3.Connection,
        token: str,
        schema_registry: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._token = token
        self._schema_registry = schema_registry
        self._p: Palette = LIGHT

        self._worker: DataJudWorker | None = None
        self._thread: QThread | None = None
        self._last_output_path: str = ""

        self._build_ui()
        self._refresh_modo_a_estimativa()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        p = self._p
        self.setObjectName("DataJUDPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#DataJUDPage {{ background-color: {p.app_bg}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(SP_8, SP_6, SP_8, SP_6)
        root.setSpacing(SP_4)

        # Header — título + link de alternância
        header_row = QHBoxLayout()
        title = QLabel("DataJUD CNJ")
        title_font = QFont(FONT_DISPLAY)
        title_font.setPixelSize(22)
        title_font.setWeight(QFont.Weight(FW_BOLD))
        title.setFont(title_font)
        title.setStyleSheet(
            f"color: {p.app_fg_strong}; background: transparent; border: none;"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        self._link_modo = QPushButton("Modo lista manual →")
        self._link_modo.setObjectName("LinkModo")
        self._link_modo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._link_modo.setFlat(True)
        self._link_modo.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {p.app_accent}; "
            f"font-size: {FS_SM2}px; border: none; }}"
        )
        self._link_modo.clicked.connect(self._toggle_modo)
        header_row.addWidget(self._link_modo)
        root.addLayout(header_row)

        # Divisor
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {p.app_border}; border: none;")
        root.addWidget(div)

        # Stack: Modo A vs Modo B (3 steps internos)
        self._stack_modos = QStackedWidget()
        root.addWidget(self._stack_modos)

        # Modo A
        self._modo_a = _ModoAWidget(p)
        self._modo_a.iniciar_clicked.connect(self._on_modo_a_iniciar)
        self._modo_a.cancelar_clicked.connect(self._cancelar_worker)
        self._stack_modos.addWidget(self._modo_a)

        # Modo B (container com 3 steps internos)
        self._modo_b_container = QStackedWidget()
        self._step1 = _ModoBStep1(p)
        self._step1.avancar_clicked.connect(self._on_step1_avancar)
        self._step2 = _ModoBStep2(p)
        self._step2.voltar_clicked.connect(self._on_step2_voltar)
        self._step2.confirmar_clicked.connect(self._on_step2_confirmar)
        self._step3 = _ModoAWidget(p)  # mesmo widget de progress
        self._step3.cancelar_clicked.connect(self._cancelar_worker)
        self._modo_b_container.addWidget(self._step1)
        self._modo_b_container.addWidget(self._step2)
        self._modo_b_container.addWidget(self._step3)
        self._stack_modos.addWidget(self._modo_b_container)

        # Estado inicial: Modo A
        self._stack_modos.setCurrentIndex(0)

    def _toggle_modo(self) -> None:
        atual = self._stack_modos.currentIndex()
        if atual == 0:
            self._stack_modos.setCurrentIndex(1)
            self._modo_b_container.setCurrentIndex(0)  # step 1
            self._link_modo.setText("Modo varredura →")
        else:
            self._stack_modos.setCurrentIndex(0)
            self._link_modo.setText("Modo lista manual →")

    # ------------------------------------------------------------------
    # Modo A — Varredura completa
    # ------------------------------------------------------------------

    def _refresh_modo_a_estimativa(self) -> None:
        try:
            n = len(self._carregar_processos_cache())
        except Exception:  # noqa: BLE001
            n = 0
        self._modo_a.set_total_processos(n)

    def _carregar_processos_cache(self) -> list[dict[str, Any]]:
        return cache_db.get_all_records(self._conn, _BASE_PROCESSOS)

    def _on_modo_a_iniciar(self, output_path: str) -> None:
        processos = self._carregar_processos_cache()
        if not processos:
            self.toast_requested.emit("Cache de Processos vazio.", "warning")
            return
        self._iniciar_worker(processos, Path(output_path), modo_b=False)

    # ------------------------------------------------------------------
    # Modo B — Wizard
    # ------------------------------------------------------------------

    def _on_step1_avancar(self, cnjs: list[CnjValidado]) -> None:
        self._step2.carregar(cnjs)
        self._modo_b_container.setCurrentIndex(1)

    def _on_step2_voltar(self) -> None:
        self._modo_b_container.setCurrentIndex(0)

    def _on_step2_confirmar(self, output_path: str) -> None:
        cnjs_validos = self._step2.cnjs_validos()
        if not cnjs_validos:
            self.toast_requested.emit("Nenhum CNJ válido.", "warning")
            return
        # Cruza com cache: filtra processos cuja chave numero_do_processo
        # esteja entre os CNJs válidos. Se algum CNJ não está no cache,
        # cria um stub com page_id="" e numero_do_processo (worker vai
        # consultar mesmo assim — DataJud aceita CNJ não-cadastrado).
        cache_records = self._carregar_processos_cache()
        index_por_cnj: dict[str, dict[str, Any]] = {}
        for r in cache_records:
            cnj_cache = str(r.get("numero_do_processo") or "").strip()
            if cnj_cache:
                index_por_cnj[cnj_cache] = r

        processos_alvo: list[dict[str, Any]] = []
        for c in cnjs_validos:
            rec = index_por_cnj.get(c.cnj_normalizado)
            if rec is not None:
                processos_alvo.append(rec)
            else:
                # CNJ não cadastrado no Notion — stub com 1º grau default.
                processos_alvo.append({
                    "page_id":            "",
                    "numero_do_processo": c.cnj_normalizado,
                    "tribunal":           "",
                    "instancia":          "",
                })

        self._modo_b_container.setCurrentIndex(2)  # step 3 (progress)
        self._step3.set_total_processos(len(processos_alvo))
        self._iniciar_worker(processos_alvo, Path(output_path), modo_b=True)

    # ------------------------------------------------------------------
    # Worker / QThread
    # ------------------------------------------------------------------

    def _iniciar_worker(
        self,
        processos: list[dict[str, Any]],
        output_path: Path,
        *,
        modo_b: bool,
    ) -> None:
        schema = self._resolver_schema()
        if not schema:
            self.toast_requested.emit(
                "Schema da base Processos não disponível. Sincronize antes.",
                "error",
            )
            return

        # Factory: cada thread do pool cria seu próprio client (1
        # session HTTP por thread, throttle independente). Sem isso,
        # 4 workers compartilhariam o mesmo client e serializariam.
        def _client_factory() -> DataJudClient:
            return DataJudClient()

        self._worker = DataJudWorker(
            processos=processos,
            client_factory=_client_factory,
            schema=schema,
            output_path=output_path,
        )
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.total.connect(self._on_total)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.cancelled.connect(
            lambda: self.toast_requested.emit("Consulta cancelada.", "info"),
        )
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._modo_b = modo_b
        widget_progress = self._step3 if modo_b else self._modo_a
        widget_progress.set_em_execucao(True)
        self._thread.start()

    def _on_total(self, n: int) -> None:
        widget = self._step3 if self._modo_b else self._modo_a
        widget.set_progresso(0, n, "")

    def _on_progress(self, count: int, cnj: str) -> None:
        widget = self._step3 if self._modo_b else self._modo_a
        # Total já está no progress bar; só atualiza valor + label
        widget.set_progresso(count, widget._progress.maximum(), cnj)

    def _on_finished(
        self, output_path: str, ok: int, parciais: int,
        erros: int, nao_encontrados: int,
    ) -> None:
        widget = self._step3 if self._modo_b else self._modo_a
        widget.set_em_execucao(False)
        self._last_output_path = output_path
        msg = (
            f"Consulta concluída: {ok} OK, {parciais} parciais, "
            f"{erros} erros, {nao_encontrados} não encontrados. "
            f"Arquivo: {Path(output_path).name}"
        )
        kind = "warning" if erros > 0 else "success"
        self.toast_requested.emit(msg, kind)

    def _on_error(self, message: str) -> None:
        widget = self._step3 if self._modo_b else self._modo_a
        widget.set_em_execucao(False)
        self.toast_requested.emit(f"Erro: {message}", "error")

    def _cancelar_worker(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolver_schema(self) -> dict[str, Any]:
        """Resolve schema da base Processos.

        Preferência: SCHEMAS dinâmico (vivo). Fallback: schema_registry
        injetado no construtor (caso o caller queira controlar).
        """
        try:
            from notion_bulk_edit.schemas import SCHEMAS
            schema = SCHEMAS.get(_BASE_PROCESSOS)
            if schema:
                return dict(schema)
        except Exception:  # noqa: BLE001
            pass
        if self._schema_registry is not None:
            try:
                schema = self._schema_registry.get_schema(_BASE_PROCESSOS)
                if schema:
                    return dict(schema)
            except Exception:  # noqa: BLE001
                pass
        return {}

    # Métodos pra abrir arquivo / pasta após conclusão (chamados via
    # botões pós-finalizacao se a UI quiser). API exposta pra MainWindow
    # ou pra futuras evoluções.

    def abrir_ultimo_arquivo(self) -> None:
        if self._last_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_output_path))

    def abrir_pasta_saida(self) -> None:
        if self._last_output_path:
            pasta = str(Path(self._last_output_path).parent)
            QDesktopServices.openUrl(QUrl.fromLocalFile(pasta))
