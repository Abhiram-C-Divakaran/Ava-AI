---
name: Adaptation Error
about: Report an issue with behavioral learning, strategy selection, or prompt override
title: "[ADAPTATION] "
labels: ["adaptation", "bug"]
assignees: ''
---

**Type of Adaptation Issue**
- [ ] Convergence Failure (Repeated feedback did not adjust behavioral profile)
- [ ] Override Ignored (Current explicit request did not supersede learned background profile)
- [ ] Strategy Misclassification (Incorrect response strategy selected for task domain)
- [ ] Reversal Resistance (Profile failed to reverse after contradictory preferences)
- [ ] Unexpected Suppression (Strategy inappropriately suppressed)

**Ava Version / Commit**
- Version:

**Interaction Details**
- Learned User Profile (from `/api/adaptation/profile` if known):
- Active User Message / Prompt:
- Expected Strategy / Behavior:
- Actual Behavior Emitted:

**Reproduction Steps**
1. Feedback sequence provided:
2. Prompt sent:
3. Behavior observed:
