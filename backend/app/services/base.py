"""Base service client for all external API integrations.

Provides a shared HTTP client foundation with connection pooling, error
handling, logging, and retry semantics.  Every concrete service client
should inherit from :class:`BaseServiceClient`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------

class ServiceError(Exception):
    """Base exception for all service-layer errors."""

    def __init__(self, service: str, message: str, status_code: int | None = None):
        self.service = service
        self.status_code = status_code
        super().__init__(f"[{service}] {message}")


class ServiceConnectionError(ServiceError):
    """Raised when a service is unreachable."""


class ServiceAuthenticationError(ServiceError):
    """Raised when authentication with a service fails (401/403)."""


class ServiceNotFoundError(ServiceError):
    """Raised when the requested resource does not exist (404)."""


class ServiceValidationError(ServiceError):
    """Raised when the service rejects the request payload (400/422)."""


class ServiceUnavailableError(ServiceError):
    """Raised when the service returns a 5xx error."""


# ---------------------------------------------------------------------------
# Base client
# ---------------------------------------------------------------------------

class BaseServiceClient:
    """Base class for all API service clients.

    Provides:
    * Lazy-initialised :class:`httpx.AsyncClient` with connection pooling.
    * Centralised ``_request`` helper with structured logging, status-code
      mapping to custom exceptions, and automatic JSON parsing.
    * A ``close`` coroutine for clean shutdown.

    Subclasses **must** implement ``_get_headers`` if they require custom
    authentication headers beyond what is set in the base client.
    """

    def __init__(self, url: str, service_name: str, timeout: float = 30.0) -> None:
        self.base_url: str = url.rstrip("/")
        self.service_name: str = service_name
        self.timeout: float = timeout
        self.logger: logging.Logger = logging.getLogger(f"arrclean.services.{service_name}")
        self._client: httpx.AsyncClient | None = None

    # -- Client lifecycle ----------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared :class:`httpx.AsyncClient`, creating it if needed."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers=self._get_headers(),
                follow_redirects=True,
            )
        return self._client

    def _get_headers(self) -> dict[str, str]:
        """Return default headers for every request.  Override in subclasses."""
        return {}

    async def close(self) -> None:
        """Gracefully close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self.logger.debug("HTTP client closed")

    # -- Request helpers -----------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        parse_json: bool = True,
        raise_for_status: bool = True,
        **kwargs: Any,
    ) -> Any:
        """Execute an HTTP request with logging and error handling.

        Parameters
        ----------
        method:
            HTTP method (``GET``, ``POST``, ``PUT``, ``DELETE``).
        path:
            URL path relative to ``base_url``.
        parse_json:
            If ``True`` (default), parse the response body as JSON and return it.
            If ``False``, return the raw :class:`httpx.Response`.
        raise_for_status:
            If ``True`` (default), raise a :class:`ServiceError` subclass on
            non-2xx responses.
        **kwargs:
            Forwarded to :meth:`httpx.AsyncClient.request` (e.g. ``params``,
            ``json``, ``data``, ``headers``).

        Returns
        -------
        Any
            Parsed JSON (``dict`` / ``list``) or raw :class:`httpx.Response`.

        Raises
        ------
        ServiceConnectionError
            When the service is unreachable.
        ServiceAuthenticationError
            On 401 / 403 responses.
        ServiceNotFoundError
            On 404 responses.
        ServiceValidationError
            On 400 / 422 responses.
        ServiceUnavailableError
            On 5xx responses.
        ServiceError
            On any other non-2xx response.
        """
        self.logger.debug("%s %s %s", method, path, kwargs.get("params", ""))
        client = await self._get_client()

        try:
            response = await client.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise ServiceConnectionError(
                self.service_name,
                f"Failed to connect to {self.base_url}{path}: {exc}",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ServiceConnectionError(
                self.service_name,
                f"Request timed out: {method} {path}",
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceError(
                self.service_name,
                f"HTTP error during {method} {path}: {exc}",
            ) from exc

        if raise_for_status and not response.is_success:
            self._raise_for_status(response, path)

        if not parse_json:
            return response

        # Some endpoints return empty bodies on success (e.g. DELETE)
        if response.status_code == 204 or not response.content:
            return None

        try:
            return response.json()
        except Exception as exc:
            self.logger.warning(
                "Failed to parse JSON from %s %s (status %s): %s",
                method,
                path,
                response.status_code,
                exc,
            )
            raise ServiceError(
                self.service_name,
                f"Invalid JSON response from {method} {path}",
                status_code=response.status_code,
            ) from exc

    def _raise_for_status(self, response: httpx.Response, path: str) -> None:
        """Map HTTP status codes to domain-specific exceptions."""
        status = response.status_code
        body = response.text[:500]

        if status in (401, 403):
            raise ServiceAuthenticationError(
                self.service_name,
                f"Authentication failed ({status}) for {path}: {body}",
                status_code=status,
            )
        if status == 404:
            raise ServiceNotFoundError(
                self.service_name,
                f"Resource not found (404) at {path}",
                status_code=status,
            )
        if status in (400, 422):
            raise ServiceValidationError(
                self.service_name,
                f"Validation error ({status}) for {path}: {body}",
                status_code=status,
            )
        if 500 <= status < 600:
            raise ServiceUnavailableError(
                self.service_name,
                f"Server error ({status}) for {path}: {body}",
                status_code=status,
            )

        raise ServiceError(
            self.service_name,
            f"Unexpected status {status} for {path}: {body}",
            status_code=status,
        )
