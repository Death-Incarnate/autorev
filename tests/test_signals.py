"""Tests for the multi-signal scoring engine."""

import sys
sys.path.insert(0, "..")

from signals import score_quality, score_complexity, composite_score


def test_quality_no_findings():
    assert score_quality([]) == 1.0


def test_quality_nitpick():
    findings = [{"type": "nitpick", "comment": "Consider renaming variable"}]
    score = score_quality(findings)
    assert 0.9 <= score <= 1.0


def test_quality_potential_issue():
    findings = [{"type": "potential_issue", "comment": "Possible null reference"}]
    score = score_quality(findings)
    assert 0.7 <= score < 0.9


def test_quality_critical():
    findings = [{"type": "critical", "comment": "SQL injection vulnerability"}]
    score = score_quality(findings)
    assert score < 0.7


def test_quality_security_boost():
    findings = [{"type": "nitpick", "comment": "security: missing input validation"}]
    score = score_quality(findings)
    # Security keyword should boost the penalty beyond a normal nitpick
    assert score < 0.7


def test_quality_multiple_findings():
    findings = [
        {"type": "nitpick", "comment": "style issue"},
        {"type": "potential_issue", "comment": "error handling"},
        {"type": "nitpick", "comment": "naming"},
    ]
    score = score_quality(findings)
    assert 0.5 <= score < 0.85


def test_complexity_no_findings():
    assert score_complexity([], 10, 10) == 1.0


def test_complexity_net_removal():
    score = score_complexity([], 5, 20)
    assert score > 1.0 - 0.01  # bonus for removing lines


def test_complexity_bloat():
    score = score_complexity([], 100, 5)
    assert score < 1.0  # penalty for adding lots


def test_complexity_duplication_finding():
    findings = [{"comment": "Consider extracting duplicate logic"}]
    score = score_complexity(findings, 10, 10)
    assert score < 1.0


def test_composite_all_perfect():
    score = composite_score(1.0, 1.0, 1.0)
    assert score == 1.0


def test_composite_weights():
    # Functional dominates
    score = composite_score(1.0, 0.0, 0.0, (0.6, 0.25, 0.15))
    assert abs(score - 0.6) < 0.001


def test_composite_quality_penalty():
    # Good functional, bad quality
    score_good = composite_score(0.9, 0.9, 0.9)
    score_bad_quality = composite_score(0.9, 0.3, 0.9)
    assert score_good > score_bad_quality


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
