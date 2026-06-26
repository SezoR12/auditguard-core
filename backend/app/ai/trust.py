"""Trust Index calculation (0-100): data quality + coverage."""
from __future__ import annotations


def coverage_ratio(certified_count: int, total_count: int) -> float:
    """Fraction of documents that reached 'certified' (human-verified)."""
    if total_count <= 0:
        return 0.0
    return min(1.0, certified_count / total_count)


def trust_index(quality: float, coverage: float, anomaly_count: int, total_docs: int) -> int:
    """Combine data-quality score (0-100), coverage (0-1), and anomaly density.

    trust = 0.6*quality + 0.4*(coverage*100) - anomaly_penalty
    """
    base = 0.6 * quality + 0.4 * (coverage * 100.0)
    penalty = 0.0
    if total_docs > 0:
        penalty = min(20.0, (anomaly_count / total_docs) * 100.0 * 0.5)
    score = base - penalty
    return int(max(0, min(100, round(score))))
