import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queries/keys';
import type { ModelInfo } from '@/types/api';

export function useModels() {
  return useQuery<ModelInfo[]>({
    queryKey: queryKeys.models.list(),
    queryFn: async () => {
      const data = await api.listModels();
      return data as ModelInfo[];
    },
    staleTime: 60 * 1000, // 1 minute
  });
}

export function useModelMetadata() {
  return useQuery({
    queryKey: queryKeys.models.metadata.all(),
    queryFn: async () => {
      const result = await api.getAllModelMetadata();
      return result as { models: any[] };
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}




