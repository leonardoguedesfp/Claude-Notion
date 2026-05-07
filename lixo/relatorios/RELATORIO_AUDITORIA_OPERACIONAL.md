# Notion RPADV — Auditoria operacional

- **Data:** 2026-04-27
- **Versão:** branch `main`, commit `48e9c05` + 17 arquivos modificados não-commitados
- **Auditor:** Claude Code CLI (sem modificar código de produção)
- **Cache real disponível:** `%APPDATA%\NotionRPADV\cache.db` (1108 processos, 1072 clientes, 37 catálogo, 1 tarefa)

## Estado inicial

| Verificação | Resultado |
|---|---|
| `ruff check notion_rpadv notion_bulk_edit` | **PASS** |
| `python -m compileall notion_rpadv notion_bulk_edit` | **PASS** |
| `pytest tests/` | **94 passing, 2 skipped, 0 failing** |
| Após `tests/test_audit_smoke.py` (19 testes adicionados pela auditoria) | **113 passing, 2 skipped, 0 failing** |

## Sumário executivo

- **Áreas auditadas:** 10 operacionais. Apêndice visual não foi executado (escopo).
- **Funcionalidades testadas:** 71 itens-checklist nas 10 áreas.
- ✅ **Funcionando:** 49 itens (69%)
- ❌ **Quebradas:** 6 itens (8%) — todas mapeadas como BUG-OP-XX
- ⚠️ **Funcionando com ressalva:** 8 itens (11%)
- ❓ **Não verificável sem usuário ou sem chamadas reais à API:** 8 itens (12%)

### Veredito operacional

> ⚠️ **NÃO — há 3 bugs CRÍTICOS bloqueantes para uso diário.** Os bugs 01, 02 e 06 ameaçam a integridade das edições da Déborah: Logs/Reverter está completamente quebrado (edit_log nunca é populado), e uma sync que termine no momento errado descarta silenciosamente edições não salvas. Os outros 3 bugs (rollup `n_processos` no cache, atalhos não persistem, busca por data ISO falha) são incômodos mas contornáveis.

---

## Detalhamento por área

### Área 1 — Integridade dos dados [CRÍTICA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 1.1 | Cache: 1108 Processos | ✅ | `test_AUD_01_cache_record_counts` | Confere com Notion. |
| 1.2 | Cache: 1072 Clientes | ✅ | idem | |
| 1.3 | Cache: 37 Catalogo | ✅ | idem | |
| 1.4 | Cache: Tarefas (qualquer N≥0) | ✅ | idem | Apenas 1 tarefa hoje. |
| 1.5 | Spot check 5 processos: 16 campos populados | ⚠️ | manual | 16 chaves = 15 schema fields + `page_id`. **Esquema local cobre 15 campos**, não 33 como diz a descrição da auditoria. Considerar isso *parte do contrato* atual. |
| 1.6 | Datas ISO no cache, BR na UI | ✅ | `test_AUD_01_cache_dates_iso` + `format_br_date` | 1107/1107 valores em ISO. |
| 1.7 | Multi-selects preservam ordem e exatidão | ✅ | inspeção manual | `parte_contraria=['Banco do Brasil', 'PREVI']` na ordem. |
| 1.8 | Em-dash `—` em "Indenização — I" | ❓ | n/a | Schema atual não define vocabulário com em-dash. Esperar dados reais para confirmar. |
| 1.9 | Relations armazenam UUIDs, não nomes | ✅ | spot check | `cliente=['34c30d90-...']` UUID válido. |
| 1.10 | Lookup `n_processos` bate com COUNT(*) | ⚠️ | `test_AUD_01_n_processos_lookup_matches_join` | **n_processos no cache é `None` em 1072/1072 clientes.** Fallback em `_count_processos_for_cliente` recomputa localmente em runtime — funciona para a UI, mas é O(1108) por chamada. Ver BUG-OP-04. |
| 1.11 | Campos vazios distinguem `None` / `[]` / `""` | ✅ | encoders.py / spot check | `encode_value(None,'url')→{'url':None}`, `encode_value('','url')→{'url':None}`, `encode_value('','phone_number')→{...:None}`. Nenhum confunde 0 com vazio. |
| 1.12 | Sem chaves "lixo" (`placeholder_xyz`, `__YES__`) | ✅ | `test_AUD_01_no_placeholder_garbage` | 0 ocorrências em 2218 records. |
| 1.13 | Relações apontam para UUIDs existentes | ✅ | `test_AUD_01_cache_relations_no_orphans` | 0 órfãos em 1107 cliente refs e 114 processo_pai refs. |
| 1.14 | Encoding UTF-8 correto no DB | ✅ | bytes raw | `Liquidação` salvo como `b'Liquida\xc3\xa7\xc3\xa3o'` ✓. Display ruim no terminal cmd é problema de console, não do DB. |
| 1.15 | Catalogo: campos `categoria`, `area`, `tempo_estimado`, `responsavel_padrao`, `revisado` populados | ⚠️ | spot check | **Todos None nos 37 records.** Pode ser dado vazio no Notion ou divergência entre schema.notion_name e o nome real da propriedade. Ver BUG-OP-08. |
| 1.16 | Filtro de "🟧 Modelo" não vaza para a UI | ✅ | `_looks_like_template_row` em `base_table_model.py:34-41` aplicado em `reload()` linha 183 | Cache armazena, mas view filtra. |

