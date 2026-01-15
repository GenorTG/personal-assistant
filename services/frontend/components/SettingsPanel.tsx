'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Brain,
  Volume2,
  Database,
  Zap,
  User,
  FileText,
  Settings as SettingsIcon,
  Package,
} from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import { saveSettingsLocally, loadSettingsLocally, clearPendingSync } from '@/lib/localSettings';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import AISettings from './settings/AISettings';
import VoiceSettings from './settings/VoiceSettings';
import ModelManagement from './settings/ModelManagement';
import MemorySettings from './MemorySettings';
import ToolSettings from './ToolSettings';
import SystemPromptEditor from './SystemPromptEditor';
import CharacterSettings from './settings/CharacterSettings';
import ProfileSettings from './settings/ProfileSettings';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import type { AppSettings } from '@/types/settings';

interface SettingsPanelProps {
  onClose: () => void;
  onWidthChange?: (width: number) => void;
}

type SettingsSection = 'ai' | 'voice' | 'voice-models' | 'memory' | 'tools' | 'character' | 'profile' | 'system-prompt';

interface SectionConfig {
  id: SettingsSection;
  label: string;
  icon: typeof Brain;
  description: string;
  parent?: SettingsSection;
}

const SECTIONS: SectionConfig[] = [
  { id: 'ai', label: 'AI & LLM', icon: Brain, description: 'LLM model selection and sampler settings' },
  { 
    id: 'voice', 
    label: 'Voice Services', 
    icon: Volume2, 
    description: 'STT and TTS configuration',
  },
  { 
    id: 'voice-models', 
    label: 'Voice Model Management', 
    icon: Package, 
    description: 'Manage STT/TTS model loading and memory',
    parent: 'voice'
  },
  { id: 'memory', label: 'Memory & Context', icon: Database, description: 'Vector memory and context retrieval' },
  { id: 'tools', label: 'Tools', icon: Zap, description: 'Enable and configure tools' },
  { id: 'character', label: 'Character', icon: User, description: 'Character card settings' },
  { id: 'profile', label: 'User Profile', icon: User, description: 'Your profile information' },
  { id: 'system-prompt', label: 'System Prompt', icon: FileText, description: 'System prompt editor' },
];

