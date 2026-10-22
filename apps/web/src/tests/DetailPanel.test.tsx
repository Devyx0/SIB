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

function task(id: number, extra: Record<string, unknown> = {}) {
  return {
    task_id: id, request_id: 1, description: `Tâche ${id}`, status: 'queued',
    assigned_employee_id: null, vendor_id: null, subcontractor_name: null,
    due_at: null, urgency_tier: null, source: 'dispatcher',
    accepted_at: '2026-10-19T12:00:00Z', parent_task_id: null, sort_order: 0,
    created_at: '2026-10-19T12:00:00Z', updated_at: '2026-10-19T12:00:00Z',
    ...extra,
  };
}
const WITH_TASK = { ...MOCK_REQUEST, status: 'open', tasks: [task(7)] };
const JEAN = { employee_id: 14, nom_employe: 'Jean Tech', role: 'technician', is_en_route: false };

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

async function openDetailTab(id: 'call' | 'tenant' | 'tasks' | 'history') {
  await userEvent.click(screen.getByTestId(`detail-tab-${id}`));
}

describe('DetailPanel', () => {
  it('renders detail-panel testid', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: true, isError: false, error: null });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    expect(screen.getByTestId('detail-panel')).toBeTruthy();
  });

  it('shows Call / Tenant / History tabs; Tasks only for editors', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({
      data: MOCK_REQUEST, isPending: false, isError: false, error: null,
    });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.getByTestId('detail-tabs')).toBeTruthy();
    expect(screen.getByTestId('detail-tab-call')).toBeTruthy();
    expect(screen.getByTestId('detail-tab-tenant')).toBeTruthy();
    expect(screen.getByTestId('detail-tab-history')).toBeTruthy();
    expect(screen.queryByTestId('detail-tab-tasks')).toBeNull();
    expect(screen.getByTestId('tab-panel-call').hidden).toBe(false);
    expect(screen.getByTestId('tab-panel-tenant').hidden).toBe(true);

    await openDetailTab('tenant');
    expect(screen.getByTestId('tab-panel-tenant').hidden).toBe(false);
    expect(screen.getByTestId('tab-panel-call').hidden).toBe(true);

    await openDetailTab('history');
    expect(screen.getByTestId('tab-panel-history').hidden).toBe(false);
  });

  it('shows Tasks tab for coordinators and keeps editors mounted when switching away', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({
      data: WITH_TASK, isPending: false, isError: false, error: null,
    });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />);
    expect(screen.getByTestId('detail-tab-tasks')).toBeTruthy();
    expect(screen.getByTestId('tab-panel-tasks').hidden).toBe(true);

    await openDetailTab('tasks');
    expect(screen.getByTestId('tab-panel-tasks').hidden).toBe(false);
    expect(screen.getByTestId('new-task-btn')).toBeTruthy();

    await openDetailTab('call');
    // Still in the DOM (hidden) so TaskEditor state survives.
    expect(screen.getByTestId('tab-panel-tasks').hidden).toBe(true);
    expect(screen.getByTestId('new-task-btn')).toBeTruthy();
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
    vi.spyOn(client, 'dispatchSave').mockRejectedValue(new ApiError('STALE_DATA', 'stale'));
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    fireEvent.change(screen.getByTestId('next-steps-input'), { target: { value: 'Commander la pièce' } });
    fireEvent.keyDown(screen.getByTestId('next-steps-input'), { key: 'Enter' });
    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith('Dégât d’eau actif chez le locataire');
    await waitFor(() => expect(screen.getByText(/La demande a été modifiée/)).toBeTruthy());
  });

  it('assigning a task goes to POST /tasks/{id}/assign with the justification', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: WITH_TASK, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    const assign = vi.spyOn(client, 'assignTask').mockResolvedValue(task(7, { assigned_employee_id: 14 }) as never);
    const schedule = vi.spyOn(client, 'scheduleTask').mockResolvedValue(task(7) as never);
    const save = vi.spyOn(client, 'dispatchSave');
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    render(
      <QueryClientProvider client={qc}>
        <JustificationProvider lang="fr">
          <DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />
        </JustificationProvider>
      </QueryClientProvider>
    );
    await waitFor(() => expect(screen.getByTestId('task-assign-7').querySelectorAll('option').length).toBeGreaterThan(1));
    await userEvent.selectOptions(screen.getByTestId('task-assign-7'), '14');
    expect(assign).not.toHaveBeenCalled();
    expect((screen.getByTestId('save-btn') as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByTestId('task-save-7')).toBeNull();
    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith();
    await waitFor(() => expect(assign).toHaveBeenCalledWith(7, {
      assigned_employee_id: 14,
      justification: { text: 'Technicien le plus proche du secteur.', input_method: 'typed' },
    }));
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['request', 1] }))
    );
    expect(schedule).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId('panel-success').textContent).toMatch(/Enregistré/));
  });

  it('shows full suggestion cards in « Nouvelle tâche » and compact chips per task', async () => {
    const twoTasks = {
      ...MOCK_REQUEST,
      status: 'open',
      tasks: [task(7), task(8, { description: 'Tâche 8' })],
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({
      data: twoTasks, isPending: false, isError: false, error: null,
    });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    vi.spyOn(client, 'fetchTechnicianSuggestions').mockResolvedValue({
      request_id: 1,
      suggestions: [{
        employee_id: 14, initials: 'JT', name: 'Jean Tech',
        why: 'Historoire immeuble', is_en_route: false,
      }],
    });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />);
    await waitFor(() => expect(screen.getByTestId('new-task-suggest')).toBeTruthy());
    // Full cards once (right); a compact chip row on each existing task.
    expect(screen.getAllByText('Suggestion technicien')).toHaveLength(1);
    expect(screen.getByTestId('task-suggest-7')).toBeTruthy();
    expect(screen.getByTestId('task-suggest-8')).toBeTruthy();

    // A chip assigns that task only and shows as picked.
    const chip = screen.getByTestId('task-suggest-7-14');
    await userEvent.click(chip);
    expect((screen.getByTestId('task-assign-7') as HTMLSelectElement).value).toBe('14');
    expect((screen.getByTestId('task-assign-8') as HTMLSelectElement).value).toBe('');
    expect(chip.getAttribute('aria-pressed')).toBe('true');

    await userEvent.click(screen.getByTestId('new-task-suggest-14'));
    expect((screen.getByTestId('new-task-assign') as HTMLSelectElement).value).toBe('14');
  });

  it('adds a task with assignee and due date via POST /tasks', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: WITH_TASK, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    const create = vi.spyOn(client, 'createTask').mockResolvedValue(task(8) as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />);
    expect((screen.getByTestId('new-task-btn') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId('new-task-name'), { target: { value: 'Remplacer le robinet' } });
    await waitFor(() => expect(screen.getByTestId('new-task-assign').querySelectorAll('option').length).toBeGreaterThan(1));
    await userEvent.selectOptions(screen.getByTestId('new-task-assign'), '14');
    fireEvent.change(screen.getByTestId('new-task-due'), { target: { value: '2026-11-02' } });
    await userEvent.click(screen.getByTestId('new-task-btn'));
    await justifyWith('Deuxième corps de métier requis');
    await waitFor(() => expect(create).toHaveBeenCalledWith({
      request_id: 1,
      description: 'Remplacer le robinet',
      assigned_employee_id: 14,
      due_at: '2026-11-02T08:00:00',
      parent_task_id: null,
      justification: { text: 'Deuxième corps de métier requis.', input_method: 'typed' },
    }));
  });

  it('« Redispatcher » on a needs_expertise task creates the child with parent_task_id', async () => {
    const req = { ...MOCK_REQUEST, status: 'open', tasks: [task(5, { status: 'needs_expertise', description: 'Fuite toiture' })] };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    const create = vi.spyOn(client, 'createTask').mockResolvedValue(task(8) as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />);
    await userEvent.click(screen.getByTestId('task-redispatch-5'));
    expect(screen.getByTestId('new-task-parent').textContent).toContain('Fuite toiture');
    expect((screen.getByTestId('new-task-name') as HTMLInputElement).value).toBe('Fuite toiture');
    await userEvent.click(screen.getByTestId('new-task-btn'));
    await justifyWith('Couvreur requis pour la toiture');
    await waitFor(() => expect(create).toHaveBeenCalledWith(expect.objectContaining({
      request_id: 1, description: 'Fuite toiture', parent_task_id: 5,
    })));
  });

  it('no « Redispatcher » once the task has a follow-up child', () => {
    const req = { ...MOCK_REQUEST, status: 'open', tasks: [
      task(5, { status: 'return_visit' }),
      task(6, { status: 'queued', parent_task_id: 5 }),
    ] };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />);
    expect(screen.queryByTestId('task-redispatch-5')).toBeNull();
  });

  it('« Créer suivi » on a done task posts the follow-up without a justification prompt', async () => {
    const req = { ...MOCK_REQUEST, status: 'open', tasks: [task(5, { status: 'done' }), task(7)] };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const followUp = vi.spyOn(client, 'followUpTask').mockResolvedValue(task(8, { source: 'follow_up', parent_task_id: 5 }) as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />);
    expect(screen.queryByTestId('task-follow-up-7')).toBeNull(); // queued: not offered
    await userEvent.click(screen.getByTestId('task-follow-up-5'));
    await waitFor(() => expect(followUp).toHaveBeenCalledWith(5));
    expect(screen.queryByTestId('justification-dialog')).toBeNull();
  });

  it('no « Créer suivi » once the task already has a follow-up child', () => {
    const req = { ...MOCK_REQUEST, status: 'open', tasks: [
      task(5, { status: 'needs_expertise' }),
      task(6, { status: 'queued', parent_task_id: 5, source: 'follow_up' }),
    ] };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />);
    expect(screen.queryByTestId('task-follow-up-5')).toBeNull();
  });

  const COORD = { employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse;
  const proposalsReq = (status = 'triage_proposal', extra: Record<string, unknown>[] = []) => ({
    ...MOCK_REQUEST, status, triage_model_version: 'claude-sonnet-4-6',
    tasks: [
      task(9, { accepted_at: null, source: 'ai_recommended', description: 'Proposé par IA' }),
      task(10, { accepted_at: null, source: 'ai_recommended', description: 'Autre proposition' }),
      ...extra,
    ],
  });

  const FEEDBACK_OK = {
    feedback_id: 1, request_id: 1, employee_id: 4, level: 'utile' as const, reason: null,
    triage_output: {}, triage_model_version: 'claude-sonnet-4-6', edit_history: [],
    created_at: '2026-10-19T00:00:00Z', updated_at: '2026-10-19T00:00:00Z',
  };

  it('proposals are listed with reject; dispatch is via AI feedback', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: proposalsReq(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={COORD} />);
    expect((screen.getByTestId('new-task-desc') as HTMLTextAreaElement).disabled).toBe(false);
    expect((screen.getByTestId('proposal-desc-9') as HTMLTextAreaElement).value).toBe('Proposé par IA');
    expect(screen.queryByTestId('proposal-accept-9')).toBeNull();
    expect(screen.getByTestId('proposal-reject-9')).toBeTruthy();
    expect(screen.queryByTestId('proposals-accept-all')).toBeNull();
    // The AI card has no button of its own: picking a rating turns the
    // popup's single footer button into « Enregistrer et dispatcher ».
    await waitFor(() => expect(screen.getByTestId('feedback-level-utile')).toBeTruthy());
    expect(screen.queryByTestId('feedback-dispatch')).toBeNull();
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    expect(screen.getByTestId('save-btn').textContent).toBe('Enregistrer et dispatcher');
  });

  it('Dispatch (utile) saves feedback then accepts every proposal', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: proposalsReq(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    const upsert = vi.spyOn(client, 'upsertFeedback').mockResolvedValue(FEEDBACK_OK);
    const accept = vi.spyOn(client, 'acceptTask').mockResolvedValue(task(9) as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={COORD} />);
    await waitFor(() => screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(upsert).toHaveBeenCalledWith(1, { level: 'utile', reason: null }));
    await waitFor(() => {
      expect(accept).toHaveBeenCalledWith(9, {});
      expect(accept).toHaveBeenCalledWith(10, {});
    });
  });

  it('Dispatch applies edited proposal fields', async () => {
    const req = {
      ...MOCK_REQUEST, status: 'triage_proposal', triage_model_version: 'claude-sonnet-4-6',
      tasks: [
        task(9, {
          accepted_at: null, source: 'ai_recommended', description: 'Fuite',
          subcontractor_name: 'Fortin', urgency_tier: 'URGENT',
        }),
      ],
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    vi.spyOn(client, 'upsertFeedback').mockResolvedValue(FEEDBACK_OK);
    const accept = vi.spyOn(client, 'acceptTask').mockResolvedValue(task(9) as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={COORD} />);
    await waitFor(() =>
      expect(screen.getByTestId('proposal-assign-9').querySelectorAll('option').length).toBeGreaterThan(1),
    );
    expect(screen.queryByTestId('proposal-sub-9')).toBeNull(); // no subcontractor field
    await userEvent.selectOptions(screen.getByTestId('proposal-assign-9'), '14');
    fireEvent.change(screen.getByTestId('proposal-due-9'), { target: { value: '2026-10-25' } });
    // « Utile » saves and dispatches on its own — no separate « Enregistrer » click.
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    await waitFor(() => expect(accept).toHaveBeenCalledWith(9, {
      assigned_employee_id: 14,
      due_at: '2026-10-25T08:00:00',
    }));
  });

  it('rejects one proposal', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: proposalsReq(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    const reject = vi.spyOn(client, 'rejectTask').mockResolvedValue(undefined);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={COORD} />);
    await userEvent.click(screen.getByTestId('proposal-reject-10'));
    await waitFor(() => expect(reject).toHaveBeenCalledWith(10));
  });

  it('reject all warns that the call returns to clarification, and only runs when confirmed', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: proposalsReq(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const rejectAll = vi.spyOn(client, 'rejectAllTasks').mockResolvedValue({ request_id: 1, status: 'triage_clarify', rejected: 2 });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={COORD} />);
    await userEvent.click(screen.getByTestId('proposals-reject-all'));
    expect(confirm.mock.calls[0][0]).toMatch(/clarification/);
    expect(rejectAll).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId('proposals-reject-all'));
    await waitFor(() => expect(rejectAll).toHaveBeenCalledWith(1));
    confirm.mockRestore();
  });

  it('proposals on an open call: no clarify warning', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: proposalsReq('open', [task(7)]), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={COORD} />);
    expect((screen.getByTestId('new-task-desc') as HTMLTextAreaElement).disabled).toBe(false);
    await userEvent.click(screen.getByTestId('proposals-reject-all'));
    expect(confirm.mock.calls[0][0]).not.toMatch(/clarification/);
    confirm.mockRestore();
  });

  it('adds a dispatcher task during triage_proposal via POST /tasks', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: proposalsReq(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const create = vi.spyOn(client, 'createTask').mockResolvedValue(task(11) as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={COORD} />);
    fireEvent.change(screen.getByTestId('new-task-name'), { target: { value: 'Inspection du toit' } });
    await userEvent.click(screen.getByTestId('new-task-btn'));
    await justifyWith('Le problème décrit exige une inspection');
    await waitFor(() => expect(create).toHaveBeenCalledWith(expect.objectContaining({
      request_id: 1, description: 'Inspection du toit', parent_task_id: null,
    })));
  });

  it('shows the API error when Dispatch accept fails', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: proposalsReq(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    vi.spyOn(client, 'upsertFeedback').mockResolvedValue(FEEDBACK_OK);
    vi.spyOn(client, 'acceptTask').mockRejectedValue(new ApiError('CONFLICT', 'Task is already accepted'));
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={COORD} />);
    await waitFor(() => screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('feedback-error').textContent).toMatch(/already accepted|déjà/i));
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

  it('disables edit controls when status is closed', async () => {
    const closedReq = { ...WITH_TASK, status: 'closed' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: closedReq, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    expect((screen.getByTestId('task-assign-7') as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByTestId('new-task-desc') as HTMLTextAreaElement).disabled).toBe(true);
    // Closed call: the steps list is read-only, with no « add a step » field.
    expect(screen.queryByTestId('next-steps-input')).toBeNull();
    expect(screen.queryByTestId('log-text')).toBeNull();
  });

  it('formats entry_date as short month + day without timezone shift', async () => {
    const reqWithLog = {
      ...MOCK_REQUEST,
      followup_log: [{ followup_id: 1, entry_date: '2026-10-15', entered_by_initials: 'AB', entry_text: 'Test log' }],
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: reqWithLog, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="en" me={null} />);
    await openDetailTab('history');
    // '2026-10-15' must render as 'Oct 15' (en-CA short) — not as '2026-10-15' raw string
    expect(screen.getByText(/\bOct[\s.]?\s*15\b/i)).toBeTruthy();
  });

  it('shows ineligible assignee with translated role label in select', async () => {
    const coordAssigned = { ...MOCK_REQUEST, status: 'open', tasks: [task(7, { assigned_employee_id: 4 })] };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: coordAssigned, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([
      { employee_id: 4, nom_employe: 'Marie Lavoie', role: 'coordinator' , is_en_route: false },
      { employee_id: 14, nom_employe: 'Jean Tech', role: 'technician' , is_en_route: false },
    ]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 5, roles: ['director'] } as any} />);
    await waitFor(() => {
      const sel = screen.getByTestId('task-assign-7') as HTMLSelectElement;
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
      const opt = Array.from(screen.getByTestId('new-task-assign').querySelectorAll('option'))
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

  it('leads with the AI summary; the tenant\'s original words open from « Demande originale »', async () => {
    const withRaw = {
      ...MOCK_REQUEST,
      triage_model_version: 'gpt-4o-mini',
      problem_summary: 'Fuite active sous l’évier de cuisine.',
      raw_caller_body: { entry_permission: 'Accès autorisé (traitement prioritaire)', animals: null, problems: 'ya de leau partout sous levier' },
      entry_permission: 'N/A Non applicable (exemple espace commun)',
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: withRaw, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.getByTestId('issue-summary')).toHaveTextContent('Fuite active sous l’évier de cuisine.');
    expect(screen.queryByTestId('original-request')).toBeNull();
    const toggle = screen.getByTestId('original-toggle');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    const original = screen.getByTestId('original-request');
    expect(within(original).getByText('ya de leau partout sous levier')).toBeTruthy();
    expect(within(original).getByText(/Accès autorisé/)).toBeTruthy();
    expect(screen.queryByTestId('dual-display')).toBeNull();
  });

  it('shows the tenant as a contact card with call and email buttons', () => {
    const req = { ...MOCK_REQUEST, caller_name: 'Sophie Gagnon', caller_phone: '418 555-0142', caller_phone_placeholder: false,
                  caller_email: 'sophie@example.com', caller_email_placeholder: false, caller_type: 'tenant' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    const card = screen.getByTestId('tenant-card');
    expect(within(card).getByText('Sophie Gagnon')).toBeTruthy();
    expect(within(card).getByTestId('avatar')).toHaveTextContent('SG');
    expect(within(card).getByTestId('contact-call')).toHaveAttribute('href', 'tel:4185550142');
    expect(within(card).getByTestId('contact-mail')).toHaveAttribute('href', 'mailto:sophie@example.com');
    expect(screen.getByTestId('unit-card')).toBeTruthy();
  });

  it('shows a clean one-line title without codes or the unit head', () => {
    const req = { ...MOCK_REQUEST, raw_title: 'CHGE AJD 1035-308 Pie XII: Fuite sous évier' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    const h = screen.getByRole('heading', { level: 2 });
    expect(h).toHaveTextContent('Fuite sous évier');
    expect(h).toHaveAttribute('title', 'CHGE AJD 1035-308 Pie XII: Fuite sous évier');
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

  it('does not show Animals on AI interpretation even when values differ', () => {
    const withRaw = {
      ...MOCK_REQUEST,
      triage_model_version: 'gpt-4o-mini',
      raw_caller_body: {
        entry_permission: 'Accès autorisé',
        animals: 'Oui — chien',
        problems: 'Fuite',
      },
      entry_permission: 'Accès autorisé',
      animals: 'Non',
      problems: 'Fuite',
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: withRaw, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.queryByTestId('dual-display')).toBeNull();
    // Still shown on the Location card from lease/caller, not as AI compare.
    expect(screen.getByText('Animaux')).toBeTruthy();
  });

  it('a changed task date goes to POST /tasks/{id}/schedule', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: WITH_TASK, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const schedule = vi.spyOn(client, 'scheduleTask').mockResolvedValue(task(7) as never);
    const assign = vi.spyOn(client, 'assignTask');
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />);

    fireEvent.change(screen.getByTestId('task-due-7'), { target: { value: '2026-11-01' } });
    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith('Locataire demande une date plus tard');

    await waitFor(() => expect(schedule).toHaveBeenCalledWith(7, {
      due_at: '2026-11-01T08:00:00',
      justification: { text: 'Locataire demande une date plus tard.', input_method: 'typed' },
    }));
    expect(assign).not.toHaveBeenCalled();
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
  it('ai-section leaves out the summary bullets (the header already says it)', () => {
    const req = {
      ...MOCK_REQUEST,
      triage_model_version: 'gpt-4',
      problem_summary: 'Fuite sous le lavabo — < 30 min',
      triage_summary: null,
      other_notes: null,
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    // Only a summary: nothing else to show, so no AI card at all.
    expect(screen.queryByTestId('ai-notes-summary')).toBeNull();
    expect(screen.queryByTestId('ai-section')).toBeNull();
  });

  it('ai-section renders Important / Next as bullet sections', () => {
    const req = {
      ...MOCK_REQUEST,
      triage_model_version: 'gpt-4',
      problem_summary: 'Fuite évier',
      other_notes: null,
      ai_important_notes: ['RÉQUÉRANT ABSENT'],
      ai_next_steps: ["Couper l'eau"],
      ai_reasoning: 'Urgence élevée à cause de l’eau active.',
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={{ employee_id: 4, roles: ['coordinator'] } as any} />);
    expect(screen.getByTestId('ai-notes-important').textContent).toContain('RÉQUÉRANT ABSENT');
    expect(screen.getByTestId('ai-notes-next').textContent).toContain("Couper l'eau");
    // Reasoning stays folded until asked for.
    expect(screen.queryByTestId('ai-reasoning')).toBeNull();
    fireEvent.click(screen.getByTestId('reasoning-toggle'));
    expect(screen.getByTestId('ai-reasoning').textContent).toContain('eau active');
    expect(screen.queryByText(/Notes IA/)).toBeNull();
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

  it('locks an en_route task with the message', async () => {
    const enRouteReq = { ...MOCK_REQUEST, status: 'open', tasks: [task(7, { status: 'en_route', assigned_employee_id: 14 })] };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: enRouteReq, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(
      <DetailPanel requestId={1} onClose={vi.fn()} lang="fr"
        me={{ employee_id: 4, roles: ['coordinator'] } as any} />
    );
    expect((screen.getByTestId('task-assign-7') as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByTestId('task-due-7') as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByTestId('task-locked-7').textContent).toContain(EN_ROUTE_MSG);
    expect(screen.queryByTestId('task-save-7')).toBeNull();
    expect(screen.queryByTestId('task-cancel-7')).toBeNull();
    // Call notes stay usable while a task is in progress.
    expect((screen.getByTestId('next-steps-input') as HTMLTextAreaElement).disabled).toBe(false);
  });

  it('shows the message when the API returns 409 ASSIGNEE_EN_ROUTE', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: WITH_TASK, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    vi.spyOn(client, 'assignTask').mockRejectedValue(new ApiError('ASSIGNEE_EN_ROUTE', 'busy'));
    wrap(
      <DetailPanel requestId={1} onClose={vi.fn()} lang="fr"
        me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />
    );
    await waitFor(() =>
      expect(screen.getByTestId('task-assign-7').querySelectorAll('option').length).toBeGreaterThan(1)
    );
    await userEvent.selectOptions(screen.getByTestId('task-assign-7'), '14');
    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith();
    await waitFor(() => expect(screen.getByText(/Technicien déjà en route/)).toBeTruthy());
  });
});

describe('cancel task', () => {
  it('shows Annuler on a queued task and posts the justification', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: WITH_TASK, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    const cancel = vi.spyOn(client, 'cancelTask').mockResolvedValue(task(7, { status: 'cancelled' }) as never);
    wrap(
      <DetailPanel requestId={1} onClose={vi.fn()} lang="fr"
        me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />
    );
    await userEvent.click(screen.getByTestId('task-cancel-7'));
    await justifyWith('Le problème est tombé');
    await waitFor(() => expect(cancel).toHaveBeenCalledWith(7, {
      justification: { text: 'Le problème est tombé.', input_method: 'typed' },
    }));
  });

  it('shows Annuler for needs_expertise and return_visit', () => {
    const req = {
      ...MOCK_REQUEST, status: 'open',
      tasks: [task(5, { status: 'needs_expertise' }), task(6, { status: 'return_visit' })],
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(
      <DetailPanel requestId={1} onClose={vi.fn()} lang="fr"
        me={{ employee_id: 4, roles: ['coordinator'] } as unknown as MeResponse} />
    );
    expect(screen.getByTestId('task-cancel-5').textContent).toBe('Annuler');
    expect(screen.getByTestId('task-cancel-6').textContent).toBe('Annuler');
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

describe('single footer save (notes + AI feedback)', () => {
  const coordMe = { employee_id: 4, nom_employe: 'Coord', roles: ['coordinator'] } as unknown as MeResponse;
  const req = () => ({ ...MOCK_REQUEST, triage_model_version: 'v1', problem_summary: 'Résumé', tasks: [] });
  const FEEDBACK_OK = {
    feedback_id: 1, request_id: 1, employee_id: 4, level: 'utile' as const, reason: null,
    triage_output: {}, triage_model_version: 'claude-sonnet-4-6', edit_history: [],
    created_at: '2026-10-19T00:00:00Z', updated_at: '2026-10-19T00:00:00Z',
  };

  it('call notes sit right under Planification, and the AI feedback sits in the footer', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'none'));
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coordMe} />);
    const planning = screen.getByRole('heading', { name: 'Planification' }).closest('section')!;
    const notes = screen.getByTestId('edit-controls');
    expect(planning.nextElementSibling).toBe(notes);
    const bar = screen.getByTestId('save-bar');
    expect(within(bar).getByTestId('feedback-level-utile')).toBeTruthy();
    expect(within(bar).getByTestId('save-btn')).toBeTruthy();
    // The save bar is the popup's footer, not part of the notes card.
    expect(notes.contains(screen.getByTestId('save-bar'))).toBe(false);
  });

  it('a feedback-only change saves from the footer without a justification', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'none'));
    const upsert = vi.spyOn(client, 'upsertFeedback').mockResolvedValue(FEEDBACK_OK);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coordMe} />);
    await waitFor(() => screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    expect(screen.getByTestId('save-bar').textContent).toMatch(/1 modification non enregistrée/);
    await userEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(upsert).toHaveBeenCalledWith(1, { level: 'utile', reason: null }));
    expect(screen.queryByTestId('justification-dialog')).toBeNull();
  });

  it('« pas utile » without its comment blocks the save', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'none'));
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coordMe} />);
    await waitFor(() => screen.getByTestId('feedback-level-pas-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-pas-utile'));
    expect((screen.getByTestId('save-btn') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId('save-bar').textContent).toMatch(/ajoutez un commentaire/);
    fireEvent.change(screen.getByTestId('feedback-reason'), { target: { value: 'Le résumé oublie la fuite' } });
    expect((screen.getByTestId('save-btn') as HTMLButtonElement).disabled).toBe(false);
  });

  it('notes + feedback: one justification, notes saved first, then the feedback', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req(), isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'none'));
    const order: string[] = [];
    vi.spyOn(client, 'dispatchSave').mockImplementation(async () => { order.push('notes'); return MOCK_REQUEST as unknown as RequestDetail; });
    vi.spyOn(client, 'upsertFeedback').mockImplementation(async () => { order.push('feedback'); return FEEDBACK_OK; });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coordMe} />);
    await userEvent.click(screen.getByTestId('edit-planning-toggle'));
    fireEvent.change(screen.getByTestId('cost-input'), { target: { value: '250' } });
    await waitFor(() => screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    expect(screen.getByTestId('save-bar').textContent).toMatch(/2 modifications non enregistrées/);
    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith('Soumission du plombier reçue');
    await waitFor(() => expect(order).toEqual(['notes', 'feedback']));
  });
});

