/* global window */
// Sample data for the Notion RPADV desktop app prototype.
// CNJs and CPFs are plausible patterns but fictional; names are common BR names.

const TRIBUNAIS = [
  { value: 'STF', label: 'STF', color: 'purple' },
  { value: 'STJ', label: 'STJ', color: 'purple' },
  { value: 'TST', label: 'TST', color: 'purple' },
  { value: 'TJDFT', label: 'TJDFT', color: 'blue' },
  { value: 'TRT/10', label: 'TRT/10', color: 'blue' },
  { value: 'TRT/2', label: 'TRT/2', color: 'blue' },
  { value: 'TRF/1', label: 'TRF/1', color: 'green' },
  { value: 'JFDF', label: 'JFDF', color: 'green' },
];

const FASES = [
  { value: 'Conhecimento', label: 'Conhecimento', color: 'gray' },
  { value: 'Recurso', label: 'Recurso', color: 'orange' },
  { value: 'Execução', label: 'Execução', color: 'yellow' },
  { value: 'Cumprimento', label: 'Cumprimento', color: 'petrol' },
  { value: 'Sobrestado', label: 'Sobrestado', color: 'red' },
  { value: 'Trânsito em julgado', label: 'Trânsito em julgado', color: 'green' },
];

const STATUS_PROC = [
  { value: 'Ativo', label: 'Ativo', color: 'green' },
  { value: 'Sobrestado', label: 'Sobrestado', color: 'red' },
  { value: 'Suspenso', label: 'Suspenso', color: 'orange' },
  { value: 'Arquivado', label: 'Arquivado', color: 'gray' },
];

const INSTANCIAS = [
  { value: '1ª', label: '1ª instância', color: 'gray' },
  { value: '2ª', label: '2ª instância', color: 'blue' },
  { value: 'Superior', label: 'Superior', color: 'purple' },
];

const PRIORIDADES = [
  { value: 'Crítica', label: 'Crítica', color: 'red' },
  { value: 'Alta', label: 'Alta', color: 'orange' },
  { value: 'Normal', label: 'Normal', color: 'gray' },
  { value: 'Baixa', label: 'Baixa', color: 'petrol' },
];

const STATUS_TAREFA = [
  { value: 'A fazer', label: 'A fazer', color: 'gray' },
  { value: 'Em andamento', label: 'Em andamento', color: 'blue' },
  { value: 'Aguardando', label: 'Aguardando', color: 'yellow' },
  { value: 'Concluída', label: 'Concluída', color: 'green' },
];

const PESSOAS = [
  { id: 'deborah', name: 'Déborah', initials: 'DM', role: 'Administradora' },
  { id: 'leonardo', name: 'Leonardo', initials: 'LV', role: 'Sócio em formação' },
  { id: 'ricardo', name: 'Ricardo', initials: 'RP', role: 'Sócio fundador' },
  { id: 'mariana', name: 'Mariana', initials: 'MS', role: 'Advogada' },
  { id: 'carla', name: 'Carla', initials: 'CB', role: 'Estagiária' },
];

// 60 processos
const NOMES_CLIENTES = [
  'Ronaldo Gesser', 'Maria Helena Sá', 'José Carlos Albuquerque', 'Lúcia Mendonça',
  'Antônio Pereira Filho', 'Beatriz Carvalho', 'Eduardo Tavares', 'Patrícia Lins',
  'Vinícius Andrade', 'Cláudia Bittencourt', 'Marcos Vieira', 'Renata Soares',
  'Fernando Magalhães', 'Adriana Quintino', 'Sérgio Bastos', 'Tereza Coelho',
  'Hugo Sampaio', 'Camila Resende', 'Otávio Brandão', 'Mariana Vasconcelos',
  'Paulo Henrique Reis', 'Sandra Lobo', 'Felipe Aragão', 'Letícia Falcão',
  'Bruno Castro', 'Juliana Peixoto', 'Diego Carvalho', 'Vânia Drummond',
  'Rafael Toledo', 'Aline Macedo', 'Igor Bezerra', 'Helena Furtado',
  'Carlos Eduardo Nunes', 'Fátima Aguiar', 'Roberto Cavalcanti', 'Cristina Pacheco',
  'Júlio Veloso', 'Mônica Beltrão', 'André Leite', 'Daniela Pimentel',
];

