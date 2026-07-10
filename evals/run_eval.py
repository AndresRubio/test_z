"""Offline eval: golden-set queries against a RUNNING Assistant API.

Usage:
    uv run python -m evals.run_eval --base-url http://localhost:8000 [--strict]

Checks are structural (retrieval hit-rate and empty-products behavior).
Answer-quality judging (LLM-as-judge) is future work — see the README roadmap.
"""
import argparse
import json
import sys
from pathlib import Path

import httpx

GOLDEN_PATH = Path(__file__).parent / "golden_set.json"


def evaluate_case(case: dict, response_body: dict) -> tuple[bool, str]:
    expect = case["expect"]
    kind = expect["kind"]
    product_ids = {
        p["product_id"] for p in response_body["retrieved_products"]["products"]
    }
    if kind == "products":
        wanted = set(expect["any_of_product_ids"])
        ok = bool(product_ids & wanted)
        return ok, f"expected any of {sorted(wanted)}, got {sorted(product_ids)}"
    if kind == "empty_products":
        ok = not product_ids
        return ok, f"expected no products, got {sorted(product_ids)}"
    raise ValueError(f"Unknown expect.kind: {kind!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero if any non-known-limitation case fails")
    args = parser.parse_args()

    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    failures = 0
    known_failures = 0

    with httpx.Client(base_url=args.base_url, timeout=120.0) as client:
        for case in cases:
            response = client.post(
                "/chat", json={"site_id": case["site_id"], "query": case["query"]}
            )
            response.raise_for_status()
            ok, detail = evaluate_case(case, response.json())
            known = case.get("known_limitation", False)
            status = "PASS" if ok else ("KNOWN-FAIL" if known else "FAIL")
            print(f"{status:10s} {case['id']:40s} {'' if ok else detail}")
            if not ok:
                if known:
                    known_failures += 1
                else:
                    failures += 1

    scored = len(cases) - sum(1 for c in cases if c.get("known_limitation"))
    print(f"\nHeadline: {scored - failures}/{scored} passed "
          f"({known_failures} known-limitation failures excluded)")
    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
