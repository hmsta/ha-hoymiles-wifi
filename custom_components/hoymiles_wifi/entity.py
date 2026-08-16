"""Entity base for Hoymiles entities."""

from dataclasses import dataclass
import logging

from enum import Enum
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from hoymiles_wifi.hoymiles import (
    DTUType,
    get_dtu_model_name,
    get_inverter_model_name,
    get_meter_model_name,
)

from .const import CONF_DTU_SERIAL_NUMBER, DOMAIN
from .coordinator import (
    HoymilesDataUpdateCoordinator,
)

_LOGGER = logging.getLogger(__name__)


class DeviceType(Enum):
    """Device type."""

    ALL_DEVICES = 0
    SINGLE_PHASE_METER = 1
    THREE_PHASE_METER = 3


@dataclass(frozen=True)
class HoymilesEntityDescription(EntityDescription):
    """Class to describe a Hoymiles Button entity."""

    is_dtu_sensor: bool = False
    serial_number: str = None
    port_number: int = None
    supported_dtu_types: list[DTUType] = None
    phase: str = None
    model_name: str = None


class HoymilesEntity(Entity):
    """Base class for Hoymiles entities."""

    _attr_has_entity_name = True

    def __init__(self, config_entry: ConfigEntry, description: EntityDescription):
        """Initialize the Hoymiles entity."""
        super().__init__()
        self.entity_description = description
        self._config_entry = config_entry
        self._attr_unique_id = get_hoymiles_entity_unique_id(
            config_entry.entry_id, description
        )
        self._attr_suggested_object_id = get_hoymiles_entity_object_id(description)

        if description.port_number:
            self._attr_translation_placeholders = {
                "port_number": f"{description.port_number}"
            }
        if description.phase:
            self._attr_translation_placeholders = {"phase": f"{description.phase}"}

        dtu_serial_number = config_entry.data[CONF_DTU_SERIAL_NUMBER]

        serial_number = str(self.entity_description.serial_number)
        serial_number_upper = serial_number.upper()

        if self.entity_description.is_dtu_sensor is True:
            device_name = "DTU"
            device_model = get_dtu_model_name(self.entity_description.serial_number)
        else:
            if "meter" in self.entity_description.key:
                device_model = (
                    self.entity_description.model_name
                    or get_meter_model_name(self.entity_description.serial_number)
                )
                device_name = "Meter"
            else:
                if self.entity_description.model_name:
                    device_model = self.entity_description.model_name
                    device_name = "Hybrid inverter"
                else:
                    device_model = get_inverter_model_name(
                        self.entity_description.serial_number
                    )
                    device_name = "Inverter"

        device_info = DeviceInfo(
            identifiers={(DOMAIN, serial_number)},
            name=f"{device_name} {serial_number_upper}",
            manufacturer="Hoymiles",
            serial_number=serial_number_upper,
            model=device_model,
        )

        if (
            not self.entity_description.is_dtu_sensor
            and "meter" not in self.entity_description.key
        ):
            device_info["via_device"] = (DOMAIN, dtu_serial_number)

        self._attr_device_info = device_info


def get_hoymiles_entity_unique_id(entry_id: str, description: EntityDescription) -> str:
    """Build a stable unique ID for a Hoymiles entity."""
    key = description.key
    serial_number = getattr(description, "serial_number", None)
    if serial_number is None or "[" not in key:
        return f"hoymiles_{entry_id}_{key}"

    stable_key = re.sub(r"\[\d+\]", "", key).lstrip(".")
    unique_id_parts = [
        "hoymiles",
        entry_id,
        str(serial_number).lower(),
    ]

    port_number = getattr(description, "port_number", None)
    if port_number is not None:
        unique_id_parts.append(f"port_{port_number}")

    phase = getattr(description, "phase", None)
    if phase is not None:
        unique_id_parts.append(f"phase_{str(phase).lower()}")

    unique_id_parts.append(stable_key)
    return "_".join(unique_id_parts)


ENTITY_OBJECT_ID_SUFFIX_OVERRIDES = {
    "ac_active_power": "ac_power",
    "dtu": "connectivity",
    "energy_total_consumed": "energy_imported",
    "energy_total_power": "energy_exported",
    "inverter_power_factor": "power_factor",
    "inverter_temperature": "temperature",
    "inverter_warning_number": "warning_number",
    "limit_power_mypower": "power_limit",
    "port_error_code": "error_code",
    "pv_hw_version": "hw_version",
    "pv_sw_version": "sw_version",
}


def get_hoymiles_entity_object_id(description: EntityDescription) -> str:
    """Build the canonical serial-based HA object ID for a Hoymiles entity."""
    serial_number = str(getattr(description, "serial_number", "")).lower()
    device_prefix = _entity_object_id_device_prefix(description)
    suffix = _entity_object_id_suffix(description)

    object_id_parts = [device_prefix, serial_number]

    port_number = getattr(description, "port_number", None)
    if port_number is not None:
        object_id_parts.extend(("port", str(port_number)))

    object_id_parts.append(suffix)

    return _slug_part("_".join(part for part in object_id_parts if part))


def _entity_object_id_device_prefix(description: EntityDescription) -> str:
    """Return the canonical object ID device prefix."""
    key = description.key

    if getattr(description, "is_dtu_sensor", False):
        return "dtu"
    if "meter" in key:
        return "meter"
    if getattr(description, "model_name", None):
        return "hybrid_inverter"
    return "inverter"


def _entity_object_id_suffix(description: EntityDescription) -> str:
    """Return the canonical object ID suffix."""
    suffix = getattr(description, "translation_key", None) or _stable_object_key(
        description.key
    )
    suffix = ENTITY_OBJECT_ID_SUFFIX_OVERRIDES.get(suffix, suffix)

    port_number = getattr(description, "port_number", None)
    if port_number is not None:
        suffix = re.sub(r"^(port|pv_panel)_", "", suffix)

    phase = getattr(description, "phase", None)
    if phase is not None and suffix.endswith("_phase"):
        suffix = f"{suffix}_{str(phase).lower()}"

    return suffix


def _stable_object_key(key: str) -> str:
    """Return a fallback object suffix from an entity description key."""
    key = re.sub(r"\[\d+\]", "", key)
    key = re.sub(r"<[^>]+>", "", key)
    return key.strip("._")


def _slug_part(value: str) -> str:
    """Return a Home Assistant object-id-safe slug fragment."""
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", value)
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value.lower()


class HoymilesCoordinatorEntity(CoordinatorEntity, HoymilesEntity):
    """Represents a Hoymiles coordinator entity."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        description: EntityDescription,
        coordinator: HoymilesDataUpdateCoordinator,
    ):
        """Pass coordinator to CoordinatorEntity."""
        CoordinatorEntity.__init__(self, coordinator)
        HoymilesEntity.__init__(self, config_entry, description)
