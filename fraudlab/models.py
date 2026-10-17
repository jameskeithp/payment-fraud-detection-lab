"""Core data models: transactions and rule findings."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class GeoPoint:
    """A geographic location as latitude/longitude in decimal degrees."""

    lat: float
    lon: float
    label: str = ""


@dataclass(frozen=True)
class Transaction:
    """A single cross-border money transfer."""

    tx_id: str
    sender_id: str
    amount: float
    currency: str
    timestamp: datetime
    geo: GeoPoint
    device_id: str
    payee_id: str


@dataclass(frozen=True)
class Finding:
    """One rule's verdict on a transaction."""

    rule: str
    severity: str  # low | medium | high | critical
    reason_code: str
    detail: str
    score_weight: float = field(default=0.0)
