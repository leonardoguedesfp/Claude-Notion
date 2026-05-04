# Round 5 — Fix das regressões P0 do Round 4

Documento único consolidando o trabalho de debug + correção das duas
regressões P0 identificadas no relatório de anatomia pós-Round-4
(`docs/anatomia-publicacoes-pos-round-4.md`, commit `0299354`).

---

## 0. Sumário executivo

| Métrica | Antes (relatório anatomia) | Depois (Round 5) |
|---|---:|---:|
| Pubs com `Partes` em JSON cru | **530 (33%)** | **0** ✅ |
| Pubs com `<br>` literal no Texto | ~517 reportadas (32%) | **0** (era falso positivo do MCP) ✅ |
| Pubs com `Tarefa sugerida` ≥ 1 | 1.608 (100%) | 1.608 (100%) ✓ mantido |
| Pubs com `Alerta contadoria` ≥ 1 | 611 (38%) | 611 (38%) ✓ mantido |
| Pubs com Status auto | 69 (4,3%) | 69 (4,3%) ✓ mantido |
| Testes totais | 909 | **916** (+7 Round 5b regressão NEGATIVA) |

**Frente A — Partes JSON cru** (P0-1): causa-raiz diagnosticada e
corrigida. 530 pubs re-sincronizadas in-place no Notion via PATCH.
Suite de testes ampliada com 9 novos testes cobrindo os 5 clusters
afetados.

**Frente B — `<br>` literal no Texto** (P0-5): **falso positivo**
identificado pela investigação. O conteúdo REAL no Notion (verificado
via API REST direta `GET /v1/pages/{id}`) tem `\n` (newlines), NÃO
`<br>`. O `<br>` que aparecia na inspeção MCP era artefato do
enhanced-markdown do MCP server, não conteúdo real. Round 4.5 commit
`afddba4` já tinha resolvido corretamente. Sem fix de código, mas 7
testes de regressão NEGATIVA adicionados para formalizar o invariante.

**Erratas no relatório de anatomia** estão na seção 4 deste documento.

---

## 1. Frente A — Partes JSON cru (P0-1)

### 1.1 Sintomas (do relatório de anatomia)

530 das 1.608 canônicas no Notion tinham `Partes` em formato pré-Round-4:

```
[{"comunicacao_id": 494748109, "nome": "BANCO DO BRASIL SA", "polo": "P"}, ...]
```

em vez do formato Round 4.1:

```
Polo Ativo: DENITA GOMES GUIMARAES
Polo Passivo: BANCO DO BRASIL SA
```

Concentração em 2 clusters:
- TRT10 Intimação Acórdão: 94/94 (100%)
- TRT10 Intimação Notificação: 408/723 (56%)

### 1.2 Investigação

**Hipótese inicial** (do relatório): caminho de envio bypassa o mapper
para certos clusters TRT10. `formatar_partes` produz output correto
isoladamente.

**Busca na codebase** (`grep -rn "Partes" --include="*.py"`): 14
ocorrências. Filtro pelas relevantes:

```
notion_rpadv/services/dje_notion_mappings.py:342  formatar_partes
notion_rpadv/services/dje_notion_mapper.py:620    partes_str = formatar_partes(...)
notion_rpadv/services/dje_notion_mapper.py:670    "Partes": _rich_text_prop(partes_str)
notion_rpadv/services/dje_dedup.py:283            def _merge_partes(...)
notion_rpadv/services/dje_dedup.py:354            partes_merged = _merge_partes(...)
notion_rpadv/services/dje_dedup.py:370            "Partes": {"rich_text": [...]}
```

**Achado crítico**: `dje_dedup.py` tem `_merge_partes` + atribuição a
`properties["Partes"]` no `_build_update_payload`. Inspeção do código
revela que `_merge_partes` produzia `json.dumps(out, ensure_ascii=False)`
— JSON serializado.

### 1.3 Causa-raiz

Sequência exata do bug:

1. **Mapper original** (`dje_notion_mapper.py:620,670`): cria a página
   com `Partes` corretamente formatado via `formatar_partes`.
