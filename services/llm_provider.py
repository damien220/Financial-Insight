"""LLM Provider abstraction — online (OpenAI/Anthropic) and offline (Ollama) modes."""

import os
import json
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        """Generate a completion from the given prompt. Returns raw text."""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier being used."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check whether this provider is reachable."""
        ...


# ---------------------------------------------------------------------------
# Online: OpenAI-compatible
# ---------------------------------------------------------------------------

class OpenAIProvider(LLMProvider):

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: int = 2,
    ):
        self._api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self._model = model or os.environ.get("LLM_ONLINE_MODEL", "gpt-4o-mini")
        self._base_url = base_url  # None = default OpenAI endpoint
        self._max_retries = max_retries
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                max_retries=self._max_retries,
            )
        return self._client

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.3),
            max_tokens=kwargs.get("max_tokens", 2048),
        )
        return response.choices[0].message.content or ""

    def get_model_name(self) -> str:
        return self._model

    async def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            client = self._get_client()
            await client.models.list()
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Online: Anthropic
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 2,
    ):
        self._api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self._model = model or os.environ.get("LLM_ONLINE_MODEL", "claude-sonnet-4-20250514")
        self._max_retries = max_retries
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(
                api_key=self._api_key,
                max_retries=self._max_retries,
            )
        return self._client

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        client = self._get_client()
        response = await client.messages.create(
            model=self._model,
            max_tokens=kwargs.get("max_tokens", 2048),
            system=system or "You are a financial analyst.",
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.3),
        )
        return response.content[0].text if response.content else ""

    def get_model_name(self) -> str:
        return self._model

    async def is_available(self) -> bool:
        return bool(self._api_key)


# ---------------------------------------------------------------------------
# Offline: Ollama
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
    ):
        self._model = model or os.environ.get("LLM_OFFLINE_MODEL", "mistral")
        self._host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from ollama import AsyncClient
            self._client = AsyncClient(host=self._host)
        return self._client

    async def generate(self, prompt: str, system: str = "", **kwargs) -> str:
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat(
            model=self._model,
            messages=messages,
            options={"temperature": kwargs.get("temperature", 0.3)},
        )
        return response.get("message", {}).get("content", "")

    def get_model_name(self) -> str:
        return f"ollama:{self._model}"

    async def is_available(self) -> bool:
        try:
            client = self._get_client()
            await client.list()
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
}


def get_llm_provider(mode: Optional[str] = None) -> LLMProvider:
    """Return the configured LLM provider.

    Args:
        mode: 'online', 'offline', or a specific provider name ('openai', 'anthropic', 'ollama').
              Defaults to LLM_MODE env var, then 'offline'.
    """
    if mode is None:
        mode = os.environ.get("LLM_MODE", "offline")

    mode = mode.lower().strip()

    if mode == "online":
        provider_name = os.environ.get("LLM_ONLINE_PROVIDER", "openai").lower()
        if provider_name not in ("openai", "anthropic"):
            provider_name = "openai"
        return _PROVIDERS[provider_name]()

    if mode == "offline":
        return OllamaProvider()

    if mode in _PROVIDERS:
        return _PROVIDERS[mode]()

    raise ValueError(f"Unknown LLM mode '{mode}'. Use 'online', 'offline', 'openai', 'anthropic', or 'ollama'.")
