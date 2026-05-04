"""
Tests for the RAGSystem query pipeline in rag_system.py.

These tests verify the end-to-end behavior when a user asks a lesson-specific
question. They use:
  - A real VectorStore (real ChromaDB + real embeddings) for realistic retrieval
  - A mocked AIGenerator to avoid Anthropic API calls

The key regression tested here is: with MAX_RESULTS=0 in config.py, VectorStore
raises an exception, CourseSearchTool surfaces that as an error string, and the AI
ends up saying "I couldn't find specific information about lesson 5."
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from rag_system import RAGSystem
from ai_generator import AIGenerator
from vector_store import VectorStore, SearchResults
from search_tools import ToolManager, CourseSearchTool
from models import Course, Lesson, CourseChunk
from config import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mcp_course() -> tuple[Course, list[CourseChunk]]:
    course = Course(
        title="Introduction to MCP",
        course_link="https://example.com/mcp",
        instructor="Test Instructor",
        lessons=[
            Lesson(lesson_number=1, title="What is MCP",   lesson_link="https://example.com/l1"),
            Lesson(lesson_number=2, title="MCP Clients",   lesson_link="https://example.com/l2"),
            Lesson(lesson_number=3, title="MCP Servers",   lesson_link="https://example.com/l3"),
            Lesson(lesson_number=4, title="MCP Resources", lesson_link="https://example.com/l4"),
            Lesson(lesson_number=5, title="Advanced MCP",  lesson_link="https://example.com/l5"),
        ],
    )
    chunks = [
        CourseChunk(
            content=f"Lesson {n} content: " + text,
            course_title=course.title,
            lesson_number=n,
            chunk_index=n - 1,
        )
        for n, text in [
            (1, "Model Context Protocol (MCP) is an open standard for AI tool integration."),
            (2, "MCP clients manage connections and request context from MCP servers."),
            (3, "MCP servers expose tools, resources, and prompt templates to clients."),
            (4, "Resources are URI-addressed data such as files or database rows."),
            (5, "Advanced MCP features include sampling, roots, and server-side prompts for complex workflows."),
        ]
    ]
    return course, chunks


class _MockAIGenerator:
    """
    Simulates AIGenerator but executes the real tool-use flow locally
    without touching the Anthropic API. On each call it:
      1. Invokes every registered tool with a dummy query
      2. Returns the tool output as the response
    This lets us test whether the VectorStore actually returns content.
    """
    def __init__(self, query_override: str, lesson_number_override: int = None):
        self._query = query_override
        self._lesson = lesson_number_override

    def generate_response(self, query, conversation_history=None, tools=None, tool_manager=None):
        if tool_manager is None:
            return "No tool manager provided."
        kwargs = {"query": self._query}
        if self._lesson is not None:
            kwargs["lesson_number"] = self._lesson
        return tool_manager.execute_tool("search_course_content", **kwargs)


# ---------------------------------------------------------------------------
# Config-level test
# ---------------------------------------------------------------------------

class TestConfig:
    def test_max_results_is_positive(self):
        """
        MAX_RESULTS must be > 0.  ChromaDB raises an exception for n_results=0,
        which propagates as a search error and causes the AI to say it can't find content.

        FIX: change MAX_RESULTS from 0 to 5 in backend/config.py
        """
        config = Config()
        assert config.MAX_RESULTS > 0, (
            f"config.MAX_RESULTS is {config.MAX_RESULTS}. "
            "It must be a positive integer (e.g. 5). "
            "A value of 0 causes ChromaDB to throw 'n_results must be positive', "
            "which makes every tool search fail silently."
        )


# ---------------------------------------------------------------------------
# Integration tests — real ChromaDB, mocked AIGenerator
# ---------------------------------------------------------------------------

class TestRAGSystemQueryPipeline:
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"

    @pytest.fixture()
    def rag_with_mcp_course(self, tmp_path):
        """
        Build a RAGSystem with a real VectorStore (max_results=5) and the MCP
        course pre-loaded. The AIGenerator is replaced with _MockAIGenerator so
        no real API calls are made.
        """
        config = Config(
            ANTHROPIC_API_KEY="test-key",
            CHROMA_PATH=str(tmp_path / "chroma"),
            MAX_RESULTS=5,  # Correct value — the fix
        )
        rag = RAGSystem(config)

        # Load test data directly into the vector store
        course, chunks = _make_mcp_course()
        rag.vector_store.add_course_metadata(course)
        rag.vector_store.add_course_content(chunks)

        # Replace real AI with a mock that drives the search tool directly
        rag.ai_generator = _MockAIGenerator(
            query_override="advanced MCP features sampling",
            lesson_number_override=5,
        )
        return rag

    def test_lesson_5_query_returns_actual_content(self, rag_with_mcp_course):
        """
        A query for lesson 5 content must return the indexed text, not an error message.
        This is the main regression for the reported bug.
        """
        response, sources = rag_with_mcp_course.query(
            "What is covered in lesson 5 of the MCP course?"
        )

        assert "couldn't find" not in response.lower(), (
            f"Got a 'not found' response: {response!r}\n"
            "This usually means VectorStore returned no results (check MAX_RESULTS in config.py)."
        )
        assert "Search error" not in response, (
            f"Got a search error as the response: {response!r}\n"
            "ChromaDB likely threw an exception — most common cause is MAX_RESULTS=0."
        )
        assert response.strip() != ""

    def test_lesson_5_query_returns_lesson_5_content_specifically(self, rag_with_mcp_course):
        """The returned content must be from lesson 5, not a generic fallback."""
        response, _ = rag_with_mcp_course.query(
            "What is covered in lesson 5 of the MCP course?"
        )

        assert "Advanced MCP" in response or "sampling" in response or "roots" in response, (
            f"Response did not contain lesson 5 content: {response!r}"
        )

    def test_query_with_zero_max_results_propagates_chromadb_error(self, tmp_path):
        """
        BUG DOCUMENTATION — end-to-end demonstration of what MAX_RESULTS=0 causes.

        With MAX_RESULTS=0:
          VectorStore.search() → ChromaDB raises "cannot be negative, or zero"
          → caught → SearchResults.empty("Search error: ...")
          → CourseSearchTool.execute() returns that error string
          → AI receives the error as tool output
          → AI responds "I couldn't find specific information about lesson 5"

        Fix: set MAX_RESULTS=5 in backend/config.py (already applied).
        This test remains as stable documentation of the failure mode.
        """
        broken_config = Config(
            ANTHROPIC_API_KEY="test-key",
            CHROMA_PATH=str(tmp_path / "chroma_broken"),
            MAX_RESULTS=0,  # Deliberately broken — documents the bug scenario
        )
        rag = RAGSystem(broken_config)

        course, chunks = _make_mcp_course()
        rag.vector_store.add_course_metadata(course)
        rag.vector_store.add_course_content(chunks)

        rag.ai_generator = _MockAIGenerator(
            query_override="advanced MCP features sampling",
            lesson_number_override=5,
        )

        response, _ = rag.query("What is covered in lesson 5 of the MCP course?")

        # With max_results=0 the error propagates through the tool to the AI response
        assert "Search error" in response and "cannot be negative, or zero" in response, (
            "Expected ChromaDB's 'cannot be negative, or zero' error to appear in the response. "
            "This documents the exact failure mode caused by MAX_RESULTS=0."
        )

    def test_session_history_is_saved_after_query(self, rag_with_mcp_course):
        """After a query, the exchange must be stored in session history."""
        session_id = rag_with_mcp_course.session_manager.create_session()
        rag_with_mcp_course.query("What is lesson 5?", session_id=session_id)

        history = rag_with_mcp_course.session_manager.get_conversation_history(session_id)
        assert history is not None
        assert "What is lesson 5?" in history

    def test_sources_are_reset_between_queries(self, rag_with_mcp_course):
        """Sources from query N must not bleed into query N+1."""
        rag_with_mcp_course.query("lesson 5 content")
        _, sources2 = rag_with_mcp_course.query("lesson 1 content")

        # After the second query, tool_manager's sources should reflect query 2 only
        # (they are reset at the end of each query() call)
        assert rag_with_mcp_course.tool_manager.get_last_sources() == [], (
            "Sources were not reset after query() — tool_manager.reset_sources() may not be working."
        )
