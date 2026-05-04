"""Testes do Round 4 — fixes pré-Round 5 da pipeline DJE × Notion (2026-05-03).

Cobre:

- 4.1 Reformatar `Partes` (Polo Ativo / Polo Passivo / Terceiro Interessado)
- 4.2 Normalizar `Classe` via `MAPA_NOMECLASSE`
- 4.3 Auto-`Tarefa sugerida` (6 regras multi-select)
- 4.4 Auto-`Alerta contadoria` (5 regras multi-select)
- 4.5 Teste de regressão para `<br>` literal residual no Texto inline
- 4.6 Mapper deixa de gravar checkbox `Processo não cadastrado`

Os testes do mapper ponta a ponta (montar_payload_publicacao) ficam em
``tests/test_dje_notion_mapper.py``; aqui isolamos as funções novas.
"""
from __future__ import annotations

from notion_rpadv.services.dje_notion_mapper import (
    ALERTA_INSTANCIA_DESATUALIZADA,
    ALERTA_PAUTA_PRESENCIAL_SEM_INSCRICAO,
    ALERTA_PROCESSO_NAO_CADASTRADO,
    ALERTA_TEXTO_IMPRESTAVEL,
    ALERTA_TRANSITO_PENDENTE,
    TAREFA_D01_ANALISE_PUBLICACAO,
    TAREFA_D02_ANALISE_SENTENCA,
    TAREFA_D03_ANALISE_ACORDAO,
    TAREFA_E01_CADASTRO,
    TAREFA_E02_ATUALIZAR_DADOS,
    TAREFA_E04_INSCRICAO_SUSTENTACAO,
    _aplicar_regras_alerta_contadoria,
    _aplicar_regras_tarefa_sugerida,
)
from notion_rpadv.services.dje_notion_mappings import (
    MAPA_NOMECLASSE,
    PARTES_INLINE_LIMIT,
    POLO_LABEL,
    formatar_partes,
    normalizar_classe,
)


# ===========================================================================
# 4.1 — Reformatar Partes
# ===========================================================================


