/**
 * Inline SVG icon set — 24×24, 1.6 stroke, round caps. No icon library.
 * Every icon returns an SVG string; use with the `ic` class.
 */

const wrap = (paths, opts = '') =>
  `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${opts}>${paths}</svg>`;

export const icons = {
  logo: wrap(
    '<path d="M4 5h16v14H4z"/><path d="M4 5l16 14" opacity="0"/><path d="M9 5v14" opacity="0.55"/><path d="M4 10h5" opacity="0"/><circle cx="15.5" cy="12" r="3.2"/>',
  ),
  chat: wrap('<path d="M21 12a8 8 0 0 1-8 8H5l-2 2V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z"/>'),
  doc: wrap(
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h4"/>',
  ),
  chart: wrap('<path d="M4 20h16"/><path d="M7 20v-6"/><path d="M12 20V9"/><path d="M17 20V4"/>'),
  wave: wrap('<path d="M3 12h3l2-6 3 12 3-9 2 3h5"/>'),
  settings: wrap(
    '<path d="M4 7h10"/><circle cx="18" cy="7" r="2.2"/><path d="M4 17h6"/><circle cx="14" cy="17" r="2.2"/><path d="M20 17h0"/><path d="M14 7h6"/>',
  ),
  sun: wrap(
    '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M4.9 4.9l1.4 1.4"/><path d="M17.7 17.7l1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="M4.9 19.1l1.4-1.4"/><path d="M17.7 6.3l1.4-1.4"/>',
  ),
  moon: wrap('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
  send: wrap('<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>'),
  plus: wrap('<path d="M12 5v14"/><path d="M5 12h14"/>'),
  evidence: wrap(
    '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  ),
  upload: wrap(
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>',
  ),
  file: wrap(
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  ),
  check: wrap('<path d="M20 6L9 17l-5-5"/>'),
  x: wrap('<path d="M18 6L6 18"/><path d="M6 6l12 12"/>'),
  alert: wrap(
    '<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  ),
  refresh: wrap(
    '<path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.5 9a9 9 0 0 1 14.9-3.4L23 10"/><path d="M1 14l4.6 4.4A9 9 0 0 0 20.5 15"/>',
  ),
  bot: wrap(
    '<rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 8V4"/><circle cx="12" cy="3" r="1"/><path d="M9 13v2"/><path d="M15 13v2"/>',
  ),
  user: wrap('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>'),
  arrow: wrap('<path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>'),
  mic: wrap(
    '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><path d="M12 19v3"/>',
  ),
  db: wrap(
    '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  ),
  search: wrap('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>'),
  minus: wrap('<path d="M5 12h14"/>'),
  square: wrap('<rect x="5" y="5" width="14" height="14" rx="1.5"/>'),
  speaker: wrap(
    '<path d="M11 5L6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/>',
  ),
  play: wrap('<path d="M7 4l13 8-13 8z"/>'),
};

/** Shorthand: icon by name as a safe HTML string. */
export function ic(name) {
  return icons[name] ?? '';
}
