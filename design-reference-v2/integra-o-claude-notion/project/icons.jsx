/* global React */
// Inline icon set — institutional, 1.5px stroke, 16px default.
const { createElement: h } = React;

const iconBase = (paths, size = 16, extra = {}) => h('svg', {
  width: size, height: size, viewBox: '0 0 24 24',
  fill: 'none', stroke: 'currentColor', strokeWidth: 1.5,
  strokeLinecap: 'round', strokeLinejoin: 'round',
  'aria-hidden': true,
  ...extra,
}, paths);

const Icon = {
  Dashboard: (p = {}) => iconBase([
    h('rect', { key: 1, x: 3, y: 3, width: 7, height: 9 }),
    h('rect', { key: 2, x: 14, y: 3, width: 7, height: 5 }),
    h('rect', { key: 3, x: 14, y: 12, width: 7, height: 9 }),
    h('rect', { key: 4, x: 3, y: 16, width: 7, height: 5 }),
  ], p.size, p),
  Folder: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z' }),
  ], p.size, p),
  Users: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2' }),
    h('circle', { key: 2, cx: 9, cy: 7, r: 4 }),
    h('path', { key: 3, d: 'M22 21v-2a4 4 0 0 0-3-3.87' }),
    h('path', { key: 4, d: 'M16 3.13a4 4 0 0 1 0 7.75' }),
  ], p.size, p),
  Check: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M5 12l5 5L20 7' }),
  ], p.size, p),
  CheckSquare: (p = {}) => iconBase([
    h('rect', { key: 1, x: 3, y: 3, width: 18, height: 18, rx: 2 }),
    h('path', { key: 2, d: 'M8 12l3 3 5-6' }),
  ], p.size, p),
  Book: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14Z' }),
    h('path', { key: 2, d: 'M4 19.5V21h16' }),
  ], p.size, p),
  Upload: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4' }),
    h('path', { key: 2, d: 'M17 8l-5-5-5 5' }),
    h('path', { key: 3, d: 'M12 3v12' }),
  ], p.size, p),
  Activity: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M22 12h-4l-3 9L9 3l-3 9H2' }),
  ], p.size, p),
  Settings: (p = {}) => iconBase([
    h('circle', { key: 1, cx: 12, cy: 12, r: 3 }),
    h('path', { key: 2, d: 'M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z' }),
  ], p.size, p),
  Search: (p = {}) => iconBase([
    h('circle', { key: 1, cx: 11, cy: 11, r: 7 }),
    h('path', { key: 2, d: 'm21 21-4.3-4.3' }),
  ], p.size, p),
  Plus: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M12 5v14M5 12h14' }),
  ], p.size, p),
  Filter: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M22 3H2l8 9.46V19l4 2v-8.54L22 3Z' }),
  ], p.size, p),
  Download: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4' }),
    h('path', { key: 2, d: 'M7 10l5 5 5-5' }),
    h('path', { key: 3, d: 'M12 15V3' }),
  ], p.size, p),
  Refresh: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M3 12a9 9 0 0 1 15-6.7L21 8' }),
    h('path', { key: 2, d: 'M21 3v5h-5' }),
    h('path', { key: 3, d: 'M21 12a9 9 0 0 1-15 6.7L3 16' }),
    h('path', { key: 4, d: 'M3 21v-5h5' }),
  ], p.size, p),
  X: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M18 6 6 18M6 6l12 12' }),
  ], p.size, p),
  ChevronDown: (p = {}) => iconBase([
    h('path', { key: 1, d: 'm6 9 6 6 6-6' }),
  ], p.size, p),
  ChevronUp: (p = {}) => iconBase([
    h('path', { key: 1, d: 'm18 15-6-6-6 6' }),
  ], p.size, p),
  ChevronRight: (p = {}) => iconBase([
    h('path', { key: 1, d: 'm9 18 6-6-6-6' }),
  ], p.size, p),
  Alert: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z' }),
    h('path', { key: 2, d: 'M12 9v4' }),
    h('path', { key: 3, d: 'M12 17h.01' }),
  ], p.size, p),
  Info: (p = {}) => iconBase([
    h('circle', { key: 1, cx: 12, cy: 12, r: 9 }),
    h('path', { key: 2, d: 'M12 8h.01' }),
    h('path', { key: 3, d: 'M11 12h1v4h1' }),
  ], p.size, p),
  WifiOff: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M1 1l22 22' }),
    h('path', { key: 2, d: 'M16.72 11.06A10.94 10.94 0 0 1 19 12.55' }),
    h('path', { key: 3, d: 'M5 12.55a10.94 10.94 0 0 1 5.17-2.39' }),
    h('path', { key: 4, d: 'M10.71 5.05A16 16 0 0 1 22.58 9' }),
    h('path', { key: 5, d: 'M1.42 9a15.91 15.91 0 0 1 4.7-2.88' }),
    h('path', { key: 6, d: 'M8.53 16.11a6 6 0 0 1 6.95 0' }),
    h('path', { key: 7, d: 'M12 20h.01' }),
  ], p.size, p),
  Eye: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z' }),
    h('circle', { key: 2, cx: 12, cy: 12, r: 3 }),
  ], p.size, p),
  EyeOff: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M9.88 9.88a3 3 0 1 0 4.24 4.24' }),
    h('path', { key: 2, d: 'M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68' }),
    h('path', { key: 3, d: 'M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61' }),
    h('path', { key: 4, d: 'M2 2l20 20' }),
  ], p.size, p),
  Trash: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M3 6h18' }),
    h('path', { key: 2, d: 'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6' }),
    h('path', { key: 3, d: 'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2' }),
  ], p.size, p),
  PanelRight: (p = {}) => iconBase([
    h('rect', { key: 1, x: 3, y: 3, width: 18, height: 18, rx: 2 }),
    h('path', { key: 2, d: 'M15 3v18' }),
  ], p.size, p),
  Edit: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7' }),
    h('path', { key: 2, d: 'M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5Z' }),
  ], p.size, p),
  Calendar: (p = {}) => iconBase([
    h('rect', { key: 1, x: 3, y: 4, width: 18, height: 18, rx: 2 }),
    h('path', { key: 2, d: 'M16 2v4' }),
    h('path', { key: 3, d: 'M8 2v4' }),
    h('path', { key: 4, d: 'M3 10h18' }),
  ], p.size, p),
  Clock: (p = {}) => iconBase([
    h('circle', { key: 1, cx: 12, cy: 12, r: 9 }),
    h('path', { key: 2, d: 'M12 7v5l3 2' }),
  ], p.size, p),
  Sun: (p = {}) => iconBase([
    h('circle', { key: 1, cx: 12, cy: 12, r: 4 }),
    h('path', { key: 2, d: 'M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41' }),
  ], p.size, p),
  Moon: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z' }),
  ], p.size, p),
  Undo: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M3 7v6h6' }),
    h('path', { key: 2, d: 'M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6.7 3L3 13' }),
  ], p.size, p),
  More: (p = {}) => iconBase([
    h('circle', { key: 1, cx: 12, cy: 12, r: 1 }),
    h('circle', { key: 2, cx: 19, cy: 12, r: 1 }),
    h('circle', { key: 3, cx: 5, cy: 12, r: 1 }),
  ], p.size, p),
  Logout: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4' }),
    h('path', { key: 2, d: 'm16 17 5-5-5-5' }),
    h('path', { key: 3, d: 'M21 12H9' }),
  ], p.size, p),
  Help: (p = {}) => iconBase([
    h('circle', { key: 1, cx: 12, cy: 12, r: 9 }),
    h('path', { key: 2, d: 'M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3' }),
    h('path', { key: 3, d: 'M12 17h.01' }),
  ], p.size, p),
  File: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z' }),
    h('path', { key: 2, d: 'M14 2v6h6' }),
  ], p.size, p),
  Wifi: (p = {}) => iconBase([
    h('path', { key: 1, d: 'M5 12.55a11 11 0 0 1 14.08 0' }),
    h('path', { key: 2, d: 'M1.42 9a16 16 0 0 1 21.16 0' }),
    h('path', { key: 3, d: 'M8.53 16.11a6 6 0 0 1 6.95 0' }),
    h('path', { key: 4, d: 'M12 20h.01' }),
  ], p.size, p),
};

window.Icon = Icon;
