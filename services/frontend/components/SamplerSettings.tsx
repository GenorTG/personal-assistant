'use client';

import { useState, useCallback } from 'react';
import { Thermometer, Repeat, Sparkles, Dice1, Settings2, RotateCcw, Save, ChevronDown, ChevronUp } from 'lucide-react';
import { useSamplerSettings, SamplerSettingsData, DEFAULT_SETTINGS } from '@/contexts/SamplerSettingsContext';
import { useToast } from '@/contexts/ToastContext';

const PRESETS = {
  default: { ...DEFAULT_SETTINGS },
  creative: {
    ...DEFAULT_SETTINGS,
    temperature: 1.0,
    top_p: 0.95,
    top_k: 100,
    repeat_penalty: 1.15,
    typical_p: 0.9,
  },
  precise: {
    ...DEFAULT_SETTINGS,
    temperature: 0.3,
    top_p: 0.8,
    top_k: 20,
    repeat_penalty: 1.05,
  },
  deterministic: {
    ...DEFAULT_SETTINGS,
    temperature: 0.0,
    top_p: 1.0,
    top_k: 1,
    repeat_penalty: 1.0,
  },
  mirostat: {
    ...DEFAULT_SETTINGS,
    temperature: 0.8,
    mirostat_mode: 2,
    mirostat_tau: 5.0,
    mirostat_eta: 0.1,
  },
};

interface Props {
  onSettingsChange?: (settings: SamplerSettingsData) => void;
}

