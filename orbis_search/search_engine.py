"""
Orbis-Search - Hybrid Search Engine

Provides semantic search capabilities using API-based embeddings (Gemini/OpenAI)
with local embeddings (sentence-transformers) as the default for offline use.

Features:
- Keyword search (~1ms) for exact symbols
- Semantic search (~200-300ms) for conceptual queries  
- Auto-pilot mode detects query type and optimizes automatically
"""

import os
import json
import pickle
import logging
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Chunk:
    """A chunk of code with metadata."""
    file_path: str
    start_line: int
    end_line: int
    content: Optional[str] = None
    embedding: Optional[List[float]] = None


@dataclass
class SearchResult:
    """A search result with relevance score breakdown."""
    file_path: str
    content: str
    start_line: int
    end_line: int
    score: float
    semantic_score: float = 0.0
    exact_match_score: float = 0.0
    partial_match_score: float = 0.0


@dataclass
class IndexConfig:
    """Configuration for the codebase indexer."""
    root_path: str = "."
    extensions: List[str] = field(default_factory=lambda: [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".cpp", ".c", ".md", ".txt"
    ])
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "node_modules", "__pycache__", ".git", "dist", "build", ".venv", "venv", 
        ".orbis-cache", "*.tmp", "*.bak"
    ])
    chunk_size: int = 50  # lines per chunk
    chunk_overlap: int = 10  # overlapping lines


@dataclass
class HybridSearchConfig:
    """Configuration for hybrid search scoring."""
    semantic_weight: float = 0.7       # Weight for semantic similarity
    exact_match_boost: float = 1.5     # Boost when exact query is found
    partial_match_weight: float = 0.3  # Weight for partial word matches
    min_word_length: int = 2           # Minimum word length for partial matching


# ============================================================================
# Embedding Providers
# ============================================================================

class EmbeddingProvider:
    """Base class for embedding providers."""
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class LocalEmbedding(EmbeddingProvider):
    """
    Local sentence-transformers embeddings (offline mode).
    
    This is the DEFAULT provider - no API keys or costs required.
    First run downloads ~400MB model.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install orbis-search[local]"
            )
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()


class GeminiEmbedding(EmbeddingProvider):
    """
    Google Gemini API embeddings.
    
    Requires: GEMINI_API_KEY environment variable
    Cost: Free tier available, then pay-per-use
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.client = genai
        except ImportError:
            raise ImportError("google-generativeai not installed. Run: pip install orbis-search[gemini]")
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            result = self.client.embed_content(
                model="models/text-embedding-004",
                content=text
            )
            embeddings.append(result['embedding'])
        return embeddings


