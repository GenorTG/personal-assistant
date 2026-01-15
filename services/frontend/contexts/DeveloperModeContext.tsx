'use client';

import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

export interface BackendLogEntry {
  timestamp: number;
  level: string;
  logger: string;
  message: string;
  exception?: string;
}

export interface ApiLogEntry {
  id: string;
  timestamp: number;
  method: string;
  url: string;
  requestHeaders?: Record<string, string>;
  requestBody?: any;
  responseStatus?: number;
  responseHeaders?: Record<string, string>;
  responseBody?: any;
  duration?: number;
  error?: string;
  backendLogs?: BackendLogEntry[];
}

interface DeveloperModeContextType {
  enabled: boolean;
  toggle: () => void;
  logs: ApiLogEntry[];
  addLog: (entry: Omit<ApiLogEntry, 'id' | 'timestamp'>) => void;
  clearLogs: () => void;
  maxLogs: number;
}

const DeveloperModeContext = createContext<DeveloperModeContextType | undefined>(undefined);

const MAX_LOGS = 1000;

export function DeveloperModeProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('developerMode') === 'true';
    }
    return false;
  });
  const [logs, setLogs] = useState<ApiLogEntry[]>([]);

  // Expose addLog globally for API client to use
  const addLog = useCallback((entry: Omit<ApiLogEntry, 'id' | 'timestamp'> & { id?: string }) => {
    // If entry has an id, try to update existing log; otherwise create new one
    if (entry.id) {
      const entryId = entry.id; // Capture for closure
      setLogs((prev) => {
        const existingIndex = prev.findIndex((log) => log.id === entryId);
        if (existingIndex >= 0) {
          // Update existing entry
          const updated = [...prev];
          updated[existingIndex] = {
            ...updated[existingIndex],
            ...entry,
            id: entryId,
            timestamp: updated[existingIndex].timestamp, // Keep original timestamp
          };
          return updated;
        } else {
          // Entry not found, create new one
          const logEntry: ApiLogEntry = {
            ...entry,
            id: entryId,
            timestamp: Date.now(),
          };
          return [logEntry, ...prev].slice(0, MAX_LOGS);
        }
      });
    } else {
      // Create new log entry
      const logEntry: ApiLogEntry = {
        ...entry,
        id: `${Date.now()}-${Math.random()}`,
        timestamp: Date.now(),
      };
      
      setLogs((prev) => {
        const newLogs = [logEntry, ...prev].slice(0, MAX_LOGS);
        return newLogs;
      });
    }
  }, []);

  // Expose addLog on window for API client (update when enabled or addLog changes)
  useEffect(() => {
    if (typeof window !== 'undefined') {
      (window as any).__developerModeAddLog = enabled ? addLog : null;
    }
  }, [enabled, addLog]);

  const toggle = useCallback(() => {
    const newValue = !enabled;
    setEnabled(newValue);
    if (typeof window !== 'undefined') {
      localStorage.setItem('developerMode', String(newValue));
    }
  }, [enabled]);

  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  return (
    <DeveloperModeContext.Provider
      value={{
        enabled,
        toggle,
        logs,
        addLog,
        clearLogs,
        maxLogs: MAX_LOGS,
      }}
    >
      {children}
    </DeveloperModeContext.Provider>
  );
}

export function useDeveloperMode() {
  const context = useContext(DeveloperModeContext);
  if (context === undefined) {
    throw new Error('useDeveloperMode must be used within a DeveloperModeProvider');
  }
  return context;
}

