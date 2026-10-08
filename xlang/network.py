"""System.io.Network.http — the awaitable ``fetch()`` HTTP client.

``fetch`` is the native half of ``System.io.Network.http``.  The interpreter
exposes it as an asynchronous builtin: calling ``fetch(url, options)`` returns
a coroutine that must be awaited inside an ``async function``.

Design goals (relative to JavaScript's ``fetch``):

- synchronous argument validation, so mistakes surface at the call site even
  before the coroutine is awaited;
- a default timeout, so a dead host can never hang the program forever;
- ``HttpException`` for every failure — DNS, refused connections, TLS,
  timeouts, redirects, invalid JSON — so ``try`` / ``catch (HttpException e)``
  / ``finally`` covers the whole request lifecycle;
- first-class ``userAgent`` support (curl-style) with a sensible default;
- ``throwOnError`` for callers that prefer HTTP error statuses as exceptions;
- no promise ceremony: the response is a plain object with ``status``,
  ``ok``, ``headers``, ``body`` plus ``text()`` / ``json()`` / ``header()``
  helpers.
"""

from __future__ import annotations

import json as _json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import __version__
from .runtime import BuiltinFunction, RuntimeErrorX

__all__ = ["FetchCall", "normalize_fetch_call", "perform_fetch"]

DEFAULT_TIMEOUT = 30.0
DEFAULT_USER_AGENT = f"X/{__version__}"
SUPPORTED_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
OPTION_NAMES = (
    "body",
    "followRedirects",
    "headers",
    "method",
    "query",
    "throwOnError",
    "timeout",
    "userAgent",
    "verifySsl",
)


def _fail(message: str) -> RuntimeErrorX:
    return RuntimeErrorX(message, "HttpException")


class FetchCall:
    """The awaitable value returned by ``fetch()``.

    Behaves like the underlying coroutine when awaited, but stays a distinct
    type so the interpreter can explain an unawaited ``fetch`` clearly — and
    Python never emits its internal "coroutine was never awaited" warning for
    one.  The coroutine itself is only created inside ``__await__``.
    """

    __slots__ = ("_factory",)

    def __init__(self, factory: Any) -> None:
        self._factory = factory

    def __await__(self) -> Any:
        return self._factory().__await__()


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    return type(value).__name__


