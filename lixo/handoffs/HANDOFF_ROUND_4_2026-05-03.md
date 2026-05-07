# Handoff — Leitor DJE × Notion Round 4/4.5/4.6 (2026-05-03)

Contexto pra retomar o trabalho em outra sessão. Estado real validado
após o Round 4 mergeado, Round 4.5 commitado direto na main, Round 4.6
(reset local) executado, e nova captura completa rodada pelo Leonardo.

---

## TL;DR

Os Rounds 4, 4.5 e 4.6 estão **concluídos**. Schema do Notion está
**finalizado** (checkbox `Processo não cadastrado` dropado, multi-selects
`Tarefa sugerida` (6 opções) e `Alerta contadoria` (5 opções) coloridos).
Captura nova rodada com pipeline pós-Round-4 cobre **01/01/2026 →
03/05/2026** com **1.608 canônicas + 544 duplicatas suprimidas** (mesmo
total do Round 3 anterior).

**Próximo round em vista** (não iniciado, prompt foi cancelado): nova
investigação anatômica das publicações entregues, gerando
`docs/anatomia-publicacoes-pos-round-4.md` para validar o que mudou,
detectar regressões e atualizar backlog.

---

## Estado atual do projeto

| | |
|---|---|
| Branch atual | `main` |
| Último commit em main | `f150072 feat(dje): Round 4.5 frente 2 — filtro Atas de Sessão TJDFT tipo "57"` |
| Suite de testes | **900 passed, 7 skipped, 0 falhas** (~18s) |
| Lint (ruff) | limpo nos arquivos do Round 4/4.5; 17 erros pré-existentes em arquivos antigos (`test_audit_smoke.py`, `test_dje_transform.py`, `test_fase_2a/2c/3.py`, `test_round_5_rendering.py`, `test_round_6.py`) — mesmos do handoff Fase 5, fora de escopo |
| Working tree | sujo apenas com untracked/modificados pré-existentes (HANDOFFs antigos, `.coverage`, `.gitignore`, `RELATORIO-AUDITORIA.md`, `scripts/auditoria_kurier/`, e o CSV exportado do Notion na pasta Temp) |

Histórico recente (`git log --oneline -10`):
```
f150072 feat(dje): Round 4.5 frente 2 — filtro Atas de Sessão TJDFT tipo "57"
afec2d7 feat(dje): Round 4.5 frente 1 — auto-Status "Nada para fazer" para Listas TRT10/TST
5d700ee Merge pull request #19 from leonardoguedesfp/round-4-mapper
afddba4 chore(dje): Round 4.5 — teste de regressão para <br> residual no Texto
2bcf9f6 feat(dje): Round 4.3+4.4+4.6 — auto-Tarefa, auto-Alerta, remove checkbox
c2fdb38 feat(dje): Round 4.2 — normalizar Classe via MAPA_NOMECLASSE
24c24ea feat(dje): Round 4.1 — reformatar Partes para formato genérico legível
cc00bc4 Merge pull request #18 from leonardoguedesfp/round-2-prep
9d12342 Merge pull request #17 from leonardoguedesfp/round-1-fixes-app
365edc6 Merge pull request #16 from leonardoguedesfp/feat/leitor-dje-notion-sync
```

---

## Histórico das fases e rounds