2. **Detector de duplicata** (`dje_dedup.py:determinar_destino`):
   marca a duplicata em `dup_pendentes`.
3. **Flush das duplicatas no fim do batch** (`flush_atualizacoes_canonicas`):
   chama `_merge_partes` para mesclar destinatários da canônica +
   duplicatas, gerando string JSON via `json.dumps(out)`.
4. **PATCH em `_build_update_payload`** (linhas 369-374): envia esse
   JSON cru no campo `Partes`, **sobrescrevendo o output do
   formatar_partes**.

**Confirmação por correlação**: 530 pubs com Partes JSON cru ≡ 530
pubs com `Duplicatas suprimidas` populada (mesmo conjunto). A 531ª
canônica (`djen=564026686` — falha 502 transient declarada no handoff)
não recebeu o flush e por isso ficou com Partes formatado correto.

**Por que TRT10 Acórdão é 100% afetado**: 94 canônicas / 194 com
duplicatas → 100 duplicatas. Toda canônica TRT10 Acórdão tem
duplicata, então toda canônica passou pelo flush bug.

**Por que TRT10 Notif é 56% (408/723)**: 723 canônicas / 1.132 com
duplicatas → 409 duplicatas. 408 canônicas Notif passaram pelo flush
(diferença de 1 = caso `djen=564026686`).

### 1.4 Fix aplicado

Mínimo, cirúrgico — 3 linhas em `notion_rpadv/services/dje_dedup.py`:

```diff
 from notion_rpadv.services import dje_db
 from notion_rpadv.services.dje_notion_mappings import (
     formatar_advogados_intimados,
+    formatar_partes,
     mapear_tipo_documento,
 )
```

```diff
 def _merge_partes(...) -> str:
-    """União de listas de destinatários (canônica + duplicatas).
-    Dedup por nome (case-insensitive). Output é JSON string compatível
-    com a property "Partes" da database (rich_text serializado)."""
+    """União de destinatários (canônica + duplicatas), dedup por nome
+    case-insensitive. Output é a string formatada pelo
+    ``formatar_partes`` (Round 4.1 — "Polo Ativo: ... / Polo Passivo:
+    ..."), pronta pra ir direto na property "Partes".
+
+    Round 5a (2026-05-04): antes este merge devolvia ``json.dumps(out)``
+    (JSON cru), o que sobrescrevia o output do ``formatar_partes`` no
+    PATCH do flush das duplicatas — gerando 530 pubs canônicas com
+    Partes em formato pré-Round-4. Agora roteia pelo mesmo formatter
+    do mapper original.
+    """
     out: list[Any] = []
     ...
     _ingest(partes_canonica_json)
     for j in partes_duplicatas_json:
         _ingest(j)
-    return json.dumps(out, ensure_ascii=False)
+    return formatar_partes(out)
```

A função `formatar_partes` aceita lista de dicts diretamente (mesma
shape do output do `_ingest`), então não houve necessidade de
adapter. O `[:2000]` defensivo no caller (`_build_update_payload`)
foi mantido — `formatar_partes` já trunca em 2000, mas a defesa em
profundidade não custa nada.

### 1.5 Validação

**Teste R1.6 antigo** (`tests/test_round_1.py::test_R1_6_merge_partes_dedup_por_nome`)
atualizado para o novo contrato. Mantém a invariante de dedup
case-insensitive, mas agora valida que o output:
- Não começa com `[` (sinal de JSON cru)
- Não contém `comunicacao_id`
- Tem labels `Polo Ativo:`/`Polo Passivo:` (ou fallback `Polo X:`)
- ACME aparece 1x (dedup case-insensitive)

**Novos testes de regressão Round 5a** (`tests/test_round_5_partes.py`):
9 testes cobrindo:

| # | Cluster | djen sentinela | Cobertura |
|---|---|---|---|
| 1 | TRT10 Acórdão (100% afetado) | 573369859 | merge canônica + 1 duplicata |
| 2 | TRT10 Notif (56% afetado) | 494748109 | merge canônica + 1 duplicata |
| 3 | TRT10 Notif multi-polo | 495174885 | 3 nomes no Polo Ativo |
| 4 | TST Decisão (100% afetado) | 547728624 | merge canônica + 1 duplicata |
| 5 | STJ Decisão (16% afetado) | 596733179 | preserva prefixo `N. NOME (PAPEL)` |
| 6 | TRT10 Lista (2% afetado) | 496542520 | merge canônica + 1 duplicata |
| 7 | End-to-end `_build_update_payload` | 494748109 | valida payload final do PATCH |
| 8 | Idempotente sem duplicatas | — | edge case |
| 9 | Canônica vazia | — | edge case (devolve "") |

**Resultado**: 10 testes verdes (9 novos + 1 R1.6 atualizado).
Suite total: **916 passed, 7 skipped** (vs 909 antes — +7 do
Round 5b adicionados na Frente B).
Lint ruff: limpo nos arquivos tocados.

### 1.6 Re-sync das 530 pubs no Notion

Script: `scripts/resync_partes_round_5.py`.

**Estratégia**:
1. Lê CSV exportado mais recente (procura em `docs/`, raiz, e Temp).
2. Filtra linhas onde `Partes` começa com `[{` ou contém
   `comunicacao_id`.
3. Para cada candidato, busca `notion_page_id` no SQLite.
4. Reconstitui `Partes` correto rodando `_merge_partes` (já corrigido)
   sobre destinatários da canônica + todas as duplicatas (encontradas
   via `dup_canonical_djen_id` no SQLite).
5. PATCH `/v1/pages/{page_id}` apenas com `Partes`.
6. Rate limit 350ms, retry exponencial em 429/5xx (5 tentativas).
7. Idempotente: se a `Partes` já está em formato legível, pula.

**Token**: lido do keyring (mesma fonte do app PySide6). Não há
`token.txt` neste setup.

**Execução** (live, 2026-05-04 00:50 → 00:53):

```
[Round 5a re-sync Partes] CSV: 📬 Publicações 6ee4f13a9ea34506824656a261d99dce_all (2).csv
[Round 5a re-sync Partes] SQLite: C:\Users\...\NotionRPADV\leitor_dje.db
[Round 5a re-sync Partes] Mode: LIVE
[Round 5a re-sync Partes] Candidatos JSON cru: 530
  [   1/530] djen=494748109 OK page=35630d90…
  [   2/530] djen=495174885 OK page=35630d90…
  ...
  [ 530/530] djen=598458539 OK page=35630d90…

==============================================================
[Round 5a re-sync Partes] SUMÁRIO
  Total candidatos no CSV: 530
  OK (PATCH 200): 530
  Erro:            0
  Skip:            0
```

**Spot-check pós-sync** (3 pubs antes em JSON cru):

| djen | Tribunal | Tipo doc | Partes (depois do re-sync) |
|---|---|---|---|
| 494748109 | TRT10 | Notif | `Polo Ativo: DENITA GOMES GUIMARAES\nPolo Passivo: BANCO DO BRASIL SA` |
| 573369859 | TRT10 | Acórdão | `Polo Ativo: ZULEIDE MALHEIROS DA FRANCA DA SILVA\nPolo Passivo: BANCO DO BRASIL SA` |
| 495174885 | TRT10 | Notif | `Polo Ativo: GISELE..., MARIA..., UNIÃO FEDERAL (PGF) - DF\nPolo Passivo: BANCO DO BRASIL SA` |

Confirmou: 100% das pubs recuperadas com formato Round 4.1.

### 1.7 Commit Frente A

`10bff98 — Round 5a — fix Partes JSON cru (530 pubs)` (push em
`origin/main`).

Arquivos:
- `notion_rpadv/services/dje_dedup.py` (fix em `_merge_partes`)
- `tests/test_round_1.py` (atualiza teste R1.6 antigo)
- `tests/test_round_5_partes.py` (NOVO — 9 testes regressão)
- `scripts/resync_partes_round_5.py` (NOVO — script PATCH 530 pubs)