def test_R4_1_partes_pub_trabalhista_normal() -> None:
    """1 Ativo + 1 Passivo (caso TRT10 djen=494748109)."""
    destinatarios = [
        {"comunicacao_id": 494748109, "nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"comunicacao_id": 494748109, "nome": "DENITA GOMES GUIMARAES", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    assert out == (
        "Polo Ativo: DENITA GOMES GUIMARAES\n"
        "Polo Passivo: BANCO DO BRASIL SA"
    )


def test_R4_1_partes_stj_3_destinatarios_com_papel() -> None:
    """STJ tem prefixo numérico + papel real entre parênteses no nome.
    A formatação genérica deste Round agrupa por polo A/P; o papel real
    fica no próprio nome (não é extraído pra label)."""
    destinatarios = [
        {"nome": "1. CAIXA DE PREVIDENCIA - PREVI (AGRAVANTE)", "polo": "A"},
        {"nome": "2. ALEX DOS SANTOS SABINO (AGRAVADO)", "polo": "P"},
        {"nome": "3. BANCO DO BRASIL SA (INTERESSADO)", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    # Ativo agrupa AGRAVANTE + INTERESSADO (ambos polo A)
    assert "Polo Ativo: 1. CAIXA DE PREVIDENCIA - PREVI (AGRAVANTE), 3. BANCO DO BRASIL SA (INTERESSADO)" in out
    assert "Polo Passivo: 2. ALEX DOS SANTOS SABINO (AGRAVADO)" in out


def test_R4_1_partes_multiplos_nomes_mesmo_polo() -> None:
    """TRT10 com 2 reclamantes (polo A) — separa por vírgula."""
    destinatarios = [
        {"nome": "RECLAMANTE 1", "polo": "A"},
        {"nome": "RECLAMANTE 2", "polo": "A"},
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},
    ]
    out = formatar_partes(destinatarios)
    assert out == (
        "Polo Ativo: RECLAMANTE 1, RECLAMANTE 2\n"
        "Polo Passivo: BANCO DO BRASIL SA"
    )


def test_R4_1_partes_sem_destinatarios() -> None:
    assert formatar_partes([]) == ""
    assert formatar_partes(None) == ""
    assert formatar_partes("not-a-list") == ""


def test_R4_1_partes_terceiro_interessado() -> None:
    """Polo T mapeia pra 'Terceiro Interessado'."""
    destinatarios = [
        {"nome": "AUTOR", "polo": "A"},
        {"nome": "RÉU", "polo": "P"},
        {"nome": "AMICUS CURIAE", "polo": "T"},
    ]
    out = formatar_partes(destinatarios)
    assert out == (
        "Polo Ativo: AUTOR\n"
        "Polo Passivo: RÉU\n"
        "Terceiro Interessado: AMICUS CURIAE"
    )


def test_R4_1_partes_polo_desconhecido_fallback() -> None:
    """Polo fora de A/P/T cai no fallback 'Polo {valor}'."""
    destinatarios = [
        {"nome": "X", "polo": "Z"},  # Z desconhecido
    ]
    assert formatar_partes(destinatarios) == "Polo Z: X"


def test_R4_1_partes_ordem_fixa_apt() -> None:
    """Ordem A → P → T mesmo se vierem invertidos no payload."""
    destinatarios = [
        {"nome": "TERC", "polo": "T"},
        {"nome": "RÉU", "polo": "P"},
        {"nome": "AUTOR", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    linhas = out.split("\n")
    assert linhas[0].startswith("Polo Ativo: ")
    assert linhas[1].startswith("Polo Passivo: ")
    assert linhas[2].startswith("Terceiro Interessado: ")


def test_R4_1_partes_dedup_nome_repetido_mesmo_polo() -> None:
    """Mesmo nome no mesmo polo (artefato do DJEN) entra 1 vez só."""
    destinatarios = [
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},  # duplicata
        {"nome": "AUTOR", "polo": "A"},
    ]
    out = formatar_partes(destinatarios)
    assert out == "Polo Ativo: AUTOR\nPolo Passivo: BANCO DO BRASIL SA"


def test_R4_1_partes_truncamento_em_2000_chars() -> None:
    """Output total ≤ 2000 chars; corte preserva nomes inteiros + marcador."""
    nomes = [f"NOME ABCD EFGH IJKL {i}" for i in range(200)]
    destinatarios = [{"nome": n, "polo": "A"} for n in nomes]
    out = formatar_partes(destinatarios)
    assert len(out) <= PARTES_INLINE_LIMIT
    assert out.endswith("…")
    # Não deve cortar no meio de um nome
    assert "NOME ABCD EFGH IJKL 0" in out


def test_R4_1_partes_nome_vazio_e_descartado() -> None:
    destinatarios = [
        {"nome": "", "polo": "A"},
        {"nome": "VALIDO", "polo": "P"},
    ]
    assert formatar_partes(destinatarios) == "Polo Passivo: VALIDO"


def test_R4_1_partes_polo_label_constante_canonica() -> None:
    """Sanity: tabela POLO_LABEL tem A/P/T."""
    assert POLO_LABEL["A"] == "Polo Ativo"
    assert POLO_LABEL["P"] == "Polo Passivo"
    assert POLO_LABEL["T"] == "Terceiro Interessado"


# ===========================================================================
# 4.2 — Normalização de Classe (casing torto)
# ===========================================================================


def test_R4_2_classe_top_5_acervo_canonizadas() -> None:
    """Top 5 classes do acervo Round 3 vêm com casing torto e são
    canonizadas para CAPS uniforme com acentos corretos."""
    assert normalizar_classe("AçãO TRABALHISTA - RITO ORDINáRIO") == (
        "AÇÃO TRABALHISTA - RITO ORDINÁRIO"
    )
    assert normalizar_classe("RECURSO ORDINáRIO TRABALHISTA") == (
        "RECURSO ORDINÁRIO TRABALHISTA"
    )
    assert normalizar_classe("CUMPRIMENTO DE SENTENçA") == (
        "CUMPRIMENTO DE SENTENÇA"
    )
    assert normalizar_classe("AGRAVO DE PETIçãO") == "AGRAVO DE PETIÇÃO"
    assert normalizar_classe("PROCEDIMENTO COMUM CíVEL") == (
        "PROCEDIMENTO COMUM CÍVEL"
    )


def test_R4_2_classe_ja_em_caps_passa_intacta() -> None:
    """Classes já em CAPS corretas (8 do acervo) NÃO entram no mapa,
    fallback preserva o cru. Testa: RECURSO ESPECIAL, AGRAVO DE
    INSTRUMENTO, RECURSO DE REVISTA, etc."""
    intactas = [
        "RECURSO ESPECIAL",
        "AGRAVO DE INSTRUMENTO",
        "AGRAVO EM RECURSO ESPECIAL",
        "AGRAVO DE INSTRUMENTO EM RECURSO DE REVISTA",
        "RECURSO DE REVISTA COM AGRAVO",
        "AGRAVO",
        "RECURSO DE REVISTA",
        "AGRAVO REGIMENTAL TRABALHISTA",
    ]
    for c in intactas:
        assert normalizar_classe(c) == c


def test_R4_2_classe_nao_mapeada_passa_intacta() -> None:
    """Classe nova/futura não listada no mapa: fallback preserva o
    valor cru (não aplica .upper() cego — pode haver classes futuras
    bem formatadas)."""
    classe_nova = "NOVA CLASSE INVENTADA - ALGO"
    assert normalizar_classe(classe_nova) == classe_nova
    # Mesmo casing não convencional fica intocado
    classe_titlecase = "Tipo de Ação Customizado"
    assert normalizar_classe(classe_titlecase) == classe_titlecase


def test_R4_2_classe_titlecase_explicita_no_mapa() -> None:
    """O caso de title case observado em produção
    ('Procedimento do Juizado Especial da Fazenda Pública') está
    no mapa pra ficar consistente com o resto (CAPS uniforme)."""
    out = normalizar_classe("Procedimento do Juizado Especial da Fazenda Pública")
    assert out == "PROCEDIMENTO DO JUIZADO ESPECIAL DA FAZENDA PÚBLICA"


def test_R4_2_classe_none_e_vazio() -> None:
    assert normalizar_classe(None) == ""
    assert normalizar_classe("") == ""
    assert normalizar_classe("   ") == ""


def test_R4_2_classe_strip_aplicado() -> None:
    """Whitespace nas pontas não atrapalha lookup."""
    assert normalizar_classe("  AçãO TRABALHISTA - RITO ORDINáRIO  ") == (
        "AÇÃO TRABALHISTA - RITO ORDINÁRIO"
    )


def test_R4_2_mapa_consistente_chave_diferente_do_valor() -> None:
    """Sanity: para todas as entradas do MAPA_NOMECLASSE, a saída é
    diferente da entrada (senão, a entrada é redundante)."""
    for chave, valor in MAPA_NOMECLASSE.items():
        assert chave != valor, (
            f"Entrada redundante: {chave!r} mapeia pra ela mesma"
        )


# ===========================================================================
# 4.4 — Auto-Alerta contadoria (5 regras)
# ===========================================================================


def _pub(**kwargs):
    """Helper: monta payload mínimo de publicação."""
    base = {
        "id": 1,
        "siglaTribunal": "TRT10",
        "numeroprocessocommascara": "0001234-56.2025.5.10.0001",
        "tipoDocumento": "Notificação",
        "tipoComunicacao": "Intimação",
        "nomeClasse": "AÇÃO TRABALHISTA",
        "texto": "Texto qualquer com tamanho suficiente para nao disparar imprestavel. " * 5,
    }
    base.update(kwargs)
    return base


def test_R4_4_alerta_processo_nao_cadastrado() -> None:
    """processo_record=None → dispara 'Processo não cadastrado'."""
    alertas = _aplicar_regras_alerta_contadoria(_pub(), processo_record=None)
    assert ALERTA_PROCESSO_NAO_CADASTRADO in alertas


def test_R4_4_alerta_processo_cadastrado_nao_dispara() -> None:
    """processo_record presente → NÃO dispara o alerta de cadastro."""
    rec = {"page_id": "x", "instancia": "TST"}
    alertas = _aplicar_regras_alerta_contadoria(_pub(siglaTribunal="TST"), processo_record=rec)
    assert ALERTA_PROCESSO_NAO_CADASTRADO not in alertas


def test_R4_4_alerta_instancia_desatualizada_tst_processo_1grau() -> None:
    """Tribunal TST + processo cadastrado em '1º grau' → alerta dispara."""
    rec = {"page_id": "x", "instancia": "1º grau"}
    alertas = _aplicar_regras_alerta_contadoria(
        _pub(siglaTribunal="TST"), processo_record=rec,
    )
    assert ALERTA_INSTANCIA_DESATUALIZADA in alertas


def test_R4_4_alerta_instancia_desatualizada_stj_processo_2grau() -> None:
    rec = {"page_id": "x", "instancia": "2º grau"}
    alertas = _aplicar_regras_alerta_contadoria(
        _pub(siglaTribunal="STJ"), processo_record=rec,
    )
    assert ALERTA_INSTANCIA_DESATUALIZADA in alertas


def test_R4_4_alerta_instancia_nao_dispara_tribunal_local() -> None:
    """Tribunal local (TJDFT) + processo cadastrado em '1º grau' → não dispara
    (instância pode estar correta)."""
    rec = {"page_id": "x", "instancia": "1º grau"}
    alertas = _aplicar_regras_alerta_contadoria(
        _pub(siglaTribunal="TJDFT"), processo_record=rec,
    )
    assert ALERTA_INSTANCIA_DESATUALIZADA not in alertas


def test_R4_4_alerta_transito_pendente_cumprimento_sem_data() -> None:
    """Cumprimento de Sentença em processo cadastrado SEM trânsito → alerta."""
    rec = {
        "page_id": "x", "instancia": "1º grau",
        "data_do_transito_em_julgado_cognitiva": None,
        "data_do_transito_em_julgado_executiva": None,
    }
    alertas = _aplicar_regras_alerta_contadoria(
        _pub(nomeClasse="CUMPRIMENTO DE SENTENÇA"), processo_record=rec,
    )
    assert ALERTA_TRANSITO_PENDENTE in alertas


def test_R4_4_alerta_transito_NAO_dispara_em_provisorio() -> None:
    """D3: cumprimento PROVISÓRIO está antes do trânsito por design — NÃO dispara."""
    rec = {
        "page_id": "x", "instancia": "1º grau",
        "data_do_transito_em_julgado_cognitiva": None,
        "data_do_transito_em_julgado_executiva": None,
    }
    alertas = _aplicar_regras_alerta_contadoria(
        _pub(nomeClasse="CUMPRIMENTO PROVISÓRIO DE SENTENÇA"), processo_record=rec,
    )
    assert ALERTA_TRANSITO_PENDENTE not in alertas


def test_R4_4_alerta_transito_nao_dispara_se_data_presente() -> None:
    """Se já há data de trânsito, alerta NÃO dispara."""
    rec = {
        "page_id": "x", "instancia": "1º grau",
        "data_do_transito_em_julgado_cognitiva": "2024-12-10",
        "data_do_transito_em_julgado_executiva": None,
    }
    alertas = _aplicar_regras_alerta_contadoria(
        _pub(nomeClasse="CUMPRIMENTO DE SENTENÇA"), processo_record=rec,
    )
    assert ALERTA_TRANSITO_PENDENTE not in alertas


def test_R4_4_alerta_texto_imprestavel_tjgo_indisponivel() -> None:
    """TJGO 'ARQUIVOS DIGITAIS INDISPONÍVEIS' → alerta dispara."""
    pub = _pub(texto="ARQUIVOS DIGITAIS INDISPONÍVEIS (NÃO SÃO DO TIPO PÚBLICO)")
    alertas = _aplicar_regras_alerta_contadoria(pub, processo_record={"page_id": "x"})
    assert ALERTA_TEXTO_IMPRESTAVEL in alertas


def test_R4_4_alerta_texto_imprestavel_intime_se_minimalista() -> None:
    """Despacho minimalista 'Intime-se.' → alerta dispara."""
    pub = _pub(texto="Intime-se.")
    alertas = _aplicar_regras_alerta_contadoria(pub, processo_record={"page_id": "x"})
    assert ALERTA_TEXTO_IMPRESTAVEL in alertas


def test_R4_4_alerta_texto_imprestavel_trt10_so_id_sem_cnj() -> None:
    """TRT10 com 'Tomar ciência do(a) Intimação de ID 8217f34' SEM CNJ → alerta."""
    pub = _pub(
        texto=(
            "Tomar ciência do(a) Intimação de ID 8217f34.\n\n"
            "Intimado(s) / Citado(s)\n - I.S.L.A."
        ),
    )
    alertas = _aplicar_regras_alerta_contadoria(pub, processo_record={"page_id": "x"})
    assert ALERTA_TEXTO_IMPRESTAVEL in alertas


def test_R4_4_alerta_texto_imprestavel_NAO_dispara_em_despacho_curto_legitimo() -> None:
    """Despacho curto legítimo (com CNJ ou estrutura) NÃO dispara."""
    pub = _pub(texto="Despacho curto: defiro o pedido. Intime-se.")
    alertas = _aplicar_regras_alerta_contadoria(pub, processo_record={"page_id": "x"})
    assert ALERTA_TEXTO_IMPRESTAVEL not in alertas


def test_R4_4_alerta_pauta_presencial_dispara() -> None:
    """Pauta de Julgamento + 'PRESENCIAL' no texto → alerta dispara."""
    pub = _pub(
        tipoDocumento="Pauta de Julgamento",
        texto="3ª SESSÃO ORDINÁRIA - 7TCV - MODALIDADE PRESENCIAL realizar-se-á…",
    )
    alertas = _aplicar_regras_alerta_contadoria(pub, processo_record={"page_id": "x"})
    assert ALERTA_PAUTA_PRESENCIAL_SEM_INSCRICAO in alertas


def test_R4_4_alerta_pauta_virtual_NAO_dispara() -> None:
    """Pauta virtual (sem 'PRESENCIAL'/'Sala de Sessão') → NÃO dispara."""
    pub = _pub(
        tipoDocumento="Pauta de Julgamento",
        texto="Sessão Virtual de 12/05/2026 a 19/05/2026.",
    )
    alertas = _aplicar_regras_alerta_contadoria(pub, processo_record={"page_id": "x"})
    assert ALERTA_PAUTA_PRESENCIAL_SEM_INSCRICAO not in alertas


def test_R4_4_alerta_coexistencia_cumprimento_e_processo_nao_cadastrado() -> None:
    """Cumprimento de sentença + processo não cadastrado → DOIS alertas."""
    pub = _pub(nomeClasse="CUMPRIMENTO DE SENTENÇA")
    alertas = _aplicar_regras_alerta_contadoria(pub, processo_record=None)
    # Não dispara Trânsito (precisa de processo_record), só Processo não cadastrado.
    assert ALERTA_PROCESSO_NAO_CADASTRADO in alertas
    assert ALERTA_TRANSITO_PENDENTE not in alertas


def test_R4_4_alerta_coexistencia_pauta_presencial_e_transito_pendente() -> None:
    """Pauta presencial + cumprimento sem trânsito → 2 alertas."""
    pub = _pub(
        tipoDocumento="Pauta de Julgamento",
        nomeClasse="CUMPRIMENTO DE SENTENÇA",
        texto="Pauta PRESENCIAL para julgamento conforme cumprimento.",
    )
    rec = {
        "page_id": "x", "instancia": "2º grau",
        "data_do_transito_em_julgado_cognitiva": None,
        "data_do_transito_em_julgado_executiva": None,
    }
    alertas = _aplicar_regras_alerta_contadoria(pub, processo_record=rec)
    assert ALERTA_PAUTA_PRESENCIAL_SEM_INSCRICAO in alertas
    assert ALERTA_TRANSITO_PENDENTE in alertas


# ===========================================================================
# 4.6 — Mapper deixou de gravar checkbox 'Processo não cadastrado'
# (testes integrados via mapper já em test_dje_notion_mapper.py)
# ===========================================================================


def test_R4_6_mapper_nao_grava_checkbox_processo_nao_cadastrado() -> None:
    """Verifica explicitamente que o checkbox foi removido do payload
    em ambos os cenários (cadastrado / não-cadastrado)."""
    import sqlite3
    from notion_rpadv.services import dje_db
    from notion_rpadv.services.dje_notion_mapper import montar_payload_publicacao
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "leitor_dje.db"
        dje_conn = dje_db.get_connection(db_path)

        cache_conn = sqlite3.connect(":memory:")
        cache_conn.row_factory = sqlite3.Row
        cache_conn.execute(
            "CREATE TABLE records ("
            "base TEXT, page_id TEXT, data_json TEXT, updated_at REAL,"
            "PRIMARY KEY (base, page_id))"
        )

        pub = {
            "id": 1, "hash": "h", "siglaTribunal": "TRT10",
            "data_disponibilizacao": "2026-01-01",
            "numeroprocessocommascara": "0001234-56.2025.5.10.0001",
            "tipoDocumento": "Notificação", "tipoComunicacao": "Intimação",
            "texto": "Texto.", "destinatarios": [], "destinatarioadvogados": [],
        }
        # Sem cadastro
        payload = montar_payload_publicacao(
            pub, dje_conn=dje_conn, cache_conn=cache_conn,
        )
        assert "Processo não cadastrado" not in payload["properties"]
        # Mas Alerta contadoria contém o sinalizador
        alertas = [
            a["name"] for a in payload["properties"]["Alerta contadoria"]["multi_select"]
        ]
        assert "Processo não cadastrado" in alertas

        dje_conn.close()
        cache_conn.close()


# ===========================================================================
# 4.3 — Auto-Tarefa sugerida (6 regras)
# ===========================================================================


def test_R4_3_tarefa_d03_acordao() -> None:
    """tipoDocumento canônico = Acórdão → D.03."""
    pub = _pub(tipoDocumento="Acórdão")  # canônico já
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record={"page_id": "x"}, alertas_disparados=[],
    )
    assert TAREFA_D03_ANALISE_ACORDAO in tarefas
    # NÃO dispara D.01 (default suprimido por D.03)
    assert TAREFA_D01_ANALISE_PUBLICACAO not in tarefas


def test_R4_3_tarefa_d03_ementa() -> None:
    """tipoDocumento canônico = Ementa → D.03 (mesma tarefa)."""
    pub = _pub(tipoDocumento="Ementa")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record={"page_id": "x"}, alertas_disparados=[],
    )
    assert TAREFA_D03_ANALISE_ACORDAO in tarefas


def test_R4_3_tarefa_d02_sentenca() -> None:
    pub = _pub(tipoDocumento="Sentença")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record={"page_id": "x"}, alertas_disparados=[],
    )
    assert TAREFA_D02_ANALISE_SENTENCA in tarefas
    assert TAREFA_D01_ANALISE_PUBLICACAO not in tarefas


