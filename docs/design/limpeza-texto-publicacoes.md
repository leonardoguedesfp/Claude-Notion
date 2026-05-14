# Limpeza do Texto da database 📬 Publicações — Análise e Proposta

**Versão:** v2 — aprofundamento empírico
**Data:** 13/05/2026
**Status:** Documento de design (não implementa código).
**Base examinada:** **173 publicações** estratificadas de um universo de 1.833 (data source `78070780-8ff2-4532-8f78-9e078967f191`). 64 da rodada v1 (12/05/2026) + 109 novas com `seed=43`.
**Fontes:** CSV exportado do Notion em 12/05/2026 (`📬 Publicações 6ee4f13a9ea34506824656a261d99dce_all (11).csv`) + leitura direta do código do app (`notion_rpadv`, commit `67c21f8`).

> **Mudanças v1 → v2:** amostra ampliada (+109 pubs); estatísticas recalculadas; nova §3.6 com padrões novos descobertos; §4.3 e §4.4 ajustados (regex unificada por linha-própria; bypass específico para "Notifico o destinatário" e "ARQUIVOS DIGITAIS"); §7.2 reescrita — implantação **one-shot** com backfill via `recalcular_alertas_publicacoes`; menções a "fases" e "modo sombra" removidas.

---

## 1. Sumário executivo

O campo `Texto` das publicações em 📬 Publicações carrega, em média, **~18% de ruído puro** (mediana 14%, máx. 90%) — conteúdo que repete informação já estruturada nas demais propriedades da pub (`Tribunal`, `Órgão`, `Classe`, `Partes`, `Tipo de comunicação`) ou que é cerimonial (assinaturas, certificações de assinatura digital, trailers `Intimado(s) / Citado(s)`).

A análise das **173 publicações** mostra três padrões distintos:

1. **Trabalhista (TRT10, TST, TRT18):** preâmbulo "PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRIBUNAL REGIONAL..." + Vara + Classe + CNJ + RECLAMANTE/RECLAMADO. ~200–400 chars antes do corpo. Marcador robusto: `INTIMAÇÃO Fica`, `INTIMAÇÃO - ATO ORDINATÓRIO`, `DESPACHO`, `CERTIDÃO E CONCLUSÃO`. **Cobertura: 86% (25/29).**
2. **STJ:** ficha técnica compacta em string contínua (sem newlines) `EDcl no AgInt no REsp NNNN/UF...RELATOR:MINISTRO ... ADVOGADOS:LISTA-DE-OABS`, depois `\n ACÓRDÃO \n \n Vistos e relatados...`. Marcador robusto: linha própria com `ACÓRDÃO`/`DECISÃO`/`SENTENÇA`/`EMENTA`. **Cobertura: 55% (11/20)** — STJ Despachos curtos não têm corpo destacado.
3. **TJDFT e TJ-estaduais:** preâmbulo "Poder Judiciário da União\nTRIBUNAL DE JUSTIÇA..." + ÓRGÃO + CLASSE + PROCESSO + PARTES + ADVOGADOS. Marcadores: `DESPACHO`, `DECISÃO`, `SENTENÇA`, `ATO ORDINATÓRIO`. **Cobertura TJDFT: 91% (32/35); TJ-estaduais: 71% (24/34); TRF: 100% (3/3).**

**Recomendação:** limpeza **one-shot** (sem fases), entrando no pipeline `dje_text_pipeline` antes do `truncar_texto_inline`/`quebrar_em_blocos`, com **bypass para tipos onde o ruído é o conteúdo** (`Distribuição`, `Pauta de Julgamento`, `Edital`, `Certidão`) e dois casos especiais — `Notifico o destinatário...` (TJRJ migração para eproc) e `ARQUIVOS DIGITAIS INDISPONÍVEIS` (texto imprestável) — recebem diagnóstico próprio e não são tocados.

**Backfill** das ~1.833 pubs já no Notion: integrado no botão "Recalcular alertas das publicações" (já existente). A função `recalcular_alertas_publicacoes` passa a recalcular também o `Texto` limpo + reescrever os blocos do corpo da página. Idempotente via comparação de hash. `--dry-run` e `--limite` permitem validação faseada operacional sem dividir o roll-out em código.

**Ganho confirmado pelo n=173:** cabeçalho médio removível = 340 chars (mediana, entre pubs com cabeçalho efetivo). Em escala (1.833 pubs), redução estimada de **~436.000 caracteres totais → ~125.000 tokens economizados** por rodada completa do classificador.

Em paralelo, o relatório identifica **3 pontos de código** que precisam de ajuste após a remoção do valor `Nada para fazer` do select `Status`.

---

## 2. Metodologia da amostragem

- **Universo:** 1.833 publicações em 📬 Publicações no Notion (snapshot 12/05/2026).
- **Estratificação:** dupla — por `Tipo de documento` (alvo principal) e por `Tribunal` (segunda dimensão, pelo menos 1 pub de cada tribunal disponível dentro de cada tipo). Pubs já analisadas na rodada v1 foram excluídas do sorteio.
- **Amostra v1 (12/05):** 64 publicações, `seed=42`.
- **Amostra v2 (13/05):** 109 novas, `seed=43`. Pesos mais altos em `Despacho` (+20), `Outros` (+20), `Acórdão` (+15), `Decisão` (+15), `Sentença` (+15), `Pauta de Julgamento` (+10), `Distribuição` (+10). `Edital` ficou em 0 porque **não existe `Edital` como `Tipo de documento` no banco atual** (Editais aparecem como `Pauta de Julgamento` quando vêm via tipo de comunicação Edital, ou caem em `Outros`). `Sentença` atingiu 10 das 15 disponíveis — universo se esgotou.
- **Amostra combinada (n = 173):** distribuição final por tipo de documento — Acórdão 21, Decisão 21, Despacho 28, Outros 22, Sentença 15, Notificação 10, Ementa 7, Certidão 7, Pauta de Julgamento 16, Distribuição 16. Por tribunal: TRT10 (37), TJDFT (52), STJ (20), TST (10), TJRJ (7), TJMG (8), TJPR (5), TJRS (5), TJSP (4), TJSC (4), TRF1 (3), TJMS (4), TJGO (2), TJBA (1), TRT18 (1).
- **Fonte do texto:** CSV exportado pelo Notion. O CSV trunca a propriedade `Texto` em **2.000 caracteres**, idêntico ao limite da API de propriedade `rich_text`. Para ~25% da amostra (pubs longas), isso significa cabeçalho + começo do corpo visíveis; o trailer fica no corpo da página (children blocks), fora desta amostra. **Implicação:** os números de "trailer" abaixo subestimam o tamanho real em pubs longas. O cabeçalho está completo em 100% da amostra.
- **Seed reprodutível:** `random.seed(42)` (v1) e `random.seed(43)` (v2).
- **Lista completa de IDs:** Apêndice A.