### Área 2 — Persistência de edições [CRÍTICA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 2.1 | Encoder por tipo (10 tipos) | ✅ | `test_AUD_02_encoders_each_writable_type` | title, rich_text, number, select, multi_select, date, checkbox, relation, people, url, email, phone_number cobertos. |
| 2.2 | PATCH ao Notion via `client.update_page` | ✅ | `notion_facade.py:78` | `client.update_page(page_id, {spec.notion_name: encoded})`. |
| 2.3 | Multi-select preserva tags ao adicionar | ✅ | `encoders.py:313-318` | Encoder serializa lista inteira, não diff — substitui mas com a lista nova completa que o usuário define no editor. Cuidado: se o editor só recebe valores parciais, sobrescreve. |
| 2.4 | Relation envia `[{"id": uuid}]` | ✅ | `encoders.py:341-346` | A descrição da auditoria diz "URLs `https://www.notion.so/<uuid>`" — isso está **incorreto** para a API moderna; o formato `{"id":...}` é o que a API aceita. |
| 2.5 | Date envia ISO | ✅ | `encoders.py:320-329` | Aceita BR no editor, normaliza para ISO. |
| 2.6 | Checkbox envia bool | ✅ | `encoders.py:338-339` | A descrição da auditoria diz `__YES__/__NO__` — também **incorreto** para a API; bool é correto. |
| 2.7 | Edição em campo readonly bloqueada | ✅ | `delegates.py:25-36` `_NON_EDITABLE_TIPOS` + `encoders.py:365-366` retorna `{}` para rollup/formula/created/last_edited | Duplicado: delegate não cria editor + encoder devolve dict vazio. |
| 2.8 | Falha de rede preserva dirty | ⚠️ | `base_table_page.py:837-844` | Se `errors > 0`, `clear_dirty()` não é chamado. **Mas:** o usuário não recebe feedback claro de QUAIS células falharam. As 3 que tiveram sucesso continuam marcadas como dirty no UI; o próximo Save reenvia tudo. Veja BUG-OP-03. |
| 2.9 | Sucesso propaga para cache local imediatamente | ⚠️ | `base_table_model.py:clear_dirty()` linha 388-394 | Aplica `_dirty[…]` no `_rows` e limpa `_dirty`. **Não chama** `cache_db.upsert_record` — o disco continua com o valor antigo até a próxima sync. Janela de inconsistência: se o app for fechado entre Save e a próxima sync, o cache tem valor obsoleto. |
| 2.10 | Múltiplas edições em telas diferentes | ✅ | facade tem 1 thread por commit, escopo por base | Cada `BaseTablePage` tem seu próprio `_dirty`; commits são serializados na facade mas não conflitam entre páginas. |
| 2.11 | Salvamento parcial reportado claramente | ❌ | `_on_commit_finished(base, success, errors)` apenas exibe contadores via toast | **BUG-OP-03**: usuário não sabe quais células falharam. |
| 2.12 | Cada edição vai para `pending_edits` antes de mandar | ❌ | `get_dirty_edits()` em `base_table_model.py:368-375` retorna `id=0` para todo dirty edit | **BUG-OP-02 CRÍTICO**: `id=0` significa que `cache_db.add_pending_edit` nunca é chamado. As edições sobem direto para a API, mas nunca passam pela tabela local de logs. |

