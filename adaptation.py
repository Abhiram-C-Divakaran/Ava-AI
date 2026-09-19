"""
adaptation.py — Phase 2: Behavioral Adaptation Engine for Ava AI.

Conceptually distinct from conversation memory:
- Memory answers: "What does Ava know about this user?" (Facts, projects, history)
- Adaptation answers: "How should Ava respond to this user?" (Verbosity, technical depth, code examples, tone)

Architecture:
- LLM + persistent memory + behavioral adaptation + feedback-driven learning
- Zero RAG / Zero embeddings / Zero vector search
- Deterministic rule-based signal observation
- Conservative confidence updates (0.0 <= confidence <= 1.0)
- Explicit requests take priority over learned adaptation
"""

import re
import json
import logging
from typing import Any, Optional
import database as db

logger = logging.getLogger("ava.adaptation")

# ─── Learning Constants ───────────────────────────────────────────────────────
DEFAULT_CONFIDENCE = 0.50
CONFIDENCE_THRESHOLD = 0.60  # Minimum confidence to inject into prompt context
LEARNING_RATE = 0.06         # Conservative step per interaction
EXPLICIT_SIGNAL_WEIGHT = 2.0 # Explicit instructions carry higher weight
IMPLICIT_SIGNAL_WEIGHT = 1.0 # Implicit observation weight

DEFAULT_PROFILE: dict[str, dict[str, Any]] = {
    "verbosity": {"value": "balanced", "confidence": DEFAULT_CONFIDENCE},
    "technical_depth": {"value": "intermediate", "confidence": DEFAULT_CONFIDENCE},
    "code_examples": {"value": False, "confidence": DEFAULT_CONFIDENCE},
    "step_by_step": {"value": False, "confidence": DEFAULT_CONFIDENCE},
    "examples": {"value": True, "confidence": DEFAULT_CONFIDENCE},
    "tone": {"value": "friendly", "confidence": DEFAULT_CONFIDENCE},
}

# ─── Pattern Definitions ──────────────────────────────────────────────────────
# Explicit Patterns (weight = EXPLICIT_SIGNAL_WEIGHT)
PATTERNS_EXPLICIT = {
    "verbosity": {
        "concise": [
            r"\b(keep it (short|brief)|be concise|make it (shorter|brief)|give me a (short|concise) answer|in a few words|briefly answer|short answers only)\b",
            r"\b(always (keep it|be) (short|concise)|too (long|wordy)|cut the fluff|skip the pleasantries|keep your answers (short|concise))\b",
        ],
        "detailed": [
            r"\b(explain (this )?in (much )?more detail|detailed explanation|go (much )?deeper|deep dive|comprehensive (overview|explanation))\b",
            r"\b(elaborate (more|further)|give me (a )?thorough explanation|in-depth analysis|detailed breakdown)\b",
        ],
    },
    "code_examples": {
        True: [
            r"\b(show (me )?(the )?code|give me (the )?code|code examples?( please)?|python code example|code snippet)\b",
            r"\b(i prefer (python )?code examples|write (the )?code for this|implement in code)\b",
        ],
        False: [
            r"\b(don't give me code|do not give me code|no code|without code|just explain it|concept only|no programming)\b",
        ],
    },
    "step_by_step": {
        True: [
            r"\b(step by step|walk me through|break it down step by step|step-by-step explanation)\b",
            r"\b(guide me step by step|one step at a time|explain things step by step)\b",
        ],
        False: [
            r"\b(all at once|no need for steps|skip the steps|just give me the final answer)\b",
        ],
    },
    "technical_depth": {
        "advanced": [
            r"\b(skip the basic(s)?|you can skip basic explanation|advanced technical|expert level|low level implementation)\b",
            r"\b(deep technical details|under the hood|technical architecture)\b",
        ],
        "beginner": [
            r"\b(explain like i('m| am) 5|eli5|for beginners|simple terms|in plain english|easy to understand|simple explanation)\b",
        ],
    },
    "tone": {
        "direct": [
            r"\b(be direct|straight to the point|cut to the chase|no fluff|no pleasantries)\b",
        ],
        "friendly": [
            r"\b(be friendly|warm tone|conversational tone|casual tone)\b",
        ],
        "formal": [
            r"\b(formal tone|professional tone|business professional)\b",
        ],
    },
}

