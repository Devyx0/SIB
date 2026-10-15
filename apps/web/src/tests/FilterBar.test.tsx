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
});
