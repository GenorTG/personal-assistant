import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queries/keys';
import { useToast } from '@/contexts/ToastContext';

export function useLoadModel() {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useToast();

  return useMutation({
    mutationFn: async ({ modelId, options }: { modelId: string; options?: Record<string, any> }) => {
      await api.loadModel(modelId, options);
      return modelId;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.models.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.services.llm.status() });
      showSuccess('Model loaded successfully');
    },
    onError: (error: Error) => {
      let errorMessage = error.message || 'Failed to load model';
      const apiError = error as any;
      
      // Extract backend logs if available
      if (apiError.response?.logs && Array.isArray(apiError.response.logs)) {
        const errorLogs = apiError.response.logs.filter((log: any) => 
          log.level === 'ERROR' || log.level === 'CRITICAL'
        );
        if (errorLogs.length > 0) {
          errorMessage += `\n\nBackend errors:\n${errorLogs.slice(0, 2).map((log: any) => `[${log.level}] ${log.message}`).join('\n')}`;
          if (errorLogs.length > 2) {
            errorMessage += `\n... and ${errorLogs.length - 2} more error(s)`;
          }
        }
      }
      
      showError(`Error loading model: ${errorMessage}`);
    },
  });
}

export function useDeleteModel() {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useToast();

  return useMutation({
    mutationFn: async (modelId: string) => {
      await api.deleteModel(modelId);
      return modelId;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.models.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.models.metadata.all() });
      showSuccess('Model deleted successfully');
    },
    onError: (error: Error) => {
      showError(`Error deleting model: ${error.message}`);
    },
  });
}

export function useDiscoverModels() {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useToast();

  return useMutation({
    mutationFn: async (forceRefresh: boolean = false) => {
      const result = await api.discoverModels(forceRefresh);
      return result as { models: any[] };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.models.list() });
      queryClient.invalidateQueries({ queryKey: queryKeys.models.metadata.all() });
      const count = data?.models?.length || 0;
      showSuccess(`Discovered ${count} model(s)! Check the Installed tab.`);
    },
    onError: (error: Error) => {
      showError(`Error scanning for models: ${error.message}`);
    },
  });
}

export function useDownloadModel() {
  const { showError } = useToast();

  return useMutation({
    mutationFn: async ({ repoId, filename }: { repoId: string; filename: string }) => {
      const result = await api.downloadModel(repoId, filename);
      return result;
    },
    onError: (error: Error) => {
      showError(`Error starting download: ${error.message}`);
    },
  });
}




