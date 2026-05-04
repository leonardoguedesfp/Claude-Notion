"""Round 5a (2026-05-04) — testes de regressão para Frente A.

Garante que a propriedade ``Partes`` na canônica nunca volte ao formato
JSON cru (regressão diagnosticada no relatório de anatomia pós-Round-4).

Causa-raiz: ``dje_dedup._merge_partes`` produzia ``json.dumps(out)``,
sobrescrevendo o output de ``formatar_partes`` no PATCH do flush das
duplicatas. 530 das 1.608 canônicas (33%) ficaram com Partes em formato
``[{"comunicacao_id":..., "nome":..., "polo":...}]``.

Fixtures usam payloads reais dos 5 clusters afetados (extraídos de
SQLite via ``payload_json``):

- TRT10 Acórdão  — 100% afetado (94/94)
- TRT10 Notif    — 56% afetado (408/723)
- TST Decisão    — 100% afetado (8/8)
- STJ Decisão    — 16% afetado (5/32)
- TRT10 Lista    — 2% afetado (4/201)
"""
from __future__ import annotations

import json

from notion_rpadv.services.dje_dedup import _build_update_payload, _merge_partes


# ---------- helpers ----------


def _payload_canon(djen_id: int, destinatarios: list[dict]) -> str:
    """Monta string ``payload_json`` mínima que ``_build_update_payload``
    consegue ler — só precisa ter ``destinatarios``."""
    return json.dumps({"id": djen_id, "destinatarios": destinatarios})


def _canonica_row(djen_id: int, destinatarios: list[dict]) -> dict:
    return {
        "djen_id": djen_id,
        "payload_json": _payload_canon(djen_id, destinatarios),
    }


def _pendente(djen_id: int, destinatarios: list[dict], descritor: str) -> dict:
    return {
        "duplicata_djen_id": djen_id,
        "duplicata_partes_json": json.dumps(destinatarios),
        "duplicata_advogados_json": "[]",
        "duplicata_destinatario": descritor,
    }


def _assert_partes_legivel(partes_str: str) -> None:
    """Asserções comuns: formato Polo Ativo/Passivo, sem JSON cru."""
    assert isinstance(partes_str, str)
    # Não pode começar com '[' (sinal de JSON cru).
    assert not partes_str.startswith("["), (
        f"Partes voltou ao formato JSON cru: {partes_str[:200]!r}"
    )
    # Não pode conter o campo interno do payload DJEN.
    assert "comunicacao_id" not in partes_str
    # Tem que ter ao menos um label canônico.
    has_label = (
        "Polo Ativo:" in partes_str
        or "Polo Passivo:" in partes_str
        or "Terceiro Interessado:" in partes_str
        or partes_str.startswith("Polo ")  # fallback "Polo X" para polo não-canônico
    )
    assert has_label, f"Partes sem label esperado: {partes_str[:200]!r}"


# ---------- Cluster 1: TRT10 Acórdão (100% afetado) ----------


def test_R5a_trt10_acordao_partes_legivel_apos_dedup():
    """djen=573369859 (TRT10 Acórdão sentinela)."""
    canon_dest = [
        {"comunicacao_id": 573369859, "nome": "BANCO DO BRASIL SA", "polo": "P"},
        {
            "comunicacao_id": 573369859,
            "nome": "ZULEIDE MALHEIROS DA FRANCA DA SILVA",
            "polo": "A",
        },
    ]
    dup_dest = [
        # Duplicata pode trazer mesmos destinatários (ex: troca de polo)
        {"comunicacao_id": 573369915, "nome": "ZULEIDE MALHEIROS DA FRANCA DA SILVA", "polo": "A"},
    ]
    out = _merge_partes(
        json.dumps(canon_dest),
        [json.dumps(dup_dest)],
    )
    _assert_partes_legivel(out)
    assert "Polo Ativo: ZULEIDE MALHEIROS DA FRANCA DA SILVA" in out
    assert "Polo Passivo: BANCO DO BRASIL SA" in out