| Round | Data | Escopo principal |
|---|---|---|
| 1 | abr/2026 | Cliente HTTP DJEN, paginação, anotação por advogado, Excel |
| 2 | abr/2026 | Schema canônico, dedup, observacoes A+B, sanitize Unicode |
| 2.1 | 01/05 | Lista 12→6 advogados, IllegalCharacterError fix |
| 2.2 | 02/05 | Split mensal, retry diferido, cancel button |
| 3 | 02/05 | SQLite cache, watermark POR ADVOGADO, abas Status/Log no Excel |
| 4-Fase | 02-03/05 | Reativação 4 advogados (volta a 6), eixo CNJ, CalendarDateEdit |
| 5-Fase | 03/05 | Integração Notion: database 📬 Publicações, sync, mapper 18 props |
| **R1 (4 dos rounds atuais)** | 03/05 | 8 fixes pré-re-migração: mapeamentos canônicos (1.1-1.3), text pipeline (1.4-1.5-1.7-1.8), dedup (1.6) — PR #17 |
| **R2** | 03/05 | Detecção dinâmica de capabilities Notion + reset SQLite — PR #18 |
| **R3** | 03/05 | Re-migração massiva (rodada pelo Leonardo) — 2.141 pubs no acervo intermediário |
| **R4** | 03/05 | Reformatar Partes, normalizar Classe, auto-Tarefa (6 regras), auto-Alerta (5 regras), remover checkbox `Processo não cadastrado` — PR #19 |
| **R4.5** | 03/05 | Frente 1: auto-Status `Nada para fazer` para Listas TRT10/TST cadastradas. Frente 2: filtro Atas TJDFT tipo "57". Direto na main (`afec2d7`, `f150072`). |
| **R4.6** | 03/05 | Reset estado local: apagar `leitor_dje.db` (+ WAL/SHM), `cache.db` preservado. Operação de filesystem, sem commits. |
| **R3 v2** | 03/05 | Nova captura completa pelo Leonardo após Round 4.6: 2.152 inseridas, 1.608 canônicas + 544 duplicatas, período 01/01/2026 → 03/05/2026 |

---

## Decisões consolidadas do Round 4 (D1-D4)

| # | Decisão | Status |
|---|---|---|
| D1 | `Partes` formato GENÉRICO (Polo Ativo / Polo Passivo / Terceiro Interessado) — não nomenclatura específica | ✅ Implementado em `formatar_partes` (`dje_notion_mappings`) |
| D2 | `Tarefa sugerida` SEM precedência: pub Acórdão + Pauta soma D.03 + E.04 | ✅ Implementado em `_aplicar_regras_tarefa_sugerida` (`dje_notion_mapper`) |
| D3 | `Alerta contadoria → Trânsito em julgado pendente` EXCLUI cumprimentos provisórios | ✅ Implementado: regex checa `nomeClasse contains "CUMPRIMENTO" AND NOT contains "PROVISÓRIO"` |
| D4 | Mapper PARA DE GRAVAR checkbox `Processo não cadastrado`, info migra pro alerta | ✅ Implementado. Schema do Notion atual JÁ DROPOU o checkbox manualmente. |

---

## Schema atual da database 📬 Publicações

**22 propriedades** (sem o checkbox `Processo não cadastrado`):

```
Identificação (title)
Advogados intimados (multi-select, 12 OABs)
Advogados não cadastrados (checkbox)
Alerta contadoria (multi-select, 5 opções coloridas)
Certidão (formula sobre Hash)
Classe (rich_text)
Cliente (rollup do Processo)
Data de disponibilização (date)
Duplicatas suprimidas (rich_text)
Hash (rich_text)
ID DJEN (number)
Link (URL)
Observações (rich_text)
Partes (rich_text)
Processo (relation com ⚖️ Processos)
Status (select: Nova, Nada para fazer, Tratada, Pré-migração)
Tarefa sugerida (multi-select, 6 opções coloridas)
Texto (rich_text, max 2000 chars)
Tipo de comunicação (select: Intimação, Lista de Distribuição, Edital)
Tipo de documento (select: 10 canônicos + Outros)
Tribunal (select)
Órgão (rich_text)
```

### Tarefa sugerida — 6 opções com cores

| Opção | Cor |
|---|---|
| `D.01 Análise de publicação` | gray |
| `D.02 Análise de sentença` | blue |
| `D.03 Análise de acórdão` | purple |
| `E.01 Cadastro de cliente/processo` | red |
| `E.02 Atualizar dados no sistema` | orange |
| `E.04 Inscrição para sustentação oral` | yellow |

### Alerta contadoria — 5 opções com cores

| Opção | Cor |
|---|---|
| `Processo não cadastrado` | red |
| `Instância desatualizada` | orange |
| `Trânsito em julgado pendente` | yellow |
| `Texto imprestável` | brown |
| `Pauta presencial sem inscrição` | pink |

