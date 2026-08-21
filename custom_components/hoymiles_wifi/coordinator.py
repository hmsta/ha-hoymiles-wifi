"""Coordinator for Hoymiles integration."""

from datetime import timedelta
from math import ceil
import logging

import homeassistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from hoymiles_wifi.dtu import DTU
from .util import is_encrypted_dtu, async_check_and_update_enc_rand


from .const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_INVERTERS,
    CONF_METERS,
    CONF_THREE_PHASE_INVERTERS,
    DOMAIN,
    HASS_REAL_DATA_STAGGER_EPOCH,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.BINARY_SENSOR, Platform.BUTTON]
SCHEDULE_TOLERANCE_SECONDS = 1.0


def _stagger_sort_key(config_entry: ConfigEntry) -> tuple[str, str]:
    """Return a stable sort key for DTU poll staggering."""
    return (
        str(
            config_entry.data.get(CONF_DTU_SERIAL_NUMBER)
            or config_entry.data.get(CONF_HOST)
            or config_entry.entry_id
        ).lower(),
        config_entry.entry_id,
    )


def _stagger_slot_for_entries(
    entries: list[ConfigEntry],
    config_entry: ConfigEntry,
    interval_seconds: float,
) -> tuple[int, int, float]:
    """Return this config entry's stagger slot in the update interval."""
    entries_by_id = {entry.entry_id: entry for entry in entries}
    entries_by_id[config_entry.entry_id] = config_entry
    sorted_entries = sorted(entries_by_id.values(), key=_stagger_sort_key)
    entry_count = max(1, len(sorted_entries))
    slot_index = next(
        index
        for index, entry in enumerate(sorted_entries)
        if entry.entry_id == config_entry.entry_id
    )

    if entry_count == 1 or interval_seconds <= 0:
        return slot_index, entry_count, 0.0

    return slot_index, entry_count, (interval_seconds * slot_index) / entry_count


def _next_staggered_refresh_time(
    earliest_refresh: float,
    epoch: float,
    interval_seconds: float,
    slot_offset_seconds: float,
) -> float:
    """Return the next staggered refresh time at or after earliest_refresh."""
    if interval_seconds <= 0:
        return earliest_refresh

    cycle = ceil(
        (
            earliest_refresh
            - epoch
            - slot_offset_seconds
            - SCHEDULE_TOLERANCE_SECONDS
        )
        / interval_seconds
    )
    next_refresh = epoch + slot_offset_seconds + (max(0, cycle) * interval_seconds)
    return max(earliest_refresh, next_refresh)


def _uses_real_data_coordinator(config_entry: ConfigEntry) -> bool:
    """Return whether an entry has entities fed by the real-data coordinator."""
    return bool(
        config_entry.data.get(CONF_INVERTERS)
        or config_entry.data.get(CONF_THREE_PHASE_INVERTERS)
        or config_entry.data.get(CONF_METERS)
    )


class HoymilesDataUpdateCoordinator(DataUpdateCoordinator):
    """Base data update coordinator for Hoymiles integration."""

    def __init__(
        self,
        hass: homeassistant,
        dtu: DTU,
        config_entry: ConfigEntry,
        update_interval: timedelta | None,
    ) -> None:
        """Initialize the HoymilesCoordinatorEntity."""
        self._dtu = dtu
        self._hass = hass
        self._config_entry = config_entry

        _LOGGER.debug(
            "Setup entry with update interval %s. IP: %s",
            update_interval,
            config_entry.data.get(CONF_HOST),
        )

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

    def get_dtu(self) -> DTU:
        """Get the DTU object."""
        return self._dtu


