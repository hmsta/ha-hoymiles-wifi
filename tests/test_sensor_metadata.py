"""Tests for static Hoymiles metadata sensors."""

from types import SimpleNamespace

from custom_components.hoymiles_wifi.const import (
    CONF_DTU_LOCATION,
    CONF_DTU_SERIAL_NUMBER,
    CONF_INVERTER_LOCATIONS,
    CONF_INVERTER_PHASES,
    DOMAIN,
)
from custom_components.hoymiles_wifi.sensor import _metadata_sensors


DTU_SERIAL_NUMBER = "4121A01953C8"
INVERTER_SERIAL_NUMBER = "1421a01a4ff5"


def _config_entry(data: dict):
    """Build a minimal config entry for metadata entity construction."""
    return SimpleNamespace(entry_id="test-entry", data=data)


def test_metadata_sensors_attach_to_expected_devices() -> None:
    """Test static metadata sensors use canonical object IDs and device info."""
    entry = _config_entry(
        {
            CONF_DTU_SERIAL_NUMBER: DTU_SERIAL_NUMBER,
            CONF_DTU_LOCATION: "Plant room",
            CONF_INVERTER_LOCATIONS: {INVERTER_SERIAL_NUMBER: "53"},
            CONF_INVERTER_PHASES: {INVERTER_SERIAL_NUMBER: "2"},
        }
    )

    sensors = _metadata_sensors(
        entry,
        [INVERTER_SERIAL_NUMBER],
        [{"inverter_serial_number": INVERTER_SERIAL_NUMBER, "port_number": 1}],
        [],
    )

    by_object_id = {
        sensor._attr_suggested_object_id: sensor for sensor in sensors
    }

    assert set(by_object_id) == {
        "dtu_4121a01953c8_location",
        "inverter_1421a01a4ff5_location",
        "inverter_1421a01a4ff5_phase",
    }
    assert by_object_id["dtu_4121a01953c8_location"].native_value == "Plant room"
    assert by_object_id["inverter_1421a01a4ff5_location"].native_value == "53"
    assert by_object_id["inverter_1421a01a4ff5_phase"].native_value == "2"
    assert (
        by_object_id["dtu_4121a01953c8_location"]._attr_entity_id
        == "sensor.dtu_4121a01953c8_location"
    )
    assert (
        by_object_id["inverter_1421a01a4ff5_location"]._attr_entity_id
        == "sensor.inverter_1421a01a4ff5_location"
    )
    assert by_object_id["dtu_4121a01953c8_location"].device_info[
        "identifiers"
    ] == {(DOMAIN, DTU_SERIAL_NUMBER)}
    assert by_object_id["inverter_1421a01a4ff5_phase"].device_info[
        "identifiers"
    ] == {(DOMAIN, INVERTER_SERIAL_NUMBER)}


def test_empty_metadata_does_not_create_entities() -> None:
    """Test empty metadata fields do not create placeholder sensors."""
    entry = _config_entry(
        {
            CONF_DTU_SERIAL_NUMBER: DTU_SERIAL_NUMBER,
            CONF_DTU_LOCATION: "",
            CONF_INVERTER_LOCATIONS: {},
            CONF_INVERTER_PHASES: {},
        }
    )

    assert _metadata_sensors(entry, [INVERTER_SERIAL_NUMBER], [], []) == []
