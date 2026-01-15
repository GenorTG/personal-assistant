import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queries/keys';

export interface ConversationDetail {
  conversation_id: string;
  id?: string;
  name?: string;
  pinned?: boolean;
  messages: any[];
  created_at?: string;
  updated_at?: string;
}

export function useConversation(id: string | null, enabled: boolean = true) {
  return useQuery<ConversationDetail>({
    queryKey: queryKeys.conversations.detail(id || ''),
    queryFn: async () => {
      if (!id) throw new Error('Conversation ID is required');
      const data = await api.getConversation(id);
      return data as ConversationDetail;
    },
    enabled: enabled && !!id,
    staleTime: 10 * 1000, // 10 seconds
  });
}




