"""
memory.py — Conversation memory for Ava AI, modeled on how Claude handles context:

1. In-session memory: the last WINDOW messages of the *current session only*
   (no cross-session bleed), plus a rolling summary of anything older than that
   window so long chats don't lose earlier context.

2. Cross-session memory: a small persistent per-user "memory" blob — durable
   facts (name, preferences, ongoing projects, recurring issues) extracted
   periodically from conversation and carried into every new chat, similar to
   Claude's memory feature.

Both pieces are injected into the LLM prompt but kept clearly separated and
labeled, so the model (and a human reading logs) can tell "what Ava knows about
you in general" apart from "what's happened in this chat so far."
"""
import database as db
from llm import call_llm

# How many of the most recent messages in the *current session* are sent verbatim.
SESSION_WINDOW = 20
# Max characters of each agent response kept in the verbatim window before truncating.
RESPONSE_TRUNCATE = 800
# Once a session has more than this many messages, older ones get rolled into a summary.
SUMMARY_TRIGGER = SESSION_WINDOW
# Re-extract cross-session user memory every N new messages from that user.
USER_MEMORY_REFRESH_INTERVAL = 8


def _format_messages(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        lines.append(f"User: {m['user_message']}")
        resp = m['agent_response'] or ""
        if len(resp) > RESPONSE_TRUNCATE:
            resp = resp[:RESPONSE_TRUNCATE] + "..."
        lines.append(f"Ava: {resp}")
    return "\n".join(lines)


def get_session_context(user_id: str, session_id: str) -> str:
    """
    Builds the in-session conversation context: a rolling summary of older
    messages (if any) followed by the verbatim recent window, scoped strictly
    to this session_id so other chats never leak in.
    """
    total = db.count_session_messages(session_id)
    if total == 0:
        return ""

    state = db.get_session_summary_state(session_id)
    existing_summary = state["summary"]
    summarized_through = state["summary_through_count"]

    # If the session has grown past what's already summarized and beyond the
    # verbatim window, roll the newly-aged-out messages into the summary.
    needs_summary_update = total > SUMMARY_TRIGGER and (total - SESSION_WINDOW) > summarized_through
    if needs_summary_update:
        new_count = total - SESSION_WINDOW
        to_fold_in = db.get_messages_in_range(session_id, offset=summarized_through, count=new_count - summarized_through)
        if to_fold_in:
            fold_text = _format_messages(to_fold_in)
            if existing_summary:
                summary_prompt = (
                    "Update this running summary of an ongoing conversation by incorporating the new "
                    "exchanges below. Keep it concise (4-6 sentences), preserve important facts, decisions, "
                    "and unresolved issues, and drop small talk.\n\n"
                    f"Existing summary:\n{existing_summary}\n\n"
                    f"New exchanges to incorporate:\n{fold_text}\n\n"
                    "Updated summary:"
                )
            else:
                summary_prompt = (
                    "Summarize this conversation concisely (4-6 sentences), preserving important facts, "
                    "decisions, and unresolved issues, and dropping small talk.\n\n"
                    f"{fold_text}\n\nSummary:"
                )
            try:
                new_summary = call_llm(
                    summary_prompt, temperature=0.3, max_tokens=220,
                    system_prompt_override="You are a precise conversation summarizer. Output only the summary, no preamble.",
                )
                db.update_session_summary(session_id, new_summary, through_count=new_count)
                existing_summary = new_summary
                summarized_through = new_count
            except Exception:
                pass  # keep using the old summary (or none) if summarization fails

    recent = db.get_recent_messages(user_id, session_id=session_id, limit=SESSION_WINDOW)
    parts = []
    if existing_summary:
        parts.append(f"Summary of earlier messages in this conversation:\n{existing_summary}")
    if recent:
        parts.append(f"Recent messages in this conversation:\n{_format_messages(recent)}")
    return "\n\n".join(parts) + "\n\n" if parts else ""


def get_user_memory_context(user_id: str) -> str:
    """Returns the durable cross-session memory blob for this user, if any."""
    mem = db.get_user_memory(user_id)
    text = mem["memory_text"]
    if not text:
        return ""
    return f"What you remember about this user from past conversations:\n{text}\n\n"


def maybe_refresh_user_memory(user_id: str, session_id: str, latest_user_message: str, latest_agent_response: str) -> None:
    """
    Periodically extracts durable facts about the user (preferences, ongoing
    projects, recurring topics) from recent activity and merges them into the
    persistent cross-session memory blob. Cheap no-op most turns; only calls
    the LLM every USER_MEMORY_REFRESH_INTERVAL messages.
    """
    total = db.count_all_user_messages(user_id)
    mem = db.get_user_memory(user_id)
    if total - mem["message_count_at_update"] < USER_MEMORY_REFRESH_INTERVAL:
        return

    recent = db.get_recent_messages(user_id, session_id=session_id, limit=SESSION_WINDOW)
    if not recent:
        return
    recent_text = _format_messages(recent)
    existing_memory = mem["memory_text"]

    extraction_prompt = f"""Extract durable, useful facts about this user from the conversation below —
things like their name, role, ongoing projects, preferences, recurring issues, or context that would
help in future unrelated conversations. Do NOT include one-off details that only matter for this single
exchange. Write 3-6 short bullet points, plain text, no preamble. If there's genuinely nothing durable
worth keeping, respond with exactly: NONE

{f"Existing known facts:{chr(10)}{existing_memory}{chr(10)}{chr(10)}" if existing_memory else ""}Recent conversation:
{recent_text}

Updated facts (merge with existing, remove anything outdated, keep it concise):"""

    try:
        extracted = call_llm(
            extraction_prompt, temperature=0.2, max_tokens=300,
            system_prompt_override="You extract durable user facts from conversation logs. Output only the bullet points or NONE, no preamble.",
        )
        extracted = extracted.strip()
        if extracted and extracted.upper() != "NONE":
            db.set_user_memory(user_id, extracted, message_count_at_update=total)
        else:
            # Nothing new to add — still bump the watermark so we don't re-check every turn.
            db.set_user_memory(user_id, existing_memory, message_count_at_update=total)
    except Exception:
        pass  # memory refresh is best-effort; never break the chat turn over it