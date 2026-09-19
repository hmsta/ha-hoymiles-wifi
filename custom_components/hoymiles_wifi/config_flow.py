"""Config flow for Hoymiles."""

from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from .const import (
    CONF_DELETE_MISSING_INVERTERS,
    CONF_DTU_LOCATION,
    CONF_DTU_SERIAL_NUMBER,
    CONF_HYBRID_INVERTERS,
    CONF_INVERTERS,
    CONF_INVERTER_LOCATIONS,
    CONF_INVERTER_LOCATION_MAP,
    CONF_INVERTER_PHASE_MAP,
    CONF_INVERTER_PHASES,
    CONF_METERS,
    CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
    CONF_METER_TYPE,
    CONF_PORTS,
    CONF_STARTUP_COOLDOWN,
    CONF_THREE_PHASE_INVERTERS,
    CONF_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    CONF_IS_ENCRYPTED,
    CONF_ENC_RAND,
    CONFIG_VERSION,
    DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_STARTUP_COOLDOWN_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
    METER_TYPE_AUTO,
    METER_TYPE_SINGLE_PHASE,
    METER_TYPE_THREE_PHASE,
    MIN_UPDATE_INTERVAL_SECONDS,
    MIN_STARTUP_COOLDOWN_SECONDS,
    MIN_METER_ENERGY_CONSISTENCY_TOLERANCE,
    MIN_TIMEOUT_SECONDS,
)
from .entity_migration import (
    async_migrate_entity_unique_ids,
    transfer_inverter_entity_registry_entries,
)
from .error import CannotConnect
from .layout_metadata import (
    MetadataMapError,
    PhaseMapError,
    normalize_metadata_value,
    parse_inverter_location_map,
    parse_inverter_phase_map,
)
from .util import async_get_config_entry_data_for_host

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(
            CONF_UPDATE_INTERVAL,
            default=timedelta(seconds=DEFAULT_UPDATE_INTERVAL_SECONDS).seconds,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=timedelta(seconds=MIN_UPDATE_INTERVAL_SECONDS).seconds),
        ),
        vol.Optional(
            CONF_TIMEOUT,
            default=timedelta(seconds=DEFAULT_TIMEOUT_SECONDS).seconds,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=timedelta(seconds=MIN_TIMEOUT_SECONDS).seconds),
        ),
        vol.Optional(
            CONF_STARTUP_COOLDOWN,
            default=timedelta(seconds=DEFAULT_STARTUP_COOLDOWN_SECONDS).seconds,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=timedelta(seconds=MIN_STARTUP_COOLDOWN_SECONDS).seconds
            ),
        ),
        vol.Optional(CONF_METER_TYPE, default=METER_TYPE_AUTO): vol.In(
            [METER_TYPE_AUTO, METER_TYPE_SINGLE_PHASE, METER_TYPE_THREE_PHASE]
        ),
        vol.Optional(
            CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
            default=DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_METER_ENERGY_CONSISTENCY_TOLERANCE),
        ),
    }
)


def _apply_meter_type_override(meters: list[dict], meter_type: str) -> list[dict]:
    """Apply the configured meter type override to detected meters."""
    if meter_type == METER_TYPE_AUTO:
        return meters

    device_type = 1 if meter_type == METER_TYPE_SINGLE_PHASE else 3
    return [{**meter, "device_type": device_type} for meter in meters]


def _metadata_from_user_input(user_input: dict[str, Any]) -> tuple[str, str, str]:
    """Return normalized metadata input strings from a config flow submission."""
    dtu_location = str(user_input.get(CONF_DTU_LOCATION) or "").strip()
    inverter_location_map = str(
        user_input.get(CONF_INVERTER_LOCATION_MAP) or ""
    ).strip()
    inverter_phase_map = str(user_input.get(CONF_INVERTER_PHASE_MAP) or "").strip()
    return dtu_location, inverter_location_map, inverter_phase_map


def _validate_metadata_input(
    inverter_location_map: str, inverter_phase_map: str
) -> dict[str, str]:
    """Validate stored metadata fields and return field errors."""
    errors = {}
    if inverter_location_map:
        try:
            parse_inverter_location_map(inverter_location_map)
        except MetadataMapError:
            errors[CONF_INVERTER_LOCATION_MAP] = "invalid_location_map"

    if inverter_phase_map:
        try:
            parse_inverter_phase_map(inverter_phase_map)
        except PhaseMapError:
            errors[CONF_INVERTER_PHASE_MAP] = "invalid_phase_map"

    return errors


