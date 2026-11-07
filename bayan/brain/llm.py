"""Thin chat client for gpt-oss-120b on HF Inference Providers, shared by extraction and wrap-up.

Tests replace the network with `set_backend(fn)`, where fn(messages, schema, max_tokens) -> str.
Every call adds its token counts to USAGE so the UI can show a measured cost meter.
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Callable

HF_TOKEN = os.environ.get("HF_TOKEN")
LLM_MODEL = os.environ.get("BAYAN_LLM", "openai/gpt-oss-120b")
LLM_PROVIDER = os.environ.get("BAYAN_LLM_PROVIDER", "cerebras")
LLM_FALLBACK_PROVIDER = os.environ.get("BAYAN_LLM_FALLBACK", "groq")
LLM_TIMEOUT_S = float(os.environ.get("BAYAN_LLM_TIMEOUT", "45"))   # per HTTP request (the talk loop's budget)

# $ per 1M tokens (input, output) for openai/gpt-oss-120b, from router.huggingface.co/v1/models on 2026-11-07.
PRICES = {"cerebras": (0.35, 0.75), "groq": (0.15, 0.75), "baseten": (0.10, 0.50), "novita": (0.05, 0.25),
          "ovhcloud": (0.09, 0.47)}

USAGE = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
_usage_lock = threading.Lock()


def cost_usd(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = PRICES.get(provider, PRICES["cerebras"])
    return (prompt_tokens * pin + completion_tokens * pout) / 1e6

_backend: Callable[[list[dict], dict | None, int], str] | None = None
_clients: dict[str, object] = {}


def set_backend(fn: Callable[[list[dict], dict | None, int], str] | None) -> None:
    """Route every call to fn instead of the network (tests, offline replay). None restores the network."""
    global _backend
    _backend = fn


def _client(provider: str):
    if provider not in _clients:
        from huggingface_hub import InferenceClient
        _clients[provider] = InferenceClient(provider=provider, api_key=HF_TOKEN or os.environ.get("HF_TOKEN"),
                                             timeout=LLM_TIMEOUT_S)
    return _clients[provider]


def _record(out, provider: str) -> None:
    u = getattr(out, "usage", None)
    with _usage_lock:
        USAGE["calls"] += 1
        if u is not None:
            pin = int(getattr(u, "prompt_tokens", 0) or 0)
            pout = int(getattr(u, "completion_tokens", 0) or 0)
            USAGE["prompt_tokens"] += pin
            USAGE["completion_tokens"] += pout
            USAGE["cost_usd"] += cost_usd(provider, pin, pout)


def _complete(messages: list[dict], schema: dict | None, max_tokens: int, reasoning: str,
              provider: str | None = None, fallback: str | None = None) -> str:
    if _backend is not None:
        return _backend(messages, schema, max_tokens)
    formats = []
    if schema is not None:
        formats.append({"type": "json_schema", "json_schema": {"name": "bayan", "schema": schema, "strict": False}})
        formats.append({"type": "json_object"})
    formats.append(None)
    last_err: Exception | None = None
    order = [provider or LLM_PROVIDER, fallback or (LLM_PROVIDER if provider else LLM_FALLBACK_PROVIDER)]
    for prov in dict.fromkeys(order):
        for fmt in formats:
            kwargs = dict(model=LLM_MODEL, messages=messages, temperature=0, max_tokens=max_tokens)
            if fmt is not None:
                kwargs["response_format"] = fmt
            try:
                try:
                    out = _client(prov).chat.completions.create(**kwargs, extra_body={"reasoning_effort": reasoning})
                except TypeError:
                    out = _client(prov).chat.completions.create(**kwargs)
                _record(out, prov)
                return out.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001 - try the next format, then the next provider
                last_err = e
    raise RuntimeError(f"LLM call failed on all providers: {last_err}")


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return {}
        try:
            out = json.loads(m.group(0))
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            return {}


def chat_text(system: str, user: str, max_tokens: int = 900, reasoning: str = "low",
              provider: str | None = None, fallback: str | None = None) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return _complete(msgs, None, max_tokens, reasoning, provider, fallback)


def chat_json(system: str, user: str, schema: dict | None = None, max_tokens: int = 900,
              reasoning: str = "low", provider: str | None = None, fallback: str | None = None) -> dict:
    """JSON-object reply. Uses response_format json_schema when the provider accepts it; never raises on bad JSON
    (returns {}), but does raise RuntimeError if every provider fails. provider/fallback override the defaults
    (e.g. background extraction on Groq, the same gpt-oss-120b at a lower input price, falling back to Cerebras)."""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return parse_json(_complete(msgs, schema, max_tokens, reasoning, provider, fallback))
