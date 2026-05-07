"""Alerta contadoria — AC01 a AC26 (Round 10).

Cada regra é função separada com signature uniforme::

    def regra_acNN_*(
        publicacao: dict[str, Any],
        processo_record: dict[str, Any] | None,
        *,
        indice_clientes: dict[str, str] | None = None,  # AC04, AC05, AC06
    ) -> TagApp | None: ...

Regras que compartilham o mesmo *tag_base* (AC04+AC05, AC15+AC16,
AC17+AC18) continuam separadas — telemetria por código de regra
(``TagApp.regra``) sobrevive, e o ``VeredictoPub.adicionar`` deduplica
no nível da propriedade pra que o vocabulário do Notion fique limpo.
"""
from __future__ import annotations

import re
from typing import Any

from notion_rpadv.services.dje_notion_mappings import mapear_tipo_documento

from ._shared.classes_cnj import (
    CLASSES_CIVEIS,
    CLASSES_DISTRIBUICAO_INICIAL,
    CLASSES_EXECUTIVAS,
    CLASSES_LIQUIDACAO,
    CLASSES_TRABALHISTAS,
)
from ._shared.constantes import (
    FASE_EXECUTIVA,
    FASE_LIQUIDACAO,
    FASE_LIQUIDACAO_PENDENTE,
    INSTANCIA_PRIMEIRO_GRAU,
    INSTANCIAS_COLEGIADAS,
    NATUREZA_CIVEL,
    NATUREZA_TRABALHISTA,
    RANK_INSTANCIA,
    TIPO_PROCESSO_PRINCIPAL,
    TIPOS_PROCESSO_DEPENDENTES,
)
from ._shared.extracao_orgao import (
    campo_relator_para_instancia,
    campo_turma_para_instancia,
    extrair_cidade_do_orgao,
    extrair_relator,
    extrair_turma_camara,
    normalizar_nome_relator,
    normalizar_vara,
    ordinal_de_turma,
)
from ._shared.matching_clientes import matching_clientes_em_pub
from ._shared.tabelas import instancia_implicada
from ._shared.tribunais import (
    TRIBUNAIS_CIVEIS,
    TRIBUNAIS_FORA_VOCABULARIO_PROC,
    TRIBUNAIS_TRABALHISTAS,
    pub_trib_normalizado_para_proc,
)
from .tipos import TagApp

# ---------------------------------------------------------------------------
# Tag bases (sem sufixo " - App") — espelham as 22 opções do select
# ---------------------------------------------------------------------------

TAG_AC_NATUREZA: str = "Conferir natureza do processo"
TAG_AC_TIPO_PROCESSO: str = "Conferir tipo de processo"
TAG_AC_VINCULAR_CLIENTE: str = "Vincular cliente ao processo"
TAG_AC_CONFERIR_VINCULACAO: str = "Conferir vinculação cliente-processo"
TAG_AC_TRIBUNAL_FORA_VOCAB: str = "Tribunal fora do vocabulário"
TAG_AC_CONFERIR_TRIBUNAL_ORIGEM: str = "Conferir tribunal de origem"
TAG_AC_CAPTURAR_NUMERACAO_STJ: str = "Capturar numeração STJ"
TAG_AC_INSTANCIA_SUBIDA: str = "Instância desatualizada (subida)"
TAG_AC_INSTANCIA_DESCIDA: str = "Instância desatualizada (descida)"
TAG_AC_ACORDAO_EM_1GRAU: str = "Acórdão em processo de 1º grau"
TAG_AC_SENTENCA_EM_COLEGIADO: str = "Sentença em processo de colegiado"
TAG_AC_PAUTA_EM_1GRAU: str = "Pauta em processo de 1º grau"
TAG_AC_CIDADE_DESATUALIZADA: str = "Cidade desatualizada"
TAG_AC_VARA_DESATUALIZADA: str = "Vara desatualizada"
TAG_AC_TURMA_DESATUALIZADA: str = "Turma desatualizada"
TAG_AC_RELATOR_DESATUALIZADO: str = "Relator desatualizado"
TAG_AC_FASE_EXECUTIVA: str = "Fase desatualizada (executiva)"
TAG_AC_FASE_LIQUIDACAO: str = "Fase desatualizada (liquidação)"
TAG_AC_CAPTURAR_DATA_DISTRIB: str = "Capturar data de distribuição"
TAG_AC_TRANSITO_PENDENTE: str = "Trânsito em julgado pendente"
TAG_AC_RECURSO_AUTONOMO_SEM_PAI: str = "Recurso autônomo sem processo pai"
TAG_AC_PROCESSO_NAO_CADASTRADO: str = "Processo não cadastrado"


