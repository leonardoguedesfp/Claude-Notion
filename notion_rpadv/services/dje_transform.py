"""Round 7 Fase 2 — refino do snapshot DJEN antes de escrever no xlsx.

Funções puras (sem Qt, sem I/O, sem rede) que transformam a saída crua
do ``dje_client`` no formato consumível final:

1. **Dedup por id**: a Fase 1 emitia 1 linha por advogado-do-escritório
   intimado, gerando inflação ~5× quando há litisconsórcio interno
   (773 linhas pra 156 publicações reais no sample 27/04→30/04).
   Aqui colapsa pra 1 linha por publicação, agregando os advogados em
   ``advogados_consultados`` (plural, separados por "; ", ordem alfabética).

2. **Coluna ``observacoes``**: sinaliza anomalias que antes precisavam
   de inspeção visual de 6 colunas constantes-mas-eventualmente-variantes
   (``ativo``, ``status``, ``meio``, ``meiocompleto``,
   ``motivo_cancelamento``, ``data_cancelamento``) e detecta ausência
   dos sócios fundadores (Ricardo + Leonardo) em ``destinatarioadvogados``.

3. **Strip de HTML do ``texto``**: 84% dos textos vêm com markup
   (``<br>``, ``<a>``, tabelas inteiras em STJ/TST). Helper
   ``strip_html`` normaliza pra texto puro com quebras de linha.

4. **Normalização de encoding misto**: bug upstream do DJEN aplica
   ``.upper()`` em string Latin-1 antes do encoding UTF-8, deixando
   acentos minúsculos no meio de all-caps (``"PROVISóRIO"``). Aplicada
   apenas em ``nomeOrgao``/``nomeClasse``/``tipoDocumento`` quando ≥70%
   das letras estão maiúsculas.

5. **Schema canônico F2** (``CANONICAL_COLUMNS``): 20 colunas em ordem
   fixa. Trava o contrato — F1 era schema-agnóstico (auto-derivado do
   1º item), F2 é editorial.

6. **Ordenação final**: ``siglaTribunal`` ASC + ``data_disponibilizacao`` DESC.

Após o transform, as 6 colunas redundantes (`ativo`, `status`, `meio`,
`meiocompleto`, `motivo_cancelamento`, `data_cancelamento`) **são
removidas** do output — qualquer anomalia delas já está em
``observacoes``.

7. **Sanitização Unicode (Fase 2.1)**: ``sanitize_for_xlsx`` remove
   caracteres de controle Unicode (incluindo o bloco "Control Pictures"
   U+2400–U+243F) que o openpyxl recusa com ``IllegalCharacterError``.
   Caso real do smoke 01/01→30/04/2026: AREsp 2427258/DF (STJ) trazia
   U+2426 SYMBOL FOR SUBSTITUTE FORM TWO no campo ``texto``, derrubando
   o exporter inteiro. Aplicada em todos os campos string da linha.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any, Final

logger = logging.getLogger("dje.transform")


# ---------------------------------------------------------------------------
# Schema canônico (Fase 2)
# ---------------------------------------------------------------------------


# Ordem editorial das 20 colunas no xlsx final. Fonte única do contrato.
# Bumpe esta lista conjuntamente com testes que assertam a ordem.
CANONICAL_COLUMNS: Final[list[str]] = [
    "advogados_consultados",
    "observacoes",
    "id",
    "hash",
    "siglaTribunal",
    "data_disponibilizacao",
    "numeroprocessocommascara",
    "numero_processo",
    "tipoComunicacao",
    "tipoDocumento",
    "nomeOrgao",
    "idOrgao",
    "nomeClasse",
    "codigoClasse",
    "numeroComunicacao",
    "texto",
    "link",
    "destinatarios",
    "destinatarioadvogados",
    "datadisponibilizacao",
]

# Colunas removidas do output F2 (cobertas pela ``observacoes``).
DROPPED_COLUMNS: Final[frozenset[str]] = frozenset({
    "ativo",
    "status",
    "meio",
    "meiocompleto",
    "motivo_cancelamento",
    "data_cancelamento",
})

# Sócios fundadores cuja ausência em destinatarioadvogados gera obs.
# Critério literal: oab + uf_oab. Homônimo em outra seccional não conta.
RICARDO_OAB: Final[str] = "15523"
LEONARDO_OAB: Final[str] = "36129"
SOCIOS_UF: Final[str] = "DF"

# Defaults dos campos da Regra A. Divergência → mensagem em observacoes.
_REGRA_A_DEFAULTS: Final[dict[str, Any]] = {
    "ativo":       True,
    "status":      "P",
    "meio":        "D",
    "meiocompleto": "Diário de Justiça Eletrônico Nacional",
}


# ---------------------------------------------------------------------------
# Helpers de texto (públicos pra teste isolado)
# ---------------------------------------------------------------------------


# Acentuadas minúsculas → maiúsculas correspondentes. Bug DJEN: .upper()
# em string Latin-1 antes do re-encoding UTF-8 escapa essas letras.
ACENTUADAS_MIN_PARA_MAIUS: Final[dict[str, str]] = {
    "á": "Á", "à": "À", "ã": "Ã", "â": "Â", "ä": "Ä",
    "é": "É", "è": "È", "ê": "Ê", "ë": "Ë",
    "í": "Í", "ì": "Ì", "î": "Î", "ï": "Ï",
    "ó": "Ó", "ò": "Ò", "õ": "Õ", "ô": "Ô", "ö": "Ö",
    "ú": "Ú", "ù": "Ù", "û": "Û", "ü": "Ü",
    "ç": "Ç", "ñ": "Ñ",
}

# Threshold pra detectar all-caps "contaminado" pelo bug DJEN.
_UPPERCASE_RATIO_THRESHOLD: Final[float] = 0.70

# Campos onde a normalização de encoding misto se aplica. ``texto`` NÃO
# entra — o corpo da publicação tem misturas legítimas de caso.
_NORMALIZE_ENCODING_FIELDS: Final[tuple[str, ...]] = (
    "nomeOrgao", "nomeClasse", "tipoDocumento",
)


# ---------------------------------------------------------------------------
# Sanitização Unicode (Fase 2.1)
# ---------------------------------------------------------------------------


# Caracteres de controle Unicode que openpyxl recusa.
# Inclui controle ASCII (0x00-0x1F exceto \t \n \r) e o bloco "Control
# Pictures" (U+2400–U+243F). U+2426 SYMBOL FOR SUBSTITUTE FORM TWO foi
# o caractere encontrado no smoke real (STJ AREsp 2427258/DF) que
# levantou ``IllegalCharacterError`` no exporter.
ILLEGAL_XLSX_CHARS_RE: Final = re.compile(
    r"[\x00-\x08\x0B\x0C\x0E-\x1F␀-␿]",
)


def sanitize_for_xlsx(s: Any) -> Any:
    """Remove caracteres de controle Unicode incompatíveis com openpyxl.

    Preserva ``\\t`` (0x09), ``\\n`` (0x0A) e ``\\r`` (0x0D). Tudo mais
    do bloco de controle ASCII baixo é removido. O bloco
    U+2400–U+243F ("Control Pictures") também é removido — mojibake
    upstream do DJEN.

    Entrada não-string (None, int, list, dict, etc.) passa direto sem
    levantar — defesa pra usar no pipeline sobre dicts heterogêneos.
    Listas e dicts NÃO são percorridos recursivamente; nestes casos a
    defesa secundária está no ``dje_exporter._serialize_cell`` que
    sanitiza a string final pós-JSON.
    """
    if not isinstance(s, str):
        return s
    return ILLEGAL_XLSX_CHARS_RE.sub("", s)


def strip_html(s: str | None) -> str | None:
    """Remove tags HTML preservando estrutura visual:
    - ``<br>``, ``</p>``, ``</div>``, ``</li>``, ``</hN>``, ``</tr>`` → ``\\n``
    - ``</td>``, ``</th>`` → espaço (separa células sem grudar)
    - Qualquer outra tag → removida
    - Entidades HTML (``&amp;``, ``&nbsp;``, ``&aacute;``) → decodificadas
    - Espaços/tabs múltiplos colapsados; quebras de linha colapsadas
      em pares (no máximo `\\n\\n` consecutivos)

    Entrada None ou vazia → devolve sem tocar (usada em pipeline,
    não pode quebrar).
    """
    if not s:
        return s
    # 1. Block-level tags viram quebra de linha
    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</\s*(p|div|li|h[1-6])\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</\s*tr\s*>", "\n", s, flags=re.IGNORECASE)
    # 2. Células de tabela viram espaço (separa conteúdo)
    s = re.sub(r"</\s*(td|th)\s*>", " ", s, flags=re.IGNORECASE)
    # 3. Resto das tags some
    s = re.sub(r"<[^>]+>", "", s)
    # 4. Decodifica entidades HTML
    s = html.unescape(s)
    # 5. Normaliza espaços/tabs e quebras
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def normalizar_encoding_misto(s: str | None) -> str | None:
    """Converte minúsculas acentuadas pra maiúsculas em strings que
    estão visualmente em all-caps mas com bug de encoding upstream.

    Regra: se ≥70% das letras estão em maiúsculas, qualquer minúscula
    com acento/cedilha é trocada pela versão maiúscula. Strings com
    proporção menor (texto natural misto) ficam intactas.

    Entrada vazia/None → devolve sem tocar.
    """
    if not s:
        return s
    letras = [c for c in s if c.isalpha()]
    if not letras:
        return s
    proporcao = sum(1 for c in letras if c.isupper()) / len(letras)
    if proporcao < _UPPERCASE_RATIO_THRESHOLD:
        return s
    return "".join(ACENTUADAS_MIN_PARA_MAIUS.get(c, c) for c in s)


# ---------------------------------------------------------------------------
# Helpers de Regra A e B
# ---------------------------------------------------------------------------


def _is_empty(value: Any) -> bool:
    """``""``, ``None`` ou whitespace-only contam como vazio."""
    return str(value or "").strip() == ""


def _check_constants(row: dict[str, Any]) -> list[str]:
    """Regra A — comparação de campos esperados-constantes contra o
    valor encontrado. Retorna lista de mensagens (vazia se nada
    divergiu)."""
    msgs: list[str] = []
    if row.get("ativo") is not True:
        msgs.append(
            "Publicação inativa (ativo=False) — verificar se foi "
            "cancelada ou substituída",
        )
    status = row.get("status")
    if status != _REGRA_A_DEFAULTS["status"]:
        msgs.append(
            f"Status diferente do habitual: '{status}' "
            "(esperado: 'P' = publicada)",
        )
    meio = row.get("meio")
    if meio != _REGRA_A_DEFAULTS["meio"]:
        msgs.append(
            f"Meio diferente do habitual: '{meio}' "
            "(esperado: 'D' = diário)",
        )
    meio_completo = row.get("meiocompleto")
    if meio_completo != _REGRA_A_DEFAULTS["meiocompleto"]:
        msgs.append(
            f"Meio completo diferente do habitual: '{meio_completo}'",
        )
    motivo = row.get("motivo_cancelamento")
    if not _is_empty(motivo):
        msgs.append(f"Motivo de cancelamento informado: {motivo}")
    data_canc = row.get("data_cancelamento")
    if not _is_empty(data_canc):
        msgs.append(f"Data de cancelamento informada: {data_canc}")
    return msgs


def _socios_presentes(
    destinatarioadvogados: Any,
) -> tuple[bool, bool]:
    """Inspeciona ``destinatarioadvogados`` e retorna ``(tem_ricardo,
    tem_leonardo)``. Critério literal: ``oab == numero AND uf == DF``.

    Aceita lista de dicts (formato real do DJEN) ou lista vazia/None
    (defesa contra payload variante)."""
    has_r = False
    has_l = False
    if not isinstance(destinatarioadvogados, list):
        return has_r, has_l
    for adv in destinatarioadvogados:
        if not isinstance(adv, dict):
            continue
        oab = str(adv.get("numero_oab") or "").strip()
        uf = str(adv.get("uf_oab") or "").strip().upper()
        if uf != SOCIOS_UF:
            continue
        if oab == RICARDO_OAB:
            has_r = True
        elif oab == LEONARDO_OAB:
            has_l = True
    return has_r, has_l


def _check_socios(row: dict[str, Any]) -> str:
    """Regra B — verifica presença dos sócios em
    ``destinatarioadvogados``. Retorna mensagem ou ``""`` quando ambos
    aparecem (regra não dispara)."""
    has_r, has_l = _socios_presentes(row.get("destinatarioadvogados"))
    if has_r and has_l:
        return ""
    if not has_r and not has_l:
        return (
            f"Nem Ricardo ({RICARDO_OAB}/{SOCIOS_UF}) nem Leonardo "
            f"({LEONARDO_OAB}/{SOCIOS_UF}) constam entre os "
            "advogados intimados"
        )
    if has_r and not has_l:
        return (
            f"Leonardo ({LEONARDO_OAB}/{SOCIOS_UF}) não consta entre "
            "os advogados intimados"
        )
    # has_l and not has_r
    return (
        f"Ricardo ({RICARDO_OAB}/{SOCIOS_UF}) não consta entre os "
        "advogados intimados"
    )


def make_observacoes(row: dict[str, Any]) -> str:
    """Compõe a coluna ``observacoes``: regra A primeiro (em ordem dos
    campos), depois regra B. Múltiplas mensagens unidas por ``" | "``.

    Linha sem anomalias → ``""`` (string vazia, NÃO None — predito UX
    pra escrita simples no xlsx).
    """
    msgs: list[str] = []
    msgs.extend(_check_constants(row))
    socios = _check_socios(row)
    if socios:
        msgs.append(socios)
    return " | ".join(msgs)


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


def _collapse_advogados(rows_for_id: list[dict[str, Any]]) -> str:
    """Coleta todos os ``advogado_consultado`` (singular, anotados pelo
    client em cada linha) das duplicatas de um mesmo id, ordena
    alfabeticamente por nome completo, junta com ``"; "``."""
    labels: set[str] = set()
    for r in rows_for_id:
        label = r.get("advogado_consultado")
        if label:
            labels.add(str(label))
    return "; ".join(sorted(labels))


def _check_divergence(rows_for_id: list[dict[str, Any]]) -> list[str]:
    """Compara as duplicatas de um mesmo id e detecta campos que
    divergem entre elas (excluindo ``advogado_consultado``, que é o
    único campo esperado divergente)."""
    if len(rows_for_id) < 2:
        return []
    base = rows_for_id[0]
    divergent: set[str] = set()
    for other in rows_for_id[1:]:
        for key in set(base.keys()) | set(other.keys()):
            if key == "advogado_consultado":
                continue
            if base.get(key) != other.get(key):
                divergent.add(key)
    return sorted(divergent)


def dedup_by_id(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Colapsa duplicatas pelo campo ``id`` (chave inteira da
    publicação no DJEN). Cada grupo de mesmo ``id`` vira uma linha:
    primeira ocorrência preservada (campos diferentes de
    ``advogado_consultado``), com ``advogados_consultados`` (plural)
    populado pelo agregado.

    Linhas sem ``id`` (defesa) ficam preservadas como estão, com
    ``advogados_consultados`` derivado do ``advogado_consultado``
    individual.

    Divergência detectada entre duplicatas → warning no logger, mas
    operação não aborta (mantém primeira ocorrência).
    """
    grouped: dict[Any, list[dict[str, Any]]] = {}
    no_id: list[dict[str, Any]] = []
    for r in rows:
        rid = r.get("id")
        if rid is None:
            no_id.append(r)
            continue
        grouped.setdefault(rid, []).append(r)

    result: list[dict[str, Any]] = []
    # Preserva ordem de inserção dos grupos (Python 3.7+ dict ordenado).
    for rid, dup_rows in grouped.items():
        divergent = _check_divergence(dup_rows)
        if divergent:
            logger.warning(
                "DJE: id=%s tem %d duplicatas com campos divergentes: %s "
                "— mantendo primeira ocorrência",
                rid, len(dup_rows), divergent,
            )
        # Pega a primeira como base (todos os campos de negócio).
        base = dict(dup_rows[0])
        # advogado_consultado (singular) sai; advogados_consultados (plural) entra.
        base.pop("advogado_consultado", None)
        base["advogados_consultados"] = _collapse_advogados(dup_rows)
        result.append(base)

    # Linhas sem id viram singular→plural com mesmo conteúdo.
    for r in no_id:
        base = dict(r)
        original = base.pop("advogado_consultado", "")
        base["advogados_consultados"] = str(original) if original else ""
        result.append(base)

    return result