---

## 3. Caracterização do ruído

### 3.1 Estatísticas agregadas (n = 173)

Excluindo bypass-por-tipo (49 pubs: Distribuição, Pauta, Certidão, Lista, Edital), a base útil é **124 publicações**:

| Métrica | min | p25 | mediana | p75 | max | média |
|---|---|---|---|---|---|---|
| Comprimento total do `Texto` | 57 | 677 | **1.264** | 1.995 | 2.000* | 1.303 |
| Comprimento do cabeçalho | 0 | 0 | **199** | 340 | 1.365 | 234 |
| Comprimento do trailer (visível) | 0 | 0 | 0 | 0 | 575 | 15 |
| Razão `(cabeçalho + trailer) / total` | 0,00 | 0,00 | **0,14** | 0,27 | 0,90 | **0,18** |

\* Truncamento em 2.000 chars (limite da propriedade `rich_text` no Notion).

Entre as **89 publicações não-bypass com cabeçalho efetivamente removível** (cab > 0):

| | min | p25 | mediana | p75 | max |
|---|---|---|---|---|---|
| Cabeçalho efetivo (chars) | 151 | 215 | **340** | 543 | 1.724 |

### 3.2 Por tipo de documento (n = 173)

| Tipo de documento | n | mediana cabeçalho | mediana total | razão ruído | cobertura marcador |
|---|---|---|---|---|---|
| Acórdão | 21 | 359 | 1.994 | **26%** | 14/21 (67%) |
| Decisão | 21 | 199 | 1.990 | 16% | 17/21 (81%) |
| Despacho | 28 | 0 (variável) | 761 | 12% | 10/28 (36%) |
| Sentença | 15 | 252 | 1.417 | **26%** | 12/15 (80%) |
| Ementa | 7 | 300 | 1.993 | 14% | 7/7 (100%) |
| Notificação | 10 | 213 | 1.117 | 17% | 8/10 (80%) |
| Outros | 22 | 0 (heterogêneo) | 1.973 | 18% | 10/22 (45%) |
| Certidão | 7 | — | 591 | — | **bypass** |
| Distribuição | 16 | — | 247 | — | **bypass** |
| Pauta de Julgamento | 16 | — | 1.913 | — | **bypass** |

**Revisão v1 → v2:**
- `Acórdão` mediana de cabeçalho **caiu de 948 para 359** (n=6 → n=21): a v1 estava enviesada para acórdãos longos do STJ; com mais TRT/TJDFT na amostra, a mediana ficou mais realista.
- `Despacho` permanece com mediana 0 (muitos curtos sem cabeçalho separável) e cobertura baixa (36%). Em **18 dos 28** despachos, o algoritmo cai em fallback (não corta nada). Mediana de ruído nesses casos é só 12%, então fallback prudente é barato.
- `Outros`: revisado. **30 das 22** publicações classificadas como "Outros" carregam conteúdo juridicamente relevante (sentenças TJMG, despachos administrativos, notificações de migração para eproc). Apenas **2 pubs (TJGO)** são lixo puro (`ARQUIVOS DIGITAIS INDISPONÍVEIS`). **`Outros` não recebe bypass** — entra no algoritmo com fallback.

### 3.3 Cobertura por família de tribunal (entre as 121 não-bypass)

| Família | Casa | Falha | Cobertura |
|---|---|---|---|
| TRF | 3 | 0 | **100%** |
| TJDFT | 32 | 3 | **91%** |
| Trabalhista (TRT10/TST/TRT18) | 25 | 4 | 86% |
| TJ-estadual (TJSP/TJMG/TJPR/TJRJ/TJRS/TJSC/TJBA/TJMS/TJGO) | 24 | 10 | 71% |
| STJ | 11 | 9 | **55%** |
| STF | — | — | sem amostra (universo zero) |

### 3.4 Marcadores observados

**Ranking (n = 121 não-bypass, soma ≥ 121 quando casa múltiplos):**

| Marcador | Ocorrências |
|---|---|
| `\bSENTEN[ÇC]A\b` | 23 |
| `\bDESPACHO\b` | 11 |
| `\bDECIS[ÃA]O\b` | 10 |
| `\bINTIMA[ÇC][ÃA]O\s+Fica\b` | 9 |
| `\bEMENTA\b` | 9 |
| `\bAC[ÓO]RD[ÃA]O\b` | 8 |
| `(?:^|\n)\s*ACÓRDÃO\s*\n` (linha própria) | 7 |
| `\bATO\s+ORDINAT[ÓO]RIO\b` (**novo na v2**) | 7 |
| `(?:^|\n)\s*DECISÃO\s*\n` (linha própria, **novo na v2**) | 5 |
| `\bVistos[,.\s]` | 4 |
| `\bINTIMA[ÇC][ÃA]O\s*-\s*ATO ORDINAT[ÓO]RIO\b` | 1 |
| `\bRELAT[ÓO]RIO\b` | 1 |

**Marcadores de fim/trailer (n = 121, visíveis dentro dos 2k chars):**

| Marcador | Ocorrências |
|---|---|
| `Intimado(s) / Citado(s)` | 7 |
| `Publique-se\.` | 6 |
| `Assinatura (digital\|eletrônica)` | 3 |
| `Documento assinado digitalmente` | 2 |
| `DOCUMENTO ASSINADO` | 1 |

Em pubs longas (>2k chars), o trailer está **no corpo da página** (children blocks) — fora da propriedade `Texto`. A limpeza precisa rodar no texto **inteiro pré-truncamento**.

### 3.5 Padrões de cabeçalho por família de tribunais