def _tag(regra: str, base: str) -> TagApp:
    """Atalho construtor — sempre devolve ``TagApp`` da propriedade
    ``Alerta contadoria``."""
    return TagApp(propriedade="Alerta contadoria", tag_base=base, regra=regra)


# ===========================================================================
# AC01 / AC02 — Natureza do processo
# ===========================================================================


def regra_ac01_natureza_x_tribunal(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC01 — Natureza inconsistente com Tribunal.

    Substitui a antiga Regra 4. Tribunais trabalhistas (TRT*, TST) só
    processam matéria trabalhista; tribunais cíveis idem. STJ/STF
    julgam ambas e ficam fora.
    """
    if processo_record is None:
        return None
    sigla = (publicacao.get("siglaTribunal") or "").strip().upper()
    natureza = (processo_record.get("natureza") or "").strip()
    if not natureza:
        return None
    if sigla in TRIBUNAIS_TRABALHISTAS and natureza == NATUREZA_CIVEL:
        return _tag("AC01", TAG_AC_NATUREZA)
    if sigla in TRIBUNAIS_CIVEIS and natureza == NATUREZA_TRABALHISTA:
        return _tag("AC01", TAG_AC_NATUREZA)
    return None


def regra_ac02_natureza_x_classe(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC02 — Natureza inconsistente com Classe (substitui Regra 5).

    Classes ambíguas (RESP, AI sem qualif, AGRAVO simples,
    CUMPRIMENTO, CONFLITO DE COMPETÊNCIA) herdam natureza do principal
    e não disparam.
    """
    if processo_record is None:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    natureza = (processo_record.get("natureza") or "").strip()
    if not classe or not natureza:
        return None
    if classe in CLASSES_TRABALHISTAS and natureza == NATUREZA_CIVEL:
        return _tag("AC02", TAG_AC_NATUREZA)
    if classe in CLASSES_CIVEIS and natureza == NATUREZA_TRABALHISTA:
        return _tag("AC02", TAG_AC_NATUREZA)
    return None


# ===========================================================================
# AC03 — Tipo de processo
# ===========================================================================


def regra_ac03_recurso_autonomo_como_principal(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC03 — AGRAVO DE INSTRUMENTO cadastrado como Principal.

    Substitui Regra 6. Apenas AI *stricto sensu* (art. 1.015 CPC,
    contra decisão interlocutória) gera CNJ próprio e exige
    ``Tipo de processo = Recurso autônomo``. Demais recursos (AI em
    RESP/RR, AgRESP) tramitam nos autos do principal por decisão
    administrativa do escritório.
    """
    if processo_record is None:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if classe != "AGRAVO DE INSTRUMENTO":  # match exato — sem qualificadores
        return None
    tipo = (processo_record.get("tipo_de_processo") or "").strip()
    if tipo == TIPO_PROCESSO_PRINCIPAL:
        return _tag("AC03", TAG_AC_TIPO_PROCESSO)
    return None


# ===========================================================================
# AC04 / AC05 / AC06 — Cliente e vinculação
# ===========================================================================


def regra_ac04_cliente_fora_relation(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
    *,
    indice_clientes: dict[str, str] | None = None,
) -> TagApp | None:
    """AC04 — Cliente do escritório aparece nas Partes mas não está em
    ``Proc.clientes``.

    Substitui Regra 7. Filtra ``Tipo de processo = Principal`` para
    evitar FP nos recursos (que têm Clientes vazio por design).
    """
    if processo_record is None or not indice_clientes:
        return None
    if (processo_record.get("tipo_de_processo") or "") != TIPO_PROCESSO_PRINCIPAL:
        return None
    matchings = matching_clientes_em_pub(publicacao, indice_clientes)
    if not matchings:
        return None
    encontrados_pub: set[str] = set()
    for clientes_polo in matchings.values():
        encontrados_pub.update(clientes_polo)
    proc_clientes = {str(c) for c in (processo_record.get("clientes") or [])}
    if not encontrados_pub.issubset(proc_clientes):
        return _tag("AC04", TAG_AC_VINCULAR_CLIENTE)
    return None


def regra_ac05_litisconsorcio_nao_refletido(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
    *,
    indice_clientes: dict[str, str] | None = None,
) -> TagApp | None:
    """AC05 — Litisconsórcio ativo não refletido no cadastro.

    Substitui Regra 8. ``Pub.Partes`` lista 2+ clientes do escritório
    no mesmo polo, mas ``Proc.clientes`` tem apenas 1.
    """
    if processo_record is None or not indice_clientes:
        return None
    if (processo_record.get("tipo_de_processo") or "") != TIPO_PROCESSO_PRINCIPAL:
        return None
    matchings = matching_clientes_em_pub(publicacao, indice_clientes)
    if not matchings:
        return None
    tem_litisconsorcio = any(len(clientes) >= 2 for clientes in matchings.values())
    if not tem_litisconsorcio:
        return None
    proc_clientes = {str(c) for c in (processo_record.get("clientes") or [])}
    if len(proc_clientes) < 2:
        return _tag("AC05", TAG_AC_VINCULAR_CLIENTE)
    return None


def regra_ac06_cliente_cadastrado_nao_aparece(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
    *,
    indice_clientes: dict[str, str] | None = None,
) -> TagApp | None:
    """AC06 — Cliente cadastrado em ``Proc.clientes`` não aparece em
    ``Pub.Partes``.

    Substitui Regra 9. Possível vinculação errada de Pub.Processo ou
    homonímia — investigação manual.
    """
    if processo_record is None or not indice_clientes:
        return None
    if (processo_record.get("tipo_de_processo") or "") != TIPO_PROCESSO_PRINCIPAL:
        return None
    proc_clientes = [str(c) for c in (processo_record.get("clientes") or [])]
    if not proc_clientes:
        return None
    matchings = matching_clientes_em_pub(publicacao, indice_clientes)
    encontrados_pub: set[str] = set()
    for clientes_polo in matchings.values():
        encontrados_pub.update(clientes_polo)
    for cliente_id in proc_clientes:
        if cliente_id in encontrados_pub:
            return None
    return _tag("AC06", TAG_AC_CONFERIR_VINCULACAO)


# ===========================================================================
# AC07 / AC08 — Tribunal de origem
# ===========================================================================


def regra_ac07_tribunal_fora_vocabulario(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC07 — Pub.Tribunal não está no vocabulário do select de
    ``Proc.tribunal`` (ex.: TRT18, TRF1).

    Substitui Regra 12. Independe de processo cadastrado — sinaliza
    atenção mesmo em pubs sem cadastro.
    """
    sigla = (publicacao.get("siglaTribunal") or "").strip().upper()
    if sigla in TRIBUNAIS_FORA_VOCABULARIO_PROC:
        return _tag("AC07", TAG_AC_TRIBUNAL_FORA_VOCAB)
    return None


def regra_ac08_conferir_tribunal_origem(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC08 — Em 1ª instância, Pub.Tribunal ≠ Proc.tribunal de origem.

    Substitui Regra 13. Não dispara nas instâncias superiores (recurso
    pode tramitar em tribunal diferente do de origem por design).
    """
    if processo_record is None:
        return None
    instancia = (processo_record.get("instancia") or "").strip()
    if instancia != INSTANCIA_PRIMEIRO_GRAU:
        return None
    pub_trib_norm = pub_trib_normalizado_para_proc(
        publicacao.get("siglaTribunal"),
    )
    proc_trib = (processo_record.get("tribunal") or "").strip()
    if not pub_trib_norm or not proc_trib:
        return None
    if pub_trib_norm != proc_trib:
        return _tag("AC08", TAG_AC_CONFERIR_TRIBUNAL_ORIGEM)
    return None


# ===========================================================================
# AC09 — Capturar numeração STJ
# ===========================================================================


def regra_ac09_capturar_numeracao_stj(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC09 — Pub do STJ e ``Proc.numero_stj`` vazio.

    Substitui Regra 2. TST mantém o CNJ original do tribunal de origem
    (não atribui numeração nova) — então pubs do TST não disparam.
    """
    if processo_record is None:
        return None
    sigla = (publicacao.get("siglaTribunal") or "").strip().upper()
    if sigla != "STJ":
        return None
    numero = (processo_record.get("numero_stj") or "").strip()
    if not numero:
        return _tag("AC09", TAG_AC_CAPTURAR_NUMERACAO_STJ)
    return None


# ===========================================================================
# AC10 / AC11 — Instância desatualizada (subida / descida)
# ===========================================================================


def regra_ac10_subida_nao_detectada(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC10 — ``instancia_implicada(Pub) > Proc.instancia``.

    Substitui Regra 14. O processo subiu (foi pra tribunal superior
    ou colegiado) e o cadastro não acompanhou.
    """
    if processo_record is None:
        return None
    instancia_pub = instancia_implicada(publicacao)
    if instancia_pub is None:
        return None
    instancia_proc = (processo_record.get("instancia") or "").strip()
    if not instancia_proc:
        return None
    rank_pub = RANK_INSTANCIA.get(instancia_pub)
    rank_proc = RANK_INSTANCIA.get(instancia_proc)
    if rank_pub is None or rank_proc is None:
        return None
    if rank_pub > rank_proc:
        return _tag("AC10", TAG_AC_INSTANCIA_SUBIDA)
    return None


def regra_ac11_descida_nao_detectada(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC11 — ``instancia_implicada(Pub) < Proc.instancia`` E classe
    NÃO é Cumprimento/Liquidação.

    Substitui Regra 15. Filtro de classe evita FP sistemáticos quando
    o processo retorna legitimamente para 1º grau pra cumprir acórdão.
    """
    if processo_record is None:
        return None
    instancia_pub = instancia_implicada(publicacao)
    if instancia_pub is None:
        return None
    instancia_proc = (processo_record.get("instancia") or "").strip()
    if not instancia_proc:
        return None
    rank_pub = RANK_INSTANCIA.get(instancia_pub)
    rank_proc = RANK_INSTANCIA.get(instancia_proc)
    if rank_pub is None or rank_proc is None:
        return None
    if rank_pub >= rank_proc:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if classe in CLASSES_EXECUTIVAS or classe in CLASSES_LIQUIDACAO:
        return None
    return _tag("AC11", TAG_AC_INSTANCIA_DESCIDA)


# ===========================================================================
# AC12 / AC13 / AC14 — Impossibilidades categóricas
# ===========================================================================


def regra_ac12_acordao_em_1grau(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC12 — Acórdão em processo cadastrado como 1º grau.

    Substitui Regra 16. Acórdão é ato de colegiado; juiz singular não
    emite. Cadastro abaixo da realidade.
    """
    if processo_record is None:
        return None
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc != "Acórdão":
        return None
    instancia = (processo_record.get("instancia") or "").strip()
    if instancia == INSTANCIA_PRIMEIRO_GRAU:
        return _tag("AC12", TAG_AC_ACORDAO_EM_1GRAU)
    return None


def regra_ac13_sentenca_em_colegiado(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC13 — Sentença em processo cadastrado em colegiado.

    Substitui Regra 17. Sentença é ato de juiz singular; colegiado
    emite acórdão. Cadastro acima da realidade — o processo
    provavelmente voltou para 1º grau.
    """
    if processo_record is None:
        return None
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc != "Sentença":
        return None
    instancia = (processo_record.get("instancia") or "").strip()
    if instancia in INSTANCIAS_COLEGIADAS:
        return _tag("AC13", TAG_AC_SENTENCA_EM_COLEGIADO)
    return None


def regra_ac14_pauta_em_1grau(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC14 — Pauta de Julgamento em processo cadastrado como 1º grau.

    Substitui Regra 18. Pauta só existe em colegiado.
    """
    if processo_record is None:
        return None
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc != "Pauta de Julgamento":
        return None
    instancia = (processo_record.get("instancia") or "").strip()
    if instancia == INSTANCIA_PRIMEIRO_GRAU:
        return _tag("AC14", TAG_AC_PAUTA_EM_1GRAU)
    return None


# ===========================================================================
# AC15 / AC16 — Cidade
# ===========================================================================


def _normalizar_cidade_proc(valor: str) -> str:
    """Remove sufixo ``- UF`` e colapsa espaços. Comparação simétrica
    com o que sai do regex de extração da Pub.Órgão."""
    s = re.sub(r"\s*-\s*[A-Z]{2}\s*$", "", valor)
    return re.sub(r"\s+", " ", s).strip()


def regra_ac15_cidade_faltando(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC15 — Pub.Órgão revela cidade e Proc.cidade está vazia.

    Substitui Regra 19.
    """
    if processo_record is None:
        return None
    cidade_pub = extrair_cidade_do_orgao(publicacao.get("nomeOrgao"))
    if not cidade_pub:
        return None
    cidade_proc_raw = (processo_record.get("cidade") or "").strip()
    if not cidade_proc_raw:
        return _tag("AC15", TAG_AC_CIDADE_DESATUALIZADA)
    return None


def regra_ac16_cidade_divergente(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC16 — Pub.Órgão revela cidade ≠ Proc.cidade populada.

    Substitui Regra 20. Comparação case-insensitive com sufixo "- UF"
    removido dos dois lados pra evitar FP cosméticos.
    """
    if processo_record is None:
        return None
    cidade_pub = extrair_cidade_do_orgao(publicacao.get("nomeOrgao"))
    if not cidade_pub:
        return None
    cidade_proc_raw = (processo_record.get("cidade") or "").strip()
    if not cidade_proc_raw:
        return None  # AC15 cobre vazio
    cidade_proc = _normalizar_cidade_proc(cidade_proc_raw)
    if cidade_pub.upper() != cidade_proc.upper():
        return _tag("AC16", TAG_AC_CIDADE_DESATUALIZADA)
    return None


# ===========================================================================
# AC17 / AC18 — Vara (1º grau)
# ===========================================================================


def regra_ac17_vara_faltando(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC17 — Em 1º grau, Pub.Órgão revela vara mas Proc.vara está
    vazia. Substitui Regra 21.
    """
    if processo_record is None:
        return None
    if (processo_record.get("instancia") or "") != INSTANCIA_PRIMEIRO_GRAU:
        return None
    if instancia_implicada(publicacao) != INSTANCIA_PRIMEIRO_GRAU:
        return None
    vara_pub_norm = normalizar_vara(publicacao.get("nomeOrgao"))
    if not vara_pub_norm:
        return None
    vara_proc_raw = (processo_record.get("vara") or "").strip()
    if not vara_proc_raw:
        return _tag("AC17", TAG_AC_VARA_DESATUALIZADA)
    return None


def regra_ac18_vara_divergente(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC18 — Em 1º grau, Pub.Órgão revela vara ≠ Proc.vara populada.

    Substitui Regra 22. Cadastro com ordinal puro ("14") OU formato
    canônico que não bate dispara — sinal de cadastro velho que precisa
    migrar pro formato canônico ``"Nª Vara X"``.
    """
    if processo_record is None:
        return None
    if (processo_record.get("instancia") or "") != INSTANCIA_PRIMEIRO_GRAU:
        return None
    if instancia_implicada(publicacao) != INSTANCIA_PRIMEIRO_GRAU:
        return None
    vara_pub_norm = normalizar_vara(publicacao.get("nomeOrgao"))
    if not vara_pub_norm:
        return None
    vara_proc_raw = (processo_record.get("vara") or "").strip()
    if not vara_proc_raw:
        return None  # AC17 cobre vazio
    vara_proc_norm = normalizar_vara(vara_proc_raw)
    if not vara_proc_norm:
        # Cadastro em formato não canônico (ordinal puro etc.) —
        # comparação canônica impossível, força revisão.
        return _tag("AC18", TAG_AC_VARA_DESATUALIZADA)
    if vara_pub_norm.upper() != vara_proc_norm.upper():
        return _tag("AC18", TAG_AC_VARA_DESATUALIZADA)
    return None


# ===========================================================================
# AC19 / AC20 — Turma e Relator (≥ 2º grau)
# ===========================================================================


def regra_ac19_turma_desatualizada(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC19 — Em colegiado, Pub.Órgão revela turma vazia ou divergente
    do que está em ``Proc.turma_no_*``.

    Substitui Regra 23. Comparação por ordinal numérico tolera
    ``"5"``, ``"5.0"``, ``"5ª Turma"``, ``"5ª Turma Cível"``.
    """
    if processo_record is None:
        return None
    instancia_proc = (processo_record.get("instancia") or "").strip()
    if instancia_proc not in INSTANCIAS_COLEGIADAS:
        return None
    turma_pub = extrair_turma_camara(publicacao.get("nomeOrgao"))
    if not turma_pub:
        return None
    campo = campo_turma_para_instancia(instancia_proc)
    if not campo:
        return None
    turma_proc_raw = (processo_record.get(campo) or "").strip()
    if not turma_proc_raw:
        return _tag("AC19", TAG_AC_TURMA_DESATUALIZADA)
    ord_pub = ordinal_de_turma(turma_pub)
    ord_proc = ordinal_de_turma(turma_proc_raw)
    if ord_pub is None or ord_proc is None:
        return _tag("AC19", TAG_AC_TURMA_DESATUALIZADA)
    if ord_pub != ord_proc:
        return _tag("AC19", TAG_AC_TURMA_DESATUALIZADA)
    return None


def regra_ac20_relator_desatualizado(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC20 — Em colegiado, Pub.Órgão revela relator vazio ou divergente
    do que está em ``Proc.relator_no_*``.

    Substitui Regra 24. Normalização simétrica via
    ``normalizar_nome_relator`` tira prefixos de tratamento dos dois
    lados antes de comparar.
    """
    if processo_record is None:
        return None
    instancia_proc = (processo_record.get("instancia") or "").strip()
    if instancia_proc not in INSTANCIAS_COLEGIADAS:
        return None
    relator_pub = extrair_relator(publicacao.get("nomeOrgao"))
    if not relator_pub:
        return None
    campo = campo_relator_para_instancia(instancia_proc)
    if not campo:
        return None
    relator_proc_raw = (processo_record.get(campo) or "").strip()
    if not relator_proc_raw:
        return _tag("AC20", TAG_AC_RELATOR_DESATUALIZADO)
    relator_pub_norm = normalizar_nome_relator(relator_pub)
    relator_proc_norm = normalizar_nome_relator(relator_proc_raw)
    if relator_pub_norm is None or relator_proc_norm is None:
        return _tag("AC20", TAG_AC_RELATOR_DESATUALIZADO)
    if relator_pub_norm.upper() != relator_proc_norm.upper():
        return _tag("AC20", TAG_AC_RELATOR_DESATUALIZADO)
    return None


# ===========================================================================
# AC21 / AC22 — Fase desatualizada (executiva, liquidação)
# ===========================================================================


def regra_ac21_fase_executiva(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC21 — Pub.Classe em classes executivas E Proc.fase ≠ Executiva.

    Substitui Regra 26. A classe da publicação determina a fase com
    certeza — se diverge da cadastrada, cadastro precisa atualizar.
    """
    if processo_record is None:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if classe not in CLASSES_EXECUTIVAS:
        return None
    fase_proc = (processo_record.get("fase") or "").strip()
    if fase_proc != FASE_EXECUTIVA:
        return _tag("AC21", TAG_AC_FASE_EXECUTIVA)
    return None


def regra_ac22_fase_liquidacao(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC22 — Pub.Classe em classes de liquidação E Proc.fase NÃO em
    {Liquidação pendente, Liquidação de sentença}.

    Substitui Regra 27.
    """
    if processo_record is None:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if classe not in CLASSES_LIQUIDACAO:
        return None
    fase_proc = (processo_record.get("fase") or "").strip()
    if fase_proc not in (FASE_LIQUIDACAO, FASE_LIQUIDACAO_PENDENTE):
        return _tag("AC22", TAG_AC_FASE_LIQUIDACAO)
    return None


# ===========================================================================
# AC23 — Capturar data de distribuição
# ===========================================================================


def regra_ac23_capturar_data_distribuicao(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC23 — ``tipoDocumento = "Distribuição"`` em classe inicial E
    ``Proc.data_de_distribuicao`` vazia.

    Substitui Regra 33. Recursos (Agravo de Petição, Apelação, etc.)
    ficam fora — distribuição recursal não é distribuição inicial do
    processo.
    """
    if processo_record is None:
        return None
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_doc != "Distribuição":
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if classe not in CLASSES_DISTRIBUICAO_INICIAL:
        return None
    if processo_record.get("data_de_distribuicao"):
        return None
    return _tag("AC23", TAG_AC_CAPTURAR_DATA_DISTRIB)


# ===========================================================================
# AC24 — Trânsito em julgado pendente
# ===========================================================================


def regra_ac24_transito_pendente(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC24 — Pub.Classe = "CUMPRIMENTO DE SENTENÇA" (não inclui
    CUMPRIMENTO PROVISÓRIO) E ``Proc.data_do_transito_em_julgado_*``
    vazias.

    Substitui Regra 35. Cumprimento definitivo só roda após trânsito
    da fase cognitiva.
    """
    if processo_record is None:
        return None
    classe = (publicacao.get("nomeClasse") or "").strip().upper()
    if classe != "CUMPRIMENTO DE SENTENÇA":
        return None
    t_cog = processo_record.get("data_do_transito_em_julgado_cognitiva")
    t_exec = processo_record.get("data_do_transito_em_julgado_executiva")
    if not t_cog and not t_exec:
        return _tag("AC24", TAG_AC_TRANSITO_PENDENTE)
    return None


# ===========================================================================
# AC25 — Recurso autônomo sem processo pai
# ===========================================================================


def regra_ac25_recurso_autonomo_sem_pai(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC25 — Proc.tipo_de_processo é dependente E processo_pai vazio.

    Substitui Regra 39. Independente de Pub — checagem interna do
    cadastro. Combina com AC03 (uma vez detectado o tipo dependente,
    conferir se tem pai vinculado).
    """
    if processo_record is None:
        return None
    tipo = (processo_record.get("tipo_de_processo") or "").strip()
    if tipo not in TIPOS_PROCESSO_DEPENDENTES:
        return None
    pai = processo_record.get("processo_pai")
    if isinstance(pai, list):
        if pai:
            return None
    elif pai:
        return None
    return _tag("AC25", TAG_AC_RECURSO_AUTONOMO_SEM_PAI)


# ===========================================================================
# AC26 — Processo não cadastrado (ex regra_processo_nao_cadastrado)
# ===========================================================================


def regra_ac26_processo_nao_cadastrado(
    publicacao: dict[str, Any],
    processo_record: dict[str, Any] | None,
) -> TagApp | None:
    """AC26 — ``processo_record is None`` E pub NÃO é distribuição.

    Substitui o antigo ``regra_processo_nao_cadastrado``. Distribuições
    já recebem ``Processo/recurso distribuído`` (TC01) — disparar
    "Processo não cadastrado" em paralelo polui o select.
    """
    from notion_rpadv.services.dje_notion_mappings import (
        mapear_tipo_comunicacao,
    )

    if processo_record is not None:
        return None
    tipo_com = mapear_tipo_comunicacao(publicacao.get("tipoComunicacao"))
    tipo_doc = mapear_tipo_documento(publicacao.get("tipoDocumento"))
    if tipo_com == "Lista de Distribuição":
        return None
    if tipo_com == "Intimação" and tipo_doc == "Distribuição":
        return None
    return _tag("AC26", TAG_AC_PROCESSO_NAO_CADASTRADO)