def _stringify_option_scalar(value: Any, context: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise _fail(f"{context} must be a string, number, or boolean, got {_type_name(value)}")


def normalize_fetch_call(url: Any, options: Any) -> dict[str, Any]:
    """Validate ``fetch(url, options)`` and return normalized request settings.

    Raises ``RuntimeExceptionX``-flavoured ``HttpException`` messages that are
    safe to show a user directly.
    """
    if not isinstance(url, str):
        raise _fail(
            f"fetch(url) expects the url to be a string, got {_type_name(url)}"
        )
    parts = urllib.parse.urlsplit(url)
    if not parts.scheme:
        raise _fail(f"Invalid URL '{url}': include a scheme such as https://")
    if parts.scheme not in ("http", "https"):
        raise _fail(
            f"fetch only supports http and https URLs, "
            f"got '{parts.scheme}' in '{url}'"
        )
    if not parts.netloc:
        raise _fail(f"Invalid URL '{url}': missing a host")

    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise _fail(f"fetch options must be an object, got {_type_name(options)}")
    unknown = sorted(str(key) for key in options if key not in OPTION_NAMES)
    if unknown:
        if len(unknown) == 1:
            prefix = f"Unknown fetch option '{unknown[0]}'"
        else:
            listed = ", ".join(f"'{name}'" for name in unknown)
            prefix = f"Unknown fetch options: {listed}"
        raise _fail(f"{prefix}. Valid options: {', '.join(OPTION_NAMES)}")

    method = options.get("method", "GET")
    if not isinstance(method, str):
        raise _fail(f"fetch method must be a string, got {_type_name(method)}")
    method = method.upper()
    if method not in SUPPORTED_METHODS:
        raise _fail(
            f"Unsupported HTTP method '{method}'. "
            f"Supported methods: {', '.join(SUPPORTED_METHODS)}"
        )

    raw_headers = options.get("headers", {})
    if raw_headers is None:
        raw_headers = {}
    if not isinstance(raw_headers, dict):
        raise _fail(
            f"fetch headers must be an object of string keys, "
            f"got {_type_name(raw_headers)}"
        )
    headers: dict[str, str] = {}
    for key, value in raw_headers.items():
        if not isinstance(key, str):
            raise _fail(f"fetch header names must be strings, got {_type_name(key)}")
        if not key.strip():
            raise _fail("fetch header names cannot be empty")
        if value is None:
            raise _fail(f"fetch header '{key}' has a null value")
        headers[key] = _stringify_option_scalar(value, f"fetch header '{key}'")

    user_agent = options.get("userAgent")
    if user_agent is not None and not isinstance(user_agent, str):
        raise _fail(
            f"fetch userAgent must be a string, got {_type_name(user_agent)}"
        )
    has_user_agent = any(key.lower() == "user-agent" for key in headers)
    if not has_user_agent:
        headers["User-Agent"] = (
            user_agent if user_agent is not None else DEFAULT_USER_AGENT
        )

    body_value = options.get("body")
    body_bytes: bytes | None = None
    if body_value is not None:
        if isinstance(body_value, dict) or isinstance(body_value, list):
            try:
                body_bytes = _json.dumps(body_value).encode("utf-8")
            except (TypeError, ValueError) as error:
                raise _fail(f"fetch body cannot be converted to JSON: {error}")
            if not any(key.lower() == "content-type" for key in headers):
                headers["Content-Type"] = "application/json; charset=utf-8"
        elif isinstance(body_value, str):
            body_bytes = body_value.encode("utf-8")
        else:
            raise _fail(
                f"fetch body must be a string, object, or array, "
                f"got {_type_name(body_value)}"
            )

    query = options.get("query")
    if query is not None:
        if not isinstance(query, dict):
            raise _fail(
                f"fetch query must be an object of key/value pairs, "
                f"got {_type_name(query)}"
            )
        pairs: list[tuple[str, str]] = []
        for key, value in query.items():
            if not isinstance(key, str):
                raise _fail(
                    f"fetch query keys must be strings, got {_type_name(key)}"
                )
            items = value if isinstance(value, list) else [value]
            for item in items:
                if item is None:
                    text = ""
                else:
                    text = _stringify_option_scalar(
                        item, f"fetch query value for '{key}'"
                    )
                pairs.append((key, text))
        encoded = urllib.parse.urlencode(pairs)
        parts = parts._replace(
            query=f"{parts.query}&{encoded}" if parts.query else encoded
        )
        url = urllib.parse.urlunsplit(parts)

    timeout_option = options.get("timeout", DEFAULT_TIMEOUT)
    if timeout_option is None:
        timeout: float | None = None
    elif isinstance(timeout_option, bool) or not isinstance(
        timeout_option, (int, float)
    ):
        raise _fail(
            f"fetch timeout must be a number of seconds (0 disables it), "
            f"got {_type_name(timeout_option)}"
        )
    elif timeout_option < 0:
        raise _fail(f"fetch timeout cannot be negative, got {timeout_option}")
    elif timeout_option == 0:
        timeout = None
    else:
        timeout = float(timeout_option)

    def bool_option(name: str, default: bool) -> bool:
        value = options.get(name, default)
        if not isinstance(value, bool):
            raise _fail(f"fetch {name} must be a boolean, got {_type_name(value)}")
        return value

    return {
        "url": url,
        "method": method,
        "headers": headers,
        "body": body_bytes,
        "timeout": timeout,
        "follow_redirects": bool_option("followRedirects", True),
        "verify_ssl": bool_option("verifySsl", True),
        "throw_on_error": bool_option("throwOnError", False),
    }


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def _timeout_failure(settings: dict[str, Any]) -> RuntimeErrorX:
    timeout = settings["timeout"]
    if timeout is None:
        return _fail(f"Request to '{settings['url']}' timed out")
    return _fail(
        f"Request to '{settings['url']}' timed out after {timeout:g} seconds"
    )


def _connection_failure(settings: dict[str, Any], reason: Any) -> RuntimeErrorX:
    url = settings["url"]
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or url
    try:
        port = parts.port
    except ValueError:
        port = None
    authority = f"{host}:{port}" if port else host
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return _timeout_failure(settings)
    if isinstance(reason, socket.gaierror):
        return _fail(
            f"DNS lookup failed for '{host}': cannot resolve the host name"
        )
    if isinstance(reason, ConnectionRefusedError):
        return _fail(
            f"Cannot reach '{authority}': connection refused (while fetching '{url}')"
        )
    if isinstance(reason, ssl.SSLError):
        return _fail(f"TLS handshake with '{host}' failed: {reason}")
    if isinstance(reason, OSError):
        detail = reason.strerror or str(reason)
        return _fail(
            f"Cannot reach '{authority}': {detail} (while fetching '{url}')"
        )
    return _fail(f"Cannot fetch '{url}': {reason}")


def perform_fetch(url: Any, options: Any) -> dict[str, Any]:
    """Execute one HTTP request and return the response object."""
    settings = normalize_fetch_call(url, options)
    request = urllib.request.Request(
        settings["url"],
        data=settings["body"],
        headers=settings["headers"],
        method=settings["method"],
    )
    handlers: list[Any] = []
    if not settings["follow_redirects"]:
        handlers.append(_NoRedirectHandler())
    if not settings["verify_ssl"]:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=context))
    opener = urllib.request.build_opener(*handlers)

    try:
        response = opener.open(request, timeout=settings["timeout"])
    except urllib.error.HTTPError as error:
        response = error
    except urllib.error.URLError as error:
        raise _connection_failure(settings, error.reason) from None
    except (socket.timeout, TimeoutError):
        raise _timeout_failure(settings) from None
    except ssl.SSLError as error:
        raise _fail(f"TLS handshake failed: {error}") from None
    except ValueError as error:
        raise _fail(f"Invalid URL '{settings['url']}': {error}") from None

    try:
        try:
            data = response.read()
        except (OSError, ValueError):
            data = b""
        status_value = (
            getattr(response, "status", None)
            or getattr(response, "code", None)
            or response.getcode()
            or 0
        )
        status = int(status_value)
        reason = str(getattr(response, "reason", "") or "")
        final_url = str(response.geturl())
        raw_headers = response.headers
    finally:
        response.close()

    if settings["follow_redirects"] and 300 <= status < 400:
        raise _fail(
            f"Redirect failed for '{settings['url']}': "
            f"{reason or 'no reason phrase'} (HTTP {status})"
        )

    header_pairs: dict[str, str] = {}
    for key, value in raw_headers.items():
        lower = key.lower()
        if lower in header_pairs:
            header_pairs[lower] += ", " + value
        else:
            header_pairs[lower] = value

    charset = None
    if hasattr(raw_headers, "get_content_charset"):
        charset = raw_headers.get_content_charset()
    if not charset:
        charset = "utf-8"
    try:
        body_text = data.decode(charset, errors="replace")
    except LookupError:
        body_text = data.decode("utf-8", errors="replace")

    if settings["throw_on_error"] and status >= 400:
        excerpt = " ".join(body_text.split())[:200]
        detail = f": {excerpt}" if excerpt else ""
        raise _fail(
            f"{settings['method']} {settings['url']} failed with "
            f"HTTP {status} {reason}{detail}"
        )

    def response_text(arguments: list[Any]) -> str:
        if arguments:
            raise RuntimeErrorX("response.text() takes no arguments")
        return body_text

    def response_json(arguments: list[Any]) -> Any:
        if arguments:
            raise RuntimeErrorX("response.json() takes no arguments")
        try:
            return _json.loads(body_text)
        except ValueError as error:
            raise _fail(
                f"Response from '{final_url}' is not valid JSON: {error}"
            ) from None

    def response_header(arguments: list[Any]) -> str | None:
        if len(arguments) != 1 or not isinstance(arguments[0], str):
            raise RuntimeErrorX("response.header(name) expects one string argument")
        return header_pairs.get(arguments[0].lower())

    return {
        "status": status,
        "statusText": reason,
        "ok": 200 <= status < 300,
        "url": final_url,
        "headers": dict(header_pairs),
        "body": body_text,
        "bodyBytes": list(data),
        "text": BuiltinFunction("response.text", response_text),
        "json": BuiltinFunction("response.json", response_json),
        "header": BuiltinFunction("response.header", response_header),
    }
