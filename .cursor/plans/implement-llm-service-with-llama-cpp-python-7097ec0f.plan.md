<!-- 7097ec0f-e097-4bc1-90f6-9562de0c86ca edf2e409-593b-4590-945a-7a8b505f0f03 -->
# Memory Service, Tool System, and LLM Hot-Loading

## Overview

Refactor the architecture to: create a dedicated Memory/Context service, implement automatic vector retrieval during chat, add editable system prompts, build a comprehensive tool system, and improve LLM service management in the launcher.

## Architecture Changes

### Current State

- Gateway handles: routing, memory store, tool manager, LLM server management
- LLM service: hot-loadable by Gateway when model is loaded
- Memory: integrated in Gateway
- Tools: Basic/minimal implementation

### Target State

- **Gateway**: API routing, LLM server management, tool orchestration
- **Memory Service** (new): Vector store, conversation management, context retrieval, character/user profiles
- **Tool Service** (new): Tool registry, execution handlers, sandboxed code execution
- **LLM Service**: Inference only (hot-loadable, no start button needed)
- **System Prompt**: Stored in shared database, editable via frontend
- **Database**: Shared SQLite (`data/assistant.db`) for all services

## Implementation Steps

### Phase 1: LLM Launcher Updates

#### 1.1 Remove LLM Start Button from Launcher

- **File**: [launcher/launcher.py](launcher/launcher.py)
- **Changes**:
  - Hide/disable "Start" button for LLM service
  - Show status as "READY" when installed (green indicator)
  - Add tooltip explaining LLM is managed by Gateway

### Phase 2: Memory Service

#### 2.1 Create Memory Service Structure

- **New Directory**: `services/memory/`
- **Port**: 8005
- **Files**:
  - `main.py` - FastAPI application
  - `src/memory/store.py` - Database operations (shared SQLite)
  - `src/memory/vector_store.py` - ChromaDB operations
  - `src/memory/retrieval.py` - Context retrieval logic
  - `src/memory/conversations.py` - Conversation CRUD
  - `src/memory/profiles.py` - Character/user profiles
  - `src/api/routes.py` - API endpoints
  - `requirements.txt`, `README.md`

#### 2.2 Implement Automatic Vector Retrieval

- On every chat message, query vector store for similar past messages
- Return context if similarity > threshold (default: 0.7)
- Gateway injects context into system prompt before proxying to LLM

#### 2.3 Add System Prompt Management

- **Endpoints**: `GET/POST /api/settings/system-prompt`
- **Database**: Add `system_prompts` table to shared database
- **Frontend**: Add System Prompt editor in SettingsPanel

#### 2.4 Migrate Existing Memory Code

- Move from `services/gateway/src/services/memory/` to `services/memory/`
- Update Gateway to use HTTP client calls to Memory service

### Phase 3: Tool System

#### 3.1 Create Tool Service Structure

- **New Directory**: `services/tools/`
- **Port**: 8006
- **Files**:
  - `main.py` - FastAPI application
  - `src/tools/registry.py` - Tool registration and discovery
  - `src/tools/executor.py` - Tool execution orchestrator
  - `src/tools/sandbox.py` - Sandboxed code execution (Docker/subprocess)
  - `src/tools/builtin/` - Built-in tool implementations
  - `src/api/routes.py` - API endpoints

#### 3.2 Implement Tool Registry

- OpenAI function calling format for tool definitions
- Dynamic tool registration/discovery
- Tool enable/disable per conversation or globally

#### 3.3 Built-in Tools Implementation

| Tool | Description | Implementation |

|------|-------------|----------------|

| **Web Search** | Search internet via DuckDuckGo/SearXNG | `src/tools/builtin/web_search.py` |

| **Code Execution** | Run Python/JS in sandbox | `src/tools/builtin/code_exec.py` |

| **File Access** | Read/write files in workspace | `src/tools/builtin/file_access.py` |

| **Memory Tools** | Explicit save/recall memories | `src/tools/builtin/memory.py` |

| **Calendar** | Reminders, scheduling | `src/tools/builtin/calendar.py` |

#### 3.4 Tool Execution Flow

1. LLM returns tool call request
2. Gateway intercepts, sends to Tool Service
3. Tool Service executes, returns result
4. Gateway sends result back to LLM for final response

### Phase 4: Gateway Integration

#### 4.1 Update Gateway Routes

