/* global React, Icon, Shared, BaseTable, CellRenderers */
const { useState, useMemo } = React;
const { Chip, PersonChip, Kbd, formatBRDate, formatBRL, daysUntil } = Shared;

// =====================================================
// PROCESSOS
// =====================================================
function ProcessosPage({ density, detailOpen, setDetailOpen, onOpenConfirm }) {
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({});
  const [sort, setSort] = useState(null);
  const [selectedId, setSelectedId] = useState('p1');
  const [edits, setEdits] = useState({}); // { rowId: { col: newVal, ... } }
  const RPDATA = window.RPDATA;

  const baseRows = RPDATA.PROCESSOS_LIST;
  const rows = useMemo(() => baseRows.map((r) => {
    const e = edits[r.id];
    if (!e) return r;
    return { ...r, ...e };
  }), [baseRows, edits]);

  const dirtyMap = {};
  Object.entries(edits).forEach(([rid, cols]) => {
    Object.keys(cols).forEach((c) => { dirtyMap[`${rid}.${c}`] = true; });
  });
  const pending = Object.keys(dirtyMap).length;

  function onCellEdit(rowId, col, val) {
    setEdits((e) => {
      const cur = e[rowId] || {};
      // If new value matches original, drop it
      const orig = baseRows.find((r) => r.id === rowId)[col];
      if (val === orig) {
        const { [col]: _, ...rest } = cur;
        const next = { ...e };
        if (Object.keys(rest).length === 0) delete next[rowId];
        else next[rowId] = rest;
        return next;
      }
      return { ...e, [rowId]: { ...cur, [col]: val } };
    });
  }

  function onSavePending() {
    const diffs = [];
    Object.entries(edits).forEach(([rid, cols]) => {
      const orig = baseRows.find((r) => r.id === rid);
      Object.entries(cols).forEach(([col, val]) => {
        diffs.push({
          label: `${orig.cnj.slice(0, 11)}… › ${col}`,
          before: String(orig[col]),
          after: String(val),
        });
      });
    });
    onOpenConfirm({
      title: `Aplicar ${pending} alteração${pending > 1 ? 'ões' : ''} no Notion?`,
      eyebrow: 'Confirmação destrutiva',
      body: React.createElement('p', { style: { fontSize: 13, lineHeight: 1.5, color: 'var(--app-fg-muted)' } },
        'As alterações serão sobrescritas nas páginas do Notion correspondentes. Esta operação fica registrada no log e pode ser revertida individualmente em ',
        React.createElement('strong', null, 'Logs'), '.'),
      diff: diffs,
      onConfirm: () => { setEdits({}); },
      confirmLabel: `Aplicar ${pending} alteração${pending > 1 ? 'ões' : ''}`,
    });
  }

  function onDiscardPending() { setEdits({}); }

  const columns = [
    {
      key: 'cnj', label: 'CNJ', width: '20%', mono: true, sortable: true, editable: true,
      className: 'cell-mono',
      render: (v) => React.createElement('span', { className: 'cell-link' }, v),
    },
    {
      key: 'tribunal', label: 'Tribunal', width: '8%', editable: true, editor: 'select-tribunal',
      filterOptions: RPDATA.TRIBUNAIS, sortable: true,
      render: (v) => React.createElement(CellRenderers.TribunalCell, { value: v }),
    },
    {
      key: 'instancia', label: 'Instância', width: '8%', editable: true,
      filterOptions: RPDATA.INSTANCIAS, sortable: true,
      render: (v) => React.createElement(CellRenderers.InstanciaCell, { value: v }),
    },
    {
      key: 'fase', label: 'Fase', width: '12%', editable: true, editor: 'select-fase',
      filterOptions: RPDATA.FASES, sortable: true,
      render: (v) => React.createElement(CellRenderers.FaseCell, { value: v }),
    },
    {
      key: 'status', label: 'Status', width: '9%', editable: true, editor: 'select-status-proc',
      filterOptions: RPDATA.STATUS_PROC, sortable: true,
      render: (v) => React.createElement(CellRenderers.ProcStatusCell, { value: v }),
    },
    { key: 'cliente', label: 'Cliente principal', width: '17%', sortable: true,
      render: (v) => React.createElement('span', { style: { color: 'var(--app-fg)' } }, v) },
    { key: 'distribuicao', label: 'Distribuição', width: '10%', sortable: true,
      render: (v) => React.createElement('span', { style: { fontVariantNumeric: 'tabular-nums' } }, formatBRDate(v)) },
    { key: 'valorCausa', label: 'Valor da causa', width: '11%', sortable: true,
      className: 'cell-num',
      render: (v) => React.createElement('span', { style: { color: 'var(--app-fg-muted)' } }, formatBRL(v)) },
    { key: 'responsavel', label: 'Resp.', width: '5%',
      filterOptions: RPDATA.PESSOAS.map((p) => ({ value: p.id, label: p.name, color: 'gray' })),
      render: (v) => React.createElement(PersonChip, { person: v }) },
  ];

  const selected = rows.find((r) => r.id === selectedId);

  function detailRender() {
    if (!selected) return React.createElement('div', { className: 'detail-body', style: { color: 'var(--app-fg-subtle)', fontSize: 12 } }, 'Selecione uma linha.');
    return React.createElement(React.Fragment, null,
      React.createElement('div', { className: 'detail-head' },
        React.createElement('div', null,
          React.createElement('div', { className: 'detail-eyebrow' }, 'Processo'),
          React.createElement('h3', null, selected.cnj.slice(0, 18) + '…'),
          React.createElement('div', { style: { marginTop: 6, display: 'flex', gap: 4, flexWrap: 'wrap' } },
            React.createElement(CellRenderers.TribunalCell, { value: selected.tribunal }),
            React.createElement(CellRenderers.ProcStatusCell, { value: selected.status }),
            selected.tema955 && React.createElement(Chip, { value: 'Tema 955', color: 'red' }),
          ),
        ),
        React.createElement('button', { className: 'btn btn-ghost btn-icon', onClick: () => setDetailOpen(false) },
          React.createElement(Icon.X, { size: 14 })),
      ),
      React.createElement('div', { className: 'detail-body' },
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'CNJ'),
          React.createElement('span', { className: 'detail-prop-value mono' }, selected.cnj),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Tribunal'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(CellRenderers.TribunalCell, { value: selected.tribunal })),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Instância'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(CellRenderers.InstanciaCell, { value: selected.instancia })),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Fase'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(CellRenderers.FaseCell, { value: selected.fase })),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Status'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(CellRenderers.ProcStatusCell, { value: selected.status })),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Cliente'),
          React.createElement('span', { className: 'detail-prop-value' },
            React.createElement('a', { className: 'chip chip-relation', href: '#' }, selected.cliente)),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Parte contrária'),
          React.createElement('span', { className: 'detail-prop-value' }, selected.parteContraria),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Distribuição'),
          React.createElement('span', { className: 'detail-prop-value' }, formatBRDate(selected.distribuicao)),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Valor da causa'),
          React.createElement('span', { className: 'detail-prop-value mono' }, formatBRL(selected.valorCausa)),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Responsável'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(PersonChip, { person: selected.responsavel })),
        ),
        selected.tema955 && React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Tema 955'),
          React.createElement('span', { className: 'detail-prop-value', style: { color: 'var(--app-danger)' } }, 'Sobrestado · acompanhar RE 1.476.596'),
        ),
        selected.observacoes && React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Observações'),
          React.createElement('span', { className: 'detail-prop-value', style: { display: 'block', fontStyle: 'italic', color: 'var(--app-fg-muted)' } }, selected.observacoes),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Tarefas vinc.'),
          React.createElement('span', { className: 'detail-prop-value' },
            (() => {
              const ts = window.RPDATA.TAREFAS_LIST.filter((t) => t.processoId === selected.id);
              if (!ts.length) return React.createElement('span', { className: 'subtle' }, 'Nenhuma');
              return ts.slice(0, 3).map((t) => React.createElement('a', { key: t.id, className: 'chip chip-relation', style: { fontSize: 11 } }, t.titulo));
            })(),
          ),
        ),
      ),
      React.createElement('div', { className: 'detail-foot' },
        React.createElement('button', { className: 'btn btn-secondary', style: { flex: 1 } },
          React.createElement(Icon.Edit, { size: 12 }), 'Editar tudo'),
        React.createElement('button', { className: 'btn btn-ghost btn-icon' },
          React.createElement(Icon.More, { size: 14 })),
      ),
    );
  }

  return React.createElement(BaseTable, {
    screenLabel: '03 Processos',
    title: 'Processos', eyebrow: 'processos',
    rows, columns, density, onCellEdit,
    search, setSearch, filters, setFilters, sort, setSort,
    selectedId, onSelect: setSelectedId, dirtyMap, pending, onSavePending, onDiscardPending,
    detailOpen, setDetailOpen, detailRender,
    emptyState: search || Object.values(filters).some((v) => v && v.length)
      ? React.createElement(Shared.EmptyState, {
          eyebrow: 'Sem resultado',
          title: 'Nenhum processo bate com os filtros atuais.',
          message: 'Ajuste os filtros ou a busca para reencontrar processos.',
          action: React.createElement('button', {
            className: 'btn btn-primary',
            onClick: () => { setFilters({}); setSearch(''); },
          }, 'Limpar filtros'),
        })
      : React.createElement(Shared.EmptyState, {
          eyebrow: 'Cache vazio',
          title: 'Sincronize para carregar processos.',
          message: 'A base de Processos ainda não foi carregada nesta máquina.',
          action: React.createElement('button', { className: 'btn btn-primary' },
            React.createElement(Icon.Refresh, { size: 12 }), 'Sincronizar Processos'),
        }),
  });
}

