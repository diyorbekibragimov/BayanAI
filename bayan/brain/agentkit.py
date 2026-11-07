"""Bayan AI · smolagents plumbing shared by the copilot (think loop) and the wrap-up agent.

Verified against smolagents 1.26.0:
  * ToolCallingAgent(tools, model, prompt_templates, instructions, max_steps, step_callbacks, max_tool_threads,
    verbosity_level). Parallel tool calls in one step run in a thread pool (so tools must be thread-safe).
  * run() raises only on model/generation errors (AgentGenerationError) or interrupt(); tool errors are recorded
    on the step and the loop continues. On max_steps it calls provide_final_answer() = one EXTRA LLM call; we
    override that to a no-op. final_answer together with other tool calls in one step is a step error (the other
    calls still execute); we interrupt the run there instead of paying for another step.
  * The agent registers its default final_answer with tools.setdefault("final_answer", ...), so a user tool named
    "final_answer" replaces it, and calling it ends the run. The copilot uses that: ONE call posts all cards and
    finishes (typical run = 1 LLM step).
  * @tool needs type hints + a Google-style "Args:" docstring and inspect.getsource() (define tools in a .py file,
    not in a REPL / python -c); `Any` is sent to the model as "string" but accepts any JSON value; params with
    defaults become optional ("nullable"). Argument types are validated (wrong type = a wasted step).
  * InferenceClientModel(model_id, provider, token|api_key, timeout, retry, **kwargs): the extra kwargs are stored
    in Model.kwargs and override the completion kwargs of every chat_completion call, so max_tokens and
    extra_body={"reasoning_effort": "low"} reach the provider (huggingface_hub 1.33 chat_completion has
    extra_body). tool_choice defaults to "required". Token usage: ChatMessage.token_usage / agent.monitor.
  * Measured live: works on Cerebras; on Groq gpt-oss calls a nonexistent "json" tool -> the agent is Cerebras-only
    and never falls back to Groq (the deterministic fallback covers failures).

run_agent() never raises: it runs the agent in a worker thread with a hard timeout. On timeout it sets the run's
`cancel` event (tools must check it, so a late post_card is a no-op), interrupts the agent and returns ok=False.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Callable

from . import llm

# The brain model (BAYAN_BRAIN_LLM / BAYAN_BRAIN_PROVIDER) wins; BAYAN_AGENT_LLM / BAYAN_AGENT_PROVIDER still work.
AGENT_MODEL = llm.BRAIN_MODEL or os.environ.get("BAYAN_AGENT_LLM", llm.LLM_MODEL)
AGENT_PROVIDER = llm.BRAIN_PROVIDER or os.environ.get("BAYAN_AGENT_PROVIDER", "cerebras")  # NOT groq: tool calls fail
AGENT_TOOL_CHOICE = os.environ.get("BAYAN_AGENT_TOOL_CHOICE", "")       # "" = smolagents default ("required")
AGENT_REASONING = os.environ.get("BAYAN_AGENT_REASONING", "medium")   # never "high": 12 s, empty replies
AGENT_HTTP_TIMEOUT = int(os.environ.get("BAYAN_AGENT_HTTP_TIMEOUT", "15"))
AGENT_MAX_TOKENS = int(os.environ.get("BAYAN_AGENT_MAX_TOKENS", "6000"))  # reasoning tokens count against it
# $ per 1M tokens for the agent model on its provider (llm.MODEL_PRICES); BAYAN_PRICE_IN / _OUT override.
PRICE_IN_PER_M = float(os.environ.get("BAYAN_PRICE_IN") or llm.price(AGENT_MODEL, AGENT_PROVIDER)[0])
PRICE_OUT_PER_M = float(os.environ.get("BAYAN_PRICE_OUT") or llm.price(AGENT_MODEL, AGENT_PROVIDER)[1])

_model_factory: Callable[[], Any] | None = None

# Replaces smolagents' 3.8k-char default system prompt (re-sent every step). Tool schemas go in the API `tools`.
SYSTEM_TEMPLATE = """{%- if custom_instructions %}{{custom_instructions}}
{% endif %}Always reply with exactly one tool call. Calling final_answer ends the run."""


def set_model_factory(fn: Callable[[], Any] | None) -> None:
    """Test hook: fn() returns a smolagents Model (e.g. a scripted fake). None restores InferenceClientModel."""
    global _model_factory
    _model_factory = fn


def available() -> bool:
    """True when an agent model can be built (fake injected, or an HF token in the environment)."""
    return _model_factory is not None or bool(os.environ.get("HF_TOKEN") or llm.HF_TOKEN)


def make_model():
    """smolagents InferenceClientModel for gpt-oss-120b on HF Inference Providers (or the injected fake)."""
    if _model_factory is not None:
        return _model_factory()
    from smolagents import InferenceClientModel
    kwargs = model_kwargs()
    if not llm.provider_known(AGENT_PROVIDER):   # e.g. deepinfra on an older huggingface_hub: the HF router
        return InferenceClientModel(model_id=f"{AGENT_MODEL}:{AGENT_PROVIDER}", base_url=llm.ROUTER_URL,
                                    api_key=os.environ.get("HF_TOKEN") or llm.HF_TOKEN, timeout=AGENT_HTTP_TIMEOUT,
                                    retry=False, **kwargs)
    return InferenceClientModel(
        model_id=AGENT_MODEL,
        provider=AGENT_PROVIDER,
        token=os.environ.get("HF_TOKEN") or llm.HF_TOKEN,
        timeout=AGENT_HTTP_TIMEOUT,
        retry=False,               # rate-limit retries sleep 60 s; the deterministic fallback is better
        **kwargs,
    )


def model_kwargs() -> dict[str, Any]:
    """Completion kwargs for the agent model (reasoning_effort only for gpt-oss; see llm.reasoning_body)."""
    kwargs: dict[str, Any] = dict(temperature=0, max_tokens=AGENT_MAX_TOKENS)
    extra = llm.reasoning_body(AGENT_MODEL, AGENT_REASONING)
    if extra:
        kwargs["extra_body"] = extra
    if AGENT_TOOL_CHOICE:
        kwargs["tool_choice"] = AGENT_TOOL_CHOICE
    return kwargs


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * PRICE_IN_PER_M / 1e6 + output_tokens * PRICE_OUT_PER_M / 1e6


def _short(x: Any, n: int = 48) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def fmt_call(name: str, args: Any) -> str:
    if isinstance(args, dict):
        cards = args.get("cards")
        if name == "final_answer" and isinstance(cards, list):
            inner = ", ".join(f"{c.get('kind') or '?'} {_short(c.get('title') or '', 40)!r}" if isinstance(c, dict)
                              else "?" for c in cards)
            return f"final_answer([{inner}])"
        if name == "post_card":
            inner = ", ".join(repr(_short(args.get(k), 60)) for k in ("kind", "title") if args.get(k))
        else:
            inner = ", ".join(repr(_short(v)) if isinstance(v, str) else _short(v) for v in args.values()
                              if v not in (None, ""))
    elif args in (None, ""):
        inner = ""
    else:
        inner = repr(_short(args))
    return f"{name}({inner})"


def fmt_result(obs: str) -> str:
    obs = (obs or "").strip()
    try:
        data = json.loads(obs)
    except (ValueError, TypeError):
        return _short(obs, 70)
    if isinstance(data, dict):
        for k in ("summary", "id", "card", "match", "result", "status"):
            if k in data:
                return _short(data[k] if data[k] is not None else "no match", 70)
        return _short(data, 70)
    if isinstance(data, list):
        ids = [d.get("id") or d.get("rule_id") for d in data if isinstance(d, dict)]
        ids = [i for i in ids if i]
        return ", ".join(ids[:6]) + ("…" if len(ids) > 6 else "") if ids else f"{len(data)} items"
    return _short(obs, 70)


def short_error(msg: str) -> str:
    """"Error executing tool 'x' with arguments {...huge...}: ValueError: why" -> "x: why"."""
    m = re.search(r"Error executing tool '([^']+)' with arguments .*?: (?:\w+(?:Error|Exception)): (.*)", msg, re.S)
    if m:
        return f"{m.group(1)}: {m.group(2).split(chr(10) + 'Please try again')[0].strip()}"
    return msg


def _agent_class():
    from smolagents import ToolCallingAgent
    from smolagents.models import ChatMessage, MessageRole

    class BayanToolCallingAgent(ToolCallingAgent):
        def provide_final_answer(self, task, *args, **kwargs):  # no extra LLM call when max_steps is hit
            return ChatMessage(role=MessageRole.ASSISTANT, content="(stopped: step limit reached)")

    return BayanToolCallingAgent


def _prompt_templates() -> dict:
    import importlib.resources

    import yaml
    templates = yaml.safe_load(
        importlib.resources.files("smolagents.prompts").joinpath("toolcalling_agent.yaml").read_text(encoding="utf-8"))
    templates["system_prompt"] = SYSTEM_TEMPLATE        # compact: tool schemas already go in the API `tools` field
    return templates


def run_agent(tools: list, task: str, consult, max_steps: int = 4, timeout_s: float = 20.0, instructions: str = "",
              cancel: threading.Event | None = None, model: Any = None, label: str = "agent") -> dict:
    """Run a ToolCallingAgent over `tools`. Never raises.

    Returns {"ok", "steps", "error", "final", "timed_out", "tool_calls", "step_errors", "input_tokens",
    "output_tokens", "cost_usd", "latency_s"}. Each tool call becomes a "tool" trace line via the step callback.
    """
    t0 = time.time()
    cancel = cancel if cancel is not None else threading.Event()
    res: dict[str, Any] = {"ok": False, "steps": 0, "error": None, "final": None, "timed_out": False,
                           "tool_calls": 0, "step_errors": 0, "input_tokens": 0, "output_tokens": 0,
                           "cost_usd": 0.0, "latency_s": 0.0}
    box: dict[str, Any] = {}

    def log(kind: str, text: str) -> None:
        if not cancel.is_set():
            try:
                consult.log(kind, text)
            except Exception:  # noqa: BLE001
                pass

    try:
        from smolagents.memory import ActionStep
        from smolagents.monitoring import LogLevel
        agent_cls = _agent_class()
        mdl = model if model is not None else make_model()

        executed: list[tuple[str, Any, Any]] = []      # (tool, args, result) in execution order
        exec_lock = threading.Lock()

        def wrap(t):
            orig = t.forward

            def forward(*a, **kw):
                out = orig(*a, **kw)
                with exec_lock:
                    executed.append((t.name, kw if kw else (a[0] if len(a) == 1 else list(a)), out))
                return out
            t.forward = forward
            return t

        tools = [wrap(t) for t in tools]

        def on_step(step, agent=None) -> None:
            """Step callback: one "tool" trace line per executed tool call, plus step errors."""
            if not isinstance(step, ActionStep) or cancel.is_set():
                return
            try:
                with exec_lock:
                    done = list(executed)
                    executed.clear()
                for name, args, out in done:
                    log("tool", f"{fmt_call(name, args)} → {fmt_result(out if isinstance(out, str) else json.dumps(out, default=str))}")
                box["tool_calls"] = box.get("tool_calls", 0) + len(done)
                err = getattr(step, "error", None)
                if err is not None:
                    msg = str(getattr(err, "message", err))
                    if "do not perform any other tool calls than the final answer" in msg:
                        box["done_early"] = True        # final_answer sent with other calls: they ran; stop here
                        if agent is not None:
                            agent.interrupt()
                        return
                    if "Reached max steps" in msg:
                        box["max_steps"] = True
                        return
                    box["step_errors"] = box.get("step_errors", 0) + 1
                    log("agent", f"{label} step {step.step_number} error: {_short(short_error(msg), 200)}")
            except Exception as e:  # noqa: BLE001 - a logging bug must not kill the run
                log("error", f"{label} step callback: {e}")

        agent = agent_cls(
            tools=list(tools),
            model=mdl,
            prompt_templates=_prompt_templates(),
            instructions=instructions or None,
            max_steps=max_steps,
            step_callbacks=[on_step],
            max_tool_threads=4,
            verbosity_level=LogLevel.OFF,
        )
    except Exception as e:  # noqa: BLE001
        res["error"] = f"setup failed: {type(e).__name__}: {e}"
        res["latency_s"] = time.time() - t0
        log("error", f"{label}: {res['error']}")
        return res

    def target() -> None:
        try:
            box["final"] = agent.run(task, reset=True, max_steps=max_steps)
        except BaseException as e:  # noqa: BLE001
            box["exc"] = e

    th = threading.Thread(target=target, daemon=True, name=f"bayan-{label}-{getattr(consult, 'id', '')}")
    th.start()
    th.join(timeout_s)
    if th.is_alive():
        cancel.set()
        try:
            agent.interrupt()
        except Exception:  # noqa: BLE001
            pass
        res["timed_out"] = True
        res["error"] = f"timed out after {timeout_s:.0f}s"
        try:
            consult.log("error", f"{label} timed out after {timeout_s:.0f}s; its later tool calls are ignored")
        except Exception:  # noqa: BLE001
            pass
    elif "exc" in box and not box.get("done_early"):
        e = box["exc"]
        res["error"] = f"{type(e).__name__}: {_short(str(getattr(e, 'message', e)), 300)}"
        log("error", f"{label} failed: {res['error']}")
    else:
        res["ok"] = True
        final = box.get("final")
        res["final"] = None if final is None else str(final)
        if box.get("done_early"):
            res["final"] = res["final"] or "done"

    try:
        from smolagents.memory import ActionStep
        res["steps"] = sum(1 for s in agent.memory.steps if isinstance(s, ActionStep)) - (1 if box.get("max_steps") else 0)
        tok = agent.monitor.get_total_token_counts()
        res["input_tokens"] = int(getattr(tok, "input_tokens", 0) or 0)
        res["output_tokens"] = int(getattr(tok, "output_tokens", 0) or 0)
    except Exception:  # noqa: BLE001
        pass
    res["tool_calls"] = box.get("tool_calls", 0)
    res["step_errors"] = box.get("step_errors", 0)
    res["max_steps_reached"] = bool(box.get("max_steps"))
    res["cost_usd"] = cost_usd(res["input_tokens"], res["output_tokens"])
    res["latency_s"] = time.time() - t0
    try:
        lock = getattr(llm, "_usage_lock", None) or threading.Lock()
        with lock:
            llm.USAGE["calls"] += res["steps"]
            llm.USAGE["prompt_tokens"] += res["input_tokens"]
            llm.USAGE["completion_tokens"] += res["output_tokens"]
    except Exception:  # noqa: BLE001
        pass
    log("agent", f"{label}: {res['steps']} step(s), {res['tool_calls']} tool call(s), {res['latency_s']:.1f}s, "
                 f"{res['input_tokens']}/{res['output_tokens']} tok (${res['cost_usd']:.4f})"
                 + ("" if res["ok"] else f" · {res['error']}"))
    return res


# ------------------------------------------------------------------ test helper: a scripted smolagents model
def scripted_model(script: list, delay_s: float = 0.0, tokens: tuple[int, int] = (400, 60)):
    """A smolagents Model replaying `script`: each item is a list of (tool_name, arguments) calls for one step,
    an Exception to raise from generate(), or a callable(messages) -> list of calls. When the script runs out
    it calls final_answer. Used by tests and offline demos (no network)."""
    from smolagents.models import (ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction, MessageRole,
                                   Model)
    from smolagents.monitoring import TokenUsage

    class ScriptedModel(Model):
        def __init__(self):
            super().__init__(model_id="scripted-fake")
            self.script = list(script)
            self.calls = 0
            self.seen_messages: list = []

        def generate(self, messages, stop_sequences=None, response_format=None, tools_to_call_from=None, **kw):
            self.calls += 1
            self.seen_messages.append(messages)
            if delay_s:
                time.sleep(delay_s)
            if self.script:
                item = self.script.pop(0)
            else:   # script exhausted: finish with whatever final_answer signature the agent has
                fa = next((t for t in tools_to_call_from or [] if getattr(t, "name", "") == "final_answer"), None)
                arg = next(iter(getattr(fa, "inputs", {}) or {"answer": None}), "answer")
                item = [("final_answer", {arg: [] if arg == "cards" else "done"})]
            if callable(item) and not isinstance(item, Exception):
                item = item(messages)
            if isinstance(item, BaseException):
                raise item
            tcs = [ChatMessageToolCall(id=f"call_{self.calls}_{i}", type="function",
                                       function=ChatMessageToolCallFunction(name=n, arguments=a))
                   for i, (n, a) in enumerate(item)]
            return ChatMessage(role=MessageRole.ASSISTANT, content="", tool_calls=tcs,
                               token_usage=TokenUsage(input_tokens=tokens[0], output_tokens=tokens[1]))

    return ScriptedModel()
