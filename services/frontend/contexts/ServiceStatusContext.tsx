'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api } from '@/lib/api';

interface ServiceStatus {
  status: 'ready' | 'offline' | 'error';
  last_check?: string;
  response_time_ms?: number;
  type?: string;
  error?: string;
}

interface TTSStatuses {
  piper: ServiceStatus;
  chatterbox: ServiceStatus;
  kokoro: ServiceStatus;
}

interface AllServicesStatus {
  stt: ServiceStatus;
  tts: TTSStatuses;
  llm: ServiceStatus;
  last_poll?: string;
}

interface ServiceStatusContextValue {
  statuses: AllServicesStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const ServiceStatusContext = createContext<ServiceStatusContextValue | undefined>(undefined);

export function ServiceStatusProvider({ children }: { children: ReactNode }) {
  const [statuses, setStatuses] = useState<AllServicesStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatuses = async () => {
    try {
      const data = await api.getServicesStatus();
      setStatuses(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch service statuses');
      console.error('Error fetching service statuses:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchStatuses();

    // Poll every 5 seconds (industry standard for frontend)
    const interval = setInterval(fetchStatuses, 5000);

    return () => clearInterval(interval);
  }, []);

  return (
    <ServiceStatusContext.Provider 
      value={{ statuses, loading, error, refresh: fetchStatuses }}
    >
      {children}
    </ServiceStatusContext.Provider>
  );
}

export function useServiceStatus() {
  const context = useContext(ServiceStatusContext);
  if (context === undefined) {
    throw new Error('useServiceStatus must be used within a ServiceStatusProvider');
  }
  return context;
}
