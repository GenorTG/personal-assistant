'use client';

import { useState } from 'react';
import { Settings2, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { useSettings } from '@/contexts/SettingsContext';
import { useSamplerSettings } from '@/contexts/SamplerSettingsContext';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import { cn } from '@/lib/utils';

export function QuickSettings() {
  const [isExpanded, setIsExpanded] = useState(false);
  const { settings: appSettings } = useSettings();
  const { settings: samplerSettings, updateSettings: updateSamplerSettings, saveToBackend } = useSamplerSettings();
  const { showSuccess, showError } = useToast();

  const streamingMode = (appSettings?.settings as any)?.streaming_mode || 'non-streaming';

  const handleStreamingModeChange = async (value: string) => {
    try {
      await api.updateSettings({ streaming_mode: value });
      showSuccess('Streaming mode updated');
    } catch (error) {
      showError('Failed to update streaming mode');
      console.error('Error updating streaming mode:', error);
    }
  };

  const handleSamplerChange = async (key: string, value: number) => {
    updateSamplerSettings({ [key]: value });
    // Debounce save to backend
    setTimeout(async () => {
      try {
        await saveToBackend();
      } catch (error) {
        console.error('Error saving sampler settings:', error);
      }
    }, 500);
  };

  return (
    <div className="border-b border-border bg-muted/30">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full justify-between px-3 py-2 h-auto"
      >
        <div className="flex items-center gap-2">
          <Settings2 size={16} />
          <span className="text-sm font-medium">Quick Settings</span>
        </div>
        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </Button>
      
      {isExpanded && (
        <div className="px-3 pb-3 space-y-3">
          {/* Streaming Mode */}
          <div className="space-y-1.5">
            <Label htmlFor="streaming-mode" className="text-xs font-medium">
              Streaming Mode
            </Label>
            <Select value={streamingMode} onValueChange={handleStreamingModeChange}>
              <SelectTrigger id="streaming-mode" className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="streaming">Streaming (Real-time, no tool calling)</SelectItem>
                <SelectItem value="non-streaming">Non-streaming (Tool calling enabled)</SelectItem>
                <SelectItem value="experimental">Experimental (Auto-detect)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Temperature */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="temperature" className="text-xs font-medium">
                Temperature
              </Label>
              <span className="text-xs text-muted-foreground">{samplerSettings.temperature.toFixed(2)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Slider
                id="temperature"
                min={0}
                max={2}
                step={0.1}
                value={[samplerSettings.temperature]}
                onValueChange={([value]) => handleSamplerChange('temperature', value)}
                className="flex-1"
              />
              <Input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={samplerSettings.temperature}
                onChange={(e) => handleSamplerChange('temperature', parseFloat(e.target.value) || 0)}
                className="w-16 h-8 text-sm"
              />
            </div>
          </div>

          {/* Top P */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="top-p" className="text-xs font-medium">
                Top P
              </Label>
              <span className="text-xs text-muted-foreground">{samplerSettings.top_p.toFixed(2)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Slider
                id="top-p"
                min={0}
                max={1}
                step={0.01}
                value={[samplerSettings.top_p]}
                onValueChange={([value]) => handleSamplerChange('top_p', value)}
                className="flex-1"
              />
              <Input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={samplerSettings.top_p}
                onChange={(e) => handleSamplerChange('top_p', parseFloat(e.target.value) || 0)}
                className="w-16 h-8 text-sm"
              />
            </div>
          </div>

          {/* Max Tokens */}
          <div className="space-y-1.5">
            <Label htmlFor="max-tokens" className="text-xs font-medium">
              Max Tokens
            </Label>
            <Input
              id="max-tokens"
              type="number"
              min={1}
              max={32768}
              step={64}
              value={samplerSettings.max_tokens}
              onChange={(e) => handleSamplerChange('max_tokens', parseInt(e.target.value) || 512)}
              className="h-8 text-sm"
            />
          </div>
        </div>
      )}
    </div>
  );
}
