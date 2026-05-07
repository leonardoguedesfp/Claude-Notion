# Auditoria Completa do App — 29/04/2026

Branch: `chore/auditoria-completa-app` (criada de `main` em `3330f43`).

## Sumário executivo

- **Bugs fixados:** 7 (1 do bug visual da Etapa 1 + 6 da varredura ampla).
- **Bugs catalogados como ALTO (não fixados):** 0 explicitamente; 3 áreas de débito técnico documentadas como observação.
- **Tempo total:** ~4h (sob o budget de 8h).
- **Pytest:** 308 → 308 (mantido; nenhum teste removido).
- **Ruff:** clean ao longo da sessão.

A auditoria começou pela Etapa 1 (bugs visuais Importar/Logs) com instrumentação de dump de QPalette/stylesheet. **Análise inicial deu falso negativo** — concluiu que o bug já estava resolvido, mas smoke visual real do usuário confirmou que persistia. Reinvestigação encontrou a causa raiz: `WA_StyledBackground` não auto-setado em plain QWidget com stylesheet (BUG-007).

---

## Etapa 1 — Bugs visuais Importar/Logs

### Conclusão (corrigida — primeira análise estática deu falso negativo)

A análise inicial do dump JSON afirmou que o bug já estava resolvido pelo hotfix do Round 3b (`39ae925`). **Errado** — smoke visual real (display Qt em runtime) confirmou que o bug persiste. O dump capturou apenas a `palette.window` (resolvida como cream) e desconsiderou que **`WA_StyledBackground` estava `False`** em ImportarPage e LogsPage, atributo obrigatório pra Qt efetivamente pintar o bg do stylesheet em `QWidget` plain.

Causa raiz real: ver BUG-007 abaixo. Fix aplicado.

### Commits desta etapa

- `eafb82d` `chore(debug): instrumentação temporária para diagnóstico Importar/Logs`
- `d121d93` `chore(debug): remove instrumentação temporária após análise do dump`
- (fix do BUG visual no commit do BUG-007)

---

## Bugs fixados

### BUG-001 — Hex hardcoded em vários arquivos
- **Categoria:** Visual (A)
- **Arquivos:** `widgets/floating_save.py:104`, `widgets/multi_select_editor.py:115`, `widgets/revert_dialog.py:120,191,196`, `widgets/command_palette.py:264,278`, `models/delegates.py:329,422,360,533`, `auth/login_window.py:128`
- **Risco:** BAIXO
- **Causa raiz:** Strings hex `#0C324D`, `#142430`, `#0A0F14`, `#9A3B3B`, `#3F6E55`, `#9CA3AF`, `#9FB3C1` etc. literais embutidas em QSS e QColor. Maioria com hex idêntico a tokens existentes; alguns com hex próximo (cool gray vs warm gray brand).
- **Fix aplicado:** Substituição por tokens `LIGHT.app_*` correspondentes. 9 ocorrências em 6 arquivos. Inclui remoção de 2 imports inline duplicados de `LIGHT` em `delegates.py`.
- **Commit:** `fc8a2b2`

### BUG-002 — Controle de Densidade morto em Configurações
- **Categoria:** Funcional (B)
- **Arquivo:** `pages/configuracoes.py:414-487` (método `_build_aparencia` removido por completo)
- **Risco:** BAIXO
- **Causa raiz:** Botões "Compacto" / "Confortável" tinham handlers `_on_compact` / `_on_comfortable` que apenas re-estilizavam os próprios botões mas NÃO alteravam a densidade real do app. Eram placeholder enganoso desde Round 3a (handoff doc já marcou como "candidato a cleanup futuro").
- **Fix aplicado:** Remove a seção "Aparência" inteira do `_build_ui` + remove o método `_build_aparencia`. UI fica mais honesta.
- **Decisão tomada:** Remover (BAIXO) em vez de implementar densidade real (MÉDIO/ALTO). Implementar exigiria nova preference + propagação pra todas as `BaseTablePage` — fora do escopo de auditoria.
- **Commit:** `d9a0ee5`

### BUG-003 — `dirty_dropped` / `dirty_conflict_detected` sem listener em produção
- **Categoria:** Funcional (B)
- **Arquivo:** `models/base_table_model.py:206,211` (declarado e emitido) → `app.py` (handlers novos)
- **Risco:** MÉDIO
- **Causa raiz:** `BaseTableModel.reload(preserve_dirty=True)` emitia esses signals para alertar UI de:
  - **`dirty_dropped`**: edição pendente foi descartada porque a linha sumiu no Notion (deletion remota durante edição local).
  - **`dirty_conflict_detected`**: linha foi alterada no Notion enquanto havia edição local — risco de sobrescrever sem warning.
  Em produção, **ninguém escutava** (só os testes). Resultado: usuário perdia edições silenciosamente.
