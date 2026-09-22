import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import globals from 'globals';

// v5 is framework-free ES modules. Type-aware linting of TypeScript config
// files is covered by `tsc --noEmit` (see tsconfig.json includes).
export default [
  {
    ignores: ['dist', 'src-tauri', 'node_modules', 'coverage', 'vite.config.ts'],
  },
  js.configs.recommended,
  {
    files: ['src/v5/**/*.js', 'scripts/**/*.mjs', 'eslint.config.js'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
    },
  },
  prettier,
];
