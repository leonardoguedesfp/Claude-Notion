"""Testes do Round 11 — limpeza de cabeçalho/trailer do `Texto` das
publicações antes de gravar no Notion.

Cobre:
- 1 caso por família de tribunal (Trabalhista, STJ, TJDFT, TJ-estadual,
  TRF) com cabeçalho típico.
- 1 caso por tipo de bypass (TIPOS_BYPASS_DOC, TIPOS_BYPASS_COM,
  notifico_eproc, texto_imprestavel).
- Idempotência: limpar duas vezes produz o mesmo resultado.
- Fallback: nenhum marcador casa → texto preservado intacto.
- Defesa "trailer no meio = ignora".
- Defesa "marcador prematuro (< CABECALHO_MIN_CHARS) = descarta".
- Normalização básica (CSS leak, espaços, quebras múltiplas).
"""
from __future__ import annotations

from notion_rpadv.services.dje_text_limpeza import (
    CABECALHO_MIN_CHARS,
    TIPOS_BYPASS_COM,
    TIPOS_BYPASS_DOC,
    limpar_cabecalho_trailer,
)


# ---------------------------------------------------------------------------
# Casos por família de tribunal
# ---------------------------------------------------------------------------


def test_trabalhista_intimacao_corta_cabecalho() -> None:
    """TRT10 com preâmbulo 'PODER JUDICIÁRIO JUSTIÇA DO TRABALHO...' +
    DESPACHO. Marcador `INTIMAÇÃO Fica` ou `DESPACHO` casa primeiro."""
    txt = (
        "PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRIBUNAL REGIONAL DO TRABALHO "
        "DA 10ª REGIÃO 15ª Vara do Trabalho de Brasília - DF "
        "ATOrd 0000833-23.2010.5.10.0015 RECLAMANTE: ZENOR COSTA DIAS "
        "RECLAMADO: CAIXA INTIMAÇÃO Fica V. Sa. intimado para tomar ciência "
        "do Despacho ID d366151 proferido nos autos. DESPACHO Vistos, etc."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TRT10", tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
    )
    assert diag.cabecalho_removido is True
    assert diag.fallback_aplicado is False
    assert diag.chars_removidos_inicio > 0
    assert diag.bypass_motivo is None
    assert saida.startswith("INTIMAÇÃO Fica")
    # ID do despacho preservado
    assert "Despacho ID d366151" in saida


def test_stj_acordao_corta_via_marcador_linha_propria() -> None:
    """STJ tem cabeçalho compacto sem newlines + corpo após `\\n ACÓRDÃO
    \\n`. O marcador 'linha própria' deve casar antes do genérico."""
    txt = (
        "EDcl no AgInt no REsp 1234567/DF (2022/0123-1)"
        "RELATOR:MINISTRO MOURA RIBEIRO"
        "EMBARGANTE:BANCO DO BRASIL SA"
        "ADVOGADOS:JOAO SILVA - DF015523"
        "EMBARGADO:JOSE DA SILVA"
        "\n ACÓRDÃO \n \n "
        "Vistos e relatados estes autos, acordam os Ministros..."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="STJ", tipo_documento="Acórdão",
        tipo_comunicacao="Intimação",
    )
    assert diag.cabecalho_removido is True
    assert diag.marcador_inicio_casado == "ACÓRDÃO (linha)"
    assert "Vistos e relatados" in saida


def test_tjdft_despacho_corta_cabecalho() -> None:
    """TJDFT com 'Poder Judiciário da União...PROCESSO:...DESPACHO'."""
    txt = (
        "Poder Judiciário da União TRIBUNAL DE JUSTIÇA DO DISTRITO FEDERAL "
        "E DOS TERRITÓRIOS Gabinete da Presidência ÓRGÃO: PRESIDÊNCIA "
        "CLASSE: AGRAVO EM RECURSO ESPECIAL PROCESSO: 0722619-78.2018.8.07.0001 "
        "AGRAVANTE: NELSON AGRAVADO: BANCO DO BRASIL "
        "DESPACHO\nVistos. determino a remessa dos autos ao STJ."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TJDFT", tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
    )
    assert diag.cabecalho_removido is True
    assert "DESPACHO" in diag.marcador_inicio_casado
    assert "determino a remessa" in saida