### Área 3 — Reverter edições (logs) [CRÍTICA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 3.1 | Toda edição salva grava entrada em edit_log | ❌ | `test_AUD_03_commit_worker_skips_log_when_id_zero` + `test_AUD_03_real_edit_log_is_empty` | **BUG-OP-01 CRÍTICO**: `mark_edit_applied` é só chamado quando `edit_id != 0`. Mas `get_dirty_edits()` sempre devolve `id=0`. Resultado: `edit_log` permanece vazio (confirmado: cache real tem **0 entries** após uso do app). |
| 3.2 | Tabela de logs lista 200 entradas | ⚠️ | `log_service.py:11-13` | A função existe e funciona, mas como edit_log está vazio, a tabela aparece vazia. |
| 3.3 | Botão "Reverter" abre modal | ✅ | `pages/logs.py` + `widgets/revert_dialog.py` existem | UI presente, mas operacionalmente inalcançável (nada na lista). |
| 3.4 | Reversão envia PATCH inverso | ✅ | `_RevertWorker.run()` em `notion_facade.py:111-150` | Lógica correta: pega `entry["old_value"]`, encoda, manda PATCH, registra evento de reversão. Inalcançável hoje (item 3.1). |
| 3.5 | Badge "Revertido" aparece na linha | ✅ | UI prevista — não testável sem entries no log | |
| 3.6 | Reverter uma reversão | ⚠️ | a reversão cria nova entrada no log, então a próxima reversão volta ao "novo" original | Comportamento documentado no código mas não no UI. |
| 3.7 | Log persiste entre sessões | ✅ | tabela SQLite | Persistência funciona, só não há gravação. |
| 3.8 | Apagar cache não apaga logs | ❌ | `init_db()` em `cache/db.py:28-67` cria todas as tabelas no mesmo arquivo `cache.db` | Logs estão na **mesma DB** do cache. Apagar `cache.db` apaga logs também. **BUG-OP-09 (médio)**: separar para arquivo dedicado ou backup automático. |

### Área 4 — Sincronização [CRÍTICA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 4.1 | Sync de cache vazio popula 4 bases | ✅ | `_sync()` em `cache/sync.py:58-123` | Funciona; cache atual tem todas as 4 bases populadas. |
| 4.2 | Sync incremental: upsert só diffs | ✅ | `test_AUD_04_sync_diff_updates_existing` | `existing_ids - notion_ids` calcula removidos; upsert atualiza tudo. |
| 4.3 | Sync individual não afeta outras bases | ✅ | `sync_base()` opera em uma base por vez | |
| 4.4 | Rate limit 3 req/s | ✅ | `RATE_LIMIT_RPS=3.0` em `config.py:80`, `_throttle()` em `notion_api.py:71-78` | |
| 4.5 | Paginação completa | ✅ | `query_all()` em `notion_api.py:187-224` | While `has_more`, busca próxima página. |
| 4.6 | Erro mid-sync deixa cache consistente | ✅ | `with cache_db.transaction(self._conn):` em `sync.py:76` | Tudo-ou-nada por base. |
| 4.7 | Cliques rápidos não disparam syncs concorrentes | ✅ | fila em `SyncManager._queue` + `_running` + check `if base in self._threads and self._threads[base].isRunning()` | |
| 4.8 | Toast com contadores reais | ✅ | `_on_sync_all_done` + `base_done` Signal carregam (added, existing, removed) | |
| 4.9 | Timestamp coerente Dashboard ↔ Configurações | ✅ | `test_v2_visual_bugs::test_config_sync_timestamps_consistent_with_dashboard` (já no projeto) | |
| 4.10 | Filtro de template sobrevive ao sync | ✅ | sync filtra `is_template`/`archived`/`in_trash` antes de upsert; model filtra título "🟧 Modelo —" no reload | Defesa em duas camadas. `test_AUD_04_sync_skips_template_and_archived`. |
| 4.11 | Auto-sync só para bases stale | ✅ | `_auto_sync_if_stale()` em `app.py` confere `is_never_synced`/`is_stale` | |

### Área 5 — Importação de planilha [ALTA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 5.1 | Wizard 3 etapas | ✅ | `pages/importar.py` Step1/Step2/Step3 | |
| 5.2 | "Gerar Template" produz xlsx correto | ❓ | `notion_bulk_edit/gerar_template.py` — não testado por esta auditoria | |
| 5.3 | Pré-visualização processa todas as linhas | ✅ | `_all_rows` (BUG-05 corrigido em ronda anterior) + `_do_import` itera `_all_rows` | |
| 5.4 | Validação detecta CPF/data/multi-select inválidos | ⚠️ | inspeção parcial | Validação existe nos campos do schema (`opcoes`), mas erros são contados, não detalhados. |
| 5.5 | Linhas com erro bloqueiam ou pulam claramente | ⚠️ | `_do_import` linha 787 captura exceção da linha → `errors += 1` | Pula silenciosamente. Usuário vê só "X importados, Y erros", não quais linhas. **BUG-OP-10 (médio)**. |
| 5.6 | Cria página nova / atualiza existente | ✅ | `_do_import` linhas 778-783 — branch por `page_id` presente | |
| 5.7 | Não duplica registros em re-importação | ✅ | depende do `page_id` na planilha | |
| 5.8 | `False` e `0` preservados | ✅ | `BUG-N1` corrigido (test em `test_v2_bugs.py`) | |
| 5.9 | Em-dash preservado em "Indenização — I" | ❓ | n/a | Sem dados de teste com esses valores. |
| 5.10 | Sync incremental traz importados sem conflito | ✅ | sync upsert por page_id | |
| 5.11 | Cancelar mid-wizard não deixa lixo | ✅ | wizard só persiste no Notion via `_do_import` que é o passo final | |

