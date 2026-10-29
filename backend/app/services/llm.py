"""Provider abstraction for optional language-model generation.

The evidence pipeline does not depend on an LLM to be trustworthy. Providers
are called only when configured, and unavailable providers return an explicit
status instead of fabricated output.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

try:
    from app.config import settings
except (ImportError, ModuleNotFoundError):
    from ..config import settings


class LLMProvider(Protocol):
    name: str

    def generate(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str: ...

    def stream(self, messages: list[dict[str, str]], *, temperature: float = 0.0): ...

    def structured_generate(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class ProviderStatus:
    configured: bool
    provider: str
    model: str
    reason: str


class UnavailableProvider:
    name = "none"

    def generate(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str:
        raise RuntimeError("No LLM provider is configured; use the deterministic evidence pipeline, set LLM_PROVIDER=ollama for local Ollama, or configure LLM_PROVIDER and LLM_API_KEY.")

    def stream(self, messages: list[dict[str, str]], *, temperature: float = 0.0):
        raise RuntimeError("No LLM provider is configured; streaming requires LLM_PROVIDER=ollama or a valid LLM_API_KEY.")

    def structured_generate(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("No LLM provider is configured")


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/") or "https://api.openai.com/v1"
        self.api_key = api_key
        self.model = model

    def generate(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str:
        body = json.dumps({"model": self.model, "messages": messages, "temperature": temperature}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:  # nosec B310 - URL is operator-configured.
            data = json.loads(response.read())
        return str(data["choices"][0]["message"]["content"])

    def stream(self, messages: list[dict[str, str]], *, temperature: float = 0.0):
        body = json.dumps({"model": self.model, "messages": messages, "temperature": temperature, "stream": True}).encode()
        request = urllib.request.Request(f"{self.base_url}/chat/completions", data=body, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=90) as response:  # nosec B310 - URL is operator-configured.
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                    delta = payload.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield str(delta)
                except json.JSONDecodeError:
                    continue

    def structured_generate(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any]:
        result = self.generate(messages + [{"role": "system", "content": f"Return valid JSON matching this schema: {json.dumps(schema)}"}], temperature=0.0)
        return json.loads(result)


def get_provider() -> LLMProvider:
    provider_name = settings.llm_provider.lower()
    if provider_name == "ollama":
        base_url = settings.llm_base_url or "http://localhost:11434/v1"
        api_key = settings.llm_api_key or "ollama"
        return OpenAICompatibleProvider(base_url, api_key, settings.llm_model or "llama3")
    if provider_name in {"openai", "openai-compatible"} and settings.llm_api_key:
        base_url = settings.llm_base_url or "https://api.openai.com/v1"
        return OpenAICompatibleProvider(base_url, settings.llm_api_key, settings.llm_model or "configured-model")
    return UnavailableProvider()


def provider_status() -> ProviderStatus:
    provider_name = settings.llm_provider.lower()
    configured = (provider_name == "ollama") or (provider_name not in {"", "none"} and bool(settings.llm_api_key))
    return ProviderStatus(configured, settings.llm_provider, settings.llm_model, "configured" if configured else "explicit deterministic fallback")
