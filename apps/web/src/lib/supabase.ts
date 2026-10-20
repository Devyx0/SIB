import { createClient } from '@supabase/supabase-js';

// Dev: same-origin so Vite can proxy /auth → local (or tunnel) Supabase.
// Prod: hit the real Supabase URL baked in at build time (VITE_SUPABASE_URL).
const url = import.meta.env.DEV
  ? window.location.origin
  : (import.meta.env.VITE_SUPABASE_URL as string);
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

export const supabase = createClient(url, anonKey);
