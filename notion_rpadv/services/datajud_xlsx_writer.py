"""Geração da planilha xlsx de enriquecimento DataJUD (Componente 3).

Saída compatível com a aba **Importar** do app: coluna A é ``page_id``
(chave do ``update_page`` no Notion) + colunas de propriedades
enriquecidas com cabeçalho == ``notion_name`` exato (igual ao formato
do template do ``notion_bulk_edit.gerar_template``).

Estrutura do arquivo:
    datajud_consulta_<YYYY-MM-DD-HHMM>.xlsx
    ├── DataJUD          (visível, importável)
    ├── Instruções       (visível, texto)
    └── _vocabularios    (oculta, dropdowns)

Aba DataJUD — ordem de colunas:
    A. page_id
    B. Diagnóstico
    C..XX. Para cada uma das 14 propriedades enriquecidas:
        - <NotionName>             (importável, com coloração)
        - <NotionName> ▸ atual     (auditoria)
        - <NotionName> ▸ status    (auditoria, label canônico)
    XX..YY. Para cada uma das ~24 propriedades fora-do-escopo do enricher:
        - <NotionName> ▸ atual     (auditoria, COLUNA OCULTA)
    YY+1. __datajud_meta (auditoria)

Coloração — só na coluna ``<NotionName>`` importável:
    - Verde claro (D4E7D4): vazio_sugerido + alta confiança.
    - Amarelo (FFF2CC):     divergente (qualquer confiança) OU
                            vazio_sugerido + baixa confiança.
    - Sem fill:             igual / nao_coberto / datajud_vazio
                            (célula LITERALMENTE NÃO ESCRITA).

INVARIANTE CRÍTICA: nunca chamar ``ws.cell(row, col, "")``. Para campos
sem valor, **não toca a célula**. A aba Importar interpreta célula
``None`` como "preserva valor existente"; uma célula com string vazia
explícita seria interpretada como "limpa o campo no Notion" pelo
``encoders.encode_value`` (especialmente perigoso para checkboxes).
Teste dedicado inspeciona o XML interno do xlsx para garantir.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from notion_rpadv.services.datajud_enricher import (
    REGRAS_ORIGEM,
    ResultadoEnriquecimento,
)

logger = logging.getLogger("datajud.writer")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SHEET_NAME_DATAJUD: Final[str]      = "DataJUD"
SHEET_NAME_INSTRUCOES: Final[str]   = "Instruções"
SHEET_NAME_VOCABULARIOS: Final[str] = "_vocabularios"

HEADER_FILL_HIGH_HEX: Final[str] = "1F4E79"  # azul (alta confiança)
HEADER_FILL_LOW_HEX: Final[str]  = "BF8F00"  # amarelo escuro (baixa)

CELL_FILL_VAZIO_SUGERIDO_ALTA_HEX: Final[str] = "D4E7D4"  # verde claro
CELL_FILL_DIVERGENTE_OU_BAIXA_HEX: Final[str] = "FFF2CC"  # amarelo

# Status labels canônicos (vão para a coluna ▸ status). Ver
# `STATUS_DIVERGENCIA` no spec do Componente 3.
STATUS_DIVERGENCIA: Final[dict[str, str]] = {
    "igual":          "✅ igual",
    "divergente":     "🔄 divergente",
    "vazio_sugerido": "⬆️ Notion vazio, DataJud sugere",
    "datajud_vazio":  "⬇️ DataJud vazio, Notion preenchido",
    "nao_coberto":    "⚪ não coberto",
}

# Selects fechados que ganham DataValidation na coluna importável.
# Apenas estes 4 entre as 14 enriquecidas têm vocabulário fechado no
# Notion: Tribunal, Instância, Status, Fase.
SELECTS_FECHADOS_VALIDADOS: Final[frozenset[str]] = frozenset({
    "Tribunal", "Instância", "Status", "Fase",
})

# Confiança no header — apenas estes 2 ficam amarelos.
RELATORES_BAIXA_CONFIANCA: Final[frozenset[str]] = frozenset({
    "Relator no 2º grau",
    "Relator no STJ/TST",
})

# Larguras
COL_WIDTH_PAGE_ID: Final[int] = 38
COL_WIDTH_DIAG: Final[int]    = 22
COL_WIDTH_DEFAULT: Final[int] = 22
COL_WIDTH_META: Final[int]    = 30


# ---------------------------------------------------------------------------
# Texto da aba Instruções
# ---------------------------------------------------------------------------

INSTRUCOES_TEXT: Final[str] = """\
PLANILHA DE ENRIQUECIMENTO DATAJUD — Ricardo Passos Advocacia

