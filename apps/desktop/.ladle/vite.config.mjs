import path from 'node:path';

import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// Ladle has its own tooling graph (axe, controls, story runtime). Reusing the
// Tauri app's manual vendor chunks creates artificial circular story chunks.
export default defineConfig({
  plugins: [tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, '../src') },
  },
});
