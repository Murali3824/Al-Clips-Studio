"""
LLM Provider Abstraction Layer
==============================

Provides a unified interface for calling any LLM backend so that all
highlight-selection passes communicate with a single ``LLMProvider``
object rather than hardcoding Ollama's REST API.

Adding a new provider
---------------------
1. Subclass ``LLMProvider``.
2. Implement ``is_available()``, ``complete()``, and ``provider_name``.
3. Add an ``elif explicit == "<name>":`` branch in ``get_llm_provider()``.

Current implementations
-----------------------
OllamaProvider
    Calls a locally-running Ollama instance via its REST API.
    Supports any model available via ``ollama pull <model>``.

NullProvider
    Always reports unavailable.  Used when no LLM is configured.
    Every pass that calls ``provider.complete()`` must have a heuristic
    fallback path activated when ``LLMUnavailable`` is raised.

Planned (future phases)
-----------------------
OpenAIProvider  — GPT-4o, GPT-4o-mini, …
AnthropicProvider — Claude 3.5 Sonnet, …
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from typing import Any, Optional

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .* doesn't match a supported version!",
)

try:
    from requests.exceptions import RequestsDependencyWarning  # type: ignore[attr-defined]
    warnings.filterwarnings("ignore", category=RequestsDependencyWarning)
except Exception:
    pass

import requests


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMUnavailable(Exception):
    """
    Raised when the configured LLM provider cannot be reached.

    All pipeline passes must catch this exception and fall back to their
    heuristic implementation path.  Never let this propagate to the
    pipeline orchestrator — partial LLM output is always better than a
    crash.
    """


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """
    Abstract interface for LLM communication.

    All pipeline passes receive an ``LLMProvider`` instance and call
    ``provider.complete(prompt)`` without knowing which backend is active.
    This allows the LLM backend to be swapped via a single settings key
    without modifying any pass code.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if this provider is currently reachable.

        Implementations should prefer a cheap liveness check (e.g. an
        HTTP HEAD or a lightweight ``/api/tags`` endpoint) that completes
        within 2 seconds.  Results MAY be cached between calls within a
        single pipeline run for performance.
        """

    @abstractmethod
    def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """
        Send ``prompt`` to the LLM and return the raw response text.

        Args:
            prompt:      The full prompt string (system role + task + data).
            temperature: Sampling temperature.  Lower = more deterministic.
                         Recommended: 0.2–0.3 for scoring tasks,
                         0.35–0.45 for creative tasks (hook generation).
            max_tokens:  Maximum response tokens.  Keep low for JSON-only
                         responses to avoid padding.

        Returns:
            Raw text string returned by the LLM.  Callers are responsible
            for parsing (typically via ``_clean_json`` helpers in each
            pass module).

        Raises:
            LLMUnavailable: If the provider cannot be reached.
            RuntimeError:   If the provider returns an error response or
                            an empty body.
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Human-readable provider identifier used in log messages and the
        ``source`` / ``model`` fields of ``highlights.json``.

        Examples: ``"ollama/llama3:8b"``, ``"openai/gpt-4o-mini"``,
        ``"anthropic/claude-3-5-sonnet"``, ``"null"``.
        """


# ---------------------------------------------------------------------------
# Concrete: Ollama (local)
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """
    Calls a locally-running Ollama instance via its REST API.

    The Ollama server must be running (``ollama serve``) and the requested
    model must already be pulled (``ollama pull <model>``).

    JSON mode is requested via ``"format": "json"`` in the request body so
    that Ollama constrains its output to valid JSON, reducing parse failures.
    """

    # How long to wait for the liveness check (seconds)
    _AVAILABILITY_TIMEOUT: float = 2.0

    # How long to wait for a generation response (seconds)
    # Set conservatively high — large models on CPU can be slow.
    _GENERATE_TIMEOUT: float = 150.0

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3:8b",
        context_size: int = 8192,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._context_size = context_size
        self._availability_cache: Optional[bool] = None

    def is_available(self) -> bool:
        """
        Ping the Ollama ``/api/tags`` endpoint.

        Result is cached for the lifetime of this provider instance
        to avoid repeated network round-trips during a single pipeline run.
        A fresh instance resets the cache.
        """
        if self._availability_cache is not None:
            return self._availability_cache
        try:
            response = requests.get(
                f"{self._base_url}/api/tags",
                timeout=self._AVAILABILITY_TIMEOUT,
            )
            self._availability_cache = response.ok
        except requests.RequestException:
            self._availability_cache = False
        return self._availability_cache  # type: ignore[return-value]

    def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """Send prompt to Ollama and return response text."""
        if not self.is_available():
            raise LLMUnavailable(
                f"Ollama is not reachable at {self._base_url}. "
                "Ensure the Ollama server is running and the model is pulled."
            )

        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self._context_size,
            },
        }

        try:
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self._GENERATE_TIMEOUT,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            # Reset availability cache so the next call re-checks
            self._availability_cache = None
            raise RuntimeError(
                f"Ollama generate request timed out after {self._GENERATE_TIMEOUT}s. "
                "Consider using a smaller model or increasing the timeout."
            ) from exc
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            ) from exc
        except requests.RequestException as exc:
            self._availability_cache = None
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        raw = response.json().get("response", "")
        if not raw:
            raise RuntimeError(
                "Ollama returned an empty response body. "
                "The model may have stopped generating due to context limits."
            )
        return raw

    @property
    def provider_name(self) -> str:
        return f"ollama/{self._model}"


# ---------------------------------------------------------------------------
# Concrete: Null (heuristic fallback mode)
# ---------------------------------------------------------------------------

class NullProvider(LLMProvider):
    """
    A provider that is always unavailable.

    Use this when no LLM is configured or available.  All pipeline passes
    that call ``provider.complete()`` will receive ``LLMUnavailable`` and
    activate their heuristic fallback path.

    This ensures the pipeline can always produce output, even without any
    LLM backend, while keeping the provider-check logic uniform across all
    passes.
    """

    def is_available(self) -> bool:
        return False

    def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        raise LLMUnavailable(
            "NullProvider is active — no LLM backend is configured. "
            "Pipeline will use heuristic fallback for all LLM-dependent passes."
        )

    @property
    def provider_name(self) -> str:
        return "null"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_provider(settings: dict[str, Any]) -> LLMProvider:
    """
    Instantiate and return the appropriate ``LLMProvider`` for a pipeline job.

    Provider selection logic
    ------------------------
    1. If ``settings["llmProvider"]`` is set explicitly, honour it.
    2. Otherwise default to ``OllamaProvider`` (local inference, no API key
       required, works offline).
    3. If the explicit value is unrecognised, emit a ``UserWarning`` and
       fall back to ``OllamaProvider``.

    Configuration keys consumed from ``settings``
    ----------------------------------------------
    ``llmProvider``  — ``"ollama"`` | ``"null"`` (default: ``"ollama"``)
    ``ollamaUrl``    — Ollama base URL (default: ``"http://localhost:11434"``)
    ``ollamaModel``  — Model name (default: ``"llama3:8b"``)

    Args:
        settings: Pipeline job settings dict from ``context["settings"]``.

    Returns:
        A ready-to-use ``LLMProvider`` instance.
    """
    explicit: str = str(settings.get("llmProvider", "")).lower().strip()
    base_url: str = str(settings.get("ollamaUrl", "http://localhost:11434"))
    model: str = str(settings.get("ollamaModel", "llama3:8b"))

    if explicit in ("ollama", ""):
        return OllamaProvider(base_url=base_url, model=model)

    if explicit == "null":
        return NullProvider()

    warnings.warn(
        f"Unknown llmProvider '{explicit}' in settings. "
        "Falling back to OllamaProvider. "
        "Supported values: 'ollama', 'null'.",
        UserWarning,
        stacklevel=2,
    )
    return OllamaProvider(base_url=base_url, model=model)
