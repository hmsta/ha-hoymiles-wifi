"""Unit tests for the Hoymiles config flow."""

from json import JSONDecodeError
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from custom_components.hoymiles_wifi.const import (
    DOMAIN,
    CONF_UPDATE_INTERVAL,
    CONF_INVERTERS,
    CONF_THREE_PHASE_INVERTERS,
    CONF_PORTS,
    CONF_STARTUP_COOLDOWN,
    CONF_METERS,
    CONF_METER_ENERGY_CONSISTENCY_TOLERANCE,
    CONF_METER_TYPE,
    CONF_HYBRID_INVERTERS,
    CONF_DTU_SERIAL_NUMBER,
    CONF_IS_ENCRYPTED,
    CONF_ENC_RAND,
    CONF_TIMEOUT,
    DEFAULT_STARTUP_COOLDOWN_SECONDS,
    DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    METER_TYPE_AUTO,
    METER_TYPE_THREE_PHASE,
)
from custom_components.hoymiles_wifi.config_flow import (
    _detected_inverter_serials,
    _remove_claimed_inverters_from_data,
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
DTU_SECOND_TEST_SERIAL_NUMBER = "414312345679"
METER_RAW_SERIAL_NUMBER = 12345678
METER_SERIAL_NUMBER = "bc614e"
INVERTER_A_SERIAL_NUMBER = "1421a01a4525"
INVERTER_B_SERIAL_NUMBER = "1421a01a4526"
INVERTER_KEEP_SERIAL_NUMBER = "1421a01a4527"
THREE_PHASE_INVERTER_SERIAL_NUMBER = "1121a01b9999"
HYBRID_INVERTER_SERIAL_NUMBER = "1161a01b1111"

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
    CONF_STARTUP_COOLDOWN: DEFAULT_STARTUP_COOLDOWN_SECONDS,
    CONF_METER_ENERGY_CONSISTENCY_TOLERANCE: (
        DEFAULT_METER_ENERGY_CONSISTENCY_TOLERANCE
    ),
}


MOCK_DATA_REAL_DATA_NEW = RealDataNew_pb2.RealDataNewReqDTO()
MOCK_DATA_REAL_DATA_NEW.device_serial_number = DTU_TEST_SERIAL_NUMBER


def _real_data_with_meter(
    dtu_serial_number: str = DTU_TEST_SERIAL_NUMBER, device_type: int = 1
):
    """Build real data response with one meter."""
    data = RealDataNew_pb2.RealDataNewReqDTO()
    data.device_serial_number = dtu_serial_number
    meter_data = data.meter_data.add()
    meter_data.serial_number = METER_RAW_SERIAL_NUMBER
    meter_data.device_type = device_type
    return data


def _add_config_entry_with_meter(
    hass: HomeAssistant,
    entry_id: str = "existing-entry",
    dtu_serial_number: str = DTU_TEST_SERIAL_NUMBER,
    meter_type: int = 1,
    meter_serial_number: str = METER_SERIAL_NUMBER,
) -> MockConfigEntry:
    """Add a Hoymiles config entry with one stored meter."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        unique_id=dtu_serial_number,
        data={
            **MOCK_DATA_RESULT,
            CONF_DTU_SERIAL_NUMBER: dtu_serial_number,
            CONF_METERS: [
                {
                    "meter_serial_number": meter_serial_number,
                    "device_type": meter_type,
                }
            ],
        },
    )
    entry.add_to_hass(hass)
    return entry


def _add_config_entry(
    hass: HomeAssistant,
    *,
    entry_id: str,
    dtu_serial_number: str,
    single_phase_inverters: list | None = None,
    three_phase_inverters: list | None = None,
    ports: list[dict] | None = None,
    meters: list[dict] | None = None,
    hybrid_inverters: list[dict] | None = None,
) -> MockConfigEntry:
    """Add a Hoymiles config entry with custom device lists."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        unique_id=dtu_serial_number,
        data={
            **MOCK_DATA_RESULT,
            CONF_DTU_SERIAL_NUMBER: dtu_serial_number,
            CONF_INVERTERS: single_phase_inverters or [],
            CONF_THREE_PHASE_INVERTERS: three_phase_inverters or [],
            CONF_PORTS: ports or [],
            CONF_METERS: meters or [],
            CONF_HYBRID_INVERTERS: hybrid_inverters or [],
        },
    )
    entry.add_to_hass(hass)
    return entry


