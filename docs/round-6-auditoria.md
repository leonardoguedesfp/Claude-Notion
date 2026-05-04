# Round 6 — Auditoria pré-implementação (Passo A)

Relatório do mapeamento que precede a remoção das regras antigas e a
implementação das 43 regras v8 (4 camada base + 39 monitoramento).

**Branch:** `feat/regras-v9`
**Doc-base:** [`anatomia-processos-vs-publicacoes-v8.md`](../anatomia-processos-vs-publicacoes-v8.md)

---

## 1. Schema atual do Notion (estado pós-Fases 1-3 do plano)

Confirmado via MCP `notion-fetch` no data source `78070780-8ff2-4532-8f78-9e078967f191`:

### `Tarefa sugerida (app)` — multi-select, 3 valores

```
Analisar acórdão (purple)
Analisar sentença (blue)
Nada para fazer (default)
```

### `Alerta contadoria (app)` — multi-select, 41 valores

3 antigos mantidos (Processo não cadastrado, Trânsito em julgado pendente,
Texto imprestável) + 38 novos (todos da v8).

### Outras propriedades relevantes

- `Tipo de comunicação`: select (Intimação, Edital, Lista de Distribuição)
- `Tipo de documento`: select (11 valores: Notificação, Distribuição, Acórdão,
  Decisão, Despacho, Pauta de Julgamento, Certidão, Ementa, Sentença, Edital, Outros)
- `Tribunal`: select (15 valores)
- `Classe`: text livre (com normalização Round 4.2)
- `Órgão`: text livre
- `feedback`: text — propriedade nova, não estava no plano. Sem signal documentado.
- `Status`: select (Nova, Nada para fazer, Tratada, Pré-migração)

**Conclusão:** schema do Notion está pronto para receber payloads conforme v8.
Código atual ainda usa nomes sem `(app)` — Passo B vai renomear.

---

## 2. Estado atual do código (5 regras antigas)

### 2.1 Constantes em `notion_rpadv/services/dje_notion_mapper.py`

**Alertas (5)** — linhas 389-393:

| Constante | Valor | Status v8 |
|---|---|---|
| `ALERTA_PROCESSO_NAO_CADASTRADO` | "Processo não cadastrado" | **Manter** (refinada — não para distribuições) |
| `ALERTA_INSTANCIA_DESATUALIZADA` | "Instância desatualizada" | **Remover** — substituído por 5 alertas específicos (Regras 14-18) |
| `ALERTA_TRANSITO_PENDENTE` | "Trânsito em julgado pendente" | **Manter** (Regra 35) |
| `ALERTA_TEXTO_IMPRESTAVEL` | "Texto imprestável" | **Manter** (técnico) |
| `ALERTA_PAUTA_PRESENCIAL_SEM_INSCRICAO` | "Pauta presencial sem inscrição" | **Remover** — substituído por `Incluir julgamento no controle` (Regra 41) |

**Tarefas (6)** — linhas 486-491:

| Constante | Valor | Status v8 |
|---|---|---|
| `TAREFA_D03_ANALISE_ACORDAO` | "D.03 Análise de acórdão" | **Renomear** → "Analisar acórdão" (Regra 43) |
| `TAREFA_D02_ANALISE_SENTENCA` | "D.02 Análise de sentença" | **Renomear** → "Analisar sentença" (Regra 42) |
| `TAREFA_D01_ANALISE_PUBLICACAO` | "D.01 Análise de publicação" | **Remover** — sem default catch-all na v8 |
| `TAREFA_E01_CADASTRO` | "E.01 Cadastro de cliente/processo" | **Remover** — fora do select (app); operador atribui manual via `Tarefa sugerida` (não-app) se quiser |
| `TAREFA_E02_ATUALIZAR_DADOS` | "E.02 Atualizar dados no sistema" | **Remover** — idem |
| `TAREFA_E04_INSCRICAO_SUSTENTACAO` | "E.04 Inscrição para sustentação oral" | **Remover** — idem |

A v8 só tem 3 valores em `Tarefa sugerida (app)`: `Analisar acórdão`,
`Analisar sentença`, `Nada para fazer`. As tarefas E.01/E.02/E.04 não
aparecem no select (app) — se forem usadas pela contadoria, será via
outra propriedade ou manual pelo operador.

