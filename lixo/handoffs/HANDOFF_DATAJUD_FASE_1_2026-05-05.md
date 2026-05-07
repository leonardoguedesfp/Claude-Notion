# Handoff — DataJUD Fase 1 (mergeado em main, 2026-05-05)

Contexto para retomar o trabalho em outra sessão. Estado real validado
após PR #22 mergeado em `main`, smoke do operador aprovado, suite
1214 testes verdes.

---

## TL;DR

**Feature DataJUD Fase 1 entregue.** Aba nova "DataJUD CNJ" no app
desktop gera planilha xlsx de revisão humana a partir de consultas à
API pública DataJud do CNJ. **Não escreve no Notion** — operador
revisa e aplica via aba Importar existente.

**6 componentes:**
1. Cliente HTTP (`datajud_client.py`)
2. Enricher com 14 propriedades + heurísticas TPU
3. Writer xlsx (compat aba Importar)
4. Parser de input do Modo B (string + xlsx + DV módulo 97)
5. Worker QThread paralelo (1 client por thread)
6. Página `DataJUDPage` com 2 modos + integração

**Smoke real aprovado** nos 3 CNJs do escritório:
- `0000449-71.2025.5.10.0003` (TRT/10 1º grau)
- `0000789-22.2019.5.10.0004` (TRT/10 → TST)
- `0016539-47.2015.8.07.0001` (TJDFT Tema 955 — divergência aceita)

**Speedup 2.7×** validado após fix de cliente compartilhado.

---

## Estado atual do projeto

| | |
|---|---|
| Branch atual | `main` |
| Último commit em main | `109c506 Merge pull request #22 from leonardoguedesfp/feat/datajud-fase-1` |
| Suite de testes | **1214 passed, 10 skipped, 0 falhas** |
| Lint (ruff) | limpo nos arquivos novos da feature |
| mypy strict | 0 erros nos arquivos novos; 2 pré-existentes (`datajud_client.py` import-untyped de requests; `notion_bulk_edit/schemas.py` call-overload) |

Histórico recente (`git log --oneline -16 main`):

```
109c506 Merge pull request #22 from leonardoguedesfp/feat/datajud-fase-1
107347e test(datajud-worker): cancel() retorna imediatamente
64c3399 fix(datajud-page): feedback visual imediato no cancelamento
83f570d fix(datajud-worker): pool de clients HTTP por worker para paralelismo real
c911332 feat(datajud): worker QThread + página DataJUD + integração (Componentes 5+6)
79742ce feat(datajud): parser de input do Modo B (Componente 4)
95adc88 fix(datajud): aplicar máscara CNJ ao Número do processo sugerido
b39b44d feat(datajud): writer xlsx — planilha de revisão humana (Componente 3)
e5d7037 docs(datajud): nota arquitetural _grau_alvo + page_id em ResultadoEnriquecimento
915e1f3 fix(datajud): TPU oficial CNJ + heurísticas refatoradas + SUP→GS + Vara tolerante
22fa06c feat(datajud): guarda numeroProcesso divergente em _extract_sources
2690a0d refactor(datajud): vocabulário Notion + assertions + Liquidação pendente
5002df4 fix(datajud): código 123 (RPV) usado por engano em fixtures de relator
8280b78 feat(datajud): enricher + heurísticas + fixtures (Componente 2)
befaa09 feat(datajud): consultar_multi no cliente HTTP
96cc399 feat(datajud): cliente HTTP DataJud + 14 testes (Componente 1)
```

---

## Estrutura da feature DataJUD Fase 1

### Arquivos novos

