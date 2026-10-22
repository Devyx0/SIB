import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DispatchBoard from '../pages/DispatchBoard';
import type { BoardMode } from '../api/boardModes';

const mocks = vi.hoisted(() => ({
  fetchRequests: vi.fn(),
  fetchTasks: vi.fn(),
  fetchRequest: vi.fn(),
}));

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchRequests: mocks.fetchRequests,
  fetchTasks: mocks.fetchTasks,
  fetchRequest: mocks.fetchRequest,
  fetchSectors: vi.fn().mockResolvedValue([]),
  fetchEmployees: vi.fn().mockResolvedValue([]),
  fetchBuildings: vi.fn().mockResolvedValue([]),
}));

const me = { employee_id: 4, nom_employe: 'Coordo', roles: ['coordinator'] } as never;

function taskRow(id: number, extra: Record<string, unknown> = {}) {
  return {
    task_id: id, request_id: 100 + id, description: `Tâche ${id}`, status: 'scheduled',
    assigned_employee_id: 14, vendor_id: null, subcontractor_name: null,
    due_at: '2026-09-10T12:00:00-04:00', urgency_tier: null, source: 'dispatcher',
    accepted_at: '2026-09-01T12:00:00Z', parent_task_id: null, sort_order: 0,
    created_at: '2026-09-01T12:00:00Z', updated_at: '2026-09-01T12:00:00Z',
    assigned_employee_name: 'Jean Tech', request_title: `Appel ${100 + id}`, request_status: 'open',
    request_asnu: null, request_urgency_tier: null, sector_id: 1, territoire: 'Québec',
    building_address: '1 rue Test', unit_label: null,
    ...extra,
  };
}

function wrap(mode: BoardMode, initial: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <QueryClientProvider client={qc}>
        <DispatchBoard lang="fr" me={me} mode={mode} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.fetchRequests.mockReset().mockResolvedValue({ total: 0, items: [], unscheduled_items: [] });
  mocks.fetchTasks.mockReset().mockResolvedValue({ total: 0, items: [] });
  mocks.fetchRequest.mockReset().mockReturnValue(new Promise(() => {}));
});

