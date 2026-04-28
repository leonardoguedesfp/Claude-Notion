"""Esquemas das bases Notion do escritório RPADV.

Fase 3 (cleanup): este módulo virou um adapter mínimo entre o registry
dinâmico (`notion_bulk_edit.schema_registry`) e os call-sites legados que
usam ``SCHEMAS["Base"]["key"]``. As schemas são servidas exclusivamente
do registry — não há mais conteúdo hardcoded.

API pública:

- ``PropSpec``: dataclass de propriedade (mesma assinatura desde Fase 0).
- ``OptionSpec``: re-exportado lazy via PEP 562 (definido em
  ``schema_registry``); usado para opções com cor.
- ``SCHEMAS``: proxy ``Mapping[base, Mapping[key, PropSpec]]``.
- Helpers públicos: ``get_prop``, ``is_nao_editavel``, ``colunas_visiveis``,
  ``vocabulario``.

Tipos suportados da API Notion:
  title, rich_text, number, select, multi_select, date,
  people, checkbox, relation, rollup, formula, url,
  email, phone_number, created_time, last_edited_time
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    # Re-export de OptionSpec sem ciclo em runtime — exposto por __getattr__.
    from notion_bulk_edit.schema_registry import OptionSpec  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PropSpec:
    notion_name: str
    tipo: str
    label: str
    editavel: bool = True
    obrigatorio: bool = False
    opcoes: tuple[str, ...] = field(default_factory=tuple)
    largura_col: str = "10%"
    mono: bool = False
    formato: str = ""          # ex: 'BRL', 'BR_DATE', 'BR_DATETIME'
    cor_por_valor: dict[str, str] = field(default_factory=dict)
    # BUG-V3 / Fase 3: base alvo quando tipo == 'relation'. Populado pelo
    # registry via lookup reverso de DATA_SOURCES (data_source_id → label).
    target_base: str = ""
    # §3.1: largura mínima em pixels — floor para QHeaderView. Fallback para
    # estimativa baseada em font quando None. Não vem do schema dinâmico.
    min_width_px: Optional[int] = None


# Lista canônica das bases conhecidas pelo app. Fase 4b adiciona "Documentos".
_KNOWN_BASES: tuple[str, ...] = ("Processos", "Clientes", "Tarefas", "Catalogo")


class _BaseSchemaProxy(Mapping[str, PropSpec]):
    """Proxy para o dict de propriedades de uma base. Lê do registry dinâmico.

    Fase 3: branch condicional ``USE_DYNAMIC_SCHEMA`` removida. Sempre tenta
    o registry; cai num dict vazio quando o singleton ainda não foi
    inicializado (cenário de testes unitários sem MainWindow).
    """

    def __init__(self, base_name: str) -> None:
        self._base = base_name

    def _backing(self) -> dict[str, PropSpec]:
        # Import adiado para evitar ciclo no load do módulo.
        from notion_bulk_edit.schema_registry import get_schema_registry
        try:
            return get_schema_registry().schema_for_base(self._base)
        except RuntimeError:
            # Singleton não inicializado — testes unitários que pulam
            # ``init_schema_registry``. Devolve dict vazio em vez de crashar.
            return {}

    def __getitem__(self, key: str) -> PropSpec:
        return self._backing()[key]

    def __iter__(self) -> Any:
        return iter(self._backing())

    def __len__(self) -> int:
        return len(self._backing())

    def __contains__(self, key: object) -> bool:
        return key in self._backing()


class _SchemasProxy(Mapping[str, _BaseSchemaProxy]):
    """Proxy para o dict de bases. ``SCHEMAS["Processos"]`` devolve um
    ``_BaseSchemaProxy("Processos")`` que resolve dinamicamente."""

    def __getitem__(self, key: str) -> _BaseSchemaProxy:
        if key not in _KNOWN_BASES:
            raise KeyError(key)
        return _BaseSchemaProxy(key)

    def __iter__(self) -> Any:
        return iter(_KNOWN_BASES)

    def __len__(self) -> int:
        return len(_KNOWN_BASES)

    def __contains__(self, key: object) -> bool:
        return key in _KNOWN_BASES


SCHEMAS: _SchemasProxy = _SchemasProxy()


def __getattr__(name: str) -> Any:
    """Re-export lazy de OptionSpec — resolve em runtime para evitar ciclo
    de import com schema_registry (que importa PropSpec deste módulo)."""
    if name == "OptionSpec":
        from notion_bulk_edit.schema_registry import OptionSpec
        return OptionSpec
    raise AttributeError(
        f"module 'notion_bulk_edit.schemas' has no attribute {name!r}",
    )


# ---------------------------------------------------------------------------
# Helpers públicos (mantêm a API legada — leem via proxy/registry)
# ---------------------------------------------------------------------------


def get_prop(base: str, key: str) -> Optional[PropSpec]:
    """Retorna o PropSpec de uma propriedade, ou None se não existir."""
    return SCHEMAS.get(base, {}).get(key)


def is_nao_editavel(base: str, key: str) -> bool:
    """True se a propriedade NÃO deve ser editada pelo app."""
    spec = get_prop(base, key)
    if spec is None:
        return True
    if not spec.editavel:
        return True
    if spec.tipo in ("rollup", "formula", "created_time", "last_edited_time"):
        return True
    return False


def colunas_visiveis(base: str, user_id: str | None = None) -> list[str]:
    """Retorna as chaves das colunas visíveis para uma base.

    Sem ``user_id`` → defaults do schema dinâmico (registry).
    Com ``user_id`` → preferências persistidas em ``meta_user_columns``.

    Fase 4: rebatido para o registry. Comportamento legado de filtrar por
    ``largura_col != '0'`` foi descartado — esse filtro nunca disparava no
    schema dinâmico (``PropSpec.largura_col`` é sempre o default ``"10%"``)
    e era a fonte da regressão visual da Fase 3 (todas as colunas visíveis
    incluindo system properties como ``criado_em``/``atualizado_em``).
    """
    from notion_bulk_edit.schema_registry import get_schema_registry
    try:
        return get_schema_registry().colunas_visiveis(base, user_id=user_id)
    except RuntimeError:
        # Singleton não inicializado — testes unitários sem MainWindow.
        return []


def vocabulario(base: str, key: str) -> tuple[str, ...]:
    """Retorna as opções válidas de um campo select."""
    spec = get_prop(base, key)
    if spec is None:
        return ()
    return spec.opcoes
