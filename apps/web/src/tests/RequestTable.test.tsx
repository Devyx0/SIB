import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import RequestTable from '../pages/DispatchBoard/RequestTable';
import TaskTable, { sortTasks } from '../pages/DispatchBoard/TaskTable';
import type { ListRow, TaskListItem } from '../api/schema.d.ts';

function makeRow(overrides: Partial<ListRow> = {}): ListRow {
  return {
    request_id: 1,
    start_date: '2026-09-10',
    asnu: 'A-001',
    urgency_tier: null,
    urgency_raw: null,
    raw_title: 'Test titre',
    building_id: 1,
    building_address: '123 rue Test',
    building_full_address: '123 rue Test, Québec, G1A 1A1',
    building_name: null,
    sector_id: 1,
    territoire: 'Butler',
    color_code: null,
    assigned_employee_id: 1,
    assigned_employee_name: 'Jean Tremblay',
    subcontractor_name: null,
    time_estimate_bucket: null,
    time_estimate_raw: null,
    source_calendar: 'main',
    source_calendar_label: null,
    status: 'triaged',
    event_id: null,
    estimated_cost: null,
    next_follow_up_date: null,
    next_steps: null,
    last_followup_date: null,
    last_followup_text: null,
    unit_label: null,
    unique_unit_number: null,
    en_route_at: null,
    arrived_at: null,
    closeout_outcome: null,
    closeout_urgent: null,
    duplicate_of_request_id: null,
    addition_to_request_id: null,
    ...overrides,
  };
}

const defaultProps = {
  rows: [],
  selectedId: null,
  sortBy: 'start_date',
  sortDir: 'asc' as const,
  onSort: vi.fn(),
  onSelect: vi.fn(),
  isLoading: false,
  isError: false,
  total: 0,
};

