"""LLM agent — proposes code changes to improve the target project."""

import json
import subprocess
import os
from pathlib import Path


def propose_change(target_dir: str, config: dict, history: list[dict]) -> str | None:
    """Ask the LLM to propose a code improvement. Returns the proposed change description."""
    provider = config["provider"]
    api_key = config["api_key"]
    model = config["model"]

    if not api_key:
        print(f"  No API key for {provider}")
        return None

    # Build context: current code state + history of past rounds
    context = _build_context(target_dir, history)

    prompt = f"""You are an expert software engineer improving a codebase iteratively.

PROJECT DIRECTORY: {target_dir}

CURRENT CODE STATE:
{context}

PAST ROUNDS (most recent first):
{_format_history(history[-5:])}

YOUR TASK:
Propose ONE focused improvement to the codebase. This could be:
- Fixing a bug
- Improving error handling
- Reducing code duplication
- Improving performance
- Making code more readable
- Adding missing validation

RULES:
- Make ONE change, not multiple unrelated changes
- The change must be small and focused (under 50 lines changed)
- Do NOT add comments explaining what the code does
- Do NOT add type hints to existing code unless fixing a bug
- Do NOT refactor working code just for style
- Focus on changes that improve functionality, security, or correctness

OUTPUT FORMAT:
Return a JSON object with:
- "description": one-line summary of the change
- "files": list of objects with "path" (relative to project root), "action" ("edit" or "create"), and "content" (full new file content for create, or "search" and "replace" strings for edit)

Example:
{{"description": "Fix potential KeyError in config parsing", "files": [{{"path": "config.py", "action": "edit", "search": "data['key']", "replace": "data.get('key', default)"}}]}}

Return ONLY the JSON object, no markdown, no explanation."""

    response = _call_llm(provider, api_key, model, prompt)
    return response


def apply_change(target_dir: str, change_json: str) -> bool:
    """Parse and apply the proposed change to the codebase."""
    try:
        change = json.loads(change_json)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        import re
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', change_json, re.DOTALL)
        if match:
            try:
                change = json.loads(match.group(1))
            except json.JSONDecodeError:
                print("  Failed to parse change JSON")
                return False
        else:
            # Try to find raw JSON
            match = re.search(r'\{[^{}]*"description"[^{}]*"files"[^{}]*\[.*?\]\s*\}', change_json, re.DOTALL)
            if match:
                try:
                    change = json.loads(match.group(0))
                except json.JSONDecodeError:
                    print("  Failed to parse change JSON")
                    return False
            else:
                print("  Failed to parse change JSON")
                return False

    files = change.get("files", [])
    if not files:
        print("  No file changes proposed")
        return False

    description = change.get("description", "unnamed change")
    print(f"  Applying: {description}")

    for f in files:
        filepath = Path(target_dir) / f["path"]
        action = f.get("action", "edit")

        if action == "create":
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(f["content"])
            print(f"    Created: {f['path']}")

        elif action == "edit":
            if not filepath.exists():
                print(f"    Skip (not found): {f['path']}")
                continue
            content = filepath.read_text()
            search = f.get("search", "")
            replace = f.get("replace", "")
            if search and search in content:
                content = content.replace(search, replace, 1)
                filepath.write_text(content)
                print(f"    Edited: {f['path']}")
            else:
                print(f"    Skip (search string not found): {f['path']}")
                return False

    # Git commit the change
    subprocess.run(["git", "add", "-A"], cwd=target_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"autorev: {description}"],
        cwd=target_dir, capture_output=True
    )
    return True


def revert_change(target_dir: str):
    """Revert the last commit."""
    subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=target_dir, capture_output=True)


def _build_context(target_dir: str, history: list[dict]) -> str:
    """Build a context string from the project files."""
    context_parts = []
    target = Path(target_dir)

    # Get tracked files
    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=target_dir
    )
    files = result.stdout.strip().splitlines()

    # Include small source files
    total_chars = 0
    max_chars = 30000  # context budget
    for f in sorted(files):
        fp = target / f
        if not fp.exists() or fp.is_dir():
            continue
        if fp.suffix not in (".py", ".js", ".ts", ".tsx", ".rs", ".go", ".java", ".rb", ".sh"):
            continue
        try:
            content = fp.read_text()
            if total_chars + len(content) > max_chars:
                continue
            context_parts.append(f"--- {f} ---\n{content}")
            total_chars += len(content)
        except Exception:
            continue

    return "\n\n".join(context_parts) if context_parts else "(no source files found)"


def _format_history(history: list[dict]) -> str:
    """Format recent history for the prompt."""
    if not history:
        return "(no previous rounds)"
    lines = []
    for h in reversed(history):
        status = "KEPT" if h.get("kept") else "REVERTED"
        lines.append(f"Round {h['round']}: [{status}] {h.get('description', '?')} "
                      f"(composite={h.get('composite', '?')}, "
                      f"functional={h.get('functional', '?')}, "
                      f"quality={h.get('quality', '?')})")
    return "\n".join(lines)


def _call_llm(provider: str, api_key: str, model: str, prompt: str) -> str | None:
    """Call the LLM provider and return the response text."""
    endpoints = {
        "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
        "cerebras": "https://api.cerebras.ai/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "anthropic": "https://api.anthropic.com/v1/messages",
    }

    endpoint = endpoints.get(provider)
    if not endpoint:
        print(f"  Unknown provider: {provider}")
        return None

    if provider == "anthropic":
        return _call_anthropic(api_key, model, prompt)

    import urllib.request
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/Death-Incarnate/autorev"

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.7,
    }).encode()

    req = urllib.request.Request(endpoint, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  LLM call failed: {e}")
        return None


def _call_anthropic(api_key: str, model: str, prompt: str) -> str | None:
    """Call Anthropic API (different format)."""
    import urllib.request
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = json.dumps({
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"]
    except Exception as e:
        print(f"  Anthropic call failed: {e}")
        return None
