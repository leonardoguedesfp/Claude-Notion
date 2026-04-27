# DELTA V1 → V2 — Notion RPADV

Documento de revisão. Para cada item: **o que mudou**, **por quê**, e **onde no código** aplicar.

> Convenções de caminho: `theme/` = `notion_rpadv/theme/`, `pages/` = `notion_rpadv/pages/`, `widgets/` = `notion_rpadv/widgets/`. Os QSS estão em `theme/qss_light.py` e `theme/qss_dark.py`.

---

## 0 · Tokens & fundações

### 0.1 Paleta consolidada
- **Mudou:** Cream `#EDEAE4`, Navy `#0C324D` / `#104063`, Petrol `#395A5A` confirmados como tokens canônicos. Removidas referências antigas a Inter/Segoe UI.
- **Por quê:** alinhar V2 com `assets/fonts/` (Nunito Sans embarcado) e com a paleta vetorizada da identidade.
- **Código:** `theme/tokens.py` — exportar `COLOR_PRIMARY`, `COLOR_SECONDARY`, `COLOR_SURFACE_*` como constantes únicas; `theme/qss_*.py` consome via `.format(**TOKENS)`.

### 0.2 Tema escuro completo
- **Mudou:** todas as 8 telas + a 9ª nova foram desenhadas em escuro. Paleta: fundo `#142430`, painéis `#1A2D3D`, sidebar mais escura `#0A1F2D`, texto cream invertido `#E8E4DD`.
- **Por quê:** V1 só desenhou claro; `qss_dark.py` (1.007 linhas) ficou inconsistente com componentes não previstos.
- **Código:** reescrever `theme/qss_dark.py` em cima dos novos tokens. Adicionar `theme/tokens_dark.py` espelhando `tokens.py`. Garantir contraste WCAG AA em todo texto sobre fundo (testado: 4.5:1 mínimo).
- **Chips:** usar paletas dessaturadas em escuro — ver `--chip-*-bg/-fg` no CSS V2.

### 0.3 Tema "Auto"
- **Mudou:** seletor de tema agora tem 3 radios (Auto / Claro / Escuro), com **Auto** como default.
- **Por quê:** usuário-alvo é desktop Windows; seguir o tema do sistema é o comportamento esperado.
- **Código:** `pages/configuracoes.py::ThemePicker` — escutar `QStyleHints.colorScheme()` quando `theme=='Auto'` e re-aplicar QSS.

---

## 1 · Login (returning)

### 1.1 Modo returning especificado
- **Mudou:** quando há token salvo no Credential Manager, a tela mostra o seletor de 17 usuários como **conteúdo principal**, não o campo de token. Avatares circulares com iniciais + função abreviada. Botão "Trocar token do escritório →" rebaixado a link no rodapé.
- **Por quê:** em uso diário, ninguém precisa retocar o token; a fricção é "qual usuário sou eu hoje". V1 priorizou o caso first-run.
- **Código:** `pages/login.py` — adicionar branch `if keyring.get_password(...): render_returning()`. Componente `UserPickerGrid` novo em `widgets/user_picker.py`.

### 1.2 Confirmação visual de token armazenado
- **Mudou:** banner sutil (acento navy, sem alarme) "Token armazenado nesta máquina · Windows Credential Manager" com ícone de cadeado.
- **Por quê:** transparência de onde o segredo está sem deixar parecer alerta.

---

## 2 · Dashboard

### 2.1 Spacing entre seções
- **Mudou:** 32px verticais entre primeiro nível (`SP_8`); cards isolados em `QFrame` com borda 1px `--border` e `border-radius:4px`.
- **Por quê:** V1 sobrepunha "Tarefas Urgentes" e "Sincronização".
- **Código:** `pages/dashboard.py::DashboardPage::__init__` — `layout.setSpacing(32)` no nível raiz; cada card é um `QGroupBox` com QSS dedicado.

### 2.2 KPI = 0 calmo
- **Mudou:** "Tarefas hoje" e "Prazo crítico" com 0 ficam em **cor neutra** (`--fg-2`, peso 400, mesma fonte) com legenda explicativa "Sem tarefas para hoje" / "Nenhum prazo na semana". Indicador vermelho **só** com N ≥ 1.
- **Por quê:** V1 desenhou só o estado feliz com números; usuário interpretava 0 como bug ("sempre 0, está quebrado").
- **Código:** `widgets/kpi_card.py::KpiCard::set_value(n, label_zero=None)` — quando n==0 e label_zero existe, troca classe CSS para `.calm` e exibe `label_zero`.

