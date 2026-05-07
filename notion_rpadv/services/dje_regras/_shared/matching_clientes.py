"""Matching tolerante de cliente cadastrado contra Pub.Partes — usado
por AC04, AC05, AC06.

4 estratégias combinadas (acumulam OR):

1. **Direto**: nomes normalizados idênticos.
2. **Substring**: cadastro inteiro contido na parte da pub.
3. **Iniciais**: cadastro vira ``"M.S."`` e bate com partes em
   formato de iniciais (sigilo de justiça).
4. **Subset de tokens**: tokens com ≥3 letras de um lado contidos no
   outro (cobre nome composto incompleto).

Round 9 (2026-05-07): introduzidas as 4 estratégias pra cobrir as
4 categorias de FP (apóstrofo, cedilha/acento, iniciais, sufixo
faltando).
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

#: Sentinela em ``Cliente.nome`` que NÃO deve participar do matching.
_CLIENTE_TEMPLATE_MARKER: str = "🧱 MODELO"


def carregar_indice_clientes(cache_conn: Any) -> dict[str, str]:
    """Lê base ``Clientes`` do cache.db e devolve dict
    ``{page_id: nome_uppercase}`` para matching.

    Pula o template ``"🧱 Modelo — usar como template"``. Devolve dict
    vazio se ``cache_conn`` for ``None``.
    """
    if cache_conn is None:
        return {}
    indice: dict[str, str] = {}
    cur = cache_conn.execute(
        "SELECT page_id, data_json FROM records WHERE base = ?",
        ("Clientes",),
    )
    for row in cur:
        try:
            data = json.loads(row["data_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        nome = (data.get("nome") or "").strip()
        if not nome:
            continue
        nome_up = nome.upper()
        if _CLIENTE_TEMPLATE_MARKER in nome_up:
            continue
        indice[str(row["page_id"])] = nome_up
    return indice


def destinatarios_por_polo(publicacao: dict[str, Any]) -> dict[str, list[str]]:
    """Agrupa ``publicacao["destinatarios"]`` por polo, devolvendo
    ``{polo: [nome_uppercase, ...]}``. Polos canônicos: ``A``, ``P``,
    ``T``."""
    out: dict[str, list[str]] = {}
    destinatarios = publicacao.get("destinatarios") or []
    for d in destinatarios:
        if not isinstance(d, dict):
            continue
        nome = str(d.get("nome") or "").strip().upper()
        if not nome:
            continue
        polo = str(d.get("polo") or "").strip().upper() or "?"
        out.setdefault(polo, []).append(nome)
    return out


def _normalizar_nome_pessoa(s: str) -> str:
    """Normaliza nome de pessoa pra comparação tolerante.

    Remove acentos/cedilha (NFKD + ASCII), uppercase, troca apóstrofos
    por espaço, mantém só letras/espaços/pontos, colapsa espaços.
    """
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.upper()
    s = re.sub(r"[''`´]", " ", s)
    s = re.sub(r"[^A-Z\s.]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokens_significativos(s: str) -> set[str]:
    """Tokens (palavras com ≥3 letras) de um nome normalizado.
    Stopwords curtas (DA, DE, DO, DOS, DAS, E) são filtradas implicit-
    amente.
    """
    return {t for t in s.split() if len(t) >= 3 and "." not in t}


def eh_match_cliente(cadastro: str, parte_pub: str) -> bool:
    """Match tolerante de cliente cadastrado contra parte da pub.

    Aceita 4 formas de match (descritas no docstring do módulo).
    """
    a = _normalizar_nome_pessoa(cadastro)
    b = _normalizar_nome_pessoa(parte_pub)
    if not a or not b:
        return False
    # 1. Direto
    if a == b:
        return True
    # 2/4. Substring
    if a in b:
        return True
    # 3. Iniciais (sigilo de justiça)
    iniciais_a = ".".join(t[0] for t in a.split() if t) + "."
    if iniciais_a == b.replace(" ", ""):
        return True
    # 4. Subset de tokens
    ta = _tokens_significativos(a)
    tb = _tokens_significativos(b)
    if ta and tb and (ta.issubset(tb) or tb.issubset(ta)):
        return True
    return False


def matching_clientes_em_pub(
    publicacao: dict[str, Any],
    indice_clientes: dict[str, str],
) -> dict[str, set[str]]:
    """Para cada polo da Pub, identifica quais clientes cadastrados
    aparecem. Devolve ``{polo: {page_id_cliente, ...}}``.
    """
    if not indice_clientes:
        return {}
    polos = destinatarios_por_polo(publicacao)
    out: dict[str, set[str]] = {}
    for polo, nomes_pub in polos.items():
        if not nomes_pub:
            continue
        encontrados: set[str] = set()
        for page_id, nome_cliente in indice_clientes.items():
            if not nome_cliente or len(nome_cliente) < 8:
                # Nomes muito curtos podem dar match falso — pula
                continue
            for nome_pub in nomes_pub:
                if eh_match_cliente(nome_cliente, nome_pub):
                    encontrados.add(page_id)
                    break
        if encontrados:
            out[polo] = encontrados
    return out
