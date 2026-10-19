import type { ListResponse, RequestDetail, SectorLookup, EmployeeLookup, BuildingLookup, UnitLookup, MeResponse, JustificationEntry, TriageFeedback, TriageFeedbackEdit, WeatherEvaluation } from './schema.d.ts';
export type { JustificationEntry, BuildingLookup, UnitLookup, TriageFeedback, TriageFeedbackEdit, WeatherEvaluation };
import { supabase } from '../lib/supabase';

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly traceId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface RequestListParams {
  start_date: string;
  end_date: string;
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
}

async function request<T>(path: string, method: string, body?: unknown): Promise<T> {
  const { data: { session } } = await supabase.auth.getSession();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (session?.access_token) headers['authorization'] = `Bearer ${session.access_token}`;

  const res = await fetch(path, {
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
    let message = res.statusText;
    let traceId: string | undefined;
    try {
      const envelope = await res.json();
      if (envelope?.error?.code) code = envelope.error.code;
      if (envelope?.error?.message) message = envelope.error.message;
      if (envelope?.error?.request_id) traceId = envelope.error.request_id;
    } catch { /* ignore parse error */ }
    throw new ApiError(code, message, traceId);
  }
  return res.json() as Promise<T>;
}

function apiFetch<T>(path: string): Promise<T> {
  return request<T>(path, 'GET');
}

function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, 'POST', body);
}

function buildQuery(params: RequestListParams): string {
  const q = new URLSearchParams();
  q.set('start_date', params.start_date);
  q.set('end_date', params.end_date);
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
  return q.toString();
}

export function fetchRequests(params: RequestListParams): Promise<ListResponse> {
  return apiFetch<ListResponse>(`/api/v1/requests?${buildQuery(params)}`);
}

export function fetchRequest(id: number): Promise<RequestDetail> {
  return apiFetch<RequestDetail>(`/api/v1/requests/${id}`);
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

export interface Justification { text: string; input_method: 'voice' | 'typed'; }

export function dispatchAssign(id: number, body: { employee_id: number | null; current_assigned_employee_id: number | null; current_start_date: string | null; current_urgency_tier: string | null; justification: Justification }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/assign`, body);
}

export function dispatchReschedule(id: number, body: { start_date: string; current_start_date: string | null; current_assigned_employee_id: number | null; current_urgency_tier: string | null; justification: Justification }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/reschedule`, body);
}

export function dispatchSetUrgency(id: number, body: { urgency_tier: string | null; current_urgency_tier: string | null; current_assigned_employee_id: number | null; current_start_date: string | null; justification: Justification; weather_evaluation_id?: number | null }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/urgency`, body);
}

export function checkWeather(id: number): Promise<WeatherEvaluation> {
  return apiPost<WeatherEvaluation>(`/api/v1/requests/${id}/weather-check`, {});
}

export function dispatchSetFollowUpDate(id: number, body: { next_follow_up_date: string | null; current_next_follow_up_date: string | null }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/follow-up-date`, body);
}

export function dispatchSetNextSteps(id: number, body: { next_steps: string | null; current_next_steps: string | null }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/next-steps`, body);
}

export function dispatchSetCost(id: number, body: { estimated_cost: number | null; current_estimated_cost: number | null }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/cost`, body);
}

export function dispatchAddLog(id: number, body: { entry_text: string }): Promise<RequestDetail> {
  return apiPost(`/api/v1/requests/${id}/log`, body);
}

export function triggerTriage(id: number): Promise<{ request_id: number; status: string }> {
  return apiPost(`/api/v1/requests/${id}/triage`, {});
}

export function routeRequest(id: number, body: { source_calendar: string; expected_source_calendar: string | null }): Promise<RequestDetail> {
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

export interface IntakeBody {
  caller_name: string;
  caller_email?: string;
  phone_1?: string;
  civic: string;
  street: string;
  apartment?: string;
  city: string;
  access: 'yes' | 'tenant_required' | 'common_area' | 'unknown';
  access_details?: string;
  animals?: AnimalsChoice;
  animal_details?: string;
  problem: string;
  attention?: string;
  building_id_override?: number;
  unit_id_override?: number;
}

export interface IntakeResponse {
  request_id: number;
  building_id: number | null;
  unit_id: number | null;
  match_status: string;
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

export function fetchFeedback(requestId: number): Promise<TriageFeedback> {
  return apiFetch<TriageFeedback>(`/api/v1/requests/${requestId}/feedback`);
}

export function upsertFeedback(requestId: number, body: { level: string; reason?: string | null }): Promise<TriageFeedback> {
  return apiPost<TriageFeedback>(`/api/v1/requests/${requestId}/feedback`, body);
}
