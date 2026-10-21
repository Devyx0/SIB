import { useQuery } from '@tanstack/react-query';
import { fetchTasks, type TaskListParams } from '../api/client';
import type { TaskListResponse } from '../api/schema.d.ts';

export function useTasks(params: TaskListParams | null) {
  return useQuery<TaskListResponse, Error>({
    queryKey: ['tasks', params],
    queryFn: () => fetchTasks(params!),
    enabled: params !== null,
  });
}
