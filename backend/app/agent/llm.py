"""LLM gateway: one streaming interface over Groq (OpenAI-compatible API) and Ollama (local).

Messages use the OpenAI chat format throughout ({"role", "content", "tool_calls",
"tool_call_id"}); the Ollama client converts to its own format. `stream()` yields text as it
arrives and finishes with one `Reply` holding the whole text and any tool calls.
"""

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

from app.agent.settings import LLMSettings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TIMEOUT = httpx.Timeout(60.0, connect=5.0)
MAX_RATE_WAIT = 20  # seconds; a longer wait is reported instead (e.g. the daily limit)


class LLMError(Exception):
    """A problem the user can do something about; the message is shown in the chat."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Reply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLM:
    provider = ""
    model = ""

    def stream(
        self, messages: list[dict], tools: list[dict], force: str | None = None
    ) -> AsyncIterator[str | Reply]:
        """`force` names a tool the model must call in this reply."""
        raise NotImplementedError


def tool_specs(tools) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.schema()},
        }
        for t in tools
    ]


def tool_call_in_text(text: str, tools: list[dict]) -> tuple[ToolCall, str] | None:
    """A tool call the model wrote out as text instead of making it: plain JSON arguments (often
    in a ```json block), {"name": ..., "arguments": ...}, or Groq's failed_generation in the
    model's own format ("to=functions.draft_booking ... {...}"). Returns the call and the text
    without it, or None."""
    specs = {t["function"]["name"]: t["function"] for t in tools}
    decoder = json.JSONDecoder()
    starts = [m.start() for m in re.finditer(r"\{", text)][:30]
    for start in starts:
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        name, args = _named_call(value, specs) or (_name_before(text[:start], specs), value)
        if name is None:
            name = _matching_tool(args, specs)
        if name is None:
            continue
        before = re.sub(r"```(?:json)?\s*$", "", text[:start])
        after = re.sub(r"^\s*```", "", text[end:])
        rest = re.sub(r"<\|[^|]*\|>|\bto=functions\.\w+|\bjson\b\s*$", "", before + after)
        return ToolCall(f"call_text_{start}", name, args), rest.strip()
    return None


def _named_call(value: dict, specs: dict) -> tuple[str, dict] | None:
    name = value.get("name") or (value.get("function") or {}).get("name")
    args = value.get("arguments", value.get("parameters"))
    if isinstance(args, str):
        args = _parse_args(args)
    if name in specs and isinstance(args, dict):
        return name, args
    return None


def _name_before(text: str, specs: dict) -> str | None:
    """The tool named just before the JSON, e.g. "to=functions.draft_booking <|message|>"."""
    found = re.findall(r"\b(\w+)\b", text[-120:])
    return next((w for w in reversed(found) if w in specs), None)


def _matching_tool(args: dict, specs: dict) -> str | None:
    """The one tool whose parameters include every key of these arguments (at least two)."""
    keys = set(args)
    if len(keys) < 2:
        return None
    fits = [
        (len(set(fn["parameters"].get("properties", {})) - keys), name)
        for name, fn in specs.items()
        if keys <= set(fn["parameters"].get("properties", {}))
    ]
    fits.sort()
    if not fits or (len(fits) > 1 and fits[0][0] == fits[1][0]):
        return None
    return fits[0][1]


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_unparsed": raw}
    return value if isinstance(value, dict) else {}


# Groq ------------------------------------------------------------------------------------------


class GroqLLM(LLM):
    provider = "groq"

    def __init__(self, api_key: str, model: str, fallback: str | None = None):
        if not api_key:
            raise LLMError(
                "Groq isn't set up yet: the Director can add an API key on the Settings page "
                "(or set GROQ_API_KEY in backend/.env)."
            )
        self.api_key, self.model, self.fallback = api_key, model, fallback

    async def stream(self, messages, tools, force=None):
        # Each retry happens before anything was yielded, so the caller never sees a half reply.
        bad_tool_calls = 0
        for _ in range(4):
            try:
                async for item in self._stream(self.model, messages, tools, force):
                    yield item
                return
            except _ModelUnavailable:
                if not self.fallback or self.fallback == self.model:
                    raise LLMError(f"Groq doesn't offer the model {self.model} any more.") from None
                self.model = self.fallback
            except _RateLimited as e:
                if e.wait > MAX_RATE_WAIT:
                    raise LLMError(
                        "Groq's free-tier limit was reached. Wait a minute, or switch to Ollama."
                    ) from None
                await asyncio.sleep(e.wait)
            except _BadToolCall as e:
                # Groq couldn't read the model's tool call. It is usually all there in the
                # failed generation; otherwise asking again usually works.
                if found := tool_call_in_text(e.generation, tools):
                    yield Reply("", [found[0]])
                    return
                bad_tool_calls += 1
                if bad_tool_calls > 2:
                    raise LLMError(
                        "The model couldn't put that request into a form. Try rephrasing it, or "
                        "give the details one at a time."
                    ) from None
        raise LLMError("Groq is busy. Try again in a minute.")

    async def _stream(self, model, messages, tools, force=None):
        body = {"model": model, "messages": messages, "stream": True, "temperature": 0.2}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = (
                {"type": "function", "function": {"name": force}} if force else "auto"
            )
        headers = {"Authorization": f"Bearer {self.api_key}"}
        text, calls = [], {}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                async with client.stream("POST", GROQ_URL, json=body, headers=headers) as res:
                    if res.status_code != 200:
                        await res.aread()
                        _raise_groq(res)
                    async for line in res.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        chunk = json.loads(data)
                        if err := chunk.get("error"):
                            message = err.get("message", "error")
                            if not text and not calls and _is_bad_tool_call(err):
                                raise _BadToolCall(message, err.get("failed_generation"))
                            raise LLMError(f"Groq: {message}")
                        if not chunk.get("choices"):
                            continue
                        delta = chunk["choices"][0].get("delta", {})
                        if delta.get("content"):
                            text.append(delta["content"])
                            yield delta["content"]
                        for c in delta.get("tool_calls") or []:
                            slot = calls.setdefault(
                                c.get("index", 0), {"id": "", "name": "", "args": ""}
                            )
                            slot["id"] = c.get("id") or slot["id"]
                            fn = c.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["args"] += fn.get("arguments") or ""
        except httpx.TimeoutException as e:
            raise LLMError("Groq took too long to answer. Try again in a moment.") from e
        except httpx.TransportError as e:
            raise LLMError("Couldn't reach Groq. Check the internet connection.") from e
        yield Reply(
            "".join(text),
            [
                ToolCall(c["id"] or f"call_{i}", c["name"], _parse_args(c["args"]))
                for i, c in sorted(calls.items())
            ],
        )


class _ModelUnavailable(Exception):
    pass


class _BadToolCall(Exception):
    def __init__(self, message: str, generation: str = ""):
        super().__init__(message)
        self.generation = generation or ""


class _RateLimited(Exception):
    def __init__(self, wait: float):
        self.wait = wait


def _is_bad_tool_call(err: dict) -> bool:
    message = err.get("message", "")
    return (
        err.get("code") in ("tool_use_failed", "output_parse_failed")
        or "validation failed" in message
        or message.startswith("Parsing failed")
    )


def _retry_after(res: httpx.Response, message: str) -> float:
    """Seconds Groq asks us to wait, from the header or "Please try again in 1m2.5s"."""
    try:
        return float(res.headers["retry-after"])
    except (KeyError, ValueError):
        pass
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)", message)
    if not m:
        return 5.0
    seconds = float(m.group(2)) / (1000 if m.group(3) == "ms" else 1)
    return int(m.group(1) or 0) * 60 + seconds


