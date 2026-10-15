import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import type { Session } from '@supabase/supabase-js';
import { supabase } from './lib/supabase';
import AppShell from './components/AppShell';
import DispatchBoard from './pages/DispatchBoard';
import Login from './pages/Login';
import { fetchMe } from './api/client';
import type { MeResponse } from './api/schema.d.ts';
import type { Lang } from './i18n';

export default function App() {
  const [lang, setLang] = useState<Lang>('fr');
  // undefined = loading; null = no session; Session = authenticated
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [me, setMe] = useState<MeResponse | null>(null);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (!session) setMe(null);
    });
    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (session) {
      fetchMe().then(setMe).catch(() => {});
    }
  }, [session]);

  async function handleSignOut() {
    await supabase.auth.signOut();
  }

  if (session === undefined) return null; // loading

  return (
    <Routes>
      <Route
        path="/login"
        element={session ? <Navigate to="/board" replace /> : <Login />}
      />
      <Route
        path="/*"
        element={
          !session ? (
            <Navigate to="/login" replace />
          ) : (
            <AppShell
              lang={lang}
              onToggleLang={() => setLang((l) => (l === 'fr' ? 'en' : 'fr'))}
              me={me}
              onSignOut={handleSignOut}
            >
              <Routes>
                <Route path="board" element={<DispatchBoard lang={lang} />} />
                <Route path="*" element={<Navigate to="board" replace />} />
              </Routes>
            </AppShell>
          )
        }
      />
    </Routes>
  );
}