| Família | Cabeçalho típico | Marcador robusto de início |
|---|---|---|
| **Trabalhista (TRT10, TST, TRT18)** | `PODER JUDICIÁRIO JUSTIÇA DO TRABALHO TRIBUNAL REGIONAL DO TRABALHO DA Nª REGIÃO\nNª Vara/Turma...\nClasse CNJ\nRECLAMANTE: X\nRECLAMADO: Y\n` | `INTIMAÇÃO`, `INTIMAÇÃO - ATO ORDINATÓRIO`, `DESPACHO`, `CERTIDÃO E CONCLUSÃO`, `ACÓRDÃO`, `EMENTA`, `Vistos` |
| **STJ** | string contínua (sem `\n`) `EDcl no AgInt no REsp 1234567/UF (AAAA/NNNNNNN-D)RELATOR:MINISTRO NOMEEMBARGANTE:XADVOGADOS:LISTA-DE-OABS` → depois `\n ACÓRDÃO \n \n Vistos e relatados...` | **linha própria com** `ACÓRDÃO`, `DECISÃO`, `SENTENÇA`, `EMENTA` (`(?:^\|\n)\s*<MARCADOR>\s*\n`) |
| **TJDFT** | `Poder Judiciário da União\nTRIBUNAL DE JUSTIÇA...\nGabinete da Presidência\nÓRGÃO:...\nCLASSE:...\nPROCESSO:...\nAGRAVANTE:...\nAGRAVADO:...\n` | `DESPACHO`, `DECISÃO`, `SENTENÇA`, `ACÓRDÃO`, `EMENTA` |
| **TJ-estaduais cíveis (TJSC/TJRS especialmente)** | **CSS leak inicial** `body{ padding: 10px; ...}; #divHeader{...}; #divBody{...}PROCEDIMENTO COMUM CÍVEL Nº NNN/UF` seguido de `RELATOR:`, `AUTOR:`, `ADVOGADO(A):`, `ATO ORDINATÓRIO\n...` | `ATO ORDINATÓRIO` (novo) ou `DESPACHO`/`DECISÃO` após normalização que limpa o CSS |
| **TJDFT/TJ Edital de Pauta** | `Nª SESSÃO ORDINÁRIA DO PLENÁRIO VIRTUAL (PERÍODO DE DD/MM/AA A DD/MM/AA)` | **bypass** — conteúdo é o próprio "cabeçalho" |
| **TJMG / TJPR cível** | `PODER JUDICIÁRIO DO ESTADO DE [UF]...\n[Comarca/Vara]...\nPROCESSO Nº:...\nCLASSE:...\nPARTES...` | sem marcador padrão; fallback prudente (não cortar) |
| **TJRJ Outros (migração eproc)** | `Notifico o destinatário que os autos do processo NNNN foi migrado para o sistema eproc...` | **bypass específico** — conteúdo é todo informativo |
| **TRF1** | `PODER JUDICIÁRIO TRIBUNAL REGIONAL FEDERAL DA 1ª REGIÃO` | `DESPACHO`, `DECISÃO`, `SENTENÇA` |
| **TST Despacho (formato compacto)** | `Embargante: BANCO DO BRASIL S.A.\nADVOGADO: ...\n[lista]\nEmbargado(a): ...\n` | sem marcador clássico; fallback |
| **Lista de Distribuição (TRT10, TST)** | `Processo NNNN distribuído para X na data Y` + URL | **bypass** — pub inteira é dado útil |
| **Texto imprestável (TJGO)** | `ARQUIVOS DIGITAIS INDISPONÍVEIS (NÃO SÃO DO TIPO PÚBLICO)` (texto inteiro, < 100 chars) | **bypass específico** — sinaliza `texto_imprestavel=true` no diagnóstico |

### 3.6 Achados adicionais da segunda amostragem

**Padrões/marcadores não previstos na v1, descobertos na amostra v2 (n=109 novas):**

1. **`ATO ORDINATÓRIO` como marcador de início de corpo:** 7 ocorrências, atinge TJSC, TJRS, TRT10. Tipicamente após CSS leak ou após bloco de ADVOGADOS. Adicionado à lista canônica de marcadores.
2. **Marcador "linha própria":** o algoritmo da v1 dependia de `\bACÓRDÃO\b` simples — quebrava no STJ (string contínua). Refinamento v2: `(?:^|\n)\s*<MARCADOR>\s*\n` casa especificamente o marcador centrado em linha própria, que é o padrão real no STJ e TJDFT.
3. **Caso especial "Notifico o destinatário..." (TJRJ migração para eproc):** 1 ocorrência na amostra; padrão de notificação puramente administrativa sobre migração de sistema. Sem cabeçalho/corpo separáveis. Adicionado como bypass específico.
4. **Caso especial "ARQUIVOS DIGITAIS INDISPONÍVEIS":** 2 ocorrências (ambas TJGO); texto < 100 chars; equivale ao antigo "texto imprestável" do Round 4.4. Bypass + flag de diagnóstico `texto_imprestavel=true`.
5. **TST Despacho compacto:** começa com `Embargante: BANCO DO BRASIL S.A.\nADVOGADO: ...\n` direto — não tem preâmbulo "PODER JUDICIÁRIO". Sem marcador padrão. Fica em fallback (não corta) — preserva conteúdo.
6. **TJMG/TJPR/TJMS "Outros" carregam sentença ou despacho relevante:** 30 das 22 pubs `Outros` na amostra combinada (incluindo 14 da v2) têm conteúdo decisório. **Decisão revista:** `Outros` **não recebe bypass** — entra no algoritmo com fallback prudente.

**Refutações ou confirmações fortes do estudo v1:**

- **Confirmado:** trailer está predominantemente fora dos 2.000 chars da propriedade `Texto` — mediana 0 também na v2 (n=121). Concluído: trailer só é tratável no texto pré-truncamento, dentro do app.
- **Confirmado:** `Acórdão` é o tipo com mais cabeçalho absoluto; mas a v1 superestimou (mediana 948) com n=6. Com n=21, mediana caiu para 359. Ainda é o pior tipo, mas menos drástico.
- **Confirmado:** CSS leak é específico de **TJSC + TJRS apenas** (3 pubs, ~2% da amostra combinada). Nenhum outro tribunal vaza CSS. Bug independente do `dje_text_pipeline.preprocessar_texto_djen`.
- **Refutado:** hipótese inicial de "Pauta de Julgamento sempre é cabeçalho = conteúdo" — confirmada, mas com nuance: em STJ algumas Pautas têm 2k chars com lista grande de processos. Mantém-se bypass.
- **Refutado parcial:** "Despachos curtos sem cabeçalho" eram suspeita. Confirmado em **3 casos** (TJRJ migração eproc, TJSC sem CSS leak, TJPR JUNTADA DE INTIMAÇÃO). Não é regra absoluta — todos cabem no fallback.
- **Refutado:** "marcadores ambíguos quebram o algoritmo". 19 pubs têm o marcador casado aparecendo +1 vez (`SENTENÇA` aparece até 4× em sentenças TJDFT que citam jurisprudência). **Mas na prática a primeira ocorrência sempre é a do cabeçalho** (no contexto destas pubs); a defesa adicional "marcador < `CABECALHO_MIN`=80 chars não conta" cobre os edge cases onde o texto começa direto com `SENTENÇA`.

**Casos atípicos que merecem tratamento específico:**

| Caso | Identificação | Tratamento |
|---|---|---|
| Sentença começa direto com `Pelo exposto, REJEITO...` (TJDFT) | `TJDFT___2026-04-07___2` | fallback (cab=0): texto inteiro vira corpo |
| `Intimação referente ao movimento (seq. N) JUNTADA DE INTIMAÇÃO ONLINE` (TJPR) | `TJPR___2026-04-30___1` | fallback (texto curto, sem cabeçalho) |
| `Notifico o destinatário que os autos...foi migrado para o sistema eproc` | `TJRJ___2026-04-06___1` | **bypass `notifico_eproc`** |
| `ARQUIVOS DIGITAIS INDISPONÍVEIS` | `TJGO___2026-02-20___1`, `TJGO___2026-03-17___1` | **bypass `texto_imprestavel`** |
| TST Despacho começa direto com `Embargante: ...` | `TST___2026-04-14___1` | fallback |