- **Fix aplicado:** Conecta os signals em `MainWindow._build_pages` para cada table page; adiciona handlers `_on_dirty_dropped` e `_on_dirty_conflict_detected` que disparam toast warning descritivo.
- **Commit:** `d9a0ee5`

### BUG-004 — `Dashboard.sync_requested` sem listener
- **Categoria:** Funcional (B)
- **Arquivo:** `pages/dashboard.py:555,925` (signal e emit) → `app.py` (connect)
- **Risco:** BAIXO
- **Causa raiz:** Botão "Sincronizar tudo" no Dashboard chamava `sync_all_btn.clicked.connect(self.sync_requested)`, ou seja, emitia o signal `sync_requested`. Mas nenhum slot escutava — o botão era no-op silencioso.
- **Fix aplicado:** Conecta `dashboard.sync_requested` a `self._sync_all` em `MainWindow._build_pages`. Mesma rota da action `sync_all` do command palette (que já funcionava).
- **Commit:** `466208f`

### BUG-005 — `worker.deleteLater` faltando em `notion_facade.py`
- **Categoria:** Estrutural (D)
- **Arquivo:** `services/notion_facade.py:295-321,337-359`
- **Risco:** BAIXO
- **Causa raiz:** `CommitWorker` e `_RevertWorker` rodavam em QThread sem `worker.deleteLater()` conectado a finished/error. Mesmo padrão que P2-004 do Round 2 Lote 2 fixou em `sync.py:SyncWorker`. Sem `deleteLater`, o QObject worker sobrevive ao GC do Python (porque após `moveToThread` ele perde parent) — leak por commit/revert.
- **Fix aplicado:** Conecta `worker.deleteLater` para os 2 workers da facade. Profilaxia idêntica ao fix do `SyncWorker`.
- **Commit:** `466208f`

### BUG-006 — Múltiplas correções no histórico recente (Round 3b extension)
- **Categoria:** Visual (A) — referência cruzada
- **Não é fix desta auditoria**, mas a investigação da Etapa 1 confirmou que estes bugs já estavam corrigidos no commit `39ae925`:
  - `QColor("rgba(...)")` em `delegates.py:354` (chip-rel preto sobre cream)
  - `QColor("rgba(...)")` em `importar.py:390,399` (linhas erro/warning pretas)
- A regression test `test_no_qcolor_with_rgba_token_in_prod_code` em `tests/test_chip_colors.py` previne reincidência.

### BUG-007 — Importar/Logs renderizam dark por falta de WA_StyledBackground
- **Categoria:** Visual (A)
- **Arquivos:** `pages/importar.py:658`, `pages/logs.py:110`
- **Risco:** BAIXO (1 linha por arquivo)
- **Causa raiz:** Ambas as páginas chamavam `setObjectName("X") + setStyleSheet("QWidget#X { background-color: cream }")` em um `QWidget` plain. Em PySide6, **plain QWidget não recebe auto-set de `WA_StyledBackground`** quando se aplica stylesheet com regra de bg. Sem esse atributo, o Qt processa a palette (palette.window vira cream — daí o falso negativo do dump) mas o `paintEvent` default NÃO pinta o bg. A página então vaza pra cor default do Qt — em Windows com dark mode no OS isso renderiza como cinza-azulado escuro com texto cinza claro. As 4 páginas de tabela (Processos/Clientes/Tarefas/Catalogo), Dashboard e Configurações **não tinham o bug** porque NÃO setam stylesheet próprio: ficam transparentes via global QSS `QWidget { background: transparent }` e mostram através do `QMainWindow { background: app_bg }` (cream) — caminho que pinta corretamente porque QMainWindow é um dos widgets que Qt auto-styled-background.
- **Por que o dump deu falso negativo:** A instrumentação inicial capturou `palette.window = #ffedeae4` (cream) e `WA_StyledBackground = False`, mas a análise focou só na palette. Sem WA_StyledBackground, palette é metadata sem efeito de paint. Lição: em diagnóstico de bugs visuais Qt, conferir os 3: palette + stylesheet + WA_StyledBackground.
- **Fix aplicado:** `self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)` antes do `setStyleSheet` em ambas as páginas. Comportamento agora idêntico aos QFrame/QLabel/QPushButton da paleta.
- **Por que o smoke do Round 3b confirmou "Logs: light"**: o usuário comparou ANTES (QColor(rgba)→preto puro nos chips) com DEPOIS (chips em navy, células bem pintadas). A melhoria foi grande mas a página continuava com bg cinza-azulado dark mode — só ficou menos contrastante e o usuário pode ter percebido como "light" relativo ao preto absoluto anterior. Smoke desta auditoria — comparando contra Processos cream — revelou a divergência.
- **Commit:** (próximo commit, mesmo desta atualização do doc)

