"""Round 4 (29-abr-2026) — layout-padrão por base.

Fonte da verdade pra (a) ordem das colunas visíveis quando o usuário não
tem prefs em ``meta_user_columns``, e (b) larguras iniciais aplicadas pelo
view ao montar a tabela. Slugs ausentes do dict ficam ocultos por default;
o usuário pode habilitar via picker.

Substitui a heurística antiga em
``notion_bulk_edit/schema_parser._is_default_visible`` (que escolhia
default_visible com base no tipo da propriedade) — agora a decisão de
visibilidade é editorial por base, não algorítmica.

A migração que descarta ``meta_user_columns`` ao subir uma versão nova
deste layout é feita por
``notion_rpadv.cache.db.wipe_user_columns_if_layout_changed`` chamado no
boot da MainWindow. Bumpe ``LAYOUT_VERSION`` sempre que mudar slug, ordem
ou largura aqui — todos os usuários têm prefs descartadas no próximo boot.
"""
from __future__ import annotations

from typing import Final

# Incrementar quando alterar slugs / ordem / larguras em DEFAULT_LAYOUTS.
# meta.layout_version é comparado contra este número no boot; mismatch
# dispara wipe de meta_user_columns pra reaplicar o novo layout a todos.
LAYOUT_VERSION: Final = 1


# (slug, width_px) na ordem visual desejada.
# Todos os slugs aqui ficam visíveis; o que NÃO está aqui fica oculto por
# default (mas continua disponível pra habilitar via picker).
DEFAULT_LAYOUTS: Final[dict[str, list[tuple[str, int]]]] = {
    "Clientes": [
        ("nome",                    280),
        ("telefone",                180),
        ("processos",               240),
        ("e_mail",                  180),
        ("data_de_aposentadoria",   130),
        ("data_de_ingresso_no_bb",  130),
        ("situacao_funcional",      140),
    ],
    "Processos": [
        ("numero_do_processo",   280),
        ("clientes",             240),
        ("fase",                 140),
        ("tipo_de_processo",     140),
        ("tipo_de_acao",         220),
        ("instancia",            140),
        ("detalhamento_da_acao", 280),
    ],
    "Tarefas": [
        ("tarefa",             280),
        ("tipo_de_tarefa",     240),
        ("cliente",            240),
        ("processo",            240),
        ("status",             140),
        ("area",               140),
        ("prioridade",         140),
        ("data_de_publicacao", 130),
        ("prazo_fatal",        130),
        ("responsavel",        160),
    ],
    "Catalogo": [
        ("nome",        280),
        ("categoria",   220),
        ("observacoes", 280),
    ],
}


def default_visible_slugs(base: str) -> list[str]:
    """Slugs visíveis na ordem do layout-padrão para uma base.

    Lista vazia se a base não está em ``DEFAULT_LAYOUTS`` — caller cai na
    heurística legada do schema_parser (default_visible por tipo).
    """
    return [slug for slug, _w in DEFAULT_LAYOUTS.get(base, [])]


def default_width(base: str, slug: str) -> int | None:
    """Largura px do slug no layout-padrão. None se slug não está no layout
    (caller usa o piso calculado por font metrics)."""
    for s, w in DEFAULT_LAYOUTS.get(base, []):
        if s == slug:
            return w
    return None
