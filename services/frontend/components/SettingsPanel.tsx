'use client';

import { useState, useEffect } from 'react';
import { Loader, CheckCircle, XCircle, Volume2 } from 'lucide-react';
import { X } from 'lucide-react';
import { api } from '@/lib/api';
import { useSettings } from '@/contexts/SettingsContext';
import TTSSettings from './TTSSettings';
import STTSettings from './STTSettings';
import { ServiceStatusPanel } from './ServiceStatusPanel';
import SystemPromptEditor from './SystemPromptEditor';
import ToolSettings from './ToolSettings';
import MemorySettings from './MemorySettings';
import SamplerSettings from './SamplerSettings';

interface SettingsPanelProps {
  onClose: () => void;
}

type SettingsTab = 'ai' | 'tts' | 'stt' | 'character' | 'profile' | 'system-prompt' | 'tools' | 'memory';

// TTS Settings Component (deprecated - using separate component)
function TTSSettingsSection() {
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
      alert('Failed to switch TTS backend');
    }
  };

  const handleUpdateOptions = async () => {
    if (!selectedBackend) return;
    try {
      await api.setTTSBackendOptions(selectedBackend, options);
      alert('TTS options updated!');
      await loadBackendDetails(selectedBackend);
    } catch (error) {
      console.error('Error updating options:', error);
      alert('Failed to update TTS options');
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

export default function SettingsPanel({ onClose }: SettingsPanelProps) {
  const { settings: contextSettings, isLoading: settingsLoading, refresh: refreshSettings } = useSettings();
  const [settings, setSettings] = useState<any>(contextSettings?.settings || null);
  const [activeTab, setActiveTab] = useState<SettingsTab>('ai');
  const [llmServiceStatus, setLlmServiceStatus] = useState<any>(null);
  const [llmServiceLoading, setLlmServiceLoading] = useState(false);

  // Update local settings when context changes
  useEffect(() => {
    if (contextSettings?.settings) {
      setSettings(contextSettings.settings);
    }
  }, [contextSettings]);

  useEffect(() => {
    loadLLMServiceStatus();
  }, []);

  const loadLLMServiceStatus = async () => {
    try {
      setLlmServiceLoading(true);
      const serviceStatus = await api.getLLMServiceStatus() as any;
      setLlmServiceStatus(serviceStatus);
    } catch (error) {
      console.error('Error loading LLM service status:', error);
    } finally {
      setLlmServiceLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      await api.updateSettings(settings);
      alert('Settings saved!');
    } catch (error) {
      console.error('Error saving settings:', error);
      alert('Error saving settings');
    }
  };

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
    <div className="w-96 bg-white border-l border-gray-200 flex flex-col fixed right-0 z-40 shadow-2xl" style={{ height: 'calc(100vh - 73px)', top: '73px' }}>
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
      
      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
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
                
                {/* LLM Service Status */}
                <div className="border-b border-gray-200 pb-4 mb-4">
                  <label className="block text-sm font-medium mb-2">LLM Service Status</label>
                  <div className="p-3 border rounded-lg bg-gray-50">
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
                  setSettings({
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
                  setSettings({
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
                  setSettings({
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
                  setSettings({
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
    </div>
  );
}