```
notion_rpadv/services/
├── datajud_client.py           ← HTTP client síncrono pra api-publica.datajud.cnj.jus.br
├── datajud_enricher.py         ← Heurísticas TPU + 14 propriedades + grau alvo Notion
├── datajud_input_parser.py     ← Parser do Modo B (string/xlsx, validação DV módulo 97)
├── datajud_worker.py           ← QThread worker, ThreadPoolExecutor, 1 client/thread
└── datajud_xlsx_writer.py      ← Geração da planilha de revisão humana

notion_rpadv/pages/
└── datajud.py                  ← DataJUDPage com Modo A + Modo B (wizard 3 passos)

tests/
├── test_datajud_client.py        ← 17 testes
├── test_datajud_enricher.py      ← 36 testes
├── test_datajud_xlsx_writer.py   ← 13 testes
├── test_datajud_input_parser.py  ← 21 testes
├── test_datajud_worker.py        ← 11 testes
├── test_datajud_page_smoke.py    ← 8 testes
└── fixtures/datajud/             ← 6 fixtures JSON (sources Elasticsearch-like)
    ├── trt10_g1_simples.json
    ├── trt10_g2_subiu_tst.json
    ├── tjdft_g1_arquivado.json
    ├── tjdft_g1_tema_955.json    ← sentinela
    ├── stj_recurso.json
    └── nao_encontrado.json
```

### Arquivos alterados (integração)

```
notion_rpadv/app.py            ← +DataJUDPage, _PAGE_DATAJUD, _NAV_COMMANDS, command palette
notion_rpadv/widgets/sidebar.py ← +"datajud" em _DADOS_NAV, _ICONS["datajud"] = "🔎"
tests/test_audit_smoke.py       ← whitelist outbound URL "api-publica.datajud.cnj.jus.br"
```

---

## Decisões arquiteturais críticas

### 1. Códigos TPU oficiais (vs spec inicial invertido)

O spec inline original (do compass_artifact que o Leonardo não tinha disponível) estava com vários códigos invertidos. Smoke real expôs e foi corrigido:

```python
# Códigos TPU oficiais — Resolução CNJ 46/2007
COD_TRANSITO_EM_JULGADO  = 848        # spec antigo dizia 11009 (que é Despacho)
COD_DESPACHO             = 11009      # NOVO, só pra docs/asserts
COD_BAIXA_DEFINITIVA     = 22
COD_ARQUIVAMENTO_DEFINITIVO = 246
COD_SOBRESTAMENTO        = frozenset({11025, 12066, 14978, 14981})
COD_LEVANTAMENTO_SOBRESTAMENTO = 12067   # spec antigo dizia 11458
COD_LIQUIDACAO           = frozenset({471, 11528})
COD_SENTENCA             = 219

# Removidos (eram baseados em códigos errados):
# - COD_CUMPRIMENTO (848 era trânsito, não cumprimento)
# - COD_RPV (123 = Remessa)
# - COD_PRECATORIO (61 não confirmado)

# Substituídos por classes processuais (mais robusto):
CLASSES_EXECUCAO = frozenset({159, 156, 11538, 1111})
```

### 2. "Maior grau" segue cadastro Notion

Status, Fase, Instância e Turma derivam do **grau cadastrado no Notion**, não do maior grau retornado pela API. Decisão preserva intenção do operador:

```python
def _grau_alvo(processo_notion: dict) -> str:
    """Mapeia Instância cadastrada → G1/G2/GS."""
    instancia = (processo_notion.get("Instância") or "").strip()
    if instancia == "1º grau":   return "G1"
    if instancia == "2º grau":   return "G2"
    if instancia in ("TST", "STJ", "STF"):  return "GS"
    return "G1"  # fallback
```

Implicação: se cadastro está desatualizado (ex.: processo subiu mas Notion ainda diz "2º grau"), enricher reporta G2 e **não detecta a subida**. Operador deve conferir Instância antes de rodar enriquecimento em massa. Documentado na aba Instruções.

### 3. SUP é sinônimo de GS (TST)

API DataJud retorna `_source.grau = "SUP"` para o TST, não `"GS"` como assumido inicialmente. Normalização em 2 pontos:

```python
# datajud_client.py
_GRAU_ORDEM: Final[dict[str, int]] = {"G1": 0, "G2": 1, "GS": 2, "SUP": 2}

# datajud_enricher.py
def sources_por_grau(sources: list) -> dict[str, dict]:
    out = {}
    for src in sources:
        grau_raw = str(src.get("grau") or "").strip()
        chave = "GS" if grau_raw in ("GS", "SUP") else grau_raw
        # ...
```

