"""Pluggable fraud detection rules.

Each rule is a small, testable unit: given a transaction and the
customer's history, return findings (possibly empty). Reason codes are
stable strings so downstream systems and tests can key on them.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import timedelta

from fraudlab.models import Finding, Transaction
from fraudlab.state import StateStore

# Nothing on Earth moves faster than this between two card-present
# style transfer origins without it being suspicious. Commercial jets
# cruise near 900 km/h; 1000 km/h leaves margin for error.
MAX_PLAUSIBLE_SPEED_KMH = 1000.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Rule(ABC):
    name: str = "base"
    reason_code: str = "BASE"

    @abstractmethod
    def evaluate(self, tx: Transaction, store: StateStore) -> list[Finding]:
        ...


class VelocityRule(Rule):
    """Flags N or more transactions from one sender within T minutes."""

    name = "velocity"
    reason_code = "VELOCITY_COUNT_EXCEEDED"

    def __init__(self, max_tx: int = 5, window_minutes: int = 10) -> None:
        self.max_tx = max_tx
        self.window = timedelta(minutes=window_minutes)

    def evaluate(self, tx: Transaction, store: StateStore) -> list[Finding]:
        prof = store.profile(tx.sender_id)
        recent = [t for t in prof.transactions if tx.timestamp - t.timestamp <= self.window]
        count = len(recent) + 1  # include the transaction under review
        if count >= self.max_tx:
            return [
                Finding(
                    rule=self.name,
                    severity="high",
                    reason_code=self.reason_code,
                    detail=f"{count} transactions in the last "
                    f"{int(self.window.total_seconds() // 60)} minutes",
                    score_weight=35.0,
                )
            ]
        return []


class ImpossibleTravelRule(Rule):
    """Flags a transaction that implies faster-than-possible travel
    between the sender's last known location and this one."""

    name = "impossible_travel"
    reason_code = "IMPOSSIBLE_TRAVEL"

    def evaluate(self, tx: Transaction, store: StateStore) -> list[Finding]:
        prof = store.profile(tx.sender_id)
        if not prof.transactions:
            return []
        prev = max(prof.transactions, key=lambda t: t.timestamp)
        if tx.timestamp <= prev.timestamp:
            return []
        km = haversine_km(prev.geo.lat, prev.geo.lon, tx.geo.lat, tx.geo.lon)
        hours = (tx.timestamp - prev.timestamp).total_seconds() / 3600.0
        if hours <= 0:
            return []
        speed = km / hours
        if speed > MAX_PLAUSIBLE_SPEED_KMH and km > 100:
            return [
                Finding(
                    rule=self.name,
                    severity="critical",
                    reason_code=self.reason_code,
                    detail=f"{km:.0f} km in {hours:.1f} h implies {speed:.0f} km/h",
                    score_weight=50.0,
                )
            ]
        return []


class NewDeviceRule(Rule):
    """Flags a first-seen device fingerprint for the sender."""

    name = "new_device"
    reason_code = "NEW_DEVICE_FINGERPRINT"

    def evaluate(self, tx: Transaction, store: StateStore) -> list[Finding]:
        prof = store.profile(tx.sender_id)
        if tx.device_id not in prof.devices:
            return [
                Finding(
                    rule=self.name,
                    severity="medium",
                    reason_code=self.reason_code,
                    detail=f"device {tx.device_id} never seen for sender {tx.sender_id}",
                    score_weight=20.0,
                )
            ]
        return []


class AmountAnomalyRule(Rule):
    """Flags amounts far outside the sender's history (z-score)."""

    name = "amount_anomaly"
    reason_code = "AMOUNT_ANOMALY"

    def __init__(self, z_threshold: float = 3.0, min_history: int = 5) -> None:
        self.z_threshold = z_threshold
        self.min_history = min_history

    def evaluate(self, tx: Transaction, store: StateStore) -> list[Finding]:
        prof = store.profile(tx.sender_id)
        amounts = [t.amount for t in prof.transactions]
        if len(amounts) < self.min_history:
            return []
        mean = sum(amounts) / len(amounts)
        var = sum((a - mean) ** 2 for a in amounts) / len(amounts)
        std = math.sqrt(var)
        if std == 0:
            return []
        z = (tx.amount - mean) / std
        if z >= self.z_threshold:
            return [
                Finding(
                    rule=self.name,
                    severity="high",
                    reason_code=self.reason_code,
                    detail=f"amount {tx.amount:.2f} is z={z:.1f} vs history "
                    f"(mean {mean:.2f}, n={len(amounts)})",
                    score_weight=30.0,
                )
            ]
        return []


class PayeeChangeRule(Rule):
    """Flags a transfer to a recently added payee above an amount floor.

    Classic account-takeover pattern: attacker adds a new payee, then
    moves money out before the real owner notices.
    """

    name = "payee_change_then_transfer"
    reason_code = "PAYEE_CHANGE_THEN_TRANSFER"

    def __init__(self, payee_age_hours: int = 24, amount_floor: float = 500.0) -> None:
        self.payee_age = timedelta(hours=payee_age_hours)
        self.amount_floor = amount_floor

    def evaluate(self, tx: Transaction, store: StateStore) -> list[Finding]:
        prof = store.profile(tx.sender_id)
        first_seen = prof.payee_first_seen.get(tx.payee_id)
        if first_seen is None:
            # Brand-new payee on this transaction counts as just added.
            first_seen = tx.timestamp
        age = tx.timestamp - first_seen
        if age <= self.payee_age and tx.amount >= self.amount_floor:
            return [
                Finding(
                    rule=self.name,
                    severity="high",
                    reason_code=self.reason_code,
                    detail=f"payee {tx.payee_id} first seen {age} ago; "
                    f"transfer of {tx.amount:.2f}",
                    score_weight=30.0,
                )
            ]
        return []


DEFAULT_RULES: list[Rule] = [
    VelocityRule(),
    ImpossibleTravelRule(),
    NewDeviceRule(),
    AmountAnomalyRule(),
    PayeeChangeRule(),
]
