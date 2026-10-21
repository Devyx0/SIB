import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CloseoutForm from '../pages/TechPortal/CloseoutForm';

vi.mock('../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: 'tok' } } }),
      onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
      signOut: vi.fn(),
    },
  },
}));

const mocks = vi.hoisted(() => ({
  fetchRequest: vi.fn(),
  uploadPhoto: vi.fn(),
  closeoutTask: vi.fn(),
}));

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    fetchRequest: mocks.fetchRequest,
    uploadPhoto: mocks.uploadPhoto,
    closeoutTask: mocks.closeoutTask,
  };
});

const ME = { employee_id: 24, nom_employe: 'Martin Poirier', roles: ['technician'] };

function task(id: number, extra: Record<string, unknown> = {}) {
  return {
    task_id: id, request_id: 5, description: `Tâche ${id}`, status: 'arrived',
    assigned_employee_id: 24, accepted_at: '2026-10-19T12:00:00Z', due_at: null,
    ...extra,
  };
}

const REQ = {
  request_id: 5,
  raw_title: 'Fuite évier',
  status: 'open',
  start_date: '2026-10-19',
  assigned_employee_id: null,
  tasks: [task(50)],
  followup_log: [],
} as never;

const LABELS = [
  'Call fermé, terminé complètement',
  'Call partiellement fait, je dois revenir',
  "Call partiellement fait, besoin d'une expertise",
  "Call pas du tout fait, besoin d'une expertise / envoyer à dispatch",
];

