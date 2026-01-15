import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queries/keys';
import { useToast } from '@/contexts/ToastContext';

export function useSendMessage() {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn: async ({
      message,
      conversationId,
      samplerSettings,
      abortController,
      onStreamChunk,
    }: {
      message: string;
      conversationId?: string;
      samplerSettings?: Record<string, any>;
      abortController?: AbortController;
      onStreamChunk?: (chunk: string) => void;
    }) => {
      // Validate message before sending
      if (!message || typeof message !== 'string' || message.trim().length === 0) {
        throw new Error('Message must be a non-empty string');
      }
      
      const response = await api.sendMessage(
        message,
        conversationId,
        samplerSettings,
        abortController,
        onStreamChunk
      );
      return response;
    },
    onMutate: async ({ message, conversationId }) => {
      // Optimistically add user message to conversation
      const userMessage = {
        role: 'user' as const,
        content: message,
        timestamp: new Date().toISOString(),
      };
      
      if (conversationId) {
        const queryKey = queryKeys.conversations.detail(conversationId);
        
        // Cancel outgoing refetches
        await queryClient.cancelQueries({ queryKey });
        
        // Snapshot previous value
        const previousConversation = queryClient.getQueryData(queryKey);
        
        // Optimistically update
        queryClient.setQueryData(queryKey, (old: any) => {
          if (!old) {
            // If conversation doesn't exist yet, create it optimistically
            return {
              conversation_id: conversationId,
              id: conversationId,
              messages: [userMessage],
            };
          }
          return {
            ...old,
            messages: [...(old.messages || []), userMessage],
          };
        });
        
        return { previousConversation, conversationId };
      } else {
        // For new conversations, we'll update after the response comes back
        // But we can still show the message in a temporary state
        return { previousConversation: null, conversationId: null };
      }
    },
    onSuccess: (data, variables) => {
      // Invalidate to get the real response from server
      if (variables.conversationId) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.conversations.detail(variables.conversationId),
        });
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
    },
    onError: (error: Error, variables, context) => {
      // Don't rollback optimistic update for aborted requests - keep the user message
      // Only rollback for actual errors (not user-initiated aborts)
      if (error.name === 'AbortError' || error.message?.includes('aborted')) {
        console.log('Request was aborted by user - keeping user message');
        return;
      }
      
      // Rollback optimistic update on actual error
      if (variables.conversationId && context?.previousConversation) {
        const queryKey = queryKeys.conversations.detail(variables.conversationId);
        queryClient.setQueryData(queryKey, context.previousConversation);
      }
      
      // Extract detailed error message and logs
      let errorMessage = error.message || 'Failed to send message';
      let backendLogs: any[] | null = null;
      
      if ((error as any).response) {
        const response = (error as any).response;
        if (response.detail) {
          errorMessage = response.detail;
        }
        if (response.logs && Array.isArray(response.logs)) {
          backendLogs = response.logs;
        }
      } else if ((error as any).status) {
        errorMessage = `HTTP ${(error as any).status}: ${errorMessage}`;
      }
      
      // Show error with backend logs if available
      if (backendLogs && backendLogs.length > 0) {
        const errorLogs = backendLogs.filter(log => 
          log.level === 'ERROR' || log.level === 'CRITICAL'
        );
        if (errorLogs.length > 0) {
          errorMessage += `\n\nBackend errors:\n${errorLogs.slice(0, 3).map(log => `[${log.level}] ${log.message}`).join('\n')}`;
          if (errorLogs.length > 3) {
            errorMessage += `\n... and ${errorLogs.length - 3} more error(s)`;
          }
        }
      }
      
      showError(`Error sending message: ${errorMessage}`);
    },
  });
}

export function useRegenerateResponse() {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn: async ({
      conversationId,
      samplerSettings,
    }: {
      conversationId: string;
      samplerSettings?: Record<string, any>;
    }) => {
      const response = await api.regenerateLastResponse(conversationId, samplerSettings);
      return response;
    },
    onMutate: async ({ conversationId }) => {
      // Optimistically remove the last assistant message
      if (conversationId) {
        const queryKey = queryKeys.conversations.detail(conversationId);
        
        // Cancel outgoing refetches
        await queryClient.cancelQueries({ queryKey });
        
        // Snapshot previous value
        const previousConversation = queryClient.getQueryData(queryKey);
        
        // Optimistically update - remove last assistant message(s) until we hit a user message
        queryClient.setQueryData(queryKey, (old: any) => {
          if (!old || !old.messages || old.messages.length === 0) {
            return old;
          }
          
          // Find the last user message index
          let lastUserIndex = -1;
          for (let i = old.messages.length - 1; i >= 0; i--) {
            if (old.messages[i].role === 'user') {
              lastUserIndex = i;
              break;
            }
          }
          
          // If we found a user message, keep everything up to and including it
          // Otherwise, keep all messages (shouldn't happen, but be safe)
          if (lastUserIndex >= 0) {
            return {
              ...old,
              messages: old.messages.slice(0, lastUserIndex + 1),
            };
          }
          
          return old;
        });
        
        return { previousConversation, conversationId };
      }
      
      return { previousConversation: null, conversationId: null };
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversations.detail(variables.conversationId),
      });
    },
    onError: (error: Error, variables, context) => {
      // Rollback optimistic update on error
      if (context?.conversationId && context?.previousConversation) {
        const queryKey = queryKeys.conversations.detail(context.conversationId);
        queryClient.setQueryData(queryKey, context.previousConversation);
      }
      showError(`Error regenerating response: ${error.message}`);
    },
  });
}

export function useUpdateMessage() {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn: async ({
      conversationId,
      messageIndex,
      content,
      role,
    }: {
      conversationId: string;
      messageIndex: number;
      content: string;
      role?: string;
    }) => {
      await api.updateMessage(conversationId, messageIndex, content, role);
      return { conversationId, messageIndex, content, role };
    },
    onSuccess: ({ conversationId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversations.detail(conversationId),
      });
    },
    onError: (error: Error) => {
      showError(`Error updating message: ${error.message}`);
    },
  });
}