export default function SettingsPanel({ onClose, onWidthChange }: SettingsPanelProps) {
  const { settings: contextSettings, isLoading: settingsLoading } = useSettings();
  const { showWarning } = useToast();
  const [settings, setSettings] = useState<AppSettings>(() => {
    const local = loadSettingsLocally();
    return contextSettings?.settings ? { ...contextSettings.settings, ...local } : local;
  });
  const [activeSection, setActiveSection] = useState<SettingsSection>('ai');
  
  // Auto-expand voice section when selecting voice-models
  useEffect(() => {
    if (activeSection === 'voice-models') {
      // Ensure voice section is expanded (handled by isActive check)
    }
    return undefined;
  }, [activeSection]);
  const syncTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (contextSettings?.settings) {
      // Use setTimeout to defer setState and avoid synchronous setState in effect
      const timeoutId = setTimeout(() => {
        const local = loadSettingsLocally();
        setSettings({ ...contextSettings.settings, ...local });
      }, 0);
      return () => clearTimeout(timeoutId);
    }
    return undefined;
  }, [contextSettings]);

  const saveSettings = useCallback(async (settingsToSave: AppSettings) => {
    try {
      saveSettingsLocally({
        character_card: settingsToSave?.character_card,
        user_profile: settingsToSave?.user_profile,
        llm_endpoint_mode: settingsToSave?.llm_endpoint_mode,
        llm_remote_url: settingsToSave?.llm_remote_url,
        llm_remote_api_key: settingsToSave?.llm_remote_api_key,
        llm_remote_model: settingsToSave?.llm_remote_model,
      });

      await api.updateSettings(settingsToSave);
      clearPendingSync();
    } catch (error) {
      console.error('Error saving settings:', error);
      showWarning('Error syncing settings to backend. Changes are saved locally.');
    }
  }, [showWarning]);

  const handleSettingsChange = useCallback((newSettings: AppSettings) => {
    setSettings(newSettings);

    saveSettingsLocally({
      character_card: newSettings?.character_card,
      user_profile: newSettings?.user_profile,
      llm_endpoint_mode: newSettings?.llm_endpoint_mode,
      llm_remote_url: newSettings?.llm_remote_url,
      llm_remote_api_key: newSettings?.llm_remote_api_key,
      llm_remote_model: newSettings?.llm_remote_model,
    });

    if (syncTimeoutRef.current) {
      clearTimeout(syncTimeoutRef.current);
    }
    syncTimeoutRef.current = setTimeout(async () => {
      try {
        await api.updateSettings(newSettings);
        clearPendingSync();
      } catch (error) {
        console.error('Error auto-syncing settings:', error);
      }
    }, 1000);
  }, []);

  const handleSave = useCallback(async () => {
    await saveSettings(settings);
  }, [settings, saveSettings]);

  const currentSection = SECTIONS.find((s) => s.id === activeSection);
  const SectionIcon = currentSection?.icon || SettingsIcon;

  return (
    <div className="flex flex-col sm:flex-row h-full max-h-full overflow-hidden">
        <div className="w-full sm:w-56 border-r border-border bg-muted/50 flex-shrink-0 flex flex-col h-full max-h-full overflow-hidden">
          <div className="p-4 border-b border-border flex-shrink-0">
            <h2 className="text-lg font-bold">Settings</h2>
            <p className="text-xs text-muted-foreground mt-1">Configure your assistant</p>
          </div>

          <ScrollArea className="flex-1 min-h-0">
            <nav className="p-2">
              {SECTIONS.filter(s => !s.parent).map((section) => {
                const Icon = section.icon;
                const isActive = activeSection === section.id || (section.id === 'voice' && activeSection === 'voice-models');
                const childSections = SECTIONS.filter(s => s.parent === section.id);

                return (
                  <div key={section.id} className="mb-1">
                    <Button
                      onClick={() => setActiveSection(section.id)}
                      variant={isActive && !childSections.length ? 'secondary' : 'ghost'}
                      className={cn(
                        'w-full justify-start gap-3',
                        isActive && !childSections.length && 'bg-secondary'
                      )}
                      title={section.description}
                    >
                      <Icon size={18} />
                      <span className="text-sm font-medium">{section.label}</span>
                    </Button>
                    {childSections.length > 0 && (
                      <div className={cn("ml-6 mt-1 space-y-1", isActive ? "block" : "hidden")}>
                        {childSections.map((child) => {
                          const ChildIcon = child.icon;
                          const isChildActive = activeSection === child.id;
                          return (
                            <Button
                              key={child.id}
                              onClick={() => setActiveSection(child.id)}
                              variant={isChildActive ? 'secondary' : 'ghost'}
                              className={cn(
                                'w-full justify-start gap-2 text-xs',
                                isChildActive && 'bg-secondary'
                              )}
                              title={child.description}
                            >
                              <ChildIcon size={14} />
                              <span>{child.label}</span>
                            </Button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </nav>
          </ScrollArea>
        </div>

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden overflow-x-hidden h-full max-h-full max-w-full" style={{ width: '100%', maxWidth: '100%' }}>
          <div className="p-4 border-b border-border flex-shrink-0 max-w-full overflow-hidden overflow-x-hidden" style={{ width: '100%', maxWidth: '100%' }}>
            <div className="flex items-center gap-2 mb-1">
              <SectionIcon size={20} className="text-muted-foreground" />
              <h3 className="text-lg font-semibold truncate">{currentSection?.label}</h3>
            </div>
            <p className="text-xs text-muted-foreground truncate">{currentSection?.description}</p>
          </div>

          <ScrollArea className="flex-1 min-h-0 max-w-full overflow-hidden overflow-x-hidden">
            <div className="p-4 sm:p-6 max-w-full overflow-hidden overflow-x-hidden" style={{ width: '100%', maxWidth: '100%' }}>
              <div className={cn("hidden", settingsLoading && "block max-w-full overflow-hidden")}>
                <div className="flex items-center justify-center py-12">
                  <Skeleton className="h-4 w-48" />
                </div>
              </div>
              <div className={cn("hidden", !settingsLoading && "block space-y-6 max-w-full overflow-hidden")}>
                <div className={cn("hidden", activeSection === 'ai' && "block max-w-full overflow-hidden")}>
                  <AISettings settings={settings} onSettingsChange={handleSettingsChange} />
                </div>
                <div className={cn("hidden", activeSection === 'voice' && "block max-w-full overflow-hidden")}>
                  <VoiceSettings />
                </div>
                <div className={cn("hidden", activeSection === 'voice-models' && "block max-w-full overflow-hidden")}>
                  <ModelManagement />
                </div>
                <div className={cn("hidden", activeSection === 'memory' && "block max-w-full overflow-hidden")}>
                  <MemorySettings />
                </div>
                <div className={cn("hidden", activeSection === 'tools' && "block max-w-full overflow-hidden")}>
                  <ToolSettings />
                </div>
                <div className={cn("hidden", activeSection === 'character' && "block max-w-full overflow-hidden")}>
                  <CharacterSettings
                    settings={settings}
                    onSettingsChange={handleSettingsChange}
                    onSave={handleSave}
                  />
                </div>
                <div className={cn("hidden", activeSection === 'profile' && "block max-w-full overflow-hidden")}>
                  <ProfileSettings
                    settings={settings}
                    onSettingsChange={handleSettingsChange}
                    onSave={handleSave}
                  />
                </div>
                <div className={cn("hidden", activeSection === 'system-prompt' && "block max-w-full overflow-hidden")}>
                  <SystemPromptEditor />
                </div>
                <div className={cn("hidden", !['ai', 'voice', 'voice-models', 'memory', 'tools', 'character', 'profile', 'system-prompt'].includes(activeSection) && "block max-w-full overflow-hidden")}>
                  <div>Section not found</div>
                </div>
              </div>
            </div>
          </ScrollArea>
        </div>
      </div>
  );
}