---

## Captura R3 v2 — log resumido

Rodada pelo Leonardo após Round 4.6. Janela: `01/01/2026 → 03/05/2026`,
6 OABs ativas.

```
[1/6] Ricardo Luiz (15523/DF) — FALHA: HTTP 429 → recuperado em retry diferido
[2/6] Leonardo Guedes (36129/DF) — FALHA: HTTP 429 → recuperado
[3/6] Vitor Guedes (48468/DF) — FALHA: HTTP 429 → recuperado
[4/6] Cecília (20120/DF) — FALHA: HTTP 429 → recuperado
[5/6] Samantha (38809/DF) — 997 publicações em 13 páginas
[6/6] Deborah (75799/DF) — FALHA: HTTP 429 → recuperado

SQLite: 2152 novas inseridas (0 já existiam).
Cursores finais:
  Ricardo (15523/DF) → 31/03/2026
  Leonardo (36129/DF) → 31/03/2026
  Vitor (48468/DF) → 31/03/2026
  Cecília (20120/DF) → 31/03/2026
  Samantha (38809/DF) → 03/05/2026
  Deborah (75799/DF) → 31/03/2026

Notion sync:
  schema capabilities detectadas (has_duplicatas_suprimidas=True)
  envio concluído — 1608 enviadas, 544 duplicatas suprimidas, 0 falharam (em 2288.5s)

Notion dedup flush:
  531 canônicas com pendentes
  530 atualizadas com sucesso
  1 falhou: djen=564026686 — HTTP 502 Bad Gateway transient
```

### Pendências da captura R3 v2

- **1 falha 502 transient no flush dedup** — `djen=564026686`. Não bloqueante; próxima execução resolve, mas a página canônica atualmente NÃO tem a duplicata suprimida na propriedade `Duplicatas suprimidas`. Pode ser corrigido manualmente ou aguardar próxima sync.
- **Cursores divergentes**: 5 OABs param em 31/03/2026 enquanto Samantha vai até 03/05/2026. Pode haver publicações entre 01/04 e 03/05 que NÃO foram capturadas para os outros 5 advogados (somente Samantha foi até a data atual; os outros 5 só rodaram 1 sub-janela no retry diferido). **A próxima captura deve cobrir essa janela faltante** — esperar varrer do `cursor + 1d` para os 5 atrasados.

---

## Estado das frentes do Round 4/4.5

| Frente | Implementação | Onde |
|---|---|---|
| **R4.1** Reformatar `Partes` | ✅ `formatar_partes(destinatarios)` com Polo Ativo/Passivo/Terceiro, dedup, ordem fixa, truncamento defensivo a 2000 chars com `…` | `notion_rpadv/services/dje_notion_mappings.py` |
| **R4.2** Normalizar `Classe` | ✅ `MAPA_NOMECLASSE` com 23 entradas (22 casing torto + 1 title case); `normalizar_classe` preserva cru no fallback | `dje_notion_mappings.py` |
| **R4.3** Auto-`Tarefa sugerida` | ✅ `_aplicar_regras_tarefa_sugerida` com 6 regras (D.01 default, D.02, D.03, E.01, E.02, E.04). D2 implementado: sem precedência | `dje_notion_mapper.py` |
| **R4.4** Auto-`Alerta contadoria` | ✅ `_aplicar_regras_alerta_contadoria` com 5 regras. D3 implementado: trânsito exclui PROVISÓRIO. Detector de texto imprestável conservador | `dje_notion_mapper.py` |
| **R4.5a** Auto-Status Listas TRT10/TST | ✅ `_calcular_status_inicial` retorna `Nada para fazer` quando Lista de Distribuição + tribunal trabalhista + cadastrado | `dje_notion_mapper.py` |
| **R4.5b** Filtro Atas TJDFT tipo "57" | ✅ `deve_filtrar_ata_tjdft` + `filtrar_ata_tjdft_57` em `dje_text_pipeline`; `aplicar_caso_15` ganhou kwargs `tipo_documento_bruto` e `cnj_escritorio`; fallback gracioso quando CNJ não está em JULGADOS | `dje_text_pipeline.py` + `dje_notion_mapper.py` |
| **R4.6** Sem checkbox | ✅ `montar_payload_publicacao` deixou de gravar `Processo não cadastrado`; info vive em `Alerta contadoria → Processo não cadastrado` | `dje_notion_mapper.py` |
| **R4.5 br residual** | ✅ Investigado: pipeline atual processa corretamente. Adicionados 2 testes de regressão (caso djen=494748109 + variantes xhtml) | `tests/test_round_4.py` |

