/* global window */
// V2 data — anchored to real numbers (1108 procs, 1072 clients, 17 users).

const V2_USERS = [
  { id: 'ricardo',    name: 'Ricardo Passos',     initials: 'RP', role: 'Sócio fundador',     active: false, last: 'hoje · 09:42' },
  { id: 'deborah',    name: 'Déborah Marques',    initials: 'DM', role: 'Administradora',     active: true,  last: 'agora' },
  { id: 'leonardo',   name: 'Leonardo Vieira',    initials: 'LV', role: 'Sócio em formação',  active: false, last: 'hoje · 10:15' },
  { id: 'mariana',    name: 'Mariana Souto',      initials: 'MS', role: 'Advogada sênior',    active: false, last: 'hoje · 11:02' },
  { id: 'fernanda',   name: 'Fernanda Lima',      initials: 'FL', role: 'Advogada júnior',    active: false, last: 'ontem · 17:30' },
  { id: 'rafael',     name: 'Rafael Mendes',      initials: 'RM', role: 'Advogado júnior',    active: false, last: 'hoje · 08:55' },
  { id: 'juliana',    name: 'Juliana Carvalho',   initials: 'JC', role: 'Advogada',           active: false, last: '24/04 · 16:11' },
  { id: 'pedro',      name: 'Pedro Henrique',     initials: 'PH', role: 'Estagiário',         active: false, last: 'hoje · 09:18' },
  { id: 'camila',     name: 'Camila Rocha',       initials: 'CR', role: 'Estagiária',         active: false, last: 'hoje · 10:40' },
  { id: 'beatriz',    name: 'Beatriz Andrade',    initials: 'BA', role: 'Estagiária',         active: false, last: '25/04 · 15:22' },
  { id: 'thiago',     name: 'Thiago Borges',      initials: 'TB', role: 'Advogado',           active: false, last: 'ontem · 14:08' },
  { id: 'larissa',    name: 'Larissa Nogueira',   initials: 'LN', role: 'Sócia em formação',  active: false, last: 'hoje · 11:30' },
  { id: 'gustavo',    name: 'Gustavo Pacheco',    initials: 'GP', role: 'Advogado',           active: false, last: '23/04 · 18:45' },
  { id: 'patricia',   name: 'Patrícia Tavares',   initials: 'PT', role: 'Paralegal',          active: false, last: 'hoje · 08:30' },
  { id: 'rodrigo',    name: 'Rodrigo Aguiar',     initials: 'RA', role: 'Advogado júnior',    active: false, last: 'hoje · 11:55' },
  { id: 'amanda',     name: 'Amanda Bessa',       initials: 'AB', role: 'Estagiária',         active: false, last: 'hoje · 09:02' },
  { id: 'henrique',   name: 'Henrique Cordeiro',  initials: 'HC', role: 'Financeiro',         active: false, last: 'hoje · 10:25' },
];

window.V2_USERS = V2_USERS;
