# Round 2 — detecção dinâmica de schema + reset SQLite (2026-05-03)

Preparação imediata para Round 3 (re-migração massiva). 2 tarefas na
mesma branch:

1. **Tarefa 1** — Substituir o opt-in manual da Fase 5/Round 1 por
   detecção automática de capabilities do schema Notion no startup.
2. **Tarefa 2** — Reset transacional do SQLite local pra deixar o
   banco "do zero" (0 publicações + cursores NULL → próxima janela
   natural `[01/01/2026, hoje]`).

## Tarefa 1 — Detecção dinâmica de schema

### O que mudou

| Antes (Round 1) | Depois (Round 2) |
|---|---|
| `flush_atualizacoes_canonicas(... schema_tem_duplicatas_suprimidas=False)` (default opt-in) | `sincronizar_pendentes(... schema_tem_duplicatas_suprimidas=None)` (default auto-detect) |
| Caller precisava lembrar de passar `True` | Sync detecta no startup e propaga pro flush |
| Sem caching | 1 fetch por sessão (cacheado em memória via `NotionSchemaCapabilities`) |

### Novo módulo

[notion_rpadv/services/dje_notion_schema.py](notion_rpadv/services/dje_notion_schema.py):

- `NotionSchemaCapabilities` (frozen dataclass): `has_duplicatas_suprimidas` + `raw_property_names`.
- `from_notion(client, ds_id)`: 1 fetch via `GET /v1/data_sources/{id}`. Em qualquer erro (auth, rate limit, API genérica, response malformado, exceção inesperada) → `legacy_fallback()` + warning. NÃO levanta — não derruba o sync.
- `legacy_fallback()`: estado-zero (`has_duplicatas_suprimidas=False`).

### Wire em `sincronizar_pendentes`

Precedência da resolução do flag:

1. `schema_caps` explícito (`NotionSchemaCapabilities` pré-detectada) → usa
2. `schema_tem_duplicatas_suprimidas=True/False` → respeita override do caller
3. `schema_tem_duplicatas_suprimidas=None` (default) → auto-detect

App pode detectar uma vez no startup e passar via `schema_caps` em todas as syncs (caminho otimizado), OU deixar o sync detectar a cada run (caminho default, custo: 1 chamada extra ao Notion por execução).

### Smoke real contra Notion

`test_R2_smoke_real_notion_has_duplicatas_suprimidas` confirma `has_duplicatas_suprimidas=True` na database 📬 Publicações de produção (data source `78070780-8ff2-4532-8f78-9e078967f191`). Skip automático em máquinas sem o token Notion no keyring.

**21 propriedades detectadas** no Notion real (Round 2 pré-requisito atendido):

```
Advogados intimados, Advogados não cadastrados, Certidão, Classe,
Cliente, Data de disponibilização, Duplicatas suprimidas, Hash,
ID DJEN, Identificação, Link, Observações, Partes, Processo,
Processo não cadastrado, Status, Texto, Tipo de comunicação,
Tipo de documento, Tribunal, Órgão
```

### Cobertura

16 testes em [tests/test_round_2_schema_detection.py](tests/test_round_2_schema_detection.py):

- 3 detecção positiva/negativa (presente, ausente, frozenset stability)
- 5 fallback gracioso (auth, rate limit, API generic, exception inesperada, response malformado)
- 1 legacy_fallback estável
- 6 wire no sync (auto-detect chama API, propaga flag pro flush, force True/False skip detect, schema_caps skip detect, falha API não derruba)
- 1 smoke real contra Notion

## Tarefa 2 — Reset SQLite

### Backups criados

```
C:\Users\LeonardoGuedesdaFons\AppData\Roaming\NotionRPADV\
  leitor_dje.db.backup-round2-20260503-171743    (45.7 MB)

C:\Users\...\Reclamações Trabalhistas\Ferramentas\Leitor DJE\
  Historico_DJEN_completo.xlsx.backup-round2-20260503-171743    (3.3 MB)
```

### D-A reinterpretado (Opção A)

O prompt sugeria literalmente `UPDATE ... data_ultima_consulta = '2026-01-01'`, mas a convenção do código (`compute_advogado_window` em [dje_state.py:204-229](notion_rpadv/services/dje_state.py:204)) é `janela = [cursor + 1d, hoje]`. Cursor literal `2026-01-01` resultaria em janela `[02/01/2026, hoje]` — perderia 01/01/2026.

