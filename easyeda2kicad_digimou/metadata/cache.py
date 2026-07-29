"""Versioned, provider-scoped JSON cache for distributor metadata."""

from __future__ import annotations

# Global imports
import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Local imports
from .models import model_to_dict, normalize_manufacturer, normalize_mpn

CACHE_SCHEMA_VERSION = 3
DEFAULT_FRESHNESS_SECONDS = 24 * 60 * 60
_KINDS = frozenset(("raw", "normalized"))
_PROVIDER = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_SECRET_NAME = re.compile(
    r"(?:^|_)(?:api_?key|access_?key|private_?key|client_?(?:id|secret)|"
    r"access_?token|refresh_?token|"
    r"authorization|password|credentials?|secret|token)(?:$|_)",
    flags=re.IGNORECASE,
)
_CONCATENATED_SECRET_NAME = re.compile(
    r"(?:api(?:key)|access(?:key|token)|privatekey|client(?:id|secret)|refreshtoken|"
    r"auth(?:token)|bearertoken|idtoken|csrftoken|sessiontoken|"
    r"authorization)(?:header|value)?|password|credentials?|secret|token",
    flags=re.IGNORECASE,
)
_SECRET_NAME_SUFFIXES = (
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
INVALID_URL_PLACEHOLDER = "<invalid-url>"


class CacheError(RuntimeError):
    """Base class for metadata cache diagnostics."""

    category = "CACHE_ERROR"

    def __init__(self, provider: str, cache_key: str, detail: str) -> None:
        self.provider = provider
        self.cache_key = cache_key
        self.detail = detail
        super().__init__(provider, cache_key, detail)

    def __str__(self) -> str:
        return "{0} [{1}] {2}".format(self.provider, self.category, self.detail)


class CacheCorruptError(CacheError):
    category = "CACHE_CORRUPT"


class OfflineCacheMissError(CacheError):
    category = "OFFLINE_CACHE_MISS"


# Short alias used by callers that model the error category as a noun.
OfflineCacheMiss = OfflineCacheMissError


def canonical_request(
    provider: str,
    operation: str,
    mpn: Optional[str] = None,
    manufacturer: Optional[str] = None,
    options: Optional[Mapping[str, Any]] = None,
    schema_version: int = CACHE_SCHEMA_VERSION,
    **public_options: Any,
) -> Dict[str, Any]:
    """Build the non-secret request representation used by the cache key."""

    normalized_provider = _validate_provider(provider)
    if not operation or not str(operation).strip():
        raise ValueError("cache operation must not be empty")
    combined_options: Dict[str, Any] = {}
    if options is not None:
        if not isinstance(options, Mapping):
            raise TypeError("cache options must be a mapping")
        combined_options.update(options)
    combined_options.update(public_options)
    request: Dict[str, Any] = {
        "provider": normalized_provider,
        "operation": str(operation).strip(),
        "schema_version": int(schema_version),
        "mpn_normalized": normalize_mpn(mpn),
        "manufacturer_normalized": normalize_manufacturer(manufacturer),
        "options": combined_options,
    }
    return cast(Dict[str, Any], strip_secrets(request))


def make_cache_key(
    provider: str,
    request: Mapping[str, Any],
    schema_version: int = CACHE_SCHEMA_VERSION,
) -> str:
    """Hash a canonical non-secret request deterministically."""

    normalized_provider = _validate_provider(provider)
    if not isinstance(request, Mapping):
        raise TypeError("cache request must be a mapping")
    canonical = strip_secrets(request)
    payload = {
        "provider": normalized_provider,
        "schema_version": int(schema_version),
        "request": canonical,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


get_cache_key = make_cache_key


def strip_secrets(value: Any) -> Any:
    """Recursively remove credential fields and secret URL query parameters."""

    safe = model_to_dict(value)
    return _redact_configured_secret_values(_strip_json_value(safe))


def redact_configured_secret_text(value: str) -> str:
    """Redact configured provider credential values without exposing them."""

    redacted = value
    for name in (
        "DIGIKEY_CLIENT_ID",
        "DIGIKEY_CLIENT_SECRET",
        "MOUSER_API_KEY",
    ):
        secret = os.environ.get(name, "")
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _redact_configured_secret_values(value: Any) -> Any:
    if isinstance(value, str):
        return redact_configured_secret_text(value)
    if isinstance(value, dict):
        return {
            str(key): _redact_configured_secret_values(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_configured_secret_values(item) for item in value]
    return value


class MetadataCache:
    """Read and write redacted-raw/normalized metadata cache entries.

    Online callers receive ``None`` for missing, stale, or corrupt entries so
    they can refetch.  Offline callers accept stale entries and receive a clear
    error for missing or corrupt data.
    """

    def __init__(
        self,
        root: Union[str, os.PathLike[str]] = ".easyeda_cache/metadata",
        freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
        schema_version: int = CACHE_SCHEMA_VERSION,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if freshness_seconds < 0:
            raise ValueError("freshness_seconds must be non-negative")
        self.root = Path(root)
        self.freshness = timedelta(seconds=freshness_seconds)
        self.schema_version = int(schema_version)
        self._now = now or (lambda: datetime.now(timezone.utc))

    def canonical_request(
        self,
        provider: str,
        operation: str,
        mpn: Optional[str] = None,
        manufacturer: Optional[str] = None,
        options: Optional[Mapping[str, Any]] = None,
        **public_options: Any,
    ) -> Dict[str, Any]:
        return canonical_request(
            provider=provider,
            operation=operation,
            mpn=mpn,
            manufacturer=manufacturer,
            options=options,
            schema_version=self.schema_version,
            **public_options,
        )

    def get_cache_key(self, provider: str, request: Mapping[str, Any]) -> str:
        return make_cache_key(provider, request, self.schema_version)

    def entry_dir(self, provider: str, cache_key: str) -> Path:
        normalized_provider = _validate_provider(provider)
        normalized_key = _validate_cache_key(cache_key)
        return self.root / normalized_provider / normalized_key

    def path(self, provider: str, cache_key: str, kind: str) -> Path:
        _validate_kind(kind)
        return self.entry_dir(provider, cache_key) / "{0}.json".format(kind)

    def read(
        self,
        provider: str,
        cache_key: str,
        kind: str = "normalized",
        offline: bool = False,
        refresh: bool = False,
        validator: Optional[Callable[[Any], Any]] = None,
    ) -> Optional[Any]:
        """Read cached data according to online/offline freshness semantics."""

        normalized_provider = _validate_provider(provider)
        normalized_key = _validate_cache_key(cache_key)
        _validate_kind(kind)
        if offline and refresh:
            raise ValueError("offline and refresh are mutually exclusive")
        if refresh:
            return None
        path = self.path(normalized_provider, normalized_key, kind)
        raw_path = self.path(normalized_provider, normalized_key, "raw")
        if kind == "normalized":
            normalized_exists = path.is_file()
            raw_exists = raw_path.is_file()
            if not normalized_exists and not raw_exists:
                if offline:
                    raise OfflineCacheMissError(
                        normalized_provider,
                        normalized_key,
                        "no usable normalized cache entry",
                    )
                return None
            if not normalized_exists or not raw_exists:
                if offline:
                    raise CacheCorruptError(
                        normalized_provider,
                        normalized_key,
                        "normalized cache evidence pair is incomplete",
                    )
                return None
        elif not path.is_file():
            if offline:
                raise OfflineCacheMissError(
                    normalized_provider,
                    normalized_key,
                    "no usable raw cache entry",
                )
            return None
        try:
            with path.open("r", encoding="utf-8") as stream:
                envelope = json.load(stream)
            self._validate_envelope(envelope, normalized_provider, normalized_key, kind)
            retrieved_at = _parse_timestamp(envelope["retrieved_at"])
            if kind == "normalized":
                with raw_path.open("r", encoding="utf-8") as stream:
                    raw_envelope = json.load(stream)
                self._validate_envelope(
                    raw_envelope,
                    normalized_provider,
                    normalized_key,
                    "raw",
                )
                self._validate_pair(envelope, raw_envelope)
        except (
            OSError,
            json.JSONDecodeError,
            OverflowError,
            ValueError,
            TypeError,
        ) as exc:
            if offline:
                raise CacheCorruptError(
                    normalized_provider,
                    normalized_key,
                    "invalid {0} cache entry: {1}".format(kind, type(exc).__name__),
                ) from None
            return None
        if not offline and self._utc_now() - retrieved_at > self.freshness:
            return None
        data = envelope["data"]
        if validator is not None:
            try:
                data = validator(data)
            except (OverflowError, TypeError, ValueError, KeyError):
                if offline:
                    raise CacheCorruptError(
                        normalized_provider,
                        normalized_key,
                        "normalized cache data failed revalidation",
                    ) from None
                return None
        return data

    def read_raw(
        self,
        provider: str,
        cache_key: str,
        offline: bool = False,
        refresh: bool = False,
    ) -> Optional[Any]:
        return self.read(provider, cache_key, "raw", offline, refresh)

    def read_normalized(
        self,
        provider: str,
        cache_key: str,
        offline: bool = False,
        refresh: bool = False,
        validator: Optional[Callable[[Any], Any]] = None,
    ) -> Optional[Any]:
        return self.read(
            provider,
            cache_key,
            "normalized",
            offline,
            refresh,
            validator,
        )

    def write(
        self,
        provider: str,
        cache_key: str,
        raw: Any,
        normalized: Any,
        request: Optional[Mapping[str, Any]] = None,
        retrieved_at: Optional[Union[str, datetime]] = None,
    ) -> Tuple[Path, Path]:
        """Store a generation-bound redacted-raw/normalized evidence pair."""

        normalized_provider = _validate_provider(provider)
        normalized_key = _validate_cache_key(cache_key)
        timestamp = _format_timestamp(retrieved_at or self._utc_now())
        safe_request = strip_secrets(request or {})
        safe_raw = strip_secrets(raw)
        safe_normalized = strip_secrets(normalized)
        generation_id = secrets.token_hex(16)
        raw_sha256 = _json_sha256(safe_raw)
        raw_envelope = self._make_envelope(
            normalized_provider,
            normalized_key,
            "raw",
            safe_raw,
            safe_request,
            timestamp,
            generation_id,
            raw_sha256,
        )
        normalized_envelope = self._make_envelope(
            normalized_provider,
            normalized_key,
            "normalized",
            safe_normalized,
            safe_request,
            timestamp,
            generation_id,
            raw_sha256,
        )
        raw_path = self.path(normalized_provider, normalized_key, "raw")
        normalized_path = self.path(normalized_provider, normalized_key, "normalized")
        _atomic_json_pair_write(
            raw_path,
            raw_envelope,
            normalized_path,
            normalized_envelope,
        )
        return raw_path, normalized_path

    def write_raw(
        self,
        provider: str,
        cache_key: str,
        data: Any,
        request: Optional[Mapping[str, Any]] = None,
        retrieved_at: Optional[Union[str, datetime]] = None,
    ) -> Path:
        """Write redacted raw data alone, invalidating any normalized pair."""

        return self._write_kind(
            provider,
            cache_key,
            "raw",
            data,
            request,
            _format_timestamp(retrieved_at or self._utc_now()),
        )

    def write_normalized(
        self,
        provider: str,
        cache_key: str,
        data: Any,
        request: Optional[Mapping[str, Any]] = None,
        retrieved_at: Optional[Union[str, datetime]] = None,
    ) -> Path:
        """Write normalized data alone; pair reads reject it until paired."""

        return self._write_kind(
            provider,
            cache_key,
            "normalized",
            data,
            request,
            _format_timestamp(retrieved_at or self._utc_now()),
        )

    def save(
        self,
        provider: str,
        request: Mapping[str, Any],
        raw: Any,
        normalized: Any,
        retrieved_at: Optional[Union[str, datetime]] = None,
    ) -> str:
        """Compute a key, write both forms, and return the cache key."""

        cache_key = self.get_cache_key(provider, request)
        self.write(provider, cache_key, raw, normalized, request, retrieved_at)
        return cache_key

    def load(
        self,
        provider: str,
        request: Mapping[str, Any],
        kind: str = "normalized",
        offline: bool = False,
        refresh: bool = False,
        validator: Optional[Callable[[Any], Any]] = None,
    ) -> Optional[Any]:
        cache_key = self.get_cache_key(provider, request)
        return self.read(provider, cache_key, kind, offline, refresh, validator)

    def _write_kind(
        self,
        provider: str,
        cache_key: str,
        kind: str,
        data: Any,
        request: Optional[Mapping[str, Any]],
        retrieved_at: str,
    ) -> Path:
        normalized_provider = _validate_provider(provider)
        normalized_key = _validate_cache_key(cache_key)
        _validate_kind(kind)
        safe_request = strip_secrets(request or {})
        safe_data = strip_secrets(data)
        generation_id = secrets.token_hex(16)
        raw_sha256 = _json_sha256(safe_data if kind == "raw" else None)
        envelope = self._make_envelope(
            normalized_provider,
            normalized_key,
            kind,
            safe_data,
            safe_request,
            retrieved_at,
            generation_id,
            raw_sha256,
        )
        target = self.path(normalized_provider, normalized_key, kind)
        _atomic_json_write(target, envelope)
        return target

    def _make_envelope(
        self,
        provider: str,
        cache_key: str,
        kind: str,
        data: Any,
        request: Any,
        retrieved_at: str,
        generation_id: str,
        raw_sha256: str,
    ) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": provider,
            "cache_key": cache_key,
            "kind": kind,
            # ``raw.json`` is deliberately a credential-stripped projection,
            # not a byte-for-byte API response.  Make that trust boundary
            # explicit in the on-disk schema while retaining the legacy name.
            "payload_type": "redacted_raw" if kind == "raw" else "normalized",
            "canonical_request": request,
            "retrieved_at": retrieved_at,
            "generation_id": generation_id,
            "raw_sha256": raw_sha256,
            "data": data,
        }

    def _validate_envelope(
        self,
        envelope: Any,
        provider: str,
        cache_key: str,
        kind: str,
    ) -> None:
        if not isinstance(envelope, Mapping):
            raise ValueError("cache envelope is not an object")
        if envelope.get("schema_version") != self.schema_version:
            raise ValueError("unsupported cache schema")
        if envelope.get("provider") != provider:
            raise ValueError("cache provider mismatch")
        if envelope.get("cache_key") != cache_key:
            raise ValueError("cache key mismatch")
        if envelope.get("kind") != kind:
            raise ValueError("cache kind mismatch")
        expected_payload_type = "redacted_raw" if kind == "raw" else "normalized"
        if envelope.get("payload_type") != expected_payload_type:
            raise ValueError("cache payload type mismatch")
        envelope_request = envelope.get("canonical_request")
        if not isinstance(envelope_request, Mapping):
            raise ValueError("canonical request is invalid")
        if make_cache_key(provider, envelope_request, self.schema_version) != cache_key:
            raise ValueError("canonical request does not match cache key")
        generation_id = envelope.get("generation_id")
        if not isinstance(generation_id, str) or not re.fullmatch(
            r"[0-9a-f]{32}", generation_id
        ):
            raise ValueError("cache generation ID is invalid")
        raw_sha256 = envelope.get("raw_sha256")
        if not isinstance(raw_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", raw_sha256
        ):
            raise ValueError("cache raw hash is invalid")
        if "retrieved_at" not in envelope or "data" not in envelope:
            raise ValueError("cache envelope is incomplete")
        if kind == "raw" and _json_sha256(envelope["data"]) != raw_sha256:
            raise ValueError("redacted raw payload hash mismatch")

    @staticmethod
    def _validate_pair(
        normalized_envelope: Mapping[str, Any],
        raw_envelope: Mapping[str, Any],
    ) -> None:
        if normalized_envelope.get("generation_id") != raw_envelope.get(
            "generation_id"
        ):
            raise ValueError("cache generation mismatch")
        if normalized_envelope.get("raw_sha256") != raw_envelope.get("raw_sha256"):
            raise ValueError("cache raw hash binding mismatch")
        if normalized_envelope.get("canonical_request") != raw_envelope.get(
            "canonical_request"
        ):
            raise ValueError("cache request binding mismatch")
        if normalized_envelope.get("retrieved_at") != raw_envelope.get("retrieved_at"):
            raise ValueError("cache timestamp binding mismatch")

    def _utc_now(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime):
            raise TypeError("now() must return datetime")
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _strip_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            if _is_secret_name(key):
                continue
            clean[key] = _strip_json_value(item)
        return clean
    if isinstance(value, list):
        return [_strip_json_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_url(value)
    return value


def sanitize_url(value: str, *, require_http: bool = False) -> str:
    """Remove URL credentials while retaining non-secret public parameters.

    Arbitrary non-URL strings pass through for recursive cache sanitization.
    Callers handling a field that must be a public URL can set
    ``require_http`` so non-HTTP(S) values are rejected as invalid.
    """

    try:
        parsed = urlsplit(value)
    except ValueError:
        if require_http or re.match(r"^\s*https?:", value, flags=re.IGNORECASE):
            return INVALID_URL_PLACEHOLDER
        return value

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return INVALID_URL_PLACEHOLDER if require_http else value
    if not parsed.netloc:
        return INVALID_URL_PLACEHOLDER

    try:
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return INVALID_URL_PLACEHOLDER
    if not hostname:
        return INVALID_URL_PLACEHOLDER
    if ":" in hostname and not hostname.startswith("["):
        hostname = "[{0}]".format(hostname)
    if port is not None:
        hostname = "{0}:{1}".format(hostname, port)

    safe_query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if not _is_secret_name(key):
            safe_query.append((key, item))
    safe_query.sort()
    return urlunsplit(
        (parsed.scheme.lower(), hostname, parsed.path, urlencode(safe_query), "")
    )


def sanitize_public_url(value: Optional[str]) -> Optional[str]:
    """Return a credential-free HTTP(S) URL, or ``None`` when it is invalid."""

    if value is None:
        return None
    sanitized = sanitize_url(str(value), require_http=True)
    if sanitized == INVALID_URL_PLACEHOLDER:
        return None
    return sanitized


def _is_secret_name(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if _SECRET_NAME.search(normalized):
        return True
    compact = normalized.replace("_", "")
    return bool(_CONCATENATED_SECRET_NAME.fullmatch(compact)) or compact.endswith(
        _SECRET_NAME_SUFFIXES
    )


def _validate_provider(provider: str) -> str:
    normalized = str(provider).strip().lower()
    if not _PROVIDER.fullmatch(normalized):
        raise ValueError("invalid cache provider name")
    return normalized


def _validate_cache_key(cache_key: str) -> str:
    normalized = str(cache_key).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError("cache key must be a SHA-256 hex digest")
    return normalized


def _validate_kind(kind: str) -> None:
    if kind not in _KINDS:
        raise ValueError("cache kind must be raw or normalized")


def _format_timestamp(value: Union[str, datetime]) -> str:
    parsed = _parse_timestamp(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime):
        raise ValueError("retrieved_at must be a datetime or ISO-8601 string")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("retrieved_at must be an ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json_temporary(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=".{0}.".format(path.name),
        suffix=".tmp",
        dir=str(path.parent),
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            if temporary.exists():
                temporary.unlink()
            raise
    return temporary


def _atomic_json_write(path: Path, value: Any) -> None:
    temporary: Optional[Path] = None
    try:
        temporary = _write_json_temporary(path, value)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _atomic_json_pair_write(
    raw_path: Path,
    raw_value: Any,
    normalized_path: Path,
    normalized_value: Any,
) -> None:
    """Prepare both files before publishing either generation.

    Two filesystem replacements cannot be one atomic operation.  A crash or
    concurrent writer between replacements can therefore leave a mixed pair,
    but the shared generation/hash binding makes that pair untrusted on read.
    """

    raw_temporary: Optional[Path] = None
    normalized_temporary: Optional[Path] = None
    try:
        raw_temporary = _write_json_temporary(raw_path, raw_value)
        normalized_temporary = _write_json_temporary(normalized_path, normalized_value)
        raw_temporary.replace(raw_path)
        normalized_temporary.replace(normalized_path)
    finally:
        for temporary in (raw_temporary, normalized_temporary):
            if temporary is not None and temporary.exists():
                temporary.unlink()
