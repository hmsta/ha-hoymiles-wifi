"""Entity registry migration helpers for Hoymiles entities."""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import Any

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .binary_sensor import BINARY_SENSORS
from .button import BUTTONS
from .const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_HYBRID_INVERTERS,
    CONF_INVERTERS,
    CONF_METERS,
    CONF_PORTS,
    CONF_THREE_PHASE_INVERTERS,
    DOMAIN,
)
from .entity import get_hoymiles_entity_object_id, get_hoymiles_entity_unique_id
from .number import CONFIG_CONTROL_ENTITIES
from .sensor import (
    APP_INFO_SENSORS,
    CONFIG_DIAGNOSTIC_SENSORS,
    HOYMILES_ENERGY_STORAGE_SENSORS,
    HOYMILES_SENSORS,
)

_LOGGER = logging.getLogger(__name__)


def _old_unique_id(entry_id: str, key: str) -> str:
    """Return the legacy index-based unique ID."""
    return f"hoymiles_{entry_id}_{key}"


def _normalize_serial(serial_number: Any) -> str:
    """Normalize a serial number for comparisons."""
    return str(serial_number).lower()


def _known_serials(data: dict) -> set[str]:
    """Collect known serials from config entry data."""
    serials = {
        _normalize_serial(serial_number)
        for serial_number in (
            [
                data.get(CONF_DTU_SERIAL_NUMBER),
                *data.get(CONF_INVERTERS, []),
                *data.get(CONF_THREE_PHASE_INVERTERS, []),
                *(meter.get("meter_serial_number") for meter in data.get(CONF_METERS, [])),
                *(port.get("inverter_serial_number") for port in data.get(CONF_PORTS, [])),
                *(
                    inverter.get("inverter_serial_number")
                    for inverter in data.get(CONF_HYBRID_INVERTERS, [])
                ),
            ]
        )
        if serial_number
    }
    return serials


def _infer_serial_from_entity(
    hass: HomeAssistant,
    entity_entry: er.RegistryEntry,
    known_serials: set[str],
) -> str | None:
    """Infer the intended serial from an existing registry entry."""
    entity_id = entity_entry.entity_id.lower()
    for serial_number in sorted(known_serials, key=len, reverse=True):
        if serial_number in entity_id:
            return serial_number

    device_id = entity_entry.device_id
    if device_id is None:
        return None

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    if device_entry is None:
        return None

    for identifier_domain, identifier in device_entry.identifiers:
        serial_number = _normalize_serial(identifier)
        if identifier_domain == DOMAIN and serial_number in known_serials:
            return serial_number

    return None


def _stable_key(key: str) -> str:
    """Return the index-free key fragment used by stable unique IDs."""
    key = re.sub(r"\[[^\]]+\]", "", key)
    return key.lstrip(".")


def _strip_known_serial_prefix(stable_key: str, known_serials: set[str]) -> str:
    """Remove a serial prefix left by an earlier migration attempt."""
    normalized_key = stable_key.lower()
    for serial_number in sorted(known_serials, key=len, reverse=True):
        prefix = f"{serial_number}_"
        if normalized_key.startswith(prefix):
            return stable_key[len(prefix) :]
    return stable_key


def _target_key(description) -> tuple[str, str, int | None, str | None]:
    """Return a lookup key for a stable unique ID target."""
    return (
        _stable_key(description.key),
        _normalize_serial(description.serial_number),
        description.port_number,
        description.phase,
    )


def _legacy_key_from_unique_id(entry_id: str, unique_id: str) -> str | None:
    """Return the legacy entity key from an old Hoymiles unique ID."""
    prefix = f"hoymiles_{entry_id}_"
    if not unique_id.startswith(prefix):
        return None
    key = unique_id[len(prefix) :]
    if "[" not in key:
        return None
    return key


def _infer_port_from_entity(entity_entry: er.RegistryEntry) -> int | None:
    """Infer a PV port number from an existing entity registry entry."""
    match = re.search(r"(?:^|_)port_?(\d+)(?:_|$)", entity_entry.entity_id.lower())
    if match is None:
        return None
    return int(match.group(1))