def _metadata_map_to_text(metadata: Any) -> str:
    """Return a deterministic serial=value text map from stored metadata."""
    if not isinstance(metadata, dict):
        return ""
    return "\n".join(
        f"{serial}={value}"
        for serial, value in sorted(
            (
                (
                    _normalize_serial(serial),
                    normalize_metadata_value(value),
                )
                for serial, value in metadata.items()
            )
        )
        if serial and value
    )


def _filter_metadata_map(metadata: dict[str, str], serials: set[str]) -> dict[str, str]:
    """Return metadata for serials that belong to the current config entry."""
    return {
        serial: value
        for serial, value in sorted(metadata.items())
        if serial in serials and value
    }


def _filter_duplicate_meters(
    hass: HomeAssistant, meters: list[dict], current_entry_id: str | None = None
) -> list[dict]:
    """Remove meters already configured by another Hoymiles entry."""
    configured_meter_serials = {
        str(meter.get("meter_serial_number")).lower()
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != current_entry_id
        for meter in entry.data.get(CONF_METERS, [])
        if meter.get("meter_serial_number")
    }

    return [
        meter
        for meter in meters
        if str(meter.get("meter_serial_number")).lower() not in configured_meter_serials
    ]


def _normalize_serial(serial_number: Any) -> str:
    """Normalize a serial number for comparisons."""
    return str(serial_number or "").strip().lower()


def _metadata_unique_id(entry_id: str, serial_number: str, kind: str) -> str:
    """Return the generated unique ID for a static metadata sensor."""
    return f"hoymiles_{entry_id}_{_normalize_serial(serial_number)}_metadata.{kind}"


def _metadata_entity_unique_ids(entry_id: str, data: dict) -> set[str]:
    """Return generated metadata unique IDs backed by config entry data."""
    unique_ids: set[str] = set()

    dtu_serial_number = _normalize_serial(data.get(CONF_DTU_SERIAL_NUMBER))
    if dtu_serial_number and str(data.get(CONF_DTU_LOCATION) or "").strip():
        unique_ids.add(_metadata_unique_id(entry_id, dtu_serial_number, "location"))

    inverter_serials = _detected_inverter_serials(
        data.get(CONF_INVERTERS, []),
        data.get(CONF_THREE_PHASE_INVERTERS, []),
        data.get(CONF_PORTS, []),
        data.get(CONF_HYBRID_INVERTERS, []),
    )

    locations = data.get(CONF_INVERTER_LOCATIONS)
    if not isinstance(locations, dict):
        locations = {}
    locations = {
        _normalize_serial(serial): normalize_metadata_value(value)
        for serial, value in locations.items()
        if _normalize_serial(serial) and normalize_metadata_value(value)
    }
    phases = data.get(CONF_INVERTER_PHASES)
    if not isinstance(phases, dict):
        phases = {}
    phases = {
        _normalize_serial(serial): normalize_metadata_value(value)
        for serial, value in phases.items()
        if _normalize_serial(serial) and normalize_metadata_value(value)
    }

    for serial_number in inverter_serials:
        if locations.get(serial_number):
            unique_ids.add(_metadata_unique_id(entry_id, serial_number, "location"))
        if phases.get(serial_number):
            unique_ids.add(_metadata_unique_id(entry_id, serial_number, "phase"))

    return unique_ids


def _remove_stale_metadata_entities(
    hass: HomeAssistant, entry_id: str, old_data: dict, new_data: dict
) -> None:
    """Remove generated metadata registry entries no longer backed by config."""
    stale_unique_ids = _metadata_entity_unique_ids(
        entry_id, old_data
    ) - _metadata_entity_unique_ids(entry_id, new_data)
    if not stale_unique_ids:
        return

    entity_registry = er.async_get(hass)
    for unique_id in stale_unique_ids:
        entity_id = entity_registry.async_get_entity_id(
            SENSOR_DOMAIN, DOMAIN, unique_id
        )
        if entity_id is not None:
            entity_registry.async_remove(entity_id)


