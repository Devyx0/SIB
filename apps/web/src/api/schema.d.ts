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
  unit_label: string | null;
  unique_unit_number: string | null;
  en_route_at: string | null;
  closeout_outcome: string | null;
  closeout_urgent: boolean | null;
}

export interface VisitEntry {
  visit_id: number;
  employee_id: number;
  employee_name: string | null;
  en_route_at: string;
  closeout_at: string | null;
  outcome: string | null;
  closeout_comment: string | null;
  photo_ids: number[];
}

export interface JustificationEntry {
  id: number;
  decision_type: string;
  before_value: Record<string, unknown> | null;
  after_value: Record<string, unknown> | null;
  justification_text: string;
  input_method: string | null;
  created_at: string;
  employee_id: number;
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
  project_id: number | null;
  project_label: string | null;
  html_link: string | null;
  caller_type: string | null;
  followup_log: FollowupEntry[];
  justification_log: JustificationEntry[];
  visits: VisitEntry[];
  caller_name: string | null;
  caller_phone: string | null;
  caller_phone_placeholder: boolean;
  caller_email: string | null;
  caller_email_placeholder: boolean;
  caller_tenant_id: number | null;
  raw_caller_body: { entry_permission: string | null; animals: string | null; problems: string | null } | null;
  problems: string | null;
  triage_model_version: string | null;
  ft_link: string | null;
  ft_name: string | null;
  // Latest evaluation (triage-time or manual re-check); null for tech/contractor.
  weather_evaluation: WeatherEvaluation | null;
}

export interface WeatherEvaluation {
  evaluation_id: number;
  status: 'ok' | 'location_unknown' | 'source_failed';
  location: string | null;
  band_name: string | null;
  suggested_tier: string | null;
  direction: 'higher' | 'lower' | 'equal' | null;
  is_critical: boolean;
  min_forecast_temp_24h_c: number | null;
  current_temp_c: number | null;
  wind_chill_c: number | null;
  current_urgency_tier: string | null;
  current_tier_at_eval: string | null;
  forecast_time_local: string | null;
  source: string | null;
  source_url: string | null;
  evaluated_at?: string | null;
}

export interface TriageFeedbackEdit {
  edited_at: string;
  edited_by: number;
  old_level: string;
  new_level: string;
  old_reason: string | null;
  new_reason: string | null;
  old_triage_output: Record<string, unknown>;
  old_triage_model_version: string;
}

export interface TriageFeedback {
  feedback_id: number;
  request_id: number;
  employee_id: number;
  level: 'utile' | 'partiellement utile' | 'pas utile';
  reason: string | null;
  triage_output: Record<string, unknown>;
  triage_model_version: string;
  edit_history: TriageFeedbackEdit[];
  created_at: string;
  updated_at: string;
}

export interface MeResponse {
  employee_id: number;
  nom_employe: string;
  roles: string[];
  weather_escalation_enabled?: boolean;
  /** null/undefined = unrestricted (director); else sectors allowed for create. */
  sector_ids?: number[] | null;
}

export interface ListResponse {
  total: number;
  items: ListRow[];
  unscheduled_items: ListRow[];
}

export interface DossierRow {
  request_id: number;
  last_en_route_at: string;
  last_closeout_at: string | null;
  unit_label: string | null;
  raw_title: string | null;
  territoire: string | null;
  color_code: string | null;
  employee_name: string | null;
  last_outcome: string | null;
  photo_count: number;
  visit_count: number;
  closeout_urgent: boolean | null;
  status: string;
}

