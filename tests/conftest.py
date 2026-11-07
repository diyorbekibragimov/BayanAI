"""Test-wide guard: tests must never make paid inference calls.

Every LLM and TTS request (bayan.brain.llm and smolagents' InferenceClientModel both go through
huggingface_hub.InferenceClient) raises here, and the cached HF token is ignored. A test that trips this
wasn't stubbed: use bayan.brain.llm.set_backend(fake) or agentkit.set_model_factory(fake).
"""

import pytest


def _blocked(*_args, **_kwargs):
    raise RuntimeError("network disabled in tests: stub the LLM with llm.set_backend() / agentkit.set_model_factory()")


@pytest.fixture(autouse=True)
def _no_paid_inference(monkeypatch):
    monkeypatch.setenv("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
    monkeypatch.setenv("HF_TOKEN", "")
    from huggingface_hub import InferenceClient

    for name in ("chat_completion", "text_generation", "text_to_speech", "automatic_speech_recognition"):
        if hasattr(InferenceClient, name):
            monkeypatch.setattr(InferenceClient, name, _blocked)
    yield