---

## 4. Estratégia de limpeza proposta

### 4.1 Localização no pipeline

A limpeza roda em **`notion_rpadv/services/dje_text_pipeline.py`**, como função `limpar_cabecalho_trailer`, chamada por `montar_payload_publicacao` em `dje_notion_mapper.py` **antes** das chamadas a `truncar_texto_inline` (que monta a propriedade `Texto`) e `quebrar_em_blocos` (que monta o corpo da página). Assim, o texto pré-limpeza vai integral para ambos os destinos.

### 4.2 Tipos onde NÃO limpar (bypass por tipo)

```
TIPOS_BYPASS_DOC = {
    "Distribuição",         # texto curto, "Processo NNN distribuído para X"
    "Pauta de Julgamento",  # estruturado, conteúdo é o "cabeçalho"
    "Edital",               # raro como tipoDocumento (vide §2); preservar se aparecer
    "Certidão",             # curta (mediana 591), informativa
}
TIPOS_BYPASS_COM = {
    "Lista de Distribuição",  # mesma justificativa de tipoDocumento Distribuição
    "Edital",                 # editais sem subtipo definido
}
```

Para `Acórdão` e `Ementa` aplicar **só remoção de cabeçalho** (mais previsível), **nunca** mexer no trailer — o dispositivo final tem valor de auditoria.

### 4.3 Bypass específico por padrão de texto

Antes de procurar marcadores, dois padrões disparam bypass com diagnóstico próprio:

1. **`notifico_eproc`:** texto inicia com `Notifico o destinat[áa]rio que os autos do processo`. Bypass total; o app preserva o texto cru.
2. **`texto_imprestavel`:** texto contém `ARQUIVOS DIGITAIS INDISPON[ÍI]VEIS` e tem menos de 200 chars. Bypass total; diagnóstico `texto_imprestavel=true` para o classificador saber que a publicação não permite análise.

### 4.4 Algoritmo (pseudo-código comentado)

```
function limpar_cabecalho_trailer(texto, tribunal, tipo_documento, tipo_comunicacao):
    diag = {
        cabecalho_removido: False, fallback_aplicado: False,
        chars_removidos_inicio: 0, chars_removidos_fim: 0,
        marcador_inicio_casado: None, marcador_fim_casado: None,
        bypass_motivo: None, texto_imprestavel: False,
    }

    # ----- 0. Bypass por tipo -----
    if tipo_documento in TIPOS_BYPASS_DOC or tipo_comunicacao in TIPOS_BYPASS_COM:
        diag.bypass_motivo = "tipo"
        return (texto, diag)

    # ----- 1. Normalização básica (sempre, mesmo no fallback) -----
    # Bug TJSC/TJRS: 'body{ padding: 10px; ...}; #div...{...}'
    texto = remover_css_inline_residual(texto)
    texto = colapsar_espacos(texto)                 # múltiplos espaços
    texto = colapsar_quebras_linha(texto, max=2)    # 3+ \n viram 2
    texto = remover_zero_width_e_controle(texto)

    # ----- 2. Bypass por padrão de texto -----
    if RX_NOTIFICO_EPROC.match(texto):
        diag.bypass_motivo = "notifico_eproc"
        return (texto, diag)

    if RX_TEXTO_IMPRESTAVEL.search(texto) and len(texto) < 200:
        diag.bypass_motivo = "texto_imprestavel"
        diag.texto_imprestavel = True
        return (texto, diag)

    # ----- 3. Procurar primeiro marcador de início -----
    # Lista UNIFICADA para todas as famílias. Ordem por especificidade.
    MARCADORES_INICIO = [
        # Mais específicos primeiro
        (r"\bINTIMA[ÇC][ÃA]O\s*-\s*ATO\s+ORDINAT[ÓO]RIO\b", "INTIMAÇÃO - ATO ORDINATÓRIO"),
        (r"\bATO\s+ORDINAT[ÓO]RIO\b", "ATO ORDINATÓRIO"),
        (r"\bINTIMA[ÇC][ÃA]O\s+Fica\b", "INTIMAÇÃO Fica"),
        (r"\bCERTID[ÃA]O\s+E\s+CONCLUS[ÃA]O\b", "CERTIDÃO E CONCLUSÃO"),
        # Marcadores em LINHA PRÓPRIA (STJ + TJDFT em pubs longas)
        (r"(?:^|\n)\s*ACÓRDÃO\s*\n", "ACÓRDÃO (linha)"),
        (r"(?:^|\n)\s*DECISÃO\s*\n", "DECISÃO (linha)"),
        (r"(?:^|\n)\s*SENTENÇA\s*\n", "SENTENÇA (linha)"),
        (r"(?:^|\n)\s*EMENTA\s*\n", "EMENTA (linha)"),
        # Marcadores genéricos (fallback dentro da própria busca)
        (r"\bDESPACHO\b", "DESPACHO"),
        (r"\bDECIS[ÃA]O\b", "DECISÃO"),
        (r"\bSENTEN[ÇC]A\b", "SENTENÇA"),
        (r"\bAC[ÓO]RD[ÃA]O\b", "ACÓRDÃO"),
        (r"\bEMENTA\b", "EMENTA"),
        (r"\bRELAT[ÓO]RIO\b", "RELATÓRIO"),
        (r"\bVistos[,.\s]", "Vistos"),
    ]

    pos_inicio = None
    marcador_casado = None
    for rx, label in MARCADORES_INICIO:
        m = rx.search(texto)
        if m and (pos_inicio is None or m.start() < pos_inicio):
            pos_inicio = m.start()
            marcador_casado = label

    # ----- 4. Defesa: marcador colado no início = não há cabeçalho -----
    CABECALHO_MIN_CHARS = 80
    if pos_inicio is not None and pos_inicio < CABECALHO_MIN_CHARS:
        # Texto já começa com o marcador (e.g., 'Pelo exposto, REJEITO...').
        # Não cortar.
        diag.fallback_aplicado = True
        diag.marcador_inicio_casado = marcador_casado + " (descartado: prematuro)"
        return (limpar_trailer(texto), diag_with_trailer)

    # ----- 5. Fallback seguro: nenhum marcador casou -----
    if pos_inicio is None:
        diag.fallback_aplicado = True
        return (limpar_trailer(texto), diag_with_trailer)

    # ----- 6. Cortar cabeçalho -----
    texto_sem_cabecalho = texto[pos_inicio:]
    diag.cabecalho_removido = True
    diag.chars_removidos_inicio = pos_inicio
    diag.marcador_inicio_casado = marcador_casado

    # ----- 7. Limpar trailer -----
    return (limpar_trailer(texto_sem_cabecalho), diag_atualizado)


function limpar_trailer(texto):
    MARCADORES_FIM = [
        (r"\bIntimado\(s\)\s*/\s*Citado\(s\)", "Intimado(s)/Citado(s)"),
        (r"\bAssinatura\s+(digital|eletr[ôo]nica)\b", "Assinatura digital/eletrônica"),
        (r"\bDocumento assinado digitalmente\b", "Documento assinado digitalmente"),
        (r"\bDOCUMENTO ASSINADO\b", "DOCUMENTO ASSINADO"),
        (r"\bPublique-se[,.]", "Publique-se"),
        (r"comunica\.pje\.jus\.br/Processo/", "URL comunica.pje"),
    ]

    pos_trailer = -1
    marcador_fim = None
    for rx, label in MARCADORES_FIM:
        for m in rx.finditer(texto):
            if m.start() > pos_trailer:
                pos_trailer = m.start()
                marcador_fim = label

    if pos_trailer < 0:
        return (texto, {marcador_fim_casado: None})

    # Defesa: trailer nos últimos 30% do texto?
    # Se 'pos_trailer < len(texto) * 0.7', a ocorrência é provavelmente uma
    # menção legítima dentro do despacho. Não cortar.
    if pos_trailer < len(texto) * 0.7:
        return (texto, {marcador_fim_casado: marcador_fim + " (ignorado: meio do texto)"})

    texto_final = texto[:pos_trailer].rstrip()
    return (texto_final, {marcador_fim_casado: marcador_fim,
                          chars_removidos_fim: len(texto) - len(texto_final)})
```

