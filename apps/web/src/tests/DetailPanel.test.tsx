import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DetailPanel from '../pages/DispatchBoard/DetailPanel';
import { JustificationProvider } from '../components/Justification';
import type { MeResponse, RequestDetail } from '../api/schema.d.ts';
import { ApiError } from '../api/client';
import * as client from '../api/client';

vi.mock('../hooks/useRequest', () => ({
  useRequest: vi.fn(),
}));
import { useRequest } from '../hooks/useRequest';

const MOCK_REQUEST = {
  request_id: 1, raw_title: 'Test request', status: 'triaged',
  start_date: '2026-10-15', assigned_employee_id: null, assigned_employee_name: null,
  urgency_tier: null, next_follow_up_date: null, next_steps: null, estimated_cost: null,
  asnu: null, building_address: null, territoire: null, subcontractor_name: null,
  time_estimate_bucket: null, source_calendar: null, followup_log: [], justification_log: [],
};

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <JustificationProvider lang="fr">{ui}</JustificationProvider>
    </QueryClientProvider>,
  );
}

/** Answer the justification prompt by typing (jsdom has no speech engine). */
async function justifyWith(text = 'Technicien le plus proche du secteur') {
  await waitFor(() => expect(screen.getByTestId('justification-dialog')).toBeTruthy());
  fireEvent.change(screen.getByTestId('justification-text'), { target: { value: text } });
  await userEvent.click(screen.getByTestId('justification-confirm'));
}

