# Conversation Storage System - Complete Architecture

## Overview
The system uses **file-based JSON storage** for conversations and settings. No SQLite databases are used for conversations anymore.

## Storage Locations

### Conversations
- **Directory**: `data/memory/conversations/`
- **Files**: 
  - `index.json` - Fast metadata index (conversation IDs, names, timestamps, pinned status)
  - `{conversation_id}.json` - Individual conversation files with full message history

### Settings
- **File**: `data/memory/settings.json`
- **Encryption Key**: `data/memory/.encryption_key` (for sensitive settings)

### Vector Store
- **Type**: ChromaDB
- **Location**: Managed by ChromaDB (persistent storage)
- **Purpose**: Semantic search across all conversations

## Data Flow

### 1. Frontend → Backend (Loading Conversations)

```
Frontend (page.tsx)
  ↓
api.getConversations() (lib/api.ts)
  ↓
GET /api/conversations (routes.py:418)
  ↓
service_manager.memory_store.list_conversations()
  ↓
MemoryStore.list_conversations() (store.py:180)
  ↓
FileConversationStore.list_conversations() (file_store.py:160)
  ↓
Reads index.json (file_store.py:27)
  ↓
Returns conversation metadata (no messages loaded)
```

**Performance**: Should be **instant** (< 100ms) because:
- Only reads one small JSON file (`index.json`)
- No database queries
- No message loading (messages loaded on-demand when conversation selected)

### 2. Saving a Conversation

```
User sends message
  ↓
POST /v1/chat/completions (routes.py:3117)
  ↓
After response stream completes:
  background_tasks.add_task(save_messages_to_vector_store)
  ↓
save_messages_to_vector_store() (routes.py:3076)
  ↓
service_manager.memory_store.store_conversation()
  ↓
MemoryStore.store_conversation() (store.py:67)
  ↓
FileConversationStore.save_conversation() (file_store.py:87)
  ↓
1. Saves {conversation_id}.json with full messages
2. Updates index.json with metadata
```

### 3. Loading a Specific Conversation

```
Frontend selects conversation
  ↓
api.getConversation(conversation_id) (lib/api.ts)
  ↓
GET /api/conversations/{conversation_id} (routes.py:491)
  ↓
service_manager.memory_store.get_conversation(conversation_id)
  ↓
MemoryStore.get_conversation() (store.py:161)
  ↓
FileConversationStore.get_conversation() (file_store.py:54)
  ↓
Reads {conversation_id}.json
  ↓
Returns messages array
```

## Key Components

### FileConversationStore (`services/gateway/src/services/memory/file_store.py`)
- **Purpose**: Fast file-based conversation storage
- **Methods**:
  - `list_conversations()` - Reads from `index.json` (very fast)
  - `get_conversation(id)` - Reads individual conversation file
  - `save_conversation(id, messages)` - Saves conversation file + updates index
  - `clear_all()` - Deletes all conversation files and resets index

### FileSettingsStore (`services/gateway/src/services/memory/settings_store.py`)
- **Purpose**: Fast file-based settings storage
- **Methods**:
  - `get_setting(key)` - Gets setting from `settings.json`
  - `set_setting(key, value)` - Updates `settings.json`
  - `clear_all()` - Deletes `settings.json` and resets cache

### MemoryStore (`services/gateway/src/services/memory/store.py`)
- **Purpose**: High-level interface combining file store, settings store, and vector store
- **Initialization**: Creates FileConversationStore, FileSettingsStore, and VectorStore
- **Uses**: Direct file access (no separate memory service needed)

## Why Conversations Load Slowly

### Root Cause
The gateway was using `MemoryServiceClient` (HTTP client) which tried to connect to a separate memory service on port 8005. Since that service isn't running, it would:
1. Try to connect (timeout after 30 seconds)
2. Fall back to empty results or errors
3. Cause slow loading

### Fix Applied
Changed `service_manager.py` to use `MemoryStore` directly instead of `MemoryServiceClient`:
- **Before**: `self.memory_store = MemoryServiceClient()` (HTTP client)
- **After**: `self.memory_store = MemoryStore()` (direct file access)

## Why Conversations Duplicate

### Possible Causes
1. **Index corruption**: If `index.json` gets corrupted, entries might duplicate
2. **Race conditions**: Multiple processes writing to index simultaneously
3. **Stale entries**: Old entries in index pointing to deleted files

### Auto-Fix Mechanism
The `list_conversations()` method automatically:
1. Checks if each indexed conversation file exists
2. Removes stale entries (indexed but file missing)
3. Saves cleaned index back to disk

## Reset App State

The `/api/reset` endpoint clears:
1. **Conversations**: Deletes all `{id}.json` files and resets `index.json`
2. **Settings**: Deletes `settings.json` and resets cache
3. **Vector Store**: Clears all ChromaDB entries
4. **Preserves**: Downloaded models in `data/models/`

## Performance Expectations

- **List conversations**: < 100ms (reads single small JSON file)
- **Load conversation**: < 50ms per conversation (reads single JSON file)
- **Save conversation**: < 200ms (writes JSON file + updates index)

## Troubleshooting

### Conversations not loading
1. Check `data/memory/conversations/index.json` exists
2. Check file permissions
3. Check gateway logs for errors

### Conversations duplicating
1. Use "Reset App State" button in launcher
2. Or manually delete `data/memory/conversations/` and restart

### Slow loading
1. Ensure gateway is using `MemoryStore` not `MemoryServiceClient`
2. Check `index.json` size (should be < 1MB for thousands of conversations)
3. Check disk I/O performance

