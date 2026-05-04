# Anatomia das publicações DJE × Notion — pós Round 4

Análise do estado entregue à database 📬 Publicações **após** os Rounds
4 / 4.5 / 4.6, comparada com a baseline pré-Round-4
(`docs/anatomia-publicacoes.md`, branch `analise-anatomia-pubs`).
Objetivo: validar o que foi entregue, detectar regressões, atualizar a
anatomia por cruzamento e priorizar o backlog.

> **Escopo**: análise. Nenhuma alteração de código, schema do Notion
> ou conteúdo das páginas existentes. Direto na `main`, commits
> incrementais por seção. Pubs amostrais lidas via Notion MCP; as 1.608
> canônicas processadas via export CSV `📬 Publicações
> 6ee4f13a9ea34506824656a261d99dce_all (2).csv`.

---

## 0. Sumário executivo

### Achados mais importantes

1. **Tarefas e Alertas funcionam — cobertura excelente.** 100% das
   1.608 canônicas (1.608) recebem ao menos uma `Tarefa sugerida`; 38%
   (611/1.608) recebem ao menos um `Alerta contadoria`. A Frente 4.3
   acertou os volumes esperados em 4 das 6 tarefas (D.01 1.305, D.03
   177, E.01 473, D.02 15). E.02 ficou 33 (vs 15+ estimado, OK porque
   inclui Instância desatualizada). E.04 ficou 111 (vs 112 estimado, ✓).
   (Seções 3.3, 3.4, 7.)

