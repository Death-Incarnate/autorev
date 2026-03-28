"""Tests for CodeRabbit output parsing."""

import sys
sys.path.insert(0, "..")

from coderabbit import parse_findings, count_by_type


# Plain text format (76 equals)
SAMPLE_PLAIN = """
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

# Prompt-only format (13 equals)
SAMPLE_PROMPT_ONLY = """Starting CodeRabbit review in plain text mode...

Connecting to review service
Setting up
Reviewing

=============
File: app.py
Line: 28
Type: potential_issue

Comment:
Unclosed file handle — use context manager.

Suggested fix:
Use `with open(filename, 'w') as f:` instead.

=============
File: app.py
Line: 45
Type: nitpick

Comment:
Using range(len(users)) — prefer enumerate or direct iteration.

=============
Review completed
"""


def test_parse_plain_count():
    findings = parse_findings(SAMPLE_PLAIN)
    assert len(findings) == 3


def test_parse_plain_types():
    findings = parse_findings(SAMPLE_PLAIN)
    types = [f["type"] for f in findings]
    assert types == ["nitpick", "potential_issue", "potential_issue"]


def test_parse_plain_files():
    findings = parse_findings(SAMPLE_PLAIN)
    files = [f["file"] for f in findings]
    assert files == ["x.py", "notify.py", "Root.tsx"]


def test_parse_plain_lines():
    findings = parse_findings(SAMPLE_PLAIN)
    assert findings[0]["line_start"] == 557
    assert findings[0]["line_end"] == 572


def test_parse_plain_comment():
    findings = parse_findings(SAMPLE_PLAIN)
    assert "tweet-parsing" in findings[0]["comment"]
    assert "KeyError" in findings[1]["comment"]


def test_parse_prompt_only_count():
    findings = parse_findings(SAMPLE_PROMPT_ONLY)
    assert len(findings) == 2


def test_parse_prompt_only_types():
    findings = parse_findings(SAMPLE_PROMPT_ONLY)
    assert findings[0]["type"] == "potential_issue"
    assert findings[1]["type"] == "nitpick"


def test_parse_prompt_only_single_line():
    findings = parse_findings(SAMPLE_PROMPT_ONLY)
    assert findings[0]["line_start"] == 28
    assert findings[0]["line_end"] == 28


def test_parse_prompt_only_comment():
    findings = parse_findings(SAMPLE_PROMPT_ONLY)
    assert "file handle" in findings[0]["comment"].lower() or "context manager" in findings[0]["comment"].lower()
    assert "range(len" in findings[1]["comment"]


def test_count_by_type():
    findings = parse_findings(SAMPLE_PLAIN)
    counts = count_by_type(findings)
    assert counts == {"nitpick": 1, "potential_issue": 2}


def test_parse_empty():
    findings = parse_findings("")
    assert findings == []


def test_parse_error_output():
    findings = parse_findings("REVIEW ERROR: something broke")
    assert findings == []


def test_parse_clean_review():
    findings = parse_findings("Review completed ✓")
    assert findings == []


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