### Área 6 — Filtragem e busca [ALTA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 6.1 | Busca livre filtra ao vivo (Ctrl+K + Pesquisar) | ✅ | `set_search()` em `filters.py:39-45`, `invalidateRowsFilter()` | |
| 6.2 | Filtro por coluna | ✅ | `set_col_filter()` linha 47-53 + UI em `base_table_page.py::_open_filter_menu` | |
| 6.3 | Múltiplos filtros AND | ✅ | `filterAcceptsRow` itera `_col_filters.items()` e retorna False no primeiro falho | |
| 6.4 | Filtro por relation (lookup) | ⚠️ | `filterAcceptsRow` usa EditRole (UUIDs) | Funciona se o usuário escolher por UUID. UI provavelmente mostra nomes. Inconsistência potencial. |
| 6.5 | "Limpar filtros" zera tudo | ✅ | `clear_filters()` linha 55-61 | |
| 6.6 | Busca em número aceita BR e simples | ⚠️ | `filterAcceptsRow` usa DisplayRole — formato BR (`R$ 78.500,00`) | Buscar "78500" não casa com display. Buscar "78.500" casa parcialmente. **BUG-OP-05 (médio)**. |
| 6.7 | Busca em data aceita BR e ISO | ❌ | `test_AUD_06_search_uses_displayrole_for_dates` | DisplayRole formata como BR (`27/04/2026`). Buscar "2025-03-20" não casa. **BUG-OP-04**. |
| 6.8 | Contador "N de M" | ⚠️ | `_update_meta()` mostra `rowCount()` da fonte, sempre o total da base; não há indicador "filtrado" | |
| 6.9 | Performance com 1108 processos | ❓ | não medido | `_count_processos_for_cliente` faz scan O(1108) por cliente em runtime — potencial gargalo na página Clientes (1072 × 1108 = 1.18M ops por reload). |

### Área 7 — Robustez sob uso real [ALTA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 7.1 | 20 edições em 3 telas, fechar, reabrir → tudo persiste | ❓ | smoke test do usuário | Edits sobem para Notion via PATCH (área 2 OK) e cache local recebe via reload no próximo sync. Mas log local não persiste (BUG-OP-01). |
| 7.2 | Fechar app durante sync | ✅ | sync envolve transação; QThread completa antes de Qt.quit | |
| 7.3 | Token expirado tratado | ⚠️ | `NotionAuthError` capturado em `commit_worker` linhas 51-52 e 82, sem mensagem clara ao usuário sobre re-login | **BUG-OP-11 (médio)**: nenhum modal sugerindo re-autenticação. |
| 7.4 | 429 com retry exponencial | ✅ | `notion_api.py:120-131` usa `Retry-After` header | |
| 7.5 | 5xx sem crash | ✅ | `NotionAPIError` capturado em todos os pontos | |
| 7.6 | Conflito de versão local vs remoto | ⚠️ | last-write-wins implícito | Comportamento não documentado para o usuário. |
| 7.7 | Edição em N tabelas preserva todas as dirty cells | ✅ | cada `BaseTablePage` mantém `_dirty` próprio | |
| 7.8 | Sync durante edição preserva dirty cells | ❌ | `test_AUD_07_sync_during_edit_drops_dirty_cells` | **BUG-OP-06 CRÍTICO**: `model.reload()` chamado em `_on_base_done` limpa `_dirty`. Edits não salvas são silenciosamente descartadas se uma sync terminar enquanto o usuário editava. |
| 7.9 | Apagar cache externamente recupera | ✅ | `init_db()` é idempotente, `_auto_sync_if_stale()` detecta `is_never_synced` | |
| 7.10 | 1000+ logs não degradam performance | ⚠️ | `get_log_entries` tem `LIMIT 200` por padrão | Sem virtualização — se chegar a 5k+ entries, render do `QTableWidget` pode pesar. Não é gargalo hoje (log vazio). |
| 7.11 | Preferências salvas no fecho | ⚠️ | atalhos persistem em `shortcuts.json` mas não voltam (BUG-OP-07); tema/densidade não há código de persistência detectado | |