describe('DetailPanel', () => {
  it('renders detail-panel testid', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: true, isError: false, error: null });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    expect(screen.getByTestId('detail-panel')).toBeTruthy();
  });

  it('shows loading state', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: true, isError: false, error: null });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    expect(screen.getByText(/Chargement/)).toBeTruthy();
  });

  it('shows error message without maintenance request ID', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: false, isError: true, error: null });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    const el = screen.getByText(/Erreur lors du chargement/);
    expect(el).toBeTruthy();
    // must not show the maintenance request number
    expect(el.textContent).not.toContain('42');
  });

  it('shows trace ID from error envelope when present', () => {
    const err = new ApiError('NOT_FOUND', 'Request not found', 'abc-trace-123');
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: false, isError: true, error: err });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    expect(screen.getByText(/abc-trace-123/)).toBeTruthy();
  });

  it('shows no trace ID bracket when traceId absent', () => {
    const err = new ApiError('NOT_FOUND', 'Request not found');
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: false, isError: true, error: err });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    const el = screen.getByText(/Erreur lors du chargement/);
    expect(el.textContent).not.toContain('[');
  });

  it('calls onClose when Escape is pressed', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: true, isError: false, error: null });
    const onClose = vi.fn();
    wrap(<DetailPanel requestId={1} onClose={onClose} />);
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose when backdrop clicked', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: true, isError: false, error: null });
    const onClose = vi.fn();
    const { container } = wrap(<DetailPanel requestId={1} onClose={onClose} />);
    const backdrop = container.querySelector('[aria-hidden]') as HTMLElement;
    await userEvent.click(backdrop);
    expect(onClose).toHaveBeenCalled();
  });

  it('hides edit controls for technician', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 14, roles: ['technician'] } as any} />);
    expect(screen.queryByTestId('edit-controls')).toBeNull();
  });

  it('hides edit controls for contractor', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 20, roles: ['contractor'] } as any} />);
    expect(screen.queryByTestId('edit-controls')).toBeNull();
  });

  it('shows stale message when STALE_DATA 409 received', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'dispatchAddLog').mockRejectedValue(new ApiError('STALE_DATA', 'stale'));
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    await userEvent.type(screen.getByTestId('log-text'), 'Note de suivi test.');
    await userEvent.click(screen.getByRole('button', { name: /ajouter/i }));
    await waitFor(() => expect(screen.getByText(/La demande a été modifiée/)).toBeTruthy());
  });

  it('Enregistrer saves the new assignee in one request, with the justification', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([
      { employee_id: 14, nom_employe: 'Jean Tech', role: 'technician' , is_en_route: false },
    ]);
    const save = vi.spyOn(client, 'dispatchSave').mockResolvedValue({
      ...MOCK_REQUEST, assigned_employee_id: 14, assigned_employee_name: 'Jean Tech',
    } as unknown as RequestDetail);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    render(
      <QueryClientProvider client={qc}>
        <JustificationProvider lang="fr">
          <DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />
        </JustificationProvider>
      </QueryClientProvider>
    );
    await waitFor(() => expect(screen.getByTestId('assign-select').querySelectorAll('option').length).toBeGreaterThan(1));
    await userEvent.selectOptions(screen.getByTestId('assign-select'), '14');
    // Picking only stages the edit.
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByTestId('save-bar').textContent).toMatch(/1 modification non enregistrée/);
    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith();
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['requests'] }))
    );
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith(1, expect.objectContaining({
      changes: { assigned_employee_id: 14 },
      current: expect.objectContaining({ assigned_employee_id: null, start_date: MOCK_REQUEST.start_date }),
      justification: { text: 'Technicien le plus proche du secteur.', input_method: 'typed' },
    }));
  });
  it('renders both Estimation (time bucket) and Coût estimé (cost) rows', () => {
    const reqWithBoth = { ...MOCK_REQUEST, time_estimate_bucket: '<1h', estimated_cost: 350 };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: reqWithBoth, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.getByText('<1h')).toBeTruthy();      // Estimation row — time_estimate_bucket
    expect(screen.getByText(/350/)).toBeTruthy();      // Coût estimé row — formatted CAD
  });

  it('links the full building address to Google Maps in a new tab', () => {
    const req = { ...MOCK_REQUEST, building_address: '1580 Perigord', building_full_address: '1580 Perigord, Québec, G1E 6J5' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    const link = screen.getByTestId('building-map-link') as HTMLAnchorElement;
    expect(link.textContent).toContain('1580 Perigord, Québec, G1E 6J5');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toContain('noopener');
    expect(link.href).toBe(
      'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent('1580 Perigord, Québec, G1E 6J5, QC, Canada'),
    );
  });

  it('shows no map link when the building has no address', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.queryByTestId('building-map-link')).toBeNull();
  });

  it('shows not urgent when urgency_tier is null', () => {
    const req = { ...MOCK_REQUEST, urgency_tier: null };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="en" me={null} />);
    expect(screen.getByText('not urgent')).toBeTruthy();
  });

  it('disables edit controls (except log) when status is closed', async () => {
    const closedReq = { ...MOCK_REQUEST, status: 'closed' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: closedReq, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    const assignSelect = screen.getByTestId('assign-select') as HTMLSelectElement;
    expect(assignSelect.disabled).toBe(true);
    // Log Add button exists (section not gated by isClosed)
    expect(screen.getByRole('button', { name: /ajouter/i })).toBeTruthy();
  });

  it('formats entry_date as short month + day without timezone shift', () => {
    const reqWithLog = {
      ...MOCK_REQUEST,
      followup_log: [{ followup_id: 1, entry_date: '2026-10-15', entered_by_initials: 'AB', entry_text: 'Test log' }],
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: reqWithLog, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="en" me={null} />);
    // '2026-10-15' must render as 'Oct 15' (en-CA short) — not as '2026-10-15' raw string
    expect(screen.getByText(/\bOct[\s.]?\s*15\b/i)).toBeTruthy();
  });

  it('shows ineligible assignee with translated role label in select', async () => {
    const coordAssigned = { ...MOCK_REQUEST, assigned_employee_id: 4, assigned_employee_name: 'Marie Lavoie' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: coordAssigned, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([
      { employee_id: 4, nom_employe: 'Marie Lavoie', role: 'coordinator' , is_en_route: false },
      { employee_id: 14, nom_employe: 'Jean Tech', role: 'technician' , is_en_route: false },
    ]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 5, roles: ['director'] } as any} />);
    await waitFor(() => {
      const sel = screen.getByTestId('assign-select') as HTMLSelectElement;
      expect(sel.value).toBe('4');
      const ineligibleOpt = Array.from(sel.options).find((o) => o.disabled && o.value === '4');
      expect(ineligibleOpt).toBeTruthy();
      expect(ineligibleOpt!.text).toContain('Coordonnateur');
    });
  });

  it('shows triage button for intake_received status (coordinator)', () => {
    const intakeReq = { ...MOCK_REQUEST, status: 'intake_received' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: intakeReq, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    expect(screen.getByTestId('triage-btn')).toBeTruthy();
  });

  it('hides triage button when status is triaged', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    expect(screen.queryByTestId('triage-btn')).toBeNull();
  });

  it('triage button calls triggerTriage on click', async () => {
    const intakeReq = { ...MOCK_REQUEST, status: 'intake_received' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: intakeReq, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'triggerTriage').mockResolvedValue({ request_id: 1, status: 'triage_pending' });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    await userEvent.click(screen.getByTestId('triage-btn'));
    await waitFor(() => expect(client.triggerTriage).toHaveBeenCalledWith(1, { lang: 'fr' }));
  });

  it('does not show calendar route override buttons (auto from secteur)', () => {
    const triaged = { ...MOCK_REQUEST, status: 'triaged', source_calendar: 'main' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: triaged, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    expect(screen.queryByTestId('routing-section')).toBeNull();
    expect(screen.queryByTestId('route-majordome')).toBeNull();
    expect(screen.queryByTestId('route-principal')).toBeNull();
  });

  it('shows French role label for assignable technician in select', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([
      { employee_id: 7, nom_employe: 'Pierre Ouvrier', role: 'technician' , is_en_route: false },
    ]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    await waitFor(() => {
      const opt = Array.from(screen.getByTestId('assign-select').querySelectorAll('option'))
        .find((o) => o.textContent?.includes('Pierre Ouvrier'));
      expect(opt?.textContent).toContain('Technicien');
    });
  });

  it('shows French source calendar label, not raw code', () => {
    const req = { ...MOCK_REQUEST, source_calendar: 'st_maj', source_calendar_label: 'Butler/Majordome' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.getByText('Butler/Majordome')).toBeTruthy();
    expect(screen.queryByText('st_maj')).toBeNull();
  });

  it('shows dual display section only when AI ran and fields differ', () => {
    const withRaw = {
      ...MOCK_REQUEST,
      triage_model_version: 'gpt-4o-mini',
      raw_caller_body: { entry_permission: 'Accès autorisé (traitement prioritaire)', animals: null, problems: 'Fuite' },
      entry_permission: 'N/A Non applicable (exemple espace commun)',
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: withRaw, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    const dd = screen.getByTestId('dual-display');
    expect(dd).toBeTruthy();
    expect(within(dd).getByText(/Accès autorisé/)).toBeTruthy();
    expect(within(dd).getByText(/N\/A Non applicable/)).toBeTruthy();
  });

  it('hides dual display when triage_model_version not set (no AI ran)', () => {
    const withRaw = {
      ...MOCK_REQUEST,
      triage_model_version: null,
      raw_caller_body: { entry_permission: 'Accès autorisé', animals: null, problems: 'Fuite' },
      entry_permission: 'N/A Non applicable',
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: withRaw, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.queryByTestId('dual-display')).toBeNull();
  });

  it('hides dual display when raw_caller_body is null', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.queryByTestId('dual-display')).toBeNull();
  });

  it('a changed schedule date is staged, then saved with Enregistrer', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const save = vi.spyOn(client, 'dispatchSave').mockResolvedValue(MOCK_REQUEST as unknown as RequestDetail);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />);

    expect(screen.queryByRole('button', { name: /appliquer/i })).toBeNull();
    fireEvent.change(screen.getByTestId('reschedule-input'), { target: { value: '2026-11-01' } });
    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith('Locataire demande une date plus tard');

    await waitFor(() => expect(save).toHaveBeenCalledWith(1, expect.objectContaining({
      changes: { start_date: '2026-11-01' },
      justification: { text: 'Locataire demande une date plus tard.', input_method: 'typed' },
    })));
  });
  it('problems-section shows raw_caller_body.problems, not data.problems', () => {
    const req = {
      ...MOCK_REQUEST,
      problems: 'AI rewritten version',
      raw_caller_body: { problems: 'Original tenant text', entry_permission: null, animals: null },
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} />);
    const section = screen.getByTestId('problems-section');
    expect(section.textContent).toContain('Original tenant text');
    expect(section.textContent).not.toContain('AI rewritten version');
  });

  it('problems-section falls back to data.problems when raw_caller_body.problems is absent', () => {
    const req = { ...MOCK_REQUEST, problems: 'Fallback text', raw_caller_body: null };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} />);
    expect(screen.getByTestId('problems-section').textContent).toContain('Fallback text');
  });

  // Item 5: AI summary reads problem_summary, not triage_summary
  it('ai-section shows problem_summary text', () => {
    const req = {
      ...MOCK_REQUEST,
      triage_model_version: 'gpt-4',
      problem_summary: 'Fuite sous le lavabo — < 30 min',
      triage_summary: null,
      other_notes: null,
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    const section = screen.getByTestId('ai-section');
    expect(section.textContent).toContain('Fuite sous le lavabo — < 30 min');
  });

  it('ai-section does not show when triage_summary is set but problem_summary is null', () => {
    const req = {
      ...MOCK_REQUEST,
      triage_model_version: 'gpt-4',
      problem_summary: null,
      triage_summary: 'Should not appear',
      other_notes: null,
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    // ai-section still rendered (triage_model_version is set), but summary text absent
    const section = screen.queryByTestId('ai-section');
    expect(section?.textContent ?? '').not.toContain('Should not appear');
  });

  // Item 3 (session 3): sentinel contacts normalised in API — panel shows "non fourni"
  it('shows non fourni for placeholder phone (API returned null + placeholder flag)', () => {
    const req = { ...MOCK_REQUEST, caller_phone: null, caller_phone_placeholder: true, caller_email: null, caller_email_placeholder: false };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" />);
    expect(screen.getByTestId('phone-display').textContent).toBe('non fourni');
  });

  it('shows non fourni for placeholder email (API returned null + placeholder flag)', () => {
    const req = { ...MOCK_REQUEST, caller_phone: null, caller_phone_placeholder: false, caller_email: null, caller_email_placeholder: true };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" />);
    expect(screen.getByTestId('email-display').textContent).toBe('non fourni');
  });

  it('shows — for null phone without placeholder flag', () => {
    const req = { ...MOCK_REQUEST, caller_phone: null, caller_phone_placeholder: false };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" />);
    expect(screen.getByTestId('phone-display').textContent).toBe('—');
  });

  it('shows actual email when not a placeholder', () => {
    const req = { ...MOCK_REQUEST, caller_email: 'real@example.com', caller_email_placeholder: false };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" />);
    expect(screen.getByTestId('email-display').textContent).toBe('real@example.com');
  });
});

