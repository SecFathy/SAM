"""Tests for the agent loop and history."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sam.agent.history import ConversationHistory
from sam.models.streaming import StreamAccumulator, ToolCallAccumulator


# --- ConversationHistory ---

def test_history_add_messages():
    history = ConversationHistory()
    history.add_system("You are SAM.")
    history.add_user("Hello")
    history.add_assistant("Hi there!")

    messages = history.get_messages()
    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"


def test_history_system_replacement():
    history = ConversationHistory()
    history.add_system("First system")
    history.add_system("Updated system")

    messages = history.get_messages()
    assert len(messages) == 1
    assert messages[0]["content"] == "Updated system"


def test_history_tool_result():
    history = ConversationHistory()
    history.add_tool_result("call_123", "File contents here")

    messages = history.get_messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "tool"
    assert messages[0]["tool_call_id"] == "call_123"


def test_history_token_estimation():
    history = ConversationHistory()
    history.add_system("Short system prompt")
    history.add_user("Hello world")

    tokens = history.estimate_tokens()
    assert tokens > 0
    assert tokens < 100


def test_history_needs_condensation():
    history = ConversationHistory(context_window=100)
    # Add enough content to exceed 75% of 100 tokens
    history.add_system("x " * 50)
    history.add_user("y " * 50)

    assert history.needs_condensation


def test_history_serialization():
    history = ConversationHistory(context_window=4096)
    history.add_system("sys")
    history.add_user("hello")
    history.add_assistant("hi")

    data = history.to_serializable()
    restored = ConversationHistory.from_serializable(data, context_window=4096)
    assert len(restored.messages) == 3


# --- StreamAccumulator ---

def test_accumulator_content():
    acc = StreamAccumulator()
    assert acc.content == ""
    assert not acc.has_tool_calls


def test_accumulator_tool_calls():
    acc = StreamAccumulator()
    acc.tool_calls[0] = ToolCallAccumulator(
        id="call_1",
        name="read_file",
        arguments='{"path": "test.py"}',
    )

    assert acc.has_tool_calls
    assert len(acc.tool_call_list) == 1
    assert acc.tool_call_list[0].name == "read_file"


def test_tool_call_parsed_arguments():
    tc = ToolCallAccumulator(
        id="call_1",
        name="read_file",
        arguments='{"path": "test.py"}',
    )
    args = tc.parsed_arguments()
    assert args == {"path": "test.py"}


def test_tool_call_malformed_json():
    tc = ToolCallAccumulator(
        id="call_1",
        name="read_file",
        arguments='{"path": "test.py"',  # missing closing brace
    )
    args = tc.parsed_arguments()
    assert args == {"path": "test.py"}


def test_accumulator_from_complete():
    """Test creating accumulator from a mock non-streaming response."""
    mock_message = MagicMock()
    mock_message.content = "Hello!"
    mock_message.tool_calls = None

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5
    mock_usage.total_tokens = 15

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    acc = StreamAccumulator.from_complete(mock_response)
    assert acc.content == "Hello!"
    assert acc.finish_reason == "stop"
    assert acc.usage["total_tokens"] == 15
