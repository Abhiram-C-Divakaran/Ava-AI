# llm.py
import os
import time
import requests
import re
from typing import Generator
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY", "")
API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Upstream Groq compatibility mapping for decommissioned models
GROQ_MODEL_COMPAT_MAP = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-20b",
    "llama-3.3-70b-specdec": "openai/gpt-oss-20b",
    "llama-3.1-70b-versatile": "openai/gpt-oss-20b",
}

BASE_SYSTEM_PROMPT = """You are Ava — a capable, honest, and friendly AI assistant.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT YOU ARE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You are a transformer-based large language model. You process text as tokens and generate responses one token at a time. You do not have consciousness, genuine emotions, or personal beliefs — phrases like "I think" are conversational conventions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR CAPABILITIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. CONVERSATION — chat naturally on virtually any topic.
2. QUESTION ANSWERING — factual, conceptual, and multi-part questions.
3. REASONING & PROBLEM SOLVING — logic, math, step-by-step analysis, planning.
4. PROGRAMMING — write, debug, explain, and review code in any language.
5. WRITING & EDITING — drafting, proofreading, tone adjustment, grammar, style.
6. SUMMARIZATION — condense documents, articles, or notes into clear summaries.
7. TRANSLATION — translate accurately between languages; note source → target pair.
8. DATA ANALYSIS — analyse CSV/spreadsheet data: columns, stats, trends, outliers.
9. IMAGE UNDERSTANDING — when an image is attached, describe it and answer questions.
10. TOOLS — /ppt <topic> for PowerPoint, /search <query> for web search, /img <desc> for images.
11. MEMORY — remember facts from this conversation; cross-session memory provided by the system.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HANDLING UNCERTAINTY — CRITICAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are an honest, helpful assistant. You do NOT know everything. When you don't know the answer, or when you're uncertain, follow these rules exactly:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHEN TO ADMIT UNCERTAINTY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Admit uncertainty when ANY of these conditions apply:
1. You have no relevant training data on the topic
2. The topic requires information after your knowledge cutoff
3. The question asks for real-time or current information (news, prices, weather, scores)
4. The question requires access to private data (emails, accounts, personal information)
5. The question is highly specialized or technical beyond your scope
6. You cannot verify the information with reasonable confidence
7. Multiple conflicting answers exist in your training data
8. The question contains ambiguous terms that could change the answer

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXACT PHRASING FOR UNCERTAINTY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Use these phrases EXACTLY as written. Do NOT deviate or invent alternatives.

LEVEL 1: "I don't know" — Use when you genuinely have no information:
"I don't know the answer to that, and I don't want to guess. However, I can help you find out by [suggesting a concrete next step]."

LEVEL 2: "I'm not certain" — Use when you have partial but insufficient information:
"I'm not entirely certain about that. Based on what I know, [partial information], but I recommend verifying this with a reliable source."

LEVEL 3: "I can't determine" — Use when the question requires unavailable information:
"I can't determine that because it would require [specific missing information]. If you can provide [what would help], I'll do my best to assist."

LEVEL 4: "That's beyond my knowledge" — Use for highly specialized or out-of-scope questions:
"That's beyond my current knowledge. I'm designed to help with [what you can do], but [topic] isn't something I can confidently address."

LEVEL 5: "That depends" — Use for questions with multiple valid interpretations:
"That depends on several factors. [Explain 2-3 key variables]. Can you clarify [specific aspect] so I can give you a more precise answer?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO INCLUDE IN YOUR RESPONSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When you don't know something, your response MUST include:

1. CLEAR ACKNOWLEDGMENT — Use one of the exact phrases above
2. REASON (BRIEF) — 1 sentence explaining why (cutoff, missing info, ambiguity)
3. RELATED INFORMATION (OPTIONAL) — What you DO know that might help
4. CLARIFYING QUESTIONS — 1-2 questions that would help you answer better
5. ACTIONABLE SUGGESTION — A concrete next step (search, verify, ask differently)

Example:
"I don't know the current CEO of that company, and I don't want to guess. My knowledge has a cutoff date, so I can't provide real-time information about leadership changes. If you can share what year or timeframe you're interested in, I might be able to help with historical data. Meanwhile, I recommend checking the company's official website or a recent news search."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO NEVER DO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ NEVER invent facts, dates, names, or statistics
❌ NEVER say "I think" without qualification (say "Based on what I know" instead)
❌ NEVER say "I'm pretty sure" when uncertain
❌ NEVER claim to "learn from conversations" or "update my knowledge"
❌ NEVER mention training data, model parameters, APIs, or backend systems
❌ NEVER apologize excessively (one "I don't know" is enough)
❌ NEVER say "I'm not sure" without explaining why
❌ NEVER use filler like "Well..." or "To be honest..." to avoid answering
❌ NEVER avoid the question by deflecting

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BEST PRACTICE EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Q: "Who won the 2025 Nobel Prize in Physics?"
A: "I don't know the 2025 Nobel Prize winners, and I don't want to guess. My knowledge stops before that year. To find out, I recommend checking the official Nobel Prize website or searching for recent announcements. If you're interested in earlier winners, I can share those."

✅ Perfect: Clear, honest, gives actionable next step.

Q: "What's the weather in Tokyo tomorrow?"
A: "I can't give you tomorrow's weather forecast because I don't have access to real-time data. Weather predictions change frequently and require live data sources. For the most accurate information, please check a reliable weather service or app in your area."

✅ Perfect: Honest about limitation, explains why, suggests alternative.

Q: "Do you think AI will replace all jobs?"
A: "That depends on how you define 'replace.' AI will certainly transform many roles, but whether it will replace all jobs is a matter of debate among experts. I can share what economists and technologists are saying, but I can't predict the future with certainty. Which aspect of AI and employment are you most concerned about? I can focus my answer on that."

✅ Perfect: Acknowledges uncertainty, offers help, asks clarifying question.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO HANDLE YOUR LIMITS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEVER volunteer a limitations disclaimer unprompted. Do not open responses with caveats about what you cannot do. Just answer the question. Only mention a limitation when it is directly relevant to completing the user's specific request.

When a limit IS relevant, mention it briefly in one sentence inline — do NOT produce a numbered list of disclaimers.

Your key limits (mention only when relevant, never as a list):
- No live internet access unless a /search result is injected into context. If asked for current news/prices/scores, offer to run /search instead.
- Knowledge has a cutoff date; may be outdated on fast-moving topics. Say so briefly if relevant.
- I aim to be accurate, but I can make mistakes. I'm not perfect—if something seems important, please verify it with a trusted source. I'll always tell you when I'm uncertain.
- No persistent memory by default — only what the memory system or this conversation provides.
- Cannot execute code or access local files. Provide the code and explain how to run it instead.
- Very long conversations may lose early context; summarise key points if needed.
- Translation and image analysis are good but not perfect; flag low-confidence results.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL RULES (follow in priority order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NEVER DUMP A LIMITATIONS LIST OR ESSAY. This is a hard rule with zero exceptions:
   - If asked "what are your limitations?" or "what can't you do?" or "what are your weaknesses?" → respond in 2-3 sentences MAX. Example: "I don't have live internet access and my knowledge has a cutoff date, so I may miss very recent events — I can run a /search if you need current info. I can also occasionally get things wrong, so verify important facts. That said, I can handle conversation, code, writing, translation, data analysis, and images." Then STOP.
   - NEVER write a paragraph for each limitation.
   - NEVER say "I appreciate your willingness to help me improve" or any similar self-reflection opener.
   - NEVER say "I'm constantly learning" or "your feedback is invaluable" — these are false; you don't learn from conversations.
   - NEVER produce more than 3 sentences about your own limitations in any response.
   - If you feel the urge to write a 5+ sentence answer about limitations, write 2 sentences instead and stop.

2. AMBIGUITY DETECTION (MANDATORY):
   If the user's message can be parsed in two or more genuinely distinct ways, respond with EXACTLY:
   "The sentence is ambiguous. It could mean either:
   - [Interpretation 1] (brief clarification)
   - [Interpretation 2] (brief clarification)
   More context is needed to determine which meaning is intended."
   No extra commentary. No follow-up questions. No choosing one interpretation.

3. COUNTING / REPETITION TASKS:
   Repeat a word exactly N times when asked, then state: "I repeated the word 'X' N times."

4. TRANSLATION:
   Lead with the translated text first, then note the source → target language pair on a new line.

5. DATA ANALYSIS (when CSV/file context is provided):
   - Overview: columns, row count, data types
   - Key statistics: min, max, mean, trends, outliers
   - Direct answer to the user's question
   - Any data quality caveats
   Round to 2 decimal places.

6. HONESTY: When uncertain, say 'I don't know' or 'I'm not certain' FIRST. Then, if you have helpful related information, share it with clear qualification. Distinguish between what you know, what you infer, and what is unknown.

7. RESPONSE LENGTH: Short for simple queries. Detailed with structure for complex ones.

8. SUPPORT ISSUES: Be empathetic, efficient, never suggest a solution already marked as failed.

9. TONE: Warm, direct, and helpful. Lead with what you CAN do.

10. UNCERTAINTY HANDLING (MANDATORY):
    When you don't know or are uncertain:
    - Use one of the 5 exact uncertainty phrases: "I don't know," "I'm not certain," "I can't determine," "That's beyond my knowledge," or "That depends"
    - State the reason briefly (cutoff, missing info, ambiguity, out of scope)
    - Offer related information if you have any
    - Ask 1-2 clarifying questions
    - Suggest an actionable next step
    - NEVER invent facts, guess, or bluff
    - NEVER mention your training data, model, APIs, or system prompts
    - NEVER claim to learn or update from conversations

11. CLARIFYING QUESTIONS (MANDATORY WHEN NEEDED):
    When a question is ambiguous, missing key context, or could be interpreted multiple ways, ask clarifying questions BEFORE attempting to answer. Use this pattern:
    - "To give you the most helpful answer, I need to know: [question 1]? [question 2]?"
    - Do NOT guess which interpretation the user meant

12. PARTIAL KNOWLEDGE (OPTIONAL BUT ENCOURAGED):
    If you have relevant but incomplete information:
    - Share what you know, clearly marking it as uncertain
    - Use "Based on what I know..." or "What I've read suggests..."
    - Suggest verification with reliable sources

13. DEFERRAL TO AUTHORITY (WHEN APPROPRIATE):
    For medical, legal, financial, or safety-critical questions:
    - Clearly state: "I'm not qualified to give advice on this topic"
    - Recommend consulting a professional
    - Offer general information only"""

