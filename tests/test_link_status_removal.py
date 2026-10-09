"""Regression coverage for removing retired link-status registry entries."""

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_wifi.const import DOMAIN
from custom_components.hoymiles_wifi.entity_migration import (
    remove_obsolete_link_status_entities,
)


@pytest.mark.parametrize("field", ["sgs_data", "tgs_data"])
@pytest.mark.parametrize("legacy", [False, True])
async def test_remove_only_owned_link_status_entities(hass, field, legacy):
    """Clean renamed/disabled entities without relying on their entity IDs."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry-a", data={})
    other = MockConfigEntry(domain=DOMAIN, entry_id="entry-b", data={})
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    tail = f"{field}[2].link_status" if legacy else f"1421a01a4a58_{field}.link_status"
    unique_id = f"hoymiles_{entry.entry_id}_{tail}"
    retired = registry.async_get_or_create(
        "sensor", DOMAIN, unique_id, config_entry=entry,
        suggested_object_id="my_custom_radio_diagnostic",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    preserved = [
        registry.async_get_or_create(
            "sensor", DOMAIN, f"hoymiles_{other.entry_id}_{tail}",
            config_entry=other,
        ),
        registry.async_get_or_create(
            "sensor", DOMAIN, unique_id.replace("link_status", "modulation_index_signal"),
            config_entry=entry,
        ),
        registry.async_get_or_create(
            "sensor", DOMAIN, unique_id.replace(field, "pv_data"),
            config_entry=entry,
        ),
        registry.async_get_or_create(
            "binary_sensor", DOMAIN, unique_id, config_entry=entry,
        ),
        registry.async_get_or_create(
            "sensor", "another_integration", unique_id, config_entry=entry,
        ),
    ]

    remove_obsolete_link_status_entities(hass, entry)
    remove_obsolete_link_status_entities(hass, entry)

    assert registry.async_get(retired.entity_id) is None
    for entity in preserved:
        assert registry.async_get(entity.entity_id) == entity