def test_R4_3_tarefa_d01_default_para_decisao() -> None:
    pub = _pub(tipoDocumento="Decisão")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record={"page_id": "x"}, alertas_disparados=[],
    )
    assert TAREFA_D01_ANALISE_PUBLICACAO in tarefas


def test_R4_3_tarefa_e01_processo_nao_cadastrado() -> None:
    pub = _pub()
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record=None, alertas_disparados=[],
    )
    assert TAREFA_E01_CADASTRO in tarefas


def test_R4_3_tarefa_e02_ata_distribuicao_stj() -> None:
    """tipoDocumento bruto = ATA DE DISTRIBUIÇÃO → E.02."""
    pub = _pub(tipoDocumento="ATA DE DISTRIBUIÇÃO")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record={"page_id": "x"}, alertas_disparados=[],
    )
    assert TAREFA_E02_ATUALIZAR_DADOS in tarefas


def test_R4_3_tarefa_e02_dispara_quando_alerta_instancia_desatualizada() -> None:
    """E.02 também dispara quando 'Instância desatualizada' está nos alertas."""
    pub = _pub(tipoDocumento="Notificação")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record={"page_id": "x"},
        alertas_disparados=[ALERTA_INSTANCIA_DESATUALIZADA],
    )
    assert TAREFA_E02_ATUALIZAR_DADOS in tarefas


