"""
Tests for CourseSearchTool.execute() in search_tools.py.

These tests cover:
  - Unit tests with a mocked VectorStore (fast, no I/O)
  - Integration tests with a real ChromaDB instance using test data
  - Regression test that reproduces the max_results=0 config bug
"""
import pytest
from unittest.mock import MagicMock

from search_tools import CourseSearchTool, ToolManager
from vector_store import VectorStore, SearchResults
from models import Course, Lesson, CourseChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mcp_course() -> tuple[Course, list[CourseChunk]]:
    """Create a minimal MCP course with 5 lessons for integration tests."""
    course = Course(
        title="Introduction to MCP",
        course_link="https://example.com/mcp",
        instructor="Test Instructor",
        lessons=[
            Lesson(lesson_number=1, title="What is MCP",    lesson_link="https://example.com/l1"),
            Lesson(lesson_number=2, title="MCP Clients",    lesson_link="https://example.com/l2"),
            Lesson(lesson_number=3, title="MCP Servers",    lesson_link="https://example.com/l3"),
            Lesson(lesson_number=4, title="MCP Resources",  lesson_link="https://example.com/l4"),
            Lesson(lesson_number=5, title="Advanced MCP",   lesson_link="https://example.com/l5"),
        ],
    )
    chunks = [
        CourseChunk(
            content="Lesson 1 content: Model Context Protocol (MCP) is an open standard for connecting AI assistants to external data sources.",
            course_title=course.title, lesson_number=1, chunk_index=0,
        ),
        CourseChunk(
            content="Lesson 2 content: MCP clients initiate connections and request context from servers on behalf of the AI model.",
            course_title=course.title, lesson_number=2, chunk_index=1,
        ),
        CourseChunk(
            content="Lesson 3 content: MCP servers expose tools, resources, and prompts that clients can discover and invoke.",
            course_title=course.title, lesson_number=3, chunk_index=2,
        ),
        CourseChunk(
            content="Lesson 4 content: Resources in MCP are URI-addressed data that the AI can read, such as files or database rows.",
            course_title=course.title, lesson_number=4, chunk_index=3,
        ),
        CourseChunk(
            content="Lesson 5 content: Advanced MCP features include sampling, roots, and server-side prompt templates for complex workflows.",
            course_title=course.title, lesson_number=5, chunk_index=4,
        ),
    ]
    return course, chunks


# ---------------------------------------------------------------------------
# Unit tests — mocked VectorStore
# ---------------------------------------------------------------------------

class TestCourseSearchToolUnit:
    """Fast unit tests that never touch ChromaDB."""

    def test_execute_returns_formatted_content_on_success(self):
        """Happy path: results exist → formatted string with header and content."""
        mock_store = MagicMock(spec=VectorStore)
        mock_store.search.return_value = SearchResults(
            documents=["Lesson 5 content: Advanced MCP features include sampling and roots."],
            metadata=[{"course_title": "Introduction to MCP", "lesson_number": 5}],
            distances=[0.05],
        )
        mock_store.get_lesson_link.return_value = "https://example.com/l5"

        tool = CourseSearchTool(mock_store)
        result = tool.execute(query="advanced MCP features", course_name="MCP", lesson_number=5)

        assert "Advanced MCP" in result
        assert "No relevant content found" not in result
        assert result.strip() != ""

    def test_execute_returns_no_results_message_when_empty(self):
        """When search returns nothing, the user should get a clear 'not found' message."""
        mock_store = MagicMock(spec=VectorStore)
        mock_store.search.return_value = SearchResults(documents=[], metadata=[], distances=[])

        tool = CourseSearchTool(mock_store)
        result = tool.execute(query="lesson 5 content", course_name="MCP", lesson_number=5)

        assert "No relevant content found" in result

    def test_execute_propagates_search_error_to_caller(self):
        """A search-level error (e.g. bad n_results) should be returned as a string, not raised."""
        error_msg = "Search error: n_results must be a positive integer greater than 0"
        mock_store = MagicMock(spec=VectorStore)
        mock_store.search.return_value = SearchResults.empty(error_msg)

        tool = CourseSearchTool(mock_store)
        result = tool.execute(query="lesson 5 content")

        # The error string must reach the caller (which is the AI, via ToolManager)
        assert "Search error" in result

    def test_execute_tracks_sources_for_successful_results(self):
        """After a successful search, last_sources should contain the matched lesson."""
        mock_store = MagicMock(spec=VectorStore)
        mock_store.search.return_value = SearchResults(
            documents=["Lesson 5 content: ..."],
            metadata=[{"course_title": "Introduction to MCP", "lesson_number": 5}],
            distances=[0.1],
        )
        mock_store.get_lesson_link.return_value = "https://example.com/l5"

        tool = CourseSearchTool(mock_store)
        tool.execute(query="MCP features", lesson_number=5)

        assert len(tool.last_sources) == 1
        assert tool.last_sources[0]["label"] == "Introduction to MCP - Lesson 5"

    def test_execute_deduplicates_sources_for_same_lesson(self):
        """Multiple chunks from the same lesson should produce only one source entry."""
        mock_store = MagicMock(spec=VectorStore)
        mock_store.search.return_value = SearchResults(
            documents=["chunk A", "chunk B"],
            metadata=[
                {"course_title": "Introduction to MCP", "lesson_number": 5},
                {"course_title": "Introduction to MCP", "lesson_number": 5},
            ],
            distances=[0.1, 0.15],
        )
        mock_store.get_lesson_link.return_value = "https://example.com/l5"

        tool = CourseSearchTool(mock_store)
        tool.execute(query="MCP features")

        assert len(tool.last_sources) == 1

    def test_tool_definition_has_required_fields(self):
        """The Anthropic tool schema must have name, description, and input_schema."""
        mock_store = MagicMock(spec=VectorStore)
        tool = CourseSearchTool(mock_store)
        defn = tool.get_tool_definition()

        assert defn["name"] == "search_course_content"
        assert "description" in defn
        assert "input_schema" in defn
        assert "query" in defn["input_schema"]["properties"]
        assert "query" in defn["input_schema"]["required"]


