# Relatório técnico — log/auditoria, usuários, multi-device

**Aplicação:** notion-rpadv 0.4.2 — companion desktop pro escritório Ricardo Passos Advocacia
**Repositório:** `C:\dev\Claude-Notion`
**Data da auditoria:** 30-abr-2026
**Branch analisada:** `feat/round-6-rollup-and-dashboard` (4 commits do Round 5 + 3 do Round 6, ainda não mergeados em `main`)
**Audiência:** Leonardo Passos (responsável pela modernização tecnológica)

---

## 0. Mapa do projeto

### 0.1 Stack técnico

| Item | Valor | Evidência |
|---|---|---|
| Linguagem | Python 3.11+ | [pyproject.toml:9](pyproject.toml) |
| UI framework | PySide6 ≥ 6.7 (Qt 6 binding) | [pyproject.toml:11](pyproject.toml) |
| Persistência | SQLite local (módulo stdlib `sqlite3`) | [notion_rpadv/cache/db.py:17](notion_rpadv/cache/db.py) |
| HTTP | `requests` ≥ 2.31 | [pyproject.toml:12](pyproject.toml), [notion_bulk_edit/notion_api.py](notion_bulk_edit/notion_api.py) |
| Excel | `openpyxl` ≥ 3.1 | [pyproject.toml:13](pyproject.toml) |
| Credenciais | `keyring` ≥ 24 (Windows Credential Manager) | [pyproject.toml:14](pyproject.toml), [notion_rpadv/auth/token_store.py:8](notion_rpadv/auth/token_store.py) |
| Empacotamento | PyInstaller (dev dependency) | [pyproject.toml:20](pyproject.toml) |
| Linting/typing | ruff + mypy strict | [pyproject.toml:25-32](pyproject.toml) |
| Testes | pytest (433 passed na branch atual) | [tests/](tests/) |

### 0.2 Arquitetura geral

**Aplicação desktop monolítica em PySide6, single-tier**, rodando localmente em Windows. **Não é** cliente-servidor próprio: o "servidor" é o próprio Notion (SaaS), acessado via REST API. O app é um **espelho local + editor inline** que sincroniza com o Notion.

Há também um CLI legado (`notion_bulk_edit/`) que compartilha config e cliente HTTP com o app desktop, usado pra import/export massivo via Excel (não é foco deste relatório).

### 0.3 Pontos de entrada

- **App desktop:** `python -m notion_rpadv` → [notion_rpadv/__main__.py:25](notion_rpadv/__main__.py)
- **CLI legado:** `python -m notion_bulk_edit` (não auditado neste relatório)

### 0.4 Localização dos três módulos críticos

| Módulo | Caminho |
|---|---|
| Autenticação/sessão | [notion_rpadv/auth/](notion_rpadv/auth/) (`login_window.py`, `token_store.py`) |
| Persistência (read/write SQLite) | [notion_rpadv/cache/db.py](notion_rpadv/cache/db.py), [notion_rpadv/cache/sync.py](notion_rpadv/cache/sync.py) |
| Logging/auditoria | [notion_rpadv/services/log_service.py](notion_rpadv/services/log_service.py) (somente leitura), schema em [notion_rpadv/cache/db.py:81-127](notion_rpadv/cache/db.py); commit das edições em [notion_rpadv/services/notion_facade.py:171-172, 245](notion_rpadv/services/notion_facade.py) |

### 0.5 Onde os dados ficam fisicamente quando o app roda

| Arquivo | Caminho Windows | Conteúdo | Fonte do path |
|---|---|---|---|
| `cache.db` | `%APPDATA%\NotionRPADV\cache.db` | Snapshot local das 4 bases Notion (records) | [notion_bulk_edit/config.py:130-131](notion_bulk_edit/config.py) |
| `audit.db` | `%APPDATA%\NotionRPADV\audit.db` | `pending_edits`, `edit_log`, `meta_schemas`, `meta_user_columns` | [notion_rpadv/cache/db.py:184-187](notion_rpadv/cache/db.py) |
| `shortcuts.json` | `%APPDATA%\NotionRPADV\shortcuts.json` | Atalhos personalizados do usuário | [notion_rpadv/services/shortcuts_store.py](notion_rpadv/services/shortcuts_store.py) |
| `cache.db.bak` | `%APPDATA%\NotionRPADV\cache.db.bak` | Backup one-shot pré-migration BUG-OP-09 | [notion_rpadv/cache/db.py:479-497](notion_rpadv/cache/db.py) |
| Token Notion | Windows Credential Manager (não em arquivo) | Token de integração `secret_...` | [notion_rpadv/auth/token_store.py:18, 29](notion_rpadv/auth/token_store.py) |
| `last_user` | Registro do Windows (`HKCU\Software\RPADV\NotionApp`) via QSettings | Slug local do último usuário logado | [notion_rpadv/__main__.py:34-35, 47](notion_rpadv/__main__.py) |

