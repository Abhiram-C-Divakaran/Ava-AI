---
name: Memory Error
about: Report an issue with factual memory retention, recall, or cross-session state
title: "[MEMORY] "
labels: ["memory", "bug"]
assignees: ''
---

**Type of Memory Issue**
- [ ] Memory Failure to Recall (User fact previously stored was not recalled)
- [ ] Stale Memory (Updated user fact did not overwrite older fact)
- [ ] Hallucinated / False Memory (Fact asserted that user never stated)
- [ ] Cross-Session Bleed (Session history leaked into an unrelated session)
- [ ] Potential Cross-User Leakage (CRITICAL: Fact from User A appeared for User B)

**Ava Version / Commit**
- Version:
- Deployment Mode:

**Reproduction Scenario**
1. User stated: "..."
2. Ava acknowledged: "..."
3. In a subsequent session, user asked: "..."
4. Ava responded: "..."

**Expected Memory Behavior**
What factual context should have been present in the prompt context?

**Relevant Context**
Any custom instructions or database configurations.
