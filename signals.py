"""Signal definitions for multi-signal scoring."""


SEVERITY_PENALTIES = {
    "critical": 0.4,
    "potential_issue": 0.2,
    "nitpick": 0.05,
    "documentation": 0.02,
}

CATEGORY_PENALTIES = {
    "security": 0.35,
    "bug": 0.3,
    "error_handling": 0.15,
    "performance": 0.1,
    "style": 0.03,
    "documentation": 0.02,
}


def score_quality(findings: list[dict]) -> float:
    """Score code quality from CodeRabbit findings. 1.0 = no issues, 0.0 = severe issues."""
    if not findings:
        return 1.0

    total_penalty = 0.0
    for f in findings:
        finding_type = f.get("type", "nitpick").lower()
        penalty = SEVERITY_PENALTIES.get(finding_type, 0.05)

        # Boost penalty for security/bug categories
        comment = f.get("comment", "").lower()
        for cat, cat_penalty in CATEGORY_PENALTIES.items():
            if cat in comment:
                penalty = max(penalty, cat_penalty)
                break

        total_penalty += penalty

    return max(0.0, 1.0 - total_penalty)


def score_complexity(findings: list[dict], lines_added: int, lines_removed: int) -> float:
    """Score complexity change. Rewards simplification, penalizes bloat."""
    complexity_findings = [f for f in findings if "complex" in f.get("comment", "").lower()
                          or "duplicate" in f.get("comment", "").lower()
                          or "extract" in f.get("comment", "").lower()]

    base = 1.0

    # Penalize complexity findings
    base -= len(complexity_findings) * 0.1

    # Reward net line reduction (simpler code)
    net_change = lines_added - lines_removed
    if net_change < 0:
        base += min(0.1, abs(net_change) * 0.002)  # bonus for removing lines
    elif net_change > 50:
        base -= min(0.2, net_change * 0.002)  # penalty for adding lots of lines

    return max(0.0, min(1.0, base))


def composite_score(functional: float, quality: float, complexity: float,
                    weights: tuple[float, float, float] = (0.6, 0.25, 0.15)) -> float:
    """Compute weighted composite score from all signals."""
    fw, qw, cw = weights
    return functional * fw + quality * qw + complexity * cw