def test_tjsc_remove_css_leak_e_corta_via_ato_ordinatorio() -> None:
    """TJSC tem CSS inline residual no início. A normalização remove o
    CSS; o marcador `ATO ORDINATÓRIO` então casa e corta."""
    txt = (
        "body{ padding: 10px; font-family: Times New Roman; font-size:13pt }; "
        "#divHeader{ line-height:25px; margin-bottom:30px }; "
        "#divBody{ max-width:90%; text-align:justify }"
        "PROCEDIMENTO COMUM CÍVEL Nº 5003415-71.2025.8.24.0005/SC"
        "RELATOR: Rodrigo Coelho Rodrigues"
        "RÉU: ELISABETH"
        "ADVOGADO(A): LEONARDO (OAB DF036129)"
        "ATO ORDINATÓRIO\nIntimação realizada no sistema eproc."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TJSC", tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
    )
    assert "css_leak_removido" in diag.normalizacoes
    assert diag.cabecalho_removido is True
    assert "ATO ORDINATÓRIO" in (diag.marcador_inicio_casado or "")
    # CSS foi removido
    assert "body{" not in saida
    # Corpo preservado
    assert "Intimação realizada" in saida


def test_trf1_decisao_casa_marcador() -> None:
    """TRF1 com formato similar ao TJDFT — marcador DECISÃO."""
    txt = (
        "PODER JUDICIÁRIO TRIBUNAL REGIONAL FEDERAL DA 1ª REGIÃO "
        "Gabinete X Processo: 0001234-56.2023.4.01.3400 "
        "RECORRENTE: ABC RECORRIDO: XYZ "
        "DECISÃO\nVistos, etc. Defiro o pedido."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TRF1", tipo_documento="Decisão",
    )
    assert diag.cabecalho_removido is True
    assert "Defiro o pedido" in saida


# ---------------------------------------------------------------------------
# Bypass por tipo
# ---------------------------------------------------------------------------


def test_bypass_distribuicao() -> None:
    """`Tipo de documento = Distribuição` → bypass total."""
    txt = "Processo 0000438-78.2026.5.10.0012 distribuído para 12ª Vara"
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TRT10", tipo_documento="Distribuição",
    )
    assert diag.bypass_motivo == "tipo"
    assert diag.cabecalho_removido is False
    assert saida == txt  # preservado


def test_bypass_pauta_julgamento() -> None:
    """`Tipo de documento = Pauta de Julgamento` → bypass total."""
    txt = "Processo incluído na Pauta de Julgamentos da QUARTA TURMA"
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="STJ", tipo_documento="Pauta de Julgamento",
    )
    assert diag.bypass_motivo == "tipo"


def test_bypass_certidao() -> None:
    """`Tipo de documento = Certidão` → bypass total (texto curto)."""
    txt = "Número do processo: 0708311-90.2025.8.07.0001 CERTIDÃO..."
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TJDFT", tipo_documento="Certidão",
    )
    assert diag.bypass_motivo == "tipo"


def test_bypass_lista_de_distribuicao() -> None:
    """`Tipo de comunicação = Lista de Distribuição` → bypass total."""
    txt = "Processo 0000666-33.2024.5.10.0009 distribuído para Presidência"
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TST", tipo_documento="Notificação",
        tipo_comunicacao="Lista de Distribuição",
    )
    assert diag.bypass_motivo == "tipo"


# ---------------------------------------------------------------------------
# Bypass por padrão de texto
# ---------------------------------------------------------------------------


