# Ava AI — Beta Test Plan & Product Validation Protocol

This document establishes the real-user beta validation protocol for **Ava AI (v1.0.1)**. The objective is to validate product-market fit, user comprehension, memory utility, and behavioral adaptation with an initial cohort of **5 to 20 real users** under strict privacy safeguards.

---

## 1. Beta Cohort & Onboarding Architecture

- **Cohort Size**: 5–20 external testers across target user profiles (Developers, Designers, Technical Product Builders).
- **Account Creation**: Standard self-serve authentication via `/auth.html` (Email/Password or Google OAuth). **No hard-coded tester accounts or bypasses exist in the codebase**.
- **Tester Isolation**: Multi-tenant database architecture strictly isolates session histories, persistent memory records, and adaptation profiles by user ID.
- **Privacy Assurance**: Telemetry records aggregate product interaction events without capturing raw prompts, assistant responses, factual memory text, or passwords.

---

## 2. 12-Step Beta Protocol

Each tester is guided through a sequential 12-step validation checklist:

| Step | Action | Objective / What to Validate |
| :--- | :--- | :--- |
| **1. Landing Page** | Visit `/` | Evaluate value proposition clarity, trust metrics, persona cards, and interactive demo. |
| **2. Signup** | Register at `/auth.html?mode=signup` | Confirm frictionless account creation and immediate redirection to chat. |
| **3. Normal Chat** | Exchange 3+ messages in main workspace | Verify conversational fluency, topic comprehension, and system latency. |
| **4. Streaming Response** | Submit a detailed query | Test word-by-word streaming rendering, status indicators, and completion state. |
| **5. New Session** | Click "+ New chat" | Verify session state isolation (session history resets to a fresh conversation). |
| **6. Persistent Memory** | Execute Memory Scenario (Section 4) | Verify cross-session recall of explicit user facts without vector databases. |
| **7. Explicit Preference** | Execute Adaptation Scenario (Section 5) | Validate behavioral style adjustment (verbosity, technical depth, tone). |
| **8. Feedback Thumbs** | Click 👍 / 👎 on responses | Verify feedback capture, counter update, and closed-loop strategy learning. |
| **9. Logout / Login** | Log out and re-authenticate | Confirm secure session cookie persistence and seamless resumption of chat list. |
| **10. Mobile Experience** | Open on smartphone or mobile viewport | Validate responsive layout, collapsible sidebar, touch targets, and drawer chat. |
| **11. Landing Drawer** | Open floating launcher on `/` | Verify landing drawer chatbot interaction and message history synchronization. |
| **12. Data / Memory Controls** | Inspect account settings | Test user data transparency: view saved memory, reset adaptation, or delete session. |

---

## 3. Post-Test Qualitative Survey

Following protocol completion, interview testers or collect answers to these standardized questions:

1. **Clarity**: *Was Ava's purpose and distinction from generic chatbots immediately clear on the landing page?*
2. **Onboarding**: *Was account signup fast and intuitive?*
3. **Latency**: *Did responses feel fast and responsive, especially when streaming?*
4. **Memory Utility**: *Did Ava remember your facts across sessions without you having to re-explain context?*
5. **Adaptation**: *Did you notice Ava adjusting its tone, verbosity, or explanation style to match your preferences?*
6. **Privacy & Trust**: *Did anything feel creepy, unexpected, or opaque regarding how your data is handled?*
7. **Friction**: *Where did you experience confusion, unexpected errors, or awkward delays?*
8. **Value**: *Which single feature felt most valuable: persistent factual memory, behavioral adaptation, or real-time speed?*
9. **Retention**: *What specific capability would make you return to Ava as your primary personal AI?*

---

## 4. Controlled Memory Beta Scenario

Ava features structured persistent factual memory without vector databases or RAG. Testers evaluate factual persistence across distinct sessions:

### Scenario Protocol:
1. **Session A (Input)**:
   > *"Remember that my preferred programming language is Python and I am building an async microservice."*
