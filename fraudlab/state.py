"""In-memory customer state used by the rules.

The engine keeps a rolling view per sender: past transactions, known
devices, and first-seen timestamps for payees. Rules read from this
store; the engine updates it after every evaluation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fraudlab.models import Transaction


class CustomerProfile:
    def __init__(self) -> None:
        self.transactions: list[Transaction] = []
        self.devices: set[str] = set()
        self.payee_first_seen: dict[str, datetime] = {}


class StateStore:
    def __init__(self) -> None:
        self._profiles: dict[str, CustomerProfile] = defaultdict(CustomerProfile)

    def profile(self, sender_id: str) -> CustomerProfile:
        return self._profiles[sender_id]

    def record(self, tx: Transaction) -> None:
        prof = self.profile(tx.sender_id)
        prof.transactions.append(tx)
        prof.devices.add(tx.device_id)
        prof.payee_first_seen.setdefault(tx.payee_id, tx.timestamp)