**Fonte de verdade dos dados de negócio:** Notion (servidor SaaS). O SQLite local é um cache de leitura + fila de edições pendentes.

---

## 1. Log e auditoria

### 1.1 Estado atual

**Logging técnico (debug/erro/diagnóstico):** ESSENCIALMENTE AUSENTE.
- `logging.getLogger(__name__)` é instanciado em pouquíssimos lugares ([notion_rpadv/services/notion_facade.py:15](notion_rpadv/services/notion_facade.py); [notion_bulk_edit/schema_registry.py:31](notion_bulk_edit/schema_registry.py); etc.) mas **nenhum handler é configurado pra arquivo** — o root logger usa o default Python (stderr, nível WARNING).
- Não existe arquivo de log persistido. Não há rotação, retenção, formato JSON, contexto estruturado.
- Erros pegos com `except Exception:` em vários pontos são frequentemente *silenciados* (`pass`, `return None`) ou virados em toast — sem registro para diagnóstico posterior.

**Trilha de auditoria de edições:** IMPLEMENTADA E FUNCIONAL.

Schema em [notion_rpadv/cache/db.py:92-102](notion_rpadv/cache/db.py):

```sql
CREATE TABLE edit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    base       TEXT    NOT NULL,
    page_id    TEXT    NOT NULL,
    key        TEXT    NOT NULL,
    old_value  TEXT    NOT NULL,   -- JSON-encoded
    new_value  TEXT    NOT NULL,   -- JSON-encoded
    applied_at REAL    NOT NULL,   -- UNIX timestamp
    user       TEXT    NOT NULL,
    reverted   INTEGER NOT NULL DEFAULT 0
)
```

Mais a tabela `pending_edits` ([db.py:81-90](notion_rpadv/cache/db.py)) que serve de fila enquanto a edição não foi aplicada no Notion.

**Como o `user` é populado:** o slug local (ex: `"deborah"`, `"leonardo"`) vem do `LoginWindow.get_user()` ([__main__.py:45](notion_rpadv/__main__.py)), atravessa `MainWindow → NotionFacade(user=self._user_id)` e é gravado em `mark_edit_applied(audit_conn, edit_id, self._user)` em [notion_facade.py:171-172, 245](notion_rpadv/services/notion_facade.py).

**Quando um log é gravado:**
1. Usuário edita célula → entra em `pending_edits` ([db.py:638-680](notion_rpadv/cache/db.py)).
2. Usuário clica "Salvar" → `CommitWorker` aplica via API Notion ([notion_facade.py:68-200](notion_rpadv/services/notion_facade.py)).
3. **Em sucesso na API**, `mark_edit_applied` move da fila pro `edit_log` com timestamp + autor.
4. Reversão posterior (`pages/logs.py`) seta `reverted=1` via UPDATE; **não deleta** a linha ([db.py:765-781](notion_rpadv/cache/db.py)).

**Página Logs ([notion_rpadv/pages/logs.py](notion_rpadv/pages/logs.py)):** mostra as 200 últimas entradas com base/página/campo/antes/depois/autor/data, e botão "Reverter" por linha. UI somente-leitura no resto — não dá pra editar nem apagar entradas.

**Localização física:** `%APPDATA%\NotionRPADV\audit.db` ([db.py:184-187](notion_rpadv/cache/db.py)).

### 1.2 Lacunas

**Crítico:**

1. **Logging técnico não persistido.** Quando o Leonardo abrir um chamado "o app travou ontem", não há arquivo de log pra inspecionar. Stack traces e warnings vão pra stderr e somem quando a janela fecha.
2. **Token e dados sensíveis em `old_value`/`new_value`.** O JSON serializado pode incluir CPF, RG, data de nascimento, telefone — qualquer campo editável da base Clientes. **Não há criptografia** em `audit.db`. Quem tiver acesso ao arquivo lê tudo em claro. *Implicação LGPD:* `audit.db` é repositório de dado pessoal sem proteção em repouso.
3. **Eventos críticos não auditados:** login bem-sucedido, login falhado, logout, sync (pull), abertura de página, exportação de dados (snapshot xlsx do Round 4), revogação de token. Em particular, **não há registro de quem exportou um snapshot xlsx pra fora da máquina**.
4. **Audit não é replicado nem backupeado.** Cada PC tem `audit.db` próprio. Se o disco do PC da Déborah falhar, perde-se a trilha. Não há export periódico.

**Importante:**

