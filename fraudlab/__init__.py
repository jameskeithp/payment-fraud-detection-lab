"""payment-fraud-detection-lab: a detection engineering lab for payments fraud.

A portfolio project demonstrating transaction fraud detection:
pluggable rules, risk scoring, and a synthetic transaction generator.
"""

__version__ = "0.1.0"

from fraudlab.models import Finding, Transaction
from fraudlab.engine import FraudEngine, ScoreResult

__all__ = ["Finding", "Transaction", "FraudEngine", "ScoreResult", "__version__"]