**Aplicado**: `reset_advogado_cursores(...)` da API oficial → cursores NULL → `DEFAULT_CURSOR_VAZIO=2025-12-31` → janela natural `[01/01/2026, hoje]` em todas as 6 OABs ativas. Confirma o intent semântico de "capturar desde 01/01/2026 inclusive".

### Reset transacional

Executado em uma única `BEGIN/COMMIT`:

| Operação | Linhas afetadas |
|---|---|
| `DELETE FROM publicacoes` | 2141 |
| `DELETE FROM dup_pendentes` | 0 |
| `DELETE FROM djen_state` (legacy singleton) | 0 |
| `DELETE FROM app_flags WHERE key='notion_primeira_carga_v1'` | 1 |
| `DELETE FROM app_flags WHERE key='reativacao_4_advogados_2026_05_02_treated'` | 1 |
| `reset_advogado_cursores` (6 OABs ativas → NULL) | 6 |
| `VACUUM` (fora da transação) | — |

#### app_flags removidas

- `notion_primeira_carga_v1` = `tudo_agora` (Fase 5 — escolha do modal de primeira carga, sem sentido após reset)
- `reativacao_4_advogados_2026_05_02_treated` = `reset_no` (Fase 4 — modal de reativação dos 4, sem sentido após reset)

#### app_flags preservadas

Nenhuma. Após o reset, `app_flags` está vazia. Quando o app rodar novamente, o modal de primeira carga Notion vai reaparecer (esperado, parte do Round 3).

### Migrations Round 1 aplicadas

O banco real ainda estava no schema pré-Round-1 (não tinha `dup_pendentes`, nem colunas `dup_chave` / `dup_canonical_djen_id`). Antes do reset, `init_db()` rodou as migrations idempotentes:

- Tabela `dup_pendentes` criada
- Colunas `dup_chave`, `dup_canonical_djen_id` adicionadas em `publicacoes`
- Índice parcial `idx_publicacoes_dup_chave` criado

Verificado: schema pós-migration tem `dup_pendentes` + 15 colunas em `publicacoes` (10 originais + 3 Notion + 2 dedup).

### Estado pós-reset

```
publicacoes:    0
dup_pendentes:  0
djen_state:     0 (legacy)
app_flags:      []
djen_advogado_state: 6 OABs ativas, todas cursor=NULL last_run=NULL

Janela natural pós-reset = [2026-01-01, hoje]
DB size: 45,707,264 → 61,440 bytes (99.87% redução via VACUUM)
```

### OABs desativadas

Conforme conversa pré-implementação: as 6 OABs desativadas
(`65089/DF`, `81225/DF`, `37654/DF`, `39857/DF`, `84703/DF`, `79658/DF`)
**não têm linha** em `djen_advogado_state` e isso foi mantido.
Se uma delas for reativada no futuro, o app cria a linha do zero.
Mantém a essência de D-C ("todas as OABs em 01/01/2026"): as ativas
estão em `cursor=NULL` (= 01/01/2026 efetivo); as desativadas não
existem na tabela e quando voltarem terão o mesmo comportamento.

## Smoke pós-reset

Executado programaticamente (não envolve UI Qt):

- ✓ Imports do app carregam sem erro
- ✓ SQLite no estado esperado
- ✓ Janela natural `[2026-01-01, 2026-05-03]` para todas as OABs ativas
- ✓ `NotionSchemaCapabilities.from_notion(real_client, ...)` retorna `has_duplicatas_suprimidas=True` com 21 properties

**Smoke manual recomendado** antes do Round 3:

1. Abrir o app (`python -m notion_rpadv`)
2. Confirmar que sobe sem erro
3. Tela Leitor DJE mostra 0 publicações
4. Configurações OAB mostram janela `01/01/2026 → hoje` para as 6 ativas
5. Sair sem capturar nada

## Suite e lint

- **828 passed, 7 skipped, 0 failing** (era 812 baseline Round 1; +16 testes do Round 2)
- `ruff check` limpo nos 3 arquivos novos/modificados

## Não-escopo

- Não rodou captura DJEN (Round 3)
- Não enviou nada ao Notion (Round 3)
- Não mexeu no schema do Notion (já feito antes deste round)
- Excel histórico atual NÃO foi apagado — fica como backup; app sobrescreve quando rodar Round 3
