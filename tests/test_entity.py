"""Unit tests for Hoymiles entities."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.hoymiles_wifi.const import CONF_DTU_SERIAL_NUMBER, DOMAIN
from custom_components.hoymiles_wifi.entity import (
    HoymilesEntity,
    HoymilesEntityDescription,
    _get_inverter_model_name,
)
from custom_components.hoymiles_wifi.entity_migration import (
    transfer_inverter_entity_registry_entries,
)


DTU_SERIAL_NUMBER = "4121a01953c8"


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
    inverter_serial = "1121a01a4525"
    _get_inverter_model_name.cache_clear()

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

    assert device_info["name"] == "Inverter 1121A01A4525"
    assert device_info["identifiers"] == {(DOMAIN, inverter_serial)}
    assert device_info["serial_number"] == "1121A01A4525"
    assert device_info["via_device"] == (DOMAIN, DTU_SERIAL_NUMBER)


def test_inverter_1421_device_uses_hms_2000d_4t_model_override() -> None:
    """Test HMS-2000D-4T serials avoid the noisy library model lookup."""
    inverter_serial = "1421a01a4525"
    _get_inverter_model_name.cache_clear()

    with patch(
        "custom_components.hoymiles_wifi.entity.get_inverter_model_name",
        side_effect=AssertionError("library lookup should not be called"),
    ):
        device_info = _device_info(
            HoymilesEntityDescription(
                key="sgs_data[0].current",
                serial_number=inverter_serial,
            )
        )

    assert device_info["model"] == "HMS-2000D-4T"


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
    assert "via_device" not in device_info


def test_meter_device_uses_explicit_model_name() -> None:
    """Test meter device model can be overridden from detected meter type."""
    meter_serial = "10c012931030"

    device_info = _device_info(
        HoymilesEntityDescription(
            key="meter_data[0].phase_total_power",
            serial_number=meter_serial,
            model_name="DTSU666",
        )
    )

    assert device_info["model"] == "DTSU666"


def test_transfer_inverter_registry_entries_preserves_original_entity() -> None:
    """Test a moved inverter keeps its original entity ID and history identity."""
    serial_number = "1421a01a4525"
    original = SimpleNamespace(
        config_entry_id="old-entry",
        domain="sensor",
        entity_id=f"sensor.inverter_{serial_number}_ac_power",
        platform=DOMAIN,
        unique_id=f"hoymiles_old-entry_{serial_number}_ac_active_power",
    )
    replacement = SimpleNamespace(
        config_entry_id="new-entry",
        domain="sensor",
        entity_id=f"sensor.inverter_{serial_number}_ac_power_2",
        platform=DOMAIN,
        unique_id=f"hoymiles_new-entry_{serial_number}_ac_active_power",
    )
    unrelated = SimpleNamespace(
        config_entry_id="old-entry",
        domain="sensor",
        entity_id="sensor.inverter_1421a01a9999_ac_power",
        platform=DOMAIN,
        unique_id="hoymiles_old-entry_1421a01a9999_ac_active_power",
    )
    registry = MagicMock()
    registry.entities = {
        entity.entity_id: entity for entity in (original, replacement, unrelated)
    }

    hass = MagicMock()
    with (
        patch(
            "custom_components.hoymiles_wifi.entity_migration.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.hoymiles_wifi.entity_migration.entity_sources",
            return_value={},
        ),
    ):
        repaired = transfer_inverter_entity_registry_entries(
            hass, "new-entry", {serial_number}
        )

    assert repaired is True
    registry.async_remove.assert_called_once_with(replacement.entity_id)
    registry.async_update_entity.assert_called_once_with(
        original.entity_id,
        config_entry_id="new-entry",
        new_unique_id=f"hoymiles_new-entry_{serial_number}_ac_active_power",
    )


def test_transfer_inverter_registry_entry_before_new_owner_loads() -> None:
    """Test a move retargets the original row without creating a duplicate."""
    serial_number = "1421a01a4525"
    original = SimpleNamespace(
        config_entry_id="old-entry",
        domain="sensor",
        entity_id=f"sensor.inverter_{serial_number}_ac_power",
        platform=DOMAIN,
        unique_id=f"hoymiles_old-entry_{serial_number}_ac_active_power",
    )
    registry = MagicMock()
    registry.entities = {original.entity_id: original}

    with (
        patch(
            "custom_components.hoymiles_wifi.entity_migration.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.hoymiles_wifi.entity_migration.entity_sources",
            return_value={},
        ),
    ):
        repaired = transfer_inverter_entity_registry_entries(
            MagicMock(), "new-entry", {serial_number}
        )

    assert repaired is True
    registry.async_remove.assert_not_called()
    registry.async_update_entity.assert_called_once_with(
        original.entity_id,
        config_entry_id="new-entry",
        new_unique_id=f"hoymiles_new-entry_{serial_number}_ac_active_power",
    )


@pytest.mark.parametrize(
    ("button_key", "entity_suffix"),
    [
        ("turn_off_inverter", "turn_off"),
        ("turn_on_inverter", "turn_on"),
        ("reboot_inverter", "restart"),
    ],
)
def test_transfer_inverter_button_preserves_original_entity(
    button_key: str, entity_suffix: str
) -> None:
    """Test moved inverter controls retain their old registry rows and IDs."""
    serial_number = "1421a01a4bb2"
    original = SimpleNamespace(
        config_entry_id="old-entry",
        domain="button",
        entity_id=f"button.inverter_{serial_number}_{entity_suffix}",
        platform=DOMAIN,
        unique_id=f"hoymiles_old-entry_{button_key}_{serial_number}",
    )
    replacement = SimpleNamespace(
        config_entry_id="new-entry",
        domain="button",
        entity_id=f"button.solar_inverter_inverter_{serial_number}_{entity_suffix}",
        platform=DOMAIN,
        unique_id=f"hoymiles_new-entry_{button_key}_{serial_number}",
    )
    registry = MagicMock()
    registry.entities = {
        entity.entity_id: entity for entity in (original, replacement)
    }

    with (
        patch(
            "custom_components.hoymiles_wifi.entity_migration.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.hoymiles_wifi.entity_migration.entity_sources",
            return_value={},
        ),
    ):
        repaired = transfer_inverter_entity_registry_entries(
            MagicMock(), "new-entry", {serial_number}
        )

    assert repaired is True
    registry.async_remove.assert_called_once_with(replacement.entity_id)
    registry.async_update_entity.assert_called_once_with(
        original.entity_id,
        config_entry_id="new-entry",
        new_unique_id=f"hoymiles_new-entry_{button_key}_{serial_number}",
    )


def test_hybrid_inverter_device_name_includes_serial() -> None:
    """Test hybrid inverter device name includes serial number."""
    hybrid_serial = "1121a01b9999"

    device_info = _device_info(
        HoymilesEntityDescription(
            key="[0].power_flow.pv_to_load",
            serial_number=hybrid_serial,
            model_name="Hybrid model",
        )
    )

    assert device_info["name"] == "Hybrid inverter 1121A01B9999"
    assert device_info["identifiers"] == {(DOMAIN, hybrid_serial)}
    assert device_info["serial_number"] == "1121A01B9999"
    assert device_info["via_device"] == (DOMAIN, DTU_SERIAL_NUMBER)
