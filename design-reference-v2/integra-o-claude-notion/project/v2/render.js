/* global window, document */

// ============================================================
// Inline SVG icons
// ============================================================
const ic = {
  dashboard: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="2" y="2" width="5" height="6" rx="1"/><rect x="9" y="2" width="5" height="3" rx="1"/><rect x="9" y="7" width="5" height="7" rx="1"/><rect x="2" y="10" width="5" height="4" rx="1"/></svg>',
  proc: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M3 2.5h7l3 3v8a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1Z"/><path d="M10 2.5v3h3M5 8h6M5 11h6"/></svg>',
  cli: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="6" r="2.5"/><path d="M3 14c0-2.8 2.2-5 5-5s5 2.2 5 5"/></svg>',
  tar: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="2.5" y="3" width="11" height="11" rx="1.5"/><path d="M2.5 6h11M5 9.5l1.5 1.5L10 8"/></svg>',
  cat: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M3 3h10M3 6h10M3 9h7M3 12h7"/></svg>',
  imp: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M8 2v8M5 7l3 3 3-3M3 13h10"/></svg>',
  logs: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="6"/><path d="M8 4.5v4l2.5 1.5"/></svg>',
  cfg: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="2"/><path d="M8 1.5v2M8 12.5v2M14.5 8h-2M3.5 8h-2M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4M12.6 12.6l-1.4-1.4M4.8 4.8L3.4 3.4"/></svg>',
  sync: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M14 5.5A6 6 0 0 0 3 5.5M2 10.5A6 6 0 0 0 13 10.5M3 2.5v3h3M13 13.5v-3h-3"/></svg>',
  search: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/></svg>',
  filter: '<svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 3.5h12l-4.5 5.5v4l-3 1.5V9z"/></svg>',
  warn: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 2L1.5 13.5h13z"/><path d="M8 6.5v3M8 11.5v.5" stroke-linecap="round"/></svg>',
  err: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5"/></svg>',
  ok: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m3 8.5 3 3 7-7"/></svg>',
  plus: '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 3v10M3 8h10"/></svg>',
  cmd: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M5.5 3a2 2 0 1 1-2 2v6a2 2 0 1 1 2-2zm5 0a2 2 0 1 0 2 2V5a2 2 0 0 0-2-2zm0 8a2 2 0 1 0 2 2v-2zm0 0H5.5"/></svg>',
  inbox: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z"/></svg>',
};

// ============================================================
// Sidebar (rendered into every <aside class="sidebar">)
// ============================================================
const SB_ITEMS = [
  { id:'dashboard', lbl:'Dashboard',   ic:ic.dashboard, sc:'⌘1' },
  { id:'processos', lbl:'Processos',   ic:ic.proc,      sc:'⌘2', badge:'1108' },
  { id:'clientes',  lbl:'Clientes',    ic:ic.cli,       sc:'⌘3', badge:'1072' },
  { id:'tarefas',   lbl:'Tarefas',     ic:ic.tar,       sc:'⌘4' },
  { id:'catalogo',  lbl:'Catálogo de tarefas', ic:ic.cat, sc:'⌘5' },
];
const SB_TOOLS = [
  { id:'importar',  lbl:'Importar',         ic:ic.imp,  sc:'⌘I' },
  { id:'logs',      lbl:'Logs de edição',   ic:ic.logs, sc:'⌘L' },
  { id:'sync',      lbl:'Sincronização',    ic:ic.sync },
  { id:'config',    lbl:'Configurações',    ic:ic.cfg,  sc:'⌘,' },
];

function renderSidebar(el) {
  const active = el.dataset.active;
  const item = (it) => `
    <div class="sb-item ${it.id===active?'active':''}">
      <span class="ic">${it.ic}</span>
      <span class="lbl">${it.lbl}</span>
      ${it.badge?`<span class="badge">${it.badge}</span>`:''}
      ${it.sc?`<span class="sc">${it.sc}</span>`:''}
    </div>`;
  el.innerHTML = `
    <div class="sb-brand">
      <img src="assets/symbol-cream.png" alt="">
      <div class="sb-brand-text">RPADV<small>Notion bridge</small></div>
    </div>
    <div class="sb-section">
      <div class="sb-label">Bases</div>
      ${SB_ITEMS.map(item).join('')}
    </div>
    <div class="sb-section">
      <div class="sb-label">Ferramentas</div>
      ${SB_TOOLS.map(item).join('')}
    </div>
    <div class="sb-spacer"></div>
    <div class="sb-section" style="border-top:1px solid var(--sidebar-border);">
      <div class="sb-item">
        <span class="ic" style="width:20px;height:20px;border-radius:50%;background:var(--cream);color:var(--navy-700);font-size:9px;font-weight:800;display:inline-flex;align-items:center;justify-content:center;flex:0 0 20px;">DM</span>
        <span class="lbl" style="display:flex;flex-direction:column;line-height:1.2;">
          <span>Déborah Marques</span>
          <span style="font-size:9.5px;opacity:0.55;font-weight:400;">Administradora</span>
        </span>
      </div>
    </div>`;
}

document.querySelectorAll('.sidebar').forEach(renderSidebar);

// ============================================================
// 01 LOGIN
// ============================================================
const USERS = window.V2_USERS || [];
function renderLogin(el) {
  el.innerHTML = `
    <h2>Bem-vinda de volta</h2>
    <p class="lead">Quem está usando esta máquina hoje?</p>
    <div class="token-stored">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3.5" y="7" width="9" height="6.5" rx="1.2"/><path d="M5.5 7V4.8a2.5 2.5 0 0 1 5 0V7" stroke-linecap="round"/></svg>
      Token do escritório armazenado nesta máquina · Windows Credential Manager
    </div>
    <div class="field-label">Selecione seu usuário · ${USERS.length} cadastrados</div>
    <div class="user-grid">
      ${USERS.map((u,i)=>`
        <div class="user-card ${i===1?'active':''}">
          <div class="av">${u.initials}</div>
          <div class="nm">${u.name.split(' ')[0]}</div>
          <div class="rl">${u.role.split(' ')[0]}</div>
        </div>
      `).join('')}
    </div>
    <div class="login-actions">
      <button class="btn btn-primary">Entrar como Déborah</button>
      <span class="kbd">⏎</span>
      <button class="swap">Trocar token do escritório →</button>
    </div>`;
}
renderLogin(document.getElementById('login-form-light'));
renderLogin(document.getElementById('login-form-dark'));

