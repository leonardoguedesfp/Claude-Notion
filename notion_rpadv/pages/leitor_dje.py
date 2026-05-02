"""Página "Leitor DJE" (refator pós-Fase 3 hotfix watermark integrity,
2026-05-02).

**Modo padrão** (default da aba) — uso diário do escritório:
- Para cada advogado oficial, lê seu cursor individual em
  ``djen_advogado_state`` e calcula janela ``[cursor + 1d, hoje]``.
  Cursor vazio → ``DEFAULT_CURSOR_VAZIO`` (= 31/12/2025), fazendo a
  janela natural ser ``[01/01/2026, hoje]``. Sem modal de "primeira
  execução" — cursor vazio é só estado normal.
- 2 datepickers + botão "Baixar período selecionado" pra carga inicial
  controlada ou recuperação de gaps em janela arbitrária. Esse botão
  roda em ``MODE_MANUAL`` internamente (não toca cursor).
- Migração legada: se ``dje_db.is_legacy_state_present(conn)``, modal
  de aviso pergunta ao usuário antes de apagar publicações + cursor
  antigo (``clear_legacy_state_and_publicacoes``).

**Modo personalizado (manual)** — pesquisa de OABs externas:
- 2 datepickers + lista dinâmica de OABs externas (nome + OAB + UF).
- **Sem checkboxes do escritório** (refator): o uso diário do
  escritório vai pelo botão "Baixar publicações novas".
- Botão habilitado se: di ≤ df AND ≥1 OAB externa preenchida (3 campos).
- NUNCA atualiza ``djen_advogado_state``.

**Comum aos modos:**
- Pipeline ``dje_transform`` aplicado: dedup por id, split em
  ``advogados_consultados_escritorio`` + ``oabs_externas_consultadas``.
- ``dje_db.insert_publicacao`` (``ON CONFLICT(djen_id) DO NOTHING``).
- Cursor avança POR ADVOGADO até a última sub-janela contígua completa
  após retry diferido (modo padrão apenas).
- **Excel-de-execução SEMPRE gerado** (mesmo com 0 novas — pra
  evidência), com abas auxiliares "Status" (cursor/dias atrás por
  advogado oficial) e "Log" (mensagens da execução).
- ``Historico_DJEN_completo.xlsx`` regenerado se banco não-vazio,
  com as mesmas abas auxiliares.
- Cancelamento via botão Cancelar (Fase 2.2 mantida).

Settings persistidos via QSettings:
- ``leitor_dje/output_dir``: diretório escolhido pelo usuário (sticky)
- ``leitor_dje/last_inicio_manual``: data inicial sticky do modo manual
"""
from __future__ import annotations

import datetime as _dt
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
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
from PySide6.QtGui import QDesktopServices, QFont, QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from notion_rpadv.services import dje_db, dje_state
from notion_rpadv.services.dje_advogados import (
    ADVOGADOS,
    Advogado,
    format_advogado_label,
)
from notion_rpadv.services.dje_client import (
    AdvogadoConsulta,
    AdvogadoResult,
    DJEClient,
)
from notion_rpadv.services.dje_exporter import (
    HISTORICO_FILENAME,
    write_historico_completo_xlsx,
    write_publicacoes_xlsx_from_processed,
)
from notion_rpadv.services.dje_transform import (
    dedup_by_id,
    split_advogados_columns,
)
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


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------


_SETTINGS_ORG: str = "RPADV"
_SETTINGS_APP: str = "NotionApp"
_KEY_OUTPUT_DIR: str = "leitor_dje/output_dir"
_KEY_LAST_INICIO_MANUAL: str = "leitor_dje/last_inicio_manual"

# Default conforme spec do operador (Leonardo). Em outros PCs o caminho
# pode não existir; o app tenta criar no momento do export, e se falhar
# abre QFileDialog pra usuário escolher.
DEFAULT_OUTPUT_DIR: str = (
    r"C:\Users\LeonardoGuedesdaFons\RICARDO PASSOS ADVOCACIA"
    r"\RICARDO PASSOS - CLIENTES-N\Reclamações Trabalhistas"
    r"\Ferramentas\Leitor DJE"
)

SKIPPED_LOG_CAP: int = 10  # Fase 2.1: cap de linhas puladas logadas

# 27 siglas do Brasil — combo box do modo manual pra OABs externas.
UFS_BRASIL: tuple[str, ...] = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
)

MODE_PADRAO: str = "padrao"
MODE_MANUAL: str = "manual"


# ---------------------------------------------------------------------------
# Worker (thread separada)
# ---------------------------------------------------------------------------


@dataclass
class WorkerOutcome:
    """Resultado consolidado do worker pra alimentar o banner da UI.

    Refator pós-Fase 3 hotfix (2026-05-02): cursor único →
    ``state_map`` por advogado, refletindo o modelo de cursor
    individual. UI usa pra mostrar status linha-a-linha.

    ``excel_path``: Excel-de-execução versionado. **Sempre populado**
    no refator atual — Excel é gerado mesmo com 0 publicações novas
    (cabeçalho + abas Status/Log) pra garantir evidência da execução.

    ``historico_path``: ``Historico_DJEN_completo.xlsx``. ``None`` se
    bloqueado ou se banco está vazio após a execução.

    ``historico_locked``: ``True`` se o arquivo destino estava bloqueado.

    ``errors``: advogados com falha persistente (mesmo critério F2.2).

    ``count_antes``: ``COUNT(*) FROM publicacoes`` ANTES de qualquer
    insert desta execução. "Y já existiam no banco" do banner.

    ``novas_inseridas``: linhas que entraram nesta execução
    (``rowcount > 0`` do ``INSERT OR IGNORE``, com sanity check).
    "X novas" do banner.

    ``skipped_count``: linhas puladas pelo exporter (defesa F2.1).

    ``cancelled``: ``True`` se cancelamento pelo usuário.

    ``state_map_apos``: snapshot de ``djen_advogado_state`` APÓS a
    execução (modo padrão atualiza cursores, modo manual mantém).
    Dict ``(oab, uf) → {ultimo_cursor, last_run}``. UI usa pra montar
    banner com status por advogado.

    ``mode``: ``'padrao'`` ou ``'manual'``.
    """

    excel_path: Path | None
    historico_path: Path | None
    historico_locked: bool
    errors: list[Advogado] = field(default_factory=list)
    count_antes: int = 0
    novas_inseridas: int = 0
    skipped_count: int = 0
    cancelled: bool = False
    state_map_apos: dict = field(default_factory=dict)
    mode: str = MODE_PADRAO


