"""Tests for Hoymiles layout metadata parsing."""

from pathlib import Path

import pytest

from custom_components.hoymiles_wifi.layout_metadata import (
    LayoutMetadataError,
    PhaseMapError,
    derive_inverter_locations,
    normalize_location,
    parse_inverter_location_map,
    parse_inverter_phase_map,
    parse_layout_json,
)


SAMPLES = Path(__file__).parents[1] / "tools" / "layout sampes"


def test_derive_wondervillage_locations_from_layout_json() -> None:
    """Test inverter locations are derived from real Hoymiles group metadata."""
    raw_layout = (SAMPLES / "wondervillage" / "v3_g_c.json").read_text()

    locations = derive_inverter_locations(raw_layout)

    assert locations["1421a01a5485"] == "53"
    assert locations["1421a01a45e2"] == "53"


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("53-a", "53"),
        ("53-b", "53"),
        ("16-a", "16"),
        ("House 90", "House 90"),
    ],
)
def test_normalize_location_strips_row_suffix(raw_name: str, expected: str) -> None:
    """Test row suffixes are removed from Hoymiles group names."""
    assert normalize_location(raw_name) == expected


def test_parse_layout_json_rejects_malformed_json() -> None:
    """Test invalid JSON is rejected."""
    with pytest.raises(LayoutMetadataError):
        parse_layout_json("{")


def test_parse_inverter_phase_map_normalizes_values() -> None:
    """Test phase map serial and phase normalization."""
    assert parse_inverter_phase_map(
        """
        1421A01A4FF5=L1
        1421a01a5294=2
        1421a01a53da: L3
        """
    ) == {
        "1421a01a4ff5": "1",
        "1421a01a5294": "2",
        "1421a01a53da": "3",
    }


def test_parse_inverter_location_map_normalizes_serials() -> None:
    """Test location map serial normalization."""
    assert parse_inverter_location_map(
        """
        1421A01A4FF5=53
        1421a01a5294: House 77
        """
    ) == {
        "1421a01a4ff5": "53",
        "1421a01a5294": "House 77",
    }


def test_parse_inverter_phase_map_rejects_invalid_phase() -> None:
    """Test invalid phase values are rejected."""
    with pytest.raises(PhaseMapError):
        parse_inverter_phase_map("1421a01a4ff5=4")
