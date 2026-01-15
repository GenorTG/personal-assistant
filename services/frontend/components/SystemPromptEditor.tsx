'use client';

import { useState, useEffect } from 'react';
import { Save, RotateCcw, FileText, Loader } from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface SystemPromptEditorProps {
  onClose?: () => void;
}

export default function SystemPromptEditor({}: SystemPromptEditorProps) {
  const { showSuccess, showError, showConfirm } = useToast();
  const [prompt, setPrompt] = useState('');
  const [name, setName] = useState('');
  const [isDefault, setIsDefault] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [prompts, setPrompts] = useState<any[]>([]);
  const [selectedPromptId, setSelectedPromptId] = useState<string | null>(null);
  const [showPromptsList, setShowPromptsList] = useState(false);

  useEffect(() => {
    loadSystemPrompt();
    loadPromptsList();
  }, []);

  const loadSystemPrompt = async () => {
    try {
      setLoading(true);
      const data = (await api.getSystemPrompt()) as any;
      if (data) {
        setPrompt(data.content || '');
        setName(data.name || '');
        setIsDefault(data.is_default || false);
        setSelectedPromptId(data.id || null);
      }
    } catch (error) {
      console.error('Error loading system prompt:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadPromptsList = async () => {
    try {
      const data = (await api.listSystemPrompts()) as any;
      setPrompts(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Error loading prompts list:', error);
      setPrompts([]);
    }
  };

  const handleSave = async () => {
    if (!prompt.trim()) {
      showError('System prompt cannot be empty');
      return;
    }

    try {
      setSaving(true);
      if (selectedPromptId) {
        await api.updateSystemPrompt(selectedPromptId, prompt, name || undefined, isDefault);
      } else {
        const result = (await api.setSystemPrompt(prompt, name || undefined, isDefault)) as any;
        if (result?.id) {
          setSelectedPromptId(result.id);
        }
      }
      await loadPromptsList();
      showSuccess('System prompt saved successfully!');
    } catch (error) {
      console.error('Error saving system prompt:', error);
      showError('Failed to save system prompt');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    showConfirm('Reset to default system prompt? This will discard your changes.', () => {
      loadSystemPrompt();
    });
  };

  const handleLoadPrompt = async (promptId: string) => {
    try {
      const data = (await api.getSystemPrompt(promptId)) as any;
      if (data) {
        setPrompt(data.content || '');
        setName(data.name || '');
        setIsDefault(data.is_default || false);
        setSelectedPromptId(data.id);
        setShowPromptsList(false);
      }
    } catch (error) {
      console.error('Error loading prompt:', error);
      showError('Failed to load prompt');
    }
  };

  const handleDeletePrompt = async (promptId: string) => {
    showConfirm('Delete this system prompt?', async () => {
      try {
        await api.deleteSystemPrompt(promptId);
        await loadPromptsList();
        if (selectedPromptId === promptId) {
          await loadSystemPrompt();
        }
        showSuccess('Prompt deleted successfully');
      } catch (error) {
        console.error('Error deleting prompt:', error);
        showError('Failed to delete prompt');
      }
    });
  };

  const hasPrompts = prompts.length > 0;

  return (
    <div className="space-y-4 w-full max-w-full overflow-hidden">
      <div className="flex items-center justify-between gap-2 min-w-0 w-full max-w-full">
        <h3 className="font-semibold text-lg flex items-center gap-2 min-w-0 flex-shrink">
          <FileText size={20} className="flex-shrink-0" />
          <span className="truncate">System Prompt</span>
        </h3>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowPromptsList(!showPromptsList)}
          className="flex-shrink-0 whitespace-nowrap"
        >
          <span className={cn("hidden", showPromptsList && "block")}>Hide</span>
          <span className={cn("hidden", !showPromptsList && "block")}>Show</span> Prompts
        </Button>
      </div>

      <div className={cn("hidden", loading && "block")}>
        <div className="flex items-center justify-center py-8">
          <Skeleton className="h-4 w-48" />
        </div>
      </div>

      <div className={cn("hidden", !loading && "block space-y-4 w-full max-w-full overflow-hidden")}>
        <Card className={cn("hidden", showPromptsList && hasPrompts && "block w-full max-w-full overflow-hidden")}>
          <CardContent className="p-3 w-full max-w-full overflow-hidden">
            <div className="text-xs font-medium text-muted-foreground mb-2 w-full max-w-full truncate">Saved Prompts:</div>
            <ScrollArea className="max-h-48 w-full max-w-full">
              <div className="space-y-1 w-full max-w-full">
                {prompts.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center justify-between p-2 bg-background rounded border border-border hover:border-primary transition-colors w-full max-w-full min-w-0 overflow-hidden"
                  >
                    <div className="flex-1 min-w-0 overflow-hidden pr-2">
                      <div className="flex items-center gap-2 min-w-0 max-w-full">
                        <span className="font-medium text-sm truncate min-w-0 flex-1">{p.name || 'Unnamed Prompt'}</span>
                        <Badge variant="default" className={cn("hidden flex-shrink-0", p.is_default && "block")}>
                          Default
                        </Badge>
                      </div>
                      <div className="text-xs text-muted-foreground truncate mt-0.5 max-w-full">
                        {p.content.substring(0, 50)}...
                      </div>
                    </div>
                    <div className="flex gap-1 ml-2 flex-shrink-0">
                      <Button
                        onClick={() => handleLoadPrompt(p.id)}
                        variant="default"
                        size="sm"
                        className="text-xs whitespace-nowrap"
                      >
                        Load
                      </Button>
                      <Button
                        onClick={() => handleDeletePrompt(p.id)}
                        variant="destructive"
                        size="sm"
                        className="text-xs whitespace-nowrap"
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        <div>
          <Label className="block text-sm font-medium mb-1">Prompt Name (optional)</Label>
          <Input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., 'Default Assistant', 'Creative Writer'"
            className="w-full"
          />
        </div>

        <div>
          <Label className="block text-sm font-medium mb-1">
            System Prompt Content
            <span className="text-xs text-muted-foreground ml-2">({prompt.length} characters)</span>
          </Label>
          <Textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Enter system prompt here. This defines the AI's behavior, personality, and instructions."
            className="w-full font-mono text-sm"
            rows={12}
            style={{ resize: 'vertical' }}
          />
          <div className="mt-1 text-xs text-muted-foreground">
            The system prompt guides the AI's behavior. Be specific about the desired personality, tone, and
            capabilities.
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <Checkbox
            id="isDefault"
            checked={isDefault}
            onCheckedChange={(checked) => setIsDefault(checked === true)}
          />
          <Label htmlFor="isDefault" className="text-sm cursor-pointer">
            Set as default prompt (used for new conversations)
          </Label>
        </div>

        <Separator />

        <div className="flex gap-2">
          <Button
            onClick={handleSave}
            disabled={saving || !prompt.trim()}
            className="flex-1 flex items-center justify-center gap-2"
          >
            {saving ? (
              <>
                <Loader className="animate-spin" size={16} />
                Saving...
              </>
            ) : (
              <>
                <Save size={16} />
                Save Prompt
              </>
            )}
          </Button>
          <Button onClick={handleReset} variant="outline" className="flex items-center gap-2">
            <RotateCcw size={16} />
            Reset
          </Button>
        </div>
      </div>
    </div>
  );
}