5. **Sem rotação ou retenção.** `edit_log` cresce indefinidamente. 16 colaboradores × N edições/dia × anos. Eventualmente a tabela ficará grande (não fatal pro SQLite, mas ruim pra busca).
6. **Sem assinatura/hash chain.** Embora a UI não permita apagar, qualquer pessoa com acesso ao arquivo pode `UPDATE edit_log SET ...` ou `DELETE FROM edit_log` direto. Não há prova de integridade — não dá pra demonstrar em juízo que o log não foi alterado.
7. **`reverted` flag é editado in-place.** Tecnicamente isso quebra "append-only puro": uma reversão mostra na UI, mas se alguém manualmente flipar o flag de volta, fica indistinguível.
8. **Filtro/busca de logs limitado.** A página Logs lista os 200 mais recentes. Não há filtro por usuário/data/base na UI (existe no service: `get_log_entries_by_user`, `get_log_entries_for_page` em [log_service.py:31-70](notion_rpadv/services/log_service.py), mas não consumido pela UI).

**Desejável:**

9. **Sem notificação de eventos críticos.** Reversão, exclusão, edição em massa — não há alert pra ninguém.

### 1.3 Recomendações priorizadas

| # | Recomendação | Prioridade | Esforço | Dependências |
|---|---|---|---|---|
| L1 | **Adicionar arquivo de log técnico rotacionado** (`%APPDATA%\NotionRPADV\app.log`) com `logging.handlers.RotatingFileHandler`, nível INFO, 5 MB × 5 arquivos. Configurar uma vez no `__main__.py` antes de qualquer import pesado. | crítica | baixo | — |
| L2 | **Auditar login (sucesso + falha)** em `edit_log` ou nova tabela `auth_log` (recomendo separar — `edit_log` é só negócio). Campos: `event_type`, `user`, `at`, `ok`, `reason`. | crítica | baixo | — |
| L3 | **Auditar exportação de snapshot xlsx** (página Exportar do Round 4). Quem exportou, quando, quais bases, hash do arquivo gerado. *Importante porque um xlsx de Clientes é vetor de exfiltração.* | crítica | baixo | L2 (mesma tabela `auth_log`/`activity_log`) |
| L4 | **Backup automático do `audit.db`** semanal pro OneDrive/SharePoint do escritório. Cron interno disparado em boot do app, 7 dias de retenção rotativa. | crítica | médio | — |
| L5 | **Política de retenção em `edit_log`** — purgar entradas com `applied_at` > 5 anos (alinha com prazo prescricional trabalhista no Brasil). Implementar como rotina de manutenção opcional, não automática. | importante | baixo | L4 (precisa ter backup antes de purgar) |
| L6 | **Filtros na UI da página Logs** (por usuário, intervalo de datas, base, campo). Os queries no service já existem; só plumbing de UI. | importante | médio | — |
| L7 | **Hash chain leve em `edit_log`** — cada linha guarda `prev_hash` (SHA-256 da linha anterior + own fields). Detecção forense de adulteração sem trocar de DB. | desejável | médio | — |
| L8 | **Mascarar dados sensíveis em logs técnicos** (token, CPF). Para o `edit_log` o conteúdo pleno é por design (precisa pra reverter), mas o app.log nunca deve receber. | importante | baixo | L1 |
| L9 | **Cifrar `audit.db` em repouso** com SQLCipher ou similar — chave derivada do token Notion + machine ID. Mitigação LGPD para roubo de máquina. | desejável | alto | L4 |

### 1.4 Decisões pendentes (perguntas para o Leonardo)

1. **Onde ficar o backup do `audit.db`?** OneDrive do escritório? SharePoint? Google Drive? Servidor próprio? *Esta decisão amarra L4.*
2. **Período de retenção.** 5 anos por padrão alinhado com CLT, mas há demandas previdenciárias com prazos maiores. Qual prazo formal o escritório quer adotar?
3. **Auditar leituras?** Hoje só escritas viram log. Saber "quem abriu o cliente X" é proporcional ao risco LGPD do escritório? (Custo: 2-3× volume de log.)
4. **Reverter deve ser ação restrita?** Hoje qualquer usuário logado pode reverter qualquer edição. Sugestão: limitar a admin (depende do RBAC da Área 2).

---

## 2. Controle de usuários

### 2.1 Estado atual

**Autenticação: token único de integração Notion, por máquina.**

- O `LoginWindow` ([notion_rpadv/auth/login_window.py](notion_rpadv/auth/login_window.py)) tem 2 modos:
  1. **Primeira execução:** usuário cola o token Notion (formato `secret_...`), valida via `NotionClient.me()`, escolhe seu nome de uma lista hardcoded de cards.
  2. **Modo "bom dia" (re-login):** se já há token salvo no keyring, mostra só o picker de usuário; se a lista é a de cards, basta clicar.
- O token vai pro Windows Credential Manager via `keyring.set_password` ([token_store.py:21-29](notion_rpadv/auth/token_store.py)).
- O slug do usuário vai pro `QSettings` (Registry do Windows) em `HKCU\Software\RPADV\NotionApp\last_user` ([__main__.py:33-47](notion_rpadv/__main__.py)).