---

## Constantes operacionais

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

`dje_notion_schema.py` (Round 2):
```python
NOTION_CATALOGO_TAREFAS_DATA_SOURCE_ID = "79afc833-77e2-4574-98ba-ebed7bd7e66c"  # implícito via cache
```

`dje_text_pipeline.py`:
```python
LIMITE_TRUNCAMENTO_BYTES = 80_000
PAUTA_FILTRO_MIN_BYTES   = 5_000
LIMITE_BLOCOS_INICIAIS   = 90
TAMANHO_PARAGRAFO_ALVO   = 1500
NOTION_BLOCK_HARD_LIMIT  = 2000
ATA_TJDFT_TIPOS_DOC      = frozenset({"57"})  # Round 4.5 frente 2
```

`dje_notion_mapper.py`:
```python
STATUS_DEFAULT_CRIACAO     = "Nova"
STATUS_NADA_PARA_FAZER     = "Nada para fazer"
_TRIBUNAIS_LISTA_AUTO_TRIADA = frozenset({"TRT10", "TST"})

# Alertas
ALERTA_PROCESSO_NAO_CADASTRADO       = "Processo não cadastrado"
ALERTA_INSTANCIA_DESATUALIZADA       = "Instância desatualizada"
ALERTA_TRANSITO_PENDENTE             = "Trânsito em julgado pendente"
ALERTA_TEXTO_IMPRESTAVEL             = "Texto imprestável"
ALERTA_PAUTA_PRESENCIAL_SEM_INSCRICAO = "Pauta presencial sem inscrição"

# Tarefas
TAREFA_D03_ANALISE_ACORDAO     = "D.03 Análise de acórdão"
TAREFA_D02_ANALISE_SENTENCA    = "D.02 Análise de sentença"
TAREFA_D01_ANALISE_PUBLICACAO  = "D.01 Análise de publicação"
TAREFA_E01_CADASTRO            = "E.01 Cadastro de cliente/processo"
TAREFA_E02_ATUALIZAR_DADOS     = "E.02 Atualizar dados no sistema"
TAREFA_E04_INSCRICAO_SUSTENTACAO = "E.04 Inscrição para sustentação oral"
```

---

## Estado do banco SQLite local

**Local**: `%APPDATA%\NotionRPADV\leitor_dje.db`

Schema completo pós-Round-1+R2:

- `djen_state` (legada, mantida vazia)
- `djen_advogado_state` — watermark por OAB (numero_oab, uf_oab, ultimo_cursor, last_run)
- `publicacoes` — 15 colunas: 10 originais + 3 Notion (notion_page_id/attempts/last_error) + 2 dedup (dup_chave, dup_canonical_djen_id). Índice parcial em `dup_chave WHERE NOT NULL`.
- `dup_pendentes` — fila de duplicatas pra flush nas canônicas (canonical_djen_id, duplicata_djen_id, descritor, partes_json, advogados_json, created_at)
- `app_flags` — flags one-shot

**Conteúdo real após R3 v2**: 2.152 publicações, todas enviadas
(notion_page_id non-NULL ou compartilhando da canônica). 6 OABs em
`djen_advogado_state` com cursores listados acima.

---

## Estado do cache.db

**Local**: `%APPDATA%\NotionRPADV\cache.db`

Tabelas: `meta`, `records`. Records por base:
- Processos: 1.108
- Clientes: 1.072
- Catalogo: 68 (67 tarefas + 1 template)
- Tarefas: 33

