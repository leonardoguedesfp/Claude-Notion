# Handoff — Leitor DJE Fase 3 (2026-05-02)

Este documento permite continuar o trabalho em outra sessão do Claude Code com contexto completo. Todo o conteúdo abaixo é estado verdadeiro e validado em smoke real.

---

## TL;DR

**Fase 3 completa do Leitor DJE foi mergeada na main (PR #14, commit `bc4ef00`).** Cache local incremental SQLite, watermark **por advogado**, modo padrão (uso diário) + modo personalizado (transient para OABs externas), Excel com abas auxiliares Status/Log, lista ativa temporariamente reduzida a Ricardo + Leonardo.

**624 passed, 7 skipped, 0 failing** após 4 rodadas de smoke real e ajustes consequentes. Branch `feat/leitor-dje-fase-3` deletada local + remoto.

---

## Estado atual do projeto

| | |
|---|---|
| Branch atual | `main` |
| Último commit em main | `bc4ef00 Merge pull request #14 from leonardoguedesfp/feat/leitor-dje-fase-3` |
| Suite de testes | 624 passed, 7 skipped, 0 failing |
| Lint (ruff) | verde nos arquivos da Fase 3 (2 erros pré-existentes em `test_dje_transform.py:732-733` E402, não-relacionados) |
| Working tree | limpo (3 untracked não-Fase-3: `.coverage`, `HANDOFF_2026-05-01.md`, `RELATORIO-AUDITORIA.md`) |

---

## Escopo do que foi entregue

A Fase 3 consolidou múltiplas iterações que evoluíram via smoke real:

1. **Fase 3 inicial** — schema `djen_state` (singleton) + 2 modos manual/padrão + Excel histórico
2. **Hotfix UX** — datepickers no modo padrão, modal de migração, layout do modo manual
3. **Hotfix watermark integrity** — 3 bugs descobertos no smoke real (modal indevido, contadores incorretos, cursor avançando com falha parcial)
4. **Reformulação watermark-por-advogado** — cursor único provou-se estruturalmente frágil; refator completo para `djen_advogado_state`
5. **Ajustes pós-smoke real** — cursor conservador (snapshot pré-retry), lista 6→2 advogados, modal legível, log claro do retry diferido

---

## Decisões arquiteturais importantes

### 1. Watermark POR ADVOGADO

Tabela `djen_advogado_state` com 1 linha por advogado oficial:
```sql
CREATE TABLE djen_advogado_state (
    numero_oab TEXT NOT NULL,
    uf_oab TEXT NOT NULL,
    ultimo_cursor TEXT,            -- ISO date YYYY-MM-DD; NULL = nunca executou
    last_run TEXT,                 -- ISO datetime; NULL = nunca executou
    PRIMARY KEY (numero_oab, uf_oab)
);
```

Cada advogado tem cursor próprio. Janela individual = `[cursor + 1d, hoje]`. Cursor vazio (`NULL`) → `DEFAULT_CURSOR_VAZIO = 2025-12-31` → janela natural `[01/01/2026, hoje]`. **Sem modal de "primeira execução"** — cursor vazio é estado normal.

Tabela legada `djen_state` (Fase 3 inicial) preservada no schema **só para detecção de migração**: `is_legacy_state_present(conn)` checa se existe linha lá; modal de aviso pede confirmação; `clear_legacy_state_and_publicacoes` zera ambas as tabelas (publicações + state legado) para reconstrução com cursores individuais.

### 2. Cursor conservador pós-smoke real

**Decisão crítica do smoke real:** retry diferido (Fase 2.2) coleta dados úteis mas **NÃO destranca o cursor**. Implementação:

- Em `dje_client.fetch_all`, snapshot `failed_per_adv_main = [set(s) for s in failed_per_adv]` é capturado **antes** do retry diferido
- `data_max_safe` é calculado a partir desse snapshot (estado pós-varredura principal)
- Se varredura principal falhou em sub-janela K → `data_max_safe = sub_windows[K-1][1]` (fim da última sub-janela contígua completa) ou `data_inicio - 1d` se K=0
- `aggs.erro` permanece setado mesmo se retry diferido recuperar items — UI mostra "FALHA: HTTP 429" coerentemente
- Items recuperados pelo retry diferido vão pro banco normalmente (dedup via `ON CONFLICT(djen_id) DO NOTHING`), reduzindo trabalho da próxima execução

**Validado em smoke real:** janela 4 meses → falha em abr/mai → cursor parou em `2026-03-31` mesmo com retry recuperando 685 publicações de abril/maio.

### 3. Modo personalizado é transient

Modo personalizado (manual) **NÃO toca o banco do escritório**:
- NÃO insere em `publicacoes`
- NÃO regenera `Historico_DJEN_completo.xlsx`
- NÃO atualiza `djen_advogado_state`
- Apenas gera Excel-de-execução com as publicações captadas (versionado)

Linha de OAB externa tem **2 campos apenas** (OAB + UF). Nome é resolvido automaticamente via `destinatarioadvogados[*].advogado.nome` retornado pela API (lógica em `dje_transform._resolve_externa_nome_via_destinatarios`).

### 4. AdvogadoConsulta + janelas individuais

`dje_client.fetch_all` aceita `list[AdvogadoConsulta]` (advogado + janela individual). Cada consulta tem suas próprias `sub_windows` (split mensal aplicado individualmente quando janela > 31 dias). Worker constrói consultas via `dje_state.compute_advogado_window` por advogado.

### 5. Excel sempre gerado + abas auxiliares

- **Excel-de-execução** versionado (`Publicacoes_DJEN_*.xlsx`) é gerado **sempre**, mesmo com 0 novas publicações — pra evidência da execução
- **`Historico_DJEN_completo.xlsx`** (path fixo) é regenerado atomicamente (.tmp + rename) ao final de cada execução em modo padrão; tolerante a `PermissionError` quando Excel está aberto
- **Aba "Status"**: 1 linha por advogado oficial (nome, OAB/UF, cursor, dias atrás, última execução)
- **Aba "Log"**: mensagens da execução com timestamps

### 6. Lista de advogados temporariamente em 2

Em `notion_rpadv/services/dje_advogados.py`:
```python
ADVOGADOS = [
    {"nome": "Ricardo Luiz Rodrigues da Fonseca Passos", "oab": "15523", "uf": "DF"},
    {"nome": "Leonardo Guedes da Fonseca Passos",        "oab": "36129", "uf": "DF"},
    # 4 outros comentados — Vitor, Cecília, Samantha, Deborah
    # Reativar quando watermark consolidado e volume diário sem 429
]
```

---

## Estado do banco SQLite em produção

**Local:** `C:\Users\LeonardoGuedesdaFons\AppData\Roaming\NotionRPADV\leitor_dje.db`

**Estado pós-smoke validação (2026-05-02 ~22h):**
- 3 tabelas: `djen_advogado_state`, `djen_state` (vazia), `publicacoes`
- `publicacoes`: 2141 linhas cobrindo `2026-01-01 → 2026-05-01`
- `djen_state`: 0 linhas (legada zerada pela migração)
- `djen_advogado_state`: 6 linhas
  - Ricardo (15523/DF): cursor `2026-03-31` ← **resultado do smoke do Ajuste 1**
  - Leonardo (36129/DF): cursor `2026-03-31`
  - Vitor, Cecília, Samantha, Deborah: cursor `2026-05-02` (dados órfãos do smoke anterior; não impactam pq não estão mais em `ADVOGADOS`)

**Próxima execução de "Baixar publicações novas"** vai varrer `[01/04/2026, hoje]` (~30 dias, sem split mensal) para Ricardo + Leonardo. Janela curta + 2 advogados = baixa probabilidade de 429.

---

## Backups disponíveis para rollback

Mesma pasta `%APPDATA%\NotionRPADV\`:

| Arquivo | Tamanho | Origem |
|---|---|---|
| `leitor_dje_BACKUP.db` | 45 MB | mais antigo |
| `leitor_dje_BACKUP_pre_smoke.db` | 45 MB | pré-smoke do hotfix watermark integrity |
| `leitor_dje_BACKUP_pre_smoke_v2.db` | 45 MB | pré-smoke da reformulação watermark-por-advogado |

Restaurar: `Copy-Item leitor_dje_BACKUP_pre_smoke_v2.db leitor_dje.db -Force` (com app fechado).

---

## Pendências operacionais

### 1. Diretório zumbi da worktree

`C:\dev\Claude-Notion\.claude\worktrees\objective-nobel-9ef0e1\` ainda existe fisicamente (git já removeu do tracking, mas pasta não pôde ser deletada por cwd lock do harness). **Quando essa sessão do Claude Code encerrar**, deletar manualmente:

```cmd
rmdir /S /Q "C:\dev\Claude-Notion\.claude\worktrees\objective-nobel-9ef0e1"
```

### 2. Branches remotas órfãs (não-Fase-3)

Listadas no GitHub mas já mergeadas em main:
- `chore/remove-dark-mode` (commit `03e9aef`)
- `fix/auditoria-lote-2` (commit `f27a795`)

Apagar via GitHub web ou:
```
git push origin --delete chore/remove-dark-mode fix/auditoria-lote-2
```

### 3. Untracked não-Fase-3 (provavelmente da Fase 2.1)

No working tree mas não commitados (decisão sua se incluir em PR futuro):
- `HANDOFF_2026-05-01.md`
- `RELATORIO-AUDITORIA.md`
- `.coverage` (artefato de pytest-cov)

---

## Memórias / preferências do usuário

(de `~/.claude/projects/C--dev-Claude-Notion/memory/MEMORY.md`)

1. **Trabalhar no main repo, não em worktree** — `cd /c/dev/Claude-Notion` direto. Worktrees deram trabalho extra na Fase 2.1.
2. **Paleta brand RPADV vence Notion** — chips no app usam brand do escritório, não cores do Notion.

(memória nova após esta sessão — capturar se quiser)

3. **Permissions configuradas** — auto-aprovar Write/Edit/pytest/etc.; pedir autorização para git push, rm, pip/npm install. Setado em `~/.claude/settings.json`.

---

## Próximas fases possíveis (não-escopo da Fase 3)

Itens explicitamente fora do escopo desta entrega, candidatos para fases futuras:

1. **Carga no Notion** — criar tarefas no banco Notion a partir das publicações (Fase 4 ou posterior)
2. **Alertas por e-mail** quando publicações chegarem
3. **Captação automática em background** (APScheduler / cron interno) — disparo continua manual
4. **UI de admin** para gerenciar lista do escritório (continua editando `dje_advogados.py`)
5. **Painel de visualização** do banco SQLite dentro do app (consulta visual com filtros)
6. **Migração para httpx + Tenacity** (continuamos com requests síncrono atual)
7. **Reativação dos 4 advogados desativados** quando volume diário estabilizar sem 429
8. **`DATA_INICIO_HISTORICO_ESCRITORIO` configurável** via UI (hoje hardcoded em `2026-01-01`)

---

## Arquivos-chave da Fase 3

```
notion_rpadv/services/
  dje_db.py              ← schema SQLite + helpers de migração + CRUD
  dje_state.py           ← API por advogado (read/update_advogado_cursor)
  dje_client.py          ← AdvogadoConsulta + fetch_all com janelas individuais
  dje_transform.py       ← split_advogados_columns + resolução de nome externo
  dje_exporter.py        ← Excel-de-execução + histórico + abas Status/Log
  dje_advogados.py       ← lista oficial (atualmente 2: Ricardo + Leonardo)

notion_rpadv/pages/
  leitor_dje.py          ← UI com 2 modos + worker bifurcado (padrão vs manual)
                            + helpers de modal estilizados (_styled_question/warning)

tests/
  test_dje_db.py
  test_dje_state.py
  test_dje_client.py
  test_dje_transform.py
  test_dje_exporter.py
  test_dje_advogados.py
  test_dje_integracao_fase3.py
  test_leitor_dje_page.py
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
print('djen_state:', conn.execute('SELECT COUNT(*) FROM djen_state').fetchone()[0])
print('djen_advogado_state:')
for r in conn.execute('SELECT * FROM djen_advogado_state'):
    print(' ', dict(r))
"
```

### Rodar testes
```
cd /c/dev/Claude-Notion
python -m pytest tests/ --no-header -q
```

### Rodar suite parcial (rápida)
```
python -m pytest tests/test_dje_advogados.py tests/test_dje_state.py tests/test_dje_db.py tests/test_dje_client.py tests/test_dje_transform.py tests/test_dje_exporter.py tests/test_dje_integracao_fase3.py --no-header -q
```
(testes de UI demoram ~5min porque carregam Qt; rodar separado quando precisar)

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
conn.commit()
conn.close()
print('Banco zerado.')
"
```

---

## Como continuar a conversa em outro chat

Cole no início do novo chat algo como:

> Estou continuando o projeto Claude-Notion (Leitor DJE). A Fase 3 já está mergeada (PR #14, commit bc4ef00). Lê o handoff em `C:\dev\Claude-Notion\HANDOFF_FASE_3_2026-05-02.md` pra contexto completo.
>
> Próximo passo: [descrição do que você quer fazer]

O Claude novo vai ler este arquivo e ter contexto suficiente pra continuar sem perder fio.
