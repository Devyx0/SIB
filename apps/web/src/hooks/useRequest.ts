import { useQuery } from '@tanstack/react-query';
import { fetchRequest } from '../api/client';
import type { RequestDetail } from '../api/schema.d.ts';

export function useRequest(id: number | null) {
  return useQuery<RequestDetail, Error>({
    queryKey: ['request', id],
    queryFn: () => fetchRequest(id!),
    enabled: id !== null,
  });
}
