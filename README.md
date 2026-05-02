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

A aba abre em **modo padrão** (uso diário) e tem um link "Modo personalizado →" pra alternar.

**Modo padrão** — captura só o delta desde a última execução:
1. Abra o app, navegue na sidebar até **Leitor DJE**.
2. Clique **Baixar publicações novas**.
3. **Primeira execução:** modal pede confirmação pra fazer a carga inicial desde 01/01/2026 (15-20 minutos). Confirme.
4. **Execuções seguintes:** o app lê o watermark do SQLite e varre só desde `cursor + 1 dia` até hoje.
5. Acompanhe o progresso e clique **Abrir arquivo gerado** / **Abrir histórico completo** / **Abrir pasta** ao final.

**Modo personalizado** (link superior direito) — período custom + subset de advogados:
1. Escolha **Data inicial** e **Data final**.
2. Marque/desmarque os 6 advogados do escritório (todos marcados por default).
3. **Outras OABs**: clique **+ Adicionar OAB externa** e preencha nome, OAB e UF pra cada externa que quiser pesquisar.
4. Clique **Baixar período personalizado**. Modo manual **não atualiza** o watermark (o cache continua do mesmo ponto que estava).

**Cancelar**: botão aparece ao lado durante a varredura. Publicações já captadas são salvas no SQLite e no Excel parcial; watermark **só é atualizado em sucesso completo do modo padrão**.

> **Janelas longas (> 31 dias)** são automaticamente divididas em
> sub-janelas mensais (jan/26, fev/26, ...) pra reduzir paginação
> profunda no backend do DJEN — descoberta da Fase 2.2 após smoke real
> identificar 429 catastrófico em paginação > 20. Sub-janelas que
> falham na 1ª passada são reagendadas com pausa de 30s (retry diferido).
> A pausa entre requisições é de 2s (Fase 2.1, era 1s) e o cliente
> honra o header `Retry-After` quando o servidor pede uma espera
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

### Formato do arquivo (Fase 3)

Cada execução gera/atualiza **dois Excel** na mesma pasta:

- `Publicacoes_DJEN_{dd.mm.aa_inicio}_a_{dd.mm.aa_fim}_v{N}.xlsx` —
  versionado, contém **só as publicações inseridas nesta execução**
  (delta novo).
- `Historico_DJEN_completo.xlsx` — **path fixo, sobrescrito atomicamente**
  ao final de cada execução. Contém **tudo** que está no SQLite. Se você
  abrir esse arquivo no Excel quando a varredura tentar regravar, o app
  registra warning e segue (Excel-de-execução é gerado normalmente).

Ambos seguem o mesmo schema canônico: **1 linha por publicação única**,
**21 colunas em ordem fixa** (Fase 3):

| # | Coluna | O que tem |
|---|---|---|
| 1 | `advogados_consultados_escritorio` | Advogados do escritório intimados naquela publicação (renomeada de `advogados_consultados` na Fase 3 pra distinguir de externos). Separador `; `, ordem alfabética |
| 2 | `observacoes` | **Vazio quando não há nada estranho.** Sinaliza anomalias: publicação inativa/cancelada, status fora do habitual, ausência de Ricardo (15523/DF) ou Leonardo (36129/DF). Múltiplas mensagens unidas por `\| ` |
| 3 | `id` | Chave numérica única no DJEN (`djen_id` no SQLite) |
| 4 | `hash` | Chave alternativa estável (UNIQUE no SQLite) |
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
| 21 | `oabs_externas_consultadas` | **Fase 3, nova.** Advogados externos pesquisados (modo manual) que aparecem nesta publicação. Vazia em modo padrão |

**Removidas em relação à F1**: `advogado_consultado` (singular, virou plural),
`ativo`, `status`, `meio`, `meiocompleto`, `motivo_cancelamento`,
`data_cancelamento` (qualquer divergência delas vai pra `observacoes`).

**Renomeada na Fase 3**: `advogados_consultados` → `advogados_consultados_escritorio`.
Excels antigos com o nome velho continuam legíveis pro humano; sem migração automática.

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

> **Nota Fase 2.2:** o smoke real de 01/01→01/05/2026 revelou que o código
> da Fase 2.1 lia `numero_oab`/`uf_oab` do nível raiz da entry de
> `destinatarioadvogados`, mas a estrutura real do DJEN aninha esses
> campos dentro de um sub-objeto `advogado` (`entry.advogado.numero_oab`).
> A Regra B disparava em 100% das publicações como falso-positivo. Fix
> da Fase 2.2: descer no nível correto, com fallback no nível raiz pra
> compat com fixtures legacy. Tolerância adicional a sufixo de letra
> na OAB (e.g. `"25200A"` da Mariana Knofel Jaguaribe) — comparamos
> só os dígitos.

### Configuração

- **Pasta de destino**: configurável via `QSettings` (`leitor_dje/output_dir`).
  Default: caminho do Leonardo no SharePoint do escritório
  (`...\Reclamações Trabalhistas\Ferramentas\Leitor DJE`). Se o caminho
  não existir/não puder ser criado, o app abre `QFileDialog` pra usuário
  escolher — a escolha é persistida. Os 2 Excels (versionado + histórico)
  ficam na mesma pasta.
- **Sticky data inicial modo manual**: `QSettings`
  (`leitor_dje/last_inicio_manual`) — preserva a última data inicial
  usada por até 30 dias.