### 2.3 Painel de Sincronização
- **Mudou:** layout de tabela 5 colunas: base, contagem `847/1.108`, barra de progresso, timestamp, chip OK. Linha ativa mostra a barra preenchendo + "Sincronizando…"; idle mostra "há X min" + chip verde OK.
- **Status bar e header consistentes:** se há sync ativa, statusbar mostra `Sincronizando: Processos (847/1108)` e o card mostra "Sincronizando…" na linha da base ativa.
- **Barra de progresso global:** 2px no rodapé do `.toolbar` durante sync ativa.
- **Código:** `pages/dashboard.py::SyncPanel`, `widgets/sync_row.py`, `widgets/global_progress.py` (novo).

### 2.4 "Última sync" unificada
- **Mudou:** statusbar e card sync usam o mesmo serviço (`SyncService.last_sync_per_base`) — nunca mais ficam dessincronizados.
- **Código:** `services/sync_service.py` — emitir signal `lastSyncChanged(base, dt)`; ambos consomem.

---

## 3 · Tabelas (Processos / Clientes / Tarefas / Catálogo)

### 3.1 Cabeçalhos
- **Mudou:** altura **36px** (era 24); padding horizontal 12px cada lado; larguras mínimas por nome de coluna; tooltip no header com nome completo quando truncado.
- **Larguras mínimas (px):** CNJ 200 · Título 280 · Cliente principal 200 · Tribunal 90 · Fase 130 · Status 90 · Responsáveis 100 · Prazo 96.
- **Por quê:** V1 truncava "ente princi" em vez de "Cliente principal".
- **Código:** `widgets/base_table.py::TableHeader::COLUMN_MIN_WIDTHS = {...}`. `setSectionResizeMode(Interactive)` + `setMinimumSectionSize(per col)`.

### 3.2 Relações resolvidas
- **Mudou:** colunas de relação mostram **título** do registro relacionado, nunca ID cru. Múltiplos: "Maria Silva, João Costa +3 outros".
- **Renderização:** chip cor `--accent` (chip-rel) clicável que abre o detalhe do registro relacionado.
- **Por quê:** V1 mostrava `['34c30d9...']`.
- **Código:** `widgets/cells/relation_cell.py` — receber `RelationValue(ids=[...], titles=[...])` resolvido pelo cache local.

### 3.3 Células vazias
- **Mudou:** `[]` ou `null` viram célula vazia (`—` em cinza claro). Nunca array cru.
- **Código:** `widgets/cells/cell_factory.py::format(value)` — guardar contra falsy/empty antes do `repr`.

### 3.4 Espaço branco abaixo das linhas
- **Mudou:** área não-preenchida usa `--surface-default` (cream sutil), não branco puro. Visualmente sinaliza fim de lista.
- **Código:** `widgets/base_table.py::Table::paintEvent` — pintar `viewport().rect()` abaixo da última linha com QBrush(token).

### 3.5 Linha "Modelo — usar como template"
- **Mudou:** filtrada antes de chegar à tabela.
- **Empty state real:** quando a base inteira está vazia (não filtrada), mostrar 9ª tela (ver §9).
- **Código:** `services/notion_repo.py::list_processos()` — `WHERE titulo NOT LIKE 'Modelo —%'`.

### 3.6 Coluna "N° processos" em Clientes
- **Mudou:** nova coluna numérica, alinhada à direita, 100px. Lookup reverso da base de Processos. Zero em cinza, ≥1 em peso 600.
- **Por quê:** estratégico para distinguir clientes ativos de históricos.
- **Código:** `services/notion_repo.py::list_clientes()` — JOIN com count agrupado. `pages/clientes.py::COLUMNS` — adicionar.

### 3.7 Coluna "Sucessor de" em Clientes
- **Mudou:** quando preenchida, exibe `↳ Nome do sucedido (†)` como chip-rel. "Sucedido por N" como chip clicável quando o cliente é sucedido por outros.
- **Código:** `widgets/cells/relation_cell.py::SuccessorCell`. Schema do Notion já tem o campo (relação reflexiva).

