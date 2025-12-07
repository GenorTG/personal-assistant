"use client";

import { useState, useEffect } from "react";
import {
  X,
  Loader2,
  CheckCircle,
  XCircle,
  Zap,
  AlertTriangle,
  Settings2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useSettings } from "@/contexts/SettingsContext";
import { useToast } from "@/contexts/ToastContext";

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
export default function LoadModelDialog({
  modelId,
  modelName,
  isMoe,
  moeInfo,
  onClose,
  onSuccess,
}: LoadModelDialogProps) {
  const { settings: contextSettings } = useSettings();
  const { showSuccess, showError } = useToast();
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
  const [ropeFreqBase, setRopeFreqBase] = useState<number | undefined>(
    undefined
  );
  const [ropeFreqScale, setRopeFreqScale] = useState<number | undefined>(
    undefined
  );

  // KV cache options
  const [cacheTypeK, setCacheTypeK] = useState("f16");
  const [cacheTypeV, setCacheTypeV] = useState("f16");

  // MoE options
  // n_cpu_moe removed - not a valid parameter for llama-cpp-python server
  const [nExpertsToUse, setNExpertsToUse] = useState<number | undefined>(
    undefined
  );

  // System info
  const [vramEstimate, setVramEstimate] = useState<any>(null);
  const [systemInfo, setSystemInfo] = useState<any>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  // Auto-detect MoE from model name if not explicitly set
  const [detectedIsMoe, setDetectedIsMoe] = useState(isMoe);

  useEffect(() => {
    // Check model name for MoE indicators
    const modelNameUpper = modelName.toUpperCase();
    if (
      !isMoe &&
      (modelNameUpper.includes("MOE") || modelNameUpper.includes("MIXTURE"))
    ) {
      setDetectedIsMoe(true);
    } else {
      setDetectedIsMoe(isMoe);
    }
  }, [modelName, isMoe]);

  // Load system info and saved config on mount
  useEffect(() => {
    let mounted = true;

    const init = async () => {
      await loadSystemInfo();

      // Use provided moeInfo first (from cached metadata), only fetch if missing
      if (moeInfo && moeInfo.is_moe && moeInfo.num_experts) {
        if (mounted) {
          console.log(
            `[LoadModelDialog] Using provided MoE info (cached):`,
            moeInfo
          );
          setFetchedMoeInfo(moeInfo);
          if (moeInfo.experts_per_token && !nExpertsToUse) {
            setNExpertsToUse(moeInfo.experts_per_token);
          }
        }
        // Don't fetch - we already have it!
      } else if (
        detectedIsMoe &&
        (!moeInfo || !moeInfo.is_moe || !moeInfo.num_experts)
      ) {
        // Only fetch if we don't have valid cached MoE info AND model is detected as MoE
        if (mounted) {
          console.log(`[LoadModelDialog] No cached MoE info, fetching...`);
          await fetchMoEInfo();
        }
      }

      if (mounted) {
        await loadSettingsAndConfig();
      }
    };

    init();

    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId]); // Only depend on modelId - moeInfo and detectedIsMoe are derived from props

  const updateVramEstimate = () => {
    // Simple VRAM estimation
    const baseVram = 4.0; // Placeholder - should come from model metadata
    const kvCacheMultiplier =
      cacheTypeK === "f16" ? 1.0 : cacheTypeK === "q8_0" ? 0.5 : 0.25;
    const contextVram = (nCtx / 4096) * 2.0 * kvCacheMultiplier;
    const totalVram = baseVram + contextVram;

    setVramEstimate({
      total_vram_gb: totalVram,
      model_vram_gb: baseVram,
      kv_cache_vram_gb: contextVram,
      will_fit: systemInfo?.vram_total
        ? totalVram < systemInfo.vram_total
        : null,
    });
  };

  // Update VRAM estimate when settings change
  useEffect(() => {
    updateVramEstimate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nCtx, nGpuLayers, cacheTypeK, cacheTypeV, updateVramEstimate]);

  const loadSystemInfo = async () => {
    try {
      const info = (await api.getSystemInfo()) as any;
      setSystemInfo(info);

      // Clamp nThreads to available CPU threads if it exceeds
      const maxThreads = info?.cpu_threads_available || info?.cpu_count || 4;
      if (nThreads > maxThreads) {
        setNThreads(maxThreads);
      }
    } catch (error) {
      console.error("Error loading system info:", error);
    }
  };

  const [fetchedMoeInfo, setFetchedMoeInfo] = useState<any>(null);
  const [fetchingMoeInfo, setFetchingMoeInfo] = useState(false);

  const fetchMoEInfo = async () => {
    setFetchingMoeInfo(true);
    try {
      console.log(
        `[LoadModelDialog] Fetching MoE info for modelId: ${modelId}`
      );
      const modelInfo = (await api.getModelInfo(modelId)) as any;
      console.log(`[LoadModelDialog] Received model info:`, modelInfo);
      if (modelInfo?.moe) {
        console.log(`[LoadModelDialog] MoE info:`, modelInfo.moe);
        setFetchedMoeInfo(modelInfo.moe);
        // Also update nExpertsToUse if we have experts_per_token
        if (modelInfo.moe.experts_per_token && !nExpertsToUse) {
          setNExpertsToUse(modelInfo.moe.experts_per_token);
        }
        return modelInfo.moe;
      } else {
        console.log(`[LoadModelDialog] No MoE info found in model info`);
      }
    } catch (error) {
      console.error("Error fetching MoE info:", error);
    } finally {
      setFetchingMoeInfo(false);
    }
    return null;
  };

  const loadSettingsAndConfig = async () => {
    try {
      // 1. Load global settings from context
      const globalDefaults = (contextSettings?.default_load_options ||
        {}) as Record<string, any>;

      // 2. Load per-model config
      const modelConfig = (await api.getModelConfig(modelId)) as any;

      // 3. Merge: Hardcoded < Global < Per-Model
      const getValue = (key: string, defaultVal: any) => {
        if (modelConfig && modelConfig[key] !== undefined)
          return modelConfig[key];
        if (globalDefaults && globalDefaults[key] !== undefined)
          return globalDefaults[key];
        return defaultVal;
      };

      setNCtx(getValue("n_ctx", 4096));
      setNBatch(getValue("n_batch", 512));
      setNThreads(getValue("n_threads", 4));
      setNGpuLayers(getValue("n_gpu_layers", -1));

      // MoE settings
      if (detectedIsMoe && (moeInfo || fetchedMoeInfo)) {
        const savedExperts = getValue("n_experts_to_use", undefined);
        const moe = moeInfo || fetchedMoeInfo;
        setNExpertsToUse(savedExperts || moe?.experts_per_token || 2);
      }
      setUseMmap(getValue("use_mmap", true));
      setUseMlock(getValue("use_mlock", false));
      setFlashAttn(getValue("flash_attn", false));
      setRopeFreqBase(getValue("rope_freq_base", undefined));
      setRopeFreqScale(getValue("rope_freq_scale", undefined));
      setCacheTypeK(getValue("cache_type_k", "f16"));
      setCacheTypeV(getValue("cache_type_v", "f16"));
      // n_cpu_moe removed - not a valid parameter
    } catch (error) {
      console.error("Error loading settings/config:", error);
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
        // n_cpu_moe removed - not a valid parameter for llama-cpp-python server
        n_experts_to_use: nExpertsToUse,
      };
      await api.saveModelConfig(modelId, config);
      showSuccess("Settings saved as default for this model!");
    } catch (error) {
      console.error("Error saving model config:", error);
      showError("Failed to save settings");
    } finally {
      setSavingConfig(false);
    }
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
        flash_attn: flashAttn, // Correct parameter name
      };

      // Only include optional params if set
      if (ropeFreqBase !== undefined) {
        options.rope_freq_base = ropeFreqBase;
      }
      if (ropeFreqScale !== undefined) {
        options.rope_freq_scale = ropeFreqScale;
      }
      // KV cache types - only set if not default
      if (cacheTypeK !== "f16") {
        options.cache_type_k = cacheTypeK;
      }
      if (cacheTypeV !== "f16") {
        options.cache_type_v = cacheTypeV;
      }
      // MoE settings - only include if set
      // n_cpu_moe is not a valid parameter for llama-cpp-python server
      // The correct parameter is n_experts_to_use (number of experts per token)
      if (nExpertsToUse !== undefined && nExpertsToUse > 0) {
        options.n_experts_to_use = nExpertsToUse;
      }

      await api.loadModel(modelId, options);

      clearInterval(progressInterval);
      setProgress(100);
      setSuccess(true);

      setTimeout(() => {
        onSuccess();
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load model");
      setProgress(0);
    } finally {
      setLoading(false);
    }
  };

  // Track mousedown to prevent closing when dragging text selection outside modal
  const [mouseDownInside, setMouseDownInside] = useState(false);

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4"
      onMouseDown={(e) => {
        // Track if mousedown was on backdrop (outside modal)
        if (e.target === e.currentTarget) {
          setMouseDownInside(false);
        }
      }}
      onMouseUp={(e) => {
        // Only close if both mousedown and mouseup were on backdrop
        if (e.target === e.currentTarget && !mouseDownInside) {
          onClose();
        }
        setMouseDownInside(false);
      }}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col relative z-[61]"
        onMouseDown={(e) => {
          // Track that mousedown was inside modal
          setMouseDownInside(true);
          e.stopPropagation();
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-gray-200 flex justify-between items-center bg-gray-50">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Load Model</h2>
            <p
              className="text-sm text-gray-500 mt-0.5 truncate max-w-md"
              title={modelName}
            >
              {modelName}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-200 transition-colors"
            disabled={loading}
          >
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
          {!loading &&
            !success &&
            vramEstimate &&
            systemInfo?.gpu_available && (
              <div
                className={`p-4 rounded-lg border-2 ${
                  vramEstimate.will_fit === true
                    ? "bg-green-50 border-green-300"
                    : vramEstimate.will_fit === false
                    ? "bg-amber-50 border-amber-300"
                    : "bg-gray-50 border-gray-200"
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Zap
                      size={18}
                      className={
                        vramEstimate.will_fit
                          ? "text-green-600"
                          : "text-amber-600"
                      }
                    />
                    <span className="font-semibold text-sm">VRAM Estimate</span>
                  </div>
                  {vramEstimate.will_fit === true && (
                    <span className="text-xs bg-green-600 text-white px-2 py-1 rounded-full font-medium">
                      Should Fit ✓
                    </span>
                  )}
                  {vramEstimate.will_fit === false && (
                    <span className="text-xs bg-amber-600 text-white px-2 py-1 rounded-full font-medium flex items-center gap-1">
                      <AlertTriangle size={12} /> May Not Fit
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-gray-600">Model:</span>{" "}
                    <span className="ml-1 font-medium">
                      {vramEstimate.model_vram_gb.toFixed(2)} GB
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-600">KV Cache:</span>{" "}
                    <span className="ml-1 font-medium">
                      {vramEstimate.kv_cache_vram_gb.toFixed(2)} GB
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-600">Total Needed:</span>{" "}
                    <span className="ml-1 font-medium">
                      {vramEstimate.total_vram_gb.toFixed(2)} GB
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-600">Available:</span>{" "}
                    <span className="ml-1 font-medium">
                      {systemInfo.vram_total?.toFixed(2) || "N/A"} GB
                    </span>
                  </div>
                </div>
              </div>
            )}

          {/* Main Settings */}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Context Size
                </label>
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
                <p className="text-xs text-gray-500 mt-1">
                  Memory for conversation history
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  GPU Layers
                </label>
                <input
                  type="number"
                  value={nGpuLayers}
                  onChange={(e) => setNGpuLayers(parseInt(e.target.value))}
                  className="input w-full"
                  disabled={loading}
                  min={-1}
                />
                <p className="text-xs text-gray-500 mt-1">
                  -1 = all, 0 = CPU only
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Batch Size
                </label>
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
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  CPU Threads
                  {systemInfo?.cpu_threads_available && (
                    <span className="text-xs text-gray-500 ml-2">
                      (max: {systemInfo.cpu_threads_available})
                    </span>
                  )}
                </label>
                <input
                  type="number"
                  value={nThreads}
                  onChange={(e) => {
                    const value = parseInt(e.target.value) || 1;
                    const maxThreads =
                      systemInfo?.cpu_threads_available ||
                      systemInfo?.cpu_count ||
                      128;
                    setNThreads(Math.min(value, maxThreads));
                  }}
                  className="input w-full"
                  disabled={loading}
                  min={1}
                  max={
                    systemInfo?.cpu_threads_available ||
                    systemInfo?.cpu_count ||
                    128
                  }
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

            {/* MoE Settings - Show for detected MoE models */}
            {detectedIsMoe && (
              <div className="p-4 bg-blue-50 rounded-lg space-y-4 border border-blue-200">
                <div className="flex items-center gap-2 mb-2">
                  <Zap size={18} className="text-blue-600" />
                  <h3 className="text-sm font-semibold text-gray-700">
                    Mixture of Experts (MoE) Settings
                  </h3>
                </div>
                {fetchingMoeInfo ? (
                  <div className="flex items-center gap-2 text-xs text-gray-600 mb-3">
                    <Loader2 size={14} className="animate-spin" />
                    <span>Reading expert count from model file...</span>
                  </div>
                ) : (moeInfo || fetchedMoeInfo)?.num_experts ? (
                  <p className="text-xs text-gray-600 mb-3">
                    This model has{" "}
                    <strong>{(moeInfo || fetchedMoeInfo).num_experts}</strong>{" "}
                    experts available
                    {(moeInfo || fetchedMoeInfo).experts_per_token &&
                      ` (default: ${
                        (moeInfo || fetchedMoeInfo).experts_per_token
                      } per token)`}
                  </p>
                ) : (moeInfo || fetchedMoeInfo)?.is_moe &&
                  !(moeInfo || fetchedMoeInfo)?.num_experts ? (
                  <div className="p-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800 mb-3">
                    <AlertTriangle size={14} className="inline mr-1" />
                    <strong>Warning:</strong> Could not determine expert count
                    from model file. Please enter the correct number of experts
                    (typically 1-8 for most MoE models).
                  </div>
                ) : null}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">
                    Number of Experts to Use
                    {(moeInfo || fetchedMoeInfo)?.num_experts && (
                      <span className="text-xs text-gray-500 ml-2">
                        (1 - {(moeInfo || fetchedMoeInfo).num_experts})
                      </span>
                    )}
                    {!(moeInfo || fetchedMoeInfo)?.num_experts &&
                      !fetchingMoeInfo && (
                        <span className="text-xs text-gray-500 ml-2">
                          (1 - 8, enter manually)
                        </span>
                      )}
                  </label>
                  <div className="space-y-2">
                    {fetchingMoeInfo ? (
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <Loader2 size={14} className="animate-spin" />
                        <span>Loading expert information...</span>
                      </div>
                    ) : (moeInfo || fetchedMoeInfo)?.num_experts ? (
                      <>
                        <input
                          type="range"
                          min={1}
                          max={(moeInfo || fetchedMoeInfo).num_experts}
                          value={
                            nExpertsToUse ||
                            (moeInfo || fetchedMoeInfo).experts_per_token ||
                            2
                          }
                          onChange={(e) =>
                            setNExpertsToUse(parseInt(e.target.value))
                          }
                          className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                          disabled={loading}
                        />
                        <div className="flex items-center gap-3">
                          <input
                            type="number"
                            value={
                              nExpertsToUse ||
                              (moeInfo || fetchedMoeInfo).experts_per_token ||
                              2
                            }
                            onChange={(e) => {
                              const val = parseInt(e.target.value);
                              const maxExperts = (moeInfo || fetchedMoeInfo)
                                .num_experts;
                              if (val >= 1 && val <= maxExperts) {
                                setNExpertsToUse(val);
                              }
                            }}
                            className="input w-20 text-center"
                            disabled={loading}
                            min={1}
                            max={(moeInfo || fetchedMoeInfo).num_experts}
                          />
                          <span className="text-xs text-gray-500">
                            of {(moeInfo || fetchedMoeInfo).num_experts} experts
                          </span>
                        </div>
                      </>
                    ) : (
                      <div className="flex items-center gap-3">
                        <input
                          type="number"
                          value={nExpertsToUse || ""}
                          onChange={(e) => {
                            const val = e.target.value
                              ? parseInt(e.target.value)
                              : undefined;
                            // Limit to 1-8 for safety when expert count is unknown
                            if (val === undefined || (val >= 1 && val <= 8)) {
                              setNExpertsToUse(val);
                            }
                          }}
                          className="input w-20 text-center"
                          disabled={loading}
                          min={1}
                          max={8}
                          placeholder="Auto"
                        />
                        <span className="text-xs text-gray-500">
                          experts per token (leave empty for model default)
                        </span>
                      </div>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Select how many experts to use per token. More experts may
                    improve quality but use more resources.
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
              {showAdvanced ? "Hide" : "Show"} Advanced Settings
            </button>

            {/* Advanced Settings */}
            {showAdvanced && (
              <div className="p-4 bg-gray-50 rounded-lg space-y-4 border border-gray-200">
                {/* MoE Settings in Advanced - REMOVED: This was a duplicate. Main MoE section above handles all cases. */}

                <h3 className="text-sm font-semibold text-gray-700">
                  KV Cache Quantization
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Cache Type K
                    </label>
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
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Cache Type V
                    </label>
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
                <p className="text-xs text-gray-500">
                  Lower precision = less VRAM but may reduce quality
                </p>

                <h3 className="text-sm font-semibold text-gray-700 pt-2">
                  RoPE Context Extension
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Freq Base
                    </label>
                    <input
                      type="number"
                      placeholder="Auto"
                      value={ropeFreqBase || ""}
                      onChange={(e) =>
                        setRopeFreqBase(
                          e.target.value
                            ? parseFloat(e.target.value)
                            : undefined
                        )
                      }
                      className="input w-full text-sm"
                      disabled={loading}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Freq Scale
                    </label>
                    <input
                      type="number"
                      placeholder="Auto"
                      value={ropeFreqScale || ""}
                      onChange={(e) =>
                        setRopeFreqScale(
                          e.target.value
                            ? parseFloat(e.target.value)
                            : undefined
                        )
                      }
                      className="input w-full text-sm"
                      disabled={loading}
                    />
                  </div>
                </div>
                <p className="text-xs text-gray-500">
                  For extended context models. Leave blank for auto.
                </p>
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
            {savingConfig ? "Saving..." : "Save as Default"}
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
                "Load Model"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
