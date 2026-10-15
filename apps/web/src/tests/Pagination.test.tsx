import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import Pagination from '../components/Pagination';

describe('Pagination', () => {
  it('renders showing indicator: 1–50 sur 200', () => {
    render(<Pagination offset={0} pageSize={50} total={200} onPrev={vi.fn()} onNext={vi.fn()} />);
    // en-dash between numbers — use loose pattern
    expect(screen.getByText(/50.+sur.+200/)).toBeTruthy();
  });

  it('clamps to on last partial page: 181–200 sur 200', () => {
    render(<Pagination offset={180} pageSize={50} total={200} onPrev={vi.fn()} onNext={vi.fn()} />);
    expect(screen.getByText(/200.+sur.+200/)).toBeTruthy();
  });

  it('prev disabled on first page', () => {
    render(<Pagination offset={0} pageSize={50} total={200} onPrev={vi.fn()} onNext={vi.fn()} />);
    expect(screen.getByTestId('pagination-prev')).toBeDisabled();
  });

  it('next enabled when more pages exist', () => {
    render(<Pagination offset={0} pageSize={50} total={200} onPrev={vi.fn()} onNext={vi.fn()} />);
    expect(screen.getByTestId('pagination-next')).not.toBeDisabled();
  });

  it('next disabled on last page', () => {
    render(<Pagination offset={150} pageSize={50} total={200} onPrev={vi.fn()} onNext={vi.fn()} />);
    expect(screen.getByTestId('pagination-next')).toBeDisabled();
  });

  it('prev enabled on second page', () => {
    render(<Pagination offset={50} pageSize={50} total={200} onPrev={vi.fn()} onNext={vi.fn()} />);
    expect(screen.getByTestId('pagination-prev')).not.toBeDisabled();
  });

  it('calls onNext when next clicked', async () => {
    const onNext = vi.fn();
    render(<Pagination offset={0} pageSize={50} total={200} onPrev={vi.fn()} onNext={onNext} />);
    await userEvent.click(screen.getByTestId('pagination-next'));
    expect(onNext).toHaveBeenCalled();
  });

  it('calls onPrev when prev clicked', async () => {
    const onPrev = vi.fn();
    render(<Pagination offset={50} pageSize={50} total={200} onPrev={onPrev} onNext={vi.fn()} />);
    await userEvent.click(screen.getByTestId('pagination-prev'));
    expect(onPrev).toHaveBeenCalled();
  });

  it('renders nothing when total is 0', () => {
    const { container } = render(
      <Pagination offset={0} pageSize={50} total={0} onPrev={vi.fn()} onNext={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('uses English labels when lang=en', () => {
    render(
      <Pagination offset={0} pageSize={50} total={100} lang="en" onPrev={vi.fn()} onNext={vi.fn()} />,
    );
    expect(screen.getByText(/of/)).toBeTruthy();
  });
});
