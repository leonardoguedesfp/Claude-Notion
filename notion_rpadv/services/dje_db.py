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
    captured_in_mode TEXT NOT NULL CHECK (captured_in_mode IN ('padrao', 'manual')),
    -- Pós-Fase 5 (2026-05-03) — integração Notion. Adicionadas via
    -- migração ALTER TABLE em ``_migrate_notion_columns_if_needed``
    -- pra bancos pré-Fase-5; aqui no DDL inicial já vêm pra DBs novos.
    notion_page_id TEXT,        -- NULL=pendente; UUID=enviado; "SKIPPED"=ignorado
    notion_attempts INTEGER NOT NULL DEFAULT 0,
    notion_last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_pub_data ON publicacoes(data_disponibilizacao);
CREATE INDEX IF NOT EXISTS idx_pub_processo ON publicacoes(numero_processo);
CREATE INDEX IF NOT EXISTS idx_pub_oabs_escritorio ON publicacoes(oabs_escritorio);
-- Índice parcial Pós-Fase 5 ``idx_publicacoes_notion_pending`` é criado em
-- ``_migrate_notion_columns_if_needed`` (depende da coluna notion_page_id
-- já existir, o que não é garantido aqui no DDL legado).

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

# Flag key: marca que o modal de "primeira carga Notion" (Fase 5,
# 2026-05-03) já foi exibido e tratado. Valores possíveis no
# ``app_flags.value``: ``"tudo_agora"``, ``"skipped_passado"``,
# ``"adiado"`` — refletem a escolha do usuário no modal.
FLAG_NOTION_PRIMEIRA_CARGA: str = "notion_primeira_carga_v1"

# Sentinela usado em ``publicacoes.notion_page_id`` pra publicações que
# o usuário escolheu ignorar na primeira carga (não enviar pro Notion).
NOTION_SKIPPED_SENTINEL: str = "SKIPPED"


# ---------------------------------------------------------------------------
# Path / connection / init
# ---------------------------------------------------------------------------


def get_db_path() -> Path:
    """``%APPDATA%/NotionRPADV/leitor_dje.db`` (mesma pasta de cache.db)."""
    return get_cache_dir() / DB_FILENAME


def init_db(conn: sqlite3.Connection) -> None:
    """Cria as 2 tabelas + índices se ainda não existirem (idempotente).

    Pragmas devem setados antes de chamar (feito por ``get_connection``).
    Função pública pra que o caller possa abrir conexão custom (e.g.
    teste com ``:memory:``) e ainda inicializar o schema.

    Pós-Fase 5 (2026-05-03): chama ``_migrate_notion_columns_if_needed``
    pra adicionar colunas Notion em bancos pré-Fase-5 (DDL inicial já
    cria pra DBs novos; ALTER TABLE cobre os legados).

    Round 1 (2026-05-03): chama ``_migrate_dedup_columns_if_needed``
    pra adicionar colunas/tabela de detecção de duplicatas (1.6).
    """
    conn.executescript(_SCHEMA_DDL)
    _migrate_notion_columns_if_needed(conn)
    _migrate_dedup_columns_if_needed(conn)
    conn.commit()


