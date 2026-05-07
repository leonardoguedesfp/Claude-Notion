"""Testes dos tipos do Round 10 — ``TagApp`` e ``VeredictoPub``.

Foco: invariantes da API pública (sufixo " - App" hardcoded,
deduplicação por tag_base, mapping de propriedades para slugs).
"""
from __future__ import annotations

import pytest

from notion_rpadv.services.dje_regras import SUFIXO_APP, TagApp, VeredictoPub
from notion_rpadv.services.dje_regras.tipos import _slug


# ---------------------------------------------------------------------------
# TagApp — sufixo hardcoded
# ---------------------------------------------------------------------------


def test_tagapp_sufixo_app_hardcoded() -> None:
    """A property ``tag`` sempre acrescenta " - App" ao tag_base."""
    t = TagApp(propriedade="Alerta contadoria", tag_base="Foo", regra="AC99")
    assert t.tag == "Foo - App"
    assert SUFIXO_APP == " - App"


def test_tagapp_eq_baseado_nos_3_campos() -> None:
    """Dataclass frozen deve gerar igualdade estrutural pelos 3 campos."""
    a = TagApp("Alerta contadoria", "Foo", "AC99")
    b = TagApp("Alerta contadoria", "Foo", "AC99")
    c = TagApp("Alerta contadoria", "Foo", "AC10")
    assert a == b
    assert a != c


def test_tagapp_e_imutavel() -> None:
    """Como dataclass frozen, atribuição depois da criação levanta."""
    t = TagApp("Alerta contadoria", "Foo", "AC99")
    with pytest.raises(Exception):  # noqa: PT011 — frozen levanta FrozenInstanceError
        t.tag_base = "Bar"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _slug
# ---------------------------------------------------------------------------


def test_slug_para_3_propriedades() -> None:
    assert _slug("Tarefa advogado") == "tarefa_advogado"
    assert _slug("Tarefa contadoria") == "tarefa_contadoria"
    assert _slug("Alerta contadoria") == "alerta_contadoria"


def test_slug_levanta_para_propriedade_invalida() -> None:
    with pytest.raises(ValueError, match="Propriedade desconhecida"):
        _slug("FooBar")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# VeredictoPub — adicionar / dedup / no-op com None
# ---------------------------------------------------------------------------


def test_veredicto_inicia_vazio() -> None:
    v = VeredictoPub()
    assert v.tarefa_advogado == []
    assert v.tarefa_contadoria == []
    assert v.alerta_contadoria == []


def test_veredicto_adicionar_none_e_noop() -> None:
    v = VeredictoPub()
    v.adicionar(None)
    assert v.alerta_contadoria == []


def test_veredicto_adicionar_distribui_por_propriedade() -> None:
    v = VeredictoPub()
    v.adicionar(TagApp("Tarefa advogado", "X", "TA99"))
    v.adicionar(TagApp("Tarefa contadoria", "Y", "TC99"))
    v.adicionar(TagApp("Alerta contadoria", "Z", "AC99"))
    assert [t.tag_base for t in v.tarefa_advogado] == ["X"]
    assert [t.tag_base for t in v.tarefa_contadoria] == ["Y"]
    assert [t.tag_base for t in v.alerta_contadoria] == ["Z"]


def test_veredicto_dedup_por_tag_base_dentro_da_propriedade() -> None:
    """Duas regras diferentes que emitem a mesma tag_base na mesma
    propriedade só geram uma entrada — sobrevive a primeira."""
    v = VeredictoPub()
    v.adicionar(TagApp("Alerta contadoria", "Cidade desatualizada", "AC15"))
    v.adicionar(TagApp("Alerta contadoria", "Cidade desatualizada", "AC16"))
    assert len(v.alerta_contadoria) == 1
    assert v.alerta_contadoria[0].regra == "AC15"


def test_veredicto_nao_dedup_entre_propriedades() -> None:
    """Mesma tag_base em propriedades diferentes coexiste — improvável
    na vida real, mas a invariante é por-propriedade."""
    v = VeredictoPub()
    v.adicionar(TagApp("Tarefa advogado", "Foo", "TA99"))
    v.adicionar(TagApp("Tarefa contadoria", "Foo", "TC99"))
    assert len(v.tarefa_advogado) == 1
    assert len(v.tarefa_contadoria) == 1


def test_veredicto_estender_lista() -> None:
    v = VeredictoPub()
    v.estender([
        TagApp("Alerta contadoria", "A", "AC01"),
        TagApp("Alerta contadoria", "B", "AC02"),
        TagApp("Alerta contadoria", "A", "AC03"),  # dedup com AC01
    ])
    assert [t.tag_base for t in v.alerta_contadoria] == ["A", "B"]


def test_veredicto_tags_por_propriedade_inclui_sufixo_app() -> None:
    v = VeredictoPub()
    v.adicionar(TagApp("Tarefa advogado", "Analisar acórdão", "TA02"))
    v.adicionar(TagApp("Alerta contadoria", "Vara desatualizada", "AC18"))
    pacote = v.tags_por_propriedade()
    assert pacote == {
        "Tarefa advogado": ["Analisar acórdão - App"],
        "Tarefa contadoria": [],
        "Alerta contadoria": ["Vara desatualizada - App"],
    }


def test_veredicto_listas_vazias_indicam_limpar() -> None:
    """Listas vazias no resultado sinalizam que a propriedade deve ser
    limpa na pub (multi_select com lista vazia no payload do Notion).
    Não é caso especial — o adapter trata uniformemente."""
    v = VeredictoPub()
    pacote = v.tags_por_propriedade()
    assert pacote["Tarefa advogado"] == []
    assert pacote["Tarefa contadoria"] == []
    assert pacote["Alerta contadoria"] == []
