import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { JustificationProvider } from '../components/Justification';
import DispatchBoard from '../pages/DispatchBoard';

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  fetchRequests: vi.fn().mockResolvedValue({
    total: 1,
    items: [{
      request_id: 42,
      start_date: '2026-10-01',
      asnu: 'ASNUF1',
      urgency_tier: null,
      urgency_raw: null,
      raw_title: 'Fuite cuisine',
      building_id: 1,
      building_address: '100 rue Test',
      building_full_address: null,
      building_name: null,
      sector_id: 1,
      territoire: null,
      color_code: null,
      assigned_employee_id: null,
      assigned_employee_name: null,
      subcontractor_name: null,
      time_estimate_bucket: null,
      time_estimate_raw: null,
      source_calendar: null,
      source_calendar_label: null,
      status: 'open',
      event_id: null,
      estimated_cost: null,
      next_follow_up_date: null,
      next_steps: null,
      last_followup_date: null,
      last_followup_text: null,
      unit_label: '404',
      unique_unit_number: null,
      en_route_at: null,
      arrived_at: null,
      closeout_outcome: null,
      closeout_urgent: null,
      duplicate_of_request_id: null,
      addition_to_request_id: null,
    }],
    unscheduled_items: [],
  }),
  fetchSectors: vi.fn().mockResolvedValue([]),
  fetchEmployees: vi.fn().mockResolvedValue([]),
  fetchTasks: vi.fn().mockResolvedValue({ total: 0, items: [] }),
  createTask: vi.fn().mockResolvedValue({ task_id: 9 }),
}));

const me = { employee_id: 4, nom_employe: 'Coordo', roles: ['coordinator'] };

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname + loc.search}</div>;
}

function wrap(initial: string, mode: 'triage' | 'tasks' = 'tasks') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <QueryClientProvider client={qc}>
        <JustificationProvider lang="fr">
          <DispatchBoard lang="fr" me={me} mode={mode} />
          <LocationProbe />
        </JustificationProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('DispatchBoard Nouvelle tâche', () => {
  it('header button opens the new-task modal', async () => {
    wrap('/tasks');
    await waitFor(() => expect(screen.getByTestId('nouvelle-tache-btn')).toBeTruthy());
    await userEvent.click(screen.getByTestId('nouvelle-tache-btn'));
    expect(screen.getByTestId('nouvelle-tache-modal')).toBeTruthy();
    expect(screen.getByRole('dialog', { name: 'Nouvelle tâche' })).toBeTruthy();
  });

  it('opens the modal when ?nouvelle-tache=1 is present', async () => {
    wrap('/tasks?nouvelle-tache=1');
    await waitFor(() => expect(screen.getByTestId('nouvelle-tache-modal')).toBeTruthy());
  });

  it('closing the modal strips the param so a refresh does not reopen it', async () => {
    wrap('/tasks?nouvelle-tache=1');
    await waitFor(() => screen.getByTestId('nouvelle-tache-modal'));
    await userEvent.click(screen.getByRole('button', { name: 'Annuler' }));
    await waitFor(() => expect(screen.queryByTestId('nouvelle-tache-modal')).toBeNull());
    expect(screen.getByTestId('location').textContent).toBe('/tasks');
  });

  it('the top-right cross closes the modal', async () => {
    wrap('/tasks?nouvelle-tache=1');
    await waitFor(() => screen.getByTestId('nouvelle-tache-modal'));
    await userEvent.click(screen.getByRole('button', { name: 'Fermer' }));
    await waitFor(() => expect(screen.queryByTestId('nouvelle-tache-modal')).toBeNull());
  });

  it('does not open the modal without the param', async () => {
    wrap('/tasks');
    await waitFor(() => expect(screen.getByTestId('location')).toBeTruthy());
    expect(screen.queryByTestId('nouvelle-tache-modal')).toBeNull();
  });

  it('New task stays on the tasks board; triage shows New call instead', async () => {
    wrap('/triage', 'triage');
    await waitFor(() => expect(screen.getByTestId('nouvel-appel-btn')).toHaveTextContent('Nouvel appel'));
    expect(screen.queryByTestId('nouvelle-tache-btn')).toBeNull();
  });

  it('call field is a typeahead dropdown listing eligible calls', async () => {
    wrap('/tasks');
    await userEvent.click(screen.getByTestId('nouvelle-tache-btn'));
    const input = screen.getByTestId('nouvelle-tache-call');
    await userEvent.click(input);
    await waitFor(() => expect(screen.getByTestId('nouvelle-tache-suggestions')).toBeTruthy());
    expect(screen.getByTestId('nouvelle-tache-call-option-42')).toHaveTextContent('ASNUF1');
    await userEvent.click(screen.getByTestId('nouvelle-tache-call-option-42'));
    await waitFor(() => expect(screen.queryByTestId('nouvelle-tache-suggestions')).toBeNull());
    expect((input as HTMLInputElement).value).toContain('ASNUF1');
  });
});