// ============================================================
// 02 DASHBOARD
// ============================================================
function dashHTML(opts={}) {
  const showProgress = opts.progress !== false;
  return `
  <div class="toolbar">
    <h1>Dashboard</h1>
    <span class="meta">Visão geral · 27 abr 2026 · 14:36</span>
    <span class="sp"></span>
    <div class="search">
      ${ic.search}
      <input class="inp" placeholder="Buscar processo, cliente, tarefa…">
    </div>
    <button class="btn"><span class="kbd">⌘</span><span class="kbd">K</span> Comandos</button>
    ${showProgress?'<div class="progress" style="position:absolute;left:0;right:0;bottom:0;height:2px;background:linear-gradient(to right,var(--accent) 0%,var(--accent) 76%,transparent 76%);"></div>':''}
  </div>
  <div class="page-body" style="position:relative;">
    <div class="dash">
      <div class="kpi-row">
        <div class="kpi"><div class="kpi-label">Processos ativos</div><div class="kpi-val">883</div><div class="kpi-foot">de 1.108 totais</div></div>
        <div class="kpi"><div class="kpi-label">Clientes</div><div class="kpi-val">1.072</div><div class="kpi-foot">+4 nesta semana</div></div>
        <div class="kpi"><div class="kpi-label">Tarefas hoje</div><div class="kpi-val calm">0</div><div class="kpi-foot">Sem tarefas para hoje</div></div>
        <div class="kpi"><div class="kpi-label">Prazo crítico (≤7d)</div><div class="kpi-val calm">0</div><div class="kpi-foot">Nenhum prazo na semana</div></div>
        <div class="kpi"><div class="kpi-label">Pendências sync</div><div class="kpi-val">3</div><div class="kpi-foot" style="color:var(--warning);">Aguardando salvar</div></div>
      </div>

      <div class="dash-row-2">
        <div class="section">
          <div class="section-head">
            <h3 class="section-title">Tarefas urgentes</h3>
            <span class="section-meta">Próximos 7 dias</span>
            <span class="sp"></span>
            <button class="btn btn-ghost sm">Ver todas →</button>
          </div>
          <div style="padding:8px 0;">
            <div class="activity-row">
              <div class="av" style="background:var(--chip-orange-bg);color:var(--chip-orange-fg);">RM</div>
              <div>
                <div><strong>Petição inicial — Caso Pereira</strong></div>
                <div class="small">Vence amanhã · Rafael Mendes</div>
              </div>
              <span class="chip chip-orange">Alta</span>
            </div>
            <div class="activity-row">
              <div class="av" style="background:var(--chip-blue-bg);color:var(--chip-blue-fg);">DM</div>
              <div>
                <div><strong>Análise de provas — Recurso Andrade</strong></div>
                <div class="small">Vence em 3 dias · Déborah Marques</div>
              </div>
              <span class="chip chip-blue">Em andamento</span>
            </div>
            <div class="activity-row" style="border-bottom:0;">
              <div class="av" style="background:var(--chip-petrol-bg);color:var(--chip-petrol-fg);">LV</div>
              <div>
                <div><strong>Reunião com cliente Souza</strong></div>
                <div class="small">Vence em 5 dias · Leonardo Vieira</div>
              </div>
              <span class="chip">Normal</span>
            </div>
          </div>
        </div>

        <div class="section">
          <div class="section-head">
            <h3 class="section-title">Sincronização</h3>
            <span class="section-meta">Última: há 2 min</span>
            <span class="sp"></span>
            <button class="btn sm">Sincronizar agora</button>
          </div>
          <div>
            <div class="sync-row">
              <span class="b"><span class="dot warn"></span>Processos</span>
              <span class="count">847 / 1.108</span>
              <div class="progress"><span style="width:76%"></span></div>
              <span class="stamp">Sincronizando…</span>
              <span></span>
            </div>
            <div class="sync-row">
              <span class="b"><span class="dot idle"></span>Clientes</span>
              <span class="count">1.072 / 1.072</span>
              <div></div>
              <span class="stamp">há 2 min</span>
              <span class="chip chip-green" style="font-size:10px;">OK</span>
            </div>
            <div class="sync-row">
              <span class="b"><span class="dot idle"></span>Tarefas</span>
              <span class="count">— / —</span>
              <div></div>
              <span class="stamp">Aguardando</span>
              <span></span>
            </div>
            <div class="sync-row" style="border-bottom:0;">
              <span class="b"><span class="dot idle"></span>Catálogo</span>
              <span class="count">37 / 37</span>
              <div></div>
              <span class="stamp">há 12 min</span>
              <span class="chip chip-green" style="font-size:10px;">OK</span>
            </div>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-head">
          <h3 class="section-title">Atividade recente</h3>
          <span class="section-meta">Últimas edições</span>
          <span class="sp"></span>
          <button class="btn btn-ghost sm">Abrir logs →</button>
        </div>
        <div>
          <div class="activity-row"><div class="av">DM</div><div><strong>Déborah</strong> alterou status de <span style="font-family:var(--font-mono);font-size:11px;">0726654-71.2024.8.07.0001</span> · <span class="chip chip-green">Ativo</span> → <span class="chip chip-gray">Arquivado</span></div><span class="ts">14:32</span></div>
          <div class="activity-row"><div class="av" style="background:var(--chip-blue-bg);color:var(--chip-blue-fg);">RM</div><div><strong>Rafael</strong> criou tarefa "Petição inicial — Pereira" em <span class="chip-rel chip">↳ Caso Pereira</span></div><span class="ts">11:15</span></div>
          <div class="activity-row" style="border-bottom:0;"><div class="av" style="background:var(--chip-petrol-bg);color:var(--chip-petrol-fg);">LV</div><div><strong>Leonardo</strong> editou prazo de <span style="font-family:var(--font-mono);font-size:11px;">0805512-22.2023.5.10.0009</span></div><span class="ts">10:48</span></div>
        </div>
      </div>
    </div>
  </div>`;
}
document.getElementById('dash-light').innerHTML = dashHTML();
document.getElementById('dash-dark').innerHTML = dashHTML();
const d2l = document.getElementById('dash-light-2'); if (d2l) d2l.innerHTML = dashHTML({progress:false});
const d2d = document.getElementById('dash-dark-2'); if (d2d) d2d.innerHTML = dashHTML({progress:false});

