from __future__ import annotations

# Global imports
import hashlib
import json
import math
import os
import re
import socket
import time
import urllib.error
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
    runtime_checkable,
)

from easyeda2kicad_digimou.metadata.cache import sanitize_url
from easyeda2kicad_digimou.metadata.models import (
    CadRecord,
    DistributorRecord,
    identity_text,
    normalize_manufacturer,
    normalize_mpn,
)


class ProviderError(RuntimeError):
    """A deliberately terse, credential-safe provider failure."""

    code = "PROVIDER_ERROR"

    def __init__(
        self,
        provider: str,
        status: Optional[int] = None,
        operation: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.status = status
        self.operation = operation
        parts = [provider, self.code]
        if operation:
            parts.append(operation)
        if status is not None:
            parts.append("HTTP %d" % status)
        self._safe_message = ": ".join(parts)
        # Retain all constructor values in ``args`` so copy/pickle can rebuild
        # the exception without ever storing transport exception text.
        super().__init__(provider, status, operation)

    def __str__(self) -> str:
        return self._safe_message

    @property
    def category(self) -> str:
        return self.code


class NotFoundError(ProviderError):
    code = "NOT_FOUND"


class AmbiguousMatchError(ProviderError):
    code = "AMBIGUOUS"


class AuthMissingError(ProviderError):
    code = "AUTH_MISSING"


class AuthFailedError(ProviderError):
    code = "AUTH_FAILED"


class RateLimitedError(ProviderError):
    code = "RATE_LIMITED"


class NetworkError(ProviderError):
    code = "NETWORK_ERROR"


class InvalidResponseError(ProviderError):
    code = "INVALID_RESPONSE"


class CacheCorruptError(ProviderError):
    code = "CACHE_CORRUPT"


class OfflineCacheMissError(ProviderError):
    code = "OFFLINE_CACHE_MISS"


class MpnMismatchError(ProviderError):
    code = "MPN_MISMATCH"


# Descriptive compatibility aliases for callers that prefer the long names.
AuthenticationMissingError = AuthMissingError
AuthenticationFailedError = AuthFailedError
RateLimitError = RateLimitedError
MPNMismatchError = MpnMismatchError


@dataclass(frozen=True)
class AuthRequirements:
    required_environment_variables: Tuple[str, ...] = ()
    optional_environment_variables: Tuple[str, ...] = ()
    help_url: Optional[str] = None

    @property
    def required_env(self) -> Tuple[str, ...]:
        return self.required_environment_variables

    @property
    def optional_env(self) -> Tuple[str, ...]:
        return self.optional_environment_variables


@runtime_checkable
class MetadataProvider(Protocol):
    name: str

    def search_exact_mpn(
        self, manufacturer: Optional[str], mpn: str
    ) -> DistributorRecord:
        raise NotImplementedError

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        raise NotImplementedError

    def normalize_response(
        self, response: Mapping[str, Any]
    ) -> List[DistributorRecord]:
        raise NotImplementedError

    def validate_exact_match(
        self,
        candidates: Sequence[DistributorRecord],
        manufacturer: Optional[str],
        mpn: str,
    ) -> DistributorRecord:
        raise NotImplementedError

    def get_cache_key(self, request: Mapping[str, Any]) -> str:
        raise NotImplementedError

    def get_cache_context(self) -> Mapping[str, str]:
        raise NotImplementedError

    def describe_auth_requirements(self) -> AuthRequirements:
        raise NotImplementedError


@runtime_checkable
class CadProvider(Protocol):
    name: str

    def get_cad_data(self, lcsc_id: str) -> Tuple[CadRecord, Dict[str, Any]]:
        raise NotImplementedError


Opener = Union[Callable[..., Any], Any]
Sleeper = Callable[[float], None]
Clock = Callable[[], float]


_SECRET_KEY_COMPACT_RE = re.compile(
    r"(?:apikey|client(?:id|secret)|access(?:key|token)|refresh(?:key|token)|"
    r"authorization(?:header|value)?|password|credentials?|secret|token)",
    re.IGNORECASE,
)
_SECRET_KEY_SUFFIXES = (
    "apikey",
    "accesskey",
    "privatekey",
    "clientid",
    "clientsecret",
    "accesstoken",
    "refreshtoken",
    "authtoken",
    "bearertoken",
    "idtoken",
    "csrftoken",
    "sessiontoken",
    "authorization",
    "authorizationheader",
    "authorizationvalue",
    "password",
    "credential",
    "credentials",
    "secret",
    "token",
)


def _is_secret_key(value: str) -> bool:
    compact = re.sub(r"[^a-z0-9]+", "", value.casefold())
    return bool(_SECRET_KEY_COMPACT_RE.fullmatch(compact)) or compact.endswith(
        _SECRET_KEY_SUFFIXES
    )


def _safe_url(value: str) -> str:
    """Remove secret-bearing query parameters before canonicalization."""

    return sanitize_url(value)


def _without_secrets(value: Any, key: str = "") -> Any:
    if key and _is_secret_key(key):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {
            str(item_key): _without_secrets(item_value, str(item_key))
            for item_key, item_value in sorted(
                value.items(), key=lambda pair: str(pair[0])
            )
        }
    if isinstance(value, (list, tuple)):
        return [_without_secrets(item) for item in value]
    if isinstance(value, str):
        normalized_key = "".join(
            character for character in key.casefold() if character.isalnum()
        )
        if normalized_key in ("mpn", "manufacturerpartnumber"):
            return normalize_mpn(value)
        if normalized_key in ("manufacturer", "manufacturername"):
            return normalize_manufacturer(value)
        return _safe_url(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def canonical_request(provider: str, request: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the non-secret canonical request used for cache identity."""

    return {
        "provider": provider,
        "request": _without_secrets(request),
    }


def make_cache_key(provider: str, request: Mapping[str, Any]) -> str:
    payload = json.dumps(
        canonical_request(provider, request),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class BaseMetadataProvider:
    """Shared exact matching, safe HTTP handling, and retry behavior."""

    name = "provider"
    retry_statuses = frozenset((429, 500, 502, 503, 504))
    max_attempts = 3
    max_retry_after: float = 30.0

    def __init__(
        self,
        *,
        opener: Optional[Opener] = None,
        sleeper: Sleeper = time.sleep,
        clock: Clock = time.time,
        env: Optional[Mapping[str, str]] = None,
        timeout: float = 30.0,
    ) -> None:
        self._opener = opener
        self._sleeper = sleeper
        self._clock = clock
        self._env = env if env is not None else os.environ
        self.timeout = timeout
        self.last_raw_response: Optional[Dict[str, Any]] = None

    def describe_auth_requirements(self) -> AuthRequirements:
        return AuthRequirements()

    def get_cache_key(self, request: Mapping[str, Any]) -> str:
        cache_request = dict(request)
        cache_request["provider_context"] = dict(self.get_cache_context())
        return make_cache_key(self.name, cache_request)

    def get_cache_context(self) -> Mapping[str, str]:
        return {}

    def validate_exact_match(
        self,
        candidates: Sequence[DistributorRecord],
        manufacturer: Optional[str],
        mpn: str,
    ) -> DistributorRecord:
        try:
            requested_mpn = normalize_mpn(identity_text(mpn, "mpn"))
            requested_manufacturer = normalize_manufacturer(
                identity_text(manufacturer, "manufacturer")
                if manufacturer is not None
                else None
            )
        except (OverflowError, TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="exact-match") from None
        exact: List[DistributorRecord] = []
        for candidate in candidates:
            if not candidate.mpn or normalize_mpn(candidate.mpn) != requested_mpn:
                continue
            if (
                requested_manufacturer
                and normalize_manufacturer(candidate.manufacturer)
                != requested_manufacturer
            ):
                continue
            exact.append(candidate)

        if not exact:
            raise NotFoundError(self.name, operation="exact-match")

        identities = {
            (
                normalize_manufacturer(item.manufacturer),
                normalize_mpn(item.mpn),
            )
            for item in exact
        }
        if len(identities) != 1:
            raise AmbiguousMatchError(self.name, operation="exact-match")

        return sorted(exact, key=self._candidate_preference)[0]

    def _normalize_exact_candidates(
        self,
        raw_candidates: Sequence[Mapping[str, Any]],
        requested_mpn: str,
        *,
        get_raw_mpn: Callable[[Mapping[str, Any]], Any],
        parse_record: Callable[[Mapping[str, Any]], Optional[DistributorRecord]],
    ) -> List[DistributorRecord]:
        """Parse exact candidates without inferring uniqueness from dropped data.

        A candidate whose raw MPN proves a mismatch is irrelevant to this exact
        query and need not satisfy the rest of the record schema. Missing,
        malformed, or exact raw MPN evidence remains potentially relevant and
        therefore fails the whole response if a complete record cannot be
        produced.
        """

        try:
            normalized_request = normalize_mpn(
                identity_text(requested_mpn, "requested_mpn")
            )
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="exact-normalize") from None
        if not normalized_request:
            raise InvalidResponseError(self.name, operation="exact-normalize")

        records: List[DistributorRecord] = []
        for raw_candidate in raw_candidates:
            try:
                normalized_candidate = normalize_mpn(
                    identity_text(get_raw_mpn(raw_candidate), "candidate_mpn")
                )
            except (OverflowError, TypeError, ValueError):
                raise InvalidResponseError(
                    self.name, operation="exact-normalize"
                ) from None
            if not normalized_candidate:
                raise InvalidResponseError(self.name, operation="exact-normalize")
            if normalized_candidate != normalized_request:
                continue

            try:
                record = parse_record(raw_candidate)
            except (OverflowError, TypeError, ValueError):
                raise InvalidResponseError(
                    self.name, operation="exact-normalize"
                ) from None
            if record is None:
                raise InvalidResponseError(self.name, operation="exact-normalize")
            try:
                normalized_record = normalize_mpn(
                    identity_text(record.mpn, "record_mpn")
                )
            except (OverflowError, TypeError, ValueError):
                raise InvalidResponseError(
                    self.name, operation="exact-normalize"
                ) from None
            if normalized_record != normalized_candidate:
                raise InvalidResponseError(self.name, operation="exact-normalize")
            records.append(record)
        return records

    @staticmethod
    def _candidate_preference(record: DistributorRecord) -> Tuple[int, str]:
        moq = record.minimum_order_quantity
        return (
            moq if moq is not None else 2**63 - 1,
            (record.distributor_part_number or "").casefold(),
        )

    def _call_opener(self, request: urllib.request.Request) -> Any:
        if self._opener is None:
            return urllib.request.urlopen(request, timeout=self.timeout)  # noqa: S310
        if hasattr(self._opener, "open"):
            return self._opener.open(request, timeout=self.timeout)
        return self._opener(request, timeout=self.timeout)

    @staticmethod
    def _status_of(response: Any) -> int:
        status = getattr(response, "status", None)
        if status is None and hasattr(response, "getcode"):
            status = response.getcode()
        return int(status or 200)

    @staticmethod
    def _header(headers: Any, name: str) -> Optional[str]:
        if headers is None:
            return None
        try:
            value = headers.get(name)
        except (AttributeError, TypeError):
            return None
        return str(value) if value is not None else None

    def _retry_delay(self, attempt: int, headers: Any) -> float:
        retry_after = self._header(headers, "Retry-After")
        if retry_after is not None:
            try:
                seconds = float(retry_after)
            except ValueError:
                pass
            else:
                return max(0.0, min(seconds, self.max_retry_after))
        return min(0.5 * (2.0**attempt), self.max_retry_after)

    def _raise_http_error(
        self,
        status: int,
        operation: str,
        auth_statuses: Sequence[int],
    ) -> None:
        if status in auth_statuses:
            raise AuthFailedError(self.name, status=status, operation=operation)
        if status == 429:
            raise RateLimitedError(self.name, status=status, operation=operation)
        raise NetworkError(self.name, status=status, operation=operation)

    def _request_json(
        self,
        request: urllib.request.Request,
        *,
        operation: str,
        auth_statuses: Sequence[int] = (401, 403),
    ) -> Dict[str, Any]:
        for attempt in range(self.max_attempts):
            response = None
            try:
                response = self._call_opener(request)
                status = self._status_of(response)
                headers = getattr(response, "headers", None)
                body = response.read()
                if status >= 400:
                    if (
                        status in self.retry_statuses
                        and attempt + 1 < self.max_attempts
                    ):
                        self._sleeper(self._retry_delay(attempt, headers))
                        continue
                    self._raise_http_error(status, operation, auth_statuses)
            except urllib.error.HTTPError as error:
                status = int(error.code)
                try:
                    if (
                        status in self.retry_statuses
                        and attempt + 1 < self.max_attempts
                    ):
                        self._sleeper(self._retry_delay(attempt, error.headers))
                        continue
                    self._raise_http_error(status, operation, auth_statuses)
                finally:
                    # A few Python/urllib combinations expose an HTTPError
                    # without a usable backing file object. Cleanup must not
                    # replace the deliberately sanitized provider exception.
                    with suppress(Exception):
                        error.close()
            except (urllib.error.URLError, socket.timeout, OSError):
                if attempt + 1 < self.max_attempts:
                    self._sleeper(self._retry_delay(attempt, None))
                    continue
                raise NetworkError(self.name, operation=operation) from None
            except (TypeError, ValueError):
                # urllib can include a full request URL in these exceptions;
                # replace it so a Mouser query-string key cannot escape.
                raise InvalidResponseError(self.name, operation=operation) from None
            finally:
                if response is not None and hasattr(response, "close"):
                    with suppress(Exception):
                        response.close()

            try:
                decoded = body.decode("utf-8") if isinstance(body, bytes) else body
                payload = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                raise InvalidResponseError(self.name, operation=operation) from None
            if not isinstance(payload, dict):
                raise InvalidResponseError(self.name, operation=operation)
            return payload

        # The loop always returns or raises; this protects future refactors.
        raise NetworkError(self.name, operation=operation)


def optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("integer value must be finite")
        try:
            return int(value)
        except OverflowError:
            raise ValueError("integer value is out of range") from None
    text = str(value).strip().replace(",", "")
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except (OverflowError, ValueError):
        return None


def parse_result_count(value: Any) -> Optional[int]:
    """Parse an optional official result total without permissive coercion."""

    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("result count must be a non-negative integer")
    if isinstance(value, int):
        count = value
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text.isdecimal():
            raise ValueError("result count must be a non-negative integer")
        count = int(text)
    else:
        raise ValueError("result count must be a non-negative integer")
    if count < 0:
        raise ValueError("result count must be a non-negative integer")
    return count


def optional_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:
            raise ValueError("floating-point value is out of range") from None
        if not math.isfinite(number):
            raise ValueError("floating-point value must be finite")
        return number
    text = str(value).strip().replace(",", "")
    match = re.search(r"-?(?:\d+(?:\.\d*)?|\.\d+)", text)
    if not match:
        return None
    try:
        number = float(match.group(0))
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(number):
        raise ValueError("floating-point value must be finite")
    return number


__all__ = [
    "AmbiguousMatchError",
    "AuthFailedError",
    "AuthMissingError",
    "AuthRequirements",
    "AuthenticationFailedError",
    "AuthenticationMissingError",
    "BaseMetadataProvider",
    "CacheCorruptError",
    "CadProvider",
    "InvalidResponseError",
    "MetadataProvider",
    "MPNMismatchError",
    "MpnMismatchError",
    "NetworkError",
    "NotFoundError",
    "OfflineCacheMissError",
    "ProviderError",
    "RateLimitError",
    "RateLimitedError",
    "canonical_request",
    "identity_text",
    "make_cache_key",
    "optional_float",
    "optional_int",
    "optional_text",
    "parse_result_count",
]
