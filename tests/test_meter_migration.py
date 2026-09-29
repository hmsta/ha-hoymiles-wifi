"""Regression coverage for meter ownership and existing entity identities."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_wifi.const import CONF_METERS, DOMAIN
from custom_components.hoymiles_wifi.entity import (
    HoymilesEntityDescription,
    get_hoymiles_entity_unique_id,
)
from custom_components.hoymiles_wifi.entity_migration import (
    migrate_meter_entity_registry_entries,
)

SERIAL = "10c000000001"
FIELD = "current_phase_A"
STABLE_ID = f"hoymiles_meter_{SERIAL}_meter_data.{FIELD}"


def test_meter_identity_does_not_depend_on_dtu_or_index():
    """Another polling DTU or a reordered discovery list is the same meter."""
    description = HoymilesEntityDescription(
        key=f"meter_data[0].{FIELD}", serial_number=SERIAL.upper()
    )
    assert get_hoymiles_entity_unique_id("old", description) == STABLE_ID
    assert get_hoymiles_entity_unique_id(
        "new", replace(description, key=f"meter_data[3].{FIELD}")
    ) == STABLE_ID


def _entries(hass):
    old = MockConfigEntry(domain=DOMAIN, entry_id="old", data={CONF_METERS: []})
    new = MockConfigEntry(
        domain=DOMAIN, entry_id="new",
        data={CONF_METERS: [{"meter_serial_number": SERIAL, "device_type": 3}]},
    )
    old.add_to_hass(hass)
    new.add_to_hass(hass)
    return old, new


@pytest.mark.parametrize("legacy", [True, False])
@pytest.mark.parametrize("duplicate", [True, False])
async def test_reuse_original_entity_and_settings(hass, legacy, duplicate, caplog):
    """Restore the old entity without renaming either recorder identity."""
    old, new = _entries(hass)
    registry = er.async_get(hass)
    original = registry.async_get_or_create(
        "sensor", DOMAIN,
        f"hoymiles_old_meter_data[0].{FIELD}" if legacy
        else f"hoymiles_old_{SERIAL}_meter_data.{FIELD}",
        config_entry=old, suggested_object_id=f"zzz_meter_{SERIAL}_current_phase_a",
    )
    registry.async_update_entity(original.entity_id, name="My meter current")
    if duplicate:
        replacement = registry.async_get_or_create(
            "sensor", DOMAIN, f"hoymiles_new_{SERIAL}_meter_data.{FIELD}",
            config_entry=new, suggested_object_id=f"solar_meter_{SERIAL}_current_phase_a",
        )
    with patch(
        "custom_components.hoymiles_wifi.entity_migration.entity_sources", return_value={}
    ):
        migrate_meter_entity_registry_entries(hass, new)
        migrate_meter_entity_registry_entries(hass, new)

    repaired = registry.async_get(original.entity_id)
    assert repaired.unique_id == STABLE_ID
    assert repaired.config_entry_id == new.entry_id
    assert repaired.name == "My meter current"
    assert repaired.id == original.id
    if duplicate:
        assert registry.async_get(replacement.entity_id) is None
        assert f"{replacement.entity_id} -> {original.entity_id}" in caplog.text


async def test_live_owner_blocks_migration_before_any_changes(hass):
    """Do not steal a loaded meter or delete its replacement during reload."""
    old, new = _entries(hass)
    registry = er.async_get(hass)
    original = registry.async_get_or_create(
        "sensor", DOMAIN, f"hoymiles_old_{SERIAL}_meter_data.{FIELD}",
        config_entry=old,
    )
    with patch(
        "custom_components.hoymiles_wifi.entity_migration.entity_sources",
        return_value={original.entity_id: {}},
    ), pytest.raises(ConfigEntryNotReady, match="Restart Home Assistant"):
        migrate_meter_entity_registry_entries(hass, new)
    assert registry.async_get(original.entity_id) == original


async def test_duplicate_config_owners_do_not_steal_meter(hass):
    """Ambiguous configuration must not depend on startup order."""
    old, new = _entries(hass)
    hass.config_entries.async_update_entry(old, data=dict(new.data))
    with pytest.raises(ConfigEntryNotReady, match="multiple DTUs"):
        migrate_meter_entity_registry_entries(hass, new)


async def test_meter_repair_leaves_other_devices_unchanged(hass):
    """Match physical serial and meter field, not a similar display name."""
    old, new = _entries(hass)
    registry = er.async_get(hass)
    unrelated = [
        registry.async_get_or_create(
            "sensor", DOMAIN, unique_id, config_entry=old,
            suggested_object_id=f"meter_{SERIAL}_unrelated_{index}",
        )
        for index, unique_id in enumerate([
            f"hoymiles_old_{SERIAL}_sgs_data.active_power",
            "hoymiles_old_10c000000002_meter_data.current_phase_A",
        ])
    ]
    migrate_meter_entity_registry_entries(hass, new)
    for entity in unrelated:
        assert registry.async_get(entity.entity_id) == entity


async def test_setup_resumes_original_meter_with_live_shared_data(hass):
    """Exercise setup, registry migration, platform loading and a real update."""
    from homeassistant.config_entries import ConfigEntryDisabler
    from homeassistant.const import CONF_HOST
    from custom_components.hoymiles_wifi.const import (
        CONF_DTU_SERIAL_NUMBER, CONF_INVERTERS, CONF_PORTS, CONF_UPDATE_INTERVAL,
        CONFIG_VERSION, HASS_SHARED_METER_COORDINATOR,
    )

    old = MockConfigEntry(
        domain=DOMAIN, entry_id="old", data={}, disabled_by=ConfigEntryDisabler.USER,
    )
    new = MockConfigEntry(
        domain=DOMAIN, entry_id="new", version=CONFIG_VERSION,
        data={
            CONF_HOST: "192.0.2.1", CONF_DTU_SERIAL_NUMBER: "412100000001",
            CONF_INVERTERS: [], CONF_PORTS: [], CONF_UPDATE_INTERVAL: 30,
            CONF_METERS: [{"meter_serial_number": SERIAL, "device_type": 3}],
        },
    )
    old.add_to_hass(hass)
    new.add_to_hass(hass)
    registry = er.async_get(hass)
    original = registry.async_get_or_create(
        "sensor", DOMAIN, f"hoymiles_old_{SERIAL}_meter_data.{FIELD}",
        config_entry=old, suggested_object_id=f"meter_{SERIAL}_current_phase_a",
    )
    replacement = registry.async_get_or_create(
        "sensor", DOMAIN, f"hoymiles_new_{SERIAL}_meter_data.{FIELD}",
        config_entry=new, suggested_object_id=f"solar_meter_{SERIAL}_current_phase_a",
    )
    with (
        patch("custom_components.hoymiles_wifi._async_register_frontend", new=AsyncMock()),
        patch("custom_components.hoymiles_wifi.HoymilesRealDataUpdateCoordinator.schedule_startup_refresh"),
        patch("custom_components.hoymiles_wifi.HoymilesConfigUpdateCoordinator.async_config_entry_first_refresh", new=AsyncMock()),
        patch("custom_components.hoymiles_wifi.HoymilesAppInfoUpdateCoordinator.async_config_entry_first_refresh", new=AsyncMock()),
        patch("custom_components.hoymiles_wifi.sensor.HoymilesEnergySensorEntity.schedule_midnight_reset"),
    ):
        assert await hass.config_entries.async_setup(new.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][HASS_SHARED_METER_COORDINATOR]
        coordinator.async_set_updated_data({SERIAL: {"values": {FIELD: 1234}}})
        await hass.async_block_till_done()

    assert hass.states.get(original.entity_id).state == "12.34"
    assert registry.async_get(original.entity_id).unique_id == STABLE_ID
    assert registry.async_get(replacement.entity_id) is None
