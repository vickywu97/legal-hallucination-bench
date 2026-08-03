"""Generate a faithful demo input (answers.jsonl) + expert-annotated
candidates.expert.jsonl for the annotate.py --candidates strict-eval loop.

The ground-truth statute texts are pulled straight from the verified KB so the
EXACT cases are genuinely verbatim. Three toy models are crafted to exercise
the full engine:

  * Model-Precise   : cites 刑法232 + 民法典584 verbatim, but appends trailing
                      prose after the quote -> heuristic window picks up noise.
  * Model-Subtle    : cites 刑法232 but DROPS the "情节较轻" tail clause
                      (a realistic, tiny deviation) + 旧公司法3 (temporal trap)
                      + 民法典584 verbatim.
  * Model-Misattr   : cites 刑法232 but renders 刑法234's text (张冠李戴).

Run:  python demo/gen_answers.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws
from benchmark.annotate import build_skeleton

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "demo")


def main():
    laws = load_laws()
    rev_x = laws["刑法"].revisions[list(laws["刑法"].revisions)[-1]]
    gt232 = rev_x.articles["232"].content
    gt234 = rev_x.articles["234"].content
    rev_c = laws["民法典"].revisions[list(laws["民法典"].revisions)[-1]]
    gt584 = rev_c.articles["584"].content

    # subtle deviation: drop the "情节较轻" tail clause of 刑法232
    gt232_dropped = "；".join(gt232.split("；")[:-1])

    # --- craft model answers ------------------------------------------------
    precise = (
        "关于故意杀人罪的量刑，根据《刑法》第232条，" + gt232 +
        "。在本案中，被告持刀行凶，其行为完全符合该条规定，应当依法严惩。"
        "\n关于违约损害赔偿，根据《民法典》第584条，" + gt584 +
        "。这一规则确立了可预见性限制原则。"
    )
    subtle = (
        "根据《刑法》第232条，" + gt232_dropped +
        "另，《旧公司法》第3条规定公司是企业法人。"
        "\n根据《民法典》第584条，" + gt584
    )
    misattr = (
        "根据《刑法》第232条，" + gt234 +
        "\n根据《民法典》第584条，" + gt584
    )

    records = [
        {"model": "Model-Precise", "as_of_date": "2025-01-01", "answer": precise},
        {"model": "Model-Subtle", "as_of_date": "2025-01-01", "answer": subtle},
        {"model": "Model-Misattr", "as_of_date": "2025-01-01", "answer": misattr},
    ]

    answers_path = os.path.join(DEMO, "answers.jsonl")
    with open(answers_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {answers_path}")

    # --- expert annotation: isolate the model's EXACT quoted text -----------
    # Index order == extraction order (first 《...》第X条 appearance per answer).
    clean = {
        "Model-Precise": {  # heuristic window would grab trailing "在本案中…"
            "0": gt232,       # 刑法232 -> trim trailing prose -> verbatim
            "1": gt584,       # 民法典584 -> verbatim
        },
        "Model-Subtle": {
            "0": gt232_dropped,  # 刑法232 -> the model's ACTUAL (dropped) quote
            "1": "公司是企业法人。",  # 旧公司法3 -> temporal trap (text ignored)
            "2": gt584,            # 民法典584 -> verbatim
        },
        "Model-Misattr": {
            "0": gt234,   # 刑法232 cited but 234 text rendered (张冠李戴)
            "1": gt584,   # 民法典584 -> verbatim
        },
    }

    skel = build_skeleton(records)
    for s in skel:
        m = s["model"]
        for k, v in clean.get(m, {}).items():
            s["candidates"][k] = v

    expert_path = os.path.join(DEMO, "candidates.expert.jsonl")
    with open(expert_path, "w", encoding="utf-8") as f:
        for s in skel:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"wrote {expert_path}")


if __name__ == "__main__":
    main()
