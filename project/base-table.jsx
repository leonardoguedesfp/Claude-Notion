/* global React, Icon, Shared */
const { useState, useEffect, useRef, useMemo } = React;
const { Chip, PersonChip, Kbd, Modal, ConfirmModal, EmptyState, formatBRDate, formatBRL, daysUntil } = Shared;

// Utility — option lookup
function getOpt(arr, value) { return arr.find((x) => x.value === value) || { color: 'gray', label: value }; }

// ========================================================
// Cell renderers
// ========================================================
function ProcStatusCell({ value }) {
  const opt = getOpt(window.RPDATA.STATUS_PROC, value);
  return React.createElement(Chip, { value: opt.label, color: opt.color });
}
function TribunalCell({ value }) {
  const opt = getOpt(window.RPDATA.TRIBUNAIS, value);
  return React.createElement(Chip, { value: opt.label, color: opt.color });
}
function FaseCell({ value }) {
  const opt = getOpt(window.RPDATA.FASES, value);
  return React.createElement(Chip, { value: opt.label, color: opt.color });
}
function InstanciaCell({ value }) {
  const opt = getOpt(window.RPDATA.INSTANCIAS, value);
  return React.createElement(Chip, { value: opt.label, color: opt.color });
}
function PrioridadeCell({ value }) {
  const opt = getOpt(window.RPDATA.PRIORIDADES, value);
  return React.createElement(Chip, { value: opt.label, color: opt.color });
}
function StatusTarefaCell({ value }) {
  const opt = getOpt(window.RPDATA.STATUS_TAREFA, value);
  return React.createElement(Chip, { value: opt.label, color: opt.color });
}

// ========================================================
// Inline editor — generic select
// ========================================================
function InlineSelect({ options, value, onCommit, onCancel }) {
  const ref = useRef();
  useEffect(() => { ref.current && ref.current.focus(); }, []);
  return React.createElement('select', {
    ref, value, autoFocus: true,
    onChange: (e) => onCommit(e.target.value),
    onBlur: onCancel,
    onKeyDown: (e) => { if (e.key === 'Escape') onCancel(); },
  },
    options.map((o) => React.createElement('option', { key: o.value, value: o.value }, o.label)),
  );
}
function InlineText({ value, onCommit, onCancel, mono }) {
  const [v, setV] = useState(value);
  const ref = useRef();
  useEffect(() => { ref.current && ref.current.select(); }, []);
  return React.createElement('input', {
    ref, value: v, autoFocus: true,
    style: mono ? { fontFamily: 'var(--font-mono)' } : null,
    onChange: (e) => setV(e.target.value),
    onBlur: () => onCommit(v),
    onKeyDown: (e) => {
      if (e.key === 'Enter') { e.preventDefault(); onCommit(v); }
      else if (e.key === 'Escape') { onCancel(); }
    },
  });
}

// ========================================================
// Filter popover
// ========================================================
function FilterPopover({ column, options, selected, onApply, onClose, anchorRect }) {
  const [sel, setSel] = useState(new Set(selected || []));
  const toggle = (v) => setSel((s) => { const n = new Set(s); n.has(v) ? n.delete(v) : n.add(v); return n; });
  if (!anchorRect) return null;
  const style = {
    top: anchorRect.bottom + 4,
    left: Math.max(8, Math.min(window.innerWidth - 240, anchorRect.left)),
  };
  return React.createElement('div', { className: 'popover', style, onClick: (e) => e.stopPropagation() },
    React.createElement('div', { className: 'popover-head' }, `Filtrar ${column}`),
    React.createElement('div', { className: 'popover-body' },
      options.map((o) =>
        React.createElement('label', { key: o.value, className: 'popover-item' },
          React.createElement('input', { type: 'checkbox', checked: sel.has(o.value), onChange: () => toggle(o.value) }),
          React.createElement('span', { className: 'chip-dot', style: { background: `var(--chip-${o.color}-fg)`, opacity: 0.7 } }),
          React.createElement('span', null, o.label),
          React.createElement('span', { className: 'item-count' }, o.count),
        ),
      ),
    ),
    React.createElement('div', { className: 'popover-foot' },
      React.createElement('button', { className: 'btn btn-ghost', onClick: () => { onApply([]); onClose(); } }, 'Limpar'),
      React.createElement('button', { className: 'btn btn-primary', onClick: () => { onApply([...sel]); onClose(); } }, 'Aplicar'),
    ),
  );
}

