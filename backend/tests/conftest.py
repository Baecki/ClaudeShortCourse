"""
Pytest configuration: adds backend/ to sys.path so all backend modules are importable.
Shared fixtures for mocking and test data setup.
"""
import sys
import os
import pytest
from unittest.mock import MagicMock

# backend/ is the parent of this tests/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def mock_rag_system():
    """Pre-configured MagicMock of RAGSystem for API endpoint tests."""
    mock = MagicMock()
    mock.session_manager.create_session.return_value = "test-session-abc"
    mock.session_manager.clear_session.return_value = None
    mock.query.return_value = (
        "MCP is a protocol for connecting AI assistants to external tools.",
        [{"label": "Introduction to MCP - Lesson 1", "url": "https://example.com/l1"}],
    )
    mock.get_course_analytics.return_value = {
        "total_courses": 1,
        "course_titles": ["Introduction to MCP"],
    }
    return mock


@pytest.fixture
def sample_query_payload():
    """Minimal valid query request body."""
    return {"query": "What is MCP?"}


@pytest.fixture
def sample_query_payload_with_session():
    """Valid query request body with an existing session."""
    return {"query": "What is MCP?", "session_id": "existing-session-xyz"}
