import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import type { Session } from '@supabase/supabase-js';
import { supabase } from './lib/supabase';
import AppShell from './components/AppShell';
import DispatchBoard from './pages/DispatchBoard';
import DossiersList from './pages/Dossiers';
import DossierDetail from './pages/Dossiers/DossierDetail';
import TechList from './pages/TechPortal';
import TechCallView from './pages/TechPortal/CallView';
import CloseoutForm from './pages/TechPortal/CloseoutForm';
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
      // Role-less fallback on failure → coordinator branch (same as before).
      fetchMe().then(setMe).catch(() => setMe({ employee_id: 0, nom_employe: '', roles: [] }));
    }
  }, [session]);

  async function handleSignOut() {
    await supabase.auth.signOut();
  }

  if (session === undefined) return null; // loading
  // Wait for roles before mounting routes: the catch-all Navigate would
  // otherwise rewrite deep links (e.g. /tech/appels/5) before `me` arrives.
  if (session && me === null) return null;

  // Technician/contractor WITHOUT coordinator/director → mobile portal.
  const techOnly =
    me != null &&
    me.roles.some((r) => r === 'technician' || r === 'contractor') &&
    !me.roles.some((r) => r === 'coordinator' || r === 'director');

  return (
    <Routes>
      <Route
        path="/login"
        element={session ? <Navigate to={techOnly ? '/tech' : '/board'} replace /> : <Login />}
      />
      <Route
        path="/*"
        element={
          !session ? (
            <Navigate to="/login" replace />
          ) : techOnly ? (
            <Routes>
              <Route path="tech" element={<TechList lang={lang} me={me} onSignOut={handleSignOut} />} />
              <Route path="tech/appels/:id" element={<TechCallView lang={lang} me={me} onSignOut={handleSignOut} />} />
              <Route path="tech/appels/:id/cloture" element={<CloseoutForm lang={lang} me={me} onSignOut={handleSignOut} />} />
              <Route path="*" element={<Navigate to="/tech" replace />} />
            </Routes>
          ) : (
            <AppShell
              lang={lang}
              onToggleLang={() => setLang((l) => (l === 'fr' ? 'en' : 'fr'))}
              me={me}
              onSignOut={handleSignOut}
            >
              <Routes>
                <Route path="board" element={<DispatchBoard lang={lang} me={me} />} />
                <Route path="dossiers" element={<DossiersList lang={lang} />} />
                <Route path="dossiers/:id" element={<DossierDetail lang={lang} />} />
                <Route path="*" element={<Navigate to="board" replace />} />
              </Routes>
            </AppShell>
          )
        }
      />
    </Routes>
  );
}
