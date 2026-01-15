import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queries/keys';

export function useModelSearch(query: string, enabled: boolean = true) {
  return useQuery({
    queryKey: queryKeys.models.search(query),
    queryFn: async () => {
      const results = await api.searchModels(query);
      return results as any[];
    },
    enabled: enabled && !!query.trim(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}




