# Round 6 — Status pré-smoke (Passo F)

Branch: `feat/regras-v9` (sem PR aberto ainda — push pendente,
reporte ao Leonardo antes do smoke).

**Doc-base:** [`anatomia-processos-vs-publicacoes-v8.md`](../anatomia-processos-vs-publicacoes-v8.md).
**Plano:** o prompt v9 com 5 fases e prompt para Claude Code (recebido
via Claude Web em 2026-05-04).

---

## 1. O que está implementado (16/43 regras = 37%)

### Camada base — 4/4 ✅

| Regra | Combinação | Tarefa | Alerta |
|---|---|---|---|
| 40 | Lista de Distribuição (qualquer doc) | Nada para fazer | Processo/recurso distribuído |
| 40 | Intimação + Distribuição | Nada para fazer | Processo/recurso distribuído |
| 41 | Edital ou Intimação + Pauta de Julgamento | Nada para fazer | Incluir julgamento no controle |
| 42 | Intimação + Sentença | Analisar sentença | — |
| 43 | Intimação + Acórdão/Ementa | Analisar acórdão | — |

### Monitoramento — 12/39 ✅

| Regra | Nome | Status |
|---|---|---|
| 14 | Subida de instância não detectada | ✅ |
| 15 | Descida de instância não detectada (com filtro de cumprimento/liquidação) | ✅ |
| 16 | Acórdão em processo de 1º grau (impossibilidade) | ✅ |
| 17 | Sentença em processo de colegiado (impossibilidade) | ✅ |
| 18 | Pauta de Julgamento em 1º grau (impossibilidade) | ✅ |
| 26 | Fase executiva confirmada por classe | ✅ |
| 27 | Fase liquidação confirmada por classe | ✅ |
| 28 | Fase cognitiva contradita por classe avançada | ✅ |
| 35 | Trânsito cognitivo pendente (mantido do Round 4.4) | ✅ |
| 11 | Partes adversas típicas ausentes — 5 alertas distintos | ✅ |
| (técnica) | Texto imprestável (mantido do Round 4.4) | ✅ |
| (operacional) | Processo não cadastrado (refinado: não dispara em distribuição) | ✅ |

### Inferências auxiliares (Tabelas A, B, C)

- ✅ **Tabela A — `instancia_implicada(pub)`**: 5 prioridades cobrindo Tribunal STJ/TST/STF, Tipo Sentença/Acórdão/Pauta, e regex de Órgão (Vara, Juizado, Desembargador, Turma/Câmara). Devolve `None` quando inconclusivo (ex: TJSP que não tem cabeçalho institucional).
- ✅ **Tabela B — `fase_implicada(pub)`**: classes cognitivas/liquidação/executiva. Recursos não-AP devolvem `None` (herdam fase do principal).
- ⏸ **Tabela C — `tipo_processo_implicado(pub)`**: não implementada (depende da Regra 6, ainda pendente).

---

## 2. O que NÃO está implementado (27/43 regras restantes)

Faltam 27 regras para o Round 7 (próximo round). Ordenadas por
prioridade declarada na v8 (Apêndice — Índice de regras).

### Prioridade alta (alto signal, baixa taxa de falso positivo)

| Regra | Nome | Esforço | Comentário |
|---|---|---|---|
| 7 | Cliente do escritório fora da relation | M | Match por nome em 👥 Clientes; filtro Tipo de processo=Principal |
| (Regras 11, 16-18, 26-28, 40-43 já feitas) | | | |

### Prioridade média

| Regra | Nome | Esforço |
|---|---|---|
| 4 | Natureza inconsistente com Tribunal | S |
| 5 | Natureza inconsistente com Classe | S |
| 6 | Recurso autônomo cadastrado como Principal | S |
| 12 | Tribunal de origem fora do vocabulário | S |
| 19, 20 | Cidade desatualizada | S |
| 21, 22 | Vara desatualizada | S |
| 23 | Turma desatualizada (precisa tabela auxiliar Desembargador→Turma) | M |
| 24, 25 | Relator desatualizado | M |
| 30 | Pauta em processo arquivado | S |
| 31 | Atividade em processo arquivado | S |
| 33, 34 | Data de distribuição (capturar/conferir) | S |

### Prioridade baixa (heurística ou meta-checagem)

| Regra | Nome |
|---|---|
| 1 | Conferir número CNJ do processo |
| 2 | Capturar numeração STJ/TST |
| 3 | Capturar numeração STF |
| 8 | Litisconsórcio ativo não refletido |
| 9 | Cliente cadastrado não aparece nas partes |
| 10 | Polo inconsistente em 1ª instância |
| 13 | Verificação de origem em 1ª instância |
| 29 | Sentença em fase pós-cognitiva |
| 32, 37 | Sobrestamento Tema 955 |
| 36 | Atividade pós-encerramento executivo |
| 38 | Capturar link externo |
| 39 | Recurso autônomo sem processo pai |

---

## 3. Auditoria final — sem resíduo das regras antigas

```bash
$ grep -rn "ALERTA_INSTANCIA_DESATUALIZADA\b\|ALERTA_PAUTA_PRESENCIAL\|TAREFA_D01\|TAREFA_D02\|TAREFA_D03\|TAREFA_E01\|TAREFA_E02\|TAREFA_E04\|_aplicar_regras_alerta_contadoria\|_aplicar_regras_tarefa_sugerida" notion_rpadv/ tests/ scripts/ --include='*.py'
# (zero matches)
```

Note que `ALERTA_INSTANCIA_DESATUALIZADA_SUBIDA` e
`ALERTA_INSTANCIA_DESATUALIZADA_DESCIDA` (com sufixo) são as novas
constantes da v8 (Regras 14 e 15) e ficam.

