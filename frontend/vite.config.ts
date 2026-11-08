import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { copyFileSync, existsSync } from 'node:fs';

export default defineConfig(({ mode }) => {
  const web = mode === 'cloudflare';
  const input: Record<string, string> = web ? { watch: resolve(__dirname, 'watch.html') } : { index: resolve(__dirname, 'index.html'), watch: resolve(__dirname, 'watch.html') };
  return {
    define: { __XENNEX_BUILD__: JSON.stringify(`${web ? 'web' : 'app'}-${new Date().toISOString()}`) },
    plugins: [react(), {
      name: 'cloudflare-entry',
      closeBundle() {
        if (web && existsSync('../cloudflare_pages/dist/watch.html')) copyFileSync('../cloudflare_pages/dist/watch.html', '../cloudflare_pages/dist/index.html');
      },
    }],
    build: {
      outDir: web ? '../cloudflare_pages/dist' : '../wwwroot',
      emptyOutDir: web,
      rollupOptions: {
        input,
        output: { entryFileNames: 'assets/index-[hash].js', assetFileNames: 'assets/index-[hash][extname]' },
      },
    },
  };
});