# ---------------------------------------------------------------------------
# Apply enrichment + cleanup
# ---------------------------------------------------------------------------


def _enrich_row(row: dict[str, Any]) -> dict[str, Any]:
    """Aplica em sequência sobre uma linha (já deduplicada):
    1. ``observacoes`` derivada das regras A+B
    2. ``texto`` strip de HTML
    3. ``nomeOrgao``/``nomeClasse``/``tipoDocumento`` normalização de
       encoding misto
    4. drop das 6 colunas redundantes (cobertas por ``observacoes``)
    5. ``sanitize_for_xlsx`` em TODOS os campos string da linha (Fase 2.1)
    """
    out = dict(row)
    out["observacoes"] = make_observacoes(row)

    if "texto" in out:
        cleaned = strip_html(out["texto"])
        if cleaned is not None:
            out["texto"] = cleaned

    for field in _NORMALIZE_ENCODING_FIELDS:
        if field in out:
            normalized = normalizar_encoding_misto(out[field])
            if normalized is not None:
                out[field] = normalized

    for col in DROPPED_COLUMNS:
        out.pop(col, None)

    # Fase 2.1: passada final de sanitização. Aplica em TODOS os campos
    # string top-level (None, int, list, dict passam intactos — sanitize
    # é defensivo). Listas/dicts aninhados ficam pra defesa secundária
    # no exporter via JSON serialize.
    for key, value in list(out.items()):
        if isinstance(value, str):
            out[key] = sanitize_for_xlsx(value)

    return out


