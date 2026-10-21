import type { ListResponse, RequestDetail, SectorLookup, EmployeeLookup, BuildingLookup, UnitLookup, MeResponse, JustificationEntry, TriageFeedback, TriageFeedbackEdit, WeatherEvaluation, DossierListResponse, DossierRow, DashboardResponse, UtilizationResponse, PortfolioSectorSummary, PortfolioSectorDetail, PortfolioProjectDetail, PortfolioBuildingDetail, PortfolioUnitDetail, PortfolioSearchResult, PortfolioUnitListPage, PortfolioCreated, BuildingReference, FicheEntry, PaintSpec, BuildingDocument, PortfolioLease, PortfolioTenant, Turnover, TenantTurnover, SurveyPublic, AlertListResponse } from './schema.d.ts';
export type { JustificationEntry, BuildingLookup, UnitLookup, TriageFeedback, TriageFeedbackEdit, WeatherEvaluation, DossierListResponse, DossierRow, DashboardResponse, UtilizationResponse, PortfolioSectorSummary, PortfolioSectorDetail, PortfolioProjectDetail, PortfolioBuildingDetail, PortfolioUnitDetail, PortfolioSearchResult, PortfolioUnitListPage, PortfolioCreated, BuildingReference, FicheEntry, PaintSpec, BuildingDocument, PortfolioLease, PortfolioTenant, Turnover, TenantTurnover, SurveyPublic, AlertListResponse };
import { supabase } from '../lib/supabase';

// Dev: same-origin (Vite proxies /api → backend). Prod: absolute API host.
const API_BASE = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_URL ?? '');

// The portal never shows English generic errors — unknown failures map to this.
export const GENERIC_ERROR_FR = 'Une erreur est survenue — réessayez';

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly traceId?: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface RequestListParams {
  // Optional as a pair — omit both to list any date (tech portal).
  start_date?: string;
  end_date?: string;
  status?: string[];
  building_id?: number;
  sector_id?: number;
  assigned_employee_id?: number;
  urgency?: string;
  source_calendar?: string;
  q?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
  redispatch?: boolean;
  has_subcontractor?: boolean;
}

async function request<T>(path: string, method: string, body?: unknown): Promise<T> {
  const { data: { session } } = await supabase.auth.getSession();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (session?.access_token) headers['authorization'] = `Bearer ${session.access_token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    await supabase.auth.signOut();
    window.location.href = '/login';
    throw new ApiError('UNAUTHORIZED', 'Session expired');
  }

  if (!res.ok) {
    let code = `HTTP_${res.status}`;
    let message = GENERIC_ERROR_FR;
    let traceId: string | undefined;
    let details: unknown;
    try {
      const envelope = await res.json();
      if (envelope?.error?.code) code = envelope.error.code;
      if (envelope?.error?.message) message = envelope.error.message;
      if (envelope?.error?.request_id) traceId = envelope.error.request_id;
      details = envelope?.error?.details;
    } catch { /* ignore parse error */ }
    throw new ApiError(code, message, traceId, details);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function apiFetch<T>(path: string): Promise<T> {
  return request<T>(path, 'GET');
}

function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, 'POST', body);
}

function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, 'PATCH', body);
}

function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, 'PUT', body);
}

function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, 'DELETE');
}

function buildQuery(params: RequestListParams): string {
  const q = new URLSearchParams();
  if (params.start_date) q.set('start_date', params.start_date);
  if (params.end_date) q.set('end_date', params.end_date);
  if (params.status?.length) params.status.forEach((s) => q.append('status', s));
  if (params.building_id != null) q.set('building_id', String(params.building_id));
  if (params.sector_id != null) q.set('sector_id', String(params.sector_id));
  if (params.assigned_employee_id != null) q.set('assigned_employee_id', String(params.assigned_employee_id));
  if (params.urgency) q.set('urgency', params.urgency);
  if (params.source_calendar) q.set('source_calendar', params.source_calendar);
  if (params.q) q.set('q', params.q);
  if (params.sort_by) q.set('sort_by', params.sort_by);
  if (params.sort_dir) q.set('sort_dir', params.sort_dir);
  if (params.limit != null) q.set('limit', String(params.limit));
  if (params.offset != null) q.set('offset', String(params.offset));
  if (params.redispatch) q.set('redispatch', 'true');
  if (params.has_subcontractor != null) q.set('has_subcontractor', String(params.has_subcontractor));
  return q.toString();
}

export function fetchRequests(params: RequestListParams): Promise<ListResponse> {
  return apiFetch<ListResponse>(`/api/v1/requests?${buildQuery(params)}`);
}

export function fetchRequest(id: number): Promise<RequestDetail> {
  return apiFetch<RequestDetail>(`/api/v1/requests/${id}`);
}

export interface DossierListParams {
  outcome?: string;
  employee_id?: number;
  start_date?: string;
  end_date?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export function fetchDossiers(params: DossierListParams): Promise<DossierListResponse> {
  const qp = new URLSearchParams();
  if (params.outcome) qp.set('outcome', params.outcome);
  if (params.employee_id != null) qp.set('employee_id', String(params.employee_id));
  if (params.start_date) qp.set('start_date', params.start_date);
  if (params.end_date) qp.set('end_date', params.end_date);
  if (params.q) qp.set('q', params.q);
  if (params.limit != null) qp.set('limit', String(params.limit));
  if (params.offset != null) qp.set('offset', String(params.offset));
  return apiFetch<DossierListResponse>(`/api/v1/dossiers?${qp.toString()}`);
}

export function fetchSectors(): Promise<SectorLookup[]> {
  return apiFetch<SectorLookup[]>('/api/v1/lookup/sectors');
}

export function fetchEmployees(): Promise<EmployeeLookup[]> {
  return apiFetch<EmployeeLookup[]>('/api/v1/lookup/employees');
}

export function fetchMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>('/api/v1/employees/me');
}

export function fetchDashboard(): Promise<DashboardResponse> {
  return apiFetch<DashboardResponse>('/api/v1/analytics/dashboard');
}

export function fetchUtilization(start_date: string, end_date: string): Promise<UtilizationResponse> {
  const q = new URLSearchParams({ start_date, end_date });
  return apiFetch<UtilizationResponse>(`/api/v1/analytics/utilization?${q}`);
}

export interface Justification { text: string; input_method: 'voice' | 'typed'; }

export function goEnRoute(id: number, body: { current_status: string; current_start_date: string | null; lat: number | null; lng: number | null }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/en-route`, body);
}