export interface DossierListResponse {
  total: number;
  items: DossierRow[];
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

export interface UnitLookup {
  unit_id: number;
  numero_appartement: string;
  rue: string | null;
}

export interface DashboardResponse {
  as_of_date: string;
  today_by_status: Array<{ status: string; count: number }>;
  load_today: Array<{
    employee_id: number;
    nom_employe: string;
    assigned_count: number;
    en_route_count: number;
  }>;
  by_territory: Array<{
    sector_id: number;
    territoire: string;
    active: number;
    AJD: number;
    ajd: number;
    untriaged: number;
    board_link: string;
  }>;
  queue_counts: {
    a_router: number;
    a_redispatcher: number;
    a_router_link: string;
    a_redispatcher_link: string;
  };
  after_hours: null;
  weather: {
    location: string;
    current_temp_c: number | null;
    min_forecast_temp_24h_c: number | null;
    source_credit: string;
  } | null;
  satisfaction: null;
  untriaged_statuses: string[];
}

export interface UtilizationResponse {
  start_date: string;
  end_date: string;
  capacity_enabled: boolean;
  capacity_hours_per_day: number | null;
  planned_footnote: string;
  rows: Array<{
    employee_id: number;
    nom_employe: string;
    territoire: string | null;
    calls_assigned: number;
    calls_closed: number;
    planned_minutes: number;
    planned_unknown_count: number;
    visit_minutes: number;
    visits_count: number;
    outcome_mix: {
      complete: number;
      partial_reschedule: number;
      partial_expertise: number;
      failed: number;
    };
    capacity_minutes: number | null;
    utilization_pct: number | null;
  }>;
}

// ── Portfolio browser (sector → project → building → unit → tenant) ─────────

export interface PortfolioSectorSummary {
  sector_id: number;
  territoire: string | null;
  color_code: string | null;
  project_count: number;
  building_count: number;
  unit_count: number;
  /** Units with a current lease that has at least one tenant. */
  occupied_unit_count: number;
  /** Up to three project names, largest first. */
  top_projects: string[];
}

export interface PortfolioProjectSummary {
  project_id: number;
  nom_unique_projet: string | null;
  adresse_quickbooks: string | null;
  accounting_project_number: string | null;
  building_count: number;
}

export interface PortfolioBuildingSummary {
  building_id: number;
  project_id: number;
  sector_id: number;
  adresse: string | null;
  ville: string | null;
  code_postal: string | null;
  web_building_name: string | null;
  actif_inactif: string | null;
  unit_count: number;
}

export interface PortfolioUnitSummary {
  unit_id: number;
  numero_appartement: string | null;
  rue: string | null;
  grandeur: string | null;
  tenant_name: string | null;
  occupant_count: number;
  lease_statut: string | null;
}

export interface PortfolioSectorDetail {
  sector_id: number;
  territoire: string | null;
  color_code: string | null;
  project_count: number;
  building_count: number;
  projects: PortfolioProjectSummary[];
}

export interface PortfolioProjectDetail {
  project_id: number;
  nom_unique_projet: string | null;
  adresse_quickbooks: string | null;
  accounting_project_number: string | null;
  building_count: number;
  buildings: PortfolioBuildingSummary[];
}

export interface PortfolioBuildingDetail {
  building_id: number;
  project_id: number;
  sector_id: number;
  adresse: string | null;
  ville: string | null;
  code_postal: string | null;
  web_building_name: string | null;
  actif_inactif: string | null;
  nb_logements: string | null;
  nb_etages: string | null;
  annee_construction: string | null;
  territoire: string | null;
  nom_unique_projet: string | null;
  unit_count: number;
  units: PortfolioUnitSummary[];
}

export interface PortfolioLease {
  lease_id: number;
  debut_bail: string | null;
  fin_bail: string | null;
  statut: string | null;
  langue_bail: string | null;
}

export interface PortfolioTenant {
  tenant_id: number;
  nom_complet: string | null;
  telephone: string | null;
  telephone_international: string | null;
  courriel: string | null;
  capacite: string | null;
  /** True when at least one turnover on the unit names this tenant. */
  has_turnover: boolean;
}

export interface PortfolioUnitDetail {
  unit_id: number;
  building_id: number;
  project_id: number;
  sector_id: number;
  numero_appartement: string | null;
  rue: string | null;
  grandeur: string | null;
  building_adresse: string | null;
  web_building_name: string | null;
  nom_unique_projet: string | null;
  territoire: string | null;
  lease: PortfolioLease | null;
  tenants: PortfolioTenant[];
}

export interface TurnoverSettlement {
  deposit_amount_owed: string | null;
  deposit_received: boolean | null;
  deposit_refund_status: string | null;
  amount_owed_by_tenant: string | null;
  tal_dossier_open: boolean | null;
  edl_received: boolean | null;
  edl_satisfactory: boolean | null;
  notes: string | null;
}

export interface TurnoverFurniture {
  appliance_type: string | null;
  included_current: boolean | null;
  included_new: boolean | null;
}

export interface Turnover {
  turnover_id: number;
  tenant_role: 'incoming' | 'outgoing' | null;
  move_reason: string | null;
  outgoing_tenant_name: string | null;
  lease_end_date: string | null;
  move_out_confirmed_date: string | null;
  move_out_time: string | null;
  key_return_method: string | null;
  assignment_desired_date: string | null;
  outgoing_loyer: string | null;
  outgoing_fin_bail: string | null;
  incoming_tenant_name: string | null;
  lease_start_date: string | null;
  move_in_confirmed_date: string | null;
  move_in_time: string | null;
  key_pickup_method: string | null;
  intercom_status: string | null;
  cleaning_status: string | null;
  parking_remote_status: string | null;
  parking_stall_current: string | null;
  parking_stall_new: string | null;
  internet_transfer_current: boolean | null;
  internet_transfer_new: boolean | null;
  furnished_status_current: string | null;
  furnished_status_new: string | null;
  room_count: string | null;
  mattress_size: string | null;
  pre_departure_inspection_notes: string | null;
  general_notes: string | null;
  settlement: TurnoverSettlement | null;
  furniture: TurnoverFurniture[];
}

export interface TenantTurnover {
  unit_id: number;
  tenant: PortfolioTenant;
  turnovers: Turnover[];
  other_turnovers: Turnover[];
}
