import { useQuery } from '@tanstack/react-query';
import { fetchRequests, type RequestListParams } from '../api/client';
import type { ListResponse } from '../api/schema.d.ts';

export function useRequests(params: RequestListParams | null) {
  return useQuery<ListResponse, Error>({
    queryKey: ['requests', params],
    queryFn: () => fetchRequests(params!),
    enabled: params !== null,
  });
}