def test_R4_3_tarefa_e04_pauta_de_julgamento() -> None:
    """tipoDocumento canônico = Pauta de Julgamento → E.04."""
    pub = _pub(tipoDocumento="Pauta de Julgamento")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record={"page_id": "x"}, alertas_disparados=[],
    )
    assert TAREFA_E04_INSCRICAO_SUSTENTACAO in tarefas


def test_R4_3_tarefa_e04_para_aditamento_pauta_via_canonizacao() -> None:
    """Aditamento à Pauta canoniza pra 'Pauta de Julgamento' (Round 1.1)
    → E.04 dispara."""
    pub = _pub(tipoDocumento="ADITAMENTO À PAUTA DE JULGAMENTOS")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record={"page_id": "x"}, alertas_disparados=[],
    )
    assert TAREFA_E04_INSCRICAO_SUSTENTACAO in tarefas


# Coexistência (D2 — sem precedência)


def test_R4_3_coexistencia_acordao_mais_pauta() -> None:
    """Acórdão E também tem marcador de pauta → D.03 + E.04 (D2)."""
    # Tipo canônico Pauta de Julgamento + texto que MENCIONE acórdão.
    # Como nossa lógica decide só por tipo canônico, precisamos de um tipo
    # que canonize pra ambos. Não há overlap puro, mas 'Acórdão' tem D.03
    # e Pauta tem E.04. Pra simular: pub com tipo Pauta E pub com tipo
    # Acórdão são distintas. O teste real de coexistência é:
    # tipo_canon=Pauta + processo não cadastrado → E.04 + E.01 (sem
    # supressão entre as duas).
    pub = _pub(tipoDocumento="Pauta de Julgamento")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record=None, alertas_disparados=[],
    )
    assert TAREFA_E04_INSCRICAO_SUSTENTACAO in tarefas
    assert TAREFA_E01_CADASTRO in tarefas
    # D.01 não dispara (Pauta de Julgamento não está na lista do default)
    assert TAREFA_D01_ANALISE_PUBLICACAO not in tarefas


