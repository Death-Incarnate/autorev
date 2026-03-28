"""Configuration loading for autorev."""

import os
from pathlib import Path

DEFAULT_WEIGHTS = (0.6, 0.25, 0.15)  # functional, quality, complexity

def load_config(args=None):
    """Load config from .env, environment, and CLI args."""
    dotenv = Path(".env")
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

    config = {
        "provider": os.getenv("AUTOREV_PROVIDER", "nvidia"),
        "api_key": None,
        "model": None,
        "target": ".",
        "rounds": 10,
        "weights": DEFAULT_WEIGHTS,
        "dry_run": False,
        "score_only": False,
        "evaluate_cmd": None,
    }

    # Provider-specific API keys and default models
    provider_defaults = {
        "nvidia": ("NVIDIA_API_KEY", "meta/llama-3.1-70b-instruct"),
        "cerebras": ("CEREBRAS_API_KEY", "qwen-3-32b"),
        "openrouter": ("OPENROUTER_API_KEY", "deepseek/deepseek-r1"),
        "anthropic": ("ANTHROPIC_API_KEY", "claude-sonnet-4-20250514"),
    }

    if config["provider"] in provider_defaults:
        env_key, default_model = provider_defaults[config["provider"]]
        config["api_key"] = os.getenv(env_key)
        config["model"] = default_model

    # CLI overrides
    if args:
        if args.target:
            config["target"] = args.target
        if args.rounds:
            config["rounds"] = args.rounds
        if args.weights:
            parts = [float(w) for w in args.weights.split(",")]
            if len(parts) == 3:
                config["weights"] = tuple(parts)
        if args.dry_run:
            config["dry_run"] = True
        if args.score_only:
            config["score_only"] = True
        if hasattr(args, "provider") and args.provider:
            config["provider"] = args.provider
            if args.provider in provider_defaults:
                env_key, default_model = provider_defaults[args.provider]
                config["api_key"] = os.getenv(env_key)
                config["model"] = default_model
        if hasattr(args, "model") and args.model:
            config["model"] = args.model
        if hasattr(args, "evaluate") and args.evaluate:
            config["evaluate_cmd"] = args.evaluate

    return config