# ---------------------------------------------------------------------------
# Integration tests — real ChromaDB, real embeddings
# ---------------------------------------------------------------------------

class TestCourseSearchToolIntegration:
    """Slower tests that spin up a real ChromaDB with test course data."""

    EMBEDDING_MODEL = "all-MiniLM-L6-v2"

    @pytest.fixture()
    def store_with_mcp_course(self, tmp_path):
        """Real VectorStore with max_results=5 and a full MCP course loaded."""
        store = VectorStore(
            chroma_path=str(tmp_path / "chroma"),
            embedding_model=self.EMBEDDING_MODEL,
            max_results=5,
        )
        course, chunks = _make_mcp_course()
        store.add_course_metadata(course)
        store.add_course_content(chunks)
        return store

    def test_search_lesson_5_returns_content_with_correct_max_results(self, store_with_mcp_course):
        """With max_results=5, a lesson-5 query must return actual content (not empty/error)."""
        tool = CourseSearchTool(store_with_mcp_course)
        result = tool.execute(
            query="advanced MCP features sampling roots",
            course_name="Introduction to MCP",
            lesson_number=5,
        )

        assert "No relevant content found" not in result, (
            "Expected lesson 5 content but got a 'not found' message. "
            "This may indicate max_results is too low or the lesson was not indexed."
        )
        assert "Search error" not in result
        assert result.strip() != ""

    def test_search_without_lesson_filter_returns_multiple_lessons(self, store_with_mcp_course):
        """A broad query without a lesson filter should match chunks across lessons."""
        tool = CourseSearchTool(store_with_mcp_course)
        result = tool.execute(query="MCP protocol features")

        assert "No relevant content found" not in result
        assert "Search error" not in result

    def test_search_nonexistent_course_fuzzy_matches_closest(self, store_with_mcp_course):
        """
        VectorStore._resolve_course_name() uses vector similarity with no distance threshold.
        When there is only one course in the catalog it is always returned as the
        'closest' match, even for a completely unrelated query.
        This test documents that known behavior: the tool returns content rather than
        a 'no course found' message.
        """
        tool = CourseSearchTool(store_with_mcp_course)
        result = tool.execute(query="lesson content", course_name="Nonexistent Course XYZ")

        # The fuzzy resolver returns the only course in the store, so content IS returned.
        # A "no course found" response would only occur if the catalog were empty.
        assert "Search error" not in result

    # -----------------------------------------------------------------------
    # BUG REPRODUCTION: max_results=0
    # -----------------------------------------------------------------------

    def test_search_with_zero_max_results_returns_chromadb_error(self, tmp_path):
        """
        BUG DOCUMENTATION — shows exactly what goes wrong when MAX_RESULTS=0.

        ChromaDB raises "Number of requested results 0, cannot be negative, or zero."
        VectorStore catches the exception and wraps it in SearchResults.empty().
        CourseSearchTool returns the error string to the AI as the tool result.
        The AI then responds with "I couldn't find specific information about lesson 5."

        Fix: set MAX_RESULTS=5 in backend/config.py (already applied).
        This test remains as a stable record of the failure mode.
        """
        broken_store = VectorStore(
            chroma_path=str(tmp_path / "chroma_zero"),
            embedding_model=self.EMBEDDING_MODEL,
            max_results=0,  # Deliberately broken — documents the bug scenario
        )
        course, chunks = _make_mcp_course()
        broken_store.add_course_metadata(course)
        broken_store.add_course_content(chunks)

        tool = CourseSearchTool(broken_store)
        result = tool.execute(
            query="advanced MCP features sampling roots",
            lesson_number=5,
        )

        # With max_results=0 the error propagates — this is the broken behavior we fixed
        assert "Search error" in result and "cannot be negative, or zero" in result, (
            "Expected ChromaDB's 'cannot be negative, or zero' error. "
            "If this assertion fails it means the max_results=0 scenario no longer "
            "produces a ChromaDB error, which would be unexpected."
        )
