from __future__ import annotations

import json
import os
from typing import Any

import requests

from models import AiProvider


class AiClientError(Exception):
    pass


def _resolve_api_key(provider: AiProvider) -> str | None:
    if provider.api_key_env:
        return os.getenv(provider.api_key_env)
    return provider.api_key_value


def generate_text(prompt: str, system: str | None, model: str | None, provider_id: int, temperature: float | None = None) -> tuple[str, str]:
    provider = AiProvider.query.get(provider_id)
    if not provider or not provider.enabled:
        raise AiClientError("AI provider not found or disabled")

    if provider.provider_type == "ollama":
        return _call_ollama(provider, prompt, system, model, temperature)
    if provider.provider_type in {"openai_compatible", "openai"}:
        return _call_openai_compatible(provider, prompt, system, model, temperature)
    if provider.provider_type == "anthropic":
        return _call_anthropic(provider, prompt, system, model, temperature)
    if provider.provider_type == "gemini":
        return _call_gemini(provider, prompt, system, model, temperature)
    if provider.provider_type == "custom_http":
        return _call_custom(provider, prompt, system, model, temperature)
    raise AiClientError(f"Unsupported provider type: {provider.provider_type}")


def _base_headers(provider: AiProvider) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    key = _resolve_api_key(provider)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if provider.headers_json:
        try:
            headers.update(json.loads(provider.headers_json))
        except json.JSONDecodeError as exc:
            raise AiClientError(f"Invalid headers_json: {exc}") from exc
    return headers


def _call_ollama(provider: AiProvider, prompt: str, system: str | None, model: str | None, temperature: float | None) -> tuple[str, str]:
    url = f"{provider.base_url.rstrip('/')}/api/generate"
    payload: dict[str, Any] = {
        "model": model or provider.model,
        "prompt": f"{system or ''}\n{prompt}".strip(),
        "stream": False,
    }
    if temperature is not None:
        payload["options"] = {"temperature": temperature}
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=provider.request_timeout_seconds)
    if resp.status_code >= 400:
        raise AiClientError(f"Ollama HTTP {resp.status_code}")
    data = resp.json()
    return data.get("response", ""), payload["model"]


def _call_openai_compatible(provider: AiProvider, prompt: str, system: str | None, model: str | None, temperature: float | None) -> tuple[str, str]:
    url = f"{provider.base_url.rstrip('/')}/v1/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, Any] = {"model": model or provider.model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    resp = requests.post(url, json=payload, headers=_base_headers(provider), timeout=provider.request_timeout_seconds)
    if resp.status_code >= 400:
        raise AiClientError(f"OpenAI-compatible HTTP {resp.status_code}")
    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiClientError(f"Unexpected response format: {data}") from exc
    return text, payload["model"]


def _call_custom(provider: AiProvider, prompt: str, system: str | None, model: str | None, temperature: float | None) -> tuple[str, str]:
    path = "/" if not provider.model else provider.model
    url = f"{provider.base_url.rstrip('/')}{path}"
    payload = {"prompt": prompt, "system": system, "model": model or provider.model, "temperature": temperature}
    resp = requests.post(url, json=payload, headers=_base_headers(provider), timeout=provider.request_timeout_seconds)
    if resp.status_code >= 400:
        raise AiClientError(f"custom_http HTTP {resp.status_code}")
    data = resp.json()
    text = data.get("text") or data.get("response") or json.dumps(data)
    return text, str(payload["model"])


def test_provider_connection(provider_id: int | None, prompt: str = "Reply with: OK") -> tuple[str, str]:
    if not provider_id:
        raise AiClientError("No provider selected")
    return generate_text(prompt=prompt, system="Health check", model=None, provider_id=provider_id, temperature=0)


def _call_anthropic(provider: AiProvider, prompt: str, system: str | None, model: str | None, temperature: float | None) -> tuple[str, str]:
    url = f"{provider.base_url.rstrip('/')}/v1/messages"
    headers = _base_headers(provider)
    key = _resolve_api_key(provider)
    if key:
        headers["x-api-key"] = key
        headers.pop("Authorization", None)
    headers.setdefault("anthropic-version", "2023-06-01")
    payload: dict[str, Any] = {
        "model": model or provider.model,
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = temperature
    resp = requests.post(url, json=payload, headers=headers, timeout=provider.request_timeout_seconds)
    if resp.status_code >= 400:
        raise AiClientError(f"Anthropic HTTP {resp.status_code}")
    data = resp.json()
    content = data.get("content", [])
    text = content[0].get("text", "") if content else ""
    return text, payload["model"]


def _call_gemini(provider: AiProvider, prompt: str, system: str | None, model: str | None, temperature: float | None) -> tuple[str, str]:
    key = _resolve_api_key(provider)
    if not key:
        raise AiClientError("Gemini requires API key")
    m = model or provider.model
    url = f"{provider.base_url.rstrip('/')}/v1beta/models/{m}:generateContent?key={key}"
    payload: dict[str, Any] = {"contents": [{"parts": [{"text": f"{system or ''}\n{prompt}".strip()}]}]}
    if temperature is not None:
        payload["generationConfig"] = {"temperature": temperature}
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=provider.request_timeout_seconds)
    if resp.status_code >= 400:
        raise AiClientError(f"Gemini HTTP {resp.status_code}")
    data = resp.json()
    cand = data.get("candidates", [])
    text = cand[0].get("content", {}).get("parts", [{}])[0].get("text", "") if cand else ""
    return text, m
