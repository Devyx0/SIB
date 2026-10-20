import { render, screen, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import FilterBar from '../pages/DispatchBoard/FilterBar';

const noop = () => {};
const defaultProps = {
  startDate: '2026-09-01',
  endDate: '2026-09-25',
  status: [],
  sourceCalendar: '',
  q: '',
  total: 42,
  onStartDate: noop,
  onEndDate: noop,
  onStatus: noop,
  onSourceCalendar: noop,
  onQ: noop,
};

describe('FilterBar', () => {
  it('renders the request count', () => {
    render(<FilterBar {...defaultProps} total={17} onQ={noop} />);
    expect(screen.getByText(/17 appels/i)).toBeTruthy();
  });

  it('calls onHasSubcontractor when the subcontractor filter changes', async () => {
    const onHasSubcontractor = vi.fn();
    render(<FilterBar {...defaultProps} onHasSubcontractor={onHasSubcontractor} />);
    await userEvent.selectOptions(screen.getByTestId('subcontractor-filter'), 'true');
    expect(onHasSubcontractor).toHaveBeenCalledWith(true);
  });

  it('shows singular for total=1', () => {
    render(<FilterBar {...defaultProps} total={1} onQ={noop} />);
    // textContent is split across nodes; match the span's full content
    expect(screen.getByText((c) => c.trim() === '1 appel')).toBeTruthy();
  });

  it('debounces search input — onQ not called immediately', () => {
    vi.useFakeTimers();
    const onQ = vi.fn();
    render(<FilterBar {...defaultProps} onQ={onQ} />);
    const input = screen.getByTestId('search-input');
    fireEvent.change(input, { target: { value: 'abc' } });
    expect(onQ).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(600); });
    expect(onQ).toHaveBeenCalledWith('abc');
    vi.useRealTimers();
  });

  it('status checkboxes live in a dropdown, hidden until opened', async () => {
    render(<FilterBar {...defaultProps} />);
    expect(screen.queryByText('Reçu')).toBeNull();
    expect(screen.getByTestId('status-select').textContent).toMatch(/Tous les statuts/);
    await userEvent.click(screen.getByTestId('status-select'));
    expect(screen.getByText('Reçu')).toBeTruthy();
    expect(screen.getByText('En triage')).toBeTruthy();
  });

  it('checking a status in the dropdown calls onStatus', async () => {
    const onStatus = vi.fn();
    render(<FilterBar {...defaultProps} status={['triaged']} onStatus={onStatus} />);
    await userEvent.click(screen.getByTestId('status-select'));
    await userEvent.click(screen.getByLabelText('Reçu'));
    expect(onStatus).toHaveBeenCalledWith(['triaged', 'intake_received']);
  });

  it('trigger summarises the selection', () => {
    const { rerender } = render(<FilterBar {...defaultProps} status={['triaged']} />);
    expect(screen.getByTestId('status-select').textContent).toMatch(/Trié/);
    rerender(<FilterBar {...defaultProps} status={['triaged', 'closed']} />);
    expect(screen.getByTestId('status-select').textContent).toMatch(/2 statuts/);
  });

  it('calls onStatus with cleared array when clear is clicked', async () => {
    const onStatus = vi.fn();
    render(<FilterBar {...defaultProps} status={['triaged']} onStatus={onStatus} />);
    await userEvent.click(screen.getByTestId('status-select'));
    await userEvent.click(screen.getByText('Effacer'));
    expect(onStatus).toHaveBeenCalledWith([]);
  });

  it('closes the status dropdown on Escape', async () => {
    render(<FilterBar {...defaultProps} />);
    await userEvent.click(screen.getByTestId('status-select'));
    expect(screen.getByText('Reçu')).toBeTruthy();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByText('Reçu')).toBeNull();
  });

  it('shows a reset link only when filters are active', async () => {
    const onReset = vi.fn();
    const { rerender } = render(<FilterBar {...defaultProps} onReset={onReset} />);
    expect(screen.queryByTestId('reset-filters')).toBeNull();
    rerender(<FilterBar {...defaultProps} onReset={onReset} hasActiveFilters />);
    await userEvent.click(screen.getByTestId('reset-filters'));
    expect(onReset).toHaveBeenCalled();
  });

  it('typing in AU never calls onStartDate (no cross-field clamping)', () => {
    vi.useFakeTimers();
    const onStartDate = vi.fn();
    const onEndDate = vi.fn();
    render(<FilterBar {...defaultProps} onStartDate={onStartDate} onEndDate={onEndDate} />);
    const auInput = screen.getByTestId('end-date-input');
    fireEvent.change(auInput, { target: { value: '2026-08-01' } });
    act(() => { vi.advanceTimersByTime(500); });
    expect(onEndDate).toHaveBeenCalledWith('2026-08-01');
    expect(onStartDate).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('typing in DU never calls onEndDate (no cross-field clamping)', () => {
    vi.useFakeTimers();
    const onStartDate = vi.fn();
    const onEndDate = vi.fn();
    render(<FilterBar {...defaultProps} onStartDate={onStartDate} onEndDate={onEndDate} />);
    const duInput = screen.getByTestId('start-date-input');
    fireEvent.change(duInput, { target: { value: '2026-10-01' } });
    act(() => { vi.advanceTimersByTime(500); });
    expect(onStartDate).toHaveBeenCalledWith('2026-10-01');
    expect(onEndDate).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('shows error when end date is before start date', () => {
    render(<FilterBar {...defaultProps} startDate="2026-09-20" endDate="2026-09-01" />);
    expect(screen.getByTestId('date-range-error')).toBeTruthy();
    expect(screen.getByTestId('date-range-error').textContent).toMatch(/date de fin/i);
  });

  it('shows error when range exceeds 31 days', () => {
    render(<FilterBar {...defaultProps} startDate="2026-09-01" endDate="2026-10-15" />);
    expect(screen.getByTestId('date-range-error')).toBeTruthy();
    expect(screen.getByTestId('date-range-error').textContent).toMatch(/31 jour/i);
  });

  it('shows no error for a valid 31-day range', () => {
    render(<FilterBar {...defaultProps} startDate="2026-09-01" endDate="2026-10-02" />);
    expect(screen.queryByTestId('date-range-error')).toBeNull();
  });

  it('partial date (empty string from browser) never propagates upstream', () => {
    const onStartDate = vi.fn();
    const onEndDate = vi.fn();
    render(<FilterBar {...defaultProps} onStartDate={onStartDate} onEndDate={onEndDate} />);
    // Browser emits '' for partial input — must NOT call upstream handlers
    fireEvent.change(screen.getByTestId('start-date-input'), { target: { value: '' } });
    fireEvent.change(screen.getByTestId('end-date-input'), { target: { value: '' } });
    expect(onStartDate).not.toHaveBeenCalled();
    expect(onEndDate).not.toHaveBeenCalled();
  });

  it('valid date is debounced — onStartDate not called immediately', () => {
    vi.useFakeTimers();
    const onStartDate = vi.fn();
    render(<FilterBar {...defaultProps} onStartDate={onStartDate} />);
    fireEvent.change(screen.getByTestId('start-date-input'), { target: { value: '2026-10-15' } });
    expect(onStartDate).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(500); });
    expect(onStartDate).toHaveBeenCalledWith('2026-10-15');
    vi.useRealTimers();
  });

  it('shows total count even when date range error is displayed', () => {
    // Error state: end before start — but total=42 must still show
    render(<FilterBar {...defaultProps} startDate="2026-09-20" endDate="2026-09-01" total={42} />);
    expect(screen.getByTestId('date-range-error')).toBeTruthy();
    expect(screen.getByText(/42 appels/i)).toBeTruthy();
  });

  it('implausible year (0009) — onStartDate not called and draft state unchanged', () => {
    vi.useFakeTimers();
    const onStartDate = vi.fn();
    render(<FilterBar {...defaultProps} onStartDate={onStartDate} />);
    const input = screen.getByTestId('start-date-input') as HTMLInputElement;
    // Baseline: input reflects the defaultProps startDate
    expect(input.value).toBe('2026-09-01');
    // Browser emits complete-format date with implausible year
    fireEvent.change(input, { target: { value: '0009-11-20' } });
    act(() => { vi.advanceTimersByTime(500); });
    expect(onStartDate).not.toHaveBeenCalled();
    // Draft must not have changed — controlled value stays at previous date
    expect(input.value).toBe('2026-09-01');
    vi.useRealTimers();
  });

  it('year 2000 is accepted (lower bound is inclusive)', () => {
    vi.useFakeTimers();
    const onStartDate = vi.fn();
    render(<FilterBar {...defaultProps} onStartDate={onStartDate} />);
    fireEvent.change(screen.getByTestId('start-date-input'), { target: { value: '2000-01-15' } });
    act(() => { vi.advanceTimersByTime(500); });
    expect(onStartDate).toHaveBeenCalledWith('2000-01-15');
    vi.useRealTimers();
  });
});

