import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../App';

vi.mock('../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: { session: { access_token: 'tok', user: { email: 'tech@sib.local' } } },
      }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
      signOut: vi.fn(),
    },
  },
}));

const mocks = vi.hoisted(() => ({
  fetchMe: vi.fn(),
  fetchRequests: vi.fn(),
  fetchTasks: vi.fn(),
  fetchRequest: vi.fn(),
  taskEnRoute: vi.fn(),
}));

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    fetchMe: mocks.fetchMe,
    fetchRequests: mocks.fetchRequests,
    fetchTasks: mocks.fetchTasks,
    fetchRequest: mocks.fetchRequest,
    taskEnRoute: mocks.taskEnRoute,
    fetchSectors: () => Promise.resolve([]),
    fetchEmployees: () => Promise.resolve([]),
  };
});

const TECH = { employee_id: 24, nom_employe: 'Martin Poirier', roles: ['technician'] };
const CONTRACTOR = { employee_id: 20, nom_employe: 'Mahmoud Chachia', roles: ['contractor'] };
const COORD = { employee_id: 4, nom_employe: 'Test Coord', roles: ['coordinator'] };
const TECH_COORD = { employee_id: 7, nom_employe: 'Chef Tech', roles: ['technician', 'coordinator'] };

/** Local noon on a Toronto day — dueDay() reads it back as that day. */
const dueOn = (ymd: string) => `${ymd}T12:00:00-05:00`;

function task(id: number, status: string, extra: Record<string, unknown> = {}) {
  return {
    task_id: id,
    request_id: 5,
    description: `Tâche ${id}`,
    status,
    assigned_employee_id: 24,
    vendor_id: null,
    subcontractor_name: null,
    due_at: dueOn('2026-10-20'),
    urgency_tier: null,
    source: 'dispatcher',
    accepted_at: '2026-10-19T12:00:00Z',
    parent_task_id: null,
    sort_order: 0,
    created_at: '2026-10-19T12:00:00Z',
    updated_at: '2026-10-19T12:00:00Z',
    ...extra,
  };
}

// GET /tasks row: the task plus its call's list context.
function row(id: number, status: string, extra: Record<string, unknown> = {}) {
  return {
    ...task(id, status),
    request_id: id,
    request_title: `Appel ${id}`,
    request_status: 'open',
    request_asnu: null,
    request_urgency_tier: null,
    assigned_employee_name: 'Martin Poirier',
    sector_id: 1,
    territoire: null,
    building_address: '123 rue Test',
    unit_label: null,
    ...extra,
  };
}

// Full-enough RequestDetail for the call view; tech 24 holds scheduled task 50.
function detail(extra: Record<string, unknown> = {}) {
  return {
    request_id: 5,
    start_date: '2026-10-20',
    status: 'open',
    urgency_tier: null,
    raw_title: 'Appel 5',
    building_address: '123 rue Test',
    unit_label: null,
    assigned_employee_id: null,
    tasks: [task(50, 'scheduled')],
    visits: [],
    problem_summary: null,
    problems: null,
    raw_caller_body: null,
    building_name: null,
    ft_link: null,
    ft_name: null,
    caller_name: null,
    caller_phone: null,
    caller_email: null,
    followup_log: [],
    ...extra,
  };
}

const EMPTY_LIST = { total: 0, items: [], unscheduled_items: [] };
const NO_TASKS = { total: 0, items: [] };

function wrap(initialEntries: string[] = ['/']) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  mocks.fetchMe.mockReset();
  mocks.fetchRequests.mockReset().mockResolvedValue(EMPTY_LIST);
  mocks.fetchTasks.mockReset().mockResolvedValue(NO_TASKS);
  mocks.fetchRequest.mockReset();
  mocks.taskEnRoute.mockReset();
});

describe('role routing', () => {
  it('technician lands on Mes appels, even from /board', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    wrap(['/board']);
    await waitFor(() => expect(screen.getByText(/Mes appels/)).toBeTruthy());
  });

  it('contractor lands on Mes appels', async () => {
    mocks.fetchMe.mockResolvedValue(CONTRACTOR);
    wrap(['/']);
    await waitFor(() => expect(screen.getByText(/Mes appels/)).toBeTruthy());
  });

  it('coordinator keeps the triage board', async () => {
    mocks.fetchMe.mockResolvedValue(COORD);
    wrap(['/board']);
    await waitFor(() => expect(screen.getAllByText('Triage').length).toBeGreaterThan(0));
    expect(screen.queryByText(/Mes appels/)).toBeNull();
  });

  it('technician+coordinator keeps the triage board', async () => {
    mocks.fetchMe.mockResolvedValue(TECH_COORD);
    wrap(['/board']);
    await waitFor(() => expect(screen.getAllByText('Triage').length).toBeGreaterThan(0));
  });
});

