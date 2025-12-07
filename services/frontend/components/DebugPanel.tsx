'use client';

import { useState, useEffect, useCallback } from 'react';
import { X, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import ResizableSidebar from './ResizableSidebar';
import { formatBytes } from '@/lib/utils';

interface DebugPanelProps {
  onClose: () => void;
  onWidthChange?: (width: number) => void;
}

export default function DebugPanel({ onClose, onWidthChange }: DebugPanelProps) {
  const [debugInfo, setDebugInfo] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadDebugInfo = useCallback(async () => {
    try {
      const info = await api.getDebugInfo();
      setDebugInfo(info);
      setLoading(false);
    } catch (error) {
      console.error('Error loading debug info:', error);
      setLoading(false);
      setDebugInfo(null);
    }
  }, []);

  useEffect(() => {
    // Initial load - necessary to fetch data on mount
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadDebugInfo();
    // Set up polling interval
    const interval = setInterval(() => {
      loadDebugInfo();
    }, 5000);
    return () => clearInterval(interval);
  }, [loadDebugInfo]);


  return (
    <ResizableSidebar
      initialWidth={384}
      minWidth={200}
      maxWidth={800}
      side="right"
      className="bg-gray-900 text-gray-100 flex flex-col fixed right-0 z-50 shadow-2xl"
      style={{ height: 'calc(100vh - 73px)', top: '73px' }}
      onWidthChange={onWidthChange}
    >
      <div className="p-4 border-b border-gray-700 flex justify-between items-center">
        <h2 className="text-xl font-bold">Debug Panel</h2>
        <div className="flex gap-2">
          <button onClick={loadDebugInfo} className="btn-icon text-gray-300">
            <RefreshCw size={20} />
          </button>
          <button onClick={onClose} className="btn-icon text-gray-300">
            <X size={20} />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
        {loading ? (
          <p>Loading...</p>
        ) : debugInfo ? (
          <>
            <div>
              <h3 className="font-semibold text-green-400 mb-2">Services</h3>
              <div className="bg-gray-800 p-3 rounded font-mono text-xs">
                {Object.entries(debugInfo.services || {}).map(([key, value]) => (
                  <div key={key}>
                    {key}:{' '}
                    <span className={value ? 'text-green-400' : 'text-red-400'}>
                      {value ? '✓' : '✗'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="font-semibold text-green-400 mb-2">Model</h3>
              <div className="bg-gray-800 p-3 rounded font-mono text-xs">
                <div>Loaded: {debugInfo.model?.loaded ? 'Yes' : 'No'}</div>
                {debugInfo.model?.current_model && (
                  <div>Model: {debugInfo.model.current_model}</div>
                )}
                {debugInfo.model?.gpu_layers !== undefined && (
                  <div>GPU Layers: {debugInfo.model.gpu_layers}</div>
                )}
              </div>
            </div>
            <div>
              <h3 className="font-semibold text-green-400 mb-2">Memory</h3>
              <div className="bg-gray-800 p-3 rounded font-mono text-xs">
                <div>Conversations: {debugInfo.memory?.conversation_count || 0}</div>
                <div>Messages: {debugInfo.memory?.message_count || 0}</div>
                {debugInfo.memory?.db_size_bytes && (
                  <div>DB Size: {formatBytes(debugInfo.memory.db_size_bytes)}</div>
                )}
              </div>
            </div>
            <div>
              <h3 className="font-semibold text-green-400 mb-2">Conversations</h3>
              <div className="bg-gray-800 p-3 rounded font-mono text-xs">
                <div>Active: {debugInfo.conversations?.active_count || 0}</div>
              </div>
            </div>
          </>
        ) : (
          <p>No debug info available</p>
        )}
      </div>
    </ResizableSidebar>
  );
}

