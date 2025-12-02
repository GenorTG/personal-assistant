'use client';

import { useState, useEffect } from 'react';
import { Save, RotateCcw, FileText, Loader } from 'lucide-react';
import { api } from '@/lib/api';

interface SystemPromptEditorProps {
  onClose?: () => void;
}

export default function SystemPromptEditor({ onClose }: SystemPromptEditorProps) {
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
      const data = await api.getSystemPrompt() as any;
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
      const data = await api.listSystemPrompts() as any;
      setPrompts(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Error loading prompts list:', error);
      setPrompts([]);
    }
  };

  const handleSave = async () => {
    if (!prompt.trim()) {
      alert('System prompt cannot be empty');
      return;
    }

    try {
      setSaving(true);
      if (selectedPromptId) {
        await api.updateSystemPrompt(selectedPromptId, prompt, name || undefined, isDefault);
      } else {
        const result = await api.setSystemPrompt(prompt, name || undefined, isDefault) as any;
        if (result?.id) {
          setSelectedPromptId(result.id);
        }
      }
      await loadPromptsList();
      alert('System prompt saved successfully!');
    } catch (error) {
      console.error('Error saving system prompt:', error);
      alert('Failed to save system prompt');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (confirm('Reset to default system prompt? This will discard your changes.')) {
      loadSystemPrompt();
    }
  };

  const handleLoadPrompt = async (promptId: string) => {
    try {
      const data = await api.getSystemPrompt(promptId) as any;
      if (data) {
        setPrompt(data.content || '');
        setName(data.name || '');
        setIsDefault(data.is_default || false);
        setSelectedPromptId(data.id);
        setShowPromptsList(false);
      }
    } catch (error) {
      console.error('Error loading prompt:', error);
      alert('Failed to load prompt');
    }
  };

  const handleDeletePrompt = async (promptId: string) => {
    if (!confirm('Delete this system prompt?')) return;
    
    try {
      await api.deleteSystemPrompt(promptId);
      await loadPromptsList();
      if (selectedPromptId === promptId) {
        await loadSystemPrompt();
      }
      alert('Prompt deleted successfully');
    } catch (error) {
      console.error('Error deleting prompt:', error);
      alert('Failed to delete prompt');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader className="animate-spin text-blue-500" size={24} />
        <span className="ml-2 text-gray-600">Loading system prompt...</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-lg flex items-center gap-2">
          <FileText size={20} />
          System Prompt
        </h3>
        <div className="flex gap-2">
          <button
            onClick={() => setShowPromptsList(!showPromptsList)}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            {showPromptsList ? 'Hide' : 'Show'} Prompts
          </button>
        </div>
      </div>

      {showPromptsList && prompts.length > 0 && (
        <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 max-h-48 overflow-y-auto">
          <div className="text-xs font-medium text-gray-600 mb-2">Saved Prompts:</div>
          <div className="space-y-1">
            {prompts.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between p-2 bg-white rounded border border-gray-200 hover:border-blue-300 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm truncate">
                      {p.name || 'Unnamed Prompt'}
                    </span>
                    {p.is_default && (
                      <span className="text-xs bg-blue-500 text-white px-1.5 py-0.5 rounded">
                        Default
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 truncate mt-0.5">
                    {p.content.substring(0, 50)}...
                  </div>
                </div>
                <div className="flex gap-1 ml-2">
                  <button
                    onClick={() => handleLoadPrompt(p.id)}
                    className="px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
                  >
                    Load
                  </button>
                  <button
                    onClick={() => handleDeletePrompt(p.id)}
                    className="px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium mb-1">Prompt Name (optional)</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g., 'Default Assistant', 'Creative Writer'"
          className="input w-full"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">
          System Prompt Content
          <span className="text-xs text-gray-500 ml-2">
            ({prompt.length} characters)
          </span>
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter system prompt here. This defines the AI's behavior, personality, and instructions."
          className="input w-full font-mono text-sm"
          rows={12}
          style={{ resize: 'vertical' }}
        />
        <div className="mt-1 text-xs text-gray-500">
          The system prompt guides the AI's behavior. Be specific about the desired personality, tone, and capabilities.
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="isDefault"
          checked={isDefault}
          onChange={(e) => setIsDefault(e.target.checked)}
          className="w-4 h-4"
        />
        <label htmlFor="isDefault" className="text-sm text-gray-700 cursor-pointer">
          Set as default prompt (used for new conversations)
        </label>
      </div>

      <div className="flex gap-2 pt-2 border-t border-gray-200">
        <button
          onClick={handleSave}
          disabled={saving || !prompt.trim()}
          className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
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
        </button>
        <button
          onClick={handleReset}
          className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors flex items-center gap-2"
        >
          <RotateCcw size={16} />
          Reset
        </button>
      </div>
    </div>
  );
}