export function markArrived(id: number, body: { current_status: string; lat: number | null; lng: number | null }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/arrived`, body);
}

// Raw image body — the mime travels in Content-Type (no multipart).
export async function uploadPhoto(id: number, file: File): Promise<{ attachment_id: number }> {
  const { data: { session } } = await supabase.auth.getSession();
  const headers: Record<string, string> = { 'Content-Type': file.type };
  if (session?.access_token) headers['authorization'] = `Bearer ${session.access_token}`;
  const res = await fetch(`${API_BASE}/api/v1/requests/${id}/photos`, { method: 'POST', headers, body: file });
  if (!res.ok) {
    let message = GENERIC_ERROR_FR;
    try { message = (await res.json())?.error?.message ?? message; } catch { /* ignore */ }
    throw new ApiError(`HTTP_${res.status}`, message);
  }
  return res.json();
}

export interface CloseoutBody {
  outcome: 'complete' | 'partial_reschedule' | 'partial_expertise' | 'failed';
  comment: string;
  input_method: 'voice' | 'typed';
  attachment_ids: number[];
  next_date: string | null;
  urgent: boolean;
  current_status: string;
  lat: number | null;
  lng: number | null;
}

export function closeoutRequest(id: number, body: CloseoutBody): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/closeout`, body);
}

export function fetchPhotoUrl(requestId: number, attachmentId: number): Promise<{ url: string }> {
  return apiFetch(`/api/v1/requests/${requestId}/photos/${attachmentId}`);
}

export function dispatchAssign(id: number, body: { employee_id: number | null; current_assigned_employee_id: number | null; current_start_date: string | null; current_urgency_tier: string | null; justification?: Justification }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/assign`, body);
}

export function dispatchReschedule(id: number, body: { start_date: string; current_start_date: string | null; current_assigned_employee_id: number | null; current_urgency_tier: string | null; justification?: Justification }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/reschedule`, body);
}

export function dispatchSetUrgency(id: number, body: { urgency_tier: string | null; current_urgency_tier: string | null; current_assigned_employee_id: number | null; current_start_date: string | null; justification?: Justification; weather_evaluation_id?: number | null }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/urgency`, body);
}

export function checkWeather(id: number): Promise<WeatherEvaluation> {
  return apiPost<WeatherEvaluation>(`/api/v1/requests/${id}/weather-check`, {});
}

export function dispatchSetFollowUpDate(id: number, body: { next_follow_up_date: string | null; current_next_follow_up_date: string | null; justification?: Justification }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/follow-up-date`, body);
}

