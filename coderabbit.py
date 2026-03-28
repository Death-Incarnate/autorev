"""CodeRabbit CLI integration — runs review and parses structured output."""

import json
import subprocess
import re


def run_review(target_dir: str, base_commit: str = "HEAD~1") -> dict:
    """Run CodeRabbit review and return parsed findings."""
    try:
        result = subprocess.run(
            ["coderabbit", "review", "--base-commit", base_commit,
             "--agent", "--plain", "--cwd", target_dir, "--no-color"],
            capture_output=True, text=True, timeout=120, cwd=target_dir
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return {"findings": [], "raw": "CodeRabbit timeout (120s)", "error": True}
    except FileNotFoundError:
        return {"findings": [], "raw": "CodeRabbit CLI not installed", "error": True}

    findings = parse_findings(output)
    return {"findings": findings, "raw": output, "error": False}


def parse_findings(output: str) -> list[dict]:
    """Parse CodeRabbit plain text output into structured findings."""
    findings = []
    blocks = output.split("=" * 76)

    for block in blocks:
        block = block.strip()
        if not block or "REVIEW ERROR" in block:
            continue

        finding = {}

        # Parse file
        file_match = re.search(r"File:\s*(.+)", block)
        if file_match:
            finding["file"] = file_match.group(1).strip()

        # Parse line range
        line_match = re.search(r"Line:\s*(\d+)\s*to\s*(\d+)", block)
        if line_match:
            finding["line_start"] = int(line_match.group(1))
            finding["line_end"] = int(line_match.group(2))

        # Parse type
        type_match = re.search(r"Type:\s*(.+)", block)
        if type_match:
            finding["type"] = type_match.group(1).strip()

        # Parse comment
        comment_match = re.search(r"Comment:\s*\n(.+?)(?:\n\n|\nPrompt for AI Agent:)", block, re.DOTALL)
        if comment_match:
            finding["comment"] = comment_match.group(1).strip()
        elif "Comment:" in block:
            # Fallback: grab everything after Comment:
            idx = block.index("Comment:") + len("Comment:")
            rest = block[idx:].strip()
            # Cut at "Prompt for AI Agent:" if present
            prompt_idx = rest.find("Prompt for AI Agent:")
            if prompt_idx > 0:
                rest = rest[:prompt_idx]
            finding["comment"] = rest.strip()

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
