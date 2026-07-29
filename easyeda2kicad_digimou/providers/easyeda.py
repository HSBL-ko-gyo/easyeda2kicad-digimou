from __future__ import annotations

# Global imports
import urllib.error
from typing import Any, Dict, Mapping, Optional, Tuple

from easyeda2kicad_digimou.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad_digimou.metadata.models import CadRecord

# Local imports
from .base import (
    CacheCorruptError,
    InvalidResponseError,
    NetworkError,
    NotFoundError,
    OfflineCacheMissError,
    identity_text,
    optional_text,
)


class EasyedaProvider:
    """Thin CAD-only adapter; EasyEDA remains the sole CAD authority."""

    name = "easyeda"

    def __init__(
        self,
        api: Optional[EasyedaApi] = None,
        *,
        offline: Optional[bool] = None,
        use_cache: bool = False,
    ) -> None:
        if api is None:
            self.api = EasyedaApi(
                use_cache=use_cache or bool(offline),
                offline=bool(offline),
            )
        else:
            self.api = api
            if offline is not None and hasattr(self.api, "offline"):
                self.api.offline = offline

    def _raise_api_error(self, operation: str) -> None:
        error = getattr(self.api, "last_error", None)
        if error == "offline_cache_miss" or (
            getattr(self.api, "offline", False) and not error
        ):
            raise OfflineCacheMissError(self.name, operation=operation)
        if error == "cache_corrupt":
            raise CacheCorruptError(self.name, operation=operation)
        if error == "network_error":
            raise NetworkError(self.name, operation=operation)
        if error == "invalid_response":
            raise InvalidResponseError(self.name, operation=operation)
        raise NotFoundError(self.name, operation=operation)

    @staticmethod
    def _c_para(raw: Mapping[str, Any]) -> Mapping[str, Any]:
        data_str = raw.get("dataStr")
        head = data_str.get("head") if isinstance(data_str, Mapping) else None
        c_para = head.get("c_para") if isinstance(head, Mapping) else None
        return c_para if isinstance(c_para, Mapping) else {}

    @staticmethod
    def _lookup(mapping: Mapping[str, Any], *names: str) -> Optional[str]:
        wanted = {name.casefold() for name in names}
        for key, value in mapping.items():
            if str(key).casefold() in wanted:
                result = optional_text(value)
                if result:
                    return result
        return None

    def _to_record(self, raw: Mapping[str, Any]) -> CadRecord:
        lcsc = raw.get("lcsc")
        lcsc_id = (
            identity_text(lcsc["number"], "lcsc_part_number")
            if isinstance(lcsc, Mapping) and lcsc.get("number") is not None
            else None
        )
        c_para = self._c_para(raw)
        package_detail = raw.get("packageDetail")
        footprint_name = (
            optional_text(package_detail.get("title"))
            if isinstance(package_detail, Mapping)
            else None
        ) or self._lookup(c_para, "Package")

        package_c_para: Mapping[str, Any] = {}
        if isinstance(package_detail, Mapping):
            package_data = package_detail.get("dataStr")
            package_head = (
                package_data.get("head") if isinstance(package_data, Mapping) else None
            )
            candidate = (
                package_head.get("c_para")
                if isinstance(package_head, Mapping)
                else None
            )
            if isinstance(candidate, Mapping):
                package_c_para = candidate

        return CadRecord(
            source=self.name,
            lcsc_part_number=lcsc_id,
            easyeda_component_id=(
                identity_text(raw["uuid"], "easyeda_component_id")
                if raw.get("uuid") is not None
                else None
            ),
            symbol_name=(
                optional_text(raw.get("title")) or self._lookup(c_para, "Name")
            ),
            footprint_name=footprint_name,
            model_3d=self._lookup(
                package_c_para, "3D Model", "3DModel", "3D Model Name"
            ),
            # Identity agreement and pin/pad checks happen above this adapter.
            verification_status="PARTIAL",
        )

    def get_cad_data(self, lcsc_id: str) -> Tuple[CadRecord, Dict[str, Any]]:
        try:
            requested_lcsc_id = identity_text(lcsc_id, "lcsc_part_number")
            raw = self.api.get_cad_data_of_component(requested_lcsc_id)
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="cad-fetch") from None
        except (urllib.error.URLError, OSError):
            raise NetworkError(self.name, operation="cad-fetch") from None
        if not raw:
            self._raise_api_error("cad-fetch")
        if not isinstance(raw, dict):
            raise InvalidResponseError(self.name, operation="cad-fetch")
        try:
            return self._to_record(raw), raw
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="cad-fetch") from None

    def get_cad_record(self, lcsc_id: str) -> Tuple[CadRecord, Dict[str, Any]]:
        return self.get_cad_data(lcsc_id)


EasyEdaProvider = EasyedaProvider

__all__ = ["EasyEdaProvider", "EasyedaProvider"]