### 4. Máscara CNJ aplicada ao "Número do processo" sugerido

API devolve sem máscara (`00004497120255100003`); Notion cadastra com máscara (`0000449-71.2025.5.10.0003`). Sem normalização, **todos** os processos sairiam como divergentes por motivo cosmético. Helper `formatar_cnj_com_mascara()` aplicado em `Número do processo` e `Número STJ/TST`.

### 5. Encoding `?` no nome de órgão

API DataJud corrompe acentos: `"22ª VARA CÍVEL DE BRASÍLIA"` vira `"22? VARA C?VEL DE BRAS?LIA"`. Regex de Vara aceita `?` como sinônimo de `ª/º`:

```python
re.compile(r"(\d+)\s*[ªºA?]?\s*Vara", re.IGNORECASE)
```

### 6. Cidade via codigoMunicipioIBGE

Decisão arquitetural: usar IBGE em vez de regex sobre nome do órgão. Mais preciso e estável. Cidade desconhecida loga WARNING `cidade IBGE desconhecida: %d (CNJ %s)` e devolve None — não bloqueia.

```python
CIDADE_POR_IBGE: dict[int, str] = {
    5300108: "Brasília",
    # adicionar conforme WARNING aparecer no smoke real
}
```

### 7. 1 client HTTP por thread do pool

**Bug exposto no Smoke 4** (10 processos em 60s = 6s/proc, esperado ~2s/proc com 4 workers): cliente compartilhado serializava por causa do throttle per-instance + lock implícito da `requests.Session`. Fix:

```python
# datajud_worker.py
class DataJudWorker:
    def __init__(self, ..., client_factory: Callable[[], DataJudClient], ...):
        self._client_factory = client_factory
        self._tls = threading.local()  # 1 client por thread

    def _get_thread_client(self) -> DataJudClient:
        client = getattr(self._tls, "client", None)
        if client is None:
            client = self._client_factory()
            self._tls.client = client
        return client
```

Speedup confirmado: **2.7×** com 4 CNJs reais (44.9s → 16.3s).

### 8. Tema 955 — limitação documentada

Heurística detecta sobrestamento por Tema 955 quando há mov. ∈ `COD_SOBRESTAMENTO` com complemento "tema 955" e sem `12067` posterior. Mas: para processos sobrestados antes da plena adoção do DataJud (~2018-2020), o movimento original pode estar ausente. Enricher sugere "Arquivado" em vez de "Arquivado provisoriamente (tema 955)" — divergência amarela esperada, operador decide. Sentinela com fixture controlada (`tjdft_g1_tema_955.json`) continua verde.

---

## API DataJud — referência rápida

```
POST https://api-publica.datajud.cnj.jus.br/api_publica_<endpoint>/_search
Headers:
  Authorization: APIKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==
  Content-Type: application/json
  User-Agent: RicardoPassosAdvocacia-DataJUD/0.1 (...)
Body:
  {"query": {"match": {"numeroProcesso": "<20-digitos>"}}, "size": 10}

Override APIKey: env DATAJUD_APIKEY (com ou sem prefixo "APIKey ").
```

15 endpoints mapeados (Tribunal Notion → slug DataJud):

```
TJDFT, TRT/10→trt10, TRT/2→trt2, TST, STJ,
TJSP, TJRJ, TJRS, TJBA, TJMG, TJSC, TJPR, TJMS, TJES, TJGO

(STF não tem endpoint público; "Outro" não suportado)
```

Política de retry:
- 3 tentativas, backoffs (2.0s, 8.0s)
- 429 honra Retry-After (cap 60s)
- 4xx ≠ 429 sem retry
- Throttle per-instance: 2.0s entre chamadas

---

## 14 Propriedades enriquecidas (REGRAS_ORIGEM)

