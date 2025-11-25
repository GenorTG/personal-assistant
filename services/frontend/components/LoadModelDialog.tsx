'use client';

import { useState, useEffect } from 'react';
import { X, Loader2, CheckCircle, XCircle, Zap, AlertTriangle } from 'lucide-react';
import { api } from '@/lib/api';

interface LoadModelDialogProps {
  modelId: string;
  modelName: string;
  isMoe?: boolean;
  moeInfo?: any;
  onClose: () => void;
  onSuccess: () => void;
}

export default function LoadModelDialog({ modelId, modelName, isMoe, moeInfo, onClose, onSuccess }: LoadModelDialogProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [progress, setProgress] = useState(0);

  // Model loading options
  const [nCtx, setNCtx] = useState(4096);
  const [nThreads, setNThreads] = useState(4);
  const [nGpuLayers, setNGpuLayers] = useState(-1);
  const [useMmap, setUseMmap] = useState(true);
  const [useMlock, setUseMlock] = useState(false);
  const [useFlashAttention, setUseFlashAttention] = useState(false);
  
  // Advanced options
  const [nBatch, setNBatch] = useState(512);
  const [offloadKqv, setOffloadKqv] = useState(true);
  const [ropeFreqBase, setRopeFreqBase] = useState<number | undefined>(undefined);
  const [ropeFreqScale, setRopeFreqScale] = useState<number | undefined>(undefined);
  
  const [nCpuMoe, setNCpuMoe] = useState(0);
  const [cacheTypeK, setCacheTypeK] = useState('f16');
  const [cacheTypeV, setCacheTypeV] = useState('f16');
  
  // VRAM estimation
  const [vramEstimate, setVramEstimate] = useState<any>(null);
  const [systemInfo, setSystemInfo] = useState<any>(null);
  const [loadingEstimate, setLoadingEstimate] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);

  // Load system info, global settings, and model config on mount
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
  }, [nCtx, nGpuLayers, cacheTypeK, cacheTypeV, offloadKqv]);

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
      // 1. Load global settings
      const settings = await api.getSettings() as any;
      const globalDefaults = settings?.settings?.default_load_options || {};
      
      // 2. Load per-model config
      const modelConfig = await api.getModelConfig(modelId) as any;
      
      // 3. Merge: Hardcoded < Global < Per-Model
      // We set state based on this priority
      
      const getValue = (key: string, defaultVal: any) => {
        if (modelConfig && modelConfig[key] !== undefined) return modelConfig[key];
        if (globalDefaults && globalDefaults[key] !== undefined) return globalDefaults[key];
        return defaultVal;
      };

      setNCtx(getValue('n_ctx', 4096));
      setNThreads(getValue('n_threads', 4));
      setNGpuLayers(getValue('n_gpu_layers', -1));
      setUseMmap(getValue('use_mmap', true));
      setUseMlock(getValue('use_mlock', false));
      setUseFlashAttention(getValue('use_flash_attention', false));
      setNBatch(getValue('n_batch', 512));
      setOffloadKqv(getValue('offload_kqv', true));
      setRopeFreqBase(getValue('rope_freq_base', undefined));
      setRopeFreqScale(getValue('rope_freq_scale', undefined));
      setNCpuMoe(getValue('n_cpu_moe', 0));
      setCacheTypeK(getValue('cache_type_k', 'f16'));
      setCacheTypeV(getValue('cache_type_v', 'f16'));
      
    } catch (error) {
      console.error('Error loading settings/config:', error);
    }
  };

  const saveModelConfig = async () => {
    setSavingConfig(true);
    try {
      const config = {
        n_ctx: nCtx,
        n_threads: nThreads,
        n_gpu_layers: nGpuLayers,
        use_mmap: useMmap,
        use_mlock: useMlock,
        use_flash_attention: useFlashAttention,
        n_batch: nBatch,
        offload_kqv: offloadKqv,
        rope_freq_base: ropeFreqBase,
        rope_freq_scale: ropeFreqScale,
        n_cpu_moe: isMoe ? nCpuMoe : undefined,
        cache_type_k: cacheTypeK,
        cache_type_v: cacheTypeV,
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

  const updateVramEstimate = async () => {
    setLoadingEstimate(true);
    try {
      const estimate = calculateVramEstimate();
      setVramEstimate(estimate);
    } catch (error) {
      console.error('Error calculating VRAM:', error);
    } finally {
      setLoadingEstimate(false);
    }
  };

  const calculateVramEstimate = () => {
    const baseVram = 4.0; // Placeholder
    const kvCacheMultiplier = cacheTypeK === 'f16' ? 1.0 : cacheTypeK === 'q8_0' ? 0.5 : 0.25;
    const contextVram = (nCtx / 4096) * 2.0 * kvCacheMultiplier;
    
    // If offloading KV, it counts towards VRAM. If not, it's RAM.
    const kvVram = offloadKqv ? contextVram : 0;
    
    const totalVram = baseVram + kvVram;
    
    return {
      total_vram_gb: totalVram,
      model_vram_gb: baseVram,
      kv_cache_vram_gb: contextVram,
      will_fit: systemInfo?.vram_total ? totalVram < systemInfo.vram_total : null
    };
  };

  const handleLoad = async () => {
    setLoading(true);
    setError(null);
    setSuccess(false);
    setProgress(0);

    try {
      const progressInterval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 200);

      const options = {
        n_ctx: nCtx,
        n_threads: nThreads,
        n_gpu_layers: nGpuLayers,
        use_mmap: useMmap,
        use_mlock: useMlock,
        use_flash_attention: useFlashAttention,
        n_batch: nBatch,
        offload_kqv: offloadKqv,
        rope_freq_base: ropeFreqBase,
        rope_freq_scale: ropeFreqScale,
        n_cpu_moe: isMoe ? nCpuMoe : undefined,
        cache_type_k: cacheTypeK !== 'f16' ? cacheTypeK : undefined,
        cache_type_v: cacheTypeV !== 'f16' ? cacheTypeV : undefined,
      };

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
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-2xl font-bold">Load Model: {modelName}</h2>
          <button onClick={onClose} className="btn-icon text-gray-600" disabled={loading}>
            <X size={24} />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {loading && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Loading model...</span>
                <span>{progress}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div
                  className="bg-primary-600 h-2.5 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {success && (
            <div className="flex items-center gap-2 text-green-600 bg-green-50 p-4 rounded-lg">
              <CheckCircle size={20} />
              <span>Model loaded successfully!</span>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 text-red-600 bg-red-50 p-4 rounded-lg">
              <XCircle size={20} />
              <span>{error}</span>
            </div>
          )}

          {!loading && !success && vramEstimate && systemInfo?.gpu_available && (
            <div className={`p-4 rounded-lg border-2 ${
              vramEstimate.will_fit === true 
                ? 'bg-green-50 border-green-300' 
                : vramEstimate.will_fit === false 
                ? 'bg-red-50 border-red-300' 
                : 'bg-gray-50 border-gray-300'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Zap size={18} className={vramEstimate.will_fit ? 'text-green-600' : 'text-red-600'} />
                  <span className="font-semibold text-sm">VRAM Estimate</span>
                </div>
                {vramEstimate.will_fit === true && (
                  <span className="text-xs bg-green-600 text-white px-2 py-1 rounded-full font-medium">Will Fit ✓</span>
                )}
                {vramEstimate.will_fit === false && (
                  <span className="text-xs bg-red-600 text-white px-2 py-1 rounded-full font-medium flex items-center gap-1">
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

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Context Size</label>
                <input type="number" value={nCtx} onChange={(e) => setNCtx(parseInt(e.target.value) || 4096)} className="input w-full" disabled={loading} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">GPU Layers</label>
                <input type="number" value={nGpuLayers} onChange={(e) => setNGpuLayers(parseInt(e.target.value) || -1)} className="input w-full" disabled={loading} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Chunk Size (n_batch)</label>
                <input type="number" value={nBatch} onChange={(e) => setNBatch(parseInt(e.target.value) || 512)} className="input w-full" disabled={loading} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">CPU Threads</label>
                <input type="number" value={nThreads} onChange={(e) => setNThreads(parseInt(e.target.value) || 4)} className="input w-full" disabled={loading} />
              </div>
            </div>

            <div className="p-3 bg-gray-50 rounded-md space-y-3">
              <h3 className="text-sm font-semibold text-gray-700">Advanced Settings</h3>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">RoPE Freq Base</label>
                  <input type="number" placeholder="Auto" value={ropeFreqBase || ''} onChange={(e) => setRopeFreqBase(e.target.value ? parseFloat(e.target.value) : undefined)} className="input w-full text-sm" disabled={loading} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">RoPE Freq Scale</label>
                  <input type="number" placeholder="Auto" value={ropeFreqScale || ''} onChange={(e) => setRopeFreqScale(e.target.value ? parseFloat(e.target.value) : undefined)} className="input w-full text-sm" disabled={loading} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">KV Cache K</label>
                  <select value={cacheTypeK} onChange={(e) => setCacheTypeK(e.target.value)} className="input w-full text-sm" disabled={loading}>
                    <option value="f16">f16 (Default)</option>
                    <option value="q8_0">q8_0</option>
                    <option value="q4_0">q4_0</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">KV Cache V</label>
                  <select value={cacheTypeV} onChange={(e) => setCacheTypeV(e.target.value)} className="input w-full text-sm" disabled={loading}>
                    <option value="f16">f16 (Default)</option>
                    <option value="q8_0">q8_0</option>
                    <option value="q4_0">q4_0</option>
                  </select>
                </div>
              </div>

              <div className="flex flex-wrap gap-4 pt-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={useFlashAttention} onChange={(e) => setUseFlashAttention(e.target.checked)} className="rounded" disabled={loading} />
                  <span className="text-sm text-gray-700">Flash Attention</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={offloadKqv} onChange={(e) => setOffloadKqv(e.target.checked)} className="rounded" disabled={loading} />
                  <span className="text-sm text-gray-700">Offload KV Cache</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={useMmap} onChange={(e) => setUseMmap(e.target.checked)} className="rounded" disabled={loading} />
                  <span className="text-sm text-gray-700">mmap</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={useMlock} onChange={(e) => setUseMlock(e.target.checked)} className="rounded" disabled={loading} />
                  <span className="text-sm text-gray-700">mlock</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-between items-center">
          <button onClick={saveModelConfig} className="text-primary-600 hover:text-primary-700 text-sm font-medium" disabled={loading || savingConfig}>
            {savingConfig ? 'Saving...' : 'Save as Default'}
          </button>
          <div className="flex gap-3">
            <button onClick={onClose} className="btn-secondary" disabled={loading}>Cancel</button>
            <button onClick={success ? onClose : handleLoad} className="btn-primary flex items-center gap-2" disabled={loading}>
              {loading ? <><Loader2 size={16} className="animate-spin" /> Loading...</> : success ? <><CheckCircle size={16} /> Close</> : 'Load Model'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

