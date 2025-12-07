'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Loader, CheckCircle, XCircle, Volume2 } from 'lucide-react';
import { X } from 'lucide-react';
import { api } from '@/lib/api';
import { useSettings } from '@/contexts/SettingsContext';
import { saveSettingsLocally, loadSettingsLocally, clearPendingSync } from '@/lib/localSettings';
import { useToast } from '@/contexts/ToastContext';
import TTSSettings from './TTSSettings';
import STTSettings from './STTSettings';
import SystemPromptEditor from './SystemPromptEditor';
import ToolSettings from './ToolSettings';
import MemorySettings from './MemorySettings';
import SamplerSettings from './SamplerSettings';
import ResizableSidebar from './ResizableSidebar';

interface SettingsPanelProps {
  onClose: () => void;
  onWidthChange?: (width: number) => void;
}

type SettingsTab = 'ai' | 'tts' | 'stt' | 'character' | 'profile' | 'system-prompt' | 'tools' | 'memory';

// TTS Settings Component (deprecated - using separate component)
function _TTSSettingsSection() {
  const [backends, setBackends] = useState<any[]>([]);
  const [currentBackend, setCurrentBackend] = useState<any>(null);
  const [voices, setVoices] = useState<any[]>([]);
  const [options, setOptions] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [selectedBackend, setSelectedBackend] = useState<string>('');

  useEffect(() => {
    loadTTSInfo();
  }, []);

  const loadTTSInfo = async () => {
    try {
      setLoading(true);
      const backendsData = await api.getTTSBackends() as any;
      setBackends(backendsData.backends || []);
      
      // Find current backend
      const current = backendsData.backends?.find((b: any) => b.is_current);
      if (current) {
        setCurrentBackend(current);
        setSelectedBackend(current.name);
        await loadBackendDetails(current.name);
      }
    } catch (error) {
      console.error('Error loading TTS info:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadBackendDetails = async (backendName: string) => {
    try {
      const info = await api.getTTSBackendInfo(backendName) as any;
      setOptions(info.options || {});
      
      const voicesData = await api.getTTSVoices(backendName) as any;
      setVoices(voicesData.voices || []);
    } catch (error) {
      console.error('Error loading backend details:', error);
    }
  };

  const handleSwitchBackend = async (backendName: string) => {
    try {
      await api.switchTTSBackend(backendName);
      setSelectedBackend(backendName);
      await loadTTSInfo();
    } catch (error) {
      console.error('Error switching backend:', error);
      // Note: This is in a nested component, so we can't use useToast here
      // The TTSSettings component should handle its own toasts
    }
  };

  const handleUpdateOptions = async () => {
    if (!selectedBackend) return;
    try {
      await api.setTTSBackendOptions(selectedBackend, options);
      // Note: This is in a nested component, so we can't use useToast here
      // The TTSSettings component should handle its own toasts
      await loadBackendDetails(selectedBackend);
    } catch (error) {
      console.error('Error updating options:', error);
      // Note: This is in a nested component, so we can't use useToast here
      // The TTSSettings component should handle its own toasts
    }
  };

  const getStatusIcon = (status: string, isGenerating: boolean) => {
    if (isGenerating) {
      return <Loader size={16} className="animate-spin text-blue-500" />;
    }
    if (status === 'ready') {
      return <CheckCircle size={16} className="text-green-500" />;
    }
    return <XCircle size={16} className="text-red-500" />;
  };

  if (loading) {
    return (
      <div>
        <h3 className="font-semibold mb-4">TTS Settings</h3>
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  return (
    <div>
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        <Volume2 size={20} />
        TTS Settings
      </h3>
      <div className="space-y-4">
        {/* Backend Selection */}
        <div>
          <label className="block text-sm font-medium mb-2">TTS Backend</label>
          <div className="space-y-2">
            {backends.map((backend: any) => (
              <div
                key={backend.name}
                className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                  backend.is_current
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
                onClick={() => handleSwitchBackend(backend.name)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(backend.status, backend.is_generating)}
                    <span className="font-medium capitalize">{backend.name}</span>
                    {backend.is_current && (
                      <span className="text-xs bg-primary-500 text-white px-2 py-0.5 rounded">
                        Current
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500">
                    {backend.status === 'ready' && !backend.is_generating
                      ? 'Ready'
                      : backend.is_generating
                      ? 'Generating...'
                      : backend.status}
                  </div>
                </div>
                {backend.error_message && (
                  <p className="text-xs text-red-500 mt-1">{backend.error_message}</p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Current Backend Options */}
        {currentBackend && currentBackend.status === 'ready' && (
          <>
            {/* Voice Selection */}
            {voices.length > 0 && (
              <div>
                <label className="block text-sm font-medium mb-1">Voice</label>
                <select
                  value={options.voice || ''}
                  onChange={(e) => setOptions({ ...options, voice: e.target.value })}
                  className="input"
                >
                  <option value="">Default</option>
                  {voices.map((voice: any) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Backend-specific Options */}
            {currentBackend.name === 'chatterbox' && (
              <div className="space-y-2">
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Speed: {options.speed || 1.0}
                  </label>
                  <input
                    type="range"
                    min="0.5"
                    max="2.0"
                    step="0.1"
                    value={options.speed || 1.0}
                    onChange={(e) =>
                      setOptions({ ...options, speed: parseFloat(e.target.value) })
                    }
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Pitch: {options.pitch || 1.0}
                  </label>
                  <input
                    type="range"
                    min="0.5"
                    max="2.0"
                    step="0.1"
                    value={options.pitch || 1.0}
                    onChange={(e) =>
                      setOptions({ ...options, pitch: parseFloat(e.target.value) })
                    }
                    className="w-full"
                  />
                </div>
              </div>
            )}

            {currentBackend.name === 'kokoro' && (
              <div className="space-y-2">
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Speed: {options.speed || 1.0}
                  </label>
                  <input
                    type="range"
                    min="0.5"
                    max="2.0"
                    step="0.1"
                    value={options.speed || 1.0}
                    onChange={(e) =>
                      setOptions({ ...options, speed: parseFloat(e.target.value) })
                    }
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Temperature: {options.temperature || 0.7}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={options.temperature || 0.7}
                    onChange={(e) =>
                      setOptions({ ...options, temperature: parseFloat(e.target.value) })
                    }
                    className="w-full"
                  />
                </div>
              </div>
            )}

            {currentBackend.name === 'pyttsx3' && (
              <div className="space-y-2">
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Rate: {options.rate || 150}
                  </label>
                  <input
                    type="range"
                    min="50"
                    max="300"
                    step="10"
                    value={options.rate || 150}
                    onChange={(e) =>
                      setOptions({ ...options, rate: parseInt(e.target.value) })
                    }
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">
                    Volume: {options.volume || 0.9}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={options.volume || 0.9}
                    onChange={(e) =>
                      setOptions({ ...options, volume: parseFloat(e.target.value) })
                    }
                    className="w-full"
                  />
                </div>
              </div>
            )}

            <button
              onClick={handleUpdateOptions}
              className="btn-primary w-full mt-4"
            >
              Update TTS Options
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function SettingsPanel({ onClose, onWidthChange }: SettingsPanelProps) {
  const { settings: contextSettings, isLoading: settingsLoading } = useSettings();
  const { showWarning } = useToast();
  // Load from localStorage first for instant UI, then merge with backend settings
  const [settings, setSettings] = useState<any>(() => {
    const local = loadSettingsLocally();
    return contextSettings?.settings ? { ...contextSettings.settings, ...local } : local;
  });
  const [activeTab, setActiveTab] = useState<SettingsTab>('ai');
  const [llmServiceStatus, setLlmServiceStatus] = useState<any>(null);
  const syncTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Update local settings when context changes (but preserve local overrides)
  useEffect(() => {
    if (contextSettings?.settings) {
      const local = loadSettingsLocally();
      setSettings({ ...contextSettings.settings, ...local });
    }
  }, [contextSettings]);

  useEffect(() => {
    loadLLMServiceStatus();
  }, []);

  const loadLLMServiceStatus = async () => {
    try {
      const serviceStatus = await api.getLLMServiceStatus() as any;
      setLlmServiceStatus(serviceStatus);
    } catch (error) {
      console.error('Error loading LLM service status:', error);
    }
  };

  // Save settings with local storage first, then sync to backend
  const saveSettings = useCallback(async (settingsToSave: any) => {
    try {
      // Save to localStorage immediately for instant UI
      saveSettingsLocally({
        character_card: settingsToSave?.character_card,
        user_profile: settingsToSave?.user_profile,
        llm_endpoint_mode: settingsToSave?.llm_endpoint_mode,
        llm_remote_url: settingsToSave?.llm_remote_url,
        llm_remote_api_key: settingsToSave?.llm_remote_api_key,
        llm_remote_model: settingsToSave?.llm_remote_model,
      });
      
      // Sync to backend
      await api.updateSettings(settingsToSave);
      clearPendingSync();
      // Don't show alert - settings are already saved locally
    } catch (error) {
      console.error('Error saving settings:', error);
      showWarning('Error syncing settings to backend. Changes are saved locally.');
    }
  }, []);

  const handleSave = useCallback(async () => {
    await saveSettings(settings);
  }, [settings, saveSettings]);

  // Auto-save on change (debounced backend sync)
  const handleSettingsChange = useCallback((newSettings: any) => {
    setSettings(newSettings);
    
    // Save to localStorage immediately
    saveSettingsLocally({
      character_card: newSettings?.character_card,
      user_profile: newSettings?.user_profile,
      llm_endpoint_mode: newSettings?.llm_endpoint_mode,
      llm_remote_url: newSettings?.llm_remote_url,
      llm_remote_api_key: newSettings?.llm_remote_api_key,
      llm_remote_model: newSettings?.llm_remote_model,
    });
    
    // Schedule backend sync (debounced)
    if (syncTimeoutRef.current) {
      clearTimeout(syncTimeoutRef.current);
    }
    syncTimeoutRef.current = setTimeout(async () => {
      try {
        await api.updateSettings(newSettings);
        clearPendingSync();
      } catch (error) {
        console.error('Error auto-syncing settings:', error);
        // Don't alert - silent failure, settings are in localStorage
      }
    }, 1000);
  }, []);

  const tabs: { id: SettingsTab; label: string }[] = [
    { id: 'ai', label: 'AI' },
    { id: 'system-prompt', label: 'System Prompt' },
    { id: 'tools', label: 'Tools' },
    { id: 'memory', label: 'Memory' },
    { id: 'tts', label: 'TTS' },
    { id: 'stt', label: 'STT' },
    { id: 'character', label: 'Character' },
    { id: 'profile', label: 'Profile' },
  ];

  return (
    <ResizableSidebar
      initialWidth={384}
      minWidth={200}
      maxWidth={800}
      side="right"
      className="bg-white border-l border-gray-200 flex flex-col fixed right-0 z-40 shadow-sm outline-none focus:outline-none animate-slide-in-right"
      style={{
        height: 'calc(100vh - 73px)',
        top: '73px',
        maxHeight: 'calc(100vh - 73px)',
        overflow: 'hidden',
        position: 'fixed'
      }}
      onWidthChange={onWidthChange}
    >
      {/* Header */}
      <div className="p-4 border-b border-gray-200 flex-shrink-0">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-bold text-gray-800">Settings</h2>
          <button 
            onClick={onClose} 
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors"
            title="Close"
          >
          <X size={20} />
        </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 flex-shrink-0 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-600 hover:text-gray-800'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      
      {/* Content - Scrollable */}
      <div className="flex-1 overflow-y-auto p-4 relative min-h-0">
        {settingsLoading ? (
          <div className="flex items-center justify-center py-8">
            <p className="text-gray-500">Loading settings...</p>
          </div>
        ) : !settings && activeTab === 'ai' ? (
          <div className="flex items-center justify-center py-8">
            <p className="text-red-500">Failed to load settings</p>
          </div>
        ) : (
          <>
            {activeTab === 'ai' && (
              <div className="space-y-4">
                <h3 className="font-semibold mb-4">AI Sampler Settings</h3>
                
                {/* LLM Endpoint Mode Selection */}
                <div className="border-b border-gray-200 pb-4 mb-4">
                  <label className="block text-sm font-medium mb-2">LLM Endpoint</label>
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <input
                        type="radio"
                        id="endpoint-local"
                        name="llm-endpoint"
                        value="local"
                        checked={settings?.llm_endpoint_mode !== 'remote'}
                        onChange={() => {
                          const newSettings = { ...settings, llm_endpoint_mode: 'local' };
                          setSettings(newSettings);
                          saveSettings(newSettings);
                        }}
                        className="w-4 h-4 text-primary-600 border-gray-300 focus:ring-primary-500"
                      />
                      <label htmlFor="endpoint-local" className="text-sm text-gray-700 cursor-pointer">
                        Local (llama-cpp-python server)
                      </label>
                    </div>
                    <div className="flex items-center gap-3">
                      <input
                        type="radio"
                        id="endpoint-remote"
                        name="llm-endpoint"
                        value="remote"
                        checked={settings?.llm_endpoint_mode === 'remote'}
                        onChange={() => {
                          const newSettings = { ...settings, llm_endpoint_mode: 'remote' };
                          setSettings(newSettings);
                          saveSettings(newSettings);
                        }}
                        className="w-4 h-4 text-primary-600 border-gray-300 focus:ring-primary-500"
                      />
                      <label htmlFor="endpoint-remote" className="text-sm text-gray-700 cursor-pointer">
                        Remote (OpenAI-compatible API)
                      </label>
                    </div>
                  </div>
                  
                  {/* Remote Endpoint Configuration */}
                  {settings?.llm_endpoint_mode === 'remote' && (
                    <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-200 space-y-3">
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1.5">
                          API Endpoint URL
                        </label>
                        <input
                          type="text"
                          value={settings?.llm_remote_url || ''}
                          onChange={(e) => {
                            const newSettings = { ...settings, llm_remote_url: e.target.value };
                            setSettings(newSettings);
                            saveSettings(newSettings);
                          }}
                          placeholder="https://api.openai.com/v1"
                          className="input w-full text-sm"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          Full URL to OpenAI-compatible endpoint (e.g., https://api.openai.com/v1 or http://localhost:1234/v1)
                        </p>
                      </div>
                      
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1.5">
                          API Key (optional)
                        </label>
                        <input
                          type="password"
                          value={settings?.llm_remote_api_key || ''}
                          onChange={(e) => {
                            const newSettings = { ...settings, llm_remote_api_key: e.target.value };
                            setSettings(newSettings);
                            saveSettings(newSettings);
                          }}
                          placeholder="sk-..."
                          className="input w-full text-sm"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          API key for authentication (required for OpenAI, optional for self-hosted)
                        </p>
                      </div>
                      
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1.5">
                          Model Name/ID
                        </label>
                        <input
                          type="text"
                          value={settings?.llm_remote_model || ''}
                          onChange={(e) => {
                            const newSettings = { ...settings, llm_remote_model: e.target.value };
                            setSettings(newSettings);
                            saveSettings(newSettings);
                          }}
                          placeholder="gpt-4, gpt-3.5-turbo, or model name"
                          className="input w-full text-sm"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          Model identifier to use with the remote endpoint (leave empty to use model from request)
                        </p>
                      </div>
                    </div>
                  )}
                  
                  {/* Local LLM Service Status */}
                  {settings?.llm_endpoint_mode !== 'remote' && (
                    <div className="mt-4 p-3 border rounded-lg bg-gray-50">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">llama-cpp-python Server</span>
                        <div className="text-sm">
                          {llmServiceStatus?.running ? (
                            <span className="text-green-600 font-medium">● Running</span>
                          ) : (
                            <span className="text-gray-400">○ Stopped</span>
                          )}
                        </div>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Port 8001 - Load a model to start</p>
                    </div>
                  )}
                </div>

                {/* Full Sampler Settings Component */}
                <SamplerSettings />
              </div>
            )}

            {activeTab === 'system-prompt' && <SystemPromptEditor />}

            {activeTab === 'tools' && <ToolSettings />}

            {activeTab === 'memory' && <MemorySettings />}

            {activeTab === 'tts' && <TTSSettings />}

            {activeTab === 'stt' && <STTSettings />}

            {activeTab === 'character' && (
              <div className="space-y-4">
          <h3 className="font-semibold mb-4">Character Card</h3>
            <div>
              <label className="block text-sm font-medium mb-1">Name</label>
              <input
                type="text"
                value={settings?.character_card?.name || ''}
                onChange={(e) =>
                  handleSettingsChange({
                    ...settings,
                    character_card: {
                      ...settings?.character_card,
                      name: e.target.value,
                    },
                  })
                }
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Personality</label>
              <textarea
                value={settings?.character_card?.personality || ''}
                onChange={(e) =>
                  handleSettingsChange({
                    ...settings,
                    character_card: {
                      ...settings?.character_card,
                      personality: e.target.value,
                    },
                  })
                }
                className="input"
                rows={4}
              />
            </div>
          </div>
            )}

            {activeTab === 'profile' && (
              <div className="space-y-4">
          <h3 className="font-semibold mb-4">Your Profile</h3>
            <div>
              <label className="block text-sm font-medium mb-1">Your Name</label>
              <input
                type="text"
                value={settings?.user_profile?.name || ''}
                onChange={(e) =>
                  handleSettingsChange({
                    ...settings,
                    user_profile: {
                      ...settings?.user_profile,
                      name: e.target.value,
                    },
                  })
                }
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">About You</label>
              <textarea
                value={settings?.user_profile?.about || ''}
                onChange={(e) =>
                  handleSettingsChange({
                    ...settings,
                    user_profile: {
                      ...settings?.user_profile,
                      about: e.target.value,
                    },
                  })
                }
                className="input"
                rows={3}
              />
            </div>
          </div>
            )}
          </>
        )}
      </div>
      
      {/* Fixed bottom padding */}
      <div className="h-16 flex-shrink-0 -mx-4 px-4" style={{
        background: 'linear-gradient(to bottom, rgba(59, 130, 246, 0.08), rgba(99, 102, 241, 0.12), rgba(139, 92, 246, 0.16), rgba(168, 85, 247, 0.2))'
      }}></div>
      
      {/* Footer - only for tabs without their own save button */}
      {!settingsLoading && settings && (activeTab === 'character' || activeTab === 'profile') && (
        <div className="p-4 border-t border-gray-200 flex-shrink-0 bg-gray-50">
          <button 
            onClick={handleSave} 
            className="btn-primary w-full"
            disabled={settingsLoading}
          >
            {activeTab === 'character' ? 'Save Character' : 'Save User Profile'}
          </button>
        </div>
      )}
    </ResizableSidebar>
  );
}