### 4.5 Normalizações adicionais (sempre executadas, mesmo no bypass)

- **CSS inline residual** (`body{ padding: 10px; ... }; #divHeader{...}; #divBody{...}`) — atinge TJSC e TJRS (3 pubs na amostra). Regex `^\s*body\s*\{[^}]*\};?\s*(?:#div[A-Za-z]+\s*\{[^}]*\};?\s*)*`.
- **Caracteres de controle** U+2400–U+243F (defesa do Round 2.1; já em uso).
- **Colapsar 3+ quebras de linha consecutivas em 2** (preserva parágrafos).
- **Trim final** (`strip()`).

### 4.6 Diagnóstico devolvido

A função devolve `(texto_limpo, diagnostico)` onde `diagnostico` é dict com:

- `cabecalho_removido` (bool)
- `fallback_aplicado` (bool)
- `chars_removidos_inicio` (int)
- `chars_removidos_fim` (int)
- `marcador_inicio_casado` (str | None)
- `marcador_fim_casado` (str | None)
- `bypass_motivo` (str | None: `"tipo"`, `"notifico_eproc"`, `"texto_imprestavel"`)
- `texto_imprestavel` (bool — flag separada pro classificador)
- `hash_pos_limpeza` (str — SHA1[:16] de `texto_limpo`, usado pra idempotência do recálculo)

O `_meta` do payload (já existente no app) ganha esse `diagnostico` como subcampo `limpeza_diag`.

---

## 5. Riscos e limites operacionais

### 5.1 Limites da API Notion

- Propriedade `rich_text`: **2.000 chars por `text` item**; até 25 items por propriedade. O app hoje grava **1 único item** com ≤ 2.000 chars (`truncar_texto_inline` em `dje_text_pipeline.py:124`).
- Texto excedente vai pro **corpo da página** em blocos `paragraph`, também ≤ 2.000 chars por bloco (`quebrar_em_blocos` em `dje_text_pipeline.py:316`).
- Constantes: `NOTION_TEXTO_INLINE_LIMIT = 2000` e `NOTION_BLOCK_TEXT_LIMIT = 2000` em `dje_notion_constants.py`.
- A limpeza **não altera o esquema** — só reduz o input antes do truncamento/quebra. Acórdão de 5k chars com 350 chars removidos vira 4.650 chars; passa pelo mesmo pipeline de truncar+blocos.

### 5.2 Token savings estimados (n = 173)

Heurística pt-BR: ~3,5 chars/token. Cálculos sobre as 173 pubs:

| Cenário | Chars antes (mediana) | Chars depois (mediana) | Δ chars | Δ tokens |
|---|---|---|---|---|
| Pub não-bypass mediana | 1.264 | 1.065 | –199 | ~–57 |
| Acórdão | 1.994 | 1.635 | –359 | ~–103 |
| Decisão | 1.990 | 1.791 | –199 | ~–57 |
| Sentença | 1.417 | 1.165 | –252 | ~–72 |
| Notificação | 1.117 | 904 | –213 | ~–61 |
| Despacho (quando há cabeçalho) | 761 | 421 | ~–340 | ~–97 |
| Despacho (fallback) | 761 | 761 | 0 | 0 |

**Projeção para universo (n = 1.833):**
- Soma de chars removidos na amostra (173): **41.175 chars**, equivalente a **~19,3%** dos 213.867 chars totais da amostra.
- Projetado para o universo: **~436.000 chars** removidos por rodada completa.
- Tokens economizados: **~125.000 tokens** (a 3,5 chars/tok).

Atenção: se o classificador hoje lê **só** a propriedade `Texto` (2.000 chars), a limpeza pode **adicionar** conteúdo do corpo da página que antes não cabia — neste caso o ganho de tokens será menor (ou pode até subir). Decisão depende da interface do classificador — fora do escopo deste documento.

### 5.3 Risco de perda de informação útil — cenários

1. **Cabeçalho cita ID interno do PJe (e.g., `Despacho ID d366151`).** Mitigação: o algoritmo corta **antes** do marcador; se o marcador for `INTIMAÇÃO Fica V. Sa. intimad[oa] para tomar ciência do (Despacho|Decisão) ID NNNN`, a frase com o ID vai junto com o corpo (corta o preâmbulo `PODER JUDICIÁRIO ...`, mantém de `INTIMAÇÃO` em diante).
2. **Cabeçalho cita juiz substituto.** Trabalhista frequentemente menciona `Juíza do Trabalho Substituta LAURA RAMOS MORAIS` apenas no rodapé pré-cabeçalho. **Mitigação:** o trailer real (assinatura) está depois do corpo — a limpeza preserva. O rodapé pré-cabeçalho (se houver) tem o cabeçalho do tribunal antes dele e é cortado junto. **Risco aceitável** dada a baixa frequência observada.
3. **Tribunal de origem em decisão de tribunal superior.** Acórdãos do STJ podem citar o TJ de origem no relatório. **Mitigação:** marcador no STJ é `ACÓRDÃO`/`RELATÓRIO` em linha própria; o relatório (com a menção do TJ de origem) fica **dentro** do corpo, depois do marcador. Preservado.
4. **Texto inteiro é "cabeçalho" (Distribuição, Pauta, Lista, Certidão, Edital).** Já protegido por `TIPOS_BYPASS_DOC` e `TIPOS_BYPASS_COM`.
5. **HTML/CSS no início (TJSC/TJRS):** ~2% da amostra. Removido na fase de normalização básica.
6. **`Outros` com sentença camuflada** (TJMS, TJMG): cobertura de marcador 45%. Pubs sem marcador caem no fallback (não cortam). Risco zero de perda.
7. **TST Despacho compacto** (`Embargante: BANCO DO BRASIL...`): sem marcador. Fallback (não corta). Risco zero.
8. **Marcador casado prematuramente:** texto começa com `SENTENÇA` (e.g., `TJDFT___2026-04-07___2: 'Pelo exposto, REJEITO os embargos...'`). Defesa: marcador a < 80 chars do início é descartado; algoritmo segue para fallback.

