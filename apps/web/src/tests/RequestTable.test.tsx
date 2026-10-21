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