def _migrate_dedup_columns_if_needed(conn: sqlite3.Connection) -> None:
    """Adiciona colunas de detecção de duplicatas em ``publicacoes`` e
    cria a tabela ``dup_pendentes`` (Round 1, 1.6, 2026-05-03).

    - ``dup_chave``: SHA-256 hex da chave canônica (CNJ + data + tribunal +
      tipo_canonico + texto[:500]). NULL = não-deduplicada (CNJ ausente,
      D-2) OU ainda não computada.
    - ``dup_canonical_djen_id``: ``djen_id`` da publicação canônica (a 1ª
      do grupo enviada ao Notion). NULL = esta linha é a própria canônica
      (ou ainda não dedup'ada).
    - Índice parcial em ``dup_chave`` pra acelerar lookup de canônica
      por chave em batches grandes.
    - ``dup_pendentes``: tabela auxiliar pra acumular duplicatas que
      precisam ser flushadas no Notion (atualização da canônica) ao
      fim do batch.

    Idempotente — pode rodar em banco pré-Round-1 (adiciona) ou já
    migrado (no-op). Não altera dados.
    """
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(publicacoes)").fetchall()
    }
    if "dup_chave" not in cols:
        conn.execute(
            "ALTER TABLE publicacoes ADD COLUMN dup_chave TEXT"
        )
        logger.info("DJE: migração Round 1 — adicionada coluna dup_chave")
    if "dup_canonical_djen_id" not in cols:
        conn.execute(
            "ALTER TABLE publicacoes ADD COLUMN dup_canonical_djen_id INTEGER"
        )
        logger.info(
            "DJE: migração Round 1 — adicionada coluna dup_canonical_djen_id",
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publicacoes_dup_chave "
        "ON publicacoes(dup_chave) WHERE dup_chave IS NOT NULL"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dup_pendentes (
            canonical_djen_id INTEGER NOT NULL,
            duplicata_djen_id INTEGER NOT NULL,
            duplicata_destinatario TEXT,
            duplicata_partes_json TEXT,
            duplicata_advogados_json TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (canonical_djen_id, duplicata_djen_id)
        )
        """
    )


def _migrate_notion_columns_if_needed(conn: sqlite3.Connection) -> None:
    """Adiciona ``notion_page_id``, ``notion_attempts`` e
    ``notion_last_error`` à tabela ``publicacoes`` se ainda não estiverem
    presentes (banco pré-Fase-5).

    SQLite não tem ``ADD COLUMN IF NOT EXISTS``, então fazemos detect via
    ``PRAGMA table_info(publicacoes)`` e ALTER TABLE seletivo. Default
    das colunas casa com o DDL canônico em ``_SCHEMA_DDL`` (notion_page_id
    NULL, notion_attempts 0, notion_last_error NULL)."""
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(publicacoes)").fetchall()
    }
    if "notion_page_id" not in cols:
        conn.execute(
            "ALTER TABLE publicacoes ADD COLUMN notion_page_id TEXT"
        )
        logger.info("DJE: migração Fase 5 — adicionada coluna notion_page_id")
    if "notion_attempts" not in cols:
        conn.execute(
            "ALTER TABLE publicacoes ADD COLUMN notion_attempts "
            "INTEGER NOT NULL DEFAULT 0"
        )
        logger.info(
            "DJE: migração Fase 5 — adicionada coluna notion_attempts"
        )
    if "notion_last_error" not in cols:
        conn.execute(
            "ALTER TABLE publicacoes ADD COLUMN notion_last_error TEXT"
        )
        logger.info(
            "DJE: migração Fase 5 — adicionada coluna notion_last_error"
        )
    # Garante o índice parcial mesmo em DBs onde o ALTER TABLE só
    # acabou de criar a coluna (executescript anterior pode ter pulado
    # o CREATE INDEX se a coluna ainda não existia).
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publicacoes_notion_pending "
        "ON publicacoes(notion_page_id) WHERE notion_page_id IS NULL"
    )


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


# ---------------------------------------------------------------------------
# Sync Notion — Pós-Fase 5 (2026-05-03)
# ---------------------------------------------------------------------------


def count_publicacoes_pending_notion(conn: sqlite3.Connection) -> int:
    """Conta publicações com ``notion_page_id IS NULL`` E
    ``notion_attempts < 3`` — elegíveis pra envio no próximo ciclo."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM publicacoes "
        "WHERE notion_page_id IS NULL AND notion_attempts < 3"
    ).fetchone()
    return int(row["n"])


