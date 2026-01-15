'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { api } from '@/lib/api';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';

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

/**
 * Service Architecture Notes:
 * - STT: Integrated into gateway (native faster-whisper) - always available
 * - Piper TTS: Integrated into gateway (native piper-tts) - always available
 * - Kokoro TTS: Integrated into gateway (native kokoro-onnx) - always available
 * - Chatterbox TTS: Optional HTTP service (port 4123) - separate process
 * - LLM: Integrated into gateway (native llama-cpp-python) - always available
 * - Memory: Integrated into gateway (native ChromaDB) - always available
 * - Tools: Integrated into gateway (native ToolManager) - always available
 */

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

  const fetchStatuses = useCallback(async () => {
    try {
      // API client will automatically use WebSocket if available, fallback to HTTP
      const data = await api.getServicesStatus();
      setStatuses(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch service statuses');
      console.error('Error fetching service statuses:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Subscribe to WebSocket events for real-time updates
  useWebSocketEvent('service_status_changed', (payload) => {
    if (payload) {
      setStatuses(payload);
      setError(null);
      setLoading(false);
    }
  });

  // Event-driven: Only fetch on mount, then rely on WebSocket events
  useEffect(() => {
    // Initial fetch only
    fetchStatuses();
  }, [fetchStatuses]);

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
