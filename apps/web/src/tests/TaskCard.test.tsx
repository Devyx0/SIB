import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '../api/client';
import TaskCard from '../pages/DispatchBoard/TaskCard';
import { JustificationProvider } from '../components/Justification';
import type { MeResponse, TaskListItem } from '../api/schema.d.ts';

const coord = { employee_id: 4, nom_employe: 'Coord', roles: ['coordinator'] } as unknown as MeResponse;
const task = {
  task_id: 7, request_id: 101, description: 'Réparer la fuite\nRemplacer le joint du siphon sous l’évier de la cuisine',
  status: 'scheduled', assigned_employee_id: 14, assigned_employee_name: 'Jean Tech', vendor_id: null,
  subcontractor_name: null, due_at: '2026-10-25T08:00:00', urgency_tier: 'URGENT', source: 'dispatcher',
  accepted_at: '2026-10-19T12:00:00Z', parent_task_id: null, sort_order: 0,
  created_at: '2026-10-19T12:00:00Z', updated_at: '2026-10-19T12:00:00Z',
  request_title: 'CHGE AJD 1580-204 Perigord: Fuite', request_status: 'open', request_asnu: 'ASNU78885',
  request_urgency_tier: 'URGENT', sector_id: 1, territoire: 'Haute-Ville', building_address: '1580 Perigord', unit_label: '204',
} as unknown as TaskListItem;

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><JustificationProvider lang="fr">{ui}</JustificationProvider></QueryClientProvider>);
}

describe('TaskCard', () => {
  it('shows the task name, one line of description, badges and a « Voir l’appel de service » button', async () => {
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const open = vi.fn();
    wrap(<TaskCard task={task} lang="fr" me={coord} onClose={vi.fn()} onOpenCall={open} />);
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Réparer la fuite');
    expect(screen.getByTestId('task-card-desc')).toHaveTextContent('Remplacer le joint du siphon');
    expect(screen.getByText('ASNU78885')).toBeTruthy();
    expect(screen.getByText('Fuite')).toBeTruthy(); // clean call title
    await userEvent.click(screen.getByTestId('open-call'));
    expect(open).toHaveBeenCalledWith(101);
  });

  it('saves a new name + description as one text, with a justification', async () => {
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const update = vi.spyOn(client, 'updateTask').mockResolvedValue(task as never);
    wrap(<TaskCard task={task} lang="fr" me={coord} onClose={vi.fn()} onOpenCall={vi.fn()} />);
    fireEvent.change(screen.getByTestId('task-name'), { target: { value: 'Réparer le siphon' } });
    fireEvent.change(screen.getByTestId('task-description'), { target: { value: 'Joint usé, apporter un siphon 1 1/2' } });
    await userEvent.click(screen.getByTestId('task-save'));
    await waitFor(() => expect(screen.getByTestId('justification-dialog')).toBeTruthy());
    fireEvent.change(screen.getByTestId('justification-text'), { target: { value: 'Précision après appel du locataire' } });
    await userEvent.click(screen.getByTestId('justification-confirm'));
    await waitFor(() => expect(update).toHaveBeenCalledWith(7, expect.objectContaining({
      description: 'Réparer le siphon\nJoint usé, apporter un siphon 1 1/2',
    })));
  });

  it('the due date has a time picker; the chosen time is saved with the date', async () => {
    vi.spyOn(client, 'fetchEmployees').mockResolvedValue([]);
    const schedule = vi.spyOn(client, 'scheduleTask').mockResolvedValue(task as never);
    wrap(<TaskCard task={task} lang="fr" me={coord} onClose={vi.fn()} onOpenCall={vi.fn()} />);
    fireEvent.change(screen.getByTestId('task-day'), { target: { value: '2026-10-28' } });
    await userEvent.selectOptions(screen.getByTestId('task-day-time'), '13:30');
    await userEvent.click(screen.getByTestId('task-save'));
    await waitFor(() => expect(screen.getByTestId('justification-dialog')).toBeTruthy());
    fireEvent.change(screen.getByTestId('justification-text'), { target: { value: 'Locataire disponible en après-midi' } });
    await userEvent.click(screen.getByTestId('justification-confirm'));
    await waitFor(() => expect(schedule).toHaveBeenCalledWith(7, expect.objectContaining({ due_at: '2026-10-28T13:30:00' })));
  });

  it('is view-only once the technician is on the way', () => {
    wrap(<TaskCard task={{ ...task, status: 'en_route' } as TaskListItem} lang="fr" me={coord} onClose={vi.fn()} onOpenCall={vi.fn()} />);
    expect(screen.queryByTestId('task-name')).toBeNull();
    expect(screen.queryByTestId('task-save')).toBeNull();
  });
});
