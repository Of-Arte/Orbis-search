# Orbis Search

Orbis Search is a lightweight, semantic code search MCP server that gives AI coding agents and developers instant, structured access to any codebase.

## Features

| Feature | Description | Speed |
|---------|-------------|-------|
| **Keyword Search** | Exact symbols (`UserModel`, `calculate_tax`) | ~1ms |
| **Semantic Search** | Concepts ("authentication logic", "error handling") | ~200-300ms |
| **Hybrid Search** | Detects query type and optimizes automatically | Auto |

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

## MCP Configuration (Antigravity / Claude Code)

To use Orbis-search with MCP-compatible tools like Antigravity or Claude Code, add this to your MCP config file:
- Antigravity: `~/.gemini/antigravity/mcp_config.json` (or `%USERPROFILE%\.gemini\antigravity\mcp_config.json` on Windows)
- Claude Code: `~/.claude/claude_code_config.json` (Mac/Linux) or `%APPDATA%\Claude\claude_code_config.json` (Windows)

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

Note: If you configured the MCP server in your IDE (above), it will start automatically. You don't need to run these command manually.

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
## Examples

### Example 1: Agent Orientation at Session Start

**User:**  
"I'm starting a new project. Can you help me understand the main entry point and overall structure?"

**Agent:**  
"Sure! I'll search for the main entry point, database models, and API routes to give you a full overview."

*Agent internally performs:*
```python
search_codebase("entry point main application startup")
search_codebase("database models schema")
search_codebase("API routes endpoints")
```

---

### Example 2: Quick Symbol Lookup

**User:**  
"Where is `HttpClient` used in the codebase?"

**Agent:**  
"I'll do a fast keyword search to find all instances of `HttpClient`."

*Agent internally performs:*
```python
search_codebase("HttpClient", keyword_only=True)
search_codebase("authenticate()")
search_codebase("MAX_RETRIES")
```

---

### Example 3: Conceptual Search

**User:**  
"How does the app handle database connections and errors?"

**Agent:**  
"I'll look for patterns related to connection pooling and error handling across the project."

*Agent internally performs:*
```python
search_codebase("database connection pooling")
search_codebase("error handling patterns")
search_codebase("user authentication flow")
```

---

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

### Technical Constraints & Scaling

* **In-Memory Retrieval**: The server loads the entire index (`index.bin`) into RAM. While keyword lookups are O(1), semantic searches are O(N) where N is the number of chunks.
* **Lazy Content Loading**: To minimize footprint, Orbis-Search does **not** store full source code in the cache. It stores metadata and hashes, reading the actual file from disk only when a search result is generated.
* **Binary Serialization**: Uses `pickle` for the index to ensure 10-50x faster load times compared to JSON.

## License

MIT