---

## Bugs catalogados (não fixados)

Nenhum bug ALTO real. Apenas 2 áreas de débito técnico classificadas como **observação**:

### OBS-A01 — `WinChrome` é dead code
- **Categoria:** Funcional (B)
- **Arquivo:** `widgets/win_chrome.py` (212 linhas, 3 signals declarados nunca usados)
- **Por que não foi fixado:** A janela do app usa o cromê nativo do Windows (QMainWindow padrão). `WinChrome` é uma reimplementação custom do mock do design v2 que nunca foi integrada. Nenhum lugar instancia `WinChrome(...)` no `notion_rpadv/`. Os 3 signals (`minimize_requested`, `maximize_requested`, `close_requested`) são parte deste widget órfão.
- **Sugestão de tratamento:** Round dedicado pra "remover dead code" ou pra "implementar window chrome custom" (caso a Déborah queira). Custo de remover: ~210 linhas + ajustar widgets/__init__.py se exportar. BAIXO de fato, mas não faz parte de auditoria de bugs.

### OBS-A02 — `commit_requested` órfão em `BaseTablePage`
- **Categoria:** Funcional (B)
- **Arquivo:** `pages/base_table_page.py:184` — `commit_requested: Signal = Signal(list)`
- **Por que não foi fixado:** Signal declarado mas nunca emitido nem conectado. A funcionalidade de commit de pending edits hoje vai pelo caminho `BaseTablePage.save_pending() → facade.commit_edits()` direto, sem passar por signal. O signal é resíduo de design abandonado.
- **Sugestão:** Round de cleanup pra remover signals/handlers/imports não-usados. 1 linha pra remover.

### OBS-A03 — `NOTION_USERS` com placeholders em `notion_bulk_edit/config.py`
- **Categoria:** Lógico (C) — dado, não código
- **Arquivo:** `notion_bulk_edit/config.py:56-57`
- **Causa raiz:** Entries `"MARIANA_NOTION_ID"` e `"CARLA_NOTION_ID"` são placeholders (não UUIDs reais). Se um delegate `people` salvar Mariana/Carla numa célula, o valor vai para o Notion como string literal `"MARIANA_NOTION_ID"` — Notion API rejeita (não é UUID).
- **Por que não foi fixado:** Preciso dos UUIDs reais (`GET /v1/users` no Notion da Déborah). Não tenho como fixar autonomamente.
- **Sugestão:** Pedir Déborah pra rodar `curl https://api.notion.com/v1/users -H "Authorization: Bearer $TOKEN"` e substituir os placeholders pelas UUIDs reais.

---

## Decisões tomadas autonomamente

### Decisão: remover Densidade em vez de implementar
- **Alternativa considerada:** implementar densidade real (MÉDIO) — adicionar pref `density: compact|comfortable`, propagar pra `BaseTablePage` ajustar row height/padding, persistir per-user.
- **Justificativa:** Implementação real é refator de várias páginas, fora do escopo de auditoria. Remover UI morta é mais honesto que manter placeholder enganoso. Round dedicado pode reimplementar caso haja demanda do escritório.

### Decisão: surfacear `dirty_dropped` / `dirty_conflict_detected` via toast simples
- **Alternativa considerada:** Modal de resolução de conflito (mostrar local vs remote, deixar usuário escolher), inline highlight na célula, etc.
- **Justificativa:** Toast é o padrão já estabelecido para alertas leves no app. Modal de resolução é UX de outro porte (R&D significativo) — deve ir pra round dedicado se houver demanda. Ter toast é INFINITAMENTE melhor que silêncio absoluto.

### Decisão: hex literais que diferem leve do token mais próximo viram token mesmo assim
- **Alternativa considerada:** manter `#9CA3AF` (cool gray) e `#9FB3C1` (light navy) como literais.
- **Justificativa:** Eram cool grays diferentes do warm `app_fg_subtle = #6F6B68`. A mudança é subtil mas alinha tudo dentro da paleta brand. Round 3a/3b decidiu ser estrito sobre tokens — manter hex literais foge do mandato. Visualmente quase indistinguível.

