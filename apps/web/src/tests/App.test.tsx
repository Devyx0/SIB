import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../App';

vi.mock('../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: { session: { access_token: 'tok', user: { email: 'coordinator@sib.local' } } },
      }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
      signOut: vi.fn(),
    },
  },
}));

vi.mock('../hooks/useRequests', () => ({
  useRequests: () => ({ data: { total: 0, items: [] }, isPending: false, isError: false }),
}));

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    fetchSectors: () => Promise.resolve([]),
    fetchEmployees: () => Promise.resolve([]),
    fetchMe: () => Promise.resolve({ employee_id: 4, nom_employe: 'Test Coord', roles: ['coordinator'] }),
  };
});

function wrap(initialEntries: string[] = ['/board']) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('App routing', () => {
  it('renders dispatch board at /board', async () => {
    wrap(['/board']);
    await waitFor(() => expect(screen.getAllByText('Répartition').length).toBeGreaterThan(0));
  });

  it('redirects unknown path to /board', async () => {
    wrap(['/whatever']);
    await waitFor(() => expect(screen.getAllByText('Répartition').length).toBeGreaterThan(0));
  });
});
