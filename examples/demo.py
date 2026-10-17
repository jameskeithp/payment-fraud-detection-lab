"""End-to-end demo: generate synthetic transfers, score them, print a summary.

Usage:
    python examples/demo.py [--count 3000] [--seed 42]
"""

import argparse
import sys
from collections import Counter

sys.path.insert(0, ".")

from fraudlab.engine import FraudEngine
from fraudlab.generator import generate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    txs = generate(count=args.count, seed=args.seed, fraud=True)
    engine = FraudEngine()
    results = engine.evaluate_batch(txs)

    decisions = Counter(r.decision for r in results)
    print(f"Scored {len(results)} transactions (seed={args.seed})")
    for d in ("allow", "step_up_auth", "block"):
        print(f"  {d:13s} {decisions[d]:5d}")

    codes = Counter(f.reason_code for r in results for f in r.findings)
    print("\nTop finding reason codes:")
    for code, n in codes.most_common(8):
        print(f"  {code:32s} {n}")

    print("\nSample blocked transfers:")
    shown = 0
    for r in results:
        if r.decision == "block" and shown < 5:
            detail = "; ".join(f"{f.reason_code} ({f.severity})" for f in r.findings)
            t = r.transaction
            print(f"  {t.tx_id} {t.sender_id} {t.amount:.2f} {t.currency} "
                  f"score={r.score:.0f} :: {detail}")
            shown += 1


if __name__ == "__main__":
    main()
