'use client';

import { Plus, X, Edit2, Check } from 'lucide-react';
import { useState } from 'react';

interface ConversationTabsProps {
  conversations: any[];
  currentId: string | null;
  onNew: () => void;
  onSwitch: (id: string) => void;
  onDelete: (id: string) => void;
  onRename?: (id: string, newName: string) => void;
}

export default function ConversationTabs({
  conversations,
  currentId,
  onNew,
  onSwitch,
  onDelete,
  onRename,
}: ConversationTabsProps) {
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
      <div className="flex gap-2 overflow-x-auto flex-1">
        {conversations.map((conv) => (
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

