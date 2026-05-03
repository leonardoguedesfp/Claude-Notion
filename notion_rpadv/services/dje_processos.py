"""Lista os CNJs (números de processo) da base "Processos" do Notion.

Pós-Fase 3 (2026-05-02): origem do **eixo CNJ** do Leitor DJE — cada CNJ
é consultado individualmente na API DJEN com o mesmo intervalo de datas,
gerando uma busca **paralela** ao eixo OAB tradicional.

Origem dos dados: cache local em ``cache.db`` da base "Processos" (já
populado pelo ``SyncManager`` quando o usuário usa qualquer outra tela
do app). Não fazemos chamada direta à API Notion aqui — uso do cache é
o pattern existente em ``base_table_model``, ``processos.py``, etc.

Schema do record (cache de Processos): ``record["numero_do_processo"]``
contém o CNJ no formato "0000000-00.0000.0.00.0000" (string title
decodificada via ``encoders.decode_value`` em sync time).
"""
from __future__ import annotations

import logging
import re
import sqlite3

from notion_rpadv.cache import db as cache_db

logger = logging.getLogger("dje.processos")

# Limite saudável pra evitar varreduras absurdas — ainda dá margem larga
# pra crescimento natural da base. Se ultrapassar, log warning e segue
# (não trunca).
MAX_CNJS_LOG_THRESHOLD: int = 5000

# Máscara CNJ esperada: 7 dígitos + "-" + 2 dígitos + "." + 4 dígitos +
# "." + 1 dígito + "." + 2 dígitos + "." + 4 dígitos. Ex: 0000000-00.0000.0.00.0000.
_CNJ_MASCARADO_RE = re.compile(
    r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$"
)


def _normaliza_cnj(raw: str) -> str | None:
    """Aceita CNJ com máscara (passa direto), sem máscara (20 dígitos
    puros, vira mascarado) ou string vazia/None (descarta).

    Retorna o CNJ canônico (com máscara) ou ``None`` se inválido.
    """
    s = (raw or "").strip()
    if not s:
        return None
    if _CNJ_MASCARADO_RE.match(s):
        return s
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 20:
        return (
            f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}."
            f"{digits[13]}.{digits[14:16]}.{digits[16:20]}"
        )
    # Numeração pré-CNJ ou string fora de padrão — não conseguimos consultar
    # via DJEN (que exige CNJ) e descartamos com log debug.
    logger.debug("DJE.processos: CNJ ignorado (formato fora de padrão): %r", s)
    return None


def listar_cnjs_do_escritorio(cache_conn: sqlite3.Connection) -> list[str]:
    """Lê todos os processos cacheados localmente e retorna lista
    deduplicada e ordenada de CNJs com máscara.

    Records sem ``numero_do_processo`` ou com numeração pré-CNJ são
    silenciosamente descartados — só CNJs válidos no formato moderno
    podem ser consultados na API DJEN.

    Cache vazio → lista vazia (caller deve avisar usuário pra sincronizar
    a base de Processos primeiro).
    """
    records = cache_db.get_all_records(cache_conn, "Processos")
    cnjs: set[str] = set()
    for r in records:
        canon = _normaliza_cnj(str(r.get("numero_do_processo") or ""))
        if canon is not None:
            cnjs.add(canon)
    out = sorted(cnjs)
    if len(out) > MAX_CNJS_LOG_THRESHOLD:
        logger.warning(
            "DJE.processos: lista de CNJs grande (%d > %d). Verifique se "
            "o cache de Processos está saudável.",
            len(out), MAX_CNJS_LOG_THRESHOLD,
        )
    logger.info("DJE.processos: %d CNJs únicos no cache local.", len(out))
    return out