def _infer_phase_from_key_or_entity(
    legacy_key: str, entity_entry: er.RegistryEntry
) -> str | None:
    """Infer a phase label from a legacy key or existing entity ID."""
    match = re.search(r"(?:^|_)phase_?([abc])(?:_|$)", entity_entry.entity_id.lower())
    if match is not None:
        return match.group(1).upper()

    match = re.search(r"phases\[(\d+)\]", legacy_key)
    if match is None:
        return None

    phase_index = int(match.group(1))
    if phase_index not in (0, 1, 2):
        return None
    return ("A", "B", "C")[phase_index]


def _fallback_target_key_from_legacy(
    legacy_key: str,
    entry_data: dict,
) -> tuple[str, str, int | None, str | None] | None:
    """Build a fallback target key from current config index data."""
    stable_key = _stable_key(legacy_key)

    inverter_match = re.search(r"\[(\d+)\]", legacy_key)
    if inverter_match is None:
        return None

    index = int(inverter_match.group(1))
    if legacy_key.startswith("sgs_data["):
        inverters = entry_data.get(CONF_INVERTERS, [])
        if index >= len(inverters):
            return None
        return (stable_key, _normalize_serial(inverters[index]), None, None)

    if legacy_key.startswith("tgs_data["):
        inverters = entry_data.get(CONF_THREE_PHASE_INVERTERS, [])
        if index >= len(inverters):
            return None
        return (stable_key, _normalize_serial(inverters[index]), None, None)

    if legacy_key.startswith("pv_data["):
        ports = entry_data.get(CONF_PORTS, [])
        if index >= len(ports):
            return None
        port = ports[index]
        return (
            stable_key,
            _normalize_serial(port.get("inverter_serial_number")),
            port.get("port_number"),
            None,
        )

    hybrid_match = re.search(r"^\[(\d+)\]", legacy_key)
    if hybrid_match is None:
        return None

    hybrid_index = int(hybrid_match.group(1))
    hybrid_inverters = entry_data.get(CONF_HYBRID_INVERTERS, [])
    if hybrid_index >= len(hybrid_inverters):
        return None

    port_number = None
    pv_panel_match = re.search(r"pv_panels\[(\d+)\]", legacy_key)
    if pv_panel_match is not None:
        port_number = int(pv_panel_match.group(1)) + 1

    phase = None
    phase_match = re.search(r"phases\[(\d+)\]", legacy_key)
    if phase_match is not None:
        phase = ("A", "B", "C")[int(phase_match.group(1))]

    return (
        stable_key,
        _normalize_serial(
            hybrid_inverters[hybrid_index].get("inverter_serial_number")
        ),
        port_number,
        phase,
    )


def _add_mapping(
    mappings: dict[
        tuple[str, str],
        tuple[str, str, str, tuple[str, str, int | None, str | None]],
    ],
    targets: dict[tuple[str, str, int | None, str | None], tuple[str, str]],
    entry_id: str,
    domain: str,
    description,
) -> None:
    """Add one legacy-to-stable unique ID mapping."""
    old_unique_id = _old_unique_id(entry_id, description.key)
    new_unique_id = get_hoymiles_entity_unique_id(entry_id, description)
    object_id = get_hoymiles_entity_object_id(description)
    target_key = _target_key(description)
    mappings[(domain, old_unique_id)] = (domain, new_unique_id, object_id, target_key)
    targets[target_key] = (new_unique_id, object_id)


