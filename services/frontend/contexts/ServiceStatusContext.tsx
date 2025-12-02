'use client';

import React, { createContext, useContext, useState, useEffect, useRef, useCallback, ReactNode } from 'react';
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

// Smart polling intervals
const STABLE_INTERVAL = 30000; // 30 seconds when all services are ready
const UNSTABLE_INTERVAL = 10000; // 10 seconds when services are unstable

export function ServiceStatusProvider({ children }: { children: ReactNode }) {
  const [statuses, setStatuses] = useState<AllServicesStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const stableCountRef = useRef(0); // Track consecutive stable checks

  const fetchStatuses = useCallback(async () => {
    try {
      const data = await api.getServicesStatus();
      setStatuses(data);
      setError(null);
      
      // Check if all services are ready
      const allReady = data && 
        data.stt?.status === 'ready' &&
        data.llm?.status === 'ready' &&
        (data.tts?.piper?.status === 'ready' || 
         data.tts?.chatterbox?.status === 'ready' || 
         data.tts?.kokoro?.status === 'ready');
      
      if (allReady) {
        stableCountRef.current += 1;
      } else {
        stableCountRef.current = 0;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch service statuses');
      console.error('Error fetching service statuses:', err);
      stableCountRef.current = 0;
    } finally {
      setLoading(false);
    }
  }, []);

  // Setup adaptive polling
  const setupPolling = useCallback(() => {
    // Clear existing interval
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    // Determine current interval based on stability
    // Consider stable after 3 consecutive successful checks with all services ready
    const isStable = stableCountRef.current >= 3;
    const currentInterval = isStable ? STABLE_INTERVAL : UNSTABLE_INTERVAL;

    // Set up new interval with adaptive timing
    intervalRef.current = setInterval(() => {
      fetchStatuses();
      // Re-evaluate interval after each check
      setupPolling();
    }, currentInterval);
  }, [fetchStatuses]);

  useEffect(() => {
    // Initial fetch
    fetchStatuses();
    setupPolling();

    // Handle page visibility (pause when tab is hidden)
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Tab is hidden - pause polling
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      } else {
        // Tab is visible - resume polling
        fetchStatuses();
        setupPolling();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [fetchStatuses, setupPolling]);

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
