"""Small OpenAI-compatible HTTP client. All calls stay on the server."""

import ipaddress
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from apps.common.crypto import decrypt


class ProviderError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post(path: str, payload: dict, *, config, timeout: int = 20) -> dict:
    key = decrypt(config.api_key_encrypted)
    if not key:
        raise ProviderError("not_configured")
    base = config.base_url.rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ProviderError("invalid_provider_url")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
            raise ProviderError("invalid_provider_url")
    except (OSError, ValueError):
        raise ProviderError("invalid_provider_url") from None
    request = Request(  # noqa: S310 - admin-configured URL is validated as HTTPS above
        f"{base}/{path.lstrip('/')}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:  # noqa: S310 - HTTPS provider URL is validated above
            data = json.loads(response.read(2_000_000))
    except HTTPError as exc:
        raise ProviderError(
            "provider_rejected_request" if exc.code < 500 else "provider_unavailable"
        ) from None
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError):
        raise ProviderError("provider_unavailable") from None
    if not isinstance(data, dict):
        raise ProviderError("provider_invalid_response")
    return data


def embed(text: str, *, config) -> list[float]:
    data = _post("embeddings", {"model": config.embedding_model, "input": text[:8000]}, config=config)
    try:
        values = data["data"][0]["embedding"]
        if not isinstance(values, list) or len(values) > 10000:
            raise ValueError
        return [float(value) for value in values]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ProviderError("provider_invalid_response") from None


def complete(messages: list[dict], *, config) -> tuple[str, dict]:
    data = _post(
        "chat/completions",
        {
            "model": config.model,
            "messages": messages,
            "temperature": float(config.temperature),
            "max_tokens": config.max_response_tokens,
        },
        config=config,
    )
    try:
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError
        usage = data.get("usage") or {}
        return content.strip()[:10000], {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }
    except (KeyError, IndexError, TypeError, ValueError):
        raise ProviderError("provider_invalid_response") from None