def _entity_registry_mappings(
    entry_id: str, data: dict
) -> tuple[
    dict[
        tuple[str, str],
        tuple[str, str, str, tuple[str, str, int | None, str | None]],
    ],
    dict[tuple[str, str, int | None, str | None], tuple[str, str]],
]:
    """Build canonical unique ID/entity ID mappings."""
    mappings: dict[
        tuple[str, str],
        tuple[str, str, str, tuple[str, str, int | None, str | None]],
    ] = {}
    targets: dict[tuple[str, str, int | None, str | None], tuple[str, str]] = {}

    dtu_serial_number = data.get(CONF_DTU_SERIAL_NUMBER)
    single_phase_inverters = data.get(CONF_INVERTERS, [])
    three_phase_inverters = data.get(CONF_THREE_PHASE_INVERTERS, [])
    inverters = single_phase_inverters + three_phase_inverters
    ports = data.get(CONF_PORTS, [])
    meters = data.get(CONF_METERS, [])
    hybrid_inverters = data.get(CONF_HYBRID_INVERTERS, [])

    for description in HOYMILES_SENSORS:
        if "<inverter_count>" in description.key and "sgs_data" in description.key:
            for index, inverter_serial in enumerate(single_phase_inverters):
                updated = dataclasses.replace(
                    description,
                    key=description.key.replace("<inverter_count>", str(index)),
                    serial_number=inverter_serial,
                )
                _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)
        elif "<inverter_count>" in description.key and "tgs_data" in description.key:
            for index, inverter_serial in enumerate(three_phase_inverters):
                updated = dataclasses.replace(
                    description,
                    key=description.key.replace("<inverter_count>", str(index)),
                    serial_number=inverter_serial,
                )
                _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)
        elif "<pv_count>" in description.key:
            for index, port in enumerate(ports):
                updated = dataclasses.replace(
                    description,
                    key=description.key.replace("<pv_count>", str(index)),
                    serial_number=port["inverter_serial_number"],
                    port_number=port["port_number"],
                )
                _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)
        elif "<meter_count>" in description.key:
            for index, meter in enumerate(meters):
                updated = dataclasses.replace(
                    description,
                    key=description.key.replace("<meter_count>", str(index)),
                    serial_number=meter["meter_serial_number"],
                )
                _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)
        elif dtu_serial_number:
            updated = dataclasses.replace(description, serial_number=dtu_serial_number)
            _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)

    for description in (*CONFIG_DIAGNOSTIC_SENSORS, *APP_INFO_SENSORS):
        if "<inverter_count>" in description.key:
            for index, inverter_serial in enumerate(inverters):
                updated = dataclasses.replace(
                    description,
                    key=description.key.replace("<inverter_count>", str(index)),
                    serial_number=inverter_serial,
                )
                _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)
        elif "<pv_count>" in description.key:
            for index, port in enumerate(ports):
                updated = dataclasses.replace(
                    description,
                    key=description.key.replace("<pv_count>", str(index)),
                    serial_number=port["inverter_serial_number"],
                    port_number=port["port_number"],
                )
                _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)
        elif dtu_serial_number:
            updated = dataclasses.replace(description, serial_number=dtu_serial_number)
            _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)

    for description in HOYMILES_ENERGY_STORAGE_SENSORS:
        if "<inverter_count>" not in description.key:
            if dtu_serial_number:
                updated = dataclasses.replace(
                    description, serial_number=dtu_serial_number
                )
                _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)
            continue

        for index, inverter in enumerate(hybrid_inverters):
            new_key = description.key.replace("<inverter_count>", str(index))
            if "<pv_panel_count>" in new_key:
                for pv_index in range(0, 2):
                    updated = dataclasses.replace(
                        description,
                        key=new_key.replace("<pv_panel_count>", str(pv_index)),
                        serial_number=inverter["inverter_serial_number"],
                        model_name=inverter["model_name"],
                        port_number=pv_index + 1,
                    )
                    _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)
            elif "<phase_count>" in new_key:
                for phase_index, phase in enumerate(("A", "B", "C")):
                    updated = dataclasses.replace(
                        description,
                        key=new_key.replace("<phase_count>", str(phase_index)),
                        serial_number=inverter["inverter_serial_number"],
                        model_name=inverter["model_name"],
                        phase=phase,
                    )
                    _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)
            else:
                updated = dataclasses.replace(
                    description,
                    key=new_key,
                    serial_number=inverter["inverter_serial_number"],
                    model_name=inverter["model_name"],
                )
                _add_mapping(mappings, targets, entry_id, SENSOR_DOMAIN, updated)

    for description in CONFIG_CONTROL_ENTITIES:
        if description.is_dtu_sensor and dtu_serial_number:
            updated = dataclasses.replace(description, serial_number=dtu_serial_number)
            _add_mapping(mappings, targets, entry_id, NUMBER_DOMAIN, updated)

    for description in BINARY_SENSORS:
        if dtu_serial_number:
            updated = dataclasses.replace(description, serial_number=dtu_serial_number)
            _add_mapping(mappings, targets, entry_id, BINARY_SENSOR_DOMAIN, updated)

    for description in BUTTONS:
        if description.is_dtu_sensor:
            if dtu_serial_number:
                updated = dataclasses.replace(
                    description, serial_number=dtu_serial_number
                )
                _add_mapping(mappings, targets, entry_id, BUTTON_DOMAIN, updated)
            continue

        for inverter_serial in inverters:
            updated = dataclasses.replace(
                description,
                key=description.key.replace("<inverter_serial>", inverter_serial),
                serial_number=inverter_serial,
            )
            _add_mapping(mappings, targets, entry_id, BUTTON_DOMAIN, updated)

    return mappings, targets


