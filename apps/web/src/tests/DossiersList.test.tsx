import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DossiersList from '../pages/Dossiers';
import { fetchDossiers } from '../api/client';
import type { DossierRow } from '../api/client';

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchDossiers: vi.fn(),
  fetchEmployees: vi.fn().mockResolvedValue([
    { employee_id: 24, nom_employe: 'Marc Tech', role: 'technician' },
    { employee_id: 4, nom_employe: 'Coordo', role: 'coordinator' },
  ]),
}));

const row: DossierRow = {
  request_id: 15927,
  last_en_route_at: '2026-10-18T14:00:00Z',
  last_closeout_at: '2026-10-18T15:42:00Z',
  unit_label: '4B',
  raw_title: 'Prise électrique cuisine',
  territoire: 'Centre-Sud',
  color_code: null,
  employee_name: 'Marc Tech',
  last_outcome: 'partial_expertise',
  photo_count: 3,
  visit_count: 1,
  closeout_urgent: true,
  status: 'triaged',
};

function wrap(initial = '/dossiers') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/dossiers" element={<DossiersList lang="fr" />} />
          <Route path="/dossiers/:id" element={<div data-testid="detail-page" />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(fetchDossiers).mockReset();
  vi.mocked(fetchDossiers).mockResolvedValue({ total: 1, items: [row] });
});

describe('DossiersList', () => {
  it('renders a row with unit, title, territory, who, outcome, elapsed, photos, urgent', async () => {
    wrap();
    await waitFor(() => expect(screen.getByText('Prise électrique cuisine')).toBeTruthy());
    expect(screen.getByText('4B')).toBeTruthy();
    expect(screen.getByText('Centre-Sud')).toBeTruthy();
    // also appears as a filter option once employees load, hence getAllByText
    expect(screen.getAllByText('Marc Tech').length).toBeGreaterThan(0);
    const table = within(screen.getByRole('table'));          // filter options reuse the labels
    expect(table.getByText(/partiellement/i)).toBeTruthy();   // French outcome label
    expect(table.getByText('1 h 42')).toBeTruthy();           // durationLabel
    expect(table.getByText('3')).toBeTruthy();                // photo count
    expect(table.getByText('Urgent')).toBeTruthy();           // badge
  });

  it('shows « En cours » for an open visit', async () => {
    vi.mocked(fetchDossiers).mockResolvedValue({
      total: 1,
      items: [{ ...row, last_closeout_at: null, last_outcome: null, closeout_urgent: null }],
    });
    wrap();
    await waitFor(() => expect(screen.getAllByText('En cours').length).toBeGreaterThan(0));
  });

  it('labels the employee filter « A fait une visite »', async () => {
    wrap();
    expect(screen.getByLabelText('A fait une visite')).toBeTruthy();
    // only field staff are offered (options render once employees load)
    await waitFor(() => expect(screen.getByRole('option', { name: 'Marc Tech' })).toBeTruthy());
    expect(screen.queryByRole('option', { name: 'Coordo' })).toBeNull();
  });

  it('puts filters in the URL and resets offset', async () => {
    wrap('/dossiers?offset=50');
    await waitFor(() => expect(screen.getByTestId('filter-outcome')).toBeTruthy());
    await userEvent.selectOptions(screen.getByTestId('filter-outcome'), 'failed');
    await waitFor(() => expect(vi.mocked(fetchDossiers)).toHaveBeenLastCalledWith(
      expect.objectContaining({ outcome: 'failed', offset: 0 }),
    ));
  });

  it('sends the date range only when both bounds are set', async () => {
    wrap('/dossiers?start_date=2026-10-01');
    await waitFor(() => expect(vi.mocked(fetchDossiers)).toHaveBeenCalled());
    expect(vi.mocked(fetchDossiers)).toHaveBeenLastCalledWith(
      expect.objectContaining({ start_date: undefined, end_date: undefined }),
    );
  });

  it('debounces the text search — no fetch per keystroke', async () => {
    wrap();
    await waitFor(() => expect(screen.getByTestId('filter-q')).toBeTruthy());
    await userEvent.type(screen.getByTestId('filter-q'), 'ab');
    await waitFor(() => expect(vi.mocked(fetchDossiers)).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: 'ab' }),
    ), { timeout: 2000 });
    const qCalls = vi.mocked(fetchDossiers).mock.calls.map(([p]) => p.q);
    expect(qCalls).not.toContain('a'); // intermediate keystroke never fetched
  });

  it('row click navigates to the detail page', async () => {
    wrap();
    await waitFor(() => screen.getByText('Prise électrique cuisine'));
    await userEvent.click(screen.getByText('Prise électrique cuisine'));
    expect(screen.getByTestId('detail-page')).toBeTruthy();
  });

  it('rows are keyboard-reachable — Enter opens the detail page', async () => {
    wrap();
    await waitFor(() => screen.getByText('Prise électrique cuisine'));
    const tr = screen.getByText('Prise électrique cuisine').closest('tr')!;
    tr.focus();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByTestId('detail-page')).toBeTruthy();
  });

  it('renders "0" for a dossier with no photos', async () => {
    vi.mocked(fetchDossiers).mockResolvedValue({
      total: 1, items: [{ ...row, photo_count: 0 }],
    });
    wrap();
    await waitFor(() => screen.getByText('Prise électrique cuisine'));
    const table = within(screen.getByRole('table'));
    expect(table.getByText('0')).toBeTruthy();
  });
});
