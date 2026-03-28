"""CodeRabbit CLI integration — runs review and parses structured output."""

import json
import subprocess
import re
import time
from pathlib import Path


# Free tier: 3 reviews/hour. Track usage to avoid rate limits.
_last_review_times: list[float] = []
REVIEWS_PER_HOUR = 3


def _ensure_main_branch(target_dir: str):
    """Ensure a 'main' branch exists — CodeRabbit requires it."""
    result = subprocess.run(
        ["git", "branch", "--list", "main"],
        capture_output=True, text=True, cwd=target_dir
    )
    if not result.stdout.strip():
        current = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=target_dir
        ).stdout.strip()
        if current and current != "main":
            subprocess.run(
                ["git", "branch", "main", current],
                capture_output=True, cwd=target_dir
            )


def _wait_for_rate_limit():
    """Wait if we're about to exceed the free tier rate limit."""
    now = time.time()
    hour_ago = now - 3600
    _last_review_times[:] = [t for t in _last_review_times if t > hour_ago]

    if len(_last_review_times) >= REVIEWS_PER_HOUR:
        oldest = _last_review_times[0]
        wait_seconds = int(oldest + 3600 - now) + 10  # 10s buffer
        if wait_seconds > 0:
            print(f"    Rate limit: waiting {wait_seconds}s ({REVIEWS_PER_HOUR}/hour free tier)")
            time.sleep(wait_seconds)
            _last_review_times.clear()


def create_strict_config(target_dir: str) -> str | None:
    """Create a .coderabbit.yaml with assertive profile if none exists."""
    config_path = Path(target_dir) / ".coderabbit.yaml"
    if config_path.exists():
        return None

    config = """language: "en-US"
reviews:
  profile: "assertive"
  high_level_summary: false
  poem: false
  sequence_diagrams: false
  slop_detection:
    enabled: true
  path_instructions:
    - path: "**/*.py"
      instructions: |
        - Flag unclosed file handles (use context managers)
        - Flag bare except clauses
        - Flag == True / == False comparisons (use truthiness)
        - Flag range(len(x)) patterns (use enumerate)
        - Flag string concatenation in loops (use f-strings or join)
        - Flag missing error handling on I/O operations
        - Flag potential division by zero
        - Flag unused imports
        - Flag mutable default arguments
    - path: "**/*.{js,ts,tsx}"
      instructions: |
        - Flag missing error boundaries
        - Flag any type usage
        - Flag missing null checks
        - Flag console.log left in production code
    - path: "**/*.{go,rs}"
      instructions: |
        - Flag unchecked error returns
        - Flag unwrap() without context
"""
    config_path.write_text(config)
    return str(config_path)


def run_review(target_dir: str, base_commit: str = "HEAD~1",
               config_files: list[str] | None = None) -> dict:
    """Run CodeRabbit review and return parsed findings."""
    _ensure_main_branch(target_dir)
    _wait_for_rate_limit()

    # Create strict config if none exists
    created_config = create_strict_config(target_dir)

    cmd = ["coderabbit", "review", "--base-commit", base_commit,
           "--prompt-only", "--no-color", "--cwd", target_dir]

    # Add custom config files
    if config_files:
        cmd.extend(["--config"] + config_files)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, cwd=target_dir
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return {"findings": [], "raw": "CodeRabbit timeout (600s)", "error": True}
    except FileNotFoundError:
        return {"findings": [], "raw": "CodeRabbit CLI not installed", "error": True}

    _last_review_times.append(time.time())

    # Check for rate limiting
    if "Rate limit exceeded" in output:
        # Parse wait time
        wait_match = re.search(r"after (\d+) minutes", output)
        if wait_match:
            wait_min = int(wait_match.group(1))
            print(f"    Rate limited — waiting {wait_min + 1} minutes")
            time.sleep((wait_min + 1) * 60)
            # Retry once
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600, cwd=target_dir
                )
                output = result.stdout + result.stderr
            except Exception:
                pass
        if "Rate limit exceeded" in output:
            return {"findings": [], "raw": output, "error": True, "rate_limited": True}

    findings = parse_findings(output)

    # Clean up created config (don't leave autorev artifacts in target)
    if created_config:
        Path(created_config).unlink(missing_ok=True)
        # Unstage if git tracked it
        subprocess.run(["git", "checkout", "--", ".coderabbit.yaml"],
                       capture_output=True, cwd=target_dir)

    return {"findings": findings, "raw": output, "error": False}


def parse_findings(output: str) -> list[dict]:
    """Parse CodeRabbit --prompt-only output into structured findings.

    prompt-only output uses ============= (13 equals) as block delimiters.
    plain output uses 76 equals. We handle both.
    """
    findings = []

    # Try both delimiter formats
    if "=============" in output:
        # Split on runs of 5+ equals signs
        blocks = re.split(r'={5,}', output)
    else:
        return findings

    for block in blocks:
        block = block.strip()
        if not block or "REVIEW ERROR" in block or "Review completed" in block:
            continue
        if "Starting CodeRabbit" in block or "Connecting to" in block:
            continue

        finding = {}

        # Parse file
        file_match = re.search(r"File:\s*(.+)", block)
        if file_match:
            finding["file"] = file_match.group(1).strip()

        # Parse line range (both "Line: X to Y" and "Line: X")
        line_match = re.search(r"Line:\s*(\d+)\s*(?:to\s*(\d+))?", block)
        if line_match:
            finding["line_start"] = int(line_match.group(1))
            finding["line_end"] = int(line_match.group(2)) if line_match.group(2) else finding["line_start"]

        # Parse type/severity
        type_match = re.search(r"(?:Type|Severity):\s*(.+)", block)
        if type_match:
            finding["type"] = type_match.group(1).strip()

        # Parse comment/description
        comment_match = re.search(
            r"(?:Comment|Description|Issue):\s*\n?(.+?)(?:\n\n|\nPrompt for AI Agent:|\nSuggested fix:|\Z)",
            block, re.DOTALL
        )
        if comment_match:
            finding["comment"] = comment_match.group(1).strip()
        elif not finding.get("comment"):
            # Fallback: if we got a file but no structured comment, use the whole block
            # minus any known headers
            text = block
            for header in ["File:", "Line:", "Type:", "Severity:", "Prompt for AI Agent:"]:
                idx = text.find(header)
                if idx >= 0:
                    # Remove the header line
                    end = text.find("\n", idx)
                    if end > 0:
                        text = text[:idx] + text[end+1:]
            text = text.strip()
            if text and len(text) > 10:
                finding["comment"] = text

        if finding.get("file") or finding.get("comment"):
            findings.append(finding)

    return findings


def count_by_type(findings: list[dict]) -> dict[str, int]:
    """Count findings by type."""
    counts = {}
    for f in findings:
        t = f.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


def get_diff_stats(target_dir: str, base_commit: str = "HEAD~1") -> tuple[int, int]:
    """Get lines added/removed since base commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--numstat", base_commit, "HEAD"],
            capture_output=True, text=True, cwd=target_dir
        )
        added = 0
        removed = 0
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0] != "-":
                added += int(parts[0])
                removed += int(parts[1])
        return added, removed
    except Exception:
        return 0, 0
