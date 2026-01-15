'use client';

import SettingsPanel from '@/components/SettingsPanel';
import ModelBrowser from '@/components/model-browser/ModelBrowser';
import DebugPanel from '@/components/DebugPanel';
import Calendar from '@/components/Calendar';
import Todo from '@/components/Todo';
import FloatingPanel from '@/components/FloatingPanel';
import type { ActivePanel } from '@/hooks/useAppState';

interface SidebarManagerProps {
  activePanel: ActivePanel;
  onClose: () => void;
}

export function SidebarManager({ activePanel, onClose }: SidebarManagerProps) {
  if (!activePanel) {
    return null;
  }

  const getPanelConfig = () => {
    switch (activePanel) {
      case 'settings':
        return { title: 'Settings', maxWidth: '1000px', maxHeight: '90vh' };
      case 'models':
        return { title: 'Model Browser', maxWidth: '1400px', maxHeight: '90vh' };
      case 'calendar':
        return { title: 'Calendar', maxWidth: '1200px', maxHeight: '90vh' };
      case 'todo':
        return { title: 'Todos', maxWidth: '1200px', maxHeight: '90vh' };
      case 'debug':
        return { title: 'Debug Panel', maxWidth: '1000px', maxHeight: '90vh' };
      default:
        return { title: '', maxWidth: '90vw', maxHeight: '90vh' };
    }
  };

  const config = getPanelConfig();

  return (
    <FloatingPanel
      title={config.title}
      onClose={onClose}
      maxWidth={config.maxWidth}
      maxHeight={config.maxHeight}
    >
      {activePanel === 'settings' && (
        <SettingsPanel onClose={onClose} />
      )}
      {activePanel === 'models' && (
        <ModelBrowser onClose={onClose} />
      )}
      {activePanel === 'calendar' && (
        <Calendar onClose={onClose} />
      )}
      {activePanel === 'todo' && (
        <Todo onClose={onClose} />
      )}
      {activePanel === 'debug' && (
        <DebugPanel onClose={onClose} />
      )}
    </FloatingPanel>
  );
}

