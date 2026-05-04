# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Install dependencies (from project root)
uv sync

# Start the server (from project root)
./run.sh

# Or manually
cd backend && uv run uvicorn app:app --reload --port 8000
```

The app serves at `http://localhost:8000`. Swagger UI at `http://localhost:8000/docs`.

Requires a `.env` file in the project root:
```
ANTHROPIC_API_KEY=your_key_here
```

## Architecture

This is a full-stack RAG chatbot. The frontend is plain HTML/JS/CSS served as static files by FastAPI. All backend modules live in `backend/` and are run from that directory (imports are relative, no package structure).

### Query flow

1. **Frontend** (`frontend/script.js`) — POSTs `{ query, session_id }` to `/api/query`, renders the response with `marked.parse()` for markdown.
2. **FastAPI** (`backend/app.py`) — Creates a session if needed, delegates to `RAGSystem.query()`.
3. **RAGSystem** (`backend/rag_system.py`) — Central orchestrator. Fetches conversation history, calls `AIGenerator`, retrieves sources from `ToolManager` after the response, and saves the exchange back to session history.
4. **AIGenerator** (`backend/ai_generator.py`) — Makes a first Claude API call with the `search_course_content` tool available. If Claude decides to search (`stop_reason == "tool_use"`), executes the tool and makes a second API call to synthesize results into a final answer.
5. **CourseSearchTool / ToolManager** (`backend/search_tools.py`) — Wraps `VectorStore.search()`. `ToolManager` is designed to hold multiple tools; `CourseSearchTool` is the only one currently registered.
6. **VectorStore** (`backend/vector_store.py`) — ChromaDB with two collections: `course_catalog` (course titles/metadata, used for fuzzy course name resolution) and `course_content` (lesson text chunks, used for semantic search). Embeddings use `all-MiniLM-L6-v2` via `sentence-transformers`.

### Document ingestion (startup)

`app.py` calls `RAGSystem.add_course_folder("../docs")` on startup. Each `.txt` file in `docs/` is parsed by `DocumentProcessor` (`backend/document_processor.py`):
- First 3 lines: `Course Title:`, `Course Link:`, `Course Instructor:`
- Body: split on `Lesson N: <title>` markers, optional `Lesson Link:` on the next line
- Each lesson's text is chunked into ~800-char sentence-aware chunks with ~100-char overlap
- Chunks are stored in ChromaDB; already-existing courses (matched by title) are skipped

### Configuration

All tunable values are in `backend/config.py` (`Config` dataclass): model name, embedding model, chunk size/overlap, max search results (5), max conversation history (2 exchanges), and ChromaDB path (`./chroma_db` relative to `backend/`).

### Extending tools

To add a new Claude tool: subclass `Tool` in `search_tools.py`, implement `get_tool_definition()` (Anthropic tool schema) and `execute()`, then register with `tool_manager.register_tool(your_tool)` in `RAGSystem.__init__`.

### Document format

Course files must follow this structure for proper parsing:
```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 1: <lesson title>
Lesson Link: <url>
<lesson content...>

Lesson 2: <lesson title>
...
```
