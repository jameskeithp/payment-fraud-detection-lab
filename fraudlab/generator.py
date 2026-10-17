"""Seeded synthetic transaction generator.

Produces realistic cross-border transfer records for lab use. With
--fraud, it injects recognizable attack patterns (velocity bursts,
impossible travel, new-device cash-outs, payee-change transfers) so
the engine has something to catch.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta

from fraudlab.models import GeoPoint, Transaction

CITIES = [
    ("New York", 40.7128, -74.0060),
    ("London", 51.5074, -0.1278),
    ("Lagos", 6.5244, 3.3792),
    ("Manila", 14.5995, 120.9842),
    ("Mumbai", 19.0760, 72.8777),
    ("Toronto", 43.6532, -79.3832),
    ("Sydney", -33.8688, 151.2093),
    ("Mexico City", 19.4326, -99.1332),
    ("Berlin", 52.5200, 13.4050),
    ("Nairobi", -1.2921, 36.8219),
    ("Baton Rouge", 30.4515, -91.1871),
    ("Singapore", 1.3521, 103.8198),
]

CURRENCIES = ["USD", "EUR", "GBP", "NGN", "PHP", "INR", "CAD", "MXN", "KES", "SGD"]


def _city(rng: random.Random) -> tuple[str, float, float]:
    return rng.choice(CITIES)


def generate(
    count: int = 1000,
    customers: int = 50,
    days: int = 30,
    seed: int = 42,
    fraud: bool = False,
    fraud_ratio: float = 0.08,
) -> list[Transaction]:
    rng = random.Random(seed)
    start = datetime(2026, 9, 16, 0, 0, 0)

    senders = [f"sender_{i:04d}" for i in range(customers)]
    devices = {s: [f"dev_{s}_{j}" for j in range(rng.randint(1, 3))] for s in senders}
    payees = {s: [f"payee_{s}_{j}" for j in range(rng.randint(1, 4))] for s in senders}
    # Each sender has a home city. Legitimate transfers cluster near home;
    # that is what makes far-flung fraud stand out.
    home_city = {s: rng.choice(CITIES) for s in senders}

    def near_home(rng: random.Random, s: str) -> tuple[str, float, float]:
        if rng.random() < 0.85:
            return home_city[s]
        return rng.choice(CITIES)

    txs: list[Transaction] = []
    n_fraud = int(count * fraud_ratio) if fraud else 0

    def normal_tx(i: int) -> Transaction:
        s = rng.choice(senders)
        label, lat, lon = near_home(rng, s)
        # Log-normal-ish remittance amounts: most transfers are small.
        amount = round(min(rng.lognormvariate(5.3, 1.1), 20000.0), 2)
        return Transaction(
            tx_id=f"tx_{i:06d}",
            sender_id=s,
            amount=amount,
            currency=rng.choice(CURRENCIES),
            timestamp=start + timedelta(seconds=rng.randint(0, days * 86400)),
            geo=GeoPoint(lat=round(lat + rng.uniform(-0.5, 0.5), 4),
                         lon=round(lon + rng.uniform(-0.5, 0.5), 4),
                         label=label),
            device_id=rng.choice(devices[s]),
            payee_id=rng.choice(payees[s]),
        )

    def fraud_tx(i: int, kind: int) -> Transaction:
        s = rng.choice(senders)
        label, lat, lon = _city(rng)
        base_time = start + timedelta(seconds=rng.randint(0, days * 86400))
        if kind == 0:  # velocity burst: handled by caller emitting a cluster
            raise AssertionError("velocity handled separately")
        if kind == 1:  # impossible travel: far from the sender's home city
            home = home_city[s]
            far = rng.choice([c for c in CITIES if abs(c[1] - home[1]) > 40])
            return Transaction(
                tx_id=f"tx_{i:06d}",
                sender_id=s,
                amount=round(rng.uniform(800, 4000), 2),
                currency="USD",
                timestamp=base_time + timedelta(minutes=20),
                geo=GeoPoint(lat=far[1], lon=far[2], label=far[0]),
                device_id=rng.choice(devices[s]),
                payee_id=rng.choice(payees[s]),
            )
        if kind == 2:  # new device cash-out
            return Transaction(
                tx_id=f"tx_{i:06d}",
                sender_id=s,
                amount=round(rng.uniform(3000, 9000), 2),
                currency="USD",
                timestamp=base_time,
                geo=GeoPoint(lat=lat, lon=lon, label=label),
                device_id=f"dev_unknown_{rng.randint(1000, 9999)}",
                payee_id=f"payee_new_{rng.randint(1000, 9999)}",
            )
        # kind == 3: payee change then transfer
        return Transaction(
            tx_id=f"tx_{i:06d}",
            sender_id=s,
            amount=round(rng.uniform(1500, 6000), 2),
            currency="USD",
            timestamp=base_time,
            geo=GeoPoint(lat=lat, lon=lon, label=label),
            device_id=rng.choice(devices[s]),
            payee_id=f"payee_new_{rng.randint(1000, 9999)}",
        )

    i = 0
    fraud_kinds = [1, 2, 3]
    while i < count:
        if fraud and i < n_fraud * 6 and rng.random() < 0.35 and i + 6 < count:
            # Velocity burst: 6 rapid transfers from one sender.
            s = rng.choice(senders)
            label, lat, lon = near_home(rng, s)
            t0 = start + timedelta(seconds=rng.randint(0, days * 86400))
            for k in range(6):
                txs.append(Transaction(
                    tx_id=f"tx_{i:06d}",
                    sender_id=s,
                    amount=round(rng.uniform(200, 900), 2),
                    currency="USD",
                    timestamp=t0 + timedelta(minutes=k),
                    geo=GeoPoint(lat=lat, lon=lon, label=label),
                    device_id=rng.choice(devices[s]),
                    payee_id=rng.choice(payees[s]),
                ))
                i += 1
            continue
        if fraud and i < n_fraud and rng.random() < 0.5:
            txs.append(fraud_tx(i, rng.choice(fraud_kinds)))
        else:
            txs.append(normal_tx(i))
        i += 1

    txs.sort(key=lambda t: t.timestamp)
    # Re-number tx_ids in time order for a clean feed.
    renumbered = [
        Transaction(
            tx_id=f"tx_{n:06d}",
            sender_id=t.sender_id,
            amount=t.amount,
            currency=t.currency,
            timestamp=t.timestamp,
            geo=t.geo,
            device_id=t.device_id,
            payee_id=t.payee_id,
        )
        for n, t in enumerate(txs)
    ]
    return renumbered


def tx_to_dict(t: Transaction) -> dict:
    return {
        "tx_id": t.tx_id,
        "sender_id": t.sender_id,
        "amount": t.amount,
        "currency": t.currency,
        "timestamp": t.timestamp.isoformat(),
        "geo": {"lat": t.geo.lat, "lon": t.geo.lon, "label": t.geo.label},
        "device_id": t.device_id,
        "payee_id": t.payee_id,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic transfer records.")
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--customers", type=int, default=50)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fraud", action="store_true", help="inject fraud patterns")
    ap.add_argument("--out", default="transactions.jsonl")
    args = ap.parse_args()

    txs = generate(count=args.count, customers=args.customers, days=args.days,
                   seed=args.seed, fraud=args.fraud)
    with open(args.out, "w") as f:
        for t in txs:
            f.write(json.dumps(tx_to_dict(t)) + "\n")
    print(f"Wrote {len(txs)} transactions to {args.out} (seed={args.seed})")


if __name__ == "__main__":
    main()
