"""
metrics.py — Lightweight in-memory operational metrics collector for Ava AI.
Enforces zero high-cardinality labels (no raw user IDs, emails, or message bodies).
"""

import threading
import time

class MetricsCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._counters = {
            "chat_requests": 0,
            "chat_errors": 0,
            "stream_requests": 0,
            "llm_failures": 0,
            "adaptation_used_count": 0,
            "feedback_positive": 0,
            "feedback_negative": 0,
            "rate_limit_events": 0,
            "database_errors": 0,
        }
        self._total_latency_ms = 0
        self._latency_samples = 0
        self._min_latency_ms = float("inf")
        self._max_latency_ms = 0.0

    def inc(self, metric: str, amount: int = 1) -> None:
        with self._lock:
            if metric in self._counters:
                self._counters[metric] += amount

    def record_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._total_latency_ms += latency_ms
            self._latency_samples += 1
            if latency_ms < self._min_latency_ms:
                self._min_latency_ms = latency_ms
            if latency_ms > self._max_latency_ms:
                self._max_latency_ms = latency_ms

    def get_metrics(self) -> dict:
        with self._lock:
            avg_latency = (
                round(self._total_latency_ms / self._latency_samples, 2)
                if self._latency_samples > 0
                else 0.0
            )
            min_lat = round(self._min_latency_ms, 2) if self._latency_samples > 0 else 0.0
            max_lat = round(self._max_latency_ms, 2) if self._latency_samples > 0 else 0.0
            uptime_seconds = int(time.time() - self._start_time)
            result = {
                "uptime_seconds": uptime_seconds,
                "counters": dict(self._counters),
                "latency": {
                    "count": self._latency_samples,
                    "avg_ms": avg_latency,
                    "min_ms": min_lat,
                    "max_ms": max_lat,
                    "total_ms": round(self._total_latency_ms, 2)
                },
                # Flat mirrors for easy access
                **self._counters,
                "average_latency_ms": avg_latency,
                "latency_samples": self._latency_samples,
            }
            return result

    def get_snapshot(self) -> dict:
        return self.get_metrics()

    def reset(self) -> None:
        with self._lock:
            for k in self._counters:
                self._counters[k] = 0
            self._total_latency_ms = 0
            self._latency_samples = 0
            self._min_latency_ms = float("inf")
            self._max_latency_ms = 0.0
            self._start_time = time.time()

# Global collector instance
metrics = MetricsCollector()
