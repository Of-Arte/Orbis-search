# Orbis Search

Orbis Search is a lightweight, privacy-first semantic code search MCP server that gives AI coding agents and developers instant, structured access to any codebase — no cloud required.

Built as a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server, Orbis integrates directly with AI-powered tools like Claude Desktop, Cursor, and Antigravity to provide real-time code context on demand.

## The Problem: Agents Start Blind

Every time a coding agent (Claude, Cursor, Copilot, etc.) starts a new session, **it has zero memory of your codebase**. It can't remember where `UserModel` is defined, how authentication is wired together, or which module owns a given piece of logic. Without grounding, agents hallucinate file paths, duplicate existing code, and require you to manually paste context into every conversation.

Orbis Search solves this by acting as a persistent, queryable memory layer for your project:

```
Agent: "Where is the payment processing logic?"
Orbis: → src/payments/processor.py (lines 42-89), src/api/checkout.py (lines 12-31)
```

Instead of starting blind, the agent searches the indexed codebase and gets precise, relevant file chunks — in under 300ms.

## Key Benefits

- **Agent-Ready**: Gives coding agents codebase memory across sessions — no more starting from scratch
- **Privacy-First**: Fully offline local embeddings, no data leaves your machine
- **Zero Cost**: Free forever with local provider, no API keys required
- **Smart Performance**: Auto-detects symbols for 200x faster lookups
- **Minimal Footprint**: 98% smaller cache than JSON-based alternatives
- **MCP Native**: Drop-in integration with modern AI development tools

## Features

| Feature | Description | Speed |
|---------|-------------|-------|
| **Keyword Search** | Exact symbols (`UserModel`, `calculate_tax`) | ~1ms |
| **Semantic Search** | Concepts ("authentication logic", "error handling") | ~200-300ms |
| **Auto-Pilot Mode** | Detects query type and optimizes automatically | Smart |

## Use Cases

* **AI Coding Agent Context**: Give agents like Claude or Cursor a live map of your repo. Agents call `search_codebase()` at session start or on demand to ground themselves in your actual code — eliminating hallucinated paths and duplicate implementations.
* **Legacy Code Discovery**: Quickly find implementation patterns ("How do we handle OAuth?") in unfamiliar repositories you've inherited or just cloned.
* **IDE Context Enhancement**: Provide real-time codebase context to MCP-compatible LLMs (Antigravity, Cursor, etc.) without manual copy-pasting.
* **Privacy-First Dev**: Use `provider="local"` for fully offline, air-gapped semantic search — nothing hits external APIs.
* **Large-Scale Symbol Jump**: Instantly find exact matches (~1ms) across projects where `grep` is too slow or too "noisy."

## Limitations

* **Workspace Level**: Designed for individual project repositories. It is **not** a drive-wide desktop search engine.
* **Memory Bound**: RAM usage scales linearly with the number of indexed chunks. High-end repositories (1M+ lines) may require significant memory.

## Installation

```powershell
# Clone/navigate to project
cd orbis-search

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install with local embeddings (default, FREE)
pip install -e ".[local]"

# OR install with cloud providers (optional)
pip install -e ".[all]"  # Includes Gemini, OpenAI, Local
```

## MCP Configuration (Antigravity / Claude Desktop)

To use Orbis-search with MCP-compatible IDEs like Antigravity or Claude Desktop, add this to your MCP config file:

**Location:**
- Antigravity: `~/.gemini/antigravity/mcp_config.json` (or `%USERPROFILE%\.gemini\antigravity\mcp_config.json` on Windows)
- Claude Desktop: `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)

**Configuration:**
```json
{
  "mcpServers": {
    "orbis-search": {
      "command": "/absolute/path/to/orbis-search/.venv/Scripts/python.exe",
      "args": [
        "-m",
        "orbis_search.server"
      ]
    }
  }
}
```

> **Important:** Replace `/absolute/path/to/orbis-search/` with the actual path to your installation (e.g., `C:\\Users\\YourName\\Projects\\orbis-search\\` on Windows or `/home/yourname/projects/orbis-search/` on Linux/Mac).

On Windows, use double backslashes (`\\`) in the path, or forward slashes work too.

## Quick Start

### 1. Start the MCP Server (if not using IDE integration)

```powershell
python -m orbis_search.server
```

Note: If you configured the MCP server in your IDE (above), it will start automatically. You don't need to run this command manually.

### 2. Index Your Codebase

```python
# Via MCP tool
index_codebase()  # Uses local embeddings (free, offline)
```

### 3. Search

```python
# Keyword search (fast)
search_codebase("UserModel", keyword_only=True)

