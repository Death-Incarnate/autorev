# autorev

Multi-signal code evolution. Combines [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) pattern with [CodeRabbit](https://coderabbit.ai) AI code review to iteratively improve codebases.

The agent proposes changes, scores them on **functionality AND code quality**, and keeps only improvements. Your code gets better every round — and stays clean.

## How it works

```
┌─────────────────────────────────────────────────┐
│                  autorev loop                   │
│                                                 │
│   propose change (LLM)                          │
│        │                                        │
│        ▼                                        │
│   apply change (git commit)                     │
│        │                                        │
│        ├──→ functional eval (tests/custom)       │
│        ├──→ coderabbit review (quality)          │
│        └──→ complexity analysis (diff stats)     │
│        │                                        │
│        ▼                                        │
│   composite score = weighted(F, Q, C)           │
│        │                                        │
│        ├── better? → KEEP                       │
│        └── worse?  → REVERT (git reset)         │
│                                                 │
│   repeat for N rounds                           │
└─────────────────────────────────────────────────┘
```

## Why multi-signal?

Autoresearch alone optimizes for one metric. That leads to code that works but rots — spaghetti that passes tests. Adding quality scoring means evolved code stays maintainable, secure, and clean.

| Signal | Weight | What it measures |
|--------|--------|-----------------|
| Functional | 0.60 | Does it work? (tests, custom eval) |
| Quality | 0.25 | Is it clean? (CodeRabbit findings) |
| Complexity | 0.15 | Is it simple? (diff stats, duplication) |

## Quick start

```bash
# 1. Clone
git clone https://github.com/Death-Incarnate/autorev.git
cd autorev

# 2. Configure
cp .env.example .env
# Add your API key for at least one provider (NVIDIA free tier works)

# 3. Install CodeRabbit CLI
npm install -g coderabbit
coderabbit auth login

# 4. Run
python3 autorev.py --target /path/to/your/project --rounds 10
```

## Usage

```bash
# Run 10 improvement rounds
python3 autorev.py --target ./my-project --rounds 10

# Score current state without changes
python3 autorev.py --target ./my-project --score-only

# Custom evaluation command (must print a float 0.0-1.0)
python3 autorev.py --target ./my-project --evaluate "python evaluate.py"

# Custom signal weights
python3 autorev.py --target ./my-project --weights 0.5,0.3,0.2

# Use a specific LLM provider
python3 autorev.py --target ./my-project --provider nvidia --model meta/llama-3.1-70b-instruct

# Dry run (show proposals without applying)
python3 autorev.py --target ./my-project --dry-run
```

## Supported LLM providers

| Provider | Free tier | Env var |
|----------|----------|---------|
| NVIDIA NIM | 5000 credits, 40 RPM | `NVIDIA_API_KEY` |
| Cerebras | Free tier available | `CEREBRAS_API_KEY` |
| OpenRouter | Pay-per-use | `OPENROUTER_API_KEY` |
| Anthropic | Pay-per-use | `ANTHROPIC_API_KEY` |

Set `AUTOREV_PROVIDER` in `.env` to your preferred provider.

## History log

Every round is logged to `autorev-log.json` in the target directory:

```json
{
  "round": 1,
  "timestamp": "2026-03-28T00:30:00",
  "description": "Fix potential KeyError in config parsing",
  "composite": 0.8750,
  "functional": 0.9000,
  "quality": 0.8500,
  "complexity": 0.9000,
  "findings_count": 2,
  "kept": true
}
```

Use this data to analyze which types of changes improve your codebase most, and to tune weights for future runs.

## Requirements

- Python 3.11+
- Git
- [CodeRabbit CLI](https://docs.coderabbit.ai/cli) (`npm install -g coderabbit`)
- API key for at least one LLM provider

## How it compares

| Tool | Functional scoring | Quality scoring | Auto-revert | Multi-provider |
|------|-------------------|-----------------|-------------|----------------|
| autoresearch | Yes | No | Yes | Yes |
| **autorev** | **Yes** | **Yes (CodeRabbit)** | **Yes** | **Yes** |

## License

MIT