describe('phone filter toggle', () => {
  beforeEach(() => { try { localStorage.clear(); } catch { /* ignore */ } });

  it('starts folded, summarises active filters, and opens/closes', async () => {
    render(
      <FilterBar
        {...defaultProps}
        status={['triaged']}
        urgency="AJD"
        sectors={[{ sector_id: 2, territoire: 'Haute-Ville', color_code: null }]}
        sectorId={2}
      />,
    );
    const toggle = screen.getByTestId('filters-toggle');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.textContent).toMatch(/Filtres\s*3/);
    expect(screen.getByTestId('filters-summary').textContent).toBe('01/09 → 25/09 · Trié · AJD · Haute-Ville');

    await userEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(toggle.textContent).toMatch(/Masquer/);
    expect(screen.queryByTestId('filters-summary')).toBeNull();
    expect(localStorage.getItem('sib.board.filtersOpen')).toBe('1');

    await userEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(localStorage.getItem('sib.board.filtersOpen')).toBe('0');
  });

  it('remembers that the filters were left open', () => {
    localStorage.setItem('sib.board.filtersOpen', '1');
    render(<FilterBar {...defaultProps} />);
    expect(screen.getByTestId('filters-toggle').getAttribute('aria-expanded')).toBe('true');
  });
});

describe('quick date ranges', () => {
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
  const minus = (n: number) => {
    const [y, m, d] = today.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, d - n)).toISOString().slice(0, 10);
  };

  it.each([[7, 6], [14, 13], [30, 29]])('%i jours sets both dates in one call, ending today', async (days, back) => {
    const onDateRange = vi.fn();
    const onStartDate = vi.fn();
    render(<FilterBar {...defaultProps} onDateRange={onDateRange} onStartDate={onStartDate} />);
    await userEvent.click(screen.getByRole('button', { name: `${days} derniers jours` }));
    expect(onDateRange).toHaveBeenCalledWith(minus(back), today);
    expect(onStartDate).not.toHaveBeenCalled();
    expect((screen.getByTestId('start-date-input') as HTMLInputElement).value).toBe(minus(back));
    expect((screen.getByTestId('end-date-input') as HTMLInputElement).value).toBe(today);
  });

  it('a custom range shows on the calendar button and is picked from the calendar', async () => {
    const onDateRange = vi.fn();
    render(<FilterBar {...defaultProps} startDate="2026-09-01" endDate="2026-09-25" onDateRange={onDateRange} />);
    const cal = screen.getByTestId('custom-range-btn');
    expect(cal.textContent).toContain('01/09 → 25/09');
    expect(cal.getAttribute('aria-expanded')).toBe('false');
    await userEvent.click(cal);
    expect(cal.getAttribute('aria-expanded')).toBe('true');
    const grid = screen.getByTestId('range-calendar');
    await userEvent.click(grid.querySelector('[data-day="2026-09-10"]')!);
    await userEvent.click(grid.querySelector('[data-day="2026-09-03"]')!);
    expect(onDateRange).toHaveBeenCalledWith('2026-09-03', '2026-09-10');
    expect(cal.getAttribute('aria-expanded')).toBe('false');
  });

  it('Escape on the calendar button closes the calendar', async () => {
    render(<FilterBar {...defaultProps} />);
    const cal = screen.getByTestId('custom-range-btn');
    await userEvent.click(cal);
    expect(cal.getAttribute('aria-expanded')).toBe('true');
    await userEvent.keyboard('{Escape}');
    expect(cal.getAttribute('aria-expanded')).toBe('false');
  });

  it('there is no long date field in the bar any more', () => {
    render(<FilterBar {...defaultProps} />);
    expect(screen.getByTestId('start-date-input').closest('[hidden]')).not.toBeNull();
  });

  it('marks the matching range as active', () => {
    render(<FilterBar {...defaultProps} startDate={minus(13)} endDate={today} />);
    expect(screen.getByTestId('quick-range-14').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('quick-range-7').getAttribute('aria-pressed')).toBe('false');
  });

  it('is disabled when dates are ignored (unrouted source)', () => {
    render(<FilterBar {...defaultProps} dateNote="dates ignorées" />);
    expect((screen.getByTestId('quick-range-7') as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('À redispatcher filter (stop 3)', () => {
  it('toggles the redispatch filter', () => {
    const onRedispatch = vi.fn();
    render(
      <FilterBar {...defaultProps} redispatch={false} onRedispatch={onRedispatch} />
    );
    const box = screen.getByTestId('redispatch-filter').querySelector('input') as HTMLInputElement;
    fireEvent.click(box);
    expect(onRedispatch).toHaveBeenCalledWith(true);
  });
});