describe('decision justification (system-wide)', () => {
  const coord = { employee_id: 4, nom_employe: 'Coord', roles: ['coordinator'] } as unknown as MeResponse;
  const ok = MOCK_REQUEST as unknown as RequestDetail;

  it('cancelling the prompt saves nothing and keeps the task edit', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: WITH_TASK, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    const assign = vi.spyOn(client, 'assignTask');
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);
    await waitFor(() =>
      expect(screen.getByTestId('task-assign-7').querySelectorAll('option').length).toBeGreaterThan(1)
    );
    await userEvent.selectOptions(screen.getByTestId('task-assign-7'), '14');
    await userEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('justification-dialog')).toBeTruthy());
    expect(screen.getByTestId('justification-dialog').textContent).toContain('Jean Tech');
    await userEvent.click(within(screen.getByTestId('justification-dialog')).getByRole('button', { name: 'Annuler' }));
    await waitFor(() => expect(screen.queryByTestId('justification-dialog')).toBeNull());
    expect(assign).not.toHaveBeenCalled();
    expect((screen.getByTestId('task-assign-7') as HTMLSelectElement).value).toBe('14');
  });
  it('confirm stays disabled under 10 characters', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);
    fireEvent.change(screen.getByTestId('next-steps-input'), { target: { value: 'Commander la pièce' } });
    fireEvent.keyDown(screen.getByTestId('next-steps-input'), { key: 'Enter' });
    await userEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('justification-dialog')).toBeTruthy());
    const confirm = screen.getByTestId('justification-confirm') as HTMLButtonElement;
    fireEvent.change(screen.getByTestId('justification-text'), { target: { value: 'trop court'.slice(0, 9) } });
    expect(confirm.disabled).toBe(true);
    fireEvent.change(screen.getByTestId('justification-text'), { target: { value: 'Dégât d’eau actif' } });
    expect(confirm.disabled).toBe(false);
  });
  it('next steps and cost go out in ONE save with ONE justification', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const save = vi.spyOn(client, 'dispatchSave').mockResolvedValue(ok);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);

    fireEvent.change(screen.getByTestId('next-steps-input'), { target: { value: 'Commander la pièce' } });
    fireEvent.keyDown(screen.getByTestId('next-steps-input'), { key: 'Enter' });
    await userEvent.click(screen.getByTestId('edit-planning-toggle'));
    fireEvent.change(screen.getByTestId('cost-input'), { target: { value: '250' } });
    expect(screen.getByTestId('save-bar').textContent).toMatch(/2 modifications non enregistrées/);

    await userEvent.click(screen.getByTestId('save-btn'));
    await waitFor(() => expect(screen.getByTestId('justification-changes').querySelectorAll('li')).toHaveLength(2));
    await justifyWith('Dégât d’eau actif chez le locataire');
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith(1, expect.objectContaining({
      changes: {
        next_steps: 'Commander la pièce',
        estimated_cost: 250,
      },
      justification: expect.objectContaining({ input_method: 'typed' }),
    }));
  });
  it('corrected call details (title, caller) save in the same « Enregistrer » with a stale snapshot', async () => {
    const req = { ...MOCK_REQUEST, raw_title: 'Fuite', caller_name: 'Jean Tremblay', caller_phone_placeholder: false,
                  caller_phone: '418 555-0100' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const save = vi.spyOn(client, 'dispatchSave').mockResolvedValue(ok);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);

    await userEvent.click(screen.getByTestId('edit-title-toggle'));
    fireEvent.change(screen.getByTestId('edit-raw_title'), { target: { value: 'Fuite sous l’évier' } });
    await userEvent.click(screen.getByTestId('edit-caller-toggle'));
    fireEvent.change(screen.getByTestId('edit-caller_name'), { target: { value: 'Jeanne Tremblay' } });
    expect(screen.getByTestId('save-bar').textContent).toMatch(/2 modifications non enregistrées/);

    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith('Correction du nom au téléphone');
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith(1, expect.objectContaining({
      changes: { raw_title: 'Fuite sous l’évier', caller_name: 'Jeanne Tremblay' },
      current: expect.objectContaining({ raw_title: 'Fuite', caller_name: 'Jean Tremblay' }),
    }));
  });

  it('header shows the ASNU, never the internal call id', () => {
    const req = { ...MOCK_REQUEST, request_id: 135, asnu: 'A-2041' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={135} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.getByTestId('header-asnu').textContent).toBe('A-2041');
    expect(screen.queryByText('#135')).toBeNull();
  });

  it('task urgency saves via updateTask; no subcontractor field to edit', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: WITH_TASK, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    const upd = vi.spyOn(client, 'updateTask').mockResolvedValue(task(7) as never);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);
    await waitFor(() => expect(screen.getByTestId('task-urgency-7')).toBeTruthy());
    await userEvent.selectOptions(screen.getByTestId('task-urgency-7'), 'URGENT');
    expect(screen.queryByTestId('task-sub-7')).toBeNull();
    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith('Urgence élevée, Fortin disponible');
    await waitFor(() => expect(upd).toHaveBeenCalledWith(7, expect.objectContaining({
      urgency_tier: 'URGENT',
    })));
  });

  it('asks before closing with unsaved changes', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: MOCK_REQUEST, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const onClose = vi.fn();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    wrap(<DetailPanel requestId={1} onClose={onClose} lang="fr" me={coord} />);
    fireEvent.change(screen.getByTestId('next-steps-input'), { target: { value: 'Note' } });
    fireEvent.keyDown(screen.getByTestId('next-steps-input'), { key: 'Enter' });
    await userEvent.click(screen.getByRole('button', { name: 'Fermer' }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    confirmSpy.mockReturnValue(true);
    await userEvent.click(screen.getByRole('button', { name: 'Fermer' }));
    expect(onClose).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});

describe('Planning card: editable from triage, view-only from the task table', () => {
  const coord = { employee_id: 4, nom_employe: 'Coord', roles: ['coordinator'] } as unknown as MeResponse;
  const ok = MOCK_REQUEST as unknown as RequestDetail;

  it('from the task table only the task card is editable: no pencils, planning as text, no AI feedback', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: { ...WITH_TASK, estimated_cost: 250 }, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} readOnly />);
    expect(screen.queryByTestId('planning-form')).toBeNull();
    expect(screen.queryByTestId('edit-controls')).toBeNull();
    expect(screen.queryByTestId('edit-title-toggle')).toBeNull();
    expect(screen.queryByTestId('feedback-level-utile')).toBeNull();
    // The task card works as it always did, with the save bar for its edits.
    expect(screen.getByTestId('task-assign-7')).not.toBeDisabled();
    expect(screen.getByTestId('save-bar')).toBeTruthy();
    // Cost now reads in the planning card.
    expect(screen.getByText('Coût estimé')).toBeTruthy();
  });

  it('from triage every planning field is editable; urgency applies to the open tasks, estimate + cost to the call', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: WITH_TASK, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([JEAN]);
    const update = vi.spyOn(client, 'updateTask').mockResolvedValue(task(7) as never);
    const save = vi.spyOn(client, 'dispatchSave').mockResolvedValue(ok);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);

    // Read-only until the pencil is pressed, like the other cards.
    expect(screen.queryByTestId('planning-form')).toBeNull();
    await userEvent.click(screen.getByTestId('edit-planning-toggle'));
    const form = screen.getByTestId('planning-form');
    expect(within(form).getByTestId('cost-input')).toBeTruthy();
    expect(screen.getByTestId('edit-controls').querySelector('[data-testid="cost-input"]')).toBeNull();

    await userEvent.selectOptions(screen.getByTestId('plan-urgency'), 'URGENT');
    await userEvent.selectOptions(screen.getByTestId('plan-estimate'), 'H1_TO_2H');
    fireEvent.change(screen.getByTestId('cost-input'), { target: { value: '300' } });
    expect(screen.getByTestId('save-bar').textContent).toMatch(/3 modifications non enregistrées/);

    await userEvent.click(screen.getByTestId('save-btn'));
    await justifyWith('Dégât d’eau actif chez le locataire');
    await waitFor(() => expect(update).toHaveBeenCalledWith(7, expect.objectContaining({ urgency_tier: 'URGENT' })));
    await waitFor(() => expect(save).toHaveBeenCalledWith(1, expect.objectContaining({
      changes: { time_estimate_bucket: 'H1_TO_2H', estimated_cost: 300 },
    })));
  });
});

