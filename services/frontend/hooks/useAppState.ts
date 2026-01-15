import { useState, useCallback } from 'react';

export type ActivePanel = 'settings' | 'models' | 'debug' | 'calendar' | 'todo' | null;

export function useAppState() {
  const [activePanel, setActivePanel] = useState<ActivePanel>(null);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);

  const openPanel = useCallback((panel: ActivePanel) => {
    setActivePanel(panel);
  }, []);

  const closePanel = useCallback(() => {
    setActivePanel(null);
  }, []);

  const togglePanel = useCallback((panel: ActivePanel) => {
    setActivePanel((current) => (current === panel ? null : panel));
  }, []);

  return {
    activePanel,
    currentConversationId,
    setCurrentConversationId,
    openPanel,
    closePanel,
    togglePanel,
  };
}




