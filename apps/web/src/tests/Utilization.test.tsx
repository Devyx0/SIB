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
      avg_rating: null,
      rating_count: 0,
      reviews: [],
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

  it('shows customer star rating and expands reviews', async () => {
    vi.mocked(fetchUtilization).mockResolvedValue({
      ...body,
      rows: [{
        ...body.rows[0],
        avg_rating: 4.5,
        rating_count: 2,
        reviews: [
          {
            survey_id: 1, request_id: 101, submitted_at: '2026-10-18T14:00:00Z',
            rating: 5, polite: true, problem_solved: true,
            comments: 'Très professionnel', building_address: '12 rue Test',
          },
          {
            survey_id: 2, request_id: 102, submitted_at: '2026-10-17T14:00:00Z',
            rating: 4, polite: true, problem_solved: false,
            comments: null, building_address: null,
          },
        ],
      }],
    });
    wrap(<Utilization lang="fr" />);
    const btn = await screen.findByTestId('util-rating-24');
    expect(btn).toHaveTextContent('4,5');
    expect(btn).toHaveTextContent('2 avis');
    expect(screen.getByTestId('kpi-rating')).toHaveTextContent('4,5');
    expect(screen.queryByTestId('util-reviews-24')).toBeNull();

    fireEvent.click(btn);
    const reviews = screen.getByTestId('util-reviews-24');
    expect(reviews).toHaveTextContent('Très professionnel');
    expect(reviews).toHaveTextContent('Résolu : non');
    expect(within(reviews).getAllByRole('listitem')).toHaveLength(2);

    fireEvent.click(btn);
    expect(screen.queryByTestId('util-reviews-24')).toBeNull();

    // Team-wide panel from the KPI tile, with technician names.
    fireEvent.click(screen.getByTestId('kpi-rating'));
    const all = screen.getByTestId('util-all-reviews');
    expect(within(all).getAllByRole('listitem')).toHaveLength(2);
    expect(all).toHaveTextContent('Test Tech');
    expect(all).toHaveTextContent('Très professionnel');
    fireEvent.click(screen.getByTestId('kpi-rating'));
    expect(screen.queryByTestId('util-all-reviews')).toBeNull();
  });

  it('previews the 3 newest reviews and opens the rest in a scroll box', async () => {
    const reviews = [1, 2, 3, 4, 5].map((n) => ({
      survey_id: n, request_id: 100 + n, submitted_at: `2026-10-1${n}T14:00:00Z`,
      rating: 4, polite: true, problem_solved: true,
      comments: `Avis ${n}`, building_address: null,
    }));
    vi.mocked(fetchUtilization).mockResolvedValue({
      ...body,
      rows: [{ ...body.rows[0], avg_rating: 4, rating_count: 5, reviews }],
    });
    wrap(<Utilization lang="fr" />);
    fireEvent.click(await screen.findByTestId('util-rating-24'));

    const list = screen.getByTestId('util-review-list-24');
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('Avis 5'); // newest first
    expect(list).not.toHaveTextContent('Avis 2');

    const more = screen.getByTestId('util-reviews-more-24');
    expect(more).toHaveTextContent('Voir les 2 autres');
    fireEvent.click(more);
    expect(within(list).getAllByRole('listitem')).toHaveLength(5);
    expect(list.className).toMatch(/reviewListScroll/);
    expect(more).toHaveTextContent('Afficher moins');

    fireEvent.click(more);
    expect(within(list).getAllByRole('listitem')).toHaveLength(3);
  });

  it('has no "more" button with 3 reviews or fewer', async () => {
    vi.mocked(fetchUtilization).mockResolvedValue({
      ...body,
      rows: [{
        ...body.rows[0], avg_rating: 5, rating_count: 1,
        reviews: [{
          survey_id: 1, request_id: 101, submitted_at: '2026-10-18T14:00:00Z',
          rating: 5, polite: true, problem_solved: true, comments: null, building_address: null,
        }],
      }],
    });
    wrap(<Utilization lang="fr" />);
    fireEvent.click(await screen.findByTestId('util-rating-24'));
    expect(screen.queryByTestId('util-reviews-more-24')).toBeNull();
  });

  it('shows "Aucun avis" when a technician has no reviews', async () => {
    wrap(<Utilization lang="fr" />);
    const row = await screen.findByTestId('util-row-24');
    expect(row).toHaveTextContent('Aucun avis');
  });
});