def _merge_serial_list(existing: list, detected: list) -> list:
    """Merge serial-number lists while preserving existing order."""
    merged = []
    known = set()
    for serial_number in (*existing, *detected):
        normalized = _normalize_serial(serial_number)
        if normalized not in known:
            merged.append(serial_number)
            known.add(normalized)
    return merged


def _remove_serials(serial_numbers: list, remove_serials: set[str]) -> list:
    """Remove serials from a list."""
    return [
        serial_number
        for serial_number in serial_numbers
        if _normalize_serial(serial_number) not in remove_serials
    ]


def _merge_ports(existing: list[dict], detected: list[dict]) -> list[dict]:
    """Merge port lists by inverter serial and port number."""
    merged = []
    known = set()
    for port in (*existing, *detected):
        key = (
            _normalize_serial(port.get("inverter_serial_number")),
            port.get("port_number"),
        )
        if key not in known:
            merged.append(port)
            known.add(key)
    return merged


def _merge_hybrid_inverters(existing: list[dict], detected: list[dict]) -> list[dict]:
    """Merge hybrid inverter config data by inverter serial."""
    merged = []
    known = set()
    for inverter in (*existing, *detected):
        normalized = _normalize_serial(inverter.get("inverter_serial_number"))
        if normalized not in known:
            merged.append(inverter)
            known.add(normalized)
    return merged


def _merge_reconfigured_inverters(
    existing_data: dict,
    detected_single_phase_inverters: list,
    detected_three_phase_inverters: list,
    detected_ports: list[dict],
    detected_hybrid_inverters: list[dict],
    delete_missing_inverters: bool,
) -> tuple[list, list, list[dict], list[dict]]:
    """Return the inverter data that should be stored after reconfigure."""
    if delete_missing_inverters:
        return (
            detected_single_phase_inverters,
            detected_three_phase_inverters,
            detected_ports,
            detected_hybrid_inverters,
        )

    detected_single_serials = {
        _normalize_serial(serial_number)
        for serial_number in detected_single_phase_inverters
    }
    detected_three_serials = {
        _normalize_serial(serial_number)
        for serial_number in detected_three_phase_inverters
    }
    detected_hybrid_serials = {
        _normalize_serial(inverter.get("inverter_serial_number"))
        for inverter in detected_hybrid_inverters
    }

    single_phase_inverters = _merge_serial_list(
        _remove_serials(
            existing_data.get(CONF_INVERTERS, []),
            detected_three_serials | detected_hybrid_serials,
        ),
        detected_single_phase_inverters,
    )
    three_phase_inverters = _merge_serial_list(
        _remove_serials(
            existing_data.get(CONF_THREE_PHASE_INVERTERS, []),
            detected_single_serials | detected_hybrid_serials,
        ),
        detected_three_phase_inverters,
    )

    existing_hybrid_inverters = [
        inverter
        for inverter in existing_data.get(CONF_HYBRID_INVERTERS, [])
        if _normalize_serial(inverter.get("inverter_serial_number"))
        not in detected_single_serials | detected_three_serials
    ]
    hybrid_inverters = _merge_hybrid_inverters(
        existing_hybrid_inverters, detected_hybrid_inverters
    )
    ports = _merge_ports(existing_data.get(CONF_PORTS, []), detected_ports)

    return single_phase_inverters, three_phase_inverters, ports, hybrid_inverters


def _detected_inverter_serials(
    single_phase_inverters: list,
    three_phase_inverters: list,
    ports: list[dict],
    hybrid_inverters: list[dict],
) -> set[str]:
    """Collect all inverter serial numbers detected by a DTU."""
    return {
        _normalize_serial(serial_number)
        for serial_number in (
            [
                *single_phase_inverters,
                *three_phase_inverters,
                *(port.get("inverter_serial_number") for port in ports),
                *(
                    inverter.get("inverter_serial_number")
                    for inverter in hybrid_inverters
                ),
            ]
        )
        if serial_number
    }