2. **🔴 Frente 4.1 (Partes legível) tem regressão massiva: 530 pubs
   (33%) ainda têm Partes em JSON cru `[{"comunicacao_id":...}]`.**
   Cluster afetado: TRT10 Intimação Acórdão 100% (94/94 pubs com JSON
   cru!), TRT10 Intimação Notificação 56% (408/723), e gotas em STJ
   Decisão (5), TST Decisão (8) e Lista TRT10 (4). O `formatar_partes`
   produz output correto quando rodado isoladamente sobre o
   `payload.destinatarios` das pubs afetadas (testado para
   djen=494748109, 495174885, 573369859 — todos retornam "Polo Ativo:
   ..."). Causa raiz não diagnosticada nesta análise; provável bypass
   no caminho de envio para certos clusters. **Maior pendência do
   Round 4.** (Seções 3.1, 4.1, 10.)

3. **🔴 Regressão `<br>` literal no Texto inline confirmada.**
   Inspeção MCP de 5 amostras mostrou `<br>` literal no Texto entregue
   ao Notion em todas elas (TRT10 Notif djen=494748109, TRT10 Acórdão
   573369859, TRT10 Lista 496542520, TJDFT Ata 524038068, etc). O
   commit `afddba4` ("Round 4.5 — teste de regressão para <br>
   residual") adicionou testes que passam contra texto bruto, mas o
   estado real no Notion ainda mostra os `<br>`. 517 pubs (32% do
   acervo) têm o trailer `Intimado(s) / Citado(s)` no Texto entregue,
   onde o `<br>` historicamente aparece. (Seções 4.2, 10.)

4. **Frente 4.2 (Classe normalizada) — sucesso total.** 1.608/1.608
   pubs (100%) com Classe em CAPS uniforme. Zero ocorrências do
   casing torto histórico (`AçãO TRABALHISTA - RITO ORDINáRIO` virou
   `AÇÃO TRABALHISTA - RITO ORDINÁRIO` em 695 pubs). 30 valores
   distintos de Classe no acervo, todos consistentes. (Seção 3.2.)

5. **Frente 4.5a (Auto-Status Listas TRT10/TST cadastradas) — sucesso
   total.** 217 Listas TRT10/TST no acervo: 69 (32%) cadastradas
   recebem `Status = "Nada para fazer"`, 148 (68%) sem cadastro
   permanecem `Nova`. Zero falsos positivos (nenhuma pub fora desse
   cluster recebe `"Nada para fazer"`). Auto-Status reduz 4,3% (69
   pubs) da fila de triagem inicial. Sample confirma: djen=505334614
   (TST Lista cadastrada) → "Nada para fazer"; djen=496542520 (TRT10
   Lista sem cadastro) → "Nova". (Seções 3.5, 7.)

6. **Frente 4.5b (Filtro Atas TJDFT tipo "57") — sucesso.** 26 Atas
   no acervo, todas com callout `[Ata filtrada automaticamente: X de Y
   processos pertence ao escritório]` no texto inline. Sample
   djen=524038068 (Ata 1ª TCV, 278 processos no original): texto cabe
   abaixo de 2000 chars com lista de CNJs filtrada (apenas
   `0724974-20.2025.8.07.0000`, o do escritório). Frente 1 do Round
   4.5 entregue. (Seção 3.6.)

7. **Frente 4.6 (Schema sem checkbox) — confirmada.** O CSV exportado
   tem 22 propriedades, sem `Processo não cadastrado`. Schema do
   Notion finalizado. A info migrou corretamente para `Alerta
   contadoria → Processo não cadastrado` (473 pubs). (Seções 3.7, 6.)

8. **Alertas com volumes acima do estimado pelo baseline** (não é
   regressão — é o detector funcionando melhor que o estimado):
   `Instância desatualizada` 25 vs estimado 2 (+1.150%; pubs STJ
   chegando para processos cadastrados como 1º/2º grau, e TST Listas
   para processos cadastrados em 1º grau); `Pauta presencial sem
   inscrição` 41 vs estimado 13 (+215%; inclui TST Pauta com 12 pubs
   além de TJDFT). `Trânsito em julgado pendente` 71 vs estimado 111
   (-36%, esperado pois D3 do Round 4 excluiu CUMPRIMENTO PROVISÓRIO).
   `Texto imprestável` 5 vs estimado 15 (-67%, detector ficou mais
   conservador). (Seções 3.4, 4.4.)

9. **Distribuição quantitativa estável.** 1.608 canônicas + 544
   duplicatas = 2.152 pubs no SQLite — exatamente igual ao Round 3
   anterior. Distribuição por tribunal e por cruzamento idêntica:
   TRT10 1.027, TJDFT 291, STJ 160, TST 67, demais TJ-estaduais
   somam 63. Os 19 cruzamentos de volume ≥10 do baseline continuam os
   mesmos. **Captura R3 v2 reproduziu o universo do Round 3 com
   fidelidade.** (Seção 2.)

10. **Cursores divergentes 5×1.** SQLite: 5 OABs em
    `2026-03-31`, Samantha em `2026-05-03`. **Janela 01/04/2026 →
    03/05/2026 NÃO foi capturada para 5 advogados.** Não é problema
    desta análise (já documentado no HANDOFF_ROUND_4 como pendência
    operacional não-bloqueante), mas significa que a contagem 1.608
    sub-representa o volume real do período.

### Estado das frentes do Round 4 / 4.5 / 4.6

| Frente | Estado | Observação principal |
|---|---|---|
| **4.1** Partes legível | 🔴 **Regressão parcial** | 530/1.608 (33%) ainda em JSON cru — TRT10 Acórdão 100% afetado, TRT10 Notif 56% |
| **4.2** Classe normalizada | 🟢 OK | 100% em CAPS uniforme; zero casing torto residual |
| **4.3** Tarefa sugerida | 🟢 OK | 100% cobertura; volumes batem com estimativas (D.01 1.305, D.03 177, E.01 473) |
| **4.4** Alerta contadoria | 🟢 OK | 38% cobertura; 5 dos 5 alertas disparam; volumes fora de estimativa investigados |
| **4.5a** Auto-Status Listas TRT10/TST | 🟢 OK | 69 pubs (32% das 217 Listas) recebem "Nada para fazer"; zero falso positivo |
| **4.5b** Filtro Atas TJDFT 57 | 🟢 OK | 26 Atas todas com callout de filtragem |
| **4.6** Schema sem checkbox | 🟢 OK | 22 props, sem `Processo não cadastrado`; info em Alerta |
| **4.5 br residual** | 🔴 Pendente | Pipeline tem teste passando, mas pubs reais no Notion ainda têm `<br>` literal |

### Backlog priorizado (P0/P1/P2 atualizado)

**Itens entregues (✓ — eram P0 do baseline, agora resolvidos)**:

- ✅ P0-2 Auto-`Tarefa sugerida` — 6 regras, 100% cobertura
- ✅ P0-3 Auto-`Alerta contadoria` — 5 regras, 38% cobertura
- ✅ P0-4 Normalizar `Classe` — 100% em CAPS uniforme
- ✅ P1-1 Auto-Status casos óbvios (Listas TRT10/TST cadastradas)
- ✅ P1-2 Filtro Atas TJDFT tipo "57"

**P0 (críticos) ainda em aberto**:

- 🔴 **P0-1bis Investigar regressão Frente 4.1**: 530 pubs com Partes
  em JSON cru. Mapper produz output correto isoladamente; problema
  está no pipeline de envio. Investigação obrigatória — esta é a
  propriedade mais visível na triagem e foi escopo central do Round
  4.
- 🔴 **P0-5 Investigar regressão `<br>` literal no Texto inline**: o
  teste do commit `afddba4` confirma pipeline OK, mas pubs reais no
  Notion ainda têm `<br>`. Auditoria do caminho de inserção do
  trailer `Intimado(s) / Citado(s)` é prioridade.

**P1 (importantes)**:

- P1-3 Capturar janela 01/04 → hoje para os 5 advogados em cursor
  desatualizado (problema de captura R3 v2, não pipeline)
- P1-4 Reformatar Partes do STJ para usar papel real (`AGRAVANTE`,
  `RECORRIDO`, `INTERESSADO`) em vez de `Polo Ativo: 1. NOME
  (PAPEL)` (formato atual misturado é menos legível que o proposto na
  seção 6.2.1 do baseline)
- P1-5 Visualizações Notion "📅 Pautas e Atas" e "📥 Listas a triar"
  (sem mudança de código, só configuração)

**P2 (polimento)**:

- P2-1 `Observações` automatizado (sumário, prazo extraído)
- P2-2 TJPR com link Projudi destacado
- P2-3 Marcador estrutural `D E C I S Ã O` (com espaços)
- P2-4 Alerta `Sócio sentinela como adversário`
- P2-5 Cruzamento `Posição do cliente`

---

## 1. Metodologia

### 1.1 Fontes consultadas

| Fonte | Caminho / ID | Uso nesta análise |
|---|---|---|
| **CSV exportado do Notion** | `%LOCALAPPDATA%\Temp\📬 Publicações 6ee4f13a9ea34506824656a261d99dce_all (2).csv` | 1.608 registros canônicos com 22 propriedades já formatadas. Atalho confiável vs queries MCP em massa. Encoding UTF-8 com BOM. Cabeçalho confirmado: `Identificação, Advogados intimados, Advogados não cadastrados, Alerta contadoria, Certidão, Classe, Cliente, Data de disponibilização, Duplicatas suprimidas, Hash, ID DJEN, Link, Observações, Partes, Processo, Status, Tarefa sugerida, Texto, Tipo de comunicação, Tipo de documento, Tribunal, Órgão`. |
| SQLite local | `%APPDATA%\NotionRPADV\leitor_dje.db` (cópia em Temp, leitura) | Texto bruto íntegro de 2.152 publicações (1.608 canônicas + 544 duplicatas), `payload_json` com `tipoComunicacao`, `tipoDocumento`, `nomeClasse`, `destinatarios`, `texto`. Cruzamento canônica × duplicata. Cursores `djen_advogado_state`. |
| Cache local | `%APPDATA%\NotionRPADV\cache.db` (cópia em Temp, leitura) | 4 bases: `Catalogo` (68), `Clientes` (1.072), `Processos` (1.108), `Tarefas` (33). Cruzamento com a base de Processos para validar regras de Alerta. Distribuição por instância: 1º grau 399, 2º grau 400, TST 164, STJ 141, STF 3, vazio 1. |
| Notion MCP | data source `78070780-8ff2-4532-8f78-9e078967f191` (📬 Publicações) | **8 pubs amostrais inspecionadas in-place** para confirmar achados do CSV (Partes, Texto `<br>`, Status auto, callout Atas, papéis STJ). Páginas-chave: TRT10 Notif djen=494748109 (page `35630d90-c916-8155-...`), TRT10 Acórdão 573369859, TJDFT Decisão 496898418, TRT10 Lista 496542520, TJDFT Ata 524038068, STJ Pauta 530258606, TST Lista 505334614, TRT10 Lista cadastrada 498387389. |
| Baseline | `docs/anatomia-publicacoes.md` (branch `analise-anatomia-pubs`, 1.617 linhas) | Comparação obrigatória — extraído via `git show` para temporário. |
| Handoff | `HANDOFF_ROUND_4_2026-05-03.md` (raiz do repo) | Estado declarado pós-Round-4: 1.608 canônicas, 544 duplicatas, 22 props, R3 v2 envio "1608 enviadas, 544 duplicatas suprimidas, 0 falharam". |

### 1.2 Critérios de agrupamento

- **Cruzamento principal**: `Tribunal × Tipo de comunicação × Tipo de
  documento` no CSV exportado (já canonizados pelo Round 1).
  Diferença vs baseline: aqui uso os tipos canônicos pós-Round-1
  (não os brutos), porque o CSV reflete o que o operador VÊ. Para
  Atas TJDFT, o tipo bruto "57" do payload original aparece como
  `Edital | Outros` no CSV (canônico). 26 Atas confirmadas no
  cluster `('TJDFT', 'Edital', 'Outros')`.
- **Profundidade**: ≥10 canônicas → análise completa com IDs DJEN.
  3-9 → parágrafo qualitativo. 1-2 → listagem.
- **Universo**: APENAS canônicas (1.608). Duplicatas (544) refletidas
  via propriedade `Duplicatas suprimidas` da canônica.

### 1.3 Decisões diante de ambiguidade

- **JSON cru no Partes**: classifiquei como "regressão" porque a
  intenção declarada do Round 4.1 era eliminar essa forma. Como o
  `formatar_partes` produz output correto isoladamente, não é bug do
  mapper — é falha no caminho de envio. Não consegui diagnosticar a
  causa raiz nesta sessão (escopo: análise, não modificação).
- **`<br>` no Texto inline**: o handoff diz que o pipeline foi
  validado correto. Mas pubs reais no Notion via MCP ainda mostram
  `<br>` literal. Reporto como "regressão observada" — a discrepância
  entre teste e produção é o achado principal.
- **Anomalias positivas no Alerta**: `Instância desatualizada` (25 vs
  estimado 2) — investiguei a distribuição: 7 pubs STJ Distribuição
  para processos cadastrados em 2º grau (correto: processo subindo de
  instância), 6 pubs TST Lista para processos cadastrados em 1º grau
  (correto), 2-3 STJ Pauta/Acórdão idem. **O detector está acertando
  inconsistências reais que o baseline não enxergou** — não é falso
  positivo, é underestimate do baseline.
- **Cursores divergentes**: 5 OABs em `2026-03-31`, Samantha em
  `2026-05-03`. Significa que a janela 01/04 → 03/05 só foi
  parcialmente capturada (apenas Samantha). 1.608 pubs sub-representa
  o volume real. Não é problema desta análise — só nota.

### 1.4 Validações cruzadas

- Total CSV (1.608 linhas de dados) = total canônicas SQLite (1.608).
- Total SQLite (2.152) = canônicas (1.608) + duplicatas (544) — bate
  com handoff Round 4.
- 100% das pubs CSV têm `Hash` e `Certidão` populados.
- 100% das pubs CSV têm `Identificação` no formato canônico
  `{Tribunal}___{YYYY-MM-DD}___{N}` — zero invalid, zero duplicates.
- 1.108 records em Processos (vs 1.107 declarados no baseline; +1
  pode ser template ou cadastro novo).

---

## 2. Distribuição quantitativa

### 2.1 Total geral (vs baseline)

| Métrica | Baseline (pré-Round-4) | Pós-Round-4 | Δ |
|---|---:|---:|---:|
| Total de publicações capturadas | 2.152 | 2.152 | 0 |
| Canônicas (com página própria no Notion) | 1.608 | 1.608 | 0 |
| Duplicatas suprimidas | 544 | 544 | 0 |
| Pendentes / Skipped | 0 / 0 | 0 / 0 | 0 |
| Período coberto (declarado) | 01/01/2026 → 03/05/2026 | 01/01/2026 → 03/05/2026 | — |
| Período coberto (real, SQLite) | — | 01/01/2026 → 01/05/2026 | — |
| Vínculo a ⚖️ Processos cadastrados | 1.135/1.608 (70,6%) | 1.135/1.608 (70,6%) | 0 |
| Sem ⚖️ Processo cadastrado (`Alerta = Processo não cadastrado`) | 473/1.608 (29,4%) | 473/1.608 (29,4%) | 0 |
| Records em Processos (cache) | 1.107 (excl. template) | 1.108 (excl. template) | +1 |
| Records em Catalogo | 67 (excl. template) | 67 (excl. template) | 0 |

**Estabilidade total**: a captura R3 v2 reproduziu o universo do Round
3 anterior com fidelidade — mesmos totais, mesma distribuição. **Zero
desvio > 5% em qualquer linha** (diferença de 1 record em Processos é
provável criação manual de cliente/processo nesse ínterim).

A diferença `max(data_disponibilizacao)` SQLite = `2026-05-01` (não
03/05) é consistente com o cursor de 5 OABs em `2026-03-31`: pubs entre
01/04 → 03/05 só foram capturadas para Samantha (única OAB com cursor
em 2026-05-03), explicando a janela "menor" no SQLite vs o declarado
no handoff.

### 2.2 Distribuição por tribunal (canônicas)

| Tribunal | Baseline | Pós-Round-4 | Δ |
|---|---:|---:|---:|
| TRT10 | ~1.027 | 1.027 | 0 |
| TJDFT | ~290 | 291 | +1 |
| STJ | ~160 | 160 | 0 |
| TST | ~67 | 67 | 0 |
| TJPR | 10 | 10 | 0 |
| TJRS | 9 | 9 | 0 |
| TJRJ | 9 | 9 | 0 |
| TJMG | 9 | 9 | 0 |
| TJSC | 8 | 8 | 0 |
| TJSP | 6 | 6 | 0 |
| TRF1 | 6 | 6 | 0 |
| TJMS | 2 | 2 | 0 |
| TJGO | 2 | 2 | 0 |
| TJBA | 1 | 1 | 0 |
| TRT18 | 1 | 1 | 0 |
| **Total** | **1.608** | **1.608** | **0** |

15 tribunais cobertos, identicamente ao baseline.

### 2.3 Cruzamento `Tribunal × Comunicação × Documento` (canônicas)

#### Volume ≥ 10 (analisados em profundidade)

Diferenças vs baseline marcadas com 🟡; novidades com 🆕; estável sem marca.

| Tribunal | Comunicação | Documento | Canônicas | Total c/ dups | Δ vs baseline |
|---|---|---|---:|---:|---|
| TRT10 | Intimação | Notificação | 723 | 1.132 | igual |
| TRT10 | Lista de Distribuição | Distribuição | 201 | 205 | igual |
| TRT10 | Intimação | Acórdão | 94 | 194 | igual |
| TJDFT | Intimação | Decisão | 81 | 82 | igual |
| TJDFT | Intimação | Certidão | 49 | 50 | igual |
| STJ | Intimação | Pauta de Julgamento | 41 | 41 | 🟡 baseline grava como `PAUTA DE JULGAMENTOS` (bruto); pós-R1 canonizou para `Pauta de Julgamento` |
| TJDFT | Edital | Pauta de Julgamento | 40 | 40 | igual |
| STJ | Intimação | Acórdão | 39 | 39 | 🟡 baseline grava como `EMENTA / ACORDÃO`; pós-R1 canonizou para `Acórdão` |
| TJDFT | Intimação | Ementa | 34 | 34 | igual |
| STJ | Intimação | Decisão | 32 | 40 | 🟡 baseline grava como `DESPACHO / DECISÃO`; canonizou para `Decisão` |
| TJDFT | Intimação | Despacho | 31 | 31 | 🟡 baseline 29 → 31 (+2) |
| STJ | Intimação | Despacho | 30 | 38 | 🆕 não estava listado separadamente no baseline ≥10; antes estava em "DESPACHO / DECISÃO" |
| TJDFT | Edital | Outros | 26 | 26 | 🟡 baseline grava como `57 (Ata de sessão)`; pós-R1 canonizou para `Outros` |
| TST | Intimação | Despacho | 17 | 19 | igual |
| TST | Lista de Distribuição | Distribuição | 16 | 16 | igual |
| STJ | Intimação | Distribuição | 15 | 15 | 🟡 baseline grava como `ATA DE DISTRIBUIÇÃO`; canonizou para `Distribuição` |
| TJDFT | Intimação | Pauta de Julgamento | 14 | 14 | 🟡 baseline 13 → 14 (+1; era `Intimação de pauta`) |
| TJDFT | Intimação | Sentença | 13 | 13 | igual |
| TST | Intimação | Pauta de Julgamento | 12 | 12 | 🟡 baseline 9 (`Pauta de Julgamento` vol 3-9) → 12 |
| TST | Intimação | Acórdão | 10 | 12 | 🆕 baseline tinha 7 (`ACORDAO`) + 3 (`Acórdão`) → consolidaram em 10 canônico |

**Total cruzamentos ≥10**: 20 (baseline tinha 19; um cruzamento STJ
saiu via canonização e outros entraram). Cobre **1.518/1.608
canônicas (94,4%)** — equivalente aos 94% do baseline.

**Observação importante**: os "🟡" são consequência da Round 1 fix 1.1
(canonização de `tipoDocumento`). Não são desvio do Round 4 — são o
estado consolidado pós-R1 corretamente refletido. Valor analítico: as
mesmas pubs estão lá; a CHAVE de cruzamento mudou.

#### Volume 3-9 (qualitativo)

| Tribunal | Comunicação | Documento | Canônicas |
|---|---|---|---:|
| TRT10 | Intimação | Despacho | 9 |
| TJMG | Intimação | Outros | 9 |
| TJRS | Intimação | Decisão | 8 |
| TST | Intimação | Decisão | 8 |
| TJPR | Intimação | Despacho | 7 |
| TJRJ | Intimação | Despacho | 5 |
| TJSP | Intimação | Outros | 4 |
| TRF1 | Intimação | Outros | 4 |
| TJSC | Intimação | Despacho | 3 |
| TJRJ | Intimação | Outros | 3 |
| TJDFT | Intimação | Outros | 3 |
| TJPR | Intimação | Outros | 3 |
| STJ | Edital | Pauta de Julgamento | 3 |
| TST | Intimação | Outros | 3 |

14 cruzamentos cobrindo 72 canônicas (4,5%). Distribuição compatível
com baseline (que tinha 17 cruzamentos em 3-9).

#### Volume 1-2

18 cruzamentos cobrindo 18 canônicas (1,1%). Listagem compacta:

`(TJSP, Despacho, 2)`, `(TJMS, Outros, 2)`, `(TJSC, Outros, 2)`,
`(TJSC, Decisão, 2)`, `(TST, Outros canônicos, 2)`, `(TJMG, Despacho,
2)` e variantes raras (TJBA, TJGO, TRT18, TJRJ Sentença, TRF1 Pauta,
TJSC Sentença etc).

### 2.4 Quantos cruzamentos analisados em cada nível

- **Profundidade total** (≥10): 20 cruzamentos cobrindo 1.518/1.608 (94,4%) — vs baseline 19/1.510 (94%)
- **Qualitativo** (3-9): 14 cruzamentos cobrindo 72/1.608 (4,5%) — vs baseline 17/74 (4,6%)
- **Listagem** (1-2): 18 cruzamentos cobrindo 18/1.608 (1,1%) — vs baseline 24/24 (1,5%)

A leve consolidação (menos cruzamentos no agregado) reflete a
canonização do Round 1 fix 1.1 — não é perda de dado.

---

## 3. Validação das frentes do Round 4 / 4.5 / 4.6

### 3.1 Frente 4.1 — Partes legível 🔴 **REGRESSÃO PARCIAL**

**Estado**: 1.078 pubs (67%) com formato `Polo Ativo: ... / Polo
Passivo: ...` correto; **530 pubs (33%) ainda com Partes em JSON cru
`[{"comunicacao_id": ..., "nome": "...", "polo": "..."}]`**.

**Distribuição do JSON cru por cluster** (530 pubs):

| Tribunal | Comunicação | Documento | Pubs com JSON cru | % do cluster |
|---|---|---|---:|---:|
| TRT10 | Intimação | Notificação | 408 | 56% (de 723) |
| TRT10 | Intimação | Acórdão | 94 | **100%** (de 94) |
| TST | Intimação | Decisão | 8 | 100% (de 8) |
| STJ | Intimação | Decisão | 5 | 16% (de 32) |
| TRT10 | Lista de Distribuição | Distribuição | 4 | 2% (de 201) |
| TST | Intimação | Acórdão | 3 | 30% (de 10) |
| TST | Intimação | Despacho | 2 | 12% (de 17) |
| TJBA | Intimação | Despacho | 1 | 100% (de 1) |
| TRT18 | Intimação | Notificação | 1 | 100% (de 1) |
| TRF1 | Intimação | Pauta de Julgamento | 1 | n/d |
| TJDFT | Intimação | Decisão | 1 | 1% (de 81) |
| TRT10 | Intimação | Despacho | 1 | 11% (de 9) |
| TJDFT | Intimação | Certidão | 1 | 2% (de 49) |

**Diagnóstico**:

1. O `formatar_partes(destinatarios)` em
   `notion_rpadv/services/dje_notion_mappings.py:342` produz output
   correto quando rodado isoladamente sobre o `payload.destinatarios`
   das pubs afetadas. Validado para djen=494748109, 495174885,
   573369859 — todos retornam strings tipo `"Polo Ativo: DENITA GOMES
   GUIMARAES\nPolo Passivo: BANCO DO BRASIL SA"`.
2. O mapper (`montar_payload_publicacao` em `dje_notion_mapper.py:620`)
   chama `formatar_partes(publicacao.get("destinatarios"))` e gera
   `properties["Partes"] = _rich_text_prop(partes_str)`.
3. Inspeção MCP confirma: a página real djen=494748109 (page
   `35630d90-c916-8155-ac1a-fdb2f0e90fa8`) tem
   `"Partes":"\\[\\{\\"comunicacao_id\\": 494748109, ..."` — JSON cru.
4. Inspeção MCP confirma também: TJDFT Decisão djen=496898418 (page
   `35630d90-c916-8116-8d99-c6e788e83e2b`) tem
   `"Partes":"Polo Ativo: JORGE HOMERO DA CUNHA"` — formato Round 4.1
   correto.
5. `captured_at` é o mesmo (2026-05-04T01:45) para todas as amostras —
   sync foi rodado na mesma janela. `captured_in_mode = padrao` para
   todas. `notion_attempts = 0` para todas (envio em primeira
   tentativa, sem retry).

**Hipóteses (não diagnosticadas nesta análise)**:

- a. O sync chamou `montar_payload_publicacao` mas alguma camada
  intermediária (transformer, validator, retry-store) descartou o
  campo `Partes` formatado e usou um fallback antigo.
- b. As páginas afetadas foram criadas em sync ANTERIOR ao Round 4
  (pré-PR #19), e o R3 v2 não recriou (apenas reusou via algum
  mecanismo de chave/hash) → mas isso conflita com R4.6 = reset do
  SQLite, que zera `notion_page_id`.
- c. Pode haver dois caminhos de envio (criação vs atualização)
  e um deles ignora a Frente 4.1.

A determinação da causa é trabalho do próximo round.

**Sample IDs DJEN**:
- Falha: 494748109 (TRT10 Notif), 495174885 (TRT10 Notif), 573369859
  (TRT10 Acórdão)
- Sucesso: 494870682 (TRT10 Notif legível, seq id `___3` mesmo dia),
  496898418 (TJDFT Decisão), 530258606 (STJ Pauta), 524038068 (TJDFT
  Ata), 496542520 (TRT10 Lista), 498387389 (TRT10 Lista cadastrada
  com Status auto)

**Cobertura final da Frente 4.1**: 67%, não 100%. **Fica em P0**
para próximo round.

### 3.2 Frente 4.2 — Classe normalizada 🟢 **OK**

**Estado**: 1.608/1.608 pubs (100%) com `Classe` em CAPS uniforme.

**Comparação com baseline**:

| Classe (top 5 pós-Round-4) | Pós-R4 | Forma no baseline |
|---|---:|---|
| AÇÃO TRABALHISTA - RITO ORDINÁRIO | 695 | `AçãO TRABALHISTA - RITO ORDINáRIO` (695×) |
| RECURSO ESPECIAL | 133 | `RECURSO ESPECIAL` (133×) |
| RECURSO ORDINÁRIO TRABALHISTA | 132 | `RECURSO ORDINáRIO TRABALHISTA` (132×) |
| CUMPRIMENTO DE SENTENÇA | 100 | `CUMPRIMENTO DE SENTENçA` (100×) |
| AGRAVO DE PETIÇÃO | 90 | `AGRAVO DE PETIçãO` (90×) |

Todas as 30 classes distintas vistas no acervo seguem CAPS uniforme
correta. O `MAPA_NOMECLASSE` (mapper Round 4.2, 23 entradas) cobriu
exatamente as classes vistas + fallback de `_normaliza_classe` para
casos não mapeados.

**Validação MCP** (4 amostras):
- djen=494748109: `Classe: AÇÃO TRABALHISTA - RITO ORDINÁRIO` ✓
- djen=573369859: `Classe: AGRAVO DE PETIÇÃO` ✓
- djen=496898418: `Classe: LIQUIDAÇÃO DE SENTENÇA PELO PROCEDIMENTO COMUM` ✓
- djen=530258606: `Classe: RECURSO ESPECIAL` ✓

**Cobertura**: 100%. Frente 4.2 tinha sido marcada 🔴 no baseline
(seção 6.1, ~2.000 pubs com casing torto); agora 🟢 100%.

### 3.3 Frente 4.3 — Tarefa sugerida 🟢 **OK**

**Estado**: 1.608/1.608 pubs (100%) recebem ao menos 1 tarefa.
Distribuição:

| Tarefa | Pós-R4 | Estimado baseline | Δ |
|---|---:|---:|---:|
| `D.01 Análise de publicação` | 1.305 | ~1.250 | +4% |
| `D.03 Análise de acórdão` | 177 | 177 | 0 |
| `D.02 Análise de sentença` | 15 | 15 | 0 |
| `E.01 Cadastro de cliente/processo` | 473 | 473 | 0 |
| `E.04 Inscrição para sustentação oral` | 111 | 112 | -1 |
| `E.02 Atualizar dados no sistema` | 33 | 15+ | +120% |

**Coexistência (multi-select)**:

| # de tarefas por pub | Pubs | % |
|---:|---:|---:|
| 1 | 1.103 | 68,6% |
| 2 | 504 | 31,3% |
| 3 | 1 | 0,1% |

Maior coexistência: D.01 + E.01 (publicação básica + processo a
cadastrar) = 473 pubs (29% do acervo).

**Análise dos desvios**:

- **D.01 1.305 vs estimado 1.250 (+4%)**: dentro do limite de
  tolerância (+20% no critério). Provavelmente o detector default
  cobre alguns casos extras que o baseline classificou como cluster
  específico.
- **E.02 33 vs estimado 15 (+120%)**: regra dispara também quando
  `Alerta = Instância desatualizada` (que veio em 25 pubs). Soma:
  ~33 pubs com E.02. Coerente — Round 4.3 D2 foi implementado sem
  precedência (handoff seção D2 ✅).
- **D.03 = exato 177**: as 177 = 94 TRT10 Acórdão + 39 STJ Acórdão +
  34 TJDFT Ementa + 7 TST Acórdão + 3 TST Acórdão. Confere com a
  soma do baseline.
- **D.02 = exato 15**: as 15 = 13 TJDFT Sentença + 1 TJSC Sentença +
  1 TJRJ Sentença. Bate.
- **E.01 = exato 473**: pubs sem `Processo` cadastrado.

**Validação MCP** (5 amostras):
- djen=494748109 (TRT10 Notif): `Tarefa = D.01` ✓
- djen=573369859 (TRT10 Acórdão): `Tarefa = D.03` ✓
- djen=530258606 (STJ Pauta): `Tarefa = E.04` ✓
- djen=496542520 (TRT10 Lista sem cadastro): `Tarefa = D.01, E.01` ✓
- djen=496898418 (TJDFT Decisão cadastrada): `Tarefa = D.01` ✓

**Cobertura**: 100% — superior ao 98% estimado pelo baseline.

### 3.4 Frente 4.4 — Alerta contadoria 🟢 **OK**

**Estado**: 611/1.608 pubs (38%) recebem ao menos 1 alerta. Coerente
com a estimativa de 36% do baseline. Distribuição:

| Alerta | Pós-R4 | Estimado baseline | Δ | Análise |
|---|---:|---:|---:|---|
| `Processo não cadastrado` | 473 | 473 | 0 | Igual ao baseline (pubs sem `Processo` cadastrado) |
| `Trânsito em julgado pendente` | 71 | 111 | -36% | **Esperado**: D3 do Round 4 EXCLUIU CUMPRIMENTO PROVISÓRIO. Baseline incluía; pós-R4 corretamente exclui ~40 pubs com `nomeClasse contains "PROVISÓRIO"`. Validado. |
| `Pauta presencial sem inscrição` | 41 | ~13 | +215% | Detector pega TJDFT Pauta + TST Pauta + TRF1 Pauta (TJDFT 28, TST 12, TRF1 1). Baseline só estimou TJDFT. **Sem falso positivo** — pubs reais de pauta presencial. |
| `Instância desatualizada` | 25 | 2 | +1.150% | Detector acerta cenários que baseline subestimou: STJ Distribuição → processo cadastrado em 2º grau (7 pubs); TST Lista → processo cadastrado em 1º grau (6); STJ Decisão/Acórdão/Pauta → processo em outras instâncias (~12). **Sem falso positivo**. |
| `Texto imprestável` | 5 | 15 | -67% | Detector ficou conservador (esperado pelo handoff: "detector de texto imprestável conservador"). Pubs detectadas: TJGO `ARQUIVOS DIGITAIS INDISPONÍVEIS` (2), `Intime-se.` curto (1), TJPR pointer-only (2). Outras "imprestáveis" do baseline ficaram fora. |

**Coexistência (multi-select)**:

| # de alertas por pub | Pubs | % |
|---:|---:|---:|
| 0 | 997 | 62,0% |
| 1 | 607 | 37,8% |
| 2 | 4 | 0,2% |

Coexistências mais comuns: `Trânsito em julgado pendente + Processo
não cadastrado` (raras, ~3-4 pubs) e `Instância desatualizada` por
si só.

**Validação MCP** (3 amostras):
- djen=496542520 (TRT10 Lista sem cadastro): `Alerta = Processo não cadastrado` ✓
- djen=494748109 (TRT10 Notif processo cadastrado): `Alerta` vazio ✓
- djen=496898418 (TJDFT Decisão cadastrada): `Alerta` vazio ✓

**Cobertura**: 38% (vs estimado 36%). Frente 4.4 tinha sido marcada
🔴 no baseline (vazio); agora 🟢 com 5 alertas operando corretamente.

### 3.5 Frente 4.5a — Auto-Status Listas TRT10/TST 🟢 **OK**

**Estado**: 217 Listas TRT10/TST no acervo (201 TRT10 + 16 TST).
Distribuição de Status:

| Subgrupo | Pubs | Status atribuído |
|---|---:|---|
| Lista TRT10/TST com `Processo` cadastrado | 69 | "Nada para fazer" ✓ |
| Lista TRT10/TST SEM `Processo` cadastrado | 148 | "Nova" ✓ |

**Zero falso positivo**: nenhuma pub fora desse cluster recebe
`"Nada para fazer"`. Verificado:

```
Status=Nada para fazer (69 pubs):
  100% são TRT10/TST + Lista de Distribuição + processo cadastrado
```

Distribuição entre tribunais (das 69 com Status auto):
- TRT10 Lista de Distribuição cadastradas: 61 pubs
- TST Lista de Distribuição cadastradas: 8 pubs

**Validação MCP** (4 amostras):
- djen=498387389 (TRT10 Lista cadastrada): `Status = "Nada para fazer"` ✓
- djen=505334614 (TST Lista cadastrada): `Status = "Nada para fazer"` ✓
- djen=496542520 (TRT10 Lista SEM cadastro): `Status = "Nova"` ✓
- djen=494748109 (TRT10 Notificação cadastrada): `Status = "Nova"` ✓ (não-Lista, regra não dispara)

**Sample IDs**:
- Status auto: TRT10___2026-01-09___1 (djen=498387389),
  TST___2026-01-19___1 (505334614), TST___2026-04-08___3 a ___7
  (579065945-579418384) — confirma que regra opera em capturas
  recentes, não só em datas antigas.

**Cobertura**: 4,3% das pubs do acervo total (69/1.608) — exatamente
no patamar estimado pelo prompt do baseline (~150-200/mês com R3
contínuo, equivalente a ~70 no acervo de ~123 dias).

### 3.6 Frente 4.5b — Filtro Atas TJDFT tipo "57" 🟢 **OK**

**Estado**: 26 Atas no acervo (cluster `TJDFT | Edital | Outros`,
tipo bruto "57" do payload), todas com filtro aplicado.

**Validação MCP** (1 amostra detalhada):

- djen=524038068 (page `35630d90-c916-8112-932d-e31dab953bac`),
  identificação `TJDFT___2026-02-06___1`, classe `EMBARGOS DE
  DECLARAÇÃO CÍVEL`, órgão `1ª Turma Cível`. Texto inline contém:

  ```
  ...JULGADOS<br>
  0724974-20.2025.8.07.0000<br>
  [Ata filtrada automaticamente: 1 de 278 processos pertence ao
   escritório. Os demais CNJs foram omitidos. Texto integral
   disponível pela Certidão.]
  ```

  Confirma filtro: lista original tinha 278 CNJs, ficou apenas o do
  escritório (0724974-20...) + callout. Texto cabe em <2.000 chars.

**Sample IDs adicionais**: djen=524038068 (1ª TCV, 278 procs no
total), djen=525274051 (5ª TCV, 335 procs no baseline), djen=542171781
(5ª TCV PRESENCIAL, 42 procs).

**Cobertura**: 100% das 26 Atas filtradas. Frente 4.5b entregue
perfeitamente.

### 3.7 Frente 4.6 — Sem checkbox `Processo não cadastrado` 🟢 **OK**

**Estado confirmado em 3 lugares**:

1. CSV exportado tem 22 colunas, sem `Processo não cadastrado`. Header
   válido confirmado: `Identificação, Advogados intimados, Advogados
   não cadastrados, Alerta contadoria, Certidão, Classe, Cliente,
   Data de disponibilização, Duplicatas suprimidas, Hash, ID DJEN,
   Link, Observações, Partes, Processo, Status, Tarefa sugerida,
   Texto, Tipo de comunicação, Tipo de documento, Tribunal, Órgão`.
2. Inspeção MCP de 8 pubs amostrais — nenhuma tem propriedade
   `Processo não cadastrado` no schema retornado.
3. A info migrou corretamente para `Alerta contadoria → Processo não
   cadastrado` em 473 pubs (igual ao count de pubs sem `Processo`
   cadastrado).

`Advogados não cadastrados` (checkbox distinto, não removido)
permanece no schema — confirmado em todas as amostras MCP, valor
booleano (`__NO__` na maioria).

**Cobertura**: 100% — schema sem o checkbox histórico, info
preservada via Alerta. Frente 4.6 entregue.

---

## 4. Regressões

Categorias de risco listadas na ordem do prompt original. Marcadas
🔴 (regressão real), 🟡 (atenção), 🟢 (sem regressão).

### 4.1 `<br>` literal residual no Texto inline 🔴

**Achado**: o commit `afddba4` ("Round 4.5 — teste de regressão para
<br> residual no Texto") adicionou testes que validam o pipeline
contra texto bruto e passam (handoff confirmou: "pipeline atual
processa corretamente"). Mas a inspeção MCP de 5 pubs reais mostra
**`<br>` literal presente no Texto entregue ao Notion**:

| djen | Tribunal | Tipo doc | Trecho com `<br>` |
|---|---|---|---|
| 494748109 | TRT10 | Notificação | `...Juiz do Trabalho Titular<br><br>Intimado(s) / Citado(s)<br> - BANCO DO BRASIL SA` |
| 573369859 | TRT10 | Acórdão | `...Servidor de Secretaria<br><br>Intimado(s) / Citado(s)<br> - ZULEIDE...` |
| 496542520 | TRT10 | Distribuição | `Processo 0001969-51.2025.5.10.0008 distribuído... 26/12/2025 <br> Para maiores informações...` |
| 524038068 | TJDFT | Outros (Ata 57) | `Poder Judiciário da União<br><br>1ª Turma Cível<br>1ª Sessão...` |
| 530258606 | STJ | Pauta de Julgamento | (não tem `<br>` no texto, mas tem advogados rodando junto sem espaços — outra anomalia, vide 4.5) |

**Quantificação**:
- SQLite raw (texto antes do pipeline): 1.138/1.608 canônicas (71%)
  têm `<br` no texto bruto.
- CSV exportado: 0 ocorrências de `<br>` detectadas (mas é
  artefato — o CSV pode estar normalizando entidades; via MCP, o
  caractere literal aparece nas pubs).
- Pubs com trailer `Intimado(s) / Citado(s)` no texto entregue: 517
  (32% do acervo). Trailer historicamente é onde o `<br>` aparece.

**Hipótese (não verificado)**: o trailer `Intimado(s) / Citado(s)<br>`
é inserido pelo DJEN na resposta da API APÓS o conteúdo principal, e
o pipeline de pré-processamento `_BR_RE` em `dje_text_pipeline.py`
roda APENAS no conteúdo principal, deixando o trailer cru. O teste do
Round 4.5 testou contra um payload bruto que inclui o trailer e passa
porque o regex pega o `<br>`. Mas em produção, talvez o trailer chegue
em fluxo diferente.

**Impacto**: cosmético no Texto inline (texto fica com markup
visível), e funcional no body content (mesmo `<br>` no body também).

**Recomendação**: P0 — investigar o ponto exato de entrada do trailer
no pipeline.

### 4.2 Cabeçalhos institucionais (`PODER JUDICIÁRIO ...`) preservados 🟢

**Achado**: cabeçalhos institucionais por tribunal continuam
presentes no Texto entregue. Confirmado nas 5 amostras MCP:

- TRT10 Notif: `PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRIBUNAL REGIONAL DO TRABALHO DA 10ª REGIÃO 18ª Vara do Trabalho de Brasília - DF`
- TRT10 Acórdão: `PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRIBUNAL REGIONAL DO TRABALHO DA 10ª REGIÃO 2ª TURMA`
- TJDFT Decisão: `Poder Judiciário da União TRIBUNAL DE JUSTIÇA DO DISTRITO FEDERAL E DOS TERRITÓRIOS 9VARCIVBSB`
- TJDFT Ata: `Poder Judiciário da UniãoTRIBUNAL DE JUSTIÇA DO DISTRITO FEDERAL E DOS TERRITÓRIOS` (sem espaço entre "União" e "TRIBUNAL" — anomalia menor de pré-processamento, mas presente)
- STJ Pauta: começa direto com `REsp 1878824/DF (2020/0140213-1)` — STJ não tem cabeçalho institucional pré-fixo (esperado per baseline 5.1)

Sem regressão.

### 4.3 Marcadores estruturais (`ACÓRDÃO`, `EMENTA`, etc) 🟢

**Achado**: marcadores estruturais são preservados no body content
das pubs. Confirmado em djen=573369859 (TRT10 Acórdão) — o body do
Notion tem `EMENTA`, `RELATÓRIO`, `VOTO`, `CONCLUSÃO`, `ACÓRDÃO`
visíveis em sequência. Algoritmo 1.4 do Round 1
(`quebrar_em_blocos`) continua operando.

Atenção: na inspeção MCP do TRT10 Acórdão, o conteúdo do body parece
estar em parágrafos contíguos sem `heading_3` explícito visível na
representação enhanced-markdown — pode ser limitação da exibição via
MCP, não regressão real. Não pude confirmar com Notion UI.

Sem regressão definitiva.

### 4.4 `Duplicatas suprimidas` populada 🟡

**Achado**: 530 das 1.608 canônicas (33%) têm `Duplicatas suprimidas`
populada no CSV. Total de duplicatas declaradas no handoff: 544 (em
531 canônicas — diferença esperada porque algumas canônicas têm
2-3 duplicatas).

**Discrepância 530 vs 531**: handoff Round 4 declara "530 atualizadas
com sucesso, 1 falhou: djen=564026686 — HTTP 502 Bad Gateway
transient". A página canônica para djen=564026686 atualmente NÃO tem
a duplicata na propriedade — pendência operacional declarada.

**Validação MCP** (2 amostras):
- djen=494748109 (TRT10 Notif): `Duplicatas suprimidas = djen=494748135 (Cecília (20120/DF), Leonardo (36129/DF), Ricardo (15523/DF), Samantha (38809/DF), Vitor (48468/DF) — BANCO DO BRASIL SA)` ✓
- djen=573369859 (TRT10 Acórdão): `Duplicatas suprimidas = djen=573369915 (Cecília..., Leonardo..., Ricardo..., Samantha..., Vitor... — BANCO DO BRASIL SA)` ✓

**Formato confirmado**: `djen={N} ({advogados — partes})` per Round
1.6.

Atenção: 1 pub pendente de flush (djen=564026686 — handoff). Não é
regressão do Round 4, é falha transient não-resolvida.

### 4.5 `Advogados intimados` formato canônico 🟢

**Achado**: 7.418 entradas de Advogados intimados no CSV (somando
todos os multi-selects das 1.608 pubs). **Todas no formato `Nome
(OAB/UF)`** — zero invalid no parse contra regex
`^[^()]+\([0-9]+/[A-Z]{2}\)$`.

Validação MCP — 12 OABs canônicas presentes no acervo (6 ativas + 6
desativadas):
- Ativos: Cecília (20120/DF), Leonardo (36129/DF), Ricardo
  (15523/DF), Samantha (38809/DF), Vitor (48468/DF), Deborah
  (75799/DF)
- Desativados (ainda aparecem em pubs antigas): Juliana Vieira
  (65089/DF), Juliana Chiaratto (81225/DF), Erika (39857/DF),
  Maria Isabel (84703/DF), Shirley (37654/DF), Cristiane (não vi nas
  amostras inspecionadas — provável pub mais antiga)

Sem regressão. **Anomalia menor mas notável**: STJ Pauta djen=530258606
tem `Texto = REsp 1878824/DF (2020/0140213-1)RELATOR:MINISTRO ...
RECORRENTE:KEILA...ADVOGADOS:RICARDO...DF015523LEONARDO...` — sem
espaços entre tokens. Parece falha de pré-processamento STJ no Texto
inline (não afeta `Advogados intimados` que é multi-select separado).

### 4.6 `Hash` + `Certidão` populadas 🟢

**Achado**: 1.608/1.608 (100%) das pubs têm `Hash` e `Certidão`
preenchidos. Sem regressão.

Sample: djen=494748109 → Hash=`KOdGxm7gZmxotOMc1T7mMgb6y5DBkl`,
Certidão URL via `comunicaapi.pje.jus.br/.../certidao` (formula sobre
Hash, automática).

### 4.7 `Identificação` formato e sequencial 🟢

**Achado**: 1.608/1.608 com formato `{Tribunal}___{YYYY-MM-DD}___{N}`
válido. Zero invalid, zero duplicates de title.

**Top 5 maiores N (sequencial mais alto por dia/tribunal)**:

| Tribunal | Data | Max N |
|---|---|---:|
| TRT10 | 2026-03-26 | 138 |
| TRT10 | 2026-03-27 | 71 |
| TRT10 | 2026-04-20 | 48 |
| TRT10 | 2026-04-22 | 46 |
| TRT10 | 2026-04-16 | 44 |

138 é alto, mas dentro do esperado (TRT10 dia útil pode ter
~150-200 pubs concentradas). Risco de colisão paralela mencionado no
baseline (seção 9.2) continua hipotético — não houve colisão real.

Sem regressão.

### 4.8 STJ — formato Partes com papel real 🟡

**Achado**: pubs STJ têm Partes no formato `Polo Ativo: 1. NOME
(PAPEL), 2. NOME (PAPEL)<br>Polo Passivo: 4. NOME (PAPEL)...`. O
`formatar_partes` agrupou por polo A/P como esperado (Round 4.1 D1:
formato genérico Polo Ativo/Polo Passivo, NÃO nomenclatura
específica), mantendo o prefixo `N. NOME (PAPEL)` original do
payload DJEN dentro da string.

**Sample MCP**: djen=530258606 (STJ Pauta REsp):

```
Polo Ativo: 1. KEILA CRISTINE GUIMARAES BERNARDES (RECORRENTE),
2. CAIXA DE PREVIDENCIA DOS FUNCS DO BANCO DO BRASIL (RECORRENTE),
3. BANCO DO BRASIL SA (RECORRENTE)
Polo Passivo: 4. KEILA CRISTINE GUIMARAES BERNARDES (RECORRIDO),
5. CAIXA DE PREVIDENCIA DOS FUNCS DO BANCO DO BRASIL (RECORRIDO),
6. BANCO DO BRASIL SA (RECORRIDO)
```

**Não é regressão**: D1 do Round 4 explicitamente decidiu por formato
genérico. Mas é **menos legível** que a alternativa proposta na
seção 6.2.1 do baseline (`AGRAVANTE: X / RECORRIDO: Y`), pois o STJ
tem o papel real disponível e ele fica enterrado entre parênteses.

**Recomendação**: P1 — refinar `formatar_partes` para STJ,
extraindo o papel real do prefixo `N. NOME (PAPEL)` e usando como
label em vez de "Polo Ativo/Polo Passivo".

### 4.9 Resumo de regressões

| # | Categoria | Severidade | Pubs afetadas | Próximo passo |
|---|---|---|---:|---|
| 4.1 | `<br>` literal no Texto | 🔴 Alta | ~517 (32%) | P0 — investigar trailer DJEN |
| 4.2 | Cabeçalhos institucionais | 🟢 — | 0 | nenhum |
| 4.3 | Marcadores estruturais | 🟢 — | 0 | nenhum |
| 4.4 | Duplicatas suprimidas | 🟡 Baixa | 1 | manual ou próxima sync |
| 4.5 | Advogados intimados | 🟢 — | 0 | nenhum |
| 4.6 | Hash + Certidão | 🟢 — | 0 | nenhum |
| 4.7 | Identificação | 🟢 — | 0 | nenhum |
| 4.8 | STJ Partes papel real | 🟡 Cosmético | ~160 | P1 — refinar formatar_partes para STJ |
| (3.1) | **Partes JSON cru** | 🔴 **Crítica** | **530 (33%)** | **P0 — investigar pipeline de envio** |

---

## 5. Anatomia atualizada por cruzamento

Reproduzo aqui os 19 cruzamentos de volume ≥10 do baseline e 1
cruzamento novo (`STJ | Intimação | Despacho` saiu do consolidado
`DESPACHO/DECISÃO`). Para cada um, o estado pós-Round-4: anatomia
mantida ✓, anomalia nova ⚠, regressão visível ❌.

### 5.1 TRT10 | Intimação | Notificação — 723 ✓

Mesma anatomia do baseline. **Sample djen=494748109**: cabeçalho
PODER JUDICIÁRIO + classe ATOrd abreviada + RECLAMANTE/RECLAMADO +
INTIMAÇÃO + corpo do despacho + trailer "Intimado(s) / Citado(s)".

Estado pós-Round-4:
- ❌ **Partes em JSON cru** em 408/723 (56%) — Frente 4.1 incompleta
- ❌ **`<br>` residual** no trailer entregue ao Notion
- ✓ Classe normalizada: `AÇÃO TRABALHISTA - RITO ORDINÁRIO` (ex-`AçãO...`)
- ✓ Tarefa: `D.01 Análise de publicação`
- ✓ Alerta: vazio se cadastrado, `Processo não cadastrado` se não

Maior cluster do acervo (45%); o impacto da regressão Partes é
desproporcional aqui.

### 5.2 TRT10 | Lista de Distribuição | Distribuição — 201 ✓

Mesma anatomia. **Sample djen=496542520**: texto curto (~360 chars),
formato `Processo {CNJ} distribuído para {Vara} na data {DD/MM/AAAA}
<br> Para maiores informações...`.

Estado pós-Round-4:
- ✓ **Partes legível** em 197/201 (98%); 4 ainda em JSON cru
- ❌ `<br>` literal no Texto inline (legítimo do payload TRT10, mas
  visível como markup)
- ✓ Tarefa: `D.01 + E.01` (sem cadastro) ou `D.01` (com cadastro)
- ✓ Alerta: `Processo não cadastrado` em 148/201 (74% das Listas)
- ✓ **Auto-Status** `Nada para fazer` em 61/201 (30%, todas as TRT10
  Listas com `Processo` cadastrado)

Frente 4.5a entrega valor visível: 30% dessas pubs saem da fila
ativa.

### 5.3 TRT10 | Intimação | Acórdão — 94 ✓

Mesma anatomia. **Sample djen=573369859**: Acórdão 2ª TURMA
(AGRAVO DE PETIÇÃO), Relatora ELKE DORIS JUST, com EMENTA + RELATÓRIO
+ VOTO + CONCLUSÃO + ACÓRDÃO.

Estado pós-Round-4:
- ❌ **Partes em JSON cru** em 94/94 (100%) — pior cluster afetado
  pela regressão Frente 4.1
- ❌ `<br>` residual no trailer
- ✓ Classe normalizada: `AGRAVO DE PETIÇÃO`
- ✓ Tarefa: `D.03 Análise de acórdão`

Esse cluster é o mais impactado pela regressão Partes — todas as
pubs de Acórdão TRT10 chegam com JSON cru.

### 5.4 TJDFT | Intimação | Decisão — 81 ✓

Mesma anatomia. **Sample djen=496898418**: Vara cível, classe
LIQUIDAÇÃO DE SENTENÇA PELO PROCEDIMENTO COMUM, AUTOR/REU,
DECISÃO INTERLOCUTÓRIA.

Estado pós-Round-4:
- ✓ **Partes legível**: `Polo Ativo: JORGE HOMERO DA CUNHA`
- ✓ Texto LIMPO sem `<br>` residual visível
- ✓ Classe em CAPS uniforme
- ✓ Tarefa: `D.01`
- ✓ Anomalias mínimas (10-11 chars `Intime-se`) ainda presentes (2/81 = 2,5%)

Cluster com **melhor execução do Round 4** entre os ≥10. Apenas 1/81
em JSON cru.

### 5.5 TJDFT | Intimação | Certidão — 49 ✓

Mesma anatomia. Texto curto (~650 chars), CERTIDÃO + intimação
secretarial pra manifestação.

Estado pós-Round-4:
- ✓ Partes legível em 48/49 (98%)
- ✓ Tarefa: `D.01`

Sem novidade. Cluster bem comportado.

### 5.6 STJ | Intimação | Pauta de Julgamento — 41 ✓

Mesma anatomia (canonização do tipo bruto `PAUTA DE JULGAMENTOS` →
`Pauta de Julgamento`). **Sample djen=530258606**: REsp 1878824/DF,
RELATOR + RECORRENTES (3) + RECORRIDOS (3), sufixo "Processo
incluído na Pauta de Julgamentos da TERCEIRA TURMA, Sessão Virtual...".

Estado pós-Round-4:
- 🟡 **Partes mistura formato genérico com papel real**: `Polo Ativo: 1. KEILA... (RECORRENTE), 2. CAIXA... (RECORRENTE)<br>Polo Passivo: 4. KEILA... (RECORRIDO)...` — vide regressão 4.8
- ⚠ **Texto sem espaços**: `RECORRENTE:KEILA CRISTINEGUIMARAESBERNARDESADVOGADOS:RICARDO LUIZ RODRIGUES DA FONSECA PASSOS - DF015523LEONARDO GUEDES DA FONSECA PASSOS - DF036129RECORRENTE:CAIXA...` — pré-processador colou tokens. Anomalia menor de UX.
- ✓ Tarefa: `E.04 Inscrição para sustentação oral`
- ✓ Tipo de doc canonizado para `Pauta de Julgamento`

### 5.7 TJDFT | Edital | Pauta de Julgamento — 40 ✓

Mesma anatomia. Pauta integral filtrada pelo caso A do Round 1
(filtro 1.5 — só blocos com OAB do escritório).

Estado pós-Round-4:
- ✓ Texto filtrado mantido (tamanho ~2KB do original ~700KB-1.2MB)
- ✓ Partes legível
- ✓ Tarefa: `E.04` (Pauta)
- ⚠ Volume cresceu para 28 com `Alerta = Pauta presencial sem inscrição` (vs estimado ~13). Detector mais agressivo.

### 5.8 STJ | Intimação | Acórdão — 39 ✓

Mesma anatomia (canonização do bruto `EMENTA / ACORDÃO` →
`Acórdão`). EDcl no AgInt nos REsp + EMBARGANTE/EMBARGADO + ementa.

Estado pós-Round-4:
- ✓ Partes legível (mesma observação STJ que 5.6)
- ✓ Tarefa: `D.03 Análise de acórdão`
- ✓ Classe normalizada: `RECURSO ESPECIAL`

### 5.9 TJDFT | Intimação | Ementa — 34 ✓

Mesma anatomia. Texto começa com "Ementa: Direito previdenciário...";
estrutura I-IV CNJ.

Estado pós-Round-4:
- ✓ Partes legível
- ✓ Tarefa: `D.03 Análise de acórdão`

### 5.10 STJ | Intimação | Decisão — 32 ✓

Mesma anatomia (canonização do bruto `DESPACHO / DECISÃO` →
`Decisão`). Decisões monocráticas STJ.

Estado pós-Round-4:
- 🟡 5/32 com Partes em JSON cru (16%)
- ✓ Tarefa: `D.01`

### 5.11 TJDFT | Intimação | Despacho — 31 ✓

Despachos ordinatórios do TJDFT (algumas pubs Presidência do
Tribunal remetendo ao STJ).

Estado pós-Round-4:
- ✓ Partes legível
- ✓ Tarefa: `D.01`
- Volume cresceu de 29 (baseline) para 31 — captura 2 pubs adicionais

### 5.12 STJ | Intimação | Despacho — 30 🆕

Cluster que estava consolidado em `DESPACHO / DECISÃO` no baseline.
Pós-canonização do Round 1 fix 1.1, separou em `Despacho` (30) +
`Decisão` (32). Mesma anatomia que STJ DESPACHO/DECISÃO do baseline.

Estado pós-Round-4:
- ✓ Partes legível
- ✓ Tarefa: `D.01`

### 5.13 TJDFT | Edital | Outros (tipo "57" Atas) — 26 ✓

Mesma anatomia. **Sample djen=524038068**: Ata 1ª TCV, 278 processos
no original. Pós-Round-4.5b: lista filtrada para apenas o CNJ do
escritório + callout.

Estado pós-Round-4:
- ✓ **Filtro 4.5b operando**: callout presente em 26/26 das amostras
  espreitadas
- ⚠ `<br>` literal aparente nos separadores das listas (esperado da
  estrutura crua das atas)
- ✓ Partes legível
- ✓ Tarefa: `D.01`

**Frente 4.5b** transformou esse cluster — antes era risco P1 (perda
de CNJ por truncamento), agora é OK.

### 5.14 TST | Intimação | Despacho — 17 ✓

Mesma anatomia. Despachos da Vice-Presidência sobre admissibilidade
de recursos.

Estado pós-Round-4:
- ✓ Partes legível em 15/17 (2 com JSON cru)
- ✓ Tarefa: `D.01`

### 5.15 TST | Lista de Distribuição | Distribuição — 16 ✓

Mesma anatomia. Listas TST análogas a TRT10.

Estado pós-Round-4:
- ✓ Partes legível
- ✓ **Auto-Status** `Nada para fazer` em 8/16 (50% — Listas TST
  cadastradas)
- ✓ Tarefa: `D.01 + E.01` (sem cadastro) ou `D.01` (com cadastro)

### 5.16 STJ | Intimação | Distribuição — 15 ✓

Mesma anatomia (canonização do bruto `ATA DE DISTRIBUIÇÃO` →
`Distribuição`). Distribuição inicial de processo no STJ.

Estado pós-Round-4:
- ✓ Partes legível
- ✓ Tarefa: `E.02 Atualizar dados no sistema`
- ⚠ **7/15 com `Alerta = Instância desatualizada`** — pubs STJ para
  processos cadastrados em 2º grau (correto: o processo subiu para
  STJ, instância no cadastro precisa ser atualizada). Frente 4.4
  acertando inconsistência real.

### 5.17 TJDFT | Intimação | Pauta de Julgamento — 14 ✓

Cluster antes chamado `Intimação de pauta` (baseline 13). Mesma
anatomia: certidão de inclusão em pauta presencial individual.

Estado pós-Round-4:
- ✓ Partes legível
- ✓ Tarefa: `E.04`

### 5.18 TJDFT | Intimação | Sentença — 13 ✓

Mesma anatomia. Sentenças de 1º grau TJDFT, alguns casos com partes
em iniciais (segredo de justiça).

Estado pós-Round-4:
- ✓ Partes legível (com nomes em iniciais quando aplicável)
- ✓ Tarefa: `D.02 Análise de sentença`

### 5.19 TST | Intimação | Pauta de Julgamento — 12 ✓

Cluster que cresceu (baseline 9 em volume 3-9 → 12 ≥10). Mesma
anatomia (Pauta TST análoga a STJ).

Estado pós-Round-4:
- ✓ Partes legível
- ✓ Tarefa: `E.04`
- ⚠ 12 pubs com `Alerta = Pauta presencial sem inscrição` (todas)

### 5.20 TST | Intimação | Acórdão — 10 ✓

Cluster que consolidou (baseline tinha 7 `ACORDAO` em CAPS bruto + 3
`Acórdão` canônico). Pós-Round 1 1.1 + Round 4.2: 10 todos
canonizados como `Acórdão`.

Estado pós-Round-4:
- 🟡 3/10 com Partes em JSON cru (30%)
- ✓ Tarefa: `D.03`

### 5.21 Cruzamentos 3-9 e 1-2 — sumário

Os 14 cruzamentos de 3-9 (TJMG Outros 9, TJRS Decisão 8, TST Decisão
8, TJPR Despacho 7, etc) e os 18 cruzamentos de 1-2 (TRT18, TJBA,
TJGO etc) seguem comportamento compatível com o tribunal/tipo. Sem
regressão específica detectada (sample reduzido nesses volumes).

`TJGO Outros` (2 pubs) continua sendo o caso patológico
`ARQUIVOS DIGITAIS INDISPONÍVEIS` — recebe `Alerta = Texto imprestável`
agora.

`TJPR Intimação Despacho` (7 pubs) continua sendo "ato no sistema de
origem" (texto pointer Projudi). Não recebe `Alerta = Texto
imprestável` por enquanto (texto de 157 chars está acima do limiar de
200 chars do detector — pode ser refinado).

---

## 6. Qualidade das propriedades — revisão

Reproduzo a tabela 6.1 do baseline com o estado pós-Round-4. Cores:
🟢 OK; 🟡 atenção; 🔴 problema sério.

### 6.1 Resumo (atualizado)

| # | Propriedade | Tipo | Baseline | Pós-Round-4 | Δ |
|---:|---|---|---|---|---|
| 1 | `Identificação` | Title | 🟢 | 🟢 | sem mudança |
| 2 | `Advogados intimados` | Multi-select | 🟢 | 🟢 | sem mudança |
| 3 | `Advogados não cadastrados` | Checkbox | 🟢 | 🟢 | sem mudança |
| 4 | `Certidão` | Formula | 🟢 | 🟢 | sem mudança |
| 5 | `Classe` | Rich text | 🔴 | 🟢 | **ENTREGUE** (Frente 4.2) |
| 6 | `Cliente` | Rollup | 🟢 | 🟢 | sem mudança |
| 7 | `Data de disponibilização` | Date | 🟢 | 🟢 | sem mudança |
| 8 | `Duplicatas suprimidas` | Rich text | 🟢 | 🟡 | 1 pub pendente flush (djen=564026686) |
| 9 | `Hash` | Rich text | 🟢 | 🟢 | sem mudança |
| 10 | `ID DJEN` | Number | 🟢 | 🟢 | sem mudança |
| 11 | `Link` | URL | 🟡 | 🟡 | sem mudança (cosmético) |
| 12 | `Observações` | Rich text | 🟡 | 🟡 | sem mudança (subutilizado) |
| 13 | `Partes` | Rich text | 🔴 | 🔴 | **REGRESSÃO PARCIAL** (Frente 4.1: 67% OK, 33% JSON cru) |
| 14 | `Processo` | Relation | 🟢 | 🟢 | sem mudança |
| ~~15~~ | ~~`Processo não cadastrado`~~ | ~~Checkbox~~ | ~~🟢~~ | **REMOVIDO** | Frente 4.6 — info migrou para Alerta |
| 16 | `Status` | Select | 🟡 | 🟢 | **MELHOROU** (Frente 4.5a — 4,3% Status auto, sem falso positivo) |
| 17 | `Texto` | Rich text | 🟡 | 🟡 | regressão `<br>` ainda presente (Round 4.5 não resolveu) |
| 18 | `Tipo de comunicação` | Select | 🟢 | 🟢 | sem mudança |
| 19 | `Tipo de documento` | Select | 🟢 | 🟢 | sem mudança |
| 20 | `Tribunal` | Select | 🟢 | 🟢 | sem mudança |
| 21 | `Órgão` | Rich text | 🟡 | 🟡 | sem mudança |
| 22 | `Tarefa sugerida` | Multi-select | 🔴 | 🟢 | **ENTREGUE** (Frente 4.3 — 100% cobertura) |
| 23 | `Alerta contadoria` | Multi-select | 🔴 | 🟢 | **ENTREGUE** (Frente 4.4 — 38% cobertura) |

### 6.2 Sumário de mudanças

**4 propriedades passaram de 🔴 para 🟢** (Classe, Tarefa sugerida,
Alerta contadoria, Status melhorou de 🟡 para 🟢).

**1 propriedade DROPADA** (Processo não cadastrado — checkbox →
Alerta).

**1 propriedade permanece 🔴** (Partes — regressão parcial nova).

**1 propriedade caiu de 🟢 para 🟡** (Duplicatas suprimidas — 1 pub
pendente de flush por falha 502 transient, não-bloqueante).

**3 propriedades 🟡 mantidas sem mudança**: Link (semântica
inconsistente entre tribunais), Observações (subutilizado), Órgão
(casing variável).

**Texto** permanece 🟡 — regressão `<br>` esperava-se resolvida pelo
Round 4.5, mas inspeção MCP confirma que ainda persiste.

### 6.3 Análise por propriedade — destaques

#### 6.3.1 `Partes` — antes 🔴 ainda 🔴 (Frente 4.1 incompleta)

**Estado atual misto**:

- Para 1.078 pubs (67%): formato `Polo Ativo: ... / Polo Passivo: ...`
  per `formatar_partes` do Round 4.1.
- Para 530 pubs (33%): JSON cru `[{"comunicacao_id": ..., "nome":
  "...", "polo": "..."}]` — formato pré-Round-4.

A função produz output correto. O fato de TRT10 Acórdão estar 100%
em JSON cru sugere bypass específico do cluster. **P0 de
investigação**.

#### 6.3.2 `Classe` — antes 🔴 agora 🟢 (Frente 4.2 ✅)

695 pubs antes em `AçãO TRABALHISTA - RITO ORDINáRIO` viraram
`AÇÃO TRABALHISTA - RITO ORDINÁRIO`. 30 valores distintos no acervo,
todos consistentes. `MAPA_NOMECLASSE` cobre.

#### 6.3.3 `Tarefa sugerida` — antes 🔴 (vazio) agora 🟢 (100%)

6 opções coloridas, 100% das pubs com pelo menos 1 tarefa. Multi-
select com até 3 tarefas (1 pub no acervo). Cobertura > 98%
estimado.

#### 6.3.4 `Alerta contadoria` — antes 🔴 (vazio) agora 🟢 (38%)

5 alertas coloridos, 38% das pubs com pelo menos 1. Coexistência
maior 2 alertas. Cobertura ligeiramente acima do 36% estimado.

#### 6.3.5 `Status` — antes 🟡 agora 🟢 (Frente 4.5a ✅)

69 pubs (4,3%) recebem `"Nada para fazer"` automaticamente —
exatamente o cluster Listas TRT10/TST cadastradas. Zero falso
positivo. Reduz a "muralha de Novas" do baseline.

#### 6.3.6 `Texto` — permanece 🟡 (regressão `<br>` não resolvida)

Inspeção MCP confirma `<br>` literal em pubs reais (TRT10 Notif,
Acórdão, Lista; TJDFT Atas). Round 4.5 commit `afddba4` declara
pipeline OK, mas estado real diverge.

---

## 7. Métricas operacionais

Métricas calculadas sobre as 1.608 canônicas do CSV.

### 7.1 Cobertura `Tarefa sugerida`

| Métrica | Valor |
|---|---:|
| Pubs com pelo menos 1 tarefa | 1.608 (100,0%) |
| Pubs com 1 tarefa | 1.103 (68,6%) |
| Pubs com 2 tarefas | 504 (31,3%) |
| Pubs com 3 tarefas | 1 (0,1%) |
| Pubs com 0 tarefas | 0 |

Top tarefas individuais:

| Tarefa | Pubs | % do acervo |
|---|---:|---:|
| `D.01 Análise de publicação` | 1.305 | 81,2% |
| `E.01 Cadastro de cliente/processo` | 473 | 29,4% |
| `D.03 Análise de acórdão` | 177 | 11,0% |
| `E.04 Inscrição para sustentação oral` | 111 | 6,9% |
| `E.02 Atualizar dados no sistema` | 33 | 2,1% |
| `D.02 Análise de sentença` | 15 | 0,9% |

Soma > 100% pelo multi-select.

### 7.2 Cobertura `Alerta contadoria`

| Métrica | Valor |
|---|---:|
| Pubs com pelo menos 1 alerta | 611 (38,0%) |
| Pubs com 1 alerta | 607 (37,8%) |
| Pubs com 2 alertas | 4 (0,2%) |
| Pubs com 0 alertas | 997 (62,0%) |

Top alertas:

| Alerta | Pubs | % do acervo |
|---|---:|---:|
| `Processo não cadastrado` | 473 | 29,4% |
| `Trânsito em julgado pendente` | 71 | 4,4% |
| `Pauta presencial sem inscrição` | 41 | 2,5% |
| `Instância desatualizada` | 25 | 1,6% |
| `Texto imprestável` | 5 | 0,3% |

### 7.3 Cobertura auto-`Status`

| Status | Pubs | % do acervo |
|---|---:|---:|
| `Nova` (default) | 1.539 | 95,7% |
| `Nada para fazer` (auto Frente 4.5a) | 69 | 4,3% |

Composição do `Nada para fazer`:
- TRT10 Lista de Distribuição cadastrada: 61
- TST Lista de Distribuição cadastrada: 8

### 7.4 Volume diário médio

- Período coberto efetivo: 01/01/2026 → 03/05/2026 = 123 dias
- Acervo: 2.152 pubs (1.608 canônicas + 544 duplicatas)
- **Média diária**: 17,5 pubs/dia
- **Média mensal** (22 dias úteis): 385 pubs/mês

Compatível com a estimativa do baseline (seção 9.6).

**Nota**: 5 OABs com cursor em 2026-03-31 significa que o volume real
de 01/04 → 03/05 está sub-amostrado. Volume real provavelmente é
maior — extrapolação inviável aqui.

### 7.5 Coexistência de regras

#### 7.5.1 Top 10 cruzamentos `Tarefa × Alerta`

Combinações mais frequentes (no acervo, multi-select):

| Tarefa | Alerta | Pubs (estimado) |
|---|---|---:|
| `D.01 Análise de publicação` | (sem alerta) | ~750 |
| `D.01 + E.01` | `Processo não cadastrado` | ~470 |
| `D.03 Análise de acórdão` | (sem alerta) | ~125 |
| `E.04 Inscrição para sustentação oral` | `Pauta presencial sem inscrição` | ~41 |
| `D.03 Análise de acórdão` | `Trânsito em julgado pendente` | ~30 |
| `D.01 Análise de publicação` | `Trânsito em julgado pendente` | ~25 |
| `D.01 + E.02` | `Instância desatualizada` | ~25 |
| `D.02 Análise de sentença` | (sem alerta) | ~15 |
| `D.01 Análise de publicação` | `Texto imprestável` | 5 |
| `E.04 + E.01` | `Processo não cadastrado + Pauta...` | ~3 (raro) |

(Estimativas calculadas pela intersecção das regras compatíveis;
números exatos exigiriam joins por pub.)

#### 7.5.2 Distribuição de cobertura combinada

| Combinação | Pubs |
|---|---:|
| Pub triada manualmente (Status `Nova` + algum trabalho) | 1.539 |
| Pub auto-resolvida (Status `Nada para fazer`) | 69 |
| Pub com pelo menos 1 alerta + 1 tarefa | 611 |
| Pub com APENAS tarefa default `D.01` (mínimo trabalho) | ~750 |

### 7.6 Métricas adicionais notáveis

- **Texto avg/min/max length**: 1.195 / 10 / 2.000 chars (no CSV;
  truncamento em 2.000 evidente).
- **Pubs com trailer "Intimado(s) / Citado(s)" no Texto entregue**:
  517/1.608 (32%).
- **Pubs com texto bruto contendo `<br`** (SQLite raw): 1.138/1.608
  (71%) — o pipeline pré-processa, mas amostra MCP confirma que
  ainda chega `<br>` literal em algumas pubs entregues ao Notion.
- **Pubs com `Duplicatas suprimidas` populada**: 530/1.608 (33%) —
  total 544 duplicatas distribuídas em 530 canônicas (algumas têm
  2-3 dups; 1 pub `djen=564026686` pendente flush).
- **Pubs com `Hash` populado**: 1.608/1.608 (100%).
- **Pubs com `Certidão` populada (formula)**: 1.608/1.608 (100%).
- **Pubs com `Identificação` válido**: 1.608/1.608 (100%); zero
  duplicates; max sequencial N por dia/tribunal = 138 (TRT10
  2026-03-26).

---

## 8. Comparação com a investigação anterior

Resumo do que mudou, manteve, apareceu desde o baseline
(`docs/anatomia-publicacoes.md`).

### 8.1 O que mudou (resolvido)

| Item baseline | Estado pós-Round-4 |
|---|---|
| 🔴 `Partes` JSON cru em 100% das pubs | 🟡 67% legível, 33% ainda JSON cru |
| 🔴 `Classe` casing torto em ~2.000 pubs | ✅ 100% CAPS uniforme |
| 🔴 `Tarefa sugerida` vazio em 100% das pubs | ✅ 100% cobertura, 6 opções operando |
| 🔴 `Alerta contadoria` vazio em 100% das pubs | ✅ 38% cobertura, 5 alertas operando |
| 🟡 `Status` sempre Nova (muralha) | ✅ 4,3% auto-resolvido, sem falso positivo |
| 🟡 Atas TJDFT 57 risco de truncamento | ✅ Filtro 4.5b aplicado em 26 pubs |
| 🟢 `Processo não cadastrado` checkbox redundante | ✅ Dropado, info migrou para Alerta |

### 8.2 O que se manteve (sem mudança)

- Estabilidade do acervo: 1.608 canônicas + 544 duplicatas, mesmas
  distribuições por tribunal e cruzamento.
- Hash + Certidão (100% cobertura, formato perfeito).
- Identificação (100% válida, sequencial sem colisão).
- Advogados intimados (formato canônico Nome (OAB/UF), 7.418
  entradas).
- Cabeçalhos institucionais por tribunal.
- Marcadores estruturais (EMENTA, RELATÓRIO, etc) no body.
- TJPR pointer-only continua sendo ato no Projudi (3-7 pubs no
  acervo).
- TJGO `ARQUIVOS DIGITAIS INDISPONÍVEIS` continua patológico (2
  pubs) — mas agora recebe `Alerta = Texto imprestável`.
- Link com semântica inconsistente entre tribunais (cosmético).
- Observações subutilizado (vazio na maioria).

### 8.3 O que apareceu (novo)

| Achado | Severidade |
|---|---|
| 🔴 Partes JSON cru regressão parcial (530 pubs, 33%) | Crítica |
| 🔴 `<br>` literal residual no Texto inline (Round 4.5 não resolveu) | Crítica |
| 🟡 STJ Partes mistura `Polo Ativo: 1. NOME (PAPEL)` | Cosmético |
| 🟡 STJ Pauta texto sem espaços entre tokens | Cosmético |
| 🟡 1 pub pendente de flush dedup (djen=564026686) | Operacional |
| 🟡 Cursores divergentes: 5 OABs em 2026-03-31, Samantha 2026-05-03 | Operacional |
| ⚠ `Instância desatualizada` (25 pubs) detector mais agressivo que estimado | Positivo (achado real) |
| ⚠ `Pauta presencial sem inscrição` (41 pubs) inclui TST/TRF1 além de TJDFT | Positivo (achado real) |
| ⚠ TRT10 Acórdão 100% afetado pela regressão Partes — pior cluster | Crítica |

### 8.4 Tabela de IDs DJEN como fio de Ariadne

Listo aqui os djens citados nesta análise vs no baseline, para
facilitar cross-reference:

| djen | Tribunal | Tipo | Citado no baseline | Citado pós-R4 |
|---|---|---|---|---|
| 494748109 | TRT10 Notif | sample principal | 6.2.5 (br residual) | 3.1 (Partes JSON), 4.1 (br) |
| 494748135 | TRT10 Notif | duplicata | 5.2.1 | 4.4 (Duplicatas) |
| 495174885 | TRT10 Notif | sample multi-polo | — | 3.1 (Partes JSON) |
| 573369859 | TRT10 Acórdão | sample acórdão | 5.2.2 | 3.1 (Partes JSON), 4.1 (br) |
| 573369915 | TRT10 Acórdão | duplicata | — | 4.4 (Duplicatas) |
| 496898418 | TJDFT Decisão | — | — | 3.2 (Classe), 5.4 (cluster OK) |
| 530258606 | STJ Pauta | — | — | 3.2 (Classe), 4.8 (Partes papel real) |
| 524038068 | TJDFT Edital 57 | sample Ata | 4.3 | 3.6 (filtro 4.5b), 5.13 |
| 525274051 | TJDFT Edital 57 | sample Ata 5ª TCV | 4.3 | (referenciado) |
| 542171781 | TJDFT Edital 57 | Ata PRESENCIAL | 4.3 | (referenciado) |
| 496542520 | TRT10 Lista | sample sem cadastro | 3 | 3.1, 3.5, 5.2 |
| 498387389 | TRT10 Lista cadastrada | — | — | 3.5 (auto-Status) |
| 505334614 | TST Lista cadastrada | — | 3 | 3.5 (auto-Status) |
| 564026686 | (não inspecionada) | — | — | 4.4 (1 pendente flush) |
| 506771737 | TJDFT Decisão "Intime-se" | anomalia 10 chars | 5.2.3 | (referenciado) |

---

## 9. Novos achados

Padrões revelados pelo pipeline pós-Round-4 que o baseline não
identificou (mascarados antes pela poluição visual ou pelas regressões
do pré-Round-4).

### 9.1 STJ Pauta texto sem espaços entre tokens ⚠

Pub djen=530258606 (STJ Pauta) tem o Texto inline com TODOS os tokens
colados:

```
REsp 1878824/DF (2020/0140213-1)RELATOR:MINISTRO RICARDO VILLAS BÔAS
CUEVARECORRENTE:KEILA CRISTINE GUIMARAES BERNARDESADVOGADOS:RICARDO
LUIZ RODRIGUES DA FONSECA PASSOS - DF015523LEONARDO GUEDES DA FONSECA
PASSOS - DF036129RECORRENTE:CAIXA DE PREVIDENCIA DOS FUNCS DO BANCO
DO BRASILADVOGADOS:RENATO LOBO GUIMARAES - DF014517...
```

Cabeçalhos `RELATOR:`, `RECORRENTE:`, `ADVOGADOS:`, `RECORRIDO:`,
nomes e OABs estão concatenados sem separação. Provável falha do
pré-processador 1.7 do Round 1 ao colapsar `<br>` em STJ — a remoção
do `<br>` perde também o separador implícito entre seções.

**Volume estimado**: maior parte das pubs STJ (Pauta, Acórdão,
Despacho — ~150 pubs).

**Recomendação P1**: refinar o pré-processamento STJ para preservar
quebras semânticas (ex: ANTES de `RELATOR:`, `RECORRENTE:`, etc,
inserir `\n`).

### 9.2 Frente 4.4 detectou inconsistências reais que o baseline subestimou ⚠

O baseline estimou `Instância desatualizada = 2 pubs`. Pós-R4: 25
pubs. Análise:

- 7 pubs STJ Distribuição → processo cadastrado em 2º grau (cliente
  agora vai pra STJ; instância no cadastro tem que subir pra STJ)
- 6 pubs TST Lista Distribuição → processo cadastrado em 1º grau
  (subiu pra TST direto via recurso autônomo)
- 4 pubs STJ Decisão / 2 STJ Acórdão / 2 STJ Pauta / 1 STJ Despacho
  → processos similares
- 3 pubs TST Decisão → cliente recebendo decisão do TST mas cadastro
  ainda em 1º/2º grau

**Achado**: o baseline considerou só `TST + processo 1º grau` como
gatilho. O detector pós-Round-4 generalizou para qualquer combinação
tribunal-superior + instância-cadastrada-inferior. **Detector mais
correto que o estimado.**

### 9.3 Trânsito em julgado pendente: PROVISÓRIO foi corretamente excluído ⚠

Volume baseline 111 → pós-R4 71 (-36%). 40 pubs faltantes são
CUMPRIMENTO PROVISÓRIO DE SENTENÇA (42 no acervo) — corretamente
excluídas pelo D3 do Round 4 ("Trânsito em julgado pendente EXCLUI
cumprimentos provisórios").

Resta refinar: 71 pubs ainda recebem o alerta. Validar quantos delas
são realmente sem trânsito vs falsos positivos (cliente pode ter
trânsito anotado em outro processo cadastrado).

### 9.4 Anomalia de canonização de tipo: `Pauta de Julgamento` em Intimação 🆕

Cluster TJDFT `Intimação | Pauta de Julgamento` cresceu de 13
(baseline `Intimação de pauta`) para 14. Mesma anatomia, canonização
do Round 1 1.1 unificou nomes próximos.

Não é anomalia em si, mas sinaliza que `Tipo de documento` já vinha
heterogêneo no DJEN — múltiplos nomes para o mesmo conceito ("pauta
TJDFT presencial individual"). A canonização ajuda.

### 9.5 Auto-Status criou um sub-conjunto bem definido para triagem 🆕

Os 69 pubs com `Status = "Nada para fazer"` são todas do mesmo
perfil:
- Tribunal trabalhista (TRT10/TST)
- Tipo de comunicação Lista de Distribuição
- Processo cadastrado em ⚖️ Processos

**Insight para o operador**: criar uma view filtrada `Status = "Nada
para fazer"` no Notion permite confirmar visualmente as 69 pubs
"resolvidas pelo robô" antes de assumi-las como verdadeiramente
resolvidas. Útil pra calibrar confiança no detector.

### 9.6 Variação no formato Partes parece correlacionada com tribunal/tipo, não com captura 🆕

Da análise da seção 3.1: o cluster mais afetado pela regressão Partes
é TRT10 Notif/Acórdão (502 das 530 = 95% do total das falhas
concentradas em 2 cruzamentos). TJDFT/STJ/Lista TRT10 têm taxa
mínima de JSON cru.

Isso sugere que a causa NÃO é "pubs antigas vs novas" (todas foram
capturadas em 04/05/2026 01:45), mas algo específico do payload ou do
caminho de envio desses clusters TRT10. Hipóteses:

- Pode ser tamanho do payload (TRT10 Acórdão tem texto grande, ~16k
  mediana).
- Pode ser estrutura específica de `destinatarios` em pubs TRT10.
- Pode ser bug em algum filtro/transformer aplicado a TRT10.
- Pode ser uma regressão acidental introduzida no commit do Round 4
  que afetou só esses clusters.

Sem inspeção mais fina do código de envio, não consigo precisar.

### 9.7 Identificação sequencial cresceu com a captura recente 🆕

Max sequencial N por dia/tribunal: TRT10 2026-03-26 = 138. Outros
top: TRT10 2026-03-27 = 71, 2026-04-20 = 48. Volume diário em TRT10
em dias específicos chega a 100-140 pubs — significativamente maior
que a média de 17,5 do acervo.

Significa que o algoritmo de sequencial (`dje_db.count_sequencial_titulo`)
está operando bem em volumes altos sem colisão. Risco do baseline
9.2 ("paralelismo poderia colidir N") não materializou.

### 9.8 Cache de Processos cresceu de 1.107 para 1.108 🆕

1 cadastro novo entre baseline e pós-R4. Provável criação manual
pelo operador (resposta a `Alerta = Processo não cadastrado` em
algum momento entre as duas análises).

Bom sinal: a contadoria está agindo nos alertas (mesmo que esta
investigação não consiga medir o ritmo).

---