def test_bypass_notifico_eproc() -> None:
    """Padrão TJRJ migração para eproc — bypass específico."""
    txt = (
        "Notifico o destinatário que os autos do processo "
        "0227552-94.2013.8.19.0001 foi migrado para o sistema eproc. "
        "O destinatário fica, desde já, ciente da impossibilidade..."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TJRJ", tipo_documento="Outros",
    )
    assert diag.bypass_motivo == "notifico_eproc"
    assert diag.cabecalho_removido is False


def test_bypass_texto_imprestavel() -> None:
    """`ARQUIVOS DIGITAIS INDISPONÍVEIS` (texto curto) → bypass + flag."""
    txt = "ARQUIVOS DIGITAIS INDISPONÍVEIS (NÃO SÃO DO TIPO PÚBLICO)"
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TJGO", tipo_documento="Outros",
    )
    assert diag.bypass_motivo == "texto_imprestavel"
    assert diag.texto_imprestavel is True


def test_arquivos_digitais_em_texto_longo_nao_bypass() -> None:
    """Se o padrão `ARQUIVOS DIGITAIS INDISPONÍVEIS` aparecer em texto
    longo (>200 chars), NÃO aciona o bypass — pode ser referência interna."""
    txt = (
        "PODER JUDICIÁRIO etc " + "x" * 200 +
        " ARQUIVOS DIGITAIS INDISPONÍVEIS em parte do despacho..."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TJGO", tipo_documento="Despacho",
    )
    assert diag.bypass_motivo != "texto_imprestavel"


# ---------------------------------------------------------------------------
# Idempotência
# ---------------------------------------------------------------------------


def test_idempotencia_segunda_passagem_nao_muda_nada() -> None:
    """Rodar a limpeza duas vezes seguidas produz o mesmo hash final.
    Crítico para idempotência do recálculo (Round 11)."""
    txt = (
        "PODER JUDICIÁRIO JUSTIÇA DO TRABALHO 5ª Vara DESPACHO\n"
        "Defiro. Intime-se."
    )
    s1, d1 = limpar_cabecalho_trailer(
        txt, tribunal="TRT10", tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
    )
    s2, d2 = limpar_cabecalho_trailer(
        s1, tribunal="TRT10", tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
    )
    assert d1.hash_pos_limpeza == d2.hash_pos_limpeza
    assert s1 == s2


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def test_fallback_sem_marcador_preserva_texto() -> None:
    """TST Despacho começa com `Embargante:` direto — sem marcador
    clássico. Fallback preserva texto integral."""
    txt = (
        "Embargante: BANCO DO BRASIL S.A.\n"
        "ADVOGADO: JOAO SILVA\n"
        "Embargado(a): JOSE DA SILVA\n"
        "Provimento parcial concedido aos autos."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TST", tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
    )
    assert diag.fallback_aplicado is True
    assert diag.cabecalho_removido is False
    assert "Embargante: BANCO DO BRASIL" in saida


def test_fallback_texto_vazio() -> None:
    saida, diag = limpar_cabecalho_trailer("", tribunal="TRT10")
    assert saida == ""
    assert diag.hash_pos_limpeza != ""


def test_fallback_texto_none() -> None:
    saida, diag = limpar_cabecalho_trailer(None)
    assert saida == ""


# ---------------------------------------------------------------------------
# Defesa: marcador prematuro (< CABECALHO_MIN_CHARS)
# ---------------------------------------------------------------------------


def test_marcador_prematuro_descartado() -> None:
    """Texto começa direto com `Pelo exposto, REJEITO...` ou `SENTENÇA`
    nas primeiras 80 chars → marcador descartado, fallback aplicado."""
    txt = "SENTENÇA Pelo exposto, REJEITO os embargos de declaração."
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TJDFT", tipo_documento="Sentença",
    )
    assert diag.fallback_aplicado is True
    assert "descartado: prematuro" in (diag.marcador_inicio_casado or "")
    # Texto preservado
    assert saida.startswith("SENTENÇA Pelo")


# ---------------------------------------------------------------------------
# Defesa: trailer no meio do texto
# ---------------------------------------------------------------------------