describe('Notes tab', () => {
  const coord = { employee_id: 4, nom_employe: 'Coord', roles: ['coordinator'] } as unknown as MeResponse;

  it('lists the notes newest first and adds one from the composer', async () => {
    const req = {
      ...MOCK_REQUEST,
      followup_log: [
        { followup_id: 1, entry_date: '2026-10-20', entered_by_initials: 'JB', entry_text: 'Locataire avisée.' },
        { followup_id: 2, entry_date: '2026-10-22', entered_by_initials: 'CL', entry_text: 'Pièce commandée.' },
      ],
    };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const add = vi.spyOn(client, 'dispatchAddLog').mockResolvedValue(req as unknown as RequestDetail);
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={coord} />);

    expect(screen.queryByTestId('call-notes')).toBeNull();
    await userEvent.click(screen.getByTestId('tab-notes'));
    expect(screen.getByTestId('tab-notes')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByTestId('note').map((n) => n.textContent)).toEqual([
      expect.stringContaining('Pièce commandée.'), expect.stringContaining('Locataire avisée.'),
    ]);
    await userEvent.type(screen.getByTestId('note-draft'), 'Rappeler demain matin');
    await userEvent.click(screen.getByTestId('note-add'));
    await waitFor(() => expect(add).toHaveBeenCalledWith(1, { entry_text: 'Rappeler demain matin' }));
  });

  it('shows the unit number without the building address', () => {
    const req = { ...MOCK_REQUEST, unit_label: null, unique_unit_number: '1580-204 Perigord' };
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: req, isPending: false, isError: false, error: null });
    wrap(<DetailPanel requestId={1} onClose={vi.fn()} lang="fr" me={null} />);
    expect(screen.getByTestId('unit-number').textContent?.trim()).toBe('204');
  });
});