describe('visits section (stop 3)', () => {
  it('shows each visit: outcome label, times, elapsed, comment, photos', async () => {
    vi.spyOn(client, 'fetchPhotoUrl').mockResolvedValue({ url: 'https://signed.local/closeout/1/9.jpg' });
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({
      data: {
        ...MOCK_REQUEST,
        visits: [{
          visit_id: 1, employee_id: 24, employee_name: 'Martin Poirier',
          en_route_at: '2026-10-19T14:00:00Z', closeout_at: '2026-10-19T15:30:00Z',
          outcome: 'partial_expertise', closeout_comment: 'Fuite réparée en partie',
          photo_ids: [9],
        }],
      },
      isPending: false, isError: false, error: null,
    });
    wrap(
      <DetailPanel requestId={1} onClose={vi.fn()} lang="fr"
        me={{ employee_id: 4, roles: ['coordinator'] } as any} />
    );
    expect(screen.getByTestId('history-timeline')).toBeTruthy();
    expect(screen.getByText(/Call partiellement fait, besoin d'une expertise/)).toBeTruthy();
    expect(screen.getByText(/1 h 30/)).toBeTruthy();
    expect(screen.getByText(/Fuite réparée en partie/)).toBeTruthy();
    expect(screen.getByText('Martin Poirier', { exact: false })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('visit-photo')).toBeTruthy());
    expect(screen.getByTestId('visit-photo').getAttribute('src')).toContain('signed.local');
  });
});

describe('en route assignment lock (fix 2026-10-19)', () => {
  const EN_ROUTE_MSG = "Appel en cours — le technicien doit d'abord clôturer";

  it('disables the assignee control with the message when en_route', async () => {
    const enRouteReq = { ...MOCK_REQUEST, status: 'en_route' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: enRouteReq, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(
      <DetailPanel requestId={1} onClose={vi.fn()} lang="fr"
        me={{ employee_id: 4, roles: ['coordinator'] } as any} />
    );
    const select = screen.getByTestId('assign-select') as HTMLSelectElement;
    expect(select.disabled).toBe(true);
    expect(screen.getByTestId('en-route-notice').textContent).toContain(EN_ROUTE_MSG);
    // The other dispatch controls stay usable (log textarea not disabled).
    expect((screen.getByTestId('log-text') as HTMLTextAreaElement).disabled).toBe(false);
  });

  it('shows the message when the API returns 409 REQUEST_EN_ROUTE', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([
      { employee_id: 14, nom_employe: 'Jean Tech', role: 'technician' , is_en_route: false },
    ]);
    vi.spyOn(client, 'dispatchSave').mockRejectedValue(new ApiError('REQUEST_EN_ROUTE', EN_ROUTE_MSG));
    wrap(
      <DetailPanel requestId={1} onClose={vi.fn()} lang="fr"
        me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />
    );
    await waitFor(() =>
      expect(screen.getByTestId('assign-select').querySelectorAll('option').length).toBeGreaterThan(1)
    );
    await userEvent.selectOptions(screen.getByTestId('assign-select'), '14');
    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith();
    await waitFor(() => expect(screen.getByText(EN_ROUTE_MSG)).toBeTruthy());
  });
});

describe('intake photos', () => {
  it('shows the photos attached to the call in the problem card', async () => {
    vi.spyOn(client, 'fetchPhotoUrl').mockResolvedValue({ url: 'https://signed.local/intake/1/7.jpg' });
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { ...MOCK_REQUEST, problems: 'Fuite', intake_photo_ids: [7, 8] }, isPending: false, isError: false, error: null,
    });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    const box = screen.getByTestId('intake-photos');
    expect(box.textContent).toMatch(/Photos jointes à l’appel \(2\)/);
    await waitFor(() => expect(screen.getAllByTestId('intake-photo')).toHaveLength(2));
    expect(screen.getAllByTestId('intake-photo')[0].getAttribute('src')).toContain('signed.local');
  });
});

