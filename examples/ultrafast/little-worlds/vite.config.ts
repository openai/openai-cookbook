import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  worker: { format: 'es' },
  server: { host: '127.0.0.1', port: 5173, strictPort: true, watch: { usePolling: true, interval: 400 }, proxy: { '/api': { target: 'http://127.0.0.1:4318', changeOrigin: false } } },
});