# ---------------------------------------------------------------------------
# Sort
# ---------------------------------------------------------------------------


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordena por ``siglaTribunal`` ASC, ``data_disponibilizacao`` DESC.

    Empate em data: ordem estável (preserva ordem anterior). Linhas
    sem ``siglaTribunal`` ou sem ``data_disponibilizacao`` ainda
    aparecem; chave ausente trata como string vazia (vão pro topo).
    """
    return sorted(
        rows,
        key=lambda r: (
            str(r.get("siglaTribunal") or ""),
            # Negação via reverse string trick não funciona; usamos
            # tupla com primeiro asc + segundo via reverse parcial.
            # Truque: fazemos o sort em 2 passes ou usamos chave
            # composta com inversão do segundo. Como datas vêm em ISO
            # (YYYY-MM-DD), comparar string asc é equivalente a date asc.
            # Pra DESC, negamos via ordenação reversa do segundo campo:
            # invertemos o sinal usando um wrapper.
            _DescStr(str(r.get("data_disponibilizacao") or "")),
        ),
    )


class _DescStr:
    """Wrapper pra comparar strings em ordem decrescente dentro de
    uma tupla de sort (Python não tem flag per-key descending nativo).

    ``a < b`` quando ``a > b`` lexicograficamente — inverte o sinal."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __lt__(self, other: "_DescStr") -> bool:
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _DescStr) and self.value == other.value


# ---------------------------------------------------------------------------
# Orquestrador público
# ---------------------------------------------------------------------------


def transform_rows(
    raw_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Pipeline completo da Fase 2:
    1. Dedup por ``id`` → 1 linha por publicação
    2. Enrich cada linha: ``observacoes``, strip HTML do ``texto``,
       normalização de encoding em nomeOrgao/nomeClasse/tipoDocumento
    3. Drop das 6 colunas redundantes
    4. Sort por siglaTribunal ASC + data_disponibilizacao DESC

    Retorna ``(rows, columns)`` — rows são os dicts processados,
    columns é ``CANONICAL_COLUMNS`` (20 entradas em ordem fixa).
    Caller (``dje_exporter.write_publicacoes_xlsx``) escreve nessa
    ordem no xlsx.
    """
    deduped = dedup_by_id(raw_rows)
    enriched = [_enrich_row(r) for r in deduped]
    sorted_rows = sort_rows(enriched)
    return sorted_rows, list(CANONICAL_COLUMNS)