export function dispatchSetNextSteps(id: number, body: { next_steps: string | null; current_next_steps: string | null; justification?: Justification }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/next-steps`, body);
}

export function dispatchSetCost(id: number, body: { estimated_cost: number | null; current_estimated_cost: number | null; justification?: Justification }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/cost`, body);
}

export interface DispatchFields {
  assigned_employee_id: number | null;
  start_date: string | null;
  urgency_tier: string | null;
  next_follow_up_date: string | null;
  next_steps: string | null;
  estimated_cost: number | null;
}

/** One « Enregistrer » in the call details: only the changed fields, one justification. */
export function dispatchSave(id: number, body: {
  current: DispatchFields;
  changes: Partial<DispatchFields>;
  justification: Justification;
}): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/dispatch`, body);
}

/** Single-use AssemblyAI streaming token (the API key stays on the server). */
export function fetchSpeechToken(): Promise<{ token: string; expires_in_seconds: number }> {
  return apiFetch('/api/v1/speech/token');
}

export function dispatchAddLog(id: number, body: { entry_text: string }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/log`, body);
}

export interface TechnicianSuggestion {
  employee_id: number;
  initials: string | null;
  name: string;
  why: string;
  is_en_route: boolean;
}

export function fetchTechnicianSuggestions(
  id: number,
  lang: 'fr' | 'en' = 'fr',
): Promise<{ request_id: number; suggestions: TechnicianSuggestion[] }> {
  return apiFetch(`/api/v1/requests/${id}/technician-suggestions?lang=${lang}`);
}

export function triggerTriage(
  id: number,
  opts?: { lang?: 'fr' | 'en' },
): Promise<{ request_id: number; status: string }> {
  return apiPost(`/api/v1/requests/${id}/triage`, { lang: opts?.lang ?? 'fr' });
}