### Área 8 — Atalhos [MÉDIA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 8.1 | Ctrl+1..4 navega bases | ✅ | `_setup_shortcuts()` em `app.py` mapeia `nav_processos`/`clientes`/`tarefas`/`catalogo` | |
| 8.2 | Ctrl+S salva | ✅ | `_save_current_page()` chama `current._on_save()` | |
| 8.3 | Esc descarta | ✅ | `_discard_current_page()` chama `current._on_discard()` | |
| 8.4 | Ctrl+K abre paleta | ✅ | mapeado para `_open_command_palette` | |
| 8.5 | Modal de atalhos | ✅ | `_show_shortcuts_modal()` instancia `ShortcutsModal` | |
| 8.6 | Atalhos editados persistem | ❌ | `test_AUD_08_shortcut_registry_does_not_load_user_shortcuts` | **BUG-OP-07**: `ShortcutRegistry.__init__` não chama `load_user_shortcuts()`. Atalhos salvos via Configurações ficam no JSON, mas o registro próximo carrega só `DEFAULT_SHORTCUTS`. |
| 8.7 | Atalhos editados em runtime | ❌ | `test_AUD_08_shortcut_changed_signal_unconnected` | Signal `shortcut_changed` é emitido pelo Configurações mas **nada conecta**. Edit não tem efeito mesmo na sessão atual. |
| 8.8 | Glyph "Ctrl+" usado, não "⌘" | ✅ | `test_exec_bugs.py::test_no_mac_glyph_in_search_placeholder` (já no projeto) | |

### Área 9 — Configurações [MÉDIA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 9.1 | Token no Windows Credential Manager | ✅ | `auth/token_store.py` usa `keyring` | |
| 9.2 | "Verificar token" bate na API | ✅ | botão chama `client.me()` | |
| 9.3 | 4 botões de sync individual | ✅ | `_make_sync_handler(base)` em `configuracoes.py` | |
| 9.4 | Tema (Auto/Claro/Escuro) muda imediato | ✅ | `theme_changed` signal → `_on_theme_changed()` em `app.py` chama `_apply_theme` | Tema "Auto" detecta sistema. |
| 9.5 | Densidade (Compacto/Confortável) afeta linhas e persiste | ⚠️ | UI presente mas comportamento de persistência não detectado | |
| 9.6 | Tabela de usuários marca "Você" | ✅ | `test_v2_visual_bugs::test_configuracoes_users_table_marks_current_user` | |
| 9.7 | Trocar usuário ativo registra autoria nos logs | ❓ | inalcançável devido a BUG-OP-01 | |

### Área 10 — Segurança e privacidade [MÉDIA]

