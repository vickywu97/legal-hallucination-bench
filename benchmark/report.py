"""Audit-report renderer (Week 5).

Renders a model's results in the style of a real audit report that
attorneys immediately understand:
  - 检查项 (check item)
  - 检查依据 (basis — which KB / rule)
  - 发现 (finding)
  - 结论 (conclusion: 幻觉 / 异常 / 不可验证)
See docs/AUDIT_REPORT_TEMPLATE.md (to be added in Week 5).
"""
from __future__ import annotations
from typing import List


def render_audit(model_name: str, verifications: List[dict]) -> str:
    """Week 5 — not yet implemented."""
    raise NotImplementedError("render_audit() lands in Week 5")