def _raise_groq(res: httpx.Response):
    try:
        err = res.json().get("error", {})
    except ValueError:
        err = {}
    message, code = err.get("message", res.text[:200]), err.get("code", "")
    if res.status_code == 401:
        raise LLMError(
            "Groq rejected the API key. The Director can update it on the Settings page."
        )
    if res.status_code == 429:
        raise _RateLimited(_retry_after(res, message))
    if _is_bad_tool_call(err):
        raise _BadToolCall(message, err.get("failed_generation"))
    if res.status_code == 404 or code in ("model_not_found", "model_decommissioned"):
        raise _ModelUnavailable()
    raise LLMError(f"Groq error ({res.status_code}): {message}")


# Ollama ----------------------------------------------------------------------------------------


class OllamaLLM(LLM):
    provider = "ollama"

    def __init__(self, base_url: str, model: str, num_ctx: int = 8192):
        self.base_url, self.model, self.num_ctx = base_url.rstrip("/"), model, num_ctx

    async def stream(self, messages, tools, force=None):
        if force:  # Ollama has no tool_choice: offer only that tool
            tools = [t for t in tools if t["function"]["name"] == force]
        body = {
            "model": self.model,
            "messages": [_to_ollama(m) for m in messages],
            "stream": True,
            "think": False,
            "options": {"num_ctx": self.num_ctx, "temperature": 0.2},
        }
        if tools:
            body["tools"] = tools
        text, calls = [], []
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=3.0)) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=body) as res:
                    if res.status_code == 404:
                        raise LLMError(
                            f"Ollama doesn't have {self.model}. Run: ollama pull {self.model}"
                        )
                    if res.status_code != 200:
                        await res.aread()
                        raise LLMError(f"Ollama error ({res.status_code}): {res.text[:200]}")
                    async for line in res.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        if chunk.get("error"):
                            raise LLMError(f"Ollama: {chunk['error']}")
                        msg = chunk.get("message") or {}
                        if msg.get("content"):
                            text.append(msg["content"])
                            yield msg["content"]
                        for c in msg.get("tool_calls") or []:
                            fn = c.get("function", {})
                            calls.append(
                                ToolCall(
                                    f"call_{len(calls)}",
                                    fn.get("name", ""),
                                    _parse_args(fn.get("arguments")),
                                )
                            )
        except httpx.ConnectError as e:
            raise LLMError(
                f"Ollama isn't running at {self.base_url}. "
                "Start it (ollama serve) or switch to Groq."
            ) from e
        except httpx.TimeoutException as e:
            raise LLMError("Ollama took too long to answer.") from e
        yield Reply("".join(text), calls)