def _discovered_config_data(
    *,
    dtu_serial_number: str,
    single_phase_inverters: list | None = None,
    three_phase_inverters: list | None = None,
    ports: list[dict] | None = None,
    meters: list[dict] | None = None,
    hybrid_inverters: list[dict] | None = None,
):
    """Build the config discovery tuple returned by util."""
    return (
        dtu_serial_number,
        single_phase_inverters or [],
        three_phase_inverters or [],
        ports or [],
        meters or [],
        hybrid_inverters or [],
        False,
        "",
    )


def test_detected_inverter_serials_collects_all_device_shapes() -> None:
    """Test inverter serial detection includes ports and hybrid inverters."""
    assert _detected_inverter_serials(
        [INVERTER_A_SERIAL_NUMBER.upper()],
        [THREE_PHASE_INVERTER_SERIAL_NUMBER],
        [{"inverter_serial_number": INVERTER_B_SERIAL_NUMBER, "port_number": 1}],
        [
            {
                "inverter_serial_number": HYBRID_INVERTER_SERIAL_NUMBER,
                "model_name": "HYS",
            }
        ],
    ) == {
        INVERTER_A_SERIAL_NUMBER,
        INVERTER_B_SERIAL_NUMBER,
        THREE_PHASE_INVERTER_SERIAL_NUMBER,
        HYBRID_INVERTER_SERIAL_NUMBER,
    }


def test_remove_claimed_inverters_from_data_preserves_meters() -> None:
    """Test claimed inverters are removed without changing meter ownership."""
    meter = {"meter_serial_number": METER_SERIAL_NUMBER, "device_type": 3}
    data = {
        **MOCK_DATA_RESULT,
        CONF_INVERTERS: [INVERTER_A_SERIAL_NUMBER.upper(), INVERTER_KEEP_SERIAL_NUMBER],
        CONF_THREE_PHASE_INVERTERS: [THREE_PHASE_INVERTER_SERIAL_NUMBER],
        CONF_PORTS: [
            {"inverter_serial_number": INVERTER_A_SERIAL_NUMBER, "port_number": 1},
            {"inverter_serial_number": INVERTER_KEEP_SERIAL_NUMBER, "port_number": 1},
            {
                "inverter_serial_number": THREE_PHASE_INVERTER_SERIAL_NUMBER.upper(),
                "port_number": 1,
            },
        ],
        CONF_METERS: [meter],
        CONF_HYBRID_INVERTERS: [
            {
                "inverter_serial_number": HYBRID_INVERTER_SERIAL_NUMBER,
                "model_name": "HYS",
            }
        ],
    }

    updated_data, changed = _remove_claimed_inverters_from_data(
        data,
        {
            INVERTER_A_SERIAL_NUMBER,
            THREE_PHASE_INVERTER_SERIAL_NUMBER,
            HYBRID_INVERTER_SERIAL_NUMBER.upper(),
        },
    )

    assert changed is True
    assert updated_data[CONF_INVERTERS] == [INVERTER_KEEP_SERIAL_NUMBER]
    assert updated_data[CONF_THREE_PHASE_INVERTERS] == []
    assert updated_data[CONF_PORTS] == [
        {"inverter_serial_number": INVERTER_KEEP_SERIAL_NUMBER, "port_number": 1}
    ]
    assert updated_data[CONF_HYBRID_INVERTERS] == []
    assert updated_data[CONF_METERS] == [meter]


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


