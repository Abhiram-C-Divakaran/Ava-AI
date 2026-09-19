"""
powers.py — Ava's capability engine.

Eliminates every major limitation:
  1. AUTO WEB SEARCH    — detects when a query needs live data, silently fetches it
  2. CODE EXECUTION     — runs code via Judge0 API, returns real output
  3. SMART TRANSLATION  — DeepL API for 29 languages, falls back to LLM
  4. CITATION BUILDER   — formats search results into grounded context
  5. KNOWLEDGE FRESHNESS— injects current date so Ava is always time-aware
"""

import os
import re
import json
import time
import requests
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
BRAVE_API_KEY   = os.getenv("BRAVE_API_KEY", "")
DEEPL_API_KEY   = os.getenv("DEEPL_API_KEY", "")          # free tier: 500k chars/month
JUDGE0_API_KEY  = os.getenv("JUDGE0_API_KEY", "")         # optional — works without for basic langs
JUDGE0_URL      = "https://judge0-ce.p.rapidapi.com"

# Code execution safety: disable by default in production unless explicitly enabled
ENABLE_CODE_EXECUTION = (
    os.getenv("ENABLE_CODE_EXECUTION", "false").lower() in ("true", "1")
    if os.getenv("ENVIRONMENT") == "production"
    else os.getenv("ENABLE_CODE_EXECUTION", "true").lower() in ("true", "1")
)

# Judge0 language IDs for common languages
JUDGE0_LANG_IDS = {
    "python": 71, "python3": 71,
    "javascript": 63, "js": 63,
    "typescript": 74, "ts": 74,
    "java": 62,
    "c": 50,
    "cpp": 54, "c++": 54,
    "csharp": 51, "c#": 51,
    "go": 60,
    "rust": 73,
    "ruby": 72,
    "php": 68,
    "swift": 83,
    "kotlin": 78,
    "bash": 46,
    "r": 80,
}

# DeepL language codes
DEEPL_LANGS = {
    "bulgarian": "BG", "czech": "CS", "danish": "DA", "german": "DE",
    "greek": "EL", "english": "EN-GB", "estonian": "ET", "finnish": "FI",
    "french": "FR", "hungarian": "HU", "indonesian": "ID", "italian": "IT",
    "japanese": "JA", "korean": "KO", "lithuanian": "LT", "latvian": "LV",
    "norwegian": "NB", "dutch": "NL", "polish": "PL", "portuguese": "PT-PT",
    "romanian": "RO", "russian": "RU", "slovak": "SK", "slovenian": "SL",
    "swedish": "SV", "turkish": "TR", "ukrainian": "UK", "chinese": "ZH",
    "spanish": "ES", "arabic": "AR", "hindi": "HI",
}

# ── 1. AUTO WEB SEARCH ────────────────────────────────────────────────────────

# Patterns that strongly signal a need for real-time / recent data
_REALTIME_PATTERNS = [
    r"\b(today|tonight|this (week|month|year)|right now|currently|at the moment)\b",
    r"\b(latest|newest|most recent|just released|just announced|breaking)\b",
    r"\b(price|stock|share price|market cap|exchange rate|bitcoin|crypto|weather)\b",
    r"\b(who (is|won|leads|runs)|who('s| is) the (ceo|president|pm|prime minister|cto|founder))\b",
    r"\b(news|headlines|update(s)?)\b",
    r"\b(score|result|match|game|tournament|championship)\b",
    r"\b(release date|when (does|did|will)|coming soon|out now)\b",
    r"\b(20(2[4-9]|3[0-9]))\b",   # years 2024-2039 — likely recent
    r"\bhow much (is|does|do|are)\b",
]

_NO_SEARCH_PATTERNS = [
    r"^(hi|hello|hey|thanks|thank you|ok|okay|sure|great|cool|bye|goodbye)[\W]*$",
    r"\b(write|create|generate|draft|make|code|explain|summarise|translate|repeat)\b",
    r"^(what is|what are|define|explain|how does|how do)\b.{0,60}$",  # short factual — LLM knows
]

def needs_web_search(message: str) -> bool:
    """Returns True if the message likely needs live internet data."""
    msg = message.strip().lower()
    # Never search for simple generative tasks
    for pat in _NO_SEARCH_PATTERNS:
        if re.search(pat, msg, re.IGNORECASE):
            return False
    # Search if realtime signals present
    for pat in _REALTIME_PATTERNS:
        if re.search(pat, msg, re.IGNORECASE):
            return True
    return False


def web_search(query: str, num_results: int = 5) -> list[dict]:
    """Search via Brave API. Returns list of {title, url, snippet}."""
    if not BRAVE_API_KEY:
        return []
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {"q": query, "count": num_results, "text_decorations": False}
    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers, params=params, timeout=8
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "age": item.get("age", ""),
            })
        return results
    except Exception:
        return []


