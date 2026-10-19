import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Utilization from '../pages/Utilization';
import type { UtilizationResponse } from '../api/schema.d.ts';

const body: UtilizationResponse = {
  start_date: '2026-10-13',
  end_date: '2026-10-19',
  capacity_enabled: false,
  capacity_hours_per_day: null,
  planned_footnote: 'estimation provisoire',
  rows: [
    {
      employee_id: 24,
      nom_employe: 'Test Tech',
      territoire: 'QUÉBEC-EST',
      calls_assigned: 2,
      calls_closed: 0,
      planned_minutes: 20,
      planned_unknown_count: 1,
      visit_minutes: 0,
      visits_count: 0,
      outcome_mix: { complete: 0, partial_reschedule: 0, partial_expertise: 0, failed: 0 },
      capacity_minutes: null,
      utilization_pct: null,
    },
  ],
};

vi.mock('../api/client', () => ({
  fetchUtilization: vi.fn(),
}));

import { fetchUtilization } from '../api/client';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Utilization', () => {
  beforeEach(() => {
    vi.mocked(fetchUtilization).mockReset();
    vi.mocked(fetchUtilization).mockResolvedValue(body);
  });

  it('shows French outcome headers and provisional footnote', async () => {
    wrap(<Utilization lang="fr" />);
    await screen.findByTestId('util-table');
    expect(screen.getByText(/Call fermé, terminé complètement/)).toBeTruthy();
    expect(screen.getByTestId('planned-footnote')).toHaveTextContent('estimation provisoire');
  });

  it('shows real zeros for visit/closed, never a capacity target', async () => {
    wrap(<Utilization lang="fr" />);
    const row = await screen.findByTestId('util-row-24');
    expect(row).toHaveTextContent('0'); // closed / visit zeros
    expect(screen.queryByText(/8\s*[-–àa]\s*14|utilisation %|capacity/i)).toBeNull();
  });

  it('filters rows by employee name and sorts by a column', async () => {
    vi.mocked(fetchUtilization).mockResolvedValue({
      ...body,
      rows: [
        body.rows[0],
        { ...body.rows[0], employee_id: 25, nom_employe: 'Alice Roy', calls_assigned: 9 },
      ],
    });
    wrap(<Utilization lang="fr" />);
    const table = await screen.findByTestId('util-table');
    // Default sort: most assigned first.
    let rows = within(table).getAllByTestId(/util-row-/);
    expect(rows[0]).toHaveAttribute('data-testid', 'util-row-25');

    fireEvent.change(screen.getByTestId('util-sort'), { target: { value: 'name' } });
    rows = within(table).getAllByTestId(/util-row-/);
    expect(rows[0]).toHaveAttribute('data-testid', 'util-row-25'); // Alice < Test

    fireEvent.change(screen.getByLabelText('Filtrer'), { target: { value: 'test' } });
    expect(screen.queryByTestId('util-row-25')).toBeNull();
    expect(screen.getByTestId('util-row-24')).toBeTruthy();
  });
});