def _remove_claimed_inverters_from_data(
    data: dict, claimed_inverter_serials: set[str]
) -> tuple[dict, bool]:
    """Remove inverter data claimed by another Hoymiles entry."""
    updated_data = {**data}
    claimed_inverter_serials = {
        _normalize_serial(serial_number)
        for serial_number in claimed_inverter_serials
        if serial_number
    }

    updated_inverters = [
        inverter
        for inverter in data.get(CONF_INVERTERS, [])
        if _normalize_serial(inverter) not in claimed_inverter_serials
    ]
    updated_three_phase_inverters = [
        inverter
        for inverter in data.get(CONF_THREE_PHASE_INVERTERS, [])
        if _normalize_serial(inverter) not in claimed_inverter_serials
    ]
    updated_hybrid_inverters = [
        inverter
        for inverter in data.get(CONF_HYBRID_INVERTERS, [])
        if _normalize_serial(inverter.get("inverter_serial_number"))
        not in claimed_inverter_serials
    ]
    updated_ports = [
        port
        for port in data.get(CONF_PORTS, [])
        if _normalize_serial(port.get("inverter_serial_number"))
        not in claimed_inverter_serials
    ]
    inverter_locations = data.get(CONF_INVERTER_LOCATIONS, {})
    if not isinstance(inverter_locations, dict):
        inverter_locations = {}
    inverter_phases = data.get(CONF_INVERTER_PHASES, {})
    if not isinstance(inverter_phases, dict):
        inverter_phases = {}
    updated_inverter_locations = {
        serial_number: value
        for serial_number, value in inverter_locations.items()
        if _normalize_serial(serial_number) not in claimed_inverter_serials
    }
    updated_inverter_phases = {
        serial_number: value
        for serial_number, value in inverter_phases.items()
        if _normalize_serial(serial_number) not in claimed_inverter_serials
    }

    changed = (
        updated_inverters != data.get(CONF_INVERTERS, [])
        or updated_three_phase_inverters != data.get(CONF_THREE_PHASE_INVERTERS, [])
        or updated_hybrid_inverters != data.get(CONF_HYBRID_INVERTERS, [])
        or updated_ports != data.get(CONF_PORTS, [])
        or updated_inverter_locations != data.get(CONF_INVERTER_LOCATIONS, {})
        or updated_inverter_phases != data.get(CONF_INVERTER_PHASES, {})
    )

    if changed:
        updated_data[CONF_INVERTERS] = updated_inverters
        updated_data[CONF_THREE_PHASE_INVERTERS] = updated_three_phase_inverters
        updated_data[CONF_HYBRID_INVERTERS] = updated_hybrid_inverters
        updated_data[CONF_PORTS] = updated_ports
        updated_data[CONF_INVERTER_LOCATIONS] = updated_inverter_locations
        updated_data[CONF_INVERTER_PHASES] = updated_inverter_phases

    return updated_data, changed


