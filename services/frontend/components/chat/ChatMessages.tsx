'use client';

import { useRef, useEffect, memo } from 'react';
import { RefreshCw, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ChatMessage } from './ChatMessage';
import { cn } from '@/lib/utils';

interface ChatMessagesProps {
  messages: any[];
  userName: string;
  botName: string;
  editingIndex: number | null;
  editContent: string;
  onEditContentChange: (content: string) => void;
  onStartEdit: (index: number) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onRegenerate: () => void;
  onTTS?: (content: string) => void;
  loading: boolean;
  onStop: () => void;
  isSaving?: boolean;
}

function ChatMessagesComponent({
  messages,
  userName,
  botName,
  editingIndex,
  editContent,
  onEditContentChange,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onRegenerate,
  onTTS,
  loading,
  onStop,
  isSaving = false,
}: ChatMessagesProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Auto-scroll to bottom when messages change or when loading
    // Use requestAnimationFrame to ensure DOM has updated
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    });
  }, [messages, loading]);

  // Also scroll on any content change (for streaming)
  useEffect(() => {
    const timer = setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 100);
    return () => clearTimeout(timer);
  }, [messages]);

  return (
    <div 
      ref={messagesContainerRef}
      className="flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6 space-y-4 min-h-0 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar]:block [&::-webkit-scrollbar-thumb]:bg-muted-foreground/30 [&::-webkit-scrollbar-thumb]:rounded [&::-webkit-scrollbar-thumb]:hover:bg-muted-foreground/50 [&::-webkit-scrollbar-track]:bg-transparent"
      style={{ 
        scrollbarWidth: 'thin',
        scrollbarColor: 'rgba(155, 155, 155, 0.5) transparent',
        height: '100%',
        width: '100%',
        maxWidth: '100%'
      }}
    >
      <div className={cn("hidden", messages.length === 0 && !loading && "block text-center text-muted-foreground mt-8")}>
        Start a conversation by sending a message
      </div>
      <div className={cn("hidden", messages.length > 0 && "block")}>
        {messages.map((msg, idx) => {
          const isUser = msg.role === 'user';
          const isEditing = editingIndex === idx;

          return (
            <ChatMessage
              key={msg.id || msg.timestamp || idx}
              message={msg}
              index={idx}
              isUser={isUser}
              userName={userName}
              botName={botName}
              isEditing={isEditing}
              editContent={editContent}
              onEditContentChange={onEditContentChange}
              onStartEdit={() => onStartEdit(idx)}
              onSaveEdit={onSaveEdit}
              isSaving={isSaving}
              onCancelEdit={onCancelEdit}
              onTTS={onTTS}
            />
          );
        })}
        <div className={cn("hidden", messages.length > 0 && messages[messages.length - 1]?.role === 'assistant' && !loading && "block mt-2 flex items-center gap-2")}>
          <Button
            onClick={onRegenerate}
            variant="outline"
            size="sm"
            className="text-xs flex items-center gap-1.5"
            title="Regenerate response"
          >
            <RefreshCw size={12} />
            Regenerate
          </Button>
        </div>
      </div>
      <div className={cn("hidden", loading && "block flex flex-col items-start mb-4")}>
        <span className="text-xs font-medium mb-1 px-2 text-muted-foreground">{botName}</span>
        <div className="bg-muted rounded px-4 py-2 flex items-center gap-3">
          <p className="text-muted-foreground">Thinking...</p>
          <Button
            onClick={onStop}
            variant="destructive"
            size="sm"
            className="flex items-center gap-1.5"
            title="Stop generation"
          >
            <Square size={12} />
            Stop
          </Button>
        </div>
      </div>
      <div ref={messagesEndRef} />
    </div>
  );
}

export const ChatMessages = memo(ChatMessagesComponent);