2. **Verification A**: Ava acknowledges the durable fact and stores it in persistent user memory.
3. **Session Switch**: Click **"+ New chat"** to instantiate an entirely fresh conversation session (Session B).
4. **Session B (Recall)**:
   > *"What programming language do I prefer and what kind of project am I building?"*
5. **Expected Result**: Ava accurately references Python and the async microservice project from persistent memory across session boundaries.

*Note for Beta Coordinators: Do NOT log the recalled factual text into analytics. Only record whether the test succeeded (`memory_test_success = true/false`).*

---

## 5. Controlled Behavioral Adaptation Scenario

Ava's behavioral adaptation engine calibrates response style across 6 behavioral dimensions and 6 response strategies.

### Scenario Protocol:
1. **Calibration Phase**:
   Send 2–3 requests with concise styling feedback:
   > *"Keep your answers extremely concise and direct."*
   Rate responses with 👍 (Helpful).
2. **Generalization Phase**:
   Ask an unrelated conceptual or planning question:
   > *"What are three key considerations when designing an API?"*
   - **Evaluation**: Does Ava automatically deliver a concise, punchy answer matching the learned brevity preference without being explicitly asked in this prompt?
3. **Dynamic Override Phase**:
   Explicitly request the opposite format:
   > *"For this answer, explain distributed consensus in comprehensive step-by-step detail with code."*
   - **Evaluation**: Does Ava honor the prompt-level override immediately, demonstrating that learned baseline preferences yield to explicit user instructions?

---

## 6. Real-Time Error & Reliability Monitoring

During beta testing, system administrators monitor backend logs and telemetry endpoints:

```bash
# View live backend logs
docker logs -f ava-rc-test

# Check operational metrics snapshot
curl -s -b cookies.txt http://127.0.0.1:8000/api/metrics

# Check beta aggregate metrics
curl -s -b cookies.txt http://127.0.0.1:8000/api/admin/beta-metrics?period_days=7
```

### Key Reliability Indicators:
- **HTTP 5xx Errors**: Target = 0.
- **LLM Execution Failures**: Tracked via `llm_failures` and `chat_error` events.
- **Stream Premature Disconnections**: Tracked via `stream_error` events.
- **Database Lock Contention**: SQLite WAL mode with 5000ms busy timeout ensures concurrency resilience.
- **Rate Limit Hits**: Monitored via `rate_limit_hit` product events.
- **Privacy Rule**: Raw user chat content or private prompt tokens are strictly prohibited in application logs and analytics tables.

---

## 7. Data Retention & Privacy Policy

| Data Category | Storage Location | Retention Period | Deletion Mechanism |
| :--- | :--- | :--- | :--- |
| **Raw Product Events** | `product_events` table | **30–90 days** (Default: 60 days) | `scripts/cleanup_events.py --days 60` |
| **Aggregate Beta Metrics** | In-memory calculation from database | Indefinite (Non-personal KPIs) | Computed dynamically on request |
| **Beta Tester Feedback** | `beta_feedback` table | Retained until resolved/reviewed | Admin status update or user account purge |
| **Chat Sessions & Messages** | `sessions`, `messages` tables | User-controlled | Manual deletion in chat UI or account purge |
| **Persistent User Memory** | `user_memory` table | User-controlled | "Clear Memory" button in profile settings |
| **Behavioral Adaptation** | `adaptation_profiles` table | User-controlled | "Reset Adaptation" button in settings |

---

## 8. Core Beta KPIs & Success Criteria

1. **Acquisition**: Landing view count and CTA click-through rate (`landing_to_signup_rate >= 15%`).
2. **Activation**: Signup completion rate (`signup_completion_rate >= 75%`) and first chat activation (`signup_to_chat_rate >= 70%`).
3. **Engagement**: Average messages sent per active chat user (`>= 8 messages/user`).
4. **Quality**: Positive feedback ratio (`positive_feedback_rate >= 80%`).
5. **Personalization**: Adaptation usage rate in generated responses (`adaptation_usage_rate >= 30%`).
6. **Memory**: Successful cross-session recall in controlled memory scenarios (`>= 90%`).
7. **Reliability**: Chat error rate (`chat_errors / messages_sent < 1%`).
