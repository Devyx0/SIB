import type { ListResponse, RequestDetail, SectorLookup, EmployeeLookup } from './schema.d.ts';

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

function buildHeaders(employeeId: string | null): HeadersInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (import.meta.env.DEV && employeeId) {
    headers['x-dev-employee-id'] = employeeId;
  }
  return headers;
}

async function apiFetch<T>(path: string, employeeId: string | null): Promise<T> {
  const res = await fetch(path, { headers: buildHeaders(employeeId) });
  if (!res.ok) {
    let code = `HTTP_${res.status}`;
    let message = res.statusText;
    let traceId: string | undefined;
    try {
      const body = await res.json();
      if (body?.error?.code) code = body.error.code;
      if (body?.error?.message) message = body.error.message;
      if (body?.error?.request_id) traceId = body.error.request_id;
    } catch {
      // ignore parse error
    }
    throw new ApiError(code, message, traceId);
  }
  return res.json() as Promise<T>;
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

export function fetchRequests(params: RequestListParams, employeeId: string | null): Promise<ListResponse> {
  return apiFetch<ListResponse>(`/api/v1/requests?${buildQuery(params)}`, employeeId);
}

export function fetchRequest(id: number, employeeId: string | null): Promise<RequestDetail> {
  return apiFetch<RequestDetail>(`/api/v1/requests/${id}`, employeeId);
}

export function fetchSectors(employeeId: string | null): Promise<SectorLookup[]> {
  return apiFetch<SectorLookup[]>('/api/v1/lookup/sectors', employeeId);
}

export function fetchEmployees(employeeId: string | null): Promise<EmployeeLookup[]> {
  return apiFetch<EmployeeLookup[]>('/api/v1/lookup/employees', employeeId);
}