def count_publicacoes_failed_notion(conn: sqlite3.Connection) -> int:
    """Conta publicações ``presas`` (3+ falhas) — pra alerta no banner +
    botão "Tentar reenviar falhas"."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM publicacoes "
        "WHERE notion_page_id IS NULL AND notion_attempts >= 3"
    ).fetchone()
    return int(row["n"])


def count_publicacoes_sent_to_notion(conn: sqlite3.Connection) -> int:
    """Conta publicações já enviadas (``notion_page_id`` não-NULL e
    diferente do sentinela SKIPPED)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM publicacoes "
        "WHERE notion_page_id IS NOT NULL AND notion_page_id != ?",
        (NOTION_SKIPPED_SENTINEL,),
    ).fetchone()
    return int(row["n"])


def fetch_pending_for_notion(
    conn: sqlite3.Connection,
    *,
    include_failed: bool = False,
) -> list[dict[str, Any]]:
    """Retorna publicações pendentes pra envio Notion.

    Default: ``notion_page_id IS NULL AND notion_attempts < 3`` (não
    inclui as ``presas`` em 3+ falhas — caller pede via flag se quiser
    forçar reenvio).

    Ordem: ``data_disponibilizacao ASC, djen_id ASC`` — envia as mais
    antigas primeiro pra preservar ordem cronológica no Notion.

    Cada dict retornado tem o mesmo shape de ``fetch_all_publicacoes``
    (payload mesclado com ``advogados_consultados_escritorio`` e
    ``oabs_externas_consultadas``) acrescido de ``notion_attempts``.
    """
    where_clause = (
        "WHERE notion_page_id IS NULL"
        if include_failed
        else "WHERE notion_page_id IS NULL AND notion_attempts < 3"
    )
    rows = conn.execute(
        f"""
        SELECT djen_id, hash, oabs_escritorio, oabs_externas,
               numero_processo, data_disponibilizacao, sigla_tribunal,
               payload_json, captured_at, captured_in_mode,
               notion_page_id, notion_attempts, notion_last_error
        FROM publicacoes
        {where_clause}
        ORDER BY data_disponibilizacao ASC, djen_id ASC
        """,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        payload["advogados_consultados_escritorio"] = row["oabs_escritorio"]
        payload["oabs_externas_consultadas"] = row["oabs_externas"] or ""
        payload["notion_attempts"] = row["notion_attempts"]
        out.append(payload)
    return out


def mark_publicacao_sent_to_notion(
    conn: sqlite3.Connection,
    djen_id: int,
    notion_page_id: str,
) -> None:
    """Após sucesso na API: persiste o ``notion_page_id`` e limpa erros."""
    conn.execute(
        "UPDATE publicacoes SET notion_page_id = ?, notion_last_error = NULL "
        "WHERE djen_id = ?",
        (notion_page_id, djen_id),
    )
    conn.commit()


def mark_publicacao_notion_failure(
    conn: sqlite3.Connection,
    djen_id: int,
    error_msg: str,
) -> None:
    """Incrementa ``notion_attempts`` e grava ``notion_last_error``.
    ``notion_page_id`` permanece NULL (continua pendente)."""
    conn.execute(
        "UPDATE publicacoes SET "
        "notion_attempts = notion_attempts + 1, "
        "notion_last_error = ? "
        "WHERE djen_id = ?",
        (str(error_msg)[:500], djen_id),
    )
    conn.commit()


def mark_all_pending_notion_skipped(conn: sqlite3.Connection) -> int:
    """Marca todas as publicações pendentes (``notion_page_id IS NULL``)
    com ``notion_page_id = NOTION_SKIPPED_SENTINEL``. Usado pelo ramo
    "Só publicações novas a partir de hoje" do modal de primeira carga.

    Retorna número de linhas afetadas."""
    cur = conn.execute(
        "UPDATE publicacoes SET notion_page_id = ? "
        "WHERE notion_page_id IS NULL",
        (NOTION_SKIPPED_SENTINEL,),
    )
    conn.commit()
    affected = cur.rowcount
    logger.info(
        "DJE.notion: %d publicações marcadas SKIPPED na primeira carga",
        affected,
    )
    return affected


def reset_notion_failed_attempts(conn: sqlite3.Connection) -> int:
    """Zera ``notion_attempts`` e ``notion_last_error`` das publicações
    presas (3+ falhas). Usado pelo botão "Tentar reenviar falhas" da UI.

    Retorna número de linhas afetadas (= quantas voltam pra fila)."""
    cur = conn.execute(
        "UPDATE publicacoes SET "
        "notion_attempts = 0, notion_last_error = NULL "
        "WHERE notion_page_id IS NULL AND notion_attempts >= 3"
    )
    conn.commit()
    affected = cur.rowcount
    logger.info(
        "DJE.notion: %d publicações tiveram attempts zerados (retry manual)",
        affected,
    )
    return affected


def count_sequencial_titulo(
    conn: sqlite3.Connection,
    sigla_tribunal: str,
    data_disponibilizacao: str,
) -> int:
    """Calcula o sequencial N pro título do Notion: conta quantas
    publicações já foram enviadas (``notion_page_id`` não-NULL e !=
    SKIPPED) na mesma combinação ``(siglaTribunal, data_disponibilizacao)``,
    e retorna count + 1.

    Single-threaded → sem race conditions. Caller chama no momento de
    montar o payload, antes da requisição."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM publicacoes "
        "WHERE sigla_tribunal = ? AND data_disponibilizacao = ? "
        "AND notion_page_id IS NOT NULL AND notion_page_id != ?",
        (sigla_tribunal, data_disponibilizacao, NOTION_SKIPPED_SENTINEL),
    ).fetchone()
    return int(row["n"]) + 1


# ---------------------------------------------------------------------------
# Detecção de duplicatas — Round 1 (2026-05-03)
# ---------------------------------------------------------------------------


def find_canonical_by_chave(
    conn: sqlite3.Connection,
    chave: str,
) -> dict[str, Any] | None:
    """Retorna a publicação canônica (a 1ª do grupo já enviada ao Notion)
    cuja ``dup_chave`` bate com ``chave``. ``None`` se nenhuma encontrada.

    Critério canônica = ``dup_chave = ?`` AND ``notion_page_id`` não-NULL e
    diferente do sentinela SKIPPED AND ``dup_canonical_djen_id`` IS NULL
    (a própria não é duplicata de outra). Ordem: ``data_disponibilizacao
    ASC, djen_id ASC`` — primeira na cronologia.

    Output: ``{djen_id, notion_page_id, data_disponibilizacao, ...}`` (row
    completa do publicacoes).
    """
    row = conn.execute(
        """
        SELECT djen_id, hash, oabs_escritorio, oabs_externas,
               numero_processo, data_disponibilizacao, sigla_tribunal,
               payload_json, captured_at, captured_in_mode,
               notion_page_id, notion_attempts, notion_last_error,
               dup_chave, dup_canonical_djen_id
        FROM publicacoes
        WHERE dup_chave = ?
          AND notion_page_id IS NOT NULL
          AND notion_page_id != ?
          AND dup_canonical_djen_id IS NULL
        ORDER BY data_disponibilizacao ASC, djen_id ASC
        LIMIT 1
        """,
        (chave, NOTION_SKIPPED_SENTINEL),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def mark_publicacao_dup_chave(
    conn: sqlite3.Connection,
    djen_id: int,
    chave: str,
) -> None:
    """Persiste ``dup_chave`` numa publicação canônica (1ª do grupo) APÓS
    sucesso no envio ao Notion. Necessário pra que duplicatas posteriores
    consigam achar a canônica em ``find_canonical_by_chave``."""
    conn.execute(
        "UPDATE publicacoes SET dup_chave = ? WHERE djen_id = ?",
        (chave, djen_id),
    )
    conn.commit()


def mark_publicacao_as_duplicate(
    conn: sqlite3.Connection,
    *,
    duplicata_djen_id: int,
    canonical_djen_id: int,
    canonical_notion_page_id: str,
    chave: str,
) -> None:
    """Marca uma publicação como duplicata da canônica.

    Atualizações:
    - ``dup_chave`` = chave (mesma da canônica).
    - ``dup_canonical_djen_id`` = djen_id da canônica.
    - ``notion_page_id`` = page_id da canônica (compartilha página).
    - ``notion_last_error`` = NULL (não houve falha — foi suprimida
      legitimamente).

    Não toca em ``notion_attempts`` (mantém histórico).
    """
    conn.execute(
        """
        UPDATE publicacoes
        SET dup_chave = ?,
            dup_canonical_djen_id = ?,
            notion_page_id = ?,
            notion_last_error = NULL
        WHERE djen_id = ?
        """,
        (chave, canonical_djen_id, canonical_notion_page_id, duplicata_djen_id),
    )
    conn.commit()


def insert_dup_pendente(
    conn: sqlite3.Connection,
    *,
    canonical_djen_id: int,
    duplicata_djen_id: int,
    duplicata_destinatario: str,
    duplicata_partes_json: str,
    duplicata_advogados_json: str,
) -> None:
    """Insere uma linha em ``dup_pendentes`` — usada pelo flush no fim
    do batch pra atualizar a canônica no Notion (Partes, Advogados
    intimados, Duplicatas suprimidas).

    Idempotente: PK ``(canonical_djen_id, duplicata_djen_id)`` evita
    duplicação de pendentes; ``ON CONFLICT DO NOTHING``.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    conn.execute(
        """
        INSERT INTO dup_pendentes (
            canonical_djen_id, duplicata_djen_id,
            duplicata_destinatario, duplicata_partes_json,
            duplicata_advogados_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (canonical_djen_id, duplicata_djen_id) DO NOTHING
        """,
        (
            canonical_djen_id, duplicata_djen_id,
            duplicata_destinatario, duplicata_partes_json,
            duplicata_advogados_json, ts,
        ),
    )
    conn.commit()


def fetch_canonicas_com_pendentes(conn: sqlite3.Connection) -> list[int]:
    """Lista de ``djen_id`` das canônicas que têm pelo menos 1 pendente
    em ``dup_pendentes``. Output ordenado por djen_id ASC pra
    determinismo nos testes/logs."""
    rows = conn.execute(
        "SELECT DISTINCT canonical_djen_id FROM dup_pendentes "
        "ORDER BY canonical_djen_id ASC"
    ).fetchall()
    return [int(r["canonical_djen_id"]) for r in rows]


def fetch_dup_pendentes_for_canonical(
    conn: sqlite3.Connection,
    canonical_djen_id: int,
) -> list[dict[str, Any]]:
    """Carrega todas as linhas de ``dup_pendentes`` para uma canônica,
    ordenadas por ``duplicata_djen_id ASC`` (cronologia estável)."""
    rows = conn.execute(
        """
        SELECT canonical_djen_id, duplicata_djen_id,
               duplicata_destinatario, duplicata_partes_json,
               duplicata_advogados_json, created_at
        FROM dup_pendentes
        WHERE canonical_djen_id = ?
        ORDER BY duplicata_djen_id ASC
        """,
        (canonical_djen_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_dup_pendentes_for_canonical(
    conn: sqlite3.Connection,
    canonical_djen_id: int,
) -> int:
    """Apaga pendentes de uma canônica após flush bem-sucedido (ou
    quando a canônica deletada — D-8). Retorna número de linhas
    afetadas."""
    cur = conn.execute(
        "DELETE FROM dup_pendentes WHERE canonical_djen_id = ?",
        (canonical_djen_id,),
    )
    conn.commit()
    return cur.rowcount


def count_dup_pendentes(conn: sqlite3.Connection) -> int:
    """Total de linhas em ``dup_pendentes`` (todas as canônicas).
    Usado pelo banner pós-sync."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM dup_pendentes"
    ).fetchone()
    return int(row["n"])


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
