"""
adaptation.py — Phase 2: Behavioral Adaptation Engine for Ava AI.

Conceptually distinct from conversation memory:
- Memory answers: "What does Ava know about this user?" (Facts, projects, history)
- Adaptation answers: "How should Ava respond to this user?" (Verbosity, technical depth, code examples, tone, examples)

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

ALLOWED_VALUES: dict[str, set] = {
    "verbosity": {"concise", "balanced", "detailed"},
    "technical_depth": {"beginner", "intermediate", "advanced"},
    "code_examples": {True, False},
    "step_by_step": {True, False},
    "examples": {True, False},
    "tone": {"friendly", "direct", "formal"},
}

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
    "examples": {
        True: [
            r"\b(give me an example|show me an example|examples help me understand|include examples|use examples|give practical examples)\b",
            r"\b(give (me )?(an )?example|show (me )?(an )?example|with examples?|practical examples?)\b",
        ],
        False: [
            r"\b(no examples|skip examples|don't give examples|do not give examples|just explain the concept|without examples)\b",
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
            r"\b(formal tone|professional tone|business professional|be formal)\b",
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


def is_valid_preference_value(preference: str, value: Any) -> bool:
    """Validate that value matches the strict type and allowed values for the preference."""
    if preference not in ALLOWED_VALUES:
        return False
    allowed = ALLOWED_VALUES[preference]
    if preference in ("code_examples", "step_by_step", "examples"):
        return isinstance(value, bool) and value in allowed
    return isinstance(value, str) and value in allowed


def get_adaptation_profile(user_id: str) -> dict:
    """
    Retrieve the user's persistent adaptation profile.
    Safely handles invalid JSON, missing dimensions, unknown dimensions, and invalid types,
    falling back gracefully to defaults. Bad adaptation data will never break chat.
    """
    try:
        record = db.get_adaptation_profile(user_id)
        if record and isinstance(record.get("profile"), dict):
            stored = record["profile"]
            profile = _clone_default_profile()
            for dim, default_item in DEFAULT_PROFILE.items():
                if dim in stored and isinstance(stored[dim], dict):
                    dim_data = stored[dim]
                    val = dim_data.get("value")
                    clean_val = val if is_valid_preference_value(dim, val) else default_item["value"]

                    conf = dim_data.get("confidence")
                    if isinstance(conf, (int, float)) and not isinstance(conf, bool) and 0.0 <= float(conf) <= 1.0:
                        clean_conf = round(float(conf), 3)
                    else:
                        clean_conf = default_item["confidence"]

                    profile[dim] = {"value": clean_val, "confidence": clean_conf}
                else:
                    profile[dim] = dict(default_item)
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
    When conflicting evidence arrives, it weakens the old preference before switching.
    """
    if preference not in ALLOWED_VALUES or not is_valid_preference_value(preference, target_value):
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
            # Contradicting evidence: weaken existing confidence first
            if curr_conf - delta < DEFAULT_CONFIDENCE:
                # Old preference weakened below baseline: crossover to target_value
                surplus = delta - (curr_conf - DEFAULT_CONFIDENCE)
                new_conf = min(1.0, DEFAULT_CONFIDENCE + surplus)
                profile[preference] = {"value": target_value, "confidence": round(new_conf, 3)}
            else:
                # Confidence in current value weakens gradually without immediately switching
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


def message_explicitly_requested(msg: str, preference: str, target_val: Any) -> bool:
    """Check if the user message contains an explicit behavioral pattern for this preference & value."""
    if not msg:
        return False
    patterns = PATTERNS_EXPLICIT.get(preference, {}).get(target_val, [])
    for pat in patterns:
        if re.search(pat, msg, re.IGNORECASE):
            return True
    return False


