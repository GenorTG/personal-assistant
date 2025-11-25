'use client';

import { useState, useEffect } from 'react';
import { X, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';

interface DebugPanelProps {
  onClose: () => void;
}

export default function DebugPanel({ onClose }: DebugPanelProps) {
  const [debugInfo, setDebugInfo] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDebugInfo();
    const interval = setInterval(loadDebugInfo, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadDebugInfo = async () => {
    try {
      const info = await api.getDebugInfo();
      setDebugInfo(info);
      setLoading(false);
    } catch (error) {
      console.error('Error loading debug info:', error);
      setLoading(false);
      setDebugInfo(null);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  return (
    <div className="w-96 bg-gray-900 text-gray-100 flex flex-col fixed right-0 z-50 shadow-2xl" style={{ height: 'calc(100vh - 73px)', top: '73px' }}>
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
    </div>
  );
}

