'use client';

import { useState, useMemo } from 'react';
import { useModels, useModelMetadata } from '@/hooks/queries/useModels';
import { useModelSearch } from '@/hooks/queries/useModelSearch';
import { useDiscoverModels, useDeleteModel } from '@/hooks/mutations/useModelMutations';
import { useModelFilters } from '@/hooks/useModelFilters';
import { useFilteredSearchResults, useFilteredInstalledModels } from '@/hooks/useFilteredModels';
import { useSettings } from '@/contexts/SettingsContext';
import { useToast } from '@/contexts/ToastContext';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queries/keys';
import { ModelBrowserHeader } from './ModelBrowserHeader';
import { ModelBrowserFilters } from './ModelBrowserFilters';
import { ModelSearchBar } from './ModelSearchBar';
import { ModelGrid } from './ModelGrid';
import LoadModelDialog from '@/components/LoadModelDialog';
import RepoDetailsModal from '@/components/RepoDetailsModal';
import { ScrollArea } from '@/components/ui/scroll-area';
import DownloadManager from '@/components/DownloadManager';
import ModelMetadataEditor from '@/components/ModelMetadataEditor';
import { Library } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface LoadDialogModel {
  id: string;
  name: string;
  isMoe?: boolean;
  moeInfo?: any;
}

interface ModelBrowserProps {
  onClose: () => void;
  onWidthChange?: (width: number) => void;
}

type Tab = 'discover' | 'installed';

