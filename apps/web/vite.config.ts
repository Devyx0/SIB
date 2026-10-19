import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  // Proxy Supabase paths to whichever project VITE_SUPABASE_URL names
  // (local `supabase start` by default, or a hosted project).
  const supabaseUrl =
    loadEnv(mode, process.cwd(), '').VITE_SUPABASE_URL || 'http://127.0.0.1:54321';
  return {
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
        '/auth': { target: supabaseUrl, changeOrigin: true },
        '/storage': { target: supabaseUrl, changeOrigin: true },
        '/rest': { target: supabaseUrl, changeOrigin: true },
        '/realtime': { target: supabaseUrl, changeOrigin: true, ws: true },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/tests/setup.ts',
      globals: true,
    },
  };
});