describe('/tasks board', () => {
  it('tasks mode loads task rows from GET /tasks, not request statuses', async () => {
    mocks.fetchTasks.mockImplementation(async (p: { status?: string[] }) => (
      p.status?.length === 1 && p.status[0] === 'queued'
        ? { total: 0, items: [] }
        : { total: 1, items: [taskRow(1)] }
    ));
    wrap('tasks', '/tasks?start_date=2026-09-01&end_date=2026-09-25');
    await waitFor(() => expect(screen.getByText('Tâche 1')).toBeTruthy());
    expect(mocks.fetchRequests).not.toHaveBeenCalled();
    expect(mocks.fetchTasks).toHaveBeenCalledWith(expect.objectContaining({
      start_date: '2026-09-01', end_date: '2026-09-25',
    }));
    const params = mocks.fetchTasks.mock.calls.find((c) => c[0].start_date)![0];
    expect(params.status).toEqual(expect.arrayContaining(['queued', 'scheduled', 'en_route', 'needs_expertise']));
    expect(params.status).not.toContain('done');
    expect(screen.getByText(/Appel 101/)).toBeTruthy();
    expect(screen.getByText((c) => c.trim() === '1 tâche')).toBeTruthy();
  });

  it('opens on « Tout »: no date window, every task', async () => {
    wrap('tasks', '/tasks');
    await waitFor(() => expect(mocks.fetchTasks).toHaveBeenCalled());
    for (const [p] of mocks.fetchTasks.mock.calls) expect(p.start_date).toBeFalsy();
    expect(screen.getByTestId('quick-range-all').getAttribute('aria-pressed')).toBe('true');
  });

  it('the period is the only date control (no separate day strip)', async () => {
    wrap('tasks', '/tasks?start_date=2026-09-01&end_date=2026-09-25');
    await waitFor(() => expect(mocks.fetchTasks).toHaveBeenCalledWith(expect.objectContaining({
      start_date: '2026-09-01', end_date: '2026-09-25',
    })));
    expect(screen.getByTestId('custom-range-btn')).toBeTruthy();
    expect(screen.queryByTestId('task-day-strip')).toBeNull();
  });

  it('« Tout » keeps undated tasks in their own group, not repeated in the table', async () => {
    mocks.fetchTasks.mockImplementation(async () => ({
      total: 2, items: [taskRow(1), taskRow(2, { status: 'queued', due_at: null })],
    }));
    wrap('tasks', '/tasks');
    const group = await screen.findByTestId('unscheduled-group');
    expect(within(group).getByText('Tâche 2')).toBeTruthy();
    expect(screen.getAllByText('Tâche 2')).toHaveLength(1); // not repeated in the main table
    for (const [p] of mocks.fetchTasks.mock.calls) expect(p.start_date).toBeFalsy();
    expect(screen.getByTestId('quick-range-all').getAttribute('aria-pressed')).toBe('true');
  });

  it('has no « Plus de colonnes » button (only triage has optional columns)', async () => {
    wrap('tasks', '/tasks');
    await waitFor(() => expect(mocks.fetchTasks).toHaveBeenCalled());
    expect(screen.queryByTestId('cols-toggle')).toBeNull();
  });

  it('calendar rests the period control; back to Liste drops the week', async () => {
    wrap('tasks', '/tasks');
    await userEvent.click(await screen.findByTestId('tasks-view-calendar'));
    await waitFor(() => expect(mocks.fetchTasks).toHaveBeenLastCalledWith(
      expect.objectContaining({ start_date: expect.any(String), end_date: expect.any(String) })));
    expect((screen.getByTestId('quick-range-7') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/flèches du calendrier/)).toBeTruthy();

    await userEvent.click(screen.getByTestId('tasks-view-list'));
    await waitFor(() => expect(mocks.fetchTasks.mock.lastCall![0].start_date).toBeFalsy());
    expect(screen.getByTestId('quick-range-all').getAttribute('aria-pressed')).toBe('true');
    expect((screen.getByTestId('quick-range-7') as HTMLButtonElement).disabled).toBe(false);
  });

  it('undated queued tasks show in « Sans date »', async () => {
    mocks.fetchTasks.mockImplementation(async (p: { start_date?: string }) => (
      p.start_date
        ? { total: 1, items: [taskRow(1)] }
        : { total: 2, items: [taskRow(2, { status: 'queued', due_at: null }), taskRow(3, { status: 'queued' })] }
    ));
    wrap('tasks', '/tasks?start_date=2026-09-01&end_date=2026-09-25');
    const group = await screen.findByTestId('unscheduled-group');
    expect(within(group).getByText('Tâche 2')).toBeTruthy();
    // A dated queued task is in the main table, not the undated group.
    expect(within(group).queryByText('Tâche 3')).toBeNull();
  });

  it('« À redispatcher » lists un-followed needs_expertise / return_visit tasks across dates', async () => {
    mocks.fetchTasks.mockResolvedValue({ total: 2, items: [
      taskRow(1, { status: 'needs_expertise', has_followup: false }),
      taskRow(2, { status: 'return_visit', has_followup: true }),
    ] });
    wrap('tasks', '/tasks?redispatch=1');
    await waitFor(() => expect(screen.getByText('Tâche 1')).toBeTruthy());
    expect(screen.queryByText('Tâche 2')).toBeNull();
    const p = mocks.fetchTasks.mock.calls[0][0];
    expect(p.status).toEqual(['needs_expertise', 'return_visit']);
    expect(p.start_date).toBeUndefined();
  });

  it('clicking a task opens its task card; « Voir l\'appel de service » opens the call', async () => {
    mocks.fetchTasks.mockResolvedValue({ total: 1, items: [taskRow(1, { description: 'Tâche 1\nRemplacer le joint du siphon' })] });
    wrap('tasks', '/tasks?start_date=2026-09-01&end_date=2026-09-25');
    await userEvent.click(await screen.findByText('Tâche 1'));
    const card = await screen.findByTestId('task-card');
    expect(within(card).getByRole('heading', { level: 2 })).toHaveTextContent('Tâche 1');
    expect(within(card).getByTestId('task-card-desc')).toHaveTextContent('Remplacer le joint du siphon');
    expect(mocks.fetchRequest).not.toHaveBeenCalled();
    await userEvent.click(within(card).getByTestId('open-call'));
    await waitFor(() => expect(mocks.fetchRequest).toHaveBeenCalledWith(101));
    expect(screen.queryByTestId('task-card')).toBeNull();
  });

  it('search filters task rows client-side', async () => {
    mocks.fetchTasks.mockResolvedValue({
      total: 2, items: [taskRow(1), taskRow(2, { description: 'Peinture salon' })],
    });
    wrap('tasks', '/tasks?start_date=2026-09-01&end_date=2026-09-25&q=peinture');
    await waitFor(() => expect(screen.getByText('Peinture salon')).toBeTruthy());
    expect(screen.queryByText('Tâche 1')).toBeNull();
  });
});

describe('/triage board', () => {
  it('lists Service Calls incl. triage_proposal, never open', async () => {
    wrap('triage', '/triage');
    await waitFor(() => expect(mocks.fetchRequests).toHaveBeenCalled());
    const p = mocks.fetchRequests.mock.calls[0][0];
    expect(p.status).toContain('triage_proposal');
    expect(p.status).toContain('triaged');
    expect(p.status).not.toContain('open');
    expect(mocks.fetchTasks).not.toHaveBeenCalled();
  });
});