def _claimed_inverter_metadata(
    entry_updates: list[tuple[ConfigEntry, dict]],
    claimed_inverter_serials: set[str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Collect metadata belonging to inverters moving from another DTU."""
    locations: dict[str, str] = {}
    phases: dict[str, str] = {}
    for entry, _updated_data in entry_updates:
        for key, target in (
            (CONF_INVERTER_LOCATIONS, locations),
            (CONF_INVERTER_PHASES, phases),
        ):
            metadata = entry.data.get(key, {})
            if not isinstance(metadata, dict):
                continue
            for serial_number, value in metadata.items():
                serial_number = _normalize_serial(serial_number)
                value = normalize_metadata_value(value)
                if (
                    serial_number in claimed_inverter_serials
                    and value
                    and serial_number not in target
                ):
                    target[serial_number] = value
    return locations, phases


def _claimed_inverter_entry_updates(
    hass: HomeAssistant,
    single_phase_inverters: list,
    three_phase_inverters: list,
    ports: list[dict],
    hybrid_inverters: list[dict],
    current_entry_id: str | None = None,
) -> list[tuple[ConfigEntry, dict]]:
    """Return config entry updates needed to remove claimed inverters."""
    claimed_inverter_serials = _detected_inverter_serials(
        single_phase_inverters, three_phase_inverters, ports, hybrid_inverters
    )
    if not claimed_inverter_serials:
        return []

    updates = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == current_entry_id:
            continue

        updated_data, changed = _remove_claimed_inverters_from_data(
            entry.data, claimed_inverter_serials
        )
        if not changed:
            continue

        updated_data.setdefault(
            CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
            DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
        )
        updates.append((entry, updated_data))

    return updates


async def _apply_claimed_inverter_entry_updates(
    hass: HomeAssistant, entry_updates: list[tuple[ConfigEntry, dict]]
) -> set[str]:
    """Apply planned config entry updates for moved inverter ownership."""
    reloaded_entry_ids: set[str] = set()
    for entry, updated_data in entry_updates:
        hass.config_entries.async_update_entry(
            entry, data=updated_data, version=CONFIG_VERSION
        )
        if await hass.config_entries.async_reload(entry.entry_id):
            reloaded_entry_ids.add(entry.entry_id)
        else:
            _LOGGER.warning(
                "Failed to reload Hoymiles entry %s after moving inverter ownership",
                entry.entry_id,
            )
    return reloaded_entry_ids


async def _claim_detected_inverters(
    hass: HomeAssistant,
    single_phase_inverters: list,
    three_phase_inverters: list,
    ports: list[dict],
    hybrid_inverters: list[dict],
    current_entry_id: str | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Move detected inverters from other Hoymiles entries to this DTU."""
    claimed_inverter_serials = _detected_inverter_serials(
        single_phase_inverters, three_phase_inverters, ports, hybrid_inverters
    )
    entry_updates = _claimed_inverter_entry_updates(
        hass,
        single_phase_inverters,
        three_phase_inverters,
        ports,
        hybrid_inverters,
        current_entry_id,
    )
    claimed_metadata = _claimed_inverter_metadata(
        entry_updates, claimed_inverter_serials
    )
    await _apply_claimed_inverter_entry_updates(
        hass,
        entry_updates,
    )
    return claimed_metadata


class HoymilesInverterConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Hoymiles Inverter config flow."""

    VERSION = CONFIG_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            update_interval = user_input.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_SECONDS
            )
            timeout = user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)
            startup_cooldown = user_input.get(
                CONF_STARTUP_COOLDOWN, DEFAULT_STARTUP_COOLDOWN_SECONDS
            )
            meter_type = user_input.get(CONF_METER_TYPE, METER_TYPE_AUTO)
            meter_energy_consistency_tolerance = user_input.get(
                CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
                DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
            )

            try:
                (
                    dtu_sn,
                    single_phase_inverters,
                    three_phase_inverters,
                    ports,
                    meters,
                    hybrid_inverters,
                    is_encrypted,
                    enc_rand,
                ) = await async_get_config_entry_data_for_host(host)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                meters = _apply_meter_type_override(meters, meter_type)
                meters = _filter_duplicate_meters(self.hass, meters)
                await self.async_set_unique_id(dtu_sn)
                self._abort_if_unique_id_configured()
                claimed_locations, claimed_phases = await _claim_detected_inverters(
                    self.hass,
                    single_phase_inverters,
                    three_phase_inverters,
                    ports,
                    hybrid_inverters,
                )

                return self.async_create_entry(
                    title=host,
                    data={
                        CONF_HOST: host,
                        CONF_UPDATE_INTERVAL: update_interval,
                        CONF_DTU_SERIAL_NUMBER: dtu_sn,
                        CONF_INVERTERS: single_phase_inverters,
                        CONF_THREE_PHASE_INVERTERS: three_phase_inverters,
                        CONF_PORTS: ports,
                        CONF_METERS: meters,
                        CONF_METER_TYPE: meter_type,
                        CONF_METER_ENERGY_CONSISTENCY_TOLERANCE: (
                            meter_energy_consistency_tolerance
                        ),
                        CONF_HYBRID_INVERTERS: hybrid_inverters,
                        CONF_IS_ENCRYPTED: is_encrypted,
                        CONF_ENC_RAND: enc_rand,
                        CONF_TIMEOUT: timeout,
                        CONF_STARTUP_COOLDOWN: startup_cooldown,
                        CONF_DTU_LOCATION: "",
                        CONF_INVERTER_LOCATIONS: claimed_locations,
                        CONF_INVERTER_PHASES: claimed_phases,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a reconfiguration flow initialized by the user."""

        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            (
                dtu_location,
                inverter_location_map,
                inverter_phase_map,
            ) = _metadata_from_user_input(user_input)
            update_interval = user_input.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_SECONDS
            )

            timeout = user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)
            startup_cooldown = user_input.get(
                CONF_STARTUP_COOLDOWN,
                entry.data.get(
                    CONF_STARTUP_COOLDOWN, DEFAULT_STARTUP_COOLDOWN_SECONDS
                ),
            )
            meter_type = user_input.get(CONF_METER_TYPE, METER_TYPE_AUTO)
            meter_energy_consistency_tolerance = user_input.get(
                CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
                entry.data.get(
                    CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
                    DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
                ),
            )
            delete_missing_inverters = user_input.get(
                CONF_DELETE_MISSING_INVERTERS, False
            )
            errors.update(
                _validate_metadata_input(inverter_location_map, inverter_phase_map)
            )

            if not errors:
                inverter_locations = parse_inverter_location_map(inverter_location_map)
                inverter_phases = parse_inverter_phase_map(inverter_phase_map)
                try:
                    (
                        dtu_sn,
                        single_phase_inverters,
                        three_phase_inverters,
                        ports,
                        meters,
                        hybrid_inverters,
                        is_encrypted,
                        enc_rand,
                    ) = await async_get_config_entry_data_for_host(host)
                except CannotConnect:
                    errors["base"] = "cannot_connect"

            if not errors:
                meters = _apply_meter_type_override(meters, meter_type)
                if dtu_sn != entry.unique_id:
                    return self.async_abort(reason="another_device")
                meters = _filter_duplicate_meters(self.hass, meters, entry.entry_id)
                detected_inverter_serials = _detected_inverter_serials(
                    single_phase_inverters,
                    three_phase_inverters,
                    ports,
                    hybrid_inverters,
                )
                claimed_inverter_entry_updates = _claimed_inverter_entry_updates(
                    self.hass,
                    single_phase_inverters,
                    three_phase_inverters,
                    ports,
                    hybrid_inverters,
                    entry.entry_id,
                )
                claimed_locations, claimed_phases = _claimed_inverter_metadata(
                    claimed_inverter_entry_updates, detected_inverter_serials
                )
                inverter_locations = {**claimed_locations, **inverter_locations}
                inverter_phases = {**claimed_phases, **inverter_phases}
                (
                    single_phase_inverters,
                    three_phase_inverters,
                    ports,
                    hybrid_inverters,
                ) = _merge_reconfigured_inverters(
                    entry.data,
                    single_phase_inverters,
                    three_phase_inverters,
                    ports,
                    hybrid_inverters,
                    delete_missing_inverters,
                )
                inverter_serials = _detected_inverter_serials(
                    single_phase_inverters,
                    three_phase_inverters,
                    ports,
                    hybrid_inverters,
                )

                data = {
                    CONF_HOST: host,
                    CONF_UPDATE_INTERVAL: update_interval,
                    CONF_DTU_SERIAL_NUMBER: dtu_sn,
                    CONF_INVERTERS: single_phase_inverters,
                    CONF_THREE_PHASE_INVERTERS: three_phase_inverters,
                    CONF_PORTS: ports,
                    CONF_METERS: meters,
                    CONF_METER_TYPE: meter_type,
                    CONF_METER_ENERGY_CONSISTENCY_TOLERANCE: (
                        meter_energy_consistency_tolerance
                    ),
                    CONF_HYBRID_INVERTERS: hybrid_inverters,
                    CONF_IS_ENCRYPTED: is_encrypted,
                    CONF_ENC_RAND: enc_rand,
                    CONF_TIMEOUT: timeout,
                    CONF_STARTUP_COOLDOWN: startup_cooldown,
                    CONF_DTU_LOCATION: dtu_location,
                    CONF_INVERTER_LOCATIONS: _filter_metadata_map(
                        inverter_locations, inverter_serials
                    ),
                    CONF_INVERTER_PHASES: _filter_metadata_map(
                        inverter_phases, inverter_serials
                    ),
                }

                old_data = dict(entry.data)
                old_version = entry.version
                claimed_entry_snapshots = [
                    (claimed_entry, dict(claimed_entry.data), claimed_entry.version)
                    for claimed_entry, _updated_data in claimed_inverter_entry_updates
                ]
                self.hass.config_entries.async_update_entry(
                    entry, data=data, version=CONFIG_VERSION
                )
                await async_migrate_entity_unique_ids(self.hass, entry.entry_id, data)
                _remove_stale_metadata_entities(
                    self.hass, entry.entry_id, old_data, data
                )

                # Reload previous owners without the moved inverter before loading
                # it here. The original registry row can then be retargeted before
                # Home Assistant has any reason to create an `_2` replacement.
                reloaded_claimed_entry_ids = (
                    await _apply_claimed_inverter_entry_updates(
                        self.hass, claimed_inverter_entry_updates
                    )
                )
                if len(reloaded_claimed_entry_ids) != len(
                    claimed_inverter_entry_updates
                ):
                    self.hass.config_entries.async_update_entry(
                        entry, data=old_data, version=old_version
                    )
                    for claimed_entry, snapshot_data, snapshot_version in (
                        claimed_entry_snapshots
                    ):
                        self.hass.config_entries.async_update_entry(
                            claimed_entry,
                            data=snapshot_data,
                            version=snapshot_version,
                        )
                        if claimed_entry.entry_id in reloaded_claimed_entry_ids:
                            await self.hass.config_entries.async_reload(
                                claimed_entry.entry_id
                            )
                    errors["base"] = "unknown"
                else:
                    transfer_inverter_entity_registry_entries(
                        self.hass,
                        entry.entry_id,
                        detected_inverter_serials,
                    )
                    if not await self.hass.config_entries.async_reload(entry.entry_id):
                        self.hass.config_entries.async_update_entry(
                            entry, data=old_data, version=old_version
                        )
                        for claimed_entry, snapshot_data, snapshot_version in (
                            claimed_entry_snapshots
                        ):
                            self.hass.config_entries.async_update_entry(
                                claimed_entry,
                                data=snapshot_data,
                                version=snapshot_version,
                            )
                            claimed_serials = detected_inverter_serials & (
                                _detected_inverter_serials(
                                    snapshot_data.get(CONF_INVERTERS, []),
                                    snapshot_data.get(
                                        CONF_THREE_PHASE_INVERTERS, []
                                    ),
                                    snapshot_data.get(CONF_PORTS, []),
                                    snapshot_data.get(CONF_HYBRID_INVERTERS, []),
                                )
                            )
                            transfer_inverter_entity_registry_entries(
                                self.hass,
                                claimed_entry.entry_id,
                                claimed_serials,
                            )
                            await self.hass.config_entries.async_reload(
                                claimed_entry.entry_id
                            )
                        errors["base"] = "unknown"
                    else:
                        return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=entry.data[CONF_UPDATE_INTERVAL],
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=timedelta(seconds=MIN_UPDATE_INTERVAL_SECONDS).seconds
                        ),
                    ),
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT_SECONDS),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=timedelta(seconds=MIN_TIMEOUT_SECONDS).seconds),
                    ),
                    vol.Optional(
                        CONF_STARTUP_COOLDOWN,
                        default=entry.data.get(
                            CONF_STARTUP_COOLDOWN,
                            DEFAULT_STARTUP_COOLDOWN_SECONDS,
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=timedelta(
                                seconds=MIN_STARTUP_COOLDOWN_SECONDS
                            ).seconds
                        ),
                    ),
                    vol.Optional(
                        CONF_METER_TYPE,
                        default=entry.data.get(CONF_METER_TYPE, METER_TYPE_AUTO),
                    ): vol.In(
                        [
                            METER_TYPE_AUTO,
                            METER_TYPE_SINGLE_PHASE,
                            METER_TYPE_THREE_PHASE,
                        ]
                    ),
                    vol.Optional(
                        CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
                        default=entry.data.get(
                            CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
                            DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_METER_ENERGY_CONSISTENCY_TOLERANCE),
                    ),
                    vol.Optional(
                        CONF_DELETE_MISSING_INVERTERS,
                        default=False,
                    ): bool,
                    vol.Optional(
                        CONF_DTU_LOCATION,
                        default=entry.data.get(CONF_DTU_LOCATION, ""),
                    ): str,
                    vol.Optional(
                        CONF_INVERTER_LOCATION_MAP,
                        default=_metadata_map_to_text(
                            entry.data.get(CONF_INVERTER_LOCATIONS)
                        ),
                    ): TextSelector(TextSelectorConfig(multiline=True)),
                    vol.Optional(
                        CONF_INVERTER_PHASE_MAP,
                        default=_metadata_map_to_text(
                            entry.data.get(CONF_INVERTER_PHASES)
                        ),
                    ): TextSelector(TextSelectorConfig(multiline=True)),
                }
            ),
            errors=errors,
        )