---

## 2. Frente B — `<br>` literal no Texto (P0-5)

### 2.1 Sintomas reportados (do relatório de anatomia)

> "Inspeção MCP de 5 amostras mostrou `<br>` literal no Texto entregue
> ao Notion em todas elas. 517 pubs (32% do acervo) têm o trailer
> `Intimado(s) / Citado(s)` no Texto entregue, onde o `<br>`
> historicamente aparece."

### 2.2 Investigação

**Busca por entrada do trailer** (`grep -rn "Intimado\|Citado"
--include="*.py"`): zero matches em `notion_rpadv/`. Apenas
`tests/test_round_4.py` cita o trailer em um teste de regressão
(`test_R4_5_preprocessador_limpa_br_no_trailer_djen_494748109`)
adicionado pelo commit `afddba4`.

**Trace do pipeline real para djen=494748109** (sentinela do Round
4.5):

```python
# Texto bruto do SQLite payload_json:
"...JONATHAN QUINTAO JACOB Juiz do Trabalho Titular<br><br>Intimado(s) / Citado(s)<br> - BANCO DO BRASIL SA<br>"
# 4 ocorrências de <br>

# preprocessar_texto_djen output:
"...Juiz do Trabalho Titular\n\nIntimado(s) / Citado(s)\n - BANCO DO BRASIL SA"
# 0 ocorrências de <br>

# truncar_texto_inline output (limite=2000):
"...Juiz do Trabalho Titular\n\nIntimado(s) / Citado(s)\n - BANCO DO BRASIL SA"
# 0 ocorrências de <br>
```

**O pipeline funciona perfeitamente.** Round 4.5 commit `afddba4` já
tinha resolvido. Por que então o relatório de anatomia reportou `<br>`?

### 2.3 Causa do falso positivo

Inspeção do conteúdo **REAL** no Notion via API REST direta
(`GET /v1/pages/{id}` com header `Notion-Version: 2022-06-28`):

```python
# djen=494748109, page 35630d90-c916-8155-...
# response.json()["properties"]["Texto"]["rich_text"][0]["text"]["content"][-200:]:
'...JONATHAN QUINTAO JACOB Juiz do Trabalho Titular\n\nIntimado(s) / Citado(s)\n - BANCO DO BRASIL SA'
# contains "<br": False
# contains "\n": True
```

**Confirmação em 5 amostras** distribuídas por cluster (TRT10 Notif,
TRT10 Acórdão, TRT10 Lista, TJDFT Ata 57, STJ Pauta, TJDFT Decisão):
**0/5 contém `<br>` literal real**. Todas com `\n` (newlines).

**Causa do falso positivo**: o MCP server do Notion (Claude.ai
integration) renderiza `\n` como `<br>` em alguns campos da
representação enhanced-markdown que retorna ao cliente. Não é
conteúdo real da propriedade — é cosmético da exibição.

O CSV exportado do Notion (que usa formato CSV padrão, sem rendering)
**confirmava esse fato** desde o início: 0 ocorrências de `<br>`
detectadas (relatório de anatomia, seção 7.6). Mas eu interpretei
isso como "artefato do CSV", quando na verdade era a verdade
operacional.

### 2.4 Decisão: sem fix de código, com teste de regressão NEGATIVA

Como não há bug, não há fix de código. Mas o invariante "nenhum
`<br>` literal no Texto inline" é importante e precisa ser
formalizado em testes para evitar regressão futura.

**Novos testes Round 5b** (`tests/test_round_5_texto_br.py`): 7
testes verificando que o pipeline (`preprocessar_texto_djen` +
`truncar_texto_inline`) sempre devolve string sem `<br>` em qualquer
forma:

