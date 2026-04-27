"""Conversão entre payloads da API Notion e valores Python simples.

decode_value: API Notion → Python (str, int, float, bool, list, None)
encode_value: Python → payload de propriedade da API Notion
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Helpers de formatação
# ---------------------------------------------------------------------------


_ISO_DATE_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})')


def format_br_date(iso: str | None) -> str:
    """Converte data ISO para formato brasileiro.

    Args:
        iso: Data no formato 'YYYY-MM-DD' ou None.

    Returns:
        Data no formato 'DD/MM/YYYY' ou string vazia se None.

    Exemplo:
        >>> format_br_date("2024-03-15")
        '15/03/2024'
    """
    if not iso:
        return ""
    # BUG-N18: use regex to avoid accepting garbage after the date
    m = _ISO_DATE_RE.match(str(iso))
    if not m:
        return str(iso)  # return raw if format is unexpected
    y, mo, d = m.groups()
    return f"{d}/{mo}/{y}"


def parse_br_date(br: str) -> str:
    """Converte data brasileira para formato ISO.

    Args:
        br: Data no formato 'DD/MM/YYYY'.

    Returns:
        Data no formato 'YYYY-MM-DD'.

    Raises:
        ValueError: Se o formato não for reconhecido ou a data for inválida.

    Exemplo:
        >>> parse_br_date("15/03/2024")
        '2024-03-15'
    """
    br = br.strip()
    if not br:
        return ""
    if "-" in br and len(br) >= 10:
        # Already ISO — validate it's a real date
        try:
            datetime.strptime(br[:10], "%Y-%m-%d")
        except ValueError:
            pass  # return as-is if it looks ISO but may not be
        return br[:10]
    # BUG-N8: use strptime for strict validation (rejects month 13, day 32, year 24)
    try:
        return datetime.strptime(br, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Data inválida (esperado DD/MM/AAAA): {br!r}") from e


def format_brl(value: float | int | None) -> str:
    """Formata valor numérico como moeda brasileira.

    Args:
        value: Valor numérico (ex: 78500).

    Returns:
        String formatada (ex: 'R$ 78.500,00') ou '' se None.

    Exemplo:
        >>> format_brl(78500)
        'R$ 78.500,00'
        >>> format_brl(1234567.89)
        'R$ 1.234.567,89'
    """
    if value is None:
        return ""
    # BUG-N10: handle inf/nan gracefully
    if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
        return "—"
    try:
        sinal = "-" if value < 0 else ""
        valor_abs = abs(float(value))
        inteiro = int(valor_abs)
        centavos = round((valor_abs - inteiro) * 100)
        # BUG-N10: carry-over when rounding pushes centavos to 100
        if centavos >= 100:
            inteiro += 1
            centavos -= 100
        inteiro_fmt = f"{inteiro:,}".replace(",", ".")
        return f"R$ {sinal}{inteiro_fmt},{centavos:02d}"
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Decodificação: API Notion → Python
# ---------------------------------------------------------------------------


def _decode_rich_text(blocks: list[dict]) -> str:
    """Extrai o texto plano de uma lista de rich_text blocks."""
    return "".join(b.get("plain_text", "") for b in blocks)


def decode_value(prop_block: dict, tipo: str) -> Any:
    """Converte um valor de propriedade da API Notion para Python.

    Args:
        prop_block: Dicionário retornado pela API para uma propriedade.
            Ex: {"type": "select", "select": {"name": "Ativo"}}
        tipo: Tipo da propriedade conforme o schema
            (ex: 'select', 'rich_text', 'number', etc.).

    Returns:
        Valor Python correspondente:
        - str para title, rich_text, url, email, phone_number, select
        - list[str] para multi_select
        - float | int | None para number
        - bool para checkbox
        - str | None para date (ISO 'YYYY-MM-DD')
        - list[str] para people (lista de user IDs)
        - list[str] para relation (lista de page IDs)
        - Any para rollup e formula (valor computado)
        - str para created_time, last_edited_time
        - None para tipos desconhecidos ou propriedade vazia
    """
    if not prop_block:
        return None

    match tipo:
        case "title":
            blocks = prop_block.get("title", [])
            return _decode_rich_text(blocks)

        case "rich_text":
            blocks = prop_block.get("rich_text", [])
            return _decode_rich_text(blocks)

        case "number":
            return prop_block.get("number")

        case "select":
            sel = prop_block.get("select")
            if sel is None:
                return None
            return sel.get("name")

        case "multi_select":
            items = prop_block.get("multi_select", [])
            return [item.get("name", "") for item in items]

        case "date":
            date_obj = prop_block.get("date")
            if date_obj is None:
                return None
            return date_obj.get("start")

        case "people":
            people = prop_block.get("people", [])
            return [p.get("id", "") for p in people]

        case "checkbox":
            return bool(prop_block.get("checkbox", False))

        case "relation":
            rels = prop_block.get("relation", [])
            return [r.get("id", "") for r in rels]

        case "rollup":
            rollup = prop_block.get("rollup", {})
            rtype = rollup.get("type")
            match rtype:
                case "number":
                    return rollup.get("number")
                case "date":
                    date_obj = rollup.get("date")
                    if date_obj is None:
                        return None
                    return date_obj.get("start")
                case "array":
                    arr = rollup.get("array", [])
                    # Retorna lista de valores simples
                    return [
                        decode_value(item, item.get("type", "rich_text"))
                        for item in arr
                    ]
                case _:
                    return None

        case "formula":
            formula = prop_block.get("formula", {})
            ftype = formula.get("type")
            match ftype:
                case "string":
                    return formula.get("string")
                case "number":
                    return formula.get("number")
                case "boolean":
                    return formula.get("boolean")
                case "date":
                    date_obj = formula.get("date")
                    if date_obj is None:
                        return None
                    return date_obj.get("start")
                case _:
                    return None

        case "url":
            return prop_block.get("url")

        case "email":
            return prop_block.get("email")

        case "phone_number":
            return prop_block.get("phone_number")

        case "created_time":
            return prop_block.get("created_time")

        case "last_edited_time":
            return prop_block.get("last_edited_time")

        case _:
            return None


# ---------------------------------------------------------------------------
# Codificação: Python → API Notion
# ---------------------------------------------------------------------------


def _parse_brl_number(s: str) -> float:
    """BUG-N9: parse BR-formatted numbers like '78.500,00' or 'R$ 1.234,56'."""
    s = str(s).replace("R$", "").replace("\xa0", "").strip()
    if "," in s and "." in s:
        # thousands dot + decimal comma: '1.234,56' → '1234.56'
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # decimal comma only: '1234,56' → '1234.56'
        s = s.replace(",", ".")
    return float(s)


def encode_value(value: Any, tipo: str, extra: dict | None = None) -> dict:
    """Converte um valor Python no payload de propriedade da API Notion.

    Tipos somente leitura (rollup, formula, created_time, last_edited_time)
    retornam dict vazio — não devem ser enviados na requisição.

    Args:
        value: Valor Python a codificar. None limpa a propriedade quando possível.
        tipo: Tipo da propriedade Notion (ex: 'select', 'rich_text', etc.).
        extra: Metadados adicionais (não utilizado atualmente, reservado).

    Returns:
        Payload dict pronto para incluir em 'properties' de update_page/create_page.

    Exemplos:
        >>> encode_value("Ativo", "select")
        {"select": {"name": "Ativo"}}

        >>> encode_value(None, "select")
        {"select": None}

        >>> encode_value("0001234-56.2023.5.10.0001", "title")
        {"title": [{"text": {"content": "0001234-56.2023.5.10.0001"}}]}
    """
    match tipo:
        case "title":
            if not value:
                return {"title": []}
            return {"title": [{"text": {"content": str(value)}}]}

        case "rich_text":
            if not value:
                return {"rich_text": []}
            return {"rich_text": [{"text": {"content": str(value)}}]}

        case "number":
            if value is None:
                return {"number": None}
            try:
                # BUG-N9: try BR number format first (e.g. '78.500,00'), then plain float
                if isinstance(value, str):
                    return {"number": _parse_brl_number(value)}
                return {"number": float(value)}
            except (TypeError, ValueError):
                return {"number": None}

        case "select":
            if not value:
                return {"select": None}
            return {"select": {"name": str(value)}}

        case "multi_select":
            if not value:
                return {"multi_select": []}
            if isinstance(value, str):
                value = [v.strip() for v in value.split(",") if v.strip()]
            return {"multi_select": [{"name": str(v)} for v in value]}

        case "date":
            if not value:
                return {"date": None}
            # Aceita tanto ISO quanto formato brasileiro
            iso: str
            if isinstance(value, str) and "/" in value:
                iso = parse_br_date(value)
            else:
                iso = str(value)[:10]
            return {"date": {"start": iso}}

        case "people":
            if not value:
                return {"people": []}
            if isinstance(value, str):
                value = [value]
            return {"people": [{"id": uid} for uid in value]}

        case "checkbox":
            return {"checkbox": bool(value)}

        case "relation":
            if not value:
                return {"relation": []}
            if isinstance(value, str):
                value = [value]
            return {"relation": [{"id": pid} for pid in value]}

        case "url":
            # BUG-N23: use explicit None check; empty string should clear the field
            if value is None or value == "":
                return {"url": None}
            return {"url": str(value)}

        case "email":
            if value is None or value == "":
                return {"email": None}
            return {"email": str(value)}

        case "phone_number":
            if value is None or value == "":
                return {"phone_number": None}
            return {"phone_number": str(value)}

        # Tipos somente leitura — não enviar na API
        case "rollup" | "formula" | "created_time" | "last_edited_time":
            return {}

        case _:
            return {}