# Implicit Patterns (weight = IMPLICIT_SIGNAL_WEIGHT)
PATTERNS_IMPLICIT = {
    "verbosity": {
        "concise": [r"^(tl;?dr|short summary|summary|quick answer)[!?.]*$"],
        "detailed": [r"\b(tell me more|what else|expand on that|can you elaborate)\b"],
    },
    "code_examples": {
        True: [r"\b(how to code|syntax for|function to)\b"],
    },
    "step_by_step": {
        True: [r"\b(what do i do next|how do i start|first step)\b"],
    },
}


# ─── Core Helpers ─────────────────────────────────────────────────────────────

def _clone_default_profile() -> dict[str, dict[str, Any]]:
    return {k: dict(v) for k, v in DEFAULT_PROFILE.items()}


def get_adaptation_profile(user_id: str) -> dict:
    """
    Retrieve the user's persistent adaptation profile.
    If the user has no profile yet, initializes and stores the default profile.
    """
    try:
        record = db.get_adaptation_profile(user_id)
        if record and record.get("profile"):
            profile = _clone_default_profile()
            stored = record["profile"]
            for key, default_item in profile.items():
                if key in stored and isinstance(stored[key], dict):
                    profile[key] = {
                        "value": stored[key].get("value", default_item["value"]),
                        "confidence": round(float(stored[key].get("confidence", default_item["confidence"])), 3),
                    }
            return profile
        else:
            default_prof = _clone_default_profile()
            db.set_adaptation_profile(user_id, default_prof, interaction_count=0)
            return default_prof
    except Exception as e:
        logger.error(f"Error loading adaptation profile for {user_id}: {e}")
        return _clone_default_profile()


def reset_adaptation_profile(user_id: str) -> None:
    """
    Reset user's behavioral profile and strategy stats to defaults.
    Conceptually separate from factual memory and conversation history (which are preserved).
    """
    try:
        db.clear_adaptation_profile(user_id)
    except Exception as e:
        logger.error(f"Error clearing adaptation profile for {user_id}: {e}")


def update_signal(
    user_id: str,
    preference: str,
    target_value: Any,
    weight: float = 1.0,
    evidence: str = "",
) -> None:
    """
    Apply a conservative confidence-bounded update toward target_value.
    0.0 <= confidence <= 1.0
    """
    if preference not in DEFAULT_PROFILE:
        return

    try:
        profile = get_adaptation_profile(user_id)
        current = profile.get(preference, DEFAULT_PROFILE[preference])
        curr_val = current["value"]
        curr_conf = float(current.get("confidence", DEFAULT_CONFIDENCE))

        delta = LEARNING_RATE * weight

        if curr_val == target_value:
            # Reinforce current value
            new_conf = min(1.0, curr_conf + delta)
            profile[preference] = {"value": curr_val, "confidence": round(new_conf, 3)}
        else:
            # Contradicting evidence
            if curr_conf - delta < DEFAULT_CONFIDENCE:
                # Value shifts over to target_value with conservative confidence
                surplus = delta - (curr_conf - DEFAULT_CONFIDENCE)
                new_conf = min(1.0, DEFAULT_CONFIDENCE + surplus)
                profile[preference] = {"value": target_value, "confidence": round(new_conf, 3)}
            else:
                # Confidence in current value weakens
                new_conf = max(0.0, curr_conf - delta)
                profile[preference] = {"value": curr_val, "confidence": round(new_conf, 3)}

        db.set_adaptation_profile(user_id, profile)
    except Exception as e:
        logger.error(f"Error updating adaptation signal for {user_id}: {e}")


# ─── Interaction Observation ──────────────────────────────────────────────────

