import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queries/keys';
import { useToast } from '@/contexts/ToastContext';

export function useCreateConversation() {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useToast();

  return useMutation({
    mutationFn: async (options?: { silent?: boolean }) => {
      const response = await api.createConversation();
      if (!response || !(response as any).conversation_id) {
        throw new Error('Invalid response from server');
      }
      const result = response as { conversation_id: string };
      // Store silent flag in a way that doesn't affect the return type
      (result as any).__silent = options?.silent;
      return result;
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
      if (!variables?.silent) {
        showSuccess('Conversation created successfully');
      }
    },
    onError: (error: Error) => {
      showError(`Error creating conversation: ${error.message}`);
    },
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn: async (id: string) => {
      // Cancel any ongoing queries for this conversation to prevent 404 errors
      await queryClient.cancelQueries({ queryKey: queryKeys.conversations.detail(id) });
      // Remove the query immediately to prevent it from being fetched
      queryClient.removeQueries({ queryKey: queryKeys.conversations.detail(id) });
      
      await api.deleteConversation(id);
      return id;
    },
    onSuccess: (id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
      // Ensure the detail query is removed (in case it wasn't already)
      queryClient.removeQueries({ queryKey: queryKeys.conversations.detail(id) });
    },
    onError: (error: Error) => {
      showError(`Error deleting conversation: ${error.message}`);
    },
  });
}

export function useDeleteAllConversations() {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useToast();

  return useMutation({
    mutationFn: async () => {
      const response = await api.deleteAllConversations();
      return response as { deleted_count: number; status: string };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
      queryClient.clear(); // Clear all conversation queries
      showSuccess(`Deleted ${data.deleted_count || 0} conversation(s)`);
    },
    onError: (error: Error) => {
      showError(`Error deleting conversations: ${error.message}`);
    },
  });
}

export function useRenameConversation() {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn: async ({ id, newName }: { id: string; newName: string }) => {
      await api.renameConversation(id, newName.trim());
      return { id, newName: newName.trim() };
    },
    onSuccess: ({ id }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.detail(id) });
    },
    onError: (error: Error) => {
      showError(`Error renaming conversation: ${error.message}`);
    },
  });
}

export function usePinConversation() {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn: async ({ id, pinned }: { id: string; pinned: boolean }) => {
      await api.pinConversation(id, pinned);
      return { id, pinned };
    },
    onSuccess: ({ id }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations.detail(id) });
    },
    onError: (error: Error) => {
      showError(`Error ${error.message}`);
    },
  });
}


