"""Tests for every fraud rule: true-positive and true-negative cases."""

from datetime import datetime, timedelta

import pytest

from fraudlab.engine import FraudEngine
from fraudlab.models import GeoPoint, Transaction
from fraudlab.rules import (
    AmountAnomalyRule,
    ImpossibleTravelRule,
    NewDeviceRule,
    PayeeChangeRule,
    VelocityRule,
)
from fraudlab.state import StateStore

NYC = GeoPoint(lat=40.7128, lon=-74.0060, label="New York")
LONDON = GeoPoint(lat=51.5074, lon=-0.1278, label="London")
T0 = datetime(2026, 10, 1, 12, 0, 0)


def make_tx(sender="s1", amount=100.0, when=T0, geo=NYC,
            device="dev1", payee="payee1", tx_id="tx1") -> Transaction:
    return Transaction(tx_id=tx_id, sender_id=sender, amount=amount,
                       currency="USD", timestamp=when, geo=geo,
                       device_id=device, payee_id=payee)


def record(store: StateStore, tx: Transaction) -> None:
    store.record(tx)


# ---- Velocity ----

def test_velocity_true_positive():
    rule = VelocityRule(max_tx=5, window_minutes=10)
    store = StateStore()
    for n in range(4):
        record(store, make_tx(tx_id=f"p{n}", when=T0 - timedelta(minutes=9 - n)))
    findings = rule.evaluate(make_tx(tx_id="now", when=T0), store)
    assert len(findings) == 1
    assert findings[0].reason_code == "VELOCITY_COUNT_EXCEEDED"
    assert findings[0].severity == "high"


def test_velocity_true_negative_spread_out():
    rule = VelocityRule(max_tx=5, window_minutes=10)
    store = StateStore()
    for n in range(4):
        record(store, make_tx(tx_id=f"p{n}", when=T0 - timedelta(hours=n + 1)))
    assert rule.evaluate(make_tx(tx_id="now", when=T0), store) == []


def test_velocity_true_negative_below_threshold():
    rule = VelocityRule(max_tx=5, window_minutes=10)
    store = StateStore()
    record(store, make_tx(tx_id="p0", when=T0 - timedelta(minutes=5)))
    assert rule.evaluate(make_tx(tx_id="now", when=T0), store) == []


# ---- Impossible travel ----

def test_impossible_travel_true_positive():
    rule = ImpossibleTravelRule()
    store = StateStore()
    record(store, make_tx(tx_id="p0", when=T0, geo=NYC))
    findings = rule.evaluate(make_tx(tx_id="now", when=T0 + timedelta(minutes=20),
                                     geo=LONDON), store)
    assert len(findings) == 1
    assert findings[0].reason_code == "IMPOSSIBLE_TRAVEL"
    assert findings[0].severity == "critical"


def test_impossible_travel_true_negative_same_city():
    rule = ImpossibleTravelRule()
    store = StateStore()
    record(store, make_tx(tx_id="p0", when=T0, geo=NYC))
    assert rule.evaluate(make_tx(tx_id="now", when=T0 + timedelta(minutes=20),
                                 geo=NYC), store) == []


def test_impossible_travel_true_negative_enough_time():
    rule = ImpossibleTravelRule()
    store = StateStore()
    record(store, make_tx(tx_id="p0", when=T0, geo=NYC))
    assert rule.evaluate(make_tx(tx_id="now", when=T0 + timedelta(hours=12),
                                 geo=LONDON), store) == []


def test_impossible_travel_true_negative_no_history():
    rule = ImpossibleTravelRule()
    assert rule.evaluate(make_tx(tx_id="now", when=T0, geo=LONDON),
                         StateStore()) == []


# ---- New device ----

def test_new_device_true_positive():
    rule = NewDeviceRule()
    store = StateStore()
    record(store, make_tx(tx_id="p0", device="dev1"))
    findings = rule.evaluate(make_tx(tx_id="now", device="dev_NEW"), store)
    assert len(findings) == 1
    assert findings[0].reason_code == "NEW_DEVICE_FINGERPRINT"


def test_new_device_true_negative_known_device():
    rule = NewDeviceRule()
    store = StateStore()
    record(store, make_tx(tx_id="p0", device="dev1"))
    assert rule.evaluate(make_tx(tx_id="now", device="dev1"), store) == []


# ---- Amount anomaly ----

