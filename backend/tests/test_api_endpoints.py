"""
API endpoint tests for the RAG chatbot.

Creates a test-specific FastAPI app that mirrors the endpoints from app.py
without static file serving, so tests run with no ChromaDB, no Anthropic
API calls, and no frontend directory required.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import List, Optional


# ---------------------------------------------------------------------------
# Inline models — mirrors app.py
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class SourceItem(BaseModel):
    label: str
    url: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    session_id: str


class CourseStats(BaseModel):
    total_courses: int
    course_titles: List[str]


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def _make_test_app(rag_system) -> FastAPI:
    """Build a minimal FastAPI app with the same routes as app.py, no static mount."""
    test_app = FastAPI()

    @test_app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = rag_system.session_manager.create_session()
            answer, sources = rag_system.query(request.query, session_id)
            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @test_app.delete("/api/session/{session_id}", status_code=204)
    async def delete_session(session_id: str):
        rag_system.session_manager.clear_session(session_id)

    @test_app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return test_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(mock_rag_system):
    """TestClient wired to the inline test app with a fresh mock RAGSystem."""
    return TestClient(_make_test_app(mock_rag_system))


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------

class TestQueryEndpoint:

    def test_returns_200_with_required_fields(self, client):
        resp = client.post("/api/query", json={"query": "What is MCP?"})
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body
        assert "session_id" in body
        assert "sources" in body

    def test_creates_new_session_when_not_provided(self, client, mock_rag_system):
        resp = client.post("/api/query", json={"query": "What is MCP?"})
        assert resp.status_code == 200
        mock_rag_system.session_manager.create_session.assert_called_once()
        assert resp.json()["session_id"] == "test-session-abc"

    def test_uses_provided_session_id(self, client, mock_rag_system):
        resp = client.post(
            "/api/query",
            json={"query": "What is MCP?", "session_id": "existing-session-xyz"},
        )
        assert resp.status_code == 200
        mock_rag_system.session_manager.create_session.assert_not_called()
        assert resp.json()["session_id"] == "existing-session-xyz"

    def test_answer_matches_rag_response(self, client, mock_rag_system):
        mock_rag_system.query.return_value = ("Exact answer text.", [])
        resp = client.post("/api/query", json={"query": "What is MCP?"})
        assert resp.json()["answer"] == "Exact answer text."

    def test_sources_are_included_in_response(self, client, mock_rag_system):
        mock_rag_system.query.return_value = (
            "MCP answer",
            [{"label": "MCP - Lesson 1", "url": "https://example.com/l1"}],
        )
        resp = client.post("/api/query", json={"query": "What is MCP?"})
        sources = resp.json()["sources"]
        assert len(sources) == 1
        assert sources[0]["label"] == "MCP - Lesson 1"
        assert sources[0]["url"] == "https://example.com/l1"

    def test_source_without_url_is_valid(self, client, mock_rag_system):
        mock_rag_system.query.return_value = (
            "Answer",
            [{"label": "Some Lesson", "url": None}],
        )
        resp = client.post("/api/query", json={"query": "test"})
        assert resp.status_code == 200
        assert resp.json()["sources"][0]["url"] is None

    def test_query_is_forwarded_to_rag_system(self, client, mock_rag_system):
        client.post("/api/query", json={"query": "What is MCP?"})
        mock_rag_system.query.assert_called_once()
        assert mock_rag_system.query.call_args.args[0] == "What is MCP?"

    def test_returns_422_when_query_field_missing(self, client):
        resp = client.post("/api/query", json={})
        assert resp.status_code == 422

    def test_returns_500_when_rag_raises(self, client, mock_rag_system):
        mock_rag_system.query.side_effect = RuntimeError("DB unavailable")
        resp = client.post("/api/query", json={"query": "What is MCP?"})
        assert resp.status_code == 500
        assert "DB unavailable" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/courses
# ---------------------------------------------------------------------------

class TestCoursesEndpoint:

    def test_returns_200_with_required_fields(self, client):
        resp = client.get("/api/courses")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_courses" in body
        assert "course_titles" in body

    def test_total_courses_matches_mock(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 3,
            "course_titles": ["Course A", "Course B", "Course C"],
        }
        resp = client.get("/api/courses")
        assert resp.json()["total_courses"] == 3

    def test_course_titles_match_mock(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 2,
            "course_titles": ["Course A", "Course B"],
        }
        resp = client.get("/api/courses")
        assert resp.json()["course_titles"] == ["Course A", "Course B"]

    def test_returns_empty_list_when_no_courses(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 0,
            "course_titles": [],
        }
        resp = client.get("/api/courses")
        assert resp.status_code == 200
        assert resp.json()["total_courses"] == 0
        assert resp.json()["course_titles"] == []

    def test_returns_500_when_analytics_raises(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.side_effect = RuntimeError("DB error")
        resp = client.get("/api/courses")
        assert resp.status_code == 500
        assert "DB error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /api/session/{session_id}
# ---------------------------------------------------------------------------

class TestDeleteSessionEndpoint:

    def test_returns_204_on_success(self, client):
        resp = client.delete("/api/session/test-session-abc")
        assert resp.status_code == 204

    def test_response_body_is_empty(self, client):
        resp = client.delete("/api/session/any-id")
        assert resp.content == b""

    def test_calls_clear_session_with_correct_id(self, client, mock_rag_system):
        client.delete("/api/session/my-session-id")
        mock_rag_system.session_manager.clear_session.assert_called_once_with("my-session-id")
