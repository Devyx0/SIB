import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Dashboard from '../pages/Dashboard';
import type { DashboardResponse } from '../api/schema.d.ts';

const base: DashboardResponse = {
  as_of_date: '2026-10-19',
  today_by_status: [],
  load_today: [],
  by_territory: [
    {
      sector_id: 1,
      territoire: 'QUÉBEC-EST',
      active: 3,
      AJD: 1,
      ajd: 0,
      untriaged: 0,
      board_link: '/board?sector_id=1&start_date=2026-09-19&end_date=2026-10-19',
    },
  ],
  queue_counts: {
    a_router: 0,
    a_redispatcher: 2,
    a_router_link: '/board?source_calendar=unrouted',
    a_redispatcher_link: '/board?redispatch=1',
  },
  after_hours: null,
  weather: null,
  satisfaction: null,
  untriaged_statuses: ['intake_received', 'triage_pending', 'triage_failed', 'triage_clarify'],
};

vi.mock('../api/client', () => ({
  fetchDashboard: vi.fn(),
}));

import { fetchDashboard } from '../api/client';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.mocked(fetchDashboard).mockReset();
  });

  it('shows 0 for empty today status, not unavailable', async () => {
    vi.mocked(fetchDashboard).mockResolvedValue(base);
    wrap(<Dashboard lang="fr" />);
    expect(await screen.findByTestId('today-status-empty')).toBeTruthy();
    expect(screen.getByTestId('today-status-empty')).toHaveTextContent('0');
    expect(screen.queryByTestId('data-unavailable')).toBeTruthy(); // weather null
  });

  it('shows Données non disponibles only for weather when null', async () => {
    vi.mocked(fetchDashboard).mockResolvedValue(base);
    wrap(<Dashboard lang="fr" />);
    await screen.findByTestId('dashboard-page');
    const nas = screen.getAllByTestId('data-unavailable');
    expect(nas.length).toBe(1);
    expect(nas[0]).toHaveTextContent('Données non disponibles');
  });

  it('shows weather numbers when present (not unavailable)', async () => {
    vi.mocked(fetchDashboard).mockResolvedValue({
      ...base,
      weather: {
        location: 'quebec',
        current_temp_c: 5,
        min_forecast_temp_24h_c: 2,
        source_credit: 'Source : Environnement et Changement climatique Canada',
      },
    });
    wrap(<Dashboard lang="fr" />);
    expect(await screen.findByTestId('weather-line')).toHaveTextContent('5 °C');
    expect(screen.queryByTestId('data-unavailable')).toBeNull();
  });

  it('queue links point at board filters', async () => {
    vi.mocked(fetchDashboard).mockResolvedValue(base);
    wrap(<Dashboard lang="fr" />);
    await screen.findByTestId('link-a-router');
    expect((screen.getByTestId('link-a-router') as HTMLAnchorElement).getAttribute('href'))
      .toBe('/board?source_calendar=unrouted');
    expect((screen.getByTestId('link-a-redispatcher') as HTMLAnchorElement).getAttribute('href'))
      .toBe('/board?redispatch=1');
  });

  it('territory untriaged header has status tooltip; zero queue shows 0', async () => {
    vi.mocked(fetchDashboard).mockResolvedValue(base);
    wrap(<Dashboard lang="fr" />);
    const hdr = await screen.findByTestId('untriaged-header');
    expect(hdr.getAttribute('title')).toMatch(/Reçu|En triage|Clarification|Triage échoué/);
    expect(screen.getByTestId('count-a-router')).toHaveTextContent('0');
    expect(screen.getByTestId('count-a-redispatcher')).toHaveTextContent('2');
  });

  it('never shows a daily call target', async () => {
    vi.mocked(fetchDashboard).mockResolvedValue(base);
    wrap(<Dashboard lang="fr" />);
    await screen.findByTestId('dashboard-page');
    expect(screen.queryByText(/8\s*[-–àa]\s*14|calls per employee|appels par employé/i)).toBeNull();
  });
});
