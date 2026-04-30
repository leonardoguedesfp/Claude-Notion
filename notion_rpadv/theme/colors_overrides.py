"""Round 3b-2 — overrides explícitos de cor por (base, propriedade, valor).

Fonte da verdade visual de chips no app. Substitui a cadeia antiga
``cor_por_valor[hex] → hex_to_color_name → chip_colors_for(name)`` (que
mimetizava cores do Notion web). Agora a paleta brand RPADV vence: a cor
configurada no Notion é apenas metadado de schema (preservada em
``PropSpec.cor_por_valor`` para diagnóstico), não influencia rendering.

Cada entrada de ``OVERRIDES`` mapeia ``(base_label, prop_key, value)`` para
uma das 10 famílias da paleta brand:
``default, blue, purple, green, orange, red, yellow, gray, petrol, pink``.

Round 4 (29-abr-2026): família ``pink`` adicionada para diferenciar
variantes de "Peça processual" no Catálogo (cível vs trabalhista vs ambos)
sem reusar cores já alocadas a outros eixos semânticos.

Decisões aplicadas seguindo princípios do Claude Design (round 3b-1):
- Vermelho é caro — só para situações que travam fluxo (Sobrestado, Crítico).
- Petrol é "metadado de fluxo institucional" (secundário da brand).
- Gray é o estado-base honesto.
- Pares opostos (Ativo/Passivo, PF/PJ) com cores complementares blue↔orange.
- Trabalhista é destaque — ganha purple (cor reservada).

Quando o schema do Notion adicionar valor novo não previsto aqui, o
fallback é ``chip_default`` (cinza neutro). Sem crash, só sem cor — sinal
visível pra adicionar entry no override map.
"""
from __future__ import annotations

from typing import Final


# ---------------------------------------------------------------------------
# Property overrides — (base_label, prop_key, value) → family_name
# ---------------------------------------------------------------------------

