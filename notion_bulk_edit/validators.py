"""Validação de dados para importação nas bases Notion do RPADV.

Valida campos individuais, linhas completas de planilha e formatos
legais específicos (CNJ, CPF).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from notion_bulk_edit.resolvers import normalize_digits
from notion_bulk_edit.schemas import SCHEMAS, PropSpec, vocabulario


# ---------------------------------------------------------------------------
# Dataclass de erro de validação
# ---------------------------------------------------------------------------


@dataclass
class ValidationError:
    """Representa um único erro de validação em um campo.

    Atributos:
        campo: Chave do campo com problema (ex: 'cnj', 'cpf').
        mensagem: Descrição legível do erro em português.
    """

    campo: str
    mensagem: str

    def __str__(self) -> str:
        return f"[{self.campo}] {self.mensagem}"


# ---------------------------------------------------------------------------
# Validação de CNJ
# ---------------------------------------------------------------------------

# Padrão oficial CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO
_CNJ_PATTERN = re.compile(
    r"^\d{7}-\d{2}\.\d{4}\.\d{1}\.\d{2}\.\d{4}$"
)


def validar_cnj(cnj: str) -> list[ValidationError]:
    """Valida o formato do número CNJ.

    O formato oficial é: NNNNNNN-DD.AAAA.J.TT.OOOO
    onde:
      - NNNNNNN = 7 dígitos do número do processo
      - DD = 2 dígitos dos dígitos verificadores
      - AAAA = 4 dígitos do ano
      - J = 1 dígito da Justiça
      - TT = 2 dígitos do Tribunal
      - OOOO = 4 dígitos do órgão

    Args:
        cnj: Número CNJ a validar.

    Returns:
        Lista de ValidationError (vazia se válido).
    """
    erros: list[ValidationError] = []

    if not cnj or not cnj.strip():
        erros.append(ValidationError("cnj", "CNJ é obrigatório."))
        return erros

    cnj = cnj.strip()

    if not _CNJ_PATTERN.match(cnj):
        erros.append(
            ValidationError(
                "cnj",
                f"CNJ '{cnj}' não está no formato válido NNNNNNN-DD.AAAA.J.TT.OOOO.",
            )
        )

    return erros


# ---------------------------------------------------------------------------
# Validação de CPF
# ---------------------------------------------------------------------------


def _cpf_digitos_verificadores(digits: str) -> bool:
    """Verifica os dígitos verificadores do CPF."""
    if len(digits) != 11:
        return False
    # CPFs com todos os dígitos iguais são inválidos
    if len(set(digits)) == 1:
        return False

    # Primeiro dígito verificador
    soma = sum(int(digits[i]) * (10 - i) for i in range(9))
    r1 = (soma * 10) % 11
    d1 = 0 if r1 >= 10 else r1
    if d1 != int(digits[9]):
        return False

    # Segundo dígito verificador
    soma2 = sum(int(digits[i]) * (11 - i) for i in range(10))
    r2 = (soma2 * 10) % 11
    d2 = 0 if r2 >= 10 else r2
    return d2 == int(digits[10])


def validar_cpf(cpf: str) -> list[ValidationError]:
    """Valida o CPF verificando os dígitos verificadores.

    Aceita CPF com ou sem formatação (pontos e traço).

    Args:
        cpf: CPF a validar (ex: '123.456.789-09' ou '12345678909').

    Returns:
        Lista de ValidationError (vazia se válido).
    """
    erros: list[ValidationError] = []

    if not cpf or not str(cpf).strip():
        erros.append(ValidationError("cpf", "CPF é obrigatório."))
        return erros

    digits = normalize_digits(str(cpf).strip())

    if len(digits) != 11:
        erros.append(
            ValidationError(
                "cpf",
                f"CPF deve conter 11 dígitos; encontrado {len(digits)}.",
            )
        )
        return erros

    if not _cpf_digitos_verificadores(digits):
        erros.append(
            ValidationError("cpf", f"CPF '{cpf}' possui dígitos verificadores inválidos.")
        )

    return erros


# ---------------------------------------------------------------------------
# Validação de data
# ---------------------------------------------------------------------------

_DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_BR = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _validar_data(campo: str, valor: str) -> list[ValidationError]:
    """Valida se uma string de data está em formato reconhecível."""
    erros: list[ValidationError] = []
    v = str(valor).strip()
    if not _DATE_ISO.match(v) and not _DATE_BR.match(v):
        erros.append(
            ValidationError(
                campo,
                f"Data '{v}' inválida. Use YYYY-MM-DD ou DD/MM/YYYY.",
            )
        )
    return erros


# ---------------------------------------------------------------------------
# Validação de valor individual
# ---------------------------------------------------------------------------


def validar_valor(base: str, campo: str, valor: Any) -> list[ValidationError]:
    """Valida um único valor para um campo específico de uma base.

    Args:
        base: Nome da base ('Processos', 'Clientes', 'Tarefas', 'Catalogo').
        campo: Chave do campo no schema (ex: 'cnj', 'status').
        valor: Valor a validar.

    Returns:
        Lista de ValidationError (vazia se válido).
    """
    erros: list[ValidationError] = []
    schema = SCHEMAS.get(base, {})
    spec: PropSpec | None = schema.get(campo)

    if spec is None:
        return erros  # Campo desconhecido — ignorar silenciosamente

    # Campo obrigatório
    vazio = valor is None or str(valor).strip() == ""
    if spec.obrigatorio and vazio:
        erros.append(ValidationError(campo, f"Campo '{spec.label}' é obrigatório."))
        return erros

    if vazio:
        return erros  # Nada mais a validar se vazio e não obrigatório

    # Validações específicas por tipo
    # Fase 3: schema dinâmico é fonte única; slug do título de Processos
    # é "numero_do_processo".
    match spec.tipo:
        case "title" if campo == "numero_do_processo":
            erros.extend(validar_cnj(str(valor)))

        case "rich_text" if campo == "cpf":
            erros.extend(validar_cpf(str(valor)))

        case "select":
            opcoes = vocabulario(base, campo)
            if opcoes and str(valor).strip() not in opcoes:
                erros.append(
                    ValidationError(
                        campo,
                        f"Valor '{valor}' inválido para '{spec.label}'. "
                        f"Opções: {', '.join(opcoes)}.",
                    )
                )

        case "multi_select":
            opcoes = vocabulario(base, campo)
            if opcoes:
                if isinstance(valor, str):
                    valores_lista = [v.strip() for v in valor.split(",") if v.strip()]
                else:
                    valores_lista = list(valor)
                invalidos = [v for v in valores_lista if v not in opcoes]
                for inv in invalidos:
                    erros.append(
                        ValidationError(
                            campo,
                            f"Valor '{inv}' inválido em '{spec.label}'. "
                            f"Opções: {', '.join(opcoes)}.",
                        )
                    )

        case "date":
            erros.extend(_validar_data(campo, str(valor)))

        case "number":
            try:
                float(str(valor).replace(",", ".").replace("R$", "").strip())
            except ValueError:
                erros.append(
                    ValidationError(campo, f"'{valor}' não é um número válido para '{spec.label}'.")
                )

        case "checkbox":
            v_str = str(valor).strip().lower()
            if v_str not in ("true", "false", "1", "0", "sim", "não", "nao", "s", "n", "x", ""):
                erros.append(
                    ValidationError(
                        campo,
                        f"Valor '{valor}' inválido para checkbox '{spec.label}'. "
                        "Use: sim/não, true/false ou 1/0.",
                    )
                )

    return erros


# ---------------------------------------------------------------------------
# Validação de linha completa
# ---------------------------------------------------------------------------


def validar_linha(base: str, row: dict[str, Any]) -> list[ValidationError]:
    """Valida uma linha completa de planilha para uma base específica.

    Verifica:
    - Campos obrigatórios presentes e não vazios
    - Selects com valor dentro do vocabulário controlado
    - CNJ com formato NNNNNNN-DD.AAAA.J.TT.OOOO
    - CPF com dígitos verificadores válidos
    - Datas em formato YYYY-MM-DD ou DD/MM/YYYY

    Args:
        base: Nome da base ('Processos', 'Clientes', 'Tarefas', 'Catalogo').
        row: Dicionário com os dados da linha. As chaves devem ser as chaves
             do schema (ex: 'cnj', 'status') ou o notion_name da propriedade.

    Returns:
        Lista de ValidationError com todos os erros encontrados.
        Lista vazia indica linha válida.
    """
    erros: list[ValidationError] = []
    schema = SCHEMAS.get(base, {})

    if not schema:
        erros.append(
            ValidationError("base", f"Base '{base}' não encontrada no schema.")
        )
        return erros

    # Normaliza chaves: aceita tanto chave do schema quanto notion_name
    notion_name_to_key: dict[str, str] = {
        spec.notion_name: key for key, spec in schema.items()
    }

    row_normalizada: dict[str, Any] = {}
    for k, v in row.items():
        if k in schema:
            row_normalizada[k] = v
        elif k in notion_name_to_key:
            row_normalizada[notion_name_to_key[k]] = v
        # Ignora colunas desconhecidas silenciosamente

    # Valida cada campo do schema
    for campo, spec in schema.items():
        valor = row_normalizada.get(campo)

        # Campos obrigatórios faltando
        if spec.obrigatorio and (valor is None or str(valor).strip() == ""):
            erros.append(
                ValidationError(campo, f"Campo obrigatório '{spec.label}' está ausente ou vazio.")
            )
            continue

        # Pula se vazio e não obrigatório
        if valor is None or str(valor).strip() == "":
            continue

        # Delega validação por campo
        erros.extend(validar_valor(base, campo, valor))

    return erros