**Não tem tabela de tracking de Publicações** — confirmado no Round 4.6.
Pública mapping `djen_id → notion_page_id` vive em
`leitor_dje.db.publicacoes.notion_page_id`.

---

## Memórias / preferências do Leonardo

(de `~/.claude/projects/C--dev-Claude-Notion/memory/MEMORY.md`)

1. **Trabalhar no main repo, não em worktree** — `cd /c/dev/Claude-Notion`
   direto. Worktrees deram trabalho extra.
2. **Paleta brand RPADV vence Notion** — chips no app usam brand do
   escritório, não cores do Notion.
3. **Permissions configuradas** — auto-aprovar Write/Edit/pytest;
   pedir autorização para git push, rm, pip install.
4. **PR + merge pelo GitHub web** pelo Leonardo — Claude faz commit +
   push de branch nova, NÃO faz merge direto em main. **EXCEÇÃO**: nos
   Rounds 4.5 e 4.6 ele explicitamente autorizou push direto na main.

---

## Pendências operacionais (não bloqueantes)

### 1. Falha transient no flush dedup R3 v2

`djen=564026686` recebeu HTTP 502 Bad Gateway no flush. Próxima
execução do app resolverá; ou correção manual via UI Notion para juntar
a duplicata em `Duplicatas suprimidas`.

### 2. Cursores divergentes 5×1

5 OABs em `31/03/2026`, Samantha em `03/05/2026`. Próxima captura cobre
de `cursor + 1d` até hoje, fechando a janela 01/04 → 03/05 para
Ricardo, Leonardo, Vitor, Cecília e Deborah. Esperar varredura
incremental.

### 3. Branches remotas órfãs no GitHub

Não verifiquei nesta sessão. Anteriormente havia
`chore/remove-dark-mode` e `fix/auditoria-lote-2`. Verificar
periodicamente.

### 4. Diretórios zumbis de worktree

`.claude/worktrees/jolly-cerf-6bb0f7` e `.claude/worktrees/sharp-mestorf-723798`
existem fisicamente. Stale agora — podem ser deletados quando esta
sessão encerrar.

### 5. Untracked não-Fase no working tree da main

- `.gitignore` (modificado, exceção pra `Auditoria_Kurier_*.xlsx`)
- `HANDOFF_2026-05-01.md`, `HANDOFF_FASE_3_2026-05-02.md`,
  `HANDOFF_FASE_5_2026-05-03.md`, `RELATORIO-AUDITORIA.md` — docs antigas
- `.coverage` — artefato pytest-cov
- `scripts/auditoria_kurier/` — utilitário separado, sem PR aberto
- `📬 Publicações 6ee4f13a9ea34506824656a261d99dce_all.csv` — export Notion

Decidir destino (commitar, mover, ou .gitignore) em Round futuro.

---

## Documentos relevantes na main

```
docs/anatomia-publicacoes.md            ← baseline 1.617 linhas, pré-Round-4
CHANGELOG_ROUND_1.md                    ← Round 1 (mappings + text pipeline + dedup)
CHANGELOG_ROUND_2.md                    ← Round 2 (schema detection + reset)
HANDOFF_FASE_5_2026-05-03.md            ← handoff anterior pré-Round-1
HANDOFF_FASE_3_2026-05-02.md            ← handoff Fase 3
HANDOFF_2026-05-01.md                   ← handoff Fase 2.1/2.2
HANDOFF_ROUND_4_2026-05-03.md           ← ESTE handoff
```

---

## Próximo round em vista (não iniciado)

O Leonardo enviou um prompt de "investigação anatomia pós-Round-4" e
pediu para descartá-lo no meio da execução. O escopo proposto era:

- **Documento alvo**: `docs/anatomia-publicacoes-pos-round-4.md`
- **Modo**: direto na main, sem branch, sem PR; commits incrementais por seção
- **Validar** cada frente do Round 4/4.5/4.6 contra o acervo real (1.608 canônicas + 544 duplicatas)
- **Detectar regressões** (`<br>` residual, marcadores estruturais, cabeçalhos institucionais)
- **Atualizar** anatomia por cruzamento Tribunal × Comunicação × Documento
- **Calcular** métricas operacionais: cobertura `Tarefa sugerida`, `Alerta contadoria`, auto-Status, volume diário, coexistências, top 10 cruzamentos
- **Comparar** com `docs/anatomia-publicacoes.md` (baseline)
- **Atualizar** backlog P0/P1/P2 do baseline com checkmarks no que foi entregue

