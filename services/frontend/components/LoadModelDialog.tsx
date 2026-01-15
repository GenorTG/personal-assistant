'use client';

import { useState, useEffect } from 'react';
import {
  Loader2,
  CheckCircle,
  XCircle,
  Zap,
  AlertTriangle,
  Settings2,
} from 'lucide-react';
import { api } from '@/lib/api';
import { useSettings } from '@/contexts/SettingsContext';
import { useToast } from '@/contexts/ToastContext';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface LoadModelDialogProps {
  modelId: string;
  modelName: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function LoadModelDialog({
  modelId,
  modelName,
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

  const [nCtx, setNCtx] = useState(4096);
  const [nBatch, setNBatch] = useState(0);
  const [nThreads, setNThreads] = useState(0);
  const [nGpuLayers, setNGpuLayers] = useState(-1);
  const [useMmap, setUseMmap] = useState(true);
  const [useMlock, setUseMlock] = useState(false);
  const [flashAttn, setFlashAttn] = useState(false);
  const [ropeFreqBase, setRopeFreqBase] = useState<number | undefined>(undefined);
  const [ropeFreqScale, setRopeFreqScale] = useState<number | undefined>(undefined);
  const [cacheTypeK, setCacheTypeK] = useState('f16');
  const [cacheTypeV, setCacheTypeV] = useState('f16');

  const [vramEstimate, setVramEstimate] = useState<any>(null);
  const [systemInfo, setSystemInfo] = useState<any>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  useEffect(() => {
    let mounted = true;

    const init = async () => {
      await loadSystemInfo();
      if (mounted) {
        await loadSettingsAndConfig();
      }
    };

    init();

    return () => {
      mounted = false;
    };
  }, [modelId]);

  const updateVramEstimate = () => {
    const baseVram = 4.0;
    const kvCacheMultiplier =
      cacheTypeK === 'f16' ? 1.0 : cacheTypeK === 'q8_0' ? 0.5 : 0.25;
    const contextVram = (nCtx / 4096) * 2.0 * kvCacheMultiplier;
    const totalVram = baseVram + contextVram;

    setVramEstimate({
      total_vram_gb: totalVram,
      model_vram_gb: baseVram,
      kv_cache_vram_gb: contextVram,
      will_fit: systemInfo?.vram_total ? totalVram < systemInfo.vram_total : null,
    });
  };

  useEffect(() => {
    updateVramEstimate();
  }, [nCtx, nGpuLayers, cacheTypeK, cacheTypeV]);

  const loadSystemInfo = async () => {
    try {
      const info = (await api.getSystemInfo()) as any;
      setSystemInfo(info);

      const maxThreads = info?.cpu_threads_available || info?.cpu_count || 4;
      if (nThreads > maxThreads) {
        setNThreads(maxThreads);
      }
    } catch (error) {
      console.error('Error loading system info:', error);
    }
  };

  const loadSettingsAndConfig = async () => {
    try {
      const globalDefaults = (contextSettings?.default_load_options || {}) as Record<string, any>;
      const modelConfig = (await api.getModelConfig(modelId)) as any;

      const getValue = (key: string, defaultVal: any) => {
        if (modelConfig && modelConfig[key] !== undefined) return modelConfig[key];
        if (globalDefaults && globalDefaults[key] !== undefined) return globalDefaults[key];
        return defaultVal;
      };

      setNCtx(getValue('n_ctx', 4096));
      setNBatch(getValue('n_batch', 0));
      setNThreads(getValue('n_threads', 0));
      setNGpuLayers(getValue('n_gpu_layers', -1));
      setUseMmap(getValue('use_mmap', true));
      setUseMlock(getValue('use_mlock', false));
      setFlashAttn(getValue('flash_attn', false));
      setRopeFreqBase(getValue('rope_freq_base', undefined));
      setRopeFreqScale(getValue('rope_freq_scale', undefined));
      setCacheTypeK(getValue('cache_type_k', 'f16'));
      setCacheTypeV(getValue('cache_type_v', 'f16'));
    } catch (error) {
      console.error('Error loading settings/config:', error);
    }
  };

  const saveModelConfig = async () => {
    setSavingConfig(true);
    try {
      // Build config object, filtering out undefined and invalid values
      const config: Record<string, any> = {};
      
      // Validate and include n_ctx (must be >= 512)
      if (nCtx !== undefined && nCtx >= 512) {
        config.n_ctx = nCtx;
      }
      // Only include n_batch if > 0 (schema requires >= 1)
      if (nBatch !== undefined && nBatch > 0) {
        config.n_batch = nBatch;
      }
      // Only include n_threads if > 0 (schema requires >= 1)
      if (nThreads !== undefined && nThreads > 0) {
        config.n_threads = nThreads;
      }
      // n_gpu_layers can be -1 or >= 0
      if (nGpuLayers !== undefined) {
        config.n_gpu_layers = nGpuLayers;
      }
      if (useMmap !== undefined) {
        config.use_mmap = useMmap;
      }
      if (useMlock !== undefined) {
        config.use_mlock = useMlock;
      }
      if (flashAttn !== undefined) {
        config.flash_attn = flashAttn;
      }
      if (ropeFreqBase !== undefined && ropeFreqBase !== null) {
        config.rope_freq_base = ropeFreqBase;
      }
      if (ropeFreqScale !== undefined && ropeFreqScale !== null) {
        config.rope_freq_scale = ropeFreqScale;
      }
      if (cacheTypeK !== undefined && cacheTypeK !== null) {
        config.cache_type_k = cacheTypeK;
      }
      if (cacheTypeV !== undefined && cacheTypeV !== null) {
        config.cache_type_v = cacheTypeV;
      }
      
      await api.saveModelConfig(modelId, config);
      showSuccess('Settings saved as default for this model!');
    } catch (error: any) {
      console.error('Error saving model config:', error);
      // Extract error message from response - check multiple possible locations
      let errorMessage = 'Failed to save settings';
      if (error?.message) {
        errorMessage = error.message;
      } else if (error?.response?.detail) {
        errorMessage = error.response.detail;
      } else if (error?.detail) {
        errorMessage = error.detail;
      } else if (typeof error === 'string') {
        errorMessage = error;
      }
      showError(`Failed to save settings: ${errorMessage}`);
    } finally {
      setSavingConfig(false);
    }
  };

  const handleLoad = async () => {
    setLoading(true);
    setError(null);
    setSuccess(false);
    setProgress(0);

    let progressInterval: NodeJS.Timeout | null = null;

    try {
      // Show indeterminate progress (pulsing animation) instead of fake progress
      // Model loading is a blocking operation, so we can't get real-time progress
      setProgress(50); // Show 50% to indicate loading is in progress

      const options: Record<string, any> = {
        n_ctx: nCtx,
        n_batch: nBatch > 0 ? nBatch : undefined,
        n_threads: nThreads > 0 ? nThreads : undefined,
        // Always send n_gpu_layers: -1 means all layers on GPU, 0 means CPU only
        // If not set, backend will auto-detect, but we want to be explicit
        n_gpu_layers: nGpuLayers !== undefined ? nGpuLayers : -1,  // Default to -1 (all GPU layers) if not set
        use_mmap: useMmap,
        use_mlock: useMlock,
        flash_attn: flashAttn,
      };

      if (ropeFreqBase !== undefined) {
        options.rope_freq_base = ropeFreqBase;
      }
      if (ropeFreqScale !== undefined) {
        options.rope_freq_scale = ropeFreqScale;
      }
      if (cacheTypeK !== 'f16') {
        options.cache_type_k = cacheTypeK;
      }
      if (cacheTypeV !== 'f16') {
        options.cache_type_v = cacheTypeV;
      }

      await api.loadModel(modelId, options);

      if (progressInterval) {
        clearInterval(progressInterval);
      }
      setProgress(100);
      setSuccess(true);

      setTimeout(() => {
        onSuccess();
      }, 2000);
    } catch (err) {
      if (progressInterval) {
        clearInterval(progressInterval);
      }
      const errorMessage = err instanceof Error ? err.message : 'Failed to load model';
      setError(errorMessage);
      setProgress(0);
      
      // Show more helpful error message if it's a connection error
      if (errorMessage.includes('connection') || errorMessage.includes('127.0.0.1:8001')) {
        setError('Failed to start LLM server. The server should start automatically when loading a model. Check Gateway logs for details.');
      }
    } finally {
      setLoading(false);
    }
  };

  const showVramEstimate = !loading && !success && vramEstimate && systemInfo?.gpu_available;
  const willFit = vramEstimate?.will_fit === true;
  const mayNotFit = vramEstimate?.will_fit === false;

  if (!modelId) {
    return null;
  }

  return (
    <Dialog open={!!modelId} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col p-0 overflow-x-hidden" style={{ maxWidth: 'min(95vw, 42rem)', width: 'min(95vw, 42rem)' }}>
        <DialogHeader className="p-5 border-b border-border flex-shrink-0 overflow-x-hidden max-w-full">
          <div className="flex justify-between items-center max-w-full overflow-x-hidden">
            <div className="min-w-0 flex-1 overflow-x-hidden">
              <DialogTitle className="truncate">Load Model</DialogTitle>
              <DialogDescription className="truncate max-w-full" title={modelName}>
                {modelName}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <ScrollArea className="flex-1 min-h-0">
          <div className="p-5 space-y-5">
            {loading && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Loading model...</span>
                  {progress === 100 ? (
                    <span className="font-medium">Complete</span>
                  ) : (
                    <span className="text-muted-foreground">Please wait...</span>
                  )}
                </div>
                {progress === 50 ? (
                  <div className="relative w-full h-2 bg-muted rounded overflow-hidden">
                    <div className="absolute inset-0 bg-primary/20" />
                    <div 
                      className="absolute left-0 top-0 h-full w-1/3 bg-primary animate-pulse" 
                      style={{ 
                        animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                      }} 
                    />
                  </div>
                ) : (
                  <Progress value={progress} />
                )}
              </div>
            )}

            <Alert variant="default" className={cn("hidden", success && "block")}>
              <CheckCircle size={20} />
              <AlertDescription className="font-medium">Model loaded successfully!</AlertDescription>
            </Alert>

            <Alert variant="destructive" className={cn("hidden", error && "block")}>
              <XCircle size={20} />
              <AlertDescription>{error}</AlertDescription>
            </Alert>

            <Card className={cn("hidden", showVramEstimate && "block")}>
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Zap size={18} className={cn(willFit ? 'text-green-600' : 'text-amber-600')} />
                    <span className="font-semibold text-sm">VRAM Estimate</span>
                  </div>
                  <Badge variant="default" className={cn("hidden", willFit && "block bg-green-600")}>
                    Should Fit ✓
                  </Badge>
                  <Badge variant="secondary" className={cn("hidden", mayNotFit && "block bg-amber-600 text-white flex items-center gap-1")}>
                    <AlertTriangle size={12} />
                    May Not Fit
                  </Badge>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Model:</span>{' '}
                    <span className="ml-1 font-medium">{vramEstimate?.model_vram_gb?.toFixed(2) || '0.00'} GB</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">KV Cache:</span>{' '}
                    <span className="ml-1 font-medium">{vramEstimate?.kv_cache_vram_gb?.toFixed(2) || '0.00'} GB</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Total Needed:</span>{' '}
                    <span className="ml-1 font-medium">{vramEstimate?.total_vram_gb?.toFixed(2) || '0.00'} GB</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Available:</span>{' '}
                    <span className="ml-1 font-medium">{systemInfo?.vram_total?.toFixed(2) || 'N/A'} GB</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Context Size</Label>
                  <Input
                    type="number"
                    value={nCtx}
                    onChange={(e) => setNCtx(parseInt(e.target.value) || 4096)}
                    disabled={loading}
                    min={512}
                    max={131072}
                    step={512}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Memory for conversation history</p>
                </div>
                <div>
                  <Label>GPU Layers</Label>
                  <Input
                    type="number"
                    value={nGpuLayers}
                    onChange={(e) => setNGpuLayers(parseInt(e.target.value))}
                    disabled={loading}
                    min={-1}
                  />
                  <p className="text-xs text-muted-foreground mt-1">-1 = all, 0 = CPU only</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Batch Size</Label>
                  <Input
                    type="number"
                    value={nBatch}
                    onChange={(e) => setNBatch(parseInt(e.target.value) || 0)}
                    disabled={loading}
                    min={0}
                    max={4096}
                    placeholder="0 = use model defaults"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    {nBatch === 0 ? "Using model defaults" : `Batch size: ${nBatch}`}
                  </p>
                </div>
                <div>
                  <Label>
                    CPU Threads
                    <span className={cn("hidden text-xs text-muted-foreground ml-2", systemInfo?.cpu_threads_available && "inline")}>
                      (max: {systemInfo?.cpu_threads_available})
                    </span>
                  </Label>
                  <Input
                    type="number"
                    value={nThreads}
                    onChange={(e) => {
                      const value = parseInt(e.target.value) || 0;
                      if (value === 0) {
                        setNThreads(0);
                      } else {
                        const maxThreads = systemInfo?.cpu_threads_available || systemInfo?.cpu_count || 128;
                        setNThreads(Math.min(value, maxThreads));
                      }
                    }}
                    disabled={loading}
                    min={0}
                    max={systemInfo?.cpu_threads_available || systemInfo?.cpu_count || 128}
                    placeholder="0 = use model defaults"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    {nThreads === 0 ? "Using model defaults" : `CPU threads: ${nThreads}`}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-x-6 gap-y-2 py-2">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="flashAttn"
                    checked={flashAttn}
                    onCheckedChange={(checked) => setFlashAttn(checked === true)}
                    disabled={loading}
                  />
                  <Label htmlFor="flashAttn" className="text-sm cursor-pointer">
                    Flash Attention
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="useMmap"
                    checked={useMmap}
                    onCheckedChange={(checked) => setUseMmap(checked === true)}
                    disabled={loading}
                  />
                  <Label htmlFor="useMmap" className="text-sm cursor-pointer">
                    Memory Map
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="useMlock"
                    checked={useMlock}
                    onCheckedChange={(checked) => setUseMlock(checked === true)}
                    disabled={loading}
                  />
                  <Label htmlFor="useMlock" className="text-sm cursor-pointer">
                    Lock Memory
                  </Label>
                </div>
              </div>

              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-sm"
              >
                <Settings2 size={16} />
                <span className={cn("hidden", showAdvanced && "block")}>Hide</span>
                <span className={cn("hidden", !showAdvanced && "block")}>Show</span> Advanced Settings
              </Button>

              <Card className={cn("hidden", showAdvanced && "block")}>
                <CardHeader>
                  <CardTitle className="text-sm">KV Cache Quantization</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs">Cache Type K</Label>
                      <Select value={cacheTypeK} onValueChange={setCacheTypeK} disabled={loading}>
                        <SelectTrigger className="text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="f16">f16 (Default)</SelectItem>
                          <SelectItem value="f32">f32</SelectItem>
                          <SelectItem value="q8_0">q8_0 (8-bit)</SelectItem>
                          <SelectItem value="q4_0">q4_0 (4-bit)</SelectItem>
                          <SelectItem value="q4_1">q4_1</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-xs">Cache Type V</Label>
                      <Select value={cacheTypeV} onValueChange={setCacheTypeV} disabled={loading}>
                        <SelectTrigger className="text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="f16">f16 (Default)</SelectItem>
                          <SelectItem value="f32">f32</SelectItem>
                          <SelectItem value="q8_0">q8_0 (8-bit)</SelectItem>
                          <SelectItem value="q4_0">q4_0 (4-bit)</SelectItem>
                          <SelectItem value="q4_1">q4_1</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground">Lower precision = less VRAM but may reduce quality</p>

                  <Separator />

                  <div>
                    <CardTitle className="text-sm">RoPE Context Extension</CardTitle>
                    <div className="grid grid-cols-2 gap-4 mt-4">
                      <div>
                        <Label className="text-xs">Freq Base</Label>
                        <Input
                          type="number"
                          placeholder="Auto"
                          value={ropeFreqBase || ''}
                          onChange={(e) =>
                            setRopeFreqBase(e.target.value ? parseFloat(e.target.value) : undefined)
                          }
                          disabled={loading}
                          className="text-sm"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Freq Scale</Label>
                        <Input
                          type="number"
                          placeholder="Auto"
                          value={ropeFreqScale || ''}
                          onChange={(e) =>
                            setRopeFreqScale(e.target.value ? parseFloat(e.target.value) : undefined)
                          }
                          disabled={loading}
                          className="text-sm"
                        />
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">For extended context models. Leave blank for auto.</p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </ScrollArea>

        <div className="p-5 border-t border-border bg-muted/50 flex justify-between items-center flex-shrink-0">
          <Button
            onClick={saveModelConfig}
            variant="ghost"
            size="sm"
            disabled={loading || savingConfig}
          >
            {savingConfig ? 'Saving...' : 'Save as Default'}
          </Button>
          <div className="flex gap-3">
            <Button onClick={onClose} variant="outline" disabled={loading}>
              Cancel
            </Button>
            <Button
              onClick={success ? onClose : handleLoad}
              disabled={loading}
              className="flex items-center gap-2"
            >
              {loading && (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Loading...
                </>
              )}
              {!loading && success && (
                <>
                  <CheckCircle size={16} />
                  Close
                </>
              )}
              {!loading && !success && 'Load Model'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