describe('Mes appels list', () => {
  it('fetches my tasks, no date window, open task statuses only', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    wrap(['/tech']);
    await waitFor(() =>
      expect(mocks.fetchTasks).toHaveBeenCalledWith(
        expect.objectContaining({ assigned_employee_id: 24 })
      )
    );
    const params = mocks.fetchTasks.mock.calls[0][0];
    expect(params.start_date).toBeUndefined();
    expect(params.end_date).toBeUndefined();
    expect(params.status).toEqual(expect.arrayContaining(['queued', 'scheduled', 'en_route', 'arrived', 'working']));
    expect(params.status).not.toContain('done');
    expect(params.status).not.toContain('cancelled');
    expect(mocks.fetchRequests).not.toHaveBeenCalled();
  });

  it('groups tasks by due day: « En retard », « À venir », « Sans date »', async () => {
    const dayMs = 86400000;
    const toronto = (ms: number) =>
      new Date(ms).toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });
    const tenDaysAgo = toronto(Date.now() - 10 * dayMs);
    const tomorrow = toronto(Date.now() + dayMs);

    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchTasks.mockResolvedValue({
      total: 3,
      items: [
        row(30, 'scheduled', { due_at: dueOn(tenDaysAgo) }),
        row(32, 'scheduled', { due_at: dueOn(tomorrow) }),
        row(33, 'queued', { due_at: null }),
      ],
    });
    wrap(['/tech']);
    await waitFor(() => expect(screen.getByText('En retard')).toBeTruthy());
    const overdueSection = screen.getByText('En retard').nextElementSibling;
    expect(overdueSection?.textContent).toContain('Appel 30');
    expect(screen.getByText('À venir').nextElementSibling?.textContent).toContain('Appel 32');
    const sansDate = screen.getByRole('heading', { name: 'Sans date' });
    expect(sansDate.nextElementSibling?.textContent).toContain('Appel 33');
  });

  it('rows link to the call with the task id', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchTasks.mockResolvedValue({ total: 1, items: [row(30, 'scheduled')] });
    wrap(['/tech']);
    await waitFor(() => expect(screen.getByText('Appel 30')).toBeTruthy());
    expect(screen.getByText('Appel 30').closest('a')?.getAttribute('href')).toBe('/tech/appels/30?task=30');
    expect(screen.getByText('Tâche 30')).toBeTruthy();
  });

  it('shows empty state when no assigned tasks', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    wrap(['/tech']);
    await waitFor(() => expect(screen.getByText('Aucun appel assigné')).toBeTruthy());
  });

  it('pins the en_route task with a banner', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchTasks.mockResolvedValue({
      total: 2,
      items: [row(10, 'scheduled'), row(11, 'en_route')],
    });
    wrap(['/tech']);
    await waitFor(() => expect(screen.getByText(/Appel en cours/)).toBeTruthy());
    expect(screen.getByText('Appel 11')).toBeTruthy();
    expect(screen.getByText('Appel 10')).toBeTruthy();
  });
});