function wrap(entry = '/tech/appels/5/cloture?task=50') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/tech/appels/:id/cloture"
            element={<CloseoutForm lang="fr" me={ME} onSignOut={vi.fn()} onToggleLang={vi.fn()} />}
          />
          <Route path="/tech" element={<div>LISTE-TECH</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function addPhoto() {
  const input = screen.getByTestId('photo-input');
  const file = new File([new Uint8Array(64)], 'p.jpg', { type: 'image/jpeg' });
  fireEvent.change(input, { target: { files: [file] } });
}

function setComment(text: string) {
  fireEvent.change(screen.getByTestId('closeout-comment'), { target: { value: text } });
}

beforeEach(() => {
  mocks.fetchRequest.mockReset().mockResolvedValue(REQ);
  mocks.uploadPhoto.mockReset().mockResolvedValue({ attachment_id: 91 });
  mocks.closeoutTask.mockReset().mockResolvedValue({ ...task(50), status: 'done', follow_up_task: null, request_status: 'closed' });
  URL.createObjectURL = vi.fn(() => 'blob:mock');
});

describe('CloseoutForm', () => {
  it('shows the four outcomes with the verbatim labels', async () => {
    wrap();
    await waitFor(() => expect(screen.getByText(LABELS[0])).toBeTruthy());
    for (const label of LABELS) expect(screen.getByText(label)).toBeTruthy();
  });

  it('submit stays disabled until outcome + 1 photo + 10-char comment', async () => {
    wrap();
    await waitFor(() => expect(screen.getByTestId('closeout-submit')).toBeTruthy());
    const submit = () => screen.getByTestId('closeout-submit') as HTMLButtonElement;
    expect(submit().disabled).toBe(true);

    const hint = screen.getByTestId('closeout-comment-hint');
    expect(hint.textContent).toMatch(/Minimum 10/);
    expect(hint.textContent).toMatch(/0\/10/);

    fireEvent.click(screen.getByText(LABELS[0]));
    expect(submit().disabled).toBe(true);

    addPhoto();
    await waitFor(() => expect(mocks.uploadPhoto).toHaveBeenCalled());
    expect(submit().disabled).toBe(true);

    setComment('court');
    expect(submit().disabled).toBe(true);
    expect(hint.textContent).toMatch(/5\/10/);

    setComment('Travail terminé, tout est réparé.');
    await waitFor(() => expect(submit().disabled).toBe(false));
    expect(hint.textContent).toMatch(/\d+\/10/);
  });

  it('uploads the photo and shows a thumbnail', async () => {
    wrap();
    await waitFor(() => expect(screen.getByText(/Fuite évier/)).toBeTruthy());
    addPhoto();
    await waitFor(() => expect(mocks.uploadPhoto).toHaveBeenCalledWith(5, expect.any(File)));
    expect(document.querySelectorAll('img').length).toBe(1);
  });

  it('outcome 2 requires a date >= today (Toronto)', async () => {
    wrap();
    await waitFor(() => expect(screen.getByText(LABELS[1])).toBeTruthy());
    fireEvent.click(screen.getByText(LABELS[1]));
    addPhoto();
    await waitFor(() => expect(mocks.uploadPhoto).toHaveBeenCalled());
    setComment('Je reviens la semaine prochaine finir.');

    const submit = () => screen.getByTestId('closeout-submit') as HTMLButtonElement;
    const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
    const date = screen.getByTestId('next-date') as HTMLInputElement;
    expect(date.getAttribute('min')).toBe(today);
    expect(submit().disabled).toBe(true); // no date yet

    fireEvent.change(date, { target: { value: '2020-01-01' } }); // past
    expect(submit().disabled).toBe(true);

    fireEvent.change(date, { target: { value: today } });
    await waitFor(() => expect(submit().disabled).toBe(false));
  });

  it('shows the urgent checkbox only for outcomes 3 and 4', async () => {
    wrap();
    await waitFor(() => expect(screen.getByText(LABELS[0])).toBeTruthy());
    expect(screen.queryByTestId('urgent-checkbox')).toBeNull();
    fireEvent.click(screen.getByText(LABELS[2]));
    expect(screen.getByTestId('urgent-checkbox')).toBeTruthy();
    fireEvent.click(screen.getByText(LABELS[3]));
    expect(screen.getByTestId('urgent-checkbox')).toBeTruthy();
    fireEvent.click(screen.getByText(LABELS[1]));
    expect(screen.queryByTestId('urgent-checkbox')).toBeNull();
  });

  it('submits outcome 3 with urgent + photos, then returns to the list', async () => {
    wrap();
    await waitFor(() => expect(screen.getByText(LABELS[2])).toBeTruthy());
    fireEvent.click(screen.getByText(LABELS[2]));
    addPhoto();
    await waitFor(() => expect(mocks.uploadPhoto).toHaveBeenCalled());
    setComment("Besoin d'un plombier certifié pour la suite.");
    fireEvent.click(screen.getByTestId('urgent-checkbox'));

    await waitFor(() =>
      expect((screen.getByTestId('closeout-submit') as HTMLButtonElement).disabled).toBe(false)
    );
    fireEvent.click(screen.getByTestId('closeout-submit'));
    await waitFor(() => expect(mocks.closeoutTask).toHaveBeenCalledWith(50, expect.objectContaining({
      outcome: 'partial_expertise',
      urgent: true,
      attachment_ids: [91],
      current_status: 'arrived',
      next_date: null,
    })));
    await waitFor(() => expect(screen.getByText('LISTE-TECH')).toBeTruthy());
  });

  it('closes out the task named in the URL, not another of mine', async () => {
    mocks.fetchRequest.mockResolvedValue({
      ...(REQ as object), tasks: [task(50), task(51, { status: 'working', description: 'Peinture' })],
    });
    wrap('/tech/appels/5/cloture?task=51');
    await waitFor(() => expect(screen.getByTestId('closeout-task').textContent).toBe('Peinture'));
    fireEvent.click(screen.getByText(LABELS[0]));
    addPhoto();
    await waitFor(() => expect(mocks.uploadPhoto).toHaveBeenCalled());
    setComment('Travail terminé, tout est réparé.');
    await waitFor(() =>
      expect((screen.getByTestId('closeout-submit') as HTMLButtonElement).disabled).toBe(false)
    );
    fireEvent.click(screen.getByTestId('closeout-submit'));
    await waitFor(() => expect(mocks.closeoutTask).toHaveBeenCalledWith(51, expect.objectContaining({
      outcome: 'complete',
      current_status: 'working',
    })));
  });

  it('cannot submit when no task on the call is mine', async () => {
    mocks.fetchRequest.mockResolvedValue({ ...(REQ as object), tasks: [task(50, { assigned_employee_id: 99 })] });
    wrap('/tech/appels/5/cloture');
    await waitFor(() => expect(screen.getByTestId('closeout-no-task')).toBeTruthy());
    fireEvent.click(screen.getByText(LABELS[0]));
    setComment('Travail terminé, tout est réparé.');
    expect((screen.getByTestId('closeout-submit') as HTMLButtonElement).disabled).toBe(true);
  });
});
