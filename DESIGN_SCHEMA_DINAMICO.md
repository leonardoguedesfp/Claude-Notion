# DESIGN — Schema dinâmico no Notion RPADV

- **Data:** 2026-04-27
- **Versão:** 0.1 (proposta para revisão — antes de qualquer linha de implementação)
- **Autor:** Claude Code CLI (sessão de spike, ~1h)
- **Baseline considerado:** branch `main`, commit `0c5a562` (145 passed, 2 skipped)
- **Worktree:** `claude/mystifying-ptolemy-70dda2`
- **Arquivos de produção tocados nesta sessão:** zero. Apenas este `DESIGN_SCHEMA_DINAMICO.md`.

---

## Sumário

- [Descobertas durante a investigação](#descobertas-durante-a-investigação)
- [1. Visão geral](#1-visão-geral)
- [2. Descoberta de schema (boot-time fetch)](#2-descoberta-de-schema-boot-time-fetch)
- [3. Cache de schemas](#3-cache-de-schemas)
- [4. Substituição do `notion_bulk_edit/schemas.py`](#4-substituição-do-notion_bulk_editschemaspy)
- [5. Encoders e validação](#5-encoders-e-validação)
- [6. UI: tabela com colunas dinâmicas](#6-ui-tabela-com-colunas-dinâmicas)
- [7. Importação de planilhas com schema dinâmico](#7-importação-de-planilhas-com-schema-dinâmico)
- [8. Plano de migração (passo a passo)](#8-plano-de-migração-passo-a-passo)
- [9. Riscos, trade-offs, perguntas em aberto](#9-riscos-trade-offs-perguntas-em-aberto)
- [Recomendação final](#recomendação-final)

---

## Descobertas durante a investigação

Coisas do código atual que afetam o desenho e que não estavam óbvias no briefing:

1. **DATA_SOURCES já é hardcoded em [`notion_bulk_edit/config.py:25-35`](notion_bulk_edit/config.py)** — quatro UUIDs em variáveis de ambiente com fallback. Já é "configuração", não "código". O caminho mais barato é manter este formato para a lista de bases conhecidas e adicionar uma quinta entrada `Documentos` quando o usuário decidir incluir. **A 5ª base (Documentos `0142efd6-…`) NÃO está em DATA_SOURCES hoje** — toda a infraestrutura (sync, model, page) literalmente desconhece a existência dela.

2. **`NotionClient` já tem `query_database` apontando para `/v1/data_sources/{id}/query` (linha 185).** Versão da API é `2025-09-03`. Por simetria, o endpoint para ler o schema é `GET /v1/data_sources/{id}` — **mas esse método NÃO existe no cliente ainda**. Vai precisar ser adicionado (`get_data_source(id) -> dict`).

3. **`audit.db` já existe e tem helpers `_set_meta`/`_get_meta`** ([`cache/db.py:187-200`](notion_rpadv/cache/db.py)). O Round C deixou prontinha a separação cache/audit, com migração idempotente flagada por `meta[audit_migrated_v1]`. **A tabela `meta_schemas` cabe nesse arquivo sem sangria adicional** — mesma `init_audit_db` é o ponto de extensão natural.

4. **`PropSpec` é `frozen=True`** ([`schemas.py:23`](notion_bulk_edit/schemas.py)) — imutável. No mundo dinâmico continua imutável; o que muda é quem o constrói (parser do JSON em vez de literal Python).

5. **`_TITLE_KEY_BY_BASE` está hardcoded em `base_table_model.py:16-21`** — usado para resolver relations. **Catalogo NÃO está nesse dict** (bug latente: a função `_looks_like_template_row` recebe `title_key=""` e nunca encontra o "🟧 Modelo —" do catálogo). No mundo dinâmico, o título de cada base vem do schema (`spec.tipo == "title"`).

6. **`_NON_EDITABLE_TIPOS` em `delegates.py:25-36`** já cobre `rollup`, `formula`, `relation`, `created_time`, `last_edited_time`, `created_by`, `last_edited_by`, `files`. Faltam tipos modernos do Notion: **`status`, `button`, `unique_id`, `verification`** — todos vão aparecer quando o schema dinâmico ler o Notion real, e o app vai precisar de uma resposta default ("readonly + sem editor + chip cinza").

7. **Em-dash em opções está confirmado nos dados reais (briefing)** — "Indenização — I", "Indenização — IR", etc. JSON UTF-8 + SQLite text preservam U+2014 sem ginástica. Nenhuma camada do app faz `.replace('—', '-')`.

8. **Tarefas tem `status` hardcoded como select com 4 opções no schema atual** (`STATUS_TAREFA = ("A fazer", "Em andamento", "Aguardando", "Concluída")`). **Mas o schema real do Notion diz que Tarefas NÃO tem campo Status** (briefing: "Tarefa 'feita' é inferida por Data de protocolo preenchida"). Esse é o BUG-OP-08 estendido para Tarefas — outra divergência inventada-vs-real que o schema dinâmico mata de raiz.

9. **`SCHEMAS` é importado em 12 arquivos de produção + 5 de teste** (mapeado via grep). A migração não pode ser big-bang — precisa de adapter que mantém a API pública (`get_prop`, `colunas_visiveis`, `is_nao_editavel`, `vocabulario`, `SCHEMAS`) e troca a fonte por baixo. Caso contrário o blast radius é o app inteiro.

10. **`_open_filter_menu` itera `SCHEMAS.get(self._base, {}).items()` literalmente** ([`base_table_page.py:906`](notion_rpadv/pages/base_table_page.py)) e usa `spec.opcoes` para construir checkboxes. Como `opcoes` é uma tupla de strings, e o schema dinâmico vai parsear opções do Notion (que vêm como `[{"id":..., "name":..., "color":...}]`), precisamos garantir que `PropSpec.opcoes` continue sendo uma `tuple[str, ...]` — ou refatorar todos os call-sites.

11. **`gerar_template.py` usa `spec.notion_name` como header da planilha** e cria coluna `_vocabularios` por opção. Funciona idêntico no mundo dinâmico se `PropSpec.notion_name` continuar igual.

12. **`config.py` define `NOTION_USERS` com IDs reais + 2 IDs placeholder ("MARIANA_NOTION_ID", "CARLA_NOTION_ID")**. Não é parte deste design, mas o método `client.list_users()` já existe — pode ser reaproveitado para popular esse mapa dinamicamente no futuro. Fora de escopo aqui.

13. **`tests/test_critical_bugs.py` e `tests/test_audit_smoke.py` instanciam `PropSpec` literalmente** dentro dos testes. Quando o schema dinâmico chegar, esses testes podem continuar usando `PropSpec(...)` direto (a dataclass continua existindo) — só o conjunto `SCHEMAS` global é que muda de "literal" para "carregado".

---

## 1. Visão geral

**Problema.** O `notion_bulk_edit/schemas.py` foi escrito por suposição: 4 schemas hardcoded com `notion_name`, `tipo` e `opcoes` que nunca foram confrontados contra o que o Notion realmente expõe. Isso produziu:
- BUG-OP-08 (Catálogo: 4 propriedades inventadas, dado vazio em runtime).
- D2 do smoke test (Processos: "Valor da causa" não existe — o real é "Valor da Causa" no schema atual mas a base não tem essa coluna).
- BUG silencioso em Tarefas (`status` hardcoded mas inexistente no Notion).
- Tarefas com `Cliente`/`Tribunal` declarados como rollup quando são na verdade rollups que o app já lê via `decode_value`, ok — mas qualquer mudança da Déborah ou do Ricardo no Notion (renomear coluna, adicionar opção a um select) precisa de um deploy do app.

Caminho A (corrigir cada divergência) só posterga o problema. Caminho B troca a fonte de verdade.

**Solução.** O app deixa de carregar schemas literais e passa a:
1. **Descobrir** as bases via lista configurada (DATA_SOURCES + extras de Configurações).
2. **Buscar** o schema de cada base no Notion (`GET /v1/data_sources/{id}`) no boot e cachear em `audit.db.meta_schemas`.
3. **Servir** `PropSpec` em runtime a partir do JSON cacheado, mantendo a API pública (`get_prop`, `colunas_visiveis`, etc.) intacta.
4. **Permitir** ao usuário escolher quais colunas ficam visíveis (preferência por usuário, persistida em `audit.db.meta_user_columns`).
5. **Refresh** manual em Configurações ("Recarregar schemas"), automático em condições específicas (sync que retornar 401/404 da API de schema).

**O que muda para o usuário.**
- Catálogo deixa de mostrar 4 colunas vazias inventadas; passa a mostrar `Nome / Categoria / Prazo / Observações / Tarefas` que existem no Notion.
- Processos deixa de tentar editar "Valor da causa"; mostra `Tribunal`, `Instância`, `Status`, `Fase`, `Tipo de ação` (multi-select com 21 opções), `Partes adversas`, `Sobrestado - IRR 20`, etc. — a base inteira (33 propriedades).
- Por padrão: as 5–8 colunas mais importantes ficam visíveis (heurística: `title` + selects + datas; multi-selects e textos longos ficam ocultos).
- O usuário pode acionar um picker "Configurar colunas" no canto superior direito da tabela e marcar/desmarcar quais aparecem. Estado persistido por usuário.
- Documentos passa a ser navegável (5ª aba na sidebar, opcional). Veja seção 9 para a pergunta "aba ou só relation?".

**O que muda para manutenção.**
- Schema do Notion vira fonte de verdade. Renomear uma coluna no Notion → próximo refresh do schema atualiza o app sem deploy.
- Adicionar opção a um select no Notion (ex: novo Tribunal) → aparece no app no próximo refresh.
- Vocabulários hardcoded (`TRIBUNAIS`, `FASES`, etc.) somem de `schemas.py`.
- Cores por valor (`_COR_TRIBUNAL`, etc.) ficam em arquivo separado (`colors.py`) ou viram preferência de usuário, com fallback para cor neutra. O design original do Notion já carrega cores no schema (`color: "blue" | "purple" | …`), então podemos parsear e usar como default.
- Adicionar uma nova base no escritório → entrada nova em DATA_SOURCES (ou pela UI de Configurações), restart do app, schema é descoberto. Sem deploy.

---

## 2. Descoberta de schema (boot-time fetch)

### 2.1 Quando

- **Primeiro boot pós-instalação:** descobre todos os schemas das bases em DATA_SOURCES (e extras configurados). Bloqueia a UI atrás de uma splash "Descobrindo bases…" — boot é pelo menos `4 × 1 chamada API ≈ 1.5s` com rate limit. Aceitável.
- **Boots subsequentes:** lê do cache (`meta_schemas`). Não bloqueia. Em background dispara um refresh "leve" que só reage se a versão (hash) mudou.
- **Sob demanda:** botão "Recarregar schemas" em Configurações (próximo aos 4 botões de sync existentes) força refresh imediato.
- **Recovery:** se uma sync ou um save retornar **erro de propriedade desconhecida** (Notion responde 400 com `validation_error` quando o nome da propriedade não existe), o app dispara refresh automático do schema daquela base e re-tenta uma vez. Se ainda falhar, escala via toast/Logs.

### 2.2 Como

A API Notion v2025-09-03 expõe um objeto **Data Source** (o equivalente moderno ao Database). O endpoint `GET /v1/data_sources/{data_source_id}` (presumido — ver pergunta em aberto 9.4) retorna algo na forma:

```json
{
  "object": "data_source",
  "id": "5e93b734-...",
  "title": [{"plain_text": "Processos", ...}],
  "properties": {
    "Tribunal": {
      "id": "abc",
      "type": "select",
      "select": {
        "options": [
          {"id": "...", "name": "TRT/2",   "color": "blue"},
          {"id": "...", "name": "TRT/10",  "color": "blue"},
          {"id": "...", "name": "TJDFT",   "color": "purple"}
        ]
      }
    },
    "Número do processo": {"id": "title", "type": "title", "title": {}},
    "Tipo de ação":      {"id": "...",   "type": "multi_select", "multi_select": {"options": [...]}},
    "Data de distribuição": {"id": "...", "type": "date", "date": {}},
    "Clientes":         {"id": "...",   "type": "relation", "relation": {"data_source_id": "939e5dcf-...", "type": "single_property", ...}}
  }
}
```

**Ação concreta no código:**
- Adicionar `NotionClient.get_data_source(data_source_id: str) -> dict` em [`notion_bulk_edit/notion_api.py`](notion_bulk_edit/notion_api.py). Implementação: `return self._request("GET", f"/data_sources/{data_source_id}")`. Usa o mesmo throttle, mesmas exceções tipadas. Custo de implementação: ~10 linhas. **Antes de mergear, validar empiricamente** com curl/script que a rota existe nessa versão da API — se não existir, fallback é `GET /v1/databases/{id}` (alias retro-compat).

### 2.3 Quais bases

Três fontes em ordem:
1. **DATA_SOURCES (config.py)** — fonte primária. Hoje: 4 entradas. Adicionar 5ª `Documentos` se o usuário decidir.
2. **Extras configurados pelo usuário em Configurações** (futuro — Fase 4): `audit.db.meta_user_bases` — `(label, data_source_id, ordem)`.
3. **Bases descobertas via `POST /v1/search`** (futuro — Fase 4 opcional): retorna lista de databases acessíveis ao token. UI: "Adicionar base do meu workspace" → lista as opções → usuário escolhe nome + se quer aba na sidebar.

**MVP (Fases 0-3)**: usa apenas DATA_SOURCES. Adicionar `Documentos` direto no dict é trivial.

### 2.4 Configuração inicial

Ver **ADR-01** abaixo. Decisão recomendada: **DATA_SOURCES continua sendo a fonte de verdade no MVP**. Não há UI de "cadastrar bases" na Fase 0–3. Se o usuário quer adicionar uma base, edita `config.py` (ou variável de ambiente). UI vem na Fase 4 se houver demanda real.

### 2.5 Frequência de refresh

| Gatilho | Comportamento |
|---|---|
| Boot, cache vazio | Bloqueante. Splash "Descobrindo bases (1/4…)…". |
| Boot, cache existe | Não bloqueante. Usa cache. Background fetch silencioso, atualiza se hash mudou (toast: "Schema de Processos atualizado"). |
| "Recarregar schemas" em Configurações | Bloqueante (modal "Recarregando…"). Atualiza os 4-5 schemas. Toast resumo. |
| Save falha com erro de propriedade desconhecida | Refresh do schema daquela base, retry 1×. Se ainda falhar, abre o Logs page filtrado nos saves falhos. |
| Auto-refresh por idade do cache | **Sim, com TTL longo (24h).** Schema do Notion é estável; o usuário não vai adicionar/renomear coluna toda hora. Se preocupa: o fluxo de retry no save já cobre a maior parte dos drift. |

### ADR-01: estratégia de descoberta de bases

**Contexto.** O app precisa saber quais bases existem para descobrir o schema de cada uma. Quatro opções consideradas:

| Opção | Prós | Contras |
|---|---|---|
| **(A) Lista hardcoded em config.py** (status quo, 4 bases) | Zero UI. Determinístico. Já existe. | Adicionar base = editar código. |
| **(B) Lista em config.py + UI "Adicionar"** | Flexível. UI no Configurações. | Trabalho UI extra. Estado em audit.db. |
| **(C) Detecção automática via `POST /v1/search`** | Zero config. Reflete o workspace inteiro. | Pode trazer 30+ bases que não interessam. Token precisa permissão de search. |
| **(D) Wizard de primeira execução** | UX bonita. | Trabalho grande. UX para uso recorrente é pior. |

**Decisão.** **(A) no MVP, (B) na Fase 4 se houver demanda.** DATA_SOURCES já é "config externalizada via env vars". Adicionar a 5ª base (Documentos) é uma linha. UI complexa (B/D) e detecção mágica (C) são overkill para um escritório de 17 usuários com 4-5 bases conhecidas.

**Consequências.**
- Trabalho de descoberta vira pequeno: itera sobre `DATA_SOURCES.items()` e chama `client.get_data_source(id)`.
- Adicionar Documentos: PR de 1 linha em config.py + entrada no menu lateral.
- Se a Déborah/Ricardo um dia quiser adicionar uma 6ª base por conta própria, gera um pedido de Fase 4. Aceitável.

---

## 3. Cache de schemas

### 3.1 Onde

**Em `audit.db`** — não em `cache.db`. Justificativas:

1. **`cache.db` é descartável.** O Round C separou os arquivos justamente para "apagar cache para forçar re-sync" não destruir audit. Se schemas viverem em `cache.db`, qualquer apagão de cache obriga refresh remoto na primeira ação do usuário (4-5 chamadas API extras em sequência). Mais lento e mais frágil.
2. **Schema é metadata estrutural,** mesma natureza dos shortcuts do usuário e do edit log: persistente, não regenerado por sync.
3. **`audit.db` já tem `_init_meta` + helpers `_get_meta`/`_set_meta`** — extensão natural.

### 3.2 Tabelas SQL

```sql
-- Em audit.db, criada em init_audit_db()

CREATE TABLE IF NOT EXISTS meta_schemas (
    data_source_id TEXT PRIMARY KEY,
    base_label     TEXT NOT NULL,        -- 'Processos', 'Clientes', 'Documentos', etc.
    title_property TEXT,                 -- 'Número do processo' (notion_name do tipo title)
    schema_json    TEXT NOT NULL,        -- JSON serializado — ver §3.3
    schema_hash    TEXT NOT NULL,        -- SHA-256 hex do schema_json (para detectar mudanças)
    fetched_at     REAL NOT NULL,        -- UNIX timestamp do último fetch
    api_version    TEXT NOT NULL DEFAULT '2025-09-03',  -- versão da API quando foi capturado
    cache_version  INTEGER NOT NULL DEFAULT 1            -- bumpa quando MUDARMOS o formato do JSON
);

-- Visibilidade de colunas por usuário e por base. Ver §6.3.
CREATE TABLE IF NOT EXISTS meta_user_columns (
    user_id        TEXT NOT NULL,
    data_source_id TEXT NOT NULL,
    visible_keys   TEXT NOT NULL,   -- JSON array com chaves visíveis NA ORDEM desejada
    updated_at     REAL NOT NULL,
    PRIMARY KEY (user_id, data_source_id)
);
```

`schema_hash` permite o boot incremental detectar mudanças sem reparsear o JSON inteiro. `cache_version` é a versão do **formato do nosso JSON** (não do schema do Notion) — bumpamos quando, por exemplo, decidirmos passar a serializar `cor_por_valor` ou `min_width_px` no JSON (hoje vivem no PropSpec hardcoded — ver §3.3).

### 3.3 Estrutura do `schema_json`

Camada intermediária (não 1:1 com a API do Notion). Razões:
- Notion API responde com muito ruído irrelevante para o app (IDs internos de cada opção, configurações de relation que o app não usa).
- O `PropSpec` atual carrega metadados do app que a API não dá: `label` em português, `largura_col`, `mono`, `formato`, `cor_por_valor`, `min_width_px`. Esses precisam ter um lar.

**Formato proposto** (string JSON, um por base):

```json
{
  "data_source_id": "5e93b734-4043-4c89-a513-5e00a14081bb",
  "base_label": "Processos",
  "title_property": "Número do processo",
  "title_key": "cnj",
  "properties": {
    "cnj": {
      "notion_name": "Número do processo",
      "tipo": "title",
      "label": "CNJ",
      "editavel": true,
      "obrigatorio": true,
      "opcoes": [],
      "default_visible": true,
      "default_order": 1,
      "label_pt": null,
      "format_hint": null,
      "min_width_px": 200,
      "mono": true
    },
    "tribunal": {
      "notion_name": "Tribunal",
      "tipo": "select",
      "label": "Tribunal",
      "editavel": true,
      "obrigatorio": false,
      "opcoes": [
        {"name": "TJDFT",  "color": "purple"},
        {"name": "TRT/2",  "color": "blue"},
        {"name": "TRT/10", "color": "blue"}
      ],
      "default_visible": true,
      "default_order": 2
    },
    "tipo_acao": {
      "notion_name": "Tipo de ação",
      "tipo": "multi_select",
      "label": "Tipo de ação",
      "editavel": true,
      "opcoes": [
        {"name": "Indenização — I",  "color": "default"},
        {"name": "Indenização — IR", "color": "default"},
        {"name": "Indenização — RI", "color": "default"},
        {"name": "Indenização — R",  "color": "default"},
        {"name": "Redução Salarial — HE",  "color": "yellow"},
        {"name": "Redução Salarial — PCS", "color": "yellow"},
        ...
      ],
      "default_visible": false,
      "default_order": 11
    }
  }
}
```

**Distinções de design:**

- **`opcoes` deixa de ser `tuple[str]` e vira `list[{name, color}]`.** Isso quebra a API atual de `vocabulario(base, key) -> tuple[str, ...]`. Solução: `vocabulario()` continua retornando `tuple[str, ...]` (extrai os names); para acesso à cor introduzir `vocabulario_full(base, key) -> tuple[OptionSpec, ...]`. Migração transparente para todos os call-sites.
- **`label`** começa igual a `notion_name` (português do Notion). Se quisermos um label custom em pt-BR, podemos sobrescrever em arquivo `notion_rpadv/labels_overrides.py` (mapa `(data_source_id, key) -> label_custom`). Fora de escopo do MVP.
- **`label_pt`** é o slot pra esse override custom. `null` no Notion → cai pro `notion_name`.
- **`default_visible`** vem de heurística no parser: title sempre `true`; selects e dates `true`; relations `true` (até 2); multi-selects e rich_text longos `false`. Pode ser sobrescrito pelo usuário (ver §6).
- **`default_order`** = ordem na resposta da API, com title forçado em 1.
- **`min_width_px` / `mono`** são overrides nossos (não vêm da API). Podem viver em `labels_overrides.py` e serem mergeados no parser. Fora do MVP — começa tudo None/false e deixa o `_resize_columns_to_header` calcular.
- **Cores por valor** vêm do Notion (`color: "blue"`). Mapa `notion_color → hex` vive em `notion_rpadv/theme/notion_colors.py` (8 cores: blue, purple, red, orange, yellow, green, gray, brown, pink, default). Substitui os mapas `_COR_TRIBUNAL` etc. de `schemas.py`. Trabalho de 30min.

### 3.4 Versionamento e detecção de drift

Ao fazer refresh:
```python
def refresh_schema(data_source_id, client, audit_conn):
    raw = client.get_data_source(data_source_id)
    parsed = parse_to_schema_json(raw)            # estrutura §3.3
    new_json = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    new_hash = hashlib.sha256(new_json.encode("utf-8")).hexdigest()
    
    existing = get_cached_schema(audit_conn, data_source_id)
    if existing is None:
        upsert_schema(audit_conn, data_source_id, parsed, new_hash)
        return ChangeReport(kind="initial", base=parsed["base_label"])
    
    if existing["schema_hash"] == new_hash:
        return ChangeReport(kind="unchanged", base=parsed["base_label"])
    
    diff = compute_diff(existing["properties"], parsed["properties"])
    upsert_schema(audit_conn, data_source_id, parsed, new_hash)
    return ChangeReport(kind="changed", base=parsed["base_label"], diff=diff)
```

`compute_diff` produz três listas: `added_props`, `removed_props`, `changed_props` (com sub-categoria: tipo mudou, opções de select mudaram, label mudou). Resultado vai pra **toast** ("Schema de Processos atualizado: 1 nova coluna 'X', 1 opção adicionada em 'Tribunal'") e pro **edit_log** (entrada especial `kind="schema_change"` se quisermos compliance).

**Migração de dados local.** Se uma propriedade some do Notion mas há registros no `cache.db.records[*].data_json` com essa chave: **manter** a chave por 1 versão (next refresh), avisar via toast, dropar na seguinte. Implementação simples: parser ignora chaves desconhecidas, `delete_record` natural via sync. Prática equivalente do que já acontece quando uma página é arquivada.

### ADR-02: serialização do schema (1:1 da API vs camada própria)

**Contexto.** O JSON do Notion tem ~5x mais campos do que precisamos. Se serializarmos 1:1 ganhamos fidelidade mas (a) o JSON fica grande, (b) o app fica acoplado à forma exata da API.

**Decisão.** **Camada própria** (`schema_json` na forma de §3.3). Razões:
1. Trabalho do parser é isolado em uma função (`parse_to_schema_json`). Se o Notion mudar o shape em uma versão futura da API, só ela quebra — não o app inteiro.
2. Carregamos overrides (label_pt, mono, min_width_px) na mesma estrutura, sem precisar de tabela paralela.
3. JSON menor, `data_json` mais legível em dump SQL.

**Consequência.** Precisamos manter o parser. ~80 linhas. Coberto por testes unitários em [`tests/test_schema_parser.py`](tests/) (a criar).

---

## 4. Substituição do `notion_bulk_edit/schemas.py`

### 4.1 Estratégia: adapter, não rewrite

`schemas.py` **continua existindo** mas vira fino: apenas (a) define o `PropSpec` dataclass, (b) implementa as quatro funções públicas como leitura do cache em memória.

**API pública preservada (mesma assinatura):**

```python
# schemas.py — refatorado

@dataclass(frozen=True)
class PropSpec:
    notion_name: str
    tipo: str
    label: str
    editavel: bool = True
    obrigatorio: bool = False
    opcoes: tuple[str, ...] = ()
    largura_col: str = "10%"
    mono: bool = False
    formato: str = ""
    cor_por_valor: dict[str, str] = field(default_factory=dict)
    target_base: str = ""
    min_width_px: Optional[int] = None

# NOVA classe pública para opções com cor
@dataclass(frozen=True)
class OptionSpec:
    name: str
    color: str = "default"

def get_prop(base: str, key: str) -> Optional[PropSpec]:
    return _registry().get_prop(base, key)

def is_nao_editavel(base: str, key: str) -> bool:
    return _registry().is_nao_editavel(base, key)

def colunas_visiveis(base: str, user_id: str | None = None) -> list[str]:
    """user_id None → defaults do schema; user_id presente → preferências do usuário."""
    return _registry().colunas_visiveis(base, user_id)

def vocabulario(base: str, key: str) -> tuple[str, ...]:
    return _registry().vocabulario(base, key)

# NOVA — para chips coloridos
def vocabulario_full(base: str, key: str) -> tuple[OptionSpec, ...]:
    return _registry().vocabulario_full(base, key)

# NOVO — substituto de SCHEMAS para call-sites que precisam iterar
def schema_for_base(base: str) -> dict[str, PropSpec]:
    return _registry().schema_for_base(base)

# Compat shim — SCHEMAS continua funcionando como mapa-em-tempo-real
class _SchemaProxy:
    def __getitem__(self, key): return _registry().schema_for_base(key)
    def get(self, key, default=None):
        try: return _registry().schema_for_base(key)
        except KeyError: return default if default is not None else {}
    def keys(self): return _registry().bases()
    def items(self): return [(b, _registry().schema_for_base(b)) for b in _registry().bases()]
    def __contains__(self, key): return key in _registry().bases()

SCHEMAS: _SchemaProxy = _SchemaProxy()
```

`_registry()` retorna a instância singleton de `SchemaRegistry` (em módulo separado `notion_bulk_edit/schema_registry.py`):

```python
class SchemaRegistry:
    """Lazy-loaded em memória; cache em audit.db."""
    
    def __init__(self, audit_conn): ...
    def load_all_from_cache(self): ...                       # boot
    def refresh_from_api(self, base, client): ...            # boot ou Configurações
    def schema_for_base(self, base) -> dict[str, PropSpec]: ...
    def get_prop(self, base, key) -> Optional[PropSpec]: ...
    def is_nao_editavel(self, base, key) -> bool: ...
    def colunas_visiveis(self, base, user_id=None) -> list[str]: ...
    def vocabulario(self, base, key) -> tuple[str, ...]: ...
    def vocabulario_full(self, base, key) -> tuple[OptionSpec, ...]: ...
    def bases(self) -> list[str]: ...
```

Inicialização: feita em `MainWindow.__init__` (após `self._audit_conn = ...`) chamando `init_schema_registry(self._audit_conn)`. Em `app.py:160`, antes de `_build_ui()`, adicionar:

```python
from notion_bulk_edit.schema_registry import init_schema_registry
init_schema_registry(self._audit_conn)
# Boot-time refresh se cache vazio (bloqueante com splash); ver §2
```

### 4.2 `is_nao_editavel(base, key)` — sem mudança de assinatura

Hoje em `schemas.py:457`:
```python
def is_nao_editavel(base: str, key: str) -> bool:
    spec = get_prop(base, key)
    if spec is None:
        return True
    if not spec.editavel:
        return True
    if spec.tipo in ("rollup", "formula", "created_time", "last_edited_time"):
        return True
    return False
```

Continua igual. A lista de tipos não-editáveis cresce: passa a incluir `rollup, formula, created_time, last_edited_time, status, button, unique_id, verification, last_edited_by, created_by, files`. **Mas:** `status` é potencialmente editável (no Notion moderno é); aceitar como readonly por enquanto e introduzir editor depois se houver demanda.

### 4.3 PropSpec construção em runtime

`SchemaRegistry.load_all_from_cache()` chama o parser para cada `meta_schemas` row e produz `dict[base_label, dict[key, PropSpec]]` em memória. A construção é eager (uma vez no boot) — overhead total estimado: 5 bases × 30 props × 0.05ms = 7.5ms. Desprezível.

Se quisermos ser preguiçosos (lazy load por base), `schema_for_base(base)` faz parse on-demand e cacheia. Não é necessário no MVP.

### 4.4 Mapeamento de impacto — arquivos que importam `schemas`

Mapeado via grep:

| Arquivo | O que usa | Impacto |
|---|---|---|
| [`notion_bulk_edit/gerar_template.py:11`](notion_bulk_edit/gerar_template.py) | `SCHEMAS, PropSpec` | **Zero mudanças.** `SCHEMAS[base].items()` continua funcionando via proxy. |
| [`notion_bulk_edit/main.py:22`](notion_bulk_edit/main.py) (CLI legado) | `SCHEMAS, PropSpec` | Zero mudanças. CLI lê o mesmo cache. **Atenção:** se o CLI rodar antes do app abrir uma vez, o cache estará vazio. Adicionar wrapper que chama `init_schema_registry` + boot fetch antes do main. |
| [`notion_bulk_edit/validators.py:13`](notion_bulk_edit/validators.py) | `SCHEMAS, PropSpec, vocabulario` | Zero. |
| [`notion_rpadv/app.py:697`](notion_rpadv/app.py) | `get_prop` | Zero. **Mas:** precisa adicionar `init_schema_registry(audit_conn)` no `__init__`. |
| [`notion_rpadv/cache/sync.py:13`](notion_rpadv/cache/sync.py) | `SCHEMAS` | Zero. `_sync()` itera `schema.items()`, decode_value continua. |
| [`notion_rpadv/models/base_table_model.py:11`](notion_rpadv/models/base_table_model.py) | `PropSpec, colunas_visiveis, get_prop, is_nao_editavel` | **Pequena**: passar `user_id` para `colunas_visiveis()`. Atualizar `_TITLE_KEY_BY_BASE` para olhar dinamicamente o `title_key` do schema (substituir por função `_title_key_for_base(base) -> str`). |
| [`notion_rpadv/models/delegates.py:20`](notion_rpadv/models/delegates.py) | `PropSpec, get_prop` | Zero. Adicionar branch defensivo em `createEditor()` para tipos novos: retornar None + flag readonly. |
| [`notion_rpadv/pages/base_table_page.py:25,704,770,785,794,806`](notion_rpadv/pages/base_table_page.py) | `SCHEMAS, get_prop, colunas_visiveis` | Zero (todas continuam funcionando via proxy). |
| [`notion_rpadv/pages/clientes.py:8`](notion_rpadv/pages/clientes.py) | `colunas_visiveis` | Zero. |
| [`notion_rpadv/pages/processos.py:8`](notion_rpadv/pages/processos.py) | `colunas_visiveis` | Zero. |
| [`notion_rpadv/pages/importar.py:746`](notion_rpadv/pages/importar.py) | `SCHEMAS` | Zero. |
| [`notion_rpadv/services/notion_facade.py:11`](notion_rpadv/services/notion_facade.py) | `get_prop` | Zero. |
| [`build.py`](build.py) | (verificar) | Provavelmente PyInstaller manifest — ver se inclui `schemas.py` em data files. Provavelmente não importa. |

**Tests (5 arquivos):**

| Arquivo | Uso | Impacto |
|---|---|---|
| `tests/test_audit_smoke.py:1364, 1394` | `SCHEMAS` | Zero — leitura via proxy. |
| `tests/test_critical_bugs.py:94..220` | `SCHEMAS, is_nao_editavel` | Zero. **Mas:** se algum teste assume schema hardcoded com chaves específicas (`cnj`, `tribunal`), precisa de fixture que popule o cache de schema antes. Ver §8 fase 1. |
| `tests/test_exec_bugs.py:210, 223, 233` | `PropSpec` | Zero — instanciam `PropSpec(...)` literal. |
| `tests/test_v2_bugs.py:252, 261` | `PropSpec` | Zero. |
| `tests/test_v2_visual_bugs.py:149, 475, 504, 642` | `PropSpec, colunas_visiveis, get_prop` | Pequeno: testes que dependem de `colunas_visiveis("Processos") == [...]` precisam fixar o cache de schema antes. **Solução:** fixture `dynamic_schema_fixture()` em `conftest.py` que popula `meta_schemas` com snapshot dos schemas reais (committed em `tests/fixtures/schemas/*.json`). |

**Conclusão:** o trabalho real está em (1) construir o registry, (2) mexer em `_TITLE_KEY_BY_BASE` em `base_table_model.py`, (3) atualizar 1-2 fixtures de teste. Tudo o resto continua "funcionando" via shim de retro-compat.

---

## 5. Encoders e validação

### 5.1 `encode_value(value, tipo)` — sem nova assinatura

`encoders.py:262` continua `encode_value(value, tipo, extra=None)`. Não precisa do nome da propriedade — encoders só dependem do tipo Notion. Mesma vibe atual.

**O que NÃO precisa mudar:** branches por tipo. Os 17 tipos atuais continuam idênticos. **Adicionar branches** para `status`, `unique_id`, `button`, `verification`, `created_by`, `last_edited_by` retornando `{}` (igual ao readonly handling) — ver §5.4.

### 5.2 Validação de select contra opções dinâmicas

`validators.py:209-218`:
```python
case "select":
    opcoes = vocabulario(base, campo)
    if opcoes and str(valor).strip() not in opcoes:
        erros.append(...)
```

`vocabulario()` continua retornando tuple de strings — agora vinda do cache dinâmico. **Funcionamento idêntico.** Diferença visível: a tupla cresce (Tribunal vai de 8 → 17 opções) ou encolhe quando o Notion muda. Sem ginástica.

**Caso novo: opção que não existe no cache mas o usuário tenta usar.** Cenário real: a Déborah adicionou "TRT/3" no Notion ontem, o app não fez refresh ainda, ela tenta importar uma planilha com "TRT/3". Atualmente: validação rejeita. Decisão proposta:

- **Não criar opção automaticamente via API.** Risco alto: typos viram opções reais ("TRT/3 " com espaço, "trt/3" minúsculo). Notion não permite criar opção via API durante PATCH de page de qualquer forma (precisa de PATCH no schema da database, endpoint separado, mais complexo).
- **Bloquear com mensagem específica:** "Valor 'TRT/3' não está nas opções de Tribunal. Atualize o schema (Configurações → Recarregar schemas) ou verifique a digitação."
- **Sugerir refresh:** se a validação falha 1× para um valor específico, primeiro tenta refresh do schema daquela base. Se a opção apareceu, aceita. Se não, bloqueia. Custo: 1 chamada extra de API por save com erro de validação. Aceitável.

### 5.3 Em-dash em opções

JSON UTF-8 + SQLite TEXT (`PRAGMA encoding = 'UTF-8'` no SQLite atual via WAL) preservam U+2014 transparente. Validação `str(valor).strip() not in opcoes` compara strings Python — caractere literal. Sem normalização Unicode (NFC vs NFD) necessária se ambos lados vêm do Notion API (API é canônica NFC). **Cuidado:** se algum usuário copiar-e-colar de um PDF que tem dash em NFD, vira mismatch silencioso. Mitigação: aplicar `unicodedata.normalize("NFC", v)` em `vocabulario()` e na comparação. ~3 linhas.

### 5.4 Tipos novos não cobertos

Tipos que a API Notion expõe mas o app não conhece hoje: `status`, `files`, `button`, `verification`, `unique_id`, `last_edited_by`, `created_by`, `formula`-com-rich_text, `rollup`-com-people.

Estratégia padrão para qualquer tipo desconhecido pelo schema dinâmico:

| Camada | Comportamento |
|---|---|
| `decode_value` | Retorna `None`. Já é o `case _:` default. **Nenhuma mudança.** |
| `encode_value` | Retorna `{}`. Adicionar `case "status" \| "files" \| "button" \| "verification" \| "unique_id" \| "last_edited_by" \| "created_by": return {}` — explicita o readonly. |
| `is_nao_editavel` | Adicionar lista de tipos novos junto aos 4 atuais. Resultado: célula não recebe editor. |
| `delegates.PropDelegate.createEditor` | Já retorna None se `spec.tipo in _NON_EDITABLE_TIPOS`. Adicionar tipos novos ao `_NON_EDITABLE_TIPOS`. |
| `data() DisplayRole` | Para `status` e `unique_id`, mostrar `str(raw)` ou "—" se None. Para `files`, mostrar contagem ("3 arquivos"). Para `button`, "—" e tooltip "tipo button (não suportado)". |
| Painter de chip | Não pintar chip para tipos não cobertos. Texto plano. |

**Status especial:** futuramente vale virar editor próprio (Notion Status é select+grupos). Por ora, readonly chega no MVP.

### 5.5 Validação dinâmica para multi_select

Idêntico ao select: `vocabulario(base, key)` retorna tuple, validador checa `if v not in opcoes`. Já é o que `validators.py:222-235` faz hoje. Zero mudança.

---

## 6. UI: tabela com colunas dinâmicas

A seção mais importante. Resumo: `BaseTableModel._cols` deixa de ser fixo no `__init__` e passa a ser **(a) ordem default do schema do Notion + (b) preferências de visibilidade do usuário**.

### 6.1 `BaseTableModel._cols` — fonte e atualização

Hoje:
```python
self._cols: list[str] = colunas_visiveis(base)   # base_table_model.py:185
```

Depois:
```python
self._user_id: str = user_id        # passado pelo BaseTablePage
self._cols: list[str] = colunas_visiveis(base, user_id=user_id)
```

`colunas_visiveis(base, user_id)` consulta primeiro `meta_user_columns(user_id, data_source_id)`. Se existe → retorna `visible_keys` na ordem armazenada. Se não existe → retorna keys do schema cujo `default_visible=True`, na ordem de `default_order`.

**Sinal:** `SchemaRegistry.user_columns_changed(user_id, base)` emitido quando o usuário muda a configuração. Cada `BaseTablePage` ouve e re-monta `self._cols` + `model.beginResetModel/endResetModel`.

### 6.2 Ordem de colunas

- **Default:** ordem que o Notion devolve em `properties` (insertion order do dict). Title sempre primeiro (forçado pelo parser).
- **Customizada pelo usuário:** se `meta_user_columns.visible_keys` existe, usa essa ordem (drag-and-drop salva nessa lista).

### 6.3 Visibilidade vs ocultação

Modelo idêntico ao Notion web:
- "Mostrar/Esconder coluna" — toggle visível em menu contextual no header (clique direito) e no picker.
- Coluna escondida não some do schema; some apenas da view atual desse usuário.
- Persistência por `(user_id, data_source_id)` — não global.

**Onde guarda:** `audit.db.meta_user_columns`. Por usuário. Por base. Compartilhar entre 17 usuários é uma decisão de Produto que **vai virar pergunta em aberto** (§9.1).

### 6.4 Criar/Renomear/Deletar coluna direto do app

**FORA DE ESCOPO no MVP.** Razões:
1. Requer endpoint `PATCH /v1/databases/{id}` (modifica o schema). Mais sensível: mudar uma coluna no Notion afeta todos os 17 usuários da Déborah simultaneamente.
2. UI de definição de tipo (select com opções, etc.) é trabalho substancial.
3. Boundary natural: o app é "leitor + editor de dados". Schema management fica no Notion web (como hoje).

Quando virar prioridade, vira Fase 5+.

### 6.5 Picker de colunas — UI sugerida

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Processos                                       1108 registros           │
│                              [ Pesquisar… ] [Filtros ▾] | [Sync] [+Novo] │
│                                                              [⋮ Colunas] │
├──────────────────────────────────────────────────────────────────────────┤
│ CNJ          │ Tribunal │ Status │ Fase │ Distribuição │ Cliente princ. │
│ 0001234-...  │ TJDFT    │ Ativo  │ ...  │ ...          │ ...            │
```

`[⋮ Colunas]` é um QPushButton ghost no canto direito do toolbar. Abre QMenu:

```
┌─────────────────────────────────┐
│ Visíveis (5)                    │
│ ☑ CNJ                            │
│ ☑ Tribunal                       │
│ ☑ Status                         │
│ ☑ Fase                           │
│ ☑ Distribuição                   │
│ ─────────────────────────────── │
│ Ocultas (28)                     │
│ ☐ Instância                      │
│ ☐ Tipo de ação                   │
│ ☐ Vara                           │
│ ☐ Cidade                         │
│ ☐ Detalhamento                   │
│ ☐ Sobrestado - IRR 20            │
│ ☐ Sobrestado - TJ conexa         │
│ ☐ Tema 955 — Sobrestado          │
│ … (20 mais)                      │
│ ─────────────────────────────── │
│ Reordenar visíveis: arraste no  │
│ cabeçalho da tabela              │
│ ─────────────────────────────── │
│ [ Restaurar padrão ]             │
└─────────────────────────────────┘
```

- Toggle do checkbox = mostra/esconde a coluna; persiste imediatamente.
- "Restaurar padrão" = `DELETE FROM meta_user_columns WHERE user_id=? AND data_source_id=?`. Próximo reload usa defaults do schema.
- Reordenar = drag-and-drop no header da tabela (Qt: `QHeaderView.setSectionsMovable(True)`); ao soltar, salva nova ordem em `meta_user_columns.visible_keys`.

**Header context menu** (clique direito no header):
```
┌────────────────────────────┐
│ Esconder coluna 'Tribunal' │
│ ────────────────────────── │
│ Filtrar por…               │
│ Ordenar A-Z                │
│ Ordenar Z-A                │
└────────────────────────────┘
```

### 6.6 Migração das telas atuais

Hoje as 4 páginas são quase iguais — `ProcessosPage`, `ClientesPage`, `TarefasPage`, `CatalogoPage` herdam de `BaseTablePage` e só passam `base="..."` no super (e `ProcessosPage` instala um `CnjDelegate` extra para a coluna CNJ).

No mundo dinâmico:
- **`BaseTablePage` continua sendo a unidade.** Recebe `base` (label) + `data_source_id`.
- **Subclasses ficam ainda mais finas.** ProcessosPage continua existindo só pra instalar o CnjDelegate.
- **Adicionar Documentos:** criar `DocumentosPage(BaseTablePage)` (3 linhas) + adicionar `_PAGE_DOCUMENTOS = "documentos"` em app.py + nav_documentos no command palette + 5ª entrada no `_NAV_COMMANDS` e no menu lateral.
- **Não vale a pena ir 100% dinâmico** (eliminar as subclasses) no MVP — o ganho é nulo (4 classes de 3 linhas) e perde-se o ponto de extensão para delegates específicos.

### ADR-02 (UI): hardcode de "estas 4 bases" vs full dinâmico

**Contexto.** Hoje há vários hardcodes de "as 4 bases":
- `_NAV_COMMANDS` em [`app.py:89-98`](notion_rpadv/app.py)
- `_PAGE_PROCESSOS` etc. constantes
- Tuplas de instanciação `((_PAGE_PROCESSOS, ProcessosPage), ...)` em `_build_pages()`
- `_TITLE_KEY_BY_BASE` em `base_table_model.py`
- Sidebar provavelmente também

Tornar tudo isso 100% dinâmico = sidebar + command palette construídos de `SchemaRegistry.bases()`. Trabalho médio.

**Decisão.** **Tornar dinâmico só o suficiente para Documentos.** Manter constantes e hardcodes para as 4 bases existentes. Adicionar 5ª (`_PAGE_DOCUMENTOS`, `DocumentosPage`) explicitamente. Razões:
1. Atalho `Ctrl+1..4` já está mapeado em `app.py:89-98` (`nav_processos` etc.). Tornar a sidebar 100% dinâmica obrigaria reatribuir `Ctrl+5..N` automaticamente — UX duvidosa, surpresa pra quem decorou.
2. A 5ª base (Documentos) é o único caso real de extensão hoje. Bases 6+ são teóricas.
3. "Configurar bases pelo usuário" (ADR-01 opção B) não está no MVP. Sem usuário-adiciona, não há benefício de full dinâmico.

**Consequência.** Quando vier 6ª base, repetir o exercício de adicionar `_PAGE_X = ...` + página subclass + nav. Aceitável até virar problema real.

---

## 7. Importação de planilhas com schema dinâmico

`pages/importar.py` e `notion_bulk_edit/gerar_template.py` usam `SCHEMAS[base]` direto.

### 7.1 "Gerar Template"

Continua funcionando via shim — `SCHEMAS[base]` retorna o dict atual de `PropSpec` em runtime. Diferenças visíveis:
- Headers da planilha vão refletir os nomes reais do Notion (ex: "Número do processo" em vez de algum apelido).
- Campos que o app não suporta editar (rollup, formula, status, etc.) entram como readonly cinza com `_COR_READONLY_BG` (já é o comportamento de `gerar_template.py:113-166`).
- Todas as 33 colunas de Processos ficam no template (sub-conjunto = trabalho de Fase 4 se quisermos um template "essencial").

### 7.2 Validação na pré-visualização

`validar_linha(base, row)` em `validators.py` — funciona igual. Lê `SCHEMAS.get(base)`, itera. Validações são por `spec.tipo`.

### 7.3 Refresh forçado antes da importação

**Decisão proposta:** ao entrar em "Importar Planilha", o wizard mostra um banner "Schema cacheado em DD/MM HH:MM. [Atualizar agora]". Se o usuário clica → refresh do schema dessa base + continua o wizard. Se ignora → segue com cache.

Adicionalmente, **antes de processar cada linha** se `validar_linha` retorna erro de "Valor X não está em opções" para um select, **disparar refresh automático** daquele schema e re-validar a linha 1 vez. Cobre o caso "adicionei opção nova no Notion 5min atrás, importei planilha que usa, app aceita".

### 7.4 Caso edge: importação em base que ganhou propriedade nova

Cenário: Notion tem propriedade nova `Vara` que o cache não conhece. Planilha tem coluna `Vara` preenchida. Hoje: `_do_import` faz `for prop_key, spec in schema.items()` e ignora colunas da planilha que não estão no schema — silencioso.

**Decisão:** mensagem mais clara. Após o refresh forçado, se ainda há colunas na planilha que não existem no schema → mostrar warning "5 colunas da planilha foram ignoradas: 'X', 'Y', 'Z'…". Trabalho pequeno, vai junto com BUG-OP-10.

---

## 8. Plano de migração (passo a passo)

Strangler fig pattern. Cada fase mergeia em `main` separadamente. Em qualquer fase a app continua 100% funcional.

### Fase 0 — Infra do schema dinâmico (só backend)

**Escopo.**
- Adicionar `NotionClient.get_data_source(id)` em `notion_api.py`.
- Adicionar tabela `meta_schemas` em `audit.db` (extensão de `init_audit_db`).
- Implementar parser `parse_to_schema_json(raw_notion_response) -> dict`.
- Implementar `SchemaRegistry` com `load_all_from_cache`, `refresh_from_api`, `get_prop`, etc.
- Função `init_schema_registry(audit_conn) -> SchemaRegistry`.
- Função `boot_refresh_all(client, registry) -> list[ChangeReport]` (helper de boot).

**Não toca em.** UI, modelos, páginas, schemas.py legado. Tudo continua funcionando via `SCHEMAS` hardcoded.

**Testes (criar):**
- `tests/test_schema_parser.py`: snapshots dos 4 (5) schemas reais em `tests/fixtures/schemas/*.json` → testa que parser produz estrutura correta.
- `tests/test_schema_registry.py`: load do cache, refresh, diff detection.
- `tests/test_notion_api_get_data_source.py`: smoke test com mock que verifica URL correta.
- Empíricos: rodar `python -c "from notion_bulk_edit.notion_api import NotionClient; ..."` contra a API real (com token do usuário) e validar 1× que `get_data_source` funciona com cada um dos 5 IDs reais. **Salvar a resposta como fixtures.**

**Estimativa:** 3-4 horas.

### Fase 1 — Adapter shim em `schemas.py`

**Escopo.**
- Refatorar `schemas.py` mantendo `PropSpec`. Adicionar `OptionSpec`. As 4 funções públicas (`get_prop`, `is_nao_editavel`, `colunas_visiveis`, `vocabulario`) viram métodos do registry (já existem em Fase 0); a função-namespace de schemas.py vira fina.
- `SCHEMAS` vira `_SchemaProxy` — leitura via registry.
- **Manter o conteúdo hardcoded como fallback** se o registry estiver vazio. Uma flag `USE_DYNAMIC_SCHEMA: bool = False` em `config.py` controla. Default `False` na Fase 1 — registry coexiste com o legacy mas não é usado.
- Em `MainWindow.__init__`, chamar `init_schema_registry(audit_conn)` e (se `USE_DYNAMIC_SCHEMA`) `boot_refresh_all`.

**Testes:**
- Existentes (145 passed) precisam continuar verdes — fixture global de teste seta `USE_DYNAMIC_SCHEMA=False`, código rodando legado.
- Novo: `tests/test_schema_legacy_compat.py` — verifica que com `USE_DYNAMIC_SCHEMA=True` + registry populado por fixture, `SCHEMAS["Processos"]["cnj"]` retorna o `PropSpec` esperado.

**Estimativa:** 2-3 horas.

### Fase 2 — Migrar uma base por vez

Começar pelo **Catálogo**: menor (5 props), mais danificado pelo BUG-OP-08, baixíssimo risco. Sequência:

1. Refresh real do Catálogo via `client.get_data_source("79afc833-...")`.
2. Inspecionar JSON. Validar que parser produz o schema esperado (5 propriedades reais, sem as 4 inventadas).
3. Adicionar flag por-base: `DYNAMIC_BASES: set[str] = {"Catalogo"}` em `config.py`.
4. `SCHEMAS["Catalogo"]` retorna do registry; outras 3 bases continuam hardcoded.
5. **Smoke manual:** abrir app → Catálogo → ver 5 colunas, sem `area`/`tempo_estimado`/`responsavel_padrao`/`revisado` (que não existem). Editar uma célula, salvar, conferir no Notion.
6. Validar que cenário **D1 do smoke** passa.
7. Cache local de `cache.db.records` ainda tem chaves `area`, etc. (legado). **Decisão:** essas chaves ficam órfãs no JSON mas não aparecem na UI (o model só usa as chaves do `cols`). Próxima sync após o fix gera novos records sem essas chaves. **Não migrar dado existente** — ele se atualiza naturalmente.
8. Mergear.
9. Repetir para Tarefas → Clientes → Processos. Por base. Cada uma é PR separado.

**Testes:** 
- Para cada base migrada, fixture específica `tests/fixtures/schemas/catalogo.json` (etc.) usada nos testes que dependem daquela base.
- Os testes de bug crítico (test_critical_bugs.py) que assumem schema hardcoded de Processos podem usar fixture até Processos ser migrada.

**Estimativa:** 1-1.5 horas por base × 4 bases = 4-6 horas total. Cada PR é pequeno e independente.

### Fase 3 — Deprecar SCHEMAS hardcoded

**Escopo.**
- Remover o conteúdo literal de `SCHEMAS` em `schemas.py`. Vocabulários e mapas de cor saem.
- Manter só a `PropSpec` dataclass + as funções públicas + `_SchemaProxy`.
- Remover flags `USE_DYNAMIC_SCHEMA` e `DYNAMIC_BASES` — assumido sempre on.
- Adicionar `notion_rpadv/theme/notion_colors.py` com mapa de cores `notion_color → hex`.
- Atualizar fixtures de teste para fixar schemas via cache pré-populado.

**Testes:** todos verdes. Bugs latentes que viam apareceram nos testes da Fase 2 — devem estar resolvidos.

**Estimativa:** 1-2 horas.

### Fase 4 — Picker de colunas + persistência por usuário

**Escopo.**
- Tabela `meta_user_columns`.
- Botão "⋮ Colunas" no toolbar de `BaseTablePage`.
- Menu contextual no header (esconder coluna, ordenar).
- `QHeaderView.setSectionsMovable(True)` + persistência da nova ordem.
- Sinal `user_columns_changed` no registry; `BaseTableModel.reload()` em resposta.
- Migração: usuário sem entrada usa defaults.

**Testes:**
- `tests/test_user_columns.py`: salva preferência → reload → ordem preservada.
- Smoke manual: 2 usuários no app, cada um com colunas diferentes em Processos. Trocar de usuário, ver layout próprio.

**Estimativa:** 4-6 horas (UI + persistência + testes).

### Fase 4b — Documentos (5ª base)

Pode rodar paralelo à Fase 4.

**Escopo.**
- Adicionar `"Documentos": "0142efd6-..."` em `DATA_SOURCES`.
- Criar `DocumentosPage(BaseTablePage)`.
- Adicionar entrada `_PAGE_DOCUMENTOS` em `app.py`, nav_documentos no command palette, atalho `Ctrl+5`.
- Adicionar item na sidebar.
- Smoke: abrir app, navegar pra Documentos, ver lista do Notion real.

**Estimativa:** 1-2 horas.

### Fase 5 (opcional, futuro) — UI de "Adicionar base"

Só se a Déborah/Ricardo um dia pedir. Trabalho de 4-6h.

---

### Total estimado

| Fase | Horas |
|---|---|
| 0 — Infra | 3-4 |
| 1 — Shim | 2-3 |
| 2 — Catálogo + Tarefas + Clientes + Processos | 4-6 |
| 3 — Cleanup | 1-2 |
| 4 — Picker | 4-6 |
| 4b — Documentos | 1-2 |
| **Total para MVP completo** | **15-23h** |
| Fase 5 (opcional) | +4-6h |

Dividido em ~6-7 PRs, cada um mergeável independentemente. Saída funcional após **Fase 2 do Catálogo** (resolve BUG-OP-08 sozinho) — o resto é incremental.

---

## 9. Riscos, trade-offs, perguntas em aberto

### 9.1 Riscos identificados

| Risco | Mitigação |
|---|---|
| **Schema do Notion muda entre fetch do schema e edit subsequente.** Usuária edita coluna que foi renomeada/removida. | Save retorna 400 com `validation_error`. Hook em `_on_commit_finished`: se erro inclui "property does not exist" → refresh schema da base + retry 1×. Se ainda falhar, modal "A coluna 'X' foi renomeada/removida no Notion. Edição preservada localmente até confirmação." Dirty cell continua amarela. |
| **Endpoint `GET /v1/data_sources/{id}` não existe ou tem nome diferente nesta versão da API.** | **Antes da Fase 0 começar:** validar empiricamente. Se não existir, fallback para `GET /v1/databases/{id}` com mapeamento de retorno. Adicionar este check como passo 0 do plano. |
| **Tipos não suportados aparecem nas bases reais** (`status`, `files`, etc.) e quebram a UI. | Padrão default: readonly + sem editor + render como `str(raw)` ou "—". Coberto pelo `_NON_EDITABLE_TIPOS` ampliado. **Adicionar 5 testes** — um por tipo novo confirmando que célula não trava o app. |
| **Performance do schema fetch no boot.** | 5 bases × 1 chamada = 5 × ~330ms (rate limit 3 RPS) = ~1.7s. Boot cold = aceitável. Boot warm (cache) = 0ms. **Não bloquear** o splash além de 3s — se demorar, abrir app com cache (ou hardcoded fallback temporário) e refresh em background. |
| **Token sem permissão de leitura em uma base nova.** Usuário adicionou Documentos no DATA_SOURCES mas o token não foi compartilhado com a integração. | `client.get_data_source(id)` retorna 404 ou 403. `SchemaRegistry.refresh_from_api` captura, marca a base como `unavailable: true` na meta_schemas. UI: aba aparece como "Documentos (sem acesso)" com tooltip "Compartilhe a base com a integração no Notion para liberar". |
| **Migração de cache existente.** `cache.db.records[Catalogo]` tem chaves `area`, `tempo_estimado` etc. inventadas. | Não migrar. Próxima sync após Fase 2 do Catálogo gera records sem essas chaves. Chaves antigas ficam no JSON, mas o model só usa `_cols` que vem do schema novo — nunca aparecem. Em ~2 syncs, os registros antigos foram todos sobrescritos. **Opcional:** script one-shot `scripts/clean_orphan_keys.py` que remove. Não recomendo — natural decay é suficiente. |
| **Em-dash em opções dá mismatch silencioso** entre planilha de import e cache (NFD vs NFC). | `unicodedata.normalize("NFC", v)` em `vocabulario()` e na comparação do validator. ~3 linhas. Já incluído em §5.3. |
| **Retro-compat com CLI (`notion_bulk_edit/main.py`).** O CLI roda fora do Qt, não tem `MainWindow.__init__` que inicializa o registry. | `notion_bulk_edit/__init__.py` ou um `init_registry_for_cli()` chamado no início do `main.py` que faz `init_schema_registry(get_audit_conn())` + `boot_refresh_all` se cache vazio. Idempotente. |
| **Tests que dependem de `colunas_visiveis("Processos") == [...]` específico.** | Fixture `dynamic_schema_fixture()` em `conftest.py` que popula `meta_schemas` com snapshot dos 4-5 schemas reais (capturados na Fase 0). Tests que precisam de schema usam essa fixture. |
| **Race condition: usuário troca preferência de colunas durante uma sync.** | `meta_user_columns` é tabela separada. Sync mexe em `records`. Sem conflito. `BaseTableModel.reload(preserve_dirty=True)` (já existe via BUG-OP-06) não limpa cols — só rows. Safe. |

### 9.2 Trade-offs deliberados

- **Escolhi uma camada intermediária no JSON serializado** (não 1:1 da API). Trade-off: mais código (parser) mas mais resilencia a mudança da API + suporte a overrides locais. Detalhado em ADR-02.
- **MVP NÃO faz UI de "configurar bases".** Assume DATA_SOURCES é configurável via env vars. Trade-off: fricção para o caso raro (5+ bases personalizadas) em troca de menos código. Detalhado em ADR-01.
- **Schema fetch é eager no boot, não lazy.** 1.7s de boot frio para evitar a complexidade de "qual aba pode abrir antes do registry estar pronto". Aceitável.
- **Não migro `cache.db` orfão.** Decay natural via re-sync. Trade-off: 1-2 syncs de "convivência" com chaves órfãs no JSON. Sem visual impact.
- **Tipos novos viram readonly sem editor.** Não tento implementar editor de Status/Files/etc. agora. Trade-off: usuário não edita esses tipos no app — tem que ir no Notion web. Se for prioridade, vira tarefa separada.

### 9.3 Perguntas que preciso o Leonardo decidir antes da implementação

Em ordem de impacto no design:

1. **Documentos vira aba na sidebar (5ª base, igual às outras 4) ou fica acessível só via relation?**  
   Recomendo: **aba na sidebar**. Custo é 1-2h, e dá ao usuário visão direta do que existe. `Ctrl+5` natural.

2. **Configuração de colunas (visíveis + ordem) é por usuário ou compartilhada entre os 17 usuários?**  
   Recomendo: **por usuário.** É como o Notion web funciona. Cada um tem seu layout. `meta_user_columns` no design assume isso.

3. **O picker de colunas precisa permitir reordenar via drag-and-drop ou só toggle visibilidade?**  
   Recomendo: **toggle no MVP, drag-and-drop como follow-up.** Toggle resolve 90% do valor com 30% do esforço. Drag-and-drop adiciona complexidade no `setSectionsMovable` + persistência da ordem.

4. **Qual é o endpoint correto para ler o schema na API 2025-09-03?**  
   `GET /v1/data_sources/{id}` ou `GET /v1/databases/{id}`? **Decisão:** investigar com curl/script empírico ANTES de começar a Fase 0. **Pergunta concreta para o Leonardo:** posso fazer 1 chamada teste com seu token via Bash para validar?

5. **Vocabulários hardcoded (TRIBUNAIS = (...8 valores)) somem completamente, ou viram fallback?**  
   Recomendo: **somem completamente.** Source of truth é o Notion. Se cache falhar e Notion estiver fora, melhor mostrar "Schema indisponível" do que opções fantasmas.

6. **Refresh automático (TTL 24h) ou só on-demand?**  
   Recomendo: **on-demand + recovery** (refresh quando save falha por validation). Sem TTL automático — schema do Notion é estável; usuários aprendem a clicar "Recarregar" quando trocam algo.

7. **Quando o schema mudar e perder colunas que havia dado dirty: comportamento?**  
   Recomendo: **modal explícito** "A coluna X foi removida no Notion. Suas X edições não salvas serão descartadas. [Confirmar] [Cancelar — manter cache antigo]". Bloqueia até decisão.

8. **Fase 2 começa pelo Catálogo (recomendação) ou por outra base?**  
   Recomendo: **Catálogo.** Resolve BUG-OP-08. Menor blast radius. Schema simples (5 props). Bem alinhado com o smoke D1.

9. **Documentos: o app sabe que Documentos existe via DATA_SOURCES (via env var/config) ou via auto-discovery (POST /v1/search)?**  
   Recomendo: **via DATA_SOURCES no MVP**, com PR de 1 linha adicionando o ID. Auto-discovery vira Fase 5 se houver demanda.

10. **Override de label/cor por propriedade.** Vamos manter um arquivo `labels_overrides.py` (mapa data_source_id × key → custom label) ou aceitar que tudo seja o que o Notion mostra?  
    Recomendo: **arquivo de override existe mas começa vazio**. Leonardo/Déborah pode customizar caso a caso quando o nome do Notion ficar feio. Estrutura presente, conteúdo reativo.

11. **Densidade do "Configurar colunas":** o picker mostra label do Notion ou label custom (se houver)?  
    Recomendo: **label custom se existir, fallback notion_name**. Consistente com o que aparece na tabela.

---

## Recomendação final

**Começar pela Fase 0 imediatamente após responder à pergunta 4.** As decisões 1-3 e 5-11 podem ser tomadas no decorrer das fases sem retrabalho — o design comporta os defaults recomendados.

**Pré-requisito bloqueante:** validar empiricamente que `GET /v1/data_sources/{id}` (ou alternativa) funciona contra o token real. Posso fazer essa chamada via Bash + `curl` com o token disponível, em ~5min, antes da próxima sessão.

**Alternativa de menor escopo (se preferir um meio-termo):** **fazer só Fase 0 + Fase 2-Catálogo.** Resolve BUG-OP-08 sem mudar nada nas outras 3 bases. Trabalho total: 5-6h. Captura 60% do valor. As outras 3 bases continuam hardcoded até gerar incômodo real (ex: Déborah renomear coluna). Fica um híbrido por algum tempo, mas é tecnicamente OK.

**Não recomendo começar pela UI de picker (Fase 4)** antes de Fase 2 estar completa. Dinamizar visibilidade quando a fonte ainda é hardcoded é trabalhar em cima de areia movediça.

**Ponto de atenção sobre a sessão atual:** este é um spike de design — pode ter perdido detalhes. Sugiro **revisar com a Déborah** (especialmente seções 6 e 9.1) o que ela espera ver na UI ao adicionar uma coluna nova no Notion. O comportamento "aparece em 'Ocultas', usuário marca para mostrar" pode ser surpreendente para quem espera "aparece automaticamente onde foi adicionada no Notion".
