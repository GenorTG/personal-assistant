'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api } from '@/lib/api';
import { useSettings } from './SettingsContext';

export interface SamplerSettingsData {
  // Basic sampling
  temperature: number;
  top_p: number;
  top_k: number;
  min_p: number;
  
  // Repetition control
  repeat_penalty: number;
  presence_penalty: number;
  frequency_penalty: number;
  
  // Advanced sampling
  typical_p: number;
  tfs_z: number;
  
  // Mirostat
  mirostat_mode: number;
  mirostat_tau: number;
  mirostat_eta: number;
  
  // Output
  max_tokens: number;
}

export const DEFAULT_SETTINGS: SamplerSettingsData = {
  temperature: 0.7,
  top_p: 0.9,
  top_k: 40,
  min_p: 0.0,
  repeat_penalty: 1.1,
  presence_penalty: 0.0,
  frequency_penalty: 0.0,
  typical_p: 1.0,
  tfs_z: 1.0,
  mirostat_mode: 0,
  mirostat_tau: 5.0,
  mirostat_eta: 0.1,
  max_tokens: 512,
};

interface SamplerSettingsContextType {
  settings: SamplerSettingsData;
  updateSettings: (updates: Partial<SamplerSettingsData>) => void;
  resetToDefaults: () => void;
  loadFromBackend: () => Promise<void>;
  saveToBackend: () => Promise<void>;
  isLoading: boolean;
}

const SamplerSettingsContext = createContext<SamplerSettingsContextType | undefined>(undefined);

export function SamplerSettingsProvider({ children }: { children: ReactNode }) {
  const { settings: appSettings, refresh: refreshAppSettings } = useSettings();
  const [settings, setSettings] = useState<SamplerSettingsData>(DEFAULT_SETTINGS);
  const [isLoading, setIsLoading] = useState(true);

  // Load saved settings from SettingsContext
  useEffect(() => {
    if (appSettings?.settings) {
      const loaded: Partial<SamplerSettingsData> = {};
        
        // Map all sampler fields from backend
        const fields: (keyof SamplerSettingsData)[] = [
          'temperature', 'top_p', 'top_k', 'min_p',
          'repeat_penalty', 'presence_penalty', 'frequency_penalty',
          'typical_p', 'tfs_z',
          'mirostat_mode', 'mirostat_tau', 'mirostat_eta',
          'max_tokens'
        ];
        
      for (const field of fields) {
        if ((appSettings.settings as any)[field] !== undefined) {
          loaded[field] = (appSettings.settings as any)[field];
        }
      }
      
      setSettings(prev => ({ ...prev, ...loaded }));
      setIsLoading(false);
    } else if (!appSettings) {
      // Settings not loaded yet, keep loading state
      setIsLoading(true);
    } else {
      // Settings loaded but no sampler settings, use defaults
      setIsLoading(false);
    }
  }, [appSettings]);

  const updateSettings = (updates: Partial<SamplerSettingsData>) => {
    setSettings(prev => ({ ...prev, ...updates }));
  };

  const resetToDefaults = () => {
    setSettings(DEFAULT_SETTINGS);
  };

  const saveToBackend = async () => {
    try {
      await api.updateSettings(settings);
    } catch (error) {
      console.error('Error saving sampler settings:', error);
      throw error;
    }
  };

  return (
    <SamplerSettingsContext.Provider
      value={{
        settings,
        updateSettings,
        resetToDefaults,
        loadFromBackend: refreshAppSettings,
        saveToBackend,
        isLoading,
      }}
    >
      {children}
    </SamplerSettingsContext.Provider>
  );
}

export function useSamplerSettings() {
  const context = useContext(SamplerSettingsContext);
  if (context === undefined) {
    throw new Error('useSamplerSettings must be used within a SamplerSettingsProvider');
  }
  return context;
}