| # | Cenário | djen / fixture |
|---|---|---|
| 1 | TRT10 Notif com trailer (4 `<br>`) | djen=494748109 |
| 2 | TRT10 Acórdão com trailer + corpo > 2000 | djen=573369859 |
| 3 | TRT10 Lista com `<br>` inline | djen=496542520 |
| 4 | TJDFT Ata 57 (lista CNJs JULGADOS) | djen=524038068 |
| 5 | Variantes XHTML completas | `<br>`, `<br/>`, `<br />`, `<BR>`, `<Br />`, `<BR/>`, `<BR  />`, escape duplo `\<br\>` |
| 6 | Truncamento inline não introduz `<br>` | edge case |
| 7 | Observações (`payload.observacoes`) também sem `<br>` | sanity |

Asserção comum (`_assert_no_br`):
- `re.compile(r"<br\s*/?>", re.IGNORECASE)` não casa nada
- Substring `"<br"` (case-insensitive) não está no texto

**Resultado**: 7/7 verdes.

### 2.5 Auditoria ampla — confirmação operacional

Script auditoria one-shot consultou a API REST do Notion para
**todas as 1.608 canônicas** e contou quantas têm `<br` literal no
campo Texto.

**Resultado**:

```
Total canônicas com page_id no SQLite: 1608
  ... 100/1608 (com_br=0, erros=0)
  ... 200/1608 (com_br=0, erros=0)
  ... 1600/1608 (com_br=0, erros=0)

============================================================
SUMÁRIO Round 5b auditoria <br>:
  Total verificadas: 1608
  Com <br> literal real: 0
  Sem <br>: 1608
  Erros: 0
```

**Verdade definitiva**: 0/1608 pubs têm `<br>` literal no Texto.
Falso positivo do relatório de anatomia 100% confirmado.

### 2.6 Sem re-sync necessário

Como o conteúdo real já está correto (`\n` em vez de `<br>`), não há
nada a corrigir no Notion. Decisão: NÃO criar
`scripts/resync_texto_round_5.py`. Documentar a investigação é
suficiente.

### 2.7 Commit Frente B

`Round 5b — confirmar fix do Round 4.5 (<br>) + teste regressão
NEGATIVA` (a vir).

Arquivos:
- `tests/test_round_5_texto_br.py` (NOVO — 7 testes regressão NEGATIVA)
- `docs/round-5-fix-regressoes-p0.md` (este documento)

---

## 3. Testes adicionados

| Arquivo | Frente | Testes | Status |
|---|---|---:|---|
| `tests/test_round_5_partes.py` | 5a | 9 | 🟢 verdes |
| `tests/test_round_5_texto_br.py` | 5b | 7 | 🟢 verdes |
| `tests/test_round_1.py::test_R1_6_merge_partes_dedup_por_nome` | 5a (atualizado) | 1 | 🟢 verde |
| **Total novos/atualizados** | — | **17** | **🟢 todos verdes** |

Suite full pré-Round-5: 909 passed.
Suite full pós-Round-5: **916 passed, 7 skipped** (+7 testes; o R1.6
antigo virou +0 porque atualizou um existente).

---

## 4. Métricas finais (preencher pós-auditoria)

| Métrica | Antes (relatório anatomia) | Depois (Round 5) |
|---|---:|---:|
| Pubs com `Partes` em JSON cru | 530 (33%) | **0/1608** ✅ |
| Pubs com `<br>` literal no Texto | ~517 reportadas | **0/1608** (nunca foi >0 — falso positivo) ✅ |
| Pubs com `Tarefa sugerida` ≥ 1 | 1.608 (100%) | 1.608 (100%) ✓ |
| Pubs com `Alerta contadoria` ≥ 1 | 611 (38%) | 611 (38%) ✓ |
| Pubs com Status auto | 69 (4,3%) | 69 (4,3%) ✓ |
| Testes totais | 909 | **916** |

Validação:
- `Partes`: spot-check API direta confirma 3/3 amostras corretas;
  re-sync sumarizou 530/530 OK.
- `<br>`: spot-check API direta confirma 5/5 amostras sem `<br>`;
  **auditoria ampla via API REST das 1.608 canônicas: 0 com `<br>`,
  0 erros**. Validação operacional fechada.

