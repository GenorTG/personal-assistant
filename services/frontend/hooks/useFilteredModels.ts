import { useMemo } from 'react';

export function useFilteredSearchResults(
  searchResults: any[],
  minParams: number,
  maxParams: number,
  supportsToolCalling?: 'all' | 'yes' | 'no'
) {
  return useMemo(() => {
    return searchResults.filter((model) => {
      // Filter by parameter size
      const extractParamsFromModel = (modelData: any): number | null => {
        const name = modelData.model_id?.toLowerCase() || '';
        const tags = modelData.tags || [];

        for (const tag of tags) {
          const match = tag.match(/(\d+)b/i);
          if (match) return parseInt(match[1]);
        }

        const nameMatch = name.match(/(\d+)b/i);
        if (nameMatch) return parseInt(nameMatch[1]);

        return null;
      };

      const params = extractParamsFromModel(model);

      if (params !== null) {
        if (params < minParams || params > maxParams) return false;
      }

      // Filter by tool calling support
      if (supportsToolCalling && supportsToolCalling !== 'all') {
        // Handle both boolean true and truthy values, but be strict
        const modelSupportsTools = model.supports_tool_calling === true || model.supports_tool_calling === 1;
        if (supportsToolCalling === 'yes' && !modelSupportsTools) return false;
        if (supportsToolCalling === 'no' && modelSupportsTools) return false;
      }

      return true;
    });
  }, [searchResults, minParams, maxParams, supportsToolCalling]);
}

export function useFilteredInstalledModels(
  models: any[],
  searchQuery: string,
  modelMetadata: Record<string, any>
) {
  return useMemo(() => {
    return models
      .filter((model) => {
        if (!model) return false;
        const name = (model.name || '').toLowerCase();
        if (searchQuery && !name.includes(searchQuery.toLowerCase())) return false;
        return true;
      })
      .map((model) => {
        if (!model || !model.model_id) return null;
        const metadata = modelMetadata[model.model_id];
        if (metadata) {
          return {
            ...model,
            repo_id: metadata.repo_id,
            repo_name: metadata.repo_name,
            author: metadata.author,
            architecture: metadata.architecture,
            parameters: metadata.parameters,
            quantization: metadata.quantization,
            context_length: metadata.context_length,
            moe: metadata.moe,
            discovered: true,
          };
        }
        return model;
      });
  }, [models, searchQuery, modelMetadata]);
}