**Modelo de usuários: três listas paralelas em código, sem união.**

| Constante | Localização | Conteúdo | Uso real |
|---|---|---|---|
| `NOTION_USERS` | [config.py:50-58](notion_bulk_edit/config.py) | UUID Notion → nome/iniciais/cargo | Resolver `Responsável` em Tarefas, `people` no xlsx (Round 5) |
| `USUARIOS_LOCAIS` | [config.py:64-70](notion_bulk_edit/config.py) | Slug → nome/iniciais/cargo (deborah, leonardo, ricardo, mariana, carla) | Display do `LoginWindow`, autor em `edit_log.user` |
| `USUARIOS_AUTORIZADOS` | [config.py:61](notion_bulk_edit/config.py) | Lista de slugs `["deborah", "leonardo"]` | **DECORATIVA — nunca verificada no código.** Grep por essa constante mostra apenas a definição. |

**Senhas:** não existem. Não há algoritmo de hash, não há campo de senha, não há fluxo de set/reset password. Autenticação é 100% via token Notion.

**RBAC:** AUSENTE NO CÓDIGO.
- O campo `role` em `USUARIOS_LOCAIS` (`"Administradora"`, `"Sócio fundador"`, `"Estagiária"`, etc.) **nunca é lido pra gating de funcionalidade**. Grep por `role`, `is_admin`, `can_edit`, `permission` na pasta `notion_rpadv` retorna zero usos pra controle de acesso. O campo é puramente cosmético (aparece no chip de avatar e na sidebar).
- Qualquer pessoa que coloque seu slug em `USUARIOS_LOCAIS` e tenha o token Notion da máquina logada pode editar/exportar tudo.

**Sessão:** persistente até logout manual ou revogação de token.
- Não há TTL, não há "última atividade", não há lock de tela após X minutos.
- Detecção de token revogado é **reativa**: só vê quando uma chamada API falha ([app.py:159-162](notion_rpadv/app.py)).
- Trocar de usuário no app: sair, abrir o Login, escolher outro card. **Mas o token continua o mesmo.** Trocar de usuário não troca de credencial — só muda o autor que vai pro `edit_log`.

**Revogação de acesso:**
- Sem comando UI/CLI no app pra "desativar" um usuário.
- Pra cortar o acesso de alguém que sai: ou (a) revogar a integração Notion no painel `notion.so/my-integrations` (afeta todas as máquinas), ou (b) deletar o token do Credential Manager naquela máquina específica, ou (c) editar `config.py` removendo o slug e republicar o app.

**Não implementado:** 2FA, recuperação de senha, bloqueio por tentativa, MFA, SSO, OAuth, magic link, sessões com expiração.

### 2.2 Lacunas

**Crítico:**

1. **Toda autenticação assume o token Notion como única credencial.** Se uma máquina compartilhada é deixada destravada, qualquer um clica no card de outro usuário e edita em nome dele. **Não há senha pessoal por colaborador.** O `edit_log.user` reflete quem CLICOU, não quem É.
2. **`USUARIOS_AUTORIZADOS` é mentira.** A lista existe, dá impressão de gating, mas nunca é checada. Basta editar `USUARIOS_LOCAIS` que o usuário entra. *Risco:* falsa sensação de segurança.
3. **Adicionar/remover usuário exige edição de código + redeploy.** Não dá pra um admin gerenciar a lista pela UI. Se a Carla sai do escritório, alguém precisa abrir [config.py:64-70](notion_bulk_edit/config.py), apagar a entrada e gerar novo executável (PyInstaller).
4. **RBAC zero.** Estagiária, sócio fundador e administradora têm o mesmo poder técnico. Estagiária pode editar processo do sócio, exportar snapshot completo de Clientes pra fora da máquina, reverter qualquer edição.

**Importante:**

5. **Token compartilhado por máquina.** Se a Déborah usa o PC da Mariana, o token "logado" lá é o da integração da máquina (não dela). Toda edição vira `user="mariana"` se ela clicar no card da Mariana. O log de auditoria não distingue identidade real.
6. **Sem expiração de sessão.** Máquina destravada às 18h, alguém entra à noite, edita.
7. **Sem registro de revogação.** Se você apagar o token, não há entrada em log dizendo "token deletado por X em Y". Idem L2 da seção anterior.

**Desejável:**

8. **`NOTION_USERS` tem placeholders (`MARIANA_NOTION_ID`, `CARLA_NOTION_ID`)** ([config.py:56-57](notion_bulk_edit/config.py)). Isso significa que o resolve UUID→nome falha pra essas duas em `Responsável` e `Tarefas` exportadas. Pendência conhecida desde Round 4 (OBS-A03).