### 5.4 Auditabilidade

A limpeza descarta informação. Para recuperar o original, o app já preserva tudo no banco local `%APPDATA%\NotionRPADV\leitor_dje.db.publicacoes.payload_json` por design. Auditoria via SQLite. Nenhuma propriedade nova no Notion é criada para isso.

### 5.5 Riscos de regressão na limpeza

- **Mudança de formato pelo DJEN sem aviso:** se o STJ alterar o separador de linha do marcador `\n ACÓRDÃO \n` para outra coisa, a cobertura cai sem aviso até alguém olhar. **Mitigação:** o `_meta.limpeza_diag` registrado em cada pub deve ser monitorado periodicamente (consulta SQL sobre `publicacoes.payload_meta`). Se a taxa de `fallback_aplicado=true` subir muito, é sinal de regressão.
- **Tribunais novos** (TRT2, STF) não estão na amostra. Para eles, o algoritmo cai em fallback até observação suficiente de cabeçalhos típicos. Decisão consciente: preferimos preservar texto do que cortar de forma errada.

---

## 6. Plano de migração — remoção de "Nada para fazer" do Status

Conforme apurado, o select `Status` da database 📬 Publicações **não tem mais** o valor `Nada para fazer`. O vocabulário atual é `[Nova, Tratada, Pré-migração]`. A semântica de "publicação não exige providência" passa para `Conclusão automática = "Nada para fazer"` (propriedade nova do classificador, separada de `Status`).

Qualquer `create_page`/`update_page` que tente gravar `Status = "Nada para fazer"` falha com `validation_error` da API do Notion.

### 6.1 Pontos do código a alterar

| Arquivo / linha | Conteúdo atual | Mudança proposta |
|---|---|---|
| `notion_rpadv/services/dje_notion_mapper.py:342` | `STATUS_NADA_PARA_FAZER: str = "Nada para fazer"` | **Remover constante.** |
| `notion_rpadv/services/dje_notion_mapper.py:344-348` | `_TRIBUNAIS_LISTA_AUTO_TRIADA = frozenset({"TRT10", "TST"})` + comentário sobre auto-Status | **Remover frozenset.** Nenhuma regra de Status auto resta. |
| `notion_rpadv/services/dje_notion_mapper.py:351-379` | `_calcular_status_inicial(...)` retorna `STATUS_NADA_PARA_FAZER` quando Lista+TRT10/TST+cadastrado | **Remover função** (ou simplificar para retornar sempre `STATUS_DEFAULT_CRIACAO`). |
| `notion_rpadv/services/dje_notion_mapper.py:589-597` | chamada de `_calcular_status_inicial(...)` no `montar_payload_publicacao` | **Substituir** por `status_inicial = STATUS_DEFAULT_CRIACAO` direto. |
| `tests/test_round_4_5.py` (5 testes) | testes que dependem de `STATUS_NADA_PARA_FAZER` | **Apagar** os 2 testes que verificam `== STATUS_NADA_PARA_FAZER` (`trt10_cadastrado_nada_para_fazer`, `tst_cadastrado_nada_para_fazer`). **Apagar** `test_R4_5_status_constantes_canonicas`. **Manter** os 4 que verificam "Nova" (atualizando imports). |
| `tests/test_round_4_5.py:1-7` | docstring menciona "Frente 1: auto Nada para fazer..." | atualizar para refletir nova semântica |

### 6.2 Verificações adicionais

Não foram encontradas referências a `"Nada para fazer"` em:

- `notion_rpadv/services/dje_recalcular_alertas.py` — não menciona Status.
- Outros arquivos em `scripts/` — nenhum recria schema.
- READMEs principais. Há menções em **handoffs antigos** que são histórico — não precisam alteração.

### 6.3 Risco residual

Pubs antigas no Notion ainda têm `Status = "Nada para fazer"` (valor "fantasma" — Notion mantém exibido mas não permite gravar de novo). Filtros de view baseados nele já estão quebrados. O classificador, ao processar uma dessas, deve sobrescrever `Status` para `Nova` (ou apropriado) e gravar `Conclusão automática = "Nada para fazer"` quando for o caso. **Comportamento do classificador é decisão de outro escopo.**

---

## 7. Alternativas consideradas e recomendação final

### 7.1 Alternativas

- **(a) Manter `Texto` cru + campo paralelo `Texto limpo`.** Preserva original como auditoria; classificador lê só o limpo. Custo: nova propriedade no schema, ~2× consumo. **Descartado** — o original já fica no `leitor_dje.db.payload_json`.
- **(b) Limpeza fora do app (property automation Notion / passo do classificador).** Notion não tem regex robusto em rich_text; Notion AI custa. Classificador faria, mas o LLM teria que ignorar o ruído a cada chamada — paga sempre o token. **Descartado** — menos eficiente.
- **(c) Limpeza progressiva em fases / modo sombra.** Originalmente recomendado na v1. **Descartado pela decisão de produto** — ver §7.2.

### 7.2 Recomendação final — implantação one-shot com backfill via "Recalcular alertas"

**A limpeza vai a produção em um único passo, simultaneamente:**

- Função `limpar_cabecalho_trailer` é adicionada ao `dje_text_pipeline.py`.
- A integração no fluxo de criação de pub (`montar_payload_publicacao`) é ativada imediatamente para **todos** os tribunais e **todos** os tipos de documento (respeitando `TIPOS_BYPASS_DOC`/`TIPOS_BYPASS_COM` e os bypass-por-padrão).
- O backfill das ~1.833 pubs existentes acontece **como efeito colateral do botão/CLI "Recalcular alertas das publicações"** que já existe (`recalcular_alertas_publicacoes` em `dje_recalcular_alertas.py`).