### 2.2 Funções com lógica das regras antigas

**`_aplicar_regras_alerta_contadoria`** — `dje_notion_mapper.py:420-477`

Aplica os 5 alertas antigos. Dispara:
- Processo não cadastrado se `processo_record is None`
- Instância desatualizada se `Pub.Tribunal in (TST, STJ, STF)` e `Proc.Instancia in (1º grau, 2º grau)` (cobre só subida)
- Trânsito pendente se `Pub.Classe contains CUMPRIMENTO` (sem PROVISÓRIO) e `Proc.Data trânsito *` vazia
- Texto imprestável (heurística len < 200 + padrões)
- Pauta presencial sem inscrição (Pauta de Julgamento + texto contém PRESENCIAL)

**`_aplicar_regras_tarefa_sugerida`** — `dje_notion_mapper.py:494-557`

Aplica as 6 tarefas antigas seguindo regras D.01 (default catch-all),
D.02 (sentença), D.03 (acórdão/ementa), E.01 (sem cadastro), E.02
(STJ ATA + alerta instância), E.04 (Pauta de Julgamento).

**`_calcular_status_inicial`** — `dje_notion_mapper.py:352-390`

Round 4.5a: retorna `"Nada para fazer"` para Listas TRT10/TST cadastradas;
default `"Nova"` para o resto. **Manter** — Status é select separado de
Tarefa sugerida; v8 não substitui esse comportamento.

### 2.3 Atribuição às propriedades

**`montar_payload_publicacao`** — `dje_notion_mapper.py:670-679`

Payload final atribui:
```python
"Tarefa sugerida": _multi_select_prop(tarefas_sugeridas),
"Alerta contadoria": _multi_select_prop(alertas_contadoria),
```

**Renomear para `(app)`** em ambas as linhas (Passo B).

### 2.4 Testes que exercitam regras antigas

| Arquivo | Padrão de testes |
|---|---|
| `tests/test_round_4.py` | Testes das 5 regras de alerta + 6 tarefas (Round 4.3 + 4.4); inclui sentinela br djen=494748109 |
| `tests/test_round_4_5.py` | Testes do auto-Status Listas TRT10/TST (Round 4.5a, mantido) + filtro Atas TJDFT (Round 4.5b, mantido) |
| `tests/test_dje_notion_mapper.py` | Testes do `montar_payload_publicacao` ponta-a-ponta |
| `tests/test_round_5_partes.py` | Round 5a — Partes JSON cru (mantido) |
| `tests/test_round_5_texto_br.py` | Round 5b — `<br>` literal (mantido) |
| `tests/test_round_1.py` | Round 1 — incluindo teste R1.6 atualizado em Round 5a (mantido) |

**Decisões para Passo F**:
- Apagar testes que validam `D.01 catch-all`, `Pauta presencial sem inscrição`,
  `Instância desatualizada` (genérica), `E.01/E.02/E.04` (não estão no select
  app).
- Adaptar testes que validam `D.02→Analisar sentença` e `D.03→Analisar acórdão`
  (renomeação).
- Manter testes que validam `Trânsito em julgado pendente`, `Texto imprestável`,
  `Processo não cadastrado` (estes alertas continuam, com refinamentos).
- Manter intactos: Round 4.5a/b, Round 5a/b, Round 1, e o resto da suite que
  não toca regras de tarefa/alerta.

---

## 3. Estado persistente do leitor (`%APPDATA%\NotionRPADV\leitor_dje.db`)

Tabelas e o que cada uma guarda (de `dje_db.py:_SCHEMA_DDL`):

| Tabela | Guarda | Reset Round 6 |
|---|---|---|
| `djen_state` | Cursor singleton legado (Fase 3 original) | Truncar |
| `djen_advogado_state` | Cursor por OAB (`numero_oab + uf_oab → ultimo_cursor + last_run`) | Truncar — força próxima execução a refazer todo histórico |
| `publicacoes` | 2.152 linhas (1.608 canônicas + 544 duplicatas), com `notion_page_id` para 1.608 | **Truncar** |
| `dup_pendentes` | Fila de duplicatas a serem flushadas no Notion | Truncar |
| `app_flags` | Flags one-shot (`notion_primeira_carga_v1`, `reativacao_4_advogados_2026_05_02_treated`) | Truncar |

