import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DetailPanel from '../pages/DispatchBoard/DetailPanel';
import { ApiError } from '../api/client';

vi.mock('../hooks/useRequest', () => ({
  useRequest: vi.fn(),
}));
import { useRequest } from '../hooks/useRequest';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('DetailPanel', () => {
  it('renders detail-panel testid', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: true, isError: false, error: null });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    expect(screen.getByTestId('detail-panel')).toBeTruthy();
  });

  it('shows loading state', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: true, isError: false, error: null });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    expect(screen.getByText(/Chargement/)).toBeTruthy();
  });

  it('shows error message without maintenance request ID', () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: false, isError: true, error: null });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    const el = screen.getByText(/Erreur lors du chargement/);
    expect(el).toBeTruthy();
    // must not show the maintenance request number
    expect(el.textContent).not.toContain('42');
  });

  it('shows trace ID from error envelope when present', () => {
    const err = new ApiError('NOT_FOUND', 'Request not found', 'abc-trace-123');
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: false, isError: true, error: err });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    expect(screen.getByText(/abc-trace-123/)).toBeTruthy();
  });

  it('shows no trace ID bracket when traceId absent', () => {
    const err = new ApiError('NOT_FOUND', 'Request not found');
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: false, isError: true, error: err });
    wrap(<DetailPanel requestId={42} onClose={vi.fn()} />);
    const el = screen.getByText(/Erreur lors du chargement/);
    expect(el.textContent).not.toContain('[');
  });

  it('calls onClose when Escape is pressed', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: true, isError: false, error: null });
    const onClose = vi.fn();
    wrap(<DetailPanel requestId={1} onClose={onClose} />);
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose when backdrop clicked', async () => {
    (useRequest as ReturnType<typeof vi.fn>).mockReturnValue({ data: null, isPending: true, isError: false, error: null });
    const onClose = vi.fn();
    const { container } = wrap(<DetailPanel requestId={1} onClose={onClose} />);
    const backdrop = container.querySelector('[aria-hidden]') as HTMLElement;
    await userEvent.click(backdrop);
    expect(onClose).toHaveBeenCalled();
  });
});
