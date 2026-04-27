/* global React, Icon, Shared */
const { Chip, PersonChip, formatBRDate, daysUntil, relativeTime } = Shared;

function Dashboard({ user, onNavigate, lastSync, onSync, syncing }) {
  const RPDATA = window.RPDATA;
  const procAtivos = RPDATA.PROCESSOS_LIST.filter((p) => p.status === 'Ativo').length;
  const tarefasUrgentes = RPDATA.TAREFAS_LIST.filter((t) => {
    const d = daysUntil(t.prazoFatal);
    return d >= 0 && d <= 7 && t.status !== 'Concluída';
  });
  const sobrestados = RPDATA.PROCESSOS_LIST.filter((p) => p.tema955).length;
  const clientesSemProc = RPDATA.CLIENTES_LIST.filter((c) => c.nProcessos === 0).length;
  const sucessoes = RPDATA.PROCESSOS_LIST.filter((p) => p.sucessao).length;

  const recentLogs = RPDATA.LOGS_LIST.slice(0, 8);

  return React.createElement('div', { className: 'page', 'data-screen-label': '02 Dashboard', style: { overflow: 'auto' } },
    React.createElement('div', { className: 'toolbar' },
      React.createElement('h1', { className: 'toolbar-title' },
        new Date().getHours() < 12 ? 'Bom dia, ' : new Date().getHours() < 18 ? 'Boa tarde, ' : 'Boa noite, ',
        user.name, '.'),
      React.createElement('span', { className: 'toolbar-meta', style: { marginLeft: 12 } },
        new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })),
      React.createElement('div', { className: 'toolbar-spacer' }),
      React.createElement('span', { style: { fontSize: 11, color: 'var(--app-fg-subtle)', marginRight: 8 } },
        `Última sync: ${lastSync}`),
      React.createElement('button', {
        className: 'btn btn-secondary',
        onClick: onSync, disabled: syncing,
      },
        syncing
          ? React.createElement('span', { className: 'spinner' })
          : React.createElement(Icon.Refresh, { size: 13 }),
        syncing ? 'Sincronizando…' : 'Sincronizar tudo',
        !syncing && React.createElement(Shared.Kbd, null, 'F5'),
      ),
    ),
    React.createElement('div', { style: { padding: 24, display: 'flex', flexDirection: 'column', gap: 24 } },
      // KPIs
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 } },
        React.createElement('div', { className: 'kpi', onClick: () => onNavigate('processos'), style: { cursor: 'pointer' } },
          React.createElement('div', { className: 'kpi-label' }, 'Processos ativos'),
          React.createElement('div', { className: 'kpi-value' }, procAtivos.toLocaleString('pt-BR')),
          React.createElement('div', { className: 'kpi-foot' }, 'de 1.094 totais · 8 novos esta semana'),
        ),
        React.createElement('div', { className: 'kpi alert', onClick: () => onNavigate('tarefas'), style: { cursor: 'pointer' } },
          React.createElement('div', { className: 'kpi-label' }, 'Prazos fatais — 7 dias'),
          React.createElement('div', { className: 'kpi-value' }, tarefasUrgentes.length,
            React.createElement('span', { className: 'num-suffix' }, 'tarefas')),
          React.createElement('div', { className: 'kpi-foot' },
            React.createElement(Icon.Alert, { size: 12 }),
            tarefasUrgentes.filter((t) => daysUntil(t.prazoFatal) < 0).length, ' já vencidas'),
        ),
        React.createElement('div', { className: 'kpi warn' },
          React.createElement('div', { className: 'kpi-label' }, 'Sobrestados Tema 955'),
          React.createElement('div', { className: 'kpi-value' }, sobrestados),
          React.createElement('div', { className: 'kpi-foot' }, 'Acompanhar julgamento RE 1.476.596'),
        ),
        React.createElement('div', { className: 'kpi', onClick: () => onNavigate('clientes'), style: { cursor: 'pointer' } },
          React.createElement('div', { className: 'kpi-label' }, 'Clientes sem processo'),
          React.createElement('div', { className: 'kpi-value' }, clientesSemProc),
          React.createElement('div', { className: 'kpi-foot' }, 'revisar para arquivamento'),
        ),
        React.createElement('div', { className: 'kpi' },
          React.createElement('div', { className: 'kpi-label' }, 'Sucessões pendentes'),
          React.createElement('div', { className: 'kpi-value' }, sucessoes),
          React.createElement('div', { className: 'kpi-foot' }, 'aguardando habilitação'),
        ),
      ),

      // Two column: tarefas urgentes + atividade
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 16 } },
        React.createElement('div', { className: 'card' },
          React.createElement('div', { className: 'section-head' },
            React.createElement('h2', { className: 'section-title' }, 'Tarefas urgentes'),
            React.createElement('span', { className: 'section-meta' }, 'Próximos 7 dias'),
          ),
          React.createElement('table', { className: 'tbl' },
            React.createElement('thead', null,
              React.createElement('tr', null,
                React.createElement('th', { style: { width: '38%' } }, 'Tarefa'),
                React.createElement('th', { style: { width: '24%' } }, 'CNJ'),
                React.createElement('th', { style: { width: '18%' } }, 'Prazo'),
                React.createElement('th', null, 'Resp.'),
              ),
            ),
            React.createElement('tbody', null,
              tarefasUrgentes.slice(0, 8).map((t) => {
                const d = daysUntil(t.prazoFatal);
                return React.createElement('tr', {
                  key: t.id,
                  onClick: () => onNavigate('tarefas'),
                  style: { cursor: 'pointer' },
                  className: d < 0 ? 'row-danger' : d <= 3 ? 'row-warn' : '',
                },
                  React.createElement('td', null, t.titulo),
                  React.createElement('td', { className: 'cell-mono', style: { color: 'var(--app-fg-muted)' } }, t.processo.slice(0, 14) + '…'),
                  React.createElement('td', null,
                    React.createElement('span', {
                      style: {
                        fontSize: 11.5,
                        color: d < 0 ? 'var(--app-danger)' : d <= 3 ? 'var(--app-warning)' : 'var(--app-fg)',
                        fontWeight: d <= 3 ? 600 : 400,
                      },
                    },
                      formatBRDate(t.prazoFatal),
                      React.createElement('span', { style: { color: 'var(--app-fg-subtle)', marginLeft: 6, fontWeight: 400 } },
                        d < 0 ? `· vencida há ${Math.abs(d)}d` : d === 0 ? '· hoje' : d === 1 ? '· amanhã' : `· em ${d}d`),
                    ),
                  ),
                  React.createElement('td', null, React.createElement(PersonChip, { person: t.responsavel })),
                );
              }),
            ),
          ),
        ),
        React.createElement('div', { className: 'card' },
          React.createElement('div', { className: 'section-head' },
            React.createElement('h2', { className: 'section-title' }, 'Atividade recente'),
            React.createElement('span', { className: 'section-meta' }, 'Últimas 8'),
          ),
          React.createElement('div', { style: { padding: '6px 4px' } },
            recentLogs.map((l) => {
              const p = window.RPDATA.PESSOAS.find((x) => x.id === l.usuario);
              return React.createElement('div', { key: l.id, style: { display: 'grid', gridTemplateColumns: '24px 1fr auto', gap: 10, padding: '10px 14px', borderBottom: '1px solid var(--app-divider)', alignItems: 'start' } },
                React.createElement('span', { style: { width: 22, height: 22, borderRadius: '50%', background: 'var(--app-accent)', color: 'white', fontSize: 10, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' } }, p && p.initials),
                React.createElement('div', { style: { fontSize: 12.5, lineHeight: 1.45 } },
                  React.createElement('strong', { style: { fontWeight: 600 } }, p && p.name),
                  ' alterou ',
                  React.createElement('em', { style: { fontStyle: 'normal', color: 'var(--app-accent)' } }, l.propriedade),
                  ' em ',
                  React.createElement('span', { className: 'mono', style: { fontSize: 11.5, color: 'var(--app-fg-muted)' } }, l.identificador.slice(0, 11) + '…'),
                  React.createElement('div', { style: { fontSize: 11, color: 'var(--app-fg-subtle)', marginTop: 2 } },
                    `${l.valorAntigo} → ${l.valorNovo}`,
                    l.status === 'ERRO' && React.createElement('span', { style: { color: 'var(--app-danger)', marginLeft: 6 } }, '· erro'),
                  ),
                ),
                React.createElement('span', { style: { fontSize: 11, color: 'var(--app-fg-subtle)' } }, relativeTime(l.timestamp)),
              );
            }),
          ),
        ),
      ),

      // Cache hint
      React.createElement('div', { style: { fontSize: 11, color: 'var(--app-fg-subtle)', textAlign: 'center', padding: '4px 0', letterSpacing: '0.04em' } },
        'Dados em cache local · próxima sincronização automática em 2 h'),
    ),
  );
}

window.Dashboard = Dashboard;
