"""SQLite local pro cache incremental do Leitor DJE (Fase 3).

Schema:
- ``djen_state``: 1 linha singleton com ``(ultimo_cursor, last_run)``.
  Watermark único representa "última publicação captada pra QUALQUER
  advogado do escritório". Não é por OAB nem por tribunal.
- ``publicacoes``: todas as publicações já captadas. ``djen_id`` é a
  chave primária; ``hash`` é UNIQUE (defesa contra inconsistência DJEN).

Pragmas: WAL, foreign_keys ON, synchronous=NORMAL.

Datas/timestamps: SQLite não tem tipo nativo — armazenamos ISO-8601:
- Datas: ``YYYY-MM-DD``
- Timestamps: ``YYYY-MM-DDTHH:MM:SS`` (UTC, naive)

Localização: ``%APPDATA%/NotionRPADV/leitor_dje.db`` (mesma pasta de
``cache.db`` e ``audit.db``, via ``get_cache_dir()`` de
``notion_bulk_edit.config``). Em Linux/Mac, ``~/.notionrpadv/``.

Conexão lazy: criada na primeira chamada de ``get_connection()``. Init
é idempotente (``CREATE TABLE IF NOT EXISTS``); banco existente não é
derrubado.

Sobre os campos ``oabs_escritorio``/``oabs_externas``: armazenam labels
no formato ``"Nome Completo (OAB/UF); Nome Completo (OAB/UF); ..."`` —
mesma forma usada no Excel-de-execução. Decisão deliberada divergindo do
spec literal (que sugeriu ``"OAB/UF"`` puro): preserva o nome dos
advogados externos digitados pelo usuário no modo manual, que
seriam perdidos quando o histórico é regerado a partir do SQLite.
Ordenação: alfabética por label (mesmo critério do legado
``_collapse_advogados``, validado pelos testes da Fase 2).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from notion_bulk_edit.config import get_cache_dir

logger = logging.getLogger("dje.db")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DB_FILENAME: str = "leitor_dje.db"

CAPTURE_MODE_PADRAO: str = "padrao"
CAPTURE_MODE_MANUAL: str = "manual"

_VALID_MODES: frozenset[str] = frozenset(
    {CAPTURE_MODE_PADRAO, CAPTURE_MODE_MANUAL},
)


_SCHEMA_DDL: str = """
-- Tabela legada (Fase 3 original) — mantida no schema só pra detecção
-- de migração. Após migração executada (clear_legacy_state), fica vazia
-- e não é mais usada. Será dropada num refresh futuro de schema.
CREATE TABLE IF NOT EXISTS djen_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ultimo_cursor TEXT NOT NULL,
    last_run TEXT NOT NULL
);

-- Watermark POR ADVOGADO (refator pós-Fase 3 hotfix watermark integrity).
-- Cada advogado oficial do escritório tem seu próprio cursor; cada
-- execução de "Baixar publicações novas" calcula janela individual
-- ``[ultimo_cursor + 1d, hoje]``. Falha de um advogado não afeta os
-- outros.
CREATE TABLE IF NOT EXISTS djen_advogado_state (
    numero_oab TEXT NOT NULL,
    uf_oab TEXT NOT NULL,
    ultimo_cursor TEXT,            -- ISO date YYYY-MM-DD; NULL = nunca executou
    last_run TEXT,                 -- ISO datetime; NULL = nunca executou
    PRIMARY KEY (numero_oab, uf_oab)
);

CREATE TABLE IF NOT EXISTS publicacoes (
    djen_id INTEGER PRIMARY KEY,
    hash TEXT UNIQUE NOT NULL,
    oabs_escritorio TEXT NOT NULL,
    oabs_externas TEXT,
    numero_processo TEXT,
    data_disponibilizacao TEXT NOT NULL,
    sigla_tribunal TEXT,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    captured_in_mode TEXT NOT NULL CHECK (captured_in_mode IN ('padrao', 'manual'))
);

CREATE INDEX IF NOT EXISTS idx_pub_data ON publicacoes(data_disponibilizacao);
CREATE INDEX IF NOT EXISTS idx_pub_processo ON publicacoes(numero_processo);
CREATE INDEX IF NOT EXISTS idx_pub_oabs_escritorio ON publicacoes(oabs_escritorio);

