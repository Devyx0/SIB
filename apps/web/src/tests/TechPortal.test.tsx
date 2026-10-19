import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../App';

vi.mock('../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: { session: { access_token: 'tok', user: { email: 'tech@sib.local' } } },
      }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
      signOut: vi.fn(),
    },
  },
}));

const mocks = vi.hoisted(() => ({
  fetchMe: vi.fn(),
  fetchRequests: vi.fn(),
  fetchRequest: vi.fn(),
}));

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    fetchMe: mocks.fetchMe,
    fetchRequests: mocks.fetchRequests,
    fetchRequest: mocks.fetchRequest,
    fetchSectors: () => Promise.resolve([]),
    fetchEmployees: () => Promise.resolve([]),
  };
});

const TECH = { employee_id: 24, nom_employe: 'Martin Poirier', roles: ['technician'] };
const CONTRACTOR = { employee_id: 20, nom_employe: 'Mahmoud Chachia', roles: ['contractor'] };
const COORD = { employee_id: 4, nom_employe: 'Test Coord', roles: ['coordinator'] };
const TECH_COORD = { employee_id: 7, nom_employe: 'Chef Tech', roles: ['technician', 'coordinator'] };

function row(id: number, status: string, extra: Record<string, unknown> = {}) {
  return {
    request_id: id,
    start_date: '2026-10-20',
    status,
    urgency_tier: null,
    raw_title: `Appel ${id}`,
    building_address: '123 rue Test',
    ...extra,
  };
}

const EMPTY_LIST = { total: 0, items: [], unscheduled_items: [] };

function wrap(initialEntries: string[] = ['/']) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  mocks.fetchMe.mockReset();
  mocks.fetchRequests.mockReset().mockResolvedValue(EMPTY_LIST);
  mocks.fetchRequest.mockReset();
});

describe('role routing', () => {
  it('technician lands on Mes appels, even from /board', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    wrap(['/board']);
    await waitFor(() => expect(screen.getByText(/Mes appels/)).toBeTruthy());
  });

  it('contractor lands on Mes appels', async () => {
    mocks.fetchMe.mockResolvedValue(CONTRACTOR);
    wrap(['/']);
    await waitFor(() => expect(screen.getByText(/Mes appels/)).toBeTruthy());
  });

  it('coordinator keeps the dispatch board', async () => {
    mocks.fetchMe.mockResolvedValue(COORD);
    wrap(['/board']);
    await waitFor(() => expect(screen.getAllByText('Répartition').length).toBeGreaterThan(0));
    expect(screen.queryByText(/Mes appels/)).toBeNull();
  });

  it('technician+coordinator keeps the dispatch board', async () => {
    mocks.fetchMe.mockResolvedValue(TECH_COORD);
    wrap(['/board']);
    await waitFor(() => expect(screen.getAllByText('Répartition').length).toBeGreaterThan(0));
  });
});

describe('Mes appels list', () => {
  it('fetches assigned-only, no date window, open statuses only', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    wrap(['/tech']);
    await waitFor(() =>
      expect(mocks.fetchRequests).toHaveBeenCalledWith(
        expect.objectContaining({ assigned_employee_id: 24 })
      )
    );
    const params = mocks.fetchRequests.mock.calls[0][0];
    expect(params.start_date).toBeUndefined();
    expect(params.end_date).toBeUndefined();
    expect(params.status).not.toContain('closed');
    expect(params.status).toContain('triaged');
    expect(params.status).toContain('en_route');
  });

  it('shows an old open call under « En retard » and never a closed one', async () => {
    const dayMs = 86400000;
    const toronto = (ms: number) =>
      new Date(ms).toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
    const tenDaysAgo = toronto(Date.now() - 10 * dayMs);
    const tomorrow = toronto(Date.now() + dayMs);

    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequests.mockResolvedValue({
      total: 3,
      items: [
        row(30, 'triaged', { start_date: tenDaysAgo }),
        row(31, 'closed', { start_date: tenDaysAgo }),
        row(32, 'triaged', { start_date: tomorrow }),
      ],
      unscheduled_items: [row(33, 'triaged', { start_date: null })],
    });
    wrap(['/tech']);
    await waitFor(() => expect(screen.getByText('En retard')).toBeTruthy());
    // The overdue call sits in the « En retard » section…
    const overdueSection = screen.getByText('En retard').nextElementSibling;
    expect(overdueSection?.textContent).toContain('Appel 30');
    // …the closed one is nowhere, the future one is under « À venir »,
    // the undated one under « Sans date ».
    expect(screen.queryByText('Appel 31')).toBeNull();
    expect(screen.getByText('À venir').nextElementSibling?.textContent).toContain('Appel 32');
    const sansDate = screen.getByRole('heading', { name: 'Sans date' });
    expect(sansDate.nextElementSibling?.textContent).toContain('Appel 33');
  });

  it('shows empty state when no assigned calls', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    wrap(['/tech']);
    await waitFor(() => expect(screen.getByText('Aucun appel assigné')).toBeTruthy());
  });

  it('pins the open en_route call with a banner', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequests.mockResolvedValue({
      total: 2,
      items: [row(10, 'triaged'), row(11, 'en_route')],
      unscheduled_items: [],
    });
    wrap(['/tech']);
    await waitFor(() => expect(screen.getByText(/Appel en cours/)).toBeTruthy());
    expect(screen.getByText('Appel 11')).toBeTruthy();
    expect(screen.getByText('Appel 10')).toBeTruthy();
  });
});

describe('call view', () => {
  it('shows tenant contact when the API returns it', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue({
      ...row(5, 'triaged'),
      problem_summary: 'Fuite sous évier',
      unit_label: '3',
      building_name: null,
      ft_link: 'https://example.com/ft',
      ft_name: 'Fiche 123',
      caller_name: 'Jean Locataire',
      caller_phone: '418-555-1234',
      caller_email: null,
      followup_log: [],
    });
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByText('Jean Locataire')).toBeTruthy());
    const tel = screen.getByText('418-555-1234');
    expect(tel.getAttribute('href')).toBe('tel:418-555-1234');
    expect(screen.getByText('Fuite sous évier')).toBeTruthy();
    expect(screen.getByText('Fiche 123').getAttribute('href')).toBe('https://example.com/ft');
  });

  it('hides tenant contact when the API nulls it (case-scoped rule)', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue({
      ...row(6, 'triaged'),
      problem_summary: null,
      unit_label: null,
      building_name: null,
      ft_link: null,
      ft_name: null,
      caller_name: null,
      caller_phone: null,
      caller_email: null,
      followup_log: [],
    });
    wrap(['/tech/appels/6']);
    await waitFor(() => expect(screen.getByText('Contact locataire')).toBeTruthy());
    expect(screen.queryByText(/tel:/)).toBeNull();
    expect(screen.queryByText('Jean Locataire')).toBeNull();
  });

  it('shows not-found state on 404', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    const { ApiError } = await import('../api/client');
    mocks.fetchRequest.mockRejectedValue(new ApiError('NOT_FOUND', 'Request 999 not found'));
    wrap(['/tech/appels/999']);
    await waitFor(() => expect(screen.getByText('Appel introuvable')).toBeTruthy());
  });
});
