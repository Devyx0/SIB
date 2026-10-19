import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DetailPanel from '../pages/DispatchBoard/DetailPanel';
import * as client from '../api/client';

vi.mock('../hooks/useRequest', () => ({ useRequest: vi.fn() }));
import { useRequest } from '../hooks/useRequest';

const BASE = {
  request_id: 1, raw_title: 'Appel test', status: 'triaged',
  start_date: '2026-10-15', assigned_employee_id: null, assigned_employee_name: null,
  urgency_tier: null, next_follow_up_date: null, next_steps: null, estimated_cost: null,
  asnu: null, building_address: null, territoire: null, subcontractor_name: null,
  time_estimate_bucket: null, source_calendar: null, followup_log: [], justification_log: [],
  problem_summary: null, problems: null, triage_model_version: null, heating_keyword_hint: false,
};
const COORD = { employee_id: 4, nom_employe: 'Coord', roles: ['coordinator'], weather_escalation_enabled: true };

function mockData(over: Record<string, unknown> = {}) {
  (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({
    data: { ...BASE, ...over }, isPending: false, isError: false, error: null,
  });
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const OK_HIGHER = {
  evaluation_id: 7, status: 'ok', location: 'quebec', band_name: 'critical',
  suggested_tier: 'AJD', direction: 'higher', is_critical: true,
  min_forecast_temp_24h_c: -22, current_temp_c: -18, wind_chill_c: -29,
  current_urgency_tier: null, current_tier_at_eval: null, forecast_time_local: '14:05',
  source: 'msc_citypage', source_url: 'https://dd.weather.gc.ca/x.xml',
};

beforeEach(() => { vi.restoreAllMocks(); });

describe('Weather panel', () => {
  it('does not render the weather button when feature is off', () => {
    mockData();
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={{ ...COORD, weather_escalation_enabled: false }} />);
    expect(screen.queryByTestId('weather-check-btn')).toBeNull();
  });

  it('renders the weather button when feature on for an editor', () => {
    mockData();
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    expect(screen.getByTestId('weather-check-btn')).toBeTruthy();
  });

  it('shows the heating hint when keyword matched', () => {
    mockData({ heating_keyword_hint: true });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    expect(screen.getByTestId('weather-hint')).toBeTruthy();
  });

  it('hides the heating hint when no keyword match', () => {
    mockData({ heating_keyword_hint: false });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    expect(screen.queryByTestId('weather-hint')).toBeNull();
  });

  it('higher suggestion shows raise label, astreinte badge, licence and accept', async () => {
    mockData();
    vi.spyOn(client, 'checkWeather').mockResolvedValue(OK_HIGHER as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    await userEvent.click(screen.getByTestId('weather-check-btn'));
    await waitFor(() => expect(screen.getByTestId('weather-result')).toBeTruthy());
    expect(screen.getByText(/Hausse suggérée/)).toBeTruthy();
    expect(screen.getByTestId('weather-astreinte')).toBeTruthy();
    expect(screen.getByText(/Environnement et Changement climatique Canada/)).toBeTruthy();
    expect(screen.getByTestId('weather-accept')).toBeTruthy();
    // Location + French band + forecast time + single draft-threshold note
    expect(screen.getByText(/Météo — Québec/)).toBeTruthy();
    expect(screen.getByText(/palier critique/)).toBeTruthy();
    expect(screen.getByText(/prévision de 14:05/)).toBeTruthy();
    expect(screen.getByText(/Seuils provisoires — à valider/)).toBeTruthy();
    expect(screen.queryByText(/\(brouillon\)/)).toBeNull();
  });

  it('lower suggestion is neutral and still offers accept', async () => {
    mockData({ urgency_tier: 'AJD' });
    vi.spyOn(client, 'checkWeather').mockResolvedValue({
      ...OK_HIGHER, band_name: 'normal', suggested_tier: null, direction: 'lower',
      is_critical: false, min_forecast_temp_24h_c: 15, current_tier_at_eval: 'AJD',
    } as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    await userEvent.click(screen.getByTestId('weather-check-btn'));
    await waitFor(() => expect(screen.getByText(/Baisse possible/)).toBeTruthy());
    expect(screen.queryByTestId('weather-astreinte')).toBeNull();
    expect(screen.getByText(/palier normal/)).toBeTruthy();
    expect(screen.getByTestId('weather-accept')).toBeTruthy();
  });

  it('equal suggestion shows context only, no accept', async () => {
    mockData({ urgency_tier: 'AJD' });
    vi.spyOn(client, 'checkWeather').mockResolvedValue({
      ...OK_HIGHER, direction: 'equal', current_tier_at_eval: 'AJD',
    } as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    await userEvent.click(screen.getByTestId('weather-check-btn'));
    await waitFor(() => expect(screen.getByTestId('weather-result')).toBeTruthy());
    expect(screen.queryByTestId('weather-accept')).toBeNull();
  });

  it('shows "Emplacement inconnu" for unknown location', async () => {
    mockData();
    vi.spyOn(client, 'checkWeather').mockResolvedValue({
      evaluation_id: 9, status: 'location_unknown', is_critical: false,
    } as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    await userEvent.click(screen.getByTestId('weather-check-btn'));
    await waitFor(() => expect(screen.getByText(/Emplacement inconnu/)).toBeTruthy());
  });

  it('shows failure message when source failed', async () => {
    mockData();
    vi.spyOn(client, 'checkWeather').mockResolvedValue({
      evaluation_id: 9, status: 'source_failed', is_critical: false,
    } as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    await userEvent.click(screen.getByTestId('weather-check-btn'));
    await waitFor(() => expect(screen.getByTestId('weather-failed')).toBeTruthy());
  });

  it('accepting a higher suggestion posts urgency with weather_evaluation_id', async () => {
    mockData();
    vi.spyOn(client, 'checkWeather').mockResolvedValue(OK_HIGHER as never);
    const setUrgency = vi.spyOn(client, 'dispatchSetUrgency').mockResolvedValue({ ...BASE, urgency_tier: 'AJD' } as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    await userEvent.click(screen.getByTestId('weather-check-btn'));
    await waitFor(() => expect(screen.getByTestId('weather-accept')).toBeTruthy());
    await userEvent.click(screen.getByTestId('weather-accept'));
    // Read-only weather context above the textarea; textarea NOT prefilled.
    expect(screen.getByTestId('justification-context').textContent).toMatch(/Suite à la suggestion météo/);
    expect((screen.getByTestId('justification-text') as HTMLTextAreaElement).value).toBe('');
    await userEvent.type(screen.getByTestId('justification-text'), 'Météo -22 °C prévu sur 24 h.');
    await userEvent.click(screen.getByTestId('justification-save'));
    await waitFor(() => expect(setUrgency).toHaveBeenCalled());
    const [, body] = setUrgency.mock.calls[0];
    expect(body.urgency_tier).toBe('AJD');
    expect(body.weather_evaluation_id).toBe(7);
  });

  it('hides suggestion and accept when urgency changed since the check', async () => {
    mockData({ urgency_tier: 'AJD' });  // differs from eval tier below
    vi.spyOn(client, 'checkWeather').mockResolvedValue({ ...OK_HIGHER, current_tier_at_eval: 'ajd' } as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    await userEvent.click(screen.getByTestId('weather-check-btn'));
    await waitFor(() => expect(screen.getByTestId('weather-result')).toBeTruthy());
    expect(screen.queryByTestId('weather-accept')).toBeNull();
    expect(screen.queryByText(/Hausse suggérée/)).toBeNull();
    expect(screen.getByText(/Météo — Québec/)).toBeTruthy();  // context still shown
  });

  it('hides suggestion after accept (urgency now equals suggested, not eval tier)', async () => {
    mockData({ urgency_tier: 'AJD' });  // urgency became the suggested AJD after accepting
    vi.spyOn(client, 'checkWeather').mockResolvedValue({ ...OK_HIGHER, current_tier_at_eval: null } as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} me={COORD} />);
    await userEvent.click(screen.getByTestId('weather-check-btn'));
    await waitFor(() => expect(screen.getByTestId('weather-result')).toBeTruthy());
    expect(screen.queryByTestId('weather-accept')).toBeNull();
  });
});
