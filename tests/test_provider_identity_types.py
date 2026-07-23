from __future__ import annotations

# Global imports
import copy
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from easyeda2kicad.providers import (
    DigiKeyProvider,
    EasyedaProvider,
    InvalidResponseError,
    LcscProvider,
    MouserProvider,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "providers"


def _fixture(name: str) -> Dict[str, Any]:
    value = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


_INVALID_IDENTITIES = [True, 123, ["PART"], {"mpn": "PART"}, ""]


@pytest.mark.parametrize("value", _INVALID_IDENTITIES)
@pytest.mark.parametrize("field_name", ["mpn", "manufacturer", "distributor_id"])
def test_digikey_rejects_non_text_response_identity(
    field_name: str, value: object
) -> None:
    response = _fixture("digikey_keyword_opa333.json")
    product = response["Products"][0]
    if field_name == "mpn":
        product["ManufacturerProductNumber"] = value
    elif field_name == "manufacturer":
        product["Manufacturer"]["Name"] = value
    else:
        product["ProductVariations"][0]["DigiKeyProductNumber"] = value

    with pytest.raises(InvalidResponseError):
        DigiKeyProvider(env={}).normalize_response(response)


@pytest.mark.parametrize("value", _INVALID_IDENTITIES)
@pytest.mark.parametrize("field_name", ["mpn", "manufacturer", "distributor_id"])
def test_mouser_rejects_non_text_response_identity(
    field_name: str, value: object
) -> None:
    response = _fixture("mouser_search_lm321.json")
    part = response["SearchResults"]["Parts"][0]
    response_name = {
        "mpn": "ManufacturerPartNumber",
        "manufacturer": "Manufacturer",
        "distributor_id": "MouserPartNumber",
    }[field_name]
    part[response_name] = value

    with pytest.raises(InvalidResponseError):
        MouserProvider(env={}).normalize_response(response)


@pytest.mark.parametrize("value", _INVALID_IDENTITIES)
@pytest.mark.parametrize("field_name", ["mpn", "manufacturer", "lcsc_id"])
def test_lcsc_rejects_non_text_response_identity(
    field_name: str, value: object
) -> None:
    item: Dict[str, Any] = {
        "model": "OPA333AIDBVR",
        "brand": "Texas Instruments",
        "lcsc": "C30878",
    }
    item[{"mpn": "model", "manufacturer": "brand", "lcsc_id": "lcsc"}[field_name]] = (
        value
    )

    with pytest.raises(InvalidResponseError):
        LcscProvider().normalize_response({"results": [item]})


class _EasyedaIdentityApi:
    def __init__(self, raw: Dict[str, Any]) -> None:
        self.raw = raw

    def get_cad_data_of_component(self, _lcsc_id: str) -> Dict[str, Any]:
        return copy.deepcopy(self.raw)


@pytest.mark.parametrize("value", _INVALID_IDENTITIES)
@pytest.mark.parametrize("field_name", ["lcsc_id", "component_id"])
def test_easyeda_rejects_non_text_response_identity(
    field_name: str, value: object
) -> None:
    raw: Dict[str, Any] = {
        "uuid": "component-id",
        "lcsc": {"number": "C30878"},
        "dataStr": {"head": {"c_para": {}}},
    }
    if field_name == "lcsc_id":
        raw["lcsc"]["number"] = value
    else:
        raw["uuid"] = value
    provider = EasyedaProvider(api=_EasyedaIdentityApi(raw))  # type: ignore[arg-type]

    with pytest.raises(InvalidResponseError):
        provider.get_cad_data("C30878")


@pytest.mark.parametrize(
    "provider",
    [DigiKeyProvider(env={}), MouserProvider(env={}), LcscProvider()],
)
@pytest.mark.parametrize("value", _INVALID_IDENTITIES)
@pytest.mark.parametrize("field_name", ["mpn", "manufacturer"])
def test_exact_query_rejects_non_text_or_empty_identity_before_transport(
    provider: object, field_name: str, value: object
) -> None:
    manufacturer: object = "Texas Instruments"
    mpn: object = "OPA333AIDBVR"
    if field_name == "mpn":
        mpn = value
    else:
        manufacturer = value

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(manufacturer, mpn)  # type: ignore[attr-defined]


@pytest.mark.parametrize("value", _INVALID_IDENTITIES)
def test_easyeda_query_rejects_non_text_or_empty_lcsc_id(value: object) -> None:
    provider = EasyedaProvider(api=_EasyedaIdentityApi({}))  # type: ignore[arg-type]

    with pytest.raises(InvalidResponseError):
        provider.get_cad_data(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "provider",
    [DigiKeyProvider(env={}), MouserProvider(env={}), LcscProvider()],
)
@pytest.mark.parametrize("value", _INVALID_IDENTITIES)
def test_distributor_query_rejects_non_text_or_empty_identity_before_transport(
    provider: object, value: object
) -> None:
    with pytest.raises(InvalidResponseError):
        provider.get_part_by_distributor_id(value)  # type: ignore[attr-defined]
