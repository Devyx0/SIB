import { useQuery } from '@tanstack/react-query';
import { fetchRequest } from '../api/client';
import type { RequestDetail } from '../api/schema.d.ts';
import { DEMO_DETAIL, DEMO_REQUEST_ID } from '../dev/demoRequest';

export function useRequest(id: number | null, opts?: { refetchInterval?: number | false }) {
  return useQuery<RequestDetail, Error>({
    queryKey: ['request', id],
    // The dev-only demo call never hits the API (see dev/demoRequest.ts).
    queryFn: () => (import.meta.env.DEV && id === DEMO_REQUEST_ID ? Promise.resolve(DEMO_DETAIL) : fetchRequest(id!)),
    enabled: id !== null,
    refetchInterval: opts?.refetchInterval,
  });
}
