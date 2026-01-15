'use client';

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

/**
 * Hook to check if the model is currently generating a response
 */
export function useGenerationState(): boolean {
  const queryClient = useQueryClient();
  const [isGenerating, setIsGenerating] = useState(false);

  useEffect(() => {
    // Check mutations on mount and subscribe to changes
    const checkMutations = () => {
      const mutations = queryClient.getMutationCache().getAll();
      const generating = mutations.some(mutation => {
        if (mutation.state.status !== 'pending') {
          return false;
        }
        
        // Check mutation key
        const mutationKey = mutation.options.mutationKey;
        if (Array.isArray(mutationKey) && mutationKey.length > 0) {
          const key = mutationKey[0];
          if (typeof key === 'string') {
            return key.includes('sendMessage') || key.includes('regenerate');
          }
        }
        
        // Check mutationFn - look for sendMessage or regenerate in the function
        const fn = mutation.options.mutationFn;
        if (fn) {
          const fnStr = fn.toString();
          return fnStr.includes('sendMessage') || fnStr.includes('regenerateLastResponse');
        }
        
        return false;
      });
      
      setIsGenerating(generating);
    };

    // Initial check
    checkMutations();

    // Subscribe to mutation cache changes
    const unsubscribe = queryClient.getMutationCache().subscribe(() => {
      checkMutations();
    });

    // Also poll periodically as backup
    const interval = setInterval(checkMutations, 500);

    return () => {
      unsubscribe();
      clearInterval(interval);
    };
  }, [queryClient]);

  return isGenerating;
}