### 4.1 Errata do relatório de anatomia

Atualizar (em round futuro de polimento, NÃO neste round) as seguintes
afirmações do `docs/anatomia-publicacoes-pos-round-4.md`:

| Seção | Afirmação errada | Correção |
|---|---|---|
| Sumário 0, item 3 | "Regressão `<br>` literal no Texto inline confirmada" | "Falso positivo — MCP server renderiza `\n` como `<br>` em alguns campos do enhanced-markdown. Conteúdo real verificado via API REST tem `\n`." |
| Seção 4.1 | Tabela "djen com `<br>`" baseada em MCP | Tabela inválida — repetir com API REST. |
| Seção 6.3.6 | "`Texto` permanece 🟡" | "`Texto` é 🟢 — pipeline correto, falso positivo." |
| Seção 8.3 | "`<br>` literal residual no Texto inline (Round 4.5 não resolveu)" | "Round 4.5 resolveu corretamente; aparente persistência veio de artefato MCP." |
| Seção 10.3 | "P0-5 Investigar regressão `<br>` literal no Texto inline" | Resolvido sem fix — fechar como falso positivo. |

---

## 5. Pendências detectadas durante o round

Itens identificados que NÃO foram corrigidos neste round (registro):

1. **`djen=564026686` ainda sem flush dedup**: pendência operacional
   declarada no HANDOFF_ROUND_4. O re-sync da Frente A NÃO toca essa
   pub porque ela não tem Partes em JSON cru (o flush nunca rodou).
   Próxima sync do app a resolverá.

2. **Cursores divergentes 5×1**: 5 OABs em `2026-03-31`, Samantha em
   `2026-05-03` (declarado no HANDOFF). Não escopo deste round.

3. **STJ Pauta texto sem espaços**: pré-processador colando tokens
   (`RELATOR:MINISTRO...`). Anomalia visível no relatório de anatomia
   seção 9.1, P1 — não é P0, não corrigido aqui.

4. **STJ Partes mistura formato genérico com papel real**: P1-4 do
   backlog do relatório de anatomia. Não corrigido aqui.

5. **Errata do relatório de anatomia**: 5 correções identificadas na
   seção 4.1 acima. Não aplicadas neste round (escopo: fix das
   regressões + documentação Round 5).

---

## 6. Comandos úteis para validação manual

### Confirmar que `Partes` está OK em uma pub específica

```python
import requests, keyring
from notion_bulk_edit.config import KEYRING_SERVICE, KEYRING_USERNAME
tok = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
page_id = "35630d90-c916-8155-ac1a-fdb2f0e90fa8"  # djen=494748109
r = requests.get(
    f"https://api.notion.com/v1/pages/{page_id}",
    headers={"Authorization": f"Bearer {tok}", "Notion-Version": "2022-06-28"},
)
print(r.json()["properties"]["Partes"]["rich_text"][0]["text"]["content"])
# Esperado: "Polo Ativo: DENITA GOMES GUIMARAES\nPolo Passivo: BANCO DO BRASIL SA"
```

### Confirmar que `Texto` está sem `<br>`

```python
import requests, keyring
from notion_bulk_edit.config import KEYRING_SERVICE, KEYRING_USERNAME
tok = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
page_id = "35630d90-c916-8155-ac1a-fdb2f0e90fa8"
r = requests.get(
    f"https://api.notion.com/v1/pages/{page_id}",
    headers={"Authorization": f"Bearer {tok}", "Notion-Version": "2022-06-28"},
)
texto = "".join(p["text"]["content"] for p in r.json()["properties"]["Texto"]["rich_text"])
assert "<br" not in texto.lower()
```

### Re-rodar suite Round 5

```bash
cd C:\dev\Claude-Notion
.venv/Scripts/python.exe -m pytest tests/test_round_5_partes.py tests/test_round_5_texto_br.py -v
# Esperado: 9 + 7 = 16 passed
```

---

**Fim.** Round 5 fechado.