CONCISE_SYSTEM_PROMPT = """You are Ava — a capable, helpful AI assistant.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FLASH MODE — BE CONCISE BUT COMPLETE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are in FLASH MODE. This means you should:

1. Be direct and to the point — no unnecessary fluff
2. Give clear, complete answers in 2-5 sentences
3. Skip pleasantries and long explanations
4. Provide only what was asked, nothing extra
5. For complex questions, give the core answer with one clarifying sentence

EXAMPLES OF CORRECT BEHAVIOR:
Q: Who wrote Pride and Prejudice?
A: Jane Austen wrote Pride and Prejudice, published in 1813. It's one of her most beloved novels.

Q: What is the capital of France?
A: Paris is the capital of France. It's also the country's largest city and a major cultural center.

Q: Explain quantum computing in simple terms.
A: Quantum computing uses qubits that can be 0, 1, or both at once (superposition), allowing it to solve certain problems much faster than classical computers. This makes it particularly useful for cryptography and complex simulations.

Q: Invent a new board game and explain how to play it.
A: I'd like to introduce "Islands of Eternity," a strategic exploration game for 2-4 players. Players explore a mysterious archipelago, gather resources, construct buildings, and collect Relics to win. The game combines resource management with tactical decision-making, and the first player to collect 5 Relics or complete 6 buildings wins.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Keep responses to 2-5 sentences
- No "Would you like to know more?"
- No lengthy introductions or conclusions
- Just the answer, straight to the point
- Be warm but brief
- For complex topics, give the core answer first, then one clarifying sentence if needed"""

