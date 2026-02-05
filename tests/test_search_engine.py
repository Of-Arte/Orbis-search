"""
Tests for Orbis-Search Engine

Tests the CodebaseIndexer, HybridSearch, and embedding providers.
"""

import pytest
import tempfile
from pathlib import Path

from orbis_search.search_engine import (
    Chunk,
    SearchResult,
    IndexConfig,
    HybridSearchConfig,
    CodebaseIndexer,
    HybridSearch,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_codebase():
    """Create a temporary codebase with sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create sample Python file
        py_file = Path(tmpdir) / "sample.py"
        py_file.write_text("""
def get_user_by_id(user_id: int):
    '''Fetch a user from the database by their ID.'''
    return database.query(User).filter(User.id == user_id).first()

def authenticate_user(username: str, password: str):
    '''Authenticate a user with username and password.'''
    user = get_user_by_name(username)
    if user and verify_password(password, user.password_hash):
        return create_session(user)
    return None

class UserManager:
    '''Manages user operations.'''
    
    def create_user(self, name: str, email: str):
        return User(name=name, email=email)
    
    def delete_user(self, user_id: int):
        user = get_user_by_id(user_id)
        if user:
            database.delete(user)
""")
        
        # Create sample JS file
        js_file = Path(tmpdir) / "utils.js"
        js_file.write_text("""
function calculateTotal(items) {
    return items.reduce((sum, item) => sum + item.price, 0);
}

function formatCurrency(amount) {
    return '$' + amount.toFixed(2);
}

export { calculateTotal, formatCurrency };
""")
        
        yield tmpdir


@pytest.fixture
def indexer(temp_codebase):
    """Create an indexer with the temp codebase."""
    config = IndexConfig(root_path=temp_codebase)
    idx = CodebaseIndexer(config)
    idx.index_all(provider=None)  # Index without embeddings
    return idx


# ============================================================================
# Data Model Tests
# ============================================================================

class TestDataModels:
    """Test data model creation and fields."""
    
    def test_chunk_creation(self):
        chunk = Chunk(
            file_path="/test/file.py",
            content="def foo(): pass",
            start_line=1,
            end_line=1
        )
        assert chunk.file_path == "/test/file.py"
        assert chunk.embedding is None
    
    def test_search_result_with_scores(self):
        result = SearchResult(
            file_path="/test/file.py",
            content="test",
            start_line=1,
            end_line=1,
            score=1.5,
            semantic_score=0.7,
            exact_match_score=0.8,
            partial_match_score=0.0
        )
        assert result.score == 1.5
        assert result.exact_match_score == 0.8
    
    def test_hybrid_search_config_defaults(self):
        config = HybridSearchConfig()
        assert config.semantic_weight == 0.7
        assert config.exact_match_boost == 1.5
        assert config.partial_match_weight == 0.3
        assert config.min_word_length == 2


# ============================================================================
# Indexer Tests
# ============================================================================

class TestCodebaseIndexer:
    """Test codebase indexing functionality."""
    
    def test_scan_files(self, temp_codebase):
        config = IndexConfig(root_path=temp_codebase)
        indexer = CodebaseIndexer(config)
        files = indexer.scan_files()
        
        # Should find both .py and .js files
        extensions = [f.suffix for f in files]
        assert ".py" in extensions
        assert ".js" in extensions
    
    def test_chunk_file(self, temp_codebase):
        config = IndexConfig(root_path=temp_codebase, chunk_size=10, chunk_overlap=2)
        indexer = CodebaseIndexer(config)
        
        py_file = Path(temp_codebase) / "sample.py"
        chunks = indexer.chunk_file(py_file)
        
        assert len(chunks) > 0
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.file_path == str(py_file) for c in chunks)
    
    def test_index_all_creates_chunks(self, indexer):
        assert len(indexer.chunks) > 0
    
    def test_cache_save_and_load(self, temp_codebase):
        config = IndexConfig(root_path=temp_codebase)
        indexer1 = CodebaseIndexer(config)
        indexer1.index_all(provider=None)
        
        # Load in new indexer
        indexer2 = CodebaseIndexer(config)
        loaded = indexer2.load_cache()
        
        assert loaded is True
        assert len(indexer2.chunks) == len(indexer1.chunks)


# ============================================================================
# Hybrid Search Tests
# ============================================================================

class TestHybridSearch:
    """Test hybrid search functionality."""
    
    def test_keyword_search_exact_match(self, indexer):
        searcher = HybridSearch(indexer)
        results = searcher.keyword_search("get_user_by_id", top_k=5)
        
        assert len(results) > 0
        # Exact match should have high score
        assert results[0].exact_match_score > 0
    
    def test_keyword_search_partial_match(self, indexer):
        searcher = HybridSearch(indexer)
        results = searcher.keyword_search("user database", top_k=5)
        
        assert len(results) > 0
        # Should find partial matches
        assert any(r.partial_match_score > 0 for r in results)
    
    def test_keyword_search_no_results(self, indexer):
        searcher = HybridSearch(indexer)
        results = searcher.keyword_search("xyznonexistent123", top_k=5)
        
        assert len(results) == 0
    
    def test_keyword_search_case_insensitive(self, indexer):
        searcher = HybridSearch(indexer)
        
        results_lower = searcher.keyword_search("usermanager", top_k=5)
        results_mixed = searcher.keyword_search("UserManager", top_k=5)
        
        assert len(results_lower) == len(results_mixed)
    
    def test_hybrid_search_without_embeddings(self, indexer):
        """Hybrid search should fall back to keyword when no embeddings."""
        searcher = HybridSearch(indexer, provider=None)
        results = searcher.search("authenticate user", top_k=5)
        
        # Should still find results via keyword matching
        assert len(results) > 0
    
    def test_search_respects_top_k(self, indexer):
        searcher = HybridSearch(indexer)
        
        results_3 = searcher.keyword_search("def", top_k=3)
        results_10 = searcher.keyword_search("def", top_k=10)
        
        assert len(results_3) <= 3
        assert len(results_10) <= 10
    
    def test_results_sorted_by_score(self, indexer):
        searcher = HybridSearch(indexer)
        results = searcher.keyword_search("user", top_k=10)
        
        if len(results) > 1:
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True)


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_query(self, indexer):
        searcher = HybridSearch(indexer)
        results = searcher.keyword_search("", top_k=5)
        
        # Empty string matching is acceptable behavior
        assert isinstance(results, list)
    
    def test_single_character_query(self, indexer):
        searcher = HybridSearch(indexer)
        results = searcher.keyword_search("a", top_k=5)
        
        # Single char below min_word_length
        assert isinstance(results, list)
    
    def test_search_empty_index(self):
        config = IndexConfig(root_path=".")
        indexer = CodebaseIndexer(config)
        indexer.chunks = []
        
        searcher = HybridSearch(indexer)
        results = searcher.search("test", top_k=5)
        
        assert results == []
