# Handoff — Leitor DJE Fase 5 (2026-05-03)

Documento de contexto pra continuar o trabalho em outra sessão. Todo
o conteúdo abaixo é estado verdadeiro e validado em smoke real após
o merge da Fase 5.

---

## TL;DR

**Fases 4 e 5 mergeadas na main em sequência:**
- **Fase 4** (PR #15, commit `0c535c5`) — eixo CNJ minimalista, reordenação
  de colunas no Excel, reativação dos 4 advogados desativados,
  CalendarDateEdit, refinamentos UI/UX.
- **Fase 5** (PR #16, commit `0eb8362`) — integração com Notion: app
  popula automaticamente a database 📬 Publicações após cada captura
  DJEN. SQLite ganhou 3 colunas pra rastreio de envio (page_id, attempts,
  last_error). Modal one-shot na 1ª execução pergunta o que fazer com
  publicações já no banco.

**728 passed, 7 skipped, 0 failing.** Suite roda em ~10s. Lint verde
nos arquivos modificados.

---

## Estado atual do projeto

| | |
|---|---|
| Branch atual | `main` |
| Último commit em main | `365edc6 Merge pull request #16 from leonardoguedesfp/feat/leitor-dje-notion-sync` |
| Suite de testes | 728 passed, 7 skipped, 0 failing (~10s) |
| Lint (ruff) | verde nos arquivos das Fases 4-5; 17 erros pré-existentes (mesmos do handoff anterior) em outros arquivos |
| Working tree | 1 modificação não commitada (`.gitignore` — exceção pra `Auditoria_Kurier_*.xlsx`) + alguns untracked não-relacionados |

Histórico recente (`git log --oneline -10`):
```
365edc6 Merge pull request #16 from leonardoguedesfp/feat/leitor-dje-notion-sync
0eb8362 feat(dje): Fase 5 — integração Notion (database 📬 Publicações)
3dfbb42 Merge pull request #15 from leonardoguedesfp/feat/leitor-dje-fase-4
0c535c5 feat(dje): Fase 4 — eixo CNJ + reativação de advogados + UI/UX refinada
bc4ef00 Merge pull request #14 from leonardoguedesfp/feat/leitor-dje-fase-3
fb5bfc7 feat(dje): Fase 3 — cache SQLite + watermark por advogado + UX refinada
```

---

## Histórico das fases (linha do tempo)

| Fase | Data | Escopo principal |
|---|---|---|
| 1 | abr/2026 | Cliente HTTP DJEN, paginação, retry, anotação por advogado, Excel xlsx |
| 2 | abr/2026 | Schema canônico, dedup, observacoes A+B, strip HTML, sanitize Unicode |
| 2.1 | 01/05/2026 | Lista 12→6 advogados, IllegalCharacterError fix, defesa per-row no exporter |
| 2.2 | 02/05/2026 | Split mensal de janelas, retry diferido, cancel button, Regra B fix |
| 3 | 02/05/2026 | SQLite cache, watermark POR ADVOGADO, modo padrão/personalizado, abas Status/Log no Excel, lista 6→2 advogados |
| 4 | 02-03/05/2026 | Reativação 4 advogados (volta a 6), eixo CNJ minimalista (1 botão, janela fixa 15d), CalendarDateEdit, Excel 20 cols (9+11), UI/UX (container Execução, progress dinâmica, alinhamentos), hotfix modal "Arquivo não encontrado" |
| 5 | 03/05/2026 | Integração Notion: 3 cols em `publicacoes`, modal one-shot primeira carga, sync com rate-limit + retry, mapper de 18 propriedades, hook no worker, botão "Tentar reenviar falhas" |

---

## Decisões arquiteturais importantes (acumuladas)

### 1. Watermark POR ADVOGADO (Fase 3)

Tabela `djen_advogado_state` com 1 linha por OAB oficial:
```sql
CREATE TABLE djen_advogado_state (
    numero_oab TEXT NOT NULL,
    uf_oab TEXT NOT NULL,
    ultimo_cursor TEXT,
    last_run TEXT,
    PRIMARY KEY (numero_oab, uf_oab)
);
```

Cada advogado tem cursor próprio. Janela individual = `[cursor + 1d, hoje]`.
Cursor vazio (`NULL`) → `DEFAULT_CURSOR_VAZIO = 2025-12-31` → janela
natural `[01/01/2026, hoje]`.

### 2. Cursor conservador (Fase 3, pós-smoke real)

Retry diferido (Fase 2.2) **NÃO destranca o cursor**. Snapshot pré-retry
`failed_per_adv_main` é capturado em `dje_client.fetch_all` antes do
retry; `data_max_safe` calculado a partir desse snapshot. Items
recuperados pelo retry vão pro banco mas cursor só avança quando a
varredura PRINCIPAL completou sem falha.

### 3. Modo personalizado é transient (Fase 3)

NÃO insere em `publicacoes`, NÃO regenera histórico, NÃO atualiza
cursor. Linha de OAB externa tem 2 campos (OAB + UF); nome resolvido
via `destinatarioadvogados` pela API DJEN.

### 4. Eixo CNJ minimalista (Fase 4)

- 1 botão único: "Publicações novas por número CNJ"
- Janela FIXA `[hoje - 15d, hoje]` (constante `CNJ_WINDOW_DAYS = 15`)
- Lista de CNJs vem do cache local da base "Processos" do Notion
  (`cache_db.get_all_records(cache_conn, "Processos")`)
- Grava no banco com dedup global (`INSERT OR IGNORE` por `djen_id`)
- Regenera `Historico_DJEN_completo.xlsx`
- **NÃO atualiza cursor** — eixo CNJ é complementar, não pode marcar
  como "captado" para o eixo OAB algo que verificou só pra alguns CNJs

`compute_oldest_cursor_window` foi removida (era usada antes do
spec mudar pra janela fixa).

### 5. Excel: 20 colunas (Fase 4)

- 9 visíveis: `datadisponibilizacao, siglaTribunal, numeroprocessocommascara,
  nomeOrgao, tipoComunicacao, tipoDocumento, nomeClasse, texto, link`
- 11 ocultas (via `column_dimensions[letter].hidden = True`):
  `advogados_consultados_escritorio, observacoes, id, hash, numero_processo,
  idOrgao, codigoClasse, numeroComunicacao, destinatarios,
  destinatarioadvogados, oabs_externas_consultadas`
- Eliminada `data_disponibilizacao` (com underscore — duplicata da
  `datadisponibilizacao` BR). Versão ISO ainda existe em `publicacoes`
  no SQLite e em `sort_rows`, só não vai no Excel.
- Constante `HIDDEN_COLUMNS` em `dje_transform.py` é o contrato.

### 6. CalendarDateEdit (Fase 4)

`notion_rpadv/widgets/calendar_date_edit.py`. Subclass de `QDateEdit`
com `setCalendarPopup(False)` e `QCalendarWidget` próprio (popup custom)
porque a tentativa anterior de simular Alt+Down via `keyPressEvent`
decrementava o ano em vez de abrir popup. Substitui `QDateEdit` em
todos os datepickers do app + delegate de tabela.

### 7. Container "Execução em andamento" (Fase 4 — A7)

`_exec_container` (QFrame) agrupa heading + botão Cancelar + progress
bar + log. Visível durante varredura; heading vira "Última execução"
em `_on_thread_done` e botão Cancelar some.

Progress bar com cor `app_success` (verde RPADV `#3F6E55`) sobre fundo
claro pra contraste reforçado. Label dinâmica: `%v / %m advogados`
no eixo OAB, `%v / %m processos` no CNJ.

### 8. Hotfix modal "Arquivo não encontrado" (Fase 4 — pós-smoke)

Botões "Abrir arquivo / pasta / histórico" agora **escondem
silenciosamente** quando o alvo no FS sumiu (entre término da varredura
e clique do usuário). `_refresh_open_buttons_visibility` chamado em
`_on_finished`, `showEvent` (troca de aba) e dentro dos próprios click
handlers. Sem mais modal "Rode novamente" que confundia o operador.

### 9. Integração Notion (Fase 5)

**Database 📬 Publicações** já criada no Notion do escritório:
- Database URL: https://www.notion.so/6ee4f13a9ea34506824656a261d99dce
- Data source ID: `78070780-8ff2-4532-8f78-9e078967f191`
- Database ⚖️ Processos data source: `5e93b734-4043-4c89-a513-5e00a14081bb`

**SQLite — 3 colunas novas em `publicacoes`:**
- `notion_page_id TEXT`: NULL=pendente; UUID=enviado; "SKIPPED"=ignorado
- `notion_attempts INTEGER NOT NULL DEFAULT 0`
- `notion_last_error TEXT`
- Índice parcial: `idx_publicacoes_notion_pending ON publicacoes(notion_page_id) WHERE notion_page_id IS NULL`
- Migração ALTER TABLE idempotente em `_migrate_notion_columns_if_needed`
  cobre bancos pré-Fase 5.

**Modal one-shot** (`FLAG_NOTION_PRIMEIRA_CARGA` em `app_flags`) —
3 ramos: `tudo_agora` / `skipped_passado` / `adiado` / `banco_vazio`.
Disparado na 1ª invocação dos handlers de download, antes do worker.

**Sync** (`notion_rpadv/services/dje_notion_sync.py`):
- `fetch_pending_for_notion(conn)` — pega `notion_page_id IS NULL AND
  notion_attempts < 3`, ordem cronológica.
- Rate-limit 350ms entre chamadas; retry exponencial 1s/2s/4s em 429.
- Falha em uma pub: `mark_publicacao_notion_failure` (attempts +1,
  grava last_error); segue.
- 3 falhas → pub fica "presa" (não retentada automaticamente).
- `NotionAuthError` aborta loop completo.
- Hook no `_DJEWorker._run_notion_sync_if_applicable` chamado após
  `_finalize_*` em todos os flows EXCETO `flow=manual` (modo
  personalizado não toca banco do escritório).

**Mapper** (`notion_rpadv/services/dje_notion_mapper.py`):
- 18 das 20 propriedades enviadas (Cliente é Rollup, Certidão é Formula
  automáticas).
- Título sequencial: `{Tribunal}___{YYYY-MM-DD}___{N}` onde N =
  count+1 de pubs já enviadas (`notion_page_id` não-NULL e != SKIPPED)
  com mesma combinação tribunal+data.
- Texto truncado em 2000 chars no inline; corpo da página recebe texto
  COMPLETO em blocos `paragraph` quebrados em chunks ≤ 2000 chars.
- Lookup do Processo via cache local (Relation ↔ ⚖️ Processos);
  checkbox "Processo não cadastrado" se lookup falha.
- Multi-select "Advogados intimados" cruza com **12 OABs** (6 ativas +
  6 desativadas — pubs antigas podem ter qualquer uma); externos
  desprezados; checkbox "Advogados não cadastrados" só dispara quando
  havia destinatários mas nenhum era do escritório.

**NotionClient** ganhou `create_page_in_data_source(data_source_id,
properties, children)` — endpoint API 2025-09-03 com
`parent.data_source_id` em vez de `parent.database_id` legacy.

**UI:**
- Botão "Tentar reenviar falhas Notion" (visível quando
  `count_publicacoes_failed_notion > 0`); click zera attempts e dispara
  sync síncrona.
- Banner final inclui sumário: "Notion: X enviadas, Y falharam (Z
  presas há 3+ tentativas)".
- Container "Execução" reusado pra logs do envio Notion (mesmo log_area).

---

## Lista oficial de advogados (Fase 4 reativou os 4)

`notion_rpadv/services/dje_advogados.py`:
```python
ADVOGADOS = [
    {"nome": "Ricardo Luiz Rodrigues da Fonseca Passos", "oab": "15523", "uf": "DF"},
    {"nome": "Leonardo Guedes da Fonseca Passos",        "oab": "36129", "uf": "DF"},
    {"nome": "Vitor Guedes da Fonseca Passos",           "oab": "48468", "uf": "DF"},
    {"nome": "Cecília Maria Lapetina Chiaratto",         "oab": "20120", "uf": "DF"},
    {"nome": "Samantha Lais Soares Mickievicz",          "oab": "38809", "uf": "DF"},
    {"nome": "Deborah Nascimento de Castro",             "oab": "75799", "uf": "DF"},
    # 6 desativados na Fase 2.1 (2026-05-01) seguem comentados:
    # Juliana Vieira (65089), Juliana Chiaratto (81225), Shirley (37654),
    # Erika (39857), Maria Isabel (84703), Cristiane (79658)
]

# Constante usada pelo modal de reativação (controla cursores falsos):
REACTIVATED_2026_05_02_OABS = (
    ("48468", "DF"), ("20120", "DF"), ("38809", "DF"), ("75799", "DF"),
)
```

**Multi-select "Advogados intimados"** no Notion mapper usa as **12**
OABs (6 ativas + 6 desativadas) porque pubs antigas podem conter
qualquer uma. Lista canônica em
`notion_rpadv/services/dje_notion_mapper._OABS_ESCRITORIO_TAGS`.

---

## Estado do banco SQLite em produção

**Local:** `%APPDATA%\NotionRPADV\leitor_dje.db`

**Schema atual (pós-Fase 5):**
- `djen_state` — legada, mantida só pra detecção de migração da Fase 3
- `djen_advogado_state` — watermark por advogado
- `publicacoes` — schema com 13 colunas (10 originais + 3 Notion):
  - djen_id (PK), hash (UNIQUE), oabs_escritorio, oabs_externas,
    numero_processo, data_disponibilizacao, sigla_tribunal, payload_json,
    captured_at, captured_in_mode, **notion_page_id, notion_attempts,
    notion_last_error**
- `app_flags` — flags one-shot (key, value, set_at)

**Flags canônicas:**
- `FLAG_REATIVACAO_2026_05_02 = "reativacao_4_advogados_2026_05_02_treated"`
- `FLAG_NOTION_PRIMEIRA_CARGA = "notion_primeira_carga_v1"`

**Sentinela:**
- `NOTION_SKIPPED_SENTINEL = "SKIPPED"` (em `notion_page_id` quando
  usuário escolheu pular envio na 1ª carga)

**Estado dos cursores e publicações em produção:** o último
inventário documentado é do handoff anterior (Fase 3, 02/05/2026):
2141 publicações cobrindo `2026-01-01 → 2026-05-01`. Após Fase 4 e
Fase 5, o usuário ainda não relatou execuções de smoke pesado contra
o banco real — execuções subsequentes podem ter alterado contagens.

---

## Constantes operacionais Notion (Fase 5)

`notion_rpadv/services/dje_notion_constants.py`:
```python
NOTION_PUBLICACOES_DATA_SOURCE_ID = "78070780-8ff2-4532-8f78-9e078967f191"
NOTION_PROCESSOS_DATA_SOURCE_ID  = "5e93b734-4043-4c89-a513-5e00a14081bb"
NOTION_RATE_LIMIT_DELAY_MS       = 350
NOTION_MAX_RETRY_ATTEMPTS        = 3
NOTION_RETRY_BACKOFFS_SECONDS    = (1.0, 2.0, 4.0)
NOTION_TEXTO_INLINE_LIMIT        = 2000
NOTION_BLOCK_TEXT_LIMIT          = 2000
```

---

## Memórias / preferências do usuário

(de `~/.claude/projects/C--dev-Claude-Notion/memory/MEMORY.md`)

1. **Trabalhar no main repo, não em worktree** — `cd /c/dev/Claude-Notion`
   direto. Worktrees deram trabalho extra na Fase 2.1.
2. **Paleta brand RPADV vence Notion** — chips no app usam brand do
   escritório, não cores do Notion.
3. **Permissions configuradas** — auto-aprovar Write/Edit/pytest;
   pedir autorização para git push, rm, pip/npm install.
4. **PR + merge pelo GitHub web** pelo usuário — Claude faz commit +
   push de branch nova, NÃO faz merge direto em main.

---

## Pendências operacionais (não bloqueantes)

### 1. Branches remotas órfãs no GitHub

Mergeadas há tempos, podem ser deletadas:
- `chore/remove-dark-mode` (commit `03e9aef`)
- `fix/auditoria-lote-2` (commit `f27a795`)

Comando opcional:
```
git push origin --delete chore/remove-dark-mode fix/auditoria-lote-2
```

### 2. Diretório zumbi de worktree

`C:\dev\Claude-Notion\.claude\worktrees\jolly-cerf-6bb0f7\` ainda existe
físicamente (worktree usada pelo Claude nas últimas sessões). Stale
agora — pode deletar quando esta sessão encerrar:
```cmd
rmdir /S /Q "C:\dev\Claude-Notion\.claude\worktrees\jolly-cerf-6bb0f7"
git worktree prune
git branch -D claude/jolly-cerf-6bb0f7
```

### 3. Untracked não-Fase-5 (não faziam parte das entregas)

- `.gitignore` (modificado — exceção pra `Auditoria_Kurier_*.xlsx`)
- `HANDOFF_2026-05-01.md`, `HANDOFF_FASE_3_2026-05-02.md`,
  `RELATORIO-AUDITORIA.md` — docs antigas
- `.coverage` — artefato pytest-cov
- `scripts/auditoria_kurier/` — utilitário separado, não tem PR aberto

---

## Próximas fases possíveis (não-escopo)

Itens explicitamente fora do escopo até aqui, candidatos pra próximas
entregas:

1. **Atualização de páginas existentes no Notion** — hoje só cria
   (notion_page_id NUNCA é regravado). Pra suportar atualização
   precisaria detectar mudanças relevantes na publicação e fazer
   PATCH `/v1/pages/{id}`.
2. **Sincronização bidirecional** — mudanças manuais no Notion (ex:
   marcar Status=Lida) não voltam pro SQLite.
3. **Integração com database de Tarefas** — criar Tarefa
   automaticamente a partir de Publicação relevante (filtro: Status
   default + tipo de comunicação).
4. **Tabela `execucoes_dje`** no SQLite — persistir histórico de
   execuções (datetime início/fim, flow, contagens, status).
5. **Filtragem de processos do Notion por advogado responsável** no
   eixo CNJ — hoje varre TODOS os processos cadastrados (~1000+).
6. **Aba "Banco" no app** com visualização do SQLite (read-only,
   filtros).
7. **Modo de revisão antes de enviar** — dry-run que mostra o que
   SERIA enviado sem mandar.
8. **Atualizar Status no Notion** baseado em mudanças no SQLite (se
   pub é re-classificada localmente, Status no Notion vira "Triada").
9. **Cron / agendamento automático** (APScheduler interno) — disparo
   diário automático, hoje continua manual.
10. **`DATA_INICIO_HISTORICO_ESCRITORIO` configurável** via UI (hoje
    hardcoded em `2026-01-01`).
11. **Reativação dos 6 advogados pré-Fase-2.1** quando volume diário
    estabilizar sem 429.
12. **Schema da tabela `publicacoes` com CHECK pra mode='cnj'** —
    hoje `captured_in_mode` aceita só `'padrao'/'manual'` e o eixo CNJ
    grava como `'padrao'`. Distinção fica só no naming do Excel
    (`Publicacoes_CNJ_*`).

---

## Arquivos-chave

```
notion_rpadv/services/
  dje_db.py                    ← schema SQLite + helpers Notion sync (Fase 5)
  dje_state.py                 ← API por advogado (read/update/reset cursor)
  dje_client.py                ← AdvogadoConsulta + ProcessoConsulta + fetch_all
  dje_transform.py             ← schema canônico 20 cols + HIDDEN_COLUMNS
  dje_exporter.py              ← Excel-de-execução + histórico + abas Status/Log
  dje_advogados.py             ← lista oficial 6 + REACTIVATED_2026_05_02_OABS
  dje_processos.py             ← lista CNJs do cache Notion (eixo CNJ)
  dje_notion_constants.py      ← Fase 5: data source IDs, rate limit, retries
  dje_notion_mapper.py         ← Fase 5: payload das 18 propriedades + corpo
  dje_notion_sync.py           ← Fase 5: loop com rate-limit + retry + attempts

notion_rpadv/widgets/
  calendar_date_edit.py        ← Fase 4: QDateEdit com QCalendarWidget custom

notion_rpadv/pages/
  leitor_dje.py                ← UI completa: 2 eixos, 3 modos, Notion sync hook,
                                  modal primeira carga, botão retry Notion

notion_bulk_edit/
  notion_api.py                ← Fase 5: create_page_in_data_source

tests/
  test_dje_db.py               ← + 8 tests F5 (migração + helpers Notion)
  test_dje_state.py
  test_dje_client.py
  test_dje_transform.py
  test_dje_exporter.py
  test_dje_advogados.py
  test_dje_integracao_fase3.py
  test_dje_processos.py
  test_dje_notion_mapper.py    ← Fase 5 NEW: 24 tests (mapper + helpers)
  test_dje_notion_sync.py      ← Fase 5 NEW: 11 tests (sync + retry + cancel)
  test_leitor_dje_page.py      ← + 6 tests F5 (modal + botão retry)
```

---

## Comandos úteis

### Verificar estado do banco
```
python -c "
import os, sqlite3
from pathlib import Path
db = Path(os.environ['APPDATA']) / 'NotionRPADV' / 'leitor_dje.db'
conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row
print('publicacoes:', conn.execute('SELECT COUNT(*) FROM publicacoes').fetchone()[0])
print('  pendentes Notion:', conn.execute(
    'SELECT COUNT(*) FROM publicacoes WHERE notion_page_id IS NULL AND notion_attempts < 3'
).fetchone()[0])
print('  enviadas Notion:', conn.execute(
    'SELECT COUNT(*) FROM publicacoes WHERE notion_page_id IS NOT NULL AND notion_page_id != \"SKIPPED\"'
).fetchone()[0])
print('  presas (3+ falhas):', conn.execute(
    'SELECT COUNT(*) FROM publicacoes WHERE notion_page_id IS NULL AND notion_attempts >= 3'
).fetchone()[0])
print('djen_advogado_state:')
for r in conn.execute('SELECT * FROM djen_advogado_state'):
    print(' ', dict(r))
print('app_flags:')
for r in conn.execute('SELECT * FROM app_flags'):
    print(' ', dict(r))
"
```

### Forçar reset do modal de primeira carga Notion
```
python -c "
import os, sqlite3
from pathlib import Path
db = Path(os.environ['APPDATA']) / 'NotionRPADV' / 'leitor_dje.db'
conn = sqlite3.connect(str(db))
conn.execute('DELETE FROM app_flags WHERE key=?', ('notion_primeira_carga_v1',))
conn.commit()
"
```

### Rodar suite completa
```
cd /c/dev/Claude-Notion
python -m pytest tests/ --no-header -q
```

### Rodar apenas tests da Fase 5
```
python -m pytest tests/test_dje_notion_mapper.py tests/test_dje_notion_sync.py \
  tests/test_dje_db.py -k "F5 or notion" tests/test_leitor_dje_page.py -k "F5_" \
  --no-header -q
```

### Lint
```
python -m ruff check notion_rpadv/ tests/
```

### Reset honesto do banco (cuidado — destrutivo)
```
python -c "
import os, sqlite3
from pathlib import Path
db = Path(os.environ['APPDATA']) / 'NotionRPADV' / 'leitor_dje.db'
conn = sqlite3.connect(str(db))
conn.execute('DELETE FROM publicacoes')
conn.execute('DELETE FROM djen_advogado_state')
conn.execute('DELETE FROM djen_state')
conn.execute('DELETE FROM app_flags')
conn.commit()
print('Banco zerado.')
"
```

---

## Como continuar a conversa em outro chat

Cole no início do novo chat:

> Estou continuando o projeto Claude-Notion (Leitor DJE). A Fase 5 está
> mergeada (PR #16, commit `0eb8362`). Lê o handoff em
> `C:\dev\Claude-Notion\HANDOFF_FASE_5_2026-05-03.md` pra contexto completo.
>
> Próximo passo: [descrição do que você quer fazer]

O Claude novo vai ler este arquivo e ter contexto suficiente pra
continuar sem perder fio.
