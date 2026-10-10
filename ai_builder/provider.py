"""Bounded server-side AI access for SaaSsum website generation."""

from dataclasses import dataclass
import socket
from typing import Callable

from django.conf import settings
from django.core.cache import cache

from dispatch import groq_client
from dispatch.config import is_groq_configured


class WebsiteProviderError(RuntimeError):
    """Recoverable provider failure safe to expose through the builder API."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


class WebsiteProviderUnavailable(WebsiteProviderError):
    def __init__(self):
        super().__init__(
            "Website generation is unavailable. Check the Groq configuration and try again.",
            code="provider_unavailable",
        )


class WebsiteProviderRateLimited(WebsiteProviderError):
    def __init__(self):
        super().__init__(
            "Website generation is temporarily rate limited. Please try again shortly.",
            code="rate_limited",
        )


class WebsiteProviderMalformedResponse(WebsiteProviderError):
    def __init__(self):
        super().__init__(
            "The AI service returned an invalid website response. Please try again.",
            code="malformed_response",
        )


@dataclass(frozen=True)
class WebsiteProviderSettings:
    timeout_seconds: float = 30.0
    max_output_chars: int = 50_000
    rate_limit: int = 10
    rate_window_seconds: int = 60

    @classmethod
    def from_django(cls) -> "WebsiteProviderSettings":
        return cls(
            timeout_seconds=float(getattr(settings, "SAASSUM_GROQ_TIMEOUT_SECONDS", 30.0)),
            max_output_chars=int(getattr(settings, "SAASSUM_GROQ_MAX_OUTPUT_CHARS", 50_000)),
            rate_limit=int(getattr(settings, "SAASSUM_GROQ_RATE_LIMIT", 10)),
            rate_window_seconds=int(getattr(settings, "SAASSUM_GROQ_RATE_WINDOW_SECONDS", 60)),
        )


class WebsiteAIProvider:
    """Small provider interface that never sends credentials to the browser."""

    def __init__(
        self,
        chat: Callable[..., dict] | None = None,
        config: WebsiteProviderSettings | None = None,
    ):
        self._chat = chat or groq_client.chat
        self._uses_injected_chat = chat is not None
        self.config = config or WebsiteProviderSettings.from_django()

    def generate_json(
        self,
        *,
        messages: list[dict],
        actor_key: str,
        max_tokens: int,
        model: str | None = None,
    ) -> dict:
        self._check_rate_limit(actor_key)
        if not self._uses_injected_chat and not is_groq_configured():
            raise WebsiteProviderUnavailable()
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")

        try:
            response = self._chat(
                messages=messages,
                model=model or groq_client.DEFAULT_MODEL,
                temperature=0.2,
                max_tokens=min(max_tokens, 5_000),
                timeout=self.config.timeout_seconds,
            )
        except (TimeoutError, socket.timeout) as error:
            raise WebsiteProviderError(
                "The AI service timed out. Please try again.",
                code="timeout",
            ) from error
        except WebsiteProviderError:
            raise
        except Exception as error:
            message = str(error).lower()
            if "429" in message or "rate_limit" in message:
                raise WebsiteProviderRateLimited() from error
            if "timeout" in message or "timed out" in message:
                raise WebsiteProviderError(
                    "The AI service timed out. Please try again.",
                    code="timeout",
                ) from error
            raise WebsiteProviderError(
                "The AI service could not complete the request. Please try again.",
                code="provider_error",
            ) from error

        if not isinstance(response, dict):
            raise WebsiteProviderMalformedResponse()
        content = response.get("content")
        if not isinstance(content, str) or not content.strip():
            raise WebsiteProviderMalformedResponse()
        if len(content) > self.config.max_output_chars:
            raise WebsiteProviderError(
                "The AI response exceeded the website size limit. Please try again.",
                code="output_too_large",
            )
        return response

    def _check_rate_limit(self, actor_key: str) -> None:
        if not isinstance(actor_key, str) or not actor_key.strip():
            raise ValueError("actor_key is required")
        key = f"saassum:provider-rate:{actor_key.strip()}"
        try:
            current = cache.get(key, 0)
            if current >= self.config.rate_limit:
                raise WebsiteProviderRateLimited()
            if not cache.add(key, 1, timeout=self.config.rate_window_seconds):
                cache.incr(key)
        except WebsiteProviderRateLimited:
            raise
        except Exception:
            # A cache outage must not silently bypass the configured limit.
            raise WebsiteProviderError(
                "Website generation is temporarily unavailable. Please try again.",
                code="rate_limit_unavailable",
            )


class MockWebsiteAIProvider(WebsiteAIProvider):
    """Deterministic local/test provider; it never contacts Groq."""

    def __init__(self, response: dict):
        self.response = response
        self.config = WebsiteProviderSettings()

    def generate_json(self, **kwargs) -> dict:
        return self.response
