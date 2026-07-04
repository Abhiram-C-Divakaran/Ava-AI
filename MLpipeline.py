"""
ML Pipeline — Zero external ML dependency approach.
"""
import re
from collections import defaultdict


class SentimentAnalyzer:
    POSITIVE_LEXICON = {
        "thank", "thanks", "great", "awesome", "excellent", "perfect", "love",
        "good", "nice", "helpful", "resolved", "fixed", "working", "works",
        "solved", "happy", "appreciate", "wonderful", "fantastic", "brilliant",
        "amazing", "pleased", "satisfied", "clear", "easy", "smooth"
    }
    NEGATIVE_LEXICON = {
        "broken", "crash", "error", "fail", "failed", "issue", "problem",
        "not working", "doesn't work", "bug", "wrong", "bad", "terrible",
        "awful", "horrible", "useless", "frustrated", "angry", "annoyed",
        "disappointed", "worst", "hate", "stuck", "lost", "confused",
        "impossible", "never", "always", "again", "still",
        "cannot", "can't", "won't", "slow", "down", "outage"
    }
    INTENSIFIERS = {"very", "extremely", "really", "so", "absolutely", "completely", "totally"}
    NEGATORS = {"not", "no", "never", "isn't", "aren't", "wasn't", "doesn't", "don't", "can't", "won't"}

    def analyze(self, text: str) -> dict:
        tokens = re.findall(r"\b\w+\b", text.lower())
        pos_score, neg_score = 0, 0
        intensifier_active = False
        for i, token in enumerate(tokens):
            if token in self.INTENSIFIERS:
                intensifier_active = True
                continue
            multiplier = 1.5 if intensifier_active else 1.0
            intensifier_active = False
            negated = any(tokens[max(0, i-2):i].count(n) > 0 for n in self.NEGATORS)
            if token in self.POSITIVE_LEXICON:
                if negated:
                    neg_score += 1.0 * multiplier
                else:
                    pos_score += 1.0 * multiplier
            if token in self.NEGATIVE_LEXICON:
                if negated:
                    pos_score += 0.5 * multiplier
                else:
                    neg_score += 1.0 * multiplier
        text_lower = text.lower()
        if "not working" in text_lower or "doesn't work" in text_lower:
            neg_score += 2.0
        if "thank you" in text_lower or "much appreciated" in text_lower:
            pos_score += 2.0
        total = pos_score + neg_score + 0.001
        if pos_score > neg_score * 1.2:
            label = "positive"
            score = pos_score / total
        elif neg_score > pos_score * 1.2:
            label = "negative"
            score = neg_score / total
        else:
            label = "neutral"
            score = 0.5
        return {"label": label, "score": round(min(score, 1.0), 3), "pos_score": round(pos_score, 2), "neg_score": round(neg_score, 2)}


class IntentClassifier:
    INTENT_PATTERNS = {
        "billing_issue": ["charge", "payment", "invoice", "refund", "bill", "subscription", "price", "cost", "fee", "money", "paid", "credit", "debit", "overcharged"],
        "login_issue": ["login", "sign in", "password", "forgot", "reset", "access", "account", "locked", "auth", "authenticate", "2fa", "otp", "username"],
        "app_crash": ["crash", "crashes", "crashing", "frozen", "freeze", "unresponsive", "black screen", "force close", "stops", "shuts", "error code"],
        "performance_issue": ["slow", "lag", "lagging", "loading", "takes forever", "timeout", "wait", "delay", "buffering", "stuck", "hangs", "response time"],
        "feature_request": ["add", "feature", "would be nice", "suggestion", "improve", "wish", "could you", "please add", "implement", "support for", "want"],
        "data_loss": ["lost", "missing", "deleted", "gone", "disappeared", "can't find", "backup", "restore", "recovery", "data", "file", "document"],
        "connectivity": ["connect", "connection", "offline", "internet", "network", "wifi", "sync", "not syncing", "disconnected", "server", "timeout"],
        "installation": ["install", "setup", "download", "update", "upgrade", "uninstall", "version", "install fails", "not installing"],
        "general_inquiry": ["how", "what", "where", "when", "why", "explain", "tell me", "information", "help", "guide", "tutorial", "documentation"],
        "escalation_request": ["manager", "supervisor", "escalate", "speak to", "human", "agent", "representative", "complaint", "unacceptable", "legal"],
        "general_question": ["what is", "who is", "why does", "how does", "explain", "define", "meaning of", "tell me about", "what's the difference", "what are", "can you explain", "describe", "what does"]
    }

    def classify(self, text: str) -> str:
        text_lower = text.lower()
        scores = defaultdict(float)
        for intent, keywords in self.INTENT_PATTERNS.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[intent] += 1 + len(kw.split()) * 0.5
        if not scores:
            return "general_inquiry"
        return max(scores, key=scores.__getitem__)


class FrustrationDetector:
    HIGH_FRUSTRATION_PHRASES = ["this is ridiculous", "absolutely useless", "never works", "sick of this", "worst app", "terrible service", "i give up", "still broken", "again?", "how many times", "waste of time", "scam", "fraud", "demanding refund", "unacceptable"]
    FRUSTRATION_WORDS = ["frustrated", "angry", "furious", "annoyed", "disgusted", "done with", "fed up", "had enough", "cannot believe"]
    _user_history = defaultdict(list)

    def score(self, user_id: str, message: str) -> float:
        score = 0.0
        text_lower = message.lower()
        alpha_chars = [c for c in message if c.isalpha()]
        if alpha_chars:
            caps_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
            if caps_ratio > 0.5:
                score += 0.25
        exclamations = message.count("!")
        questions = message.count("?")
        score += min(exclamations * 0.08, 0.2)
        score += min(questions * 0.05, 0.1)
        for phrase in self.HIGH_FRUSTRATION_PHRASES:
            if phrase in text_lower:
                score += 0.35
                break
        for word in self.FRUSTRATION_WORDS:
            if word in text_lower:
                score += 0.2
                break
        now = __import__("time").time()
        history = self._user_history[user_id]
        history.append(now)
        self._user_history[user_id] = history[-10:]
        if len(history) >= 3:
            recent_window = now - history[-3]
            if recent_window < 120:
                score += 0.2
        repeat_signals = ["again", "still", "same", "keep", "keeps", "every time"]
        for signal in repeat_signals:
            if signal in text_lower:
                score += 0.1
                break
        return min(score, 1.0)