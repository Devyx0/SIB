import { createClient } from '@supabase/supabase-js';

// Same origin as the page so login works through Vite's /auth proxy
// (local dev and a public tunnel). VITE_SUPABASE_URL is only a fallback
// for non-browser contexts.
const url =
  typeof window !== 'undefined' && window.location?.origin
    ? window.location.origin
    : (import.meta.env.VITE_SUPABASE_URL as string);
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

export const supabase = createClient(url, anonKey);
