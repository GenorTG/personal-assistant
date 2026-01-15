'use client';

import { useState, useEffect } from 'react';
import { Brain, CheckCircle, XCircle } from 'lucide-react';
import { api } from '@/lib/api';
import SamplerSettings from '../SamplerSettings';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

interface AISettingsProps {
  settings: any;
  onSettingsChange: (settings: any) => void;
}

export default function AISettings({ settings, onSettingsChange }: AISettingsProps) {
  const [llmServiceStatus, setLlmServiceStatus] = useState<any>(null);

  const loadLLMServiceStatus = async () => {
    try {
      const serviceStatus = (await api.getLLMServiceStatus()) as any;
      // Use setTimeout to defer setState and avoid synchronous setState in effect
      setTimeout(() => {
        setLlmServiceStatus(serviceStatus);
      }, 0);
    } catch (error) {
      console.error('Error loading LLM service status:', error);
    }
  };

  useEffect(() => {
    loadLLMServiceStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isRemote = settings?.llm_endpoint_mode === 'remote';
  const isLocal = !isRemote;
  const isRunning = llmServiceStatus?.running;

  return (
    <div className="space-y-6">
      <div className="border-b border-border pb-6">
        <h4 className="font-semibold mb-4 flex items-center gap-2">
          <Brain size={18} />
          LLM Endpoint Configuration
        </h4>

        <RadioGroup
          value={settings?.llm_endpoint_mode || 'local'}
          onValueChange={(value) => {
            const newSettings = { ...settings, llm_endpoint_mode: value };
            onSettingsChange(newSettings);
          }}
          className="space-y-3"
        >
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="local" id="endpoint-local" />
            <Label htmlFor="endpoint-local" className="text-sm cursor-pointer">
              Local (llama-cpp-python server)
            </Label>
          </div>
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="remote" id="endpoint-remote" />
            <Label htmlFor="endpoint-remote" className="text-sm cursor-pointer">
              Remote (OpenAI-compatible API)
            </Label>
          </div>
        </RadioGroup>

        <Card className={cn("hidden mt-4", isRemote && "block")}>
          <CardContent className="p-4 space-y-3">
            <div>
              <Label className="text-xs font-medium mb-1.5 block">API Endpoint URL</Label>
              <Input
                type="text"
                value={settings?.llm_remote_url || ''}
                onChange={(e) => {
                  const newSettings = { ...settings, llm_remote_url: e.target.value };
                  onSettingsChange(newSettings);
                }}
                placeholder="https://api.openai.com/v1"
                className="text-sm"
              />
            </div>

            <div>
              <Label className="text-xs font-medium mb-1.5 block">API Key (optional)</Label>
              <Input
                type="password"
                value={settings?.llm_remote_api_key || ''}
                onChange={(e) => {
                  const newSettings = { ...settings, llm_remote_api_key: e.target.value };
                  onSettingsChange(newSettings);
                }}
                placeholder="sk-..."
                className="text-sm"
              />
            </div>

            <div>
              <Label className="text-xs font-medium mb-1.5 block">Model Name/ID</Label>
              <Input
                type="text"
                value={settings?.llm_remote_model || ''}
                onChange={(e) => {
                  const newSettings = { ...settings, llm_remote_model: e.target.value };
                  onSettingsChange(newSettings);
                }}
                placeholder="gpt-4, gpt-3.5-turbo, or model name"
                className="text-sm"
              />
            </div>
          </CardContent>
        </Card>

        <Card className={cn("hidden mt-4", isLocal && "block")}>
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="font-medium">llama-cpp-python Server</span>
              <div className="text-sm">
                <Badge variant={isRunning ? 'default' : 'secondary'} className="flex items-center gap-1">
                  {isRunning ? (
                    <>
                      <CheckCircle size={16} />
                      Running
                    </>
                  ) : (
                    <>
                      <XCircle size={16} />
                      Stopped
                    </>
                  )}
                </Badge>
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-1">Integrated in Gateway - Load a model to start</p>
          </CardContent>
        </Card>
      </div>

      <Separator />

      <div className="pt-6">
        <h4 className="font-semibold mb-4">Sampler Settings</h4>
        <SamplerSettings />
      </div>
    </div>
  );
}




