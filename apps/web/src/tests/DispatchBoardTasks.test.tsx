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

  it('the day strip narrows the due-date window to that day', async () => {
    wrap('tasks', '/tasks?start_date=2026-09-01&end_date=2026-09-25&day=2026-09-10');
    await waitFor(() => expect(mocks.fetchTasks).toHaveBeenCalledWith(expect.objectContaining({
      start_date: '2026-09-10', end_date: '2026-09-10',
    })));
    expect(screen.getByTestId('task-day-strip')).toBeTruthy();
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

  it('clicking a task opens its call in the detail panel', async () => {
    mocks.fetchTasks.mockResolvedValue({ total: 1, items: [taskRow(1)] });
    wrap('tasks', '/tasks?start_date=2026-09-01&end_date=2026-09-25');
    await userEvent.click(await screen.findByText('Tâche 1'));
    await waitFor(() => expect(mocks.fetchRequest).toHaveBeenCalledWith(101));
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
