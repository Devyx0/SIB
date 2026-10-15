// Hand-written from OpenAPI spec — regenerate with: npm run gen-schema

export type StatusValue =
  | 'intake_received'
  | 'triage_pending'
  | 'triaged'
  | 'triage_clarify'
  | 'triage_proposal'
  | 'triage_failed'
  | 'en_route'
  | 'closed';

export type SortKey =
  | 'start_date'
  | 'asnu'
  | 'urgency_tier'
  | 'raw_title'
  | 'territoire'
  | 'building_address'
  | 'assigned_employee_name'
  | 'subcontractor_name'
  | 'time_estimate_bucket'
  | 'status'
  | 'source_calendar'
  | 'last_followup_date'
  | 'estimated_cost'
  | 'next_follow_up_date'
  | 'next_steps';

export interface FollowupEntry {
  followup_id: number;
  entry_date: string | null;
  entered_by_initials: string | null;
  entry_text: string | null;
}

export interface ListRow {
  request_id: number;
  start_date: string | null;
  asnu: string | null;
  urgency_tier: string | null;
  urgency_raw: string | null;
  raw_title: string | null;
  building_id: number | null;
  building_address: string | null;
  building_name: string | null;
  sector_id: number | null;
  territoire: string | null;
  color_code: string | null;
  assigned_employee_id: number | null;
  assigned_employee_name: string | null;
  subcontractor_name: string | null;
  time_estimate_bucket: string | null;
  time_estimate_raw: string | null;
  source_calendar: string | null;
  source_calendar_label: string | null;
  status: string;
  event_id: string | null;
  estimated_cost: number | null;
  next_follow_up_date: string | null;
  next_steps: string | null;
  last_followup_date: string | null;
  last_followup_text: string | null;
}

export interface RequestDetail extends ListRow {
  problem_summary: string | null;
  triage_summary: string | null;
  work_performed: string | null;
  other_notes: string | null;
  delegable_notes: string | null;
  report_notes: string | null;
  tenant_agreement_notes: string | null;
  entry_permission: string | null;
  animals: string | null;
  occupants_raw: string | null;
  follow_up_expected: boolean | null;
  unit_id: number | null;
  unit_label: string | null;
  project_id: number | null;
  project_label: string | null;
  html_link: string | null;
  caller_type: string | null;
  followup_log: FollowupEntry[];
  caller_name: string | null;
  caller_phone: string | null;
  caller_email: string | null;
  caller_tenant_id: number | null;
}

export interface MeResponse {
  employee_id: number;
  nom_employe: string;
  roles: string[];
}

export interface ListResponse {
  total: number;
  items: ListRow[];
}

export interface SectorLookup {
  sector_id: number;
  territoire: string;
  color_code: string | null;
}

export interface BuildingLookup {
  building_id: number;
  adresse: string | null;
  web_building_name: string | null;
  sector_id: number | null;
}

export interface EmployeeLookup {
  employee_id: number;
  nom_employe: string;
  role: string;
}