describe('call view', () => {
  it('shows tenant contact when the API returns it', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({
      problems: 'Fuite sous évier',
      unit_label: '3',
      ft_link: 'https://example.com/ft',
      ft_name: 'Fiche 123',
      caller_name: 'Jean Locataire',
      caller_phone: '418-555-1234',
    }));
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByText('Jean Locataire')).toBeTruthy());
    const tel = screen.getByText('418-555-1234');
    expect(tel.getAttribute('href')).toBe('tel:418-555-1234');
    expect(screen.getByText('Fuite sous évier')).toBeTruthy();
    expect(screen.getByText('Fiche 123').getAttribute('href')).toBe('https://example.com/ft');
  });

  it('hides tenant contact when the API nulls it (case-scoped rule)', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({ request_id: 6, tasks: [task(60, 'scheduled', { assigned_employee_id: 99 })] }));
    wrap(['/tech/appels/6']);
    await waitFor(() => expect(screen.getByText('Contact locataire')).toBeTruthy());
    expect(screen.queryByText(/tel:/)).toBeNull();
    expect(screen.queryByText('Jean Locataire')).toBeNull();
  });

  it('shows not-found state on 404', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    const { ApiError } = await import('../api/client');
    mocks.fetchRequest.mockRejectedValue(new ApiError('NOT_FOUND', 'Request 999 not found'));
    wrap(['/tech/appels/999']);
    await waitFor(() => expect(screen.getByText('Appel introuvable')).toBeTruthy());
  });

  it('shows the tenant version from raw_caller_body and never the AI summary', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({
      problem_summary: 'RÉSUMÉ IA — NE PAS AFFICHER',
      raw_caller_body: {
        problems: 'Mon robinet coule depuis hier',
        entry_permission: 'Oui, entrez',
        animals: 'Un chat',
      },
    }));
    wrap(['/tech/appels/5']);
    await waitFor(() =>
      expect(screen.getByText('Mon robinet coule depuis hier')).toBeTruthy()
    );
    expect(screen.getByText('Problème (version du locataire)')).toBeTruthy();
    expect(screen.getByText('Oui, entrez')).toBeTruthy();
    expect(screen.getByText('Un chat')).toBeTruthy();
    expect(screen.queryByText('RÉSUMÉ IA — NE PAS AFFICHER')).toBeNull();
  });

  it('falls back to the raw problem field when raw_caller_body is absent', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({
      problem_summary: 'RÉSUMÉ IA — NE PAS AFFICHER',
      problems: 'Texte brut du calendrier',
      entry_permission: 'Présence exigée',
      animals: 'Non',
      raw_caller_body: null,
    }));
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByText('Texte brut du calendrier')).toBeTruthy());
    expect(screen.getByText('Problème')).toBeTruthy();
    expect(screen.getByText('Présence exigée')).toBeTruthy();
    expect(screen.getByText('Non')).toBeTruthy();
    expect(screen.queryByText(/version du locataire/)).toBeNull();
    expect(screen.queryByText('RÉSUMÉ IA — NE PAS AFFICHER')).toBeNull();
  });

  it('shows taxonomy, next steps, ASNU and estimate for the technician', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({
      asnu: 'ASNUF42',
      time_estimate_bucket: 'MIN30_TO_1H',
      element: 'Plomberie',
      symptome: 'Fuite',
      composante: 'Robinet',
      emplacement: 'Cuisine',
      next_steps: 'Couper l’eau avant d’ouvrir le mur.',
      work_performed: null,
      problems: 'Fuite sous évier',
    }));
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByTestId('call-taxonomy')).toBeTruthy());
    expect(screen.getByTestId('call-facts').textContent).toMatch(/ASNUF42/);
    expect(screen.getByText('Plomberie')).toBeTruthy();
    expect(screen.getByText('Fuite')).toBeTruthy();
    expect(screen.getByText('Robinet')).toBeTruthy();
    expect(screen.getByText('Cuisine')).toBeTruthy();
    expect(screen.getByTestId('call-next-steps').textContent).toMatch(/Couper l’eau/);
  });

  it('shows « Fiche technique non disponible » when both ft fields are null', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail());
    wrap(['/tech/appels/5']);
    await waitFor(() =>
      expect(screen.getByText('Fiche technique non disponible')).toBeTruthy()
    );
  });

  it('extracts the link when it is embedded in ft_name (data shape bug)', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({
      ft_link: null,
      ft_name: '3034-3038-3052-3054 Lechasseur (https://docs.google.com/spreadsheets/d/XYZ/edit?usp=drivesdk)',
    }));
    wrap(['/tech/appels/5']);
    await waitFor(() =>
      expect(screen.getByText('3034-3038-3052-3054 Lechasseur')).toBeTruthy()
    );
    expect(screen.getByText('3034-3038-3052-3054 Lechasseur').getAttribute('href'))
      .toBe('https://docs.google.com/spreadsheets/d/XYZ/edit?usp=drivesdk');
  });
});

