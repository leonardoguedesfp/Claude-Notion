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

## Leitor DJE (Round 7)

Aba do app que baixa publicações do **DJEN — Diário de Justiça Eletrônico
Nacional** (API pública `comunicaapi.pje.jus.br/api/v1/comunicacao`) pros
6 advogados do escritório (Fase 2.1) e gera um `.xlsx` consolidado.

### Advogados consultados (Fase 2.1, 2026-05-01)

| Advogado | OAB |
|---|---|
| Ricardo Luiz Rodrigues da Fonseca Passos | 15523/DF |
| Leonardo Guedes da Fonseca Passos | 36129/DF |
| Vitor Guedes da Fonseca Passos | 48468/DF |
| Cecília Maria Lapetina Chiaratto | 20120/DF |
| Samantha Lais Soares Mickievicz | 38809/DF |
| Deborah Nascimento de Castro | 75799/DF |

A lista anterior (12 advogados) foi reduzida para 6 em 2026-05-01 após
smoke real em janela longa (01/01→30/04/2026) gerar 429 catastrófico em
7 dos 12. Os 6 desativados ficam comentados em
[notion_rpadv/services/dje_advogados.py](notion_rpadv/services/dje_advogados.py)
— para reativar um deles, descomentar a linha correspondente.

### Como usar

1. Abra o app, navegue na sidebar até **Leitor DJE** (entre "Exportar dados" e "Logs").
2. Escolha **Data inicial** e **Data final** (default: ambas em ontem). Pode ser o mesmo dia.
3. Clique **Baixar publicações**.
4. Acompanhe o progresso na barra (6 etapas — uma por advogado) e na área de log abaixo.
5. Ao terminar, clique **Abrir arquivo gerado** ou **Abrir pasta**.

> **Janelas longas (> 30 dias)** podem demorar vários minutos por
> advogado. A pausa entre requisições é de 2s (Fase 2.1, era 1s) e o
> cliente honra o header `Retry-After` quando o servidor pede uma espera
> explícita no 429 (cap em 60s pra evitar travar a UI por minutos).

### O que ele faz

- Para cada um dos 6 advogados ativos (lista hardcoded em
  [notion_rpadv/services/dje_advogados.py](notion_rpadv/services/dje_advogados.py)),
  busca por OAB/DF no DJEN.
- Pagina até esgotar (até 100 itens por página).
- Aplica pipeline de transformação ([notion_rpadv/services/dje_transform.py](notion_rpadv/services/dje_transform.py)):
  dedup por `id`, enriquecimento com coluna `observacoes`, strip de HTML
  no campo `texto`, normalização de encoding misto, drop de colunas
  redundantes, ordenação por tribunal+data.
- Salva em `Publicacoes_DJEN_{dd.mm.aa_inicio}_a_{dd.mm.aa_fim}_v{N}.xlsx`.
  O `N` auto-incrementa pra nunca sobrescrever (rodar 2× = `v1` e `v2`).

### Formato do arquivo (Fase 2)

**1 linha por publicação única**, com **20 colunas em ordem fixa**:

| # | Coluna | O que tem |
|---|---|---|
| 1 | `advogados_consultados` | Nomes dos advogados do escritório intimados naquela publicação, separados por `; ` em ordem alfabética. Em caso de litisconsórcio interno (Ricardo + Leonardo no mesmo processo), aparecem os dois aqui |
| 2 | `observacoes` | **Vazio quando não há nada estranho.** Sinaliza anomalias: publicação inativa/cancelada, status fora do habitual, ausência de Ricardo (15523/DF) ou Leonardo (36129/DF) na lista de advogados intimados. Múltiplas mensagens unidas por `\| ` |
| 3 | `id` | Chave numérica única no DJEN |
| 4 | `hash` | Chave alternativa estável |
| 5 | `siglaTribunal` | TRT10, STF, STJ, TST, etc. |
| 6 | `data_disponibilizacao` | ISO `2026-04-30` |
| 7-9 | `numeroprocessocommascara`, `numero_processo`, `tipoComunicacao` | Identificação processual |
| 10 | `tipoDocumento` | Despacho, Intimação, etc. |
| 11-12 | `nomeOrgao`, `idOrgao` | Vara/turma onde tramita |
| 13-14 | `nomeClasse`, `codigoClasse` | Tipo de ação |
| 15 | `numeroComunicacao` | Sequência interna do tribunal |
| 16 | `texto` | Corpo da publicação **sem HTML** (Fase 2 limpa `<br>`/`<a>`/tabelas) |
| 17 | `link` | URL da publicação no portal do tribunal |
| 18-19 | `destinatarios`, `destinatarioadvogados` | Partes e advogados (JSON string com acentos) |
| 20 | `datadisponibilizacao` | Mesma data em formato BR `30/04/2026` |

