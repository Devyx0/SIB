import { useQuery } from '@tanstack/react-query';
import { fetchRequests, type RequestListParams } from '../api/client';
import type { ListResponse } from '../api/schema.d.ts';

export function useRequests(params: RequestListParams | null, employeeId: string | null) {
  return useQuery<ListResponse, Error>({
    queryKey: ['requests', params, employeeId],
    queryFn: () => fetchRequests(params!, employeeId),
    enabled: params !== null,
  });
}