-- Pós-Fase 3 (2026-05-02): flags arbitrárias one-shot pra eventos
-- operacionais que não pertencem a um schema mais estruturado.
-- Caso de uso inicial: marcar que o modal de "reativação dos 4
-- advogados de 2026-05-02" já foi tratado nesta máquina (sim ou não),
-- pra não recorrer toda execução. Chave estável → valor texto livre.
CREATE TABLE IF NOT EXISTS app_flags (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    set_at TEXT NOT NULL
);
"""

# Flag key: marca que o modal de reativação dos 4 advogados de
# 2026-05-02 já foi tratado (independentemente da resposta do usuário).
# Bumpe esta string se for preciso re-mostrar o modal (improvável).
FLAG_REATIVACAO_2026_05_02: str = "reativacao_4_advogados_2026_05_02_treated"


# ---------------------------------------------------------------------------
# Path / connection / init
# ---------------------------------------------------------------------------


def get_db_path() -> Path:
    """``%APPDATA%/NotionRPADV/leitor_dje.db`` (mesma pasta de cache.db)."""
    return get_cache_dir() / DB_FILENAME


def init_db(conn: sqlite3.Connection) -> None:
    """Cria as 2 tabelas + índices se ainda não existirem (idempotente).

    Pragmas devem estar setados antes de chamar (feito por
    ``get_connection``). Função pública pra que o caller possa abrir
    conexão custom (e.g. teste com ``:memory:``) e ainda inicializar
    o schema.
    """
    conn.executescript(_SCHEMA_DDL)
    conn.commit()


def get_connection(path: Path | None = None) -> sqlite3.Connection:
    """Abre conexão SQLite com pragmas e schema iniciados (lazy).

    ``path`` opcional pra teste/CI; default é ``get_db_path()``.

    ``check_same_thread=False`` pra suportar UI Qt + worker thread
    compartilhando a mesma conexão (mesma escolha de cache.db/audit.db).
    Caller deve garantir serialização de escritas (i.e. 1 worker por vez).
    """
    resolved = path if path is not None else get_db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    init_db(conn)
    return conn


# ---------------------------------------------------------------------------
# CRUD: publicacoes
# ---------------------------------------------------------------------------


def insert_publicacao(
    conn: sqlite3.Connection,
    *,
    djen_id: int,
    hash_: str,
    oabs_escritorio: str,
    oabs_externas: str,
    numero_processo: str | None,
    data_disponibilizacao: str,
    sigla_tribunal: str | None,
    payload: dict[str, Any],
    mode: str,
    captured_at: str | None = None,
) -> bool:
    """Insere 1 publicação. Retorna ``True`` se inseriu, ``False`` se
    ``djen_id`` já existia (``ON CONFLICT(djen_id) DO NOTHING``).

    Importante: ``ON CONFLICT(djen_id)`` é seletivo — só ignora colisão
    na PK. Colisão UNIQUE em ``hash`` (caso teórico: 2 publicações com
    hash igual mas ``djen_id`` distinto, anomalia DJEN) AINDA levanta
    ``IntegrityError`` — não silenciamos. Diferença vs ``INSERT OR IGNORE``
    que ignoraria os 2 tipos de conflito.

    ``captured_at`` opcional pra teste (default: now UTC).
    ``payload`` é serializado com ``ensure_ascii=False`` pra preservar
    acentos.
    """
    if mode not in _VALID_MODES:
        raise ValueError(
            f"mode inválido: {mode!r} (esperado: 'padrao' ou 'manual')",
        )
    ts = captured_at or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S",
    )
    cur = conn.execute(
        """
        INSERT INTO publicacoes (
            djen_id, hash, oabs_escritorio, oabs_externas,
            numero_processo, data_disponibilizacao, sigla_tribunal,
            payload_json, captured_at, captured_in_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(djen_id) DO NOTHING
        """,
        (
            djen_id, hash_, oabs_escritorio, oabs_externas or "",
            numero_processo, data_disponibilizacao, sigla_tribunal,
            json.dumps(payload, ensure_ascii=False), ts, mode,
        ),
    )
    return cur.rowcount > 0


def fetch_all_publicacoes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Retorna todas as publicações ordenadas por
    ``data_disponibilizacao DESC, sigla_tribunal ASC``.

    Cada dict é o payload JSON original mesclado com os 2 campos derivados
    que vivem no SQLite:
    - ``advogados_consultados_escritorio`` (do campo ``oabs_escritorio``)
    - ``oabs_externas_consultadas`` (do campo ``oabs_externas``)

    Pronto pra alimentar o transform/exporter do histórico completo
    (não precisa re-rodar dedup, pois cada row já é uma publicação única).
    """
    rows = conn.execute(
        """
        SELECT djen_id, hash, oabs_escritorio, oabs_externas,
               numero_processo, data_disponibilizacao, sigla_tribunal,
               payload_json, captured_at, captured_in_mode
        FROM publicacoes
        ORDER BY data_disponibilizacao DESC, sigla_tribunal ASC
        """,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        payload["advogados_consultados_escritorio"] = row["oabs_escritorio"]
        payload["oabs_externas_consultadas"] = row["oabs_externas"] or ""
        out.append(payload)
    return out


def count_publicacoes(conn: sqlite3.Connection) -> int:
    """Total de linhas em ``publicacoes`` — usado pra detectar 'banco
    vazio' antes de gerar histórico (regra F3-37)."""
    row = conn.execute("SELECT COUNT(*) AS n FROM publicacoes").fetchone()
    return int(row["n"])


def max_data_disponibilizacao(conn: sqlite3.Connection):
    """Retorna a maior ``data_disponibilizacao`` da tabela ``publicacoes``
    como ``date``, ou ``None`` se a tabela está vazia.

    Hotfix watermark integrity: usado pelo modo padrão como fallback
    quando ``djen_state.ultimo_cursor`` está vazio MAS o banco já tem
    publicações captadas via "Baixar período selecionado" ou modo
    manual (que não tocam o cursor). Sem esse fallback, o app abre
    modal de "primeira execução" mesmo com milhares de publicações
    no SQLite.
    """
    from datetime import date as _date  # lazy: evita escopo global

    row = conn.execute(
        "SELECT MAX(data_disponibilizacao) AS m FROM publicacoes",
    ).fetchone()
    if row is None or row["m"] is None:
        return None
    # SQLite ocasionalmente devolve bytes em colunas TEXT quando há
    # afinidade ambígua — coerce explícita pra str pra não estourar
    # ``fromisoformat``.
    raw = row["m"]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return _date.fromisoformat(str(raw))


def is_legacy_state_present(conn: sqlite3.Connection) -> bool:
    """Detecta se o banco está no schema legado (Fase 3 original):
    ``djen_state`` populada (1 linha) E ``djen_advogado_state`` vazia.

    Trigger de migração — UI mostra modal de aviso + chama
    ``clear_legacy_state_and_publicacoes`` ao confirmar.
    """
    legacy_count = conn.execute(
        "SELECT COUNT(*) AS n FROM djen_state"
    ).fetchone()["n"]
    new_count = conn.execute(
        "SELECT COUNT(*) AS n FROM djen_advogado_state"
    ).fetchone()["n"]
    return legacy_count > 0 and new_count == 0


def clear_legacy_state_and_publicacoes(conn: sqlite3.Connection) -> None:
    """Reset honesto da migração pós-Fase 3.

    Decisão (spec do refator): cursor único legado pode estar contaminado
    (avançou pra data_fim mesmo com falhas reais). Pra evitar gaps
    permanentes nos dados dos advogados que falharam, reconstruímos a
    base do zero.

    Apaga: ``djen_state`` (linha do cursor antigo) + ``publicacoes``
    inteira. NÃO toca em ``djen_advogado_state`` (que estará vazia, e
    a próxima execução de "Baixar publicações novas" vai popular
    naturalmente).

    Caller (UI) deve avisar o usuário ANTES e confirmar a perda de dados.
    """
    conn.execute("DELETE FROM djen_state")
    conn.execute("DELETE FROM publicacoes")
    conn.commit()
    logger.info(
        "DJE: migração legada executada — djen_state e publicacoes zeradas",
    )


# ---------------------------------------------------------------------------
# Flags arbitrárias (one-shot)
# ---------------------------------------------------------------------------


def read_flag(conn: sqlite3.Connection, key: str) -> str | None:
    """Lê o valor de uma flag em ``app_flags``. ``None`` se não existe."""
    row = conn.execute(
        "SELECT value FROM app_flags WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    return str(row["value"])


def set_flag(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert numa flag de ``app_flags``. ``value`` é texto livre."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    conn.execute(
        """
        INSERT INTO app_flags (key, value, set_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            set_at = excluded.set_at
        """,
        (key, value, ts),
    )
    conn.commit()


def fetch_publicacoes_by_ids(
    conn: sqlite3.Connection,
    djen_ids: list[int],
) -> list[dict[str, Any]]:
    """Retorna o subset de publicações cujo ``djen_id`` está na lista.

    Ordem do retorno: mesma de ``fetch_all_publicacoes``
    (``data_disponibilizacao DESC, sigla_tribunal ASC``). Útil pro
    Excel-de-execução, que precisa só dos ids efetivamente inseridos
    nesta varredura.

    Lista vazia → retorna lista vazia (sem query). SQLite tem limite
    de variáveis por consulta (default 999); pra listas maiores,
    chunking seria necessário, mas o caso real do escritório (varredura
    diária) raramente passa de centenas.
    """
    if not djen_ids:
        return []
    placeholders = ",".join("?" for _ in djen_ids)
    rows = conn.execute(
        f"""
        SELECT djen_id, hash, oabs_escritorio, oabs_externas,
               numero_processo, data_disponibilizacao, sigla_tribunal,
               payload_json, captured_at, captured_in_mode
        FROM publicacoes
        WHERE djen_id IN ({placeholders})
        ORDER BY data_disponibilizacao DESC, sigla_tribunal ASC
        """,
        djen_ids,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        payload["advogados_consultados_escritorio"] = row["oabs_escritorio"]
        payload["oabs_externas_consultadas"] = row["oabs_externas"] or ""
        out.append(payload)
    return out
