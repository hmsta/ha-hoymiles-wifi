"""Helpers for Hoymiles cloud layout metadata."""

from __future__ import annotations

from collections import defaultdict
import json
import re
from typing import Any


class LayoutMetadataError(ValueError):
    """Raised when Hoymiles layout metadata cannot be parsed."""


class PhaseMapError(ValueError):
    """Raised when the inverter phase map cannot be parsed."""


class MetadataMapError(ValueError):
    """Raised when a serial=value metadata map cannot be parsed."""


def normalize_serial(serial_number: Any) -> str:
    """Normalize Hoymiles serials for entity IDs and metadata lookups."""
    return str(serial_number or "").strip().lower()


def normalize_metadata_value(value: Any) -> str:
    """Normalize optional metadata values without turning None into text."""
    return "" if value is None else str(value).strip()


def parse_layout_json(raw_layout: Any) -> dict[str, Any] | None:
    """Parse and validate a Hoymiles layout JSON payload."""
    if raw_layout is None:
        return None

    if isinstance(raw_layout, str):
        raw_layout = raw_layout.strip()
        if not raw_layout:
            return None
        try:
            layout = json.loads(raw_layout)
        except json.JSONDecodeError as err:
            raise LayoutMetadataError(f"Invalid layout JSON: {err}") from err
    elif isinstance(raw_layout, dict):
        layout = raw_layout
    else:
        raise LayoutMetadataError("Layout JSON must be an object or JSON string")

    if _layout_scene(layout) is None:
        raise LayoutMetadataError("Layout JSON does not contain k_100 scene data")

    return layout


def derive_inverter_locations(raw_layout: Any) -> dict[str, str]:
    """Return inverter serial -> normalized location from Hoymiles layout JSON."""
    layout = parse_layout_json(raw_layout)
    if layout is None:
        return {}

    scene = _layout_scene(layout)
    if scene is None:
        return {}

    areas = _area_name_by_id(scene)
    locations_by_serial: dict[str, set[str]] = defaultdict(set)

    for slot in scene.get("emts") or []:
        if not isinstance(slot, dict):
            continue
        serial = normalize_serial(slot.get("sn"))
        if not serial:
            continue
        area_name = areas.get(str(slot.get("lid")))
        if not area_name:
            continue
        location = normalize_location(area_name)
        if location:
            locations_by_serial[serial].add(location)

    return {
        serial: ", ".join(sorted(locations, key=_natural_sort_key))
        for serial, locations in locations_by_serial.items()
        if locations
    }


def parse_inverter_phase_map(raw_map: Any) -> dict[str, str]:
    """Parse serial=phase lines and normalize phases to 1/2/3."""
    phases: dict[str, str] = {}
    try:
        phase_map = parse_inverter_metadata_map(raw_map)
    except MetadataMapError as err:
        raise PhaseMapError(str(err)) from err

    for serial, raw_phase in phase_map.items():
        phase = normalize_phase(raw_phase)
        if phase is None:
            raise PhaseMapError(f"{serial} has an invalid phase")
        phases[serial] = phase

    return phases


def parse_inverter_location_map(raw_map: Any) -> dict[str, str]:
    """Parse serial=location lines."""
    return parse_inverter_metadata_map(raw_map)


def parse_inverter_metadata_map(raw_map: Any) -> dict[str, str]:
    """Parse serial=value lines into a normalized metadata dictionary."""
    if raw_map is None:
        return {}

    if isinstance(raw_map, dict):
        parsed: dict[str, str] = {}
        for serial_number, raw_value in raw_map.items():
            serial = normalize_serial(serial_number)
            value = normalize_metadata_value(raw_value)
            if serial and value:
                parsed[serial] = value
        return parsed

    text = str(raw_map).strip()
    if not text:
        return {}

    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line:
            serial, value = line.split("=", 1)
        elif ":" in line:
            serial, value = line.split(":", 1)
        else:
            raise MetadataMapError(f"Line {line_number} must use serial=value")

        serial = normalize_serial(serial)
        value = str(value or "").strip()
        if not serial:
            raise MetadataMapError(f"Line {line_number} is missing a serial")
        if not value:
            raise MetadataMapError(f"Line {line_number} is missing a value")
        parsed[serial] = value

    return parsed


def normalize_phase(raw_phase: Any) -> str | None:
    """Normalize accepted phase labels to 1/2/3."""
    phase = str(raw_phase or "").strip().upper()
    if phase.startswith("L"):
        phase = phase[1:]
    return phase if phase in {"1", "2", "3"} else None


def normalize_location(raw_name: Any) -> str:
    """Normalize Hoymiles row names like 53-a to inverter-level locations."""
    name = str(raw_name or "").strip()
    if not name:
        return ""
    return re.sub(r"[-_\s]+[A-Za-z]+$", "", name).strip()


def _layout_scene(layout: dict[str, Any]) -> dict[str, Any] | None:
    """Return the Hoymiles k_100 scene from common wrapper shapes."""
    root = layout
    if "data" in root:
        data = root.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as err:
                raise LayoutMetadataError(f"Invalid layout data JSON: {err}") from err
        if isinstance(data, dict):
            root = data

    scene = root.get("k_100")
    return scene if isinstance(scene, dict) else None


def _area_name_by_id(scene: dict[str, Any]) -> dict[str, str]:
    """Build an area lookup using the IDs observed in Hoymiles layout JSON."""
    areas: dict[str, str] = {}
    for area in scene.get("pls") or []:
        if not isinstance(area, dict):
            continue
        name = str(area.get("n") or "").strip()
        if not name:
            continue
        for key in ("iid", "xid", "rid"):
            value = area.get(key)
            if value is not None:
                areas[str(value)] = name
    return areas


def _natural_sort_key(value: str) -> list[Any]:
    """Sort text with embedded numbers naturally."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", value)
    ]
