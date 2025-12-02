'use client';

import { useState, useEffect } from 'react';
import { X, Loader2, CheckCircle, XCircle, Zap, AlertTriangle, Settings2 } from 'lucide-react';
import { api } from '@/lib/api';
import { useSettings } from '@/contexts/SettingsContext';

interface LoadModelDialogProps {
  modelId: string;
  modelName: string;
  isMoe?: boolean;
  moeInfo?: any;
  onClose: () => void;
  onSuccess: () => void;
}

/**
 * Model loading dialog with llama-cpp-python server parameters.
 * 
 * Parameters match the llama-cpp-python server config format.
 */
export default function LoadModelDialog({ modelId, modelName, isMoe, moeInfo, onClose, onSuccess }: LoadModelDialogProps) {
  const { settings: contextSettings } = useSettings();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [progress, setProgress] = useState(0);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Core model loading options
  const [nCtx, setNCtx] = useState(4096);
  const [nBatch, setNBatch] = useState(512);
  const [nThreads, setNThreads] = useState(4);
  const [nGpuLayers, setNGpuLayers] = useState(-1);
  
  // Memory options
  const [useMmap, setUseMmap] = useState(true);
  const [useMlock, setUseMlock] = useState(false);
  
  // Performance options
  const [flashAttn, setFlashAttn] = useState(false);
  
  // RoPE options (for extended context)
  const [ropeFreqBase, setRopeFreqBase] = useState<number | undefined>(undefined);
  const [ropeFreqScale, setRopeFreqScale] = useState<number | undefined>(undefined);
  
  // KV cache options
  const [cacheTypeK, setCacheTypeK] = useState('f16');
  const [cacheTypeV, setCacheTypeV] = useState('f16');
  
  // MoE options
  const [nCpuMoe, setNCpuMoe] = useState<number | undefined>(undefined);
  
  // System info
  const [vramEstimate, setVramEstimate] = useState<any>(null);
  const [systemInfo, setSystemInfo] = useState<any>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  // Load system info and saved config on mount
  useEffect(() => {
    const init = async () => {
      await loadSystemInfo();
      await loadSettingsAndConfig();
    };
    init();
  }, []);

  // Update VRAM estimate when settings change
  useEffect(() => {
    updateVramEstimate();
  }, [nCtx, nGpuLayers, cacheTypeK, cacheTypeV]);

  const loadSystemInfo = async () => {
    try {
      const info = await api.getSystemInfo() as any;
      setSystemInfo(info);
    } catch (error) {
      console.error('Error loading system info:', error);
    }
  };

  const loadSettingsAndConfig = async () => {
    try {
      // 1. Load global settings from context
      const globalDefaults = (contextSettings?.default_load_options || {}) as Record<string, any>;
      
      // 2. Load per-model config
      const modelConfig = await api.getModelConfig(modelId) as any;
      
      // 3. Merge: Hardcoded < Global < Per-Model
      const getValue = (key: string, defaultVal: any) => {
        if (modelConfig && modelConfig[key] !== undefined) return modelConfig[key];
        if (globalDefaults && globalDefaults[key] !== undefined) return globalDefaults[key];
        return defaultVal;
      };

      setNCtx(getValue('n_ctx', 4096));
      setNBatch(getValue('n_batch', 512));
      setNThreads(getValue('n_threads', 4));
      setNGpuLayers(getValue('n_gpu_layers', -1));
      setUseMmap(getValue('use_mmap', true));
      setUseMlock(getValue('use_mlock', false));
      setFlashAttn(getValue('flash_attn', false));
      setRopeFreqBase(getValue('rope_freq_base', undefined));
      setRopeFreqScale(getValue('rope_freq_scale', undefined));
      setCacheTypeK(getValue('cache_type_k', 'f16'));
      setCacheTypeV(getValue('cache_type_v', 'f16'));
      setNCpuMoe(getValue('n_cpu_moe', undefined));
      
    } catch (error) {
      console.error('Error loading settings/config:', error);
    }
  };

  const saveModelConfig = async () => {
    setSavingConfig(true);
    try {
      const config = {
        n_ctx: nCtx,
        n_batch: nBatch,
        n_threads: nThreads,
        n_gpu_layers: nGpuLayers,
        use_mmap: useMmap,
        use_mlock: useMlock,
        flash_attn: flashAttn,
        rope_freq_base: ropeFreqBase,
        rope_freq_scale: ropeFreqScale,
        cache_type_k: cacheTypeK,
        cache_type_v: cacheTypeV,
        n_cpu_moe: nCpuMoe,
      };
      await api.saveModelConfig(modelId, config);
      alert('Settings saved as default for this model!');
    } catch (error) {
      console.error('Error saving model config:', error);
      alert('Failed to save settings');
    } finally {
      setSavingConfig(false);
    }
  };

  const updateVramEstimate = () => {
    // Simple VRAM estimation
    const baseVram = 4.0; // Placeholder - should come from model metadata
    const kvCacheMultiplier = cacheTypeK === 'f16' ? 1.0 : cacheTypeK === 'q8_0' ? 0.5 : 0.25;
    const contextVram = (nCtx / 4096) * 2.0 * kvCacheMultiplier;
    const totalVram = baseVram + contextVram;
    
    setVramEstimate({
      total_vram_gb: totalVram,
      model_vram_gb: baseVram,
      kv_cache_vram_gb: contextVram,
      will_fit: systemInfo?.vram_total ? totalVram < systemInfo.vram_total : null
    });
  };

  const handleLoad = async () => {
    setLoading(true);
    setError(null);
    setSuccess(false);
    setProgress(0);

    try {
      // Progress animation
      const progressInterval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 200);

      // Build options with correct llama-cpp-python parameter names
      const options: Record<string, any> = {
        n_ctx: nCtx,
        n_batch: nBatch,
        n_threads: nThreads,
        n_gpu_layers: nGpuLayers,
        use_mmap: useMmap,
        use_mlock: useMlock,
        flash_attn: flashAttn,  // Correct parameter name
      };
      
      // Only include optional params if set
      if (ropeFreqBase !== undefined) {
        options.rope_freq_base = ropeFreqBase;
      }
      if (ropeFreqScale !== undefined) {
        options.rope_freq_scale = ropeFreqScale;
      }
      // KV cache types - only set if not default
      if (cacheTypeK !== 'f16') {
        options.cache_type_k = cacheTypeK;
      }
      if (cacheTypeV !== 'f16') {
        options.cache_type_v = cacheTypeV;
      }
      // MoE settings - only include if set
      if (nCpuMoe !== undefined && nCpuMoe > 0) {
        options.n_cpu_moe = nCpuMoe;
      }

      await api.loadModel(modelId, options);

      clearInterval(progressInterval);
      setProgress(100);
      setSuccess(true);
      
      setTimeout(() => {
        onSuccess();
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load model');
      setProgress(0);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-5 border-b border-gray-200 flex justify-between items-center bg-gray-50">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Load Model</h2>
            <p className="text-sm text-gray-500 mt-0.5 truncate max-w-md" title={modelName}>{modelName}</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-200 transition-colors" disabled={loading}>
            <X size={22} className="text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Progress/Status */}
          {loading && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Loading model...</span>
                <span className="font-medium">{progress}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-primary-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {success && (
            <div className="flex items-center gap-3 text-green-700 bg-green-50 border border-green-200 p-4 rounded-lg">
              <CheckCircle size={22} />
              <span className="font-medium">Model loaded successfully!</span>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-3 text-red-700 bg-red-50 border border-red-200 p-4 rounded-lg">
              <XCircle size={22} />
              <span>{error}</span>
            </div>
          )}

          {/* VRAM Estimate */}
          {!loading && !success && vramEstimate && systemInfo?.gpu_available && (
            <div className={`p-4 rounded-lg border-2 ${
              vramEstimate.will_fit === true 
                ? 'bg-green-50 border-green-300' 
                : vramEstimate.will_fit === false 
                ? 'bg-amber-50 border-amber-300' 
                : 'bg-gray-50 border-gray-200'
            }`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Zap size={18} className={vramEstimate.will_fit ? 'text-green-600' : 'text-amber-600'} />
                  <span className="font-semibold text-sm">VRAM Estimate</span>
                </div>
                {vramEstimate.will_fit === true && (
                  <span className="text-xs bg-green-600 text-white px-2 py-1 rounded-full font-medium">Should Fit ✓</span>
                )}
                {vramEstimate.will_fit === false && (
                  <span className="text-xs bg-amber-600 text-white px-2 py-1 rounded-full font-medium flex items-center gap-1">
                    <AlertTriangle size={12} /> May Not Fit
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><span className="text-gray-600">Model:</span> <span className="ml-1 font-medium">{vramEstimate.model_vram_gb.toFixed(2)} GB</span></div>
                <div><span className="text-gray-600">KV Cache:</span> <span className="ml-1 font-medium">{vramEstimate.kv_cache_vram_gb.toFixed(2)} GB</span></div>
                <div><span className="text-gray-600">Total Needed:</span> <span className="ml-1 font-medium">{vramEstimate.total_vram_gb.toFixed(2)} GB</span></div>
                <div><span className="text-gray-600">Available:</span> <span className="ml-1 font-medium">{systemInfo.vram_total?.toFixed(2) || 'N/A'} GB</span></div>
              </div>
            </div>
          )}

          {/* Main Settings */}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Context Size</label>
                <input 
                  type="number" 
                  value={nCtx} 
                  onChange={(e) => setNCtx(parseInt(e.target.value) || 4096)} 
                  className="input w-full" 
                  disabled={loading}
                  min={512}
                  max={131072}
                  step={512}
                />
                <p className="text-xs text-gray-500 mt-1">Memory for conversation history</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">GPU Layers</label>
                <input 
                  type="number" 
                  value={nGpuLayers} 
                  onChange={(e) => setNGpuLayers(parseInt(e.target.value))} 
                  className="input w-full" 
                  disabled={loading}
                  min={-1}
                />
                <p className="text-xs text-gray-500 mt-1">-1 = all, 0 = CPU only</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Batch Size</label>
                <input 
                  type="number" 
                  value={nBatch} 
                  onChange={(e) => setNBatch(parseInt(e.target.value) || 512)} 
                  className="input w-full" 
                  disabled={loading}
                  min={1}
                  max={4096}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">CPU Threads</label>
                <input 
                  type="number" 
                  value={nThreads} 
                  onChange={(e) => setNThreads(parseInt(e.target.value) || 4)} 
                  className="input w-full" 
                  disabled={loading}
                  min={1}
                  max={128}
                />
              </div>
            </div>

            {/* Quick toggles */}
            <div className="flex flex-wrap gap-x-6 gap-y-2 py-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input 
                  type="checkbox" 
                  checked={flashAttn} 
                  onChange={(e) => setFlashAttn(e.target.checked)} 
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500" 
                  disabled={loading} 
                />
                <span className="text-sm text-gray-700">Flash Attention</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input 
                  type="checkbox" 
                  checked={useMmap} 
                  onChange={(e) => setUseMmap(e.target.checked)} 
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500" 
                  disabled={loading} 
                />
                <span className="text-sm text-gray-700">Memory Map</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input 
                  type="checkbox" 
                  checked={useMlock} 
                  onChange={(e) => setUseMlock(e.target.checked)} 
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500" 
                  disabled={loading} 
                />
                <span className="text-sm text-gray-700">Lock Memory</span>
              </label>
            </div>

            {/* MoE Settings - Only show for MoE models */}
            {isMoe && moeInfo && (
              <div className="p-4 bg-blue-50 rounded-lg space-y-4 border border-blue-200">
                <div className="flex items-center gap-2 mb-2">
                  <Zap size={18} className="text-blue-600" />
                  <h3 className="text-sm font-semibold text-gray-700">Mixture of Experts (MoE) Settings</h3>
                </div>
                {moeInfo.num_experts && (
                  <p className="text-xs text-gray-600 mb-3">
                    This model has <strong>{moeInfo.num_experts}</strong> experts
                    {moeInfo.experts_per_token && ` (using ${moeInfo.experts_per_token} per token)`}
                  </p>
                )}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">
                    CPU Threads for MoE Experts
                  </label>
                  <input 
                    type="number" 
                    value={nCpuMoe || ''} 
                    onChange={(e) => setNCpuMoe(e.target.value ? parseInt(e.target.value) : undefined)} 
                    className="input w-full" 
                    disabled={loading}
                    min={1}
                    max={128}
                    placeholder="Auto (uses n_threads)"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Number of CPU threads dedicated to MoE expert computation. Leave empty to use the main thread count.
                  </p>
                </div>
              </div>
            )}

            {/* Advanced Settings Toggle */}
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Settings2 size={16} />
              {showAdvanced ? 'Hide' : 'Show'} Advanced Settings
            </button>

            {/* Advanced Settings */}
            {showAdvanced && (
              <div className="p-4 bg-gray-50 rounded-lg space-y-4 border border-gray-200">
                <h3 className="text-sm font-semibold text-gray-700">KV Cache Quantization</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Cache Type K</label>
                    <select 
                      value={cacheTypeK} 
                      onChange={(e) => setCacheTypeK(e.target.value)} 
                      className="input w-full text-sm" 
                      disabled={loading}
                    >
                      <option value="f16">f16 (Default)</option>
                      <option value="f32">f32</option>
                      <option value="q8_0">q8_0 (8-bit)</option>
                      <option value="q4_0">q4_0 (4-bit)</option>
                      <option value="q4_1">q4_1</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Cache Type V</label>
                    <select 
                      value={cacheTypeV} 
                      onChange={(e) => setCacheTypeV(e.target.value)} 
                      className="input w-full text-sm" 
                      disabled={loading}
                    >
                      <option value="f16">f16 (Default)</option>
                      <option value="f32">f32</option>
                      <option value="q8_0">q8_0 (8-bit)</option>
                      <option value="q4_0">q4_0 (4-bit)</option>
                      <option value="q4_1">q4_1</option>
                    </select>
                  </div>
                </div>
                <p className="text-xs text-gray-500">Lower precision = less VRAM but may reduce quality</p>
                
                <h3 className="text-sm font-semibold text-gray-700 pt-2">RoPE Context Extension</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Freq Base</label>
                    <input 
                      type="number" 
                      placeholder="Auto" 
                      value={ropeFreqBase || ''} 
                      onChange={(e) => setRopeFreqBase(e.target.value ? parseFloat(e.target.value) : undefined)} 
                      className="input w-full text-sm" 
                      disabled={loading} 
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Freq Scale</label>
                    <input 
                      type="number" 
                      placeholder="Auto" 
                      value={ropeFreqScale || ''} 
                      onChange={(e) => setRopeFreqScale(e.target.value ? parseFloat(e.target.value) : undefined)} 
                      className="input w-full text-sm" 
                      disabled={loading} 
                    />
                  </div>
                </div>
                <p className="text-xs text-gray-500">For extended context models. Leave blank for auto.</p>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-5 border-t border-gray-200 bg-gray-50 flex justify-between items-center">
          <button 
            onClick={saveModelConfig} 
            className="text-primary-600 hover:text-primary-700 text-sm font-medium transition-colors" 
            disabled={loading || savingConfig}
          >
            {savingConfig ? 'Saving...' : 'Save as Default'}
          </button>
          <div className="flex gap-3">
            <button 
              onClick={onClose} 
              className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors" 
              disabled={loading}
            >
              Cancel
            </button>
            <button 
              onClick={success ? onClose : handleLoad} 
              className="px-5 py-2 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors flex items-center gap-2 disabled:opacity-50" 
              disabled={loading}
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Loading...
                </>
              ) : success ? (
                <>
                  <CheckCircle size={16} />
                  Close
                </>
              ) : (
                'Load Model'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
