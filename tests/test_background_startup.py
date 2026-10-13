"""Startup must finish without waiting for DTU network responses."""

import asyncio
from contextlib import ExitStack
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_wifi import async_setup_entry, async_unload_entry
from custom_components.hoymiles_wifi.const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_HYBRID_INVERTERS,
    CONF_INVERTERS,
    CONF_THREE_PHASE_INVERTERS,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    HASS_APP_INFO_COORDINATOR,
    HASS_CONFIG_COORDINATOR,
    HASS_DATA_COORDINATOR,
    HASS_ENERGY_STORAGE_DATA_COORDINATOR,
)
from custom_components.hoymiles_wifi.coordinator import (
    HoymilesAppInfoUpdateCoordinator,
    HoymilesConfigUpdateCoordinator,
    HoymilesEnergyStorageUpdateCoordinator,
)


@pytest.mark.parametrize("hybrid", [False, True])
async def test_pending_dtu_reads_do_not_block_startup_and_cancel_on_unload(hass, hybrid):
    """Exercise setup and HA task tracking with network reads that never return."""
    started = set()
    cancelled = set()
    all_started = asyncio.Event()
    expected = {"real", "config", "app"} | ({"storage"} if hybrid else set())

    def read(name):
        async def pending(*args, **kwargs):
            started.add(name)
            if started == expected:
                all_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.add(name)
        return pending

    dtu = SimpleNamespace(
        async_send_request=read("real"),
        async_get_config=read("config"),
        async_app_information_data=read("app"),
        async_get_energy_storage_data=read("storage"),
    )
    entry = MockConfigEntry(domain=DOMAIN, data={
        "host": "192.0.2.1",
        CONF_DTU_SERIAL_NUMBER: "412100195308",
        CONF_INVERTERS: ["1421a01a4a58"],
        CONF_THREE_PHASE_INVERTERS: [],
        CONF_HYBRID_INVERTERS: [{"inverter_serial_number": 123}] if hybrid else [],
        CONF_UPDATE_INTERVAL: 300,
    })
    entry.add_to_hass(hass)
    coordinators = []
    remove_listeners = []

    async def forward(config_entry, platforms):
        data = hass.data[DOMAIN][entry.entry_id]
        for key in (
            HASS_DATA_COORDINATOR, HASS_CONFIG_COORDINATOR,
            HASS_APP_INFO_COORDINATOR, HASS_ENERGY_STORAGE_DATA_COORDINATOR,
        ):
            if coordinator := data.get(key):
                coordinators.append(coordinator)
                remove_listeners.append(coordinator.async_add_listener(lambda: None))

    async def unload(config_entry, platforms):
        for remove in remove_listeners:
            remove()
        return True

    with ExitStack() as stack:
        stack.enter_context(patch(
            "custom_components.hoymiles_wifi._async_register_frontend", new=AsyncMock()
        ))
        for name in (
            "_ensure_dtu_device_registry_entry", "migrate_meter_entity_registry_entries",
            "transfer_inverter_entity_registry_entries", "_repair_metadata_entity_ids",
            "remove_obsolete_link_status_entities",
        ):
            stack.enter_context(patch(f"custom_components.hoymiles_wifi.{name}"))
        stack.enter_context(patch("custom_components.hoymiles_wifi.DTU", return_value=dtu))
        stack.enter_context(patch.object(
            hass.config_entries, "async_forward_entry_setups", side_effect=forward
        ))
        stack.enter_context(patch.object(
            hass.config_entries, "async_unload_platforms", side_effect=unload
        ))
        try:
            assert await asyncio.wait_for(async_setup_entry(hass, entry), 1) is True
            await asyncio.wait_for(all_started.wait(), 1)
            # This is HA's actual startup task barrier, not a mocked no-op.
            await asyncio.wait_for(hass.async_block_till_done(), 1)
            assert cancelled == set()
            assert len(entry._background_tasks) == len(expected)
        finally:
            assert await async_unload_entry(hass, entry) is True
            await entry._async_process_on_unload(hass)

    assert cancelled == expected
    assert not entry._background_tasks
    assert all(c._shutdown_requested and c._unsub_refresh is None for c in coordinators)


@pytest.mark.parametrize("kind", ["config", "app", "storage"])
async def test_failed_initial_background_read_can_recover(hass, kind):
    """A missing response marks failure and leaves periodic retry scheduled."""
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.1"})
    entry.add_to_hass(hass)
    response = SimpleNamespace(dtu_info=SimpleNamespace(dfs=0))
    method = AsyncMock(side_effect=[None, response])
    cls, method_name = {
        "config": (HoymilesConfigUpdateCoordinator, "async_get_config"),
        "app": (HoymilesAppInfoUpdateCoordinator, "async_app_information_data"),
        "storage": (HoymilesEnergyStorageUpdateCoordinator, "async_get_energy_storage_data"),
    }[kind]
    kwargs = {"dtu_serial_number": 123, "inverters": [{"inverter_serial_number": 456}]} if kind == "storage" else {}
    coordinator = cls(
        hass, SimpleNamespace(**{method_name: method}), entry, timedelta(seconds=300),
        **kwargs,
    )
    remove = coordinator.async_add_listener(lambda: None)
    try:
        task = entry.async_create_background_task(hass, coordinator.async_refresh(), "test initial read")
        await task
        assert coordinator.last_update_success is False
        assert coordinator._unsub_refresh is not None
        await coordinator.async_refresh()
        assert coordinator.last_update_success is True
        assert coordinator.data == ([response] if kind == "storage" else response)
        assert coordinator._unsub_refresh is not None
    finally:
        remove()
        await entry._async_process_on_unload(hass)
