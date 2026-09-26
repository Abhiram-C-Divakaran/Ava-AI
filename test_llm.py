#!/usr/bin/env python3
"""
test_llm.py — Comprehensive LLM Runtime & Regression Test Suite.

Verifies:
1. Canonical model resolves correctly
2. Explicit model argument overrides default
3. Unknown model is not silently changed
4. Streaming and non-streaming resolve identically
5. Transient 429 retries
6. 502 retries
7. 503 retries
8. 504 retries
9. 400 does not retry
10. 401 does not retry
11. 403 does not retry
12. Retry-After seconds parsing
13. Retry-After milliseconds parsing
14. Retry count is bounded
15. Timeout eventually raises a clean error
16. Connection error eventually raises cleanly
17. Ordinary text containing a number does NOT trigger repetition
18. "repeat hello 5 times" produces exactly five instances
19. "write hello 5 times" works
20. Unrelated "say something about 5 databases" is not treated as repetition
21. Documented aliases resolve properly
22. Diagnostic get_model_info surfaces both requested and actual model
"""

import os
import unittest
from unittest.mock import patch, MagicMock
import requests

import llm
from llm import (
    call_llm,
    call_llm_streaming,
    resolve_model,
    get_model_info,
    handle_repetition_request,
    parse_retry_after,
    MODEL,
    MODEL_ALIASES,
)