### 3.8 Coluna "Processo pai" em Processos
- **Mudou:** quando preenchido (linha de recurso), CNJ exibido com `↳ <CNJ pai>` em cima e CNJ próprio embaixo, monospace menor. Linha visualmente identificada como dependente.
- **Código:** `widgets/cells/cnj_cell.py::CnjCell::paintEvent` — duas linhas; `notion_repo.py` já retorna `parent_cnj`.

### 3.9 Filtros multivalor
- **Mudou:** chip count "2 filtros ativos" na barra acima da tabela; chip individual por coluna filtrada com botão `×`; "Limpar todos" como link.
- **Estado simultâneo:** "selecionado + filtrado" coexistem em colunas diferentes (ícone `${ic.filter}` ganha estado `.active`).
- **Código:** `widgets/filter_bar.py` (novo). `widgets/base_table.py::FilterController`.

### 3.10 Aba "Comentários" no painel direito
- **Mudou:** reservar aba mesmo que vazia hoje. Pip cinza quando não há comentários.
- **Por quê:** funcionalidade futura (Notion comments) não pode aparecer como gambiarra depois.
- **Código:** `widgets/detail_panel.py::TABS` — adicionar `Comentários` com placeholder "Sem comentários ainda".

---

## 4 · Edição inline & barra flutuante

### 4.1 Posicionamento
- **Mudou:** barra flutuante posicionada **bottom-right da área de conteúdo** (não da janela), 16px de margem.
- **Código:** `widgets/dirty_bar.py::DirtyBar` — pai = `MainContent`, não `MainWindow`.

### 4.2 Texto do contador
- **Mudou:** "3 alterações pendentes em **Processos**" — incluir sempre o nome da base.
- **Texto secundário:** primeiros 2-3 alvos + "+N".
- **Código:** `widgets/dirty_bar.py::set_count(n, base_name, sample_titles)`.

### 4.3 Botões
- **Mudou:** Salvar = primary navy. Descartar = link/ghost (não secondary com borda).
- **Código:** `theme/qss_*.py::DirtyBar` — restyle.

### 4.4 Célula dirty
- **Mudou:** mantida cor `#FFF9C4` no claro. No escuro: `rgba(255,217,90,0.18)` com inset-shadow `--warning` 2px à esquerda.
- **Código:** `theme/qss_dark.py::Table::item[dirty="true"]`.

---

## 5 · Importar — etapa 2

### 5.1 Stepper visível
- **Mudou:** 3 passos — Origem (✓) · Mapear & validar (atual) · Confirmar.
- **Código:** `widgets/stepper.py::Stepper(steps, current)`.

### 5.2 Banner de erros/conflitos no topo
- **Mudou:** banner amarelo "1 linha com erro · 2 conflitos — corrija ou ignore antes de continuar".
- **Resumo na barra:** chips "9 ok · 2 conflitos · 1 erro" alinhados à direita.

### 5.3 Linhas com estado
- **`row-err`:** fundo `rgba(154,59,59,0.06)`, ícone vermelho na primeira célula, chip "CNJ inválido".
- **`row-warn`:** fundo `rgba(181,138,63,0.08)`, chip "Já existe · atualizar?".
- **OK:** chip verde com check.
- **Código:** `pages/importar.py::ImportPreviewTable` — coluna virtual "Validação" derivada do payload.

### 5.4 Continuar com erros
- **Mudou:** botão Continuar fica habilitado, mas a contagem mostra "9 prontas para importar". A linha com erro vai ser pulada.

---

## 6 · Logs · modal de reversão

### 6.1 Tabela
- **Mudou:** colunas Quando (mono) · Usuário · Base · Registro · Propriedade · Alteração (antes → depois) · Ações.
- **Eventos revertidos:** chip cinza "Revertido" no lugar do botão.
- **Código:** `pages/logs.py`.

### 6.2 Modal
- **Backdrop:** cobre **toda a janela** (`QDialog` modal-window com flag `Qt.WindowModality.ApplicationModal`). V1 era subwindow, deixava sidebar interativa.
- **Largura:** 480px, centralizado.
- **Conteúdo:**
  - Eyebrow "Confirmação destrutiva" + título "Reverter alteração?"
  - Resumo: "Reverter alteração feita por **Déborah** em **27/04 14:32**: Status do processo `0726654-71.2024.8.07.0001`"
  - Diff em tabela: Propriedade · Antes (vermelho riscado) · Depois (verde).
  - Disclaimer: "A alteração será desfeita no Notion e registrada como evento 'Reversão'."