def _available_entity_id(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entity_id: str,
) -> bool:
    """Return if an entity ID is free in the registry and state machine."""
    return (
        entity_registry.async_get(entity_id) is None
        and hass.states.get(entity_id) is None
    )


def _stale_entity_id(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    domain: str,
    object_id: str,
) -> str:
    """Return an unused entity ID for a stale legacy Hoymiles registry entry."""
    base_entity_id = f"{domain}.hoymiles_stale_{object_id}"
    if _available_entity_id(hass, entity_registry, base_entity_id):
        return base_entity_id

    for index in range(2, 1000):
        entity_id = f"{base_entity_id}_{index}"
        if _available_entity_id(hass, entity_registry, entity_id):
            return entity_id

    raise ValueError(f"Cannot find free stale entity ID for {base_entity_id}")


def _prepare_canonical_entity_id(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entity_id: str,
    new_unique_id: str,
    canonical_entity_id: str,
) -> bool:
    """Make the canonical entity ID available for the entity being migrated."""
    if entity_id == canonical_entity_id:
        return True

    conflicting_entry = entity_registry.async_get(canonical_entity_id)
    if conflicting_entry is None:
        return True

    if conflicting_entry.unique_id == new_unique_id:
        _LOGGER.debug(
            "Hoymiles canonical entity ID %s already belongs to %s",
            canonical_entity_id,
            new_unique_id,
        )
        return False

    if conflicting_entry.platform != DOMAIN:
        _LOGGER.warning(
            "Cannot assign Hoymiles canonical entity ID %s to %s because it is "
            "already used by %s",
            canonical_entity_id,
            entity_id,
            conflicting_entry.platform,
        )
        return False

    stale_entity_id = _stale_entity_id(
        hass,
        entity_registry,
        conflicting_entry.domain,
        canonical_entity_id.split(".", 1)[1],
    )
    try:
        entity_registry.async_update_entity(
            conflicting_entry.entity_id, new_entity_id=stale_entity_id
        )
    except ValueError as err:
        _LOGGER.warning(
            "Cannot move stale Hoymiles entity %s out of canonical slot %s: %s",
            conflicting_entry.entity_id,
            canonical_entity_id,
            err,
        )
        return False

    _LOGGER.info(
        "Moved stale Hoymiles entity %s to %s so %s can use canonical entity ID",
        conflicting_entry.entity_id,
        stale_entity_id,
        entity_id,
    )
    return True


def _migrate_entity_registry_entry(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entity_entry: er.RegistryEntry,
    new_unique_id: str,
    object_id: str,
) -> bool:
    """Migrate one entity registry entry to its stable ID and canonical name."""
    canonical_entity_id = f"{entity_entry.domain}.{object_id}"
    if not _prepare_canonical_entity_id(
        hass,
        entity_registry,
        entity_entry.entity_id,
        new_unique_id,
        canonical_entity_id,
    ):
        return False

    update_kwargs = {}
    if entity_entry.unique_id != new_unique_id:
        update_kwargs["new_unique_id"] = new_unique_id
    if entity_entry.entity_id != canonical_entity_id:
        update_kwargs["new_entity_id"] = canonical_entity_id

    if not update_kwargs:
        return False

    try:
        entity_registry.async_update_entity(entity_entry.entity_id, **update_kwargs)
    except ValueError as err:
        _LOGGER.warning(
            "Cannot migrate Hoymiles entity %s to %s/%s: %s",
            entity_entry.entity_id,
            new_unique_id,
            canonical_entity_id,
            err,
        )
        return False

    return True


