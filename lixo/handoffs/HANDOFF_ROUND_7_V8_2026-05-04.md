# Handoff — Leitor DJE × Notion: pós-Rounds 6+7 + smoke v8 (2026-05-04)

Contexto pra retomar o trabalho em outra sessão. Estado real validado
após Rounds 6 e 7 mergeados em `main` (PRs #20 e #21), smoke v8
executado e aprovado.

---

## TL;DR

**Adequação do app à anatomia v8** está **41/43 regras = 95%**
implementada e validada via smoke real. Pendentes apenas as Regras 25
(troca de relator sequencial) e 37 (inatividade prolongada PREVI/RESP)
— ambas exigem refator do pipeline para receber histórico de pubs
anteriores.

**Schema do Notion finalizado** (Tarefa sugerida (app) com 3 valores +
Alerta contadoria (app) com 41 valores). Zero resíduo das regras
antigas (D.01-D.03, E.01/02/04, "Pauta presencial", "Instância
desatualizada" sem qualificador).

**Smoke v8** (96 pubs reais, janela 28/04→04/05) passou nos 4
critérios:
- Camada base 17/17 candidatas corretas
- 18 das 39 regras de monitoramento disparam ≥1 vez
- Zero valores depreciados
- Schema observado bate com canônico v8

**Próximo round em vista** (não iniciado): pode ser Regras 25+37 (com
refator do pipeline), captura completa do histórico, ou trabalho de
outra natureza no app.

---

## Estado atual do projeto

| | |
|---|---|
| Branch atual | `main` |
| Último commit em main | `ed2cfb6 chore(smoke): atualizar referência ao novo nome inspecionar_smoke_v8.py` |
| Suite de testes | **1103 passed, 10 skipped, 0 falhas** |
| Lint (ruff) | limpo nos arquivos de regras v8 e scripts de smoke |
| Working tree | só com untracked pré-existentes (HANDOFFs antigos, .coverage, anatomia-v8.md, CSV exportado, scripts/auditoria_kurier/) — fora de escopo desde Round 4 |

Histórico recente (`git log --oneline -10 main`):
```
ed2cfb6 chore(smoke): atualizar referência ao novo nome inspecionar_smoke_v8.py
dec027c chore(smoke): inspecionar_smoke_round_6.py → inspecionar_smoke_v8.py
badeda7 Merge pull request #21 from leonardoguedesfp/feat/regras-v9-round-7
1bdcf35 feat(round-7f): Regras 1, 32, 33, 34, 36 (CNJ + Tema 955 + datas)
542b480 feat(round-7e): Regras 19-24 (Localização — Cidade, Vara, Turma, Relator)
9a7c135 feat(round-7d): Regras 7, 8, 9, 10 (Cliente e posição)
e0361e1 feat(round-7c): Regras 29, 30, 31, 38 (Estado processual + link)
ddd0589 feat(round-7b): Regras 4, 5, 6, 39 (Classificação processual + processo pai)
ca7914e feat(round-7a): Regras 2, 3, 12, 13 (Tribunal e numerações superiores)
3267b11 Merge pull request #20 from leonardoguedesfp/feat/regras-v9
```

---

## Histórico das fases e rounds (atualizado)

| Round | Data | Escopo principal |
|---|---|---|
| Fases 1–5 + Rounds 1–4 | abr-mai/2026 | Cliente DJEN, dedup, Notion sync, Round 4 (Partes/Classe/Tarefa/Alerta) |
| Round 5 | 03/05 | Fix das regressões P0 do Round 4 (Partes JSON cru + `<br>` falso positivo) — PR mergeado |
| **Round 6** | 03-04/05 | Adequação à v8: schema renomeado para `(app)`, regras antigas removidas, Camada base (40-43) + 12 regras de monitoramento — PR #20 mergeado |
| **Round 7** | 04/05 | 21 regras de monitoramento adicionais (Round 7a-f). 41/43 regras totais — PR #21 mergeado |
| **Smoke v8** | 04/05 | Captura real 96 pubs (5 dias úteis), inspeção `scripts/inspecionar_smoke_v8.py`, todos critérios OK |

---

## Estado das 43 regras v8

**Camada base (4/4)** — `aplicar_camada_base()` em `dje_regras_v8.py`:

| Regra | Combinação | Tarefa | Alerta |
|---|---|---|---|
| 40 | Lista Distribuição (qq doc) ou Intimação+Distribuição | Nada para fazer | Processo/recurso distribuído |
| 41 | Edital ou Intimação + Pauta de Julgamento | Nada para fazer | Incluir julgamento no controle |
| 42 | Intimação + Sentença | Analisar sentença | — |
| 43 | Intimação + Acórdão/Ementa | Analisar acórdão | — |

**Monitoramento (37/39)** — `aplicar_regras_monitoramento()`:

| Round | Regras implementadas |
|---|---|
| 6 | 11 (5 alertas), 14, 15, 16, 17, 18, 26, 27, 28, 35 + Texto imprestável + Processo não cadastrado |
| 7a | 2, 3, 12, 13 |
| 7b | 4, 5, 6, 39 |
| 7c | 29, 30, 31, 38 |
| 7d | 7, 8, 9, 10 |
| 7e | 19, 20, 21, 22, 23, 24 |
| 7f | 1, 32, 33, 34, 36 |

**Pendentes (2)**:

| Regra | Motivo | Esforço estimado |
|---|---|---|
| 25 | Troca de relator detectada por sequência de publicações — exige histórico de pubs anteriores do mesmo processo | M (refator pipeline para receber `cache_pubs_anteriores` opcional) |
| 37 | Inatividade prolongada PREVI/RESP > 12 meses — idem | M (mesmo refator) |

---

## Smoke v8 — resumo da execução (2026-05-04)

Janela: **28/04 → 04/05/2026** (5 dias úteis), 6 OABs ativas.

### Captura
- 6 advogados, 146 pubs únicas no SQLite (após dedup intra-batch)
- 96 canônicas enviadas ao Notion + 50 duplicatas suprimidas
- 48 flushadas no dedup
- 0 falhas, 0 presas (em 239,3s)

### Distribuição por par no Notion (96 pubs)

| Tipo de comunicação | Tipo de documento | Pubs |
|---|---|---:|
| Intimação | Notificação | 58 |
| Intimação | Decisão | 11 |
| Intimação | Acórdão | 4 |
| Intimação | Despacho | 4 |
| Intimação | Outros | 3 |
| Intimação | Certidão | 3 |
| Intimação | Ementa | 3 |
| Intimação | Distribuição | 3 |
| Intimação | Pauta de Julgamento | 2 |
| Intimação | Sentença | 1 |
| Lista de Distribuição | Distribuição | 3 |
| Edital | Pauta de Julgamento | 1 |

### Disparos de monitoramento (top 10)

| Regra | Disparos |
|---|---:|
| Capturar link externo (R38) | 59 |
| Processo não cadastrado | 34 |
| Vara desatualizada (R21+22) | 18 |
| BB ausente em partes adversas (R11) | 11 |
| Turma desatualizada (R23) | 9 |
| Fase cognitiva contradita (R28) | 8 |
| Conferir Tema 955 (R32) | 8 |
| Descida de instância (R15) | 7 |
| Trânsito pendente (R35) | 5 |
| Subida (R14) e STJ/TST (R2) | 4 cada |

**52 pubs com 2+ alertas** (composição funcionando).

### Critérios de sucesso — todos OK ✅

| Critério | Resultado |
|---|---|
| Camada base 100% correta | 17/17 candidatas |
| ≥10 regras de monitoramento ≥1 disparo | 18 regras |
| Zero valores depreciados | confirmado |
| Schema observado bate canônico | 3 tarefas + 20 alertas únicos, todos canônicos |

Relatório completo: `logs/smoke_v8_2026-05-04-1655.md` (gitignorado).

---

## Schema atual da database 📬 Publicações (22 propriedades)

```
Identificação (title)
Advogados intimados (multi-select, 12 OABs)
Advogados não cadastrados (checkbox)
Alerta contadoria (app) (multi-select, 41 valores)
Certidão (formula)
Classe (rich_text)
Cliente (rollup)
Data de disponibilização (date)
Duplicatas suprimidas (rich_text)
Hash (rich_text)
ID DJEN (number)
Link (URL)
Observações (rich_text)
Partes (rich_text)
Processo (relation com ⚖️ Processos)
Status (select: Nova, Nada para fazer, Tratada, Pré-migração)
Tarefa sugerida (app) (multi-select, 3 valores)
Texto (rich_text, max 2000 chars)
Tipo de comunicação (select: Intimação, Lista de Distribuição, Edital)
Tipo de documento (select: 11 valores canônicos)
Tribunal (select, 15 valores)
Órgão (rich_text)
feedback (rich_text — sem signal documentado)
```

### Tarefa sugerida (app) — 3 valores

| Valor | Cor |
|---|---|
| Analisar acórdão | purple |
| Analisar sentença | blue |
| Nada para fazer | default |

### Alerta contadoria (app) — 41 valores

3 mantidos (Processo não cadastrado, Trânsito em julgado pendente,
Texto imprestável) + 38 novos da v8. Lista completa em
`scripts/inspecionar_smoke_v8.py:ALERTAS_CANONICOS`.

---

## Constantes operacionais

`notion_rpadv/services/dje_notion_constants.py`:
```python
NOTION_PUBLICACOES_DATA_SOURCE_ID = "78070780-8ff2-4532-8f78-9e078967f191"
NOTION_PROCESSOS_DATA_SOURCE_ID  = "5e93b734-4043-4c89-a513-5e00a14081bb"
```

`notion_rpadv/services/dje_regras_v8.py`:
```python
TAREFA_ANALISAR_ACORDAO     = "Analisar acórdão"
TAREFA_ANALISAR_SENTENCA    = "Analisar sentença"
TAREFA_NADA_PARA_FAZER      = "Nada para fazer"

# 41 alertas canônicos (3 mantidos + 38 novos v8)
# Vide arquivo completo
```

OABs ativas (6) — `notion_rpadv/services/dje_advogados.py:ADVOGADOS`:
```
15523/DF Ricardo Luiz Rodrigues da Fonseca Passos
36129/DF Leonardo Guedes da Fonseca Passos
48468/DF Vitor Guedes da Fonseca Passos
20120/DF Cecília Maria Lapetina Chiaratto
38809/DF Samantha Lais Soares Mickievicz
75799/DF Deborah Nascimento de Castro
```

---

## Estado do banco SQLite local

**Local**: `%APPDATA%\NotionRPADV\leitor_dje.db`

Após o smoke v8 (em 2026-05-04 16:55):
- `publicacoes`: **146** linhas (96 canônicas + 50 duplicatas)
- `dup_pendentes`: 0 (flush concluído)
- `djen_advogado_state`: 6 cursores em `2026-05-04`
- `app_flags`:
  - `reativacao_4_advogados_2026_05_02_treated = skipped_by_smoke_setup`
  - `notion_primeira_carga_v1 = banco_vazio`

**Cache do Notion** (`%APPDATA%\NotionRPADV\cache.db`): preservado.
- Processos: 1.108 records
- Clientes: 1.072 records
- Catálogo: 68 records
- Tarefas: 33 records

---

## Pendências operacionais (não bloqueantes)

### 1. Regras 25 e 37 deferidas

Exigem refator do pipeline `aplicar_regras_monitoramento` para
receber `cache_pubs_anteriores` opcional. Quando implementadas:
- Regra 25 detecta troca de relator sequenciando pubs do mesmo
  processo por data
- Regra 37 detecta processos PREVI/RESP sem atividade > 12 meses

### 2. Notion 📬 Publicações tem 96 pubs do smoke v8

Após captura do smoke (28/04 → 04/05), 96 pubs canônicas + 50
duplicatas estão no Notion + SQLite. Decisão para próximo round:
- (a) Manter como está e fazer captura incremental do histórico
  (`cursor + 1d` → hoje, mas cursor está em 04/05 — só pegaria
  pubs futuras)
- (b) Apagar pubs Notion + reset SQLite + capturar histórico
  completo (01/01/2026 → 04/05/2026, ~1.608 pubs estimadas)
- (c) Capturar histórico anterior via `setar_cursor_pre_smoke
  --dias-atras N` regredindo até `2025-12-31`

### 3. Branches remotas órfãs

`feat/regras-v9` e `feat/regras-v9-round-7` ficaram após merge.
Podem ser deletadas pelo Leonardo no GitHub.

### 4. Untracked não-Fase no working tree da main

- `.coverage` (artefato pytest-cov)
- `HANDOFF_2026-05-01.md`, `HANDOFF_FASE_3_2026-05-02.md`,
  `HANDOFF_FASE_5_2026-05-03.md`, `HANDOFF_ROUND_4_2026-05-03.md`
- `RELATORIO-AUDITORIA.md`
- `anatomia-processos-vs-publicacoes-v8.md` (doc-base, deve ficar
  fora do repo? ou commitar como referência?)
- `scripts/auditoria_kurier/` (utilitário separado)
- `📬 Publicações 6ee4f13a9ea34506824656a261d99dce_all.csv` (export
  Notion antigo)

Decidir destino em algum round futuro.

---

## Documentos relevantes na main

```
docs/anatomia-publicacoes-pos-round-4.md   ← anatomia pós-Round 4 (1740 linhas)
docs/round-5-fix-regressoes-p0.md          ← Round 5 (debug regressões)
docs/round-6-auditoria.md                  ← Round 6 Passo A
docs/round-6-status.md                     ← Round 6 status pré-smoke
HANDOFF_ROUND_7_V8_2026-05-04.md           ← ESTE handoff
README.md
CHANGELOG_ROUND_1.md, CHANGELOG_ROUND_2.md
```

(Documentos de rounds anteriores: `docs/anatomia-publicacoes.md` na
branch `analise-anatomia-pubs`; HANDOFFs antigos no working tree
untracked.)

---

## Scripts auxiliares na main

`scripts/`:
- `reset_estado_leitor_round_6.py` — trunca SQLite local (publicacoes,
  dup_pendentes, djen_advogado_state, djen_state, app_flags).
  Preserva `cache.db`. Suporta `--dry-run`.
- `setar_cursor_pre_smoke.py` — pré-seta cursor das 6 OABs +
  FLAG_REATIVACAO preventiva. Args: `--dias-atras N` (default 7).
  Usa API pública `dje_state.update_advogado_cursor`.
- `inspecionar_smoke_v8.py` — relatório pós-smoke cruzando SQLite ×
  Notion. Read-only, idempotente. 7 seções, 39 entradas de regras
  cobrindo as 41 regras v8 implementadas. Salva em
  `logs/smoke_v8_<ts>.md`. Args: `--verbose`, `--no-notion`.
- `resync_partes_round_5.py` — script one-shot do Round 5 (Frente A);
  já rodou e atualizou as 530 pubs JSON cru. Mantido para histórico.

---

## Memórias / preferências do Leonardo

(de `~/.claude/projects/C--dev-Claude-Notion/memory/MEMORY.md`)

1. **Trabalhar no main repo, não em worktree** — `cd /c/dev/Claude-Notion`
   direto.
2. **Paleta brand RPADV vence Notion** — chips no app usam brand do
   escritório.
3. **PR + merge pelo GitHub web pelo Leonardo** — Claude faz commit +
   push de branch nova, NÃO faz merge direto em main, salvo exceções
   explícitas.
4. **Push direto na main** quando explicitamente autorizado (Round
   4.5/4.6, scripts auxiliares de smoke).

---

## Como continuar a conversa em outro chat

Cole no início do novo chat:

> Estou continuando o projeto Claude-Notion (Leitor DJE). Os Rounds
> 6 e 7 estão concluídos (PRs #20 e #21 mergeados em main). 41 das
> 43 regras v8 implementadas. Smoke v8 com 96 pubs reais aprovado em
> todos os 4 critérios (vide
> `HANDOFF_ROUND_7_V8_2026-05-04.md` na main).
>
> Estado:
> - Branch main em `ed2cfb6`
> - 1103 testes verdes
> - SQLite com 146 pubs do smoke; cursores em 04/05/2026
> - Notion 📬 Publicações com 96 pubs do smoke
> - Pendências: Regras 25 e 37 (exigem refator do pipeline)
>
> Próximo passo: [descrever o que quer]

O Claude novo lê o handoff + memo do projeto e tem contexto
suficiente pra continuar.

---

## Comandos úteis

### Verificar estado do banco
```python
python -c "
import os, sqlite3
from pathlib import Path
db = Path(os.environ['APPDATA']) / 'NotionRPADV' / 'leitor_dje.db'
conn = sqlite3.connect(str(db))
print('publicacoes:', conn.execute('SELECT COUNT(*) FROM publicacoes').fetchone()[0])
print('canonicas:', conn.execute(\"SELECT COUNT(*) FROM publicacoes WHERE notion_page_id IS NOT NULL AND dup_canonical_djen_id IS NULL\").fetchone()[0])
print('cursores:')
for r in conn.execute('SELECT numero_oab, ultimo_cursor FROM djen_advogado_state'):
    print(f'  {r[0]} → {r[1]}')
"
```

### Rodar suite completa
```
cd /c/dev/Claude-Notion
.venv/Scripts/python.exe -m pytest tests/ --no-header -q
# esperado: 1103 passed, 10 skipped
```

### Rodar testes específicos das regras v8
```
.venv/Scripts/python.exe -m pytest tests/test_round_6_camada_base.py tests/test_round_6_monitoramento.py -v
# esperado: 15 + 204 = 219 passed
```

### Lint focado
```
.venv/Scripts/python.exe -m ruff check notion_rpadv/services/dje_regras_v8.py tests/test_round_6_*.py scripts/inspecionar_smoke_v8.py scripts/setar_cursor_pre_smoke.py scripts/reset_estado_leitor_round_6.py
# esperado: All checks passed!
```

### Smoke v8 completo (sequência operacional)

Pré-requisitos:
- Notion 📬 Publicações vazio (manual via UI)
- Lixeira do Notion vazia (manual via UI)

Sequência:
```bash
# 1. Reset SQLite (zera publicacoes + cursores + flags)
.venv/Scripts/python.exe scripts/reset_estado_leitor_round_6.py

# 2. Pré-setar cursor + flag preventiva (5 dias úteis típicos)
.venv/Scripts/python.exe scripts/setar_cursor_pre_smoke.py --dias-atras 7

# 3. Abrir app: python -m notion_rpadv → Login → "Baixar publicações novas"
#    (Operador faz manualmente — Claude não consegue rodar PySide6)

# 4. Aguardar captura + sync Notion completar

# 5. Inspecionar
.venv/Scripts/python.exe scripts/inspecionar_smoke_v8.py --verbose

# Output: logs/smoke_v8_<timestamp>.md
```

### Inspecionar pubs no Notion via MCP
- Data source `📬 Publicações`: `78070780-8ff2-4532-8f78-9e078967f191`
- Data source `⚖️ Processos`: `5e93b734-4043-4c89-a513-5e00a14081bb`
- Data source `📚 Catálogo de Tarefas`: `79afc833-77e2-4574-98ba-ebed7bd7e66c`

### Token Notion (para scripts diretos)
Lido do keyring (`KEYRING_SERVICE`, `KEYRING_USERNAME` em
`notion_bulk_edit/config.py`). Não há `token.txt`.

```python
import keyring
from notion_bulk_edit.config import KEYRING_SERVICE, KEYRING_USERNAME
tok = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
```

---

## Contexto crítico para o próximo Claude

### Como rodar o app
**Não rodo PySide6 em ambiente headless.** Quando precisar rodar
captura DJE, peço ao Leonardo abrir `python -m notion_rpadv` e
executar manualmente. Eu inspeciono o resultado via SQLite + MCP +
script de inspeção.

### Modal de reativação
Após `reset_estado_leitor_round_6.py`, **a flag
`FLAG_REATIVACAO_2026_05_02` é apagada**. Se o operador abre o app
sem rodar `setar_cursor_pre_smoke.py` primeiro, e os 4 advogados
reativados (Vitor 48468, Cecília 20120, Samantha 38809, Deborah
75799) tiverem cursor não-NULL, o modal "Reativação detectada"
dispara. Se o operador clica "Sim, resetar", os 4 cursores são
zerados — captura puxa desde `2026-01-01`.

**Sempre rodar `setar_cursor_pre_smoke.py` ANTES do app** após reset.
Esse script grava `FLAG_REATIVACAO_2026_05_02 = "skipped_by_smoke_setup"`
preventivamente para evitar o modal.

### Regras 25 e 37 — refator necessário
Para implementar essas duas regras, o pipeline precisa receber
contexto de pubs anteriores do mesmo processo. Opções:
1. Adicionar parâmetro `cache_pubs_anteriores: list[dict] | None` em
   `aplicar_regras_monitoramento` — caller carrega via SQLite.
2. Helpers `_cache_pubs_por_processo` que agrupa via SQL no SQLite e
   passa o sub-conjunto da pub atual.

A v8 doc descreve as regras (Seção IV.6, V.6) — ler antes de
implementar.

### Conteúdo do CSV exportado do Notion
O working tree tem `📬 Publicações 6ee4f13a9ea34506824656a261d99dce_all.csv`
(8.907 linhas — export histórico do Round 4). Útil pra spot-check
em alguns scripts de auditoria (`scripts/inspecionar_smoke_v8.py`
prefere queryar o Notion direto via MCP/REST).

---

## Referência rápida das 43 regras v8

(Resumo — descrição completa em `anatomia-processos-vs-publicacoes-v8.md`)

### I. Identificação e numeração
- 1 ✅ Conferir número CNJ do processo
- 2 ✅ Capturar numeração STJ/TST
- 3 ✅ Capturar numeração STF

### II. Classificação processual
- 4 ✅ Conferir natureza (vs Tribunal)
- 5 ✅ Conferir natureza (vs Classe)
- 6 ✅ Conferir tipo de processo

### III. Partes
- 7 ✅ Vincular cliente ao processo
- 8 ✅ Vincular cliente (litisconsórcio)
- 9 ✅ Conferir vinculação cliente-processo
- 10 ✅ Conferir posição do cliente
- 11 ✅ Partes adversas (5 alertas: BB, PREVI, CASSI, Bradesco Saúde, BB Consórcios)

### IV. Localização processual
- 12 ✅ Tribunal fora do vocabulário
- 13 ✅ Conferir tribunal de origem
- 14 ✅ Subida de instância
- 15 ✅ Descida de instância
- 16 ✅ Acórdão em 1º grau
- 17 ✅ Sentença em colegiado
- 18 ✅ Pauta em 1º grau
- 19 ✅ Cidade desatualizada (faltando)
- 20 ✅ Cidade desatualizada (divergente)
- 21 ✅ Vara desatualizada (faltando)
- 22 ✅ Vara desatualizada (divergente)
- 23 ✅ Turma desatualizada
- 24 ✅ Relator desatualizado (faltando)
- 25 ⏸ Troca de relator (sequencial — pendente)

### V. Estado processual
- 26 ✅ Fase executiva confirmada por classe
- 27 ✅ Fase liquidação confirmada por classe
- 28 ✅ Fase cognitiva contradita por classe avançada
- 29 ✅ Conferir sentença em fase pós-cognitiva
- 30 ✅ Pauta em processo arquivado
- 31 ✅ Atividade em processo arquivado
- 32 ✅ Conferir Tema 955 (sobrestamento)
- 33 ✅ Capturar data de distribuição
- 34 ✅ Conferir data de distribuição (≥30 dias antes)
- 35 ✅ Trânsito cognitivo pendente
- 36 ✅ Atividade pós-encerramento executivo
- 37 ⏸ Inatividade prolongada PREVI/RESP (sequencial — pendente)

### VI. Outros
- 38 ✅ Capturar link externo
- 39 ✅ Recurso autônomo sem processo pai

### VII. Camada base
- 40 ✅ Distribuição (Lista qualquer | Intimação Distribuição)
- 41 ✅ Pauta de Julgamento (Edital | Intimação)
- 42 ✅ Sentença (Intimação)
- 43 ✅ Acórdão/Ementa (Intimação)

### Alertas técnicos/operacionais (sem número)
- ✅ Texto imprestável (qualidade do conteúdo DJEN)
- ✅ Processo não cadastrado (refinado: não dispara em distribuição)

**Total: 41/43 regras numeradas + Camada base 4/4 + 2 alertas
técnicos = 47 disparadores ativos.**
