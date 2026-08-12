"""Config flow for Hoymiles."""

from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_HYBRID_INVERTERS,
    CONF_INVERTERS,
    CONF_METERS,
    CONF_METER_TYPE,
    CONF_PORTS,
    CONF_THREE_PHASE_INVERTERS,
    CONF_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    CONF_IS_ENCRYPTED,
    CONF_ENC_RAND,
    CONFIG_VERSION,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
    METER_TYPE_AUTO,
    METER_TYPE_SINGLE_PHASE,
    METER_TYPE_THREE_PHASE,
    MIN_UPDATE_INTERVAL_SECONDS,
    MIN_TIMEOUT_SECONDS,
)
from .error import CannotConnect
from .util import async_get_config_entry_data_for_host

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(
            CONF_UPDATE_INTERVAL,
            default=timedelta(seconds=DEFAULT_UPDATE_INTERVAL_SECONDS).seconds,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=timedelta(seconds=MIN_UPDATE_INTERVAL_SECONDS).seconds),
        ),
        vol.Optional(
            CONF_TIMEOUT,
            default=timedelta(seconds=DEFAULT_TIMEOUT_SECONDS).seconds,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=timedelta(seconds=MIN_TIMEOUT_SECONDS).seconds),
        ),
        vol.Optional(CONF_METER_TYPE, default=METER_TYPE_AUTO): vol.In(
            [METER_TYPE_AUTO, METER_TYPE_SINGLE_PHASE, METER_TYPE_THREE_PHASE]
        ),
    }
)


def _apply_meter_type_override(meters: list[dict], meter_type: str) -> list[dict]:
    """Apply the configured meter type override to detected meters."""
    if meter_type == METER_TYPE_AUTO:
        return meters

    device_type = 1 if meter_type == METER_TYPE_SINGLE_PHASE else 3
    return [{**meter, "device_type": device_type} for meter in meters]


def _filter_duplicate_meters(
    hass: HomeAssistant, meters: list[dict], current_entry_id: str | None = None
) -> list[dict]:
    """Remove meters already configured by another Hoymiles entry."""
    configured_meter_serials = {
        meter.get("meter_serial_number")
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != current_entry_id
        for meter in entry.data.get(CONF_METERS, [])
        if meter.get("meter_serial_number")
    }

    return [
        meter
        for meter in meters
        if meter.get("meter_serial_number") not in configured_meter_serials
    ]


class HoymilesInverterConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Hoymiles Inverter config flow."""

    VERSION = CONFIG_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            update_interval = user_input.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_SECONDS
            )
            timeout = user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)
            meter_type = user_input.get(CONF_METER_TYPE, METER_TYPE_AUTO)

            try:
                (
                    dtu_sn,
                    single_phase_inverters,
                    three_phase_inverters,
                    ports,
                    meters,
                    hybrid_inverters,
                    is_encrypted,
                    enc_rand,
                ) = await async_get_config_entry_data_for_host(host)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                meters = _apply_meter_type_override(meters, meter_type)
                meters = _filter_duplicate_meters(self.hass, meters)
                await self.async_set_unique_id(dtu_sn)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=host,
                    data={
                        CONF_HOST: host,
                        CONF_UPDATE_INTERVAL: update_interval,
                        CONF_DTU_SERIAL_NUMBER: dtu_sn,
                        CONF_INVERTERS: single_phase_inverters,
                        CONF_THREE_PHASE_INVERTERS: three_phase_inverters,
                        CONF_PORTS: ports,
                        CONF_METERS: meters,
                        CONF_METER_TYPE: meter_type,
                        CONF_HYBRID_INVERTERS: hybrid_inverters,
                        CONF_IS_ENCRYPTED: is_encrypted,
                        CONF_ENC_RAND: enc_rand,
                        CONF_TIMEOUT: timeout,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a reconfiguration flow initialized by the user."""

        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            update_interval = user_input.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_SECONDS
            )

            timeout = user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT_SECONDS)
            meter_type = user_input.get(CONF_METER_TYPE, METER_TYPE_AUTO)

            try:
                (
                    dtu_sn,
                    single_phase_inverters,
                    three_phase_inverters,
                    ports,
                    meters,
                    hybrid_inverters,
                    is_encrypted,
                    enc_rand,
                ) = await async_get_config_entry_data_for_host(host)
            except CannotConnect:
                errors["base"] = "cannot_connect"

            else:
                meters = _apply_meter_type_override(meters, meter_type)
                if dtu_sn != entry.unique_id:
                    return self.async_abort(reason="another_device")
                meters = _filter_duplicate_meters(self.hass, meters, entry.entry_id)

                data = {
                    CONF_HOST: host,
                    CONF_UPDATE_INTERVAL: update_interval,
                    CONF_DTU_SERIAL_NUMBER: dtu_sn,
                    CONF_INVERTERS: single_phase_inverters,
                    CONF_THREE_PHASE_INVERTERS: three_phase_inverters,
                    CONF_PORTS: ports,
                    CONF_METERS: meters,
                    CONF_METER_TYPE: meter_type,
                    CONF_HYBRID_INVERTERS: hybrid_inverters,
                    CONF_IS_ENCRYPTED: is_encrypted,
                    CONF_ENC_RAND: enc_rand,
                    CONF_TIMEOUT: timeout,
                }

                self.hass.config_entries.async_update_entry(
                    entry, data=data, version=CONFIG_VERSION
                )
                result = await self.hass.config_entries.async_reload(entry.entry_id)
                if not result:
                    errors["base"] = "unknown"
                else:
                    return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=entry.data[CONF_UPDATE_INTERVAL],
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=timedelta(seconds=MIN_UPDATE_INTERVAL_SECONDS).seconds
                        ),
                    ),
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT_SECONDS),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=timedelta(seconds=MIN_TIMEOUT_SECONDS).seconds),
                    ),
                    vol.Optional(
                        CONF_METER_TYPE,
                        default=entry.data.get(CONF_METER_TYPE, METER_TYPE_AUTO),
                    ): vol.In(
                        [
                            METER_TYPE_AUTO,
                            METER_TYPE_SINGLE_PHASE,
                            METER_TYPE_THREE_PHASE,
                        ]
                    ),
                }
            ),
            errors=errors,
        )