- **Lista de advogados**: editar
  [notion_rpadv/services/dje_advogados.py](notion_rpadv/services/dje_advogados.py)
  (Python module). Sem UI de admin nesta fase.
- **Banco SQLite**: criado lazily na primeira varredura em
  `%APPDATA%\NotionRPADV\leitor_dje.db`. Não há configuração — caminho
  é derivado do mesmo helper de `cache.db` (`get_cache_dir()` em
  `notion_bulk_edit/config.py`).

### Tratamento de erros

- Rate limit: **2 req/s** entre todas as requisições (Fase 2.1, era 1s),
  incluindo entre páginas do mesmo advogado.
- Retry para HTTP 429/503/timeout/erro de rede: **3 tentativas totais**
  com esperas de **2s e 8s**. Última falha → registra no log da UI e
  segue pro próximo advogado (varredura inteira não aborta).
- 429 com header `Retry-After: <segundos>` → cliente honra o valor do
  servidor em vez do backoff fixo, capado em **60s** pra evitar travar
  a UI (Fase 2.1).
- 429 com `Retry-After: 0` → não espera, prossegue imediato (Fase 2.2).
- 429 com `Retry-After: -39` (negativo, bug do servidor DJEN observado
  no smoke real) → cai no fallback do backoff atual, com warning log
  específico classificando a origem (Fase 2.2).
- HTTP 4xx (≠ 429) → registra corpo da resposta e segue (sem retry).
- **Janela > 31 dias é dividida automaticamente em sub-janelas mensais**
  (Fase 2.2) — calendar-aligned (jan/26, fev/26, ...) — pra reduzir
  pressão de paginação profunda no backend. Reduz risco de 429
  catastrófico observado em janelas de 4 meses.
- **Retry diferido** (Fase 2.2): após a varredura principal de uma janela
  splitada, sub-janelas que falharam persistentemente são reagendadas
  UMA vez com pausa de **30s** entre cada — tempo pro backend recuperar
  bucket de rate limit. Se recuperar todas as falhas de um advogado,
  o erro é limpo; se ainda falhar, mantém. Retry diferido NÃO dispara
  em janelas curtas (≤ 31 dias).
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
- **Cancelamento da varredura** (Fase 2.2): botão "Cancelar" ao lado de
  "Baixar publicações" interrompe a varredura entre advogados, entre
  sub-janelas, ou entre páginas. NÃO interrompe HTTP em retry (pra não
  corromper paginação). Items já captados são salvos em arquivo parcial.
  Banner final mostra "Varredura cancelada pelo usuário. N publicações
  captadas até o ponto do cancelamento foram salvas".
- Divergência entre duplicatas de mesmo `id` (campos não-advogado) →
  warning no logger `dje.transform`, primeira ocorrência mantida.

### Cache local SQLite (Fase 3)

A Fase 3 introduz um **cache persistente local** que torna a varredura
incremental e elimina re-fetch de dados já baixados.

**Localização**: `%APPDATA%\NotionRPADV\leitor_dje.db` (mesma pasta de
`cache.db` e `audit.db`). Em Linux/Mac: `~/.notionrpadv/leitor_dje.db`.

**Schema** (2 tabelas):

- `djen_state` — singleton (1 linha):
  - `ultimo_cursor`: data da última publicação completa captada para
    qualquer advogado do escritório (watermark único).
  - `last_run`: timestamp UTC da última execução em modo padrão.
- `publicacoes` — todas as publicações já captadas:
  - `djen_id` (PK), `hash` (UNIQUE), `oabs_escritorio`, `oabs_externas`,
    `numero_processo`, `data_disponibilizacao`, `sigla_tribunal`,
    `payload_json` (JSON do payload original), `captured_at`,
    `captured_in_mode` (`padrao` | `manual`).
- Índices em `data_disponibilizacao`, `numero_processo`, `oabs_escritorio`.
- Pragmas: WAL, foreign_keys ON, synchronous=NORMAL.

**Watermark e modos**:
- **Modo padrão** atualiza `ultimo_cursor` somente quando a varredura
  completa com sucesso (sem cancelamento e sem erro persistente em
  advogado). A próxima execução varre `[cursor + 1 dia, hoje]`.
- **Modo manual** NUNCA toca o cursor — é uma janela ad-hoc fora da
  rotina (recuperar gap histórico, pesquisar OAB externa, etc).
- Cancelamento ou erro em modo padrão **não regride o cursor** mas as
  publicações já captadas entram no SQLite via `INSERT OR IGNORE` por
  `djen_id`. Próxima execução naturalmente pega o resto.

**Inspecionar o banco** (opcional): use uma ferramenta SQL externa
(DB Browser for SQLite, sqlite3 CLI, DBeaver). O Excel
`Historico_DJEN_completo.xlsx` é a vista oficial para uso humano.

### Não-escopo (Fase 4+)

- Carga das publicações no Notion (criação de tarefas).
- Alertas por e-mail.
- Captação automática em background (APScheduler / cron interno).
- UI de admin pra gerenciar lista do escritório (continua editando
  [dje_advogados.py](notion_rpadv/services/dje_advogados.py)).
- Painel de visualização do banco SQLite dentro do app (use o
  `Historico_DJEN_completo.xlsx` ou ferramenta SQL externa).
- Classificação por relevância.
- Busca por número de processo.
- Captação de TJSP/STF (tribunais não cobertos pelo DJEN).
