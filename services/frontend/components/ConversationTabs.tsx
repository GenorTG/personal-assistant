'use client';

import { Plus, X, Edit2, Check, Pin } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface ConversationTabsProps {
  conversations: any[];
  currentId: string | null;
  onNew: () => void;
  onSwitch: (id: string) => void;
  onDelete: (id: string) => void;
  onDeleteAll?: () => void;
  onRename?: (id: string, newName: string) => void;
  onPin?: (id: string, pinned: boolean) => void;
}

export default function ConversationTabs({
  conversations,
  currentId,
  onNew,
  onSwitch,
  onDelete,
  onDeleteAll,
  onRename,
  onPin,
}: ConversationTabsProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [pendingDeleteAll, setPendingDeleteAll] = useState(false);

  const getTitle = (conv: any) => {
    if (conv.name) return conv.name;
    if (conv.messages && conv.messages.length > 0) {
      return conv.messages[0].content.substring(0, 30) + '...';
    }
    return `Chat ${conv.conversation_id.substring(0, 8)}`;
  };

  const handleRenameStart = (conv: any, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(conv.conversation_id);
    setEditName(getTitle(conv));
  };

  const handleRenameSave = (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (onRename && editName.trim()) {
      onRename(id, editName.trim());
    }
    setEditingId(null);
    setEditName('');
  };

  const handleRenameCancel = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setEditingId(null);
    setEditName('');
  };

  const handleKeyDown = (e: React.KeyboardEvent, id: string) => {
    if (e.key === 'Enter') {
      handleRenameSave(id);
    } else if (e.key === 'Escape') {
      handleRenameCancel();
    }
  };

  const handleDeleteClick = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (pendingDeleteId === id) {
      // Second click - confirm delete
      onDelete(id);
      setPendingDeleteId(null);
    } else {
      // First click - show confirmation state
      setPendingDeleteId(id);
      // Reset after 3 seconds if not confirmed
      setTimeout(() => setPendingDeleteId(null), 3000);
    }
  };

  const handleDeleteAllClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (pendingDeleteAll) {
      // Second click - confirm delete all
      if (onDeleteAll) {
        onDeleteAll();
      }
      setPendingDeleteAll(false);
    } else {
      // First click - show confirmation state
      setPendingDeleteAll(true);
      // Reset after 3 seconds if not confirmed
      setTimeout(() => setPendingDeleteAll(false), 3000);
    }
  };

  const sortedConversations = [...conversations].sort((a, b) => {
    // Pinned conversations first
    if (a.pinned && !b.pinned) return -1;
    if (!a.pinned && b.pinned) return 1;
    // Then by timestamp (newest first)
    const aTime = a.updated_at || a.created_at || '';
    const bTime = b.updated_at || b.created_at || '';
    return bTime.localeCompare(aTime);
  });

  return (
    <div className="w-full border-b bg-muted/30">
      <div className="px-4 py-2">
        <Tabs value={currentId || ''} onValueChange={onSwitch} className="w-full">
          <div className="flex items-center justify-between gap-2 mb-2">
            <TabsList className="flex-1 overflow-x-auto justify-start h-auto p-1 bg-background border">
              {sortedConversations.map((conv) => {
                const id = conv.conversation_id || conv.id;
                const isActive = currentId === id;
                const isEditing = editingId === id;
                const isPendingDelete = pendingDeleteId === id;

                return (
                  <div
                    key={id}
                    className="relative group"
                    onClick={(e) => {
                      if (!isEditing) {
                        e.stopPropagation();
                        onSwitch(id);
                      }
                    }}
                  >
                    <TabsTrigger
                      value={id}
                      className={cn(
                        "relative px-3 py-1.5 text-sm max-w-[200px] min-w-[120px] border border-transparent",
                        isActive 
                          ? "bg-primary text-primary-foreground border-primary" 
                          : "bg-background hover:bg-muted text-foreground"
                      )}
                      onClick={(e) => {
                        if (isEditing) {
                          e.stopPropagation();
                        }
                      }}
                    >
                      {isEditing ? (
                        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                          <Input
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            onKeyDown={(e) => handleKeyDown(e, id)}
                            onClick={(e) => e.stopPropagation()}
                            className="h-6 text-xs px-1"
                            autoFocus
                          />
                          <div
                            onClick={(e) => handleRenameSave(id, e)}
                            className="h-6 w-6 p-0 flex items-center justify-center cursor-pointer hover:bg-muted rounded transition-colors"
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                handleRenameSave(id, e as any);
                              }
                            }}
                          >
                            <Check size={10} />
                          </div>
                          <div
                            onClick={(e) => handleRenameCancel(e)}
                            className="h-6 w-6 p-0 flex items-center justify-center cursor-pointer hover:bg-muted rounded transition-colors"
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                handleRenameCancel(e as any);
                              }
                            }}
                          >
                            <X size={10} />
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 min-w-0">
                          {conv.pinned && <Pin size={10} className="flex-shrink-0 fill-current" />}
                          <span className="truncate">{getTitle(conv)}</span>
                          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                            {onPin && (
                              <div
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onPin(id, !conv.pinned);
                                }}
                                className="h-5 w-5 p-0 flex items-center justify-center cursor-pointer hover:bg-muted rounded transition-colors"
                                title={conv.pinned ? 'Unpin' : 'Pin'}
                              >
                                <Pin size={10} className={cn(conv.pinned && 'fill-current')} />
                              </div>
                            )}
                            {onRename && (
                              <div
                                onClick={(e) => handleRenameStart(conv, e)}
                                className="h-5 w-5 p-0 flex items-center justify-center cursor-pointer hover:bg-muted rounded transition-colors"
                                title="Rename"
                              >
                                <Edit2 size={10} />
                              </div>
                            )}
                            <div
                              onClick={(e) => handleDeleteClick(id, e)}
                              className={cn(
                                "h-5 px-1.5 text-xs flex items-center justify-center cursor-pointer rounded transition-colors",
                                isPendingDelete 
                                  ? "bg-destructive text-destructive-foreground hover:bg-destructive/90" 
                                  : "text-destructive hover:bg-muted"
                              )}
                              title={isPendingDelete ? "Click again to confirm" : "Delete"}
                            >
                              {isPendingDelete ? "Confirm" : <X size={10} />}
                            </div>
                          </div>
                        </div>
                      )}
                    </TabsTrigger>
                  </div>
                );
              })}
            </TabsList>
            <div className="flex items-center gap-1 flex-shrink-0">
              <Button
                variant="ghost"
                size="sm"
                onClick={onNew}
                className="h-8 w-8 p-0"
                title="New conversation"
              >
                <Plus size={16} />
              </Button>
              {onDeleteAll && conversations.length > 0 && (
                <Button
                  variant={pendingDeleteAll ? "destructive" : "ghost"}
                  size="sm"
                  onClick={handleDeleteAllClick}
                  className={cn(
                    "h-8 px-2 text-xs",
                    pendingDeleteAll ? "bg-destructive text-destructive-foreground" : "text-destructive hover:text-destructive"
                  )}
                  title={pendingDeleteAll ? "Click again to confirm" : "Delete all conversations"}
                >
                  {pendingDeleteAll ? "Confirm" : <X size={16} />}
                </Button>
              )}
            </div>
          </div>
        </Tabs>
      </div>
    </div>
  );
}
