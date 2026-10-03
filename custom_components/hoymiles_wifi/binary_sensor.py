"""Contains binary sensor entities for Hoymiles WiFi integration."""

import dataclasses
from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from hoymiles_wifi.dtu import NetworkState

from .const import (
    CONF_DTU_SERIAL_NUMBER,
    DOMAIN,
    HASS_CONFIG_COORDINATOR,
    HASS_DATA_COORDINATOR,
    HASS_ENERGY_STORAGE_DATA_COORDINATOR,
)
from .entity import HoymilesCoordinatorEntity, HoymilesEntityDescription

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HoymilesBinarySensorEntityDescription(
    HoymilesEntityDescription, BinarySensorEntityDescription
):
    """Describes Homiles binary sensor entity."""


BINARY_SENSORS = (
    HoymilesBinarySensorEntityDescription(
        key="DTU",
        translation_key="dtu",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_dtu_sensor=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    hass_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = hass_data.get(HASS_DATA_COORDINATOR, None)
    if coordinator is None:
        coordinator = hass_data.get(HASS_ENERGY_STORAGE_DATA_COORDINATOR, None)

    dtu_serial_number = config_entry.data[CONF_DTU_SERIAL_NUMBER]

    hass_data = hass.data[DOMAIN][config_entry.entry_id]

    sensors = []

    for description in BINARY_SENSORS:
        updated_description = dataclasses.replace(
            description, serial_number=dtu_serial_number
        )
        sensors.append(
            HoymilesInverterSensorEntity(config_entry, updated_description, coordinator)
        )

    config_coordinator = hass_data.get(HASS_CONFIG_COORDINATOR)
    if config_coordinator is not None:
        export_sensor = HoymilesExportManagementSensorEntity(
            config_entry,
            HoymilesBinarySensorEntityDescription(
                key="zero_export_enable",
                translation_key="zero_export_enable",
                entity_category=EntityCategory.DIAGNOSTIC,
                is_dtu_sensor=True,
                serial_number=dtu_serial_number,
            ),
            config_coordinator,
        )
        _repair_export_management_entity_id(hass, export_sensor)
        sensors.append(export_sensor)

    async_add_entities(sensors)


@callback
def _repair_export_management_entity_id(hass, sensor) -> None:
    """Repair previously generated names while preserving registry identity."""
    registry = er.async_get(hass)
    existing_id = registry.async_get_entity_id("binary_sensor", DOMAIN, sensor.unique_id)
    if not existing_id or existing_id == sensor.entity_id:
        return
    if registry.async_get(sensor.entity_id) is not None:
        _LOGGER.warning(
            "Cannot rename zero-export entity %s to %s: ID already occupied",
            existing_id,
            sensor.entity_id,
        )
        return
    registry.async_update_entity(existing_id, new_entity_id=sensor.entity_id)


class HoymilesExportManagementSensorEntity(HoymilesCoordinatorEntity, BinarySensorEntity):
    """Report the zero-export flag from the DTU configuration."""

    @property
    def is_on(self) -> bool | None:
        """Return unknown when the flag is missing or unrecognized."""
        value = getattr(self.coordinator.data, "zero_export_enable", None)
        if value == 1:
            return True
        if value == 0:
            return False
        return None


class HoymilesInverterSensorEntity(HoymilesCoordinatorEntity, BinarySensorEntity):
    """Represents a binary sensor entity for Hoymiles WiFi integration."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        description: HoymilesBinarySensorEntityDescription,
        coordinator: HoymilesCoordinatorEntity,
    ):
        """Initialize the HoymilesInverterSensorEntity."""
        super().__init__(config_entry, description, coordinator)
        self._dtu = coordinator.get_dtu()
        self._native_value = None

        self.update_state_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update_state_value()
        super()._handle_coordinator_update()

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        return self._native_value

    def update_state_value(self):
        """Update connectivity from the latest real-data poll completeness."""
        poll_successful = getattr(
            self.coordinator, "real_data_poll_successful", None
        )
        if poll_successful is not None:
            self._native_value = poll_successful
            return

        dtu_state = self._dtu.get_state()
        if dtu_state == NetworkState.Online:
            self._native_value = True
        elif dtu_state == NetworkState.Offline:
            self._native_value = False
        else:
            self._native_value = None