def _history(store: StateStore, amounts, sender="s1"):
    for n, a in enumerate(amounts):
        record(store, make_tx(tx_id=f"h{n}", sender=sender, amount=a,
                              when=T0 - timedelta(days=len(amounts) - n)))


def test_amount_anomaly_true_positive():
    rule = AmountAnomalyRule(z_threshold=3.0, min_history=5)
    store = StateStore()
    _history(store, [95, 105, 100, 98, 102, 101, 99, 103])
    findings = rule.evaluate(make_tx(tx_id="now", amount=5000.0), store)
    assert len(findings) == 1
    assert findings[0].reason_code == "AMOUNT_ANOMALY"


def test_amount_anomaly_true_negative_normal_amount():
    rule = AmountAnomalyRule(z_threshold=3.0, min_history=5)
    store = StateStore()
    _history(store, [95, 105, 100, 98, 102, 101, 99, 103])
    assert rule.evaluate(make_tx(tx_id="now", amount=102.0), store) == []


def test_amount_anomaly_true_negative_too_little_history():
    rule = AmountAnomalyRule(z_threshold=3.0, min_history=5)
    store = StateStore()
    _history(store, [100, 100, 100])
    assert rule.evaluate(make_tx(tx_id="now", amount=5000.0), store) == []


# ---- Payee change then transfer ----

def test_payee_change_true_positive():
    rule = PayeeChangeRule(payee_age_hours=24, amount_floor=500.0)
    store = StateStore()
    record(store, make_tx(tx_id="p0", payee="old_payee", amount=100.0,
                          when=T0 - timedelta(days=10)))
    findings = rule.evaluate(make_tx(tx_id="now", payee="brand_new_payee",
                                     amount=2500.0), store)
    assert len(findings) == 1
    assert findings[0].reason_code == "PAYEE_CHANGE_THEN_TRANSFER"


def test_payee_change_true_negative_old_payee():
    rule = PayeeChangeRule(payee_age_hours=24, amount_floor=500.0)
    store = StateStore()
    record(store, make_tx(tx_id="p0", payee="old_payee", amount=100.0,
                          when=T0 - timedelta(days=10)))
    assert rule.evaluate(make_tx(tx_id="now", payee="old_payee",
                                 amount=2500.0), store) == []


def test_payee_change_true_negative_small_amount():
    rule = PayeeChangeRule(payee_age_hours=24, amount_floor=500.0)
    store = StateStore()
    assert rule.evaluate(make_tx(tx_id="now", payee="brand_new_payee",
                                 amount=50.0), store) == []


# ---- Engine aggregation ----

def test_engine_allow_clean_transaction():
    engine = FraudEngine()
    record(engine.store, make_tx(tx_id="p0", when=T0 - timedelta(days=1)))
    result = engine.evaluate(make_tx(tx_id="now", when=T0, device="dev1",
                                     payee="payee1", amount=100.0))
    assert result.decision == "allow"
    assert result.score < 30


def test_engine_step_up_on_single_high_finding():
    engine = FraudEngine()
    record(engine.store, make_tx(tx_id="p0", when=T0, geo=NYC))
    result = engine.evaluate(make_tx(tx_id="now", when=T0 + timedelta(minutes=20),
                                     geo=LONDON, device="dev1", payee="payee1"))
    codes = {f.reason_code for f in result.findings}
    assert "IMPOSSIBLE_TRAVEL" in codes
    assert result.decision == "step_up_auth"


def test_engine_block_on_stacked_findings():
    engine = FraudEngine()
    record(engine.store, make_tx(tx_id="p0", when=T0, geo=NYC))
    # Impossible travel (50) + new device (20) = 70 -> block.
    result = engine.evaluate(make_tx(tx_id="now", when=T0 + timedelta(minutes=20),
                                     geo=LONDON, device="dev_NEW",
                                     payee="payee1", amount=100.0))
    assert result.score >= 70
    assert result.decision == "block"


def test_engine_score_is_capped_at_100():
    engine = FraudEngine()
    result = engine.evaluate(make_tx(tx_id="now"))
    assert 0 <= result.score <= 100


def test_engine_records_transaction_after_evaluation():
    engine = FraudEngine()
    tx = make_tx(tx_id="now")
    engine.evaluate(tx)
    assert engine.store.profile("s1").transactions[-1].tx_id == "now"


def test_rules_are_pluggable():
    engine = FraudEngine(rules=[NewDeviceRule()])
    result = engine.evaluate(make_tx(tx_id="now", device="dev_NEW"))
    assert [f.rule for f in result.findings] == ["new_device"]