def test_trailer_no_meio_ignorado() -> None:
    """`Intimado(s) / Citado(s)` aparece no meio do despacho (referência
    interna), não no fim. Não deve cortar."""
    txt = (
        "PODER JUDICIÁRIO TRT 10ª REGIÃO DESPACHO\n"
        "Considerando que Intimado(s) / Citado(s) já compareceu, "
        "determino o seguinte: "
        + "x" * 500 +
        " Decisão final aqui."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TRT10", tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
    )
    # marcador_fim casou mas foi ignorado (no meio)
    if diag.marcador_fim_casado:
        assert "ignorado" in diag.marcador_fim_casado
    # Decisão final preservada
    assert "Decisão final" in saida


# ---------------------------------------------------------------------------
# Normalização básica
# ---------------------------------------------------------------------------


def test_normalizacao_quebras_multiplas() -> None:
    txt = "DESPACHO\n\n\n\n\nVistos."
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TRT10", tipo_documento="Despacho",
    )
    # 5 \n viram 2
    assert "\n\n\n" not in saida


def test_normalizacao_espacos_multiplos() -> None:
    txt = "DESPACHO    Vistos       etc."
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TRT10", tipo_documento="Despacho",
    )
    assert "espacos_colapsados" in diag.normalizacoes
    assert "    " not in saida


# ---------------------------------------------------------------------------
# Sanity de constantes públicas
# ---------------------------------------------------------------------------


def test_constantes_publicas() -> None:
    assert CABECALHO_MIN_CHARS == 80
    assert "Distribuição" in TIPOS_BYPASS_DOC
    assert "Pauta de Julgamento" in TIPOS_BYPASS_DOC
    assert "Edital" in TIPOS_BYPASS_DOC
    assert "Certidão" in TIPOS_BYPASS_DOC
    assert "Lista de Distribuição" in TIPOS_BYPASS_COM


def test_diagnostico_to_dict_serializavel() -> None:
    """`DiagnosticoLimpeza.to_dict()` precisa retornar JSON-serializável
    para gravar em `_meta.limpeza_diag` no payload da pub."""
    import json

    _, diag = limpar_cabecalho_trailer(
        "PODER JUDICIÁRIO TRT DESPACHO\nVistos.",
        tribunal="TRT10", tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
    )
    d = diag.to_dict()
    # JSON dump não deve levantar
    s = json.dumps(d)
    assert "cabecalho_removido" in s
    assert "hash_pos_limpeza" in s


# ---------------------------------------------------------------------------
# Casos compostos vindos da amostra empírica (smoke real)
# ---------------------------------------------------------------------------


def test_real_trt10_intimacao_ato_ordinatorio() -> None:
    """Pub real TRT10 com `INTIMAÇÃO - ATO ORDINATÓRIO`."""
    txt = (
        "PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRIBUNAL REGIONAL DO TRABALHO "
        "DA 10ª REGIÃO 8ª Vara do Trabalho de Brasília - DF "
        "ATOrd 0001716-78.2016.5.10.0008 RECLAMANTE: SAULO RECLAMADO: "
        "BANCO DO BRASIL SA INTIMAÇÃO - ATO ORDINATÓRIO DESTINATÁRIO: "
        "BANCO DO BRASIL SA Certifico e dou fé, com amparo no art. 152..."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TRT10", tipo_documento="Notificação",
        tipo_comunicacao="Intimação",
    )
    assert diag.cabecalho_removido is True
    # Marcador específico casa antes do genérico
    assert "INTIMAÇÃO - ATO ORDINATÓRIO" in (diag.marcador_inicio_casado or "")


# ---------------------------------------------------------------------------
# Regressões Round 11.1 — hotfix case-sensitive
# ---------------------------------------------------------------------------


