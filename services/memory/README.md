# Memory Service

Memory and context management service for Personal Assistant.

## Overview

The Memory Service provides:
- **Vector Store**: Semantic search using ChromaDB
- **Conversation Management**: Store and retrieve conversation history
- **Context Retrieval**: Automatic retrieval of relevant past conversations
- **System Prompts**: Editable and savable system prompts
- **Shared Database**: Uses `data/assistant.db` for all services

## Port

Runs on port **8005**.

## API Endpoints

### Memory/Context
- `POST /api/memory/retrieve-context` - Retrieve relevant context for a query
- `POST /api/memory/save-message` - Save messages to memory

### Conversations
- `GET /api/conversations` - List all conversations
- `GET /api/conversations/{conversation_id}` - Get a specific conversation
- `DELETE /api/conversations/{conversation_id}` - Delete a conversation
- `PUT /api/conversations/{conversation_id}/name` - Set conversation name

### System Prompts
- `GET /api/settings/system-prompt` - Get system prompt (default if no ID)
- `POST /api/settings/system-prompt` - Create system prompt
- `PUT /api/settings/system-prompt/{prompt_id}` - Update system prompt
- `GET /api/settings/system-prompts` - List all system prompts
- `DELETE /api/settings/system-prompt/{prompt_id}` - Delete system prompt

### Profiles (TODO)
- `GET /api/profiles/characters` - List character profiles
- `POST /api/profiles/characters` - Create character profile
- `GET /api/profiles/user` - Get user profile
- `POST /api/profiles/user` - Set user profile

## Database

Uses shared SQLite database at `data/assistant.db` with tables:
- `conversations` - Conversation metadata
- `messages` - Individual messages
- `system_prompts` - System prompts
- `app_settings` - Application settings

## Vector Store

Uses ChromaDB for semantic search, stored in `data/vector_store/`.

## Installation

Install dependencies:
```bash
pip install -r requirements.txt
```

## Running

Start the service:
```bash
python main.py
```

Or with uvicorn:
```bash
uvicorn main:app --host 0.0.0.0 --port 8005
```

## Configuration

Settings can be configured via environment variables or `.env` file:
- `PORT` - Service port (default: 8005)
- `DEBUG` - Debug mode (default: False)
- `EMBEDDING_MODEL` - Embedding model name (default: all-MiniLM-L6-v2)
- `VECTOR_STORE_TYPE` - Vector store type (default: chromadb)
- `CONTEXT_RETRIEVAL_TOP_K` - Default top-k for context retrieval (default: 5)
- `CONTEXT_SIMILARITY_THRESHOLD` - Minimum similarity score (default: 0.7)