| # | nome_notion | grau | confiança |
|---|---|---|---|
| 1 | Número do processo | qualquer | alta |
| 2 | Tribunal | menor | alta |
| 3 | Instância | maior | alta |
| 4 | Vara | menor | alta |
| 5 | Cidade | menor | alta |
| 6 | Data de distribuição | menor | alta |
| 7 | Data do trânsito em julgado (cognitiva) | menor (fallback maior) | alta |
| 8 | Status | maior | alta |
| 9 | Fase | maior | alta |
| 10 | Número STJ/TST | STJ ou TST | alta |
| 11 | Turma no 2º grau | G2 | alta |
| 12 | Turma no STJ/TST | STJ ou TST | alta |
| 13 | Relator no 2º grau | G2 | **baixa** |
| 14 | Relator no STJ/TST | STJ ou TST | **baixa** |

23 propriedades fora-do-escopo viram coluna `▸ atual` oculta no xlsx (auditoria).

---

## Performance esperada (pós-fix do worker)

Com 4 workers paralelos × 1 client cada:
- CNJ só TJ (~5s/req): ~48 CNJ/min
- CNJ que subiu ao TST (~28s com timeout): ~8.6 CNJ/min
- Mix 90% TJ + 10% TST: **~30 CNJ/min**

A latência alta no TST é hard-floor da API (timeouts ~30s frequentes), fora do controle do app.

---

## Pendências operacionais (não bloqueantes)

### 1. Fase 2 do DataJUD (futura)

Possíveis evoluções:
- **Escrita direta no Notion** (sem aba Importar como passo manual). Usar `NotionFacade` + `CommitWorker` existentes.
- **Cache de respostas DataJud** em SQLite (`cache.db`). Hoje o worker consulta sempre; cache reduz latência em re-runs.
- **Detecção de Tema 955 via assuntos** (`assunto.codigo == 4805 = Previdência privada` é forte indicador). Combinar com Status=Arquivado para confiança baixa.
- **Captura automática** de campos atualmente fora do escopo (Detalhamento, Partes adversas via texto, etc.).

### 2. Refinamentos de heurística

- `derivar_relator` é "baixa confiança" — refinar com código TPU específico de "Atribuição de relator" quando aparecer no smoke. Olhar `complementosTabelados` em runs reais.
- `CIDADE_POR_IBGE` tem só Brasília (5300108). Expandir conforme WARNING `"cidade IBGE desconhecida: %d (CNJ %s)"` aparecer.
- `COD_LIQUIDACAO` tem só {471, 11528}. Smoke real pode revelar outros códigos.
- `DATAJUD_TRIBUNAL_TO_NOTION` cobre 15. Tribunal não-mapeado loga WARNING `"DataJUD: tribunal não mapeado: %r (CNJ %s)"`.

### 3. mypy strict — `import-untyped` de requests

Pré-existente em `datajud_client.py` e `dje_client.py`. Resolução fora do escopo da feature: `chore(deps)` com `pip install types-requests` + entrada em `requirements-dev.txt`. Tarefa pequena, isolada.

### 4. Branches locais de outras features

- `analise-anatomia-pubs` — 9 commits órfãos (não-mergeados em main). Decidir: preservar / `git branch -D` / cherry-pick. Conteúdo: análise de anatomia de publicações pré-Round 4.
- 4 worktrees do Claude (`claude/*`) ativas no harness — gerenciamento automático.

### 5. Untracked não-Fase no working tree

- `.coverage`, HANDOFFs antigos (`HANDOFF_*.md`), `RELATORIO-AUDITORIA.md`, `anatomia-processos-vs-publicacoes-v8.md`, `scripts/auditoria_kurier/`, CSV antigo de export Notion. Pré-existentes desde Round 4. Decidir destino em algum round futuro.

---

## Documentos relevantes na main

