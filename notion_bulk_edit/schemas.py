"""Esquemas das 4 bases Notion do escritório RPADV.

Cada propriedade tem:
- notion_name: nome exato da propriedade no Notion (case-sensitive)
- tipo: tipo de propriedade da API Notion
- editavel: se o app permite edição inline
- obrigatorio: se é obrigatório na validação de importação
- opcoes: para selects — lista de valores válidos
- label: rótulo em português para a UI
- largura_col: largura sugerida para a coluna na tabela (em px ou %)

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
    # Fase 1 — schema dinâmico: re-export de OptionSpec sem ciclo de import
    # em runtime. Em runtime, expomos via PEP 562 __getattr__ no fim do módulo.
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
    # BUG-V3: which base to look up when tipo == 'relation'
    target_base: str = ""
    # §3.1: explicit minimum column width in pixels. The QHeaderView resize
    # logic uses this as a floor so labels like "Cliente principal" never
    # truncate to "Cliente Princip.". Falls back to a font-aware estimate
    # when None.
    min_width_px: Optional[int] = None


# ---------------------------------------------------------------------------
# Vocabulários controlados (espelham brand.css / protótipo)
# ---------------------------------------------------------------------------

TRIBUNAIS = ("TJDFT", "TRT/10", "TRT/2", "TRF/1", "JFDF", "STF", "STJ", "TST")
FASES     = ("Conhecimento", "Recurso", "Execução", "Cumprimento", "Sobrestado", "Trânsito em julgado")
STATUS_PROC   = ("Ativo", "Sobrestado", "Suspenso", "Arquivado")
INSTANCIAS    = ("1ª", "2ª", "Superior")
PRIORIDADES   = ("Crítica", "Alta", "Normal", "Baixa")
STATUS_TAREFA = ("A fazer", "Em andamento", "Aguardando", "Concluída")
CATEGORIAS_CATALOGO = ("Petição", "Recurso", "Audiência", "Cálculo", "Reunião", "Outros")
AREAS_CATALOGO      = ("Trabalhista", "Empresarial", "Geral")
CIDADES_UF = (
    "Brasília/DF", "Taguatinga/DF", "Ceilândia/DF", "Águas Claras/DF",
    "Sobradinho/DF", "Planaltina/DF", "Samambaia/DF", "Gama/DF",
    "Goiânia/GO", "Outro",
)

# Cores por valor para chips na UI (mapeadas nos QSS)
_COR_TRIBUNAL: dict[str, str] = {
    "STF": "purple", "STJ": "purple", "TST": "purple",
    "TJDFT": "blue", "TRT/10": "blue", "TRT/2": "blue",
    "TRF/1": "green", "JFDF": "green",
}
_COR_FASE: dict[str, str] = {
    "Conhecimento": "gray", "Recurso": "orange", "Execução": "yellow",
    "Cumprimento": "petrol", "Sobrestado": "red", "Trânsito em julgado": "green",
}
_COR_STATUS_PROC: dict[str, str] = {
    "Ativo": "green", "Sobrestado": "red", "Suspenso": "orange", "Arquivado": "gray",
}
_COR_INSTANCIA: dict[str, str] = {
    "1ª": "gray", "2ª": "blue", "Superior": "purple",
}
_COR_PRIORIDADE: dict[str, str] = {
    "Crítica": "red", "Alta": "orange", "Normal": "gray", "Baixa": "petrol",
}
_COR_STATUS_TAREFA: dict[str, str] = {
    "A fazer": "gray", "Em andamento": "blue", "Aguardando": "yellow", "Concluída": "green",
}
_COR_CATEGORIA: dict[str, str] = {v: "petrol" for v in CATEGORIAS_CATALOGO}
_COR_AREA: dict[str, str] = {
    "Trabalhista": "blue", "Empresarial": "purple", "Geral": "gray",
}

# ---------------------------------------------------------------------------
# Schemas das bases
#
# Fase 1 — schema dinâmico: o dict literal abaixo virou ``_LEGACY_SCHEMAS``
# (privado). O símbolo público ``SCHEMAS`` é um proxy (definido após o dict)
# que devolve do registry dinâmico quando ``USE_DYNAMIC_SCHEMA`` está True
# e a base está em ``DYNAMIC_BASES``; caso contrário, devolve do dict legado.
# Removido na Fase 3 (assumido todas as bases migradas).
# ---------------------------------------------------------------------------

_LEGACY_SCHEMAS: dict[str, dict[str, PropSpec]] = {

    "Processos": {
        "cnj": PropSpec(
            notion_name="Número do processo",
            tipo="title",
            label="CNJ",
            editavel=True,
            obrigatorio=True,
            largura_col="20%",
            mono=True,
            min_width_px=200,  # §3.1
        ),
        "tribunal": PropSpec(
            notion_name="Tribunal",
            tipo="select",
            label="Tribunal",
            editavel=True,
            obrigatorio=True,
            opcoes=TRIBUNAIS,
            largura_col="8%",
            cor_por_valor=_COR_TRIBUNAL,
            min_width_px=90,  # §3.1
        ),
        "instancia": PropSpec(
            notion_name="Instância",
            tipo="select",
            label="Instância",
            editavel=True,
            opcoes=INSTANCIAS,
            largura_col="8%",
            cor_por_valor=_COR_INSTANCIA,
            min_width_px=96,
        ),
        "fase": PropSpec(
            notion_name="Fase",
            tipo="select",
            label="Fase",
            editavel=True,
            opcoes=FASES,
            largura_col="12%",
            cor_por_valor=_COR_FASE,
            min_width_px=130,  # §3.1
        ),
        "status": PropSpec(
            notion_name="Status",
            tipo="select",
            label="Status",
            editavel=True,
            opcoes=STATUS_PROC,
            largura_col="9%",
            cor_por_valor=_COR_STATUS_PROC,
            min_width_px=90,  # §3.1
        ),
        "cliente": PropSpec(
            notion_name="Clientes",
            tipo="relation",
            label="Cliente principal",
            editavel=False,  # BUG-N11: relation editor not yet implemented
            largura_col="17%",
            target_base="Clientes",  # BUG-V3
            min_width_px=200,  # §3.1
        ),
        "parte_contraria": PropSpec(
            notion_name="Partes adversas",
            tipo="multi_select",
            label="Parte contrária",
            editavel=True,
            largura_col="15%",
            min_width_px=180,
        ),
        "distribuicao": PropSpec(
            notion_name="Data de distribuição",
            tipo="date",
            label="Distribuição",
            editavel=True,
            largura_col="10%",
            formato="BR_DATE",
            min_width_px=130,
        ),
        "valor_causa": PropSpec(
            notion_name="Valor da Causa",
            tipo="number",
            label="Valor da causa",
            editavel=True,
            largura_col="11%",
            formato="BRL",
            min_width_px=140,
        ),
        "responsavel": PropSpec(
            notion_name="Responsável",
            tipo="people",
            label="Resp.",
            editavel=True,
            largura_col="5%",
            min_width_px=100,  # §3.1
        ),
        # §3.8: reflexive relation — when set, the row is a recurso/sub-process
        # of the referenced CNJ. Hidden from default view (largura_col="0")
        # because the CnjDelegate already surfaces the parent CNJ inline.
        "processo_pai": PropSpec(
            notion_name="Processo pai",
            tipo="relation",
            label="Processo pai",
            editavel=False,
            largura_col="0",
            target_base="Processos",
        ),
        "tema955": PropSpec(
            notion_name="Tema 955 — Sobrestado",
            tipo="checkbox",
            label="Tema 955",
            editavel=True,
            largura_col="5%",
        ),
        "sobrestado_tj": PropSpec(
            notion_name="Sobrestado - TJ conexa",
            tipo="checkbox",
            label="Sob. TJ",
            editavel=True,
            largura_col="5%",
        ),
        "sobrestado_irr": PropSpec(
            notion_name="Sobrestado - IRR 20",
            tipo="checkbox",
            label="Sob. IRR",
            editavel=True,
            largura_col="5%",
        ),
        "observacoes": PropSpec(
            notion_name="Observações",
            tipo="rich_text",
            label="Observações",
            editavel=True,
            largura_col="0",  # hidden in default view
        ),
    },

    "Clientes": {
        "nome": PropSpec(
            notion_name="Nome",
            tipo="title",
            label="Nome",
            editavel=True,
            obrigatorio=True,
            largura_col="24%",
            min_width_px=240,
        ),
        "cpf": PropSpec(
            notion_name="CPF/CNPJ",
            tipo="rich_text",
            label="CPF/CNPJ",
            editavel=True,
            obrigatorio=True,
            largura_col="12%",
            mono=True,
            min_width_px=140,
        ),
        "email": PropSpec(
            notion_name="E-mail",
            tipo="email",
            label="E-mail",
            editavel=True,
            largura_col="20%",
            min_width_px=200,
        ),
        "telefone": PropSpec(
            notion_name="Telefone",
            tipo="phone_number",
            label="Telefone",
            editavel=True,
            largura_col="12%",
            mono=True,
            min_width_px=130,
        ),
        "falecido": PropSpec(
            notion_name="Falecido",
            tipo="checkbox",
            label="Falecido",
            editavel=True,
            largura_col="5%",
            min_width_px=90,
        ),
        "cidade": PropSpec(
            notion_name="Cidade/UF",
            tipo="select",
            label="Cidade/UF",
            editavel=True,
            opcoes=CIDADES_UF,
            largura_col="13%",
            min_width_px=140,
        ),
        "cadastrado": PropSpec(
            notion_name="Cadastrado em",
            tipo="date",
            label="Cadastro",
            editavel=False,
            largura_col="10%",
            formato="BR_DATE",
            min_width_px=110,
        ),
        "n_processos": PropSpec(
            notion_name="Nº de Processos",
            tipo="rollup",
            label="Nº processos",
            editavel=False,
            largura_col="9%",
            min_width_px=100,  # §3.6: numeric, alinhado à direita
        ),
        # §3.7: reflexive relation — when filled, the cliente é sucessor do
        # registro relacionado (espólio, herdeiro, sucessão empresarial, etc.).
        "sucessor_de": PropSpec(
            notion_name="Sucessor de",
            tipo="relation",
            label="Sucessor de",
            editavel=False,
            largura_col="14%",
            target_base="Clientes",
            min_width_px=160,
        ),
        "notas": PropSpec(
            notion_name="Notas",
            tipo="rich_text",
            label="Notas",
            editavel=True,
            largura_col="0",
        ),
    },

    "Tarefas": {
        "titulo": PropSpec(
            notion_name="Tarefa",
            tipo="title",
            label="Tarefa",
            editavel=True,
            obrigatorio=True,
            largura_col="28%",
            min_width_px=280,  # §3.1
        ),
        "prazo_fatal": PropSpec(
            notion_name="Prazo fatal",
            tipo="date",
            label="Prazo fatal",
            editavel=True,
            obrigatorio=True,
            largura_col="14%",
            formato="BR_DATE",
            min_width_px=110,  # §3.1 ("Prazo" → 96; "Prazo fatal" needs more)
        ),
        "prioridade": PropSpec(
            notion_name="Prioridade",
            tipo="select",
            label="Prioridade",
            editavel=True,
            opcoes=PRIORIDADES,
            largura_col="10%",
            cor_por_valor=_COR_PRIORIDADE,
            min_width_px=110,
        ),
        "status": PropSpec(
            notion_name="Status",
            tipo="select",
            label="Status",
            editavel=True,
            opcoes=STATUS_TAREFA,
            largura_col="12%",
            cor_por_valor=_COR_STATUS_TAREFA,
            min_width_px=120,
        ),
        "processo": PropSpec(
            notion_name="Processo",
            tipo="relation",
            label="Processo",
            editavel=False,  # BUG-N11: relation editor not yet implemented
            largura_col="17%",
            mono=True,
            target_base="Processos",  # BUG-V3
            min_width_px=200,
        ),
        "cliente": PropSpec(
            notion_name="Cliente",
            tipo="rollup",
            label="Cliente",
            editavel=False,
            largura_col="14%",
            min_width_px=160,
        ),
        "responsavel": PropSpec(
            notion_name="Responsável",
            tipo="people",
            label="Resp.",
            editavel=True,
            largura_col="5%",
            min_width_px=100,  # §3.1
        ),
        "catalogo_tipo": PropSpec(
            notion_name="Tipo de tarefa",
            tipo="relation",
            label="Tipo (catálogo)",
            editavel=False,  # BUG-N11: relation editor not yet implemented
            largura_col="0",
            target_base="Catalogo",  # BUG-V3
        ),
    },

    "Catalogo": {
        "titulo": PropSpec(
            notion_name="Nome",
            tipo="title",
            label="Tipo de tarefa",
            editavel=True,
            obrigatorio=True,
            largura_col="36%",
        ),
        "categoria": PropSpec(
            notion_name="Categoria",
            tipo="select",
            label="Categoria",
            editavel=True,
            opcoes=CATEGORIAS_CATALOGO,
            largura_col="14%",
            cor_por_valor=_COR_CATEGORIA,
        ),
        "area": PropSpec(
            notion_name="Área",
            tipo="select",
            label="Área",
            editavel=True,
            opcoes=AREAS_CATALOGO,
            largura_col="14%",
            cor_por_valor=_COR_AREA,
        ),
        "tempo_estimado": PropSpec(
            notion_name="Tempo Estimado",
            tipo="rich_text",
            label="Tempo médio",
            editavel=True,
            largura_col="12%",
            mono=True,
        ),
        "responsavel_padrao": PropSpec(
            notion_name="Responsável Padrão",
            tipo="people",
            label="Resp. padrão",
            editavel=True,
            largura_col="14%",
        ),
        "revisado": PropSpec(
            notion_name="Última Revisão",
            tipo="date",
            label="Última revisão",
            editavel=True,
            largura_col="12%",
            formato="BR_DATE",
        ),
    },
}


# ---------------------------------------------------------------------------
# Fase 1 — schema dinâmico: proxy de SCHEMAS
# ---------------------------------------------------------------------------

# Lista canônica das 4 bases conhecidas. Fase 4b adiciona "Documentos".
_KNOWN_BASES: tuple[str, ...] = ("Processos", "Clientes", "Tarefas", "Catalogo")


class _BaseSchemaProxy(Mapping[str, PropSpec]):
    """Proxy para o dict de propriedades de uma base.

    Em cada acesso, decide se serve do registry dinâmico (Fase 0) ou
    cai no ``_LEGACY_SCHEMAS`` hardcoded. A decisão depende de:
      - ``config.USE_DYNAMIC_SCHEMA`` (flag global)
      - ``config.DYNAMIC_BASES`` (whitelist por-base, ativada na Fase 2)

    O ``_backing()`` recalcula a cada acesso porque os testes flipam as
    flags em runtime; cachear quebraria a expectativa.
    """

    def __init__(self, base_name: str) -> None:
        self._base = base_name

    def _backing(self) -> dict[str, PropSpec]:
        # Imports adiados para evitar ciclo durante o load do módulo.
        from notion_bulk_edit import config

        use_dynamic = getattr(config, "USE_DYNAMIC_SCHEMA", False)
        dynamic_bases = getattr(config, "DYNAMIC_BASES", set())
        if use_dynamic and self._base in dynamic_bases:
            try:
                from notion_bulk_edit.schema_registry import get_schema_registry
                schema = get_schema_registry().schema_for_base(self._base)
                if schema:
                    return schema
            except RuntimeError:
                # Singleton não inicializado — fallback silencioso.
                pass
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Falha ao consultar schema dinâmico de %s; "
                    "caindo no _LEGACY_SCHEMAS.", self._base,
                )
        return _LEGACY_SCHEMAS.get(self._base, {})

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
    """Fase 1 — schema dinâmico: re-export lazy de OptionSpec.

    Resolve em runtime para evitar ciclo de import com schema_registry
    (que importa PropSpec deste módulo no top-level).
    """
    if name == "OptionSpec":
        from notion_bulk_edit.schema_registry import OptionSpec
        return OptionSpec
    raise AttributeError(
        f"module 'notion_bulk_edit.schemas' has no attribute {name!r}",
    )


# ---------------------------------------------------------------------------
# Helpers públicos (mantêm a API legada — agora consultam o proxy)
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


def colunas_visiveis(base: str) -> list[str]:
    """Retorna as chaves das colunas visíveis por default (largura_col != '0')."""
    schema = SCHEMAS.get(base, {})
    return [k for k, s in schema.items() if s.largura_col != "0"]


def vocabulario(base: str, key: str) -> tuple[str, ...]:
    """Retorna as opções válidas de um campo select."""
    spec = get_prop(base, key)
    if spec is None:
        return ()
    return spec.opcoes
