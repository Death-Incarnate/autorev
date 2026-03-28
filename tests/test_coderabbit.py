"""Tests for CodeRabbit output parsing."""

import sys
sys.path.insert(0, "..")

from coderabbit import parse_findings, count_by_type


SAMPLE_OUTPUT = """
============================================================================
File: x.py
Line: 557 to 572
Type: nitpick

Comment:
Consider extracting shared tweet-parsing logic.

The instruction/entry parsing in cmd_bookmarks duplicates the pattern.

Prompt for AI Agent:
Fix the duplication.

============================================================================
File: notify.py
Line: 51 to 64
Type: potential_issue

Comment:
Potential KeyError when auto-detecting chat_id.

The code assumes data["result"][-1]["message"]["chat"]["id"] exists.

Prompt for AI Agent:
Add safe access.

============================================================================
File: Root.tsx
Line: 1 to 5
Type: potential_issue

Comment:
Missing React import for type annotation.

Prompt for AI Agent:
Add import.
"""


def test_parse_findings_count():
    findings = parse_findings(SAMPLE_OUTPUT)
    assert len(findings) == 3


def test_parse_findings_types():
    findings = parse_findings(SAMPLE_OUTPUT)
    types = [f["type"] for f in findings]
    assert types == ["nitpick", "potential_issue", "potential_issue"]


def test_parse_findings_files():
    findings = parse_findings(SAMPLE_OUTPUT)
    files = [f["file"] for f in findings]
    assert files == ["x.py", "notify.py", "Root.tsx"]


def test_parse_findings_lines():
    findings = parse_findings(SAMPLE_OUTPUT)
    assert findings[0]["line_start"] == 557
    assert findings[0]["line_end"] == 572


def test_parse_findings_comment():
    findings = parse_findings(SAMPLE_OUTPUT)
    assert "tweet-parsing" in findings[0]["comment"]
    assert "KeyError" in findings[1]["comment"]


def test_count_by_type():
    findings = parse_findings(SAMPLE_OUTPUT)
    counts = count_by_type(findings)
    assert counts == {"nitpick": 1, "potential_issue": 2}


def test_parse_empty():
    findings = parse_findings("")
    assert findings == []


def test_parse_error_output():
    findings = parse_findings("REVIEW ERROR: something broke")
    assert findings == []


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