describe('RequestTable', () => {
  it('shows empty state when no rows', () => {
    render(<RequestTable {...defaultProps} />);
    expect(screen.getByText(/Aucun appel/)).toBeTruthy();
  });

  it('shows loading skeletons', () => {
    render(<RequestTable {...defaultProps} isLoading />);
    expect(screen.queryByText(/Aucun appel/)).toBeNull();
  });

  it('shows error state', () => {
    render(<RequestTable {...defaultProps} isError />);
    expect(screen.getByText(/Erreur lors du chargement/)).toBeTruthy();
  });

  it('marks awaiting_redispatch rows as escalated', () => {
    render(<RequestTable {...defaultProps} rows={[makeRow({ status: 'awaiting_redispatch' })]} />);
    expect(screen.getByTestId('request-row').getAttribute('data-escalated')).not.toBeNull();
  });

  it('renders row data', () => {
    render(<RequestTable {...defaultProps} rows={[makeRow()]} />);
    expect(screen.getByText('Test titre')).toBeTruthy();
    expect(screen.getByText('A-001')).toBeTruthy();
    expect(screen.getByText('Jean Tremblay')).toBeTruthy();
  });

  it('calls onSelect when row clicked', async () => {
    const onSelect = vi.fn();
    render(<RequestTable {...defaultProps} rows={[makeRow()]} onSelect={onSelect} />);
    await userEvent.click(screen.getByTestId('request-row'));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('links the building to Google Maps without opening the row', async () => {
    const onSelect = vi.fn();
    render(<RequestTable {...defaultProps} rows={[makeRow()]} onSelect={onSelect} />);
    const link = screen.getByTestId('row-map-link') as HTMLAnchorElement;
    expect(link.textContent).toBe('123 rue Test ↗');
    expect(link.target).toBe('_blank');
    expect(link.href).toContain(encodeURIComponent('123 rue Test, Québec, G1A 1A1'));
    link.addEventListener('click', (e) => e.preventDefault()); // jsdom: no navigation
    await userEvent.click(link);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('shows no map link when the building has no address', () => {
    render(<RequestTable {...defaultProps} rows={[makeRow({ building_address: null, building_full_address: null })]} />);
    expect(screen.queryByTestId('row-map-link')).toBeNull();
  });

  it('inserts day-header rows when sortBy=start_date', () => {
    const rows = [
      makeRow({ request_id: 1, start_date: '2026-09-10' }),
      makeRow({ request_id: 2, start_date: '2026-09-11' }),
    ];
    render(<RequestTable {...defaultProps} rows={rows} sortBy="start_date" />);
    const headers = screen.getAllByTestId('day-header');
    expect(headers.length).toBe(2);
    // 2026-09-10 = Thursday (4), 2026-09-11 = Friday (5)
    expect(headers[0].getAttribute('data-weekday')).toBe('4');
    expect(headers[1].getAttribute('data-weekday')).toBe('5');
  });

  it('always shows subcontractor and est. time columns', () => {
    render(
      <RequestTable
        {...defaultProps}
        rows={[makeRow({ subcontractor_name: 'Duclos', time_estimate_bucket: 'UNDER_30_MIN' })]}
      />,
    );
    expect(screen.getByText('Duclos')).toBeTruthy();
    expect(screen.getByText('< 30 min')).toBeTruthy();
    expect(screen.getByText('Sous-traitant')).toBeTruthy();
    expect(screen.getByText('Durée')).toBeTruthy();
  });

  it('does NOT insert day-header rows when sortBy != start_date', () => {
    const rows = [
      makeRow({ request_id: 1, start_date: '2026-09-10' }),
      makeRow({ request_id: 2, start_date: '2026-09-11' }),
    ];
    render(<RequestTable {...defaultProps} rows={rows} sortBy="asnu" />);
    expect(screen.queryAllByTestId('day-header').length).toBe(0);
  });

  it('renders Urgent row without error', () => {
    render(<RequestTable {...defaultProps} rows={[makeRow({ urgency_tier: 'URGENT' })]} />);
    expect(screen.getByText('Urgent')).toBeTruthy();
  });

  it('shows the category (intake category, else the triaged element)', () => {
    render(<RequestTable {...defaultProps} rows={[
      makeRow({ request_id: 1, category_raw: 'Plomberie' }),
      makeRow({ request_id: 2, category_raw: null, element: 'Chauffage' }),
      makeRow({ request_id: 3 }),
    ]} />);
    expect(screen.getByRole('columnheader', { name: /Catégorie/ })).toBeTruthy();
    expect(screen.getAllByTestId('row-category').map((c) => c.textContent)).toEqual(['Plomberie', 'Chauffage', '—']);
  });

  it('shows the assigned employee with their initials', () => {
    render(<RequestTable {...defaultProps} rows={[makeRow()]} />);
    const row = screen.getByTestId('request-row');
    expect(row.querySelector('[data-testid="avatar"]')?.textContent).toBe('JT');
  });

  it('marks selected row', () => {
    render(<RequestTable {...defaultProps} rows={[makeRow()]} selectedId={1} />);
    const row = screen.getByTestId('request-row');
    expect(row.getAttribute('aria-selected')).toBe('true');
  });
});

describe('en route visibility (stop 2)', () => {
  it('shows a highlighted « En route » status tag — the X prefix equivalent', () => {
    render(
      <RequestTable {...defaultProps} rows={[makeRow({ status: 'en_route' })]} total={1} />
    );
    const tag = screen.getByText('En route');
    expect(tag.getAttribute('data-status')).toBe('en_route');
  });
});

describe('closeout urgent badge (stop 3)', () => {
  it('shows an URGENT badge when closeout_urgent is set', () => {
    render(
      <RequestTable {...defaultProps}
        rows={[makeRow({ status: 'triaged', closeout_urgent: true })]} total={1} />
    );
    expect(screen.getByTestId('closeout-urgent-badge').textContent).toBe('URGENT');
  });

  it('no badge when closeout_urgent is null', () => {
    render(<RequestTable {...defaultProps} rows={[makeRow()]} total={1} />);
    expect(screen.queryByTestId('closeout-urgent-badge')).toBeNull();
  });
});

describe('awaiting_redispatch status pill', () => {
  it('labels awaiting_redispatch as À redispatcher', () => {
    render(
      <RequestTable {...defaultProps} rows={[makeRow({
        status: 'awaiting_redispatch',
        assigned_employee_id: null,
        assigned_employee_name: null,
        closeout_outcome: 'partial_expertise',
      })]} total={1} />,
    );
    const tag = screen.getByText('À redispatcher');
    expect(tag.getAttribute('data-status')).toBe('awaiting_redispatch');
  });
});

function makeTask(overrides: Partial<TaskListItem> = {}): TaskListItem {
  return {
    task_id: 1, request_id: 10, description: 'Plomberie', status: 'scheduled',
    assigned_employee_id: 14, vendor_id: null, subcontractor_name: null,
    due_at: '2026-09-10T12:00:00-04:00', urgency_tier: null, source: 'dispatcher',
    accepted_at: '2026-09-01T12:00:00Z', parent_task_id: null, sort_order: 0,
    created_at: '2026-09-01T12:00:00Z', updated_at: '2026-09-01T12:00:00Z',
    assigned_employee_name: 'Jean Tech', request_title: 'Fuite', request_status: 'open',
    request_asnu: null, request_urgency_tier: 'URGENT', sector_id: 1, territoire: 'Québec',
    building_address: '1 rue Test', unit_label: '3',
    ...overrides,
  };
}

describe('TaskTable', () => {
  const props = {
    selectedTaskId: null, sortBy: 'due_at', sortDir: 'asc' as const,
    onSort: vi.fn(), onSelect: vi.fn(), isLoading: false, isError: false,
  };

  it('renders a task row with its call, task status and the call urgency fallback', () => {
    render(<TaskTable {...props} rows={[makeTask({ request_asnu: 'A-0010' })]} />);
    const row = screen.getByTestId('task-row');
    expect(row.textContent).toContain('Plomberie');
    expect(row.textContent).toContain('A-0010 · Fuite');
    expect(row.textContent).not.toContain('#10');
    expect(row.textContent).toContain('1 rue Test, app. 3');
    expect(row.textContent).toContain('Jean Tech');
    expect(row.textContent).toContain('Planifié');
    expect(row.textContent).toMatch(/urgent/i);
    expect(screen.getByTestId('day-header').textContent).toMatch(/1 tâche/);
  });

  it('marks needs_expertise tasks as escalated', () => {
    render(<TaskTable {...props} rows={[makeTask({ status: 'needs_expertise' })]} />);
    expect(screen.getByTestId('task-row').getAttribute('data-escalated')).toBe('true');
    expect(screen.getByText('Expertise requise')).toBeTruthy();
  });

  it('calls onSelect with the task row', async () => {
    const onSelect = vi.fn();
    const t = makeTask();
    render(<TaskTable {...props} rows={[t]} onSelect={onSelect} />);
    await userEvent.click(screen.getByTestId('task-row'));
    expect(onSelect).toHaveBeenCalledWith(t);
  });

  it('sortTasks keeps missing values last in both directions', () => {
    const rows = [
      makeTask({ task_id: 1, due_at: null }),
      makeTask({ task_id: 2, due_at: '2026-09-12T12:00:00Z' }),
      makeTask({ task_id: 3, due_at: '2026-09-11T12:00:00Z' }),
    ];
    expect(sortTasks(rows, 'due_at', 'asc').map((r) => r.task_id)).toEqual([3, 2, 1]);
    expect(sortTasks(rows, 'due_at', 'desc').map((r) => r.task_id)).toEqual([2, 3, 1]);
  });
});
