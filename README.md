# CODING AGENTS: READ THIS FIRST

This is a **handoff bundle** from Claude Design (claude.ai/design).

A user mocked up designs in HTML/CSS/JS using an AI design tool, then exported this bundle so a coding agent can implement the designs for real.

## What you should do — IMPORTANT

**Read the chat transcripts first.** There are 1 chat transcript(s) in `chats/`. The transcripts show the full back-and-forth between the user and the design assistant — they tell you **what the user actually wants** and **where they landed** after iterating. Don't skip them. The final HTML files are the output, but the chat is where the intent lives.

**Find the primary design file under `project/` and read it top to bottom.** The chat transcripts will tell you which file the user was last iterating on. Then **follow its imports**: open every file it pulls in (shared components, CSS, scripts) so you understand how the pieces fit together before you start implementing.

**If anything is ambiguous, ask the user to confirm before you start implementing.** It's much cheaper to clarify scope up front than to build the wrong thing.

## About the design files

The design medium is **HTML/CSS/JS** — these are prototypes, not production code. Your job is to **recreate them pixel-perfectly** in whatever technology makes sense for the target codebase (React, Vue, native, whatever fits). Match the visual output; don't copy the prototype's internal structure unless it happens to fit.

**Don't render these files in a browser or take screenshots unless the user asks you to.** Everything you need — dimensions, colors, layout rules — is spelled out in the source. Read the HTML and CSS directly; a screenshot won't tell you anything they don't.

## Bundle contents

- `README.md` — this file
- `chats/` — conversation transcripts (read these!)
- `project/` — the `Integração Claude-Notion` project files (HTML prototypes, assets, components)


---

## Leitor DJE (Round 7 — Fase 1)

Aba do app que baixa publicações do **DJEN — Diário de Justiça Eletrônico
Nacional** (API pública `comunicaapi.pje.jus.br/api/v1/comunicacao`) pros
12 advogados do escritório e empilha tudo num único `.xlsx`.

### Como usar

1. Abra o app, navegue na sidebar até **Leitor DJE** (entre "Exportar dados" e "Logs").
2. Escolha **Data inicial** e **Data final** (default: ambas em ontem). Pode ser o mesmo dia.
3. Clique **Baixar publicações**.
4. Acompanhe o progresso na barra (12 etapas) e na área de log abaixo.
5. Ao terminar, clique **Abrir arquivo gerado** ou **Abrir pasta**.

### O que ele faz

- Para cada um dos 12 advogados (lista hardcoded em
  [notion_rpadv/services/dje_advogados.py](notion_rpadv/services/dje_advogados.py)),
  busca por OAB/DF no DJEN.
- Pagina até esgotar (até 100 itens por página).
- Empilha tudo num xlsx em
  `Publicacoes_DJEN_{dd.mm.aa_inicio}_a_{dd.mm.aa_fim}_v{N}.xlsx`.
  O `N` auto-incrementa pra nunca sobrescrever (rodar 2× = `v1` e `v2`).
- Coluna `advogado_consultado` é injetada como **primeira coluna** —
  identifica de qual advogado do escritório veio cada publicação
  (mesma publicação aparece N vezes em casos de litisconsórcio interno).
- Demais colunas vêm na ordem do JSON da API DJEN, sem renomear nem
  traduzir. Arrays viram JSON string com acentos preservados.

### Configuração

- **Pasta de destino**: configurável via `QSettings` (`leitor_dje/output_dir`).
  Default: caminho do Leonardo no SharePoint do escritório
  (`...\Reclamações Trabalhistas\Ferramentas\Leitor DJE`).
  Se o caminho não existir/não puder ser criado no PC corrente, o app
  abre `QFileDialog` no momento do export pra usuário escolher — a
  escolha é persistida.
- **Lista de advogados**: editar
  [notion_rpadv/services/dje_advogados.py](notion_rpadv/services/dje_advogados.py)
  (Python module). Sem UI de admin nesta fase.

### Tratamento de erros

- Rate limit: **1 req/s** entre todas as requisições (incluindo entre
  páginas do mesmo advogado).
- Retry para HTTP 429/503/timeout/erro de rede: **3 tentativas totais**
  com esperas de **2s e 8s**. Última falha → registra no log da UI e
  segue pro próximo advogado (varredura inteira não aborta).
- HTTP 4xx (≠ 429) → registra corpo da resposta e segue (sem retry).
- Falha em ≥ 1 advogado → arquivo é gerado mesmo assim (incompleto), com
  banner amarelo listando os advogados afetados.

### Limitações desta fase

- Não trata o campo `texto` (mantém HTML/escapes brutos).
- Não cria tarefas no Notion.
- Não envia e-mail de alerta.
- Não classifica por relevância.
- Não busca por número de processo (só por OAB).
- Não deduplica — publicações com litisconsórcio interno do escritório
  aparecem N vezes (uma por advogado consultado). A coluna `hash` da
  resposta é a chave única estável; Fase 2 vai deduplicar via ela.
