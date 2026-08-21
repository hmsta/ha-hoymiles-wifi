"""Platform for retrieving values of a Hoymiles inverter."""

from datetime import timedelta
import inspect
import logging
from pathlib import Path
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_ID, CONF_TYPE, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import SupportsResponse
from hoymiles_wifi.dtu import DTU

from .const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_HYBRID_INVERTERS,
    CONF_INVERTERS,
    CONF_METERS,
    CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
    CONF_PORTS,
    CONF_STARTUP_COOLDOWN,
    CONF_THREE_PHASE_INVERTERS,
    CONF_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    CONFIG_VERSION,
    CONF_IS_ENCRYPTED,
    CONF_ENC_RAND,
    DEFAULT_APP_INFO_UPDATE_INTERVAL_SECONDS,
    DEFAULT_CONFIG_UPDATE_INTERVAL_SECONDS,
    DEFAULT_STARTUP_COOLDOWN_SECONDS,
    DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
    DEFAULT_TIMEOUT_SECONDS,
    DOMAIN,
    HASS_APP_INFO_COORDINATOR,
    HASS_CONFIG_COORDINATOR,
    HASS_DATA_COORDINATOR,
    HASS_DTU,
    HASS_ENERGY_STORAGE_DATA_COORDINATOR,
    HASS_SHARED_METER_COORDINATOR,
)
from .coordinator import (
    HoymilesAppInfoUpdateCoordinator,
    HoymilesConfigUpdateCoordinator,
    HoymilesRealDataUpdateCoordinator,
    HoymilesEnergyStorageUpdateCoordinator,
)
from .entity_migration import async_migrate_entity_unique_ids
from .services import async_handle_set_bms_mode
from .shared_meter import HoymilesSharedMeterCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.BINARY_SENSOR, Platform.BUTTON]
FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_URL = f"/{DOMAIN}_static"
FRONTEND_CARD_FILENAME = "hoymiles-layout-card.js"
FRONTEND_CARD_URL = f"{FRONTEND_URL}/{FRONTEND_CARD_FILENAME}"
FRONTEND_CARD_RESOURCE_TYPE = "module"
LOVELACE_DOMAIN = "lovelace"
LOVELACE_RESOURCES = "resources"
LOVELACE_RESOURCE_TYPE = "res_type"