**Fontes recomendadas** (já validadas como acessíveis nos rounds
anteriores):

| Fonte | Caminho | Uso |
|---|---|---|
| SQLite | `%APPDATA%\NotionRPADV\leitor_dje.db` (read-only) | Texto íntegro |
| Cache | `%APPDATA%\NotionRPADV\cache.db` (read-only) | Cruzamento com Processos |
| Notion MCP | data source `78070780-8ff2-4532-8f78-9e078967f191` | Estado entregue |
| **CSV** | `%LOCALAPPDATA%\Temp\📬 Publicações 6ee4f13a9ea34506824656a261d99dce_all.csv` | **Atalho do export Notion: tem todas as 1.608 canônicas com props já formatadas. Inspecionar este CSV economiza ~50 chamadas MCP.** |
| Baseline | `docs/anatomia-publicacoes.md` | Comparação |

**Estrutura mínima esperada do documento** (12 seções):
0. Sumário executivo
1. Metodologia
2. Distribuição quantitativa
3. Validação das frentes
4. Regressões
5. Anatomia atualizada
6. Qualidade das propriedades — revisão
7. Métricas operacionais
8. Comparação com investigação anterior
9. Novos achados
10. Backlog priorizado
11. Limitações
12. Conclusões e recomendações

---

## Como continuar a conversa em outro chat

Cole no início do novo chat:

> Estou continuando o projeto Claude-Notion (Leitor DJE). Os Rounds 4,
> 4.5 e 4.6 estão concluídos (ver `HANDOFF_ROUND_4_2026-05-03.md` na
> main). Acervo atual: 1.608 canônicas + 544 duplicatas. Schema do
> Notion finalizado (22 props, sem checkbox). Captura nova rodada com
> pipeline pós-Round-4.
>
> Próximo passo: [descrever o que quer]

O Claude novo lê este handoff e tem contexto suficiente para continuar
sem perda de fio.

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
print('  canonicas:', conn.execute(\"SELECT COUNT(*) FROM publicacoes WHERE notion_page_id IS NOT NULL AND dup_canonical_djen_id IS NULL\").fetchone()[0])
print('  duplicatas:', conn.execute(\"SELECT COUNT(*) FROM publicacoes WHERE dup_canonical_djen_id IS NOT NULL\").fetchone()[0])
print('djen_advogado_state:')
for r in conn.execute('SELECT * FROM djen_advogado_state ORDER BY numero_oab'):
    print(' ', dict(r))
print('app_flags:')
for r in conn.execute('SELECT * FROM app_flags'):
    print(' ', dict(r))
"
```

### Rodar suite completa
```
cd /c/dev/Claude-Notion
python -m pytest tests/ --no-header -q
# esperado: 900 passed, 7 skipped
```

### Rodar apenas tests do Round 4 + 4.5
```
python -m pytest tests/test_round_4.py tests/test_round_4_5.py -v --no-header
# esperado: 50 + 22 = 72 passed
```

### Lint focado
```
python -m ruff check notion_rpadv/services/dje_notion_mappings.py notion_rpadv/services/dje_notion_mapper.py notion_rpadv/services/dje_text_pipeline.py tests/test_round_4.py tests/test_round_4_5.py
# esperado: All checks passed
```

### Inspecionar CSV exportado do Notion
```
python -c "
import csv
from pathlib import Path
csv_path = Path.home() / 'AppData/Local/Temp' / '📬 Publicações 6ee4f13a9ea34506824656a261d99dce_all.csv'
with open(csv_path, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    print('colunas:', reader.fieldnames)
    rows = list(reader)
    print('total linhas:', len(rows))
    print('primeira:', rows[0])
"
```
