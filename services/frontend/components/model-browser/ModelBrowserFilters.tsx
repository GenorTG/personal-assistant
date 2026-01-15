'use client';

import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import SystemStatus from '@/components/SystemStatus';
import { cn } from '@/lib/utils';

interface ModelBrowserFiltersProps {
  minParams: number;
  maxParams: number;
  quantFilter: string;
  targetContext: number;
  gpuLayers: number;
  nBatch: number;
  useFlashAttn: boolean;
  offloadKqv: boolean;
  supportsToolCalling?: 'all' | 'yes' | 'no';
  searchBySize?: boolean;
  onMinParamsChange: (value: number) => void;
  onMaxParamsChange: (value: number) => void;
  onQuantFilterChange: (value: string) => void;
  onTargetContextChange: (value: number) => void;
  onGpuLayersChange: (value: number) => void;
  onNBatchChange: (value: number) => void;
  onUseFlashAttnChange: (value: boolean) => void;
  onOffloadKqvChange: (value: boolean) => void;
  onSupportsToolCallingChange?: (value: 'all' | 'yes' | 'no') => void;
  onSearchBySizeChange?: (value: boolean) => void;
  onSaveSettings: () => void;
  viewMode: 'grid' | 'list';
  onViewModeChange: (mode: 'grid' | 'list') => void;
  activeTab: 'discover' | 'installed';
}

