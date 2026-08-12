"""Test component setup."""

from homeassistant.setup import async_setup_component
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_wifi import async_remove_config_entry_device
from custom_components.hoymiles_wifi.const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_INVERTERS,
    CONF_METERS,
    CONF_PORTS,
    CONF_THREE_PHASE_INVERTERS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
)


async def test_async_setup(hass):
    """Test the component gets setup."""

    assert await async_setup_component(hass, DOMAIN, {}) is True


async def test_remove_meter_device_updates_config_entry(hass):
    """Test removing a meter device removes it from config entry data."""
    meter_serial = "10c012931030"
    other_meter_serial = "10c012931031"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DTU_SERIAL_NUMBER: "414312345678",
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_SECONDS,
            CONF_INVERTERS: [],
            CONF_THREE_PHASE_INVERTERS: [],
            CONF_PORTS: [],
            CONF_METERS: [
                {"meter_serial_number": meter_serial, "device_type": 3},
                {"meter_serial_number": other_meter_serial, "device_type": 3},
            ],
        },
    )
    entry.add_to_hass(hass)
    device_entry = DeviceEntry(
        id="meter-device",
        identifiers={(DOMAIN, meter_serial)},
    )

    assert await async_remove_config_entry_device(hass, entry, device_entry) is True
    assert entry.data[CONF_METERS] == [
        {"meter_serial_number": other_meter_serial, "device_type": 3}
    ]


async def test_remove_non_meter_device_keeps_config_entry_meters(hass):
    """Test removing another device does not remove stored meters."""
    meter_serial = "10c012931030"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_DTU_SERIAL_NUMBER: "414312345678",
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_SECONDS,
            CONF_INVERTERS: [],
            CONF_THREE_PHASE_INVERTERS: [],
            CONF_PORTS: [],
            CONF_METERS: [
                {"meter_serial_number": meter_serial, "device_type": 3},
            ],
        },
    )
    entry.add_to_hass(hass)
    device_entry = DeviceEntry(
        id="inverter-device",
        identifiers={(DOMAIN, "114112345678")},
    )

    assert await async_remove_config_entry_device(hass, entry, device_entry) is True
    assert entry.data[CONF_METERS] == [
        {"meter_serial_number": meter_serial, "device_type": 3}
    ]
