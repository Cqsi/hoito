"""Two interchangeable model back-ends with the same small interface:
step() → (calls, refused), add_results([...]), nudge(text), tokens, name.

Provider: HOITO_PROVIDER=claude|openai, or picked from whichever API key is set (Claude first)."""
import json
import os
from dataclasses import dataclass

import anthropic
import openai


@dataclass
class Call:
    id: str
    name: str
    input: dict


# $ per million tokens (input, output), for the cost readout only. Check current prices before quoting them.
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0),
          "gpt-4.1": (2.0, 8.0), "gpt-4.1-mini": (0.4, 1.6)}


def provider() -> str:
    p = os.getenv("HOITO_PROVIDER", "").lower()
    if p in ("claude", "openai"):
        return p
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
        return "claude"
    return "openai" if os.getenv("OPENAI_API_KEY") else "none"


def model_name() -> str:
    p = provider()
    if p == "claude":
        return os.getenv("HOITO_MODEL", "claude-opus-5-5")
    if p == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4.1")
    return "none"


class ClaudeLLM:
    def __init__(self, system: str, tools: list[dict], first_message: str):
        self.client = anthropic.AsyncAnthropic()
        self.name = model_name()
        self.system, self.tools = system, tools
        self.messages: list[dict] = [{"role": "user", "content": first_message}]
        self.tokens_in = self.tokens_out = 0

    async def step(self, final: bool = False) -> tuple[list[Call], bool]:
        tools = [t for t in self.tools if t["name"] == "submit_answer"] if final else self.tools
        while True:
            resp = await self.client.beta.messages.create(
                model=self.name, max_tokens=16000, system=self.system, tools=tools, messages=self.messages,
                output_config={"effort": os.getenv("HOITO_EFFORT", "medium")},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            )
            self.tokens_in += resp.usage.input_tokens or 0
            self.tokens_out += resp.usage.output_tokens or 0
            if resp.stop_reason == "refusal":
                return [], True
            self.messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "pause_turn":
                return [Call(b.id, b.name, dict(b.input)) for b in resp.content if b.type == "tool_use"], False

    def add_results(self, results: list[tuple[str, str, bool]], note: str | None = None) -> None:
        blocks = [{"type": "tool_result", "tool_use_id": i, "content": c, "is_error": e} for i, c, e in results]
        self.messages.append({"role": "user", "content": blocks + ([{"type": "text", "text": note}] if note else [])})

    def nudge(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})


class OpenAILLM:
    def __init__(self, system: str, tools: list[dict], first_message: str):
        self.client = openai.AsyncOpenAI(max_retries=6)  # rides out tokens-per-minute 429s
        self.name = model_name()
        self.tools = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"],
            **({"strict": True} if t.get("strict") else {})}} for t in tools]
        self.messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": first_message}]
        self.tokens_in = self.tokens_out = 0

    async def step(self, final: bool = False) -> tuple[list[Call], bool]:
        extra = {"tool_choice": {"type": "function", "function": {"name": "submit_answer"}}} if final else {}
        resp = await self.client.chat.completions.create(
            model=self.name, messages=self.messages, tools=self.tools, parallel_tool_calls=not final,
            max_completion_tokens=16000, **extra,
        )
        if resp.usage:
            self.tokens_in += resp.usage.prompt_tokens or 0
            self.tokens_out += resp.usage.completion_tokens or 0
        msg = resp.choices[0].message
        if getattr(msg, "refusal", None):
            return [], True
        self.messages.append(msg.model_dump(exclude_none=True))
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_invalid_json": tc.function.arguments}
            calls.append(Call(tc.id, tc.function.name, args))
        return calls, False

    def add_results(self, results: list[tuple[str, str, bool]], note: str | None = None) -> None:
        for i, c, e in results:
            self.messages.append({"role": "tool", "tool_call_id": i, "content": ("ERROR: " + c) if e else c})
        if note:
            self.messages.append({"role": "user", "content": note})

    def nudge(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})


def make(system: str, tools: list[dict], first_message: str):
    p = provider()
    if p == "claude":
        return ClaudeLLM(system, tools, first_message)
    if p == "openai":
        return OpenAILLM(system, tools, first_message)
    raise RuntimeError("No model API key: set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env")
