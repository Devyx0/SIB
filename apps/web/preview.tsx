// Throwaway harness: every API call fails; only the dev demo call renders. Delete after review.
import '@fontsource/work-sans/400.css';
import '@fontsource/work-sans/500.css';
import '@fontsource/work-sans/600.css';
import '../src/globals.css';
import ReactDOM from 'react-dom/client';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AppShell from '../src/components/AppShell';
import DispatchBoard from '../src/pages/DispatchBoard';
import { JustificationProvider } from '../src/components/Justification';

window.fetch = async () => new Response('{}', { status: 503, headers: { 'Content-Type': 'application/json' } });
const me = { employee_id: 9, nom_employe: 'Julie Bélanger', roles: ['coordinator'] };
const noop = () => {};
ReactDOM.createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <JustificationProvider lang="fr">
      <MemoryRouter initialEntries={['/triage?demo=1']}>
        <Routes>
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
          <Route path="/triage" element={<AppShell lang="fr" onToggleLang={noop} me={me as any} onSignOut={noop}><DispatchBoard lang="fr" me={me as any} mode="triage" /></AppShell>} />
        </Routes>
      </MemoryRouter>
    </JustificationProvider>
  </QueryClientProvider>
);