def build_search_context(query: str, results: list[dict]) -> str:
    """Format search results into a clean context block for the LLM."""
    if not results:
        return ""
    today = datetime.now().strftime("%B %d, %Y")
    lines = [f"[Web search results for: \"{query}\" — retrieved {today}]"]
    for i, r in enumerate(results[:5], 1):
        age = f" ({r['age']})" if r.get("age") else ""
        lines.append(f"\n[{i}] {r['title']}{age}\n    {r['snippet']}\n    Source: {r['url']}")
    lines.append("\n[Use the above sources to answer the user. Cite sources inline as [1], [2] etc. when referencing specific facts.]")
    return "\n".join(lines)


# ── 2. CODE EXECUTION ─────────────────────────────────────────────────────────

def detect_run_command(message: str) -> dict | None:
    """
    Detects /run command with optional language flag.
    Formats: /run <code>  or  /run python <code>  or  /run```python ...```
    Returns {lang, code} or None.
    """
    msg = message.strip()
    if not msg.startswith("/run"):
        return None
    body = msg[4:].strip()

    # Extract fenced code block if present
    fence_match = re.search(r"```(\w+)?\n?([\s\S]+?)```", body)
    if fence_match:
        lang = (fence_match.group(1) or "python").lower()
        code = fence_match.group(2).strip()
        return {"lang": lang, "code": code}

    # First token might be the language
    tokens = body.split(None, 1)
    if tokens and tokens[0].lower() in JUDGE0_LANG_IDS:
        lang = tokens[0].lower()
        code = tokens[1] if len(tokens) > 1 else ""
        return {"lang": lang, "code": code}

    # Default to Python
    return {"lang": "python", "code": body}


def execute_code(lang: str, code: str, stdin: str = "") -> dict:
    """
    Execute code via Judge0 CE. Returns {stdout, stderr, status, time, memory}.
    Works without API key on the free public endpoint (rate limited).
    """
    if not ENABLE_CODE_EXECUTION:
        return {
            "stdout": "",
            "stderr": "Code execution is disabled in production environment.",
            "success": False,
            "status": "Disabled",
        }

    lang_id = JUDGE0_LANG_IDS.get(lang.lower(), 71)  # default Python

    # Try RapidAPI Judge0 if key is available, else use public CE
    if JUDGE0_API_KEY:
        url = f"{JUDGE0_URL}/submissions?base64_encoded=false&wait=true"
        headers = {
            "X-RapidAPI-Key": JUDGE0_API_KEY,
            "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com",
            "Content-Type": "application/json",
        }
    else:
        url = "https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=false&wait=true"
        headers = {"Content-Type": "application/json"}

    payload = {
        "source_code": code,
        "language_id": lang_id,
        "stdin": stdin,
        "cpu_time_limit": 5,
        "memory_limit": 128000,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            data = resp.json()
            return {
                "stdout": (data.get("stdout") or "").strip(),
                "stderr": (data.get("stderr") or "").strip(),
                "compile_output": (data.get("compile_output") or "").strip(),
                "status": data.get("status", {}).get("description", "Unknown"),
                "time": data.get("time", "?"),
                "memory": data.get("memory", "?"),
                "success": data.get("status", {}).get("id", 0) == 3,
            }
        return {"stdout": "", "stderr": f"Judge0 returned {resp.status_code}", "success": False, "status": "Error"}
    except requests.Timeout:
        return {"stdout": "", "stderr": "Execution timed out (>15s)", "success": False, "status": "Timeout"}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "success": False, "status": "Error"}


def format_execution_result(lang: str, code: str, result: dict) -> str:
    """Format code execution result into a clean markdown response."""
    status = result.get("status", "Unknown")
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    compile_out = result.get("compile_output", "")
    exec_time = result.get("time", "?")

    lines = [f"**Running {lang} code…**\n"]
    lines.append(f"```{lang}\n{code}\n```\n")

    if result.get("success"):
        lines.append(f"✅ **Output** *(ran in {exec_time}s)*")
        lines.append(f"```\n{stdout if stdout else '(no output)'}\n```")
    else:
        lines.append(f"❌ **{status}**")
        if compile_out:
            lines.append(f"```\n{compile_out}\n```")
        if stderr:
            lines.append(f"```\n{stderr}\n```")
        if stdout:
            lines.append(f"Partial output:\n```\n{stdout}\n```")

    return "\n".join(lines)


# ── 3. SMART TRANSLATION ──────────────────────────────────────────────────────