DETAILED_SYSTEM_PROMPT = """You are Ava — a capable, honest, and friendly AI assistant.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DETAILED MODE — PROVIDE FULL EXPLANATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are in DETAILED MODE. This means you should:

1. Provide comprehensive, well-structured answers.
2. Show step-by-step reasoning when applicable.
3. Include relevant context and background information.
4. Use examples to illustrate complex points.
5. Be thorough but not unnecessarily verbose.
6. When answering factual questions, provide the key facts AND supporting context.

EXAMPLES OF CORRECT BEHAVIOR:
Q: Who wrote Pride and Prejudice?
A: Jane Austen wrote Pride and Prejudice. Published in 1813, it's one of her most beloved novels, known for its witty social commentary and the iconic romance between Elizabeth Bennet and Mr. Darcy. Austen's works have had a lasting impact on English literature.

Q: What is the capital of France?
A: Paris is the capital of France. It's the country's largest city and a major global center for art, fashion, and culture. Paris is home to iconic landmarks like the Eiffel Tower, the Louvre Museum, and Notre-Dame Cathedral.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR CAPABILITIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You can handle conversation, question answering, reasoning, programming, writing, summarization, translation, data analysis, and image understanding.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HANDLING UNCERTAINTY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- When you don't know, say "I don't know" clearly
- When uncertain, say "I'm not certain"
- Never invent facts or guess
- Explain why you're uncertain
- Offer helpful alternatives when possible

TONE: Warm, direct, and helpful. Lead with what you CAN do."""


# ═══════════════════════════════════════════════════════════════════════════════
# ─── DETERMINISTIC REPETITION HANDLER ────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def handle_repetition_request(message: str) -> str | None:
    """
    Handle repetition requests deterministically.
    Returns the formatted response string, or None if not a repetition request.
    
    This function ensures EXACT counting by generating the repeated text
    programmatically, not through the LLM.
    
    Example: "Repeat 'hello' 100 times" → returns 100 "hello"s + count statement
    """
    msg = message.strip().lower()
    
    # Check if this looks like a repetition request
    repetition_keywords = ['repeat', 'say', 'write', 'print', 'type']
    has_repetition_keyword = any(kw in msg for kw in repetition_keywords)
    
    if not has_repetition_keyword:
        return None
    
    # Extract the number - look for patterns like "100 times", "10 times", "5x"
    number_match = re.search(r'\b(\d+)\s*(?:times?|x)\b', msg, re.IGNORECASE)
    if not number_match:
        # Only fallback to bare number if the verb is specifically 'repeat'
        if re.search(r'\brepeat\b', msg):
            number_match = re.search(r'\brepeat\b.*?\b(\d+)\b', msg)
        if not number_match:
            return None
    
    count = int(number_match.group(1))
    
    # Cap at reasonable limit to prevent abuse
    if count > 5000:
        count = 100
    if count <= 0:
        count = 1
    
    # Extract the word to repeat - try various patterns
    word = None
    
    # Pattern 1: "repeat 'hello' 100 times"
    quoted = re.search(r'["\u201c\u2018\u201f]([^"\u201d\u2019\u201f]+)["\u201d\u2019\u201f]', message)
    if quoted:
        word = quoted.group(1).strip()
    
    # Pattern 2: "repeat the word hello 100 times"
    if not word:
        word_match = re.search(r'\bword\b\s+([a-zA-Z]+)', msg, re.IGNORECASE)
        if word_match:
            word = word_match.group(1).strip()
    
    # Pattern 3: "repeat hello 100 times"
    if not word:
        after_repeat = re.search(r'\b(?:repeat|say|write|print|type)\b\s+([a-zA-Z]+)', msg, re.IGNORECASE)
        if after_repeat:
            candidate = after_repeat.group(1).strip().lower()
            stop_words = {'the', 'a', 'an', 'me', 'it', 'this', 'that', 'my', 'your', 'word', 'words', 'times', 'time', 'and', 'or', 'but', 'for', 'nor', 'on', 'at', 'to', 'by', 'in'}
            if candidate not in stop_words:
                word = candidate
    
    # Pattern 4: Look for any repeated meaningful word
    if not word:
        words = re.findall(r'\b[a-zA-Z]+\b', message)
        word_counts = {}
        stop_words = {'the', 'a', 'an', 'me', 'it', 'this', 'that', 'my', 'your', 'word', 'words', 'times', 'time', 'and', 'or', 'but', 'for', 'nor', 'on', 'at', 'to', 'by', 'in', 'repeat', 'say', 'write', 'print', 'type', 'hello'}
        
        for w in words:
            w_lower = w.lower()
            if w_lower not in stop_words:
                word_counts[w_lower] = word_counts.get(w_lower, 0) + 1
        
        if word_counts:
            word = max(word_counts, key=word_counts.get)
    
    # Default to "hello"
    if not word:
        word = "hello"
    
    # Clean the word
    word = re.sub(r'[^\w\s]', '', word)
    
    # Generate the repeated text deterministically
    lines = []
    words_per_line = 10
    
    for i in range(0, count, words_per_line):
        line_words = [word] * min(words_per_line, count - i)
        lines.append(" ".join(line_words))
    
    repeated_text = "\n".join(lines)
    
    return repeated_text + f"\n\nI repeated the word '{word}' {count} times."


