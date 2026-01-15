'use client';

import { Search } from 'lucide-react';
import ModelSearchResultCard from '@/components/ModelSearchResultCard';
import { cn } from '@/lib/utils';

interface ModelGridProps {
  models: any[];
  viewMode: 'grid' | 'list';
  currentModel?: string | null;
  onLoad?: (modelId: string) => void;
  onViewDetails?: (modelId: string) => void;
  onEditMetadata?: (model: any) => void;
  onDelete?: (modelId: string) => Promise<void>;
  loading?: boolean;
}

export function ModelGrid({
  models,
  viewMode,
  currentModel,
  onLoad,
  onViewDetails,
  onEditMetadata,
  onDelete,
  loading,
}: ModelGridProps) {
  if (loading) {
    return (
      <div className="col-span-full flex justify-center py-20">
        <div className="animate-spin rounded h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (models.length === 0) {
    return (
      <div className="col-span-full text-center py-20 text-muted-foreground">
        <Search size={48} className="mx-auto mb-4 opacity-20" />
        <p className="text-lg">No models found. Try a different search term.</p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'w-full max-w-full overflow-hidden overflow-x-hidden',
        // On smaller screens (< xl), always use list layout (vertical stacking)
        'flex flex-col space-y-3',
        // On extra wide screens (xl+), use grid if viewMode is grid
        viewMode === 'grid' && 'xl:grid xl:grid-cols-2 2xl:grid-cols-3 xl:gap-4 xl:space-y-0'
      )}
      style={{ width: '100%', maxWidth: '100%', minWidth: 0 }}
    >
      {models.map((model) => {
        if (!model || !model.model_id) return null;
        
        const isCurrentModel = Boolean(
          currentModel &&
            (currentModel.includes(model.model_id) ||
              model.model_id === currentModel.split(/[/\\]/).pop())
        );

        return (
          <div key={model.model_id} className="min-w-0 max-w-full overflow-x-hidden" style={{ width: '100%', maxWidth: '100%', minWidth: 0 }}>
            <ModelSearchResultCard
              model={model}
              isCurrent={isCurrentModel}
              onLoad={onLoad}
              onViewDetails={onViewDetails}
              onEditMetadata={onEditMetadata}
              onDelete={onDelete}
            />
          </div>
        );
      })}
    </div>
  );
}