export default function SamplerSettings({ onSettingsChange }: Props) {
  const { settings, updateSettings, resetToDefaults, saveToBackend, isLoading } = useSamplerSettings();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleChange = useCallback((key: keyof SamplerSettingsData, value: number) => {
    updateSettings({ [key]: value });
    onSettingsChange?.({ ...settings, [key]: value });
  }, [settings, updateSettings, onSettingsChange]);

  const handlePreset = (presetName: keyof typeof PRESETS) => {
    const preset = PRESETS[presetName];
    updateSettings(preset);
    onSettingsChange?.(preset);
  };

  const handleReset = () => {
    resetToDefaults();
    onSettingsChange?.(DEFAULT_SETTINGS);
  };

  const { showError } = useToast();
  
  const handleSave = async () => {
    setSaving(true);
    try {
      await saveToBackend();
    } catch (error) {
      console.error('Error saving settings:', error);
      showError('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="p-4 text-center text-gray-500">
        Loading sampler settings...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Presets */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Quick Presets</label>
        <div className="flex flex-wrap gap-2">
          {Object.keys(PRESETS).map((preset) => (
            <button
              key={preset}
              onClick={() => handlePreset(preset as keyof typeof PRESETS)}
              className="px-3 py-1.5 text-sm rounded border border-gray-300 hover:border-primary-400 hover:bg-primary-50 transition-colors capitalize"
            >
              {preset}
            </button>
          ))}
        </div>
      </div>

      {/* Basic Settings */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <Thermometer size={16} />
          Basic Sampling
        </h3>
        
        {/* Temperature */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm text-gray-600">Temperature</label>
            <span className="text-sm font-medium text-gray-900">{settings.temperature.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={2}
            step={0.05}
            value={settings.temperature}
            onChange={(e) => handleChange('temperature', parseFloat(e.target.value))}
            className="w-full accent-primary-600"
          />
          <p className="text-xs text-gray-500 mt-1">Controls randomness. 0 = deterministic, 2 = very random</p>
        </div>

        {/* Top P */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm text-gray-600">Top P (Nucleus)</label>
            <span className="text-sm font-medium text-gray-900">{settings.top_p.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={settings.top_p}
            onChange={(e) => handleChange('top_p', parseFloat(e.target.value))}
            className="w-full accent-primary-600"
          />
          <p className="text-xs text-gray-500 mt-1">Only consider tokens with cumulative probability above this</p>
        </div>

        {/* Top K */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm text-gray-600">Top K</label>
            <span className="text-sm font-medium text-gray-900">{settings.top_k}</span>
          </div>
          <input
            type="range"
            min={0}
            max={200}
            step={1}
            value={settings.top_k}
            onChange={(e) => handleChange('top_k', parseInt(e.target.value))}
            className="w-full accent-primary-600"
          />
          <p className="text-xs text-gray-500 mt-1">Only consider top K most likely tokens (0 = disabled)</p>
        </div>

        {/* Min P */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm text-gray-600">Min P</label>
            <span className="text-sm font-medium text-gray-900">{settings.min_p.toFixed(3)}</span>
          </div>
          <input
            type="range"
            min={0}
            max={0.5}
            step={0.01}
            value={settings.min_p}
            onChange={(e) => handleChange('min_p', parseFloat(e.target.value))}
            className="w-full accent-primary-600"
          />
          <p className="text-xs text-gray-500 mt-1">Minimum probability threshold (0 = disabled)</p>
        </div>

        {/* Max Tokens */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm text-gray-600">Max Tokens</label>
            <span className="text-sm font-medium text-gray-900">{settings.max_tokens}</span>
          </div>
          <input
            type="range"
            min={64}
            max={4096}
            step={64}
            value={settings.max_tokens}
            onChange={(e) => handleChange('max_tokens', parseInt(e.target.value))}
            className="w-full accent-primary-600"
          />
          <p className="text-xs text-gray-500 mt-1">Maximum number of tokens to generate</p>
        </div>
      </div>

      {/* Repetition Control */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <Repeat size={16} />
          Repetition Control
        </h3>

        {/* Repeat Penalty */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm text-gray-600">Repeat Penalty</label>
            <span className="text-sm font-medium text-gray-900">{settings.repeat_penalty.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={1}
            max={2}
            step={0.05}
            value={settings.repeat_penalty}
            onChange={(e) => handleChange('repeat_penalty', parseFloat(e.target.value))}
            className="w-full accent-primary-600"
          />
          <p className="text-xs text-gray-500 mt-1">Penalize repeated tokens (1.0 = disabled)</p>
        </div>

        {/* Presence Penalty */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm text-gray-600">Presence Penalty</label>
            <span className="text-sm font-medium text-gray-900">{settings.presence_penalty.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={-2}
            max={2}
            step={0.1}
            value={settings.presence_penalty}
            onChange={(e) => handleChange('presence_penalty', parseFloat(e.target.value))}
            className="w-full accent-primary-600"
          />
          <p className="text-xs text-gray-500 mt-1">OpenAI-style: penalize tokens that appear at all</p>
        </div>

        {/* Frequency Penalty */}
        <div>
          <div className="flex justify-between mb-1">
            <label className="text-sm text-gray-600">Frequency Penalty</label>
            <span className="text-sm font-medium text-gray-900">{settings.frequency_penalty.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={-2}
            max={2}
            step={0.1}
            value={settings.frequency_penalty}
            onChange={(e) => handleChange('frequency_penalty', parseFloat(e.target.value))}
            className="w-full accent-primary-600"
          />
          <p className="text-xs text-gray-500 mt-1">OpenAI-style: penalize based on frequency</p>
        </div>
      </div>

      {/* Advanced Settings Toggle */}
      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 w-full justify-between py-2 border-t border-gray-200"
      >
        <span className="flex items-center gap-2">
          <Settings2 size={16} />
          Advanced Sampling Settings
        </span>
        {showAdvanced ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {/* Advanced Settings */}
      {showAdvanced && (
        <div className="space-y-6 pt-2">
          {/* Advanced Sampling */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Sparkles size={16} />
              Advanced Sampling
            </h3>

            {/* Typical P */}
            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm text-gray-600">Typical P</label>
                <span className="text-sm font-medium text-gray-900">{settings.typical_p.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={settings.typical_p}
                onChange={(e) => handleChange('typical_p', parseFloat(e.target.value))}
                className="w-full accent-primary-600"
              />
              <p className="text-xs text-gray-500 mt-1">Typical sampling (1.0 = disabled)</p>
            </div>

            {/* TFS Z */}
            <div>
              <div className="flex justify-between mb-1">
                <label className="text-sm text-gray-600">Tail Free Sampling (Z)</label>
                <span className="text-sm font-medium text-gray-900">{settings.tfs_z.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={settings.tfs_z}
                onChange={(e) => handleChange('tfs_z', parseFloat(e.target.value))}
                className="w-full accent-primary-600"
              />
              <p className="text-xs text-gray-500 mt-1">Remove unlikely tokens (1.0 = disabled)</p>
            </div>
          </div>

          {/* Mirostat */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Dice1 size={16} />
              Mirostat (Entropy-based Sampling)
            </h3>

            {/* Mirostat Mode */}
            <div>
              <label className="text-sm text-gray-600 block mb-2">Mirostat Mode</label>
              <div className="flex gap-2">
                {[0, 1, 2].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => handleChange('mirostat_mode', mode)}
                    className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                      settings.mirostat_mode === mode
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {mode === 0 ? 'Off' : `v${mode}`}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">Mirostat maintains consistent perplexity</p>
            </div>

            {settings.mirostat_mode > 0 && (
              <>
                {/* Mirostat Tau */}
                <div>
                  <div className="flex justify-between mb-1">
                    <label className="text-sm text-gray-600">Target Entropy (Tau)</label>
                    <span className="text-sm font-medium text-gray-900">{settings.mirostat_tau.toFixed(1)}</span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={10}
                    step={0.5}
                    value={settings.mirostat_tau}
                    onChange={(e) => handleChange('mirostat_tau', parseFloat(e.target.value))}
                    className="w-full accent-primary-600"
                  />
                  <p className="text-xs text-gray-500 mt-1">Higher = more random, Lower = more focused</p>
                </div>

                {/* Mirostat Eta */}
                <div>
                  <div className="flex justify-between mb-1">
                    <label className="text-sm text-gray-600">Learning Rate (Eta)</label>
                    <span className="text-sm font-medium text-gray-900">{settings.mirostat_eta.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={settings.mirostat_eta}
                    onChange={(e) => handleChange('mirostat_eta', parseFloat(e.target.value))}
                    className="w-full accent-primary-600"
                  />
                  <p className="text-xs text-gray-500 mt-1">How quickly Mirostat adapts</p>
                </div>
              </>
            )}
          </div>

          {/* Smooth Sampling */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <Settings2 size={16} />
                Smooth Sampling
              </h3>
              {(settings.smoothing_factor || 0) > 0 ? (
                <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded font-medium">
                  Enabled
                </span>
              ) : (
                <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded font-medium">
                  Disabled
                </span>
              )}
            </div>
            
            {(settings.smoothing_factor || 0) > 0 && (
              <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
                <p className="text-xs text-yellow-800">
                  <strong>Note:</strong> This is an approximation via temperature/top_p adjustments. 
                  If results are poor, set Smoothing Factor to 0.0 to disable. 
                  In SillyTavern/oobabooga, 0.23 typically produces excellent results.
                </p>
              </div>
            )}
            
            <div>
              <label className="text-sm text-gray-600 block mb-2">
                Smoothing Factor: {((settings.smoothing_factor || 0) * 100).toFixed(0)}%
                {(settings.smoothing_factor || 0) === 0 && (
                  <span className="ml-2 text-gray-400 text-xs">(Disabled)</span>
                )}
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={settings.smoothing_factor || 0}
                onChange={(e) => {
                  const value = parseFloat(e.target.value);
                  updateSettings({ smoothing_factor: value });
                  onSettingsChange?.({ ...settings, smoothing_factor: value });
                }}
                className={`w-full ${(settings.smoothing_factor || 0) === 0 ? 'accent-gray-400' : 'accent-primary-600'}`}
              />
              <p className="text-xs text-gray-500 mt-1">
                Allows quadratic/cubic transformations to adjust the distribution. Lower values will be more creative, usually between 0.2-0.3 is the sweetspot (assuming curve = 1.0). 
                <strong className="text-gray-700"> Set to 0.0 to disable.</strong>
              </p>
            </div>
            <div>
              <label className="text-sm text-gray-600 block mb-2">
                Smoothing Curve: {((settings.smoothing_curve || 1.0) * 10).toFixed(1)} ({(settings.smoothing_curve || 1.0).toFixed(2)})
              </label>
              <input
                type="range"
                min={1.0}
                max={3.0}
                step={0.1}
                value={settings.smoothing_curve || 1.0}
                onChange={(e) => {
                  const value = parseFloat(e.target.value);
                  updateSettings({ smoothing_curve: value });
                  onSettingsChange?.({ ...settings, smoothing_curve: value });
                }}
                className={`w-full ${(settings.smoothing_factor || 0) === 0 ? 'accent-gray-400 opacity-50' : 'accent-primary-600'}`}
                disabled={(settings.smoothing_factor || 0) === 0}
              />
              <p className="text-xs text-gray-500 mt-1">
                Higher values make the curve steeper, which punishes low probability choices more aggressively. 1.0 = equivalent to only using smoothing factor.
              </p>
            </div>
          </div>

          {/* Stop Strings */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Settings2 size={16} />
              Stop Strings
            </h3>
            <div>
              <label className="text-sm text-gray-600 block mb-2">
                Stop Sequences (one per line, supports {'{{user}}'} and {'{{char}}'} template variables)
              </label>
              <textarea
                value={(settings.stop || []).join('\n')}
                onChange={(e) => {
                  const lines = e.target.value.split('\n').filter(line => line.trim() !== '');
                  updateSettings({ stop: lines.length > 0 ? lines : undefined });
                  onSettingsChange?.({ ...settings, stop: lines.length > 0 ? lines : undefined });
                }}
                placeholder={`Example:\n*{{user}}\n{{user}}\n{{user}}:`}
                className="w-full min-h-[100px] px-3 py-2 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent font-mono"
                rows={4}
              />
              <p className="text-xs text-gray-500 mt-1">
                Generation will stop when any of these sequences are encountered. Use {'{{user}}'} and {'{{char}}'} for template variables.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex justify-between pt-4 border-t border-gray-200">
        <button
          onClick={handleReset}
          className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:text-gray-900 transition-colors"
        >
          <RotateCcw size={16} />
          Reset to Default
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2 bg-primary-600 text-white rounded font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
        >
          <Save size={16} />
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}

