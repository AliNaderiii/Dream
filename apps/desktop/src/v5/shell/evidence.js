/**
 * Evidence drawer — the Open-Science habit: every output can show the chain
 * that produced it (steps, inputs, code, timestamps). Slides in from the end
 * edge; nothing here is decoration — rows are supplied by callers.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';

export function evidenceDrawer() {
  const host = h('aside', { class: 'drawer', 'aria-hidden': 'true' });

  function close() {
    host.classList.remove('open');
    host.setAttribute('aria-hidden', 'true');
  }

  function open(payload) {
    const steps = payload?.steps ?? [];
    host.replaceChildren(
      h(
        'div',
        { class: 'drawer-head' },
        h(
          'div',
          { class: 'drawer-title' },
          h('span', { class: 'micro', text: 'EVIDENCE CHAIN' }),
          h('span', { class: 'drawer-name', text: payload?.title ?? 'زنجیره شواهد' }),
        ),
        h('button', {
          class: 'btn btn-ghost btn-sm',
          onclick: close,
          html: ic('x'),
          title: 'بستن',
        }),
      ),
      h(
        'div',
        { class: 'drawer-body' },
        steps.length === 0
          ? h(
              'div',
              { class: 'empty' },
              h('span', { html: ic('evidence') }),
              h('span', { class: 'empty-title', text: 'شواهدی ثبت نشده' }),
              h('span', {
                class: 'empty-note',
                text: 'هر خروجی واقعی، مراحل تولیدش را اینجا نشان می‌دهد.',
              }),
            )
          : h(
              'ol',
              { class: 'evidence-steps' },
              ...steps.map((step, i) =>
                h(
                  'li',
                  { class: 'evidence-step' },
                  h('span', { class: 'evidence-idx mono', text: String(i + 1).padStart(2, '0') }),
                  h(
                    'div',
                    { class: 'evidence-main' },
                    h('span', { class: 'evidence-name', text: step.name ?? 'مرحله' }),
                    step.detail ? h('span', { class: 'evidence-detail', text: step.detail }) : null,
                  ),
                  step.meta ? h('span', { class: 'evidence-meta mono', text: step.meta }) : null,
                ),
              ),
            ),
      ),
    );
    host.classList.add('open');
    host.setAttribute('aria-hidden', 'false');
  }

  host.addEventListener('click', (e) => {
    if (e.target === host) close();
  });

  return { el: host, open, close };
}