async def test_form_keeps_new_meter(hass: HomeAssistant) -> None:
    """Test first DTU keeps a newly detected meter."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "custom_components.hoymiles_wifi.async_setup_entry",
            return_value=True,
        ),
        patch(
            "hoymiles_wifi.dtu.DTU.async_get_real_data_new",
            return_value=_real_data_with_meter(),
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_DATA_STEP,
        )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_METERS] == [
        {"meter_serial_number": METER_SERIAL_NUMBER, "device_type": 1}
    ]


async def test_form_skips_meter_known_by_another_dtu(hass: HomeAssistant) -> None:
    """Test second DTU skips a meter already configured by another DTU."""

    _add_config_entry_with_meter(hass, meter_serial_number=METER_SERIAL_NUMBER.upper())

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "custom_components.hoymiles_wifi.async_setup_entry",
            return_value=True,
        ),
        patch(
            "hoymiles_wifi.dtu.DTU.async_get_real_data_new",
            return_value=_real_data_with_meter(DTU_SECOND_TEST_SERIAL_NUMBER),
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_DATA_STEP,
        )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_DTU_SERIAL_NUMBER] == DTU_SECOND_TEST_SERIAL_NUMBER
    assert result2["data"][CONF_METERS] == []


async def test_reconfigure_keeps_own_meter(hass: HomeAssistant) -> None:
    """Test reconfigure ignores the current entry when filtering meters."""

    entry = _add_config_entry_with_meter(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    with (
        patch.object(hass.config_entries, "async_reload", return_value=True),
        patch(
            "hoymiles_wifi.dtu.DTU.async_get_real_data_new",
            return_value=_real_data_with_meter(),
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_DATA_STEP,
        )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"
    assert entry.data[CONF_METERS] == [
        {"meter_serial_number": METER_SERIAL_NUMBER, "device_type": 1}
    ]


async def test_meter_type_override_applies_before_duplicate_filter(
    hass: HomeAssistant,
) -> None:
    """Test meter type override runs before duplicate meter filtering."""

    _add_config_entry_with_meter(hass, meter_type=1)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "custom_components.hoymiles_wifi.async_setup_entry",
            return_value=True,
        ),
        patch(
            "hoymiles_wifi.dtu.DTU.async_get_real_data_new",
            return_value=_real_data_with_meter(DTU_SECOND_TEST_SERIAL_NUMBER),
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {**MOCK_DATA_STEP, CONF_METER_TYPE: METER_TYPE_THREE_PHASE},
        )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_METER_TYPE] == METER_TYPE_THREE_PHASE
    assert result2["data"][CONF_METERS] == []


async def test_form_claims_detected_inverters_from_other_dtu(
    hass: HomeAssistant,
) -> None:
    """Test newly added DTU moves detected inverters from another DTU entry."""
    existing_meter = {"meter_serial_number": METER_SERIAL_NUMBER, "device_type": 3}
    existing_entry = _add_config_entry(
        hass,
        entry_id="dtu-a",
        dtu_serial_number=DTU_TEST_SERIAL_NUMBER,
        single_phase_inverters=[
            INVERTER_A_SERIAL_NUMBER.upper(),
            INVERTER_KEEP_SERIAL_NUMBER,
        ],
        three_phase_inverters=[THREE_PHASE_INVERTER_SERIAL_NUMBER],
        ports=[
            {
                "inverter_serial_number": INVERTER_A_SERIAL_NUMBER,
                "port_number": 1,
            },
            {
                "inverter_serial_number": INVERTER_KEEP_SERIAL_NUMBER,
                "port_number": 1,
            },
            {
                "inverter_serial_number": THREE_PHASE_INVERTER_SERIAL_NUMBER,
                "port_number": 1,
            },
        ],
        meters=[existing_meter],
        hybrid_inverters=[
            {
                "inverter_serial_number": HYBRID_INVERTER_SERIAL_NUMBER,
                "model_name": "HYS",
            }
        ],
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    discovered_ports = [
        {"inverter_serial_number": INVERTER_A_SERIAL_NUMBER, "port_number": 1},
        {
            "inverter_serial_number": THREE_PHASE_INVERTER_SERIAL_NUMBER.upper(),
            "port_number": 1,
        },
    ]
    discovered_hybrid_inverters = [
        {
            "inverter_serial_number": HYBRID_INVERTER_SERIAL_NUMBER.upper(),
            "model_name": "HYS",
        }
    ]

    with (
        patch("custom_components.hoymiles_wifi.async_setup_entry", return_value=True),
        patch(
            "custom_components.hoymiles_wifi.config_flow.async_get_config_entry_data_for_host",
            new=AsyncMock(
                return_value=_discovered_config_data(
                    dtu_serial_number=DTU_SECOND_TEST_SERIAL_NUMBER,
                    single_phase_inverters=[INVERTER_A_SERIAL_NUMBER],
                    three_phase_inverters=[
                        THREE_PHASE_INVERTER_SERIAL_NUMBER.upper()
                    ],
                    ports=discovered_ports,
                    hybrid_inverters=discovered_hybrid_inverters,
                )
            ),
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            new=AsyncMock(return_value=True),
        ) as mock_reload,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            MOCK_DATA_STEP,
        )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_INVERTERS] == [INVERTER_A_SERIAL_NUMBER]
    assert result2["data"][CONF_THREE_PHASE_INVERTERS] == [
        THREE_PHASE_INVERTER_SERIAL_NUMBER.upper()
    ]
    assert result2["data"][CONF_PORTS] == discovered_ports
    assert result2["data"][CONF_HYBRID_INVERTERS] == discovered_hybrid_inverters

    assert existing_entry.data[CONF_INVERTERS] == [INVERTER_KEEP_SERIAL_NUMBER]
    assert existing_entry.data[CONF_THREE_PHASE_INVERTERS] == []
    assert existing_entry.data[CONF_PORTS] == [
        {
            "inverter_serial_number": INVERTER_KEEP_SERIAL_NUMBER,
            "port_number": 1,
        }
    ]
    assert existing_entry.data[CONF_HYBRID_INVERTERS] == []
    assert existing_entry.data[CONF_METERS] == [existing_meter]
    mock_reload.assert_awaited_once_with(existing_entry.entry_id)


async def test_reconfigure_moves_swapped_inverters_between_dtus(
    hass: HomeAssistant,
) -> None:
    """Test reconfiguring either side can move inverters between DTUs."""
    entry_a = _add_config_entry(
        hass,
        entry_id="dtu-a",
        dtu_serial_number=DTU_TEST_SERIAL_NUMBER,
        single_phase_inverters=[INVERTER_A_SERIAL_NUMBER],
        ports=[
            {
                "inverter_serial_number": INVERTER_A_SERIAL_NUMBER,
                "port_number": 1,
            }
        ],
    )
    entry_b = _add_config_entry(
        hass,
        entry_id="dtu-b",
        dtu_serial_number=DTU_SECOND_TEST_SERIAL_NUMBER,
        single_phase_inverters=[INVERTER_B_SERIAL_NUMBER],
        ports=[
            {
                "inverter_serial_number": INVERTER_B_SERIAL_NUMBER,
                "port_number": 1,
            }
        ],
    )

    with patch.object(
        hass.config_entries,
        "async_reload",
        new=AsyncMock(return_value=True),
    ) as mock_reload:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry_b.entry_id,
            },
        )
        with patch(
            "custom_components.hoymiles_wifi.config_flow.async_get_config_entry_data_for_host",
            new=AsyncMock(
                return_value=_discovered_config_data(
                    dtu_serial_number=DTU_SECOND_TEST_SERIAL_NUMBER,
                    single_phase_inverters=[INVERTER_A_SERIAL_NUMBER],
                    ports=[
                        {
                            "inverter_serial_number": INVERTER_A_SERIAL_NUMBER,
                            "port_number": 1,
                        }
                    ],
                )
            ),
        ):
            result2 = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                MOCK_DATA_STEP,
            )

        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "reconfigure_successful"
        assert entry_a.data[CONF_INVERTERS] == []
        assert entry_a.data[CONF_PORTS] == []
        assert entry_b.data[CONF_INVERTERS] == [INVERTER_A_SERIAL_NUMBER]

        result3 = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry_a.entry_id,
            },
        )
        with patch(
            "custom_components.hoymiles_wifi.config_flow.async_get_config_entry_data_for_host",
            new=AsyncMock(
                return_value=_discovered_config_data(
                    dtu_serial_number=DTU_TEST_SERIAL_NUMBER,
                    single_phase_inverters=[INVERTER_B_SERIAL_NUMBER.upper()],
                    ports=[
                        {
                            "inverter_serial_number": INVERTER_B_SERIAL_NUMBER.upper(),
                            "port_number": 1,
                        }
                    ],
                )
            ),
        ):
            result4 = await hass.config_entries.flow.async_configure(
                result3["flow_id"],
                MOCK_DATA_STEP,
            )

    assert result4["type"] == FlowResultType.ABORT
    assert result4["reason"] == "reconfigure_successful"
    assert entry_a.data[CONF_INVERTERS] == [INVERTER_B_SERIAL_NUMBER.upper()]
    assert entry_b.data[CONF_INVERTERS] == []
    assert entry_b.data[CONF_PORTS] == []
    assert mock_reload.await_count == 4


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
