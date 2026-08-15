"""Pioneer — Bookit's model layer.

Pioneer (Fastino Labs) is an OpenAI-compatible inference endpoint with a
*model router* in front of it. Instead of naming a model, you send
``pioneer/auto`` and the router scores the request against ~200 candidate
models, then serves the cheapest one predicted to clear the quality bar. The
response carries an ``x_pioneer`` block naming the model it actually picked and
what that choice saved against a frontier baseline.

That is the same trade Bookit makes with labour — buy the expensive option only
where it changes the outcome — so the router is doing for models what the
planner does for tasks.

Two things about this endpoint shape the code below:

* **No structured-output support.** ``response_format={"type": "json_object"}``
  and ``json_schema`` both fail (400 / 503). JSON has to be requested in the
  prompt and parsed defensively, with a repair round-trip when it comes back
  malformed.
* **Routed models may reason before answering.** Reasoning tokens are billed
  against ``max_tokens``, so a tight budget returns an empty message rather
  than a short one. Budgets here are deliberately generous.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

BASE_URL = "https://api.pioneer.ai/v1"

# The router. Overridable so a specific model can be pinned for debugging.
AUTO_MODEL = "pioneer/auto"

# Reasoning tokens count against this too, so the budget covers both thinking
# and output. A full action plan — a dozen actions, each with a complete Terac
# opportunity — runs well past 8k, which truncates the JSON mid-object.
DEFAULT_MAX_TOKENS = 16000

# What a truncated response gets retried with. Cheaper than starting high on
# every call, since most plans fit the default.
MAX_TOKENS_CEILING = 32000

DEFAULT_TIMEOUT = 300.0


class PioneerError(RuntimeError):
    """Pioneer could not be reached, or would not return usable JSON."""


@dataclass(frozen=True)
class Route:
    """What the router actually did with one request.

    Kept alongside every result so the app can show which model served a plan
    and what routing saved — the interesting half of using a router at all.
    """

    model: str
    inference_id: str | None = None
    baseline_model: str | None = None
    rate_diff_per_mtok: dict[str, float] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    attempts: int = 1

    @property
    def saved_usd(self) -> float:
        """Dollars this request did not spend, versus the baseline model.

        ``rate_diff_per_mtok`` is the per-million-token rate *difference*
        between the baseline and the routed model, so multiplying it by this
        request's own token counts gives the saving on this call.
        """
        d = self.rate_diff_per_mtok
        return (self.prompt_tokens * d.get("input", 0.0)
                + self.completion_tokens * d.get("output", 0.0)) / 1_000_000

    @property
    def label(self) -> str:
        if not self.baseline_model:
            return self.model
        return f"{self.model} (routed from {self.baseline_model}, saved ${self.saved_usd:.4f})"


def _api_key(explicit: str | None = None) -> str:
    """Env first, Streamlit secrets second — so it works in app and in tests."""
    if explicit:
        return explicit
    if key := os.environ.get("PIONEER_API_KEY"):
        return key
    try:  # optional: only present when running inside Streamlit
        import streamlit as st

        if key := st.secrets.get("PIONEER_API_KEY"):
            return str(key)
    except Exception:  # noqa: BLE001 - no secrets file, no streamlit, no problem
        pass
    raise PioneerError(
        "No Pioneer API key. Set PIONEER_API_KEY in the environment or add it to "
        ".streamlit/secrets.toml."
    )


def _strip_fences(text: str) -> str:
    fence = re.match(r"\s*```(?:json)?\s*(.*?)\s*```\s*$", text, re.DOTALL)
    return fence.group(1) if fence else text


def _first_json_object(text: str) -> str | None:
    """Scan out the first balanced ``{...}`` block, ignoring braces in strings.

    Routed models prepend explanations or append trailing notes often enough
    that a plain ``json.loads`` of the whole message is not reliable.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth, in_string, escaped = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_json_response(text: str) -> dict[str, Any]:
    """Best-effort JSON out of a model message. Raises PioneerError if hopeless."""
    if not text or not text.strip():
        raise PioneerError("Model returned an empty message (likely spent its token budget).")
    for candidate in (_strip_fences(text), text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            block = _first_json_object(candidate)
            if block is None:
                continue
            try:
                parsed = json.loads(block)
            except json.JSONDecodeError:
                continue
        if isinstance(parsed, dict):
            return parsed
    raise PioneerError(f"Could not parse JSON from model output: {text[:300]}…")


class PioneerClient:
    """Thin wrapper over the OpenAI SDK pointed at Pioneer."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        from openai import OpenAI  # imported late: keeps import cost off app start

        self.model = model or os.environ.get("PIONEER_MODEL", AUTO_MODEL)
        self._client = OpenAI(
            base_url=base_url,
            api_key=_api_key(api_key),
            timeout=timeout,
            max_retries=2,  # transport-level: connection resets, 429s, 5xx
        )

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float | None = None,
        attempts: int = 3,
    ) -> tuple[dict[str, Any], Route]:
        """Ask for JSON, parse it, and report how the router served the request.

        Pioneer has no structured-output mode, so an unusable reply is a normal
        outcome rather than an exception, and the two causes need opposite
        responses:

        * **Truncated** (``finish_reason == "length"``) — re-run the original
          request with double the token budget.
        * **Malformed** — hand the model its own output back at the same budget
          and ask for the object alone.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        started = time.monotonic()
        last_error: Exception | None = None
        budget = max_tokens

        for attempt in range(1, attempts + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    max_tokens=budget,
                    **({} if temperature is None else {"temperature": temperature}),
                )
            except Exception as exc:  # noqa: BLE001 - surfaced as PioneerError below
                last_error = exc
                if attempt == attempts:
                    raise PioneerError(f"Pioneer request failed: {exc}") from exc
                time.sleep(1.5 * attempt)
                continue

            choice = response.choices[0]
            text = choice.message.content or ""

            # Truncation is not a formatting mistake — asking the model to "fix
            # its JSON" just truncates again at the same place. Widen the budget
            # and re-run the original request instead.
            if choice.finish_reason == "length":
                last_error = PioneerError(
                    f"Response hit the {budget}-token limit mid-JSON "
                    f"({response.usage.completion_tokens} generated)."
                )
                if attempt == attempts or budget >= MAX_TOKENS_CEILING:
                    break
                budget = min(budget * 2, MAX_TOKENS_CEILING)
                continue

            try:
                payload = parse_json_response(text)
            except PioneerError as exc:
                last_error = exc
                if attempt == attempts:
                    break
                messages += [
                    {"role": "assistant", "content": text[:2000] or "(empty)"},
                    {
                        "role": "user",
                        "content": "That was not valid JSON. Return the JSON object only — "
                                   "no prose, no markdown fences, no trailing commentary.",
                    },
                ]
                continue

            return payload, self._route(response, started, attempt)

        raise PioneerError(f"Pioneer returned unusable JSON after {attempts} attempts: {last_error}")

    @staticmethod
    def _route(response: Any, started: float, attempt: int) -> Route:
        meta = (getattr(response, "model_extra", None) or {}).get("x_pioneer") or {}
        savings = meta.get("savings") or {}
        usage = response.usage
        return Route(
            model=meta.get("routed_model") or response.model,
            inference_id=meta.get("inference_id"),
            baseline_model=savings.get("baseline_model"),
            rate_diff_per_mtok=savings.get("rate_diff_per_mtok") or {},
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_s=round(time.monotonic() - started, 2),
            attempts=attempt,
        )
