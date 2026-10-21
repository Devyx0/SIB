import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  // Proxy Supabase paths to whichever project VITE_SUPABASE_URL names
  // (local `supabase start` by default, or a hosted project).
  const env = loadEnv(mode, process.cwd(), '');
  const supabaseUrl = env.VITE_SUPABASE_URL || 'http://127.0.0.1:54321';
  const frameAncestors = (env.VITE_PUBLIC_INTAKE_FRAME_ANCESTORS || '').trim();
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
      configureServer(server) {
        if (!frameAncestors) return;
        server.middlewares.use((_req, res, next) => {
          res.setHeader(
            'Content-Security-Policy',
            `frame-ancestors 'self' ${frameAncestors}`,
          );
          next();
        });
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/tests/setup.ts',
      globals: true,
    },
  };
});
