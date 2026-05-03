# Round 1 — Fixes pré-re-migração massiva DJE×Notion (2026-05-03)

8 fixes que preparam o app pra absorver a re-migração das 2141
publicações jan-mai/2026 sem reproduzir os bugs identificados na 1ª
migração massiva.

## Sumário das mudanças

| # | Fix | Onde | Severidade |
|---|---|---|---|
| 1.1 | Mapeamento de Tipo de documento | `dje_notion_mappings.py` | Alto |
| 1.2 | Mapeamento de Tipo de comunicação | `dje_notion_mappings.py` | Médio |
| 1.3 | Multi-select de advogados (formato canônico "Nome (OAB/UF)") | `dje_notion_mappings.py` | Alto |
| 1.4 | Block split com detecção de seções (anti bug "100 blocos") | `dje_text_pipeline.py` | Crítico |
| 1.5 | Filtragem inteligente Pautas TJDFT + truncamento + callout | `dje_text_pipeline.py` | Crítico |
| 1.6 | Detector de duplicatas + flush canônicas | `dje_dedup.py` + `dje_db.py` | Alto |
| 1.7 | Pre-processador HTML | `dje_text_pipeline.py` | Alto |
| 1.8 | Truncamento limpo do campo Texto inline | `dje_text_pipeline.py` | Cosmético |

## Novos módulos

```
notion_rpadv/services/
├── dje_notion_mappings.py   ← 1.1, 1.2, 1.3
├── dje_text_pipeline.py     ← 1.4, 1.5, 1.7, 1.8
└── dje_dedup.py             ← 1.6
```

## Pipeline ponta a ponta

```
publicacao DJEN
  ↓ 1.7 preprocessar_texto_djen (HTML → texto puro)
texto_pre
  ↓ chave canônica dedup (1.6)
  ↓ 1.5 aplicar_caso_15 (filtragem TJDFT / truncamento + callout)
texto_corpo + callouts
  ↓ 1.4 quebrar_em_blocos (heading_3 por seção + paragraphs)
blocos_corpo
  ↓ +callouts +observações
children pronto pra Notion API

texto_pre → 1.8 truncar_texto_inline → property "Texto"
```

## Migrações SQLite

Todas idempotentes (rodam em banco pré-Round-1 ou já migrado sem erro):

- `publicacoes` ganha 2 colunas: `dup_chave TEXT`,
  `dup_canonical_djen_id INTEGER`.
- Índice parcial `idx_publicacoes_dup_chave` (`WHERE dup_chave IS NOT NULL`).
- Tabela nova `dup_pendentes` (canonical_djen_id, duplicata_djen_id,
  duplicata_destinatario, partes_json, advogados_json, created_at).

## Desvio do spec

O prompt sugeria 3 colunas pra dedup (`dup_canonical_id` +
`dup_canonical_djen_id`). Como `djen_id` já é a PK da tabela
`publicacoes`, unifiquei numa única coluna `dup_canonical_djen_id`
(serve como FK lógica). Sem perda funcional.

## Validações

### Suite de testes

- **818 passed, 7 skipped, 0 failing** (era 728+7 na baseline da Fase 5;
  +84 testes do Round 1).
- `tests/test_round_1.py`: 87 testes unitários cobrindo os 8 fixes.
- `tests/smoke_test_round_1.py`: 5 testes integrados contra SQLite real
  (skip automático se ausente). Validações:
  - Pipeline completa em 8 djen_ids alvo + 12 random (sem exceções).
  - Par TRT10 djen=527365047/527365146 → mesma chave canônica.
  - Pauta TJDFT djen=506249151 (1.2MB bruto) → 1996 chars filtrados
    (1 de 334 processos do escritório).
  - Acórdão TST djen=524358619 (248KB bruto) → 80KB truncado + callout
    com URL da certidão DJEN.

### Lint

`ruff check` limpo nos 8 arquivos novos/modificados (F401, E402, F811).

### Decisões consolidadas D-1 a D-9

Todas mantidas e cobertas por testes. Detalhes:

- **D-1** (tipoDocumento null/vazio → Outros): `test_R1_1_null_e_vazio_caem_em_outros`
- **D-2** (CNJ ausente → não deduplica): `test_R1_6_chave_canonica_cnj_nulo_devolve_none`
- **D-3 B** (acumular em dup_pendentes, 1 update no fim): implementado em
  `flush_atualizacoes_canonicas`
- **D-4** (Status NÃO altera no flush): `test_R1_6_flush_chama_update_page_e_limpa_pendentes`
  (assert "Status" not in props)
- **D-5 A** (advogados = união): `test_R1_6_merge_advogados_uniao_ordenada`
- **D-6** (html.unescape): `test_R1_7_html_unescape_basico`
- **D-7** (canônica = ordem `data_disp ASC, djen_id ASC`): `find_canonical_by_chave`
  ORDER BY
- **D-8** (404 silencioso + warning): `test_R1_6_flush_404_descarta_pendentes_d8`
- **D-9** (pauta com 0 escritório match → nota explicativa): `test_R1_5_filtragem_pauta_d9_zero_matches`

## Discrepância com Anexo A do spec

O prompt classifica djen=508345146 como caso D-9 ("sem match"). Validação
contra dados reais mostra **1 de 253 processos** do escritório. O algoritmo
cobre ambos os casos corretamente — a classificação no Anexo A era uma
estimativa, não uma quebra das decisões D-1 a D-9.

## Não-escopo (Round 2/3)

Round 1 NÃO inclui (conforme prompt):
- Criação da propriedade "Duplicatas suprimidas" no Notion (Round 2).
  App emite gracefully — só inclui no payload se
  `schema_tem_duplicatas_suprimidas=True` é passado.
- Apagamento das 2108 páginas existentes (Round 2).
- Reenvio das 33 falhas (Round 3 absorve via re-migração).
- Rodar a re-migração massiva em si.