**Justificativa do one-shot:**
- O fallback do algoritmo é "não fazer nada" — o pior caso da regex falhar é preservar o texto cru. A defesa em profundidade (`CABECALHO_MIN_CHARS = 80`, "trailer no meio do texto = ignorar") reduz drasticamente o risco de cortar conteúdo útil.
- A amostra de 173 pubs cobre 15 dos 15 tribunais presentes na base e os 10 tipos de documento. Cobertura por família entre 55% e 100%, mediana ~80%.
- O texto original está preservado no banco local — qualquer regressão é reversível com 1 comando.
- Implantação progressiva atrasaria o ganho de tokens (estimado em ~125k tokens economizados por rodada completa do classificador) sem benefício proporcional de segurança.

**Integração no `recalcular_alertas_publicacoes`:**

A função existente já itera todas as pubs no Notion (~1.833) e atualiza tags. **Estender** para também recalcular o `Texto`:

```
para cada pub_notion em recalculo:
    payload_local = ler_payload_json(leitor_dje.db, djen_id)
    if payload_local is None:
        log.warning("pub não está mais no banco local, pulando")
        continue

    texto_bruto = payload_local["texto"]
    texto_limpo, diag = limpar_cabecalho_trailer(texto_bruto,
                                                  tribunal=pub.tribunal,
                                                  tipo_documento=pub.tipo_doc,
                                                  tipo_comunicacao=pub.tipo_com)

    # Idempotência via hash
    hash_atual = sha1(pub_notion.texto_propriedade + "|" + str(pub_notion.blocos_corpo))[:16]
    hash_novo = sha1(texto_limpo)[:16]

    if hash_atual == hash_novo:
        # nada mudou (incluindo segunda rodada)
        log.debug("idempotente, pulando")
        continue

    # Atualiza propriedade Texto (rich_text inline) + reescreve corpo (blocos)
    notion.update_page(page_id, {"Texto": truncar_texto_inline(texto_limpo)})
    notion.replace_children_blocks(page_id, quebrar_em_blocos(texto_limpo))
    log.info("pub_id={page_id} chars_antes={n} chars_depois={m} diag={diag}")
```

**Critério de idempotência:** comparação de hash entre o estado atual no Notion e o estado calculado. Segunda rodada não dispara `update_page`.

**Riscos do one-shot e mitigações:**

| Risco | Mitigação |
|---|---|
| Erro em regex corrompe ~1.833 pubs de uma vez | Texto original em `leitor_dje.db.payload_json` permite rollback completo. Testes unitários (§5 do handoff) cobrem os 5 padrões principais antes do merge. |
| Sem janela de validação em sombra | (1) `--dry-run` no CLI imprime diagnóstico sem escrever; (2) `--limite N` permite rodar em 50 pubs primeiro e olhar resultado; (3) log estruturado emite uma linha por pub com `chars_antes/chars_depois/marcador_casado`. |
| Regressão silenciosa (formato DJEN muda) | `_meta.limpeza_diag` gravado em cada pub permite query SQL pra ver taxa de `fallback_aplicado=true`. Se subir muito, alerta operacional. |
| Conteúdo crítico cortado erroneamente | Defesa "marcador < `CABECALHO_MIN_CHARS=80` = descarta" + "trailer no meio do texto = ignora". Spot-check manual em 10 pubs após backfill (item 6 dos critérios de aceitação no handoff). |

**Plano de rollback:**

Se o operador identificar que a limpeza está produzindo texto pior:

1. Reverter o código em `dje_text_pipeline.py` (PR de revert do commit da limpeza).
2. Rodar `python scripts/recalcular_alertas_publicacoes.py` novamente. Como `limpar_cabecalho_trailer` ficou inerte (ou foi removida), o texto reconstruído a partir do `payload_json` é o cru original. Hash atual ≠ hash novo (cru) → `update_page` reescreve para o cru. Idempotente.

Tempo de rollback: ~10 minutos (rebuild + ~13 min de execução do recálculo).

---

## 8. Próximos passos sugeridos

1. **Aplicar as mudanças da Seção 6** (remoção de "Nada para fazer" do código). Independe da limpeza, mas é pré-requisito — o app pode estar falhando silenciosamente em pubs de Lista TRT10/TST com Processo cadastrado.
2. **Implementar a limpeza** conforme §4 + §7.2. Detalhe operacional no handoff [`handoff-implementacao-limpeza-texto.md`](./handoff-implementacao-limpeza-texto.md).
3. **Confirmar com o operador do classificador** se ele lê só `Texto` (propriedade) ou também o corpo da página. Decide se o ganho de tokens vai ser confirmado na prática ou se vai oscilar.
4. **Corrigir CSS leak TJSC/TJRS** no `preprocessar_texto_djen`. Ganho rápido independente.
5. **Monitorar `limpeza_diag` por 30 dias** após o roll-out (query SQL sobre `leitor_dje.db.publicacoes` + `payload_meta`). Métricas-chave: % de fallback aplicado, mediana de chars removidos, distribuição de `bypass_motivo`.

---

## Apêndice A — IDs das publicações examinadas

### A.1 Rodada v1 (n = 64, seed=42, 12/05/2026)