**Removidas em relação à F1**: `advogado_consultado` (singular, virou plural),
`ativo`, `status`, `meio`, `meiocompleto`, `motivo_cancelamento`,
`data_cancelamento` (qualquer divergência delas vai pra `observacoes`).

**Ordenação final**: por `siglaTribunal` ASC, depois `data_disponibilizacao`
DESC (mais recente primeiro dentro de cada tribunal).

### Coluna `observacoes` — quando dispara

A coluna sinaliza dois grupos de anomalia:

**Regra A — campos que costumam ser constantes mas variaram:**
- `Publicação inativa (ativo=False) — verificar se foi cancelada ou substituída`
- `Status diferente do habitual: 'C' (esperado: 'P' = publicada)`
- `Meio diferente do habitual: 'X' (esperado: 'D' = diário)`
- `Meio completo diferente do habitual: '<valor>'`
- `Motivo de cancelamento informado: <texto>`
- `Data de cancelamento informada: <data>`

**Regra B — sócios fundadores ausentes** (Ricardo OAB 15523/DF, Leonardo OAB 36129/DF):
- `Leonardo (36129/DF) não consta entre os advogados intimados`
- `Ricardo (15523/DF) não consta entre os advogados intimados`
- `Nem Ricardo (15523/DF) nem Leonardo (36129/DF) constam entre os advogados intimados`

Linhas sem anomalia → `observacoes` é string vazia. Múltiplas mensagens
unidas por ` | ` (Regra A primeiro, Regra B depois).

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

- Rate limit: **2 req/s** entre todas as requisições (Fase 2.1, era 1s),
  incluindo entre páginas do mesmo advogado.
- Retry para HTTP 429/503/timeout/erro de rede: **3 tentativas totais**
  com esperas de **2s e 8s**. Última falha → registra no log da UI e
  segue pro próximo advogado (varredura inteira não aborta).
- 429 com header `Retry-After: <segundos>` → cliente honra o valor do
  servidor em vez do backoff fixo, capado em **60s** pra evitar travar
  a UI (Fase 2.1).
- HTTP 4xx (≠ 429) → registra corpo da resposta e segue (sem retry).
- Falha em ≥ 1 advogado → arquivo é gerado mesmo assim (incompleto), com
  banner amarelo listando os advogados afetados.
- Caracteres de controle Unicode (incluindo o bloco "Control Pictures"
  U+2400–U+243F) são **removidos automaticamente** antes da escrita
  (Fase 2.1) — defesa contra mojibake do upstream que travava o exporter
  com `IllegalCharacterError`. Defesa em 2 camadas: sanitize no transform
  + try/except por linha no exporter.
- Linhas que ainda assim falhem na escrita são **puladas individualmente**
  (não derrubam o arquivo inteiro) e contabilizadas no banner final
  ("M linha(s) com caractere inválido foram puladas"). Detalhes (até 10
  linhas) aparecem na área de log da UI; acima do cap, log do sistema
  guarda o resto.
- Divergência entre duplicatas de mesmo `id` (campos não-advogado) →
  warning no logger `dje.transform`, primeira ocorrência mantida.

### Não-escopo (Fase 3+)

- Carga das publicações no Notion (criação de tarefas).
- Alertas por e-mail.
- Classificação por relevância.
- Busca por número de processo.
- Captação de TJSP/STF (tribunais não cobertos pelo DJEN).
