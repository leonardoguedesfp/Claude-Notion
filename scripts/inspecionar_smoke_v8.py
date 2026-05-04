"""Inspeção do smoke test das regras v8 (Round 6 + Round 7).

Cruza ``leitor_dje.db`` (SQLite local pós-captura) com a database
``📬 Publicações`` no Notion (via ``NotionClient.query_all`` — mesmo
cliente usado pelo app PySide6 para gravar). Gera relatório Markdown
estruturado em ``logs/smoke_v8_<timestamp>.md`` com 7 seções:

1. Totais (SQLite × Notion + diferença).
2. Distribuição por par (Tipo de comunicação × Tipo de documento).
3. Camada base — validação por regra (40-43).
4. Regras de monitoramento — disparos (39 entradas cobrindo 41 das 43
   regras v8: 16 do Round 6 + 23 do Round 7).
5. Composição (pubs com 2+ alertas).
6. Auditoria de valores depreciados (D.01-D.03, E.01/02/04, "Pauta
   presencial sem inscrição", "Instância desatualizada" sem qualif).
7. Schema observado (cruzando com vocabulário canônico v8 — 3 tarefas
   + 41 alertas).

Regras 25 (troca de relator sequencial) e 37 (inatividade prolongada
PREVI/RESP) ficam fora — exigem histórico de pubs anteriores.

Uso:
    python scripts/inspecionar_smoke_v8.py [--verbose] [--no-notion]

Read-only: zero escrita em Notion ou SQLite. Idempotente.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# --- bootstrap path ---
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from notion_bulk_edit.config import KEYRING_SERVICE, KEYRING_USERNAME  # noqa: E402
from notion_bulk_edit.notion_api import NotionClient  # noqa: E402
from notion_rpadv.services.dje_notion_constants import (  # noqa: E402
    NOTION_PUBLICACOES_DATA_SOURCE_ID,
)
from notion_rpadv.services.dje_regras_v8 import (  # noqa: E402
    ALERTA_ACORDAO_EM_1GRAU,
    ALERTA_ATIVIDADE_EM_PROCESSO_ARQUIVADO,
    ALERTA_ATIVIDADE_POS_ENCERRAMENTO_EXECUTIVO,
    ALERTA_CAPTURAR_DATA_DISTRIBUICAO,
    ALERTA_CAPTURAR_LINK_EXTERNO,
    ALERTA_CAPTURAR_NUMERACAO_STF,
    ALERTA_CAPTURAR_NUMERACAO_STJ_TST,
    ALERTA_CIDADE_DESATUALIZADA,
    ALERTA_CONFERIR_DATA_DISTRIBUICAO,
    ALERTA_CONFERIR_NATUREZA_PROCESSO,
    ALERTA_CONFERIR_NUMERO_CNJ,
    ALERTA_CONFERIR_POSICAO_DO_CLIENTE,
    ALERTA_CONFERIR_SENTENCA_FASE_POS_COGNITIVA,
    ALERTA_CONFERIR_TEMA_955,
    ALERTA_CONFERIR_TIPO_PROCESSO,
    ALERTA_CONFERIR_TRIBUNAL_ORIGEM,
    ALERTA_CONFERIR_VINCULACAO_CLIENTE_PROCESSO,
    ALERTA_FASE_DESATUALIZADA_COGNITIVA,
    ALERTA_FASE_DESATUALIZADA_EXECUTIVA,
    ALERTA_FASE_DESATUALIZADA_LIQUIDACAO,
    ALERTA_INCLUIR_JULGAMENTO_NO_CONTROLE,
    ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA,
    ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA,
    ALERTA_PARTE_ADVERSA_BB,
    ALERTA_PARTE_ADVERSA_BB_CONSORCIOS,
    ALERTA_PARTE_ADVERSA_BRADESCO_SAUDE,
    ALERTA_PARTE_ADVERSA_CASSI,
    ALERTA_PARTE_ADVERSA_PREVI,
    ALERTA_PAUTA_EM_1GRAU,
    ALERTA_PAUTA_EM_PROCESSO_ARQUIVADO,
    ALERTA_PROCESSO_NAO_CADASTRADO,
    ALERTA_PROCESSO_RECURSO_DISTRIBUIDO,
    ALERTA_RECURSO_AUTONOMO_SEM_PROCESSO_PAI,
    ALERTA_RELATOR_DESATUALIZADO,
    ALERTA_SENTENCA_EM_COLEGIADO,
    ALERTA_TEXTO_IMPRESTAVEL,
    ALERTA_TRANSITO_PENDENTE,
    ALERTA_TRIBUNAL_FORA_VOCABULARIO,
    ALERTA_TURMA_DESATUALIZADA,
    ALERTA_VARA_DESATUALIZADA,
    ALERTA_VINCULAR_CLIENTE_AO_PROCESSO,
    TAREFA_ANALISAR_ACORDAO,
    TAREFA_ANALISAR_SENTENCA,
    TAREFA_NADA_PARA_FAZER,
)

# ---------------------------------------------------------------------------
# Vocabulário v8 (alinhado com schema do Notion confirmado em 2026-05-04)
# ---------------------------------------------------------------------------

TAREFAS_CANONICAS: tuple[str, ...] = (
    TAREFA_ANALISAR_ACORDAO,
    TAREFA_ANALISAR_SENTENCA,
    TAREFA_NADA_PARA_FAZER,
)

ALERTAS_CANONICOS: tuple[str, ...] = (
    "Processo não cadastrado",
    "Trânsito em julgado pendente",
    "Texto imprestável",
    "Processo/recurso distribuído",
    "Incluir julgamento no controle",
    "Conferir número CNJ do processo",
    "Capturar numeração STJ/TST",
    "Capturar numeração STF",
    "Conferir natureza do processo",
    "Conferir tipo de processo",
    "Vincular cliente ao processo",
    "Conferir vinculação cliente-processo",
    "Conferir posição do cliente",
    "Banco do Brasil ausente em partes adversas",
    "PREVI ausente em partes adversas",
    "CASSI ausente em partes adversas",
    "Bradesco Saúde ausente em partes adversas",
    "BB Adm. Consórcios ausente em partes adversas",
    "Tribunal fora do vocabulário",
    "Conferir tribunal de origem",
    "Instância desatualizada (subida)",
    "Instância desatualizada (descida)",
    "Acórdão em processo de 1º grau",
    "Sentença em processo de colegiado",
    "Pauta em processo de 1º grau",
    "Cidade desatualizada",
    "Vara desatualizada",
    "Turma desatualizada",
    "Relator desatualizado",
    "Fase desatualizada (executiva)",
    "Fase desatualizada (liquidação)",
    "Fase desatualizada (cognitiva)",
    "Conferir sentença em fase pós-cognitiva",
    "Pauta em processo arquivado",
    "Atividade em processo arquivado",
    "Conferir Tema 955",
    "Capturar data de distribuição",
    "Conferir data de distribuição",
    "Atividade pós-encerramento executivo",
    "Capturar link externo",
    "Recurso autônomo sem processo pai",
)

#: Valores que NÃO PODEM aparecer no acervo pós-Round-6 (regressão).
VALORES_DEPRECIADOS_TAREFA: tuple[str, ...] = (
    "D.01 Análise de publicação",
    "D.02 Análise de sentença",
    "D.03 Análise de acórdão",
    "E.01 Cadastro de cliente/processo",
    "E.02 Atualizar dados no sistema",
    "E.04 Inscrição para sustentação oral",
)
VALORES_DEPRECIADOS_ALERTA: tuple[str, ...] = (
    "Pauta presencial sem inscrição",
    # "Instância desatualizada" exato (sem qualificador entre parênteses)
    "Instância desatualizada",
)

#: Substrings que indicam D.01-E.04 mesmo se nome variar.
SUBSTRINGS_DEPRECIADAS_TAREFA: tuple[str, ...] = (
    "D.01", "D.02", "D.03", "E.01", "E.02", "E.04",
)


# ---------------------------------------------------------------------------
# Camada base — matriz Tipo de comunicação × Tipo de documento (v8 Sec VII)
# ---------------------------------------------------------------------------

def _camada_base_esperada(
    tipo_com: str, tipo_doc: str,
) -> tuple[set[str], set[str]]:
    """Devolve (tarefas_esperadas, alertas_esperados) da camada base."""
    if tipo_com == "Lista de Distribuição":
        return ({TAREFA_NADA_PARA_FAZER}, {ALERTA_PROCESSO_RECURSO_DISTRIBUIDO})
    if tipo_com == "Intimação" and tipo_doc == "Distribuição":
        return ({TAREFA_NADA_PARA_FAZER}, {ALERTA_PROCESSO_RECURSO_DISTRIBUIDO})
    if tipo_doc == "Pauta de Julgamento":
        return ({TAREFA_NADA_PARA_FAZER}, {ALERTA_INCLUIR_JULGAMENTO_NO_CONTROLE})
    if tipo_com == "Intimação" and tipo_doc == "Sentença":
        return ({TAREFA_ANALISAR_SENTENCA}, set())
    if tipo_com == "Intimação" and tipo_doc in {"Acórdão", "Ementa"}:
        return ({TAREFA_ANALISAR_ACORDAO}, set())
    return (set(), set())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _localizar_sqlite() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit("APPDATA não definido (esperado no Windows).")
    p = Path(appdata) / "NotionRPADV" / "leitor_dje.db"
    if not p.exists():
        raise SystemExit(f"SQLite não encontrado: {p}")
    return p


def _get_token() -> str:
    import keyring  # noqa: PLC0415
    tok = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if not tok:
        raise SystemExit("Token Notion não encontrado no keyring.")
    return tok


def _extrair_propriedades_pagina(page: dict) -> dict[str, Any]:
    """Extrai os campos de interesse de uma página Notion."""
    props = page.get("properties", {})

    def _select_value(prop: dict | None) -> str | None:
        if not prop:
            return None
        sel = prop.get("select")
        if sel:
            return sel.get("name")
        return None

    def _multi_select_values(prop: dict | None) -> list[str]:
        if not prop:
            return []
        items = prop.get("multi_select") or []
        return [it.get("name", "") for it in items if it.get("name")]

    def _number_value(prop: dict | None) -> int | None:
        if not prop:
            return None
        return prop.get("number")

    return {
        "page_id": page.get("id"),
        "id_djen": _number_value(props.get("ID DJEN")),
        "tribunal": _select_value(props.get("Tribunal")),
        "tipo_comunicacao": _select_value(props.get("Tipo de comunicação")),
        "tipo_documento": _select_value(props.get("Tipo de documento")),
        "tarefas": _multi_select_values(props.get("Tarefa sugerida (app)")),
        "alertas": _multi_select_values(props.get("Alerta contadoria (app)")),
    }


def _carregar_sqlite_publicacoes(
    db: Path,
) -> list[dict[str, Any]]:
    """Lê todas as canônicas do SQLite local com tipos canônicos
    derivados do payload_json."""
    from notion_rpadv.services.dje_notion_mappings import (
        mapear_tipo_comunicacao,
        mapear_tipo_documento,
    )

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows: list[dict[str, Any]] = []
    cur = conn.execute(
        "SELECT djen_id, sigla_tribunal, payload_json, notion_page_id, "
        "dup_canonical_djen_id "
        "FROM publicacoes "
        "WHERE dup_canonical_djen_id IS NULL"  # apenas canônicas
    )
    for r in cur:
        try:
            payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
        except json.JSONDecodeError:
            payload = {}
        rows.append({
            "id_djen": r["djen_id"],
            "tribunal": r["sigla_tribunal"],
            "tipo_comunicacao": mapear_tipo_comunicacao(payload.get("tipoComunicacao")),
            "tipo_documento": mapear_tipo_documento(payload.get("tipoDocumento")),
            "notion_page_id": r["notion_page_id"],
        })
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Sections — geração de markdown
# ---------------------------------------------------------------------------


def _md_section_totais(
    pubs_sqlite: list[dict],
    pubs_notion: list[dict],
) -> str:
    djens_sqlite = {p["id_djen"] for p in pubs_sqlite if p["id_djen"]}
    djens_notion = {p["id_djen"] for p in pubs_notion if p["id_djen"]}
    so_sqlite = djens_sqlite - djens_notion
    so_notion = djens_notion - djens_sqlite

    lines = ["## Totais", ""]
    lines.append(f"- Publicações canônicas no SQLite: **{len(djens_sqlite)}**")
    lines.append(f"- Publicações no Notion (📬 Publicações): **{len(djens_notion)}**")
    lines.append(f"- Diferença: **{abs(len(djens_sqlite) - len(djens_notion))}**")
    if so_sqlite or so_notion:
        lines.append("")
        lines.append("**⚠ Divergência detectada**:")
        if so_sqlite:
            lines.append(f"- {len(so_sqlite)} djens só no SQLite (não enviados ao Notion):")
            for d in sorted(so_sqlite)[:10]:
                lines.append(f"  - `djen={d}`")
            if len(so_sqlite) > 10:
                lines.append(f"  - ... (+{len(so_sqlite) - 10} omitidos)")
        if so_notion:
            lines.append(f"- {len(so_notion)} djens só no Notion (sem record SQLite):")
            for d in sorted(so_notion)[:10]:
                lines.append(f"  - `djen={d}`")
            if len(so_notion) > 10:
                lines.append(f"  - ... (+{len(so_notion) - 10} omitidos)")
    else:
        lines.append("- ✅ Zero divergência (esperado).")
    lines.append("")
    return "\n".join(lines)


def _md_section_distribuicao(pubs_notion: list[dict]) -> str:
    """Distribuição por par (Tipo de comunicação, Tipo de documento)."""
    counts: Counter[tuple[str, str]] = Counter()
    for p in pubs_notion:
        tc = p["tipo_comunicacao"] or "—"
        td = p["tipo_documento"] or "—"
        counts[(tc, td)] += 1

    lines = [
        "## Distribuição por par (Tipo de comunicação, Tipo de documento)",
        "",
        "| Tipo de comunicação | Tipo de documento | Pubs | Tarefa default (camada base) | Alerta default (camada base) |",
        "|---|---|---:|---|---|",
    ]
    for (tc, td), n in sorted(counts.items(), key=lambda x: -x[1]):
        tarefas_esp, alertas_esp = _camada_base_esperada(tc, td)
        t_str = ", ".join(sorted(tarefas_esp)) if tarefas_esp else "—"
        a_str = ", ".join(sorted(alertas_esp)) if alertas_esp else "—"
        lines.append(f"| {tc} | {td} | {n} | {t_str} | {a_str} |")
    lines.append("")
    return "\n".join(lines)


def _validar_camada_base(
    pubs_notion: list[dict],
) -> dict[str, dict[str, Any]]:
    """Para cada Regra 40-43, conta n_esperado vs n_observado e lista
    divergências (até 5 amostras)."""
    resultado: dict[str, dict[str, Any]] = {
        "Regra 40 (Distribuição)": {
            "esperados": [],
            "ok": 0,
            "divergencias": [],
        },
        "Regra 41 (Pauta)": {"esperados": [], "ok": 0, "divergencias": []},
        "Regra 42 (Sentença)": {"esperados": [], "ok": 0, "divergencias": []},
        "Regra 43 (Acórdão/Ementa)": {"esperados": [], "ok": 0, "divergencias": []},
    }

    for p in pubs_notion:
        tc = p["tipo_comunicacao"]
        td = p["tipo_documento"]
        if not tc or not td:
            continue

        # Identifica regra (mutuamente exclusivas)
        regra: str | None = None
        if tc == "Lista de Distribuição" or (tc == "Intimação" and td == "Distribuição"):
            regra = "Regra 40 (Distribuição)"
        elif td == "Pauta de Julgamento":
            regra = "Regra 41 (Pauta)"
        elif tc == "Intimação" and td == "Sentença":
            regra = "Regra 42 (Sentença)"
        elif tc == "Intimação" and td in {"Acórdão", "Ementa"}:
            regra = "Regra 43 (Acórdão/Ementa)"
        if regra is None:
            continue

        resultado[regra]["esperados"].append(p["id_djen"])

        tarefas_esp, alertas_esp = _camada_base_esperada(tc, td)
        tarefas_obs = set(p["tarefas"])
        alertas_obs = set(p["alertas"])

        # Validação: cada tarefa/alerta esperada deve estar presente
        tarefas_ok = tarefas_esp.issubset(tarefas_obs)
        alertas_ok = alertas_esp.issubset(alertas_obs)
        if tarefas_ok and alertas_ok:
            resultado[regra]["ok"] += 1
        elif len(resultado[regra]["divergencias"]) < 5:
            resultado[regra]["divergencias"].append({
                "djen": p["id_djen"],
                "esperado_tarefa": sorted(tarefas_esp),
                "obs_tarefa": sorted(tarefas_obs),
                "esperado_alerta": sorted(alertas_esp),
                "obs_alerta": sorted(alertas_obs),
            })

    return resultado


def _md_section_camada_base(pubs_notion: list[dict]) -> str:
    res = _validar_camada_base(pubs_notion)
    lines = ["## Camada base — validação por regra", ""]
    for regra, dados in res.items():
        n_esp = len(dados["esperados"])
        n_ok = dados["ok"]
        status = "✅" if n_ok == n_esp and n_esp > 0 else (
            "—" if n_esp == 0 else "⚠"
        )
        lines.append(f"### {status} {regra}")
        lines.append("")
        lines.append(f"- Pubs candidatas: **{n_esp}**")
        lines.append(f"- OK (tarefas + alertas conforme esperado): **{n_ok}**")
        if n_esp > 0:
            lines.append(f"- Divergências reportadas: **{n_esp - n_ok}** (até 5 listadas)")
            for d in dados["divergencias"]:
                lines.append(
                    f"  - `djen={d['djen']}` → "
                    f"esperado tarefa={d['esperado_tarefa']!r} alerta={d['esperado_alerta']!r}; "
                    f"observado tarefa={d['obs_tarefa']!r} alerta={d['obs_alerta']!r}"
                )
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Seção 4 — Regras de monitoramento
# ---------------------------------------------------------------------------

#: Definição de cada regra de monitoramento implementada (Round 6 + Round 7).
#: (alerta_canonico, descricao_curta) — agrupadas por sub-round/seção da v8.
#: Para regras que compartilham alerta (ex: R4+R5 → "Conferir natureza"),
#: a contagem aparecerá igual em ambas as linhas — é o mesmo alerta no Notion.
REGRAS_MONITORAMENTO: list[tuple[str, str]] = [
    # --- Round 6 ---
    # Identificação categórica (impossibilidades)
    (ALERTA_ACORDAO_EM_1GRAU, "Regra 16 — Acórdão em processo de 1º grau (impossível)"),
    (ALERTA_SENTENCA_EM_COLEGIADO, "Regra 17 — Sentença em colegiado (impossível)"),
    (ALERTA_PAUTA_EM_1GRAU, "Regra 18 — Pauta em processo de 1º grau (impossível)"),
    # Instância (subida/descida)
    (ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA, "Regra 14 — Subida de instância não detectada"),
    (ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA, "Regra 15 — Descida de instância não detectada"),
    # Fase
    (ALERTA_FASE_DESATUALIZADA_EXECUTIVA, "Regra 26 — Fase executiva confirmada por classe"),
    (ALERTA_FASE_DESATUALIZADA_LIQUIDACAO, "Regra 27 — Fase liquidação confirmada por classe"),
    (ALERTA_FASE_DESATUALIZADA_COGNITIVA, "Regra 28 — Fase cognitiva contradita por classe avançada"),
    # Trânsito
    (ALERTA_TRANSITO_PENDENTE, "Regra 35 — Trânsito cognitivo pendente"),
    # Partes adversas (Regra 11 — 5 alertas distintos)
    (ALERTA_PARTE_ADVERSA_BB, "Regra 11 — Banco do Brasil ausente em partes adversas"),
    (ALERTA_PARTE_ADVERSA_PREVI, "Regra 11 — PREVI ausente em partes adversas"),
    (ALERTA_PARTE_ADVERSA_CASSI, "Regra 11 — CASSI ausente em partes adversas"),
    (ALERTA_PARTE_ADVERSA_BRADESCO_SAUDE, "Regra 11 — Bradesco Saúde ausente em partes adversas"),
    (ALERTA_PARTE_ADVERSA_BB_CONSORCIOS, "Regra 11 — BB Adm. Consórcios ausente em partes adversas"),
    # Técnicos / operacionais (sem número formal)
    (ALERTA_TEXTO_IMPRESTAVEL, "Técnico — Texto imprestável (sem regra numerada na v8)"),
    (ALERTA_PROCESSO_NAO_CADASTRADO, "Operacional — Processo não cadastrado (não dispara em distribuição)"),

    # --- Round 7a — Tribunal e numerações superiores ---
    (ALERTA_CAPTURAR_NUMERACAO_STJ_TST, "Regra 2 — Capturar numeração STJ/TST"),
    (ALERTA_CAPTURAR_NUMERACAO_STF, "Regra 3 — Capturar numeração STF"),
    (ALERTA_TRIBUNAL_FORA_VOCABULARIO, "Regra 12 — Tribunal fora do vocabulário"),
    (ALERTA_CONFERIR_TRIBUNAL_ORIGEM, "Regra 13 — Conferir tribunal de origem"),

    # --- Round 7b — Classificação processual + processo pai ---
    # R4 e R5 disparam o MESMO alerta — duas entradas mostram a mesma
    # contagem; é o conjunto de pubs com Conferir natureza, vindo de
    # qualquer um dos dois critérios (Tribunal ou Classe).
    (ALERTA_CONFERIR_NATUREZA_PROCESSO, "Regras 4+5 — Conferir natureza do processo (vs Tribunal/Classe)"),
    (ALERTA_CONFERIR_TIPO_PROCESSO, "Regra 6 — Conferir tipo de processo (recurso autônomo cadastrado como Principal)"),
    (ALERTA_RECURSO_AUTONOMO_SEM_PROCESSO_PAI, "Regra 39 — Recurso autônomo sem processo pai"),

    # --- Round 7c — Estado processual + link ---
    (ALERTA_CONFERIR_SENTENCA_FASE_POS_COGNITIVA, "Regra 29 — Conferir sentença em fase pós-cognitiva"),
    (ALERTA_PAUTA_EM_PROCESSO_ARQUIVADO, "Regra 30 — Pauta em processo arquivado"),
    (ALERTA_ATIVIDADE_EM_PROCESSO_ARQUIVADO, "Regra 31 — Atividade em processo arquivado"),
    (ALERTA_CAPTURAR_LINK_EXTERNO, "Regra 38 — Capturar link externo"),

    # --- Round 7d — Cliente e posição ---
    # R7 e R8 compartilham alerta (mesma ação operacional: vincular cliente).
    (ALERTA_VINCULAR_CLIENTE_AO_PROCESSO, "Regras 7+8 — Vincular cliente ao processo (cliente fora ou litisconsórcio)"),
    (ALERTA_CONFERIR_VINCULACAO_CLIENTE_PROCESSO, "Regra 9 — Conferir vinculação cliente-processo"),
    (ALERTA_CONFERIR_POSICAO_DO_CLIENTE, "Regra 10 — Conferir posição do cliente (em 1º grau)"),

    # --- Round 7e — Localização (Cidade, Vara, Turma, Relator) ---
    # R19+R20 e R21+R22 compartilham alertas (ações idênticas: extrair/conferir).
    (ALERTA_CIDADE_DESATUALIZADA, "Regras 19+20 — Cidade desatualizada (faltando ou divergente)"),
    (ALERTA_VARA_DESATUALIZADA, "Regras 21+22 — Vara desatualizada (faltando ou divergente)"),
    (ALERTA_TURMA_DESATUALIZADA, "Regra 23 — Turma desatualizada"),
    (ALERTA_RELATOR_DESATUALIZADO, "Regra 24 — Relator desatualizado"),

    # --- Round 7f — CNJ + Tema 955 + datas ---
    (ALERTA_CONFERIR_NUMERO_CNJ, "Regra 1 — Conferir número CNJ do processo"),
    (ALERTA_CONFERIR_TEMA_955, "Regra 32 — Conferir Tema 955"),
    (ALERTA_CAPTURAR_DATA_DISTRIBUICAO, "Regra 33 — Capturar data de distribuição"),
    (ALERTA_CONFERIR_DATA_DISTRIBUICAO, "Regra 34 — Conferir data de distribuição (≥30 dias antes)"),
    (ALERTA_ATIVIDADE_POS_ENCERRAMENTO_EXECUTIVO, "Regra 36 — Atividade pós-encerramento executivo"),
]


def _md_section_monitoramento(pubs_notion: list[dict]) -> str:
    """Para cada regra de monitoramento, conta disparos + 3 exemplos."""
    djens_por_alerta: dict[str, list[int]] = defaultdict(list)
    for p in pubs_notion:
        for a in p["alertas"]:
            djens_por_alerta[a].append(p["id_djen"])

    lines = [
        "## Regras de monitoramento — disparos",
        "",
        "**39 entradas** cobrindo 39 alertas distintos das 41 das 43 regras v8 implementadas:",
        "",
        "- Round 6 (16 entradas): Regras 11×5, 14, 15, 16, 17, 18, 26, 27, 28, 35 + Texto imprestável + Processo não cadastrado.",
        "- Round 7 (23 entradas): Regras 1, 2, 3, 4+5, 6, 7+8, 9, 10, 12, 13, 19+20, 21+22, 23, 24, 29, 30, 31, 32, 33, 34, 36, 38, 39.",
        "",
        "Regras 25 (troca de relator sequencial) e 37 (inatividade prolongada PREVI/RESP) ficam fora — exigem histórico de pubs anteriores.",
        "",
        "Algumas linhas reportam **regras múltiplas** que compartilham alerta (R4+R5 → Conferir natureza; R7+R8 → Vincular cliente; R19+R20 → Cidade desatualizada; R21+R22 → Vara desatualizada). Nesses casos a contagem é por alerta no Notion, não por critério individual de gatilho.",
        "",
        "Dos 41 alertas do select v8, 39 são monitoramento (listados abaixo) + 2 da camada base (Processo/recurso distribuído na R40 e Incluir julgamento no controle na R41 — validados na Seção 3).",
        "",
        "| Regra / Alerta | Disparos | Exemplos (até 3 IDs DJEN) |",
        "|---|---:|---|",
    ]
    for alerta, descricao in REGRAS_MONITORAMENTO:
        djens = djens_por_alerta.get(alerta, [])
        amostras = ", ".join(f"`{d}`" for d in djens[:3]) if djens else "—"
        lines.append(f"| {descricao} (`{alerta}`) | {len(djens)} | {amostras} |")
    lines.append("")
    return "\n".join(lines)


def _md_section_composicao(pubs_notion: list[dict]) -> str:
    """Pubs com 2+ alertas — total + até 5 exemplos."""
    multi = [p for p in pubs_notion if len(p["alertas"]) >= 2]
    lines = ["## Composição — pubs com 2+ alertas", ""]
    lines.append(f"- Pubs com 2+ alertas: **{len(multi)}**")
    lines.append("")
    if multi:
        lines.append("Exemplos (até 5):")
        lines.append("")
        lines.append("| ID DJEN | Tribunal | Tipo de comunicação | Tipo de documento | Tarefas | Alertas |")
        lines.append("|---|---|---|---|---|---|")
        for p in multi[:5]:
            tarefas = ", ".join(p["tarefas"]) if p["tarefas"] else "—"
            alertas = ", ".join(p["alertas"])
            lines.append(
                f"| `{p['id_djen']}` | {p['tribunal']} | "
                f"{p['tipo_comunicacao']} | {p['tipo_documento']} | "
                f"{tarefas} | {alertas} |"
            )
    lines.append("")
    return "\n".join(lines)


def _md_section_auditoria_depreciados(pubs_notion: list[dict]) -> str:
    """Verifica que nenhum valor depreciado aparece em Tarefa/Alerta."""
    achados_tarefa: list[tuple[int, str]] = []  # (djen, valor)
    achados_alerta: list[tuple[int, str]] = []

    for p in pubs_notion:
        for t in p["tarefas"]:
            # match exato OU substring (D.01-E.04)
            if t in VALORES_DEPRECIADOS_TAREFA or any(
                sub in t for sub in SUBSTRINGS_DEPRECIADAS_TAREFA
            ):
                achados_tarefa.append((p["id_djen"], t))
        for a in p["alertas"]:
            if a in VALORES_DEPRECIADOS_ALERTA:
                achados_alerta.append((p["id_djen"], a))

    lines = ["## Auditoria de valores depreciados", ""]
    total = len(achados_tarefa) + len(achados_alerta)
    if total == 0:
        lines.append("✅ **Zero valores depreciados detectados.**")
        lines.append("")
        lines.append("- Nenhuma pub com Tarefa em {D.01-D.03, E.01/02/04}.")
        lines.append("- Nenhuma pub com Alerta em {Pauta presencial sem inscrição,")
        lines.append("  'Instância desatualizada' sem qualificador}.")
    else:
        lines.append(f"🔴 **FALHA — {total} valor(es) depreciado(s) detectados.**")
        lines.append("")
        if achados_tarefa:
            lines.append(f"### Tarefa depreciada ({len(achados_tarefa)} ocorrências)")
            for d, t in achados_tarefa[:20]:
                lines.append(f"- `djen={d}`: `{t!r}`")
            if len(achados_tarefa) > 20:
                lines.append(f"- ... (+{len(achados_tarefa) - 20} omitidos)")
        if achados_alerta:
            lines.append("")
            lines.append(f"### Alerta depreciado ({len(achados_alerta)} ocorrências)")
            for d, a in achados_alerta[:20]:
                lines.append(f"- `djen={d}`: `{a!r}`")
            if len(achados_alerta) > 20:
                lines.append(f"- ... (+{len(achados_alerta) - 20} omitidos)")
    lines.append("")
    return "\n".join(lines)


def _md_section_schema_observado(pubs_notion: list[dict]) -> str:
    """Lista valores únicos vistos em Tarefa sugerida (app) e Alerta
    contadoria (app), cruzando com vocabulário canônico."""
    tarefas_obs: set[str] = set()
    alertas_obs: set[str] = set()
    for p in pubs_notion:
        tarefas_obs.update(p["tarefas"])
        alertas_obs.update(p["alertas"])

    canon_tarefas = set(TAREFAS_CANONICAS)
    canon_alertas = set(ALERTAS_CANONICOS)

    lines = ["## Schema observado", ""]
    lines.append(f"### Tarefa sugerida (app) — {len(tarefas_obs)} valor(es) único(s) observado(s)")
    lines.append("")
    if not tarefas_obs:
        lines.append("- (nenhum valor observado — pubs sem tarefa atribuída?)")
    else:
        for t in sorted(tarefas_obs):
            mark = "✅" if t in canon_tarefas else "🔴 fora do vocabulário canônico"
            lines.append(f"- `{t}` {mark}")
    fora_t = tarefas_obs - canon_tarefas
    if fora_t:
        lines.append("")
        lines.append(f"⚠ **{len(fora_t)} valor(es) observado(s) fora do select v8** (3 canônicos): {sorted(fora_t)!r}")

    lines.append("")
    lines.append(f"### Alerta contadoria (app) — {len(alertas_obs)} valor(es) único(s) observado(s)")
    lines.append("")
    if not alertas_obs:
        lines.append("- (nenhum valor observado)")
    else:
        for a in sorted(alertas_obs):
            mark = "✅" if a in canon_alertas else "🔴 fora do vocabulário canônico"
            lines.append(f"- `{a}` {mark}")
    fora_a = alertas_obs - canon_alertas
    if fora_a:
        lines.append("")
        lines.append(f"⚠ **{len(fora_a)} valor(es) observado(s) fora do select v8** (41 canônicos): {sorted(fora_a)!r}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Imprime o relatório no stdout além de salvar.",
    )
    parser.add_argument(
        "--no-notion", action="store_true",
        help="Pula a leitura da API Notion (modo dev/offline).",
    )
    args = parser.parse_args()

    # 1. SQLite
    db = _localizar_sqlite()
    pubs_sqlite = _carregar_sqlite_publicacoes(db)

    # 2. Notion via cliente do app
    if args.no_notion:
        pubs_notion: list[dict] = []
        notion_status = "(modo --no-notion: leitura do Notion pulada)"
    else:
        token = _get_token()
        client = NotionClient(token=token)
        pages = client.query_all(NOTION_PUBLICACOES_DATA_SOURCE_ID)
        pubs_notion = [_extrair_propriedades_pagina(p) for p in pages]
        notion_status = f"{len(pubs_notion)} páginas baixadas via NotionClient.query_all"

    # 3. Monta relatório
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    logs_dir = _REPO / "logs"
    logs_dir.mkdir(exist_ok=True)
    out_path = logs_dir / f"smoke_v8_{timestamp}.md"

    cmd = "python scripts/inspecionar_smoke_v8.py"
    if args.verbose:
        cmd += " --verbose"
    if args.no_notion:
        cmd += " --no-notion"
    header = [
        f"# Smoke test v8 (Rounds 6+7) — relatório de inspeção ({timestamp})",
        "",
        "- Cobertura: 41/43 regras v8 (Rounds 6+7 mergeados em main; "
        "Regras 25 e 37 deferred — exigem histórico)",
        f"- Comando: `{cmd}`",
        f"- SQLite: `{db}`",
        f"- Notion: {notion_status}",
        "",
        "Gerado por leitura pura — zero escrita em Notion ou SQLite. Idempotente.",
        "",
        "---",
        "",
    ]

    secoes = [
        _md_section_totais(pubs_sqlite, pubs_notion),
        _md_section_distribuicao(pubs_notion),
        _md_section_camada_base(pubs_notion),
        _md_section_monitoramento(pubs_notion),
        _md_section_composicao(pubs_notion),
        _md_section_auditoria_depreciados(pubs_notion),
        _md_section_schema_observado(pubs_notion),
    ]

    relatorio = "\n".join(header) + "\n---\n\n".join(secoes)
    out_path.write_text(relatorio, encoding="utf-8")

    print(f"[smoke inspect] Relatório salvo em: {out_path}")
    if args.verbose:
        print()
        print(relatorio)

    return 0


if __name__ == "__main__":
    sys.exit(main())
