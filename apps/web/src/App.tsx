import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './components/AppShell';
import DispatchBoard from './pages/DispatchBoard';
import { useEmployee } from './hooks/useEmployee';
import type { Lang } from './i18n';

export default function App() {
  const [lang, setLang] = useState<Lang>('fr');
  const { employeeId, setEmployee } = useEmployee();

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return (
    <AppShell
      lang={lang}
      onToggleLang={() => setLang((l) => (l === 'fr' ? 'en' : 'fr'))}
      employeeId={employeeId}
      onSetEmployee={setEmployee}
    >
      <Routes>
        <Route
          path="/board"
          element={<DispatchBoard lang={lang} employeeId={employeeId} />}
        />
        <Route path="*" element={<Navigate to="/board" replace />} />
      </Routes>
    </AppShell>
  );
}
