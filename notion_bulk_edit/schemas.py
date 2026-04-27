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

from dataclasses import dataclass, field
from typing import Any, Optional


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
# ---------------------------------------------------------------------------

SCHEMAS: dict[str, dict[str, PropSpec]] = {

    "Processos": {
        "cnj": PropSpec(
            notion_name="CNJ",
            tipo="title",
            label="CNJ",
            editavel=True,
            obrigatorio=True,
            largura_col="20%",
            mono=True,
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
        ),
        "instancia": PropSpec(
            notion_name="Instância",
            tipo="select",
            label="Instância",
            editavel=True,
            opcoes=INSTANCIAS,
            largura_col="8%",
            cor_por_valor=_COR_INSTANCIA,
        ),
        "fase": PropSpec(
            notion_name="Fase",
            tipo="select",
            label="Fase",
            editavel=True,
            opcoes=FASES,
            largura_col="12%",
            cor_por_valor=_COR_FASE,
        ),
        "status": PropSpec(
            notion_name="Status",
            tipo="select",
            label="Status",
            editavel=True,
            opcoes=STATUS_PROC,
            largura_col="9%",
            cor_por_valor=_COR_STATUS_PROC,
        ),
        "cliente": PropSpec(
            notion_name="Cliente",
            tipo="relation",
            label="Cliente principal",
            editavel=True,
            largura_col="17%",
        ),
        "parte_contraria": PropSpec(
            notion_name="Parte Contrária",
            tipo="rich_text",
            label="Parte contrária",
            editavel=True,
            largura_col="15%",
        ),
        "distribuicao": PropSpec(
            notion_name="Distribuição",
            tipo="date",
            label="Distribuição",
            editavel=True,
            largura_col="10%",
            formato="BR_DATE",
        ),
        "valor_causa": PropSpec(
            notion_name="Valor da Causa",
            tipo="number",
            label="Valor da causa",
            editavel=True,
            largura_col="11%",
            formato="BRL",
        ),
        "responsavel": PropSpec(
            notion_name="Responsável",
            tipo="people",
            label="Resp.",
            editavel=True,
            largura_col="5%",
        ),
        "tema955": PropSpec(
            notion_name="Tema 955",
            tipo="checkbox",
            label="Tema 955",
            editavel=True,
            largura_col="5%",
        ),
        "sucessao": PropSpec(
            notion_name="Sucessão",
            tipo="checkbox",
            label="Sucessão",
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
        ),
        "cpf": PropSpec(
            notion_name="CPF",
            tipo="rich_text",
            label="CPF",
            editavel=True,
            obrigatorio=True,
            largura_col="12%",
            mono=True,
        ),
        "email": PropSpec(
            notion_name="E-mail",
            tipo="email",
            label="E-mail",
            editavel=True,
            largura_col="20%",
        ),
        "telefone": PropSpec(
            notion_name="Telefone",
            tipo="phone_number",
            label="Telefone",
            editavel=True,
            largura_col="12%",
            mono=True,
        ),
        "falecido": PropSpec(
            notion_name="Falecido",
            tipo="checkbox",
            label="Falecido",
            editavel=True,
            largura_col="5%",
        ),
        "cidade": PropSpec(
            notion_name="Cidade/UF",
            tipo="select",
            label="Cidade/UF",
            editavel=True,
            opcoes=CIDADES_UF,
            largura_col="13%",
        ),
        "cadastrado": PropSpec(
            notion_name="Cadastrado em",
            tipo="date",
            label="Cadastro",
            editavel=False,   # geralmente data de criação
            largura_col="10%",
            formato="BR_DATE",
        ),
        "n_processos": PropSpec(
            notion_name="Nº de Processos",
            tipo="rollup",
            label="Nº processos",
            editavel=False,
            largura_col="9%",
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
            notion_name="Título",
            tipo="title",
            label="Tarefa",
            editavel=True,
            obrigatorio=True,
            largura_col="28%",
        ),
        "prazo_fatal": PropSpec(
            notion_name="Prazo Fatal",
            tipo="date",
            label="Prazo fatal",
            editavel=True,
            obrigatorio=True,
            largura_col="14%",
            formato="BR_DATE",
        ),
        "prioridade": PropSpec(
            notion_name="Prioridade",
            tipo="select",
            label="Prioridade",
            editavel=True,
            opcoes=PRIORIDADES,
            largura_col="10%",
            cor_por_valor=_COR_PRIORIDADE,
        ),
        "status": PropSpec(
            notion_name="Status",
            tipo="select",
            label="Status",
            editavel=True,
            opcoes=STATUS_TAREFA,
            largura_col="12%",
            cor_por_valor=_COR_STATUS_TAREFA,
        ),
        "processo": PropSpec(
            notion_name="Processo",
            tipo="relation",
            label="Processo",
            editavel=True,
            largura_col="17%",
            mono=True,
        ),
        "cliente": PropSpec(
            notion_name="Cliente",
            tipo="rollup",   # derivado da relação Processo
            label="Cliente",
            editavel=False,
            largura_col="14%",
        ),
        "responsavel": PropSpec(
            notion_name="Responsável",
            tipo="people",
            label="Resp.",
            editavel=True,
            largura_col="5%",
        ),
        "catalogo_tipo": PropSpec(
            notion_name="Tipo (Catálogo)",
            tipo="relation",
            label="Tipo (catálogo)",
            editavel=True,
            largura_col="0",
        ),
    },

    "Catalogo": {
        "titulo": PropSpec(
            notion_name="Título",
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