async def async_migrate_entity_unique_ids(
    hass: HomeAssistant, entry_id: str, data: dict
) -> None:
    """Migrate legacy Hoymiles registry entries to serial-based IDs."""
    entity_registry = er.async_get(hass)
    mappings, targets = _entity_registry_mappings(entry_id, data)
    known_serials = _known_serials(data)
    migrated_entity_ids: set[str] = set()

    for (
        entity_domain,
        old_unique_id,
    ), (
        _,
        default_new_unique_id,
        default_object_id,
        target_key,
    ) in mappings.items():
        entity_id = entity_registry.async_get_entity_id(
            entity_domain, DOMAIN, old_unique_id
        )
        if entity_id is None:
            continue

        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry is None:
            continue

        new_unique_id = default_new_unique_id
        object_id = default_object_id
        inferred_serial = _infer_serial_from_entity(hass, entity_entry, known_serials)
        if inferred_serial is not None:
            inferred_port = _infer_port_from_entity(entity_entry)
            legacy_key = _legacy_key_from_unique_id(entry_id, old_unique_id)
            inferred_phase = _infer_phase_from_key_or_entity(
                legacy_key or target_key[0], entity_entry
            )
            inferred_target_key = (
                target_key[0],
                inferred_serial,
                inferred_port if inferred_port is not None else target_key[2],
                inferred_phase if inferred_phase is not None else target_key[3],
            )
            new_unique_id, object_id = targets.get(
                inferred_target_key, (default_new_unique_id, default_object_id)
            )

        existing_entity_id = entity_registry.async_get_entity_id(
            entity_domain, DOMAIN, new_unique_id
        )
        if existing_entity_id is not None and existing_entity_id != entity_id:
            _LOGGER.warning(
                "Cannot migrate Hoymiles entity %s from %s to %s because %s "
                "already uses the target unique ID",
                entity_id,
                old_unique_id,
                new_unique_id,
                existing_entity_id,
            )
            continue

        if _migrate_entity_registry_entry(
            hass, entity_registry, entity_entry, new_unique_id, object_id
        ):
            migrated_entity_ids.add(entity_id)

    for entity_entry in list(entity_registry.entities.values()):
        if entity_entry.domain != SENSOR_DOMAIN or entity_entry.platform != DOMAIN:
            continue
        if entity_entry.config_entry_id != entry_id:
            continue
        if entity_entry.entity_id in migrated_entity_ids:
            continue

        legacy_key = _legacy_key_from_unique_id(entry_id, entity_entry.unique_id)
        if legacy_key is None:
            continue

        stable_key = _strip_known_serial_prefix(_stable_key(legacy_key), known_serials)
        inferred_serial = _infer_serial_from_entity(hass, entity_entry, known_serials)
        target_key = None
        if inferred_serial is not None:
            target_key = (
                stable_key,
                inferred_serial,
                _infer_port_from_entity(entity_entry),
                _infer_phase_from_key_or_entity(legacy_key, entity_entry),
            )

        if target_key not in targets:
            target_key = _fallback_target_key_from_legacy(legacy_key, data)

        if target_key not in targets:
            _LOGGER.debug(
                "Cannot infer stable Hoymiles unique ID target for %s",
                entity_entry.entity_id,
            )
            continue

        new_unique_id, object_id = targets[target_key]
        existing_entity_id = entity_registry.async_get_entity_id(
            SENSOR_DOMAIN, DOMAIN, new_unique_id
        )
        if (
            existing_entity_id is not None
            and existing_entity_id != entity_entry.entity_id
        ):
            _LOGGER.warning(
                "Cannot migrate Hoymiles entity %s from %s to %s because %s "
                "already uses the target unique ID",
                entity_entry.entity_id,
                entity_entry.unique_id,
                new_unique_id,
                existing_entity_id,
            )
            continue

        _migrate_entity_registry_entry(
            hass, entity_registry, entity_entry, new_unique_id, object_id
        )