// =====================================================
// CLIENTES
// =====================================================
function ClientesPage({ density, detailOpen, setDetailOpen, onOpenConfirm }) {
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({});
  const [sort, setSort] = useState(null);
  const [selectedId, setSelectedId] = useState('c1');
  const [edits, setEdits] = useState({});
  const RPDATA = window.RPDATA;
  const baseRows = RPDATA.CLIENTES_LIST;
  const rows = useMemo(() => baseRows.map((r) => ({ ...r, ...(edits[r.id] || {}) })), [baseRows, edits]);
  const dirtyMap = {};
  Object.entries(edits).forEach(([rid, cols]) => Object.keys(cols).forEach((c) => { dirtyMap[`${rid}.${c}`] = true; }));
  const pending = Object.keys(dirtyMap).length;

  const columns = [
    { key: 'nome', label: 'Nome', width: '24%', editable: true, sortable: true,
      render: (v, r) => React.createElement('span', null,
        r.falecido && React.createElement('span', { className: 'cell-deceased', title: 'Falecido' }),
        React.createElement('span', { style: { color: 'var(--app-fg)', fontWeight: 500 } }, v),
        r.falecido && React.createElement('span', { style: { fontSize: 10, color: 'var(--app-fg-subtle)', marginLeft: 6, letterSpacing: '0.06em', textTransform: 'uppercase' } }, '· falecido'),
      ),
    },
    { key: 'cpf', label: 'CPF', width: '12%', mono: true, className: 'cell-mono', sortable: true, editable: true },
    { key: 'email', label: 'E-mail', width: '20%', sortable: true, editable: true,
      render: (v) => React.createElement('span', { style: { color: 'var(--app-fg-muted)' } }, v) },
    { key: 'telefone', label: 'Telefone', width: '12%', mono: true, className: 'cell-mono', editable: true,
      render: (v) => React.createElement('span', { style: { color: 'var(--app-fg-muted)' } }, v) },
    { key: 'cidade', label: 'Cidade/UF', width: '13%', sortable: true, editable: true },
    { key: 'nProcessos', label: 'Nº processos', width: '9%', sortable: true, className: 'cell-num',
      render: (v) => React.createElement('span', { style: { fontVariantNumeric: 'tabular-nums', color: v === 0 ? 'var(--app-fg-subtle)' : 'var(--app-fg)' } }, v) },
    { key: 'cadastrado', label: 'Cadastro', width: '10%', sortable: true,
      render: (v) => React.createElement('span', { style: { fontVariantNumeric: 'tabular-nums', color: 'var(--app-fg-muted)' } }, formatBRDate(v)) },
  ];

  function onCellEdit(rid, col, val) {
    setEdits((e) => {
      const cur = e[rid] || {};
      const orig = baseRows.find((r) => r.id === rid)[col];
      if (val === orig) {
        const { [col]: _, ...rest } = cur;
        const next = { ...e };
        if (!Object.keys(rest).length) delete next[rid]; else next[rid] = rest;
        return next;
      }
      return { ...e, [rid]: { ...cur, [col]: val } };
    });
  }

  const selected = rows.find((r) => r.id === selectedId);

  return React.createElement(BaseTable, {
    screenLabel: '04 Clientes',
    title: 'Clientes', eyebrow: 'clientes',
    rows, columns, density, onCellEdit,
    search, setSearch, filters, setFilters, sort, setSort,
    selectedId, onSelect: setSelectedId, dirtyMap, pending,
    onSavePending: () => { setEdits({}); },
    onDiscardPending: () => setEdits({}),
    detailOpen, setDetailOpen,
    detailRender: () => selected ? React.createElement(React.Fragment, null,
      React.createElement('div', { className: 'detail-head' },
        React.createElement('div', null,
          React.createElement('div', { className: 'detail-eyebrow' }, 'Cliente' + (selected.falecido ? ' · falecido' : '')),
          React.createElement('h3', null, selected.nome),
        ),
        React.createElement('button', { className: 'btn btn-ghost btn-icon', onClick: () => setDetailOpen(false) }, React.createElement(Icon.X, { size: 14 })),
      ),
      React.createElement('div', { className: 'detail-body' },
        ['cpf:CPF', 'email:E-mail', 'telefone:Telefone', 'cidade:Cidade/UF', 'cadastrado:Cadastrado em', 'nProcessos:Nº processos'].map((kv) => {
          const [k, l] = kv.split(':');
          let v = selected[k];
          if (k === 'cadastrado') v = formatBRDate(v);
          return React.createElement('div', { key: k, className: 'detail-prop' },
            React.createElement('span', { className: 'detail-prop-label' }, l),
            React.createElement('span', { className: 'detail-prop-value' + (k === 'cpf' ? ' mono' : '') }, v),
          );
        }),
        selected.notas && React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Notas'),
          React.createElement('span', { className: 'detail-prop-value', style: { fontStyle: 'italic', color: 'var(--app-fg-muted)' } }, selected.notas),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Processos'),
          React.createElement('span', { className: 'detail-prop-value' },
            (() => {
              const ps = window.RPDATA.PROCESSOS_LIST.filter((p) => p.clienteId === selected.id);
              if (!ps.length) return React.createElement('span', { className: 'subtle' }, 'Nenhum');
              return ps.slice(0, 5).map((p) => React.createElement('a', { key: p.id, className: 'chip chip-relation', style: { fontSize: 11, fontFamily: 'var(--font-mono)' } }, p.cnj.slice(0, 14) + '…'));
            })(),
          ),
        ),
      ),
      React.createElement('div', { className: 'detail-foot' },
        React.createElement('button', { className: 'btn btn-secondary', style: { flex: 1 } },
          React.createElement(Icon.Edit, { size: 12 }), 'Editar tudo'),
      ),
    ) : null,
    emptyState: React.createElement(Shared.EmptyState, {
      eyebrow: 'Sem resultado', title: 'Nenhum cliente bate com os filtros atuais.',
      message: 'Ajuste a busca ou os filtros para reencontrar.',
      action: React.createElement('button', { className: 'btn btn-primary', onClick: () => { setFilters({}); setSearch(''); } }, 'Limpar filtros'),
    }),
  });
}