### 2.3 Modelo de papéis proposto

A divisão típica de um escritório trabalhista de 16 pessoas em Brasília:

| Papel | Nº típico | Capacidades sugeridas |
|---|---|---|
| **Sócio** | 1-3 | Tudo: ler/escrever/excluir nas 4 bases; exportar; configurar usuários e permissões; ver e reverter qualquer edição; ver logs de auditoria de todos. |
| **Advogado** | 4-6 | Ler tudo; escrever/editar Tarefas e Processos; criar Cliente novo; **não excluir** (só sócio); exportar limitado a clientes onde está como responsável; ver seu próprio log. |
| **Paralegal/Controladoria** | 2-3 | Ler tudo; escrever Tarefas (e.g., atualizar status, anexar peça); editar campos não-jurídicos de Processos (data de protocolo, nº STJ); **não criar/excluir Cliente**; exportação restrita a relatórios consolidados (não dump de Clientes). |
| **Estagiário** | 4-6 | Ler quase tudo (sem campos de honorários, dados financeiros sensíveis); escrever apenas Tarefas que lhe foram atribuídas (Responsável = ele); **sem exportação**; sem reverter. |

**Operações sensíveis que sempre exigem sócio:**
- Excluir cliente, processo ou tarefa
- Reverter qualquer edição alheia
- Exportar snapshot completo
- Adicionar/remover usuário, mudar papel
- Ver logs de outros usuários
- Configurar token Notion da máquina

**Granularidade adicional desejável (custo médio):**
- "Cliente confidencial" — flag em Cliente que esconde de estagiários e paralegais não-atribuídos. Útil pra casos de assédio, demissão de executivo, etc.
- "Processo restrito" — idem, com lista explícita de quem vê.

**O que é código vs. configuração:**
- **Código (precisa implementar):** o motor de RBAC — função `can(user, action, resource)`, gating em UI (esconder botões), gating em API (verificar antes de chamar Notion), gating em export.
- **Configuração (admin via UI):** matriz de permissões por papel; lista de usuários ativos; atribuição de papel a cada usuário; lista de clientes/processos confidenciais.

### 2.4 Recomendações priorizadas

| # | Recomendação | Prioridade | Esforço | Dependências |
|---|---|---|---|---|
| U1 | **Migrar usuários pra tabela SQLite** em `audit.db` (`users(id, slug, name, role, active, created_at)`) com seeding inicial a partir de `USUARIOS_LOCAIS`. Decommissionar a constante. UI de admin pra ativar/desativar e mudar papel. | crítica | médio | — |
| U2 | **Implementar verificação de `USUARIOS_AUTORIZADOS`** ANTES de migração — virar a checagem real e remover slugs não autorizados do `LoginWindow`. Patch de 5 linhas, fecha o vetor mais óbvio. | crítica | baixo | — |
| U3 | **Senha pessoal por usuário** (PBKDF2/Argon2 + salt em `users.password_hash`). Login passa a ser slug + senha; token Notion continua sendo da máquina mas ESCONDIDO do usuário comum (só sócio configura). | crítica | médio | U1 |
| U4 | **Motor RBAC mínimo:** módulo `notion_rpadv/auth/rbac.py` com `can(user, action, resource)`. Ações: `read`, `write`, `delete`, `export`, `revert`, `manage_users`. Aplicar gate em 4 pontos: handler de save (NotionFacade), botão Reverter (logs.py), botão Exportar (exportar.py), nova página de admin. | crítica | médio | U1 |
| U5 | **Expiração de sessão por inatividade** (default 4h, configurável). QTimer reseta a cada interação. Ao expirar, abre LoginWindow de novo (token persiste, só pede senha). | importante | baixo | U3 |
| U6 | **UI de admin de usuários** (página Configurações, seção visível só pra sócio): adicionar, desativar, trocar papel, resetar senha. | importante | médio | U1, U4 |
| U7 | **Resolver placeholders `MARIANA_NOTION_ID`/`CARLA_NOTION_ID`** ([config.py:56-57](notion_bulk_edit/config.py)) — pedir Déborah rodar `GET /v1/users` e substituir. *Trivial mas trava a resolução de Responsável dela e da Carla.* | importante | baixo | — |
| U8 | **Bloqueio após N tentativas falhadas** (5 tentativas → 15 min trava). Necessário se U3 entrar. | importante | baixo | U3 |
| U9 | **2FA opcional pra sócio** (TOTP via `pyotp`). Aplicar a operações sensíveis (excluir, exportar massivo, mudar permissão). | desejável | médio | U3, U4 |
| U10 | **Granularidade por cliente/processo** (flag `confidencial` em Cliente, lista `visible_to` em Processo). Aplicar via RBAC. | desejável | alto | U4 |

### 2.5 Decisões pendentes

