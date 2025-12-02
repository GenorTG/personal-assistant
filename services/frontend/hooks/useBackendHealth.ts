'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';

interface UseBackendHealthOptions {
  /** Interval in milliseconds for health checks. Default: 30000 (30s) */
  interval?: number;
  /** Initial delay before first check. Default: 0 */
  initialDelay?: number;
  /** Whether to start checking immediately. Default: true */
  enabled?: boolean;
}

export function useBackendHealth(options: UseBackendHealthOptions = {}) {
  const {
    interval = 30000,
    initialDelay = 0,
    enabled = true,
  } = options;

  const [isReady, setIsReady] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isReadyRef = useRef(false);
  const stableCountRef = useRef(0); // Track consecutive successful checks
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Smart polling: 30s when stable, 5s when unstable
  const STABLE_INTERVAL = 30000; // 30 seconds when backend is ready and stable
  const UNSTABLE_INTERVAL = 5000; // 5 seconds when backend is failing or was ready but now failing
  const STABLE_THRESHOLD = 3; // Number of consecutive successful checks to consider stable

  const checkHealth = useCallback(async () => {
    if (!enabled) return;
    
    setIsChecking(true);
    try {
      const ready = await api.checkBackendHealth();
      const wasReady = isReadyRef.current;
      isReadyRef.current = ready;
      setIsReady(ready);
      
      if (ready) {
        setError(null);
        stableCountRef.current += 1;
      } else {
        stableCountRef.current = 0;
        if (wasReady) {
          // Backend was ready but now it's not
          setError('Backend is not responding');
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Backend health check failed';
      setError(errorMessage);
      isReadyRef.current = false;
      setIsReady(false);
      stableCountRef.current = 0;
    } finally {
      setIsChecking(false);
    }
  }, [enabled]);

  // Setup polling with adaptive interval
  const setupPolling = useCallback(() => {
    // Clear existing intervals
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!enabled) return;

    // Determine current interval based on stability
    const isStable = stableCountRef.current >= STABLE_THRESHOLD && isReadyRef.current;
    const currentInterval = isStable ? STABLE_INTERVAL : UNSTABLE_INTERVAL;

    // Set up new interval with adaptive timing
    intervalRef.current = setInterval(() => {
      checkHealth();
      // After each check, re-evaluate interval
      setupPolling();
    }, currentInterval);
  }, [enabled, checkHealth]);

  useEffect(() => {
    if (!enabled) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      return;
    }

    // Initial check immediately (or after delay)
    if (initialDelay > 0) {
      timeoutRef.current = setTimeout(() => {
        checkHealth();
        setupPolling();
      }, initialDelay);
    } else {
      checkHealth();
      setupPolling();
    }

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
        checkHealth();
        setupPolling();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [enabled, initialDelay, checkHealth, setupPolling]);

  return {
    isReady,
    isChecking,
    error,
    checkHealth, // Manual refresh capability
  };
}