// =====================================================
// TAREFAS
// =====================================================
function TarefasPage({ density, detailOpen, setDetailOpen }) {
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({});
  const [sort, setSort] = useState({ col: 'prazoFatal', dir: 'asc' });
  const [selectedId, setSelectedId] = useState('t1');
  const [edits, setEdits] = useState({});
  const RPDATA = window.RPDATA;
  const baseRows = RPDATA.TAREFAS_LIST;
  const rows = useMemo(() => baseRows.map((r) => {
    const merged = { ...r, ...(edits[r.id] || {}) };
    const d = daysUntil(merged.prazoFatal);
    if (d < 0 && merged.status !== 'Concluída') merged._rowClass = 'row-danger';
    else if (d <= 3 && merged.status !== 'Concluída') merged._rowClass = 'row-warn';
    return merged;
  }), [baseRows, edits]);
  const dirtyMap = {};
  Object.entries(edits).forEach(([rid, cols]) => Object.keys(cols).forEach((c) => { dirtyMap[`${rid}.${c}`] = true; }));
  const pending = Object.keys(dirtyMap).length;

  const columns = [
    { key: 'titulo', label: 'Tarefa', width: '28%', editable: true, sortable: true,
      render: (v) => React.createElement('span', { style: { color: 'var(--app-fg)', fontWeight: 500 } }, v) },
    { key: 'prazoFatal', label: 'Prazo fatal', width: '14%', editable: true, sortable: true,
      render: (v, r) => {
        const d = daysUntil(v);
        const cor = d < 0 && r.status !== 'Concluída' ? 'var(--app-danger)' : d <= 3 && r.status !== 'Concluída' ? 'var(--app-warning)' : 'var(--app-fg)';
        return React.createElement('span', { style: { fontVariantNumeric: 'tabular-nums', color: cor, fontWeight: d <= 3 ? 600 : 400 } },
          formatBRDate(v),
          React.createElement('span', { style: { color: 'var(--app-fg-subtle)', marginLeft: 6, fontWeight: 400, fontSize: 11 } },
            d < 0 ? `· venceu há ${Math.abs(d)}d` : d === 0 ? '· hoje' : d === 1 ? '· amanhã' : d <= 7 ? `· em ${d}d` : ''),
        );
      },
    },
    { key: 'prioridade', label: 'Prioridade', width: '10%', editable: true, editor: 'select-prioridade',
      filterOptions: RPDATA.PRIORIDADES, sortable: true,
      render: (v) => React.createElement(CellRenderers.PrioridadeCell, { value: v }) },
    { key: 'status', label: 'Status', width: '12%', editable: true, editor: 'select-status-tarefa',
      filterOptions: RPDATA.STATUS_TAREFA, sortable: true,
      render: (v) => React.createElement(CellRenderers.StatusTarefaCell, { value: v }) },
    { key: 'processo', label: 'Processo', width: '17%', mono: true, className: 'cell-mono',
      render: (v) => React.createElement('span', { className: 'cell-link' }, v.slice(0, 18) + '…') },
    { key: 'cliente', label: 'Cliente', width: '14%', sortable: true,
      render: (v) => React.createElement('span', { style: { color: 'var(--app-fg-muted)' } }, v) },
    { key: 'responsavel', label: 'Resp.', width: '5%',
      filterOptions: RPDATA.PESSOAS.map((p) => ({ value: p.id, label: p.name, color: 'gray' })),
      render: (v) => React.createElement(PersonChip, { person: v }) },
  ];

  function onCellEdit(rid, col, val) {
    setEdits((e) => {
      const cur = e[rid] || {};
      const orig = baseRows.find((r) => r.id === rid)[col];
      if (val === orig) {
        const { [col]: _, ...rest } = cur;
        const next = { ...e };
        if (!Object.keys(rest).length) delete next[rid]; else next[rid] = rest;
        return next;
      }
      return { ...e, [rid]: { ...cur, [col]: val } };
    });
  }

  const selected = rows.find((r) => r.id === selectedId);

  return React.createElement(BaseTable, {
    screenLabel: '05 Tarefas',
    title: 'Tarefas', eyebrow: 'tarefas',
    rows, columns, density, onCellEdit,
    search, setSearch, filters, setFilters, sort, setSort,
    selectedId, onSelect: setSelectedId, dirtyMap, pending,
    onSavePending: () => setEdits({}),
    onDiscardPending: () => setEdits({}),
    detailOpen, setDetailOpen,
    detailRender: () => selected ? React.createElement(React.Fragment, null,
      React.createElement('div', { className: 'detail-head' },
        React.createElement('div', null,
          React.createElement('div', { className: 'detail-eyebrow' }, 'Tarefa'),
          React.createElement('h3', null, selected.titulo),
        ),
        React.createElement('button', { className: 'btn btn-ghost btn-icon', onClick: () => setDetailOpen(false) }, React.createElement(Icon.X, { size: 14 })),
      ),
      React.createElement('div', { className: 'detail-body' },
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Prazo fatal'),
          React.createElement('span', { className: 'detail-prop-value' }, formatBRDate(selected.prazoFatal)),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Prioridade'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(CellRenderers.PrioridadeCell, { value: selected.prioridade })),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Status'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(CellRenderers.StatusTarefaCell, { value: selected.status })),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Processo'),
          React.createElement('span', { className: 'detail-prop-value' },
            React.createElement('a', { className: 'chip chip-relation mono', style: { fontFamily: 'var(--font-mono)', fontSize: 11 } }, selected.processo)),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Cliente'),
          React.createElement('span', { className: 'detail-prop-value' }, selected.cliente),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Tipo (catálogo)'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(Chip, { value: selected.catalogoTipo, color: 'petrol' })),
        ),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Responsável'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(PersonChip, { person: selected.responsavel })),
        ),
      ),
      React.createElement('div', { className: 'detail-foot' },
        React.createElement('button', { className: 'btn btn-primary', style: { flex: 1 } },
          React.createElement(Icon.Check, { size: 12 }), 'Marcar como concluída'),
      ),
    ) : null,
    emptyState: React.createElement(Shared.EmptyState, {
      eyebrow: 'Sem resultado', title: 'Nenhuma tarefa bate com os filtros atuais.',
      message: 'Limpe os filtros para ver todas as tarefas pendentes.',
      action: React.createElement('button', { className: 'btn btn-primary', onClick: () => { setFilters({}); setSearch(''); } }, 'Limpar filtros'),
    }),
  });
}