1. **Token Notion: por máquina ou por usuário?** Hoje é por máquina. Se virar por usuário, cada um precisa ter sua integração Notion pessoal — mais limpo do ponto de vista de auditoria, mas mais trabalho administrativo (Notion limita N integrações por workspace).
2. **Quem é sócio?** Hoje a constante diz que Ricardo e Leonardo são "Sócio fundador" e "Sócio em formação" respectivamente. Consideramos os dois como papel "sócio" pra RBAC, ou só Ricardo?
3. **Estagiários veem dados financeiros?** Honorários, valor da causa, etc. existem em Processos. Esconder esses campos pra estagiário é granularidade adicional (custo médio na recomendação U10).
4. **Exportar xlsx — quem pode?** Hoje qualquer um. Sugestão: só sócio + advogado (não estagiário, não paralegal). Concorda?
5. **Reset de senha de outro usuário — só sócio?** Sim. Mas que fluxo: gera senha temporária no chat? Email? UI mostra texto pro sócio copiar e dar pessoalmente?

---

## 3. Persistência e multi-device

### 3.1 Estado atual

**Topologia: cada PC tem seu próprio cache local + audit local. O Notion é hub.**

- `cache.db` (records) e `audit.db` (edições + schemas + prefs) ficam em `%APPDATA%\NotionRPADV\` ([config.py:122-127, 130-131](notion_bulk_edit/config.py); [db.py:184-187](notion_rpadv/cache/db.py)).
- **Não há banco compartilhado** (nem por rede, nem em cloud). Cada máquina é uma ilha.
- Sincronização é **pull-only manual** disparada por `SyncManager` ([notion_rpadv/cache/sync.py:136-230](notion_rpadv/cache/sync.py)) — o usuário clica "Sincronizar tudo" no Dashboard, ou cada base é re-puxada quando aberta. **Não há polling automático**, nem WebSocket de notificação Notion.
- Edições do usuário viram `pending_edits` no audit local; quando ele clica Salvar, `CommitWorker` ([notion_facade.py:68-200](notion_rpadv/services/notion_facade.py)) chama a API Notion (`update_page`) e em sucesso move pro `edit_log`.

**Conflitos:**
- *Detecção parcial intra-PC:* o sinal `dirty_conflict_detected` ([base_table_model.py](notion_rpadv/models/base_table_model.py)) dispara quando, durante um reload, o cache descobre que o valor remoto mudou enquanto o usuário tinha edição pendente local. UI mostra toast.
- *Entre PCs: nenhuma detecção.* Se PC A edita e salva, PC B (que tem cópia stale) edita e salva depois — last-write-wins na API Notion. PC A nunca vê que sua edição foi sobrescrita até fazer um sync novo.

**Backup:**
- `cache.db.bak` é criado **uma única vez** antes da migration BUG-OP-09 que separou cache de audit ([db.py:479-497](notion_rpadv/cache/db.py)). **Não rotativo**, **não periódico**.
- `audit.db` **nunca é backupeado automaticamente.**
- Não há backup automático de `shortcuts.json`, `meta_user_columns`, `meta_schemas`, `QSettings`.

**Dados que NÃO sincronizam entre PCs (são por-máquina):**

| Dado | Implicação prática |
|---|---|
| `meta_user_columns` (prefs de coluna por usuário) | Déborah configura colunas no PC dela; muda pra PC da Mariana, perdeu a config — vê layout default. |
| `meta_schemas` (cache do schema Notion) | Cada PC re-fetch quando boota. Não corrupta, mas duplica trabalho. |
| `shortcuts.json` (atalhos personalizados) | Idem — atalho customizado fica preso ao PC. |
| `QSettings.last_user` | Idem — primeiro login em PC novo precisa escolher do zero. |
| `pending_edits` | Crítico: edições offline ficam presas no PC onde foram feitas. Se o PC da Carla quebrar antes dela clicar Salvar, perde tudo. |
| `edit_log` | Trilha de auditoria fragmentada por PC. Não há visão consolidada por usuário sem juntar manualmente. |

**Modo offline:**
- O app tolera Notion fora do ar — `NotionClient` retorna erro, `CommitWorker` propaga via signal `commit_error`, edição fica em `pending_edits` esperando.
- **Mas:** sem detecção proativa de "Notion OK?" ao abrir. O usuário descobre que está offline ao tentar salvar.

### 3.2 Resposta direta: classificação

**(c) multi-device sem sincronização — cada cópia tem dados independentes que divergem com o tempo.**

Justificativa em uma linha: cada PC tem `cache.db`/`audit.db` local; sync com Notion é manual e pull-only; conflitos entre PCs são last-write-wins não detectado; preferências de UI e auditoria nunca cruzam entre máquinas.

**Caveat importante:** os *dados de negócio* (clientes, processos, tarefas, catálogo) ficam consistentes na medida em que o Notion é fonte de verdade — depois de um sync recente em ambos os PCs, os 2 veem o mesmo estado. Mas essa "consistência" depende de:
- ambos os usuários lembrarem de sincronizar
- ninguém ter edições pendentes não-salvas
- não haver conflito simultâneo

Na prática operacional, isso quebra com frequência: Déborah edita e esquece de salvar; Mariana abre o mesmo registro 2h depois com cópia velha; uma sobrescreve a outra sem aviso.

### 3.3 Lacunas

**Crítico:**

1. **Edições pendentes morrem com o disco.** Se o PC da Déborah quebra antes dela clicar Salvar, todas as edições em `pending_edits` somem. Nenhum backup dispara antes do save bem-sucedido.
2. **Preferências de UI e auditoria por-máquina.** Trocar de PC = começar do zero (layout, atalhos, histórico de logs). Pra um escritório onde colaboradores frequentemente trabalham em PCs diferentes (notebook + desktop), isso é fricção real.
3. **Conflito entre PCs é silencioso.** Last-write-wins. Sem aviso, sem merge, sem versão. Edições somem.

**Importante:**

4. **Sem sync automático em background.** O app só puxa quando o usuário clica. Quem abre o app de manhã trabalha o dia inteiro vendo o snapshot das 9h.
5. **Detecção de "Notion offline" reativa.** Indicador visual de conexão no canto da janela ajudaria.
6. **Tempo de boot proporcional a `query_all` × 4 bases.** ~2200 registros, 30-60s na primeira sync. Não é problema funcional, mas é fricção.

**Desejável:**

7. **Sem versão/histórico de cache.** Se sync trouxe dado errado (Notion estava num estado inconsistente), não dá pra "voltar" ao snapshot anterior — só esperar o Notion estabilizar e re-sync.

### 3.4 Recomendações priorizadas

A pergunta-chave é *qual estado-alvo o escritório quer*. Há três caminhos viáveis:

**Caminho B — sincronização indireta via Notion + backup periódico do local.** *Mantém a arquitetura atual; mitiga as lacunas.*
**Caminho D — virar cliente fino que não cacheia em SQLite.** *Reescreve a camada de persistência. Cada PC vira janela de leitura ao Notion.*
**Caminho híbrido — cache local + servidor próprio compartilhando audit + prefs.** *Mais complexo, mas é o que escala se o escritório crescer.*

| # | Recomendação | Caminho | Prioridade | Esforço | Dependências |
|---|---|---|---|---|---|
| P1 | **Backup automático dos `pending_edits`** antes de qualquer reload — copia pra `pending_edits.bak.json` no APPDATA. Mitigação imediata pro pior cenário (perder edição não-salva). | B | crítica | baixo | — |
| P2 | **Backup periódico do `audit.db`** semanal pra OneDrive/SharePoint do escritório (mesma decisão da L4 da Área 1). | B | crítica | médio | escolher destino (decisão pendente) |
| P3 | **Sync automático em background** — QTimer dispara sync silencioso a cada 5-10 min. Indicador visual quando há mudança remota nova. | B | importante | médio | — |
| P4 | **Indicador visual de conectividade** (badge "online/offline" no canto da janela) com ping periódico ao Notion. | B | importante | baixo | — |
| P5 | **Exportar `meta_user_columns` e `shortcuts.json` pro Notion** (página/banco "Preferências de usuário" controlado por integration). Cada PC sincroniza prefs no boot. *Reusa Notion como hub — não introduz novo backend.* | B | desejável | médio | — |
| P6 | **Detecção de conflito entre PCs** — antes de cada `update_page`, fazer um `get_page` e comparar `last_edited_time` com a última visão local. Se mudou, abortar e mostrar diff. | B | importante | médio | — |
| P7 | **Cliente fino (sem cache local)** — remove `cache.db`, toda leitura/escrita vai direto ao Notion. Performance cai (latência de rede em cada interação) mas resolve consistência multi-device de uma vez. | D | (opção) | alto | — |
| P8 | **Servidor próprio leve** (FastAPI + Postgres + 1 VM) que centraliza `audit.db` + prefs + auth + RBAC. Cada PC vira cliente desse servidor. *Não substitui Notion — adiciona uma camada.* | híbrido | (opção) | alto | decisão estratégica |

Recomendação prática: começar pelo **Caminho B** (P1+P2+P3+P4 cobrem 80% das dores) com investimento total ~1-2 semanas. Reavaliar a necessidade de D ou híbrido em 6 meses, depois de medir quantos conflitos e quantas perdas de dado realmente acontecem.

### 3.5 Decisões pendentes

1. **Caminho-alvo: B, D ou híbrido?** Esta é a decisão arquitetural mais importante. Caminho B é evolução; D é reescrita parcial; híbrido é projeto.
2. **Onde guardar o backup do audit.db?** (Mesma pergunta da Área 1.)
3. **Aceitamos last-write-wins entre PCs?** Se o caso de uso real é "Déborah trabalha de manhã, Mariana de tarde, raramente concorrem", LWW + sync periódico talvez seja aceitável. Se há frequência de concorrência (e.g., uma reunião onde 2 advogados editam o mesmo processo simultaneamente), precisa P6.
4. **Quem usa qual PC?** Mapear: a Déborah trabalha sempre no mesmo PC? Os estagiários têm máquina pessoal ou dividem? Isto altera a urgência de P5 (sync de prefs).
5. **Há rede local entre os PCs?** Se sim, abre opção de SQLite compartilhado em pasta de rede (Caminho híbrido leve, sem precisar VM). Mas SQLite em rede tem armadilhas — precisa avaliar.

---

## 4. Roadmap sugerido

Considerando dependências entre as 3 áreas + risco operacional, sugiro a sequência abaixo. Cada bloco é entregável independente; o escritório pode parar entre blocos.

### Bloco 0 — Higiene imediata (1 semana)
- **L1** logging técnico em arquivo
- **L2** auditar login (sucesso + falha)
- **L3** auditar exportação xlsx
- **U2** virar `USUARIOS_AUTORIZADOS` em checagem real (5 linhas)
- **U7** resolver UUIDs Mariana/Carla
- **P1** backup automático de `pending_edits`

*Por que primeiro:* tudo é baixo esforço, alto valor defensivo, sem dependência de decisões arquiteturais.

### Bloco 1 — Backup e visibilidade (1 semana)
- **P2** backup semanal de `audit.db` pro OneDrive/SharePoint (depende: decidir destino)
- **P3** sync automático em background
- **P4** indicador online/offline
- **L6** filtros na página Logs

*Por que aqui:* operacional sem mudar arquitetura. Reduz a fricção do dia-a-dia.

### Bloco 2 — Identidade e papéis (2 semanas)
- **U1** migrar usuários pra SQLite
- **U3** senha pessoal por usuário
- **U4** motor RBAC mínimo
- **U5** expiração de sessão
- **U6** UI de admin de usuários
- **U8** bloqueio após N tentativas

*Por que aqui:* depende de decisões pendentes sobre papéis/granularidade. É o salto de "máquina logada" pra "pessoa logada".

### Bloco 3 — Robustez de auditoria (1-2 semanas)
- **L4** backup do audit.db (já entregue parcialmente em P2; aqui é só formalizar política)
- **L5** retenção de logs
- **L8** mascarar dados sensíveis no app.log
- **L7** hash chain (opcional)

*Por que aqui:* acessório. Não bloqueia operação, mas protege contra contestação futura.

### Bloco 4 — Decisão arquitetural (a definir)
- Decidir entre **Caminho B** (P5+P6 — sincroniza prefs via Notion + detecta conflito entre PCs) e **Caminho D/híbrido** (P7 ou P8).
- Esta decisão depende de medições do Bloco 1 (quantos conflitos reais? quanto tempo offline?).

### Bloco 5 — Granularidade fina (opcional, sob demanda)
- **U9** 2FA pra sócio
- **U10** flags de cliente/processo confidencial
- **L9** cifragem de audit.db em repouso

*Por que último:* só compensa se houver caso concreto pedindo (cliente de alto perfil, fiscalização LGPD apertada, vazamento próximo).

---

### Observações finais

- O sistema atual é **funcional pra um escritório de 16 pessoas** com a ressalva de que o controle de identidade é frouxo (U2 sozinho já tira isso do vermelho) e a operação multi-device é por-PC (P3+P4 mascaram bem).
- **Não há dívida arquitetural impeditiva.** Os módulos estão bem separados (auth, cache, services, models, pages); inserir RBAC e sync automático é cirúrgico.
- **Notion como backend gratuito** é uma vantagem que vale preservar até ter caso de negócio pra mover. Limita-se a ~3 RPS por integração ([config.py:80](notion_bulk_edit/config.py)) — confortável pra 16 pessoas, apertado pra 50+.
- **A maior fragilidade hoje, do ponto de vista LGPD, é `audit.db` sem cifragem** (L9) somado a `pending_edits` sem backup (P1). Um notebook roubado vaza CPF + tudo o que foi editado.
- **A maior fragilidade operacional é a falta de RBAC** (U2+U4): basta um clique em outro card de usuário pra agir em nome de outra pessoa, sem senha.

Reformar essas duas coisas (Bloco 0 + parte do Bloco 2) cabe em 3 semanas e tira o sistema do estado "vulnerável por desenho" pro estado "vulnerável por escolha consciente" — que é onde um escritório pequeno pode operar com responsabilidade.
