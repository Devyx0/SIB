import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DispatchBoard from '../pages/DispatchBoard';

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchRequests: vi.fn().mockResolvedValue({ total: 0, items: [], unscheduled_items: [] }),
  fetchSectors: vi.fn().mockResolvedValue([]),
  fetchEmployees: vi.fn().mockResolvedValue([]),
  fetchBuildings: vi.fn().mockResolvedValue([]),
}));

const me = { employee_id: 4, nom_employe: 'Coordo', roles: ['coordinator'] };

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname + loc.search}</div>;
}

function wrap(initial: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <QueryClientProvider client={qc}>
        <DispatchBoard lang="fr" me={me} />
        <LocationProbe />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('DispatchBoard ?nouvel-appel=1', () => {
  it('opens the modal when the param is present', async () => {
    wrap('/board?nouvel-appel=1');
    await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
  });

  it('closing the modal strips the param so a refresh does not reopen it', async () => {
    wrap('/board?nouvel-appel=1');
    await waitFor(() => screen.getByRole('dialog'));
    await userEvent.click(screen.getByRole('button', { name: 'Annuler' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByTestId('location').textContent).toBe('/board');
  });

  it('does not open the modal without the param', async () => {
    wrap('/board');
    await waitFor(() => expect(screen.getByTestId('location')).toBeTruthy());
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