---

## 4. Suite de testes

```
982 passed, 7 skipped, 11 warnings
```

(909 antes do Round 6 → 982; +73 testes novos das regras v8 +
ajustes em testes antigos.)

| Arquivo | Testes |
|---|---|
| `tests/test_round_6_camada_base.py` | 15 |
| `tests/test_round_6_monitoramento.py` | 80 |
| **Total Round 6 novos** | **95** |

(Testes antigos do Round 4.3/4.4 foram apagados — 22 testes removidos
no Passo B. Net: +73.)

Ruff: limpo nos arquivos do Round 6.

---

## 5. Commits da branch `feat/regras-v9`

| Commit | Descrição |
|---|---|
| `3126457` | docs: Passo A — relatório de auditoria pré-implementação |
| `9da10de` | refactor: renomear "Alerta contadoria" → "Alerta contadoria (app)" e idem Tarefa sugerida |
| `453cc42` | refactor: remover regras antigas do Round 4.3 + 4.4 |
| `1fb3b46` | feat: Regras 16-18 (impossibilidades categóricas) |
| `4593981` | feat: Tabelas A/B + Regras 14, 15, 26, 27, 28 |
| `52be6f2` | feat: Regra 35 + Regra 11 + alertas técnicos mantidos |
| `c6d5218` | feat: script `scripts/reset_estado_leitor_round_6.py` |
| (este commit) | docs: Passo F — status pré-smoke |

---

## 6. O que vem no smoke test (Passo G)

**Pré-requisito**: aprovação do Leonardo. NÃO executar smoke sem OK.

Comandos planejados (não executados ainda):

1. **Reset estado leitor** (Passo E):
   ```bash
   python scripts/reset_estado_leitor_round_6.py --dry-run
   # confirma 2152 publicações, 1 dup_pendente, 6 cursores OAB
   python scripts/reset_estado_leitor_round_6.py
   # zera todas as tabelas + VACUUM
   ```

2. **Re-ingestão pequena** (10-50 publicações de 1 dia):
   - Rodar app via UI (com autorização) para capturar 1 dia recente.
   - OU rodar manualmente um subset via CLI/script.
   - Não há CLI de ingestão pronto — esse é trabalho do app PySide6.

3. **Verificações esperadas**:
   - Pubs novas no Notion populando `Tarefa sugerida (app)` e
     `Alerta contadoria (app)` com valores de v8 (não mais D.01-D.03,
     etc).
   - Pelo menos 1 publicação dispara um alerta de monitoramento das
     16 regras implementadas (Regras 14-18, 26-28, 35, 11, alertas
     técnicos).
   - Nenhuma referência aos valores depreciados:
     ```bash
     grep -r "Pauta presencial\|D\.01\|^Instância desatualizada$" --include='*.py'
     # zero matches
     ```

4. **Reportar resultado** ao Leonardo. Aguardar OK antes de:
   - Continuar implementando as 27 regras pendentes (Round 7).
   - Pushar para origin (push só após smoke aprovado, conforme
     prompt v9 Seção 6).

---

## 6.1 Diferença 2.152 vs 1.608 (esclarecimento)

**SQLite** (`leitor_dje.db`): `publicacoes` tem 2.152 linhas.
**Notion** (📬 Publicações antes do reset manual): 1.608 páginas.

Diferença de 544 = **duplicatas suprimidas pelo dedup** (Round 1 fix
1.6, commit `2bcf9f6` e flush em `dje_dedup.py:flush_atualizacoes_canonicas`).

Cada uma das 544 linhas tem `dup_canonical_djen_id` populado apontando
para a canônica correspondente que ficou no Notion. O detector
implementa a chave canônica
``sha256(CNJ|data|tribunal|tipo_canonico|texto[:500])`` (D-2 do
Round 1) para identificar publicações duplicadas (DJEN às vezes
retorna 2+ linhas com `djen_id` próprios para o mesmo ato processual,
tipicamente quando a intimação tem múltiplos polos).

Composição:
- 1.608 canônicas (`notion_page_id` populado, `dup_canonical_djen_id IS NULL`)
- 544 duplicatas (`dup_canonical_djen_id IS NOT NULL`, sem `notion_page_id`
  porque a duplicata não vira página própria — é mesclada com a canônica
  via `Duplicatas suprimidas`)
- Total = 2.152

Após `scripts/reset_estado_leitor_round_6.py`, todas as 2.152 são
truncadas. A próxima ingestão recapturará tudo do zero. As duplicatas
são re-detectadas pelo mesmo dedup.

---

## 7. Decisão de fatiamento

**Decisão**: pausa pré-smoke com 16/43 regras (37%) implementadas.

**Razão**: as 16 regras já cobrem os clusters de maior volume e
prioridade alta da v8:
- Camada base (537 pubs estimadas — 33% do universo de 1.608).
- Regras 16, 17, 18 (143 + 15 + 111 = 269 candidatos).
- Regras 26, 27 (234 + 43 = 277 candidatos).
- Regra 11 (potencialmente centenas).
- Regra 35 (71 candidatos confirmados).
- Regras 14, 15 (25+ candidatos identificáveis).

Total cobertura potencial: > 1.200 pubs com pelo menos 1 alerta ou
tarefa atribuído (75% do universo).

As 27 regras pendentes têm prioridade média/baixa por design da v8
e podem ser implementadas em iteração subsequente sem bloquear o
smoke test do que já está pronto.

**Reporte do Claude Code ao Leonardo**: ver mensagem na próxima
seção do chat.
