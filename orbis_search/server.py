"""
Orbis-Search MCP Server

FastMCP server exposing hybrid search functionality.
"""

import sys
import os
import logging
import asyncio
import re
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from orbis_search.search_engine import (
    CodebaseIndexer,
    HybridSearch,
    IndexConfig,
    get_embedding_provider
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("OrbisSearch")

# Initialize FastMCP server
mcp = FastMCP("Orbis-Search v1.0.0")

# Global indexer (lazy-loaded)
_indexer: Optional[CodebaseIndexer] = None


# ============================================================================
# Helper Functions
# ============================================================================

def get_indexer() -> CodebaseIndexer:
    """Lazy-load indexer instance."""
    global _indexer
    if _indexer is None:
        logger.info("📚 Initializing Codebase Indexer...")
        config = IndexConfig()
        _indexer = CodebaseIndexer(config)
        _indexer.load_cache()  # Try to load existing index
    return _indexer


def _is_likely_symbol(query: str) -> bool:
    """
    Heuristic to detect if query looks like an exact symbol.
    Used to auto-suggest keyword-only search for better performance.
    """
    query = query.strip()
    
    # Check common symbol patterns
    patterns = [
        r'^[A-Z][a-zA-Z0-9]+$',                # CamelCase: UserModel, HttpClient
        r'^[a-z_][a-z0-9_]+$',                 # snake_case: user_model, calculate_tax
        r'^[a-z_][a-z0-9_]*\(\)$',            # function(): authenticate(), get_user()
        r'^\.\w+$',                            # .method: .save, .validate
        r'^[A-Z][A-Z_0-9]+$',                  # CONSTANTS: MAX_SIZE, API_KEY
    ]
    
    return any(re.match(p, query) for p in patterns)


# ============================================================================
# MCP Tools
# ============================================================================

@mcp.tool()
async def search_codebase(query: str, top_k: int = 5, keyword_only: bool = False) -> str:
    """
    Search the codebase using hybrid semantic + keyword search.
    
    **Search Strategy (auto-suggested):**
    
    Use keyword_only=True (⚡ ~1ms) for exact symbols:
    - Class names: "UserModel", "HttpClient"
    - Function names: "calculate_tax", "authenticate()"
    - Variable names: "user_id", "config_path"
    - Constants: "MAX_SIZE", "API_KEY"
    
    Use semantic (default, ~200-300ms) for concepts:
    - "authentication logic" → finds OAuth, JWT, sessions
    - "database pooling" → finds connection managers
    - "error handling patterns" → finds try/catch, Result types
    - "user management" → finds profiles, accounts, permissions
    
    **Performance:**
    - Keyword: ~1ms (indexed hash lookup)
    - Semantic: ~200-300ms (embedding computation)
    - Trade-off: 200ms for conceptual understanding vs exact matching
    
    **When to use:**
    - Finding functions/classes by description: "authentication logic"
    - Locating implementation of features: "payment processing"
    - Discovering patterns: "error handling"
    - Quick symbol lookups: "UserModel"
    
    **Examples:**
    ```
    # Fast keyword search for exact symbols
    search_codebase("UserModel", keyword_only=True)  # ~1ms
    search_codebase("calculate_tax", keyword_only=True)  # ~1ms
    
    # Semantic search for concepts
    search_codebase("authentication logic")  # ~240ms, finds OAuth, JWT
    search_codebase("database connection pooling")  # understands intent
    
    # Get more results
    search_codebase("error handling", top_k=10)
    ```
    
    Args:
        query: Natural language description or exact keywords
        top_k: Number of results to return (1-50, default 5)
        keyword_only: Skip semantic matching for faster literal searches
        
    Returns:
        Formatted search results with file paths, line numbers, scores, and code snippets
    """
    
    def _blocking_search():
        """Run the actual search in a thread to avoid blocking the event loop."""
        indexer = get_indexer()
        
        if not indexer.chunks:
            return "⚠️ No index found. Please run `index_codebase()` first."
        
        # Check if query looks like a symbol (auto-suggest keyword_only)
        is_symbol = _is_likely_symbol(query)
        
        # ACTIVE GOVERNANCE: Auto-Pilot
        if is_symbol and not keyword_only:
            logger.info(f"⚡ Auto-Pilot: Detected symbol '{query}'. Attempting keyword search optimization...")
            searcher = HybridSearch(indexer, None)
            keyword_results = searcher.keyword_search(query, top_k=top_k)
            
            if keyword_results:
                result_lines = [f"⚡ Auto-optimized to keyword search (~1ms) for symbol '{query}'.\nFound {len(keyword_results)} results:\n"]
                for i, result in enumerate(keyword_results, 1):
                    result_lines.append(f"{i}. {result.file_path}:{result.start_line}-{result.end_line}")
                    result_lines.append(f"   Score: {result.score:.3f}")
                    result_lines.append(f"   {result.content[:200]}...\n")
                return "\n".join(result_lines)
            
            logger.info("Auto-Pilot: No keyword matches found. Falling back to semantic search.")

        # Get embedding provider for hybrid search (optional)
        embed_provider = None
        if not keyword_only:
            has_embeddings = any(c.embedding is not None for c in indexer.chunks)
            if has_embeddings:
                try:
                    embed_provider = get_embedding_provider("local")
                except Exception as e:
                    logger.warning(f"Embedding provider unavailable: {e}, falling back to keyword search")
        
        # Perform search
        searcher = HybridSearch(indexer, embed_provider)
        
        if keyword_only:
            results = searcher.keyword_search(query, top_k=top_k)
        else:
            results = searcher.search(query, top_k=top_k)
        
        if not results:
            if keyword_only:
                return "🔍 No exact matches found.\n\n💡 Tip: Try semantic search (remove keyword_only=True) to find conceptually similar code."
            else:
                return "🔍 No results found.\n\n💡 Tip: Try indexing with embeddings enabled for better semantic search."
        
        # Format results
        result_lines = [f"🔍 Found {len(results)} results for: {query}\n"]
        for i, result in enumerate(results, 1):
            result_lines.append(f"{i}. {result.file_path}:{result.start_line}-{result.end_line}")
            result_lines.append(f"   Score: {result.score:.3f}")
            result_lines.append(f"   {result.content[:200]}...\n")
        
        return "\n".join(result_lines)
    
    try:
        # Run blocking search in thread pool to avoid blocking the MCP event loop
        return await asyncio.to_thread(_blocking_search)
    except Exception as e:
        logger.error(f"Error searching codebase: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def index_codebase(path: str = ".", provider: str = "local") -> str:
    """
    Index the codebase for semantic search capabilities.
    
    **Provider Selection Guide:**
    
    local (default) - FREE, offline embeddings:
    - Uses sentence-transformers (~400MB model download on first run)
    - No API keys or costs required
    - Slower indexing (60-120s for 150 chunks) but works offline
    - Recommended for most use cases
    
    gemini - Google Gemini API embeddings:
    - Fast API calls (~2-5s for 150 chunks)
    - Best quality semantic understanding
    - Requires: GEMINI_API_KEY environment variable
    - Cost: Free tier available, then pay-per-use
    
    openai - OpenAI API embeddings:
    - Alternative to Gemini, similar quality
    - Requires: OPENAI_API_KEY environment variable
    - Cost: Pay-per-use pricing
    
    keyword - No embeddings (keyword-only search):
    - Fastest indexing (~0.2s)
    - FREE, no dependencies
    - Only exact/partial text matching available
    
    auto - Try local first, then cloud providers if available
    
    **When to Index:**
    - ✅ First-time setup
    - ✅ After adding >10 new files
    - ✅ After major refactoring
    - ✅ When switching projects/directories
    - ❌ Minor edits (index persists)
    - ❌ Before every search (wasteful)
    
    **Performance (150 chunks):**
    - Local: 60-120s (CPU-bound, one-time model download)
    - Gemini/OpenAI: ~45s (API calls)
    - Keyword-only: ~0.2s (no embeddings)
    
    **Included Files:**
    - Extensions: .py, .js, .ts, .jsx, .tsx, .go, .rs, .java, .cpp, .c, .md, .txt
    - Excludes: node_modules, .git, .venv, dist, build, __pycache__
    
    **Examples:**
    ```
    # Default: Local embeddings (free, offline)
    index_codebase()
    
    # Cloud provider (requires API key)
    index_codebase(provider="gemini")
    
    # Keyword-only (fastest, no semantic search)
    index_codebase(provider="keyword")
    
    # Index specific directory
    index_codebase("/path/to/project")
    ```
    
    Args:
        path: Absolute or relative path to codebase root (default: current directory)
        provider: Embedding provider - "local" (default) | "gemini" | "openai" | "keyword" | "auto"
        
    Returns:
        Number of indexed code chunks and status message
    """
    
    def _blocking_index():
        """Run the actual indexing in a thread to avoid blocking the event loop."""
        global _indexer
        
        config = IndexConfig(root_path=path)
        indexer = CodebaseIndexer(config)
        
        # Try to get embedding provider
        try:
            embed_provider = get_embedding_provider(provider)
            if embed_provider:
                logger.info(f"Using embedding provider: {type(embed_provider).__name__}")
            else:
                logger.info("Using keyword-only indexing (no embeddings)")
            indexer.index_all(embed_provider)
        except Exception as e:
            logger.error(f"❌ Indexing failed with provider '{provider}': {e}")
            logger.warning("Falling back to keyword-only indexing (no embeddings)")
            try:
                indexer.index_all(None)
            except Exception as inner_e:
                logger.error(f"❌ Critical indexing failure: {inner_e}")
                raise inner_e
        
        # Update global indexer
        _indexer = indexer
        
        has_embeddings = any(c.embedding is not None for c in indexer.chunks)
        embedding_status = "with embeddings" if has_embeddings else "keyword-only"
        
        return f"✅ Indexed {len(indexer.chunks)} chunks from {path} ({embedding_status})"
    
    try:
        # Run blocking indexing in thread pool to avoid blocking the MCP event loop
        return await asyncio.to_thread(_blocking_index)
    except Exception as e:
        logger.error(f"Error indexing codebase: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
def check_health() -> str:
    """
    Check the health of the Orbis-Search MCP server.
    Returns status of indexer and current configuration.
    """
    status = ["🟢 Orbis-Search MCP Server is healthy."]
    
    if _indexer:
        chunk_count = len(_indexer.chunks)
        has_embeddings = any(c.embedding is not None for c in _indexer.chunks) if _indexer.chunks else False
        status.append(f"✅ Indexer: {chunk_count} chunks indexed")
        status.append(f"   Embeddings: {'Enabled' if has_embeddings else 'Disabled (keyword-only)'}")
    else:
        status.append("⚪ Indexer: Ready (not initialized)")
        
    return "\n".join(status)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the MCP server."""
    logger.info("🚀 Starting Orbis-Search MCP Server...")
    logger.info("🔌 Transport: Stdio (Standard Input/Output)")
    logger.info("💡 Default provider: Local embeddings (free, offline)")
    mcp.run()


if __name__ == "__main__":
    main()