class _DJEWorker(QObject):
    """Worker que roda fetch_all + SQLite + xlsx em thread separada.

    Emite ``log`` (string) e ``progress`` (idx, total) durante o
    fetch_all. Em sucesso, emite ``finished(WorkerOutcome)``. Em erro
    fatal não-recuperável, emite ``error(str)``.
    """

    log: Signal = Signal(str)
    progress: Signal = Signal(int, int)
    finished: Signal = Signal(object)  # WorkerOutcome
    error: Signal = Signal(str)

    def __init__(
        self,
        *,
        consultas: list[AdvogadoConsulta],
        output_dir: Path,
        mode: str,
        oabs_escritorio_marcadas: set[str],
        oabs_externas_pesquisadas: set[str],
        dje_conn: sqlite3.Connection,
    ) -> None:
        super().__init__()
        self._consultas = consultas
        self._output_dir = output_dir
        self._mode = mode
        self._oabs_marcadas = oabs_escritorio_marcadas
        self._oabs_externas = oabs_externas_pesquisadas
        self._dje_conn = dje_conn
        self._client: DJEClient | None = None
        self._cancel_event = threading.Event()
        # Refator: log persistido pra aba "Log" do Excel.
        self._log_lines: list[str] = []
        # Faixa de datas pro nome do arquivo: MIN(di), MAX(df) entre
        # as consultas. Usado em ``write_publicacoes_xlsx_from_processed``.
        if consultas:
            self._range_di = min(c.data_inicio for c in consultas)
            self._range_df = max(c.data_fim for c in consultas)
        else:
            today = _dt.date.today()
            self._range_di = today
            self._range_df = today

    def _emit_log(self, line: str) -> None:
        """Emite log pra UI E persiste pra aba "Log" do Excel."""
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        stamped = f"[{ts}] {line}"
        self._log_lines.append(stamped)
        self.log.emit(line)

    def request_cancel(self) -> None:
        """Sinaliza o worker pra parar entre o próximo checkpoint do
        client (Fase 2.2)."""
        self._cancel_event.set()

    def run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:  # noqa: BLE001
            logger.exception("DJE: erro fatal no worker")
            self.error.emit(f"{type(exc).__name__}: {exc}")

    def _run_inner(self) -> None:
        self._client = DJEClient()
        spans = ", ".join(
            f"{c.advogado['oab']}/{c.advogado['uf']}: "
            f"{c.data_inicio.strftime('%d/%m')}–{c.data_fim.strftime('%d/%m')}"
            for c in self._consultas
        )
        self._emit_log(
            f"Iniciando varredura — modo {self._mode}, "
            f"{len(self._consultas)} advogado(s).",
        )
        self._emit_log(f"Janelas: {spans}")

        summary = self._client.fetch_all(
            self._consultas,
            on_progress=self._emit_progress,
            is_cancelled=self._cancel_event.is_set,
            on_log_event=self._emit_log,
        )

        if summary.cancelled:
            self._emit_log(
                "⚠ Varredura cancelada — publicações captadas até o "
                "ponto do cancel serão processadas mesmo assim.",
            )
        else:
            self._emit_log("Varredura concluída.")

        # Pipeline dedup + split (comum aos 2 modos — necessário pro Excel).
        deduped = dedup_by_id(summary.rows)
        splitted = split_advogados_columns(
            deduped,
            oabs_escritorio_marcadas=self._oabs_marcadas,
            oabs_externas_pesquisadas=self._oabs_externas,
        )

        if self._mode == MODE_PADRAO:
            outcome = self._finalize_padrao(summary, splitted)
        else:
            outcome = self._finalize_manual(summary, splitted)
        self.finished.emit(outcome)

    def _finalize_padrao(self, summary, splitted) -> "WorkerOutcome":
        """Modo padrão (uso diário do escritório): persiste no SQLite,
        atualiza cursor por advogado, gera Excel-de-execução com novas
        + histórico completo."""
        # Snapshot do banco ANTES de qualquer inserção.
        count_antes = dje_db.count_publicacoes(self._dje_conn)

        novas_rows: list[dict] = []
        for row in splitted:
            djen_id = row.get("id")
            if djen_id is None:
                continue
            payload = {k: v for k, v in row.items() if k not in (
                "advogados_consultados_escritorio",
                "oabs_externas_consultadas",
            )}
            inserted = dje_db.insert_publicacao(
                self._dje_conn,
                djen_id=int(djen_id),
                hash_=str(row.get("hash") or ""),
                oabs_escritorio=row.get(
                    "advogados_consultados_escritorio", "",
                ),
                oabs_externas=row.get("oabs_externas_consultadas", ""),
                numero_processo=row.get("numero_processo"),
                data_disponibilizacao=str(row.get("data_disponibilizacao") or ""),
                sigla_tribunal=row.get("siglaTribunal"),
                payload=payload,
                mode=MODE_PADRAO,
            )
            if inserted:
                novas_rows.append(row)
        self._dje_conn.commit()

        # Sanity check de contadores.
        count_apos = dje_db.count_publicacoes(self._dje_conn)
        novas_inseridas = len(novas_rows)
        novas_real = count_apos - count_antes
        if novas_real != novas_inseridas:
            logger.warning(
                "DJE: divergência em contadores — rowcount=%d, "
                "COUNT(*)_pre=%d, COUNT(*)_pos=%d, real=%d. Usando real.",
                novas_inseridas, count_antes, count_apos, novas_real,
            )
            novas_inseridas = novas_real

        self._emit_log(
            f"SQLite: {novas_inseridas} novas inseridas "
            f"({count_antes} já existiam).",
        )

        # Atualização do cursor POR ADVOGADO. Cada advogado avança até
        # seu próprio data_max_safe (granularidade sub-janela mensal).
        if not summary.cancelled:
            for adv_result in summary.by_advogado:
                if adv_result.data_max_safe is None:
                    continue
                ok = dje_state.update_advogado_cursor(
                    self._dje_conn,
                    oab=adv_result.advogado["oab"],
                    uf=adv_result.advogado["uf"],
                    novo_cursor=adv_result.data_max_safe,
                )
                if ok:
                    self._emit_log(
                        f"Cursor de {format_advogado_label(adv_result.advogado)} "
                        f"→ {adv_result.data_max_safe.strftime('%d/%m/%Y')}",
                    )

        state_map = dje_state.read_all_advogados_state(self._dje_conn)

        # Excel-de-execução: sempre gerado, com abas Status + Log.
        export = write_publicacoes_xlsx_from_processed(
            novas_rows,
            self._output_dir,
            self._range_di,
            self._range_df,
            advogados=list(ADVOGADOS),
            state_map=state_map,
            log_lines=list(self._log_lines),
        )
        excel_path = export.path
        skipped_count = len(export.skipped)
        self._emit_log(f"Arquivo de execução salvo: {export.path}")
        self._log_skipped(export.skipped)

        # Histórico completo (regenerado se banco não-vazio).
        historico_path: Path | None = None
        historico_locked = False
        total_db = dje_db.count_publicacoes(self._dje_conn)
        if total_db > 0:
            self._emit_log(
                f"Regerando histórico completo ({total_db} publicações)...",
            )
            all_db_rows = dje_db.fetch_all_publicacoes(self._dje_conn)
            hist = write_historico_completo_xlsx(
                all_db_rows, self._output_dir,
                advogados=list(ADVOGADOS),
                state_map=state_map,
                log_lines=list(self._log_lines),
            )
            if hist.locked:
                historico_locked = True
                self._emit_log(
                    f"⚠ {HISTORICO_FILENAME} bloqueado (provável Excel "
                    "aberto). Feche o Excel e rode novamente.",
                )
            else:
                historico_path = hist.path
                self._emit_log(f"Histórico atualizado: {hist.path}")
        else:
            self._emit_log("Banco vazio — histórico não gerado.")

        return WorkerOutcome(
            excel_path=excel_path,
            historico_path=historico_path,
            historico_locked=historico_locked,
            errors=[r.advogado for r in summary.errors],
            count_antes=count_antes,
            novas_inseridas=novas_inseridas,
            skipped_count=skipped_count,
            cancelled=summary.cancelled,
            state_map_apos=state_map,
            mode=MODE_PADRAO,
        )

    def _finalize_manual(self, summary, splitted) -> "WorkerOutcome":
        """Modo personalizado (refator pós-Fase 3 hotfix):
        **NÃO toca o SQLite, NÃO regenera histórico, NÃO atualiza cursor.**
        Apenas gera o Excel-de-execução com as publicações captadas.

        O banco do escritório fica completamente intacto após qualquer
        execução em modo manual — a pesquisa de OABs externas é
        transient, só pra gerar o Excel ad-hoc.
        """
        self._emit_log(
            "Modo personalizado: banco do escritório NÃO será tocado. "
            "Apenas o Excel desta execução será gerado.",
        )
        # Excel-de-execução com TODAS as splitted (não filtra novas
        # porque não há SQLite pra comparar). Abas Status (state atual
        # do escritório, intacto) + Log (log desta execução).
        state_map = dje_state.read_all_advogados_state(self._dje_conn)
        export = write_publicacoes_xlsx_from_processed(
            splitted,
            self._output_dir,
            self._range_di,
            self._range_df,
            advogados=list(ADVOGADOS),
            state_map=state_map,
            log_lines=list(self._log_lines),
        )
        excel_path = export.path
        skipped_count = len(export.skipped)
        self._emit_log(f"Arquivo de execução salvo: {export.path}")
        self._log_skipped(export.skipped)

        return WorkerOutcome(
            excel_path=excel_path,
            historico_path=None,         # nunca regenera no manual
            historico_locked=False,
            errors=[r.advogado for r in summary.errors],
            count_antes=0,                # N/A no manual
            novas_inseridas=len(splitted),  # publicações captadas nesta exec
            skipped_count=skipped_count,
            cancelled=summary.cancelled,
            state_map_apos=state_map,
            mode=MODE_MANUAL,
        )

    def _log_skipped(self, skipped: list) -> None:
        """Loga linhas puladas pelo exporter com cap (Fase 2.1)."""
        if not skipped:
            return
        n = len(skipped)
        head = min(n, SKIPPED_LOG_CAP)
        self._emit_log(
            f"⚠ {n} linha(s) com caractere inválido foram puladas:",
        )
        for sk in skipped[:head]:
            self._emit_log(
                f"  [skipped] row_idx={sk.source_idx} id={sk.row_id} "
                f"motivo={sk.error}",
            )
        if n > SKIPPED_LOG_CAP:
            self._emit_log(
                f"  ... e mais {n - SKIPPED_LOG_CAP} linha(s) puladas "
                "(ver log do sistema/stderr)",
            )

    def _emit_progress(
        self, idx: int, total: int, result: AdvogadoResult,
    ) -> None:
        label = format_advogado_label(result.advogado)
        if result.erro is not None:
            self._emit_log(f"[{idx}/{total}] {label} — FALHA: {result.erro}")
        else:
            self._emit_log(
                f"[{idx}/{total}] {label} — "
                f"{len(result.items)} publicações em "
                f"{result.paginas} página(s)",
            )
        self.progress.emit(idx, total)


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------


