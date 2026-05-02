"""Watermark POR ADVOGADO do Leitor DJE (refator pós-Fase 3 hotfix).

Cada advogado oficial do escritório tem seu próprio cursor armazenado
em ``djen_advogado_state``. A varredura de "Baixar publicações novas"
calcula janela individual ``[cursor + 1 dia, hoje]`` por advogado.
Falha de um advogado não afeta o cursor dos outros.

Cursor de cada advogado avança até a última sub-janela contígua
completa após retry diferido (granularidade mensal, mesma do split de
``dje_client``). Anti-regressão garantida: ``update_advogado_cursor``
recusa data anterior ao cursor existente.

Modo manual NUNCA toca em ``djen_advogado_state`` — modo manual é uso
ad-hoc pra OABs externas, não pertence ao watermark do escritório.

**Constantes**:
- ``DATA_INICIO_HISTORICO_ESCRITORIO``: data inicial pra "primeira
  varredura" de qualquer advogado oficial. Quando o cursor está vazio,
  o app trata como se cursor fosse ``DATA_INICIO_HISTORICO_ESCRITORIO -
  1 dia``, fazendo a janela ser ``[01/01/2026, hoje]``.
- ``DEFAULT_CURSOR_VAZIO``: derivado da constante acima — a "data
  fictícia" que substitui ``None`` quando o cursor está vazio.

Sem modal de "primeira execução": cursor vazio é só estado normal,
tratado como qualquer outro cursor mais antigo.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger("dje.state")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------


DATA_INICIO_HISTORICO_ESCRITORIO: date = date(2026, 1, 1)
DEFAULT_CURSOR_VAZIO: date = DATA_INICIO_HISTORICO_ESCRITORIO - timedelta(days=1)


# ---------------------------------------------------------------------------
# API por advogado
# ---------------------------------------------------------------------------


def read_advogado_cursor(
    conn: sqlite3.Connection,
    *,
    oab: str,
    uf: str,
) -> date | None:
    """Cursor de 1 advogado. ``None`` se nunca executou.

    Caller decide o que fazer com ``None`` — tipicamente substituir
    por ``DEFAULT_CURSOR_VAZIO`` pra obter janela ``[01/01/2026, hoje]``.
    """
    row = conn.execute(
        "SELECT ultimo_cursor FROM djen_advogado_state "
        "WHERE numero_oab = ? AND uf_oab = ?",
        (oab, uf),
    ).fetchone()
    if row is None or row["ultimo_cursor"] is None:
        return None
    return date.fromisoformat(row["ultimo_cursor"])


def read_advogado_last_run(
    conn: sqlite3.Connection,
    *,
    oab: str,
    uf: str,
) -> datetime | None:
    """``last_run`` do advogado (UTC naive)."""
    row = conn.execute(
        "SELECT last_run FROM djen_advogado_state "
        "WHERE numero_oab = ? AND uf_oab = ?",
        (oab, uf),
    ).fetchone()
    if row is None or row["last_run"] is None:
        return None
    return datetime.fromisoformat(row["last_run"])


def update_advogado_cursor(
    conn: sqlite3.Connection,
    *,
    oab: str,
    uf: str,
    novo_cursor: date,
    last_run: datetime | None = None,
) -> bool:
    """Upsert do cursor de 1 advogado.

    Retorna ``True`` se aplicou; ``False`` se rejeitou por regressão
    (``novo_cursor < cursor_existente``, loga warning e mantém estado).

    ``last_run`` opcional pra teste — default: now UTC naive.
    """
    ts = (last_run or datetime.now(timezone.utc).replace(tzinfo=None))
    ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%S")
    novo_iso = novo_cursor.isoformat()

    existente = read_advogado_cursor(conn, oab=oab, uf=uf)
    if existente is not None and novo_cursor < existente:
        logger.warning(
            "DJE: cursor do advogado %s/%s não regride — "
            "pedido novo=%s, existente=%s; ignorado",
            oab, uf, novo_iso, existente.isoformat(),
        )
        return False

    conn.execute(
        """
        INSERT INTO djen_advogado_state (
            numero_oab, uf_oab, ultimo_cursor, last_run
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(numero_oab, uf_oab) DO UPDATE SET
            ultimo_cursor = excluded.ultimo_cursor,
            last_run = excluded.last_run
        """,
        (oab, uf, novo_iso, ts_iso),
    )
    conn.commit()
    return True


def read_all_advogados_state(
    conn: sqlite3.Connection,
) -> dict[tuple[str, str], dict]:
    """Lê todos os advogados com state armazenado.

    Retorna dict com chave ``(oab, uf)`` e valor ``{ultimo_cursor:
    date|None, last_run: datetime|None}``. UI usa pra montar a aba
    "Status" do Excel e o banner final por advogado.
    """
    rows = conn.execute(
        "SELECT numero_oab, uf_oab, ultimo_cursor, last_run "
        "FROM djen_advogado_state",
    ).fetchall()
    out: dict[tuple[str, str], dict] = {}
    for row in rows:
        cursor = (
            date.fromisoformat(row["ultimo_cursor"])
            if row["ultimo_cursor"] else None
        )
        last_run = (
            datetime.fromisoformat(row["last_run"])
            if row["last_run"] else None
        )
        out[(row["numero_oab"], row["uf_oab"])] = {
            "ultimo_cursor": cursor,
            "last_run": last_run,
        }
    return out


def compute_advogado_window(
    conn: sqlite3.Connection,
    advogado: dict,
    *,
    data_fim: date | None = None,
) -> tuple[date, date]:
    """Calcula a janela ``(data_inicio, data_fim)`` de busca pra 1 advogado.

    - ``data_inicio = (cursor existente OU DEFAULT_CURSOR_VAZIO) + 1 dia``
    - ``data_fim`` default = hoje
    - Se ``data_inicio > data_fim`` (cursor já está no presente), clamp
      pra ``(data_fim, data_fim)`` — janela de 1 dia.

    Não há modal de "primeira execução": cursor vazio é só ``None`` e
    vira ``DEFAULT_CURSOR_VAZIO`` (= 2025-12-31), que faz a janela
    natural ser ``[2026-01-01, hoje]``.
    """
    cursor = read_advogado_cursor(
        conn, oab=advogado["oab"], uf=advogado["uf"],
    )
    base = cursor if cursor is not None else DEFAULT_CURSOR_VAZIO
    di = base + timedelta(days=1)
    df = data_fim if data_fim is not None else date.today()
    if di > df:
        di = df
    return di, df