```
HANDOFF_ROUND_7_V8_2026-05-04.md           ← Round 7+v8 (estado pré-DataJUD)
HANDOFF_DATAJUD_FASE_1_2026-05-05.md       ← ESTE handoff
docs/anatomia-publicacoes-pos-round-4.md   ← anatomia v4 (1740 linhas)
docs/round-5-fix-regressoes-p0.md
docs/round-6-auditoria.md
docs/round-6-status.md
README.md
CHANGELOG_ROUND_1.md, CHANGELOG_ROUND_2.md
```

---

## Scripts auxiliares na main

`scripts/`:
- `reset_estado_leitor_round_6.py` — trunca SQLite local
- `setar_cursor_pre_smoke.py` — pré-seta cursor das 6 OABs
- `inspecionar_smoke_v8.py` — relatório pós-smoke v8
- `resync_partes_round_5.py` — script one-shot do Round 5

`scripts/analise/` (untracked, do Round 7 análise alertas):
- `analise_alertas_round_7.py`

---

## Memórias / preferências do Leonardo

(de `~/.claude/projects/C--dev-Claude-Notion/memory/MEMORY.md`)

1. **Trabalhar no main repo, não em worktree** — `cd /c/dev/Claude-Notion` direto.
2. **Paleta brand RPADV vence Notion** — chips no app usam brand do escritório.
3. **PR + merge pelo GitHub web pelo Leonardo** — Claude faz commit + push de branch nova, NÃO faz merge direto em main, salvo exceções explícitas.
4. **Push direto na main** quando explicitamente autorizado (Round 4.5/4.6, scripts auxiliares de smoke).

---

## Como continuar a conversa em outro chat

Cole no início do novo chat:

