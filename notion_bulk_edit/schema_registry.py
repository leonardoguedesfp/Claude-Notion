"""Fase 0 — schema dinâmico: registry singleton de schemas em memória.

Cache primário: ``audit.db.meta_schemas`` (criado por ``init_audit_db``).
Cache secundário: dicts em memória populados via ``load_all_from_cache``.

A API pública (``get_prop``, ``is_nao_editavel``, ``colunas_visiveis``,
``vocabulario``, ``schema_for_base``) preserva a assinatura usada hoje
em ``notion_bulk_edit/schemas.py`` para que a Fase 1 possa fazer o
adapter shim sem quebrar call-sites.

A Fase 0 NÃO conecta este registry no app — só constrói a infra. O legado
hardcoded em ``schemas.py`` continua sendo a fonte de verdade até a Fase 1.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Literal

from notion_bulk_edit.schema_parser import (
    compute_schema_hash,
    parse_to_schema_json,
)
from notion_bulk_edit.schemas import PropSpec
from notion_rpadv.cache import db as cache_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OptionSpec:
    """Opção de select/multi_select com cor preservada da API Notion.

    Não substitui a API de ``vocabulario(base, key) -> tuple[str, ...]``
    que continua existindo. Para acessar a cor, use ``vocabulario_full``.
    """

    name: str
    color: str = "default"


@dataclass(frozen=True)
class ChangeReport:
    """Resultado de um refresh de schema. Usado pelo boot e pelo recovery."""

    kind: Literal["initial", "unchanged", "changed"]
    base: str
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# SchemaRegistry
# ---------------------------------------------------------------------------


class SchemaRegistry:
    """Cache em memória dos schemas dinâmicos, com persistência em audit.db.

    Não thread-safe — assume uso single-threaded do main thread (compatível
    com PySide6/Qt). Workers QThread devem usar a connection passada
    pelo SchemaRegistry, não o registry diretamente.
    """

    def __init__(self, audit_conn: sqlite3.Connection) -> None:
        self._audit_conn = audit_conn
        # base_label -> parsed_schema dict (na forma de schema_parser §3.3)
        self._schemas: dict[str, dict[str, Any]] = {}
        # base_label -> data_source_id (para refresh sem precisar do dict externo)
        self._base_to_dsid: dict[str, str] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def load_all_from_cache(self) -> None:
        """Carrega schemas de meta_schemas para o cache em memória.

        Idempotente — chamadas subsequentes recarregam do disco
        (útil após refresh em outro processo, embora não seja o caso
        no app desktop atual)."""
        rows = cache_db.get_all_cached_schemas(self._audit_conn)
        self._schemas.clear()
        self._base_to_dsid.clear()
        for row in rows:
            try:
                parsed = json.loads(row["schema_json"])
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "Schema cacheado de %r corrompido (%s); ignorando.",
                    row["base_label"], exc,
                )
                continue
            self._schemas[row["base_label"]] = parsed
            self._base_to_dsid[row["base_label"]] = row["data_source_id"]
        self._loaded = True

    # ------------------------------------------------------------------
    # Refresh via API
    # ------------------------------------------------------------------

    def refresh_from_api(
        self,
        base_label: str,
        data_source_id: str,
        client: Any,
    ) -> ChangeReport:
        """Faz fetch via API, parsa, persiste em meta_schemas, atualiza memória.

        Retorna ChangeReport descrevendo se foi initial/unchanged/changed,
        com listas de propriedades adicionadas/removidas/alteradas quando
        for "changed". Não emite signals nem toasts — UI lê o report.
        """
        raw = client.get_data_source(data_source_id)
        parsed = parse_to_schema_json(raw, base_label)
        new_hash = compute_schema_hash(parsed)
        new_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)

        existing = cache_db.get_cached_schema(self._audit_conn, data_source_id)
        kind: Literal["initial", "unchanged", "changed"]
        added: list[str] = []
        removed: list[str] = []
        changed: list[str] = []

        if existing is None:
            kind = "initial"
        elif existing["schema_hash"] == new_hash:
            kind = "unchanged"
        else:
            kind = "changed"
            try:
                old_parsed = json.loads(existing["schema_json"])
                added, removed, changed = _diff_properties(old_parsed, parsed)
            except (json.JSONDecodeError, TypeError, KeyError):
                # Cache antigo corrompido; trata como mudança total
                added = list(parsed.get("properties", {}).keys())

        cache_db.upsert_schema(
            self._audit_conn,
            data_source_id=data_source_id,
            base_label=base_label,
            title_property=parsed.get("title_property"),
            schema_json=new_json,
            schema_hash=new_hash,
            fetched_at=time.time(),
        )
        self._schemas[base_label] = parsed
        self._base_to_dsid[base_label] = data_source_id

        return ChangeReport(
            kind=kind, base=base_label,
            added=tuple(added), removed=tuple(removed), changed=tuple(changed),
        )

    # ------------------------------------------------------------------
    # Lookup público
    # ------------------------------------------------------------------

    def bases(self) -> list[str]:
        """Lista de base_labels conhecidos."""
        return list(self._schemas.keys())

    def schema_for_base(self, base: str) -> dict[str, PropSpec]:
        """Dict {key: PropSpec} para uma base. {} se base desconhecida."""
        parsed = self._schemas.get(base)
        if parsed is None:
            return {}
        return {
            key: _dict_to_propspec(prop_dict)
            for key, prop_dict in parsed.get("properties", {}).items()
        }

    def get_prop(self, base: str, key: str) -> PropSpec | None:
        """Lookup por base + key. None se base ou key não existe."""
        parsed = self._schemas.get(base)
        if parsed is None:
            return None
        prop_dict = parsed.get("properties", {}).get(key)
        if prop_dict is None:
            return None
        return _dict_to_propspec(prop_dict)

    def is_nao_editavel(self, base: str, key: str) -> bool:
        """True quando o app NÃO deve permitir edição inline da célula.

        Mantém a mesma semântica de ``schemas.is_nao_editavel`` legado:
        spec ausente → True; spec.editavel False → True; tipo readonly → True.
        """
        spec = self.get_prop(base, key)
        if spec is None:
            return True
        if not spec.editavel:
            return True
        if spec.tipo in (
            "rollup", "formula", "created_time", "last_edited_time",
            "created_by", "last_edited_by", "unique_id",
            "button", "verification",
        ):
            return True
        return False

    def colunas_visiveis(
        self, base: str, user_id: str | None = None,
    ) -> list[str]:
        """Lista de keys visíveis em ordem de exibição.

        Sem user_id → defaults do schema (default_visible=True ordenados
        por default_order). Com user_id → leitura de meta_user_columns
        (Fase 4); por enquanto apenas faz fallback ao default.
        """
        parsed = self._schemas.get(base)
        if parsed is None:
            return []
        properties = parsed.get("properties", {})

        # Fase 4 vai consultar meta_user_columns aqui. Por enquanto, ignora user_id.
        # Mantém parâmetro na assinatura para a Fase 1 já chamar com a forma final.
        _ = user_id  # parâmetro reservado para Fase 4

        # Defaults: keys com default_visible=True, ordenados por default_order
        visible = [
            (prop.get("default_order", 999), key)
            for key, prop in properties.items()
            if prop.get("default_visible", False)
        ]
        visible.sort(key=lambda t: t[0])
        return [key for _order, key in visible]

    def vocabulario(self, base: str, key: str) -> tuple[str, ...]:
        """Tupla de strings com nomes de opções (sem cor).

        Compatível com a API legada de ``schemas.vocabulario``.
        Para acessar cores, use ``vocabulario_full``.
        """
        parsed = self._schemas.get(base)
        if parsed is None:
            return ()
        prop = parsed.get("properties", {}).get(key)
        if prop is None:
            return ()
        return tuple(opt.get("name", "") for opt in prop.get("opcoes", []))

    def vocabulario_full(self, base: str, key: str) -> tuple[OptionSpec, ...]:
        """Tupla de OptionSpec(name, color) preservando a cor da API."""
        parsed = self._schemas.get(base)
        if parsed is None:
            return ()
        prop = parsed.get("properties", {}).get(key)
        if prop is None:
            return ()
        return tuple(
            OptionSpec(
                name=opt.get("name", ""),
                color=opt.get("color", "default"),
            )
            for opt in prop.get("opcoes", [])
        )


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------


_registry: SchemaRegistry | None = None


def init_schema_registry(audit_conn: sqlite3.Connection) -> SchemaRegistry:
    """Inicializa o singleton do SchemaRegistry.

    Chamado uma vez no boot do app (em MainWindow.__init__, na Fase 1).
    Idempotente quanto a estado em disco — sempre faz load_all_from_cache.
    """
    global _registry
    _registry = SchemaRegistry(audit_conn)
    _registry.load_all_from_cache()
    return _registry


def get_schema_registry() -> SchemaRegistry:
    """Acessa o singleton. Lança RuntimeError se não inicializado."""
    if _registry is None:
        raise RuntimeError(
            "SchemaRegistry não inicializado — chame init_schema_registry() no boot.",
        )
    return _registry


def boot_refresh_all(
    client: Any,
    registry: SchemaRegistry,
    data_sources: dict[str, str],
) -> list[ChangeReport]:
    """Para cada (base_label, data_source_id) em ``data_sources``, faz refresh.

    Bloqueante — chamado no splash screen quando cache está vazio
    (Fase 1). Erros de fetch numa base individual não abortam as outras:
    a base falhada gera um ChangeReport(kind="changed", changed=["__error__"])
    e o boot continua.
    """
    reports: list[ChangeReport] = []
    for base_label, data_source_id in data_sources.items():
        try:
            report = registry.refresh_from_api(
                base_label, data_source_id, client,
            )
            reports.append(report)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Refresh de schema falhou para %s (%s): %s",
                base_label, data_source_id, exc,
            )
            reports.append(
                ChangeReport(kind="changed", base=base_label, changed=("__error__",)),
            )
    return reports


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _dict_to_propspec(prop_dict: dict[str, Any]) -> PropSpec:
    """Constrói um PropSpec a partir do dict canônico do parser.

    Fase 3:
    - cor_por_valor populada via notion_colors (mapeamento Notion → hex).
    - target_base resolvido via DATA_SOURCES (lookup reverso de
      data_source_id → base_label) para que double-click em relations
      navegue corretamente.

    Campos restantes do PropSpec não cobertos pelo schema dinâmico
    (largura_col, mono, formato, min_width_px) ficam com valores default —
    overrides custom podem entrar em labels_overrides.py em fase futura.
    """
    from notion_bulk_edit.config import DATA_SOURCES
    from notion_rpadv.theme.notion_colors import color_to_hex

    opcoes_dicts = prop_dict.get("opcoes", []) or []
    opcoes = tuple(opt.get("name", "") for opt in opcoes_dicts)

    # cor_por_valor: traduz cor nominal do Notion para hex do RPADV.
    cor_por_valor: dict[str, str] = {
        opt.get("name", ""): color_to_hex(opt.get("color", "default"))
        for opt in opcoes_dicts
        if opt.get("name")
    }

    # target_base: lookup reverso de data_source_id → base_label.
    # Usado por delegates/_on_table_double_clicked para navegação.
    target_base = ""
    target_dsid = prop_dict.get("target_data_source_id", "")
    if target_dsid:
        for label, dsid in DATA_SOURCES.items():
            if dsid == target_dsid:
                target_base = label
                break

    return PropSpec(
        notion_name=prop_dict.get("notion_name", ""),
        tipo=prop_dict.get("tipo", "rich_text"),
        label=prop_dict.get("label", prop_dict.get("notion_name", "")),
        editavel=prop_dict.get("editavel", True),
        obrigatorio=prop_dict.get("obrigatorio", False),
        opcoes=opcoes,
        cor_por_valor=cor_por_valor,
        target_base=target_base,
    )


def _diff_properties(
    old: dict[str, Any], new: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """Compara dois schemas parseados e retorna (added, removed, changed) keys.

    "changed" inclui qualquer mudança em tipo, label, editavel, obrigatorio,
    default_visible, default_order ou nas opções (nome ou cor) de selects.
    """
    old_props: dict[str, Any] = old.get("properties", {})
    new_props: dict[str, Any] = new.get("properties", {})
    added = sorted(set(new_props.keys()) - set(old_props.keys()))
    removed = sorted(set(old_props.keys()) - set(new_props.keys()))
    changed: list[str] = []
    for key in sorted(set(old_props.keys()) & set(new_props.keys())):
        if old_props[key] != new_props[key]:
            changed.append(key)
    return added, removed, changed
