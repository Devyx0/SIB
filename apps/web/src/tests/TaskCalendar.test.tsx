import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TaskCalendar from '../pages/TaskCalendar';

const mocks = vi.hoisted(() => ({
  fetchTasks: vi.fn(),
}));

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchTasks: mocks.fetchTasks,
}));

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

function wrap(initial = '/tasks/calendar?start_date=2026-09-07') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <QueryClientProvider client={qc}>
        <TaskCalendar lang="fr" />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mocks.fetchTasks.mockReset().mockResolvedValue({ total: 0, items: [] });
});

describe('task week calendar', () => {
  it('renders the task description on its due day', async () => {
    mocks.fetchTasks.mockResolvedValue({
      total: 1,
      items: [taskRow(1, { description: 'Fuite cuisine', due_at: '2026-09-10T12:00:00-04:00' })],
    });
    wrap();
    const day = await screen.findByTestId('day-2026-09-10');
    expect(await within(day).findByText('Fuite cuisine')).toBeTruthy();
    expect(within(screen.getByTestId('day-2026-09-09')).queryByText('Fuite cuisine')).toBeNull();
    await waitFor(() => expect(mocks.fetchTasks).toHaveBeenCalledWith(expect.objectContaining({
      start_date: '2026-09-07',
      end_date: '2026-09-13',
    })));
  });

  it('puts a task with no due date in Sans date', async () => {
    mocks.fetchTasks.mockImplementation(async (p: { start_date?: string }) => (
      p.start_date
        ? { total: 0, items: [] }
        : { total: 1, items: [taskRow(2, { description: 'Sans échéance', status: 'queued', due_at: null })] }
    ));
    wrap();
    const bucket = await screen.findByTestId('sans-date');
    expect(within(bucket).getByText('Sans échéance')).toBeTruthy();
    expect(within(bucket).getByText(/Sans date/)).toBeTruthy();
    expect(screen.getByTestId('day-2026-09-10').textContent).not.toContain('Sans échéance');
  });
});
