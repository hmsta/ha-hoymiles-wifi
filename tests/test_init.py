"""Test component setup."""

from homeassistant.setup import async_setup_component
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_wifi import (
    _async_register_lovelace_resource,
    _frontend_card_resource_url,
    _resource_base_url,
    async_remove_config_entry_device,
)
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


class FakeLovelaceResources:
    """Minimal Lovelace resource collection for frontend registration tests."""

    def __init__(self, items=None):
        self.items = items or []
        self.created = []
        self.updated = []

    async def async_get_info(self):
        """Pretend storage has been loaded."""
        return {"resources": len(self.items)}

    def async_items(self):
        """Return stored Lovelace resources."""
        return self.items

    async def async_create_item(self, data):
        """Record created resources."""
        self.created.append(data)
        item = {
            "id": f"created-{len(self.created)}",
            "url": data["url"],
            "type": data["res_type"],
        }
        self.items.append(item)
        return item

    async def async_update_item(self, item_id, data):
        """Record resource updates."""
        self.updated.append((item_id, data))
        for item in self.items:
            if item["id"] == item_id:
                item["url"] = data["url"]
                item["type"] = data["res_type"]
                return item
        return None


async def test_async_setup(hass):
    """Test the component gets setup."""

    assert await async_setup_component(hass, DOMAIN, {}) is True


async def test_register_lovelace_resource_creates_cache_busted_module(
    hass, monkeypatch
):
    """Test Lovelace resource registration creates the cache-busted card URL."""
    resources = FakeLovelaceResources()
    hass.data["lovelace"] = {"resources": resources}
    monkeypatch.setattr(
        "custom_components.hoymiles_wifi._frontend_card_resource_url",
        lambda: "/hoymiles_wifi_static/hoymiles-layout-card.js?v=123",
    )

    await _async_register_lovelace_resource(hass)

    assert resources.created == [
        {
            "url": "/hoymiles_wifi_static/hoymiles-layout-card.js?v=123",
            "res_type": "module",
        }
    ]


async def test_register_lovelace_resource_updates_changed_cache_buster(
    hass, monkeypatch
):
    """Test existing card resources are updated when the cache buster changes."""
    resources = FakeLovelaceResources(
        [
            {
                "id": "existing-resource",
                "url": "/hoymiles_wifi_static/hoymiles-layout-card.js?v=122",
                "type": "module",
            }
        ]
    )
    hass.data["lovelace"] = {"resources": resources}
    monkeypatch.setattr(
        "custom_components.hoymiles_wifi._frontend_card_resource_url",
        lambda: "/hoymiles_wifi_static/hoymiles-layout-card.js?v=123",
    )

    await _async_register_lovelace_resource(hass)

    assert resources.created == []
    assert resources.updated == [
        (
            "existing-resource",
            {
                "url": "/hoymiles_wifi_static/hoymiles-layout-card.js?v=123",
                "res_type": "module",
            },
        )
    ]


def test_frontend_card_resource_url_uses_js_mtime():
    """Test the generated card URL includes a cache-busting version."""
    url = _frontend_card_resource_url()

    assert _resource_base_url(url) == "/hoymiles_wifi_static/hoymiles-layout-card.js"
    assert "?v=" in url


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
        identifiers={(DOMAIN, meter_serial.upper())},
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
