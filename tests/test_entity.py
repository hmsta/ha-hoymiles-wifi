"""Unit tests for Hoymiles entities."""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

from custom_components.hoymiles_wifi.const import CONF_DTU_SERIAL_NUMBER, DOMAIN
from custom_components.hoymiles_wifi.entity import (
    HoymilesEntity,
    HoymilesEntityDescription,
)


DTU_SERIAL_NUMBER = "4121a01953c8"


@dataclass(frozen=True)
class HybridEntityDescription(HoymilesEntityDescription):
    """Entity description with hybrid inverter model information."""

    model_name: str = None


def _config_entry():
    """Build minimal config entry for entity construction."""
    return SimpleNamespace(
        entry_id="test-entry",
        data={CONF_DTU_SERIAL_NUMBER: DTU_SERIAL_NUMBER},
    )


def _device_info(description: HoymilesEntityDescription):
    """Build device info for a description."""
    entity = HoymilesEntity(_config_entry(), description)
    return entity.device_info


def test_dtu_device_name_includes_serial() -> None:
    """Test DTU device name includes serial number."""
    with patch(
        "custom_components.hoymiles_wifi.entity.get_dtu_model_name",
        return_value="DTU model",
    ):
        device_info = _device_info(
            HoymilesEntityDescription(
                key="DTU",
                serial_number=DTU_SERIAL_NUMBER,
                is_dtu_sensor=True,
            )
        )

    assert device_info["name"] == "DTU 4121A01953C8"
    assert device_info["identifiers"] == {(DOMAIN, DTU_SERIAL_NUMBER)}
    assert device_info["serial_number"] == "4121A01953C8"
    assert "via_device" not in device_info


def test_inverter_device_name_includes_serial() -> None:
    """Test inverter device name includes serial number."""
    inverter_serial = "1421a01a4525"

    with patch(
        "custom_components.hoymiles_wifi.entity.get_inverter_model_name",
        return_value="Inverter model",
    ):
        device_info = _device_info(
            HoymilesEntityDescription(
                key="sgs_data[0].current",
                serial_number=inverter_serial,
            )
        )

    assert device_info["name"] == "Inverter 1421A01A4525"
    assert device_info["identifiers"] == {(DOMAIN, inverter_serial)}
    assert device_info["serial_number"] == "1421A01A4525"
    assert device_info["via_device"] == (DOMAIN, DTU_SERIAL_NUMBER)


def test_meter_device_name_includes_serial() -> None:
    """Test meter device name includes serial number."""
    meter_serial = "10c012931030"

    with patch(
        "custom_components.hoymiles_wifi.entity.get_meter_model_name",
        return_value="Meter model",
    ):
        device_info = _device_info(
            HoymilesEntityDescription(
                key="meter_data[0].phase_total_power",
                serial_number=meter_serial,
            )
        )

    assert device_info["name"] == "Meter 10C012931030"
    assert device_info["identifiers"] == {(DOMAIN, meter_serial)}
    assert device_info["serial_number"] == "10C012931030"
    assert device_info["via_device"] == (DOMAIN, DTU_SERIAL_NUMBER)


def test_hybrid_inverter_device_name_includes_serial() -> None:
    """Test hybrid inverter device name includes serial number."""
    hybrid_serial = "1121a01b9999"

    device_info = _device_info(
        HybridEntityDescription(
            key="[0].power_flow.pv_to_load",
            serial_number=hybrid_serial,
            model_name="Hybrid model",
        )
    )

    assert device_info["name"] == "Hybrid inverter 1121A01B9999"
    assert device_info["identifiers"] == {(DOMAIN, hybrid_serial)}
    assert device_info["serial_number"] == "1121A01B9999"
    assert device_info["via_device"] == (DOMAIN, DTU_SERIAL_NUMBER)