function randCNJ(year, tribunal) {
  const seq = String(Math.floor(Math.random() * 9999999)).padStart(7, '0');
  const dv = String(Math.floor(Math.random() * 99)).padStart(2, '0');
  const segmento = tribunal.startsWith('TRT') ? '5' : tribunal.startsWith('STF') ? '0' : tribunal.startsWith('STJ') ? '3' : '8';
  const tr = tribunal === 'TRT/10' ? '10' : tribunal === 'TRT/2' ? '02' : tribunal === 'TJDFT' ? '07' : tribunal === 'STF' ? '00' : tribunal === 'STJ' ? '00' : '01';
  const orig = String(Math.floor(Math.random() * 9999)).padStart(4, '0');
  return `${seq}-${dv}.${year}.${segmento}.${tr}.${orig}`;
}

function randCPF() {
  const a = String(Math.floor(Math.random() * 999)).padStart(3, '0');
  const b = String(Math.floor(Math.random() * 999)).padStart(3, '0');
  const c = String(Math.floor(Math.random() * 999)).padStart(3, '0');
  const d = String(Math.floor(Math.random() * 99)).padStart(2, '0');
  return `${a}.${b}.${c}-${d}`;
}

// Seeded pseudo-random for repeatability
let _seed = 7;
function rand() { _seed = (_seed * 9301 + 49297) % 233280; return _seed / 233280; }
function pick(arr) { return arr[Math.floor(rand() * arr.length)]; }
function randInt(min, max) { return Math.floor(rand() * (max - min + 1)) + min; }

const CLIENTES_LIST = NOMES_CLIENTES.map((nome, i) => {
  const isFalecido = i % 11 === 0;
  return {
    id: `c${i + 1}`,
    nome,
    cpf: randCPF(),
    email: nome.toLowerCase().replace(/\s+/g, '.').normalize('NFD').replace(/[\u0300-\u036f]/g, '') + '@email.com',
    telefone: `(61) 9${randInt(8000, 9999)}-${String(randInt(0, 9999)).padStart(4, '0')}`,
    falecido: isFalecido,
    nProcessos: randInt(0, 6),
    cidade: pick(['Brasília/DF', 'Taguatinga/DF', 'Ceilândia/DF', 'Águas Claras/DF', 'Sobradinho/DF', 'Goiânia/GO']),
    cadastrado: `${randInt(2018, 2024)}-${String(randInt(1, 12)).padStart(2, '0')}-${String(randInt(1, 28)).padStart(2, '0')}`,
    notas: i % 5 === 0 ? 'Cliente recorrente — atendido pela Déborah.' : '',
  };
});

const PROCESSOS_LIST = Array.from({ length: 60 }, (_, i) => {
  const tribunal = pick(TRIBUNAIS).value;
  const year = randInt(2017, 2024);
  const fase = pick(FASES).value;
  const cliente = CLIENTES_LIST[i % CLIENTES_LIST.length];
  const isTema955 = i % 13 === 0;
  return {
    id: `p${i + 1}`,
    cnj: randCNJ(year, tribunal),
    tribunal,
    instancia: pick(INSTANCIAS).value,
    fase: isTema955 ? 'Sobrestado' : fase,
    status: isTema955 ? 'Sobrestado' : pick(STATUS_PROC).value,
    cliente: cliente.nome,
    clienteId: cliente.id,
    parteContraria: pick(['União Federal', 'INSS', 'Banco Bradesco S/A', 'Caixa Econômica Federal', 'Petrobras Distribuidora', 'Telefônica Brasil S/A', 'Município de Brasília']),
    distribuicao: `${year}-${String(randInt(1, 12)).padStart(2, '0')}-${String(randInt(1, 28)).padStart(2, '0')}`,
    valorCausa: randInt(15, 850) * 1000,
    responsavel: pick(PESSOAS).id,
    tema955: isTema955,
    sucessao: i % 17 === 0,
    observacoes: i % 7 === 0 ? 'Aguardando publicação de acórdão.' : '',
  };
});

// Tarefas (40)
function daysFromNow(d) {
  const dt = new Date();
  dt.setDate(dt.getDate() + d);
  return dt.toISOString().slice(0, 10);
}