OVERRIDES: Final[dict[tuple[str, str, str], str]] = {
    # =================================================================
    # Catalogo
    # =================================================================
    # Round 4 (29-abr-2026): schema renomeado pra singular + valores novos.
    #   "Peças processuais" → "Peça processual (cível/trabalhista)"
    #   "Outras tarefas jurídicas" → "Outra tarefa jurídica"
    #   Adicionadas: variantes (cível) e (trabalhista), Controladoria.
    ("Catalogo", "categoria", "Peça processual (cível/trabalhista)"): "blue",
    ("Catalogo", "categoria", "Peça processual (cível)"):             "green",
    ("Catalogo", "categoria", "Peça processual (trabalhista)"):       "pink",
    ("Catalogo", "categoria", "Outra tarefa jurídica"):               "purple",
    ("Catalogo", "categoria", "Controladoria"):                       "yellow",
    ("Catalogo", "categoria", "Administrativo"):                      "petrol",
    ("Catalogo", "categoria", "Diversos"):                            "gray",

    # =================================================================
    # Clientes
    # =================================================================
    # Tipo PF/PJ — PF=default (regra/padrão, ~80% dos casos), PJ=purple (exceção).
    ("Clientes", "tipo", "PF"): "default",
    ("Clientes", "tipo", "PJ"): "purple",

    # Status do cadastro
    ("Clientes", "status_do_cadastro", "Ativo"):    "green",
    ("Clientes", "status_do_cadastro", "Inativo"):  "gray",
    ("Clientes", "status_do_cadastro", "Prospect"): "yellow",

    # Situação funcional — relevante pra causas trabalhistas.
    ("Clientes", "situacao_funcional", "Ativo (em atividade)"): "blue",
    ("Clientes", "situacao_funcional", "Aposentado"):           "green",
    ("Clientes", "situacao_funcional", "Pensionista"):          "green",
    ("Clientes", "situacao_funcional", "Ex-funcionário"):       "orange",
    ("Clientes", "situacao_funcional", "Não se aplica"):        "default",

    # Sexo, Estado civil, UF — DESIGN decidiu texto puro. Sem entradas aqui;
    # rendering não-chip é responsabilidade dos delegates/views.

    # =================================================================
    # Processos
    # =================================================================
    # Fase — adaptado dos nomes reais (Cognitiva ≈ Conhecimento, etc).
    ("Processos", "fase", "Cognitiva"):                          "blue",
    ("Processos", "fase", "Executiva"):                          "green",
    ("Processos", "fase", "Liquidação pendente"):                "yellow",
    ("Processos", "fase", "Liquidação de sentença"):             "petrol",
    ("Processos", "fase", "TJ - sentença não será executada"):   "gray",

    # Instância — superiores agrupados em purple.
    ("Processos", "instancia", "1º grau"): "gray",
    ("Processos", "instancia", "2º grau"): "blue",
    ("Processos", "instancia", "TST"):     "purple",
    ("Processos", "instancia", "STJ"):     "purple",
    ("Processos", "instancia", "STF"):     "purple",

    # Natureza — Trabalhista é área-foco, ganha purple.
    ("Processos", "natureza", "Trabalhista"): "purple",
    ("Processos", "natureza", "Cível"):       "blue",

    # Partes adversas — entidades específicas do BB universe + outras.
    # Diferenciado pra que multi-select com várias entidades fique legível.
    ("Processos", "partes_adversas", "Banco do Brasil"):                       "orange",
    ("Processos", "partes_adversas", "PREVI"):                                 "petrol",
    ("Processos", "partes_adversas", "CASSI"):                                 "green",
    ("Processos", "partes_adversas", "Bradesco Saúde"):                        "blue",
    ("Processos", "partes_adversas", "BB administradora de Consórcios S.A"):   "yellow",
    ("Processos", "partes_adversas", "Outro"):                                 "gray",

    # Posição do cliente — princípio Design: ativo↔passivo = blue↔orange.
    ("Processos", "posicao_do_cliente", "Autor"):      "blue",
    ("Processos", "posicao_do_cliente", "Recorrente"): "blue",
    ("Processos", "posicao_do_cliente", "Réu"):        "orange",
    ("Processos", "posicao_do_cliente", "Recorrido"):  "orange",

    # Status — Tema 955 vira sobrestado em essência.
    ("Processos", "status", "Ativo"):                                "green",
    ("Processos", "status", "Arquivado provisoriamente (tema 955)"): "red",
    ("Processos", "status", "Arquivado"):                            "gray",

    # Tipo de ação (21 valores agrupados em 7 famílias semânticas).
    # Universo BB-centrado revelado pelo schema real.
    # Revisão de benefício (previdenciário/securitário) → blue
    ("Processos", "tipo_de_acao", "Revisão de benefício (Tema 955)"): "blue",
    ("Processos", "tipo_de_acao", "Revisão de benefício (antigo)"):   "blue",
    # Indenização (4 variantes) → orange
    ("Processos", "tipo_de_acao", "Indenização — I"):  "orange",
    ("Processos", "tipo_de_acao", "Indenização — IR"): "orange",
    ("Processos", "tipo_de_acao", "Indenização — RI"): "orange",
    ("Processos", "tipo_de_acao", "Indenização — R"):  "orange",
    # Trabalhista CLT core → green
    ("Processos", "tipo_de_acao", "Verbas trabalhistas"): "green",
    ("Processos", "tipo_de_acao", "Horas extras"):        "green",
    ("Processos", "tipo_de_acao", "Anuênios"):            "green",
    ("Processos", "tipo_de_acao", "Ação de 15 minutos"):  "green",
    ("Processos", "tipo_de_acao", "Periculosidade"):      "green",
    # Estatutárias BB-family → petrol
    ("Processos", "tipo_de_acao", "Ação PREVI"): "petrol",
    ("Processos", "tipo_de_acao", "Ação CASSI"): "petrol",
    # Salarial / Cargo → yellow
    ("Processos", "tipo_de_acao", "Redução Salarial — HE"):   "yellow",
    ("Processos", "tipo_de_acao", "Redução Salarial — PCS"):  "yellow",
    ("Processos", "tipo_de_acao", "Descomissionamento"):      "yellow",
    ("Processos", "tipo_de_acao", "Descomissionamento — LS"): "yellow",
    # Execução → purple (ganho consolidado, fase nobre)
    ("Processos", "tipo_de_acao", "Execução de AC"): "purple",
    # Cauda / Misc → gray
    ("Processos", "tipo_de_acao", "Preservação"):    "gray",
    ("Processos", "tipo_de_acao", "Plano de Saúde"): "gray",
    ("Processos", "tipo_de_acao", "Outra"):          "gray",

    # Tipo de processo — Decisão 3 reaberta (existe com 4 valores ortogonais
    # a Instância/Fase, então vira chip).
    ("Processos", "tipo_de_processo", "Principal"):                "blue",
    ("Processos", "tipo_de_processo", "Incidente"):                "yellow",
    ("Processos", "tipo_de_processo", "Recurso autônomo"):         "orange",
    ("Processos", "tipo_de_processo", "Reclamação constitucional"): "purple",

    # Tribunal — superiores=purple, regionais trabalhistas+DF=blue,
    # estaduais não-DF=green (regionais minoritários do escritório).
    ("Processos", "tribunal", "STF"):    "purple",
    ("Processos", "tribunal", "STJ"):    "purple",
    ("Processos", "tribunal", "TST"):    "purple",
    ("Processos", "tribunal", "TRT/10"): "blue",
    ("Processos", "tribunal", "TRT/2"):  "blue",
    ("Processos", "tribunal", "TJDFT"):  "blue",
    ("Processos", "tribunal", "TJRJ"):   "green",
    ("Processos", "tribunal", "TJRS"):   "green",
    ("Processos", "tribunal", "TJBA"):   "green",
    ("Processos", "tribunal", "TJMG"):   "green",
    ("Processos", "tribunal", "TJSP"):   "green",
    ("Processos", "tribunal", "TJSC"):   "green",
    ("Processos", "tribunal", "TJPR"):   "green",
    ("Processos", "tribunal", "TJMS"):   "green",
    ("Processos", "tribunal", "TJES"):   "green",
    ("Processos", "tribunal", "TJGO"):   "green",
    ("Processos", "tribunal", "Outro"):  "gray",

    # =================================================================
    # Tarefas
    # =================================================================
    # Round 4 (29-abr-2026): schema expandido — Status passou de 2 pra 6
    # valores, Área e Prioridade adicionadas como propriedades novas.
    #
    # Status — fluxo expandido com 4 valores intermediários/terminais.
    ("Tarefas", "status", "Pendente"):              "blue",
    ("Tarefas", "status", "Em revisão"):            "orange",
    ("Tarefas", "status", "Aguardando protocolo"):  "purple",
    ("Tarefas", "status", "Concluída"):             "green",
    ("Tarefas", "status", "Cancelada"):             "gray",
    ("Tarefas", "status", "Prejudicada"):           "red",

    # Área — propriedade nova; en-dash U+2013 separa nome da sigla.
    ("Tarefas", "area", "Cível – CC"):                "blue",
    ("Tarefas", "area", "Trabalhista – CT"):          "green",
    ("Tarefas", "area", "Execução cível – EC"):       "purple",
    ("Tarefas", "area", "Execução trabalhista – ET"): "orange",
    ("Tarefas", "area", "Liquidação cível – LSC"):    "red",

    # Prioridade — propriedade nova; Normal=default (regra/padrão silenciosa).
    ("Tarefas", "prioridade", "Normal"):  "default",
    ("Tarefas", "prioridade", "Alta"):    "orange",
    ("Tarefas", "prioridade", "Urgente"): "red",
}