def observe_interaction(
    user_id: str,
    user_message: str,
    agent_response: str,
    intent: Optional[str] = None,
    sentiment: Optional[str] = None,
) -> None:
    """
    Evaluates the user's message for behavioral preference signals.
    Uses fast deterministic pattern matching (No external LLM / No RAG).
    """
    if not user_id or not user_message:
        return

    msg = user_message.strip().lower()

    try:
        # Increment interaction counter
        db.increment_adaptation_interaction_count(user_id)

        # 1. Check explicit patterns first (weight = EXPLICIT_SIGNAL_WEIGHT)
        detected_explicit = set()
        for pref, val_dict in PATTERNS_EXPLICIT.items():
            for val, patterns in val_dict.items():
                for pat in patterns:
                    if re.search(pat, msg, re.IGNORECASE):
                        update_signal(user_id, pref, val, weight=EXPLICIT_SIGNAL_WEIGHT, evidence=pat)
                        detected_explicit.add(pref)
                        break

        # 2. Check implicit patterns for dimensions not explicitly set
        for pref, val_dict in PATTERNS_IMPLICIT.items():
            if pref in detected_explicit:
                continue
            for val, patterns in val_dict.items():
                for pat in patterns:
                    if re.search(pat, msg, re.IGNORECASE):
                        update_signal(user_id, pref, val, weight=IMPLICIT_SIGNAL_WEIGHT, evidence=pat)
                        break

    except Exception as e:
        logger.warning(f"Adaptation observation failed for {user_id}: {e}")


# ─── Strategy Tracking & Feedback ─────────────────────────────────────────────

def _classify_strategy(response_text: str) -> str:
    """Determine the behavioral response strategy utilized in the agent reply."""
    resp = response_text.strip()
    has_code = "```" in resp
    has_steps = bool(re.search(r"^(\d+\.|[-*])\s+", resp, re.MULTILINE))
    is_short = len(resp) < 450

    if is_short and has_code:
        return "concise_with_code"
    elif is_short:
        return "concise_direct"
    elif has_code and has_steps:
        return "step_by_step_code"
    elif has_steps:
        return "detailed_step_by_step"
    elif has_code:
        return "code_first"
    else:
        return "detailed_explanation"


def process_feedback(user_id: str, message_id: str, helpful: bool) -> None:
    """
    Process thumbs-up / thumbs-down feedback conservatively.
    Updates behavioral strategy statistics and adjusts profile signals if mismatched.
    """
    if not user_id:
        return

    try:
        # Find the message if possible to determine response strategy
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT user_message, agent_response FROM messages WHERE message_id = ?",
                (message_id,)
            ).fetchone()

        if row:
            agent_resp = row["agent_response"] or ""
            strategy = _classify_strategy(agent_resp)
            db.record_strategy_feedback(user_id, strategy, helpful)

            profile = get_adaptation_profile(user_id)
            verbosity_pref = profile.get("verbosity", {}).get("value", "balanced")
            code_pref = profile.get("code_examples", {}).get("value", False)

            if not helpful:
                # Conservative negative feedback adjustments
                # e.g., if response was excessively long (>900 chars) while user prefers concise, reinforce concise
                if len(agent_resp) > 900 and verbosity_pref == "concise":
                    update_signal(user_id, "verbosity", "concise", weight=0.5, evidence="negative_feedback_on_long_response")
                # e.g., if response had code but user preferred no code
                if "```" in agent_resp and code_pref is False:
                    update_signal(user_id, "code_examples", False, weight=0.5, evidence="negative_feedback_on_code")
            else:
                # Positive reinforcement
                if "```" in agent_resp:
                    update_signal(user_id, "code_examples", True, weight=0.3, evidence="positive_feedback_on_code")
                if len(agent_resp) < 450 and verbosity_pref == "concise":
                    update_signal(user_id, "verbosity", "concise", weight=0.3, evidence="positive_feedback_on_concise")

    except Exception as e:
        logger.warning(f"Adaptation feedback processing failed for {user_id}: {e}")


