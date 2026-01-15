import { useState } from 'react';

export interface ModelFilters {
  searchQuery: string;
  minParams: number;
  maxParams: number;
  quantFilter: string;
  viewMode: 'grid' | 'list';
  targetContext?: number;
  gpuLayers?: number;
  nBatch?: number;
  useFlashAttn?: boolean;
  offloadKqv?: boolean;
  supportsToolCalling?: 'all' | 'yes' | 'no';
  searchBySize?: boolean;
}

export function useModelFilters() {
  const [filters, setFilters] = useState<ModelFilters>({
    searchQuery: '',
    minParams: 0,
    maxParams: 70,
    quantFilter: 'all',
    viewMode: 'grid',
    targetContext: 4096,
    gpuLayers: -1,
    nBatch: 0,
    useFlashAttn: false,
    offloadKqv: true,
    supportsToolCalling: 'all',
    searchBySize: false,
  });

  const updateFilter = <K extends keyof ModelFilters>(
    key: K,
    value: ModelFilters[K]
  ) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const resetFilters = () => {
    setFilters({
      searchQuery: '',
      minParams: 0,
      maxParams: 70,
      quantFilter: 'all',
      viewMode: 'grid',
      targetContext: 4096,
      gpuLayers: -1,
      nBatch: 0,
      useFlashAttn: false,
      offloadKqv: true,
      supportsToolCalling: 'all',
      searchBySize: false,
    });
  };

  return {
    filters,
    updateFilter,
    resetFilters,
  };
}