**Cache do Notion** (`%APPDATA%\NotionRPADV\cache.db`): contém Processos
(1.108), Clientes (1.072), Catálogo (68), Tarefas (33) — leitura do schema
do Notion, não estado do leitor. **NÃO resetar** — esse cache é necessário
para as regras de monitoramento cruzarem `Pub × Proc`.

---

## 4. Plano de commits (incrementais, na branch `feat/regras-v9`)

| # | Commit | Conteúdo | Status |
|---|---|---|---|
| 1 | `docs(round-6): relatório Passo A` | Este arquivo | em curso |
| 2 | `refactor(round-6): renomear propriedades para (app)` | Renomear `"Alerta contadoria"` → `"Alerta contadoria (app)"`, `"Tarefa sugerida"` → `"Tarefa sugerida (app)"` em código + testes | próximo |
| 3 | `refactor(round-6): remover regras antigas` | Apagar 5 alertas + 6 tarefas antigas; remover funções `_aplicar_regras_*`; apagar testes obsoletos | seguinte |
| 4 | `feat(round-6): camada base (Regras 40-43)` | Implementar matriz Tipo de comunicação × Tipo de documento | depois |
| 5+ | `feat(round-6): regras de monitoramento <seção>` | Regras 1-39 em commits por seção (I, II, III, IV, V, VI) | depois |
| N-1 | `feat(round-6): script de reset estado leitor (CLI)` | Passo E | depois |
| N | `docs(round-6): pendencias.md + MIGRACAO.md` | Documentar comando de re-ingestão | depois |

**Antes do smoke test (Passo G)**: pytest verde, ruff verde, branch
pushada, e reporte ao Leonardo aguardando OK para rodar o reset + 1 dia
de DJE.

---

## 5. Pontos de atenção identificados

1. **Renomeação `(app)`**: vai precisar tocar mapper.py + `montar_payload_publicacao`
   + `montar_payload_dedup` (em `dje_dedup.py:_build_update_payload`)
   + 3 testes que ainda mencionam o nome sem sufixo.

2. **`Status` (Round 4.5a) intacto**: o auto-Status `Nada para fazer` em
   Listas TRT10/TST cadastradas continua. Não confundir com o valor
   `Nada para fazer` da `Tarefa sugerida (app)` (Regras 40-41 da camada
   base) — são propriedades diferentes (`Status` vs `Tarefa sugerida (app)`).

3. **Tabela A (instância_implicada) — regex de Órgão**: TRT usa "X ª Vara
   do Trabalho", TJDFT usa "X ª Vara Cível", STJ/TST tem prefixos
   diferentes, e o "ª" pode ser unicode. Centralizar normalização.
   Regras 16/17/18 são as mais simples (instância depende só de Tipo
   de documento — vão primeiro).

4. **Filtros importantes** (do prompt v9):
   - Regras 7-9 (Cliente fora da relation): filtrar `Tipo de processo=Principal` para evitar 113 falsos positivos dos recursos.
   - Regra 35 (Trânsito): só `Cumprimento de Sentença`, **excluindo** `Cumprimento Provisório`.
   - Regra 15 (Descida): excluir Cumprimento e Liquidação para não falso-positivar retornos legítimos.

5. **Composição com camada base**: regras de monitoramento ADICIONAM
   alertas, não substituem. Pub pode ter `[Camada base alerta + 2 regras
   de monitoramento]`.

6. **Regra 11 (Partes adversas)**: dispara 5 alertas distintos. Implementar
   como tabela mapeando substring → alerta.

---

## 6. Critério de conclusão (Round 6)

- [ ] Os 5 alertas antigos e as 4 tarefas antigas (D.01-D.03 + E.01/02/04)
  totalmente removidos sem resíduo (audit `grep` final).
- [ ] 43 regras v8 implementadas e testadas.
- [ ] Smoke test com 10-50 publicações reais aprovado pelo Leonardo.
- [ ] `pytest` verde + `ruff` limpo nos arquivos tocados.
- [ ] `pendencias.md` atualizado.
- [ ] Branch pushada, sem merge para main (PR via GitHub web).

---

**Início do trabalho.** Próximo commit: renomeação `(app)` (Passo B preparatório).
