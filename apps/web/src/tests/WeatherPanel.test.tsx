import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DetailPanel from '../pages/DispatchBoard/DetailPanel';

vi.mock('../hooks/useRequest', () => ({ useRequest: vi.fn() }));
import { useRequest } from '../hooks/useRequest';

const BASE = {
  request_id: 1, raw_title: 'Appel test', status: 'triaged',
  start_date: '2026-10-15', assigned_employee_id: null, assigned_employee_name: null,
  urgency_tier: null, next_follow_up_date: null, next_steps: null, estimated_cost: null,
  asnu: null, building_address: null, territoire: null, subcontractor_name: null,
  time_estimate_bucket: null, source_calendar: null, followup_log: [], justification_log: [],
  problem_summary: null, problems: null, triage_model_version: null, weather_evaluation: null,
};
const COORD = { employee_id: 4, nom_employe: 'Coord', roles: ['coordinator'], weather_escalation_enabled: true };
const TECH = { employee_id: 14, nom_employe: 'Tech', roles: ['technician'], weather_escalation_enabled: true };

// Weather stays available to the triage agent; the coordinator UI no longer surfaces it.
const EVAL_OK = {
  evaluation_id: 7, status: 'ok', location: 'quebec', band_name: 'critical',
  suggested_tier: 'URGENT', is_critical: true, min_forecast_temp_24h_c: -22,
  current_tier_at_eval: null, evaluated_at: '2026-10-19T14:05:00-04:00',
};

function mockData(over: Record<string, unknown> = {}) {
  (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({
    data: { ...BASE, ...over }, isPending: false, isError: false, error: null,
  });
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => { vi.restoreAllMocks(); });

describe('Weather UI removed from service call panel', () => {
  it('does not render a weather section even when an evaluation exists', () => {
    mockData({ weather_evaluation: EVAL_OK });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    expect(screen.queryByTestId('weather-section')).toBeNull();
    expect(screen.queryByTestId('weather-check-btn')).toBeNull();
    expect(screen.queryByTestId('weather-accept')).toBeNull();
  });

  it('does not render weather for technicians either', () => {
    mockData({ weather_evaluation: EVAL_OK });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={TECH} />);
    expect(screen.queryByTestId('weather-section')).toBeNull();
  });
});