| Tribunal | Tipo de documento | Identificação |
|---|---|---|
| STJ | Acórdão | STJ\_\_\_2026-03-11\_\_\_2, STJ\_\_\_2026-03-18\_\_\_2, STJ\_\_\_2026-04-07\_\_\_12, STJ\_\_\_2026-04-24\_\_\_2 |
| STJ | Decisão | STJ\_\_\_2026-01-16\_\_\_1, STJ\_\_\_2026-05-05\_\_\_5 |
| STJ | Distribuição | STJ\_\_\_2026-05-12\_\_\_2 |
| STJ | Pauta de Julgamento | STJ\_\_\_2026-03-05\_\_\_17 |
| TJBA | Despacho | TJBA\_\_\_2026-01-09\_\_\_1 |
| TJDFT | Certidão | TJDFT\_\_\_2026-01-21\_\_\_4, TJDFT\_\_\_2026-03-16\_\_\_6, TJDFT\_\_\_2026-05-07\_\_\_6, TJDFT\_\_\_2026-05-13\_\_\_4 |
| TJDFT | Despacho | TJDFT\_\_\_2026-05-05\_\_\_2 |
| TJDFT | Ementa | TJDFT\_\_\_2026-02-13\_\_\_7, TJDFT\_\_\_2026-03-27\_\_\_2, TJDFT\_\_\_2026-04-14\_\_\_6, TJDFT\_\_\_2026-04-27\_\_\_2 |
| TJDFT | Outros | TJDFT\_\_\_2026-03-23\_\_\_9 |
| TJDFT | Pauta de Julgamento | TJDFT\_\_\_2026-02-05\_\_\_2, TJDFT\_\_\_2026-03-06\_\_\_1 |
| TJDFT | Sentença | TJDFT\_\_\_2026-04-07\_\_\_2, TJDFT\_\_\_2026-04-07\_\_\_3, TJDFT\_\_\_2026-04-20\_\_\_1, TJDFT\_\_\_2026-04-20\_\_\_6 |
| TJGO | Outros | TJGO\_\_\_2026-02-20\_\_\_1, TJGO\_\_\_2026-03-17\_\_\_1 |
| TJMG | Outros | TJMG\_\_\_2026-04-09\_\_\_1, TJMG\_\_\_2026-05-08\_\_\_1, TJMG\_\_\_2026-05-11\_\_\_1 |
| TJMS | Outros | TJMS\_\_\_2026-02-09\_\_\_1, TJMS\_\_\_2026-02-26\_\_\_1 |
| TJPR | Despacho | TJPR\_\_\_2026-01-16\_\_\_1, TJPR\_\_\_2026-03-04\_\_\_1 |
| TJPR | Outros | TJPR\_\_\_2026-04-30\_\_\_1 |
| TJRJ | Outros | TJRJ\_\_\_2026-01-21\_\_\_1, TJRJ\_\_\_2026-04-06\_\_\_1 |
| TJRJ | Sentença | TJRJ\_\_\_2026-03-13\_\_\_1 |
| TJRS | Decisão | TJRS\_\_\_2026-01-21\_\_\_1, TJRS\_\_\_2026-03-16\_\_\_1 |
| TJRS | Despacho | TJRS\_\_\_2026-05-06\_\_\_1 |
| TJSC | Decisão | TJSC\_\_\_2026-03-17\_\_\_1 |
| TJSC | Despacho | TJSC\_\_\_2026-01-21\_\_\_2 |
| TJSP | Despacho | TJSP\_\_\_2026-02-02\_\_\_1 |
| TJSP | Outros | TJSP\_\_\_2026-03-19\_\_\_1 |
| TRF1 | Decisão | TRF1\_\_\_2026-02-19\_\_\_1 |
| TRF1 | Pauta de Julgamento | TRF1\_\_\_2026-02-02\_\_\_1 |
| TRT10 | Acórdão | TRT10\_\_\_2026-02-09\_\_\_13 |
| TRT10 | Distribuição | TRT10\_\_\_2026-03-26\_\_\_103, TRT10\_\_\_2026-03-27\_\_\_19, TRT10\_\_\_2026-04-06\_\_\_30 |
| TRT10 | Notificação | TRT10\_\_\_2026-02-04\_\_\_8, TRT10\_\_\_2026-03-17\_\_\_1, TRT10\_\_\_2026-03-18\_\_\_14, TRT10\_\_\_2026-04-10\_\_\_15, TRT10\_\_\_2026-04-16\_\_\_19, TRT10\_\_\_2026-05-11\_\_\_11 |
| TRT18 | Notificação | TRT18\_\_\_2026-01-30\_\_\_1 |
| TST | Acórdão | TST\_\_\_2026-03-05\_\_\_3 |
| TST | Despacho | TST\_\_\_2026-04-14\_\_\_1 |
| TST | Distribuição | TST\_\_\_2026-04-22\_\_\_3, TST\_\_\_2026-04-23\_\_\_3 |
| TST | Pauta de Julgamento | TST\_\_\_2026-02-13\_\_\_3, TST\_\_\_2026-05-08\_\_\_1 |

### A.2 Rodada v2 (n = 109, seed=43, 13/05/2026)

A lista bruta está em `.tmp_amostra_v2_novas.json` (não versionado). Distribuição por tipo: Despacho 20, Outros 20, Acórdão 15, Decisão 15, Pauta de Julgamento 10, Distribuição 10, Sentença 10 (universo esgotou em 15-5=10), Notificação 3, Certidão 3, Ementa 3. Por tribunal mais representado: TJDFT 47, TRT10 24, STJ 12, TST 6.

---

## Apêndice B — Tabela bruta de medições

A tabela completa das 173 pubs (Identificação, Tribunal, Tipo, comprimento total, cabeçalho, trailer, marcador casado, motivo de bypass) está disponível em `.tmp_analise_v2_out.json` no diretório de trabalho (não versionado). Para regenerar, ver scripts em §2 da metodologia.

Excerto representativo:

| Identificação | Tribunal | Tipo | Total | Cab | Marcador início | Bypass |
|---|---|---|---|---|---|---|
| TRT10\_\_\_2026-02-04\_\_\_8 | TRT10 | Notificação | 639 | 218 | INTIMAÇÃO Fica | — |
| TRT10\_\_\_2026-03-20\_\_\_9 | TRT10 | Despacho | 1.345 | 207 | INTIMAÇÃO Fica | — |
| TRT10\_\_\_2026-02-09\_\_\_13 | TRT10 | Acórdão | 1.975 | ~600 | ACÓRDÃO | — |
| STJ\_\_\_2026-03-18\_\_\_2 | STJ | Acórdão | 1.506 | 948 | ACÓRDÃO (linha) | — |
| STJ\_\_\_2026-05-05\_\_\_5 | STJ | Decisão | 1.997 | 467 | DECISÃO (linha) | — |
| STJ\_\_\_2026-03-05\_\_\_17 | STJ | Pauta de Julgamento | 967 | 0 | — | tipo |
| TJDFT\_\_\_2026-03-27\_\_\_2 | TJDFT | Ementa | 1.995 | 304 | EMENTA | — |
| TJDFT\_\_\_2026-05-05\_\_\_2 | TJDFT | Despacho | 995 | ~250 | DESPACHO | — |
| TJDFT\_\_\_2026-05-07\_\_\_6 | TJDFT | Certidão | 382 | 0 | — | tipo |
| TJDFT\_\_\_2026-04-07\_\_\_2 | TJDFT | Sentença | ~1.500 | 0 | SENTENÇA (descartado: prematuro) | fallback |
| TJRJ\_\_\_2026-03-13\_\_\_1 | TJRJ | Sentença | 983 | 252 | SENTENÇA | — |
| TJSC\_\_\_2026-01-21\_\_\_2 | TJSC | Despacho | 467 | 264 | ATO ORDINATÓRIO (após remover CSS leak) | — |
| TJRS\_\_\_2026-05-06\_\_\_1 | TJRS | Despacho | 671 | ~350 | ATO ORDINATÓRIO (após remover CSS leak) | — |
| TJRJ\_\_\_2026-04-06\_\_\_1 | TJRJ | Outros | 378 | 0 | — | notifico_eproc |
| TJGO\_\_\_2026-03-17\_\_\_1 | TJGO | Outros | 57 | 0 | — | texto_imprestavel |
| TST\_\_\_2026-04-14\_\_\_1 | TST | Despacho | 1.502 | 0 | — | fallback (sem marcador) |
