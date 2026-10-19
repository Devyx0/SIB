import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import RequestTable from '../pages/DispatchBoard/RequestTable';
import type { ListRow } from '../api/schema.d.ts';

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
    en_route_at: null,
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

  it('inserts day-header rows when sortBy=start_date', () => {
    const rows = [
      makeRow({ request_id: 1, start_date: '2026-09-10' }),
      makeRow({ request_id: 2, start_date: '2026-09-11' }),
    ];
    render(<RequestTable {...defaultProps} rows={rows} sortBy="start_date" />);
    const headers = screen.getAllByTestId('day-header');
    expect(headers.length).toBe(2);
  });

  it('does NOT insert day-header rows when sortBy != start_date', () => {
    const rows = [
      makeRow({ request_id: 1, start_date: '2026-09-10' }),
      makeRow({ request_id: 2, start_date: '2026-09-11' }),
    ];
    render(<RequestTable {...defaultProps} rows={rows} sortBy="asnu" />);
    expect(screen.queryAllByTestId('day-header').length).toBe(0);
  });

  it('renders AJD row without error', () => {
    render(<RequestTable {...defaultProps} rows={[makeRow({ urgency_tier: 'AJD' })]} />);
    expect(screen.getByText('AJD')).toBeTruthy();
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
