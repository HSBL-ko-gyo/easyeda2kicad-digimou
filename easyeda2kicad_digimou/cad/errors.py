"""Credential-safe failures for local CAD package processing."""

from __future__ import annotations

from typing import Optional


class CadPackageError(RuntimeError):
    """A typed package failure that never includes archive payload contents."""

    def __init__(
        self,
        code: str,
        detail: str,
        relative_path: Optional[str] = None,
    ) -> None:
        self.code = code
        self.detail = detail
        self.relative_path = relative_path
        message = "{0}: {1}".format(code, detail)
        if relative_path:
            message = "{0} [{1}]".format(message, relative_path)
        super().__init__(message)


__all__ = ["CadPackageError"]
