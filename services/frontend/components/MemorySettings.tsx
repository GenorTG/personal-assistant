'use client';

import { useState, useEffect } from 'react';
import { Database, Brain, Sliders, Save, Eye } from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export default function MemorySettings() {
  const { showSuccess, showError } = useToast();
  const [similarityThreshold, setSimilarityThreshold] = useState(0.7);
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(true);

  const [vectorMemoryEnabled, setVectorMemoryEnabled] = useState(true);
  const [vectorMemorySaveEnabled, setVectorMemorySaveEnabled] = useState(true);
  const [vectorMemoryReadEnabled, setVectorMemoryReadEnabled] = useState(true);
  const [vectorMemoryApplyToAll, setVectorMemoryApplyToAll] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const memorySettings = (await api.getMemorySettings()) as any;
      if (memorySettings) {
        setSimilarityThreshold(memorySettings.similarity_threshold ?? 0.7);
        setTopK(memorySettings.top_k ?? 5);
      }

      const vectorSettings = (await api.getVectorMemorySettings()) as any;
      if (vectorSettings) {
        setVectorMemoryEnabled(vectorSettings.vector_memory_enabled ?? true);
        setVectorMemorySaveEnabled(vectorSettings.vector_memory_save_enabled ?? true);
        setVectorMemoryReadEnabled(vectorSettings.vector_memory_read_enabled ?? true);
        setVectorMemoryApplyToAll(vectorSettings.vector_memory_apply_to_all ?? false);
      }
    } catch (error) {
      console.error('Error loading memory settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      await api.updateMemorySettings({
        similarity_threshold: similarityThreshold,
        top_k: topK,
      });

      await api.setVectorMemorySettings({
        vector_memory_enabled: vectorMemoryEnabled,
        vector_memory_save_enabled: vectorMemorySaveEnabled,
        vector_memory_read_enabled: vectorMemoryReadEnabled,
        vector_memory_apply_to_all: vectorMemoryApplyToAll,
      });

      showSuccess('Memory settings saved successfully!');
    } catch (error) {
      console.error('Error saving memory settings:', error);
      showError('Failed to save memory settings');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={20} />
        <h3 className="font-semibold text-lg">Memory & Context Settings</h3>
      </div>

      <div className={cn("hidden", loading && "block")}>
        <div className="flex items-center justify-center py-8">
          <Skeleton className="h-4 w-48" />
        </div>
      </div>

      <div className={cn("hidden", !loading && "block space-y-4")}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database size={18} />
              Automatic Vector Memory
            </CardTitle>
            <CardDescription>
              Controls automatic context saving and retrieval. When enabled, messages are automatically saved to
              vector memory and relevant context is retrieved for conversations.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between p-3 border rounded">
              <div>
                <Label className="font-medium text-sm">Enable Vector Memory</Label>
                <p className="text-xs text-muted-foreground">Master switch for vector memory system</p>
              </div>
              <Switch checked={vectorMemoryEnabled} onCheckedChange={setVectorMemoryEnabled} />
            </div>

            <div className={cn("hidden space-y-3", vectorMemoryEnabled && "block")}>
              <div className="flex items-center justify-between p-3 border rounded">
                <div>
                  <Label className="font-medium text-sm flex items-center gap-2">
                    <Save size={16} />
                    Save New Information
                  </Label>
                  <p className="text-xs text-muted-foreground">Store new messages in vector memory</p>
                </div>
                <Switch checked={vectorMemorySaveEnabled} onCheckedChange={setVectorMemorySaveEnabled} />
              </div>

              <div className="flex items-center justify-between p-3 border rounded">
                <div>
                  <Label className="font-medium text-sm flex items-center gap-2">
                    <Eye size={16} />
                    Read/Retrieve Information
                  </Label>
                  <p className="text-xs text-muted-foreground">Use stored information for context</p>
                </div>
                <Switch checked={vectorMemoryReadEnabled} onCheckedChange={setVectorMemoryReadEnabled} />
              </div>

              <div className="flex items-center justify-between p-3 border rounded bg-yellow-50 dark:bg-yellow-950/20">
                <div>
                  <Label className="font-medium text-sm">Apply to All Conversations</Label>
                  <p className="text-xs text-muted-foreground">Override per-conversation settings</p>
                </div>
                <Switch checked={vectorMemoryApplyToAll} onCheckedChange={setVectorMemoryApplyToAll} />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sliders size={18} />
              Retrieval Parameters
            </CardTitle>
            <CardDescription>
              These settings control HOW vector memory retrieval works (when automatic retrieval is enabled).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label className="block text-sm font-medium mb-2">
                Similarity Threshold: {similarityThreshold.toFixed(2)}
              </Label>
              <Slider
                value={[similarityThreshold]}
                onValueChange={([value]) => setSimilarityThreshold(value)}
                min={0}
                max={1}
                step={0.05}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Minimum similarity score (0-1) for context retrieval. Higher values = more relevant but fewer
                results.
              </p>
            </div>

            <div>
              <Label className="block text-sm font-medium mb-2">Top-K Results: {topK}</Label>
              <Slider
                value={[topK]}
                onValueChange={([value]) => setTopK(value)}
                min={1}
                max={20}
                step={1}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Maximum number of relevant past messages to retrieve for context.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Brain size={18} />
              Memory Tool (Explicit Memory)
            </CardTitle>
            <CardDescription>
              The LLM can explicitly save and recall memories using the "memory" tool. This is separate from
              automatic vector memory and allows the model to decide when to store important information.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground italic">
              No settings needed - the tool is automatically available when tool calling is enabled.
            </p>
          </CardContent>
        </Card>

        <Separator />

        <Button onClick={handleSave} className="w-full">
          Save Memory Settings
        </Button>
      </div>
    </div>
  );
}
