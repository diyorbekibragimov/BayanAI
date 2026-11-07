"""Thin chat client for gpt-oss-120b on HF Inference Providers, shared by translation, extraction and wrap-up.

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
# Live translation (bayan.talk): BAYAN_LLM on BAYAN_LLM_PROVIDER.
LLM_MODEL = os.environ.get("BAYAN_LLM", "openai/gpt-oss-120b")
LLM_PROVIDER = os.environ.get("BAYAN_LLM_PROVIDER", "cerebras")
LLM_FALLBACK_PROVIDER = os.environ.get("BAYAN_LLM_FALLBACK", "groq")
LLM_TIMEOUT_S = float(os.environ.get("BAYAN_LLM_TIMEOUT", "45"))   # per HTTP request (the talk loop's budget)
# The agentic "brain" (copilot extraction, copilot agent, wrap-up note / care plan / wrap-up agent) can run on its own
# model, for A/B tests: BAYAN_BRAIN_LLM on BAYAN_BRAIN_PROVIDER (fallback BAYAN_BRAIN_FALLBACK, default the same
# provider: another host rarely serves the same model). Unset = the defaults above, with extraction on Groq.
BRAIN_MODEL = os.environ.get("BAYAN_BRAIN_LLM", "")
BRAIN_PROVIDER = os.environ.get("BAYAN_BRAIN_PROVIDER", "")
BRAIN_FALLBACK = os.environ.get("BAYAN_BRAIN_FALLBACK", "")

# $ per 1M tokens (input, output) by model and provider, from router.huggingface.co/v1/models on 2026-11-07.
MODEL_PRICES = {
    "openai/gpt-oss-120b": {"cerebras": (0.35, 0.75), "groq": (0.15, 0.75), "baseten": (0.10, 0.50),
                            "novita": (0.05, 0.25), "ovhcloud": (0.09, 0.47), "deepinfra": (0.037, 0.17)},
}
PRICES = MODEL_PRICES["openai/gpt-oss-120b"]          # gpt-oss by provider (kept for callers that pass a provider)
# Provider/model pairs whose router listing says "supports_structured_output: false": skip json_schema (one wasted
# request each time) and ask for json_object; the callers validate the JSON (extract.clean_delta, wrap-up schemas).
NO_JSON_SCHEMA = {("openai/gpt-oss-120b", "deepinfra")}

USAGE = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
_usage_lock = threading.Lock()


def brain_model() -> str:
    return BRAIN_MODEL or LLM_MODEL


def brain_route(provider: str | None = None, fallback: str | None = None) -> dict:
    """kwargs (model / provider / fallback) for a brain call. Unset BAYAN_BRAIN_*: the caller's own provider and
    fallback (or the defaults), so behaviour is unchanged. Set: the brain model on the brain provider."""
    if not (BRAIN_MODEL or BRAIN_PROVIDER):
        out: dict = {}
        if provider:
            out["provider"] = provider
        if fallback:
            out["fallback"] = fallback
        return out
    prov = BRAIN_PROVIDER or LLM_PROVIDER
    return {"model": brain_model(), "provider": prov, "fallback": BRAIN_FALLBACK or prov}


def price(model: str | None, provider: str) -> tuple[float, float]:
    """$ per 1M (input, output) tokens for this model on this provider; an unlisted pair is priced as gpt-oss on
    that provider (or Cerebras)."""
    table = MODEL_PRICES.get(model or LLM_MODEL) or {}
    return table.get(provider) or PRICES.get(provider, PRICES["cerebras"])


def cost_usd(provider: str, prompt_tokens: int, completion_tokens: int, model: str | None = None) -> float:
    pin, pout = price(model, provider)
    return (prompt_tokens * pin + completion_tokens * pout) / 1e6


def reasoning_body(model: str | None, reasoning: str) -> dict:
    """extra_body for the reasoning effort: gpt-oss takes "reasoning_effort"; other models get none, since
    an unknown parameter can make the provider reject the request."""
    if reasoning and "gpt-oss" in str(model or LLM_MODEL).lower():
        return {"reasoning_effort": reasoning}
    return {}

_backend: Callable[[list[dict], dict | None, int], str] | None = None
_clients: dict[str, object] = {}


def set_backend(fn: Callable[[list[dict], dict | None, int], str] | None) -> None:
    """Route every call to fn instead of the network (tests, offline replay). None restores the network."""
    global _backend
    _backend = fn


ROUTER_URL = "https://router.huggingface.co/v1"


def provider_known(provider: str) -> bool:
    """True when the installed huggingface_hub has a client for this provider (0.36.2 has no "deepinfra")."""
    try:
        from huggingface_hub.inference._providers import PROVIDERS
        return provider in PROVIDERS
    except Exception:  # noqa: BLE001
        return True


class _RouterCompletions:
    """OpenAI-compatible HF router with the `model:provider` suffix, for providers the library does not know."""

    def __init__(self, client, provider: str):
        self._c, self._p = client, provider

    def create(self, model, **kw):
        return self._c.chat.completions.create(model=f"{model}:{self._p}", **kw)


class _RouterClient:
    def __init__(self, provider: str):
        from huggingface_hub import InferenceClient
        c = InferenceClient(base_url=ROUTER_URL, api_key=HF_TOKEN or os.environ.get("HF_TOKEN"), timeout=LLM_TIMEOUT_S)
        self.chat = type("_Chat", (), {})()
        self.chat.completions = _RouterCompletions(c, provider)


def _client(provider: str):
    if provider not in _clients:
        if not provider_known(provider):
            _clients[provider] = _RouterClient(provider)
        else:
            from huggingface_hub import InferenceClient
            _clients[provider] = InferenceClient(provider=provider, api_key=HF_TOKEN or os.environ.get("HF_TOKEN"),
                                                 timeout=LLM_TIMEOUT_S)
    return _clients[provider]


def _record(out, provider: str, model: str | None = None) -> None:
    u = getattr(out, "usage", None)
    with _usage_lock:
        USAGE["calls"] += 1
        if u is not None:
            pin = int(getattr(u, "prompt_tokens", 0) or 0)
            pout = int(getattr(u, "completion_tokens", 0) or 0)
            USAGE["prompt_tokens"] += pin
            USAGE["completion_tokens"] += pout
            USAGE["cost_usd"] += cost_usd(provider, pin, pout, model)


def _complete(messages: list[dict], schema: dict | None, max_tokens: int, reasoning: str,
              provider: str | None = None, fallback: str | None = None, model: str | None = None) -> str:
    if _backend is not None:
        return _backend(messages, schema, max_tokens)
    model = model or LLM_MODEL
    last_err: Exception | None = None
    order = [provider or LLM_PROVIDER, fallback or (LLM_PROVIDER if provider else LLM_FALLBACK_PROVIDER)]
    for prov in dict.fromkeys(order):
        formats = []
        if schema is not None:
            if (model, prov) not in NO_JSON_SCHEMA:
                formats.append({"type": "json_schema", "json_schema": {"name": "bayan", "schema": schema,
                                                                       "strict": False}})
            formats.append({"type": "json_object"})
        formats.append(None)
        extra = reasoning_body(model, reasoning)
        for fmt in formats:
            kwargs = dict(model=model, messages=messages, temperature=0, max_tokens=max_tokens)
            if fmt is not None:
                kwargs["response_format"] = fmt
            try:
                try:
                    out = (_client(prov).chat.completions.create(**kwargs, extra_body=extra) if extra
                           else _client(prov).chat.completions.create(**kwargs))
                except TypeError:
                    out = _client(prov).chat.completions.create(**kwargs)
                _record(out, prov, model)
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
              provider: str | None = None, fallback: str | None = None, model: str | None = None) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return _complete(msgs, None, max_tokens, reasoning, provider, fallback, model)


def chat_json(system: str, user: str, schema: dict | None = None, max_tokens: int = 900,
              reasoning: str = "low", provider: str | None = None, fallback: str | None = None,
              model: str | None = None) -> dict:
    """JSON-object reply. Uses response_format json_schema when the provider accepts it; never raises on bad JSON
    (returns {}), but does raise RuntimeError if every provider fails. provider/fallback override the defaults
    (e.g. background extraction on Groq, the same gpt-oss-120b at a lower input price, falling back to Cerebras)."""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return parse_json(_complete(msgs, schema, max_tokens, reasoning, provider, fallback, model))
