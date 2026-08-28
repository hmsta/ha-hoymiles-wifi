"""Unit tests for Hoymiles button entities."""

from types import SimpleNamespace

from custom_components.hoymiles_wifi.button import (
    HoymilesButtonEntity,
    HoymilesButtonEntityDescription,
    async_setup_entry,
)
from custom_components.hoymiles_wifi.const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_INVERTERS,
    CONF_THREE_PHASE_INVERTERS,
    DOMAIN,
    HASS_APP_INFO_COORDINATOR,
    HASS_DATA_COORDINATOR,
    HASS_DTU,
)


async def test_force_update_button_requests_real_data_refresh() -> None:
    """Test the DTU force-update button refreshes real-data and app-info."""

    class FakeCoordinator:
        def __init__(self) -> None:
            self.refresh_count = 0

        async def async_request_refresh(self) -> None:
            self.refresh_count += 1

    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = FakeCoordinator()
    app_info_coordinator = FakeCoordinator()
    entity = HoymilesButtonEntity(
        config_entry,
        HoymilesButtonEntityDescription(
            key="force_update",
            translation_key="force_update",
            serial_number="4121a01953c8",
            is_dtu_sensor=True,
            force_data_update=True,
        ),
        dtu=object(),
        data_coordinator=coordinator,
        app_info_coordinator=app_info_coordinator,
    )

    await entity.async_press()

    assert coordinator.refresh_count == 1
    assert app_info_coordinator.refresh_count == 1


async def test_setup_entry_adds_force_update_button_for_meter_only_entry() -> None:
    """Test meter-only DTU entries still get the force-update control."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={
            CONF_DTU_SERIAL_NUMBER: "4121a01953c8",
            CONF_INVERTERS: [],
            CONF_THREE_PHASE_INVERTERS: [],
        },
    )
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry-a": {
                    HASS_DTU: object(),
                    HASS_DATA_COORDINATOR: object(),
                    HASS_APP_INFO_COORDINATOR: object(),
                }
            }
        }
    )
    added_entities = []

    def add_entities(entities):
        added_entities.extend(entities)

    await async_setup_entry(hass, config_entry, add_entities)

    assert [
        entity.entity_description.key for entity in added_entities
    ] == ["force_update"]
