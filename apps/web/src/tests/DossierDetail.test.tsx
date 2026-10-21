import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DossierDetail from '../pages/Dossiers/DossierDetail';
import { fetchRequest, fetchPhotoUrl } from '../api/client';
import type { RequestDetail } from '../api/schema.d.ts';

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchRequest: vi.fn(),
  fetchPhotoUrl: vi.fn().mockResolvedValue({ url: 'https://signed.local/p.jpg' }),
}));

const detail = {
  request_id: 15927,
  raw_title: 'Prise électrique cuisine',
  status: 'closed',
  start_date: '2026-10-18',
  building_address: '123 rue Principale',
  territoire: 'Centre-Sud',
  unit_label: '4B',
  assigned_employee_name: 'Marc Tech',
  closeout_outcome: 'complete',
  work_performed: 'Remplacement de la prise.',
  visits: [{
    visit_id: 7, employee_id: 24, employee_name: 'Marc Tech',
    en_route_at: '2026-10-18T14:00:00Z', closeout_at: '2026-10-18T15:42:00Z',
    outcome: 'complete', closeout_comment: 'Travail effectué.', photo_ids: [41],
  }],
  followup_log: [{ followup_id: 1, entry_date: '2026-10-18', entered_by_initials: 'MT',
                   entry_text: 'Travail effectué.' }],
  justification_log: [{ id: 9, decision_type: 'assign', before_value: null, after_value: null,
                        justification_text: 'Assigné après triage.', input_method: 'typed',
                        created_at: '2026-10-17T12:00:00Z', employee_id: 4 }],
} as unknown as RequestDetail;

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/dossiers/15927']}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/dossiers/:id" element={<DossierDetail lang="fr" />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(fetchRequest).mockReset();
  vi.mocked(fetchRequest).mockResolvedValue(detail);
});

describe('DossierDetail', () => {
  it('renders summary, visit with times/elapsed/comment, photo, logs', async () => {
    wrap();
    await waitFor(() => expect(screen.getByText('Prise électrique cuisine')).toBeTruthy());
    expect(screen.getByText('123 rue Principale')).toBeTruthy();
    expect(screen.getByTestId('history-timeline')).toBeTruthy();
    expect(screen.getByText(/1 h 42/)).toBeTruthy();
    expect(screen.getAllByText(/Travail effectué/).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByTestId('visit-photo')).toBeTruthy());
    expect(vi.mocked(fetchPhotoUrl)).toHaveBeenCalledWith(15927, 41);
    expect(screen.getByTestId('history-filter-decision')).toBeTruthy();
    expect(screen.getByText('Assigné après triage.')).toBeTruthy();
  });

  it('shows the error branch with a back link for a non-numeric id', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={['/dossiers/abc']}>
        <QueryClientProvider client={qc}>
          <Routes>
            <Route path="/dossiers/:id" element={<DossierDetail lang="fr" />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    expect(screen.getByText('Erreur de chargement')).toBeTruthy();
    expect(screen.getByText(/Dossiers/)).toBeTruthy(); // back link present
    expect(vi.mocked(fetchRequest)).not.toHaveBeenCalled();
  });

  it('has no write controls', async () => {
    wrap();
    await waitFor(() => screen.getByText('Prise électrique cuisine'));
    // Read-only page: no form fields; the only buttons filter the history.
    expect(document.querySelectorAll('input, select, textarea')).toHaveLength(0);
    const timeline = screen.getByTestId('history-timeline');
    document.querySelectorAll('button').forEach((b) => expect(timeline.contains(b)).toBe(true));
  });
});
