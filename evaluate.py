"""Multi-signal evaluation engine."""

import subprocess
import json
from signals import score_quality, score_complexity, composite_score
from coderabbit import run_review, count_by_type, get_diff_stats


def evaluate(target_dir: str, evaluate_cmd: str | None, base_commit: str,
             weights: tuple[float, float, float]) -> dict:
    """Run full multi-signal evaluation on a code change.

    Returns dict with all scores, findings, and the composite result.
    """
    # Signal 1: Functional score
    functional = run_functional_eval(target_dir, evaluate_cmd)

    # Signal 2 & 3: CodeRabbit review
    cr_result = run_review(target_dir, base_commit)
    findings = cr_result["findings"]
    quality = score_quality(findings)

    # Diff stats for complexity scoring
    lines_added, lines_removed = get_diff_stats(target_dir, base_commit)
    complexity = score_complexity(findings, lines_added, lines_removed)

    # Composite
    total = composite_score(functional, quality, complexity, weights)

    return {
        "composite": round(total, 4),
        "functional": round(functional, 4),
        "quality": round(quality, 4),
        "complexity": round(complexity, 4),
        "weights": weights,
        "findings_count": len(findings),
        "findings_by_type": count_by_type(findings),
        "findings": findings,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "coderabbit_error": cr_result.get("error", False),
    }


def run_functional_eval(target_dir: str, evaluate_cmd: str | None) -> float:
    """Run the user-defined functional evaluation.

    If evaluate_cmd is provided, run it and expect a float on stdout.
    Otherwise, try to run pytest and use pass rate.
    """
    if evaluate_cmd:
        return _run_custom_eval(target_dir, evaluate_cmd)
    return _run_pytest_eval(target_dir)


def _run_custom_eval(target_dir: str, cmd: str) -> float:
    """Run a custom evaluation command. Expects a float score on the last line of stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=300, cwd=target_dir
        )
        lines = result.stdout.strip().splitlines()
        if lines:
            # Try to parse the last line as a float
            try:
                return max(0.0, min(1.0, float(lines[-1])))
            except ValueError:
                pass
            # Try to find a float anywhere in the last line
            import re
            match = re.search(r"(\d+\.?\d*)", lines[-1])
            if match:
                val = float(match.group(1))
                if val > 1.0:
                    val = val / 100.0  # assume percentage
                return max(0.0, min(1.0, val))
        return 0.0
    except subprocess.TimeoutExpired:
        return 0.0
    except Exception:
        return 0.0


def _run_pytest_eval(target_dir: str) -> float:
    """Fallback: run pytest and use pass rate as functional score."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--tb=no", "-q"],
            capture_output=True, text=True, timeout=120, cwd=target_dir
        )
        output = result.stdout
        # Parse "X passed, Y failed" or "X passed"
        import re
        passed = 0
        failed = 0
        match = re.search(r"(\d+) passed", output)
        if match:
            passed = int(match.group(1))
        match = re.search(r"(\d+) failed", output)
        if match:
            failed = int(match.group(1))
        total = passed + failed
        if total == 0:
            return 1.0  # no tests = neutral
        return passed / total
    except Exception:
        return 1.0  # no pytest = neutral
