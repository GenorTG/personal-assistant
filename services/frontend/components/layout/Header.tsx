'use client';

import { useState } from 'react';
import { Settings, Package, Bug, Calendar as CalendarIcon, CheckCircle2, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useSettings } from '@/contexts/SettingsContext';
import { useModels } from '@/hooks/queries/useModels';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queries/keys';
import { cn } from '@/lib/utils';
import type { ActivePanel } from '@/hooks/useAppState';
import type { ModelInfo } from '@/types/api';
import type { ApiError } from '@/types/api';

interface HeaderProps {
  activePanel: ActivePanel;
  onTogglePanel: (panel: ActivePanel) => void;
}

export function Header({ activePanel, onTogglePanel }: HeaderProps) {
  const { modelLoaded, currentModel, refresh } = useSettings();
  const { data: models = [] } = useModels();
  const { showSuccess, showError } = useToast();
  const queryClient = useQueryClient();
  const [loadingModelId, setLoadingModelId] = useState<string | null>(null);

  const installedModels = models.filter((m: ModelInfo) => m.downloaded);

  const loadModelMutation = useMutation({
    mutationFn: async (modelId: string) => {
      setLoadingModelId(modelId);
      try {
        await api.post(`/api/models/${modelId}/load`, {}, { timeout: 90000, retries: 0 }); // 90s timeout, no retries
        // Wait a bit for model to fully load before checking status
        await new Promise(resolve => setTimeout(resolve, 1000));
        // Refresh settings to get updated model status
        await refresh();
        // Also invalidate models query to refresh list
        queryClient.invalidateQueries({ queryKey: queryKeys.models.list() });
        // Poll status a few times to ensure it updates
        let attempts = 0;
        const checkStatus = async () => {
          await refresh();
          attempts++;
          if (attempts < 5) {
            setTimeout(checkStatus, 1000);
          }
        };
        setTimeout(checkStatus, 500);
        showSuccess('Model loaded successfully');
      } catch (error) {
        const apiError = error as ApiError;
        showError(apiError?.message || apiError?.detail || 'Failed to load model');
        throw error;
      } finally {
        setLoadingModelId(null);
      }
    },
    retry: false, // Disable automatic retries
  });

  const unloadModelMutation = useMutation({
    mutationFn: async () => {
      try {
        await api.post('/api/models/unload', {});
        await refresh();
        queryClient.invalidateQueries({ queryKey: queryKeys.models.list() });
        showSuccess('Model unloaded successfully');
      } catch (error) {
        const apiError = error as ApiError;
        showError(apiError?.message || apiError?.detail || 'Failed to unload model');
        throw error;
      }
    },
  });

  const handleModelSelect = (modelId: string) => {
    if (modelId !== currentModel) {
      loadModelMutation.mutate(modelId);
    }
  };

  const handleUnloadModel = () => {
    if (modelLoaded && currentModel) {
      unloadModelMutation.mutate();
    }
  };

  return (
    <header className="bg-primary text-primary-foreground border-b">
      <div className="container mx-auto px-4 py-4">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <h1 className="text-xl sm:text-2xl font-bold">Personal AI Assistant</h1>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onTogglePanel(activePanel === 'models' ? null : 'models')}
              className={cn(
                "text-white hover:bg-white/20",
                activePanel === 'models' && "bg-white/30"
              )}
              title="Model Browser"
            >
              <Package size={20} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onTogglePanel(activePanel === 'settings' ? null : 'settings')}
              className={cn(
                "text-white hover:bg-white/20",
                activePanel === 'settings' && "bg-white/30"
              )}
              title="Settings"
            >
              <Settings size={20} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onTogglePanel(activePanel === 'calendar' ? null : 'calendar')}
              className={cn(
                "text-white hover:bg-white/20",
                activePanel === 'calendar' && "bg-white/30"
              )}
              title="Calendar"
            >
              <CalendarIcon size={20} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onTogglePanel(activePanel === 'todo' ? null : 'todo')}
              className={cn(
                "text-white hover:bg-white/20",
                activePanel === 'todo' && "bg-white/30"
              )}
              title="Todos"
            >
              <CheckCircle2 size={20} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onTogglePanel(activePanel === 'debug' ? null : 'debug')}
              className={cn(
                "text-white hover:bg-white/20",
                activePanel === 'debug' && "bg-white/30"
              )}
              title="Debug Panel"
            >
              <Bug size={20} />
            </Button>
          </div>
        </div>
        {/* Model Status Bar */}
        <div className="mt-2 px-4 py-2 bg-white/10 rounded">
          <div className="flex items-center justify-between gap-4 text-sm">
            <span className="font-medium">Model:</span>
            {installedModels.length > 0 ? (
              <div className="flex items-center gap-2">
                <Select
                  value={currentModel || ''}
                  onValueChange={handleModelSelect}
                  disabled={!!loadingModelId}
                >
                  <SelectTrigger className="w-[300px] bg-white/10 border-white/20 text-white hover:bg-white/20 [&>span]:!text-white [&[data-placeholder]>span]:!text-white/90">
                    {loadingModelId ? (
                      <div className="flex items-center gap-2 text-white">
                        <Loader2 size={14} className="animate-spin text-white" />
                        <span className="text-white">Loading...</span>
                      </div>
                    ) : (
                      <SelectValue placeholder="Select a model" className="text-white placeholder:text-white/80">
                        {currentModel ? (
                          <div className="flex items-center gap-2">
                            <span className={cn("w-2 h-2 rounded", modelLoaded ? "bg-green-400 animate-pulse" : "bg-yellow-400")}></span>
                            <span className="truncate text-white">{currentModel.split(/[/\\]/).pop()}</span>
                          </div>
                        ) : (
                          <span className="text-yellow-200">No model loaded</span>
                        )}
                      </SelectValue>
                    )}
                  </SelectTrigger>
                  <SelectContent className="bg-background border-border">
                    {installedModels.map((model: ModelInfo) => (
                      <SelectItem 
                        key={model.model_id} 
                        value={model.model_id}
                        className="cursor-pointer text-foreground hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
                      >
                        <div className="flex items-center gap-2">
                          <span className={cn("w-2 h-2 rounded", model.model_id === currentModel && modelLoaded ? "bg-green-400" : "bg-gray-400")}></span>
                          <span className="font-medium">{model.name || model.model_id.split(/[/\\]/).pop()}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {modelLoaded && currentModel && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleUnloadModel}
                    disabled={unloadModelMutation.isPending}
                    className="text-white hover:bg-white/20"
                    title="Unload Model"
                  >
                    {unloadModelMutation.isPending ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <X size={16} />
                    )}
                  </Button>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-yellow-200">No models installed</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onTogglePanel(activePanel === 'models' ? null : 'models')}
                  className="text-white hover:bg-white/20"
                >
                  <Package size={14} className="mr-1" />
                  Browse Models
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}