# Semantic search (conceptual)
search_codebase("authentication logic")

# Auto-pilot (detects best mode)
search_codebase("calculate_tax")  # Auto-optimizes to keyword (~1ms)
```

## Embedding Providers

> **Default: Local Embeddings** - No API keys or costs required!

| Provider | Cost | Latency (150 chunks) | Setup |
|----------|------|---------------------|-------|
| **local** (default) | **FREE** | 60-120s | `pip install -e ".[local]"` |
| gemini | Free tier → paid | ~45s | Set `GEMINI_API_KEY` |
| openai | Paid | ~45s | Set `OPENAI_API_KEY` |
| keyword | **FREE** | ~0.2s | No embeddings |

### Using Cloud Providers

```bash
# Set API key
export GEMINI_API_KEY="your-key-here"  # Linux/Mac
set GEMINI_API_KEY=your-key-here       # Windows

# Index with Gemini
index_codebase(provider="gemini")
```

### Cost Details

- **Local**: FREE forever, ~400MB model downloads on first run
- **Gemini**: Free tier (15 RPM), then $0.00025/1K tokens
- **OpenAI**: $0.0001/1K tokens for `text-embedding-3-small`
- **Keyword**: FREE, no embeddings (exact match only)

## API Reference

### `index_codebase(path=".", provider="local")`

Index your codebase for search.

**Parameters:**
- `path`: Directory to index (default: current directory)
- `provider`: `"local"` (default), `"gemini"`, `"openai"`, `"keyword"`, or `"auto"`

**Returns:** Status message with chunk count

### `search_codebase(query, top_k=5, keyword_only=False)`

Search indexed codebase.

**Parameters:**
- `query`: Search query (symbol or concept)
- `top_k`: Number of results to return
- `keyword_only`: Force keyword-only search (faster)

**Returns:** Formatted search results

### `check_health()`

Check server status and indexer state.

## Examples

### Example 1: Agent Orientation at Session Start

```python
# Agent calls this at the start of a new session to orient itself
search_codebase("entry point main application startup")
search_codebase("database models schema")
search_codebase("API routes endpoints")
```

### Example 2: Symbol Lookup (Fast)

```python
# Auto-pilot detects symbol pattern → keyword search (~1ms)
search_codebase("HttpClient")
search_codebase("authenticate()")
search_codebase("MAX_RETRIES")
```

### Example 3: Conceptual Search

```python
# Semantic search finds related concepts
search_codebase("database connection pooling")
search_codebase("error handling patterns")
search_codebase("user authentication flow")
```

### Example 4: Mixed Workflow

```python
# 1. Quick symbol check
search_codebase("UserModel", keyword_only=True)  # ~1ms

# 2. Find related code
search_codebase("user management logic")  # ~240ms, broader context
```

## Configuration

### File Extensions Indexed

`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.go`, `.rs`, `.java`, `.cpp`, `.c`, `.md`, `.txt`

### Excluded Directories

`node_modules`, `__pycache__`, `.git`, `dist`, `build`, `.venv`, `venv`

### Customization

Edit `IndexConfig` in your code:

```python
from orbis_search.search_engine import IndexConfig, CodebaseIndexer

config = IndexConfig(
    root_path="./my-project",
    extensions=[".py", ".js"],  # Only Python and JavaScript
    exclude_patterns=["tests", "docs"]
)
indexer = CodebaseIndexer(config)
```

## Architecture

```
orbis_search/
├── search_engine.py  # Core: Indexer, HybridSearch, Providers
└── server.py         # MCP: Tools and auto-pilot logic
```

**Key Components:**
- `CodebaseIndexer` - File scanning, chunking, embedding generation
- `HybridSearch` - Combines semantic + keyword scoring
- `LocalEmbedding` - Default provider (sentence-transformers)
- `GeminiEmbedding` / `OpenAIEmbedding` - Cloud providers

### Technical Constraints & Scaling

* **In-Memory Retrieval**: The server loads the entire index (`index.bin`) into RAM. While keyword lookups are O(1), semantic searches are O(N) where N is the number of chunks.
* **Lazy Content Loading**: To minimize footprint, Orbis-Search does **not** store full source code in the cache. It stores metadata and hashes, reading the actual file from disk only when a search result is generated.
* **Binary Serialization**: Uses `pickle` for the index to ensure 10-50x faster load times compared to JSON.

## Development

```powershell
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run specific test
pytest tests/test_search_engine.py::TestHybridSearch -v
```

## License

MIT