- **File**: [services/gateway/src/api/routes.py](services/gateway/src/api/routes.py)
- Before `/v1/chat/completions`:

  1. Call Memory service for context retrieval
  2. Inject system prompt and context
  3. Proxy to LLM with tool definitions
  4. Handle tool calls via Tool service
  5. Save messages to Memory service

#### 4.2 Add Service Clients

- Memory service client (HTTP)
- Tool service client (HTTP)
- Graceful fallback if services unavailable

### Phase 5: Frontend Updates

#### 5.1 Settings Panel Updates

- System Prompt editor (textarea, save, reset)
- Tool enable/disable toggles
- Memory/context settings (similarity threshold, top-k)

#### 5.2 Chat Interface Updates

- Tool call visualization (show when tools are used)
- Memory context indicator (show when context retrieved)
- File upload support (drag-and-drop or button)
  - Upload files to `data/files/` via Gateway endpoint
  - Display uploaded files in chat
  - Allow LLM to process uploaded files via file access tool

### Phase 6: Launcher Integration

- Add Memory service (port 8005, required)
- Add Tool service (port 8006, optional)
- Update LLM service status handling

## Database Schema Additions

```sql
-- System prompts (in shared data/assistant.db)
CREATE TABLE system_prompts (
    id TEXT PRIMARY KEY,
    name TEXT,
    content TEXT NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Calendar/reminders
CREATE TABLE reminders (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    due_at TIMESTAMP,
    repeat_rule TEXT,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tool execution logs
CREATE TABLE tool_executions (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    tool_name TEXT NOT NULL,
    input_params TEXT,
    output_result TEXT,
    status TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## API Specifications

### Memory Service (port 8005)

```
POST /api/memory/retrieve-context
POST /api/memory/save-message
GET/POST/PUT/DELETE /api/conversations
GET/POST/PUT/DELETE /api/profiles/characters
GET/POST /api/profiles/user
```

### Tool Service (port 8006)

```
GET /api/tools - List available tools
POST /api/tools/execute - Execute a tool
GET /api/tools/{name}/schema - Get tool schema
POST /api/reminders - Create reminder
GET /api/reminders - List reminders
```

## Files to Create

1. `services/memory/` - Entire new service
2. `services/tools/` - Entire new service
3. Tool implementations in `services/tools/src/tools/builtin/`

## Files to Modify

1. [launcher/launcher.py](launcher/launcher.py) - LLM start button, add new services
2. [launcher/manager.py](launcher/manager.py) - Add memory and tool service configs
3. [services/gateway/src/api/routes.py](services/gateway/src/api/routes.py) - Integration with new services
4. [services/gateway/src/services/service_manager.py](services/gateway/src/services/service_manager.py) - Add service clients
5. [services/frontend/components/SettingsPanel.tsx](services/frontend/components/SettingsPanel.tsx) - System prompt, tool settings
6. [services/frontend/lib/api.ts](services/frontend/lib/api.ts) - New API methods

## Testing Checklist

- [ ] Memory service starts independently
- [ ] Tool service starts independently
- [ ] Automatic context retrieval works
- [ ] System prompt is editable and persists
- [ ] Web search tool works
- [ ] Code execution runs in sandbox safely
- [ ] File access respects permissions
- [ ] Memory tools save/recall correctly
- [ ] Calendar/reminders work
- [ ] LLM shows "READY" status in launcher
- [ ] Tool calls are visualized in frontend

### To-dos

- [ ] Remove/disable LLM Start button, show READY status when installed
- [ ] Create Memory service structure (main.py, routes, store, vector_store, retrieval)
- [ ] Implement automatic vector retrieval with similarity threshold
- [ ] Add system prompt management (API endpoints, database table, frontend UI)
- [ ] Migrate memory code from Gateway to Memory service
- [ ] Create Tool service structure (main.py, registry, executor, sandbox)
- [ ] Implement web search tool (DuckDuckGo/SearXNG integration)
- [ ] Implement sandboxed code execution tool (Python/JS)
- [ ] Implement file access tool with permission controls
- [ ] Implement explicit memory save/recall tools
- [ ] Implement calendar/reminder tool with database storage
- [ ] Update Gateway to orchestrate Memory and Tool services
- [ ] Update frontend: system prompt editor, tool toggles, tool call visualization
- [ ] Add Memory and Tool services to launcher with install/start commands