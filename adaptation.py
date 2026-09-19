"""
adaptation.py — Phase 3: Closed-Loop Strategy Learning & Behavioral Adaptation Engine.

Conceptually distinct from conversation memory:
- Memory answers: "What does Ava know about this user?" (Facts, projects, history)
- Adaptation answers: "How should Ava respond to this user?" (Verbosity, technical depth, code examples, tone, examples, strategy policy)

Architecture:
- LLM + persistent memory + behavioral adaptation + feedback-driven self-learning
- Response -> Feedback -> Strategy outcome -> Strategy confidence -> Preferred behavior policy -> Future system prompt -> Future response
- Zero RAG / Zero embeddings / Zero vector search
- Deterministic rule-based signal observation
- Conservative confidence updates (0.0 <= confidence <= 1.0)
- Explicit user requests take strict priority over learned adaptation
"""

import re
import json
import logging
from datetime import datetime
from typing import Any, Optional
import database as db

logger = logging.getLogger("ava.adaptation")

# ─── Learning Constants ───────────────────────────────────────────────────────
DEFAULT_CONFIDENCE = 0.50
CONFIDENCE_THRESHOLD = 0.60  # Minimum confidence to inject into prompt context
LEARNING_RATE = 0.06         # Conservative step per interaction
EXPLICIT_SIGNAL_WEIGHT = 2.0 # Explicit instructions carry higher weight
IMPLICIT_SIGNAL_WEIGHT = 1.0 # Implicit observation weight

MIN_STRATEGY_EVIDENCE = 3    # Minimum feedback samples needed to prefer a strategy
DECAY_HALF_LIFE_DAYS = 60.0  # Half-life for evidence decay (older evidence decays slowly)

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

SUPPORTED_STRATEGIES: set[str] = {
    "concise_with_code",
    "concise_direct",
    "step_by_step_code",
    "detailed_step_by_step",
    "code_first",
    "detailed_explanation",
}

STRATEGY_GUIDANCE_MAP: dict[str, str] = {
    "concise_direct": "Provide a short, direct answer with minimal extra explanation.",
    "concise_with_code": "Prefer concise responses with focused code examples when appropriate. Provide a short explanation followed by clean, focused code.",
    "detailed_step_by_step": "Provide a thorough, structured, step-by-step walkthrough.",
    "step_by_step_code": "Provide a structured, step-by-step explanation with code snippets at relevant steps.",
    "code_first": "Lead directly with the code implementation, then provide explanation afterward.",
    "detailed_explanation": "Provide deep conceptual and architectural explanations before practical implementation.",
}

# ─── Pattern Definitions ──────────────────────────────────────────────────────
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


