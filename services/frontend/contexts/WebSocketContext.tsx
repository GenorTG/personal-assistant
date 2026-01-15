'use client';

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react';
import { getWebSocketClient, WebSocketClient, WSMessage } from '@/lib/websocket';

interface WebSocketContextValue {
  client: WebSocketClient;
  isConnected: boolean;
  connectionState: 'connecting' | 'connected' | 'disconnected' | 'error';
  subscribe: (action: string, handler: (message: WSMessage) => void) => () => void;
  request: (action: string, payload?: any) => Promise<any>;
}

const WebSocketContext = createContext<WebSocketContextValue | undefined>(undefined);

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => getWebSocketClient());
  const [isConnected, setIsConnected] = useState(false);
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected');

  useEffect(() => {
    // Connect on mount
    client.connect();

    // Subscribe to connection state changes
    const unsubscribe = client.onConnectionStateChange((state) => {
      setConnectionState(state);
      setIsConnected(state === 'connected');
    });

    // Initial state
    setConnectionState(client.getConnectionState());
    setIsConnected(client.isConnected());

    return () => {
      unsubscribe();
      // Don't disconnect on unmount - let it stay connected for other components
      // client.disconnect();
    };
  }, [client]);

  const subscribe = useCallback((action: string, handler: (message: WSMessage) => void) => {
    return client.subscribe(action, handler);
  }, [client]);

  const request = useCallback(async (action: string, payload?: any) => {
    return client.request(action, payload);
  }, [client]);

  return (
    <WebSocketContext.Provider
      value={{
        client,
        isConnected,
        connectionState,
        subscribe,
        request,
      }}
    >
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket(): WebSocketContextValue {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
}

/**
 * Hook to subscribe to WebSocket events.
 */
export function useWebSocketEvent<T = any>(
  action: string,
  handler: (payload: T) => void,
  deps: React.DependencyList = []
) {
  const { subscribe } = useWebSocket();

  useEffect(() => {
    const unsubscribe = subscribe(action, (message) => {
      handler(message.payload);
    });

    return unsubscribe;
  }, [action, subscribe, ...deps]);
}

/**
 * Hook to get real-time state from WebSocket.
 */
export function useRealtimeState<T>(
  action: string,
  initialValue: T,
  transform?: (payload: any) => T
): T {
  const [state, setState] = useState<T>(initialValue);
  const { subscribe, request, isConnected } = useWebSocket();

  // Subscribe to updates
  useEffect(() => {
    if (!isConnected) return;

    const unsubscribe = subscribe(action, (message) => {
      const newValue = transform ? transform(message.payload) : message.payload;
      setState(newValue);
    });

    // Also fetch initial value
    request(action).then((payload) => {
      const newValue = transform ? transform(payload) : payload;
      setState(newValue);
    }).catch((error) => {
      console.error(`Failed to fetch initial ${action}:`, error);
    });

    return unsubscribe;
  }, [action, subscribe, request, isConnected, transform]);

  return state;
}