class LeitorDJEPage(QWidget):
    """Página da aba Leitor DJE com 2 modos (padrão/manual) via
    ``QStackedWidget``."""

    toast_requested: Signal = Signal(str, str)  # (mensagem, kind)

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

        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._last_output_path: Path | None = None
        self._last_historico_path: Path | None = None

        # Conexão SQLite lazy — só abre na 1ª varredura.
        self._dje_conn: sqlite3.Connection | None = None

        # Worker/thread
        self._worker: _DJEWorker | None = None
        self._thread: QThread | None = None

        # State do modo manual (refator pós-Fase 3: só OABs externas).
        self._externas_rows: list[dict] = []  # cada dict: {frame, nome, oab, uf}

        self._build_ui()
        self._refresh_manual_botao()

    # ------------------------------------------------------------------
    # Lazy SQLite open
    # ------------------------------------------------------------------

    def _ensure_dje_conn(self) -> sqlite3.Connection:
        if self._dje_conn is None:
            self._dje_conn = dje_db.get_connection()
        return self._dje_conn

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        p = self._p
        self.setObjectName("LeitorDJEPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#LeitorDJEPage {{ background-color: {p.app_bg}; }}",
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(SP_8, SP_6, SP_8, SP_6)
        root.setSpacing(SP_4)

        # Header (heading + sub) ----------------------------------
        heading = QLabel("Leitor DJE")
        heading_font = QFont(FONT_DISPLAY)
        heading_font.setPixelSize(22)
        heading_font.setWeight(QFont.Weight(FW_BOLD))
        heading.setFont(heading_font)
        heading.setStyleSheet(
            f"color: {p.app_fg_strong}; background: transparent; border: none;",
        )
        root.addWidget(heading)

        # Toggle modo padrão/manual --------------------------------
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        self._sub_padrao = QLabel(
            f"Captura publicações novas desde a última execução para os "
            f"{len(ADVOGADOS)} advogados do escritório.",
        )
        self._sub_padrao.setWordWrap(True)
        self._sub_padrao.setStyleSheet(self._sub_label_css())
        self._sub_manual = QLabel(
            "Modo personalizado: período custom, subset do escritório e "
            "OABs externas.",
        )
        self._sub_manual.setWordWrap(True)
        self._sub_manual.setStyleSheet(self._sub_label_css())
        self._sub_manual.setVisible(False)
        toggle_row.addWidget(self._sub_padrao, stretch=1)
        toggle_row.addWidget(self._sub_manual, stretch=1)

        self._toggle_link = QLabel(
            f'<a href="#" style="color: {p.app_accent}; '
            f'text-decoration: none;">Modo personalizado →</a>',
        )
        self._toggle_link.setStyleSheet(
            f"color: {p.app_accent}; background: transparent; border: none;"
            f" font-size: {FS_SM2}px;",
        )
        self._toggle_link.setOpenExternalLinks(False)
        self._toggle_link.linkActivated.connect(self._on_toggle_mode)
        toggle_row.addWidget(self._toggle_link, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(toggle_row)

        # Stacked widget com as 2 páginas --------------------------
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_padrao_page())
        self._stack.addWidget(self._build_manual_page())
        self._stack.setCurrentIndex(0)
        root.addWidget(self._stack)

        # Action row (cancelar + abrir arquivo + abrir pasta) ------
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, SP_3, 0, 0)
        action_row.setSpacing(SP_3)

        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setVisible(False)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(self._cancel_btn_css())
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        action_row.addWidget(self._cancel_btn)

        self._open_file_btn = QPushButton("Abrir arquivo gerado")
        self._open_file_btn.setVisible(False)
        self._open_file_btn.setStyleSheet(self._secondary_btn_css())
        self._open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_file_btn.clicked.connect(self._on_open_file_clicked)
        action_row.addWidget(self._open_file_btn)

        self._open_hist_btn = QPushButton("Abrir histórico completo")
        self._open_hist_btn.setVisible(False)
        self._open_hist_btn.setStyleSheet(self._secondary_btn_css())
        self._open_hist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_hist_btn.clicked.connect(self._on_open_hist_clicked)
        action_row.addWidget(self._open_hist_btn)

        self._open_dir_btn = QPushButton("Abrir pasta")
        self._open_dir_btn.setVisible(False)
        self._open_dir_btn.setStyleSheet(self._secondary_btn_css())
        self._open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_dir_btn.clicked.connect(self._on_open_dir_clicked)
        action_row.addWidget(self._open_dir_btn)

        action_row.addStretch()
        root.addLayout(action_row)

        # Banner amarelo ------------------------------------------
        self._warning_lbl = QLabel("")
        self._warning_lbl.setWordWrap(True)
        self._warning_lbl.setStyleSheet(self._warning_lbl_css())
        self._warning_lbl.setVisible(False)
        root.addWidget(self._warning_lbl)

        # Progress -------------------------------------------------
        self._progress = QProgressBar()
        self._progress.setRange(0, len(ADVOGADOS))
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%v / %m advogados")
        self._progress.setStyleSheet(self._progress_css())
        root.addWidget(self._progress)

        # Log area -------------------------------------------------
        # Refator do hotfix UX: log com altura modesta (5-6 linhas) e
        # SEM stretch dominante, pra que os controles (datepickers,
        # OABs externas, botões) tenham prioridade visual. Scroll
        # interno do QPlainTextEdit cuida do excesso de mensagens.
        self._log_area = QPlainTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMinimumHeight(110)
        self._log_area.setMaximumHeight(180)
        self._log_area.setPlaceholderText(
            "Log da varredura aparecerá aqui após clicar em "
            "'Baixar publicações novas' / 'Baixar período personalizado'.",
        )
        self._log_area.setStyleSheet(self._log_area_css())
        root.addWidget(self._log_area, stretch=0)

    def _build_padrao_page(self) -> QWidget:
        """Modo padrão: 2 datepickers (default = hoje) + 2 botões.

        - **Baixar publicações novas**: ignora os datepickers, usa o
          watermark do SQLite (delta desde a última execução). Modal
          de primeira execução continua valendo.
        - **Baixar período selecionado**: usa as datas dos datepickers,
          captura as 6 OABs do escritório no período. Salva no SQLite
          com ``INSERT OR IGNORE``. **Não atualiza o watermark** —
          internamente roda em ``MODE_MANUAL`` com todas as 6 oficiais
          marcadas e 0 externas. Útil pra carga inicial controlada e
          recuperação de gaps históricos do escritório.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, SP_4, 0, 0)
        layout.setSpacing(SP_3)

        # Datepickers (default = hoje)
        date_row = QHBoxLayout()
        date_row.setSpacing(SP_3)
        hoje = _dt.date.today()

        di_label = QLabel("Data inicial:")
        di_label.setStyleSheet(self._label_css())
        date_row.addWidget(di_label)
        self._date_inicio_padrao = QDateEdit()
        self._date_inicio_padrao.setCalendarPopup(True)
        self._date_inicio_padrao.setDisplayFormat("dd/MM/yyyy")
        self._date_inicio_padrao.setDate(QDate(hoje.year, hoje.month, hoje.day))
        self._date_inicio_padrao.setStyleSheet(self._date_edit_css())
        self._date_inicio_padrao.dateChanged.connect(self._refresh_padrao_periodo_btn)
        date_row.addWidget(self._date_inicio_padrao)

        df_label = QLabel("Data final:")
        df_label.setStyleSheet(self._label_css())
        date_row.addWidget(df_label)
        self._date_fim_padrao = QDateEdit()
        self._date_fim_padrao.setCalendarPopup(True)
        self._date_fim_padrao.setDisplayFormat("dd/MM/yyyy")
        self._date_fim_padrao.setDate(QDate(hoje.year, hoje.month, hoje.day))
        self._date_fim_padrao.setStyleSheet(self._date_edit_css())
        self._date_fim_padrao.dateChanged.connect(self._refresh_padrao_periodo_btn)
        date_row.addWidget(self._date_fim_padrao)
        date_row.addStretch()
        layout.addLayout(date_row)

        # Botões
        action_row = QHBoxLayout()
        action_row.setSpacing(SP_3)

        self._download_padrao_btn = QPushButton("Baixar publicações novas")
        self._download_padrao_btn.setFixedHeight(36)
        self._download_padrao_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_padrao_btn.setStyleSheet(self._primary_btn_css())
        self._download_padrao_btn.clicked.connect(
            self._on_download_padrao_clicked,
        )
        action_row.addWidget(self._download_padrao_btn)

        self._download_padrao_periodo_btn = QPushButton(
            "Baixar período selecionado",
        )
        self._download_padrao_periodo_btn.setFixedHeight(36)
        self._download_padrao_periodo_btn.setCursor(
            Qt.CursorShape.PointingHandCursor,
        )
        self._download_padrao_periodo_btn.setStyleSheet(
            self._secondary_action_btn_css(),
        )
        self._download_padrao_periodo_btn.clicked.connect(
            self._on_download_padrao_periodo_clicked,
        )
        action_row.addWidget(self._download_padrao_periodo_btn)
        action_row.addStretch()
        layout.addLayout(action_row)
        return page

    def _build_manual_page(self) -> QWidget:
        """Modo manual: datepickers + checkboxes do escritório + lista
        dinâmica de OABs externas + botão de download.

        Wrap final em ``QScrollArea`` pra que mesmo em janelas pequenas
        do app o usuário consiga rolar e acessar todos os controles —
        o conteúdo soma ~370px e em laptops compactos isso pode não
        caber junto com header/log/progress da página.
        """
        p = self._p
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, SP_4, 0, 0)
        layout.setSpacing(SP_3)

        # Datepickers -------------------------------------------------
        date_row = QHBoxLayout()
        date_row.setSpacing(SP_3)

        ontem = _dt.date.today() - _dt.timedelta(days=1)
        last_inicio_iso = self._settings.value(_KEY_LAST_INICIO_MANUAL, "")
        if last_inicio_iso:
            try:
                cand = _dt.date.fromisoformat(last_inicio_iso)
                if (_dt.date.today() - cand).days <= 30:
                    ontem = cand
            except ValueError:
                pass

        di_label = QLabel("Data inicial:")
        di_label.setStyleSheet(self._label_css())
        date_row.addWidget(di_label)
        self._date_inicio_manual = QDateEdit()
        self._date_inicio_manual.setCalendarPopup(True)
        self._date_inicio_manual.setDisplayFormat("dd/MM/yyyy")
        self._date_inicio_manual.setDate(
            QDate(ontem.year, ontem.month, ontem.day),
        )
        self._date_inicio_manual.setStyleSheet(self._date_edit_css())
        self._date_inicio_manual.dateChanged.connect(self._refresh_manual_botao)
        date_row.addWidget(self._date_inicio_manual)

        df_label = QLabel("Data final:")
        df_label.setStyleSheet(self._label_css())
        date_row.addWidget(df_label)
        self._date_fim_manual = QDateEdit()
        self._date_fim_manual.setCalendarPopup(True)
        self._date_fim_manual.setDisplayFormat("dd/MM/yyyy")
        hoje = _dt.date.today()
        self._date_fim_manual.setDate(QDate(hoje.year, hoje.month, hoje.day))
        self._date_fim_manual.setStyleSheet(self._date_edit_css())
        self._date_fim_manual.dateChanged.connect(self._refresh_manual_botao)
        date_row.addWidget(self._date_fim_manual)

        date_row.addStretch()
        layout.addLayout(date_row)

        # Refator pós-Fase 3: removeram-se os checkboxes do escritório.
        # Modo personalizado serve SÓ pra OABs externas; uso diário do
        # escritório vai pelo botão "Baixar publicações novas".
        layout.addWidget(self._section_label(
            "OABs externas ao escritório",
        ))
        layout.addWidget(self._hint_label(
            "Pesquise advogados que não fazem parte da lista oficial "
            "do escritório. Pelo menos 1 OAB é obrigatória.",
        ))

        # Lista de OABs externas: cresce verticalmente conforme o user
        # adiciona linhas. Sem QScrollArea interno — o wrapper externo
        # da página manual já dá scroll quando a janela do app é pequena.
        # Quando vazio, mostramos uma "drop zone" com instrução
        # discreta. O ``self._externas_layout`` é onde os frames de OAB
        # são empilhados; ``self._externas_empty_label`` aparece quando
        # ``len(self._externas_rows) == 0``.
        self._externas_container = QWidget()
        self._externas_layout = QVBoxLayout(self._externas_container)
        self._externas_layout.setContentsMargins(0, 0, 0, 0)
        self._externas_layout.setSpacing(SP_2)

        self._externas_empty_label = QLabel(
            "Nenhuma OAB externa adicionada. Clique no botão abaixo para começar.",
        )
        self._externas_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._externas_empty_label.setStyleSheet(
            f"QLabel {{ color: {p.app_fg_muted};"
            f" font-size: {FS_SM2}px;"
            f" background: {p.app_panel};"
            f" border: 1px dashed {p.app_border};"
            f" border-radius: {RADIUS_MD}px;"
            f" padding: 18px; }}",
        )
        self._externas_layout.addWidget(self._externas_empty_label)
        layout.addWidget(self._externas_container)

        add_btn = QPushButton("+ Adicionar OAB externa")
        add_btn.setStyleSheet(self._secondary_btn_css())
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._on_add_externa_clicked)
        add_row = QHBoxLayout()
        add_row.addWidget(add_btn)
        add_row.addStretch()
        layout.addLayout(add_row)

        # Botão de download manual -----------------------------------
        action_row = QHBoxLayout()
        self._download_manual_btn = QPushButton("Baixar período personalizado")
        self._download_manual_btn.setFixedHeight(36)
        self._download_manual_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_manual_btn.setStyleSheet(self._primary_btn_css())
        self._download_manual_btn.clicked.connect(
            self._on_download_manual_clicked,
        )
        action_row.addWidget(self._download_manual_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        # Wrap em QScrollArea pra rolar quando a janela do app é
        # pequena e o conteúdo (~370px de altura ideal) não cabe junto
        # com header/log da página. Sem isso, os controles ficam
        # invisíveis em laptops compactos.
        wrapper = QScrollArea()
        wrapper.setWidget(page)
        wrapper.setWidgetResizable(True)
        wrapper.setFrameShape(QFrame.Shape.NoFrame)
        wrapper.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        wrapper.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }",
        )
        return wrapper

    def _section_label(self, text: str) -> QLabel:
        p = self._p
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {p.app_fg_strong}; font-size: {FS_SM2}px; "
            f"font-weight: {FW_BOLD}; background: transparent; "
            "border: none; margin-top: 4px;",
        )
        return lbl

    def _hint_label(self, text: str) -> QLabel:
        """Texto auxiliar discreto abaixo de section labels."""
        p = self._p
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {p.app_fg_muted}; font-size: {FS_SM2}px;"
            " background: transparent; border: none;",
        )
        return lbl

    # ------------------------------------------------------------------
    # OABs externas — lista dinâmica
    # ------------------------------------------------------------------

    def _on_add_externa_clicked(self) -> None:
        """Adiciona uma linha de OAB externa.

        Refator pós-Fase 3 hotfix UX: linha tem **2 campos apenas**,
        OAB (dígitos) + UF (combobox). O nome do advogado externo é
        **resolvido automaticamente** pelo ``dje_transform`` a partir
        de ``destinatarioadvogados`` retornado pela API DJEN — não há
        razão pra exigir digitação manual sujeita a typo.

        Layout responsivo:
        - OAB ocupa stretch alto (cresce com a janela)
        - UF combobox compacto (90-110px) com dropdown legível
        - Botão "Remover" textual com tooltip
        """
        p = self._p
        if len(self._externas_rows) == 0:
            self._externas_empty_label.setVisible(False)

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {p.app_panel}; "
            f"border: 1px solid {p.app_border}; "
            f"border-radius: {RADIUS_MD}px; }}",
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(SP_3, SP_2, SP_2, SP_2)
        row.setSpacing(SP_3)

        oab_input = QLineEdit()
        oab_input.setPlaceholderText("Número da OAB (somente dígitos)")
        oab_input.setValidator(QIntValidator(1, 9999999, oab_input))
        oab_input.setStyleSheet(self._input_css())
        oab_input.setMinimumHeight(32)
        oab_input.textChanged.connect(self._refresh_manual_botao)
        row.addWidget(oab_input, stretch=1)

        uf_combo = QComboBox()
        uf_combo.addItems(("UF",) + UFS_BRASIL)
        uf_combo.setStyleSheet(self._combo_css())
        uf_combo.setMinimumHeight(32)
        uf_combo.setMinimumWidth(95)
        uf_combo.setMaximumWidth(115)
        uf_combo.setMaxVisibleItems(15)
        uf_combo.view().setMinimumWidth(85)
        uf_combo.currentIndexChanged.connect(self._refresh_manual_botao)
        row.addWidget(uf_combo, stretch=0)

        remove_btn = QPushButton("Remover")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(self._remove_btn_css())
        remove_btn.setToolTip("Remover essa OAB da lista")
        remove_btn.setMinimumHeight(32)
        remove_btn.setMinimumWidth(90)
        row.addWidget(remove_btn, stretch=0)

        row_data = {
            "frame": frame,
            "oab": oab_input,
            "uf": uf_combo,
        }
        remove_btn.clicked.connect(
            lambda _checked=False, r=row_data: self._remove_externa(r),
        )
        self._externas_rows.append(row_data)
        self._externas_layout.addWidget(frame)
        self._refresh_manual_botao()

    def _remove_externa(self, row_data: dict) -> None:
        if row_data not in self._externas_rows:
            return
        self._externas_rows.remove(row_data)
        row_data["frame"].setParent(None)
        row_data["frame"].deleteLater()
        # Se removeu o último, mostra de volta a empty label.
        if len(self._externas_rows) == 0:
            self._externas_empty_label.setVisible(True)
        self._refresh_manual_botao()

    # ------------------------------------------------------------------
    # Validação do botão manual
    # ------------------------------------------------------------------

    def _refresh_manual_botao(self) -> None:
        """Modo manual (refator pós-Fase 3 hotfix UX): linhas têm 2
        campos (OAB + UF). Habilita o botão se: ``di ≤ df`` AND ≥1 OAB
        externa com OAB+UF preenchidos AND nenhuma linha parcial."""
        if not hasattr(self, "_download_manual_btn"):
            return
        di = self._date_inicio_manual.date().toPython()
        df = self._date_fim_manual.date().toPython()
        if di > df:
            self._download_manual_btn.setEnabled(False)
            return
        externas_ok = 0
        for r in self._externas_rows:
            oab = r["oab"].text().strip()
            uf = r["uf"].currentText().strip()
            uf_real = uf if uf != "UF" else ""
            if oab and uf_real:
                externas_ok += 1
            elif oab or uf_real:
                self._download_manual_btn.setEnabled(False)
                return
        self._download_manual_btn.setEnabled(externas_ok >= 1)

    # ------------------------------------------------------------------
    # Toggle entre modos
    # ------------------------------------------------------------------

    def _on_toggle_mode(self, _href: str = "") -> None:
        p = self._p
        if self._stack.currentIndex() == 0:
            self._stack.setCurrentIndex(1)
            self._sub_padrao.setVisible(False)
            self._sub_manual.setVisible(True)
            self._toggle_link.setText(
                f'<a href="#" style="color: {p.app_accent}; '
                f'text-decoration: none;">← Modo padrão</a>',
            )
        else:
            self._stack.setCurrentIndex(0)
            self._sub_padrao.setVisible(True)
            self._sub_manual.setVisible(False)
            self._toggle_link.setText(
                f'<a href="#" style="color: {p.app_accent}; '
                f'text-decoration: none;">Modo personalizado →</a>',
            )

    # ------------------------------------------------------------------
    # Handler — modo padrão
    # ------------------------------------------------------------------

    def _dialog_stylesheet(self) -> str:
        """Stylesheet de alto contraste pra QMessageBox (refator pós-
        smoke real do hotfix UX, 2026-05-02): default do Qt em algumas
        plataformas usa azul-claro sobre preto, ficando ilegível.
        Aqui forçamos fundo claro do tema + texto escuro forte +
        botões com contraste decente.
        """
        p = self._p
        return (
            f"QMessageBox {{"
            f" background-color: {p.app_panel};"
            f" color: {p.app_fg_strong};"
            f" }}"
            f"QMessageBox QLabel {{"
            f" background: transparent;"
            f" color: {p.app_fg_strong};"
            f" font-size: {FS_MD}px;"
            f" }}"
            f"QMessageBox QPushButton {{"
            f" background-color: {p.app_panel};"
            f" color: {p.app_fg_strong};"
            f" border: 1px solid {p.app_border};"
            f" border-radius: {RADIUS_MD}px;"
            f" padding: 6px 18px;"
            f" min-width: 80px;"
            f" font-size: {FS_SM2}px;"
            f" }}"
            f"QMessageBox QPushButton:hover {{"
            f" background-color: {p.app_row_hover};"
            f" }}"
            f"QMessageBox QPushButton:default {{"
            f" background-color: {p.app_accent};"
            f" color: {p.app_accent_fg};"
            f" border: 1px solid {p.app_accent};"
            f" font-weight: {FW_BOLD};"
            f" }}"
            f"QMessageBox QPushButton:default:hover {{"
            f" background-color: {p.app_accent_hover};"
            f" }}"
        )

    def _styled_question(
        self,
        title: str,
        text: str,
        *,
        default_no: bool = True,
    ) -> bool:
        """Mostra um QMessageBox.question estilizado (alto contraste).
        Retorna True se Yes, False se No/cancelado."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
        )
        box.setDefaultButton(
            QMessageBox.StandardButton.No if default_no
            else QMessageBox.StandardButton.Yes,
        )
        box.setStyleSheet(self._dialog_stylesheet())
        return box.exec() == QMessageBox.StandardButton.Yes

    def _styled_warning(self, title: str, text: str) -> None:
        """QMessageBox.warning estilizado."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setStyleSheet(self._dialog_stylesheet())
        box.exec()

    def _check_and_run_legacy_migration(self) -> bool:
        """Detecta migração legada e, se presente, mostra modal de aviso.

        Retorna ``True`` se OK pra prosseguir (migração executada ou
        não-presente). ``False`` se usuário cancelou a migração.

        Refator pós-Fase 3 hotfix: Banco com ``djen_state`` legada
        (cursor único, possivelmente contaminado) é resetado — apaga
        publicações + djen_state pra reconstruir base do zero a partir
        de cursores individuais.
        """
        conn = self._ensure_dje_conn()
        if not dje_db.is_legacy_state_present(conn):
            return True
        confirmed = self._styled_question(
            "Atualização do controle de estado",
            "Detectada base do controle de estado anterior.\n\n"
            f"O histórico será reconstruído a partir de "
            f"{dje_state.DATA_INICIO_HISTORICO_ESCRITORIO.strftime('%d/%m/%Y')} "
            "nesta execução. Pode demorar 15-20 minutos.\n\n"
            "As publicações atualmente no banco serão apagadas e "
            "recapturadas com o novo modelo de cursor por advogado, que "
            "garante que falhas isoladas (429 etc.) não criam gaps "
            "permanentes.\n\nContinuar?",
        )
        if not confirmed:
            return False
        dje_db.clear_legacy_state_and_publicacoes(conn)
        self._append_log_line(
            "Migração executada — publicações e cursor antigo apagados. "
            "Reconstrução a partir de "
            f"{dje_state.DATA_INICIO_HISTORICO_ESCRITORIO.strftime('%d/%m/%Y')}.",
        )
        return True

    def _on_download_padrao_clicked(self) -> None:
        if self._thread is not None:
            return  # idempotente
        if not self._check_and_run_legacy_migration():
            return
        conn = self._ensure_dje_conn()
        # Janela individual por advogado (refator pós-Fase 3 hotfix).
        # Cursor vazio → DEFAULT_CURSOR_VAZIO (= 2025-12-31), fazendo a
        # janela natural ser [01/01/2026, hoje]. Sem modal, sem caminho
        # especial pra "primeira vez".
        consultas: list[AdvogadoConsulta] = []
        for adv in ADVOGADOS:
            di, df = dje_state.compute_advogado_window(conn, adv)
            consultas.append(AdvogadoConsulta(
                advogado=adv, data_inicio=di, data_fim=df,
            ))
        output_dir = self._resolve_output_dir()
        if output_dir is None:
            return
        marcadas = {f"{a['oab']}/{a['uf']}" for a in ADVOGADOS}
        self._launch_worker(
            consultas=consultas,
            output_dir=output_dir,
            mode=MODE_PADRAO,
            oabs_escritorio_marcadas=marcadas,
            oabs_externas_pesquisadas=set(),
        )

    def _refresh_padrao_periodo_btn(self) -> None:
        """Habilita ``_download_padrao_periodo_btn`` se di ≤ df."""
        if not hasattr(self, "_download_padrao_periodo_btn"):
            return
        di = self._date_inicio_padrao.date().toPython()
        df = self._date_fim_padrao.date().toPython()
        self._download_padrao_periodo_btn.setEnabled(di <= df)

    def _on_download_padrao_periodo_clicked(self) -> None:
        """Handler do "Baixar período selecionado" — varre 6 OABs do
        escritório no período dos datepickers (mesma janela pra todos),
        roda em ``MODE_MANUAL`` internamente (não toca watermark).

        Útil pra carga inicial controlada ou pra recuperar gaps de
        forma direta.
        """
        if self._thread is not None:
            return
        if not self._check_and_run_legacy_migration():
            return
        di = self._date_inicio_padrao.date().toPython()
        df = self._date_fim_padrao.date().toPython()
        if df < di:
            self._set_warning(
                "Data final é anterior à data inicial. Ajuste e tente novamente.",
            )
            return
        output_dir = self._resolve_output_dir()
        if output_dir is None:
            return
        marcadas = {f"{a['oab']}/{a['uf']}" for a in ADVOGADOS}
        consultas = [
            AdvogadoConsulta(advogado=a, data_inicio=di, data_fim=df)
            for a in ADVOGADOS
        ]
        self._launch_worker(
            consultas=consultas,
            output_dir=output_dir,
            mode=MODE_MANUAL,  # não atualiza cursor
            oabs_escritorio_marcadas=marcadas,
            oabs_externas_pesquisadas=set(),
        )

    # ------------------------------------------------------------------
    # Handler — modo manual (apenas OABs externas)
    # ------------------------------------------------------------------

    def _on_download_manual_clicked(self) -> None:
        """Refator pós-Fase 3 hotfix: modo manual serve SÓ pra OABs
        externas ao escritório. Os 6 advogados oficiais são cobertos
        naturalmente pelo botão "Baixar publicações novas".

        Pelo menos 1 OAB externa preenchida (nome+OAB+UF) é obrigatória.
        """
        if self._thread is not None:
            return
        di = self._date_inicio_manual.date().toPython()
        df = self._date_fim_manual.date().toPython()
        if df < di:
            self._set_warning(
                "Data final é anterior à data inicial. Ajuste e tente novamente.",
            )
            return

        consultas: list[AdvogadoConsulta] = []
        externas_pesquisadas: set[str] = set()
        for r in self._externas_rows:
            oab = r["oab"].text().strip()
            uf = r["uf"].currentText().strip()
            if uf == "UF":  # placeholder do combo
                uf = ""
            if not (oab and uf):
                continue
            # Nome vazio: o ``dje_transform`` resolve o nome real a
            # partir de ``destinatarioadvogados`` retornado pela API.
            ext_adv: Advogado = {"nome": "", "oab": oab, "uf": uf}
            consultas.append(
                AdvogadoConsulta(advogado=ext_adv, data_inicio=di, data_fim=df),
            )
            externas_pesquisadas.add(f"{oab}/{uf}")

        if not consultas:
            self._set_warning(
                "Adicione ao menos 1 OAB externa pra baixar.",
            )
            return

        output_dir = self._resolve_output_dir()
        if output_dir is None:
            return
        self._settings.setValue(_KEY_LAST_INICIO_MANUAL, di.isoformat())
        self._launch_worker(
            consultas=consultas,
            output_dir=output_dir,
            mode=MODE_MANUAL,
            oabs_escritorio_marcadas=set(),  # nenhum oficial
            oabs_externas_pesquisadas=externas_pesquisadas,
        )

    # ------------------------------------------------------------------
    # Worker launch (comum)
    # ------------------------------------------------------------------

    def _launch_worker(
        self,
        *,
        consultas: list[AdvogadoConsulta],
        output_dir: Path,
        mode: str,
        oabs_escritorio_marcadas: set[str],
        oabs_externas_pesquisadas: set[str],
    ) -> None:
        # Reset UI
        self._warning_lbl.setVisible(False)
        self._open_file_btn.setVisible(False)
        self._open_hist_btn.setVisible(False)
        self._open_dir_btn.setVisible(False)
        self._log_area.clear()
        self._progress.setValue(0)
        self._progress.setRange(0, len(consultas))
        self._download_padrao_btn.setEnabled(False)
        self._download_padrao_periodo_btn.setEnabled(False)
        self._download_manual_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setText("Cancelar")

        conn = self._ensure_dje_conn()
        thread = QThread(self)
        worker = _DJEWorker(
            consultas=consultas,
            output_dir=output_dir,
            mode=mode,
            oabs_escritorio_marcadas=oabs_escritorio_marcadas,
            oabs_externas_pesquisadas=oabs_externas_pesquisadas,
            dje_conn=conn,
        )
        worker.moveToThread(thread)
        worker.log.connect(self._on_log_line)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_done)
        self._worker = worker
        self._thread = thread
        thread.start()

    # ------------------------------------------------------------------
    # Output dir resolver
    # ------------------------------------------------------------------

    def _resolve_output_dir(self) -> Path | None:
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

    # ------------------------------------------------------------------
    # Slot handlers do worker
    # ------------------------------------------------------------------

    def _on_log_line(self, line: str) -> None:
        self._append_log_line(line)

    def _append_log_line(self, line: str) -> None:
        """Append no log area. Reusável fora do contexto de worker
        (ex.: log de "watermark vazio, retomando..." antes do start)."""
        self._log_area.appendPlainText(line)

    def _on_progress(self, idx: int, total: int) -> None:
        if self._progress.maximum() != total:
            self._progress.setRange(0, total)
        self._progress.setValue(idx)

    def _on_cancel_clicked(self) -> None:
        if self._worker is None:
            return
        self._worker.request_cancel()
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("Cancelando...")

    def _on_finished(self, outcome: WorkerOutcome) -> None:
        self._last_output_path = outcome.excel_path
        self._last_historico_path = outcome.historico_path
        if outcome.excel_path is not None:
            self._open_file_btn.setVisible(True)
            self._open_dir_btn.setVisible(True)
        elif outcome.historico_path is not None:
            self._open_dir_btn.setVisible(True)
        if outcome.historico_path is not None:
            self._open_hist_btn.setVisible(True)

        # Banner depende do modo: modo padrão tem banco e mostra
        # "X novas (Y já existiam)"; modo manual é transient (sem
        # SQLite) e mostra apenas "X publicações captadas".
        partes: list[str] = []
        if outcome.mode == MODE_MANUAL:
            if outcome.cancelled:
                partes.append(
                    f"Varredura cancelada. {outcome.novas_inseridas} "
                    "publicações captadas até o ponto do cancel",
                )
            elif outcome.novas_inseridas == 0:
                partes.append(
                    "0 publicações encontradas para as OABs pesquisadas",
                )
            else:
                partes.append(
                    f"{outcome.novas_inseridas} publicações captadas "
                    "(banco do escritório intacto)",
                )
        elif outcome.cancelled:
            partes.append(
                f"Varredura cancelada. {outcome.novas_inseridas} "
                f"publicações novas inseridas "
                f"({outcome.count_antes} já existiam no banco)",
            )
        elif outcome.novas_inseridas == 0:
            partes.append(
                f"0 publicações novas ({outcome.count_antes} já existiam "
                "no banco — banco já estava em dia)",
            )
        else:
            partes.append(
                f"{outcome.novas_inseridas} publicações novas "
                f"({outcome.count_antes} já existiam no banco)",
            )

        # Hotfix Bug 3: lista nominal dos advogados que falharam
        # (mais útil que só contagem) + data efetiva do watermark.
        if outcome.errors:
            partes.append(
                f"⚠ {len(outcome.errors)} advogado(s) tiveram falha: "
                + ", ".join(format_advogado_label(a) for a in outcome.errors),
            )
        if outcome.skipped_count:
            partes.append(
                f"⚠ {outcome.skipped_count} linha(s) com caractere inválido foram puladas",
            )
        if outcome.historico_locked:
            partes.append(
                f"⚠ {HISTORICO_FILENAME} bloqueado — feche o Excel e rode novamente",
            )

        # Status por advogado — refator pós-Fase 3 hotfix. Cada advogado
        # tem seu cursor; banner mostra a janela mais antiga (= advogado
        # mais "atrasado") pra dar visibilidade do gap geral. Detalhe
        # individual fica na aba "Status" do Excel.
        if outcome.mode == MODE_PADRAO and outcome.state_map_apos:
            cursors = [
                v["ultimo_cursor"] for v in outcome.state_map_apos.values()
                if v.get("ultimo_cursor") is not None
            ]
            if cursors:
                oldest = min(cursors)
                partes.append(
                    f"Status por advogado salvo na aba do Excel — "
                    f"mais atrasado em {oldest.strftime('%d/%m/%Y')}",
                )

        msg = ". ".join(partes) + "."

        has_warning = (
            outcome.cancelled or outcome.errors or outcome.skipped_count
            or outcome.historico_locked
        )
        if has_warning:
            self._set_warning(msg)
            kind = "warning"
            toast = (
                "Snapshot DJE com avisos." if not outcome.cancelled
                else "Varredura cancelada."
            )
        else:
            self._set_info(msg)
            kind = "success"
            toast = (
                f"Snapshot DJE: {outcome.novas_inseridas} novas publicações."
            )
        self.toast_requested.emit(toast, kind)

    def _on_error(self, msg: str) -> None:
        self._set_warning(f"Erro fatal: {msg}")
        self.toast_requested.emit("Falha ao gerar snapshot DJE.", "error")

    def _on_thread_done(self) -> None:
        self._thread = None
        self._worker = None
        self._download_padrao_btn.setEnabled(True)
        self._refresh_padrao_periodo_btn()
        self._refresh_manual_botao()
        self._cancel_btn.setVisible(False)
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setText("Cancelar")

    def _set_warning(self, msg: str) -> None:
        p = self._p
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
        self._warning_lbl.setText(msg)
        self._warning_lbl.setVisible(True)

    def _set_info(self, msg: str) -> None:
        p = self._p
        self._warning_lbl.setStyleSheet(
            f"QLabel {{"
            f" background-color: {p.app_panel};"
            f" color: {p.app_fg};"
            f" border-left: 4px solid {p.app_accent};"
            f" padding: {SP_2}px {SP_3}px;"
            f" border-radius: {RADIUS_MD}px;"
            f" font-size: {FS_SM2}px;"
            f" }}",
        )
        self._warning_lbl.setText(msg)
        self._warning_lbl.setVisible(True)

    def _on_open_file_clicked(self) -> None:
        if self._last_output_path is None or not self._last_output_path.exists():
            self._styled_warning(
                "Arquivo não encontrado",
                "O arquivo gerado não existe mais. Rode novamente.",
            )
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self._last_output_path)),
        )

    def _on_open_hist_clicked(self) -> None:
        if (
            self._last_historico_path is None
            or not self._last_historico_path.exists()
        ):
            self._styled_warning(
                "Histórico não encontrado",
                "O arquivo histórico não existe. Rode novamente.",
            )
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self._last_historico_path)),
        )

    def _on_open_dir_clicked(self) -> None:
        target = None
        if self._last_output_path is not None:
            target = self._last_output_path.parent
        elif self._last_historico_path is not None:
            target = self._last_historico_path.parent
        if target is None or not target.exists():
            self._styled_warning(
                "Pasta não encontrada",
                "A pasta de destino não existe.",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    # ------------------------------------------------------------------
    # CSS helpers
    # ------------------------------------------------------------------

    def _label_css(self) -> str:
        p = self._p
        return (
            f"QLabel {{ color: {p.app_fg}; font-size: {FS_MD}px;"
            f" background: transparent; border: none; }}"
        )

    def _sub_label_css(self) -> str:
        p = self._p
        return (
            f"color: {p.app_fg_muted}; font-size: {FS_SM2}px;"
            f" background: transparent; border: none;"
        )

    def _date_edit_css(self) -> str:
        p = self._p
        return (
            f"QDateEdit {{ background-color: {p.app_panel}; color: {p.app_fg};"
            f" border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px;"
            f" padding: {SP_2}px {SP_3}px; font-size: {FS_MD}px;"
            f" min-width: 120px; }}"
        )

    def _checkbox_css(self) -> str:
        p = self._p
        return (
            f"QCheckBox {{ color: {p.app_fg}; font-size: {FS_SM2}px;"
            f" background: transparent; padding: 2px 6px; }}"
            f"QCheckBox::indicator {{ width: 14px; height: 14px; }}"
        )

    def _input_css(self) -> str:
        p = self._p
        return (
            f"QLineEdit {{ background-color: {p.app_bg}; color: {p.app_fg};"
            f" border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px;"
            f" padding: 4px 6px; font-size: {FS_SM2}px; }}"
        )

    def _combo_css(self) -> str:
        p = self._p
        return (
            f"QComboBox {{ background-color: {p.app_bg}; color: {p.app_fg};"
            f" border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px;"
            f" padding: 4px 8px; font-size: {FS_MD}px; }}"
            f"QComboBox::drop-down {{ width: 22px; border: none; }}"
            f"QComboBox QAbstractItemView {{"
            f" background-color: {p.app_bg}; color: {p.app_fg};"
            f" border: 1px solid {p.app_border};"
            f" selection-background-color: {p.app_accent};"
            f" selection-color: {p.app_accent_fg};"
            f" outline: none; padding: 2px;"
            f" }}"
        )

    def _primary_btn_css(self) -> str:
        p = self._p
        return (
            f"QPushButton {{"
            f" background-color: {p.app_accent}; color: {p.app_accent_fg};"
            f" font-size: {FS_MD}px; font-weight: {FW_BOLD};"
            f" border: none; border-radius: {RADIUS_MD}px;"
            f" padding: 0 {SP_4}px; }}"
            f"QPushButton:hover {{ background-color: {p.app_accent_hover}; }}"
            f"QPushButton:disabled {{ background-color: {p.app_border};"
            f" color: {p.app_fg_subtle}; }}"
        )

    def _cancel_btn_css(self) -> str:
        p = self._p
        return (
            f"QPushButton {{"
            f" background-color: {p.app_panel}; color: {p.app_warning};"
            f" font-size: {FS_MD}px; font-weight: {FW_BOLD};"
            f" border: 1px solid {p.app_warning};"
            f" border-radius: {RADIUS_MD}px; padding: 0 {SP_4}px; }}"
            f"QPushButton:hover {{ background-color: {p.app_warning_bg}; }}"
            f"QPushButton:disabled {{ background-color: {p.app_panel};"
            f" color: {p.app_fg_subtle}; border-color: {p.app_border}; }}"
        )

    def _secondary_btn_css(self) -> str:
        p = self._p
        return (
            f"QPushButton {{ background-color: transparent; color: {p.app_fg};"
            f" border: 1px solid {p.app_border}; border-radius: {RADIUS_MD}px;"
            f" padding: 0 {SP_3}px; font-size: {FS_SM2}px; }}"
            f"QPushButton:hover {{ background: {p.app_row_hover}; }}"
        )

    def _secondary_action_btn_css(self) -> str:
        """Botão de ação secundário (mesmo peso visual que o primário,
        mas em outline pra diferenciar). Usado pelo "Baixar período
        selecionado" do modo padrão."""
        p = self._p
        return (
            f"QPushButton {{"
            f" background-color: transparent; color: {p.app_accent};"
            f" font-size: {FS_MD}px; font-weight: {FW_BOLD};"
            f" border: 1.5px solid {p.app_accent};"
            f" border-radius: {RADIUS_MD}px;"
            f" padding: 0 {SP_4}px; }}"
            f"QPushButton:hover {{ background-color: {p.app_accent_hover};"
            f" color: {p.app_accent_fg}; }}"
            f"QPushButton:disabled {{ background-color: {p.app_panel};"
            f" color: {p.app_fg_subtle}; border-color: {p.app_border}; }}"
        )

    def _remove_btn_css(self) -> str:
        p = self._p
        return (
            f"QPushButton {{"
            f" background: transparent; color: {p.app_warning};"
            f" border: 1px solid {p.app_warning};"
            f" border-radius: {RADIUS_MD}px;"
            f" padding: 4px 12px; font-size: {FS_SM2}px;"
            f" font-weight: {FW_BOLD}; }}"
            f"QPushButton:hover {{ background: {p.app_warning_bg};"
            f" color: {p.app_warning}; }}"
        )

    def _warning_lbl_css(self) -> str:
        p = self._p
        return (
            f"QLabel {{ background-color: {p.app_warning_bg};"
            f" color: {p.app_warning};"
            f" border-left: 4px solid {p.app_warning};"
            f" padding: {SP_2}px {SP_3}px; border-radius: {RADIUS_MD}px;"
            f" font-size: {FS_SM2}px; }}"
        )

    def _progress_css(self) -> str:
        p = self._p
        return (
            f"QProgressBar {{ border: 1px solid {p.app_border};"
            f" border-radius: {RADIUS_MD}px; background-color: {p.app_panel};"
            f" text-align: center; font-size: {FS_SM2}px;"
            f" color: {p.app_fg_muted}; }}"
            f"QProgressBar::chunk {{ background-color: {p.app_accent};"
            f" border-radius: {RADIUS_MD}px; }}"
        )

    def _log_area_css(self) -> str:
        p = self._p
        return (
            f"QPlainTextEdit {{ background-color: {p.app_panel};"
            f" color: {p.app_fg}; border: 1px solid {p.app_border};"
            f" border-radius: {RADIUS_MD}px;"
            f" padding: {SP_2}px {SP_3}px;"
            f" font-family: 'JetBrains Mono', 'Consolas', monospace;"
            f" font-size: {FS_SM2}px; }}"
        )
