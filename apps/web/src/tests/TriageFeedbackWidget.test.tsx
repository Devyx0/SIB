import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '../api/client';
import * as client from '../api/client';
import TriageFeedbackWidget from '../components/TriageFeedbackWidget';

function wrap(requestId = 1, props: { hasProposals?: boolean; onDispatchProposals?: () => Promise<void> } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TriageFeedbackWidget requestId={requestId} lang="fr" {...props} />
    </QueryClientProvider>
  );
}

const FEEDBACK_UTILE = {
  feedback_id: 1, request_id: 1, employee_id: 4,
  level: 'utile' as const,
  reason: null,
  triage_output: { triage_model_version: 'claude-sonnet-4-6', problem_summary: 'Test' },
  triage_model_version: 'claude-sonnet-4-6',
  edit_history: [],
  created_at: '2026-10-19T00:00:00Z',
  updated_at: '2026-10-19T00:00:00Z',
};

const FEEDBACK_PAS_UTILE = {
  ...FEEDBACK_UTILE,
  level: 'pas utile' as const,
  reason: 'Résumé complètement inexact dans ce contexte.',
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('TriageFeedbackWidget', () => {
  it('renders the three level buttons', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    wrap();
    await waitFor(() => expect(screen.getByTestId('feedback-widget')).toBeTruthy());
    expect(screen.getByTestId('feedback-level-utile')).toBeTruthy();
    expect(screen.getByTestId('feedback-level-partiellement-utile')).toBeTruthy();
    expect(screen.getByTestId('feedback-level-pas-utile')).toBeTruthy();
  });

  it('hides reason textarea when utile is selected', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    wrap();
    await waitFor(() => screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    expect(screen.queryByTestId('feedback-reason')).toBeNull();
  });

  it('shows reason textarea when partiellement utile is selected', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    wrap();
    await waitFor(() => screen.getByTestId('feedback-level-partiellement-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-partiellement-utile'));
    expect(screen.getByTestId('feedback-reason')).toBeTruthy();
  });

  it('shows reason textarea when pas utile is selected', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    wrap();
    await waitFor(() => screen.getByTestId('feedback-level-pas-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-pas-utile'));
    expect(screen.getByTestId('feedback-reason')).toBeTruthy();
  });

  it('save button disabled for lower levels until reason >= 10 chars', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    wrap();
    await waitFor(() => screen.getByTestId('feedback-level-pas-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-pas-utile'));
    const saveBtn = screen.getByTestId('feedback-save') as HTMLButtonElement;
    expect(saveBtn.disabled).toBe(true);
    await userEvent.type(screen.getByTestId('feedback-reason'), 'Court');
    expect(saveBtn.disabled).toBe(true);
  });

  it('save button enabled when utile selected (no reason needed)', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    wrap();
    await waitFor(() => screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    expect((screen.getByTestId('feedback-save') as HTMLButtonElement).disabled).toBe(false);
  });

  it('save button enabled with valid reason for pas utile', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    wrap();
    await waitFor(() => screen.getByTestId('feedback-level-pas-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-pas-utile'));
    await userEvent.type(screen.getByTestId('feedback-reason'), 'Résumé inexact pour ce cas local.');
    expect((screen.getByTestId('feedback-save') as HTMLButtonElement).disabled).toBe(false);
  });

  it('loads and pre-selects existing utile feedback', async () => {
    vi.spyOn(client, 'fetchFeedback').mockResolvedValue(FEEDBACK_UTILE);
    wrap();
    await waitFor(() => {
      const btn = screen.getByTestId('feedback-level-utile');
      expect(btn.className).toMatch(/levelActive/);
    });
    expect(screen.queryByTestId('feedback-reason')).toBeNull();
  });

  it('loads and pre-selects existing pas utile feedback with reason', async () => {
    vi.spyOn(client, 'fetchFeedback').mockResolvedValue(FEEDBACK_PAS_UTILE);
    wrap();
    await waitFor(() => {
      const btn = screen.getByTestId('feedback-level-pas-utile');
      expect(btn.className).toMatch(/levelActive/);
    });
    const textarea = screen.getByTestId('feedback-reason') as HTMLTextAreaElement;
    expect(textarea.value).toBe(FEEDBACK_PAS_UTILE.reason);
  });

  it('404 on GET shows empty unselected form', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    wrap();
    await waitFor(() => screen.getByTestId('feedback-widget'));
    const saveBtn = screen.getByTestId('feedback-save') as HTMLButtonElement;
    expect(saveBtn.disabled).toBe(true);
  });

  it('shows saved note for existing feedback', async () => {
    vi.spyOn(client, 'fetchFeedback').mockResolvedValue(FEEDBACK_UTILE);
    wrap();
    await waitFor(() => expect(screen.getByTestId('feedback-saved-note')).toBeTruthy());
  });

  it('calls upsertFeedback on save and updates cache', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    const upsertSpy = vi.spyOn(client, 'upsertFeedback').mockResolvedValue(FEEDBACK_UTILE);
    wrap();
    await waitFor(() => screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-save'));
    await waitFor(() => expect(upsertSpy).toHaveBeenCalledWith(1, { level: 'utile', reason: null }));
  });

  it('Dispatch saves feedback then runs onDispatchProposals', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    const upsertSpy = vi.spyOn(client, 'upsertFeedback').mockResolvedValue(FEEDBACK_UTILE);
    const onDispatch = vi.fn().mockResolvedValue(undefined);
    wrap(1, { hasProposals: true, onDispatchProposals: onDispatch });
    await waitFor(() => screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-dispatch'));
    await waitFor(() => expect(upsertSpy).toHaveBeenCalled());
    await waitFor(() => expect(onDispatch).toHaveBeenCalled());
  });

  it('shows error message when upsert fails', async () => {
    vi.spyOn(client, 'fetchFeedback').mockRejectedValue(new ApiError('NOT_FOUND', 'no feedback'));
    vi.spyOn(client, 'upsertFeedback').mockRejectedValue(new ApiError('SERVER_ERROR', 'Erreur serveur'));
    wrap();
    await waitFor(() => screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-level-utile'));
    await userEvent.click(screen.getByTestId('feedback-save'));
    await waitFor(() => expect(screen.getByTestId('feedback-error')).toBeTruthy());
    expect(screen.getByTestId('feedback-error').textContent).toContain('Erreur serveur');
  });
});
