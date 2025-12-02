# Tool Service

Tool execution and management service for Personal Assistant.

## Overview

The Tool Service provides:
- **Tool Registry**: Dynamic tool registration and discovery
- **Tool Execution**: Safe execution of tools with error handling
- **Built-in Tools**: Web search, code execution, file access, memory tools, calendar
- **Sandboxed Execution**: Code execution in isolated environments

## Port

Runs on port **8006**.

## Built-in Tools

### 1. Web Search (`web_search`)
Search the internet using DuckDuckGo.

### 2. Code Execution (`execute_code`)
Execute Python or JavaScript code in a sandboxed environment.

### 3. File Access (`file_access`)
Read, write, list, and delete files in `data/files/` directory (sandboxed).

### 4. Memory Tools (`memory`)
Explicitly save and recall memories via Memory service.

### 5. Calendar (`calendar`)
Create, list, and manage calendar reminders.

## API Endpoints

### Tools
- `GET /api/tools` - List all available tools
- `GET /api/tools/{tool_name}/schema` - Get tool schema
- `POST /api/tools/execute` - Execute a tool

### Reminders
- `POST /api/reminders` - Create a reminder
- `GET /api/reminders` - List all reminders

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
uvicorn main:app --host 0.0.0.0 --port 8006
```

## Configuration

Settings can be configured via environment variables or `.env` file:
- `PORT` - Service port (default: 8006)
- `DEBUG` - Debug mode (default: False)
- `ENABLE_CODE_EXECUTION` - Enable code execution (default: True)
- `ENABLE_FILE_ACCESS` - Enable file access (default: True)
- `ENABLE_WEB_SEARCH` - Enable web search (default: True)
- `MAX_CODE_EXECUTION_TIME` - Max execution time in seconds (default: 30)
- `MAX_FILE_SIZE` - Max file size in bytes (default: 10MB)

