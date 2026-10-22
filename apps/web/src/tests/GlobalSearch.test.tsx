import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import GlobalSearch from '../components/GlobalSearch';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    fetchRequests: vi.fn().mockResolvedValue({
      total: 1, unscheduled_items: [],
      items: [{ request_id: 7, raw_title: 'Fuite cuisine', asnu: 'A-7', building_address: '12 rue X', start_date: '2026-10-01' }],
    }),
    searchPortfolio: vi.fn().mockResolvedValue({
      facts: [], tenants: [], projects: [],
      units: [{ unit_id: 3, numero_appartement: '4B', building_adresse: '12 rue X', tenant_names: ['J. Tremblay'], grandeur: '4 ½' }],
      buildings: [],
    }),
  };
});

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{loc.pathname}{loc.search}</p>;
}

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><GlobalSearch lang="fr" /><Where /></MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openPalette() {
  await userEvent.click(screen.getByTestId('global-search-trigger'));
  return screen.getByTestId('global-search');
}

describe('GlobalSearch palette', () => {
  it('opens from the sidebar field and lists service calls and portfolio hits', async () => {
    setup();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await userEvent.type(await openPalette(), 'fuite');
    expect(await screen.findByText('Fuite cuisine')).toBeInTheDocument();
    expect(screen.getByText('Appels de service')).toBeInTheDocument();
    expect(screen.getByText('Logements')).toBeInTheDocument();
  });

  it('opens with Ctrl+K and closes with Escape', async () => {
    setup();
    await userEvent.keyboard('{Control>}k{/Control}');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens the highlighted result on Enter and closes the palette', async () => {
    setup();
    await userEvent.type(await openPalette(), 'fuite');
    await screen.findByText('Fuite cuisine');
    await userEvent.keyboard('{Enter}');
    expect(screen.getByTestId('where')).toHaveTextContent('/triage?request_id=7');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('moves through results with the arrow keys', async () => {
    setup();
    await userEvent.type(await openPalette(), 'fuite');
    await screen.findByText('Fuite cuisine');
    await userEvent.keyboard('{ArrowDown}{Enter}');
    expect(screen.getByTestId('where')).toHaveTextContent('/portfolio/unites/3');
  });
});
