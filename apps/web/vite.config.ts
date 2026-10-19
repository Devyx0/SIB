import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: [
      '.ngrok-free.dev', '.ngrok-free.app', '.ngrok.io', '.ngrok.app',
      '.trycloudflare.com',
    ],
    // Same-origin proxy so a public tunnel (ngrok) can reach API + local Supabase auth.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/auth': { target: 'http://127.0.0.1:54321', changeOrigin: true },
      '/storage': { target: 'http://127.0.0.1:54321', changeOrigin: true },
      '/rest': { target: 'http://127.0.0.1:54321', changeOrigin: true },
      '/realtime': { target: 'http://127.0.0.1:54321', changeOrigin: true, ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/tests/setup.ts',
    globals: true,
  },
});