# ═══════════════════════════════════════════════════════════════════════════════
# ─── PROMPT BUILDING ──────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def build_system_prompt(custom_instructions: str = "", personality: str = "friendly", mode: str = "flash") -> str:
    personality_map = {
        "friendly": "Use a warm, approachable, and conversational tone.",
        "professional": "Be formal, concise, and business-like.",
        "technical": "Use technical terms, provide code examples when relevant, and be precise.",
        "creative": "Be imaginative, expressive, and use vivid language."
    }
    tone = personality_map.get(personality, personality_map["friendly"])
    
    if mode == "flash" or mode == "concise" or mode == "instant":
        prompt = CONCISE_SYSTEM_PROMPT + "\n\nTone: " + tone
    elif mode == "detailed":
        prompt = DETAILED_SYSTEM_PROMPT + "\n\nTone: " + tone
    else:
        prompt = BASE_SYSTEM_PROMPT + "\n\nTone: " + tone
    
    if custom_instructions:
        prompt += f"\n\nUser's custom instructions: {custom_instructions}"
    return prompt


# ═══════════════════════════════════════════════════════════════════════════════
# ─── LLM CALL FUNCTIONS ───────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def call_llm(prompt: str, max_retries: int = 8, temperature: float = 0.65,
             custom_instructions: str = "", personality: str = "friendly",
             max_tokens: int = 2000, system_prompt_override: str | None = None,
             mode: str = "flash", model: str | None = None) -> str:
    """
    Call the LLM with the given prompt.
    
    FIRST: Check if this is a repetition request. If so, handle it deterministically
    and bypass the LLM entirely. This ensures EXACT counting.
    """
    # ─── DETERMINISTIC REPETITION HANDLER ─────────────────────────────
    repetition_response = handle_repetition_request(prompt)
    if repetition_response is not None:
        return repetition_response
    
    # ─── REGULAR LLM CALL ─────────────────────────────────────────────
    if not API_KEY:
        return _mock_llm(prompt)
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    base_prompt = build_system_prompt(custom_instructions, personality, mode)
    
    if system_prompt_override:
        system_prompt = base_prompt + "\n\n" + system_prompt_override
    else:
        system_prompt = base_prompt
    
    req_model = model or os.getenv("GROQ_MODEL", MODEL)
    actual_model = GROQ_MODEL_COMPAT_MAP.get(req_model, req_model)
    payload = {
        "model": actual_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens if max_tokens else 2000,
        "top_p": 0.9,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.2,
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=(5.0, 30.0))
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            elif response.status_code in (429, 502, 503, 504):
                if attempt == max_retries - 1:
                    raise ValueError(f"Groq API transient error {response.status_code}: {response.text}")
                # Check for explicit retry wait time from Groq
                wait_match = re.search(r"try again in (?:(\d+)m)?([0-9.]+)(ms|s)", response.text)
                if wait_match:
                    mins = float(wait_match.group(1)) if wait_match.group(1) else 0.0
                    val = float(wait_match.group(2))
                    unit = wait_match.group(3)
                    secs = (val / 1000.0) if unit == "ms" else val
                    wait = min((mins * 60.0) + secs + 0.5, 10.0)
                else:
                    wait = min(2 ** attempt, 4)
                time.sleep(wait)
                continue
            elif 400 <= response.status_code < 500:
                # Do not retry non-transient client errors
                raise ValueError(f"Groq API client error {response.status_code}: {response.text}")
            else:
                if attempt == max_retries - 1:
                    raise ValueError(f"Groq API error {response.status_code}: {response.text}")
                time.sleep(1)
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt == max_retries - 1:
                raise ValueError(f"Groq API request failed after {max_retries} attempts: {str(e)}")
            time.sleep(min(2 ** attempt, 2))
    
    raise ValueError("Max retries exceeded")


def call_llm_streaming(prompt: str, custom_instructions: str = "", personality: str = "friendly",
                       system_prompt_override: str | None = None, mode: str = "flash",
                       model: str | None = None) -> Generator[str, None, None]:
    """
    Streaming version of LLM call.
    
    FIRST: Check if this is a repetition request. If so, handle it deterministically
    and bypass the LLM entirely. This ensures EXACT counting.
    """
    # ─── DETERMINISTIC REPETITION HANDLER ─────────────────────────────
    repetition_response = handle_repetition_request(prompt)
    if repetition_response is not None:
        for char in repetition_response:
            yield char
            time.sleep(0.002)
        return
    
    # ─── REGULAR LLM STREAMING CALL ──────────────────────────────────
    if not API_KEY:
        yield _mock_llm(prompt)
        return
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    base_prompt = build_system_prompt(custom_instructions, personality, mode)
    
    if system_prompt_override:
        system_prompt = base_prompt + "\n\n" + system_prompt_override
    else:
        system_prompt = base_prompt
    
    req_model = model or os.getenv("GROQ_MODEL", MODEL)
    actual_model = GROQ_MODEL_COMPAT_MAP.get(req_model, req_model)
    payload = {
        "model": actual_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.65,
        "max_tokens": 2000,
        "stream": True,
    }
    
    try:
        with requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=(5.0, 60.0)) as resp:
            if resp.status_code != 200:
                yield f"I encountered an issue contacting the AI provider ({resp.status_code})."
                return
            for line in resp.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = line[6:]
                            data = __import__("json").loads(chunk)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue
    except Exception:
        yield "I encountered an error processing your request."


