"""Orquestrador do Round 10 — chama as 30 regras e produz um
:class:`VeredictoPub`.

Uso típico (a partir do mapper)::

    veredicto = aplicar_todas_regras(
        publicacao, processo_record, cache_conn=cache_conn,
    )
    payload.update({
        prop: _multi_select_prop(tags)
        for prop, tags in veredicto.tags_por_propriedade().items()
    })

A camada base (TA01-TC02) e o monitoramento (AC01-AC26) são chamados
em sequência e jogam tags no mesmo veredicto via ``adicionar``. A
deduplicação por ``tag_base`` dentro de cada propriedade vive em
:class:`VeredictoPub`, não aqui.
"""
from __future__ import annotations

from typing import Any

from . import alerta_contadoria as ac
from . import camada_base as cb
from ._shared.matching_clientes import carregar_indice_clientes
from .tipos import VeredictoPub


def aplicar_todas_regras(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
    *,
    cache_conn: Any = None,
) -> VeredictoPub:
    """Aplica as 30 regras (4 da camada base + 26 de Alerta contadoria)
    e devolve um :class:`VeredictoPub`.

    Args:
        publicacao: dict com as chaves cruas vindas do DJEN —
            ``siglaTribunal``, ``tipoComunicacao``, ``tipoDocumento``,
            ``nomeOrgao``, ``nomeClasse``, ``destinatarios``,
            ``data_disponibilizacao`` etc.
        processo_record: registro do cache.db de Processos (pode ser
            ``None`` quando o CNJ não está cadastrado).
        cache_conn: conexão SQLite opcional pra cache.db. Quando passada,
            permite que AC04/AC05/AC06 carreguem o índice de clientes
            (caso contrário essas três regras pulam).

    Returns:
        :class:`VeredictoPub` com até 3 listas de tags (uma por
        propriedade do Notion). Listas vazias sinalizam "nada a
        gravar nessa propriedade".
    """
    veredicto = VeredictoPub()

    # ---- Camada base — Tarefa advogado / Tarefa contadoria ----
    veredicto.adicionar(cb.regra_ta01_analisar_sentenca(publicacao))
    veredicto.adicionar(cb.regra_ta02_analisar_acordao(publicacao))
    veredicto.adicionar(cb.regra_tc01_distribuicao(publicacao))
    veredicto.adicionar(cb.regra_tc02_pauta_julgamento(publicacao))

    # ---- Alerta contadoria — AC01 a AC26 ----
    indice_clientes = (
        carregar_indice_clientes(cache_conn) if cache_conn is not None else {}
    )

    veredicto.adicionar(ac.regra_ac01_natureza_x_tribunal(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac02_natureza_x_classe(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac03_recurso_autonomo_como_principal(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac04_cliente_fora_relation(
        publicacao, processo_record, indice_clientes=indice_clientes,
    ))
    veredicto.adicionar(ac.regra_ac05_litisconsorcio_nao_refletido(
        publicacao, processo_record, indice_clientes=indice_clientes,
    ))
    veredicto.adicionar(ac.regra_ac06_cliente_cadastrado_nao_aparece(
        publicacao, processo_record, indice_clientes=indice_clientes,
    ))
    veredicto.adicionar(ac.regra_ac07_tribunal_fora_vocabulario(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac08_conferir_tribunal_origem(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac09_capturar_numeracao_stj(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac10_subida_nao_detectada(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac11_descida_nao_detectada(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac12_acordao_em_1grau(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac13_sentenca_em_colegiado(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac14_pauta_em_1grau(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac15_cidade_faltando(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac16_cidade_divergente(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac17_vara_faltando(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac18_vara_divergente(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac19_turma_desatualizada(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac20_relator_desatualizado(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac21_fase_executiva(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac22_fase_liquidacao(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac23_capturar_data_distribuicao(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac24_transito_pendente(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac25_recurso_autonomo_sem_pai(publicacao, processo_record))
    veredicto.adicionar(ac.regra_ac26_processo_nao_cadastrado(publicacao, processo_record))

    return veredicto