describe('en route (stop 2)', () => {
  it('shows the button on my scheduled task', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail());
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByTestId('en-route-btn')).toBeTruthy());
    expect(screen.getByTestId('my-task').textContent).toContain('Tâche 50');
  });

  it('hides the button when no task on the call is mine', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({ tasks: [task(50, 'scheduled', { assigned_employee_id: 99 })] }));
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByText('Contact locataire')).toBeTruthy());
    expect(screen.queryByTestId('en-route-btn')).toBeNull();
  });

  it('hides the button on a queued (undated) task', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({ tasks: [task(50, 'queued', { due_at: null })] }));
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByTestId('my-task')).toBeTruthy());
    expect(screen.queryByTestId('en-route-btn')).toBeNull();
  });

  it('acts on the task named in the URL', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({
      tasks: [task(50, 'scheduled'), task(51, 'scheduled', { description: 'Deuxième tâche' })],
    }));
    mocks.taskEnRoute.mockResolvedValue(task(51, 'en_route'));
    wrap(['/tech/appels/5?task=51']);
    await waitFor(() => expect(screen.getByTestId('my-task').textContent).toContain('Deuxième tâche'));
    fireEvent.click(screen.getByTestId('en-route-btn'));
    await waitFor(() => expect(mocks.taskEnRoute).toHaveBeenCalledWith(51, expect.anything()));
  });

  it('tap: sends null location when geolocation is unavailable, then shows the banner and the no-contact message', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail());
    mocks.taskEnRoute.mockImplementation(async () => {
      // The refetch after the tap brings the open visit.
      mocks.fetchRequest.mockResolvedValue(detail({
        tasks: [task(50, 'en_route')],
        visits: [{ visit_id: 1, task_id: 50, employee_id: 24, employee_name: null,
          en_route_at: new Date(Date.now() - 5 * 60000).toISOString(), arrived_at: null, closeout_at: null,
          travel_minutes: null, on_site_minutes: null, duration_minutes: null, outcome: null,
          closeout_comment: null, photo_ids: [] }],
      }));
      return task(50, 'en_route');
    });
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByTestId('en-route-btn')).toBeTruthy());
    fireEvent.click(screen.getByTestId('en-route-btn'));
    await waitFor(() => expect(screen.getByTestId('no-contact-warning')).toBeTruthy());
    expect(mocks.taskEnRoute).toHaveBeenCalledWith(50, {
      current_status: 'scheduled',
      lat: null,
      lng: null,
    });
    await waitFor(() => expect(screen.getByText(/En route depuis 5 min/)).toBeTruthy());
    expect(screen.getByText('Aucun contact pour aviser le locataire')).toBeTruthy();
    expect(screen.queryByTestId('en-route-btn')).toBeNull();
  });

  it('tap: sends the granted location', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail());
    mocks.taskEnRoute.mockResolvedValue(task(50, 'en_route'));
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition: (ok: (p: unknown) => void) =>
          ok({ coords: { latitude: 46.81, longitude: -71.21 } }),
      },
    });
    try {
      wrap(['/tech/appels/5']);
      await waitFor(() => expect(screen.getByTestId('en-route-btn')).toBeTruthy());
      fireEvent.click(screen.getByTestId('en-route-btn'));
      await waitFor(() =>
        expect(mocks.taskEnRoute).toHaveBeenCalledWith(50, expect.objectContaining({
          lat: 46.81,
          lng: -71.21,
        }))
      );
    } finally {
      Object.defineProperty(navigator, 'geolocation', { configurable: true, value: undefined });
    }
  });

  it('blocks with the open call shown when another task is already en route', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail());
    const { ApiError } = await import('../api/client');
    mocks.taskEnRoute.mockRejectedValue(new ApiError(
      'CONFLICT',
      "Appel 77 déjà en route — clôturez-le d'abord",
      undefined,
      { open_task_id: 9, open_request_id: 77, open_request_title: 'Premier appel' },
    ));
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByTestId('en-route-btn')).toBeTruthy());
    fireEvent.click(screen.getByTestId('en-route-btn'));
    await waitFor(() =>
      expect(screen.getByText(/Appel 77 déjà en route/)).toBeTruthy()
    );
    expect(screen.getByText(/Premier appel/)).toBeTruthy();
  });

  it('pinned list banner shows elapsed time', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchTasks.mockResolvedValue({
      total: 1,
      items: [row(11, 'en_route', { updated_at: new Date(Date.now() - 30 * 60000).toISOString() })],
    });
    wrap(['/tech']);
    await waitFor(() => expect(screen.getByText(/Appel en cours/)).toBeTruthy());
    expect(screen.getByText(/En route depuis 30 min/)).toBeTruthy();
  });
});

describe('closeout entry (stop 3)', () => {
  it('shows « Clôturer » on my arrived task, linking with the task id', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({ tasks: [task(50, 'arrived')] }));
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByTestId('closeout-btn')).toBeTruthy());
    expect(screen.getByTestId('closeout-btn').getAttribute('href')).toBe('/tech/appels/5/cloture?task=50');
  });

  it('no « Clôturer » when the arrived task is not mine', async () => {
    mocks.fetchMe.mockResolvedValue(TECH);
    mocks.fetchRequest.mockResolvedValue(detail({ tasks: [task(50, 'arrived', { assigned_employee_id: 99 })] }));
    wrap(['/tech/appels/5']);
    await waitFor(() => expect(screen.getByText('Contact locataire')).toBeTruthy());
    expect(screen.queryByTestId('closeout-btn')).toBeNull();
  });
});