Esta planilha foi gerada a partir de consultas à API pública DataJud do CNJ.
Cada linha corresponde a um processo da base ⚖️ Processos.

CORES NOS CABEÇALHOS DAS COLUNAS IMPORTÁVEIS:
  Azul (1F4E79):    Enriquecimento de alta confiança.
  Amarelo escuro:   Enriquecimento de BAIXA confiança — revisar manualmente.
                    São os campos "Relator no 2º grau" e "Relator no STJ/TST".

CORES NAS CÉLULAS DE VALOR SUGERIDO:
  Verde claro:      Notion estava vazio, DataJud trouxe sugestão (alta confiança).
  Amarelo:          DataJud diverge do valor atual no Notion, OU sugestão de baixa confiança.
  Sem cor:          Valor igual ao Notion, ou DataJud não cobriu o campo.

COMO USAR:
  1. Abra a planilha. Filtre a coluna "Diagnóstico" para ver apenas linhas com "OK" ou "Dados parciais".
  2. Para cada propriedade que você quer atualizar no Notion, mantenha a coluna "<NotionName>".
     Para descartar uma sugestão, apague a célula (Delete) — não escreva nada nela.
  3. Para descartar uma propriedade inteira, apague a coluna "<NotionName>".
     As colunas "▸ atual" e "▸ status" não são lidas pela aba Importar.
  4. Salve o arquivo.
  5. Abra a aba "Importar planilha" do app, base "Processos", e selecione o arquivo.
  6. Revise o preview. Confirme.

DIAGNÓSTICOS POSSÍVEIS:
  OK:                       Processo encontrado e enriquecido normalmente.
  Não encontrado:           DataJud não tem registro do CNJ informado.
  STF não coberto:          Processos do STF não estão na API pública DataJud.
  Tribunal não suportado:   Tribunal cadastrado como "Outro" ou não mapeado.
  Dados parciais:           Encontrado em alguns endpoints, mas não em todos os esperados.
  Erro: <detalhe>:          Falha técnica na consulta. Tentar de novo depois.

ATENÇÃO:
  - Nunca escreva "" em uma célula. Se quer descartar, use Delete.
  - Não preencha as colunas "▸ atual" ou "▸ status" — elas são apenas para inspeção.
  - As colunas ocultas no final da planilha são para auditoria; não desocultar para edição.

LIMITAÇÃO TEMA 955: O DataJud só consegue detectar sobrestamento por Tema 955
quando o movimento original (códigos TPU 11025/12066/14978/14981 com
complemento "Tema 955") está presente nos dados retornados pela API. Para
processos sobrestados antes da plena adoção do DataJud (~2018-2020), esse
movimento pode estar ausente, e o enricher sugerirá "Arquivado" em vez de
"Arquivado provisoriamente (tema 955)". Tratar como divergência esperada,
não erro do enricher.

GRAU SEGUE CADASTRO NOTION: O enricher reporta o estado processual no grau
cadastrado no Notion (campo Instância). Se a Instância estiver desatualizada
(ex.: processo subiu para o TST mas Notion ainda diz "2º grau"), o DataJud
vai relatar G2 e não detectar a subida. Conferir Instância no Notion antes
de rodar enriquecimento em massa.