def process_feedback(user_id: str, message_id: str, helpful: bool) -> None:
    """
    Process thumbs-up / thumbs-down feedback conservatively.
    A positive feedback signal reinforces a preference ONLY when at least one of these is true:
      1. Preference was already learned with meaningful confidence (confidence >= CONFIDENCE_THRESHOLD),
      2. The user message explicitly requested that behavior,
      3. Repeated strategy feedback provides sufficient evidence (successes >= 3).
    A single thumbs-up on an answer containing code must NOT immediately establish a code preference.
    Negative feedback never inverts unrelated preferences.
    """
    if not user_id:
        return

    try:
        user_msg = ""
        agent_resp = ""
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT user_message, agent_response FROM messages WHERE message_id = ?",
                (message_id,)
            ).fetchone()
            if row:
                user_msg = row["user_message"] or ""
                agent_resp = row["agent_response"] or ""

        if agent_resp:
            strategy = _classify_strategy(agent_resp)
            db.record_strategy_feedback(user_id, strategy, helpful)

            profile = get_adaptation_profile(user_id)
            stats = db.get_strategy_stats(user_id)
            strat_succ = stats.get(strategy, {}).get("successes", 0)

            if helpful:
                # 1. Code examples reinforcement
                if "```" in agent_resp:
                    code_conf = profile.get("code_examples", {}).get("confidence", 0)
                    code_val = profile.get("code_examples", {}).get("value", False)
                    already_learned = (code_conf >= CONFIDENCE_THRESHOLD and code_val is True)
                    explicitly_requested = message_explicitly_requested(user_msg, "code_examples", True)
                    sufficient_evidence = (strat_succ >= 3)

                    if already_learned or explicitly_requested or sufficient_evidence:
                        update_signal(user_id, "code_examples", True, weight=0.3, evidence="verified_positive_code_feedback")

                # 2. Verbosity reinforcement
                verb_conf = profile.get("verbosity", {}).get("confidence", 0)
                verb_val = profile.get("verbosity", {}).get("value", "balanced")
                if len(agent_resp) < 450:
                    already_learned = (verb_conf >= CONFIDENCE_THRESHOLD and verb_val == "concise")
                    explicitly_requested = message_explicitly_requested(user_msg, "verbosity", "concise")
                    sufficient_evidence = (strat_succ >= 3)

                    if already_learned or explicitly_requested or sufficient_evidence:
                        update_signal(user_id, "verbosity", "concise", weight=0.3, evidence="verified_positive_concise_feedback")
                elif len(agent_resp) > 900:
                    already_learned = (verb_conf >= CONFIDENCE_THRESHOLD and verb_val == "detailed")
                    explicitly_requested = message_explicitly_requested(user_msg, "verbosity", "detailed")
                    sufficient_evidence = (strat_succ >= 3)

                    if already_learned or explicitly_requested or sufficient_evidence:
                        update_signal(user_id, "verbosity", "detailed", weight=0.3, evidence="verified_positive_detailed_feedback")

            else:
                # Conservative negative feedback
                # Only weaken if response explicitly exhibited that behavior and user preferred otherwise
                verb_val = profile.get("verbosity", {}).get("value", "balanced")
                verb_conf = profile.get("verbosity", {}).get("confidence", 0)
                if len(agent_resp) > 900 and verb_val == "concise" and verb_conf >= CONFIDENCE_THRESHOLD:
                    update_signal(user_id, "verbosity", "concise", weight=0.4, evidence="negative_feedback_on_overly_long_response")

                code_val = profile.get("code_examples", {}).get("value", False)
                code_conf = profile.get("code_examples", {}).get("confidence", 0)
                if "```" in agent_resp and code_val is False and code_conf >= CONFIDENCE_THRESHOLD:
                    update_signal(user_id, "code_examples", False, weight=0.4, evidence="negative_feedback_on_unwanted_code")

    except Exception as e:
        logger.warning(f"Adaptation feedback processing failed for {user_id}: {e}")


def get_strategy_score(user_id: str, strategy: str, prior_success: float = 1.0, prior_total: float = 2.0) -> float:
    """
    Computes a confidence-safe smoothed Bayesian score for a strategy:
    (successes + prior_success) / (successes + failures + prior_total)
    Default prior gives 1/2 = 0.50 when no evidence exists.
    """
    stats = db.get_strategy_stats(user_id)
    strat_data = stats.get(strategy, {"successes": 0, "failures": 0})
    succ = strat_data.get("successes", 0)
    fail = strat_data.get("failures", 0)
    return round((succ + prior_success) / (succ + fail + prior_total), 3)


def get_preferred_strategies(user_id: str, min_evidence: int = 3, threshold: float = 0.60) -> list[str]:
    """
    Returns list of strategies that meet the minimum evidence requirement (successes + failures >= min_evidence)
    and whose smoothed score meets or exceeds the threshold, sorted by score descending.
    A strategy with only 1 success / 0 failures is NOT considered preferred.
    """
    stats = db.get_strategy_stats(user_id)
    candidates = []
    for strat, data in stats.items():
        succ = data.get("successes", 0)
        fail = data.get("failures", 0)
        total = succ + fail
        if total >= min_evidence:
            score = get_strategy_score(user_id, strat)
            if score >= threshold:
                candidates.append((strat, score, total))
    candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [c[0] for c in candidates]


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

        # 5. Examples
        ex = profile.get("examples", {})
        if ex.get("confidence", 0) >= CONFIDENCE_THRESHOLD:
            if ex.get("value") is True:
                lines.append("- Examples: Include practical examples when useful.")
            elif ex.get("value") is False:
                lines.append("- Examples: Avoid unnecessary examples unless explicitly requested.")

        # 6. Tone
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

        header = "--- User response preferences ---\n"
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
            "If the user's current message explicitly asks for a different style (e.g., asking for detail when concise is learned, or asking for code when no code is learned), "
            "ALWAYS follow the current explicit request."
        )

        return header + body + footer

    except Exception as e:
        logger.error(f"Failed to generate adaptation context for {user_id}: {e}")
        return ""


def set_manual_preference(user_id: str, preference: str, value: Any, confidence: float = 0.85) -> dict:
    """
    Allows manual configuration of an adaptation dimension (e.g. via PATCH).
    Validates preference name, value against ALLOWED_VALUES, and confidence (0.0 <= confidence <= 1.0).
    Raises ValueError on invalid input (no silent clamping for API requests).
    """
    if preference not in ALLOWED_VALUES:
        raise ValueError(f"Unknown preference dimension: '{preference}'. Allowed: {sorted(list(ALLOWED_VALUES.keys()))}")

    if not is_valid_preference_value(preference, value):
        allowed_repr = sorted(list(ALLOWED_VALUES[preference])) if isinstance(list(ALLOWED_VALUES[preference])[0], str) else [True, False]
        raise ValueError(f"Invalid value '{value}' for preference '{preference}'. Allowed: {allowed_repr}")

    if confidence is None or isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        raise ValueError(f"Invalid confidence: {confidence}. Confidence must be a float between 0.0 and 1.0.")

    profile = get_adaptation_profile(user_id)
    profile[preference] = {
        "value": value,
        "confidence": round(float(confidence), 3),
    }
    db.set_adaptation_profile(user_id, profile)
    return profile