SET_BMS_SCHEMA = vol.Schema(
    {
        vol.Required("bms_mode"): vol.In(
            (
                "self_use",
                "economic",
                "backup_power",
                "pure_off_grid",
                "forced_charging",
                "forced_discharge",
                "peak_shaving",
                "time_of_use",
            )
        ),
        vol.Required("rev_soc"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional("max_power"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("peak_soc"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional("peak_meter_power"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("time_settings"): str,
        vol.Optional("time_periods"): str,
        vol.Optional("device_id"): cv.ensure_list,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up this integration using YAML is not supported."""
    await _async_register_frontend(hass)
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register bundled frontend assets for the Hoymiles layout card."""
    hass.data.setdefault(DOMAIN, {})

    if not (
        hass.data[DOMAIN].get("frontend_static_registered")
        or hass.data[DOMAIN].get("frontend_registered")
    ):
        await _async_register_static_frontend(hass)
        hass.data[DOMAIN]["frontend_static_registered"] = True
        hass.data[DOMAIN]["frontend_registered"] = True

    await _async_register_lovelace_resource(hass)


async def _async_register_static_frontend(hass: HomeAssistant) -> None:
    """Register the static frontend path."""

    try:
        from homeassistant.components.http import (  # pylint: disable=import-outside-toplevel
            StaticPathConfig,
        )
    except ImportError:
        StaticPathConfig = None

    try:
        from homeassistant.components.http import (  # pylint: disable=import-outside-toplevel
            async_register_static_paths,
        )
    except ImportError:
        async_register_static_paths = None

    if StaticPathConfig is not None and hasattr(hass.http, "async_register_static_paths"):
        result = hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    FRONTEND_URL,
                    str(FRONTEND_DIR),
                    False,
                )
            ],
        )
        if inspect.isawaitable(result):
            await result
    elif StaticPathConfig is not None and async_register_static_paths is not None:
        await async_register_static_paths(
            hass,
            [
                StaticPathConfig(
                    FRONTEND_URL,
                    str(FRONTEND_DIR),
                    False,
                )
            ],
        )
    elif hasattr(hass.http, "register_static_path"):
        result = hass.http.register_static_path(
            FRONTEND_URL,
            str(FRONTEND_DIR),
            False,
        )
        if inspect.isawaitable(result):
            await result
    else:
        raise RuntimeError("Home Assistant static path registration API is unavailable")


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Create or update the Lovelace resource for the layout card."""
    resources = await _async_get_lovelace_resources(hass)
    if resources is None:
        _LOGGER.debug("Lovelace resources are unavailable; skipping frontend resource")
        return

    can_update_resources = hasattr(resources, "async_create_item") and hasattr(
        resources, "async_update_item"
    )
    if not can_update_resources:
        _LOGGER.debug(
            "Lovelace resources are read-only; skipping frontend resource update"
        )
        return

    await resources.async_get_info()

    resource_url = _frontend_card_resource_url()
    resource_items = resources.async_items() or []
    for item in resource_items:
        if _resource_base_url(item.get(CONF_URL, "")) != FRONTEND_CARD_URL:
            continue

        resource_id = item.get(CONF_ID)
        if not resource_id:
            _LOGGER.debug("Lovelace resource for %s has no id", FRONTEND_CARD_URL)
            return

        if (
            item.get(CONF_URL) != resource_url
            or item.get(CONF_TYPE) != FRONTEND_CARD_RESOURCE_TYPE
        ):
            await resources.async_update_item(
                resource_id,
                {
                    CONF_URL: resource_url,
                    LOVELACE_RESOURCE_TYPE: FRONTEND_CARD_RESOURCE_TYPE,
                },
            )
        return

    await resources.async_create_item(
        {
            CONF_URL: resource_url,
            LOVELACE_RESOURCE_TYPE: FRONTEND_CARD_RESOURCE_TYPE,
        }
    )


async def _async_get_lovelace_resources(hass: HomeAssistant):
    """Return Lovelace resources, setting up Lovelace first if needed."""
    if LOVELACE_DOMAIN not in hass.data:
        try:
            from homeassistant.setup import (  # pylint: disable=import-outside-toplevel
                async_setup_component,
            )
        except ImportError:
            return None

        if not await async_setup_component(hass, LOVELACE_DOMAIN, {}):
            return None

    return _lovelace_resources_from_data(hass.data.get(LOVELACE_DOMAIN))


def _lovelace_resources_from_data(lovelace_data):
    """Return Lovelace resources from old dict data or newer LovelaceData."""
    if lovelace_data is None:
        return None
    if isinstance(lovelace_data, dict):
        return lovelace_data.get(LOVELACE_RESOURCES)
    return getattr(lovelace_data, LOVELACE_RESOURCES, None)


def _frontend_card_resource_url() -> str:
    """Return the cache-busted Lovelace URL for the bundled layout card."""
    try:
        version = (FRONTEND_DIR / FRONTEND_CARD_FILENAME).stat().st_mtime_ns
    except OSError:
        version = 0

    return f"{FRONTEND_CARD_URL}?v={version}"


def _resource_base_url(url: str) -> str:
    """Return a Lovelace resource URL without its cache-busting query string."""
    return url.split("?", 1)[0]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Set up this integration using UI."""

    await _async_register_frontend(hass)

    hass.data.setdefault(DOMAIN, {})
    shared_meter_coordinator = hass.data[DOMAIN].get(HASS_SHARED_METER_COORDINATOR)
    if shared_meter_coordinator is None:
        shared_meter_coordinator = HoymilesSharedMeterCoordinator(hass)
        hass.data[DOMAIN][HASS_SHARED_METER_COORDINATOR] = shared_meter_coordinator

    hass_data = dict(config_entry.data)

    host = config_entry.data.get(CONF_HOST)
    update_interval = timedelta(seconds=config_entry.data.get(CONF_UPDATE_INTERVAL))
    startup_cooldown = timedelta(
        seconds=config_entry.data.get(
            CONF_STARTUP_COOLDOWN, DEFAULT_STARTUP_COOLDOWN_SECONDS
        )
    )
    single_phase_inverters = config_entry.data[CONF_INVERTERS]
    three_phase_inverters = config_entry.data.get(CONF_THREE_PHASE_INVERTERS, [])
    hybrid_inverters = config_entry.data.get(CONF_HYBRID_INVERTERS, [])
    meters = config_entry.data.get(CONF_METERS, [])
    is_encrypted = config_entry.data.get(CONF_IS_ENCRYPTED, False)
    enc_rand = config_entry.data.get(CONF_ENC_RAND, None)
    timeout = config_entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)

    if is_encrypted:
        dtu = DTU(
            host,
            is_encrypted=is_encrypted,
            enc_rand=bytes.fromhex(enc_rand),
            timeout=timeout,
        )
    else:
        dtu = DTU(host, timeout=timeout)

    hass_data[HASS_DTU] = dtu

    if single_phase_inverters or three_phase_inverters or meters:
        data_coordinator = HoymilesRealDataUpdateCoordinator(
            hass,
            dtu=dtu,
            config_entry=config_entry,
            update_interval=update_interval,
            startup_cooldown=startup_cooldown,
            shared_meter_coordinator=shared_meter_coordinator,
        )
        hass_data[HASS_DATA_COORDINATOR] = data_coordinator

        config_update_interval = timedelta(
            seconds=DEFAULT_CONFIG_UPDATE_INTERVAL_SECONDS
        )
        config_coordinator = HoymilesConfigUpdateCoordinator(
            hass=hass,
            dtu=dtu,
            config_entry=config_entry,
            update_interval=config_update_interval,
        )
        hass_data[HASS_CONFIG_COORDINATOR] = config_coordinator

        app_info_update_interval = timedelta(
            seconds=DEFAULT_APP_INFO_UPDATE_INTERVAL_SECONDS
        )
        app_info_update_coordinator = HoymilesAppInfoUpdateCoordinator(
            hass=hass,
            dtu=dtu,
            config_entry=config_entry,
            update_interval=app_info_update_interval,
        )
        hass_data[HASS_APP_INFO_COORDINATOR] = app_info_update_coordinator

    if hybrid_inverters:
        energy_storage_data_coordinator = HoymilesEnergyStorageUpdateCoordinator(
            hass=hass,
            dtu=dtu,
            config_entry=config_entry,
            update_interval=update_interval,
            dtu_serial_number=config_entry.data[CONF_DTU_SERIAL_NUMBER],
            inverters=hybrid_inverters,
        )

        hass_data[HASS_ENERGY_STORAGE_DATA_COORDINATOR] = (
            energy_storage_data_coordinator
        )

    _LOGGER.debug(f"  hass_data: {hass_data}")  # --- IGNORE ---
    _LOGGER.debug(f"  config_entry_id: {config_entry.entry_id}")

    hass.data[DOMAIN][config_entry.entry_id] = hass_data
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    if single_phase_inverters or three_phase_inverters or meters:
        data_coordinator.schedule_startup_refresh()
        await config_coordinator.async_config_entry_first_refresh()
        await app_info_update_coordinator.async_config_entry_first_refresh()
    if hybrid_inverters:
        await energy_storage_data_coordinator.async_config_entry_first_refresh()
        hass.services.async_register(
            domain=DOMAIN,
            service="set_bms_mode",
            service_func=async_handle_set_bms_mode,
            schema=SET_BMS_SCHEMA,
            supports_response=SupportsResponse.NONE,
        )
        _LOGGER.debug("Service set_bms_mode registered")

    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    meters = config_entry.data.get(CONF_METERS, [])
    meter_serials = {
        str(identifier).lower()
        for domain, identifier in device_entry.identifiers
        if domain == DOMAIN
    }

    updated_meters = [
        meter
        for meter in meters
        if str(meter.get("meter_serial_number")).lower() not in meter_serials
    ]

    if len(updated_meters) != len(meters):
        hass.config_entries.async_update_entry(
            config_entry,
            data={**config_entry.data, CONF_METERS: updated_meters},
            version=CONFIG_VERSION,
        )
        shared_meter_coordinator = hass.data.get(DOMAIN, {}).get(
            HASS_SHARED_METER_COORDINATOR
        )
        if shared_meter_coordinator is not None:
            for meter_serial in meter_serials:
                shared_meter_coordinator.remove_meter(meter_serial)
        return True

    return False


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry data to the new entry schema."""

    current_version = config_entry.version

    if current_version != CONFIG_VERSION:
        _LOGGER.info(
            "Migrating entry %s to version %s", config_entry.entry_id, CONFIG_VERSION
        )
        new = {**config_entry.data}

        new.setdefault(CONF_THREE_PHASE_INVERTERS, [])
        new.setdefault(CONF_HYBRID_INVERTERS, [])
        new.setdefault(CONF_METERS, [])
        new.setdefault(CONF_PORTS, [])
        new.setdefault(CONF_STARTUP_COOLDOWN, DEFAULT_STARTUP_COOLDOWN_SECONDS)
        new.setdefault(CONF_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)
        new.setdefault(
            CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
            DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
        )
        new.setdefault(CONF_IS_ENCRYPTED, False)
        new.setdefault(CONF_ENC_RAND, None)

        await async_migrate_entity_unique_ids(hass, config_entry.entry_id, new)

        hass.config_entries.async_update_entry(
            config_entry, data=new, version=CONFIG_VERSION
        )
        _LOGGER.info(
            "Migration of entry %s to version %s successful",
            config_entry.entry_id,
            CONFIG_VERSION,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    return unload_ok
