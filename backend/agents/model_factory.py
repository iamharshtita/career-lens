"""
backend/agents/model_factory.py

Central model factory for CareerLens.

Reads LLM_PROVIDER from the environment and returns the appropriate
Strands model instance. All agents import get_model() from here so
switching providers requires only a single env var change.

Supported providers (set LLM_PROVIDER in .env):
  bedrock    — AWS Bedrock (default, requires AWS credentials)
  anthropic  — Anthropic API (requires ANTHROPIC_API_KEY)
  openai     — OpenAI API (requires OPENAI_API_KEY)

Model IDs (set LLM_MODEL_ID in .env to override):
  bedrock   default: us.anthropic.claude-haiku-4-5-20251001-v1:0
  anthropic default: claude-3-5-haiku-20241022
  openai    default: gpt-4o-mini
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Defaults per provider
# ---------------------------------------------------------------------------

_DEFAULT_MODEL_IDS = {
    "bedrock":   "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "anthropic": "claude-3-5-haiku-20241022",
    "openai":    "gpt-4o-mini",
}


def get_model():
    """Return a configured Strands model based on LLM_PROVIDER env var.

    Returns:
        A Strands model instance ready to pass to Agent(model=...).

    Raises:
        ValueError: If LLM_PROVIDER is set to an unsupported value.
        ImportError: If the required provider package is not installed.
    """
    provider = os.getenv("LLM_PROVIDER", "bedrock").lower().strip()
    model_id = os.getenv("LLM_MODEL_ID", _DEFAULT_MODEL_IDS.get(provider, ""))

    if provider == "bedrock":
        from strands.models.bedrock import BedrockModel
        return BedrockModel(model_id=model_id)

    elif provider == "anthropic":
        try:
            from strands.models.anthropic import AnthropicModel
        except ImportError:
            raise ImportError(
                "Anthropic provider requires the anthropic package. "
                "Run: pip install 'strands-agents[anthropic]'"
            )
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or export it in your shell."
            )
        return AnthropicModel(model_id=model_id, api_key=api_key)

    elif provider == "openai":
        try:
            from strands.models.openai import OpenAIModel
        except ImportError:
            raise ImportError(
                "OpenAI provider requires the openai package. "
                "Run: pip install 'strands-agents[openai]'"
            )
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Add it to your .env file or export it in your shell."
            )
        return OpenAIModel(model_id=model_id, api_key=api_key)

    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: '{provider}'. "
            "Choose one of: bedrock, anthropic, openai"
        )
