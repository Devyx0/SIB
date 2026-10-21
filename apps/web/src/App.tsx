import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import type { Session } from '@supabase/supabase-js';
import { supabase } from './lib/supabase';
import AppShell from './components/AppShell';
import DispatchBoard from './pages/DispatchBoard';
import TaskCalendar from './pages/TaskCalendar';
import Dashboard from './pages/Dashboard';
import Utilization from './pages/Utilization';
import Portfolio from './pages/Portfolio';
import TechList from './pages/TechPortal';
import TechCallView from './pages/TechPortal/CallView';
import CloseoutForm from './pages/TechPortal/CloseoutForm';
import Login from './pages/Login';
import SurveyPage from './pages/Survey';
import PublicDemande from './pages/PublicDemande';
import ReceptionistIntake from './pages/ReceptionistIntake';
import { JustificationProvider } from './components/Justification';
import { fetchMe } from './api/client';
import type { MeResponse } from './api/schema.d.ts';
import type { Lang } from './i18n';

function homePath(me: MeResponse | null): string {
  if (!me) return '/triage';
  const elevated = me.roles.some((r) => r === 'coordinator' || r === 'director');
  if (me.roles.includes('receptionist') && !elevated) return '/intake';
  if (
    me.roles.some((r) => r === 'technician' || r === 'contractor')
    && !elevated
  ) {
    return '/tech';
  }
  return '/triage';
}

export default function App() {
  const [lang, setLang] = useState<Lang>('fr');
  // undefined = loading; null = no session; Session = authenticated
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [me, setMe] = useState<MeResponse | null>(null);
  const toggleLang = () => setLang((l) => (l === 'fr' ? 'en' : 'fr'));

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

  const intakeOnly =
    me != null &&
    me.roles.includes('receptionist') &&
    !me.roles.some((r) => r === 'coordinator' || r === 'director');

  return (
    <JustificationProvider lang={lang}>
      <Routes>
        <Route path="/sondage/:token" element={<SurveyPage lang={lang} />} />
        <Route
          path="/public/demande"
          element={<PublicDemande lang={lang} onToggleLang={toggleLang} />}
        />
        <Route
          path="/login"
          element={session ? <Navigate to={homePath(me)} replace /> : <Login />}
        />
        <Route
          path="/*"
          element={
            !session ? (
              <Navigate to="/login" replace />
            ) : techOnly ? (
              <Routes>
                <Route path="tech" element={<TechList lang={lang} me={me} onSignOut={handleSignOut} onToggleLang={toggleLang} />} />
                <Route path="tech/appels/:id" element={<TechCallView lang={lang} me={me} onSignOut={handleSignOut} onToggleLang={toggleLang} />} />
                <Route path="tech/appels/:id/cloture" element={<CloseoutForm lang={lang} me={me} onSignOut={handleSignOut} onToggleLang={toggleLang} />} />
                <Route path="*" element={<Navigate to="/tech" replace />} />
              </Routes>
            ) : intakeOnly ? (
              <AppShell
                lang={lang}
                onToggleLang={toggleLang}
                me={me}
                onSignOut={handleSignOut}
              >
                <Routes>
                  <Route path="intake" element={<ReceptionistIntake lang={lang} />} />
                  <Route path="*" element={<Navigate to="/intake" replace />} />
                </Routes>
              </AppShell>
            ) : (
              <AppShell
                lang={lang}
                onToggleLang={toggleLang}
                me={me}
                onSignOut={handleSignOut}
              >
                <Routes>
                  <Route path="triage" element={<DispatchBoard lang={lang} me={me} mode="triage" />} />
                  <Route path="tasks/calendar" element={<TaskCalendar lang={lang} />} />
                  <Route path="tasks" element={<DispatchBoard lang={lang} me={me} mode="tasks" />} />
                  <Route path="board" element={<Navigate to="/triage" replace />} />
                  <Route path="tableau-de-bord" element={<Dashboard lang={lang} />} />
                  <Route path="utilisation" element={<Utilization lang={lang} />} />
                  <Route path="portfolio/*" element={<Portfolio lang={lang} />} />
                  <Route path="*" element={<Navigate to="/triage" replace />} />
                </Routes>
              </AppShell>
            )
          }
        />
      </Routes>
    </JustificationProvider>
  );
}