class HoymilesRealDataUpdateCoordinator(HoymilesDataUpdateCoordinator):
    """Data coordinator for Hoymiles integration."""

    def __init__(
        self,
        hass: homeassistant,
        dtu: DTU,
        config_entry: ConfigEntry,
        update_interval: timedelta | None,
        startup_cooldown: timedelta,
        shared_meter_coordinator=None,
    ) -> None:
        """Initialize the real data coordinator."""
        self._startup_cooldown = startup_cooldown
        self._startup_refresh_pending = True
        self._last_real_data_poll_monotonic: float | None = None
        self._shared_meter_coordinator = shared_meter_coordinator
        super().__init__(hass, dtu, config_entry, update_interval)

    @callback
    def _schedule_refresh(self) -> None:
        """Schedule real-data refreshes with startup cooldown and DTU staggering."""
        if self._update_interval_seconds is None:
            return

        if self.config_entry and self.config_entry.pref_disable_polling:
            return

        self._async_unsub_refresh()

        loop = self.hass.loop
        now = loop.time()
        interval_seconds = self._update_interval_seconds
        real_data_entries = [
            entry
            for entry in self._hass.config_entries.async_entries(DOMAIN)
            if _uses_real_data_coordinator(entry)
        ]
        slot_index, entry_count, slot_offset = _stagger_slot_for_entries(
            real_data_entries,
            self._config_entry,
            interval_seconds,
        )
        epoch = self._stagger_epoch()

        if self._startup_refresh_pending:
            earliest_refresh = now + self._startup_cooldown.total_seconds()
            if earliest_refresh <= epoch + interval_seconds:
                next_refresh = max(earliest_refresh, epoch + slot_offset)
            else:
                next_refresh = _next_staggered_refresh_time(
                    earliest_refresh,
                    epoch,
                    interval_seconds,
                    slot_offset,
                )
        else:
            last_poll = self._last_real_data_poll_monotonic or now
            earliest_refresh = max(now, last_poll + interval_seconds)
            next_refresh = _next_staggered_refresh_time(
                earliest_refresh,
                epoch,
                interval_seconds,
                slot_offset,
            )
        _LOGGER.debug(
            "Scheduling Hoymiles real data refresh for %s in %.1f seconds "
            "(startup pending: %s, slot: %s/%s)",
            self._config_entry.data.get(CONF_HOST),
            max(0.0, next_refresh - now),
            self._startup_refresh_pending,
            slot_index + 1,
            entry_count,
        )
        self._unsub_refresh = loop.call_at(
            next_refresh,
            self._handle_staggered_refresh_interval,
        ).cancel

    @callback
    def _handle_staggered_refresh_interval(self) -> None:
        """Request a scheduled refresh without relying on HA private helpers."""
        self._unsub_refresh = None
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def schedule_startup_refresh(self) -> None:
        """Ensure the delayed first real-data refresh is scheduled."""
        if self._unsub_refresh is None:
            self._schedule_refresh()

    @property
    def startup_refresh_pending(self) -> bool:
        """Return whether the delayed first real-data refresh has not run yet."""
        return self._startup_refresh_pending

    def _stagger_epoch(self) -> float:
        """Return the shared monotonic epoch used for all Hoymiles DTU slots."""
        domain_data = self._hass.data.setdefault(DOMAIN, {})
        return domain_data.setdefault(
            HASS_REAL_DATA_STAGGER_EPOCH,
            self._hass.loop.time() + self._startup_cooldown.total_seconds(),
        )

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Hoymiles data coordinator update")
        self._startup_refresh_pending = False
        self._last_real_data_poll_monotonic = self._hass.loop.time()

        response = await self._dtu.async_get_real_data_new()

        if response and self._shared_meter_coordinator is not None:
            self._shared_meter_coordinator.update_from_real_data(
                response, self._config_entry
            )

        if not response:
            _LOGGER.debug(
                "Unable to retrieve real data new. Inverter might be offline."
            )
        return response


class HoymilesConfigUpdateCoordinator(HoymilesDataUpdateCoordinator):
    """Config coordinator for Hoymiles integration."""

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Hoymiles data coordinator update")

        response = await self._dtu.async_get_config()

        if not response:
            _LOGGER.debug("Unable to retrieve config data. Inverter might be offline.")

        return response


class HoymilesAppInfoUpdateCoordinator(HoymilesDataUpdateCoordinator):
    """App Info coordinator for Hoymiles integration."""

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Hoymiles data coordinator update")

        response = await self._dtu.async_app_information_data()

        if response and response.dtu_info.dfs:
            if is_encrypted_dtu(response.dtu_info.dfs):
                await async_check_and_update_enc_rand(
                    self._hass,
                    self._config_entry,
                    self._dtu,
                    response.dtu_info.enc_rand.hex(),
                )

        if not response:
            _LOGGER.debug(
                "Unable to retrieve app information data. Inverter might be offline."
            )
        return response


class HoymilesGatewayInfoUpdateCoordinator(HoymilesDataUpdateCoordinator):
    """Gateway Info coordinator for Hoymiles integration."""

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Hoymiles gateway info coordinator update")

        response = await self._dtu.async_get_gateway_info()

        if not response:
            _LOGGER.debug("Unable to retrieve gateway info. Inverter might be offline.")
        return response


class HoymilesGatewayNetworkInfoUpdateCoordinator(HoymilesDataUpdateCoordinator):
    """Gateway Network Info coordinator for Hoymiles integration."""

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Hoymiles network info coordinator update")

        response = await self._dtu.async_get_gateway_network_info(
            dtu_serial_number=int(self._dtu_serial_number)
        )

        if not response:
            _LOGGER.debug(
                "Unable to retrieve network information. Inverter might be offline."
            )
        return response


class HoymilesEnergyStorageUpdateCoordinator(HoymilesDataUpdateCoordinator):
    """Energy Storage Update coordinator for Hoymiles integration."""

    def __init__(
        self,
        hass: homeassistant,
        dtu: DTU,
        config_entry: ConfigEntry,
        update_interval: timedelta,
        dtu_serial_number: int,
        inverters: list[int],
    ) -> None:
        self._dtu_serial_number = dtu_serial_number
        self._inverters = inverters
        super().__init__(hass, dtu, config_entry, update_interval)

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Hoymiles energy storage coordinator update")

        responses = []

        for inverter in self._inverters:
            storage_data = await self._dtu.async_get_energy_storage_data(
                dtu_serial_number=int(self._dtu_serial_number),
                inverter_serial_number=inverter["inverter_serial_number"],
            )
            if storage_data is not None:
                responses.append(storage_data)

        if not responses:
            _LOGGER.debug(
                "Unable to retrieve energy storage data. Inverter might be offline."
            )
        return responses