// ============================================================
// 03 PROCESSOS
// ============================================================
const PROC_ROWS = [
  { cnj:'0726654-71.2024.8.07.0001', titulo:'Pereira & Cia × Município de Brasília', cliente:'Pereira & Cia LTDA', tribunal:'TRT/10', fase:'Conhecimento', status:'Ativo', resp:['DM'], prazo:'05/05/2026', parent:null },
  { cnj:'0805512-22.2023.5.10.0009', titulo:'Andrade × Banco Safra (recurso)',     cliente:'Maria do Carmo Andrade', tribunal:'TRT/10', fase:'Recurso', status:'Ativo', resp:['DM','RM'], prazo:'12/05/2026', parent:'0805512-22.2023.5.10.0001' },
  { cnj:'1003788-44.2025.4.01.3400', titulo:'Souza × INSS',                          cliente:'João Souza Filho', tribunal:'TRT/10', fase:'Execução', status:'Ativo', resp:['LV'], prazo:'20/05/2026', parent:null, editing:true },
  { cnj:'0712233-09.2022.8.07.0015', titulo:'Costa × Loja Ametista',                cliente:'Luana Costa Oliveira', tribunal:'TRT/10', fase:'Cumprimento', status:'Ativo', resp:['MS','RM'], prazo:'—', parent:null, dirty:true },
  { cnj:'0001234-56.2025.5.10.0007', titulo:'Almeida × Construtora Horizonte',      cliente:'Reginaldo Almeida', tribunal:'TRT/10', fase:'Conhecimento', status:'Ativo', resp:['JC'], prazo:'02/06/2026', parent:null },
  { cnj:'0044121-88.2024.5.10.0003', titulo:'Lima × Estado do DF (agravo)',          cliente:'Beatriz Lima', tribunal:'TRT/10', fase:'Recurso', status:'Sobrestado', resp:['DM'], prazo:'—', parent:'0044121-88.2024.5.10.0001' },
  { cnj:'0098765-33.2023.5.10.0011', titulo:'Cooperativa União × ANEEL',             cliente:'Cooperativa União', tribunal:'TRT/10', fase:'Conhecimento', status:'Ativo', resp:['LV','PH'], prazo:'18/05/2026', parent:null, dirty:true },
  { cnj:'0500412-77.2022.5.10.0002', titulo:'Pacheco × Editora Vértice',             cliente:'Henrique Pacheco', tribunal:'TRT/10', fase:'Trânsito em julgado', status:'Arquivado', resp:['MS'], prazo:'—', parent:null },
  { cnj:'0711234-12.2025.8.07.0006', titulo:'Tavares × Município de Taguatinga',     cliente:'Patrícia Tavares', tribunal:'TRT/10', fase:'Conhecimento', status:'Ativo', resp:['DM'], prazo:'09/05/2026', parent:null, dirty:true },
  { cnj:'0803344-55.2024.5.10.0008', titulo:'Borges × Empresa Y (agravo de instrumento)', cliente:'Thiago Borges', tribunal:'TRT/10', fase:'Recurso', status:'Ativo', resp:['LN'], prazo:'15/05/2026', parent:'0803344-55.2024.5.10.0005' },
  { cnj:'0066677-22.2024.5.10.0001', titulo:'Nogueira × Banco Central',              cliente:'Larissa Nogueira', tribunal:'TRT/10', fase:'Conhecimento', status:'Suspenso', resp:['JC','GP'], prazo:'—', parent:null },
  { cnj:'0900123-44.2023.5.10.0010', titulo:'Aguiar × Universidade Federal',         cliente:'Rodrigo Aguiar', tribunal:'TRT/10', fase:'Cumprimento', status:'Ativo', resp:['MS'], prazo:'25/05/2026', parent:null },
];

function chipFase(f){
  const map={'Conhecimento':'chip-gray','Recurso':'chip-orange','Execução':'chip-yellow','Cumprimento':'chip-petrol','Sobrestado':'chip-red','Trânsito em julgado':'chip-green'};
  return `<span class="chip ${map[f]||''}">${f}</span>`;
}
function chipStatus(s){
  const map={'Ativo':'chip-green','Sobrestado':'chip-red','Suspenso':'chip-orange','Arquivado':'chip-gray'};
  return `<span class="chip ${map[s]||''}">${s}</span>`;
}
function chipPerson(initials){
  return `<span class="chip chip-person"><span class="av">${initials}</span>${initials}</span>`;
}