class OpenAIEmbedding(EmbeddingProvider):
    """
    OpenAI API embeddings.
    
    Requires: OPENAI_API_KEY environment variable
    Cost: Pay-per-use pricing
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("openai not installed. Run: pip install orbis-search[openai]")
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [item.embedding for item in response.data]


# ============================================================================
# Codebase Indexer
# ============================================================================

class CodebaseIndexer:
    """Scans and indexes a codebase into searchable chunks."""
    
    def __init__(self, config: Optional[IndexConfig] = None):
        self.config = config or IndexConfig()
        self.chunks: List[Chunk] = []
        self.cache_path = Path(self.config.root_path) / ".orbis-cache" / "index.bin"
    
    def scan_files(self) -> List[Path]:
        """Scan the codebase for indexable files, pruning excluded directories."""
        root = Path(self.config.root_path)
        files = []
        
        # Extensions set for fast lookup
        ext_set = set(self.config.extensions)
        
        for dirpath, dirnames, filenames in os.walk(str(root)):
            # Prune excluded directories in-place (MODIFY dirnames)
            dirnames[:] = [
                d for d in dirnames 
                if not any(excl in os.path.join(dirpath, d) for excl in self.config.exclude_patterns)
                and not any(excl in d for excl in self.config.exclude_patterns)
            ]
            
            for f in filenames:
                _, ext = os.path.splitext(f)
                if ext in ext_set:
                    file_path = Path(dirpath) / f
                    
                    # Double check file exclusions
                    if any(excl in str(file_path) for excl in self.config.exclude_patterns):
                        continue
                        
                    files.append(file_path)
        
        logger.info(f"Found {len(files)} files to index")
        return files
    
    def chunk_file(self, file_path: Path) -> List[Chunk]:
        """Split a file into overlapping chunks."""
        chunks = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            
            for i in range(0, len(lines), self.config.chunk_size - self.config.chunk_overlap):
                end = min(i + self.config.chunk_size, len(lines))
                chunk_lines = lines[i:end]
                
                if chunk_lines:
                    chunks.append(Chunk(
                        file_path=str(file_path),
                        content="\n".join(chunk_lines),
                        start_line=i + 1,
                        end_line=end
                    ))
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
        
        return chunks
    
    def index_all(self, provider: Optional[EmbeddingProvider] = None, max_workers: int = 4) -> None:
        """
        Index all files and generate embeddings with multi-threading.
        
        Args:
            provider: Optional embedding provider for semantic search
            max_workers: Number of threads for parallel file processing (default: 4)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from threading import Lock
        
        files = self.scan_files()
        self.chunks = []
        chunks_lock = Lock()
        
        logger.info(f"Indexing {len(files)} files with {max_workers} threads...")
        
        # Multi-threaded file chunking
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.chunk_file, file_path): file_path for file_path in files}
            
            for future in as_completed(futures):
                try:
                    file_chunks = future.result()
                    with chunks_lock:
                        self.chunks.extend(file_chunks)
                except Exception as e:
                    file_path = futures[future]
                    logger.error(f"Error chunking {file_path}: {e}")
        
        logger.info(f"Created {len(self.chunks)} chunks")
        
        # Generate embeddings if provider is available
        if provider and self.chunks:
            logger.info("Generating embeddings...")
            texts = [c.content for c in self.chunks]
            
            # Batch to avoid API limits
            batch_size = 20
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_embeddings = provider.embed(batch_texts)
                
                for j, emb in enumerate(batch_embeddings):
                    self.chunks[i + j].embedding = emb
            
            logger.info("Embeddings generated")
        
        # Save cache
        self._save_cache()
    
    def _save_cache(self) -> None:
        """Save index to cache file in binary format without source content."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        # We don't save 'content' to disk to save space (bloat reduction)
        cache_data = [
            {
                "file_path": c.file_path,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "embedding": c.embedding
            }
            for c in self.chunks
        ]
        
        with open(self.cache_path, "wb") as f:
            pickle.dump(cache_data, f)
        logger.info(f"Cache saved to {self.cache_path}")
    
    def load_cache(self) -> bool:
        """Load index from binary cache if available."""
        if not self.cache_path.exists():
            return False
        
        try:
            with open(self.cache_path, "rb") as f:
                cache_data = pickle.load(f)
            self.chunks = [Chunk(**item) for item in cache_data]
            logger.info(f"Loaded {len(self.chunks)} chunks from binary cache")
            return True
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return False


# ============================================================================
# Hybrid Search (Semantic + Exact Match)
# ============================================================================

class HybridSearch:
    """
    Performs hybrid search combining semantic similarity with exact text matching.
    
    1. Semantic similarity with configurable weight
    2. Exact match boost for literal query matches
    3. Partial word matching for multi-word queries
    """
    
    def __init__(
        self,
        indexer: CodebaseIndexer,
        provider: Optional[EmbeddingProvider] = None,
        config: Optional[HybridSearchConfig] = None
    ):
        self.indexer = indexer
        self.provider = provider
        self.config = config or HybridSearchConfig()
    
    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Hybrid search combining semantic and exact matching.
        
        Args:
            query: Search query (natural language or specific terms)
            top_k: Number of results to return
        
        Returns:
            List of SearchResult sorted by combined score
        """
        if not self.indexer.chunks:
            logger.warning("No chunks indexed. Run indexer.index_all() first.")
            return []
        
        # Prepare query for matching
        lower_query = query.lower()
        query_words = [w for w in lower_query.split() if len(w) > self.config.min_word_length]
        
        # Get query embedding if provider available
        query_embedding = None
        if self.provider:
            try:
                query_embedding = self.provider.embed([query])[0]
            except Exception as e:
                logger.warning(f"Embedding failed, falling back to keyword search: {e}")
        
        results = []
        for chunk in self.indexer.chunks:
            # Lazy load or use cached content
            content = chunk.content
            if content is None:
                content = self._get_chunk_content(chunk)
            
            lower_content = content.lower()
            
            # 1. Semantic Score
            semantic_score = 0.0
            if query_embedding and chunk.embedding:
                semantic_score = self._cosine_similarity(query_embedding, chunk.embedding)
            
            # 2. Exact Match Boost
            exact_match_score = 0.0
            if lower_query in lower_content:
                exact_match_score = self.config.exact_match_boost
            
            # 3. Partial Word Matching
            partial_match_score = 0.0
            if query_words and not exact_match_score:
                # Lazy load content for matching if not in memory
                content = chunk.content
                if content is None:
                    content = self._get_chunk_content(chunk)
                
                lower_content = content.lower()
                matched_words = sum(1 for word in query_words if word in lower_content)
                if matched_words > 0:
                    partial_match_score = (matched_words / len(query_words)) * self.config.partial_match_weight
            
            # Combined Score
            total_score = (
                (semantic_score * self.config.semantic_weight) +
                exact_match_score +
                partial_match_score
            )
            
            # Only include if there's some relevance
            if total_score > 0 or exact_match_score > 0 or partial_match_score > 0:
                results.append(SearchResult(
                    file_path=chunk.file_path,
                    content=chunk.content or self._get_chunk_content(chunk),
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    score=total_score,
                    semantic_score=semantic_score,
                    exact_match_score=exact_match_score,
                    partial_match_score=partial_match_score
                ))
        
        # Sort by total score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def keyword_search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Keyword-only search without embeddings.
        Useful for literal function names, class names, etc.
        
        Args:
            query: Exact or partial term to search for
            top_k: Number of results to return
        
        Returns:
            List of SearchResult sorted by match quality
        """
        if not self.indexer.chunks:
            logger.warning("No chunks indexed. Run indexer.index_all() first.")
            return []
        
        lower_query = query.lower()
        query_words = [w for w in lower_query.split() if len(w) > self.config.min_word_length]
        
        results = []
        for chunk in self.indexer.chunks:
            # Lazy load content for keyword search
            content = chunk.content
            if content is None:
                content = self._get_chunk_content(chunk)
            
            lower_content = content.lower()
            
            # Exact match gets highest score
            if lower_query in lower_content:
                # Count occurrences for ranking
                occurrences = lower_content.count(lower_query)
                score = self.config.exact_match_boost + (occurrences * 0.1)
                
                results.append(SearchResult(
                    file_path=chunk.file_path,
                    content=content,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    score=score,
                    semantic_score=0.0,
                    exact_match_score=score,
                    partial_match_score=0.0
                ))
            elif query_words:
                # Partial word matching
                matched_words = sum(1 for word in query_words if word in lower_content)
                if matched_words > 0:
                    score = (matched_words / len(query_words)) * self.config.partial_match_weight
                    results.append(SearchResult(
                        file_path=chunk.file_path,
                        content=content,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        score=score,
                        semantic_score=0.0,
                        exact_match_score=0.0,
                        partial_match_score=score
                    ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    
    def _get_chunk_content(self, chunk: Chunk) -> str:
        """Lazy load chunk content from file."""
        if chunk.content:
            return chunk.content
        try:
            path = Path(chunk.file_path)
            if not path.exists():
                return "[Error: File not found]"
            
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            # lines is 0-indexed, chunk.start_line is 1-indexed
            return "\n".join(lines[chunk.start_line - 1:chunk.end_line])
        except Exception as e:
            logger.error(f"Error loading chunk content from {chunk.file_path}: {e}")
            return f"[Error: {e}]"

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = sum(x ** 2 for x in a) ** 0.5
        magnitude_b = sum(x ** 2 for x in b) ** 0.5
        
        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0
        
        return dot_product / (magnitude_a * magnitude_b)


# ============================================================================
# Factory Function
# ============================================================================

def get_embedding_provider(
    provider_type: str = "local",
    api_key: Optional[str] = None
) -> Optional[EmbeddingProvider]:
    """
    Get an embedding provider by type.
    
    Args:
        provider_type: "local" (default), "gemini", "openai", "keyword", or "auto"
        api_key: Optional API key override
    
    Returns:
        An initialized EmbeddingProvider, or None if provider_type="keyword"
    
    Provider Costs:
        - local: FREE (default) - Uses sentence-transformers, downloads ~400MB model
        - gemini: Free tier available, then pay-per-use (requires GEMINI_API_KEY)
        - openai: Pay-per-use (requires OPENAI_API_KEY)
        - keyword: FREE - No embeddings, exact match only
    """
    # Keyword-only mode (no embeddings needed)
    if provider_type == "keyword":
        logger.info("Running in keyword-only mode (no embeddings)")
        return None
    
    # Local embeddings (DEFAULT - free, offline)
    if provider_type == "local":
        try:
            return LocalEmbedding()
        except ImportError as e:
            logger.warning(f"Local embeddings unavailable: {e}")
            logger.info("Falling back to keyword-only mode")
            return None
    
    # Auto mode: try local first, then API providers
    if provider_type == "auto":
        # Try local first (free)
        try:
            return LocalEmbedding()
        except ImportError:
            pass
        
        # Try Gemini
        if os.environ.get("GEMINI_API_KEY"):
            try:
                return GeminiEmbedding(api_key)
            except Exception as e:
                logger.warning(f"Gemini unavailable: {e}")
        
        # Try OpenAI
        if os.environ.get("OPENAI_API_KEY"):
            try:
                return OpenAIEmbedding(api_key)
            except Exception as e:
                logger.warning(f"OpenAI unavailable: {e}")
        
        logger.info("No embedding providers available. Using keyword-only mode.")
        return None
    
    # Gemini
    if provider_type == "gemini":
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if key:
            return GeminiEmbedding(key)
        raise ValueError("GEMINI_API_KEY not set")
    
    # OpenAI
    if provider_type == "openai":
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if key:
            return OpenAIEmbedding(key)
        raise ValueError("OPENAI_API_KEY not set")
    
    raise ValueError(f"Unknown provider type: {provider_type}")
