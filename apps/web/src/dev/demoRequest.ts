// Dev-only demo call for checking the dispatch board and its detail panel
// without real data. Shown only by the Vite dev server (`npm run dev`) and
// only when the board URL carries ?demo=1 — production builds drop it
// (import.meta.env.DEV is false there). Nothing is written anywhere: actions
// in the panel still go to the API and will fail for this fake id.
import type { ListRow, RequestDetail } from '../api/schema.d.ts';

/** Negative so it can never collide with a real request id. */
export const DEMO_REQUEST_ID = -1;

export function isDemoEnabled(params: URLSearchParams): boolean {
  return import.meta.env.DEV && params.get('demo') === '1';
}

const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Toronto' });

export const DEMO_ROW: ListRow = {
  request_id: DEMO_REQUEST_ID,
  start_date: today,
  asnu: 'DEMO-001',
  urgency_tier: 'URGENT',
  urgency_raw: 'URGENT',
  raw_title: "[DÉMO] Fuite sous l'évier de cuisine",
  building_id: null,
  building_address: '1240 chemin Sainte-Foy, Québec',
  building_full_address: '1240 chemin Sainte-Foy, Québec, G1S 2J3',
  building_name: 'Le Montcalm',
  sector_id: null,
  territoire: 'Haute-Ville',
  color_code: '#0b3263',
  assigned_employee_id: null,
  assigned_employee_name: 'Marc Tremblay',
  subcontractor_name: null,
  time_estimate_bucket: '1-2 h',
  time_estimate_raw: '1 h 30',
  source_calendar: 'main',
  source_calendar_label: 'Principal',
  status: 'triaged',
  event_id: null,
  estimated_cost: 180,
  next_follow_up_date: null,
  next_steps: 'Vérifier le siphon et le raccord sous l’évier.',
  last_followup_date: today,
  last_followup_text: 'Locataire avisée par téléphone.',
  unit_label: '204',
  unique_unit_number: '1580-204 Perigord',
  en_route_at: null,
  arrived_at: null,
  closeout_outcome: null,
  closeout_urgent: false,
  duplicate_of_request_id: null,
  addition_to_request_id: null,
};

export const DEMO_DETAIL: RequestDetail = {
  ...DEMO_ROW,
  problem_summary: 'Fuite probable au siphon de l’évier; armoire du bas gonflée par l’eau.',
  triage_summary: 'Urgence Urgent : dégât d’eau actif dans une unité occupée.',
  work_performed: null,
  other_notes: 'Prévoir des serviettes et un seau; le plancher est déjà humide.',
  delegable_notes: null,
  report_notes: null,
  tenant_agreement_notes: null,
  entry_permission: 'Oui, en tout temps',
  animals: 'Un chat (reste dans la chambre)',
  occupants_raw: null,
  follow_up_expected: true,
  unit_id: null,
  project_id: null,
  project_label: null,
  html_link: null,
  caller_type: 'tenant',
  followup_log: [
    { followup_id: -1, entry_date: today, entered_by_initials: 'JB', entry_text: 'Locataire avisée par téléphone.' },
  ],
  justification_log: [],
  visits: [],
  caller_name: 'Sophie Gagnon',
  caller_phone: '418 555-0142',
  caller_phone_placeholder: false,
  caller_email: 'locataire@example.com',
  caller_email_placeholder: false,
  caller_tenant_id: null,
  raw_caller_body: {
    entry_permission: 'oui',
    animals: 'chat',
    problems: 'Il y a de l’eau sous mon évier et l’armoire est toute gonflée.',
  },
  problems: 'Eau sous l’évier de cuisine, armoire du bas gonflée.',
  category_raw: 'Plomberie',
  element: 'Plomberie',
  symptome: 'Fuite',
  composante: 'Siphon',
  emplacement: 'Cuisine',
  triage_model_version: 'demo',
  ft_link: null,
  ft_name: null,
  weather_evaluation: null,
  tasks: [
    {
      task_id: -101,
      request_id: DEMO_REQUEST_ID,
      description: 'Réparer la fuite sous l’évier',
      status: 'queued',
      assigned_employee_id: null,
      vendor_id: null,
      subcontractor_name: 'Fortin',
      due_at: null,
      urgency_tier: 'URGENT',
      source: 'dispatcher',
      accepted_at: `${today}T12:00:00Z`,
      parent_task_id: null,
      sort_order: 0,
      created_at: `${today}T12:00:00Z`,
      updated_at: `${today}T12:00:00Z`,
    },
  ],
};
