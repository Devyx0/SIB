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

  it('renders all status checkboxes', () => {
    render(<FilterBar {...defaultProps} />);
    expect(screen.getByText('Reçu')).toBeTruthy();
    expect(screen.getByText('En triage')).toBeTruthy();
  });

  it('shows clear button when statuses are selected', () => {
    render(<FilterBar {...defaultProps} status={['triaged']} />);
    expect(screen.getByText('Effacer')).toBeTruthy();
  });

  it('calls onStatus with cleared array when clear is clicked', async () => {
    const onStatus = vi.fn();
    render(<FilterBar {...defaultProps} status={['triaged']} onStatus={onStatus} />);
    await userEvent.click(screen.getByText('Effacer'));
    expect(onStatus).toHaveBeenCalledWith([]);
  });

  it('date input guard rejects partial year — onStartDate not called for invalid value', () => {
    // The onChange guard requires /^\d{4}-\d{2}-\d{2}$/ and year 2020-2099.
    // A browser-generated partial value like "0102-02-06" (bad year) or an
    // empty intermediate value must not propagate.
    const onStartDate = vi.fn();
    render(<FilterBar {...defaultProps} onStartDate={onStartDate} />);
    const input = screen.getAllByDisplayValue('2026-09-01')[0];

    // Empty value (user clears the field) — allowed (clears the filter)
    fireEvent.change(input, { target: { value: '' } });
    expect(onStartDate).toHaveBeenCalledWith('');

    // Partial / garbled year outside 2020-2099 — must NOT call onStartDate
    onStartDate.mockClear();
    fireEvent.change(input, { target: { value: '0102-02-06' } });
    expect(onStartDate).not.toHaveBeenCalled();

    // Valid value — must call onStartDate
    fireEvent.change(input, { target: { value: '2026-10-15' } });
    expect(onStartDate).toHaveBeenCalledWith('2026-10-15');
  });
});