Gerada em: {gerada_em}
Fontes: API pública DataJud (api-publica.datajud.cnj.jus.br) + cache local Notion.
"""


# ---------------------------------------------------------------------------
# Helpers de divergência
# ---------------------------------------------------------------------------


def _eh_vazio(valor: Any) -> bool:
    """Considera None e string vazia/whitespace como vazio."""
    if valor is None:
        return True
    if isinstance(valor, str) and not valor.strip():
        return True
    if isinstance(valor, list) and not valor:
        return True
    return False


def _format_value(v: Any) -> Any:
    """Formata valor pra escrever em célula. Listas viram CSV."""
    if v is None:
        return None
    if isinstance(v, list):
        return ", ".join(str(x) for x in v if x is not None and str(x) != "")
    return str(v) if not isinstance(v, (int, float, bool)) else v


def status_divergencia(
    notion_value: Any,
    datajud_value: Any,
    *,
    enriquecida: bool,
) -> str:
    """Decide o label canônico de divergência para a coluna ▸ status.

    - ``enriquecida=False`` → ``"nao_coberto"`` (auxiliares fora-do-escopo).
    - Notion vazio + DataJud preenchido → ``"vazio_sugerido"``.
    - Notion preenchido + DataJud vazio → ``"datajud_vazio"``.
    - Ambos vazios → ``"datajud_vazio"`` (mais conservador; sem fill;
      mostra sinal de "DataJud não trouxe", que é a leitura correta).
    - Ambos preenchidos e iguais (após strip) → ``"igual"``.
    - Ambos preenchidos e diferentes → ``"divergente"``.
    """
    if not enriquecida:
        return "nao_coberto"
    notion_vazio = _eh_vazio(notion_value)
    datajud_vazio = _eh_vazio(datajud_value)
    if notion_vazio and not datajud_vazio:
        return "vazio_sugerido"
    if datajud_vazio:
        return "datajud_vazio"
    # Ambos preenchidos
    if str(notion_value).strip() == str(datajud_value).strip():
        return "igual"
    return "divergente"


def _decide_fill(
    status: str,
    confianca: str,
) -> PatternFill | None:
    """Coloração da célula ``<NotionName>`` (importável)."""
    if status == "vazio_sugerido":
        if confianca == "alta":
            return PatternFill("solid", fgColor=CELL_FILL_VAZIO_SUGERIDO_ALTA_HEX)
        return PatternFill("solid", fgColor=CELL_FILL_DIVERGENTE_OU_BAIXA_HEX)
    if status == "divergente":
        return PatternFill("solid", fgColor=CELL_FILL_DIVERGENTE_OU_BAIXA_HEX)
    return None  # igual / nao_coberto / datajud_vazio


# ---------------------------------------------------------------------------
# Helpers de meta
# ---------------------------------------------------------------------------


def _hash_payload(movs_brutos_por_grau: dict[str, list[dict[str, Any]]]) -> str:
    """SHA-256 dos primeiros 1024 chars do dump JSON de movimentos brutos.

    Truncamos para limitar custo. Usa a versão truncada como digest
    estável entre runs com o mesmo conteúdo.
    """
    serialized = json.dumps(
        movs_brutos_por_grau, sort_keys=True, ensure_ascii=False, default=str,
    )
    return hashlib.sha256(serialized[:1024].encode("utf-8")).hexdigest()[:16]


def _build_meta_json(
    resultado: ResultadoEnriquecimento,
    ts_consulta_iso: str,
) -> str:
    """JSON inline para a coluna __datajud_meta."""
    meta = {
        "ts_consulta":     ts_consulta_iso,
        "fontes_tribunal": resultado.fontes_tribunal,
        "hash_payload":    _hash_payload(resultado.movimentos_brutos_por_grau),
    }
    return json.dumps(meta, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Construção da aba DataJUD
# ---------------------------------------------------------------------------


def _make_header_cell(
    ws: Worksheet, row: int, col: int, text: str, *, baixa_confianca: bool = False,
) -> None:
    cell = ws.cell(row=row, column=col, value=text)
    fill_hex = HEADER_FILL_LOW_HEX if baixa_confianca else HEADER_FILL_HIGH_HEX
    cell.fill = PatternFill("solid", fgColor=fill_hex)
    cell.font = Font(color="FFFFFF", bold=True, size=11)
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)


def _resolve_property_specs(
    schema: dict[str, Any],
) -> tuple[dict[str, str], list[tuple[str, str, Any]]]:
    """Indexa o schema da base Processos.

    Retorna:
        - ``nn_to_chave``: dict ``notion_name → chave_python``.
        - ``auxiliares``: lista ``[(notion_name, chave_python, spec), ...]``
          de propriedades NÃO enriquecidas pelo DataJud, na ordem do
          schema (= ordem natural da base no Notion).
    """
    nomes_enriquecidos = {r.nome_notion for r in REGRAS_ORIGEM}
    nn_to_chave: dict[str, str] = {}
    auxiliares: list[tuple[str, str, Any]] = []
    for chave, spec in schema.items():
        nn = getattr(spec, "notion_name", None)
        if not nn:
            continue
        nn_to_chave[nn] = chave
        if nn not in nomes_enriquecidos:
            auxiliares.append((nn, chave, spec))
    return nn_to_chave, auxiliares


def _build_vocabularios_sheet(
    wb: Workbook,
    schema: dict[str, Any],
) -> dict[str, str]:
    """Aba oculta com 1 coluna por select fechado validado.

    Retorna ``dict notion_name → letra_da_coluna_no_vocabularios`` para
    o caller construir as fórmulas de DataValidation.
    """
    ws = wb.create_sheet(title=SHEET_NAME_VOCABULARIOS)
    ws.sheet_state = "hidden"

    col_map: dict[str, str] = {}
    col_idx = 1
    for chave, spec in schema.items():
        nn = getattr(spec, "notion_name", None)
        if nn not in SELECTS_FECHADOS_VALIDADOS:
            continue
        opcoes = list(getattr(spec, "opcoes", ()) or ())
        if not opcoes:
            continue
        letra = get_column_letter(col_idx)
        col_map[nn] = letra
        ws.cell(row=1, column=col_idx, value=nn)
        for r_idx, opt in enumerate(opcoes, start=2):
            ws.cell(row=r_idx, column=col_idx, value=opt)
        col_idx += 1
    return col_map


def _add_data_validations(
    ws: Worksheet,
    schema: dict[str, Any],
    col_map_voc: dict[str, str],
    col_letter_for_nn: dict[str, str],
    last_row: int,
) -> None:
    """Adiciona DataValidation às colunas importáveis dos selects fechados."""
    for chave, spec in schema.items():
        nn = getattr(spec, "notion_name", None)
        if nn not in SELECTS_FECHADOS_VALIDADOS:
            continue
        if nn not in col_map_voc:
            continue
        opcoes = list(getattr(spec, "opcoes", ()) or ())
        if not opcoes:
            continue
        voc_letra = col_map_voc[nn]
        n_opcoes = len(opcoes)
        formula = (
            f"={SHEET_NAME_VOCABULARIOS}!${voc_letra}$2:${voc_letra}${n_opcoes + 1}"
        )
        col_letra_imp = col_letter_for_nn.get(nn)
        if col_letra_imp is None:
            continue
        dv = DataValidation(
            type="list",
            formula1=formula,
            allow_blank=True,
            showDropDown=False,
            showErrorMessage=True,
            errorTitle="Valor inválido",
            error=f"Selecione uma opção válida para '{nn}'.",
        )
        dv.sqref = f"{col_letra_imp}2:{col_letra_imp}{max(last_row, 2)}"
        ws.add_data_validation(dv)


def _build_instrucoes_sheet(wb: Workbook, ts_iso: str) -> None:
    ws = wb.create_sheet(title=SHEET_NAME_INSTRUCOES)
    ws.column_dimensions["A"].width = 100
    text = INSTRUCOES_TEXT.format(gerada_em=ts_iso)
    for r_idx, linha in enumerate(text.splitlines(), start=1):
        cell = ws.cell(row=r_idx, column=1, value=linha)
        if linha and not linha.startswith(" "):
            # Linhas título (começam na col 0) ficam bold
            cell.font = Font(bold=True)


# ---------------------------------------------------------------------------
# Função pública principal
# ---------------------------------------------------------------------------


def gerar_xlsx(
    resultados: list[ResultadoEnriquecimento],
    processos_cache: dict[str, dict[str, Any]],
    schema: dict[str, Any],
    output_path: Path,
    *,
    ts_consulta: datetime | None = None,
) -> None:
    """Escreve a planilha completa em ``output_path``.

    Args:
        resultados: lista de ``ResultadoEnriquecimento`` (com ``page_id``
            populado). Cada um vira uma linha na aba DataJUD.
        processos_cache: dict ``page_id → registro do cache``. Os
            registros são dicts com chaves do schema (``prop_key``).
            Caller tipicamente passa subset de ``cache_db.records``
            indexado por ``page_id``.
        schema: schema da base Processos do Notion. Formato esperado:
            ``dict[chave_python, PropSpec]`` (PropSpec do
            ``notion_bulk_edit.schemas``). Ordem importa (ordem natural
            da base no Notion ↔ ordem das colunas auxiliares ocultas).
        output_path: caminho absoluto de saída. Diretório-pai criado
            se não existir.
        ts_consulta: timestamp UTC do momento da consulta (padrão:
            ``datetime.now(timezone.utc)``). Vai pra ``__datajud_meta``
            e pro rodapé da aba Instruções.

    Returns:
        None. Arquivo gravado em ``output_path``.

    Note:
        Uso real com schema da base ⚖️ Processos (37 propriedades):
        14 enriquecidas + **23 auxiliares ▸ atual ocultas**. O writer
        é genérico — itera todas as propriedades fora da lista de
        ``REGRAS_ORIGEM`` e adiciona uma coluna oculta para cada,
        independente do tipo (rich_text, multi_select, relation,
        checkbox, last_edited_time, etc.). Não há corte deliberado
        de propriedades; o que define a quantidade é o schema passado.

        Categorização das 23 auxiliares no schema atual:
            - 5 relations: Clientes, Tarefas, Desdobramentos,
              Processo pai, Documentos.
            - 4 selects: Natureza, Tipo de processo, Posição do cliente,
              Tipo de ação (multi-select).
            - 4 checkboxes: Tema 955 — Sobrestado, Sobrestado - IRR 20,
              Sobrestado - TJ conexa, e (espaço pra novos).
            - 3 datas/timestamps: Data trânsito (executiva),
              Atualizado em (last_edited_time), Criado em (created_time).
            - 4 textos: Detalhamento da ação, Observações,
              Turma no STF, Relator no STF.
            - 2 numerações: ID Legal One, Número STF.
            - 1 url: Link externo.

        Todas vão pra coluna ▸ atual ocultada. O operador pode desocultar
        (não recomendado — a aba Importar não consome essas colunas).
    """
    ts = ts_consulta or datetime.now(timezone.utc)
    ts_iso = ts.replace(microsecond=0).isoformat()

    wb = Workbook()
    ws_default = wb.active
    if ws_default is not None:
        wb.remove(ws_default)

    nn_to_chave, auxiliares = _resolve_property_specs(schema)

    # Ordem das 14 enriquecidas vem fixa de REGRAS_ORIGEM.
    enriquecidas: list[tuple[str, str]] = []  # [(notion_name, confianca), ...]
    for regra in REGRAS_ORIGEM:
        enriquecidas.append((regra.nome_notion, regra.confianca))

    # ---- Aba DataJUD ----
    ws = wb.create_sheet(title=SHEET_NAME_DATAJUD)

    # Mapa notion_name → letra da coluna importável (pra DataValidation depois)
    col_letter_for_nn: dict[str, str] = {}

    # Header (linha 1)
    col = 1
    _make_header_cell(ws, 1, col, "page_id")
    ws.column_dimensions[get_column_letter(col)].width = COL_WIDTH_PAGE_ID
    col_page_id = col
    col += 1

    _make_header_cell(ws, 1, col, "Diagnóstico")
    ws.column_dimensions[get_column_letter(col)].width = COL_WIDTH_DIAG
    col += 1

    # 14 enriquecidas × 3 colunas
    for nn, confianca in enriquecidas:
        baixa_conf = nn in RELATORES_BAIXA_CONFIANCA
        # Coluna importável
        col_letter_for_nn[nn] = get_column_letter(col)
        _make_header_cell(ws, 1, col, nn, baixa_confianca=baixa_conf)
        ws.column_dimensions[get_column_letter(col)].width = COL_WIDTH_DEFAULT
        col += 1
        # Coluna ▸ atual
        _make_header_cell(ws, 1, col, f"{nn} ▸ atual")
        ws.column_dimensions[get_column_letter(col)].width = COL_WIDTH_DEFAULT
        col += 1
        # Coluna ▸ status
        _make_header_cell(ws, 1, col, f"{nn} ▸ status")
        ws.column_dimensions[get_column_letter(col)].width = COL_WIDTH_DEFAULT
        col += 1

    # Auxiliares (▸ atual ocultas)
    aux_cols_inicio = col
    for nn, _chave, _spec in auxiliares:
        _make_header_cell(ws, 1, col, f"{nn} ▸ atual")
        letra = get_column_letter(col)
        ws.column_dimensions[letra].width = COL_WIDTH_DEFAULT
        ws.column_dimensions[letra].hidden = True
        col += 1
    aux_cols_fim = col - 1

    # __datajud_meta (visível, última coluna)
    _make_header_cell(ws, 1, col, "__datajud_meta")
    ws.column_dimensions[get_column_letter(col)].width = COL_WIDTH_META
    col_meta = col

    # ---- Linhas de dados ----
    for i, resultado in enumerate(resultados, start=2):
        page_id = resultado.page_id
        proc_record = processos_cache.get(page_id, {})

        # Col 1: page_id (sempre escreve se não vazio)
        if page_id:
            ws.cell(row=i, column=col_page_id, value=page_id)

        # Col 2: Diagnóstico (sempre escreve se não vazio)
        if resultado.diagnostico:
            ws.cell(row=i, column=2, value=resultado.diagnostico)

        # 14 enriquecidas
        c = 3
        for nn, confianca in enriquecidas:
            valor_datajud = resultado.propriedades_sugeridas.get(nn)
            chave_schema = nn_to_chave.get(nn)
            valor_notion = (
                proc_record.get(chave_schema) if chave_schema else None
            )
            status = status_divergencia(
                valor_notion, valor_datajud, enriquecida=True,
            )

            # Coluna importável <NotionName>:
            # INVARIANTE: só escreve se valor_datajud for não-vazio.
            # Não toca a célula caso contrário.
            if not _eh_vazio(valor_datajud):
                # Não escreve se é igual ao Notion (evita poluir com
                # sugestões redundantes que não geram update no
                # Notion). Status "igual" → célula intacta.
                if status != "igual":
                    cell = ws.cell(
                        row=i, column=c, value=_format_value(valor_datajud),
                    )
                    fill = _decide_fill(status, confianca)
                    if fill is not None:
                        cell.fill = fill
            c += 1

            # Coluna ▸ atual: só escreve se valor_notion for não-vazio.
            if not _eh_vazio(valor_notion):
                ws.cell(row=i, column=c, value=_format_value(valor_notion))
            c += 1

            # Coluna ▸ status: SEMPRE escreve label canônico.
            ws.cell(row=i, column=c, value=STATUS_DIVERGENCIA[status])
            c += 1

        # Auxiliares (▸ atual ocultas) — só escreve se não-vazio.
        for nn, chave, _spec in auxiliares:
            valor = proc_record.get(chave)
            if not _eh_vazio(valor):
                ws.cell(row=i, column=c, value=_format_value(valor))
            c += 1

        # __datajud_meta — sempre escreve (carga de auditoria).
        ws.cell(row=i, column=col_meta, value=_build_meta_json(resultado, ts_iso))

    last_row = max(len(resultados) + 1, 2)

    # Freeze panes (page_id + Diagnóstico + linha cabeçalho) e auto_filter.
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 28

    # ---- Aba _vocabularios (oculta) + DataValidation ----
    col_map_voc = _build_vocabularios_sheet(wb, schema)
    _add_data_validations(ws, schema, col_map_voc, col_letter_for_nn, last_row)

    # ---- Aba Instruções ----
    _build_instrucoes_sheet(wb, ts_iso)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))
    logger.info(
        "DataJUD: planilha gerada em %s (%d linhas, %d aux ocultas)",
        output_path, len(resultados), aux_cols_fim - aux_cols_inicio + 1,
    )
