/* global React, Icon */
const { useState, useEffect, useRef, useMemo, useCallback } = React;

// ============================================================
// Chip — semantic pill
// ============================================================
function Chip({ value, color = 'default', icon, onClick, className = '' }) {
  const cls = `chip chip-${color} ${className}`;
  return React.createElement(
    onClick ? 'button' : 'span',
    { className: cls, onClick, style: onClick ? { border: 'none', cursor: 'pointer' } : null },
    icon,
    value,
  );
}

// ============================================================
// Person chip — avatar + first name
// ============================================================
function PersonChip({ person }) {
  const RPDATA = window.RPDATA;
  const p = RPDATA.PESSOAS.find((x) => x.id === person);
  if (!p) return null;
  return React.createElement('span', { className: 'chip chip-person' },
    React.createElement('span', { className: 'avatar' }, p.initials),
    p.name,
  );
}

// ============================================================
// Format helpers
// ============================================================
function formatBRDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}
function formatBRDateTime(iso) {
  const dt = new Date(iso);
  const d = String(dt.getDate()).padStart(2, '0');
  const m = String(dt.getMonth() + 1).padStart(2, '0');
  const y = dt.getFullYear();
  const hh = String(dt.getHours()).padStart(2, '0');
  const mm = String(dt.getMinutes()).padStart(2, '0');
  return `${d}/${m}/${y} ${hh}:${mm}`;
}
function formatBRL(n) {
  return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 0, maximumFractionDigits: 0 });
}
function relativeTime(iso) {
  const dt = new Date(iso);
  const diff = (Date.now() - dt.getTime()) / 1000;
  if (diff < 60) return 'agora';
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  return `há ${Math.floor(diff / 86400)} dias`;
}
function daysUntil(iso) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(iso + 'T00:00:00');
  return Math.round((target - today) / 86400000);
}

// ============================================================
// KBD pill
// ============================================================
function Kbd({ children }) {
  return React.createElement('span', { className: 'kbd' }, children);
}

// ============================================================
// Window chrome (Windows-style)
// ============================================================
function WinChrome({ user, onMinimize, onMaximize, onClose }) {
  return React.createElement('div', { className: 'win-chrome' },
    React.createElement('div', { className: 'win-chrome-title' },
      `Notion RPADV — ${user ? user.name : 'Não autenticado'}`),
    React.createElement('div', { className: 'win-chrome-buttons' },
      React.createElement('button', { className: 'win-chrome-btn', onClick: onMinimize, 'aria-label': 'Minimizar' },
        React.createElement('svg', { width: 10, height: 10, viewBox: '0 0 10 10' },
          React.createElement('path', { d: 'M0 5h10', stroke: 'currentColor', strokeWidth: 1 }))),
      React.createElement('button', { className: 'win-chrome-btn', onClick: onMaximize, 'aria-label': 'Maximizar' },
        React.createElement('svg', { width: 10, height: 10, viewBox: '0 0 10 10' },
          React.createElement('rect', { x: 0.5, y: 0.5, width: 9, height: 9, fill: 'none', stroke: 'currentColor', strokeWidth: 1 }))),
      React.createElement('button', { className: 'win-chrome-btn close', onClick: onClose, 'aria-label': 'Fechar' },
        React.createElement('svg', { width: 10, height: 10, viewBox: '0 0 10 10' },
          React.createElement('path', { d: 'M0 0L10 10M10 0L0 10', stroke: 'currentColor', strokeWidth: 1 }))),
    ),
  );
}

// ============================================================
// Sidebar
// ============================================================
function Sidebar({ active, onNavigate, urgentCount }) {
  const items = [
    { id: 'dashboard', label: 'Dashboard', icon: Icon.Dashboard, shortcut: '⌘1' },
    { id: 'processos', label: 'Processos', icon: Icon.Folder, shortcut: '⌘2' },
    { id: 'clientes',  label: 'Clientes',  icon: Icon.Users,  shortcut: '⌘3' },
    { id: 'tarefas',   label: 'Tarefas',   icon: Icon.CheckSquare, shortcut: '⌘4', badge: urgentCount },
    { id: 'catalogo',  label: 'Catálogo',  icon: Icon.Book,   shortcut: '⌘5' },
  ];
  const data = [
    { id: 'importar', label: 'Importar planilha', icon: Icon.Upload },
    { id: 'logs',     label: 'Logs',              icon: Icon.Activity },
  ];
  const sys = [
    { id: 'config',   label: 'Configurações',     icon: Icon.Settings },
  ];

  const renderItem = (item) => {
    const isActive = active === item.id;
    return React.createElement('button', {
      key: item.id,
      className: `sidebar-nav-item${isActive ? ' active' : ''}`,
      onClick: () => onNavigate(item.id),
    },
      React.createElement(item.icon, { className: 'nav-icon' }),
      React.createElement('span', { className: 'nav-label' }, item.label),
      item.badge ? React.createElement('span', { className: 'nav-badge' }, item.badge) : null,
      item.shortcut && !item.badge ? React.createElement('span', { className: 'nav-shortcut' }, item.shortcut) : null,
    );
  };

  return React.createElement('aside', { className: 'sidebar' },
    React.createElement('div', { className: 'sidebar-brand' },
      React.createElement('img', { src: 'assets/symbol-cream.png', alt: '' }),
      React.createElement('div', { className: 'sidebar-brand-text' },
        'Notion RPADV',
        React.createElement('small', null, 'Ricardo Passos Advocacia'),
      ),
    ),
    React.createElement('div', { className: 'sidebar-section' },
      items.map(renderItem),
    ),
    React.createElement('div', { className: 'sidebar-section' },
      React.createElement('div', { className: 'sidebar-label' }, 'Dados'),
      data.map(renderItem),
    ),
    React.createElement('div', { className: 'sidebar-section', style: { marginTop: 'auto' } },
      sys.map(renderItem),
    ),
  );
}

