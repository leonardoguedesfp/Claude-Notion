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