class TestLLMRuntimeSuite(unittest.TestCase):
    def setUp(self):
        # Ensure dummy API key so call_llm does not fallback to _mock_llm
        self.api_key_patch = patch.object(llm, "API_KEY", "gsk_test_mock_key_12345")
        self.api_key_patch.start()
        # Mock time.sleep to keep test suite fast
        self.sleep_patch = patch("time.sleep", return_value=None)
        self.sleep_patch.start()

    def tearDown(self):
        self.api_key_patch.stop()
        self.sleep_patch.stop()

    # 1. Canonical model resolves correctly
    def test_01_canonical_model_resolves_correctly(self):
        self.assertEqual(resolve_model(), "openai/gpt-oss-120b")
        self.assertEqual(resolve_model("openai/gpt-oss-120b"), "openai/gpt-oss-120b")
        self.assertEqual(resolve_model(""), "openai/gpt-oss-120b")
        self.assertEqual(resolve_model(MODEL), "openai/gpt-oss-120b")

    # 2. Explicit model argument overrides default
    @patch("llm.requests.post")
    def test_02_explicit_model_argument_overrides_default(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_post.return_value = mock_resp

        call_llm("test prompt", model="custom-override-model")

        self.assertTrue(mock_post.called)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["model"], "custom-override-model")

    # 3. Unknown model is not silently changed
    @patch("llm.requests.post")
    def test_03_unknown_model_is_not_silently_changed(self, mock_post):
        unknown = "some-unknown-future-model-v99"
        self.assertEqual(resolve_model(unknown), unknown)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_post.return_value = mock_resp

        call_llm("test prompt", model=unknown)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["model"], unknown)

    # 4. Streaming and non-streaming resolve identically
    @patch("llm.requests.post")
    def test_04_streaming_and_non_streaming_resolve_identically(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_resp.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "ok"}}]}',
            b'data: [DONE]',
        ]
        mock_post.return_value = mock_resp

        # Non-streaming default
        call_llm("hello")
        non_streaming_model = mock_post.call_args[1]["json"]["model"]

        # Streaming default
        list(call_llm_streaming("hello"))
        streaming_model = mock_post.call_args[1]["json"]["model"]

        self.assertEqual(non_streaming_model, streaming_model)
        self.assertEqual(streaming_model, resolve_model(MODEL))

        # Explicit model
        explicit = "another-model-v2"
        call_llm("hello", model=explicit)
        ns_explicit = mock_post.call_args[1]["json"]["model"]

        list(call_llm_streaming("hello", model=explicit))
        s_explicit = mock_post.call_args[1]["json"]["model"]

        self.assertEqual(ns_explicit, explicit)
        self.assertEqual(s_explicit, explicit)

    # 5. Transient 429 retries
    @patch("llm.requests.post")
    def test_05_transient_429_retries(self, mock_post):
        resp_429 = MagicMock(status_code=429, text='{"error": "rate limit, try again in 0.5s"}')
        resp_429.headers = {}
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {"choices": [{"message": {"content": "recovered from 429"}}]}

        mock_post.side_effect = [resp_429, resp_200]

        result = call_llm("test query", max_retries=3)
        self.assertEqual(result, "recovered from 429")
        self.assertEqual(mock_post.call_count, 2)

    # 6. 502 retries
    @patch("llm.requests.post")
    def test_06_502_retries(self, mock_post):
        resp_502 = MagicMock(status_code=502, text="Bad Gateway", headers={})
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {"choices": [{"message": {"content": "recovered from 502"}}]}

        mock_post.side_effect = [resp_502, resp_200]

        result = call_llm("test query", max_retries=3)
        self.assertEqual(result, "recovered from 502")
        self.assertEqual(mock_post.call_count, 2)

    # 7. 503 retries
    @patch("llm.requests.post")
    def test_07_503_retries(self, mock_post):
        resp_503 = MagicMock(status_code=503, text="Service Unavailable", headers={})
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {"choices": [{"message": {"content": "recovered from 503"}}]}

        mock_post.side_effect = [resp_503, resp_200]

        result = call_llm("test query", max_retries=3)
        self.assertEqual(result, "recovered from 503")
        self.assertEqual(mock_post.call_count, 2)

    # 8. 504 retries
    @patch("llm.requests.post")
    def test_08_504_retries(self, mock_post):
        resp_504 = MagicMock(status_code=504, text="Gateway Timeout", headers={})
        resp_200 = MagicMock(status_code=200)
        resp_200.json.return_value = {"choices": [{"message": {"content": "recovered from 504"}}]}

        mock_post.side_effect = [resp_504, resp_200]

        result = call_llm("test query", max_retries=3)
        self.assertEqual(result, "recovered from 504")
        self.assertEqual(mock_post.call_count, 2)

    # 9. 400 does not retry
    @patch("llm.requests.post")
    def test_09_400_does_not_retry(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400, text="Bad Request: invalid payload", headers={})

        with self.assertRaises(ValueError) as ctx:
            call_llm("test query", max_retries=5)

        self.assertIn("client error 400", str(ctx.exception))
        self.assertEqual(mock_post.call_count, 1)

    # 10. 401 does not retry
    @patch("llm.requests.post")
    def test_10_401_does_not_retry(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401, text="Unauthorized: Invalid API Key", headers={})

        with self.assertRaises(ValueError) as ctx:
            call_llm("test query", max_retries=5)

        self.assertIn("client error 401", str(ctx.exception))
        self.assertEqual(mock_post.call_count, 1)

    # 11. 403 does not retry
    @patch("llm.requests.post")
    def test_11_403_does_not_retry(self, mock_post):
        mock_post.return_value = MagicMock(status_code=403, text="Forbidden: Access Denied", headers={})

        with self.assertRaises(ValueError) as ctx:
            call_llm("test query", max_retries=5)

        self.assertIn("client error 403", str(ctx.exception))
        self.assertEqual(mock_post.call_count, 1)

    # 12. Retry-After seconds parsing
    def test_12_retry_after_seconds_parsing(self):
        # Header integer seconds
        self.assertEqual(parse_retry_after({"Retry-After": "2"}), 2.0)
        # Header float seconds
        self.assertEqual(parse_retry_after({"Retry-After": "3.5"}), 3.5)
        # Header with 's' suffix
        self.assertEqual(parse_retry_after({"Retry-After": "4s"}), 4.0)
        # Body text pattern
        self.assertEqual(parse_retry_after({}, "Rate limit reached. Please try again in 2.5s."), 2.5)

    # 13. Retry-After milliseconds parsing
    def test_13_retry_after_milliseconds_parsing(self):
        # Header milliseconds
        self.assertEqual(parse_retry_after({"Retry-After": "500ms"}), 0.5)
        self.assertEqual(parse_retry_after({"Retry-After": "250ms"}), 0.25)
        # Body text pattern with ms
        self.assertEqual(parse_retry_after({}, "Rate limit exceeded. try again in 400ms."), 0.4)

    # 14. Retry count is bounded
    @patch("llm.requests.post")
    def test_14_retry_count_is_bounded(self, mock_post):
        mock_post.return_value = MagicMock(status_code=429, text="Rate limit exceeded", headers={})

        max_allowed = 4
        with self.assertRaises(ValueError) as ctx:
            call_llm("test query", max_retries=max_allowed)

        self.assertEqual(mock_post.call_count, max_allowed)
        self.assertIn("transient error 429", str(ctx.exception))

    # 15. Timeout eventually raises a clean error
    @patch("llm.requests.post")
    def test_15_timeout_eventually_raises_clean_error(self, mock_post):
        mock_post.side_effect = requests.Timeout("Connection timed out after 30s")

        with self.assertRaises(ValueError) as ctx:
            call_llm("test query", max_retries=3)

        self.assertEqual(mock_post.call_count, 3)
        self.assertIn("failed after 3 attempts", str(ctx.exception))

    # 16. Connection error eventually raises cleanly
    @patch("llm.requests.post")
    def test_16_connection_error_eventually_raises_cleanly(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("Failed to establish a new connection")

        with self.assertRaises(ValueError) as ctx:
            call_llm("test query", max_retries=3)

        self.assertEqual(mock_post.call_count, 3)
        self.assertIn("failed after 3 attempts", str(ctx.exception))

    # 17. Ordinary text containing a number does NOT trigger repetition
    def test_17_ordinary_text_containing_a_number_does_not_trigger_repetition(self):
        prompts = [
            "We have 5 databases in the cluster.",
            "Explain 3 sorting algorithms.",
            "Top 10 vacation destinations in Europe.",
            "There are 42 apples on the tree.",
            "Tell me about the 7 habits of highly effective people.",
        ]
        for p in prompts:
            self.assertIsNone(handle_repetition_request(p), f"False positive repetition on: '{p}'")

    # 18. "repeat hello 5 times" produces exactly five instances
    def test_18_repeat_hello_5_times_produces_exactly_five_instances(self):
        resp = call_llm("repeat hello 5 times")
        self.assertIsNotNone(resp)
        # Check first block containing repeated instances
        rep_block = resp.split("\n\n")[0]
        words = rep_block.split()
        self.assertEqual(len(words), 5)
        self.assertEqual(words, ["hello"] * 5)
        self.assertEqual(words.count("hello"), 5)

    # 19. "write hello 5 times" works
    def test_19_write_hello_5_times_works(self):
        resp = call_llm("write hello 5 times")
        self.assertIsNotNone(resp)
        rep_block = resp.split("\n\n")[0]
        words = rep_block.split()
        self.assertEqual(len(words), 5)
        self.assertEqual(words, ["hello"] * 5)
        self.assertEqual(words.count("hello"), 5)

    # 20. Unrelated "say something about 5 databases" is not treated as repetition
    @patch("llm.requests.post")
    def test_20_unrelated_say_something_about_5_databases_not_repetition(self, mock_post):
        prompt = "say something about 5 databases"
        # Deterministic handler returns None
        self.assertIsNone(handle_repetition_request(prompt))

        # Full call routes to LLM
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"choices": [{"message": {"content": "PostgreSQL, MySQL, Redis, MongoDB, SQLite"}}]}
        mock_post.return_value = mock_resp

        result = call_llm(prompt)
        self.assertTrue(mock_post.called)
        self.assertIn("PostgreSQL", result)

    # 21. Documented aliases resolve properly
    def test_21_alias_model_resolution(self):
        for alias, target in MODEL_ALIASES.items():
            self.assertEqual(resolve_model(alias), target)

    # 22. Diagnostic get_model_info surfaces both requested and actual model
    def test_22_get_model_info_surfaces_provenance(self):
        # Unaliased
        info = get_model_info("openai/gpt-oss-120b")
        self.assertEqual(info["requested_model"], "openai/gpt-oss-120b")
        self.assertEqual(info["actual_model"], "openai/gpt-oss-120b")
        self.assertFalse(info["was_remapped"])

        # Aliased
        info_alias = get_model_info("llama-3.1-70b-versatile")
        self.assertEqual(info_alias["requested_model"], "llama-3.1-70b-versatile")
        self.assertEqual(info_alias["actual_model"], "openai/gpt-oss-120b")
        self.assertTrue(info_alias["was_remapped"])


if __name__ == "__main__":
    unittest.main()
