"""Tipos do Round 10 — ``TagApp``, ``VeredictoPub``, ``PropriedadeNotion``.

Round 10 (2026-05-07) substituiu a propriedade única ``Alerta contadoria
(app)`` por **três** multi-selects no schema do Notion:

- ``Tarefa advogado``     — tarefas técnicas que o advogado precisa fazer
                            (analisar sentença, analisar acórdão).
- ``Tarefa contadoria``   — eventos do processo que a contadoria precisa
                            registrar (distribuição, pauta de julgamento).
- ``Alerta contadoria``   — desconformidades de cadastro detectadas pela
                            comparação Pub × Proc.

Todas as tags emitidas pelo app terminam com ``" - App"``. O sufixo é
**hardcoded** no construtor de :class:`TagApp` — não há flag de
configuração — pra que o vocabulário do Notion não colida com tags que
um operador humano possa criar manualmente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: As três propriedades do Notion que recebem tags do app.
PropriedadeNotion = Literal[
    "Tarefa advogado",
    "Tarefa contadoria",
    "Alerta contadoria",
]

#: Sufixo hardcoded em todas as tags emitidas pelo app. Imutável por
#: design — ver docstring do módulo.
SUFIXO_APP: str = " - App"


@dataclass(frozen=True)
class TagApp:
    """Uma tag a ser gravada numa das três propriedades multi-select.

    Atributos:
        propriedade: a qual propriedade do Notion essa tag pertence.
        tag_base: nome da tag **sem** sufixo. Ex.: ``"Cidade
            desatualizada"``.
        regra: código da regra que disparou a tag. Ex.: ``"AC15"``,
            ``"TC01"``. Usado pra telemetria e debug — o Notion não
            recebe esse campo.

    A tag final (com sufixo) é exposta via :attr:`tag`.
    """
    propriedade: PropriedadeNotion
    tag_base: str
    regra: str

    @property
    def tag(self) -> str:
        """Tag final com sufixo ``" - App"`` hardcoded.

        É impossível emitir uma tag sem o sufixo — o construtor não
        recebe ``tag`` direto, apenas ``tag_base``, e esta property é
        a única forma de obter o nome completo.
        """
        return f"{self.tag_base}{SUFIXO_APP}"


# ---------------------------------------------------------------------------
# Slug interno: PropriedadeNotion → atributo do VeredictoPub
# ---------------------------------------------------------------------------

_SLUGS: dict[PropriedadeNotion, str] = {
    "Tarefa advogado": "tarefa_advogado",
    "Tarefa contadoria": "tarefa_contadoria",
    "Alerta contadoria": "alerta_contadoria",
}


def _slug(propriedade: PropriedadeNotion) -> str:
    """Converte ``PropriedadeNotion`` no nome do atributo correspondente
    em :class:`VeredictoPub`. Levanta ``ValueError`` para valores fora
    do enum (defesa estática contra futuras renomeações).
    """
    try:
        return _SLUGS[propriedade]
    except KeyError as exc:
        raise ValueError(f"Propriedade desconhecida: {propriedade!r}") from exc


@dataclass
class VeredictoPub:
    """Conjunto agregado de tags de uma publicação, separado por
    propriedade do Notion.

    Cada propriedade carrega uma lista de :class:`TagApp` em ordem de
    chegada. Duplicatas por ``tag_base`` (mesma tag emitida por
    regras diferentes) são automaticamente filtradas em :meth:`adicionar`
    — sobrevive a primeira ``TagApp`` da lista, e a regra a que ela
    aponta é mantida no atributo ``regra``.
    """
    tarefa_advogado: list[TagApp] = field(default_factory=list)
    tarefa_contadoria: list[TagApp] = field(default_factory=list)
    alerta_contadoria: list[TagApp] = field(default_factory=list)

    def adicionar(self, tag: TagApp | None) -> None:
        """Adiciona uma tag à propriedade certa, deduplicando por
        ``tag_base`` dentro daquela propriedade. Aceita ``None`` (no-op)
        pra simplificar o orquestrador.
        """
        if tag is None:
            return
        bucket: list[TagApp] = getattr(self, _slug(tag.propriedade))
        if any(t.tag_base == tag.tag_base for t in bucket):
            return
        bucket.append(tag)

    def estender(self, tags: list[TagApp]) -> None:
        """Adiciona múltiplas tags via :meth:`adicionar`. Conveniência
        pra regras que retornam lista (poucas, mas existem)."""
        for t in tags:
            self.adicionar(t)

    def tags_por_propriedade(self) -> dict[PropriedadeNotion, list[str]]:
        """Devolve mapa ``{propriedade: [tag_completa, ...]}``, com
        sufixo ``" - App"`` aplicado, pronto pra serializar no payload
        Notion. Listas vazias sinalizam "limpar a propriedade na pub".
        """
        return {
            "Tarefa advogado": [t.tag for t in self.tarefa_advogado],
            "Tarefa contadoria": [t.tag for t in self.tarefa_contadoria],
            "Alerta contadoria": [t.tag for t in self.alerta_contadoria],
        }