export default function ModelBrowser({ onClose, onWidthChange }: ModelBrowserProps) {
  const [activeTab, setActiveTab] = useState<Tab>('discover');
  const [searchQuery, setSearchQuery] = useState('');
  const [loadDialogModel, setLoadDialogModel] = useState<LoadDialogModel | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [showDownloadManager, setShowDownloadManager] = useState(false);
  const [editingModel, setEditingModel] = useState<any | null>(null);
  const [showFilters] = useState(true);

  const { currentModel, refresh: refreshSettings } = useSettings();
  const { showSuccess, showError, showInfo } = useToast();
  const queryClient = useQueryClient();

  const { filters, updateFilter } = useModelFilters();
  const { data: models = [] } = useModels();
  const { data: metadataData } = useModelMetadata();
  const modelMetadata = useMemo(() => {
    if (!metadataData?.models) return {};
    const map: Record<string, any> = {};
    for (const model of metadataData.models) {
      if (model && model.model_id) {
        map[model.model_id] = model;
      }
    }
    return map;
  }, [metadataData]);

  // Construct search query based on filters
  const effectiveSearchQuery = useMemo(() => {
    if (filters.searchBySize && activeTab === 'discover') {
      // Build query from size range
      const sizeQueries: string[] = [];
      if (filters.minParams > 0 || filters.maxParams < 70) {
        // Generate size-based query
        for (let size = filters.minParams; size <= Math.min(filters.maxParams, 70); size++) {
          if (size > 0) {
            sizeQueries.push(`${size}b`);
          }
        }
        return sizeQueries.length > 0 ? `gguf ${sizeQueries.slice(0, 5).join(' OR ')}` : 'gguf';
      }
      return 'gguf';
    }
    return searchQuery || 'gguf';
  }, [searchQuery, filters.searchBySize, filters.minParams, filters.maxParams, activeTab]);

  const { data: searchResults = [], isLoading: searchLoading } = useModelSearch(
    effectiveSearchQuery,
    activeTab === 'discover' && (!!effectiveSearchQuery.trim() || filters.searchBySize)
  );

  const discoverModels = useDiscoverModels();
  const deleteModel = useDeleteModel();

  const saveGlobalSettings = useMutation({
    mutationFn: async () => {
      await api.updateSettings({
        default_load_options: {
          n_ctx: filters.targetContext || 4096,
          n_gpu_layers: filters.gpuLayers || -1,
          use_flash_attention: filters.useFlashAttn || false,
          n_batch: filters.nBatch !== undefined && filters.nBatch > 0 ? filters.nBatch : undefined,
          offload_kqv: filters.offloadKqv !== undefined ? filters.offloadKqv : true,
        },
      });
    },
    onSuccess: () => {
      showSuccess('Global loading settings saved!');
    },
    onError: () => {
      showError('Failed to save settings');
    },
  });

  const handleScanLocal = async () => {
    await discoverModels.mutateAsync(false);
  };

  const handleSearch = () => {
    // Search is handled by useModelSearch hook
  };

  const handleDownload = async (repoId: string, filename?: string) => {
    if (!filename) {
      showInfo('Please select a specific file to download');
      return;
    }

    try {
      await api.downloadModel(repoId, filename);
      setShowDownloadManager(true);
    } catch (error) {
      showError(`Error starting download: ${(error as Error).message}`);
    }
  };

  const handleDownloadComplete = async () => {
    // Automatically discover models when download completes
    try {
      await discoverModels.mutateAsync(false);
    } catch (error) {
      console.error('Error discovering models after download:', error);
    }
    // Also invalidate queries to refresh the list
    await queryClient.invalidateQueries({ queryKey: queryKeys.models.list() });
    await queryClient.invalidateQueries({ queryKey: queryKeys.models.metadata.all() });
  };

  const handleDeleteModel = async (modelId: string) => {
    await deleteModel.mutateAsync(modelId);
  };

  const filteredSearchResults = useFilteredSearchResults(
    searchResults,
    filters.minParams,
    filters.maxParams,
    filters.supportsToolCalling
  );

  const filteredInstalledModels = useFilteredInstalledModels(
    models,
    searchQuery,
    modelMetadata
  );

  const displayModels = activeTab === 'discover' ? filteredSearchResults : filteredInstalledModels;
  const isLoading = activeTab === 'discover' ? searchLoading : false;

  return (
    <>
    <div className="w-full flex flex-col sm:flex-row overflow-hidden bg-background overflow-x-hidden" style={{ height: '100%', maxHeight: '100%', minHeight: 0 }}>
            {/* Filters Sidebar */}
            {showFilters && (
              <div className="border-r border-border bg-muted/50 w-full sm:w-64 flex-shrink-0 flex flex-col overflow-hidden overflow-x-hidden" style={{ height: '100%', maxHeight: '100%' }}>
                <ScrollArea className="flex-1 min-h-0 h-full">
                  <ModelBrowserFilters
                minParams={filters.minParams}
                maxParams={filters.maxParams}
                quantFilter={filters.quantFilter}
                targetContext={filters.targetContext || 4096}
                gpuLayers={filters.gpuLayers || -1}
                nBatch={filters.nBatch ?? 0}
                useFlashAttn={filters.useFlashAttn || false}
                offloadKqv={filters.offloadKqv !== undefined ? filters.offloadKqv : true}
                onMinParamsChange={(v) => updateFilter('minParams', v)}
                onMaxParamsChange={(v) => updateFilter('maxParams', v)}
                onQuantFilterChange={(v) => updateFilter('quantFilter', v)}
                onTargetContextChange={(v) => updateFilter('targetContext', v)}
                onGpuLayersChange={(v) => updateFilter('gpuLayers', v)}
                onNBatchChange={(v) => updateFilter('nBatch', v)}
                onUseFlashAttnChange={(v) => updateFilter('useFlashAttn', v)}
                onOffloadKqvChange={(v) => updateFilter('offloadKqv', v)}
                supportsToolCalling={filters.supportsToolCalling || 'all'}
                searchBySize={filters.searchBySize || false}
                onSupportsToolCallingChange={(v) => updateFilter('supportsToolCalling', v)}
                onSearchBySizeChange={(v) => updateFilter('searchBySize', v)}
                onSaveSettings={() => saveGlobalSettings.mutate()}
                viewMode={filters.viewMode}
                onViewModeChange={(m) => updateFilter('viewMode', m)}
                activeTab={activeTab}
              />
                </ScrollArea>
              </div>
            )}

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden overflow-x-hidden" style={{ height: '100%', maxHeight: '100%' }}>
              <div className="flex-shrink-0">
                <ModelBrowserHeader
                  activeTab={activeTab}
                  onTabChange={setActiveTab}
                  onClose={onClose}
                  onScanLocal={handleScanLocal}
                  scanning={discoverModels.isPending}
                  onShowDownloadManager={() => setShowDownloadManager(true)}
                />

                <ModelSearchBar
                  searchQuery={searchQuery}
                  onSearchQueryChange={setSearchQuery}
                  onSearch={handleSearch}
                  loading={isLoading}
                  activeTab={activeTab}
                />
              </div>

              <ScrollArea className="flex-1 min-h-0 h-full overflow-x-hidden">
                <div className="px-4 sm:px-8 pb-8 min-w-0 overflow-x-hidden" style={{ maxWidth: '100%' }}>
                  <div className="w-full overflow-hidden overflow-x-hidden" style={{ maxWidth: '100%', width: '100%' }}>
                  {activeTab === 'discover' && (
                    <ModelGrid
                      models={displayModels}
                      viewMode={filters.viewMode}
                      currentModel={currentModel}
                      onViewDetails={(id) => setSelectedModelId(id)}
                      loading={isLoading}
                    />
                  )}
                  {activeTab === 'installed' && (
                    <>
                      <ModelGrid
                        models={displayModels}
                        viewMode={filters.viewMode}
                        currentModel={currentModel}
                        onLoad={(modelId) => {
                          const model = models.find((m) => m.model_id === modelId);
                          const modelName = (model?.name || modelId).toUpperCase();
                          const isMoeFromName =
                            modelName.includes('MOE') || modelName.includes('MIXTURE');
                          const isMoe = (model?.moe !== null && model?.moe !== undefined) || isMoeFromName;

                          setLoadDialogModel({
                            id: modelId,
                            name: model?.name || modelId,
                            isMoe: isMoe,
                            moeInfo: model?.moe,
                          });
                        }}
                        onEditMetadata={(m) => setEditingModel(m)}
                        onDelete={handleDeleteModel}
                      />
                      {displayModels.length === 0 && !isLoading && (
                        <div className="col-span-full text-center py-20 text-muted-foreground">
                          <Library size={48} className="mx-auto mb-4 opacity-20" />
                          <p className="text-lg">No installed models found.</p>
                          <Button
                            onClick={() => setActiveTab('discover')}
                            variant="link"
                            className="mt-2"
                          >
                            Go to Discover to download models
                          </Button>
                        </div>
                      )}
                    </>
                  )}
                  </div>
                </div>
              </ScrollArea>
            </div>
          </div>

      {/* Load Model Dialog */}
      {loadDialogModel && (
        <LoadModelDialog
          modelId={loadDialogModel?.id || ''}
          modelName={loadDialogModel?.name || ''}
          onClose={() => setLoadDialogModel(null)}
          onSuccess={() => {
            setLoadDialogModel(null);
            refreshSettings();
            queryClient.invalidateQueries({ queryKey: queryKeys.models.list() });
          }}
        />
      )}

      {/* Repo Details Modal */}
      {selectedModelId && (
        <RepoDetailsModal
          modelId={selectedModelId || ''}
          onClose={() => setSelectedModelId(null)}
          onDownload={(filename) => {
            if (selectedModelId) {
              handleDownload(selectedModelId, filename);
              setSelectedModelId(null);
            }
          }}
        />
      )}

      {/* Download Manager */}
      {showDownloadManager && (
        <DownloadManager
          isOpen={showDownloadManager}
          onClose={() => setShowDownloadManager(false)}
          onDownloadComplete={handleDownloadComplete}
        />
      )}

      {/* Metadata Editor */}
      {editingModel && (
        <ModelMetadataEditor
          model={editingModel}
          onClose={() => setEditingModel(null)}
          onSave={() => {
            queryClient.invalidateQueries({ queryKey: queryKeys.models.list() });
            queryClient.invalidateQueries({ queryKey: queryKeys.models.metadata.all() });
          }}
        />
      )}
    </>
  );
}


