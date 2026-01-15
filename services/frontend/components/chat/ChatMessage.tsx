'use client';

import { useState, useRef, useEffect } from 'react';
import { Edit2, Volume2, Check, X as XIcon, FileText, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { MessageToolCalls } from './MessageToolCalls';
import { MessageContext } from './MessageContext';
import { Badge } from '@/components/ui/badge';

interface ChatMessageProps {
  message: any;
  index: number;
  isUser: boolean;
  userName: string;
  botName: string;
  isEditing: boolean;
  editContent: string;
  onEditContentChange: (content: string) => void;
  onStartEdit: () => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onTTS?: (content: string) => void;
  isSaving?: boolean;
}

export function ChatMessage({
  message,
  isUser,
  userName,
  botName,
  isEditing,
  editContent,
  onEditContentChange,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onTTS,
  isSaving = false,
}: ChatMessageProps) {
  const displayName = isUser ? userName : botName;
  const toolCalls = message.tool_calls || [];
  const contextUsed = message.context_used || [];
  // Reset tool calls panel when message changes - use key to trigger reset
  const messageKey = message.id || JSON.stringify(message);
  const [showToolCalls, setShowToolCalls] = useState(false);
  
  // Reset when message key changes (using key prop pattern)
  const prevMessageKeyRef = useRef<string | null>(null);
  if (prevMessageKeyRef.current !== messageKey) {
    prevMessageKeyRef.current = messageKey;
    if (showToolCalls) {
      setShowToolCalls(false);
    }
  }

  return (
    <div className={cn('flex flex-col mb-4', isUser ? 'items-end' : 'items-start')}>
      <span
        className={cn(
          'text-xs font-medium mb-1 px-2',
          isUser ? 'text-primary' : 'text-muted-foreground'
        )}
      >
        {displayName}
      </span>

      <MessageContext contextUsed={contextUsed} />

      <div className={cn("hidden w-full max-w-3xl", showToolCalls && "block")}>
        <MessageToolCalls toolCalls={toolCalls} />
      </div>

      <div
        className={cn(
          'max-w-3xl rounded px-4 py-2',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'
        )}
      >
        <div className={cn("hidden", isEditing && "block")}>
          <div className="flex flex-col gap-2">
            <Textarea
              value={editContent}
              onChange={(e) => onEditContentChange(e.target.value)}
              className={cn(
                "w-full p-3 rounded resize-none min-h-[100px] font-sans",
                isUser 
                  ? "bg-primary text-primary-foreground border-primary-foreground/30 focus:border-primary-foreground/60 focus:ring-2 focus:ring-primary-foreground/20 placeholder:text-primary-foreground/60" 
                  : "bg-muted text-foreground border-border/50 focus:border-primary focus:ring-2 focus:ring-primary/20 placeholder:text-muted-foreground"
              )}
              placeholder={isUser ? "Edit your message..." : "Edit assistant message..."}
              rows={Math.max(4, Math.ceil(editContent.split('\n').length))}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  onSaveEdit();
                } else if (e.key === 'Escape') {
                  e.preventDefault();
                  onCancelEdit();
                }
              }}
            />
            <div className="flex gap-2 justify-end">
              <Button 
                onClick={onCancelEdit} 
                variant="ghost" 
                size="sm" 
                className={cn(
                  "flex items-center gap-1.5",
                  isUser 
                    ? "text-primary-foreground hover:bg-primary-foreground/20" 
                    : "text-foreground hover:bg-muted-foreground/10"
                )}
              >
                <XIcon size={14} />
                Cancel
              </Button>
              <Button 
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  console.log('[ChatMessage] Save button clicked', { isSaving, hasHandler: !!onSaveEdit });
                  if (onSaveEdit && !isSaving) {
                    onSaveEdit();
                  } else {
                    console.warn('[ChatMessage] Save button clicked but handler not available or already saving', { hasHandler: !!onSaveEdit, isSaving });
                  }
                }} 
                size="sm" 
                type="button"
                disabled={!onSaveEdit || isSaving || !editContent.trim()}
                className={cn(
                  "flex items-center gap-1.5",
                  isUser 
                    ? "bg-primary-foreground text-primary hover:bg-primary-foreground/90 shadow-sm" 
                    : "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
                )}
              >
                <Check size={14} />
                {isSaving ? 'Saving...' : 'Save (Ctrl+Enter)'}
              </Button>
            </div>
          </div>
        </div>
        <div className={cn("hidden", !isEditing && "block")}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <p className="whitespace-pre-wrap">{message.content}</p>
              <div className={cn(
                "hidden mt-2 pt-2 flex flex-wrap gap-2",
                message.files && message.files.length > 0 && "flex"
              )}>
                {message.files?.map((file: any, fileIdx: number) => (
                  <div
                    key={fileIdx}
                    className={cn(
                      "flex items-center gap-1.5 px-2 py-1 rounded text-xs",
                      isUser
                        ? 'bg-background/20 text-primary-foreground'
                        : 'bg-muted-foreground/20 text-foreground'
                    )}
                  >
                    <FileText size={12} />
                    <span className="truncate max-w-[150px]">{file.name}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              <div className={cn("hidden", !isUser && toolCalls.length > 0 && "flex")}>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowToolCalls((prev) => !prev)}
                  className="h-6 w-6 relative"
                  title={showToolCalls ? "Hide tool calls" : "Show tool calls"}
                >
                  <Wrench size={14} />
                  <Badge className="absolute -top-1 -right-1 h-4 min-w-4 px-1 text-[10px] leading-none rounded">
                    {toolCalls.length}
                  </Badge>
                </Button>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={onStartEdit}
                className="h-6 w-6"
                title="Edit message"
              >
                <Edit2 size={14} />
              </Button>
              <div className={cn("hidden", !isUser && message.content && onTTS && "block")}>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => onTTS?.(message.content)}
                  className="h-6 w-6"
                  title="Text to Speech"
                >
                  <Volume2 size={14} />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
