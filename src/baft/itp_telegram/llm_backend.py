"""LM Studio shim for ``heddle.contrib.rag.analysis.llm_analyzers.LLMBackend``.

Heddle's analyzer ``LLMBackend`` only knows ``ollama:`` and
``anthropic:`` model prefixes (it does an Ollama-shaped POST to
``/api/chat``). LM Studio speaks the OpenAI Chat Completions schema at
``/v1/chat/completions``, so we override ``complete()`` to talk to it
directly while preserving the analyzer's retry semantics.

Also handles the ``reasoning_content`` rescue for thinking models
(qwen3.x, deepseek-r1, etc.) — LM Studio puts the visible answer there
when ``content`` is empty.
"""

from __future__ import annotations

import logging
import time

import requests

from heddle.contrib.rag.analysis.llm_analyzers import (
    _MAX_RETRIES,
    _RETRY_DELAY_S,
    LLMBackend,
)

logger = logging.getLogger(__name__)


class LMStudioLLMBackend(LLMBackend):
    """``LLMBackend`` that targets an LM Studio (or OpenAI-compatible) server.

    Drop-in replacement for the analyzer's default ``LLMBackend``. Use
    in place of the parent class when the analyzer should run against
    LM Studio rather than Ollama or Anthropic.

    Args:
        model: Model identifier as listed by LM Studio's ``/v1/models``
            (e.g. ``"qwen/qwen3.6-35b-a3b"``).
        base_url: LM Studio base URL (with or without trailing ``/v1``;
            normalized to include ``/v1``).
        temperature: Sampling temperature (default 0.1, matches parent).
        max_tokens: Max output tokens.
        api_key: Sent as a Bearer token; LM Studio ignores it.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:1234/v1",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        api_key: str = "not-needed",
    ) -> None:
        # Bypass parent's prefix detection — we own the backend.
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        normalized = base_url.rstrip("/")
        if not normalized.endswith("/v1"):
            normalized = normalized + "/v1"
        self._base_url = normalized
        self._api_key = api_key
        self._backend = "lmstudio"
        self._model_name = model
        self._anthropic_client = None  # parent attribute, unused here

    def complete(self, system: str, user: str) -> str:
        """OpenAI-compatible chat completion with the same retry shape."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return self._lmstudio_complete(system, user)
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "LM Studio call attempt %d failed (%s), retrying in %.1fs",
                        attempt + 1,
                        exc,
                        _RETRY_DELAY_S,
                    )
                    time.sleep(_RETRY_DELAY_S)
        logger.error("LM Studio call failed after %d attempts: %s", _MAX_RETRIES, last_exc)
        return "{}"

    def _lmstudio_complete(self, system: str, user: str) -> str:
        resp = requests.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": False,
            },
            timeout=300,
        )
        if not resp.ok:
            # Surface the response body — LM Studio's 400s carry useful detail
            # (model not loaded, context overflow, etc.) that bare HTTPError loses.
            body = resp.text[:1000] if resp.text else "(empty body)"
            logger.error(
                "lmstudio.http_error status=%d model=%s body=%s",
                resp.status_code,
                self._model_name,
                body,
            )
            resp.raise_for_status()  # re-raise after logging
        payload = resp.json()
        message = payload["choices"][0]["message"]
        finish_reason = payload["choices"][0].get("finish_reason")
        # Thinking models put the answer on reasoning_content when content is empty.
        content = message.get("content") or ""
        if not content.strip():
            content = message.get("reasoning_content") or ""
            if content.strip():
                logger.info(
                    "lmstudio.reasoning_content.rescue model=%s finish=%s",
                    self._model_name,
                    finish_reason,
                )
        # If the model exhausted its token budget on reasoning, warn loudly —
        # the JSON-mode parsers downstream will get garbage or empty.
        if finish_reason == "length" and not content.strip():
            logger.warning(
                "lmstudio.budget_exhausted model=%s — output empty after %s tokens. "
                "Either raise max_tokens or use a non-thinking model.",
                self._model_name,
                self.max_tokens,
            )
        return content