// ============================================================
// Status bar
// ============================================================
function StatusBar({ user, lastSync, online, pending, theme, onlineState }) {
  let dotClass = 'statusbar-dot';
  let connText = 'Online';
  if (onlineState === 'offline') { dotClass += ' offline'; connText = 'Offline — alterações em fila'; }
  else if (onlineState === 'rate-limit') { dotClass += ' offline'; connText = 'Aguardando Notion (429) — 3s'; }
  else if (onlineState === 'error') { dotClass += ' error'; connText = 'Erro de conexão'; }

  return React.createElement('footer', { className: 'statusbar' },
    React.createElement('div', { className: 'statusbar-section' },
      React.createElement('span', { className: dotClass }),
      React.createElement('span', null, connText),
    ),
    React.createElement('div', { className: 'statusbar-section' },
      React.createElement(Icon.Users, { size: 11 }),
      React.createElement('span', null, user.name),
    ),
    React.createElement('div', { className: 'statusbar-section' },
      React.createElement(Icon.Refresh, { size: 11 }),
      React.createElement('span', null, `Última sync: ${lastSync}`),
    ),
    pending > 0 && React.createElement('div', { className: 'statusbar-section', style: { color: 'var(--app-warning)' } },
      React.createElement('span', null, `${pending} alteração(ões) pendente(s)`),
    ),
    React.createElement('div', { className: 'statusbar-section right' },
      React.createElement('span', null, 'v0.4.2 · Windows'),
    ),
  );
}

// ============================================================
// Toast hook
// ============================================================
function useToasts() {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((message, opts = {}) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, message, type: opts.type || 'success' }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), opts.duration || 3200);
  }, []);
  const node = React.createElement('div', { className: 'toast-stack' },
    toasts.map((t) =>
      React.createElement('div', { key: t.id, className: `toast ${t.type === 'success' ? '' : t.type}` },
        t.type === 'success' ? React.createElement(Icon.Check, { size: 14 }) :
        t.type === 'error'   ? React.createElement(Icon.Alert, { size: 14 }) :
                               React.createElement(Icon.Info, { size: 14 }),
        React.createElement('span', null, t.message),
      ),
    ),
  );
  return { push, node };
}

// ============================================================
// Modal shell
// ============================================================
function Modal({ children, onClose }) {
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose && onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return React.createElement('div', { className: 'modal-backdrop', onClick: onClose },
    React.createElement('div', { className: 'modal', onClick: (e) => e.stopPropagation() }, children),
  );
}

// Confirm modal with diff
function ConfirmModal({ title, eyebrow, body, diff, onCancel, onConfirm, confirmLabel = 'Confirmar', danger }) {
  return React.createElement(Modal, { onClose: onCancel },
    React.createElement('div', { className: 'modal-head' },
      React.createElement('div', null,
        eyebrow && React.createElement('div', { className: 'modal-eyebrow' }, eyebrow),
        React.createElement('h2', null, title),
      ),
      React.createElement('button', { className: 'btn-ghost btn btn-icon', onClick: onCancel, 'aria-label': 'Fechar' },
        React.createElement(Icon.X, { size: 14 })),
    ),
    React.createElement('div', { className: 'modal-body' },
      body,
      diff && React.createElement('div', { className: 'diff', style: { marginTop: 12 } },
        React.createElement('div', { className: 'diff-row', style: { background: 'var(--app-bg)', fontWeight: 700, fontSize: 10.5, letterSpacing: '0.10em', textTransform: 'uppercase', color: 'var(--app-fg-subtle)' } },
          React.createElement('div', { className: 'diff-cell label' }, 'Propriedade'),
          React.createElement('div', { className: 'diff-cell', style: { borderRight: '1px solid var(--app-divider)' } }, 'Antes'),
          React.createElement('div', { className: 'diff-cell' }, 'Depois'),
        ),
        diff.map((row, i) =>
          React.createElement('div', { key: i, className: 'diff-row' },
            React.createElement('div', { className: 'diff-cell label' }, row.label),
            React.createElement('div', { className: 'diff-cell before' }, row.before),
            React.createElement('div', { className: 'diff-cell after' }, row.after),
          ),
        ),
      ),
    ),
    React.createElement('div', { className: 'modal-foot' },
      React.createElement('button', { className: 'btn btn-secondary', onClick: onCancel, autoFocus: true }, 'Cancelar', React.createElement(Kbd, null, 'Esc')),
      React.createElement('button', {
        className: `btn ${danger ? 'btn-danger' : 'btn-primary'}`,
        onClick: onConfirm,
      }, confirmLabel),
    ),
  );
}

// ============================================================
// Empty state
// ============================================================
function EmptyState({ eyebrow, title, message, action, tech }) {
  return React.createElement('div', { className: 'empty' },
    React.createElement('div', { className: 'empty-inner' },
      eyebrow && React.createElement('div', { className: 'empty-eyebrow' }, eyebrow),
      React.createElement('h3', null, title),
      React.createElement('p', null, message),
      action,
      tech && React.createElement('details', { style: { textAlign: 'left' } },
        React.createElement('summary', { style: { fontSize: 11, cursor: 'pointer', color: 'var(--app-fg-subtle)', letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 600 } }, 'Detalhe técnico'),
        React.createElement('div', { className: 'empty-tech' }, tech),
      ),
    ),
  );
}

window.Shared = {
  Chip, PersonChip, Kbd, WinChrome, Sidebar, StatusBar, useToasts,
  Modal, ConfirmModal, EmptyState,
  formatBRDate, formatBRDateTime, formatBRL, relativeTime, daysUntil,
};
