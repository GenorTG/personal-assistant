'use client';

import { useState, useEffect } from 'react';
import { Package, RefreshCw, Download, CheckCircle, XCircle } from 'lucide-react';
import { STTServiceClient, TTSServiceClient } from '@/lib/api/services';
import { getWhisperModels, getPiperVoices } from '@/lib/models/catalog';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

const sttClient = new STTServiceClient();
const ttsClient = new TTSServiceClient();

export default function ModelManagement() {
  const { showSuccess, showError } = useToast();
  const [loading, setLoading] = useState(true);
  const [sttStatus, setSttStatus] = useState<any>(null);
  const [sttMemory, setSttMemory] = useState<any>(null);
  const [ttsMemory, setTtsMemory] = useState<any>(null);
  const [piperStatus, setPiperStatus] = useState<any>(null);
  const [kokoroStatus, setKokoroStatus] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadStatus();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadStatus = async () => {
    try {
      setLoading(true);
      await Promise.all([loadSTTStatus(), loadTTSStatus(), loadMemoryUsage()]);
    } catch (error) {
      console.error('Error loading model status:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadSTTStatus = async () => {
    try {
      const [status, memory] = await Promise.all([
        sttClient.getModelStatus(),
        sttClient.getMemoryUsage(),
      ]);
      setSttStatus(status);
      setSttMemory(memory);
    } catch (error) {
      console.error('Error loading STT status:', error);
    }
  };

  const loadTTSStatus = async () => {
    try {
      const [piperStatus, kokoroStatus, memory] = await Promise.all([
        ttsClient.getModelStatus('piper').catch(() => null),
        ttsClient.getModelStatus('kokoro').catch(() => null),
        ttsClient.getMemoryUsage(),
      ]);
      setPiperStatus(piperStatus);
      setKokoroStatus(kokoroStatus);
      setTtsMemory(memory);
    } catch (error) {
      console.error('Error loading TTS status:', error);
    }
  };

  const loadMemoryUsage = async () => {
    try {
      const [sttMem, ttsMem] = await Promise.all([
        sttClient.getMemoryUsage(),
        ttsClient.getMemoryUsage(),
      ]);
      setSttMemory(sttMem);
      setTtsMemory(ttsMem);
    } catch (error) {
      console.error('Error loading memory usage:', error);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadStatus();
    setRefreshing(false);
    showSuccess('Status refreshed');
  };

  const handleUnloadSTT = async () => {
    try {
      await sttClient.unloadModel();
      showSuccess('STT model unloaded');
      await loadSTTStatus();
    } catch {
      showError('Failed to unload STT model');
    }
  };

  const handleSwitchSTT = async (modelSize: string) => {
    try {
      const result = (await sttClient.switchModel(modelSize)) as any;
      if (result.status === 'success') {
        showSuccess(result.message || `Switched to Whisper ${modelSize}`);
        let attempts = 0;
        const maxAttempts = 30;
        const pollStatus = async () => {
          attempts++;
          await loadSTTStatus();
          const currentStatus = sttStatus;
          if (currentStatus?.loaded && currentStatus?.model_size === modelSize) {
            showSuccess(`Whisper ${modelSize} loaded successfully`);
          } else if (attempts < maxAttempts) {
            setTimeout(pollStatus, 1000);
          } else {
            showError('Model switch timed out - check logs for details');
          }
        };
        setTimeout(pollStatus, 1000);
      } else {
        showError(result.message || 'Failed to switch STT model');
      }
    } catch (error) {
      console.error('Error switching STT model:', error);
      showError('Failed to switch STT model');
    }
  };

  const handleUnloadTTS = async (backend: string) => {
    try {
      await ttsClient.unloadModel(backend);
      showSuccess(`${backend} model unloaded`);
      await loadTTSStatus();
    } catch {
      showError(`Failed to unload ${backend} model`);
    }
  };

  const handleReloadTTS = async (backend: string) => {
    try {
      await ttsClient.reloadModel(backend);
      showSuccess(`${backend} model reloaded`);
      await loadTTSStatus();
    } catch {
      showError(`Failed to reload ${backend} model`);
    }
  };

  const whisperModels = getWhisperModels();
  const piperVoices = getPiperVoices();

  const sttLoaded = sttStatus?.loaded;
  const piperLoaded = piperStatus?.loaded;
  const kokoroLoaded = kokoroStatus?.loaded;

  return (
    <div className="space-y-6">
      <div className={cn("hidden", loading && "block")}>
        <div className="flex items-center justify-center py-12">
          <Skeleton className="h-4 w-48" />
        </div>
      </div>

      <div className={cn("hidden", !loading && "block space-y-6")}>
        <div className="border-b border-border pb-4">
          <div className="flex items-center justify-between mb-4">
            <h4 className="font-semibold flex items-center gap-2">
              <Package size={18} />
              Model Overview
            </h4>
            <Button onClick={handleRefresh} disabled={refreshing} variant="outline" size="sm" className="flex items-center gap-2">
              <RefreshCw size={16} className={cn(refreshing && 'animate-spin')} />
              Refresh
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardContent className="p-3">
                <div className="text-xs text-muted-foreground mb-1">STT Memory</div>
                <div className="text-lg font-semibold">
                  {sttMemory?.model_memory_mb ? `${sttMemory.model_memory_mb.toFixed(1)} MB` : '0 MB'}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <div className="text-xs text-muted-foreground mb-1">TTS Memory</div>
                <div className="text-lg font-semibold">
                  {ttsMemory?.total_model_memory_mb
                    ? `${ttsMemory.total_model_memory_mb.toFixed(1)} MB`
                    : '0 MB'}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        <div className="border-b border-border pb-6">
          <h4 className="font-semibold mb-4">STT Models (Whisper)</h4>

          <Card className={cn("hidden mb-4", sttStatus && "block")}>
            <CardContent className="p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {sttLoaded ? (
                    <CheckCircle size={16} className="text-green-500" />
                  ) : (
                    <XCircle size={16} className="text-muted-foreground" />
                  )}
                  <span className="font-medium">
                    {sttLoaded ? `Loaded: ${sttStatus.model_size || 'Unknown'}` : 'No model loaded'}
                  </span>
                </div>
                <Button
                  onClick={handleUnloadSTT}
                  variant="destructive"
                  size="sm"
                  className={cn("hidden text-xs", sttLoaded && "flex")}
                >
                  Unload
                </Button>
              </div>
              <div className={cn("hidden text-xs text-muted-foreground", sttMemory && "block")}>
                Memory: {sttMemory?.model_memory_mb?.toFixed(1) || 0} MB
              </div>
            </CardContent>
          </Card>

          <div className="space-y-2">
            <Label>Switch Model Size</Label>
            <Select
              value={sttStatus?.model_size || 'base'}
              onValueChange={handleSwitchSTT}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {whisperModels.map((model) => {
                  if (!model || !model.id) return null;
                  return (
                    <SelectItem key={model.id} value={model.id}>
                      {model?.name || 'Unknown'} ({model?.memory_mb || 0} MB memory)
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-4">
          <h4 className="font-semibold">TTS Models</h4>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Piper TTS</CardTitle>
                <div className={cn("hidden flex items-center gap-2", piperStatus && "flex")}>
                  {piperLoaded ? (
                    <>
                      <CheckCircle size={14} className="text-green-500" />
                      <span className="text-xs text-muted-foreground">Loaded</span>
                      <Button
                        onClick={() => handleUnloadTTS('piper')}
                        variant="destructive"
                        size="sm"
                        className="text-xs"
                      >
                        Unload
                      </Button>
                    </>
                  ) : (
                    <>
                      <XCircle size={14} className="text-muted-foreground" />
                      <Button
                        onClick={() => handleReloadTTS('piper')}
                        variant="outline"
                        size="sm"
                        className="text-xs"
                      >
                        Load
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className={cn("hidden text-xs text-muted-foreground mb-3", piperStatus?.memory_mb && "block")}>
                Memory: {piperStatus?.memory_mb?.toFixed(1) || 0} MB
              </div>

              <div className="mt-3">
                <Label className="block text-sm font-medium mb-2">Available Voice Models</Label>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {piperVoices.map((voice: any) => {
                    if (!voice || !voice.id) return null;
                    const isCurrent =
                      piperStatus?.model_path?.includes(voice.id) || piperStatus?.voice === voice.id;
                    return (
                      <Card
                        key={voice.id}
                        className={cn(
                          'p-2',
                          isCurrent && 'bg-primary/10 border-primary'
                        )}
                      >
                        <CardContent className="p-0">
                          <div className="flex items-center justify-between">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="text-sm font-medium truncate">{voice?.name || voice?.id || 'Unknown'}</p>
                                <Badge variant="default" className={cn("hidden", isCurrent && "block")}>
                                  Current
                                </Badge>
                              </div>
                              <p className={cn("hidden text-xs text-muted-foreground", voice.language && "block")}>
                                {voice.language}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              <Button
                                onClick={async () => {
                                  try {
                                    const voiceId = voice.id || '';
                                    if (!voiceId) {
                                      showError('Voice ID is missing');
                                      return;
                                    }
                                    await api.switchTTSModel('piper', voiceId);
                                    showSuccess(`Switched to ${voice?.name || voice?.id || 'voice'}`);
                                    await loadTTSStatus();
                                  } catch (error: any) {
                                    showError(`Failed to switch: ${error.message}`);
                                  }
                                }}
                                variant="default"
                                size="sm"
                                className={cn("hidden text-xs", !isCurrent && "flex")}
                              >
                                Switch
                              </Button>
                              <Button
                                onClick={async () => {
                                  try {
                                    await ttsClient.getModelStatus('piper');
                                    showSuccess('Model download initiated');
                                    await loadTTSStatus();
                                  } catch (error: any) {
                                    showError(`Download failed: ${error.message}`);
                                  }
                                }}
                                variant="outline"
                                size="sm"
                                className={cn("hidden text-xs", voice.download_url && "flex")}
                              >
                                <Download size={12} className="mr-1" />
                                Download
                              </Button>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Kokoro TTS</CardTitle>
                <div className={cn("hidden flex items-center gap-2", kokoroStatus && "flex")}>
                  {kokoroLoaded ? (
                    <>
                      <CheckCircle size={14} className="text-green-500" />
                      <span className="text-xs text-muted-foreground">Loaded</span>
                      <Button
                        onClick={() => handleUnloadTTS('kokoro')}
                        variant="destructive"
                        size="sm"
                        className="text-xs"
                      >
                        Unload
                      </Button>
                    </>
                  ) : (
                    <>
                      <XCircle size={14} className="text-muted-foreground" />
                      <Button
                        onClick={() => handleReloadTTS('kokoro')}
                        variant="outline"
                        size="sm"
                        className="text-xs"
                      >
                        Load
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className={cn("hidden text-xs text-muted-foreground", kokoroStatus?.memory_mb && "block")}>
                Memory: {kokoroStatus?.memory_mb?.toFixed(1) || 0} MB
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
