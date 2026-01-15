'use client';

import { useEffect, useState } from 'react';
import ChatPanel from '@/components/chat/ChatPanel';
import ConversationTabs from '@/components/ConversationTabs';
import Organizer from '@/components/Organizer';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { MessageSquare, CalendarDays } from 'lucide-react';
import { useConversations } from '@/hooks/queries/useConversations';
import {
  useCreateConversation,
  useDeleteConversation,
  useDeleteAllConversations,
  useRenameConversation,
  usePinConversation,
} from '@/hooks/mutations/useConversationMutations';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queries/keys';
import { useWebSocketEvent } from '@/contexts/WebSocketContext';

interface MainContentProps {
  conversations: any[];
  currentConversationId: string | null;
  onConversationSwitch: (id: string) => void;
  onConversationNotFound: (id: string) => void;
}

export function MainContent({
  conversations,
  currentConversationId,
  onConversationSwitch,
  onConversationNotFound,
}: MainContentProps) {
  const [activeTab, setActiveTab] = useState<'chat' | 'organizer'>('chat');
  const { data: conversationsData, isLoading, error, refetch } = useConversations();
  const queryClient = useQueryClient();
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();
  const deleteAllConversations = useDeleteAllConversations();
  const renameConversation = useRenameConversation();
  const pinConversation = usePinConversation();

  const handleNewConversation = async () => {
    const result = await createConversation.mutateAsync(undefined);
    if (result?.conversation_id) {
      onConversationSwitch(result.conversation_id);
      if (typeof window !== 'undefined') {
        localStorage.setItem('lastConversationId', result.conversation_id);
      }
    }
  };

  const handleDeleteConversation = async (id: string) => {
    // If deleting the active conversation, switch to another one FIRST (before deletion)
    // This prevents the ChatPanel from trying to fetch the deleted conversation
    if (currentConversationId === id) {
      // Cancel and remove the query for the conversation being deleted to prevent 404 errors
      queryClient.cancelQueries({ queryKey: queryKeys.conversations.detail(id) });
      queryClient.removeQueries({ queryKey: queryKeys.conversations.detail(id) });
      
      // Get remaining conversations (excluding the one being deleted)
      // Use conversationsData if available (more up-to-date), otherwise fall back to conversations prop
      const allConversations = conversationsData || conversations;
      const remaining = allConversations.filter((c: any) => c.conversation_id !== id);
      
      if (remaining.length > 0) {
        // Switch to the first remaining conversation
        const nextId = remaining[0].conversation_id;
        onConversationSwitch(nextId);
        if (typeof window !== 'undefined') {
          localStorage.setItem('lastConversationId', nextId);
        }
      } else {
        // No conversations left, create a new one
        const result = await createConversation.mutateAsync(undefined);
        if (result?.conversation_id) {
          onConversationSwitch(result.conversation_id);
          if (typeof window !== 'undefined') {
            localStorage.setItem('lastConversationId', result.conversation_id);
          }
        } else {
          // If creation fails, switch to empty string
          onConversationSwitch('');
          if (typeof window !== 'undefined') {
            localStorage.removeItem('lastConversationId');
          }
        }
      }
    }
    
    // Now delete the conversation (after switching away from it)
    await deleteConversation.mutateAsync(id);
  };

  const handleRenameConversation = async (id: string, newName: string) => {
    await renameConversation.mutateAsync({ id, newName });
  };

  const handlePinConversation = async (id: string, pinned: boolean) => {
    await pinConversation.mutateAsync({ id, pinned });
  };

  const displayConversations = conversationsData || conversations;

  // Listen for WebSocket events to update conversations list
  useWebSocketEvent('conversation_created', () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
  });

  useWebSocketEvent('conversation_deleted', (payload) => {
    const conversationId = payload?.conversation_id;
    if (conversationId) {
      // Remove the conversation query
      queryClient.removeQueries({ queryKey: queryKeys.conversations.detail(conversationId) });
    }
    // Refresh conversations list
    queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
  });

  useWebSocketEvent('conversation_updated', () => {
    // Refresh conversations list when a conversation is updated (renamed, pinned, etc.)
    queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
  });

  useWebSocketEvent('conversations_list_changed', () => {
    // Refresh conversations list when backend notifies of changes
    queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
  });

  return (
    <>
      {/* Main Tab Switcher */}
      <div className="w-full border-b bg-background flex-shrink-0">
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'chat' | 'organizer')}>
          <div className="flex items-center justify-between px-4">
            <TabsList>
              <TabsTrigger value="chat">
                <MessageSquare className="h-4 w-4 mr-2" />
                Chat
              </TabsTrigger>
              <TabsTrigger value="organizer">
                <CalendarDays className="h-4 w-4 mr-2" />
                Organizer
              </TabsTrigger>
            </TabsList>
          </div>
        </Tabs>
      </div>

      {/* Content based on active tab */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {activeTab === 'chat' && (
          <>
            {/* Conversation Tabs */}
            <div className="w-full border-b bg-background flex-shrink-0">
              {isLoading && (
                <div className="px-4 py-2">
                  <Skeleton className="h-8 w-full" />
                </div>
              )}
              {error && !isLoading && (
                <div className="px-4 py-2">
                  <Alert variant="destructive">
                    <AlertTitle>Error</AlertTitle>
                    <AlertDescription className="flex items-center justify-between">
                      <span>{error instanceof Error ? error.message : 'Failed to load conversations'}</span>
                      <Button variant="outline" size="sm" onClick={() => refetch()}>
                        Retry
                      </Button>
                    </AlertDescription>
                  </Alert>
                </div>
              )}
              {!isLoading && !error && (
                <ConversationTabs
                  conversations={displayConversations}
                  currentId={currentConversationId}
                  onNew={handleNewConversation}
                  onSwitch={onConversationSwitch}
                  onDelete={handleDeleteConversation}
                  onDeleteAll={async () => {
                    await deleteAllConversations.mutateAsync();
                    // After deleting all, the AppLayout useEffect will create a new default conversation
                  }}
                  onRename={handleRenameConversation}
                  onPin={handlePinConversation}
                />
              )}
            </div>

            {/* Chat Panel */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
              <ChatPanel
                conversationId={currentConversationId}
                conversations={displayConversations}
                onConversationNotFound={onConversationNotFound}
                onConversationCreated={async (newId) => {
                  onConversationSwitch(newId);
                  if (typeof window !== 'undefined') {
                    localStorage.setItem('lastConversationId', newId);
                  }
                  await queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
                }}
              />
            </div>
          </>
        )}

        {activeTab === 'organizer' && (
          <div className="flex-1 overflow-hidden">
            <Organizer />
          </div>
        )}
      </div>
    </>
  );
}

