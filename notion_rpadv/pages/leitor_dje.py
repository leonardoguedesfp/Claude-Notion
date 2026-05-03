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
    REACTIVATED_2026_05_02_OABS,
    Advogado,
    format_advogado_label,
)
from notion_rpadv.services.dje_client import (
    AdvogadoConsulta,
    AdvogadoResult,
    DJEClient,
    ProcessoConsulta,
    ProcessoResult,
)
from notion_rpadv.services.dje_exporter import (
    HISTORICO_FILENAME,
    format_filename_cnj,
    write_historico_completo_xlsx,
    write_publicacoes_xlsx_from_processed,
)
from notion_rpadv.services.dje_processos import listar_cnjs_do_escritorio
from notion_rpadv.services.dje_transform import (
    dedup_by_id,
    split_advogados_columns,
)
from notion_rpadv.widgets.calendar_date_edit import CalendarDateEdit
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

# Pós-Fase 3 (2026-05-02) — flows internos do worker. Diferem em:
# - qual fetch chamar (eixo OAB ou CNJ)
# - se grava no banco (sim em "novas"; não em "período" ou personalizado)
# - se atualiza cursor (só OAB_NOVAS)
# - se regenera histórico (sim em qualquer "novas" que grava no banco)
# - naming do Excel (OAB → ``Publicacoes_DJEN_*``, CNJ → ``Publicacoes_CNJ_*``)
#
# Pós-revisão 2026-05-03 (Seção B): ``FLOW_CNJ_PERIODO`` removido —
# eixo CNJ agora tem apenas 1 botão com janela fixa.
FLOW_OAB_NOVAS: str = "oab_novas"
FLOW_OAB_PERIODO: str = "oab_periodo"
FLOW_CNJ_NOVAS: str = "cnj_novas"
FLOW_MANUAL: str = "manual"  # modo personalizado (OABs externas)