> Estou continuando o projeto Claude-Notion (app desktop PySide6 +
> bases Notion). A Fase 1 da feature DataJUD foi mergeada em main
> (PR #22, commit `109c506`). 1214 testes verdes.
>
> Estado:
> - main em `109c506`
> - Aba "DataJUD CNJ" funcional com Modo A (varredura completa) +
>   Modo B (wizard 3 passos pra lista manual)
> - 6 componentes implementados: cliente HTTP, enricher (14 props +
>   TPU oficial), writer xlsx (compat aba Importar), parser DV módulo 97,
>   worker QThread paralelo (1 client/thread, speedup 2.7×), página
>   integrada
> - Sentinela Tema 955 verde com fixture; smoke real em 3 CNJs aprovou
>
> Detalhes em `HANDOFF_DATAJUD_FASE_1_2026-05-05.md` na main.
>
> Próximo passo: [descrever o que quer]

---

## Comandos úteis

### Verificar estado do banco
```python
python -c "
import os, sqlite3
from pathlib import Path
db = Path(os.environ['APPDATA']) / 'NotionRPADV' / 'leitor_dje.db'
conn = sqlite3.connect(str(db))
print('publicacoes:', conn.execute('SELECT COUNT(*) FROM publicacoes').fetchone()[0])
"
```

### Rodar suite completa
```
cd /c/dev/Claude-Notion
.venv/Scripts/python.exe -m pytest tests/ --no-header -q
# esperado: 1214 passed, 10 skipped
```

### Rodar testes específicos da feature DataJUD
```
.venv/Scripts/python.exe -m pytest tests/test_datajud_*.py -v
# esperado: 106 passed (17+36+13+21+11+8)
```

### Lint focado nos arquivos da feature
```
.venv/Scripts/python.exe -m ruff check \
  notion_rpadv/services/datajud_*.py \
  notion_rpadv/pages/datajud.py \
  tests/test_datajud_*.py
# esperado: All checks passed!
```

### Testar o cliente real contra a API DataJud
```python
from notion_rpadv.services.datajud_client import DataJudClient
client = DataJudClient()
sources = client.consultar('0000449-71.2025.5.10.0003', 'trt10')
print(f'{len(sources)} grau(s) encontrado(s)')
```

### Rodar enricher contra os 3 CNJs reais
```python
from notion_rpadv.services.datajud_client import DataJudClient
from notion_rpadv.services.datajud_enricher import enriquecer
client = DataJudClient()
proc = {
    'page_id': 'p1',
    'Número do processo': '0000449-71.2025.5.10.0003',
    'Tribunal':            'TRT/10',
    'Instância':           '1º grau',
}
res = enriquecer(proc, client=client)
print(res.diagnostico, res.propriedades_sugeridas)
```

### Gerar planilha de amostra (sem rodar o app)
```python
# Vide logs/datajud_amostra_3cnjs.xlsx (gerada no Componente 3)
# Ou rodar o script de geração manual usado no Checkpoint 3.
```

### Inspecionar planilhas no logs/
```
logs/datajud_amostra_3cnjs.xlsx               ← amostra fixa (Componente 3)
logs/datajud_amostra_3cnjs_v2.xlsx            ← amostra com schema real (37 props)
logs/datajud_consulta_2026-05-05-1457.xlsx    ← Smoke 4 do Leonardo
logs/datajud_consulta_2026-05-05-1503.xlsx    ← Smoke 4
logs/datajud_consulta_2026-05-05-1526.xlsx    ← Smoke 5 (pós-fix)
logs/datajud_consulta_2026-05-05-1529.xlsx    ← Smoke 5 (pós-fix)
logs/datajud_modo_a.png                        ← screenshot Modo A
logs/datajud_modo_b_step1.png                  ← screenshot Modo B Step 1
logs/datajud_modo_b_step2.png                  ← screenshot Modo B Step 2
```

---

## Contexto crítico para o próximo Claude

### Como rodar o app
**Não rodo PySide6 em ambiente headless.** Quando precisar rodar o app
real, peço ao Leonardo abrir `python -m notion_rpadv` e executar
manualmente. Eu inspeciono o resultado via SQLite + MCP + scripts.

### Worktree vs main repo
A memória diz pra trabalhar direto em `C:\dev\Claude-Notion`, não em
worktree. Mas o harness do Claude Code coloca a sessão em
`C:\dev\Claude-Notion\.claude\worktrees\<algo>` por default. Operar
via `git -C /c/dev/Claude-Notion ...` ou `cd /c/dev/Claude-Notion &&
...` resolve sem migrar.

### PR e merge
Claude **NÃO abre PR** via `gh` nem faz merge direto em main, salvo
autorização explícita. Padrão: Claude commita + pusha branch nova
(`feat/<slug>`) e dá a URL `https://github.com/leonardoguedesfp/Claude-Notion/pull/new/<branch>`
para o Leonardo abrir e mergear no GitHub web.

### Encoding cp1252 vs utf-8 no Windows
Vários scripts crasham no print de caracteres como `→`, `📬`, `ª`.
Sempre rodar com `PYTHONIOENCODING=utf-8` antes do comando Python.

### `requests` import-untyped
mypy strict reclama de `import-untyped` em arquivos que importam
`requests`. É pré-existente (`dje_client.py` tem o mesmo). Resolução
deferida: instalar `types-requests` em `chore(deps)` futuro.

### Fixtures de schema do Notion
`tests/fixtures/schemas/processos_raw.json` é o snapshot real da API
GET `/v1/data_sources/{id}` da base ⚖️ Processos. Tem 37 propriedades
(14 enriquecidas + 23 auxiliares). Para testes sem chamar o registry
do Notion, usar essa fixture.

### Latência do TST é hard-floor
O endpoint `tst` da API DataJud está com timeouts frequentes (~30s).
Mesmo com 4 clients paralelos, qualquer CNJ que tem grau no TST vai
custar ~28s (timeout + retry). É limitação da API, não do app.

---

## Total de testes da feature por arquivo

| Arquivo | Testes |
|---|---:|
| `test_datajud_client.py` | 17 |
| `test_datajud_enricher.py` | 36 |
| `test_datajud_xlsx_writer.py` | 13 |
| `test_datajud_input_parser.py` | 21 |
| `test_datajud_worker.py` | 11 |
| `test_datajud_page_smoke.py` | 8 |
| **Total DataJUD** | **106** |

Suite completa do projeto (com testes pré-existentes): **1214 passed**.
