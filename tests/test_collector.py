"""Tests for the zero-dependency answer collector's resilience logic.

These mock the network layer so they run offline and fast. They guard the two
behaviors added for the Kimi 400 incident:
  - error *body* is surfaced (so a 400 is debuggable from logs alone)
  - a schema-strict 400 self-heals via a minimal-payload retry
"""
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.generate_answers as g


class TestCollectorResilience(unittest.TestCase):
    def _messages(self):
        return [
            {"role": "system", "content": g.SYSTEM_PROMPT},
            {"role": "user", "content": "p"},
        ]

    def test_body_is_surfaced_on_persistent_400(self):
        # Full payload 400s twice (no self-heal because body insists on 400 even
        # for minimal) -> the RuntimeError must carry the provider response body.
        calls = []

        def fake_post(url, headers, payload):
            calls.append(payload)
            raise RuntimeError('HTTP 400: Bad Request | body={"error":{"message":"bad model field"}}')

        with patch.object(g, "_post", side_effect=fake_post):
            with self.assertRaises(RuntimeError) as cm:
                g._call_openai({"url": "u", "model": "m"}, "k", "p")
        self.assertIn('body={"error"', str(cm.exception))
        # full payload only; minimal was attempted because of the 400 path
        self.assertEqual(len(calls), 2)

    def test_minimal_fallback_succeeds_on_400(self):
        full = {
            "model": "m",
            "messages": self._messages(),
            "temperature": 0,
            "stream": False,
        }
        minimal = {"model": "m", "messages": self._messages()}
        calls = []

        def fake_post(url, headers, payload):
            calls.append(payload)
            if payload == full:
                raise RuntimeError("HTTP 400: Bad Request | body=...")
            return {"choices": [{"message": {"content": "  hi  "}}]}

        with patch.object(g, "_post", side_effect=fake_post):
            out = g._call_openai({"url": "u", "model": "m"}, "k", "p")
        self.assertEqual(out, "hi")  # stripped
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1], minimal)

    def test_500_still_raises_without_minimal_fallback(self):
        # 5xx should retry per _post policy and never trigger the 400-only heal.
        def fake_post(url, headers, payload):
            raise RuntimeError("HTTP 500: Internal Server Error | body=...")
        with patch.object(g, "_post", side_effect=fake_post):
            with self.assertRaises(RuntimeError):
                g._call_openai({"url": "u", "model": "m"}, "k", "p")


if __name__ == "__main__":
    unittest.main()
