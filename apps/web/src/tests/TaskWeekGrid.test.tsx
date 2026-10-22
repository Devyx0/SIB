import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import type { TaskListItem } from '../api/schema.d.ts';
import TaskWeekGrid from '../pages/DispatchBoard/TaskWeekGrid';

function taskRow(id: number, extra: Partial<TaskListItem> = {}): TaskListItem {
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

describe('TaskWeekGrid', () => {
  it('renders the task on its due day', () => {
    render(
      <TaskWeekGrid
        lang="fr"
        weekStart="2026-09-07"
        datedRows={[taskRow(1, { description: 'Fuite cuisine' })]}
        undatedRows={[]}
        selectedTaskId={null}
        onSelect={vi.fn()}
        onShiftWeek={vi.fn()}
        onToday={vi.fn()}
      />,
    );
    const day = screen.getByTestId('day-2026-09-10');
    expect(within(day).getByText('Fuite cuisine')).toBeTruthy();
    expect(within(screen.getByTestId('day-2026-09-09')).queryByText('Fuite cuisine')).toBeNull();
  });

  it('puts undated tasks in Sans date', () => {
    render(
      <TaskWeekGrid
        lang="fr"
        weekStart="2026-09-07"
        datedRows={[]}
        undatedRows={[taskRow(2, { description: 'Sans échéance', status: 'queued', due_at: null })]}
        selectedTaskId={null}
        onSelect={vi.fn()}
        onShiftWeek={vi.fn()}
        onToday={vi.fn()}
      />,
    );
    expect(within(screen.getByTestId('sans-date')).getByText('Sans échéance')).toBeTruthy();
  });

  it('calls onSelect when a chip is clicked', async () => {
    const onSelect = vi.fn();
    const row = taskRow(1, { description: 'Fuite' });
    render(
      <TaskWeekGrid
        lang="fr"
        weekStart="2026-09-07"
        datedRows={[row]}
        undatedRows={[]}
        selectedTaskId={null}
        onSelect={onSelect}
        onShiftWeek={vi.fn()}
        onToday={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByTestId('cal-task-1'));
    expect(onSelect).toHaveBeenCalledWith(row);
  });
});
