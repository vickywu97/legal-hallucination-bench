"""Model API adapters (Week 5).

Uniform interface over providers so the harness stays provider-agnostic:
  - 智谱 GLM-4
  - 通义千问-Max
  - DeepSeek-Chat
  - (optional) GPT-4o / Claude for cross-reference

All calls are made with temperature=0 and a recorded seed for reproducibility.
Requires the optional `live` extra (httpx) and provider API keys.
"""
from __future__ import annotations
from typing import Dict, List


SUPPORTED = ["glm-4", "qwen-max", "deepseek-chat"]


def call_model(model_id: str, prompt: str, **kwargs) -> str:
    """Week 5 — not yet implemented."""
    raise NotImplementedError("call_model() lands in Week 5")