function renderProc(el) {
  el.innerHTML = `
  <div class="toolbar">
    <h1>Processos</h1>
    <span class="meta">${PROC_ROWS.length} de 1.108 · 1 filtro ativo</span>
    <span class="sp"></span>
    <div class="search">
      ${ic.search}
      <input class="inp" placeholder="Buscar CNJ, parte, advogado…">
    </div>
    <button class="btn">${ic.plus} Novo processo</button>
  </div>

  <div class="filter-bar">
    <span class="lbl">Filtros ativos</span>
    <span class="filter-pill">Tribunal <span class="count">TRT/10</span><span class="x">×</span></span>
    <span class="filter-pill">Status <span class="count">2</span><span class="x">×</span></span>
    <span class="filter-clear">Limpar todos</span>
    <span class="sp" style="flex:1"></span>
    <span class="small">Ordenar por: <strong style="color:var(--fg);">Última edição</strong> ↓</span>
  </div>

  <div class="with-detail">
    <div class="tbl-wrap">
      <table class="tbl" style="min-width:980px;">
        <colgroup>
          <col style="width:200px"/>
          <col style="width:280px"/>
          <col style="width:180px"/>
          <col style="width:90px"/>
          <col style="width:130px"/>
          <col style="width:90px"/>
          <col style="width:100px"/>
          <col style="width:96px"/>
        </colgroup>
        <thead>
          <tr>
            <th><span class="th-in">CNJ <span class="filter-btn">${ic.filter}</span></span></th>
            <th><span class="th-in">Título</span></th>
            <th><span class="th-in">Cliente principal <span class="filter-btn">${ic.filter}</span></span></th>
            <th><span class="th-in">Tribunal <span class="filter-btn active">${ic.filter}</span></span></th>
            <th><span class="th-in">Fase <span class="filter-btn">${ic.filter}</span></span></th>
            <th><span class="th-in">Status <span class="filter-btn active">${ic.filter}</span></span></th>
            <th><span class="th-in">Responsáveis</span></th>
            <th class="num"><span class="th-in">Prazo</span></th>
          </tr>
        </thead>
        <tbody>
          ${PROC_ROWS.map((r,i)=>{
            const parentCell = r.parent
              ? `<span class="rel-arrow">↳</span><span class="mono" style="font-family:var(--font-mono);font-size:11px;">${r.parent}</span><br><span class="mono" style="font-family:var(--font-mono);font-size:11px;color:var(--fg);">${r.cnj}</span>`
              : `<span class="mono" style="font-family:var(--font-mono);font-size:11.5px;">${r.cnj}</span>`;
            const cls = [];
            if (r.dirty) cls.push('dirty');
            if (r.editing) cls.push('editing');
            if (i===2) cls.push('selected');
            return `
            <tr class="${cls.join(' ')}">
              <td>${parentCell}</td>
              <td>${r.titulo}</td>
              <td>${r.editing
                ? `<span class="chip chip-rel">${r.cliente}</span>`
                : `<span class="chip chip-rel">${r.cliente.split(' ').slice(0,2).join(' ')}</span>`}</td>
              <td>${r.editing
                ? `<span class="chip chip-blue">${r.tribunal}</span>`
                : `<span class="chip chip-blue">${r.tribunal}</span>`}</td>
              <td class="${r.editing?'editing-cell':''}">${r.editing
                ? `<input value="${r.fase}" />`
                : chipFase(r.fase)}</td>
              <td class="${r.dirty && i===3?'dirty-cell':''}">${chipStatus(r.status)}</td>
              <td>${r.resp.map(chipPerson).join(' ')}</td>
              <td class="num" style="font-variant-numeric:tabular-nums; ${r.prazo==='—'?'color:var(--fg-3);':''}">${r.prazo}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      <div class="tbl-pad"></div>
    </div>

    <aside class="detail">
      <div class="detail-tabs">
        <div class="detail-tab active">Detalhes</div>
        <div class="detail-tab">Tarefas <span class="pip"></span></div>
        <div class="detail-tab">Comentários</div>
        <div class="detail-tab">Histórico</div>
      </div>
      <div class="detail-head">
        <div class="detail-eyebrow">Processo selecionado</div>
        <h3>Souza × INSS</h3>
        <div class="small" style="margin-top:4px;font-family:var(--font-mono);">1003788-44.2025.4.01.3400</div>
      </div>
      <div class="detail-body">
        <div class="dprop"><div class="dprop-l">Cliente</div><div class="dprop-v"><span class="chip chip-rel">João Souza Filho</span></div></div>
        <div class="dprop"><div class="dprop-l">Tribunal</div><div class="dprop-v"><span class="chip chip-blue">TRT/10</span> · 1ª instância</div></div>
        <div class="dprop"><div class="dprop-l">Fase</div><div class="dprop-v">${chipFase('Execução')} <span class="subtle" style="font-size:10px;">editando…</span></div></div>
        <div class="dprop"><div class="dprop-l">Status</div><div class="dprop-v">${chipStatus('Ativo')}</div></div>
        <div class="dprop"><div class="dprop-l">Responsáveis</div><div class="dprop-v">${chipPerson('LV')}</div></div>
        <div class="dprop"><div class="dprop-l">Próximo prazo</div><div class="dprop-v">20/05/2026 <span class="subtle">· em 23 dias</span></div></div>
        <div class="dprop"><div class="dprop-l">Recursos</div><div class="dprop-v"><span class="muted-empty">Sem recursos vinculados</span></div></div>
        <div class="dprop"><div class="dprop-l">Última edição</div><div class="dprop-v"><span class="chip chip-person"><span class="av">LV</span>Leonardo</span> · 27/04 13:50</div></div>
        <div class="dprop"><div class="dprop-l">Notion</div><div class="dprop-v"><a style="color:var(--accent);text-decoration:none;" href="#">Abrir no Notion ↗</a></div></div>
      </div>
    </aside>
  </div>

  <div class="floating-save">
    <span><strong>3 alterações pendentes</strong> em Processos</span>
    <span class="pendings">Souza × INSS · Costa × Loja Ametista · +1</span>
    <button class="ghost">Descartar</button>
    <button class="btn btn-primary">Salvar <span class="kbd" style="background:rgba(255,255,255,0.2);border:0;color:inherit;">⌘S</span></button>
  </div>`;
}
renderProc(document.getElementById('proc-light'));
renderProc(document.getElementById('proc-dark'));

// ============================================================
// 04 CLIENTES
// ============================================================
const CLI_ROWS = [
  { name:'Pereira & Cia LTDA',      tipo:'PJ', cidade:'Brasília', proc:14, sucessor:null, ult:'27/04', status:'Ativo' },
  { name:'Maria do Carmo Andrade',  tipo:'PF', cidade:'Brasília', proc:6,  sucessor:'Sebastião Andrade (†)', ult:'26/04', status:'Ativo' },
  { name:'João Souza Filho',        tipo:'PF', cidade:'Taguatinga', proc:3, sucessor:null, ult:'25/04', status:'Ativo' },
  { name:'Luana Costa Oliveira',    tipo:'PF', cidade:'Brasília', proc:2,  sucessor:null, ult:'24/04', status:'Ativo' },
  { name:'Reginaldo Almeida',       tipo:'PF', cidade:'Ceilândia', proc:1, sucessor:null, ult:'23/04', status:'Ativo' },
  { name:'Beatriz Lima',            tipo:'PF', cidade:'Brasília', proc:4, sucessor:'Roberto Lima (†)', ult:'22/04', status:'Ativo' },
  { name:'Cooperativa União',       tipo:'PJ', cidade:'Brasília', proc:8, sucessor:null, ult:'21/04', status:'Ativo' },
  { name:'Henrique Pacheco',        tipo:'PF', cidade:'Goiânia',  proc:0, sucessor:null, ult:'15/04', status:'Histórico' },
  { name:'Patrícia Tavares',        tipo:'PF', cidade:'Brasília', proc:2, sucessor:null, ult:'27/04', status:'Ativo' },
  { name:'Thiago Borges',           tipo:'PF', cidade:'Brasília', proc:5, sucessor:null, ult:'26/04', status:'Ativo' },
  { name:'Larissa Nogueira',        tipo:'PF', cidade:'Brasília', proc:3, sucessor:'Antônia Nogueira (†)', ult:'24/04', status:'Ativo' },
  { name:'Rodrigo Aguiar',          tipo:'PF', cidade:'Sobradinho', proc:2, sucessor:null, ult:'27/04', status:'Ativo' },
  { name:'Estado de Goiás (litisconsorte)', tipo:'PJ', cidade:'Goiânia', proc:0, sucessor:null, ult:'10/03', status:'Histórico' },
];

function renderCli(el) {
  el.innerHTML = `
  <div class="toolbar">
    <h1>Clientes</h1>
    <span class="meta">${CLI_ROWS.length} de 1.072 · ordenado por última edição</span>
    <span class="sp"></span>
    <div class="search">
      ${ic.search}
      <input class="inp" placeholder="Buscar nome, CPF/CNPJ, cidade…">
    </div>
    <button class="btn">${ic.plus} Novo cliente</button>
  </div>

  <div class="filter-bar">
    <span class="lbl">Visão</span>
    <span class="filter-pill">Status: Ativo <span class="x">×</span></span>
    <span class="sp" style="flex:1"></span>
    <span class="small">Mostrando colunas: <strong style="color:var(--fg);">Nome · Tipo · Cidade · N° processos · Sucessor · Última ed.</strong></span>
  </div>

  <div class="with-detail" style="grid-template-columns:1fr 320px;">
    <div class="tbl-wrap">
      <table class="tbl" style="min-width:880px;">
        <colgroup>
          <col style="width:240px"/>
          <col style="width:60px"/>
          <col style="width:130px"/>
          <col style="width:100px"/>
          <col style="width:200px"/>
          <col style="width:110px"/>
          <col style="width:90px"/>
        </colgroup>
        <thead>
          <tr>
            <th><span class="th-in">Nome <span class="filter-btn">${ic.filter}</span></span></th>
            <th><span class="th-in">Tipo</span></th>
            <th><span class="th-in">Cidade</span></th>
            <th class="num"><span class="th-in">N° processos</span></th>
            <th><span class="th-in">Sucessor de</span></th>
            <th class="num"><span class="th-in">Última edição</span></th>
            <th><span class="th-in">Status</span></th>
          </tr>
        </thead>
        <tbody>
          ${CLI_ROWS.map((r,i)=>{
            const cls = i===1 ? 'selected' : '';
            return `
            <tr class="${cls}">
              <td>${r.sucessor?'<span class="rel-arrow">↳</span>':''}<strong>${r.name}</strong></td>
              <td><span class="chip ${r.tipo==='PJ'?'chip-purple':''}">${r.tipo}</span></td>
              <td>${r.cidade}</td>
              <td class="num" style="font-variant-numeric:tabular-nums; ${r.proc===0?'color:var(--fg-3);':'color:var(--fg);font-weight:600;'}">${r.proc}</td>
              <td>${r.sucessor
                ? `<span class="chip chip-rel">${r.sucessor}</span>`
                : `<span class="muted-empty">—</span>`}</td>
              <td class="num" style="font-variant-numeric:tabular-nums; color:var(--fg-3);">${r.ult}</td>
              <td><span class="chip ${r.status==='Ativo'?'chip-green':'chip-gray'}">${r.status}</span></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      <div class="tbl-pad"></div>
    </div>

    <aside class="detail">
      <div class="detail-tabs">
        <div class="detail-tab active">Detalhes</div>
        <div class="detail-tab">Processos <span class="pip" style="background:var(--accent);"></span></div>
        <div class="detail-tab">Comentários</div>
        <div class="detail-tab">Histórico</div>
      </div>
      <div class="detail-head">
        <div class="detail-eyebrow">Cliente</div>
        <h3>Maria do Carmo Andrade</h3>
        <div class="small" style="margin-top:4px;">PF · Brasília · DF</div>
      </div>
      <div class="detail-body">
        <div class="dprop"><div class="dprop-l">CPF</div><div class="dprop-v mono">123.456.789-00</div></div>
        <div class="dprop"><div class="dprop-l">N° processos</div><div class="dprop-v"><strong>6 ativos</strong> <span class="subtle">· lookup reverso</span></div></div>
        <div class="dprop"><div class="dprop-l">Sucessor de</div><div class="dprop-v"><span class="chip chip-rel">Sebastião Andrade (†)</span></div></div>
        <div class="dprop"><div class="dprop-l">Sucedido por</div><div class="dprop-v"><span class="chip" style="cursor:pointer;background:var(--row-hover);">Sucedido por 0</span></div></div>
        <div class="dprop"><div class="dprop-l">Telefone</div><div class="dprop-v mono">(61) 9 8765-4321</div></div>
        <div class="dprop"><div class="dprop-l">E-mail</div><div class="dprop-v">maria.andrade@example.com</div></div>
        <div class="dprop"><div class="dprop-l">Cadastro</div><div class="dprop-v">22/03/2022</div></div>
        <div class="dprop"><div class="dprop-l">Última edição</div><div class="dprop-v">${chipPerson('DM')} · 26/04 09:14</div></div>
      </div>
    </aside>
  </div>`;
}
renderCli(document.getElementById('cli-light'));
renderCli(document.getElementById('cli-dark'));

// ============================================================
// 05 IMPORTAR — etapa 2
// ============================================================
function renderImp(el) {
  el.innerHTML = `
  <div class="toolbar">
    <h1>Importar processos</h1>
    <span class="meta">CSV · processos_abr_2026.csv · 12 linhas</span>
    <span class="sp"></span>
    <button class="btn">Cancelar</button>
  </div>
  <div class="stepper">
    <div class="step-item done"><span class="step-dot">${ic.ok}</span>1 · Origem</div>
    <div class="step-line"></div>
    <div class="step-item active"><span class="step-dot">2</span>2 · Mapear & validar</div>
    <div class="step-line"></div>
    <div class="step-item"><span class="step-dot">3</span>3 · Confirmar</div>
  </div>
  <div class="banner banner-warn">
    ${ic.warn} <strong>1 linha com erro</strong> e <strong>2 conflitos</strong> — corrija ou ignore antes de continuar.
  </div>
  <div class="page-body" style="padding:0;">
    <div class="filter-bar" style="background:var(--bg);">
      <span class="lbl">Mapeamento</span>
      <span class="small">CSV → Notion: <strong style="color:var(--fg);">CNJ → Identificador (CNJ)</strong>, <strong style="color:var(--fg);">Cliente → Cliente principal</strong>, <strong style="color:var(--fg);">Tribunal → Tribunal</strong>… <a href="#" style="color:var(--accent);">editar mapeamento</a></span>
      <span class="sp" style="flex:1"></span>
      <span class="filter-pill" style="background:rgba(63,110,85,0.12);color:var(--success);">9 ok</span>
      <span class="filter-pill" style="background:rgba(181,138,63,0.16);color:var(--warning);">2 conflitos</span>
      <span class="filter-pill" style="background:rgba(154,59,59,0.12);color:var(--danger);">1 erro</span>
    </div>
    <div class="tbl-wrap" style="height:480px;">
      <table class="tbl" style="min-width:980px;">
        <colgroup><col style="width:36px"/><col style="width:200px"/><col style="width:280px"/><col style="width:180px"/><col style="width:100px"/><col style="width:130px"/><col style="width:140px"/></colgroup>
        <thead><tr>
          <th></th>
          <th>CNJ</th><th>Título</th><th>Cliente</th><th>Tribunal</th><th>Fase</th><th>Validação</th>
        </tr></thead>
        <tbody>
          <tr><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0726700-44.2025.8.07.0001</td><td>Vasconcelos × Município de Brasília</td><td><span class="chip chip-rel">Vasconcelos & Filhos</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Conhecimento')}</td><td><span class="chip chip-green">${ic.ok} OK · novo</span></td></tr>
          <tr class="row-err"><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;color:var(--danger);"><span class="cell-err-icon">${ic.err}</span>07266-2025-7</td><td>Andrade × Banco</td><td><span class="muted-empty">[vazio]</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Conhecimento')}</td><td><span class="chip chip-red">CNJ inválido</span></td></tr>
          <tr class="row-warn"><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0726654-71.2024.8.07.0001</td><td>Pereira & Cia × Município de Brasília</td><td><span class="chip chip-rel">Pereira & Cia LTDA</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Conhecimento')}</td><td><span class="chip chip-yellow">${ic.warn} Já existe · atualizar?</span></td></tr>
          <tr><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0011111-22.2025.4.01.3400</td><td>Mendes × Caixa Econômica</td><td><span class="chip chip-rel">Carlos Mendes</span></td><td><span class="chip chip-green">TRF/1</span></td><td>${chipFase('Conhecimento')}</td><td><span class="chip chip-green">${ic.ok} OK · novo</span></td></tr>
          <tr><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0044556-77.2024.5.10.0011</td><td>Ribeiro × Empresa Z</td><td><span class="chip chip-rel">Sandra Ribeiro</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Conhecimento')}</td><td><span class="chip chip-green">${ic.ok} OK · novo</span></td></tr>
          <tr><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0066678-90.2025.5.10.0002</td><td>Cardoso × União</td><td><span class="chip chip-rel">Daniel Cardoso</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Recurso')}</td><td><span class="chip chip-green">${ic.ok} OK · novo</span></td></tr>
          <tr class="row-warn"><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0805512-22.2023.5.10.0009</td><td>Andrade × Banco Safra</td><td><span class="chip chip-rel">Maria do Carmo Andrade</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Recurso')}</td><td><span class="chip chip-yellow">${ic.warn} Já existe · atualizar?</span></td></tr>
          <tr><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0123456-78.2025.8.07.0014</td><td>Oliveira × Concessionária BR</td><td><span class="chip chip-rel">Tatiana Oliveira</span></td><td><span class="chip chip-blue">TJDFT</span></td><td>${chipFase('Conhecimento')}</td><td><span class="chip chip-green">${ic.ok} OK · novo</span></td></tr>
          <tr><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0700099-11.2024.5.10.0001</td><td>Cunha × Comércio Aurora</td><td><span class="chip chip-rel">Wellington Cunha</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Cumprimento')}</td><td><span class="chip chip-green">${ic.ok} OK · novo</span></td></tr>
          <tr><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0888777-66.2025.5.10.0008</td><td>Barbosa × Distribuidora Sul</td><td><span class="chip chip-rel">Eduardo Barbosa</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Conhecimento')}</td><td><span class="chip chip-green">${ic.ok} OK · novo</span></td></tr>
          <tr><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0011223-44.2024.5.10.0006</td><td>Freitas × Município de Brasília</td><td><span class="chip chip-rel">Camila Freitas</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Conhecimento')}</td><td><span class="chip chip-green">${ic.ok} OK · novo</span></td></tr>
          <tr><td><input type="checkbox" checked></td><td class="mono" style="font-family:var(--font-mono);font-size:11.5px;">0033445-66.2025.5.10.0009</td><td>Domingues × Estado do DF</td><td><span class="chip chip-rel">Ana Domingues</span></td><td><span class="chip chip-blue">TRT/10</span></td><td>${chipFase('Conhecimento')}</td><td><span class="chip chip-green">${ic.ok} OK · novo</span></td></tr>
        </tbody>
      </table>
    </div>
  </div>
  <div class="floating-save" style="position:relative;right:auto;bottom:auto;margin:12px 18px;align-self:flex-end;">
    <span><strong>9 prontas</strong> para importar · 2 conflitos · 1 erro</span>
    <button class="ghost">← Voltar</button>
    <button class="btn btn-primary">Continuar →</button>
  </div>`;
}
renderImp(document.getElementById('imp-light'));
renderImp(document.getElementById('imp-dark'));

// ============================================================
// 06 LOGS
// ============================================================
const LOG_ROWS = [
  { ts:'27/04 14:32', user:'DM', userN:'Déborah', base:'Processos', target:'0726654-71.2024.8.07.0001', prop:'Status', from:'Ativo', to:'Arquivado', reverted:false, sel:true },
  { ts:'27/04 13:50', user:'LV', userN:'Leonardo', base:'Processos', target:'1003788-44.2025.4.01.3400', prop:'Fase', from:'Conhecimento', to:'Execução', reverted:false },
  { ts:'27/04 11:15', user:'RM', userN:'Rafael', base:'Tarefas', target:'Petição inicial — Pereira', prop:'(criação)', from:'—', to:'Nova tarefa', reverted:false },
  { ts:'27/04 10:48', user:'LV', userN:'Leonardo', base:'Processos', target:'0805512-22.2023.5.10.0009', prop:'Prazo', from:'05/05/2026', to:'12/05/2026', reverted:false },
  { ts:'27/04 09:14', user:'DM', userN:'Déborah', base:'Clientes', target:'Maria do Carmo Andrade', prop:'Telefone', from:'(61) 3344-5566', to:'(61) 9 8765-4321', reverted:false },
  { ts:'26/04 17:22', user:'JC', userN:'Juliana', base:'Processos', target:'0044121-88.2024.5.10.0003', prop:'Status', from:'Ativo', to:'Sobrestado', reverted:true },
  { ts:'26/04 15:08', user:'MS', userN:'Mariana', base:'Processos', target:'0712233-09.2022.8.07.0015', prop:'Responsáveis', from:'MS', to:'MS, RM', reverted:false },
  { ts:'26/04 11:45', user:'LN', userN:'Larissa', base:'Tarefas', target:'Análise de provas — Andrade', prop:'Status', from:'A fazer', to:'Em andamento', reverted:false },
  { ts:'26/04 09:30', user:'DM', userN:'Déborah', base:'Processos', target:'0066677-22.2024.5.10.0001', prop:'Status', from:'Ativo', to:'Suspenso', reverted:false },
  { ts:'25/04 16:55', user:'RM', userN:'Rafael', base:'Processos', target:'0900123-44.2023.5.10.0010', prop:'Fase', from:'Execução', to:'Cumprimento', reverted:false },
  { ts:'25/04 14:20', user:'PH', userN:'Pedro', base:'Clientes', target:'Cooperativa União', prop:'Cidade', from:'Brasília', to:'Brasília · DF', reverted:false },
  { ts:'25/04 10:10', user:'GP', userN:'Gustavo', base:'Processos', target:'0098765-33.2023.5.10.0011', prop:'(criação)', from:'—', to:'Novo processo', reverted:false },
];

function renderLogs(el) {
  el.innerHTML = `
  <div class="toolbar">
    <h1>Logs de edição</h1>
    <span class="meta">Auditoria · todas as bases · últimos 30 dias</span>
    <span class="sp"></span>
    <div class="search">${ic.search}<input class="inp" placeholder="Buscar por usuário, base, propriedade…"></div>
  </div>
  <div class="filter-bar">
    <span class="lbl">Visão</span>
    <span class="filter-pill">Período: 30 dias <span class="x">×</span></span>
    <span class="filter-clear">Limpar</span>
    <span class="sp" style="flex:1"></span>
    <span class="small">${LOG_ROWS.length} eventos · 1 revertido</span>
  </div>
  <div class="page-body" style="padding:0;">
    <div class="tbl-wrap">
      <table class="tbl" style="min-width:920px;">
        <colgroup><col style="width:120px"/><col style="width:120px"/><col style="width:110px"/><col style="width:240px"/><col style="width:120px"/><col style="width:300px"/><col style="width:120px"/></colgroup>
        <thead><tr>
          <th>Quando</th><th>Usuário</th><th>Base</th><th>Registro</th><th>Propriedade</th><th>Alteração</th><th>Ações</th>
        </tr></thead>
        <tbody>
          ${LOG_ROWS.map(r=>`
            <tr class="${r.sel?'selected':''}">
              <td class="mono" style="font-family:var(--font-mono);font-size:11px;color:var(--fg-3);">${r.ts}</td>
              <td>${chipPerson(r.user)} ${r.userN}</td>
              <td><span class="chip">${r.base}</span></td>
              <td>${r.base==='Processos'?`<span class="mono" style="font-family:var(--font-mono);font-size:11px;">${r.target}</span>`:r.target}</td>
              <td style="color:var(--fg-2);">${r.prop}</td>
              <td><span style="color:var(--fg-3);text-decoration:line-through;">${r.from}</span> <span style="color:var(--fg-3);">→</span> <span style="color:var(--success);font-weight:600;">${r.to}</span></td>
              <td>${r.reverted
                ? `<span class="chip chip-gray">Revertido</span>`
                : `<button class="btn sm" style="height:22px;font-size:11px;">↩ Reverter</button>`}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  </div>`;
}
renderLogs(document.getElementById('logs-light'));
renderLogs(document.getElementById('logs-dark'));

// ============================================================
// 07 CONFIGURAÇÕES
// ============================================================
function renderCfg(el) {
  el.innerHTML = `
  <div class="toolbar">
    <h1>Configurações</h1>
    <span class="meta">Preferências do escritório · armazenadas em %APPDATA%/RPADV</span>
  </div>
  <div class="cfg-layout">
    <nav class="cfg-nav">
      <div class="cfg-nav-item active">${ic.cfg} Aparência</div>
      <div class="cfg-nav-item">${ic.cmd} Atalhos</div>
      <div class="cfg-nav-item">${ic.cli} Usuários</div>
      <div class="cfg-nav-item">${ic.sync} Sincronização</div>
      <div class="cfg-nav-item">${ic.imp} Importação</div>
      <div class="cfg-nav-item">${ic.logs} Auditoria & Token</div>
    </nav>
    <div class="cfg-body">

      <div class="cfg-section">
        <h2>Aparência</h2>
        <p class="help">O tema "Auto" segue a configuração do Windows e troca automaticamente entre claro e escuro ao amanhecer/anoitecer.</p>
        <div class="cfg-row">
          <label>Tema</label>
          <div class="cfg-val">
            <div class="theme-cards">
              <div class="theme-card active"><div class="tp tp-auto"><span></span><span></span></div>Auto <span class="subtle" style="font-size:9.5px;color:var(--fg-3);font-weight:400;">(padrão)</span></div>
              <div class="theme-card"><div class="tp tp-light"><span></span><span></span></div>Claro</div>
              <div class="theme-card"><div class="tp tp-dark"><span></span><span></span></div>Escuro</div>
            </div>
          </div>
        </div>
        <div class="cfg-row">
          <label>Densidade</label>
          <div class="cfg-val">
            <div style="display:inline-flex;border:1px solid var(--border-strong);border-radius:3px;overflow:hidden;">
              <button class="btn sm" style="border:0;border-radius:0;background:var(--accent);color:var(--accent-fg);">Compacto</button>
              <button class="btn sm" style="border:0;border-radius:0;border-left:1px solid var(--border-strong);">Confortável</button>
            </div>
            <span class="subtle">11–13px corpo · linhas 28px</span>
          </div>
        </div>
        <div class="cfg-row">
          <label>Tipografia</label>
          <div class="cfg-val mono">Playfair Display · Nunito Sans <span class="subtle">(embarcadas em assets/fonts/)</span></div>
        </div>
      </div>

      <div class="cfg-section">
        <h2>Atalhos de teclado</h2>
        <p class="help">Clique em um atalho para capturar uma nova combinação. Pressione Esc para cancelar, Enter para salvar.</p>
        <div class="shortcut-grid">
          <div class="sc-row"><span class="lb">Abrir paleta de comandos</span><span class="keys"><span class="kbd">⌘</span><span class="kbd">K</span></span></div>
          <div class="sc-row captured"><span class="lb">Ir para Processos</span><span class="keys" style="display:flex;align-items:center;gap:8px;"><span style="font-size:10.5px;color:var(--accent);font-style:italic;">Pressione a combinação…</span><span class="kbd" style="background:var(--accent);color:var(--accent-fg);border-color:var(--accent);">⌘</span><span class="kbd" style="background:var(--accent);color:var(--accent-fg);border-color:var(--accent);">2</span></span><span class="saved">${ic.ok} Salvo</span></div>
          <div class="sc-row"><span class="lb">Ir para Clientes</span><span class="keys"><span class="kbd">⌘</span><span class="kbd">3</span></span></div>
          <div class="sc-row"><span class="lb">Salvar pendentes</span><span class="keys"><span class="kbd">⌘</span><span class="kbd">S</span></span></div>
          <div class="sc-row"><span class="lb">Sincronizar agora</span><span class="keys"><span class="kbd">⌘</span><span class="kbd">R</span></span></div>
          <div class="sc-row"><span class="lb">Editar célula</span><span class="keys"><span class="kbd">F2</span></span></div>
          <div class="sc-row"><span class="lb">Cancelar edição</span><span class="keys"><span class="kbd">Esc</span></span></div>
          <div class="sc-row"><span class="lb">Confirmar edição</span><span class="keys"><span class="kbd">⏎</span></span></div>
        </div>
      </div>

      <div class="cfg-section">
        <h2>Usuários do escritório</h2>
        <p class="help">17 usuários cadastrados. O usuário ativo é destacado e recebe o chip "Você".</p>
        <table class="user-tbl">
          <thead><tr><th>Nome</th><th>Função</th><th>Último acesso</th><th></th></tr></thead>
          <tbody>
            ${USERS.slice(0,8).map(u=>`
              <tr class="${u.active?'you':''}">
                <td><span class="chip chip-person"><span class="av">${u.initials}</span>${u.name}</span></td>
                <td style="color:var(--fg-2);">${u.role}</td>
                <td style="color:var(--fg-3);font-family:var(--font-mono);font-size:11px;">${u.last}</td>
                <td>${u.active?'<span class="you-chip">Você</span>':''}</td>
              </tr>
            `).join('')}
            <tr><td colspan="4" style="text-align:center;color:var(--fg-3);font-size:11.5px;padding:10px;">+ 9 usuários · <a href="#" style="color:var(--accent);">ver todos</a></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>`;
}
renderCfg(document.getElementById('cfg-light'));
renderCfg(document.getElementById('cfg-dark'));

// ============================================================
// 08 PALETTE
// ============================================================
function renderPalette(el) {
  el.innerHTML = `
    <div class="palette-input">
      ${ic.search}
      <span class="typed">rec</span>
      <span class="kbd">Esc</span>
    </div>
    <div class="palette-list">
      <div class="palette-section">Ações</div>
      <div class="palette-row active">
        <span class="ic">${ic.proc}</span>
        <span class="lb">Filtrar processos por fase = <strong>Recurso</strong></span>
        <span class="kn">processos</span>
        <span class="kbd">⏎</span>
      </div>
      <div class="palette-row">
        <span class="ic">${ic.plus}</span>
        <span class="lb">Novo <strong>recurso</strong> a partir de processo selecionado</span>
        <span class="kn">novo</span>
        <span class="kbd">⌘N</span>
      </div>
      <div class="palette-row">
        <span class="ic">${ic.sync}</span>
        <span class="lb"><strong>Reconectar</strong> ao Notion</span>
        <span class="kn">conexão</span>
        <span></span>
      </div>
      <div class="palette-section">Resultados (3)</div>
      <div class="palette-row">
        <span class="ic">${ic.proc}</span>
        <span class="lb">Andrade × Banco Safra <span style="color:var(--fg-3);">(<strong style="color:var(--accent);">rec</strong>urso)</span></span>
        <span class="kn">processo</span>
        <span></span>
      </div>
      <div class="palette-row">
        <span class="ic">${ic.proc}</span>
        <span class="lb">Lima × Estado do DF <span style="color:var(--fg-3);">(agravo · <strong style="color:var(--accent);">rec</strong>urso)</span></span>
        <span class="kn">processo</span>
        <span></span>
      </div>
      <div class="palette-row">
        <span class="ic">${ic.proc}</span>
        <span class="lb">Borges × Empresa Y <span style="color:var(--fg-3);">(<strong style="color:var(--accent);">rec</strong>urso)</span></span>
        <span class="kn">processo</span>
        <span></span>
      </div>
    </div>`;
}
renderPalette(document.getElementById('palette-light'));
renderPalette(document.getElementById('palette-dark'));

// ============================================================
// 09 EMPTY STATE
// ============================================================
function renderEmpty(el) {
  el.innerHTML = `
  <div class="toolbar">
    <h1>Tarefas</h1>
    <span class="meta">0 de 0 registros · base sincronizada</span>
    <span class="sp"></span>
    <div class="search">${ic.search}<input class="inp" placeholder="Buscar tarefa…" disabled></div>
    <button class="btn" disabled>${ic.plus} Nova tarefa</button>
  </div>
  <div class="empty">
    <div class="empty-inner">
      <div class="empty-icon">${ic.inbox}</div>
      <h3>Nenhum registro nesta base ainda</h3>
      <p>A última sincronização não retornou tarefas. Isso pode ser normal (a base está vazia no Notion) ou indicar que o template precisa ser preenchido. Você ainda pode criar registros manualmente.</p>
      <div style="display:flex;gap:8px;justify-content:center;">
        <button class="btn btn-primary">${ic.sync} Sincronizar agora</button>
        <button class="btn">${ic.plus} Criar primeira tarefa</button>
      </div>
      <p style="margin-top:24px;font-size:11px;color:var(--fg-3);">Última sync: há 1 min · 0 registros · sem erros</p>
    </div>
  </div>`;
}
renderEmpty(document.getElementById('empty-light'));
renderEmpty(document.getElementById('empty-dark'));