// =====================================================
// CATÁLOGO
// =====================================================
function CatalogoPage({ density, detailOpen, setDetailOpen }) {
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState({});
  const [sort, setSort] = useState(null);
  const [selectedId, setSelectedId] = useState('k1');
  const [edits, setEdits] = useState({});
  const RPDATA = window.RPDATA;
  const baseRows = RPDATA.CATALOGO_LIST;
  const rows = useMemo(() => baseRows.map((r) => ({ ...r, ...(edits[r.id] || {}) })), [baseRows, edits]);

  const columns = [
    { key: 'titulo', label: 'Tipo de tarefa', width: '36%', editable: true, sortable: true,
      render: (v) => React.createElement('span', { style: { fontWeight: 500 } }, v) },
    { key: 'categoria', label: 'Categoria', width: '14%', editable: true,
      filterOptions: ['Petição', 'Recurso', 'Audiência', 'Cálculo', 'Reunião', 'Outros'].map((v) => ({ value: v, label: v, color: 'petrol' })),
      render: (v) => React.createElement(Chip, { value: v, color: 'petrol' }) },
    { key: 'area', label: 'Área', width: '14%', editable: true,
      filterOptions: ['Trabalhista', 'Empresarial', 'Geral'].map((v) => ({ value: v, label: v, color: 'blue' })),
      render: (v) => React.createElement(Chip, { value: v, color: v === 'Trabalhista' ? 'blue' : v === 'Empresarial' ? 'purple' : 'gray' }) },
    { key: 'tempoEstimado', label: 'Tempo médio', width: '12%', editable: true, sortable: true,
      render: (v) => React.createElement('span', { className: 'mono', style: { color: 'var(--app-fg-muted)' } }, v) },
    { key: 'responsavelPadrao', label: 'Resp. padrão', width: '14%',
      render: (v) => React.createElement(PersonChip, { person: v }) },
    { key: 'revisado', label: 'Última revisão', width: '12%', sortable: true,
      render: (v) => React.createElement('span', { style: { fontVariantNumeric: 'tabular-nums', color: 'var(--app-fg-muted)' } }, formatBRDate(v)) },
  ];

  const selected = rows.find((r) => r.id === selectedId);

  return React.createElement(BaseTable, {
    screenLabel: '06 Catálogo',
    title: 'Catálogo de tarefas', eyebrow: 'tipos',
    rows, columns, density: 'comfort',
    onCellEdit: (rid, col, val) => setEdits((e) => ({ ...e, [rid]: { ...(e[rid] || {}), [col]: val } })),
    search, setSearch, filters, setFilters, sort, setSort,
    selectedId, onSelect: setSelectedId,
    detailOpen, setDetailOpen, dirtyMap: {}, pending: 0,
    onSavePending: () => setEdits({}), onDiscardPending: () => setEdits({}),
    detailRender: () => selected ? React.createElement(React.Fragment, null,
      React.createElement('div', { className: 'detail-head' },
        React.createElement('div', null,
          React.createElement('div', { className: 'detail-eyebrow' }, 'Tipo de tarefa'),
          React.createElement('h3', null, selected.titulo),
        ),
        React.createElement('button', { className: 'btn btn-ghost btn-icon', onClick: () => setDetailOpen(false) }, React.createElement(Icon.X, { size: 14 })),
      ),
      React.createElement('div', { className: 'detail-body' },
        ['categoria:Categoria', 'area:Área', 'tempoEstimado:Tempo médio', 'revisado:Última revisão'].map((kv) => {
          const [k, l] = kv.split(':');
          let v = selected[k];
          if (k === 'revisado') v = formatBRDate(v);
          return React.createElement('div', { key: k, className: 'detail-prop' },
            React.createElement('span', { className: 'detail-prop-label' }, l),
            React.createElement('span', { className: 'detail-prop-value' }, v),
          );
        }),
        React.createElement('div', { className: 'detail-prop' },
          React.createElement('span', { className: 'detail-prop-label' }, 'Resp. padrão'),
          React.createElement('span', { className: 'detail-prop-value' }, React.createElement(PersonChip, { person: selected.responsavelPadrao })),
        ),
      ),
    ) : null,
    emptyState: React.createElement(Shared.EmptyState, {
      eyebrow: 'Sem resultado', title: 'Nenhum tipo de tarefa bate com os filtros.',
      message: 'Limpe a busca para ver o catálogo completo.',
      action: React.createElement('button', { className: 'btn btn-primary', onClick: () => { setFilters({}); setSearch(''); } }, 'Limpar filtros'),
    }),
  });
}

window.Pages = { ProcessosPage, ClientesPage, TarefasPage, CatalogoPage };