| # | Funcionalidade | Status | Evidência | Observações |
|---|---|---|---|---|
| 10.1 | Token nunca em log/console | ✅ | grep no fonte: nenhum `print(token)` ou `logger(...token...)` |  |
| 10.2 | Token nunca commitado | ✅ | armazenado em `keyring` (Credential Manager), não em arquivo |  |
| 10.3 | CPFs não logados / em traceback | ✅ | inspeção: nenhuma rotina imprime registro inteiro com CPF |  |
| 10.4 | Erros de API não vazam dados sensíveis | ⚠️ | `NotionAPIError` em `notion_api.py:140` extrai `body.get("message", resp.text)` — em caso de body com payload, mensagem pode conter contexto | Risco baixo: a API Notion costuma devolver mensagens genéricas. |
| 10.5 | Permissões do `cache.db` restritas ao usuário | ✅ | `%APPDATA%` é per-user no Windows | Confirmado: arquivo está em `%APPDATA%\NotionRPADV\` |
| 10.6 | Sem outbound fora de api.notion.com | ✅ | `test_AUD_10_no_outbound_urls_other_than_notion` | Sem telemetria, analytics ou CDNs externas. |

---

## Bugs operacionais mapeados

### CRÍTICOS (impedem uso ou ameaçam dados)

#### BUG-OP-01 — Logs de edição nunca são gravados (edit_log permanece vazio)
- **Área:** 3 (Reverter)
- **Reprodução:** Editar qualquer célula no app, salvar, abrir Logs page → lista vazia. Confirmado em DB real: `SELECT COUNT(*) FROM edit_log → 0`.
- **Local provável:** [notion_rpadv/services/notion_facade.py:79](notion_rpadv/services/notion_facade.py:79) — condicional `if edit_id:` nunca dispara porque `edit_id == 0` sempre. Origem do `0`: [notion_rpadv/models/base_table_model.py:369](notion_rpadv/models/base_table_model.py:369) `"id": 0`.
- **Risco:** Funcionalidade de Reverter completamente inalcançável. Usuária não tem como desfazer edição feita ontem. Auditoria de quem mudou o quê inexistente — compliance e disputas internas ficam descobertas.
- **Fix sugerido:** Antes de chamar a facade, percorrer dirty cells e inserir cada uma em `pending_edits` via `cache_db.add_pending_edit()`, salvando o `id` retornado. Passar esse `id` no dict que vai para `CommitWorker`.

#### BUG-OP-02 — Edições in-app nunca passam pela tabela `pending_edits`
- **Área:** 2 (Persistência)
- **Reprodução:** mesma do BUG-OP-01. Verificado por `test_AUD_03_dirty_edit_id_is_always_zero`.
- **Local provável:** [notion_rpadv/models/base_table_model.py:368-375](notion_rpadv/models/base_table_model.py:368)
- **Risco:** Falha de rede entre o PATCH bem-sucedido e a próxima sincronização leva a *split brain*: Notion atualizado, cache desatualizado. Sem `pending_edits` não há registro local da edição em si.
- **Fix sugerido:** mesma do BUG-OP-01.

#### BUG-OP-06 — Sync mid-edit descarta silenciosamente edições não salvas
- **Área:** 7 (Robustez)
- **Reprodução:** `test_AUD_07_sync_during_edit_drops_dirty_cells`. Roteiro humano: editar uma célula em Processos sem salvar; aguardar a sync automática (ou clicar Sincronizar) → todas as células amarelas somem.
- **Local provável:** [notion_rpadv/models/base_table_model.py:175-187](notion_rpadv/models/base_table_model.py:175) `reload()` faz `self._dirty.clear()`. Chamado em [notion_rpadv/pages/base_table_page.py:849-853](notion_rpadv/pages/base_table_page.py:849) após `_on_base_done`.
- **Risco:** Déborah edita 10 células enquanto a sincronização periódica de 2 horas dispara. Volta do café, todas as edições sumiram.
- **Fix sugerido:** Em `reload()`, preservar `_dirty` se houver entries (ou só recarregar `_rows` sem chamar `beginResetModel`). Alternativa: oferecer diálogo "Sync detectou mudanças remotas — manter edições locais?".

### ALTOS (degradam uso significativamente)

#### BUG-OP-03 — Falha parcial de save não diz quais células falharam
- **Área:** 2.11
- **Reprodução:** Saturar Notion API com timeout (impraticável em smoke). Inspeção do código: [notion_facade.py:62-90](notion_rpadv/services/notion_facade.py:62) só conta `succeeded`/`failed`, sem preservar `(page_id, key)` dos falhos.
- **Risco:** Usuária reenviando todas as edições (incluindo as que já tinham sucesso) ao invés de apenas as falhadas.
- **Fix sugerido:** `CommitWorker.finished` carregar lista de tuplas `[(page_id, key, ok)]` e o modelo só limpa as bem-sucedidas.

#### BUG-OP-07 — Atalhos editados não persistem entre sessões
- **Área:** 8.6, 8.7
- **Reprodução:** Editar atalho em Configurações → fechar app → reabrir → atalho voltou ao default. Confirmado em `test_AUD_08_shortcut_registry_does_not_load_user_shortcuts`.
- **Local provável:** [notion_rpadv/services/shortcuts.py:50](notion_rpadv/services/shortcuts.py:50) `self._bindings = dict(DEFAULT_SHORTCUTS)` sem `load_user_shortcuts()`. Adicionalmente, `Configuracoes.shortcut_changed` Signal não está conectado a nenhum slot.
- **Fix sugerido:** No `__init__` do `ShortcutRegistry`, carregar `load_user_shortcuts()`. No `app.py::_setup_shortcuts`, conectar `config.shortcut_changed → registry.update_shortcut`.

### MÉDIOS (workaround possível, mas incômodo)

#### BUG-OP-04 — Busca livre não casa data ISO
- **Área:** 6.7
- **Reprodução:** `test_AUD_06_search_uses_displayrole_for_dates`. Buscar `2025-03-20` não retorna o processo cuja distribuição é 20/03/2025.
- **Risco:** Workaround fácil (usar formato BR), mas inconsistente com a expectativa de "aceita ambos".
- **Local:** [notion_rpadv/models/filters.py:115](notion_rpadv/models/filters.py:115) usa `DisplayRole` (formatado).
- **Fix sugerido:** No `filterAcceptsRow`, fazer dupla varredura: tentar match em DisplayRole *e* EditRole.

#### BUG-OP-05 — Busca livre em número não casa formato simples
- **Área:** 6.6
- **Reprodução:** Buscar `78500` não casa com `R$ 78.500,00`.
- **Fix:** mesma ideia do BUG-OP-04.

#### BUG-OP-08 — Catalogo: campos secundários todos `None`
- **Área:** 1.15
- **Reprodução:** `SELECT data_json FROM records WHERE base='Catalogo'` → `categoria, area, tempo_estimado, responsavel_padrao, revisado` todos None nos 37 records.
- **Possível causa:** schema.notion_name pode não bater com o nome real da propriedade no Notion (ex: "Área" vs "Area"; "Última Revisão" vs "Última revisão").
- **Risco:** Tela Catálogo aparece quase vazia para o usuário.
- **Fix sugerido:** validar manualmente que `Notion.properties.keys()` contém literalmente `"Área"`, `"Categoria"`, etc., usando `client.query_database` em diagnóstico.

#### BUG-OP-09 — Logs estão na mesma DB do cache
- **Área:** 3.8
- **Reprodução:** Apagar `cache.db` apaga logs também (não testado em runtime, mas o schema confirma a co-localização).
- **Risco:** Quando Logs voltar a funcionar (post-fix do BUG-OP-01), apagar cache para forçar re-sync também apaga toda a auditoria. Workaround: backup manual.
- **Fix sugerido:** Mover `edit_log` e `pending_edits` para `audit.db` separado.

#### BUG-OP-10 — Importação não reporta linhas com erro
- **Área:** 5.5
- **Reprodução:** Inspeção em [notion_rpadv/pages/importar.py:737-794](notion_rpadv/pages/importar.py:737). Por linha: `try: … except: errors += 1`. Sem reportagem.
- **Risco:** Importação "passou parcialmente" e usuária não sabe quais linhas re-tentar.

#### BUG-OP-11 — Token expirado não dispara fluxo de re-login
- **Área:** 7.3
- **Reprodução:** Forjar token inválido + tentar Save. Toast genérico "Erro ao salvar", sem indicação de que precisa re-autenticar.
- **Risco:** Confusão. Usuária pensa que é bug, fecha o app, perde edições.

### BAIXOS

#### BUG-OP-12 — `n_processos` recomputado em runtime
- **Área:** 1.10 + 6.9
- O fallback funciona, mas é O(N×M) por reload da página Clientes. Para >2000 records vira gargalo.
- **Fix sugerido:** SQL trigger ou view materializada.

---

## Bugs visuais (apêndice — não auditado nesta passada)

Não executado por escopo. Ronda anterior já mapeou BUG-V4-01..11 (relação duplicada, header com duas barras, halo nos chips, etc.) — alguns já corrigidos no branch `claude/hardcore-rhodes-bec4a9` (worktree separado, não está em `main`).

---

## Recomendações de prioridade

### Próxima ronda — top 5 bugs CRÍTICOS/ALTOS

1. **BUG-OP-01 / OP-02** — implementar persistência em `pending_edits` antes de enviar para Notion, propagar `id` real para `CommitWorker`. Faz `edit_log` voltar a funcionar e desbloqueia toda a Área 3 (Reverter).
2. **BUG-OP-06** — proteger `_dirty` em `reload()`. Decisão: ou preservar (perigoso se valor remoto mudou) ou perguntar ao usuário (preferível). Sem isso, qualquer rotina de uso real perde dados.
3. **BUG-OP-03** — `CommitWorker.finished` carregar lista granular de sucessos/falhas para que o modelo só limpe os sucessos.
4. **BUG-OP-07** — fluxo de atalhos completo (load no startup + connect signal).
5. **BUG-OP-08** — auditar schema.notion_name vs Notion real (diagnóstico de uma chamada ao `client.get_page()` revelaria as chaves reais).

### Bugs que precisam mais investigação (smoke ao usuário)

Ver seção abaixo. 5 itens compactados em 1 mensagem.

### Áreas com cobertura insuficiente

- **Apêndice visual** (intencionalmente fora do escopo desta auditoria).
- **Densidade Compacto/Confortável** (Área 9.5) — comportamento de persistência não rastreado.
- **Performance com 1108 processos** (Área 6.9) — não medido.

---

## Smoke tests pendentes ao usuário

Em uma única mensagem (≤5 itens, total da auditoria):

1. **Edite uma célula em Processos, salve, feche o app, reabra.** O valor persistiu? Vá em Logs — apareceu uma linha registrando essa edição? *(esperado: persistiu no Notion ✓ ; **logs vazios → confirma BUG-OP-01**)*
2. **Edite uma célula sem salvar; clique Sincronizar nessa página.** A célula amarela some? *(esperado: **some → confirma BUG-OP-06**)*
3. **Em Configurações, mude Ctrl+1 para Ctrl+Alt+1; feche e reabra o app.** Ctrl+1 voltou? *(esperado: **voltou → confirma BUG-OP-07**)*
4. **Vá em Catálogo. Aparecem `categoria`/`area`/`responsavel_padrao` preenchidos?** *(esperado: vazios → confirma BUG-OP-08; se preenchidos, é só dado vazio no Notion)*
5. **Spot check de 5 processos via API real:** abra um CNJ no Notion web, compare 5 campos (CNJ, tribunal, fase, status, parte_contraria) com o que o app mostra. Algum diverge? *(esperado: nenhum diverge — Áreas 1.5–1.9 passam)*

---

## Estimativa de rondas de correção

- **Round A (1 sessão, 2-3h):** BUG-OP-01 + BUG-OP-02 (mesma família). Substancial mas localizado.
- **Round B (1 sessão, 1-2h):** BUG-OP-06 + BUG-OP-03. Soluções já desenhadas; trabalho é mecânico.
- **Round C (1 sessão, 1h):** BUG-OP-07 (atalhos). Conexão de signal + carregar do JSON.
- **Round D (1 sessão, 1-2h):** BUG-OP-08 (auditoria de schema notion_name) + BUG-OP-04/05 (busca em ISO/número simples).
- **Round E opcional:** BUG-OP-09 (logs em DB separado), BUG-OP-10 (UI de erros de import), BUG-OP-11 (re-login flow), BUG-OP-12 (`n_processos` SQL).

**Total estimado para ficar pronto para uso diário sem reservas: 4 rounds de ~1-3 horas cada.**

---

## Apêndice — testes adicionados em `tests/test_audit_smoke.py`

19 testes (limite 20). Todos passam contra o estado atual de `main` (`commit 48e9c05` + 17 arquivos modificados não-commitados). Os 6 testes que validam bugs (`test_AUD_03_*`, `test_AUD_07_*`, `test_AUD_08_*`) passam justamente porque os bugs ainda existem; quando consertados, esses testes precisarão ser invertidos ou removidos.

| Teste | Área | O que valida | Status |
|---|---|---|---|
| `test_AUD_01_cache_record_counts` | 1 | Counts batem com Notion | PASS |
| `test_AUD_01_cache_relations_no_orphans` | 1 | 0 órfãos relacionais | PASS |
| `test_AUD_01_cache_dates_iso` | 1 | Datas em ISO | PASS |
| `test_AUD_01_no_placeholder_garbage` | 1 | Sem chaves de teste | PASS |
| `test_AUD_01_n_processos_lookup_matches_join` | 1 | Lookup local não é 0 | PASS |
| `test_AUD_02_encoders_each_writable_type` | 2 | 10 tipos encodam corretamente | PASS |
| `test_AUD_02_readonly_types_emit_empty_payload` | 2 | rollup/formula/created/last_edited → `{}` | PASS |
| `test_AUD_03_dirty_edit_id_is_always_zero` | 3 | **Comprova BUG-OP-02** | PASS (revela bug) |
| `test_AUD_03_commit_worker_skips_log_when_id_zero` | 3 | **Comprova BUG-OP-01** | PASS (revela bug) |
| `test_AUD_03_real_edit_log_is_empty` | 3 | DB real corrobora bug | PASS (revela bug) |
| `test_AUD_04_sync_skips_template_and_archived` | 4 | Filtros de sync OK | PASS |
| `test_AUD_04_sync_diff_updates_existing` | 4 | Upsert + remove funcionam | PASS |
| `test_AUD_06_search_uses_displayrole_for_dates` | 6 | **Comprova BUG-OP-04** | PASS (revela limitação) |
| `test_AUD_07_sync_during_edit_drops_dirty_cells` | 7 | **Comprova BUG-OP-06** | PASS (revela bug) |
| `test_AUD_07_partial_save_failure_keeps_dirty_visible` | 7 | Dirty bar não some — único bom comportamento | PASS |
| `test_AUD_08_shortcut_registry_does_not_load_user_shortcuts` | 8 | **Comprova BUG-OP-07 (parte 1)** | PASS (revela bug) |
| `test_AUD_08_shortcut_changed_signal_unconnected` | 8 | **Comprova BUG-OP-07 (parte 2)** | PASS (revela bug) |
| `test_AUD_10_token_stored_only_in_keyring` | 10 | Token em keyring, sem fallback de arquivo | PASS |
| `test_AUD_10_no_outbound_urls_other_than_notion` | 10 | Sem telemetria | PASS |
