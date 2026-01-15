import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queries/keys';

export interface Conversation {
  conversation_id: string;
  id?: string;
  name?: string;
  pinned?: boolean;
  messages?: any[];
  created_at?: string;
  updated_at?: string;
}

export function useConversations(filters?: { limit?: number; offset?: number }) {
  return useQuery<Conversation[]>({
    queryKey: queryKeys.conversations.list(filters),
    queryFn: async () => {
      const data = await api.getConversations(filters?.limit, filters?.offset);
      return data as Conversation[];
    },
    staleTime: 30 * 1000, // 30 seconds
  });
}




