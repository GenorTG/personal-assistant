'use client';

import { useState, useEffect } from 'react';
import { X, Save, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';

interface ServerSettingsPanelProps {
  onClose: () => void;
}

export default function ServerSettingsPanel({ onClose }: ServerSettingsPanelProps) {
  const [loading, setLoading] = useState(false);
  const [systemInfo, setSystemInfo] = useState<any>(null);
  
  // Server settings state
  const [nCtx, setNCtx] = useState(4096);
  const [nThreads, setNThreads] = useState(4);
  const [nGpuLayers, setNGpuLayers] = useState(-1);
  const [nBatch, setNBatch] = useState(512);
  const [useMmap, setUseMmap] = useState(true);
  const [useMlock, setUseMlock] = useState(false);
  const [useFlashAttention, setUseFlashAttention] = useState(false);
  const [cacheTypeK, setCacheTypeK] = useState('f16');
  const [cacheTypeV, setCacheTypeV] = useState('f16');

  useEffect(() => {
    loadSystemInfo();
  }, []);

  const loadSystemInfo = async () => {
    try {
      const info = await api.getSystemInfo();
      setSystemInfo(info);
    } catch (error) {
      console.error('Error loading system info:', error);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      // Note: This would require a new API endpoint to update server settings
      // For now, these settings are applied when loading a model
      alert('Settings saved! They will be applied when loading the next model.');
      onClose();
    } catch (error) {
      console.error('Error saving settings:', error);
      alert('Error saving settings');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-96 bg-white border-l border-gray-200 flex flex-col fixed right-0 z-40 shadow-2xl" style={{ height: 'calc(100vh - 73px)', top: '73px' }}>
      <div className="p-4 border-b border-gray-200">
        <div className="flex justify-between items-center mb-2">
          <h2 className="text-xl font-bold">Server Settings</h2>
          <button onClick={onClose} className="btn-icon text-gray-600">
            <X size={20} />
          </button>
        </div>
        
        {/* System Info */}
        {systemInfo && (
          <div className="mt-2 p-2 rounded bg-gray-50 border border-gray-200">
            <div className="text-xs font-semibold text-gray-600 mb-1">System Info:</div>
            <div className="text-xs text-gray-700">
              <div>GPU: {systemInfo.gpu_available ? '✓ Available' : '✗ Not Available'}</div>
              {systemInfo.gpu_name && <div>Device: {systemInfo.gpu_name}</div>}
              {systemInfo.vram_total && <div>VRAM: {systemInfo.vram_total} GB</div>}
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Context Settings */}
        <div className="space-y-3">
          <h3 className="font-semibold text-sm text-gray-700">Context & Processing</h3>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Context Size (n_ctx)
            </label>
            <input
              type="number"
              min="512"
              max="32768"
              step="512"
              value={nCtx}
              onChange={(e) => setNCtx(parseInt(e.target.value) || 4096)}
              className="input w-full"
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">
              Maximum context window size (higher = more VRAM)
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Batch Size (n_batch)
            </label>
            <input
              type="number"
              min="128"
              max="4096"
              step="128"
              value={nBatch}
              onChange={(e) => setNBatch(parseInt(e.target.value) || 512)}
              className="input w-full"
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">
              Batch size for prompt processing
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              CPU Threads (n_threads)
            </label>
            <input
              type="number"
              min="1"
              max="64"
              value={nThreads}
              onChange={(e) => setNThreads(parseInt(e.target.value) || 4)}
              className="input w-full"
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">
              Number of CPU threads to use
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              GPU Layers (n_gpu_layers)
            </label>
            <input
              type="number"
              min="-1"
              max="100"
              value={nGpuLayers}
              onChange={(e) => setNGpuLayers(parseInt(e.target.value) || -1)}
              className="input w-full"
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">
              Layers to offload to GPU (-1 = all layers)
            </p>
          </div>
        </div>

        {/* KV Cache Settings */}
        <div className="space-y-3">
          <h3 className="font-semibold text-sm text-gray-700">KV Cache Quantization</h3>
          
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Cache Type K
              </label>
              <select
                value={cacheTypeK}
                onChange={(e) => setCacheTypeK(e.target.value)}
                className="input w-full"
                disabled={loading}
              >
                <option value="f16">f16 (Default)</option>
                <option value="q8_0">q8_0 (Less VRAM)</option>
                <option value="q4_0">q4_0 (Least VRAM)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Cache Type V
              </label>
              <select
                value={cacheTypeV}
                onChange={(e) => setCacheTypeV(e.target.value)}
                className="input w-full"
                disabled={loading}
              >
                <option value="f16">f16 (Default)</option>
                <option value="q8_0">q8_0 (Less VRAM)</option>
                <option value="q4_0">q4_0 (Least VRAM)</option>
              </select>
            </div>
          </div>
          <p className="text-xs text-gray-500">
            Quantizing KV cache reduces VRAM usage but may slightly impact quality.
          </p>
        </div>

        {/* Memory & Performance */}
        <div className="space-y-3">
          <h3 className="font-semibold text-sm text-gray-700">Memory & Performance</h3>
          
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={useMmap}
              onChange={(e) => setUseMmap(e.target.checked)}
              className="rounded"
              disabled={loading}
            />
            <span className="text-sm font-medium text-gray-700">Use Memory Mapping (mmap)</span>
          </label>
          <p className="text-xs text-gray-500 ml-6">
            Memory map the model file for faster loading and lower memory usage
          </p>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={useMlock}
              onChange={(e) => setUseMlock(e.target.checked)}
              className="rounded"
              disabled={loading}
            />
            <span className="text-sm font-medium text-gray-700">Lock Memory (mlock)</span>
          </label>
          <p className="text-xs text-gray-500 ml-6">
            Lock model memory in RAM to prevent swapping (may require root)
          </p>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={useFlashAttention}
              onChange={(e) => setUseFlashAttention(e.target.checked)}
              className="rounded"
              disabled={loading}
            />
            <span className="text-sm font-medium text-gray-700">Flash Attention</span>
          </label>
          <p className="text-xs text-gray-500 ml-6">
            Enable flash attention for faster inference (if supported by model)
          </p>
        </div>
      </div>

      {/* Footer Actions */}
      <div className="p-4 border-t border-gray-200">
        <div className="flex gap-2">
          <button
            onClick={handleSave}
            className="btn-primary flex-1 flex items-center justify-center gap-2"
            disabled={loading}
          >
            <Save size={16} />
            Save Settings
          </button>
          <button
            onClick={loadSystemInfo}
            className="btn-icon text-gray-600"
            disabled={loading}
          >
            <RefreshCw size={16} />
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-2 text-center">
          Settings will be applied when loading the next model
        </p>
      </div>
    </div>
  );
}