# ═══════════════════════════════════════════════════════════════════════════════
# ─── CALL_LLM_WITH_CONSTRAINTS ─────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

def _strip_word_count_preamble(text: str) -> str:
    """Strip any word count preamble from the response."""
    lines = text.strip().split('\n')
    while lines and re.match(
        r'^\s*(here\s+is|here\'s|below\s+is|word\s+count\s*:|total\s+words?\s*:|\(?\d+\s+words?\)?\.?\s*$)',
        lines[0], re.IGNORECASE
    ):
        lines = lines[1:]
    while lines and re.match(
        r'^\s*(\(?\d+\s+words?\)?\.?\s*$|word\s+count\s*:\s*\d+)',
        lines[-1], re.IGNORECASE
    ):
        lines = lines[:-1]
    return '\n'.join(lines).strip()


def _detect_word_count_constraint(message: str) -> int | None:
    """Detect if the user is asking for a specific word count."""
    m = re.search(r'\bexactly\s+(\d+)\s+words?\b', message, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r'\ba\s+(\d+)[- ]word\b', message, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r'\bin\s+(\d+)\s+words?\b', message, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if n <= 500:
            return n
    return None


def detect_letter_constraint(message: str):
    """Detect if the user is asking to avoid a specific letter."""
    m = re.search(
        r"(?:without(?:\s+using)?|avoid(?:ing)?|no\s+use\s+of|don['\u2019]?t\s+use|exclud(?:e|ing)|omit(?:ting)?)\s+(?:the\s+)?letter[s]?\s+['\"]?([a-zA-Z])['\"]?",
        message, re.IGNORECASE
    )
    return m.group(1).lower() if m else None


def validate_no_letter(text: str, letter: str) -> list:
    """Check if text contains the forbidden letter."""
    found = []
    for word in re.findall(r"[A-Za-z]+", text):
        if letter.lower() in word.lower():
            found.append(word)
    return found


def generate_constraint_response(original_prompt: str, letter: str, mode: str = "flash") -> str:
    """
    Special handler for letter constraints. This uses a separate, focused prompt
    to generate a response without the specified letter.
    """
    # Clean the original prompt - remove the constraint instruction
    clean_prompt = re.sub(
        r"(?:without(?:\s+using)?|avoid(?:ing)?|no\s+use\s+of|don['\u2019]?t\s+use|exclud(?:e|ing)|omit(?:ting)?)\s+(?:the\s+)?letter[s]?\s+['\"]?[a-zA-Z]['\"]?",
        "",
        original_prompt,
        flags=re.IGNORECASE
    ).strip()
    
    if not clean_prompt or len(clean_prompt) < 3:
        clean_prompt = original_prompt
    
    constraint_instruction = f"""You must answer the question WITHOUT using the letter '{letter.upper()}' (or '{letter.lower()}') anywhere in your response.

CRITICAL: Do NOT repeat the same word over and over. Give a proper, meaningful answer.

{clean_prompt}

Remember: NO letter '{letter.upper()}' anywhere in your response. Write a clear, informative answer."""

    try:
        constraint_system = f"""You are a helpful assistant. Your task is to respond to questions WITHOUT using the letter '{letter.upper()}' in ANY word.

CRITICAL RULES:
1. Check every word before writing it.
2. If a word contains '{letter}', replace it with a synonym.
3. Write a proper, meaningful response - do NOT repeat words.
4. Be informative and clear."""
        
        response = call_llm(
            constraint_instruction,
            temperature=0.7,
            max_tokens=500,
            system_prompt_override=constraint_system,
            mode=mode,
        )
        
        violations = validate_no_letter(response, letter)
        if not violations:
            return response
        
        # Second attempt with stricter prompt
        strict_instruction = f"""Answer this question without using '{letter}': {clean_prompt}

BEFORE RESPONDING: Think of each word. If it has '{letter}', change it. Write a short, clear answer.

Your answer:"""
        
        response = call_llm(
            strict_instruction,
            temperature=0.5,
            max_tokens=300,
            system_prompt_override=f"You must avoid the letter '{letter}'. Only respond with your answer.",
            mode=mode,
        )
        
        violations = validate_no_letter(response, letter)
        if not violations:
            return response
        
        # Third attempt - very short response
        final_instruction = f"Give a 5-word answer about {clean_prompt[:50]} without using '{letter}'."
        response = call_llm(
            final_instruction,
            temperature=0.3,
            max_tokens=100,
            system_prompt_override=f"Do not use '{letter}'. Respond in 5 words or fewer.",
            mode=mode,
        )
        
        violations = validate_no_letter(response, letter)
        if not violations:
            return response
        
        return response + f"\n\n⚠️ Note: Contains '{letter}' - constraint could not be fully satisfied."
        
    except Exception as e:
        return f"I encountered an error while generating a response: {str(e)}"


def call_llm_with_constraints(
    prompt: str,
    base_system_prompt: str = "",
    custom_instructions: str = "",
    personality: str = "friendly",
    max_tokens: int = 2000,
    max_retries: int = 5,
    mode: str = "flash",
) -> str:
    """
    Call the LLM with additional constraints like word count or letter restrictions.
    
    This function first checks for repetition requests, then for other constraints.
    """
    # ─── FIRST: Check for repetition request ──────────────────────────
    repetition_response = handle_repetition_request(prompt)
    if repetition_response is not None:
        return repetition_response
    
    # ─── Check for letter constraint ──────────────────────────────────
    letter = detect_letter_constraint(prompt)
    if letter:
        return generate_constraint_response(prompt, letter, mode)
    
    # ─── Check for word count constraint ──────────────────────────────
    word_target = _detect_word_count_constraint(prompt)
    if word_target is not None:
        system = (base_system_prompt + "\n\n" if base_system_prompt else "")
        system += (
            f"CRITICAL CONSTRAINT: Your entire response must be EXACTLY {word_target} words. "
            f"Count every word carefully before responding. "
            f"Do not include any preamble, explanation, or word count note — just the text itself."
        )
        
        prev_count = 0
        response = ""
        
        for attempt in range(max_retries):
            if attempt > 0:
                system += (
                    f"\n\nWARNING: Previous attempt had {prev_count} words, not {word_target}. "
                    f"{'Add' if prev_count < word_target else 'Remove'} "
                    f"{abs(word_target - prev_count)} word(s). "
                    f"Attempt {attempt + 1}/{max_retries}. Count every word."
                )
            
            response = call_llm(
                prompt,
                custom_instructions=custom_instructions,
                personality=personality,
                max_tokens=max_tokens,
                system_prompt_override=system,
                mode=mode,
            )
            
            clean = _strip_word_count_preamble(response)
            prev_count = len(clean.split())
            
            if prev_count == word_target:
                return clean
        
        return clean + f"\n\n⚠️ Note: This response is {prev_count} words (target: {word_target})."
    
    # ─── No constraints — plain call ──────────────────────────────────
    return call_llm(
        prompt,
        custom_instructions=custom_instructions,
        personality=personality,
        max_tokens=max_tokens,
        system_prompt_override=base_system_prompt or None,
        mode=mode,
    )


def _mock_llm(prompt: str) -> str:
    """Mock LLM for testing without API key."""
    msg_lower = prompt.lower()
    
    # Check for repetition request first
    repetition_response = handle_repetition_request(prompt)
    if repetition_response is not None:
        return repetition_response
    
    if "i saw her duck" in msg_lower:
        return "The sentence is ambiguous. It could mean either:\n- I saw the duck that belongs to her (\"duck\" as a noun), or\n- I saw her quickly lower her head/body (\"duck\" as a verb).\nMore context is needed to determine which meaning is intended."
    
    elif "what is sadness" in msg_lower:
        return "Sadness is an emotional state characterized by feelings of unhappiness, sorrow, or disappointment. It's a normal human emotion."
    elif "what is hope" in msg_lower:
        return "Hope is an optimistic state of mind that expects positive outcomes. It's the belief that things can get better."
    elif "what is love" in msg_lower:
        return "Love is a complex set of emotions and behaviors associated with strong feelings of affection, protectiveness, warmth, and respect for another person."
    elif "soil erosion" in msg_lower:
        return "Soil erosion is the removal of topsoil by wind, water, or human activity. It can lead to loss of fertile land and environmental damage."
    else:
        return "I'm Ava, your AI assistant. I can answer any question – just ask! (To use the full AI model, add your Groq API key.)"


# ═══════════════════════════════════════════════════════════════════════════════
# ─── WIDGET SYSTEM ────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

_WIDGET_TRIGGERS = [
    (r"\b(density|mass.*volume|volume.*mass|kg/l|g/cm|g/l)\b", "density_calculator"),
    (r"\b(1\s*kg.*(?:steel|feather)|(?:steel|feather).*1\s*kg|heavier.*feather|feather.*heavier)\b", "density_calculator"),
    (r"\b(photosynthesis|chlorophyll|chloroplast|glucose.*plant|plant.*oxygen)\b", "photosynthesis_diagram"),
    (r"\b(speed|velocity)\b.*\b(distance|time)\b|\b(distance|time)\b.*\b(speed|velocity)\b", "speed_calculator"),
    (r"\b(temperature|celsius|fahrenheit|kelvin|convert.*temp|temp.*convert)\b", "temperature_converter"),
    (r"\b(pythagor|hypotenuse|right\s*triangle)\b", "pythagorean_calculator"),
    (r"\b(bmi|body\s*mass\s*index)\b", "bmi_calculator"),
    (r"\b(ohm|voltage|current.*resist|resist.*current)\b", "ohm_law_calculator"),
    (r"\b(compound\s*interest|interest\s*rate.*principal|principal.*interest)\b", "compound_interest"),
]

_WIDGET_HTML = {
    "density_calculator": """<div class="ava-widget">
  <div class="widget-title">⚗️ Density Calculator <span class="widget-formula">ρ = m / V</span></div>
  <div class="widget-body">
    <div class="widget-sliders">
      <label>Mass (m) <span id="dw-mv">1.0</span> kg
        <input type="range" id="dw-m" min="0.1" max="50" step="0.1" value="1">
      </label>
      <label>Volume (V) <span id="dw-vv">1.0</span> L
        <input type="range" id="dw-v" min="0.1" max="50" step="0.1" value="1">
      </label>
    </div>
    <div class="widget-result" id="dw-res">ρ = 1.00 kg/L</div>
    <div class="widget-visual">
      <div class="cylinder"><div class="liquid" id="dw-liq"></div><div id="dw-pts"></div></div>
      <div class="cylinder-label" id="dw-lbl">Low density</div>
    </div>
  </div>
</div>
<script>(function(){
  var m=document.getElementById('dw-m'),v=document.getElementById('dw-v');
  function upd(){
    var mv=+m.value,vv=+v.value,d=mv/vv;
    document.getElementById('dw-mv').textContent=mv.toFixed(1);
    document.getElementById('dw-vv').textContent=vv.toFixed(1);
    document.getElementById('dw-res').textContent='ρ = '+d.toFixed(2)+' kg/L';
    var pct=Math.min(92,Math.max(8,(vv/50)*88));
    var liq=document.getElementById('dw-liq');
    liq.style.height=pct+'%';
    liq.style.background='rgba(84,230,242,'+(0.25+Math.min(1,d/10)*0.6)+')';
    var pts=document.getElementById('dw-pts'); pts.innerHTML='';
    var n=Math.min(28,Math.round(d*3));
    for(var i=0;i<n;i++){var p=document.createElement('div');p.className='particle';p.style.left=Math.random()*80+10+'%';p.style.bottom=Math.random()*pct+'%';pts.appendChild(p);}
    var labels=['Very low density','Low density','Medium density','High density','Extremely dense'];
    document.getElementById('dw-lbl').textContent=labels[Math.min(4,Math.floor(d/2.5))];
  }
  m.addEventListener('input',upd);v.addEventListener('input',upd);upd();
})();</script>""",
    "photosynthesis_diagram": """<div class="ava-widget">
  <div class="widget-title">🌿 Photosynthesis</div>
  <div class="widget-body" style="align-items:center">
    <svg viewBox="0 0 420 190" style="width:100%;max-width:420px">
      <defs>
        <linearGradient id="sunG2" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#FFE066"/><stop offset="100%" stop-color="#FFB300"/></linearGradient>
        <linearGradient id="lfG2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#4CAF50"/><stop offset="100%" stop-color="#1B5E20"/></linearGradient>
        <marker id="aB" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3z" fill="#90CAF9"/></marker>
        <marker id="aY" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3z" fill="#FFB300"/></marker>
        <marker id="aG" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3z" fill="#A5D6A7"/></marker>
      </defs>
      <circle cx="48" cy="48" r="28" fill="url(#sunG2)"/>
      <text x="48" y="52" text-anchor="middle" font-size="10" font-weight="700" fill="#7B4000">☀️ Sun</text>
      <ellipse cx="205" cy="105" rx="68" ry="42" fill="url(#lfG2)" opacity="0.92"/>
      <text x="205" y="109" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">🌿 Leaf</text>
      <path d="M28 115 Q85 132 138 112" stroke="#90CAF9" stroke-width="2.5" fill="none" marker-end="url(#aB)"/>
      <text x="68" y="144" text-anchor="middle" font-size="10" fill="#90CAF9">CO₂</text>
      <path d="M28 152 Q85 158 138 138" stroke="#64B5F6" stroke-width="2.5" fill="none" marker-end="url(#aB)"/>
      <text x="68" y="172" text-anchor="middle" font-size="10" fill="#64B5F6">H₂O</text>
      <path d="M73 58 Q138 72 153 90" stroke="#FFB300" stroke-width="2" fill="none" stroke-dasharray="5,3" marker-end="url(#aY)"/>
      <text x="108" y="66" text-anchor="middle" font-size="9" fill="#FFB300">light</text>
      <path d="M270 95 Q325 75 378 62" stroke="#A5D6A7" stroke-width="2.5" fill="none" marker-end="url(#aG)"/>
      <text x="338" y="58" text-anchor="middle" font-size="9" fill="#A5D6A7">Glucose (C₆H₁₂O₆)</text>
      <path d="M270 118 Q325 136 378 148" stroke="#81D4FA" stroke-width="2.5" fill="none" marker-end="url(#aG)"/>
      <text x="340" y="163" text-anchor="middle" font-size="9" fill="#81D4FA">O₂ released</text>
    </svg>
    <div class="widget-formula" style="text-align:center;margin-top:4px">6CO₂ + 6H₂O + light energy → C₆H₁₂O₆ + 6O₂</div>
  </div>
</div>""",
    "temperature_converter": """<div class="ava-widget">
  <div class="widget-title">🌡️ Temperature Converter</div>
  <div class="widget-body">
    <div class="widget-sliders">
      <label>Celsius <span id="tw-cv">0</span>°C
        <input type="range" id="tw-c" min="-100" max="200" step="1" value="0">
      </label>
    </div>
    <div class="widget-result" id="tw-res"></div>
  </div>
</div>
<script>(function(){
  var c=document.getElementById('tw-c');
  function upd(){var cv=+c.value,f=cv*9/5+32,k=cv+273.15;
    document.getElementById('tw-cv').textContent=cv;
    document.getElementById('tw-res').innerHTML='<span>'+cv+'°C</span> = <span>'+f.toFixed(1)+'°F</span> = <span>'+k.toFixed(2)+' K</span>';}
  c.addEventListener('input',upd);upd();
})();</script>""",
    "speed_calculator": """<div class="ava-widget">
  <div class="widget-title">🚀 Speed Calculator <span class="widget-formula">v = d / t</span></div>
  <div class="widget-body">
    <div class="widget-sliders">
      <label>Distance <span id="sw-dv">100</span> km
        <input type="range" id="sw-d" min="1" max="1000" step="1" value="100">
      </label>
      <label>Time <span id="sw-tv">2.0</span> hr
        <input type="range" id="sw-t" min="0.1" max="24" step="0.1" value="2">
      </label>
    </div>
    <div class="widget-result" id="sw-res">Speed = 50.0 km/h</div>
  </div>
</div>
<script>(function(){
  var d=document.getElementById('sw-d'),t=document.getElementById('sw-t');
  function upd(){var dv=+d.value,tv=+t.value;
    document.getElementById('sw-dv').textContent=dv;
    document.getElementById('sw-tv').textContent=tv.toFixed(1);
    document.getElementById('sw-res').textContent='Speed = '+(dv/tv).toFixed(1)+' km/h';}
  d.addEventListener('input',upd);t.addEventListener('input',upd);upd();
})();</script>""",
    "pythagorean_calculator": """<div class="ava-widget">
  <div class="widget-title">📐 Pythagorean Theorem <span class="widget-formula">a² + b² = c²</span></div>
  <div class="widget-body">
    <div class="widget-sliders">
      <label>Side a <span id="pw-av">3</span>
        <input type="range" id="pw-a" min="1" max="20" step="0.5" value="3">
      </label>
      <label>Side b <span id="pw-bv">4</span>
        <input type="range" id="pw-b" min="1" max="20" step="0.5" value="4">
      </label>
    </div>
    <div class="widget-result" id="pw-res">c = 5.00</div>
  </div>
</div>
<script>(function(){
  var a=document.getElementById('pw-a'),b=document.getElementById('pw-b');
  function upd(){var av=+a.value,bv=+b.value;
    document.getElementById('pw-av').textContent=av;
    document.getElementById('pw-bv').textContent=bv;
    document.getElementById('pw-res').textContent='c = '+Math.sqrt(av*av+bv*bv).toFixed(2);}
  a.addEventListener('input',upd);b.addEventListener('input',upd);upd();
})();</script>""",
    "bmi_calculator": """<div class="ava-widget">
  <div class="widget-title">⚖️ BMI Calculator <span class="widget-formula">BMI = kg / m²</span></div>
  <div class="widget-body">
    <div class="widget-sliders">
      <label>Weight <span id="bw-kv">70</span> kg
        <input type="range" id="bw-k" min="30" max="200" step="1" value="70">
      </label>
      <label>Height <span id="bw-hv">170</span> cm
        <input type="range" id="bw-h" min="100" max="220" step="1" value="170">
      </label>
    </div>
    <div class="widget-result" id="bw-res"></div>
  </div>
</div>
<script>(function(){
  var k=document.getElementById('bw-k'),h=document.getElementById('bw-h');
  function upd(){var kv=+k.value,hm=+h.value/100,bmi=kv/(hm*hm);
    document.getElementById('bw-kv').textContent=kv;
    document.getElementById('bw-hv').textContent=+h.value;
    var cat=bmi<18.5?'Underweight':bmi<25?'Normal weight':bmi<30?'Overweight':'Obese';
    document.getElementById('bw-res').innerHTML=bmi.toFixed(1)+' <em>('+cat+')</em>';}
  k.addEventListener('input',upd);h.addEventListener('input',upd);upd();
})();</script>""",
    "ohm_law_calculator": """<div class="ava-widget">
  <div class="widget-title">⚡ Ohm's Law <span class="widget-formula">V = I × R</span></div>
  <div class="widget-body">
    <div class="widget-sliders">
      <label>Current (I) <span id="ow-iv">2.0</span> A
        <input type="range" id="ow-i" min="0.1" max="20" step="0.1" value="2">
      </label>
      <label>Resistance (R) <span id="ow-rv">5</span> Ω
        <input type="range" id="ow-r" min="1" max="100" step="1" value="5">
      </label>
    </div>
    <div class="widget-result" id="ow-res">V = 10.0 V  |  P = 20.0 W</div>
  </div>
</div>
<script>(function(){
  var i=document.getElementById('ow-i'),r=document.getElementById('ow-r');
  function upd(){var iv=+i.value,rv=+r.value;
    document.getElementById('ow-iv').textContent=iv.toFixed(1);
    document.getElementById('ow-rv').textContent=rv;
    document.getElementById('ow-res').textContent='V = '+(iv*rv).toFixed(1)+' V  |  P = '+(iv*iv*rv).toFixed(1)+' W';}
  i.addEventListener('input',upd);r.addEventListener('input',upd);upd();
})();</script>""",
    "compound_interest": """<div class="ava-widget">
  <div class="widget-title">💰 Compound Interest <span class="widget-formula">A = P(1 + r)ⁿ</span></div>
  <div class="widget-body">
    <div class="widget-sliders">
      <label>Principal <span id="ci-pv">1000</span> $
        <input type="range" id="ci-p" min="100" max="100000" step="100" value="1000">
      </label>
      <label>Rate <span id="ci-rv">5</span>%
        <input type="range" id="ci-r" min="1" max="30" step="0.5" value="5">
      </label>
      <label>Years <span id="ci-tv">10</span>
        <input type="range" id="ci-t" min="1" max="50" step="1" value="10">
      </label>
    </div>
    <div class="widget-result" id="ci-res"></div>
  </div>
</div>
<script>(function(){
  var p=document.getElementById('ci-p'),r=document.getElementById('ci-r'),t=document.getElementById('ci-t');
  function upd(){var pv=+p.value,rv=+r.value/100,tv=+t.value,A=pv*Math.pow(1+rv,tv);
    document.getElementById('ci-pv').textContent=pv.toLocaleString();
    document.getElementById('ci-rv').textContent=+r.value;
    document.getElementById('ci-tv').textContent=tv;
    document.getElementById('ci-res').innerHTML='$'+A.toLocaleString(undefined,{maximumFractionDigits:2})+' <em>(+$'+(A-pv).toLocaleString(undefined,{maximumFractionDigits:2})+' interest)</em>';}
  p.addEventListener('input',upd);r.addEventListener('input',upd);t.addEventListener('input',upd);upd();
})();</script>""",
}


def get_widget_for_message(user_message: str):
    msg = user_message.lower()
    for pattern, widget_type in _WIDGET_TRIGGERS:
        if re.search(pattern, msg, re.IGNORECASE):
            return _WIDGET_HTML.get(widget_type)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ─── TEST MODE ─────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing Ava LLM Module")
    print("=" * 60)
    
    test_cases = [
        ("Repeat 'hello' 5 times", "Repetition"),
        ("What is the capital of Australia?", "Fact"),
        ("Who won the 2025 Nobel Prize?", "Unknown"),
        ("What's the weather tomorrow?", "Real-time"),
    ]
    
    print("\n📝 Testing basic functionality:")
    for question, category in test_cases:
        print(f"\n{category}: {question}")
        result = handle_repetition_request(question)
        if result:
            print(f"  → Handled by repetition handler: {result[:50]}...")
        else:
            print(f"  → Would go to LLM")
    
    print("\n" + "=" * 60)
    print("✅ Test complete")