// ========================================================
// Reusable BaseTable
// ========================================================
function BaseTable({
  screenLabel, title, eyebrow, rows, columns, density, onCellEdit,
  search, setSearch, filters, setFilters, sort, setSort,
  selectedId, onSelect, dirtyMap, pending, onSavePending, onDiscardPending,
  detailOpen, setDetailOpen, detailRender,
  toolbarExtras, emptyState, loading,
}) {
  const [editingCell, setEditingCell] = useState(null); // {rowId, col}
  const [filterAnchor, setFilterAnchor] = useState(null); // {col, rect}

  const filteredRows = useMemo(() => {
    let out = rows;
    if (search) {
      const q = search.toLowerCase();
      out = out.filter((r) => columns.some((c) => {
        const v = r[c.key];
        return v && String(v).toLowerCase().includes(q);
      }));
    }
    Object.entries(filters || {}).forEach(([k, vals]) => {
      if (!vals || !vals.length) return;
      out = out.filter((r) => vals.includes(r[k]));
    });
    if (sort && sort.col) {
      const dir = sort.dir === 'desc' ? -1 : 1;
      out = [...out].sort((a, b) => {
        const av = a[sort.col]; const bv = b[sort.col];
        if (av === bv) return 0;
        return av > bv ? dir : -dir;
      });
    }
    return out;
  }, [rows, columns, search, filters, sort]);

  const headerClick = (c) => {
    setSort((s) => {
      if (!c.sortable) return s;
      if (!s || s.col !== c.key) return { col: c.key, dir: 'asc' };
      if (s.dir === 'asc') return { col: c.key, dir: 'desc' };
      return null;
    });
  };

  const closeFilter = () => setFilterAnchor(null);
  useEffect(() => {
    if (!filterAnchor) return;
    const onDoc = () => setFilterAnchor(null);
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, [filterAnchor]);

  const renderCell = (row, c) => {
    const dirtyKey = `${row.id}.${c.key}`;
    const isDirty = dirtyMap && dirtyMap[dirtyKey];
    const isEditing = editingCell && editingCell.rowId === row.id && editingCell.col === c.key;
    const editable = c.editable;
    let content;
    if (isEditing) {
      const commit = (v) => { onCellEdit && onCellEdit(row.id, c.key, v); setEditingCell(null); };
      const cancel = () => setEditingCell(null);
      if (c.editor === 'select-status-proc') content = React.createElement(InlineSelect, { options: window.RPDATA.STATUS_PROC, value: row[c.key], onCommit: commit, onCancel: cancel });
      else if (c.editor === 'select-fase')   content = React.createElement(InlineSelect, { options: window.RPDATA.FASES, value: row[c.key], onCommit: commit, onCancel: cancel });
      else if (c.editor === 'select-tribunal') content = React.createElement(InlineSelect, { options: window.RPDATA.TRIBUNAIS, value: row[c.key], onCommit: commit, onCancel: cancel });
      else if (c.editor === 'select-prioridade') content = React.createElement(InlineSelect, { options: window.RPDATA.PRIORIDADES, value: row[c.key], onCommit: commit, onCancel: cancel });
      else if (c.editor === 'select-status-tarefa') content = React.createElement(InlineSelect, { options: window.RPDATA.STATUS_TAREFA, value: row[c.key], onCommit: commit, onCancel: cancel });
      else content = React.createElement(InlineText, { value: row[c.key], onCommit: commit, onCancel: cancel, mono: c.mono });
    } else {
      content = c.render ? c.render(row[c.key], row) : (row[c.key] == null ? '—' : row[c.key]);
    }
    return React.createElement('td', {
      key: c.key,
      className: [c.className || '', isDirty ? 'dirty' : '', isEditing ? 'editing' : ''].join(' '),
      onDoubleClick: () => editable && setEditingCell({ rowId: row.id, col: c.key }),
      onClick: () => onSelect && onSelect(row.id),
      style: c.width ? { width: c.width } : null,
      title: c.tooltip ? c.tooltip(row[c.key], row) : null,
    }, content);
  };

  const filterColumn = filterAnchor && columns.find((c) => c.key === filterAnchor.col);
  const filterOptionsList = filterColumn && filterColumn.filterOptions
    ? filterColumn.filterOptions.map((o) => ({ ...o, count: rows.filter((r) => r[filterColumn.key] === o.value).length }))
    : [];

  return React.createElement('div', { className: 'page', 'data-screen-label': screenLabel },
    React.createElement('div', { className: 'toolbar' },
      React.createElement('h1', { className: 'toolbar-title' }, title),
      React.createElement('span', { className: 'toolbar-meta' },
        loading ? '— · — · —' : `${filteredRows.length} de ${rows.length} ${eyebrow}`),
      React.createElement('div', { className: 'toolbar-spacer' }),
      React.createElement('div', { className: 'search-input' },
        React.createElement(Icon.Search),
        React.createElement('input', {
          className: 'input', value: search, onChange: (e) => setSearch(e.target.value),
          placeholder: `Buscar em ${eyebrow}…`,
        }),
        React.createElement('span', { className: 'kbd-hint' }, React.createElement(Kbd, null, 'Ctrl+F')),
      ),
      toolbarExtras,
      React.createElement('button', { className: 'btn btn-secondary' },
        React.createElement(Icon.Plus, { size: 13 }), 'Novo'),
      React.createElement('button', { className: 'btn btn-ghost' },
        React.createElement(Icon.Filter, { size: 13 }), 'Filtros salvos',
        React.createElement(Icon.ChevronDown, { size: 12 })),
      React.createElement('button', { className: 'btn btn-ghost' },
        React.createElement(Icon.Download, { size: 13 }), 'Exportar'),
      React.createElement('div', { className: 'divider-v' }),
      React.createElement('button', {
        className: 'btn btn-ghost btn-icon',
        onClick: () => setDetailOpen(!detailOpen),
        title: detailOpen ? 'Esconder detalhe' : 'Mostrar detalhe',
      }, React.createElement(Icon.PanelRight, { size: 14 })),
    ),

    // Active filters bar
    (filters && Object.values(filters).some((v) => v && v.length)) && React.createElement('div', { className: 'filter-bar' },
      React.createElement('span', { style: { fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', fontSize: 10.5, color: 'var(--app-fg-subtle)' } }, 'Filtros ativos:'),
      Object.entries(filters).map(([k, vals]) => (vals || []).map((v) => {
        const col = columns.find((c) => c.key === k);
        return React.createElement('span', {
          key: `${k}-${v}`,
          className: 'filter-pill',
          onClick: () => setFilters({ ...filters, [k]: filters[k].filter((x) => x !== v) }),
        }, `${col ? col.label : k}: ${v}`,
          React.createElement('span', { className: 'filter-x' }, '×'),
        );
      })).flat(),
      React.createElement('button', {
        className: 'btn btn-ghost', style: { height: 22, padding: '0 6px', fontSize: 11, marginLeft: 'auto' },
        onClick: () => setFilters({}),
      }, 'Limpar tudo'),
    ),

    React.createElement('div', { className: `with-detail${detailOpen ? '' : ' collapsed'}` },
      React.createElement('div', { className: 'tbl-wrap' },
        loading
          ? React.createElement('div', { style: { padding: 16 } },
              [...Array(8)].map((_, i) =>
                React.createElement('div', { key: i, style: { display: 'flex', gap: 12, padding: '8px 4px' } },
                  React.createElement('span', { className: 'skel', style: { width: 180, height: 12 } }),
                  React.createElement('span', { className: 'skel', style: { width: 64, height: 16, borderRadius: 3 } }),
                  React.createElement('span', { className: 'skel', style: { width: 80, height: 16, borderRadius: 3 } }),
                  React.createElement('span', { className: 'skel', style: { width: 130, height: 12 } }),
                  React.createElement('span', { className: 'skel', style: { width: 100, height: 12 } }),
                ),
              ),
            )
          : filteredRows.length === 0
          ? emptyState
          : React.createElement('div', { className: 'tbl-scroll', style: { position: 'relative' } },
              React.createElement('table', { className: `tbl ${density}` },
                React.createElement('colgroup', null,
                  columns.map((c) => React.createElement('col', { key: c.key, style: c.width ? { width: c.width } : null })),
                ),
                React.createElement('thead', null,
                  React.createElement('tr', null,
                    columns.map((c) => React.createElement('th', { key: c.key },
                      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 4 } },
                        React.createElement('span', {
                          className: `th-inner${sort && sort.col === c.key ? ' active' : ''}`,
                          onClick: () => headerClick(c),
                        },
                          c.label,
                          sort && sort.col === c.key
                            ? React.createElement(sort.dir === 'asc' ? Icon.ChevronUp : Icon.ChevronDown, { size: 12 })
                            : null,
                        ),
                        c.filterOptions ? React.createElement('button', {
                          className: `th-filter${(filters && filters[c.key] && filters[c.key].length) ? ' active' : ''}`,
                          onClick: (e) => { e.stopPropagation(); const r = e.currentTarget.getBoundingClientRect(); setFilterAnchor({ col: c.key, rect: r }); },
                        }, React.createElement(Icon.Filter, { size: 11 })) : null,
                      ),
                    )),
                  ),
                ),
                React.createElement('tbody', null,
                  filteredRows.map((r) => {
                    const isDirtyRow = dirtyMap && Object.keys(dirtyMap).some((k) => k.startsWith(r.id + '.'));
                    return React.createElement('tr', {
                      key: r.id,
                      className: [
                        selectedId === r.id ? 'selected' : '',
                        isDirtyRow ? 'dirty' : '',
                        r._rowClass || '',
                      ].join(' '),
                    },
                      columns.map((c) => renderCell(r, c)),
                    );
                  }),
                ),
              ),
              pending > 0 && React.createElement('div', { className: 'floating-save' },
                React.createElement('span', null, `${pending} alteração${pending > 1 ? 'ões' : ''} pendente${pending > 1 ? 's' : ''}`),
                React.createElement('span', { className: 'floating-pendings' },
                  Object.keys(dirtyMap || {}).slice(0, 3).join(', '),
                  Object.keys(dirtyMap || {}).length > 3 ? '…' : ''),
                React.createElement('button', { className: 'btn btn-ghost', onClick: onDiscardPending }, 'Descartar'),
                React.createElement('button', { className: 'btn btn-primary', onClick: onSavePending },
                  React.createElement(Icon.Check, { size: 12 }), 'Salvar', React.createElement(Kbd, null, 'Ctrl+S')),
              ),
            ),
      ),
      detailOpen && React.createElement('aside', { className: 'detail' }, detailRender()),
    ),

    filterAnchor && filterColumn && React.createElement(FilterPopover, {
      column: filterColumn.label, options: filterOptionsList,
      selected: (filters && filters[filterColumn.key]) || [],
      onApply: (vals) => setFilters({ ...(filters || {}), [filterColumn.key]: vals }),
      onClose: closeFilter,
      anchorRect: filterAnchor.rect,
    }),
  );
}

window.BaseTable = BaseTable;
window.CellRenderers = { ProcStatusCell, TribunalCell, FaseCell, InstanciaCell, PrioridadeCell, StatusTarefaCell };