# ─── Context Generation for Prompt Injection ──────────────────────────────────

def get_adaptation_context(user_id: str) -> str:
    """
    Generates a concise behavioral guidance string for prompt injection.
    Only includes dimensions where confidence >= CONFIDENCE_THRESHOLD.
    Explicitly emphasizes that current user instructions override learned defaults.
    """
    try:
        profile = get_adaptation_profile(user_id)
        lines = []

        # 1. Verbosity
        verb = profile.get("verbosity", {})
        if verb.get("confidence", 0) >= CONFIDENCE_THRESHOLD:
            v_val = verb.get("value")
            if v_val == "concise":
                lines.append("- Verbosity: Prefer concise, direct, and to-the-point answers. Omit boilerplate and unnecessary filler.")
            elif v_val == "detailed":
                lines.append("- Verbosity: Provide thorough, comprehensive explanations with depth.")

        # 2. Code Examples
        code = profile.get("code_examples", {})
        if code.get("confidence", 0) >= CONFIDENCE_THRESHOLD:
            if code.get("value"):
                lines.append("- Code Examples: Include clean, runnable code examples whenever applicable.")
            else:
                lines.append("- Code Examples: Avoid unprompted code snippets; focus on conceptual and architectural explanations.")

        # 3. Technical Depth
        depth = profile.get("technical_depth", {})
        if depth.get("confidence", 0) >= CONFIDENCE_THRESHOLD:
            d_val = depth.get("value")
            if d_val == "advanced":
                lines.append("- Technical Level: Advanced. You may skip introductory concepts and discuss mechanics directly.")
            elif d_val == "beginner":
                lines.append("- Technical Level: Beginner-friendly. Use intuitive analogies, avoid unexplained jargon.")

        # 4. Step by Step
        step = profile.get("step_by_step", {})
        if step.get("confidence", 0) >= CONFIDENCE_THRESHOLD and step.get("value"):
            lines.append("- Structure: Prefer structured, step-by-step breakdowns.")

        # 5. Tone
        tone = profile.get("tone", {})
        if tone.get("confidence", 0) >= CONFIDENCE_THRESHOLD:
            t_val = tone.get("value")
            if t_val == "direct":
                lines.append("- Tone: Direct, professional, and efficient.")
            elif t_val == "friendly":
                lines.append("- Tone: Warm, helpful, and collaborative.")
            elif t_val == "formal":
                lines.append("- Tone: Professional and formal.")

        if not lines:
            return ""

        header = "--- User response preferences (Learned Adaptation Profile) ---\n"
        header += "Ava has learned the following response preferences for this user:\n"
        body = "\n".join(lines)
        footer = (
            "\n\nIMPORTANT PRIORITY RULE:\n"
            "Learned adaptation preferences are guidance, NOT absolute mandates.\n"
            "Priority order:\n"
            "1. Safety and system rules\n"
            "2. The user's CURRENT explicit request in this prompt (overrides any learned preference)\n"
            "3. Explicit custom instructions in user profile\n"
            "4. Learned adaptation preferences above\n"
            "5. Default Ava behavior\n"
            "If the user's current message explicitly asks for a different style (e.g., asking for detail when concise is learned), "
            "ALWAYS follow the current explicit request."
        )

        return header + body + footer

    except Exception as e:
        logger.error(f"Failed to generate adaptation context for {user_id}: {e}")
        return ""


def set_manual_preference(user_id: str, preference: str, value: Any, confidence: float = 0.85) -> dict:
    """Allows manual configuration or inspection of an adaptation dimension (e.g. via PATCH)."""
    if preference not in DEFAULT_PROFILE:
        raise ValueError(f"Unknown preference dimension: {preference}")

    profile = get_adaptation_profile(user_id)
    profile[preference] = {
        "value": value,
        "confidence": round(min(1.0, max(0.0, float(confidence))), 3),
    }
    db.set_adaptation_profile(user_id, profile)
    return profile