const TAREFAS_LIST = Array.from({ length: 40 }, (_, i) => {
  const proc = PROCESSOS_LIST[i % PROCESSOS_LIST.length];
  const offsetOptions = [-3, -1, 0, 1, 2, 3, 5, 7, 10, 14, 21, 30];
  const offset = offsetOptions[i % offsetOptions.length];
  const tipos = [
    'Protocolar petição inicial',
    'Apresentar contestação',
    'Recorrer da sentença',
    'Manifestar sobre laudo pericial',
    'Requerer juntada de documentos',
    'Cumprir intimação',
    'Acompanhar audiência',
    'Solicitar perícia médica',
    'Verificar publicação no DJE',
    'Atualizar cálculos',
    'Reunião com cliente',
    'Revisar minuta',
  ];
  return {
    id: `t${i + 1}`,
    titulo: tipos[i % tipos.length],
    prazoFatal: daysFromNow(offset),
    processo: proc.cnj,
    processoId: proc.id,
    cliente: proc.cliente,
    responsavel: pick(PESSOAS).id,
    prioridade: offset < 0 ? 'Crítica' : offset < 3 ? 'Alta' : 'Normal',
    status: offset < 0 ? 'Em andamento' : pick(STATUS_TAREFA).value,
    catalogoTipo: pick(['Petição', 'Audiência', 'Recurso', 'Cálculo', 'Reunião']),
  };
});

const CATALOGO_LIST = [
  { id: 'k1', titulo: 'Petição inicial trabalhista', categoria: 'Petição', area: 'Trabalhista', tempoEstimado: '4h', responsavelPadrao: 'leonardo', revisado: '2024-08-12' },
  { id: 'k2', titulo: 'Recurso ordinário', categoria: 'Recurso', area: 'Trabalhista', tempoEstimado: '6h', responsavelPadrao: 'leonardo', revisado: '2024-09-03' },
  { id: 'k3', titulo: 'Audiência inaugural', categoria: 'Audiência', area: 'Trabalhista', tempoEstimado: '2h', responsavelPadrao: 'mariana', revisado: '2024-07-22' },
  { id: 'k4', titulo: 'Cálculo de liquidação', categoria: 'Cálculo', area: 'Geral', tempoEstimado: '3h', responsavelPadrao: 'deborah', revisado: '2024-09-18' },
  { id: 'k5', titulo: 'Manifestação sobre laudo pericial', categoria: 'Petição', area: 'Trabalhista', tempoEstimado: '2h', responsavelPadrao: 'leonardo', revisado: '2024-06-30' },
  { id: 'k6', titulo: 'Reunião de alinhamento — cliente PJ', categoria: 'Reunião', area: 'Empresarial', tempoEstimado: '1h', responsavelPadrao: 'ricardo', revisado: '2024-09-25' },
  { id: 'k7', titulo: 'Embargos de declaração', categoria: 'Recurso', area: 'Geral', tempoEstimado: '3h', responsavelPadrao: 'leonardo', revisado: '2024-08-04' },
  { id: 'k8', titulo: 'Habilitação de sucessão', categoria: 'Petição', area: 'Geral', tempoEstimado: '2h', responsavelPadrao: 'deborah', revisado: '2024-05-12' },
  { id: 'k9', titulo: 'Acompanhamento de pauta', categoria: 'Audiência', area: 'Geral', tempoEstimado: '0,5h', responsavelPadrao: 'carla', revisado: '2024-10-01' },
  { id: 'k10', titulo: 'Verificação de DJE', categoria: 'Outros', area: 'Geral', tempoEstimado: '0,3h', responsavelPadrao: 'carla', revisado: '2024-10-04' },
  { id: 'k11', titulo: 'Atualização monetária', categoria: 'Cálculo', area: 'Trabalhista', tempoEstimado: '2h', responsavelPadrao: 'deborah', revisado: '2024-07-15' },
  { id: 'k12', titulo: 'Resposta de oficio', categoria: 'Petição', area: 'Geral', tempoEstimado: '1,5h', responsavelPadrao: 'mariana', revisado: '2024-08-28' },
];

