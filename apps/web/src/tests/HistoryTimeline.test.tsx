import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import HistoryTimeline, { buildTimeline } from '../components/HistoryTimeline';
import type { FollowupEntry, JustificationEntry, StatusChange, VisitEntry } from '../api/schema.d.ts';

vi.mock('../api/client', () => ({
  fetchPhotoUrl: vi.fn().mockResolvedValue({ url: 'https://signed.local/p.jpg' }),
}));

const decision = (over: Partial<JustificationEntry>): JustificationEntry => ({
  id: 1, decision_type: 'assign', before_value: null, after_value: null,
  justification_text: 'Le plus proche du bâtiment', input_method: 'typed',
  created_at: '2026-10-17T14:00:00+00:00', employee_id: 4, employee_name: 'Marie Lavoie', ...over,
});

const visit: VisitEntry = {
  visit_id: 7, employee_id: 24, employee_name: 'Marc Tech',
  en_route_at: '2026-10-18T14:00:00Z', arrived_at: '2026-10-18T14:20:00Z', closeout_at: '2026-10-18T15:42:00Z',
  travel_minutes: 20, on_site_minutes: 82, duration_minutes: 102,
  outcome: 'partial_expertise', closeout_comment: 'Fuite réparée en partie.', photo_ids: [41],
};

const followup = (over: Partial<FollowupEntry>): FollowupEntry => ({
  followup_id: 1, entry_date: '2026-10-16', entered_by_initials: 'JB', entry_text: 'Locataire avisée.', ...over,
});

function wrap(props: Partial<Parameters<typeof HistoryTimeline>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <HistoryTimeline requestId={15927} visits={[]} followups={[]} decisions={[]} lang="fr" {...props} />
    </QueryClientProvider>,
  );
}

describe('buildTimeline', () => {
  it('groups one dispatch save into a single entry listing each change', () => {
    const items = buildTimeline({
      visits: [], followups: [], statusChanges: [],
      decisions: [
        decision({ id: 1, before_value: { assigned_employee_id: null },
                   after_value: { assigned_employee_id: 24, assigned_employee_name: 'Marc Tech' } }),
        decision({ id: 2, decision_type: 'urgency', created_at: '2026-10-17T14:00:01+00:00',
                   before_value: { urgency_tier: null }, after_value: { urgency_tier: 'AJD' } }),
        // Same person, same text, but minutes later: a separate decision.
        decision({ id: 3, decision_type: 'cost', created_at: '2026-10-17T15:00:00+00:00',
                   before_value: { estimated_cost: null }, after_value: { estimated_cost: '250.00' } }),
      ],
    }, 'fr');
    expect(items).toHaveLength(2);
    const [later, save] = items;
    expect(later.changes?.[0]).toMatchObject({ label: 'Coût estimé', before: '—' });
    expect(later.changes?.[0].after).toMatch(/250,00/);
    expect(save.title).toBe('Répartition modifiée (2 changements)');
    expect(save.who).toBe('Marie Lavoie');
    expect(save.changes).toEqual([
      { label: 'Assignation', before: 'Personne', after: 'Marc Tech' },
      { label: 'Urgence', before: 'Aucune', after: 'AJD' },
    ]);
  });

  it('shows a closeout comment once, on the visit', () => {
    const items = buildTimeline({
      visits: [visit],
      followups: [followup({ followup_id: 2, entry_date: '2026-10-18', entered_by_initials: 'MT',
                             entry_text: 'Fuite réparée en partie.' })],
      decisions: [decision({ id: 5, decision_type: 'closeout', employee_id: 24, employee_name: 'Marc Tech',
                             created_at: '2026-10-18T15:42:00+00:00',
                             justification_text: 'Fuite réparée en partie.' })],
      statusChanges: [],
    }, 'fr');
    expect(items.map((i) => i.kind)).toEqual(['visit']);
    expect(items[0].text).toBe('Fuite réparée en partie.');
    expect(items[0].detail).toMatch(/20 min de trajet/);
    expect(items[0].detail).toMatch(/1 h 22 sur place/);
  });

  it('folds status changes into the decision or visit that caused them', () => {
    const status = (over: Partial<StatusChange>): StatusChange => ({
      id: 1, status_from: 'triaged', status_to: 'scheduled', changed_at: '2026-10-17T14:00:00Z',
      employee_id: 4, employee_name: 'Marie Lavoie', ...over,
    });
    const items = buildTimeline({
      visits: [visit],
      followups: [],
      decisions: [decision({})],
      statusChanges: [
        status({ id: 1 }),
        status({ id: 2, status_from: 'scheduled', status_to: 'en_route', changed_at: '2026-10-18T14:00:00Z',
                 employee_id: 24 }),
        status({ id: 3, status_from: 'awaiting_redispatch', status_to: 'triaged',
                 changed_at: '2026-10-19T09:00:00Z', employee_id: 5, employee_name: 'Directeur' }),
      ],
    }, 'fr');
    expect(items.map((i) => i.kind)).toEqual(['status', 'visit', 'decision']);
    expect(items[2].changes?.map((c) => c.label)).toEqual(['Assignation', 'Statut']);
    expect(items[0].who).toBe('Directeur');
  });

  it('orders newest first with dated notes after the timed events of their day', () => {
    const items = buildTimeline({
      visits: [], statusChanges: [],
      decisions: [decision({ created_at: '2026-10-16T13:00:00+00:00' })],
      followups: [followup({ followup_id: 1, entry_date: '2026-10-15' }), followup({ followup_id: 2 })],
    }, 'fr');
    expect(items.map((i) => i.key)).toEqual(['f2', 'd1', 'f1']);
  });
});

describe('HistoryTimeline', () => {
  it('renders day headings, who, before → after and the justification', () => {
    wrap({
      decisions: [decision({ before_value: { assigned_employee_id: 9, assigned_employee_name: 'Jean Tech' },
                             after_value: { assigned_employee_id: 24, assigned_employee_name: 'Marc Tech' },
                             input_method: 'voice' })],
    });
    const item = screen.getByTestId('history-item');
    expect(item).toHaveAttribute('data-kind', 'decision');
    expect(within(item).getByText('Marie Lavoie')).toBeTruthy();
    expect(within(item).getByText('Jean Tech')).toBeTruthy();
    expect(within(item).getByText('Marc Tech')).toBeTruthy();
    expect(within(item).getByText(/Le plus proche du bâtiment/)).toBeTruthy();
    expect(within(item).getByText(/dicté/)).toBeTruthy();
    expect(screen.getByRole('heading', { level: 4 })).toHaveTextContent(/17 oct/);
  });

  it('filters by kind and collapses long histories', async () => {
    const user = userEvent.setup();
    const followups = Array.from({ length: 12 }, (_, i) =>
      followup({ followup_id: i + 1, entry_date: `2026-09-${String(i + 1).padStart(2, '0')}`, entry_text: `Note ${i + 1}` }));
    wrap({ followups, visits: [visit] });
    expect(screen.getAllByTestId('history-item')).toHaveLength(10);
    await user.click(screen.getByTestId('history-more'));
    expect(screen.getAllByTestId('history-item')).toHaveLength(13);

    await user.click(screen.getByTestId('history-filter-visit'));
    const items = screen.getAllByTestId('history-item');
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveAttribute('data-kind', 'visit');
    expect(screen.queryByTestId('history-filter-decision')).toBeNull(); // no decisions → no chip
  });

  it('says so when there is no history', () => {
    wrap();
    expect(screen.getByText('Aucun historique pour le moment.')).toBeTruthy();
  });
});