export function routeRequest(id: number, body: { source_calendar: string; expected_source_calendar: string | null; justification?: Justification }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/route`, body);
}

export interface MatchAddressBody {
  civic: string;
  street: string;
  apartment?: string;
}

export interface CandidateBuilding {
  building_id: number;
  adresse: string | null;
}

export interface MatchAddressResponse {
  match_status: 'exact' | 'building_only' | 'ambiguous' | 'no_match' | 'garbled';
  building_id: number | null;
  unit_id: number | null;
  building_adresse: string | null;
  candidate_building_ids: number[];
  candidate_buildings: CandidateBuilding[];
}

export function matchAddress(body: MatchAddressBody): Promise<MatchAddressResponse> {
  return apiPost('/api/v1/intake/match', body);
}

export type AnimalsChoice = 'oui' | 'non' | 'na';

export type AccessChoice = 'yes' | 'yes_instructions' | 'tenant_required' | 'common_area';

export interface IntakeBody {
  caller_name: string;
  caller_email?: string;
  phone_1: string;
  phone_2?: string;
  building_id: number;
  unit_id: number;
  access: AccessChoice;
  access_details?: string;
  animals?: AnimalsChoice;
  animal_details?: string;
  problem: string;
  category?: string;
  element: string;
  symptome: string;
  composante: string;
  emplacement: string;
  secondary_name?: string;
  secondary_email?: string;
  attention?: string;
  ui_lang?: 'fr' | 'en';
  /** Photos of the problem, sent with the call (recommended, max 5). */
  photos?: { mime: 'image/jpeg' | 'image/png' | 'image/webp'; data_base64: string }[];
}

export interface IntakeResponse {
  request_id: number;
  building_id: number | null;
  unit_id: number | null;
  match_status: string;
}

export interface PublicIntakeLookupBody {
  phone?: string;
  email?: string;
  turnstile_token: string;
}

export interface PublicIntakeLookupResponse {
  session_token: string;
  caller_name: string;
  phone: string | null;
  email: string | null;
  address_label: string;
  unit_label: string | null;
  pets_allowed: boolean;
}

export interface PublicIntakeSubmitBody {
  session_token: string;
  turnstile_token: string;
  access: AccessChoice;
  access_details?: string;
  animals?: AnimalsChoice;
  animal_details?: string;
  problem: string;
  category?: string;
  element: string;
  symptome: string;
  composante: string;
  emplacement: string;
  secondary_name?: string;
  secondary_email?: string;
  attention?: string;
  ui_lang?: 'fr' | 'en';
  photos?: { mime: 'image/jpeg' | 'image/png' | 'image/webp'; data_base64: string }[];
}

export function publicIntakeLookup(body: PublicIntakeLookupBody): Promise<PublicIntakeLookupResponse> {
  return apiPost('/api/v1/public/intake/lookup', body);
}

export function publicIntakeSubmit(body: PublicIntakeSubmitBody): Promise<{ request_id: number }> {
  return apiPost('/api/v1/public/intake/submit', body);
}

export interface LeaseTenant {
  tenant_id: number;
  name: string | null;
  phone: string | null;
  email: string | null;
}

export interface UnitByNumberLookup {
  unit_id: number;
  building_id: number;
  sector_id: number | null;
  unique_unit_number: string | null;
  numero_appartement: string | null;
  rue: string | null;
  building_adresse: string | null;
  pets_allowed: boolean;
  tenants: LeaseTenant[];
}

export function createManualRequest(body: IntakeBody): Promise<IntakeResponse> {
  return apiPost('/api/v1/intake', body);
}

export function fetchBuildings(sectorId?: number): Promise<BuildingLookup[]> {
  const q = sectorId != null ? `?sector_id=${sectorId}` : '';
  return apiFetch(`/api/v1/lookup/buildings${q}`);
}

export function fetchUnits(buildingId: number): Promise<UnitLookup[]> {
  return apiFetch(`/api/v1/lookup/units?building_id=${buildingId}`);
}

export interface UnitNumberHit {
  unit_id: number;
  unique_unit_number: string;
  building_adresse: string | null;
  numero_appartement: string | null;
}

export function fetchUnitByNumber(uniqueUnitNumber: string): Promise<UnitByNumberLookup> {
  const q = encodeURIComponent(uniqueUnitNumber.trim());
  return apiFetch(`/api/v1/lookup/unit-by-number?unique_unit_number=${q}`);
}

export function fetchUnitContext(unitId: number): Promise<UnitByNumberLookup> {
  return apiFetch(`/api/v1/lookup/unit-context?unit_id=${unitId}`);
}

export function searchUnitNumbers(q: string, limit = 20): Promise<UnitNumberHit[]> {
  const term = encodeURIComponent(q.trim());
  return apiFetch(`/api/v1/lookup/unit-numbers?q=${term}&limit=${limit}`);
}

export function fetchFeedback(requestId: number): Promise<TriageFeedback> {
  return apiFetch<TriageFeedback>(`/api/v1/requests/${requestId}/feedback`);
}

export function upsertFeedback(requestId: number, body: { level: string; reason?: string | null }): Promise<TriageFeedback> {
  return apiPost<TriageFeedback>(`/api/v1/requests/${requestId}/feedback`, body);
}

// ── Portfolio browser ────────────────────────────────────────────────────────

export function fetchPortfolioSectors(): Promise<PortfolioSectorSummary[]> {
  return apiFetch('/api/v1/portfolio/sectors');
}

export function fetchPortfolioSector(sectorId: number): Promise<PortfolioSectorDetail> {
  return apiFetch(`/api/v1/portfolio/sectors/${sectorId}`);
}

export function fetchPortfolioProject(projectId: number, sectorId?: number): Promise<PortfolioProjectDetail> {
  const q = sectorId != null ? `?sector_id=${sectorId}` : '';
  return apiFetch(`/api/v1/portfolio/projects/${projectId}${q}`);
}

export function fetchPortfolioBuilding(buildingId: number): Promise<PortfolioBuildingDetail> {
  return apiFetch(`/api/v1/portfolio/buildings/${buildingId}`);
}

export function fetchPortfolioUnit(unitId: number): Promise<PortfolioUnitDetail> {
  return apiFetch(`/api/v1/portfolio/units/${unitId}`);
}

export function searchPortfolio(q: string, limit = 8): Promise<PortfolioSearchResult> {
  return apiFetch(`/api/v1/portfolio/search?q=${encodeURIComponent(q.trim())}&limit=${limit}`);
}

export interface PortfolioUnitListParams {
  sector_id?: number | null;
  project_id?: number | null;
  building_id?: number | null;
  occupancy?: 'vacant' | 'occupied' | null;
  grandeur?: string | null;
  lease_ending_within_days?: number | null;
  q?: string | null;
  page?: number;
  page_size?: number;
}

export function fetchPortfolioUnits(params: PortfolioUnitListParams): Promise<PortfolioUnitListPage> {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') q.set(k, String(v));
  }
  return apiFetch(`/api/v1/portfolio/units?${q.toString()}`);
}

// ── Portfolio editing ────────────────────────────────────────────────────────
// Edits send `changes` (only what changed) and `current` (what the editor saw
// for those fields); a mismatch is refused with STALE_DATA.

export type Patch<T> = { changes: Partial<T>; current: Partial<T> };

export interface ProjectFields {
  nom_unique_projet: string | null;
  adresse_quickbooks: string | null;
  accounting_project_number: string | null;
}

export interface BuildingFields extends Partial<BuildingReference> {
  adresse?: string | null;
  ville?: string | null;
  code_postal?: string | null;
  web_building_name?: string | null;
  actif_inactif?: 'Actif' | 'Inactif' | null;
  nb_logements?: string | null;
  nb_etages?: string | null;
  annee_construction?: string | null;
}

export interface UnitFields {
  numero_appartement: string | null;
  rue: string | null;
  grandeur: string | null;
  unique_unit_number: string | null;
}

export type PaintSpecFields = Omit<PaintSpec, 'paint_spec_id'>;

export function createProject(body: Partial<ProjectFields> & {
  nom_unique_projet: string; first_building: BuildingFields & { sector_id: number; adresse: string };
}): Promise<PortfolioCreated> {
  return apiPost('/api/v1/portfolio/projects', body);
}

export function updateProject(projectId: number, patch: Patch<ProjectFields>): Promise<void> {
  return apiPatch(`/api/v1/portfolio/projects/${projectId}`, patch);
}

export function createBuilding(body: BuildingFields & { project_id: number; sector_id: number; adresse: string }): Promise<PortfolioCreated> {
  return apiPost('/api/v1/portfolio/buildings', body);
}

export function updateBuilding(buildingId: number, patch: Patch<BuildingFields>): Promise<void> {
  return apiPatch(`/api/v1/portfolio/buildings/${buildingId}`, patch);
}

export function createUnit(body: Partial<UnitFields> & { building_id: number; numero_appartement: string }): Promise<PortfolioCreated> {
  return apiPost('/api/v1/portfolio/units', body);
}

export function updateUnit(unitId: number, patch: Patch<UnitFields>): Promise<void> {
  return apiPatch(`/api/v1/portfolio/units/${unitId}`, patch);
}

/** Set one fiche-technique line; value null removes it. */
export function setFicheEntry(buildingId: number, body: { label: string; value: string | null; current_value: string | null }): Promise<void> {
  return apiPut(`/api/v1/portfolio/buildings/${buildingId}/fiche`, body);
}

export function createPaintSpec(buildingId: number, body: Partial<PaintSpecFields>): Promise<PortfolioCreated> {
  return apiPost(`/api/v1/portfolio/buildings/${buildingId}/paint-specs`, body);
}

export function updatePaintSpec(paintSpecId: number, patch: Patch<PaintSpecFields>): Promise<void> {
  return apiPatch(`/api/v1/portfolio/paint-specs/${paintSpecId}`, patch);
}

export function deletePaintSpec(paintSpecId: number): Promise<void> {
  return apiDelete(`/api/v1/portfolio/paint-specs/${paintSpecId}`);
}

export function createBuildingDocument(buildingId: number, body: { title: string; url: string; category?: string | null }): Promise<PortfolioCreated> {
  return apiPost(`/api/v1/portfolio/buildings/${buildingId}/documents`, body);
}

export function deleteBuildingDocument(documentId: number): Promise<void> {
  return apiDelete(`/api/v1/portfolio/documents/${documentId}`);
}

export function fetchTenantTurnover(unitId: number, tenantId: number): Promise<TenantTurnover> {
  return apiFetch(`/api/v1/portfolio/units/${unitId}/tenants/${tenantId}/turnover`);
}

/** Public survey — no auth header; do not redirect to login on 401. */
export async function fetchSurvey(token: string): Promise<SurveyPublic> {
  const res = await fetch(`${API_BASE}/api/v1/survey/${encodeURIComponent(token)}`);
  if (!res.ok) {
    let message = GENERIC_ERROR_FR;
    try { message = (await res.json())?.error?.message ?? message; } catch { /* ignore */ }
    throw new ApiError(`HTTP_${res.status}`, message);
  }
  return res.json();
}

export async function submitSurvey(
  token: string,
  body: { polite: boolean; satisfaction_rating: number; problem_solved: boolean; comments: string | null },
): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE}/api/v1/survey/${encodeURIComponent(token)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let message = GENERIC_ERROR_FR;
    try { message = (await res.json())?.error?.message ?? message; } catch { /* ignore */ }
    throw new ApiError(`HTTP_${res.status}`, message);
  }
  return res.json();
}

export function fetchAlerts(unreadOnly = false): Promise<AlertListResponse> {
  const q = unreadOnly ? '?unread_only=true' : '';
  return apiFetch(`/api/v1/alerts${q}`);
}

export function markAlertRead(alertId: number): Promise<void> {
  return apiPost(`/api/v1/alerts/${alertId}/read`, {});
}

export function markAllAlertsRead(): Promise<void> {
  return apiPost('/api/v1/alerts/read-all', {});
}