// Logs (recent activity)
const LOGS_LIST = Array.from({ length: 35 }, (_, i) => {
  const minsAgo = i * 13 + randInt(2, 30);
  const dt = new Date(Date.now() - minsAgo * 60000);
  const proc = PROCESSOS_LIST[i % PROCESSOS_LIST.length];
  const props = [
    { name: 'Status', from: 'Ativo', to: 'Sobrestado' },
    { name: 'Fase', from: 'Conhecimento', to: 'Recurso' },
    { name: 'Responsável', from: 'Mariana', to: 'Leonardo' },
    { name: 'Tribunal', from: 'TJDFT', to: 'TRT/10' },
    { name: 'Observações', from: '(vazio)', to: 'Aguardando publicação.' },
    { name: 'Prazo fatal', from: '2024-10-15', to: '2024-10-22' },
    { name: 'Status', from: 'A fazer', to: 'Concluída' },
  ];
  const prop = props[i % props.length];
  const ok = i % 9 !== 0;
  return {
    id: `l${i + 1}`,
    timestamp: dt.toISOString(),
    usuario: pick(PESSOAS).id,
    base: pick(['Processos', 'Tarefas', 'Clientes', 'Catálogo']),
    identificador: proc.cnj,
    propriedade: prop.name,
    valorAntigo: prop.from,
    valorNovo: prop.to,
    status: ok ? 'OK' : 'ERRO',
    mensagemErro: ok ? null : 'rate_limited: aguardar 3s e retentar',
    revertido: false,
    justificativa: i % 4 === 0 ? 'Atualização em massa via planilha (set/24).' : '',
  };
});

// Import preview (for the Importar screen)
const IMPORT_PREVIEW = [
  { action: 'create',   cnj: '0801234-55.2024.5.10.0001', cliente: 'Eduardo Tavares',     fase: 'Conhecimento', status: 'Ativo',      valor: 'R$ 78.500',  note: '' },
  { action: 'create',   cnj: '0802201-19.2024.5.10.0008', cliente: 'Patrícia Lins',       fase: 'Conhecimento', status: 'Ativo',      valor: 'R$ 142.000', note: '' },
  { action: 'update',   cnj: '0709812-66.2023.5.10.0014', cliente: 'Ronaldo Gesser',      fase: 'Recurso',      status: 'Ativo',      valor: 'R$ 215.000', note: 'Fase: Conhecimento → Recurso' },
  { action: 'update',   cnj: '0506677-08.2022.4.01.3400', cliente: 'Maria Helena Sá',     fase: 'Cumprimento',  status: 'Ativo',      valor: 'R$ 92.300',  note: 'Status: Suspenso → Ativo' },
  { action: 'conflict', cnj: '0103445-72.2023.8.07.0001', cliente: 'Lúcia Mendonça',      fase: 'Recurso',      status: 'Ativo',      valor: 'R$ 56.000',  note: 'Editado no Notion em 18/03 14:22 — revisar' },
  { action: 'conflict', cnj: '0011223-44.2023.5.10.0010', cliente: 'Antônio Pereira F.',  fase: 'Sobrestado',   status: 'Sobrestado', valor: 'R$ 380.000', note: 'Tema 955 — não sobrescrever sem revisão' },
  { action: 'create',   cnj: '0801556-33.2024.5.10.0002', cliente: 'Beatriz Carvalho',    fase: 'Conhecimento', status: 'Ativo',      valor: 'R$ 64.200',  note: '' },
  { action: 'update',   cnj: '0008812-19.2022.5.02.0042', cliente: 'Vinícius Andrade',    fase: 'Execução',     status: 'Ativo',      valor: 'R$ 124.700', note: 'Valor: R$ 98.000 → R$ 124.700' },
  { action: 'skip',     cnj: '0203344-55.2021.8.07.0007', cliente: 'Cláudia Bittencourt', fase: 'Conhecimento', status: 'Arquivado',  valor: 'R$ 12.000',  note: 'Linha duplicada na planilha' },
  { action: 'create',   cnj: '0809988-77.2024.5.10.0005', cliente: 'Marcos Vieira',       fase: 'Conhecimento', status: 'Ativo',      valor: 'R$ 88.450',  note: '' },
  { action: 'update',   cnj: '0410045-21.2022.4.01.3400', cliente: 'Renata Soares',       fase: 'Recurso',      status: 'Ativo',      valor: 'R$ 167.000', note: 'Responsável: Mariana → Leonardo' },
  { action: 'create',   cnj: '0812334-66.2024.5.10.0003', cliente: 'Fernando Magalhães',  fase: 'Conhecimento', status: 'Ativo',      valor: 'R$ 53.700',  note: '' },
];

window.RPDATA = {
  TRIBUNAIS, FASES, STATUS_PROC, INSTANCIAS, PRIORIDADES, STATUS_TAREFA, PESSOAS,
  CLIENTES_LIST, PROCESSOS_LIST, TAREFAS_LIST, CATALOGO_LIST, LOGS_LIST, IMPORT_PREVIEW,
};