# Janela fixa do eixo CNJ (pós-revisão 2026-05-03 da Seção B). Sempre
# ``[hoje - CNJ_WINDOW_DAYS, hoje]``, independente de cursor ou input.
# Justificativa de produto: o eixo CNJ é complementar à busca por OAB
# e não pretende reconstruir histórico — só rastrear novidades recentes
# nos processos cadastrados no Notion.
CNJ_WINDOW_DAYS: int = 15


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

    Pós-Fase 3 (2026-05-02): aceita ``flow`` em vez de só ``mode``.
    Cinco flows possíveis (ver constantes ``FLOW_*`` no topo do módulo);
    cada um determina:
    - qual fetch da ``DJEClient`` chamar (OAB ou CNJ)
    - se grava no SQLite + atualiza cursor + regenera histórico
    - naming do Excel-de-execução (DJEN para eixo OAB, CNJ para eixo CNJ)
    """

    log: Signal = Signal(str)
    progress: Signal = Signal(int, int)
    finished: Signal = Signal(object)  # WorkerOutcome
    error: Signal = Signal(str)

    def __init__(
        self,
        *,
        flow: str,
        consultas_oab: list[AdvogadoConsulta] | None = None,
        consultas_cnj: list[ProcessoConsulta] | None = None,
        output_dir: Path,
        oabs_escritorio_marcadas: set[str],
        oabs_externas_pesquisadas: set[str],
        dje_conn: sqlite3.Connection,
    ) -> None:
        super().__init__()
        self._flow = flow
        self._consultas_oab = consultas_oab or []
        self._consultas_cnj = consultas_cnj or []
        self._output_dir = output_dir
        self._oabs_marcadas = oabs_escritorio_marcadas
        self._oabs_externas = oabs_externas_pesquisadas
        self._dje_conn = dje_conn
        self._client: DJEClient | None = None
        self._cancel_event = threading.Event()
        # Refator: log persistido pra aba "Log" do Excel.
        self._log_lines: list[str] = []
        # ``mode`` semântico pro WorkerOutcome (UI usa pra banner).
        # OAB_NOVAS → 'padrao'; CNJ_NOVAS → 'padrao' (mesma semântica de
        # captura oficial); demais → 'manual' (transient, não toca banco).
        self._mode = (
            MODE_PADRAO if flow in (FLOW_OAB_NOVAS, FLOW_CNJ_NOVAS)
            else MODE_MANUAL
        )
        # Faixa de datas pro nome do arquivo: MIN(di), MAX(df) entre
        # as consultas. Usado em ``write_publicacoes_xlsx_from_processed``.
        all_consultas = list(self._consultas_oab) + list(self._consultas_cnj)
        if all_consultas:
            self._range_di = min(c.data_inicio for c in all_consultas)
            self._range_df = max(c.data_fim for c in all_consultas)
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
        if self._flow in (FLOW_OAB_NOVAS, FLOW_OAB_PERIODO, FLOW_MANUAL):
            self._run_inner_oab()
        elif self._flow == FLOW_CNJ_NOVAS:
            self._run_inner_cnj()
        else:
            raise ValueError(f"flow desconhecido: {self._flow!r}")

    def _run_inner_oab(self) -> None:
        """Eixo OAB: OAB_NOVAS (grava+cursor), OAB_PERIODO (transient,
        b — não grava), MANUAL (transient, OABs externas)."""
        spans = ", ".join(
            f"{c.advogado['oab']}/{c.advogado['uf']}: "
            f"{c.data_inicio.strftime('%d/%m')}–{c.data_fim.strftime('%d/%m')}"
            for c in self._consultas_oab
        )
        self._emit_log(
            f"Iniciando varredura — flow {self._flow}, "
            f"{len(self._consultas_oab)} advogado(s).",
        )
        self._emit_log(f"Janelas: {spans}")

        summary = self._client.fetch_all(
            self._consultas_oab,
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

        deduped = dedup_by_id(summary.rows)
        splitted = split_advogados_columns(
            deduped,
            oabs_escritorio_marcadas=self._oabs_marcadas,
            oabs_externas_pesquisadas=self._oabs_externas,
        )

        if self._flow == FLOW_OAB_NOVAS:
            outcome = self._finalize_padrao(summary, splitted)
        else:  # FLOW_OAB_PERIODO ou FLOW_MANUAL — ambos transient (b)
            outcome = self._finalize_manual(summary, splitted)
        self.finished.emit(outcome)

    def _run_inner_cnj(self) -> None:
        """Eixo CNJ — flow ``FLOW_CNJ_NOVAS`` (único após Seção B,
        2026-05-03): janela fixa, grava banco + regenera histórico,
        NÃO atualiza cursor."""
        cnjs = ", ".join(c.cnj for c in self._consultas_cnj[:5])
        if len(self._consultas_cnj) > 5:
            cnjs += f" ... (+{len(self._consultas_cnj) - 5} CNJs)"
        sample_di = self._consultas_cnj[0].data_inicio
        sample_df = self._consultas_cnj[0].data_fim
        self._emit_log(
            f"Iniciando varredura por CNJ — "
            f"{len(self._consultas_cnj)} processo(s) na janela "
            f"{sample_di.strftime('%d/%m/%Y')} → {sample_df.strftime('%d/%m/%Y')}.",
        )
        self._emit_log(f"Primeiros CNJs: {cnjs}")

        summary = self._client.fetch_all_processos(
            self._consultas_cnj,
            on_progress=self._emit_progress_cnj,
            is_cancelled=self._cancel_event.is_set,
            on_log_event=self._emit_log,
        )

        if summary.cancelled:
            self._emit_log(
                "⚠ Varredura cancelada — publicações captadas até o ponto "
                "do cancel serão processadas mesmo assim.",
            )
        else:
            self._emit_log("Varredura por CNJ concluída.")

        # Pipeline dedup + split. As rows do eixo CNJ vêm anotadas com
        # ``cnj_consultado`` em vez de ``advogado_consultado``;
        # ``dedup_by_id`` agrupa por ``id`` e ``split_advogados_columns``
        # detecta os advogados do escritório a partir de
        # ``destinatarioadvogados`` da publicação (regra de fallback do
        # split quando ``oabs_escritorio_marcadas`` está vazio — o eixo
        # CNJ não tem "OABs marcadas" porque busca por número de processo).
        deduped = dedup_by_id(summary.rows)
        splitted = split_advogados_columns(
            deduped,
            oabs_escritorio_marcadas=set(),  # eixo CNJ: detecta via destinatarios
            oabs_externas_pesquisadas=set(),
        )

        outcome = self._finalize_cnj_novas(summary, splitted)
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
        """Eixo OAB transient (b — escolha do user no spec): OAB_PERIODO
        e MANUAL (modo personalizado).
        **NÃO toca o SQLite, NÃO regenera histórico, NÃO atualiza cursor.**
        Apenas gera o Excel-de-execução com as publicações captadas.

        O banco do escritório fica completamente intacto após qualquer
        execução em modo manual — a pesquisa de OABs externas é
        transient, só pra gerar o Excel ad-hoc.
        """
        self._emit_log(
            "Banco do escritório NÃO será tocado (período/personalizado). "
            "Apenas o Excel desta execução será gerado.",
        )
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
            historico_path=None,         # nunca regenera no transient
            historico_locked=False,
            errors=[r.advogado for r in summary.errors],
            count_antes=0,                # N/A no transient
            novas_inseridas=len(splitted),  # publicações captadas nesta exec
            skipped_count=skipped_count,
            cancelled=summary.cancelled,
            state_map_apos=state_map,
            mode=MODE_MANUAL,
        )

    def _finalize_cnj_novas(self, summary, splitted) -> "WorkerOutcome":
        """Eixo CNJ — flow ``CNJ_NOVAS``: GRAVA no banco (com dedup
        global por ``djen_id``), NÃO atualiza cursor (eixo CNJ não tem
        watermark por processo), regenera ``Historico_DJEN_completo.xlsx``
        e gera Excel-de-execução com naming ``Publicacoes_CNJ_*``.
        """
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
                data_disponibilizacao=str(
                    row.get("data_disponibilizacao") or "",
                ),
                sigla_tribunal=row.get("siglaTribunal"),
                payload=payload,
                # Eixo CNJ usa mode='padrao' no banco (mesma semântica de
                # captura oficial — pra agregação simples e compat com
                # CHECK constraint atual). Distinção do eixo (OAB vs CNJ)
                # vive só no log e no naming do Excel-de-execução.
                mode=MODE_PADRAO,
            )
            if inserted:
                novas_rows.append(row)
        self._dje_conn.commit()

        count_apos = dje_db.count_publicacoes(self._dje_conn)
        novas_inseridas = len(novas_rows)
        novas_real = count_apos - count_antes
        if novas_real != novas_inseridas:
            logger.warning(
                "DJE.cnj: divergência em contadores — rowcount=%d, "
                "COUNT(*)_pre=%d, COUNT(*)_pos=%d, real=%d. Usando real.",
                novas_inseridas, count_antes, count_apos, novas_real,
            )
            novas_inseridas = novas_real

        self._emit_log(
            f"SQLite: {novas_inseridas} novas inseridas "
            f"({count_antes} já existiam).",
        )

        state_map = dje_state.read_all_advogados_state(self._dje_conn)

        # Excel-de-execução com naming CNJ.
        export = write_publicacoes_xlsx_from_processed(
            novas_rows,
            self._output_dir,
            self._range_di,
            self._range_df,
            advogados=list(ADVOGADOS),
            state_map=state_map,
            log_lines=list(self._log_lines),
            filename_fn=format_filename_cnj,
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

        # ``errors`` no eixo CNJ é lista de processos que falharam — UI
        # banner consome via ``len(errors)`` apenas, então passamos
        # AdvogadoConsulta-like dicts pra preservar o formato esperado
        # do banner. Mais simples: lista vazia (CNJ errors não bloqueiam
        # cursor; UI vê detalhe via aba Log do Excel).
        return WorkerOutcome(
            excel_path=excel_path,
            historico_path=historico_path,
            historico_locked=historico_locked,
            errors=[],  # ver comentário acima
            count_antes=count_antes,
            novas_inseridas=novas_inseridas,
            skipped_count=skipped_count,
            cancelled=summary.cancelled,
            state_map_apos=state_map,
            mode=MODE_PADRAO,
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

    def _emit_progress_cnj(
        self, idx: int, total: int, result: ProcessoResult,
    ) -> None:
        # Log compacto pro eixo CNJ — N processos pode ser >> 6 e o log
        # ficaria poluído com 1 linha por processo. ``fetch_all_processos``
        # já emite via ``on_log_event`` quando há erro ou items > 0;
        # aqui só atualizamos a barra de progresso.
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
        # A2 (2026-05-03): texto introdutório neutro entre os 2 eixos
        # do modo padrão. O sub-texto antigo era específico do eixo OAB
        # ("para os 6 advogados") e ficava confuso quando o usuário
        # olhava o painel CNJ.
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        self._sub_padrao = QLabel(
            "Captura publicações no DJEN. 'Por OAB' busca pelos advogados "
            "do escritório; 'Por número CNJ' busca pelos processos cadastrados "
            "no Notion.",
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

        # Action row dos botões pós-execução (Abrir arquivo/pasta/histórico)
        # Ficam fora do container "Execução em andamento" porque são
        # ações pós-conclusão, não in-flight.
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, SP_2, 0, 0)
        action_row.setSpacing(SP_3)

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

        # ==========================================================
        # A7 (2026-05-03) — Container "Execução em andamento"
        # Agrupa: heading + barra de progresso + log + botão Cancelar.
        # Aparece quando worker inicia, some quando termina (a UI fica
        # mais limpa antes da varredura).
        # ==========================================================
        self._exec_container = QFrame()
        self._exec_container.setStyleSheet(self._eixo_panel_css())
        self._exec_container.setVisible(False)
        exec_col = QVBoxLayout(self._exec_container)
        exec_col.setContentsMargins(SP_4, SP_3, SP_4, SP_3)
        exec_col.setSpacing(SP_2)

        # Header da execução (heading + Cancelar à direita).
        # Heading muda entre "Execução em andamento" (worker ativo) e
        # "Última execução" (após terminar) — sinaliza claramente o estado.
        exec_header = QHBoxLayout()
        exec_header.setSpacing(SP_3)
        self._exec_heading = QLabel("Execução em andamento")
        self._exec_heading.setStyleSheet(self._eixo_heading_css())
        exec_header.addWidget(self._exec_heading)
        exec_header.addStretch()
        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setMinimumHeight(32)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(self._cancel_btn_css())
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        exec_header.addWidget(self._cancel_btn)
        exec_col.addLayout(exec_header)

        # A6: Progress bar com contraste reforçado (cor accent_strong
        # via stylesheet em ``_progress_css`` — refeito abaixo).
        self._progress = QProgressBar()
        self._progress.setRange(0, len(ADVOGADOS))
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%v / %m advogados")
        self._progress.setMinimumHeight(20)
        self._progress.setStyleSheet(self._progress_css())
        exec_col.addWidget(self._progress)

        # Log area dentro do container (5-6 linhas).
        self._log_area = QPlainTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMinimumHeight(110)
        self._log_area.setMaximumHeight(180)
        self._log_area.setPlaceholderText(
            "Log da varredura aparecerá aqui durante a execução.",
        )
        self._log_area.setStyleSheet(self._log_area_css())
        exec_col.addWidget(self._log_area, stretch=0)

        root.addWidget(self._exec_container)

    def _build_padrao_page(self) -> QWidget:
        """Modo padrão: 2 eixos paralelos de busca (OAB e CNJ), cada um
        com 2 botões + datepickers próprios.

        **Eixo OAB** (busca clássica do escritório):
        - "Publicações novas por OAB": janela individual por advogado
          a partir do cursor (``djen_advogado_state``); grava no banco;
          atualiza cursor; regenera ``Historico_DJEN_completo.xlsx``.
        - "Baixar pelo período selecionado": usa datepickers; **não grava
          no banco** (escolha b do user, 2026-05-02) — gera só
          Excel-de-execução, banco intacto.

        **Eixo CNJ** (pós-Fase 3, busca via lista de processos do Notion):
        - "Publicações novas por número CNJ": janela calculada do cursor
          mais antigo dos advogados +1d até hoje; consulta cada CNJ do
          cache local da base "Processos"; grava no banco com dedup
          global; regenera histórico; **não atualiza cursor** (eixo CNJ
          não tem watermark por processo).
        - "Baixar pelo período selecionado": datepickers; **não grava no
          banco** (escolha b).
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, SP_3, 0, 0)
        # A5 (2026-05-03): spacing entre os 2 painéis reduzido pra
        # hierarquia visual mais compacta — havia muito ar entre eles
        # antes (``SP_4``), agora ``SP_3``.
        layout.setSpacing(SP_3)

        # ==========================================================
        # EIXO 1 — OAB (existente, com renomeações)
        # ==========================================================
        layout.addWidget(self._build_eixo_oab_panel())

        # ==========================================================
        # EIXO 2 — CNJ (novo, pós-Fase 3 2026-05-02)
        # ==========================================================
        layout.addWidget(self._build_eixo_cnj_panel())

        layout.addStretch()
        return page

    def _eixo_panel_css(self) -> str:
        """Estilo de painel agrupador (frame com borda discreta + padding)."""
        p = self._p
        return (
            f"QFrame {{"
            f" background: {p.app_panel};"
            f" border: 1px solid {p.app_border};"
            f" border-radius: {RADIUS_MD}px;"
            f" }}"
        )

    def _eixo_heading_css(self) -> str:
        p = self._p
        return (
            f"color: {p.app_fg_strong}; font-size: {FS_MD}px;"
            f" font-weight: {FW_BOLD};"
            f" background: transparent; border: none;"
        )

    def _build_eixo_oab_panel(self) -> QFrame:
        """Painel do eixo OAB — datepickers + 2 botões (novas + período)."""
        frame = QFrame()
        frame.setStyleSheet(self._eixo_panel_css())
        # A3/A8 (2026-05-03): margens internas amplas (especialmente
        # bottom) pra que botões com altura ~36px não toquem a borda
        # arredondada do painel. SP_4 em todos os lados.
        col = QVBoxLayout(frame)
        col.setContentsMargins(SP_4, SP_4, SP_4, SP_4)
        # A5: spacing reduzido pra hierarquia mais compacta.
        col.setSpacing(SP_2)

        heading = QLabel("Por OAB")
        heading.setStyleSheet(self._eixo_heading_css())
        col.addWidget(heading)

        sub = QLabel(
            f"Busca pelos {len(ADVOGADOS)} advogados oficiais do escritório.",
        )
        sub.setStyleSheet(self._sub_label_css())
        sub.setWordWrap(True)
        col.addWidget(sub)

        # Datepickers do eixo OAB.
        # A4 (2026-05-03): labels com ``AlignVCenter`` pra ficar
        # baseline-alinhadas com o campo de data ao lado.
        date_row = QHBoxLayout()
        date_row.setSpacing(SP_2)
        date_row.setContentsMargins(0, SP_2, 0, 0)
        hoje = _dt.date.today()

        di_label = QLabel("Período:")
        di_label.setStyleSheet(self._label_css())
        date_row.addWidget(di_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._date_inicio_padrao = CalendarDateEdit()
        self._date_inicio_padrao.setDisplayFormat("dd/MM/yyyy")
        self._date_inicio_padrao.setDate(QDate(hoje.year, hoje.month, hoje.day))
        self._date_inicio_padrao.setStyleSheet(self._date_edit_css())
        self._date_inicio_padrao.dateChanged.connect(
            self._refresh_padrao_periodo_btn,
        )
        date_row.addWidget(
            self._date_inicio_padrao,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )

        ate_label = QLabel("até")
        ate_label.setStyleSheet(self._label_css())
        date_row.addWidget(ate_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._date_fim_padrao = CalendarDateEdit()
        self._date_fim_padrao.setDisplayFormat("dd/MM/yyyy")
        self._date_fim_padrao.setDate(QDate(hoje.year, hoje.month, hoje.day))
        self._date_fim_padrao.setStyleSheet(self._date_edit_css())
        self._date_fim_padrao.dateChanged.connect(
            self._refresh_padrao_periodo_btn,
        )
        date_row.addWidget(
            self._date_fim_padrao,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        date_row.addStretch()
        col.addLayout(date_row)

        # Botões do eixo OAB.
        # A3/A8: ``setMinimumHeight`` em vez de ``setFixedHeight`` —
        # permite o botão crescer ligeiramente se a fonte do sistema
        # for maior, evitando recorte de glifos descendentes.
        action_row = QHBoxLayout()
        action_row.setSpacing(SP_3)
        action_row.setContentsMargins(0, SP_2, 0, 0)

        self._download_padrao_btn = QPushButton("Publicações novas por OAB")
        self._download_padrao_btn.setMinimumHeight(36)
        self._download_padrao_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_padrao_btn.setStyleSheet(self._primary_btn_css())
        self._download_padrao_btn.setToolTip(
            "Baixa as publicações desde o cursor de cada advogado (estado "
            "do banco). Atualiza o cursor e regenera o histórico.",
        )
        self._download_padrao_btn.clicked.connect(
            self._on_download_padrao_clicked,
        )
        action_row.addWidget(self._download_padrao_btn)

        self._download_padrao_periodo_btn = QPushButton(
            "Baixar pelo período selecionado",
        )
        self._download_padrao_periodo_btn.setMinimumHeight(36)
        self._download_padrao_periodo_btn.setCursor(
            Qt.CursorShape.PointingHandCursor,
        )
        self._download_padrao_periodo_btn.setStyleSheet(
            self._secondary_action_btn_css(),
        )
        self._download_padrao_periodo_btn.setToolTip(
            "Roda no período acima sem gravar no banco — gera só Excel "
            "de execução pra inspeção/teste.",
        )
        self._download_padrao_periodo_btn.clicked.connect(
            self._on_download_padrao_periodo_clicked,
        )
        action_row.addWidget(self._download_padrao_periodo_btn)
        action_row.addStretch()
        col.addLayout(action_row)
        return frame

    def _build_eixo_cnj_panel(self) -> QFrame:
        """Painel do eixo CNJ — minimalista: 1 botão + texto explicativo.

        Pós-revisão de produto (2026-05-03, Seção B): sem datepickers,
        sem botão de período. Janela é fixa: ``[hoje - 15d, hoje]``.
        Origem dos CNJs: cache local da base "Processos" do Notion."""
        frame = QFrame()
        frame.setStyleSheet(self._eixo_panel_css())
        # A3/A8: margens internas amplas pra que o botão não toque a
        # borda arredondada do painel.
        col = QVBoxLayout(frame)
        col.setContentsMargins(SP_4, SP_4, SP_4, SP_4)
        col.setSpacing(SP_2)

        heading = QLabel("Por número CNJ")
        heading.setStyleSheet(self._eixo_heading_css())
        col.addWidget(heading)

        self._cnj_sub_label = QLabel(
            "Busca publicações dos últimos 15 dias para todos os processos "
            "cadastrados no Notion. Complementa a busca por OAB.",
        )
        self._cnj_sub_label.setStyleSheet(self._sub_label_css())
        self._cnj_sub_label.setWordWrap(True)
        col.addWidget(self._cnj_sub_label)

        # Botão único do eixo CNJ.
        action_row = QHBoxLayout()
        action_row.setSpacing(SP_3)
        action_row.setContentsMargins(0, SP_2, 0, 0)

        self._download_cnj_btn = QPushButton("Publicações novas por número CNJ")
        self._download_cnj_btn.setMinimumHeight(36)
        self._download_cnj_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_cnj_btn.setStyleSheet(self._primary_btn_css())
        self._download_cnj_btn.setToolTip(
            f"Busca dos últimos {CNJ_WINDOW_DAYS} dias até hoje, "
            "consulta cada processo do Notion individualmente, grava no banco "
            "com dedup global. NÃO atualiza cursor (eixo CNJ não tem watermark "
            "por processo).",
        )
        self._download_cnj_btn.clicked.connect(self._on_download_cnj_clicked)
        action_row.addWidget(self._download_cnj_btn)
        action_row.addStretch()
        col.addLayout(action_row)
        return frame

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
        date_row.addWidget(di_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._date_inicio_manual = CalendarDateEdit()
        self._date_inicio_manual.setDisplayFormat("dd/MM/yyyy")
        self._date_inicio_manual.setDate(
            QDate(ontem.year, ontem.month, ontem.day),
        )
        self._date_inicio_manual.setStyleSheet(self._date_edit_css())
        self._date_inicio_manual.dateChanged.connect(self._refresh_manual_botao)
        date_row.addWidget(
            self._date_inicio_manual,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )

        df_label = QLabel("Data final:")
        df_label.setStyleSheet(self._label_css())
        date_row.addWidget(df_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._date_fim_manual = CalendarDateEdit()
        self._date_fim_manual.setDisplayFormat("dd/MM/yyyy")
        hoje = _dt.date.today()
        self._date_fim_manual.setDate(QDate(hoje.year, hoje.month, hoje.day))
        self._date_fim_manual.setStyleSheet(self._date_edit_css())
        self._date_fim_manual.dateChanged.connect(self._refresh_manual_botao)
        date_row.addWidget(
            self._date_fim_manual,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )

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

    def _check_and_offer_reactivation_reset(self) -> None:
        """Pós-Fase 3 (2026-05-02): se detectar que os 4 advogados
        reativados têm cursor armazenado mas a flag de tratamento
        ainda não foi setada, oferece modal one-shot pra zerar esses
        cursores.

        Caso de uso: antes de 02/05/2026, esses 4 advogados estavam
        ativos com cursores em ``2026-05-02`` que NÃO refletem captura
        real (foram preservados antes do refator de watermark-por-
        advogado). Sem o reset, a próxima execução parte de 03/05 e o
        gap de jan-abr/2026 fica permanente pra eles.

        A flag ``FLAG_REATIVACAO_2026_05_02`` em ``app_flags`` é setada
        em **qualquer** ramo (sim/não/no-op) — modal nunca recorre na
        mesma máquina. Bumpe o nome da flag em ``dje_db.py`` se for
        necessário re-mostrar o modal.

        Não retorna nada — quando o usuário escolhe "Sim", os cursores
        são zerados ali mesmo; quando escolhe "Não", segue com cursores
        preservados. O ramo "máquina sem nenhum dos 4 cursores" (e.g.
        máquina nova ou que nunca rodou esses advogados) marca a flag
        sem mostrar nada.
        """
        conn = self._ensure_dje_conn()
        if dje_db.read_flag(
            conn, dje_db.FLAG_REATIVACAO_2026_05_02,
        ) is not None:
            return  # já tratado nesta máquina

        state_map = dje_state.read_all_advogados_state(conn)
        com_cursor = [
            oab_uf for oab_uf in REACTIVATED_2026_05_02_OABS
            if state_map.get(oab_uf, {}).get("ultimo_cursor") is not None
        ]
        if not com_cursor:
            # Máquina sem nenhum dos 4 cursores — não há o que resetar.
            # Marca a flag pra não recorrer (próxima execução o estado
            # já será o desejado naturalmente).
            dje_db.set_flag(
                conn, dje_db.FLAG_REATIVACAO_2026_05_02, "no_cursors_to_reset",
            )
            return

        nomes = "Vitor, Cecília, Samantha, Deborah"
        confirmed = self._styled_question(
            "Reativação detectada",
            f"Detectada reativação de 4 advogados ({nomes}).\n\n"
            f"Para reconstruir o histórico deles desde "
            f"{dje_state.DATA_INICIO_HISTORICO_ESCRITORIO.strftime('%d/%m/%Y')}, "
            "os cursores serão zerados. Pode demorar 15-20 minutos e "
            "haverá alta probabilidade de 429 da API DJEN.\n\n"
            "Continuar com reset?",
            default_no=True,
        )
        if confirmed:
            dje_state.reset_advogado_cursores(conn, list(com_cursor))
            dje_db.set_flag(
                conn, dje_db.FLAG_REATIVACAO_2026_05_02, "reset_yes",
            )
            self._append_log_line(
                f"Cursores zerados de {len(com_cursor)} advogado(s) — "
                "próxima varredura reconstrói desde "
                f"{dje_state.DATA_INICIO_HISTORICO_ESCRITORIO.strftime('%d/%m/%Y')}.",
            )
        else:
            dje_db.set_flag(
                conn, dje_db.FLAG_REATIVACAO_2026_05_02, "reset_no",
            )
            self._append_log_line(
                "Reativação tratada — cursores mantidos. Gap consciente: "
                "histórico anterior não será reconstruído pra esses 4 advogados.",
            )

    def _on_download_padrao_clicked(self) -> None:
        """Eixo OAB — "Publicações novas por OAB" (FLOW_OAB_NOVAS):
        janela individual por advogado a partir do cursor."""
        if self._thread is not None:
            return  # idempotente
        if not self._check_and_run_legacy_migration():
            return
        # Pós-Fase 3: oferece reset one-shot dos 4 advogados reativados
        # em 2026-05-02 (cursores falsos). Não-bloqueante — segue com
        # qualquer resposta.
        self._check_and_offer_reactivation_reset()
        conn = self._ensure_dje_conn()
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
            flow=FLOW_OAB_NOVAS,
            consultas_oab=consultas,
            consultas_cnj=None,
            output_dir=output_dir,
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
        """Eixo OAB — "Baixar pelo período selecionado" (FLOW_OAB_PERIODO):
        varre as OABs do escritório no período dos datepickers.

        Pós-Fase 3 (escolha b do user, 2026-05-02): NÃO grava no banco —
        gera só Excel-de-execução. Banco intacto.
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
            flow=FLOW_OAB_PERIODO,
            consultas_oab=consultas,
            consultas_cnj=None,
            output_dir=output_dir,
            oabs_escritorio_marcadas=marcadas,
            oabs_externas_pesquisadas=set(),
        )

    # ------------------------------------------------------------------
    # Handler — eixo CNJ (pós-revisão Seção B, 2026-05-03)
    # ------------------------------------------------------------------

    def _coletar_consultas_cnj(
        self, di: _dt.date, df: _dt.date,
    ) -> list[ProcessoConsulta] | None:
        """Lê CNJs do cache local (base "Processos" do Notion) e monta
        a lista de consultas pra ``fetch_all_processos``.

        Retorna ``None`` (com toast/warning para o usuário) se cache
        estiver vazio — caller aborta o fluxo. Retorna lista vazia é
        estado teórico só (cache populado mas sem CNJs válidos).
        """
        try:
            cnjs = listar_cnjs_do_escritorio(self._conn)
        except Exception as exc:  # noqa: BLE001
            logger.exception("DJE.cnj: falha ao listar CNJs do cache")
            self._styled_warning(
                "Erro lendo lista de processos",
                f"Não consegui ler os CNJs do cache local: {exc}",
            )
            return None
        if not cnjs:
            self._styled_warning(
                "Cache de Processos vazio",
                "O cache local da base 'Processos' está vazio. Sincronize "
                "a base (aba Processos → 'Sincronizar') antes de usar o "
                "eixo CNJ.",
            )
            return None
        return [
            ProcessoConsulta(cnj=c, data_inicio=di, data_fim=df)
            for c in cnjs
        ]

    def _on_download_cnj_clicked(self) -> None:
        """Eixo CNJ — "Publicações novas por número CNJ" (``FLOW_CNJ_NOVAS``):
        janela FIXA ``[hoje - CNJ_WINDOW_DAYS, hoje]``, busca cada processo
        do Notion individualmente, grava no banco com dedup global, regenera
        o histórico. NÃO atualiza cursor (eixo CNJ é complementar e não
        pode marcar como "captado" para o eixo OAB algo que verificou só
        para alguns processos específicos)."""
        if self._thread is not None:
            return
        if not self._check_and_run_legacy_migration():
            return
        self._check_and_offer_reactivation_reset()
        df = _dt.date.today()
        di = df - _dt.timedelta(days=CNJ_WINDOW_DAYS)
        consultas = self._coletar_consultas_cnj(di, df)
        if consultas is None:
            return
        output_dir = self._resolve_output_dir()
        if output_dir is None:
            return
        self._launch_worker(
            flow=FLOW_CNJ_NOVAS,
            consultas_oab=None,
            consultas_cnj=consultas,
            output_dir=output_dir,
            oabs_escritorio_marcadas=set(),
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
            flow=FLOW_MANUAL,
            consultas_oab=consultas,
            consultas_cnj=None,
            output_dir=output_dir,
            oabs_escritorio_marcadas=set(),  # nenhum oficial
            oabs_externas_pesquisadas=externas_pesquisadas,
        )

    # ------------------------------------------------------------------
    # Worker launch (comum)
    # ------------------------------------------------------------------

    def _launch_worker(
        self,
        *,
        flow: str,
        consultas_oab: list[AdvogadoConsulta] | None,
        consultas_cnj: list[ProcessoConsulta] | None,
        output_dir: Path,
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
        n_consultas = len(consultas_oab or []) + len(consultas_cnj or [])
        self._progress.setRange(0, max(n_consultas, 1))
        # A1 (2026-05-03): label da barra reflete o que está sendo iterado
        # — "advogados" no eixo OAB, "processos" no eixo CNJ.
        unidade = "processos" if flow == FLOW_CNJ_NOVAS else "advogados"
        self._progress.setFormat(f"%v / %m {unidade}")
        # A7: mostra container "Execução em andamento" — heading ativo
        # enquanto worker roda, depois vira "Última execução".
        self._exec_heading.setText("Execução em andamento")
        self._exec_container.setVisible(True)
        # Desabilita TODOS os botões de início enquanto worker roda.
        self._download_padrao_btn.setEnabled(False)
        self._download_padrao_periodo_btn.setEnabled(False)
        self._download_cnj_btn.setEnabled(False)
        self._download_manual_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setText("Cancelar")

        conn = self._ensure_dje_conn()
        thread = QThread(self)
        worker = _DJEWorker(
            flow=flow,
            consultas_oab=consultas_oab,
            consultas_cnj=consultas_cnj,
            output_dir=output_dir,
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
        # Hotfix 2026-05-03: confiar no path retornado E confirmar
        # que existe — caso o exporter retorne path mas a escrita
        # tenha falhado silenciosamente, ou o arquivo desapareça antes
        # do click do usuário. ``_refresh_open_buttons_visibility`` só
        # esconde — mostramos primeiro de forma otimista.
        if outcome.excel_path is not None:
            self._open_file_btn.setVisible(True)
            self._open_dir_btn.setVisible(True)
        elif outcome.historico_path is not None:
            self._open_dir_btn.setVisible(True)
        if outcome.historico_path is not None:
            self._open_hist_btn.setVisible(True)
        # Revalida: se algum path retornado pelo worker não existe no
        # FS por algum motivo, esconde silenciosamente.
        self._refresh_open_buttons_visibility()

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
        self._download_cnj_btn.setEnabled(True)
        self._refresh_padrao_periodo_btn()
        self._refresh_manual_botao()
        # Container fica visível com o log da execução pra o usuário
        # poder revisar; heading muda pra "Última execução" e o botão
        # Cancelar some.
        self._exec_heading.setText("Última execução")
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

    def _refresh_open_buttons_visibility(self) -> None:
        """Verifica silenciosamente se os arquivos/pastas referenciados
        em ``_last_*_path`` ainda existem; esconde botões cujos alvos
        foram movidos/apagados.

        Hotfix 2026-05-03: o modal "Arquivo não encontrado" do
        ``_on_open_file_clicked`` aparecia toda vez que o operador
        clicava em "Abrir arquivo gerado" depois de qualquer mudança
        no FS (Excel fechado e movido pra outra pasta, .xlsx renomeado,
        etc). Política nova:

        - Botões só ficam visíveis enquanto o alvo existe de fato.
        - Se sumiu, esconde o botão e segue silenciosamente.
        - Modal só aparece pra erro inesperado durante a abertura
          em si (gap entre ``exists()`` check e ``openUrl()`` é
          microssegundos — quase impossível disparar).

        Chamado em ``_on_finished``, ``showEvent`` (revalida ao voltar
        pra aba) e dentro dos próprios click handlers.
        """
        output_ok = (
            self._last_output_path is not None
            and self._last_output_path.exists()
        )
        hist_ok = (
            self._last_historico_path is not None
            and self._last_historico_path.exists()
        )
        # Pasta-alvo do "Abrir pasta" pode vir de qualquer um dos 2 paths.
        dir_target: Path | None = None
        if self._last_output_path is not None:
            dir_target = self._last_output_path.parent
        elif self._last_historico_path is not None:
            dir_target = self._last_historico_path.parent
        dir_ok = dir_target is not None and dir_target.exists()

        if not output_ok:
            self._open_file_btn.setVisible(False)
        if not hist_ok:
            self._open_hist_btn.setVisible(False)
        if not dir_ok:
            self._open_dir_btn.setVisible(False)

    def showEvent(self, event) -> None:  # noqa: N802
        """Revalida visibilidade dos botões de "Abrir" sempre que a
        página volta a ser exibida (troca de aba). Mantém invariante
        de que botões só aparecem com alvo válido."""
        super().showEvent(event)
        self._refresh_open_buttons_visibility()

    def _on_open_file_clicked(self) -> None:
        # Re-checa silenciosamente antes de tentar abrir; se sumiu,
        # esconde o botão e ignora — sem modal "Rode novamente" que
        # é confuso (o usuário sabe que rodou).
        if (
            self._last_output_path is None
            or not self._last_output_path.exists()
        ):
            self._open_file_btn.setVisible(False)
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self._last_output_path)),
        )

    def _on_open_hist_clicked(self) -> None:
        if (
            self._last_historico_path is None
            or not self._last_historico_path.exists()
        ):
            self._open_hist_btn.setVisible(False)
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self._last_historico_path)),
        )

    def _on_open_dir_clicked(self) -> None:
        target: Path | None = None
        if self._last_output_path is not None:
            target = self._last_output_path.parent
        elif self._last_historico_path is not None:
            target = self._last_historico_path.parent
        if target is None or not target.exists():
            self._open_dir_btn.setVisible(False)
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
        """A6 (2026-05-03): contraste reforçado.

        Antes: chunk azul-marinho ``app_accent`` (#104063) sobre fundo
        ``app_panel`` claro, ambos escuros — só aparecia sombra fina.
        Agora: track ``app_bg`` (cinza muito claro) + chunk com
        ``app_success`` (verde RPADV #3F6E55, semântica de "progresso/
        andamento OK") + texto preto forte centralizado. Dá muito mais
        contraste sem sair da brand."""
        p = self._p
        return (
            f"QProgressBar {{"
            f" border: 1px solid {p.app_border};"
            f" border-radius: {RADIUS_MD}px;"
            f" background-color: {p.app_bg};"
            f" text-align: center;"
            f" font-size: {FS_SM2}px;"
            f" font-weight: {FW_BOLD};"
            f" color: {p.app_fg_strong};"
            f" min-height: 20px;"
            f" }}"
            f"QProgressBar::chunk {{"
            f" background-color: {p.app_success};"
            f" border-radius: {RADIUS_MD}px;"
            f" }}"
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