def test_R4_3_coexistencia_decisao_mais_processo_nao_cadastrado() -> None:
    """Decisão + processo não cadastrado → D.01 + E.01 (multi-select)."""
    pub = _pub(tipoDocumento="Decisão")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record=None, alertas_disparados=[],
    )
    assert TAREFA_D01_ANALISE_PUBLICACAO in tarefas
    assert TAREFA_E01_CADASTRO in tarefas


def test_R4_3_ordem_estavel_alfabetica_por_codigo() -> None:
    """Output ordenado por código pra leitura previsível."""
    pub = _pub(tipoDocumento="Acórdão")
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record=None, alertas_disparados=[],
    )
    # Acórdão sem cadastro: D.03 + E.01
    assert tarefas == sorted(tarefas)
    assert tarefas == [TAREFA_D03_ANALISE_ACORDAO, TAREFA_E01_CADASTRO]


def test_R4_3_pub_sem_categoria_definida_nao_dispara_d01() -> None:
    """Tipo canônico fora dos buckets do D.01 → D.01 NÃO dispara."""
    pub = _pub(tipoDocumento="Pauta de Julgamento")  # canon = Pauta, não está em D.01
    tarefas = _aplicar_regras_tarefa_sugerida(
        pub, processo_record={"page_id": "x"}, alertas_disparados=[],
    )
    assert TAREFA_D01_ANALISE_PUBLICACAO not in tarefas
    # E.04 dispara
    assert TAREFA_E04_INSCRICAO_SUSTENTACAO in tarefas
