/**
 * Dream v5 — entry point.
 * Pure HTML/CSS/JS (ES modules). No framework, no echo layer, no fake data.
 */

import './styles/tokens.css';
import './styles/base.css';
import './styles/shell.css';
import './styles/views.css';

import { mountApp } from './shell/app.js';
import { mountWizard } from './wizard/first-run.js';
import { settings } from './lib/store.js';

const root = document.getElementById('root');
mountApp(root);

// First run: the wizard walks through model + honest core check.
if (!settings.get().onboarded) {
  mountWizard(root);
}
