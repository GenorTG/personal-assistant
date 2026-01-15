'use client';

import { useEffect, useRef } from 'react';
import { Header } from './Header';
import { BackendStatusBar } from './BackendStatusBar';
import { MainContent } from './MainContent';
import { SidebarManager } from './SidebarManager';
import { DebugStatusPanel } from '@/components/DebugStatusPanel';
import { useAppState } from '@/hooks/useAppState';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import { useConversations } from '@/hooks/queries/useConversations';
import { useCreateConversation } from '@/hooks/mutations/useConversationMutations';

export function AppLayout() {
  const { isReady: backendReady } = useBackendHealth({ interval: 5000, enabled: true });
  const { data: conversations, isLoading } = useConversations();
  const createConversation = useCreateConversation();
  const {
    activePanel,
    currentConversationId,
    setCurrentConversationId,
    togglePanel,
    closePanel,
  } = useAppState();
  
  // Track if we're currently creating a conversation to prevent loops
  const isCreatingRef = useRef(false);
  const hasInitializedRef = useRef(false);
  const lastConversationCountRef = useRef<number>(0);

  // Initialize conversation on mount
  useEffect(() => {
    if (typeof window === 'undefined') return undefined; // Skip during SSR/build
    if (isLoading) return undefined; // Wait for conversations to load
    if (isCreatingRef.current) return undefined; // Prevent concurrent creation
    
    const conversationCount = conversations?.length || 0;
    
    // Reset initialization flag if all conversations were deleted
    if (conversationCount === 0 && lastConversationCountRef.current > 0) {
      hasInitializedRef.current = false;
    }
    lastConversationCountRef.current = conversationCount;
    
    // Only auto-create once on initial mount when there are no conversations
    if (!hasInitializedRef.current && conversationCount === 0 && backendReady) {
      hasInitializedRef.current = true;
      isCreatingRef.current = true;
      createConversation.mutate({ silent: true }, {
        onSettled: () => {
          isCreatingRef.current = false;
        },
      });
    } else if (conversations && conversations.length > 0 && !currentConversationId) {
      // Set current conversation if we have conversations but no current one
      const lastId = localStorage.getItem('lastConversationId');
      const lastExists = lastId && conversations.some((c: any) => c.conversation_id === lastId);
      
      if (lastExists) {
        setCurrentConversationId(lastId);
      } else {
        const firstId = conversations[0]?.conversation_id;
        if (firstId) {
          setCurrentConversationId(firstId);
          localStorage.setItem('lastConversationId', firstId);
        }
      }
      hasInitializedRef.current = true;
    } else if (conversations && conversations.length > 0) {
      // Mark as initialized if we have conversations
      hasInitializedRef.current = true;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, conversations, backendReady, currentConversationId, createConversation]);

  const handleConversationSwitch = (id: string) => {
    setCurrentConversationId(id);
    if (typeof window !== 'undefined') {
      localStorage.setItem('lastConversationId', id);
    }
  };

  const handleConversationNotFound = (id: string) => {
    const remaining = conversations?.filter((c: any) => c.conversation_id !== id) || [];
    if (currentConversationId === id) {
      const nextId = remaining.length > 0 ? remaining[0].conversation_id : null;
      setCurrentConversationId(nextId);
      if (typeof window !== 'undefined') {
        if (nextId) {
          localStorage.setItem('lastConversationId', nextId);
        } else {
          localStorage.removeItem('lastConversationId');
        }
      }
    }
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden max-h-screen overflow-x-hidden max-w-full w-full">
      <Header activePanel={activePanel} onTogglePanel={togglePanel} />
      <BackendStatusBar isReady={backendReady} />
      <div className="flex-1 flex overflow-hidden overflow-x-hidden max-w-full w-full min-w-0">
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden overflow-x-hidden max-w-full w-full">
          <MainContent
            conversations={conversations || []}
            currentConversationId={currentConversationId}
            onConversationSwitch={handleConversationSwitch}
            onConversationNotFound={handleConversationNotFound}
          />
        </div>
      </div>
      <SidebarManager activePanel={activePanel} onClose={closePanel} />
      <DebugStatusPanel />
    </div>
  );
}

