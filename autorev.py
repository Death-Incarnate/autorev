#!/usr/bin/env python3
"""autorev — Multi-signal code evolution with CodeRabbit quality gates.

Combines Karpathy's autoresearch pattern with CodeRabbit AI code review
to iteratively improve codebases using functional AND quality scoring.

Usage:
    python autorev.py --target ./my-project --rounds 10
    python autorev.py --target ./my-project --score-only
    python autorev.py --target ./my-project --evaluate "python evaluate.py"
    python autorev.py --target ./my-project --weights 0.6,0.25,0.15
    python autorev.py --target ./my-project --provider nvidia --model meta/llama-3.1-70b-instruct
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from config import load_config
from evaluate import evaluate
from agent import propose_change, apply_change, revert_change


def parse_args():
    p = argparse.ArgumentParser(description="autorev — multi-signal code evolution")
    p.add_argument("--target", "-t", default=".", help="Target project directory")
    p.add_argument("--rounds", "-r", type=int, default=10, help="Number of improvement rounds")
    p.add_argument("--weights", "-w", default=None, help="Signal weights: functional,quality,complexity (e.g. 0.6,0.25,0.15)")
    p.add_argument("--dry-run", action="store_true", help="Show proposed changes without applying")
    p.add_argument("--score-only", action="store_true", help="Score current state and exit")
    p.add_argument("--evaluate", "-e", default=None, help="Custom evaluation command (should print float score)")
    p.add_argument("--provider", "-p", default=None, help="LLM provider: nvidia, cerebras, openrouter, anthropic")
    p.add_argument("--model", "-m", default=None, help="LLM model override")
    p.add_argument("--log", default=None, help="Log file path (default: autorev-log.json in target dir)")
    return p.parse_args()


def print_banner():
    print()
    print("  autorev — multi-signal code evolution")
    print("  CodeRabbit + autoresearch pattern")
    print("  ─────────────────────────────────────")
    print()


def print_score(result: dict, round_num: int | None = None):
    prefix = f"  Round {round_num}" if round_num is not None else "  Current"
    print(f"{prefix} scores:")
    print(f"    Composite:  {result['composite']:.4f}  (weights: {result['weights']})")
    print(f"    Functional: {result['functional']:.4f}  (weight: {result['weights'][0]})")
    print(f"    Quality:    {result['quality']:.4f}  (weight: {result['weights'][1]})")
    print(f"    Complexity: {result['complexity']:.4f}  (weight: {result['weights'][2]})")
    print(f"    Findings:   {result['findings_count']} ({result['findings_by_type']})")
    print(f"    Diff:       +{result['lines_added']} -{result['lines_removed']}")
    print()


def load_history(log_path: Path) -> list[dict]:
    if log_path.exists():
        try:
            return json.loads(log_path.read_text())
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def save_history(log_path: Path, history: list[dict]):
    log_path.write_text(json.dumps(history, indent=2))


def run_score_only(config: dict):
    """Score the current state without making changes."""
    target = os.path.abspath(config["target"])
    print(f"  Target: {target}")
    print(f"  Mode: score-only")
    print()

    result = evaluate(target, config["evaluate_cmd"], "HEAD~1", config["weights"])
    print_score(result)
    return result


def run_loop(config: dict):
    """Run the autoresearch loop with multi-signal scoring."""
    target = os.path.abspath(config["target"])
    rounds = config["rounds"]
    weights = config["weights"]

    log_path = Path(config.get("log") or os.path.join(target, "autorev-log.json"))
    history = load_history(log_path)

    print(f"  Target:   {target}")
    print(f"  Rounds:   {rounds}")
    print(f"  Weights:  functional={weights[0]}, quality={weights[1]}, complexity={weights[2]}")
    print(f"  Provider: {config['provider']} ({config['model']})")
    print(f"  Log:      {log_path}")
    print(f"  History:  {len(history)} previous rounds")
    print()

    # Baseline: ensure repo has an empty root commit for diffing, then score full codebase
    print("  Scoring baseline...")
    import subprocess as _sp

    # Check commit count
    commit_count = _sp.run(["git", "rev-list", "--count", "HEAD"],
                           capture_output=True, text=True, cwd=target)
    count = int(commit_count.stdout.strip()) if commit_count.stdout.strip() else 0

    if count <= 1:
        # Only 1 commit — create an empty root so we can diff the full codebase
        # Use git rebase to insert an empty commit at the beginning
        _sp.run(["git", "stash"], capture_output=True, cwd=target)
        root_hash = _sp.run(
            ["git", "commit-tree", "-m", "autorev: empty root",
             _sp.run(["git", "hash-object", "-t", "tree", "/dev/null"],
                     capture_output=True, text=True).stdout.strip()],
            capture_output=True, text=True, cwd=target
        ).stdout.strip()
        if root_hash:
            _sp.run(["git", "rebase", "--onto", root_hash, "--root"],
                    capture_output=True, cwd=target)
        _sp.run(["git", "stash", "pop"], capture_output=True, cwd=target)

    # Find root commit
    root_result = _sp.run(["git", "rev-list", "--max-parents=0", "HEAD"],
                          capture_output=True, text=True, cwd=target)
    root_commit = root_result.stdout.strip().splitlines()[0] if root_result.stdout.strip() else "HEAD~1"

    baseline = evaluate(target, config["evaluate_cmd"], root_commit, config["weights"])
    print_score(baseline)
    best_composite = baseline["composite"]

    for round_num in range(1, rounds + 1):
        print(f"  ── Round {round_num}/{rounds} ──")
        start_time = time.time()

        # Step 1: Propose a change
        print("  Proposing change...")
        change = propose_change(target, config, history)
        if not change:
            print("  No change proposed, skipping round")
            continue

        if config["dry_run"]:
            print(f"  [dry-run] Would apply: {change[:200]}...")
            continue

        # Step 2: Apply the change
        if not apply_change(target, change):
            print("  Failed to apply change, skipping round")
            continue

        # Step 3: Evaluate
        print("  Evaluating...")
        result = evaluate(target, config["evaluate_cmd"], "HEAD~1", weights)
        print_score(result, round_num)

        # Step 4: Keep or revert
        description = "unknown"
        try:
            parsed = json.loads(change)
            description = parsed.get("description", "unknown")
        except (json.JSONDecodeError, AttributeError):
            import re
            match = re.search(r'"description"\s*:\s*"([^"]+)"', change)
            if match:
                description = match.group(1)

        elapsed = round(time.time() - start_time, 1)

        round_entry = {
            "round": len(history) + 1,
            "timestamp": datetime.now().isoformat(),
            "description": description,
            "composite": result["composite"],
            "functional": result["functional"],
            "quality": result["quality"],
            "complexity": result["complexity"],
            "findings_count": result["findings_count"],
            "findings_by_type": result["findings_by_type"],
            "lines_added": result["lines_added"],
            "lines_removed": result["lines_removed"],
            "elapsed_seconds": elapsed,
            "kept": False,
        }

        if result["composite"] > best_composite:
            print(f"  KEPT — composite {best_composite:.4f} → {result['composite']:.4f} (+{result['composite'] - best_composite:.4f})")
            best_composite = result["composite"]
            round_entry["kept"] = True
        else:
            print(f"  REVERTED — composite {result['composite']:.4f} <= {best_composite:.4f}")
            revert_change(target)

        history.append(round_entry)
        save_history(log_path, history)
        print()

    # Summary
    kept = sum(1 for h in history[-rounds:] if h.get("kept"))
    print("  ── Summary ──")
    print(f"  Rounds: {rounds}, Kept: {kept}, Reverted: {rounds - kept}")
    print(f"  Best composite: {best_composite:.4f}")

    if history:
        print(f"\n  Score progression:")
        for h in history[-rounds:]:
            status = "KEPT" if h["kept"] else "REV "
            print(f"    R{h['round']:3d} [{status}] {h['composite']:.4f} | "
                  f"F={h['functional']:.3f} Q={h['quality']:.3f} C={h['complexity']:.3f} | "
                  f"{h['description'][:60]}")

    print()
    return history


def main():
    print_banner()
    args = parse_args()
    config = load_config(args)

    if config["score_only"]:
        run_score_only(config)
    else:
        run_loop(config)


if __name__ == "__main__":
    main()
