'use client';

import { Plus, X, Edit2, Check, Pin } from 'lucide-react';
import { useState } from 'react';
import { useToast } from '@/contexts/ToastContext';

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
  const { showConfirm } = useToast();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const getTitle = (conv: any) => {
    // Use conversation name if available
    if (conv.name) {
      return conv.name;
    }
    // Fallback to first message preview
    if (conv.messages && conv.messages.length > 0) {
      return conv.messages[0].content.substring(0, 30) + '...';
    }
    // Final fallback
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

  const handleRenameCancel = () => {
    setEditingId(null);
    setEditName('');
  };

  const handleDeleteAll = () => {
    if (!onDeleteAll) return;
    if (conversations.length === 0) return;
    
    const confirmMessage = `Are you sure you want to delete all ${conversations.length} conversations? This action cannot be undone.`;
    showConfirm(confirmMessage, () => {
      onDeleteAll();
    });
  };

  return (
    <div className="w-full bg-gray-100 border-b border-gray-200 px-4 py-2 flex items-center gap-2 overflow-x-auto flex-shrink-0">
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onNew();
        }}
        className="btn-primary flex items-center gap-2 whitespace-nowrap flex-shrink-0 px-4 py-2 min-w-[120px]"
        type="button"
      >
        <Plus size={16} />
        New Chat
      </button>
      {onDeleteAll && conversations.length > 0 && (
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            handleDeleteAll();
          }}
          className="btn-secondary flex items-center gap-2 whitespace-nowrap flex-shrink-0 px-4 py-2 text-red-600 hover:bg-red-50 border-red-300"
          type="button"
          title="Delete all conversations"
        >
          <X size={16} />
          Delete All
        </button>
      )}
      <div className="flex gap-2 overflow-x-auto flex-1">
        {/* Separate pinned conversations */}
        {conversations.filter(conv => conv.pinned).length > 0 && (
          <div className="flex items-center gap-1 px-2 border-r border-gray-300">
            <Pin size={14} className="text-yellow-600" fill="currentColor" />
            <span className="text-xs text-gray-600">Pinned:</span>
          </div>
        )}
        {conversations
          .filter(conv => conv.pinned)
          .map((conv) => (
            <div
              key={conv.conversation_id}
              onClick={() => editingId !== conv.conversation_id && onSwitch(conv.conversation_id)}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg cursor-pointer transition-colors
                whitespace-nowrap flex-shrink-0 border-2 border-yellow-400
                ${
                  currentId === conv.conversation_id
                    ? 'bg-primary-600 text-white border-yellow-300'
                    : 'bg-yellow-50 hover:bg-yellow-100 text-gray-800'
                }
              `}
            >
              {editingId === conv.conversation_id ? (
                <>
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRenameSave(conv.conversation_id);
                      if (e.key === 'Escape') handleRenameCancel();
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="text-sm px-2 py-1 rounded border border-gray-300 text-gray-800 min-w-[150px]"
                    autoFocus
                  />
                  <button
                    onClick={(e) => handleRenameSave(conv.conversation_id, e)}
                    className="hover:bg-white/20 rounded p-1"
                    title="Save"
                  >
                    <Check size={14} />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRenameCancel();
                    }}
                    className="hover:bg-white/20 rounded p-1"
                    title="Cancel"
                  >
                    <X size={14} />
                  </button>
                </>
              ) : (
                <>
                  <Pin size={14} className="text-yellow-600" fill="currentColor" />
                  <span className="text-sm">{getTitle(conv)}</span>
                  {onPin && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onPin(conv.conversation_id, false);
                      }}
                      className="hover:bg-white/20 rounded p-1"
                      title="Unpin"
                    >
                      <Pin size={14} />
                    </button>
                  )}
                  {onRename && (
                    <button
                      onClick={(e) => handleRenameStart(conv, e)}
                      className="hover:bg-white/20 rounded p-1"
                      title="Rename"
                    >
                      <Edit2 size={14} />
                    </button>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(conv.conversation_id);
                    }}
                    className="hover:bg-white/20 rounded p-1"
                    title="Delete"
                  >
                    <X size={14} />
                  </button>
                </>
              )}
            </div>
          ))}
        
        {/* Separator between pinned and unpinned */}
        {conversations.filter(conv => conv.pinned).length > 0 && 
         conversations.filter(conv => !conv.pinned).length > 0 && (
          <div className="flex items-center gap-1 px-2 border-r border-gray-300">
            <span className="text-xs text-gray-600">Others:</span>
          </div>
        )}
        
        {/* Unpinned conversations */}
        {conversations
          .filter(conv => !conv.pinned)
          .map((conv) => (
          <div
            key={conv.conversation_id}
            onClick={() => editingId !== conv.conversation_id && onSwitch(conv.conversation_id)}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-lg cursor-pointer transition-colors
              whitespace-nowrap flex-shrink-0
              ${
                currentId === conv.conversation_id
                  ? 'bg-primary-600 text-white'
                  : 'bg-white hover:bg-gray-200 text-gray-800'
              }
            `}
          >
            {editingId === conv.conversation_id ? (
              <>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleRenameSave(conv.conversation_id);
                    if (e.key === 'Escape') handleRenameCancel();
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="text-sm px-2 py-1 rounded border border-gray-300 text-gray-800 min-w-[150px]"
                  autoFocus
                />
                <button
                  onClick={(e) => handleRenameSave(conv.conversation_id, e)}
                  className="hover:bg-white/20 rounded p-1"
                  title="Save"
                >
                  <Check size={14} />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRenameCancel();
                  }}
                  className="hover:bg-white/20 rounded p-1"
                  title="Cancel"
                >
                  <X size={14} />
                </button>
              </>
            ) : (
              <>
                <span className="text-sm">{getTitle(conv)}</span>
                {onPin && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onPin(conv.conversation_id, true);
                    }}
                    className="hover:bg-white/20 rounded p-1"
                    title="Pin"
                  >
                    <Pin size={14} />
                  </button>
                )}
                {onRename && (
                  <button
                    onClick={(e) => handleRenameStart(conv, e)}
                    className="hover:bg-white/20 rounded p-1"
                    title="Rename"
                  >
                    <Edit2 size={14} />
                  </button>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(conv.conversation_id);
                  }}
                  className="hover:bg-white/20 rounded p-1"
                  title="Delete"
                >
                  <X size={14} />
                </button>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