export function ModelBrowserFilters({
  minParams,
  maxParams,
  quantFilter,
  targetContext,
  gpuLayers,
  nBatch,
  useFlashAttn,
  offloadKqv,
  supportsToolCalling = 'all',
  searchBySize = false,
  onMinParamsChange,
  onMaxParamsChange,
  onQuantFilterChange,
  onTargetContextChange,
  onGpuLayersChange,
  onNBatchChange,
  onUseFlashAttnChange,
  onOffloadKqvChange,
  onSupportsToolCallingChange,
  onSearchBySizeChange,
  onSaveSettings,
  viewMode,
  onViewModeChange,
  activeTab,
}: ModelBrowserFiltersProps) {
  return (
    <div className="p-4 sm:p-6 flex flex-col gap-6">
      <div className="space-y-6">
        <div>
          <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 block">
            Model Size (Billions of Parameters)
          </Label>
          <div className="space-y-4">
            <div>
              <Label className="text-xs text-muted-foreground block mb-1">
                Min: {minParams}B
              </Label>
              <Slider
                value={[minParams]}
                onValueChange={([value]) => onMinParamsChange(value)}
                min={0}
                max={70}
                step={1}
                className="w-full"
              />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground block mb-1">
                Max: {maxParams}B
              </Label>
              <Slider
                value={[maxParams]}
                onValueChange={([value]) => onMaxParamsChange(value)}
                min={0}
                max={70}
                step={1}
                className="w-full"
              />
            </div>
          </div>
        </div>

        <div>
          <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 block">
            Quantization
          </Label>
          <RadioGroup value={quantFilter} onValueChange={onQuantFilterChange}>
            <div className="space-y-2">
              {['all', 'q4', 'q5', 'q8', 'f16'].map((q) => (
                <div key={q} className="flex items-center space-x-2">
                  <RadioGroupItem value={q} id={`quant-${q}`} />
                  <Label
                    htmlFor={`quant-${q}`}
                    className="text-sm font-normal cursor-pointer capitalize"
                  >
                    {q === 'all' ? 'Any' : q.toUpperCase()}
                  </Label>
                </div>
              ))}
            </div>
          </RadioGroup>
        </div>

        {activeTab === 'discover' && onSupportsToolCallingChange && (
          <div>
            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 block">
              Tool Calling Support
            </Label>
            <RadioGroup value={supportsToolCalling} onValueChange={onSupportsToolCallingChange}>
              <div className="space-y-2">
                {[
                  { value: 'all', label: 'All Models' },
                  { value: 'yes', label: 'With Tools' },
                  { value: 'no', label: 'Without Tools' },
                ].map((option) => (
                  <div key={option.value} className="flex items-center space-x-2">
                    <RadioGroupItem value={option.value} id={`tool-${option.value}`} />
                    <Label
                      htmlFor={`tool-${option.value}`}
                      className="text-sm font-normal cursor-pointer"
                    >
                      {option.label}
                    </Label>
                  </div>
                ))}
              </div>
            </RadioGroup>
          </div>
        )}

        {activeTab === 'discover' && onSearchBySizeChange && (
          <div className="flex items-center space-x-2">
            <Checkbox
              id="search-by-size"
              checked={searchBySize}
              onCheckedChange={(checked) => onSearchBySizeChange(checked === true)}
            />
            <Label htmlFor="search-by-size" className="text-sm font-normal cursor-pointer">
              Search by size only (ignore keywords)
            </Label>
          </div>
        )}

        <Separator />

        <div>
          <h3 className="text-sm font-bold mb-3">Loading Settings</h3>
          <div className="space-y-4">
            <div>
              <Label className="text-xs text-muted-foreground block mb-1">Context Size</Label>
              <Select
                value={targetContext.toString()}
                onValueChange={(v) => onTargetContextChange(Number(v))}
              >
                <SelectTrigger className="w-full text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="2048">2048 (2k)</SelectItem>
                  <SelectItem value="4096">4096 (4k)</SelectItem>
                  <SelectItem value="8192">8192 (8k)</SelectItem>
                  <SelectItem value="16384">16384 (16k)</SelectItem>
                  <SelectItem value="32768">32768 (32k)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-xs text-muted-foreground block mb-1">GPU Layers</Label>
              <Input
                type="number"
                value={gpuLayers}
                onChange={(e) => onGpuLayersChange(Number(e.target.value))}
                className="w-full text-sm"
                placeholder="-1 for all"
              />
              <p className="text-xs text-muted-foreground mt-1">-1 = Offload all to GPU</p>
            </div>

            <div>
              <Label className="text-xs text-muted-foreground block mb-1">Chunk Size</Label>
              <Input
                type="number"
                value={nBatch}
                onChange={(e) => onNBatchChange(Number(e.target.value) || 0)}
                className="w-full text-sm"
                min={0}
                placeholder="0 = use model defaults"
              />
              <p className="text-xs text-muted-foreground mt-1">
                {nBatch === 0 ? "Using model defaults" : `Chunk size: ${nBatch}`}
              </p>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="flash-attn"
                checked={useFlashAttn}
                onCheckedChange={(checked) => onUseFlashAttnChange(checked === true)}
              />
              <Label htmlFor="flash-attn" className="text-sm font-normal cursor-pointer">
                Flash Attention
              </Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="offload-kqv"
                checked={offloadKqv}
                onCheckedChange={(checked) => onOffloadKqvChange(checked === true)}
              />
              <Label htmlFor="offload-kqv" className="text-sm font-normal cursor-pointer">
                Offload KV Cache
              </Label>
            </div>

            <Button onClick={onSaveSettings} variant="outline" className="w-full text-xs" size="sm">
              Save as Defaults
            </Button>
          </div>
        </div>

        <Separator />

        <div>
          <SystemStatus />
        </div>
      </div>

      <div className="mt-auto space-y-4">
        <div className="p-4 bg-primary/10 rounded border border-primary/20">
          <h3 className="text-sm font-semibold text-primary mb-1">Pro Tip</h3>
          <p className="text-xs text-primary/80">
            Search for "GGUF" to find compatible models. Look for Q4_K_M quantization for best
            balance.
          </p>
        </div>

        <div className={cn("hidden", activeTab === 'discover' && "block")}>
          <div className="flex bg-muted p-1 rounded">
            <Button
              variant={viewMode === 'grid' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => onViewModeChange('grid')}
              className="flex-1"
              title="Grid View"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
                <rect x="1" y="1" width="6" height="6" rx="1" />
                <rect x="9" y="1" width="6" height="6" rx="1" />
                <rect x="1" y="9" width="6" height="6" rx="1" />
                <rect x="9" y="9" width="6" height="6" rx="1" />
              </svg>
            </Button>
            <Button
              variant={viewMode === 'list' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => onViewModeChange('list')}
              className="flex-1"
              title="List View"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
                <rect x="1" y="2" width="14" height="2" rx="1" />
                <rect x="1" y="7" width="14" height="2" rx="1" />
                <rect x="1" y="12" width="14" height="2" rx="1" />
              </svg>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}


