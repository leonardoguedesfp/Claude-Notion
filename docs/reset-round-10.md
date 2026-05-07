# Reset operacional Round 10

Documento operacional curto. Para o passo a passo do dia, veja a seção
"Receita do operador" no fim.

## Por que existe

O Round 10 (2026-05-07) muda o vocabulário de tags do app — uma
propriedade única `Alerta contadoria (app)` virou três (`Tarefa
advogado`, `Tarefa contadoria`, `Alerta contadoria`). O schema do
Notion já foi alterado pelo Leonardo. Agora ele vai apagar todas as
publicações do Notion na mão e rodar o app do zero contra o histórico
DJEN, pra que cada pub seja recriada com as tags certas pelas regras
novas.

Para essa "captura do zero" funcionar limpo, o app precisa esquecer
que já capturou as 2.270 pubs. O script `scripts/reset_para_round_10.py`
faz isso de forma contida — apenas no `leitor_dje.db`, sem tocar nos
dados estruturais (`cache.db`) nem na auditoria (`audit.db`).

## O que o script faz

1. **Backup** dos 3 SQLite em `%APPDATA%\NotionRPADV\` com sufixo
   `.bak-round10`. Sobrescreve backups anteriores com o mesmo nome.
2. **Reset do `leitor_dje.db`**:
   - `DELETE FROM publicacoes` — apaga todas as ~2.270 pubs já
     capturadas.
   - `DELETE FROM dup_pendentes` — dedup pendente esquecido.
   - `DELETE FROM djen_state` — cursor legado (geralmente vazio).
   - `UPDATE djen_advogado_state SET ultimo_cursor=NULL,
     last_run=NULL` — cursores por OAB voltam pro estado "primeira
     execução".
3. **Arquivamento de `logs/`** — move tudo (XLSX/JSON/MD acumulados)
   pra `archive/round-9/`, **preservando** arquivos com prefixo
   `datajud_` (cache do DataJUD que custou 26min pra gerar).
4. **Marca idempotência** em `app_flags.round_10_reset_done = '1'`
   com timestamp.

## O que NÃO toca

- `cache.db` — Processos (1.240), Clientes (1.072), Tarefas (33),
  Catalogo (68) ficam intactos.
- `audit.db` — edit_log, pending_edits e schemas cacheados pertencem
  ao bulk-edit, sem relação com DJE.
- DataJUD — cache preservado via filtro de prefixo.
- Publicações no Notion — apagadas manualmente pelo usuário na UI,
  não via API.

## Idempotência

O script registra `round_10_reset_done='1'` em `app_flags`. Re-execução
sem `--force` aborta com mensagem informativa. Use `--force` pra
re-rodar (refaz backup + reset + arquivamento).

## Receita do operador

```powershell
cd C:\dev\Claude-Notion
$env:PYTHONPATH = "."

# 1. Preview — mostra o que seria feito, sem escrever
python scripts\reset_para_round_10.py --dry-run

# 2. Aplicar
python scripts\reset_para_round_10.py

# 3. (no Notion, manualmente) selecionar todas as publicações em
#    📬 Publicações e apagar via UI

# 4. Rodar o app — a captura DJE vai detectar todas as OABs com
#    cursor=NULL e fazer o catch-up pelo histórico
python -m notion_rpadv
```

## Tabela de saída

| Recurso | Estado pré-reset (snapshot 2026-05-07) | Estado pós-reset |
|---|---|---|
| `cache.db.records` (Processos/Clientes/Tarefas/Catalogo) | 2.412 linhas | 2.412 linhas (preservado) |
| `audit.db.edit_log` | 28 linhas | 28 linhas (preservado) |
| `leitor_dje.db.publicacoes` | 2.270 linhas | 0 linhas |
| `leitor_dje.db.djen_advogado_state.ultimo_cursor` | populado em 6 OABs | NULL em todas |
| `leitor_dje.db.dup_pendentes` | 1 linha | 0 linhas |
| `logs/*.xlsx`, `logs/*.json`, `logs/*.md` | 30+ arquivos | movidos para `archive/round-9/` |
| `logs/datajud_*` | 6 arquivos | preservados (não movidos) |
| `app_flags.round_10_reset_done` | ausente | `'1'` + timestamp |

## Recuperação

Se algo der errado e o usuário quiser **desfazer**, basta restaurar
os backups:

```powershell
$dir = "$env:APPDATA\NotionRPADV"
copy "$dir\leitor_dje.db.bak-round10" "$dir\leitor_dje.db"
copy "$dir\cache.db.bak-round10"      "$dir\cache.db"
copy "$dir\audit.db.bak-round10"      "$dir\audit.db"
```

E mover os logs de volta de `archive/round-9/` para `logs/`.
