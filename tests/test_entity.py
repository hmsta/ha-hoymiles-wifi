"""Unit tests for Hoymiles entities."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.helpers.entity import Entity

from custom_components.hoymiles_wifi import binary_sensor, button, number, sensor
from custom_components.hoymiles_wifi.const import CONF_DTU_SERIAL_NUMBER, DOMAIN
from custom_components.hoymiles_wifi.entity import (
    HoymilesEntity,
    HoymilesEntityDescription,
    _get_inverter_model_name,
)
from custom_components.hoymiles_wifi.entity_migration import (
    _repair_inverter_device_registry_entries,
    transfer_inverter_entity_registry_entries,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry


DTU_SERIAL_NUMBER = "4121a01953c8"


@pytest.mark.parametrize(
    ("entity_class", "domain"),
    [
        (entity_class, domain)
        for module, domain in (
            (sensor, "sensor"),
            (binary_sensor, "binary_sensor"),
            (button, "button"),
            (number, "number"),
        )
        for entity_class in vars(module).values()
        if isinstance(entity_class, type)
        and entity_class.__module__ == module.__name__
        and issubclass(entity_class, Entity)
    ],
)
def test_all_entity_classes_receive_explicit_ids(entity_class, domain) -> None:
    """Every concrete entity must get a real ID from the shared initializer."""
    entity = entity_class.__new__(entity_class)
    description = HoymilesEntityDescription(
        key="sgs_data[0].inverter_temperature",
        translation_key="inverter_temperature",
        serial_number="1421A01A4525",
    )
    HoymilesEntity.__init__(entity, _config_entry(), description)
    assert entity.entity_id == f"{domain}.inverter_1421a01a4525_temperature"


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


async def test_transfer_repairs_stale_inverter_device_config_entry(
    hass: HomeAssistant,
) -> None:
    """Test an already moved inverter drops its previous DTU association."""
    serial_number = "1421a01a4bb2"
    old_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="old-entry",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    target_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="new-entry",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c9"},
    )
    old_entry.add_to_hass(hass)
    target_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    old_dtu_device = device_registry.async_get_or_create(
        config_entry_id=old_entry.entry_id,
        identifiers={(DOMAIN, old_entry.data[CONF_DTU_SERIAL_NUMBER])},
    )
    target_dtu_device = device_registry.async_get_or_create(
        config_entry_id=target_entry.entry_id,
        identifiers={(DOMAIN, target_entry.data[CONF_DTU_SERIAL_NUMBER])},
    )
    device = device_registry.async_get_or_create(
        config_entry_id=old_entry.entry_id,
        identifiers={(DOMAIN, serial_number)},
        via_device=(DOMAIN, old_entry.data[CONF_DTU_SERIAL_NUMBER]),
    )
    device_registry.async_update_device(
        device.id,
        add_config_entry_id=target_entry.entry_id,
    )

    repaired = transfer_inverter_entity_registry_entries(
        hass, target_entry.entry_id, {serial_number}
    )

    assert repaired is True
    assert device_registry.async_get(device.id).config_entries == {
        target_entry.entry_id
    }
    assert device_registry.async_get(device.id).via_device_id == target_dtu_device.id
    assert device_registry.async_get(device.id).via_device_id != old_dtu_device.id


async def test_transfer_adds_owner_before_removing_stale_owner(
    hass: HomeAssistant,
) -> None:
    """Test moving a device keeps the new owner's subentry association intact."""
    serial_number = "1421a01a5294"
    old_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="old-entry",
        data={CONF_DTU_SERIAL_NUMBER: "4121A01953C8"},
    )
    target_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="new-entry",
        data={CONF_DTU_SERIAL_NUMBER: "4121A01954D1"},
    )
    old_entry.add_to_hass(hass)
    target_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=target_entry.entry_id,
        identifiers={(DOMAIN, target_entry.data[CONF_DTU_SERIAL_NUMBER])},
    )
    device = device_registry.async_get_or_create(
        config_entry_id=old_entry.entry_id,
        identifiers={(DOMAIN, serial_number)},
        via_device=(DOMAIN, old_entry.data[CONF_DTU_SERIAL_NUMBER]),
    )

    repaired = transfer_inverter_entity_registry_entries(
        hass, target_entry.entry_id, {serial_number}
    )

    assert repaired is True
    repaired_device = device_registry.async_get(device.id)
    assert repaired_device.config_entries == {target_entry.entry_id}
    assert repaired_device.config_entries_subentries == {
        target_entry.entry_id: {None}
    }


def test_transfer_repairs_missing_config_entry_subentry_mapping() -> None:
    """Test startup repairs the malformed ownership written by the old code."""
    serial_number = "1421a01a5294"
    target_entry = SimpleNamespace(
        entry_id="new-entry",
        domain=DOMAIN,
        data={CONF_DTU_SERIAL_NUMBER: "4121A01954D1"},
    )
    target_dtu_device = SimpleNamespace(id="target-dtu-device")
    malformed_device = dr.DeviceEntry(
        id="inverter-device",
        config_entries={target_entry.entry_id},
        config_entries_subentries={},
        via_device_id=target_dtu_device.id,
        identifiers={(DOMAIN, serial_number)},
    )
    registry = MagicMock()
    registry.devices = {}
    registry.async_get_device.side_effect = [target_dtu_device, malformed_device]
    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = target_entry

    with patch(
        "custom_components.hoymiles_wifi.entity_migration.dr.async_get",
        return_value=registry,
    ):
        repaired = _repair_inverter_device_registry_entries(
            hass, target_entry.entry_id, {serial_number}
        )

    assert repaired is True
    assert registry.devices[malformed_device.id].config_entries_subentries == {
        target_entry.entry_id: {None}
    }
    registry.async_schedule_save.assert_called_once_with()
    registry.async_update_device.assert_not_called()


async def test_transfer_repairs_stale_inverter_via_device(
    hass: HomeAssistant,
) -> None:
    """Test a moved inverter with correct ownership gets its new parent DTU."""
    serial_number = "1421a01a4ffc"
    old_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="old-entry",
        data={CONF_DTU_SERIAL_NUMBER: "4121A0194D6C"},
    )
    target_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="new-entry",
        data={CONF_DTU_SERIAL_NUMBER: "4121A0194E49"},
    )
    old_entry.add_to_hass(hass)
    target_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    old_dtu_device = device_registry.async_get_or_create(
        config_entry_id=old_entry.entry_id,
        identifiers={(DOMAIN, old_entry.data[CONF_DTU_SERIAL_NUMBER])},
    )
    target_dtu_device = device_registry.async_get_or_create(
        config_entry_id=target_entry.entry_id,
        identifiers={(DOMAIN, target_entry.data[CONF_DTU_SERIAL_NUMBER])},
    )
    device = device_registry.async_get_or_create(
        config_entry_id=target_entry.entry_id,
        identifiers={(DOMAIN, serial_number)},
        via_device=(DOMAIN, old_entry.data[CONF_DTU_SERIAL_NUMBER]),
    )

    repaired = transfer_inverter_entity_registry_entries(
        hass, target_entry.entry_id, {serial_number}
    )

    assert repaired is True
    repaired_device = device_registry.async_get(device.id)
    assert repaired_device.config_entries == {target_entry.entry_id}
    assert repaired_device.via_device_id == target_dtu_device.id
    assert repaired_device.via_device_id != old_dtu_device.id


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