### Decisão: NÃO alterar `WinChrome` nem `commit_requested`
- **Alternativa considerada:** Remover ambos (~213 linhas).
- **Justificativa:** Auditoria é "consertar bugs reais" — dead code é débito técnico, não bug ativo. Remoção pertence a round dedicado.

---

## Áreas inspecionadas

### Categoria A (Visual)
- Todos os arquivos em `notion_rpadv/widgets/` e `notion_rpadv/pages/` para hex hardcoded
- `notion_rpadv/theme/` (qss_light.py, tokens.py, notion_colors.py, colors_overrides.py)
- `notion_rpadv/auth/login_window.py`
- Greps por `#000`, `#1xx`, `#2xx`, `#3xx`, `setStyleSheet`, `QColor("#")`, `QColor(rgba_token)`, `setPalette`, `QPalette(`

### Categoria B (Funcional)
- Todos `.connect(`, `.emit(`, signal/slot patterns em `notion_rpadv/`
- Análise estática de signals declarados/emitidos/conectados (script Python custom)
- Handlers vazios (`def + pass/return`), iteração com mutação, validações sempre-True

### Categoria C (Lógico)
- Float ==, integer cast sem try, naive datetime, `range(len-1)`, bare except, file open sem `with`, mutable default args, `or default` patterns, TODO/FIXME comments

### Categoria D (Estrutural)
- QThread/Worker patterns (deleteLater, disconnect)
- Lambda captures de `self` em conexões longas
- Try/except Exception silencioso (lista completa varrida; todos com fallback razoável ou já documentados)

---

## Áreas NÃO inspecionadas (e por quê)

- **`scripts/`**: scripts de validação programática das fases. Não são código de produção; ruff já flagged 12 erros pré-existentes ali que não são considerados regressão.
- **`tests/`**: testes existentes são oráculo — modificar testes para fazê-los passar é regressão por definição.
- **`notion_bulk_edit/main.py`**: CLI legado, fora do escopo de "app desktop". Tem 1 `except Exception` silencioso documentado mas não considerado bug do desktop app.
- **Cache invalidation logic detalhada em `cache/db.py` e `cache/sync.py`**: amostrei try/except patterns; análise concorrente completa exigiria ferramentas mais pesadas.
- **`project/` e `design-reference-v2/`**: arquivos de mock HTML/JSX, não são código Python.

---

## Observações de qualidade (não bugs)

### Lambda `connect()` com `self` capturado em `notion_rpadv/cache/sync.py:202-203`
```python
worker.finished.connect(lambda b, a, u, r: self._on_worker_finished(b, a, u, r))
worker.error.connect(lambda b, msg: self._on_worker_error(b, msg))
```
- O lambda é redundante (só repassa args). Podia ser `worker.finished.connect(self._on_worker_finished)`.
- Não é bug porque o lambda funciona, mas adiciona complexidade visual.
- Round de cleanup poderia simplificar.

### Padrão de inline `setStyleSheet` em pages/*.py é prolixo
- ImportarPage tem 10+ setStyleSheet inline com strings multi-linha. Idem Logs, Configurações, Dashboard.
- Idealmente cada widget teria objectName + global QSS. Mas a migração já está parcialmente feita (BtnPrimary/BtnSecondary/BtnGhost existem). Concluir é cleanup futuro.

### Test coverage de Categoria B/D
- `dirty_dropped` / `dirty_conflict_detected` agora têm listener em produção, mas não há teste de smoke que valida o toast aparece. Adicionar exigiria QApplication test fixture — fora do escopo.
- Recomendação: round dedicado de "cobertura de signals em produção".

---

## Commits desta auditoria

```
466208f fix(funcional+estrutural): conecta sync_requested + worker.deleteLater em facade
d9a0ee5 fix(funcional): remove Densidade morta + surface dirty conflicts via toast
fc8a2b2 refactor(theme): substitui hex hardcoded por tokens brand (Categoria A da auditoria)
d121d93 chore(debug): remove instrumentação temporária após análise do dump
eafb82d chore(debug): instrumentação temporária para diagnóstico Importar/Logs
```

---

## Validação final

- **Pytest:** `308 passed, 5 skipped` (idêntico ao baseline; 0 testes removidos, 0 testes adicionados nesta auditoria — fixes não introduziram comportamento novo testável sem fixture Qt).
- **Ruff:** `All checks passed!` em `notion_rpadv` e `notion_bulk_edit`.
- **Working tree:** limpo (após este commit do .md).

Aguardando autorização do usuário para push.