# ---------------------------------------------------------------------------
# PersonChip — cor de avatar por iniciais
# ---------------------------------------------------------------------------

# Distribuição alfabética por iniciais ciclando 7 famílias usáveis (skip
# `red` reservado pra crítico e `default` reservado pra regra/padrão).
# Decisão 15 do Round 3b-1: hierarquia por cargo descartada (artificial),
# família `blue-light` rejeitada — paleta fica em 9 famílias.
#
# Para novos usuários no futuro: continuar o ciclo na ordem alfabética da
# inicial — inserção mantém o mapeamento existente intacto.

PERSON_CHIP_COLORS: Final[dict[str, str]] = {
    "AB": "blue",      # Amanda Bessa
    "BA": "purple",    # Beatriz Andrade
    "CR": "green",     # Camila Rocha
    "DM": "orange",    # Déborah Marques
    "FL": "yellow",    # Fernanda Lima
    "GP": "gray",      # Gustavo Pacheco
    "HC": "petrol",    # Henrique Cordeiro
    "JC": "blue",      # Juliana Carvalho
    "LN": "purple",    # Larissa Nogueira
    "LV": "green",     # Leonardo Vieira
    "MS": "orange",    # Mariana Souto
    "PH": "yellow",    # Pedro Henrique
    "PT": "gray",      # Patrícia Tavares
    "RA": "petrol",    # Rodrigo Aguiar
    "RM": "blue",      # Rafael Mendes
    "RP": "purple",    # Ricardo Passos
    "TB": "green",     # Thiago Borges
}