def translate_deepl(text: str, target_lang_name: str, source_lang_name: str = "auto") -> dict | None:
    """
    Translate via DeepL API. Returns {translated, source_lang, target_lang} or None.
    Falls back gracefully if DeepL key not set or language not supported.
    """
    if not DEEPL_API_KEY:
        return None

    target_code = DEEPL_LANGS.get(target_lang_name.lower())
    if not target_code:
        # Try partial match
        for name, code in DEEPL_LANGS.items():
            if target_lang_name.lower() in name:
                target_code = code
                break
    if not target_code:
        return None  # Language not in DeepL — LLM will handle it

    source_code = None
    if source_lang_name.lower() not in ("auto", "auto-detect", ""):
        source_code = DEEPL_LANGS.get(source_lang_name.lower())

    # DeepL free API endpoint
    endpoint = "https://api-free.deepl.com/v2/translate"
    payload = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "target_lang": target_code,
    }
    if source_code:
        payload["source_lang"] = source_code.split("-")[0]  # DeepL source uses base code

    try:
        resp = requests.post(endpoint, data=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            translation = data["translations"][0]
            detected_src = translation.get("detected_source_language", source_lang_name)
            return {
                "translated": translation["text"],
                "source_lang": detected_src,
                "target_lang": target_code,
                "engine": "DeepL",
            }
    except Exception:
        pass
    return None


def extract_text_to_translate(message: str) -> str | None:
    """
    Extracts the actual text to translate from a translation request.
    e.g. 'Translate "hello world" to French' → 'hello world'
         'Translate this to Spanish: Good morning everyone' → 'Good morning everyone'
    """
    # Quoted text
    quoted = re.search(r'["\u201c\u2018](.*?)["\u201d\u2019]', message)
    if quoted:
        return quoted.group(1).strip()
    # After colon
    colon = re.search(r':\s*(.+)$', message, re.DOTALL)
    if colon:
        return colon.group(1).strip()
    # After "translate X to LANG" — X is everything before "to LANG"
    m = re.search(r'\btranslate\b\s+(.+?)\s+\bto\b\s+\w+', message, re.IGNORECASE | re.DOTALL)
    if m:
        candidate = m.group(1).strip()
        # Skip if candidate is just "this", "it", "the following"
        if candidate.lower() not in ("this", "it", "the following", "the text", ""):
            return candidate
    return None


# ── 4. KNOWLEDGE FRESHNESS ────────────────────────────────────────────────────

def get_time_context() -> str:
    """Returns a brief time context string to inject into every prompt."""
    now = datetime.now()
    return f"[Current date: {now.strftime('%A, %B %d, %Y')} | Time: {now.strftime('%H:%M')}]"


# ── 5. SMART CONTEXT BUILDER ──────────────────────────────────────────────────

def build_augmented_system_prompt(
    base_prompt: str,
    user_message: str,
    conversation_context: str = "",
    file_context: str = "",
    failed_note: str = "",
    sentiment_label: str = "neutral",
    frustration: float = 0.0,
    translation_langs: dict | None = None,
    support_flag: bool = False,
    web_search_enabled: bool = False,
    adaptation_context: str = "",
    user_memory_context: str = "",
) -> tuple[str, dict]:
    """
    Builds the final system prompt with all augmentations injected in strict conceptual order:
    1. Base system prompt
    2. Current time context
    3. Factual persistent user memory (--- What Ava remembers about this user ---)
    4. Behavioral adaptation context (--- User response preferences ---)
    5. Conversation context so far (current session only: --- Conversation so far ---)
    6. Search context, attached documents/files, failure notes, routing instructions
    """
    metadata = {"searched": False, "search_results": [], "deepl_used": False}
    parts = [base_prompt]

    # 1. Always inject current time
    parts.append(f"\n\n{get_time_context()}")

    # 2. Persistent cross-session user memory (factual memory)
    if user_memory_context and user_memory_context.strip():
        parts.append(f"\n\n--- What Ava remembers about this user ---\n{user_memory_context.strip()}")

    # 3. Behavioral adaptation context (learned response preferences)
    if adaptation_context and adaptation_context.strip():
        parts.append(f"\n\n{adaptation_context.strip()}")

    # 4. Conversation history (current-session context only)
    if conversation_context and conversation_context.strip():
        parts.append(f"\n\n--- Conversation so far ---\n{conversation_context.strip()}")

    # 5. Auto web search — check if query needs live data
    search_ctx = ""
    should_search = web_search_enabled or needs_web_search(user_message)
    if should_search and BRAVE_API_KEY:
        results = web_search(user_message, num_results=5)
        if results:
            search_ctx = build_search_context(user_message, results)
            parts.append(f"\n\n{search_ctx}")
            metadata["searched"] = True
            metadata["search_results"] = results

    # 6. File context
    if file_context:
        is_csv = "[CSV DATA" in file_context or "[TSV DATA" in file_context
        label = "CSV/spreadsheet data" if is_csv else "attached document"
        parts.append(f"\n\n--- {label} ---\n{file_context[:6000]}")
        if is_csv:
            parts.append("\nAnalyse this data following your DATA ANALYSIS rules.")

    if failed_note:
        parts.append(f"\n{failed_note}")

    # 7. Routing instructions
    if translation_langs:
        src = translation_langs.get("src", "auto-detect")
        tgt = translation_langs.get("tgt", "English")
        parts.append(f"\n\nThe user wants a translation from {src} to {tgt}. Lead with the translated text, then note the language pair.")
    elif support_flag:
        parts.append(f"\n\nUser sentiment: {sentiment_label}, frustration score: {frustration:.2f}. Be empathetic and efficient.")
    else:
        parts.append("\n\nRespond naturally and helpfully.")

    return "".join(parts), metadata