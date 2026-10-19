import { render, screen, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect } from 'vitest';
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