- **Botões:** "Cancelar" (Esc) à esquerda, "Confirmar reversão" (danger) à direita.
- **Código:** `widgets/revert_dialog.py::RevertDialog(log_entry)`.

---

## 7 · Configurações

### 7.1 Tema "Auto"
- Ver §0.3.

### 7.2 Atalhos editáveis
- **Mudou:** clicar num atalho ativa modo captura — fundo acento-soft, texto "Pressione a combinação…", as kbd-keys ficam em destaque acento. Enter salva, Esc cancela. Após salvar, chip "✓ Salvo" inline por 2s.
- **Código:** `widgets/shortcut_editor.py::ShortcutCapture` — usar `QKeySequenceEdit`.

### 7.3 Tabela de usuários
- **Mudou:** linha do usuário ativo destacada com fundo `--accent-soft`, peso 600 e chip "Você" alinhado à direita.
- **Código:** `widgets/users_table.py::row_for(user)` — aplicar property `you=true` quando `user.id==current_user.id`.

### 7.4 Densidade
- **Mudou:** novo controle Compacto/Confortável (segmented). Compacto é default.

---

## 8 · Paleta de comandos

### 8.1 Backdrop
- **Mudou:** backdrop semi-opaco `rgba(20,36,48,0.30)` no claro, `rgba(0,0,0,0.55)` no escuro com `backdrop-filter:blur(2px)` quando suportado.
- **Posicionamento:** topo 14% da janela, 540px largura, centralizado horizontalmente.
- **Código:** `widgets/command_palette.py`.

### 8.2 Estrutura de resultados
- **Mudou:** seções "Ações" e "Resultados (N)" com label uppercase. Match do termo grifado em acento.
- **Linhas:** ícone · label · contexto (right-aligned, uppercase pequeno) · atalho/Enter.
- **Estado active:** fundo `--accent-soft`, ícone tinge.

---

## 9 · Empty state (NOVO)

### 9.1 Quando aparece
- Base **inteira** vazia (após sync que retornou 0 registros). **NÃO** aparece quando há dados mas filtros zeraram a lista — esse caso usa o estado "sem resultados após filtro" da V1.

### 9.2 Conteúdo
- Ícone neutro (inbox) em círculo cinza-quente.
- "Nenhum registro nesta base ainda"
- "A última sincronização não retornou tarefas. Isso pode ser normal..."
- Botão primário "Sincronizar agora" + secundário "Criar primeira tarefa".
- Rodapé: "Última sync: há 1 min · 0 registros · sem erros".

### 9.3 Toolbar
- Search e botão "Nova" ficam **disabled** visualmente para indicar que não há sobre o que agir.

### 9.4 Código
- `widgets/empty_state.py::EmptyState(base_name, on_sync, on_create)`.
- `pages/base_page.py` — bifurcar `if rows.is_empty(after_filter=False): show_empty()`.

---

## 10 · Sync individual — toast

- **Mudou:** ao sincronizar uma base só, toast no canto inferior-direito: "**Processos**: 1.108 registros sincronizados (5 novos, 12 atualizados)". Auto-dismiss 4s.
- **Código:** `widgets/toast.py::SyncSummaryToast(base, total, new, updated)`.

---

## Sugestões para V3 (fora do escopo desta entrega)

- **Comentários do Notion** (§3.10) — aba reservada, mas a integração de fato fica para V3.
- **Drag-to-reorder** de colunas customizadas pelo usuário, com persistência por usuário.
- **Visão "Kanban"** opcional para Tarefas (mesma base, layout alternativo).
- **Exportação** — botão "Exportar visão atual" (CSV/XLSX) com filtros aplicados.
- **Notificações de prazo** — push do Windows quando prazo crítico ≤ 48h.
- **Visões salvas por usuário** (filtros + ordenação + colunas) com nomes — ex: "Meus processos · TRT/10".
- **Modo offline real** com fila de PATCHes pendentes que dispara quando volta online.

---

*Documento gerado para a V2 · 27/04/2026 · Próxima sessão Claude Code aplica em `notion_rpadv/`.*
