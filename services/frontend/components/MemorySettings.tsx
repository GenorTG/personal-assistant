'use client';

import { useState, useEffect } from 'react';
import { Database, Brain, Sliders, Save, Eye } from 'lucide-react';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';

export default function MemorySettings() {
  const { showSuccess, showError } = useToast();
  const [similarityThreshold, setSimilarityThreshold] = useState(0.7);
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(true);
  
  // Vector Memory Settings
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
      // Load memory settings (retrieval parameters)
      const memorySettings = await api.getMemorySettings() as any;
      if (memorySettings) {
        setSimilarityThreshold(memorySettings.similarity_threshold ?? 0.7);
        setTopK(memorySettings.top_k ?? 5);
      }
      
      // Load vector memory settings
      const vectorSettings = await api.getVectorMemorySettings() as any;
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
      // Save memory settings
      await api.updateMemorySettings({
        similarity_threshold: similarityThreshold,
        top_k: topK
      });
      
      // Save vector memory settings
      await api.setVectorMemorySettings({
        vector_memory_enabled: vectorMemoryEnabled,
        vector_memory_save_enabled: vectorMemorySaveEnabled,
        vector_memory_read_enabled: vectorMemoryReadEnabled,
        vector_memory_apply_to_all: vectorMemoryApplyToAll
      });
      
      showSuccess('Memory settings saved successfully!');
    } catch (error) {
      console.error('Error saving memory settings:', error);
      showError('Failed to save memory settings');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <p className="text-gray-500">Loading memory settings...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={20} />
        <h3 className="font-semibold text-lg">Memory & Context Settings</h3>
      </div>

      <div className="space-y-4">
        {/* Automatic Vector Memory Section */}
        <div className="pt-4 border-t border-gray-200">
          <h4 className="font-semibold mb-3 flex items-center gap-2">
            <Database size={18} />
            Automatic Vector Memory
          </h4>
          <p className="text-xs text-gray-500 mb-3">
            Controls automatic context saving and retrieval. When enabled, messages are automatically saved to vector memory and relevant context is retrieved for conversations.
          </p>
          
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 border rounded-lg">
              <div>
                <label className="font-medium text-sm">Enable Vector Memory</label>
                <p className="text-xs text-gray-500">Master switch for vector memory system</p>
              </div>
              <input
                type="checkbox"
                checked={vectorMemoryEnabled}
                onChange={(e) => setVectorMemoryEnabled(e.target.checked)}
                className="w-5 h-5"
              />
            </div>
            
            {vectorMemoryEnabled && (
              <>
                <div className="flex items-center justify-between p-3 border rounded-lg">
                  <div>
                    <label className="font-medium text-sm flex items-center gap-2">
                      <Save size={16} />
                      Save New Information
                    </label>
                    <p className="text-xs text-gray-500">Store new messages in vector memory</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={vectorMemorySaveEnabled}
                    onChange={(e) => setVectorMemorySaveEnabled(e.target.checked)}
                    className="w-5 h-5"
                  />
                </div>
                
                <div className="flex items-center justify-between p-3 border rounded-lg">
                  <div>
                    <label className="font-medium text-sm flex items-center gap-2">
                      <Eye size={16} />
                      Read/Retrieve Information
                    </label>
                    <p className="text-xs text-gray-500">Use stored information for context</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={vectorMemoryReadEnabled}
                    onChange={(e) => setVectorMemoryReadEnabled(e.target.checked)}
                    className="w-5 h-5"
                  />
                </div>
                
                <div className="flex items-center justify-between p-3 border rounded-lg bg-yellow-50">
                  <div>
                    <label className="font-medium text-sm">Apply to All Conversations</label>
                    <p className="text-xs text-gray-500">Override per-conversation settings</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={vectorMemoryApplyToAll}
                    onChange={(e) => setVectorMemoryApplyToAll(e.target.checked)}
                    className="w-5 h-5"
                  />
                </div>
              </>
            )}
          </div>
        </div>

        {/* Retrieval Parameters Section */}
        <div className="pt-4 border-t border-gray-200">
          <h4 className="font-semibold mb-3 flex items-center gap-2">
            <Sliders size={18} />
            Retrieval Parameters
          </h4>
          <p className="text-xs text-gray-500 mb-3">
            These settings control HOW vector memory retrieval works (when automatic retrieval is enabled).
          </p>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">
                Similarity Threshold: {similarityThreshold.toFixed(2)}
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={similarityThreshold}
                onChange={(e) => setSimilarityThreshold(parseFloat(e.target.value))}
                className="w-full"
              />
              <p className="text-xs text-gray-500 mt-1">
                Minimum similarity score (0-1) for context retrieval. Higher values = more relevant but fewer results.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">
                Top-K Results: {topK}
              </label>
              <input
                type="range"
                min="1"
                max="20"
                step="1"
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="w-full"
              />
              <p className="text-xs text-gray-500 mt-1">
                Maximum number of relevant past messages to retrieve for context.
              </p>
            </div>
          </div>
        </div>

        {/* Memory Tool Info Section */}
        <div className="pt-4 border-t border-gray-200">
          <h4 className="font-semibold mb-3 flex items-center gap-2">
            <Brain size={18} />
            Memory Tool (Explicit Memory)
          </h4>
          <p className="text-xs text-gray-500 mb-2">
            The LLM can explicitly save and recall memories using the "memory" tool. This is separate from automatic vector memory and allows the model to decide when to store important information.
          </p>
          <p className="text-xs text-gray-400 italic">
            No settings needed - the tool is automatically available when tool calling is enabled.
          </p>
        </div>

        <div className="pt-4 border-t border-gray-200">
          <button
            onClick={handleSave}
            className="btn-primary w-full"
          >
            Save Memory Settings
          </button>
        </div>
      </div>
    </div>
  );
}