def test_regressao_decisao_minuscula_no_meio_nao_corta() -> None:
    """Pub TJDFT___2026-02-09___3: começava direto com dispositivo,
    sem cabeçalho. Antes do hotfix, regex `\\bDECISÃO\\b` case-insensitive
    casava em `decisão.` minúsculo no meio, cortando o dispositivo.

    Após o fix (uppercase only), nada deve casar — texto preservado
    via fallback.
    """
    txt = (
        "Sendo assim, CONHEÇO e DOU PARCIAL PROVIMENTO aos embargos de "
        "declaração opostos, a fim de que passe a constar: Faculto à parte "
        "autora o prazo de 15 (quinze) dias para informar se possui "
        "interesse na produção da prova pericial. No mais, permanecerá "
        "intacta a decisão. Decisão registrada e assinada eletronicamente "
        "pelo Juiz de Direito abaixo identificado, na data da certificação "
        "digital. Publique-se. Intime-se."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TJDFT", tipo_documento="Decisão",
        tipo_comunicacao="Intimação",
    )
    # Hotfix Round 11.1: regex `\bDECISÃO\b` é case-sensitive — `decisão.`
    # minúsculo NÃO casa, então cai em fallback.
    assert diag.fallback_aplicado is True
    assert diag.cabecalho_removido is False
    # Conteúdo decisório preservado integralmente
    assert "Sendo assim, CONHEÇO" in saida
    assert "DOU PARCIAL PROVIMENTO" in saida


def test_regressao_acordao_minusculo_no_meio_nao_corta() -> None:
    """Ementa TJDFT: começa direto com texto da ementa
    (`EMBARGOS DE DECLARAÇÃO. OMISSÃO...`), depois cita `acórdão
    recorrido` minúsculo. Antes do hotfix, regex `\\bACÓRDÃO\\b` casava
    no minúsculo. Após, cai em fallback.
    """
    txt = (
        "EMBARGOS DE DECLARAÇÃO. OMISSÃO. NÃO OCORRÊNCIA. INTERESSE "
        "DE REEXAME. PREQUESTIONAMENTO. RECURSO DESPROVIDO. "
        "1. De acordo com o disposto no art. 1022 do Código de Processo "
        "Civil, os embargos de declaração não se prestam a "
        "rediscutir o acórdão recorrido."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TJDFT", tipo_documento="Ementa",
        tipo_comunicacao="Intimação",
    )
    # `EMBARGOS DE DECLARAÇÃO` no início NÃO é marcador, mas `EMENTA`
    # genérico não casa porque é uppercase puro e essa palavra não aparece.
    # `acórdão recorrido` minúsculo também não casa após o hotfix.
    # Defesa adicional: se algo casasse antes de CABECALHO_MIN_CHARS=80,
    # ainda assim cairia em fallback.
    if diag.cabecalho_removido:
        # Se o algoritmo escolheu cortar, garantir que pelo menos preserva
        # o início (texto da ementa).
        assert "EMBARGOS DE DECLARAÇÃO" in saida
    else:
        # Esperado: fallback total
        assert diag.fallback_aplicado is True
        assert "EMBARGOS DE DECLARAÇÃO" in saida


def test_regressao_despacho_uppercase_real_funciona() -> None:
    """Sanity check: o hotfix uppercase-only NÃO quebrou o caso comum.
    Pubs reais usam `DESPACHO` em maiúsculas no marcador de cabeçalho —
    devem continuar sendo cortadas corretamente.
    """
    txt = (
        "PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRIBUNAL REGIONAL DO TRABALHO "
        "DA 10ª REGIÃO 5ª Vara do Trabalho de Brasília - DF "
        "ATOrd 0001234-56.2024.5.10.0005 RECLAMANTE: X RECLAMADO: Y "
        "DESPACHO Vistos, etc. Defiro o pedido inicial."
    )
    saida, diag = limpar_cabecalho_trailer(
        txt, tribunal="TRT10", tipo_documento="Despacho",
        tipo_comunicacao="Intimação",
    )
    assert diag.cabecalho_removido is True
    assert "DESPACHO" in (diag.marcador_inicio_casado or "")
    assert saida.startswith("DESPACHO")