def process_feedback(user_id: str, message_id: str, helpful: bool, timestamp: Optional[str] = None) -> None:
    """
    Process thumbs-up / thumbs-down feedback conservatively.
    Updates behavioral strategy statistics and adjusts profile signals if verified.
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
            if strategy in SUPPORTED_STRATEGIES:
                db.record_strategy_feedback(user_id, strategy, helpful, timestamp=timestamp)

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


# ─── Evidence Decay & Strategy Scoring ────────────────────────────────────────

def calculate_evidence_decay(
    last_updated: Optional[str],
    half_life_days: float = DECAY_HALF_LIFE_DAYS,
    now_time: Optional[datetime] = None,
) -> float:
    """
    Computes a slow half-life decay factor: decay_factor = 2.0^(-delta_days / half_life_days).
    Recent evidence has decay factor close to 1.0; 6-month-old evidence has decayed weight,
    but old repeated evidence still contributes.
    """
    if not last_updated:
        return 1.0
    try:
        if isinstance(last_updated, str):
            try:
                dt = datetime.fromisoformat(last_updated)
            except Exception:
                clean_ts = last_updated.replace("T", " ").split(".")[0].split("+")[0].split("Z")[0].strip()
                dt = datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
        elif isinstance(last_updated, datetime):
            dt = last_updated
        else:
            return 1.0

        current = now_time or datetime.now(timezone.utc)
        if dt.tzinfo is not None and current.tzinfo is None:
            current = current.replace(tzinfo=dt.tzinfo)
        elif dt.tzinfo is None and current.tzinfo is not None:
            dt = dt.replace(tzinfo=current.tzinfo)

        delta = (current - dt).total_seconds() / 86400.0  # elapsed days
        if delta <= 0:
            return 1.0
        return max(0.05, round(2.0 ** (-delta / half_life_days), 4))
    except Exception:
        return 1.0


def get_strategy_score(
    user_id: str,
    strategy: str,
    prior_success: float = 1.0,
    prior_total: float = 2.0,
    apply_decay: bool = True,
    now_time: Optional[datetime] = None,
) -> float:
    """
    Computes a confidence-safe smoothed Bayesian score for a strategy,
    optionally applying gradual half-life decay to older evidence:
    (effective_successes + prior_success) / (effective_successes + effective_failures + prior_total)
    Default prior gives 1/2 = 0.50 when no evidence exists.
    """
    if strategy not in SUPPORTED_STRATEGIES:
        return 0.50

    try:
        stats = db.get_strategy_stats(user_id)
        strat_data = stats.get(strategy, {"successes": 0, "failures": 0})
        succ = max(0, strat_data.get("successes", 0))
        fail = max(0, strat_data.get("failures", 0))

        if apply_decay and (succ > 0 or fail > 0):
            decay = calculate_evidence_decay(strat_data.get("last_updated"), now_time=now_time)
            eff_succ = succ * decay
            eff_fail = fail * decay
        else:
            eff_succ = float(succ)
            eff_fail = float(fail)

        return round((eff_succ + prior_success) / (eff_succ + eff_fail + prior_total), 3)
    except Exception as e:
        logger.warning(f"Error calculating strategy score for {user_id}/{strategy}: {e}")
        return 0.50


def is_strategy_suppressed(user_id: str, strategy: str) -> bool:
    """
    Checks if a strategy is suppressed due to repeated negative feedback.
    Suppressed if total evidence >= MIN_STRATEGY_EVIDENCE and failures > successes (or score < 0.40).
    A single dislike does NOT permanently ban or suppress a strategy.
    """
    if strategy not in SUPPORTED_STRATEGIES:
        return True
    try:
        stats = db.get_strategy_stats(user_id)
        data = stats.get(strategy)
        if not data:
            return False
        succ = max(0, data.get("successes", 0))
        fail = max(0, data.get("failures", 0))
        total = succ + fail
        if total < MIN_STRATEGY_EVIDENCE:
            return False
        if fail > succ:
            return True
        score = get_strategy_score(user_id, strategy, apply_decay=False)
        return score < 0.40
    except Exception as e:
        logger.warning(f"Error checking strategy suppression for {user_id}/{strategy}: {e}")
        return False


def get_avoided_strategies(user_id: str) -> list[str]:
    """Returns list of supported strategies that are currently suppressed due to negative feedback."""
    try:
        return [s for s in sorted(SUPPORTED_STRATEGIES) if is_strategy_suppressed(user_id, s)]
    except Exception as e:
        logger.warning(f"Error getting avoided strategies for {user_id}: {e}")
        return []


def get_preferred_strategies(
    user_id: str,
    min_evidence: int = MIN_STRATEGY_EVIDENCE,
    threshold: float = 0.60,
    apply_decay: bool = True,
    now_time: Optional[datetime] = None,
) -> list[str]:
    """
    Returns list of strategies meeting the minimum evidence requirement (total >= min_evidence),
    with smoothed score >= threshold, and NOT suppressed.
    A strategy with only 1 success / 0 failures is NOT considered preferred.
    """
    try:
        stats = db.get_strategy_stats(user_id)
        candidates = []
        for strat, data in stats.items():
            if strat not in SUPPORTED_STRATEGIES:
                continue
            if is_strategy_suppressed(user_id, strat):
                continue

            succ = max(0, data.get("successes", 0))
            fail = max(0, data.get("failures", 0))
            total = succ + fail
            if total >= min_evidence:
                score = get_strategy_score(user_id, strat, apply_decay=apply_decay, now_time=now_time)
                if score >= threshold:
                    candidates.append((strat, score, total))

        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return [c[0] for c in candidates]
    except Exception as e:
        logger.warning(f"Error getting preferred strategies for {user_id}: {e}")
        return []


# ─── Task Domain & Conflict Resolution ────────────────────────────────────────

def _detect_task_domain(user_message: str) -> str:
    """
    Determines query intent/domain deterministically without LLM calls.
    Returns 'programming', 'conceptual', or 'general'.
    """
    if not user_message:
        return "general"
    msg = user_message.lower()

    prog_keywords = [
        "code", "python", "javascript", "function", "syntax", "bug", "error",
        "exception", "script", "api", "implement", "class", "method", "compile",
        "algorithm", "array", "sql", "query", "debug", "library", "git", "bash",
    ]
    concept_keywords = [
        "concept", "theory", "why", "architecture", "overview", "explain the difference",
        "history", "what is the meaning", "philosophy", "compare", "tradeoffs",
    ]

    prog_matches = sum(1 for kw in prog_keywords if kw in msg)
    concept_matches = sum(1 for kw in concept_keywords if kw in msg)

    if prog_matches > concept_matches and prog_matches > 0:
        return "programming"
    elif concept_matches > prog_matches and concept_matches > 0:
        return "conceptual"
    return "general"


def resolve_preferred_strategy(user_id: str, user_message: str = "") -> Optional[str]:
    """
    Deterministically resolves a single preferred response strategy for the current interaction.
    Priority & Resolution Order:
      1. Current explicit user request (overrides everything)
      2. Learned behavioral profile constraints (e.g. if profile verbosity is detailed, concise strategies are suppressed)
      3. Task domain (programming vs. conceptual)
      4. Decayed Bayesian scores and evidence counts
    Returns None if no strategy qualifies or if explicit requests forbid it.
    """
    try:
        msg = (user_message or "").strip().lower()

        # 1. Current explicit request checks
        forbids_code = bool(re.search(r"\b(no code|don't give me code|without code|no programming|just explain it)\b", msg))
        forbids_concise = bool(re.search(r"\b(in detail|comprehensive|deep dive|elaborate|thorough|in-depth)\b", msg))
        forbids_detailed = bool(re.search(r"\b(keep it (short|brief)|be concise|quick answer|tl;?dr)\b", msg))
        forbids_steps = bool(re.search(r"\b(all at once|no steps|skip the steps|no need for steps)\b", msg))

        # 2. Check current learned profile constraints (newer explicit profile updates)
        profile = get_adaptation_profile(user_id)
        verb_item = profile.get("verbosity", {})
        code_item = profile.get("code_examples", {})

        profile_wants_detailed = (verb_item.get("confidence", 0) >= CONFIDENCE_THRESHOLD and verb_item.get("value") == "detailed")
        profile_wants_concise = (verb_item.get("confidence", 0) >= CONFIDENCE_THRESHOLD and verb_item.get("value") == "concise")
        profile_forbids_code = (code_item.get("confidence", 0) >= CONFIDENCE_THRESHOLD and code_item.get("value") is False)

        preferred_list = get_preferred_strategies(user_id)
        if not preferred_list:
            return None

        task_domain = _detect_task_domain(user_message)

        # Filter candidates based on explicit prompt & active profile constraints
        viable = []
        for strat in preferred_list:
            is_code_strat = "code" in strat
            if is_code_strat and (forbids_code or profile_forbids_code):
                continue

            is_concise_strat = "concise" in strat
            is_detailed_strat = "detailed" in strat
            if is_concise_strat and (forbids_concise or profile_wants_detailed):
                continue
            if is_detailed_strat and (forbids_detailed or profile_wants_concise):
                continue

            if "step_by_step" in strat and forbids_steps:
                continue

            viable.append(strat)

        if not viable:
            return None

        # Task domain prioritization
        if task_domain == "programming":
            code_candidates = [s for s in viable if "code" in s]
            if code_candidates:
                return code_candidates[0]

        if task_domain == "conceptual":
            concept_candidates = [s for s in viable if s in ("detailed_explanation", "detailed_step_by_step")]
            if concept_candidates:
                return concept_candidates[0]

        # Default to highest-ranked viable strategy
        return viable[0]

    except Exception as e:
        logger.warning(f"Error resolving preferred strategy for {user_id}: {e}")
        return None


# ─── Behavior Policy Layer ───────────────────────────────────────────────────

def build_behavior_policy(user_id: str, user_message: str = "") -> dict:
    """
    Builds the unified behavior policy for the user, combining:
    - Explicit learned preferences & confidence
    - Contextual preferred response strategy
    - Avoided/suppressed response strategies
    """
    try:
        profile = get_adaptation_profile(user_id)
        preferred_strat = resolve_preferred_strategy(user_id, user_message)
        avoided_strats = get_avoided_strategies(user_id)

        return {
            "user_id": user_id,
            "verbosity": profile.get("verbosity", {}).get("value"),
            "technical_depth": profile.get("technical_depth", {}).get("value"),
            "code_examples": profile.get("code_examples", {}).get("value"),
            "step_by_step": profile.get("step_by_step", {}).get("value"),
            "examples": profile.get("examples", {}).get("value"),
            "tone": profile.get("tone", {}).get("value"),
            "preferred_strategy": preferred_strat,
            "avoided_strategies": avoided_strats,
        }
    except Exception as e:
        logger.error(f"Error building behavior policy for {user_id}: {e}")
        return {
            "user_id": user_id,
            "verbosity": "balanced",
            "technical_depth": "intermediate",
            "code_examples": False,
            "step_by_step": False,
            "examples": True,
            "tone": "friendly",
            "preferred_strategy": None,
            "avoided_strategies": [],
        }


def get_behavior_policy(user_id: str, user_message: str = "") -> dict:
    """Alias for build_behavior_policy."""
    return build_behavior_policy(user_id, user_message)


def get_strategy_context(user_id: str, user_message: str = "") -> str:
    """
    Generates natural language behavioral instructions from learned strategy statistics.
    Translates statistical preferences into clear guidance without exposing database terms.
    """
    try:
        strat = resolve_preferred_strategy(user_id, user_message)
        if not strat or strat not in STRATEGY_GUIDANCE_MAP:
            return ""

        guidance = STRATEGY_GUIDANCE_MAP[strat]
        lines = [
            "--- Learned Response Strategy (Behavior Policy) ---",
            "Based on repeated positive user feedback, prefer this response structure:",
            f"- {guidance}",
            "- Apply this format when relevant to the user's inquiry.",
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Error generating strategy context for {user_id}: {e}")
        return ""


# ─── Context Generation for Prompt Injection ──────────────────────────────────

def get_adaptation_context(user_id: str, user_message: str = "") -> str:
    """
    Generates a concise behavioral guidance string for prompt injection.
    Only includes dimensions where confidence >= CONFIDENCE_THRESHOLD and
    incorporates the resolved preferred strategy when evidence criteria are met.
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

        # 7. Preferred Strategy Context (Phase 3 Closed-Loop)
        strat_context = get_strategy_context(user_id, user_message)
        has_any_strategy = bool(get_preferred_strategies(user_id))

        if not lines and not strat_context and not has_any_strategy:
            return ""

        header = "--- User response preferences ---\n"
        header += "Ava has learned the following response preferences for this user:\n"
        body = "\n".join(lines) if lines else "- Default balanced response style."

        if strat_context:
            body = f"{body}\n\n{strat_context}"

        footer = (
            "\n\nIMPORTANT PRIORITY RULE:\n"
            "Learned adaptation preferences and strategies are guidance, NOT absolute mandates.\n"
            "Priority order:\n"
            "1. Safety and system rules\n"
            "2. The user's CURRENT explicit request in this prompt (overrides any learned preference)\n"
            "3. Explicit custom instructions in user profile\n"
            "4. Learned adaptation preferences & behavior policy above\n"
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


# ─── Adaptation Effectiveness Metrics ─────────────────────────────────────────

def get_adaptation_metrics(user_id: str) -> dict:
    """
    Calculates real adaptation effectiveness metrics from actual stored database records.
    Never fabricates metrics.
    """
    try:
        feedback_stats = db.get_user_feedback_stats(user_id)
        strat_stats = db.get_strategy_stats(user_id)
        profile_rec = db.get_adaptation_profile(user_id)
        interaction_count = profile_rec.get("interaction_count", 0) if profile_rec else 0

        tot_strat_succ = sum(s.get("successes", 0) for s in strat_stats.values())
        tot_strat_fail = sum(s.get("failures", 0) for s in strat_stats.values())
        tot_strat_events = tot_strat_succ + tot_strat_fail
        strategy_success_rate = round(tot_strat_succ / tot_strat_events, 3) if tot_strat_events > 0 else 0.0

        preferred_strat = resolve_preferred_strategy(user_id)
        strat_evidence = 0
        if preferred_strat and preferred_strat in strat_stats:
            p_data = strat_stats[preferred_strat]
            strat_evidence = p_data.get("successes", 0) + p_data.get("failures", 0)

        profile = get_adaptation_profile(user_id)
        confs = [item.get("confidence", 0.5) for item in profile.values() if isinstance(item, dict)]
        avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.50

        return {
            "feedback_count": feedback_stats["total_feedback"],
            "positive_feedback_rate": feedback_stats["positive_rate"],
            "strategy_success_rate": strategy_success_rate,
            "adapted_responses": interaction_count,
            "preferred_strategy": preferred_strat,
            "strategy_evidence": strat_evidence,
            "preference_confidence": avg_conf,
        }
    except Exception as e:
        logger.error(f"Error computing adaptation metrics for {user_id}: {e}")
        return {
            "feedback_count": 0,
            "positive_feedback_rate": 0.0,
            "strategy_success_rate": 0.0,
            "adapted_responses": 0,
            "preferred_strategy": None,
            "strategy_evidence": 0,
            "preference_confidence": 0.50,
        }