# ---------- Cluster 2: TRT10 Notificação (56% afetado) ----------


def test_R5a_trt10_notificacao_partes_legivel_apos_dedup():
    """djen=494748109 (TRT10 Notif sentinela do baseline)."""
    canon_dest = [
        {"comunicacao_id": 494748109, "nome": "BANCO DO BRASIL SA", "polo": "P"},
        {
            "comunicacao_id": 494748109,
            "nome": "DENITA GOMES GUIMARAES",
            "polo": "A",
        },
    ]
    dup_dest = [
        {"comunicacao_id": 494748135, "nome": "BANCO DO BRASIL SA", "polo": "P"},
    ]
    out = _merge_partes(
        json.dumps(canon_dest),
        [json.dumps(dup_dest)],
    )
    _assert_partes_legivel(out)
    assert "Polo Ativo: DENITA GOMES GUIMARAES" in out
    assert "Polo Passivo: BANCO DO BRASIL SA" in out


def test_R5a_trt10_notif_multi_polo_ativo_apos_dedup():
    """djen=495174885 (TRT10 Notif com 3 destinatários no polo A)."""
    canon_dest = [
        {"comunicacao_id": 495174885, "nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"comunicacao_id": 495174885, "nome": "GISELE CRISTINE DE ALMEIDA MONTENEGRO", "polo": "A"},
        {"comunicacao_id": 495174885, "nome": "MARIA CRISTINA DO VALE CASTILHO", "polo": "A"},
        {"comunicacao_id": 495174885, "nome": "UNIÃO FEDERAL (PGF) - DF", "polo": "A"},
    ]
    out = _merge_partes(json.dumps(canon_dest), [])
    _assert_partes_legivel(out)
    # Múltiplos nomes no Polo Ativo separados por vírgula
    assert "Polo Ativo: GISELE" in out
    assert "MARIA CRISTINA" in out
    assert "UNIÃO FEDERAL" in out
    assert "Polo Passivo: BANCO DO BRASIL SA" in out


# ---------- Cluster 3: TST Decisão (100% afetado) ----------


def test_R5a_tst_decisao_partes_legivel_apos_dedup():
    """TST Decisão — 100% das 8 canônicas afetadas."""
    canon_dest = [
        {"comunicacao_id": 547728624, "nome": "BANCO DO BRASIL S.A.", "polo": "P"},
        {"comunicacao_id": 547728624, "nome": "CLEMICE ALVARES OLIVEIRA TANABE", "polo": "A"},
    ]
    dup_dest = [
        {"comunicacao_id": 547728999, "nome": "CLEMICE ALVARES OLIVEIRA TANABE", "polo": "A"},
    ]
    out = _merge_partes(
        json.dumps(canon_dest),
        [json.dumps(dup_dest)],
    )
    _assert_partes_legivel(out)
    assert "Polo Ativo: CLEMICE ALVARES OLIVEIRA TANABE" in out
    assert "Polo Passivo: BANCO DO BRASIL S.A." in out


# ---------- Cluster 4: STJ Decisão (16% afetado) ----------


def test_R5a_stj_decisao_partes_legivel_apos_dedup():
    """STJ Decisão — destinatários têm prefixo numerado N. NOME (PAPEL).

    Mantemos esse prefixo dentro da string formatada (D1 do Round 4:
    formato genérico Polo Ativo/Passivo, não nomenclatura específica).
    """
    canon_dest = [
        {
            "comunicacao_id": 596733179,
            "nome": "1. TULIO JOSE NASCIMENTO MATA (RECORRENTE)",
            "polo": "A",
        },
        {
            "comunicacao_id": 596733179,
            "nome": "2. CAIXA DE PREVIDENCIA DOS FUNCS DO BANCO DO BRASIL (RECORRIDO)",
            "polo": "P",
        },
    ]
    dup_dest = [
        {
            "comunicacao_id": 596733200,
            "nome": "1. TULIO JOSE NASCIMENTO MATA (RECORRENTE)",
            "polo": "A",
        },
    ]
    out = _merge_partes(
        json.dumps(canon_dest),
        [json.dumps(dup_dest)],
    )
    _assert_partes_legivel(out)
    assert "Polo Ativo: 1. TULIO JOSE NASCIMENTO MATA (RECORRENTE)" in out
    assert "Polo Passivo: 2. CAIXA DE PREVIDENCIA" in out


# ---------- Cluster 5: TRT10 Lista (2% afetado) ----------


def test_R5a_trt10_lista_partes_legivel_apos_dedup():
    """TRT10 Lista de Distribuição — 4/201 afetadas."""
    canon_dest = [
        {"comunicacao_id": 496542520, "nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"comunicacao_id": 496542520, "nome": "VERA LILIAM LAMEGO MORO", "polo": "A"},
    ]
    dup_dest = [
        {"comunicacao_id": 496542600, "nome": "VERA LILIAM LAMEGO MORO", "polo": "A"},
    ]
    out = _merge_partes(
        json.dumps(canon_dest),
        [json.dumps(dup_dest)],
    )
    _assert_partes_legivel(out)
    assert "Polo Ativo: VERA LILIAM LAMEGO MORO" in out
    assert "Polo Passivo: BANCO DO BRASIL SA" in out


# ---------- Teste end-to-end: _build_update_payload ----------


def test_R5a_build_update_payload_envia_partes_legivel():
    """Garante que o PATCH produzido pelo flush das duplicatas envia
    Partes formatado, não JSON cru. Esta é a defesa final contra a
    regressão do Round 4: o caller do flush é quem PATCH-eia o Notion,
    e este payload é o que vira o conteúdo da pub canônica.
    """
    canon_dest = [
        {"comunicacao_id": 494748109, "nome": "BANCO DO BRASIL SA", "polo": "P"},
        {
            "comunicacao_id": 494748109,
            "nome": "DENITA GOMES GUIMARAES",
            "polo": "A",
        },
    ]
    canon_row = _canonica_row(494748109, canon_dest)
    pendentes = [
        _pendente(
            494748135,
            [{"comunicacao_id": 494748135, "nome": "BANCO DO BRASIL SA", "polo": "P"}],
            "Cecília (20120/DF) — BANCO DO BRASIL SA",
        ),
    ]

    payload = _build_update_payload(
        canon_row,
        pendentes,
        schema_tem_duplicatas_suprimidas=True,
    )

    # A chave 'Partes' tem que vir como rich_text com content legível
    partes_blocks = payload["Partes"]["rich_text"]
    assert len(partes_blocks) == 1
    content = partes_blocks[0]["text"]["content"]
    _assert_partes_legivel(content)
    assert "Polo Ativo: DENITA GOMES GUIMARAES" in content
    assert "Polo Passivo: BANCO DO BRASIL SA" in content
    # E 'Duplicatas suprimidas' está presente (schema_tem_duplicatas_suprimidas=True)
    assert "Duplicatas suprimidas" in payload
    assert "djen=494748135" in payload["Duplicatas suprimidas"]["rich_text"][0]["text"]["content"]


# ---------- Idempotência: reprocessar mesma canônica não corrompe ----------


def test_R5a_merge_partes_idempotente_sem_duplicatas():
    """Sem duplicatas, _merge_partes devolve formato legível só com a
    canônica. Confirma que o caminho normal (sem dedup) também funciona.
    """
    canon_dest = [
        {"nome": "BANCO DO BRASIL SA", "polo": "P"},
        {"nome": "DENITA GOMES GUIMARAES", "polo": "A"},
    ]
    out = _merge_partes(json.dumps(canon_dest), [])
    _assert_partes_legivel(out)
    assert "Polo Ativo: DENITA GOMES GUIMARAES" in out
    assert "Polo Passivo: BANCO DO BRASIL SA" in out


def test_R5a_merge_partes_canonica_vazia():
    """Edge case: payload sem destinatários."""
    out = _merge_partes(None, [])
    assert out == ""
