import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

// Same as the production nginx: a glyph range we did not ship is an empty file, not the app's index.html
const emptyMissingGlyphs = {
  name: 'empty-missing-glyphs',
  configureServer(server: { middlewares: { use: (fn: (req: { url?: string }, res: { setHeader: (k: string, v: string) => void; end: (b: string) => void }, next: () => void) => void) => void } }) {
    server.middlewares.use((req, res, next) => {
      const path = decodeURIComponent((req.url ?? '').split('?')[0]);
      if (path.startsWith('/map/fonts/') && path.endsWith('.pbf') && !existsSync(join(process.cwd(), 'public', path))) {
        res.setHeader('Content-Type', 'application/x-protobuf');
        res.end('');
        return;
      }
      next();
    });
  },
};

export default defineConfig({
  plugins: [react(), emptyMissingGlyphs],
  server: {
    port: Number(process.env.PORT) || 3000,
    strictPort: false,
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