describe('decision justification (system-wide)', () => {
  const coord = { employee_id: 4, nom_employe: 'Coord', roles: ['coordinator'] } as unknown as MeResponse;
  const ok = MOCK_REQUEST as unknown as RequestDetail;

  it('cancelling the prompt saves nothing and keeps the edits; discard restores them', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([
      { employee_id: 14, nom_employe: 'Jean Tech', role: 'technician' , is_en_route: false },
    ]);
    const save = vi.spyOn(client, 'dispatchSave').mockResolvedValue(ok);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);
    await waitFor(() =>
      expect(screen.getByTestId('assign-select').querySelectorAll('option').length).toBeGreaterThan(1)
    );
    await userEvent.selectOptions(screen.getByTestId('assign-select'), '14');
    await userEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('justification-dialog')).toBeTruthy());
    expect(screen.getByTestId('justification-dialog').textContent).toContain('Jean Tech');
    await userEvent.click(screen.getByRole('button', { name: 'Annuler' }));
    await waitFor(() => expect(screen.queryByTestId('justification-dialog')).toBeNull());
    expect(save).not.toHaveBeenCalled();
    expect((screen.getByTestId('assign-select') as HTMLSelectElement).value).toBe('14');
    await userEvent.click(screen.getByRole('button', { name: 'Annuler les modifications' }));
    expect((screen.getByTestId('assign-select') as HTMLSelectElement).value).toBe('');
    expect((screen.getByTestId('save-btn') as HTMLButtonElement).disabled).toBe(true);
  });
  it('confirm stays disabled under 10 characters', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);
    await userEvent.click(screen.getByRole('button', { name: 'Urgent' }));
    await userEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('justification-dialog')).toBeTruthy());
    const confirm = screen.getByTestId('justification-confirm') as HTMLButtonElement;
    fireEvent.change(screen.getByTestId('justification-text'), { target: { value: 'trop court'.slice(0, 9) } });
    expect(confirm.disabled).toBe(true);
    fireEvent.change(screen.getByTestId('justification-text'), { target: { value: 'Dégât d’eau actif' } });
    expect(confirm.disabled).toBe(false);
  });
  it('urgency, follow-up, next steps and cost go out in ONE save with ONE justification', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const save = vi.spyOn(client, 'dispatchSave').mockResolvedValue(ok);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);

    await userEvent.click(screen.getByRole('button', { name: 'Urgent' }));
    fireEvent.change(screen.getByTestId('follow-up-input'), { target: { value: '2026-11-03' } });
    fireEvent.change(screen.getByTestId('next-steps-input'), { target: { value: 'Commander la pièce' } });
    fireEvent.change(screen.getByTestId('cost-input'), { target: { value: '250' } });
    expect(screen.getByTestId('save-bar').textContent).toMatch(/4 modifications non enregistrées/);

    await userEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('justification-changes').querySelectorAll('li')).toHaveLength(4));
    await justifyWith('Dégât d’eau actif chez le locataire');
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith(1, expect.objectContaining({
      changes: {
        urgency_tier: 'URGENT',
        next_follow_up_date: '2026-11-03',
        next_steps: 'Commander la pièce',
        estimated_cost: 250,
      },
      justification: expect.objectContaining({ input_method: 'typed' }),
    }));
  });
  it('choosing the current value is not a change', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { ...MOCK_REQUEST, urgency_tier: 'URGENT' }, isPending: false, isError: false, error: null,
    });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);
    await userEvent.click(screen.getByRole('button', { name: 'Urgent' }));
    expect((screen.getByTestId('save-btn') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId('save-bar').textContent).toMatch(/Aucune modification/);
  });

  it('asks before closing with unsaved changes', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const onClose = vi.fn();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    wrap(<DetailPanel requestId={1} onClose={onClose} lang="fr" me={coord} />);
    await userEvent.click(screen.getByRole('button', { name: 'Urgent' }));
    await userEvent.click(screen.getByRole('button', { name: 'Fermer' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    confirmSpy.mockReturnValue(true);
    await userEvent.click(screen.getByRole('button', { name: 'Fermer' }));
    expect(onClose).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
