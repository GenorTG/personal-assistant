'use client';

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { api } from '@/lib/api';

export interface AppSettings {
  model_loaded?: boolean;
  current_model?: string | null;
  supports_tool_calling?: boolean;
  default_load_options?: {
    n_ctx?: number;
    n_gpu_layers?: number;
    use_flash_attention?: boolean;
    n_batch?: number;
    offload_kqv?: boolean;
  };
  settings?: {
    user_profile?: {
      name?: string;
    };
    character_card?: {
      name?: string;
    };
  };
  [key: string]: any; // For other settings we might not know about
}

interface SettingsContextType {
  settings: AppSettings | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  modelLoaded: boolean;
  currentModel: string | null;
  userName: string | null;
  botName: string | null;
  supportsToolCalling: boolean;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.getSettings() as AppSettings;
      setSettings(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load settings';
      setError(errorMessage);
      console.error('Error loading settings:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial load
    refresh();
    
    // Refresh settings every 30 seconds to keep in sync
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [refresh]);

  // Computed values
  const modelLoaded = settings?.model_loaded || false;
  const currentModel = settings?.current_model || null;
  const userName = settings?.settings?.user_profile?.name || null;
  const botName = settings?.settings?.character_card?.name || null;
  const supportsToolCalling = settings?.supports_tool_calling || false;

  return (
    <SettingsContext.Provider
      value={{
        settings,
        isLoading,
        error,
        refresh,
        modelLoaded,
        currentModel,
        userName,
        botName,
        supportsToolCalling,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}


