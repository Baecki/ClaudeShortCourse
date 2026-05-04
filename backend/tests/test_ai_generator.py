"""
Tests for AIGenerator in ai_generator.py.

These tests verify that AIGenerator:
  - Makes a first API call with tools registered
  - Detects stop_reason == "tool_use" and delegates to _handle_tool_execution
  - Calls ToolManager.execute_tool() for every tool_use content block
  - Sends tool results back to Claude in a second API call
  - Returns final text to the caller

All Anthropic API calls are mocked — no real API key required.
"""
import pytest
from unittest.mock import MagicMock, patch, call

from ai_generator import AIGenerator
from search_tools import ToolManager, CourseSearchTool
from vector_store import VectorStore, SearchResults


# ---------------------------------------------------------------------------
# Helpers — build realistic mock Anthropic response objects
# ---------------------------------------------------------------------------

def _mock_text_response(text: str):
    """Simulate a plain text response (stop_reason='end_turn')."""
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [content_block]
    return response


def _mock_tool_use_response(tool_name: str, tool_input: dict, tool_id: str = "tu_abc123"):
    """Simulate a response where Claude wants to call a tool (stop_reason='tool_use')."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input
    tool_block.id = tool_id

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_block]
    return response


# ---------------------------------------------------------------------------
# Unit tests — mocked Anthropic client
# ---------------------------------------------------------------------------

class TestAIGeneratorUnit:

    @pytest.fixture()
    def generator(self):
        return AIGenerator(api_key="test-key", model="claude-test-model")

    @pytest.fixture()
    def tool_manager_with_mock_store(self):
        mock_store = MagicMock(spec=VectorStore)
        mock_store.search.return_value = SearchResults(
            documents=["Lesson 5 content: Advanced MCP features include sampling."],
            metadata=[{"course_title": "Introduction to MCP", "lesson_number": 5}],
            distances=[0.1],
        )
        mock_store.get_lesson_link.return_value = "https://example.com/l5"

        tm = ToolManager()
        tm.register_tool(CourseSearchTool(mock_store))
        return tm

    # ------------------------------------------------------------------
    # Path 1: no tool needed
    # ------------------------------------------------------------------

    def test_returns_direct_text_when_no_tool_use(self, generator):
        """When stop_reason is 'end_turn', the text from the first response is returned directly."""
        with patch.object(generator.client.messages, "create",
                          return_value=_mock_text_response("Here is the answer.")) as mock_create:
            result = generator.generate_response(query="What is AI?")

        assert result == "Here is the answer."
        assert mock_create.call_count == 1

    def test_includes_conversation_history_in_system_prompt(self, generator):
        """Conversation history should be appended to the system prompt on each call."""
        with patch.object(generator.client.messages, "create",
                          return_value=_mock_text_response("ok")) as mock_create:
            generator.generate_response(
                query="What is lesson 5 about?",
                conversation_history="User: hello\nAssistant: hi",
            )

        system_arg = mock_create.call_args.kwargs["system"]
        assert "hello" in system_arg
        assert "Previous conversation" in system_arg

    def test_passes_tools_to_first_api_call(self, generator, tool_manager_with_mock_store):
        """Tool definitions must be included in the first API call so Claude can use them."""
        with patch.object(generator.client.messages, "create",
                          return_value=_mock_text_response("ok")) as mock_create:
            generator.generate_response(
                query="What is covered in lesson 5?",
                tools=tool_manager_with_mock_store.get_tool_definitions(),
                tool_manager=tool_manager_with_mock_store,
            )

        first_call_kwargs = mock_create.call_args.kwargs
        assert "tools" in first_call_kwargs
        tool_names = [t["name"] for t in first_call_kwargs["tools"]]
        assert "search_course_content" in tool_names

    # ------------------------------------------------------------------
    # Path 2: tool use triggered
    # ------------------------------------------------------------------

    def test_makes_second_api_call_when_tool_use_detected(self, generator, tool_manager_with_mock_store):
        """When stop_reason=='tool_use', a second API call must be made with tool results."""
        first_response = _mock_tool_use_response(
            tool_name="search_course_content",
            tool_input={"query": "advanced MCP features", "lesson_number": 5},
        )
        second_response = _mock_text_response("Advanced MCP includes sampling and roots.")

        with patch.object(generator.client.messages, "create",
                          side_effect=[first_response, second_response]) as mock_create:
            result = generator.generate_response(
                query="What is covered in lesson 5?",
                tools=tool_manager_with_mock_store.get_tool_definitions(),
                tool_manager=tool_manager_with_mock_store,
            )

        assert mock_create.call_count == 2, (
            "Expected two API calls: one to detect tool use, one to synthesize tool results"
        )
        assert result == "Advanced MCP includes sampling and roots."

    def test_tool_result_added_to_messages_before_second_call(self, generator, tool_manager_with_mock_store):
        """The messages list sent in the second API call must contain a tool_result block."""
        first_response = _mock_tool_use_response(
            tool_name="search_course_content",
            tool_input={"query": "lesson 5 MCP"},
            tool_id="tu_xyz",
        )
        second_response = _mock_text_response("Here is what lesson 5 covers.")

        with patch.object(generator.client.messages, "create",
                          side_effect=[first_response, second_response]) as mock_create:
            generator.generate_response(
                query="What is in lesson 5?",
                tools=tool_manager_with_mock_store.get_tool_definitions(),
                tool_manager=tool_manager_with_mock_store,
            )

        second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
        # Find the tool_result message (it's the last user message)
        tool_result_msg = next(
            m for m in second_call_messages if m["role"] == "user" and isinstance(m["content"], list)
        )
        result_block = tool_result_msg["content"][0]
        assert result_block["type"] == "tool_result"
        assert result_block["tool_use_id"] == "tu_xyz"

    def test_execute_tool_is_called_with_correct_arguments(self, generator):
        """ToolManager.execute_tool() must be called with the name and kwargs from the tool_use block."""
        first_response = _mock_tool_use_response(
            tool_name="search_course_content",
            tool_input={"query": "lesson 5 sampling", "lesson_number": 5},
            tool_id="tu_001",
        )
        second_response = _mock_text_response("Done.")

        mock_tm = MagicMock(spec=ToolManager)
        mock_tm.execute_tool.return_value = "Lesson 5: Advanced MCP..."
        mock_tm.get_tool_definitions.return_value = []

        with patch.object(generator.client.messages, "create",
                          side_effect=[first_response, second_response]):
            generator.generate_response(
                query="lesson 5",
                tools=[],
                tool_manager=mock_tm,
            )

        mock_tm.execute_tool.assert_called_once_with(
            "search_course_content",
            query="lesson 5 sampling",
            lesson_number=5,
        )

    # ------------------------------------------------------------------
    # Path 3: two tool rounds
    # ------------------------------------------------------------------

    def test_two_tool_rounds_makes_three_api_calls(self, generator, tool_manager_with_mock_store):
        """Two consecutive tool-use rounds should result in exactly 3 API calls."""
        r0 = _mock_tool_use_response("search_course_content", {"query": "course X outline"}, tool_id="tu_r0")
        r1 = _mock_tool_use_response("search_course_content", {"query": "similar topic"}, tool_id="tu_r1")
        r2 = _mock_text_response("Here is the final answer.")

        with patch.object(generator.client.messages, "create",
                          side_effect=[r0, r1, r2]) as mock_create:
            result = generator.generate_response(
                query="Find a course covering the same topic as lesson 4 of course X",
                tools=tool_manager_with_mock_store.get_tool_definitions(),
                tool_manager=tool_manager_with_mock_store,
            )

        assert mock_create.call_count == 3
        assert result == "Here is the final answer."

    def test_tools_available_in_both_rounds(self, generator, tool_manager_with_mock_store):
        """Tools must be present in round-0 and round-1 calls, but NOT in the forced synthesis call."""
        r0 = _mock_tool_use_response("search_course_content", {"query": "q1"}, tool_id="tu_r0")
        r1 = _mock_tool_use_response("search_course_content", {"query": "q2"}, tool_id="tu_r1")
        r2 = _mock_text_response("Done.")

        with patch.object(generator.client.messages, "create",
                          side_effect=[r0, r1, r2]) as mock_create:
            generator.generate_response(
                query="multi-step query",
                tools=tool_manager_with_mock_store.get_tool_definitions(),
                tool_manager=tool_manager_with_mock_store,
            )

        calls = mock_create.call_args_list
        assert "tools" in calls[0].kwargs, "Round 0 call should include tools"
        assert "tools" in calls[1].kwargs, "Round 1 call should include tools"
        assert "tools" not in calls[2].kwargs, "Forced synthesis call must NOT include tools"

    def test_second_round_tool_result_in_messages(self, generator, tool_manager_with_mock_store):
        """The forced synthesis call's messages must contain tool_results for both rounds."""
        r0 = _mock_tool_use_response("search_course_content", {"query": "q1"}, tool_id="tu_r0")
        r1 = _mock_tool_use_response("search_course_content", {"query": "q2"}, tool_id="tu_r1")
        r2 = _mock_text_response("Final.")

        with patch.object(generator.client.messages, "create",
                          side_effect=[r0, r1, r2]) as mock_create:
            generator.generate_response(
                query="multi-step",
                tools=tool_manager_with_mock_store.get_tool_definitions(),
                tool_manager=tool_manager_with_mock_store,
            )

        synthesis_messages = mock_create.call_args_list[2].kwargs["messages"]
        tool_use_ids = [
            block["tool_use_id"]
            for m in synthesis_messages
            if m["role"] == "user" and isinstance(m["content"], list)
            for block in m["content"]
            if block.get("type") == "tool_result"
        ]
        assert "tu_r0" in tool_use_ids
        assert "tu_r1" in tool_use_ids

    # ------------------------------------------------------------------
    # Path 4: tool execution error
    # ------------------------------------------------------------------

    def test_graceful_error_on_tool_failure(self, generator):
        """A RuntimeError from execute_tool must not propagate — the call chain continues."""
        first_response = _mock_tool_use_response(
            tool_name="search_course_content",
            tool_input={"query": "lesson 5"},
            tool_id="tu_err",
        )
        second_response = _mock_text_response("Recovered answer.")

        mock_tm = MagicMock(spec=ToolManager)
        mock_tm.execute_tool.side_effect = RuntimeError("DB unavailable")

        with patch.object(generator.client.messages, "create",
                          side_effect=[first_response, second_response]) as mock_create:
            result = generator.generate_response(
                query="lesson 5",
                tools=[],
                tool_manager=mock_tm,
            )

        assert mock_create.call_count == 2
        assert isinstance(result, str)

    def test_tool_error_content_in_messages(self, generator):
        """When execute_tool raises, the tool_result content must contain 'Tool execution failed'."""
        first_response = _mock_tool_use_response(
            tool_name="search_course_content",
            tool_input={"query": "lesson 5"},
            tool_id="tu_err",
        )
        second_response = _mock_text_response("Recovered.")

        mock_tm = MagicMock(spec=ToolManager)
        mock_tm.execute_tool.side_effect = RuntimeError("DB unavailable")

        with patch.object(generator.client.messages, "create",
                          side_effect=[first_response, second_response]) as mock_create:
            generator.generate_response(
                query="lesson 5",
                tools=[],
                tool_manager=mock_tm,
            )

        second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
        tool_result_content = next(
            block["content"]
            for m in second_call_messages
            if m["role"] == "user" and isinstance(m["content"], list)
            for block in m["content"]
            if block.get("type") == "tool_result"
        )
        assert "Tool execution failed" in tool_result_content
