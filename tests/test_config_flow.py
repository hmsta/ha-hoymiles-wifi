"""Unit tests for the Hoymiles config flow."""

from json import JSONDecodeError
from unittest.mock import patch

import pytest

from homeassistant import config_entries
from custom_components.hoymiles_wifi.const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    CONF_INVERTERS,
    CONF_THREE_PHASE_INVERTERS,
    CONF_PORTS,
    CONF_METERS,
    CONF_METER_TYPE,
    CONF_HYBRID_INVERTERS,
    CONF_DTU_SERIAL_NUMBER,
    CONF_IS_ENCRYPTED,
    CONF_ENC_RAND,
    CONF_TIMEOUT,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    METER_TYPE_AUTO,
    METER_TYPE_THREE_PHASE,
)
from custom_components.hoymiles_wifi.error import CannotConnect

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from hoymiles_wifi.protobuf import (
    RealDataNew_pb2,
)

DTU_TEST_HOST = "DTUBI-123456789101.lan"

DTU_TEST_SERIAL_NUMBER = "414312345678"

MOCK_DATA_STEP = {
    CONF_HOST: DTU_TEST_HOST,
    CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_SECONDS,
}

MOCK_DATA_RESULT = {
    CONF_HOST: DTU_TEST_HOST,
    CONF_DTU_SERIAL_NUMBER: DTU_TEST_SERIAL_NUMBER,
    CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL_SECONDS,
    CONF_INVERTERS: [],
    CONF_THREE_PHASE_INVERTERS: [],
    CONF_PORTS: [],
    CONF_METERS: [],
    CONF_METER_TYPE: METER_TYPE_AUTO,
    CONF_HYBRID_INVERTERS: [],
    CONF_IS_ENCRYPTED: False,
    CONF_ENC_RAND: "",
    CONF_TIMEOUT: DEFAULT_TIMEOUT_SECONDS,
}


MOCK_DATA_REAL_DATA_NEW = RealDataNew_pb2.RealDataNewReqDTO()
MOCK_DATA_REAL_DATA_NEW.device_serial_number = DTU_TEST_SERIAL_NUMBER


async def test_form_valid_input(hass: HomeAssistant) -> None:
    """Test handling valid user input."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}

    with (
        patch(
            "custom_components.hoymiles_wifi.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
        patch(
            "hoymiles_wifi.dtu.DTU.async_get_real_data_new",
            return_value=MOCK_DATA_REAL_DATA_NEW,
        ) as mock_async_get_real_data_new,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_DATA_STEP,
        )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == MOCK_DATA_STEP[CONF_HOST]
    assert result2["data"] == MOCK_DATA_RESULT
    assert len(mock_setup_entry.mock_calls) == 1
    assert len(mock_async_get_real_data_new.mock_calls) == 1


async def test_form_overrides_meter_type(hass: HomeAssistant) -> None:
    """Test overriding the detected meter type."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}

    user_input = {**MOCK_DATA_STEP, CONF_METER_TYPE: METER_TYPE_THREE_PHASE}
    data_with_meter = RealDataNew_pb2.RealDataNewReqDTO()
    data_with_meter.device_serial_number = DTU_TEST_SERIAL_NUMBER
    meter_data = data_with_meter.meter_data.add()
    meter_data.serial_number = 12345678
    meter_data.device_type = 1

    with (
        patch(
            "custom_components.hoymiles_wifi.async_setup_entry",
            return_value=True,
        ),
        patch(
            "hoymiles_wifi.dtu.DTU.async_get_real_data_new",
            return_value=data_with_meter,
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input,
        )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_METER_TYPE] == METER_TYPE_THREE_PHASE
    assert result2["data"][CONF_METERS][0]["device_type"] == 3


@pytest.mark.parametrize(
    ("raise_error", "text_error"),
    [
        (CannotConnect("Test hoymiles exception"), "cannot_connect"),
    ],
)
async def test_flow_user_init_data_error_and_recover(
    hass: HomeAssistant, raise_error, text_error
) -> None:
    """Test exceptions and recovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}

    with patch(
        "custom_components.hoymiles_wifi.util.DTU.async_get_real_data_new",
        side_effect=raise_error,
    ) as mock_async_get_config_entry_data_for_host:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_DATA_STEP,
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": text_error}

    assert len(mock_async_get_config_entry_data_for_host.mock_calls) == 1

    # Recover
    with (
        patch(
            "custom_components.hoymiles_wifi.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
        patch(
            "hoymiles_wifi.dtu.DTU.async_get_real_data_new",
            return_value=MOCK_DATA_REAL_DATA_NEW,
        ) as mock_async_get_real_data_new,
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_DATA_STEP,
        )

    await hass.async_block_till_done()

    assert result3["type"] == FlowResultType.CREATE_ENTRY
    assert result3["title"] == MOCK_DATA_STEP[CONF_HOST]
    assert result3["data"] == MOCK_DATA_RESULT
    assert len(mock_setup_entry.mock_calls) == 1
    assert len(mock_async_get_real_data_new.mock_calls) == 1