def _to_ollama(m: dict) -> dict:
    out = {"role": m["role"], "content": m.get("content") or ""}
    if m.get("tool_calls"):
        out["tool_calls"] = [
            {
                "function": {
                    "name": c["function"]["name"],
                    "arguments": _parse_args(c["function"]["arguments"]),
                }
            }
            for c in m["tool_calls"]
        ]
    if m["role"] == "tool" and m.get("name"):
        out["tool_name"] = m["name"]
    return out


async def ollama_models(base_url: str) -> list[str]:
    """Models pulled into Ollama, or [] when it isn't running."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
            res = await client.get(f"{base_url.rstrip('/')}/api/tags")
            res.raise_for_status()
    except (httpx.HTTPError, ValueError):
        return []
    return sorted(m["name"] for m in res.json().get("models", []))


# Choosing a model ------------------------------------------------------------------------------


def make_llm(cfg: LLMSettings, provider: str | None = None, model: str | None = None) -> LLM:
    if cfg.fake:
        from app.agent.fake import DemoLLM

        return DemoLLM()
    provider = provider or cfg.provider
    if provider == "ollama":
        return OllamaLLM(cfg.ollama_base_url, model or cfg.ollama_model)
    if provider == "groq":
        return GroqLLM(cfg.groq_api_key, model or cfg.groq_model, cfg.groq_fallback_model)
    raise LLMError(f"Unknown provider {provider}.")


async def check_connection(llm: LLM) -> dict:
    """Ask for a one-word reply; used by the Settings page."""
    started = time.monotonic()
    reply = Reply()
    messages = [{"role": "user", "content": "Reply with the single word: ready"}]
    try:
        async for item in llm.stream(messages, []):
            if isinstance(item, Reply):
                reply = item
    except LLMError as e:
        return {"ok": False, "message": str(e)}
    ms = round((time.monotonic() - started) * 1000)
    return {"ok": True, "message": f"{llm.model} answered in {ms} ms: {reply.text.strip()[:60]}"}
