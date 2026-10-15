import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../App';

vi.mock('../hooks/useRequests', () => ({
  useRequests: () => ({ data: { total: 0, items: [] }, isPending: false, isError: false }),
}));
vi.mock('../hooks/useEmployee', () => ({
  useEmployee: () => ({ employeeId: null, setEmployee: vi.fn() }),
}));
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    fetchSectors: () => Promise.resolve([]),
    fetchEmployees: () => Promise.resolve([]),
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
  it('renders dispatch board at /board', () => {
    wrap(['/board']);
    expect(screen.getAllByText('Répartition').length).toBeGreaterThan(0);
  });

  it('redirects unknown path to /board', () => {
    wrap(['/whatever']);
    expect(screen.getAllByText('Répartition').length).toBeGreaterThan(0);
  });
});
