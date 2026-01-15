'use client';

import { useState, useEffect } from 'react';
import { X, Save, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

interface ServerSettingsPanelProps {
  onClose: () => void;
}

export default function ServerSettingsPanel({ onClose }: ServerSettingsPanelProps) {
  const { showSuccess, showError } = useToast();
  const [loading, setLoading] = useState(false);
  const [systemInfo, setSystemInfo] = useState<any>(null);

  const [nCtx, setNCtx] = useState(4096);
  const [nThreads, setNThreads] = useState(0);
  const [nGpuLayers, setNGpuLayers] = useState(-1);
  const [nBatch, setNBatch] = useState(0);
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
      showSuccess('Settings saved! They will be applied when loading the next model.');
      onClose();
    } catch (error) {
      console.error('Error saving settings:', error);
      showError('Error saving settings');
    } finally {
      setLoading(false);
    }
  };

  const hasGpu = systemInfo?.gpu_available;

  return (
    <div className="w-full sm:w-96 bg-background border-l border-border flex flex-col fixed right-0 z-40 shadow-2xl h-full">
      <div className="p-4 border-b border-border flex-shrink-0">
        <div className="flex justify-between items-center mb-2">
          <h2 className="text-xl font-bold">Server Settings</h2>
          <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8">
            <X size={20} />
          </Button>
        </div>

        <Card className={cn("hidden mt-2", systemInfo && "block")}>
          <CardContent className="p-2">
            <div className="text-xs font-semibold text-muted-foreground mb-1">System Info:</div>
            <div className="text-xs space-y-1">
              <div>GPU: {hasGpu ? '✓ Available' : '✗ Not Available'}</div>
              <div className={cn("hidden", systemInfo?.gpu_name && "block")}>
                Device: {systemInfo.gpu_name}
              </div>
              <div className={cn("hidden", systemInfo?.vram_total && "block")}>
                VRAM: {systemInfo.vram_total} GB
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <div className="p-4 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Context & Processing</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label className="block text-sm font-medium mb-1">Context Size (n_ctx)</Label>
                <Input
                  type="number"
                  min="512"
                  max="32768"
                  step="512"
                  value={nCtx}
                  onChange={(e) => setNCtx(parseInt(e.target.value) || 4096)}
                  disabled={loading}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Maximum context window size (higher = more VRAM)
                </p>
              </div>

              <div>
                <Label className="block text-sm font-medium mb-1">Batch Size (n_batch)</Label>
                <Input
                  type="number"
                  min="0"
                  max="4096"
                  step="128"
                  value={nBatch}
                  onChange={(e) => setNBatch(parseInt(e.target.value) || 0)}
                  disabled={loading}
                  placeholder="0 = use model defaults"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  {nBatch === 0 ? "Using model defaults" : "Batch size for prompt processing"}
                </p>
              </div>

              <div>
                <Label className="block text-sm font-medium mb-1">CPU Threads (n_threads)</Label>
                <Input
                  type="number"
                  min="0"
                  max="64"
                  value={nThreads}
                  onChange={(e) => setNThreads(parseInt(e.target.value) || 0)}
                  disabled={loading}
                  placeholder="0 = use model defaults"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  {nThreads === 0 ? "Using model defaults" : "Number of CPU threads to use"}
                </p>
              </div>

              <div>
                <Label className="block text-sm font-medium mb-1">GPU Layers (n_gpu_layers)</Label>
                <Input
                  type="number"
                  min="-1"
                  max="100"
                  value={nGpuLayers}
                  onChange={(e) => setNGpuLayers(parseInt(e.target.value) || -1)}
                  disabled={loading}
                />
                <p className="text-xs text-muted-foreground mt-1">Layers to offload to GPU (-1 = all layers)</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">KV Cache Quantization</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="block text-sm font-medium mb-1">Cache Type K</Label>
                  <Select value={cacheTypeK} onValueChange={setCacheTypeK} disabled={loading}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="f16">f16 (Default)</SelectItem>
                      <SelectItem value="q8_0">q8_0 (Less VRAM)</SelectItem>
                      <SelectItem value="q4_0">q4_0 (Least VRAM)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="block text-sm font-medium mb-1">Cache Type V</Label>
                  <Select value={cacheTypeV} onValueChange={setCacheTypeV} disabled={loading}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="f16">f16 (Default)</SelectItem>
                      <SelectItem value="q8_0">q8_0 (Less VRAM)</SelectItem>
                      <SelectItem value="q4_0">q4_0 (Least VRAM)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Quantizing KV cache reduces VRAM usage but may slightly impact quality.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Memory & Performance</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="useMmap"
                  checked={useMmap}
                  onCheckedChange={(checked) => setUseMmap(checked === true)}
                  disabled={loading}
                />
                <Label htmlFor="useMmap" className="text-sm font-medium cursor-pointer">
                  Use Memory Mapping (mmap)
                </Label>
              </div>
              <p className="text-xs text-muted-foreground ml-6">
                Memory map the model file for faster loading and lower memory usage
              </p>

              <div className="flex items-center space-x-2">
                <Checkbox
                  id="useMlock"
                  checked={useMlock}
                  onCheckedChange={(checked) => setUseMlock(checked === true)}
                  disabled={loading}
                />
                <Label htmlFor="useMlock" className="text-sm font-medium cursor-pointer">
                  Lock Memory (mlock)
                </Label>
              </div>
              <p className="text-xs text-muted-foreground ml-6">
                Lock model memory in RAM to prevent swapping (may require root)
              </p>

              <div className="flex items-center space-x-2">
                <Checkbox
                  id="useFlashAttention"
                  checked={useFlashAttention}
                  onCheckedChange={(checked) => setUseFlashAttention(checked === true)}
                  disabled={loading}
                />
                <Label htmlFor="useFlashAttention" className="text-sm font-medium cursor-pointer">
                  Flash Attention
                </Label>
              </div>
              <p className="text-xs text-muted-foreground ml-6">
                Enable flash attention for faster inference (if supported by model)
              </p>
            </CardContent>
          </Card>
        </div>
      </ScrollArea>

      <div className="p-4 border-t border-border flex-shrink-0">
        <div className="flex gap-2">
          <Button onClick={handleSave} disabled={loading} className="flex-1 flex items-center justify-center gap-2">
            <Save size={16} />
            Save Settings
          </Button>
          <Button variant="ghost" size="icon" onClick={loadSystemInfo} disabled={loading}>
            <RefreshCw size={16} />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-2 text-center">
          Settings will be applied when loading the next model
        </p>
      </div>
    </div>
  );
}
