"""Context condensation — summarize old history at 75% capacity."""

from __future__ import annotations

from sam.agent.history import ConversationHistory
from sam.models.provider import ModelProvider

CONDENSATION_PROMPT = """Summarize the following conversation history concisely. Focus on:
1. What tasks were requested and completed
2. What files were modified and how
3. Key decisions made
4. Current state of the work
5. Any pending issues or next steps

Keep the summary focused and actionable. Preserve file paths, function names, and specific technical details.

Conversation to summarize:
{conversation}"""


async def condense_history(
    history: ConversationHistory,
    provider: ModelProvider,
    keep_recent: int = 4,
) -> None:
    """Condense old messages into a summary, keeping recent messages intact.

    Args:
        history: The conversation history to condense
        provider: Model provider for generating the summary
        keep_recent: Number of recent message pairs to keep verbatim
    """
    messages = history.messages

    # Find system message
    system_msg = None
    non_system = []
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg
        else:
            non_system.append(msg)

    if len(non_system) <= keep_recent * 2:
        return  # Not enough messages to condense

    # Split into old (to summarize) and recent (to keep)
    old_messages = non_system[: -keep_recent * 2]
    recent_messages = non_system[-keep_recent * 2 :]

    # Format old messages for summarization
    conversation_text = _format_messages(old_messages)

    # Generate summary
    summary_prompt = CONDENSATION_PROMPT.format(conversation=conversation_text)
    summary_messages = [
        {"role": "system", "content": "You are a conversation summarizer. Be concise and precise."},
        {"role": "user", "content": summary_prompt},
    ]

    try:
        result = await provider.chat_complete(summary_messages)
        summary = result.content
    except Exception:
        # If summarization fails, just truncate
        summary = _format_messages(old_messages[-4:])

    # Rebuild history: system + summary + recent
    new_messages = []
    if system_msg:
        new_messages.append(system_msg)

    new_messages.append({
        "role": "user",
        "content": f"[Previous conversation summary]\n{summary}",
    })
    new_messages.append({
        "role": "assistant",
        "content": "Understood. I have the context from our previous conversation. How can I help you continue?",
    })
    new_messages.extend(recent_messages)

    history.messages = new_messages


def _format_messages(messages: list[dict]) -> str:
    """Format messages into a readable string for summarization."""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if role == "tool":
            tool_id = msg.get("tool_call_id", "")
            lines.append(f"[Tool Result ({tool_id})]: {content[:500]}")
        elif role == "assistant" and "tool_calls" in msg:
            lines.append(f"Assistant: {content}")
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                lines.append(f"  -> Called {func.get('name', '?')}({func.get('arguments', '')[:200]})")
        else:
            lines.append(f"{role.capitalize()}: {content[:1000]}")

    return "\n".join(lines)
