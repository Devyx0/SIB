import { useQuery } from '@tanstack/react-query';
import { fetchRequest } from '../api/client';
import type { RequestDetail } from '../api/schema.d.ts';

export function useRequest(id: number | null, employeeId: string | null) {
  return useQuery<RequestDetail, Error>({
    queryKey: ['request', id, employeeId],
    queryFn: () => fetchRequest(id!, employeeId),
    enabled: id !== null,
  });
}
