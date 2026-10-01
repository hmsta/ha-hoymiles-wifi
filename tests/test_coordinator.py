"""Unit tests for Hoymiles coordinator scheduling helpers."""

from dataclasses import replace
import inspect
from types import SimpleNamespace

from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.helpers.update_coordinator import UpdateFailed
from hoymiles_wifi.protobuf import RealDataNew_pb2
import pytest

from custom_components.hoymiles_wifi.binary_sensor import HoymilesInverterSensorEntity
from custom_components.hoymiles_wifi.const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_INVERTERS,
    CONF_METERS,
    CONF_THREE_PHASE_INVERTERS,
    DOMAIN,
)
from custom_components.hoymiles_wifi.coordinator import (
    HoymilesRealDataUpdateCoordinator,
    IncompleteRealDataError,
    _async_get_complete_real_data_new,
    _merge_partial_real_data,
    _next_staggered_refresh_time,
    _stagger_slot_for_entries,
    _uses_real_data_coordinator,
)
from custom_components.hoymiles_wifi.sensor import (
    HOYMILES_SENSORS,
    HoymilesSensorEntityDescription,
    HoymilesDataSensorEntity,
    HoymilesEnergySensorEntity,
)


def _entry(entry_id: str, dtu_serial_number: str):
    """Build a minimal config entry for scheduling helper tests."""
    return SimpleNamespace(
        entry_id=entry_id,
        data={
            CONF_DTU_SERIAL_NUMBER: dtu_serial_number,
            CONF_HOST: f"192.168.10.{entry_id}",
            CONF_INVERTERS: ["1421a01a4525"],
            CONF_THREE_PHASE_INVERTERS: [],
            CONF_METERS: [],
        },
    )


def _real_data_page(
    page: int,
    total_pages: int = 3,
    dtu_serial: str = "4121A01953C8",
):
    """Build one get-real-data-new response page."""
    response = RealDataNew_pb2.RealDataNewReqDTO(
        device_serial_number=dtu_serial,
        timestamp=100,
        ap=total_pages,
        cp=page,
    )
    inverter = response.sgs_data.add()
    inverter.serial_number = 22134652552485 + page
    inverter.modulation_index_signal = -70 - page
    return response


class _PagedDtu:
    """Return predefined outcomes for each requested real-data page."""

    def __init__(self, outcomes):
        self.outcomes = {page: list(values) for page, values in outcomes.items()}
        self.requested_pages = []

    async def async_send_request(self, command, request, response_type):
        self.requested_pages.append(request.cp)
        outcome = self.outcomes[request.cp].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_complete_real_data_fetch_requires_every_page() -> None:
    """Test all advertised pages are fetched and merged."""
    dtu = _PagedDtu(
        {
            0: [_real_data_page(0)],
            1: [_real_data_page(1)],
            2: [_real_data_page(2)],
        }
    )

    response = await _async_get_complete_real_data_new(
        dtu, expected_dtu_serial="4121a01953c8", retries=2
    )

    assert dtu.requested_pages == [0, 1, 2]
    assert [item.modulation_index_signal for item in response.sgs_data] == [
        -70,
        -71,
        -72,
    ]


@pytest.mark.asyncio
async def test_complete_real_data_fetch_retries_a_missing_page() -> None:
    """Test a transient missing page is retried before publishing."""
    dtu = _PagedDtu(
        {
            0: [_real_data_page(0)],
            1: [None, _real_data_page(1)],
            2: [_real_data_page(2)],
        }
    )

    response = await _async_get_complete_real_data_new(dtu, retries=2)

    assert dtu.requested_pages == [0, 1, 1, 2]
    assert len(response.sgs_data) == 3


@pytest.mark.asyncio
async def test_complete_real_data_fetch_rejects_partial_snapshot() -> None:
    """Test an unrecoverable missing page is never returned as valid data."""
    dtu = _PagedDtu(
        {
            0: [_real_data_page(0)],
            1: [None, None],
            2: [_real_data_page(2)],
        }
    )

    with pytest.raises(IncompleteRealDataError, match="cp=1 failed"):
        await _async_get_complete_real_data_new(dtu, retries=2)

    assert dtu.requested_pages == [0, 1, 1, 2]


@pytest.mark.asyncio
async def test_complete_real_data_fetch_retries_wrong_page() -> None:
    """Test a DTU response carrying the wrong cp value is not merged."""
    dtu = _PagedDtu(
        {
            0: [_real_data_page(0)],
            1: [_real_data_page(2), _real_data_page(1)],
            2: [_real_data_page(2)],
        }
    )

    response = await _async_get_complete_real_data_new(dtu, retries=2)

    assert dtu.requested_pages == [0, 1, 1, 2]
    assert len(response.sgs_data) == 3


@pytest.mark.asyncio
async def test_coordinator_retains_values_and_marks_dtu_after_partial_poll() -> None:
    """Test a failed poll preserves values while marking DTU diagnostics failed."""
    previous = _real_data_page(0, total_pages=1)
    dtu = _PagedDtu({0: [None, None, None]})
    coordinator = SimpleNamespace(
        _dtu=dtu,
        _hass=SimpleNamespace(loop=SimpleNamespace(time=lambda: 123.0)),
        _config_entry=SimpleNamespace(
            data={
                CONF_DTU_SERIAL_NUMBER: "4121a01953c8",
                CONF_HOST: "192.168.10.250",
            }
        ),
        _shared_meter_coordinator=None,
        _startup_refresh_pending=True,
        _last_real_data_poll_monotonic=None,
        _real_data_poll_successful=True,
        data=previous,
    )

    response = await HoymilesRealDataUpdateCoordinator._async_update_data(coordinator)

    assert response is previous
    assert coordinator.data is previous
    assert coordinator._real_data_poll_successful is False


@pytest.mark.asyncio
async def test_coordinator_updates_fresh_pages_and_retains_only_missing_records() -> None:
    """Test successful pages update while a failed page keeps its previous records."""
    previous = RealDataNew_pb2.RealDataNewReqDTO()
    for page in range(3):
        previous.MergeFrom(_real_data_page(page))

    fresh_page_0 = _real_data_page(0)
    fresh_page_0.sgs_data[0].modulation_index_signal = -80
    fresh_page_2 = _real_data_page(2)
    fresh_page_2.sgs_data[0].modulation_index_signal = -82
    dtu = _PagedDtu(
        {
            0: [fresh_page_0],
            1: [None, None, None],
            2: [fresh_page_2],
        }
    )
    coordinator = SimpleNamespace(
        _dtu=dtu,
        _hass=SimpleNamespace(loop=SimpleNamespace(time=lambda: 123.0)),
        _config_entry=SimpleNamespace(
            data={
                CONF_DTU_SERIAL_NUMBER: "4121a01953c8",
                CONF_HOST: "192.168.10.250",
            }
        ),
        _shared_meter_coordinator=None,
        _startup_refresh_pending=False,
        _last_real_data_poll_monotonic=None,
        _real_data_poll_successful=True,
        data=previous,
    )

    response = await HoymilesRealDataUpdateCoordinator._async_update_data(coordinator)
    signals = {
        item.serial_number: item.modulation_index_signal
        for item in response.sgs_data
    }

    assert dtu.requested_pages == [0, 1, 1, 1, 2]
    assert signals == {
        22134652552485: -80,
        22134652552486: -71,
        22134652552487: -82,
    }
    assert coordinator._real_data_poll_successful is False


def test_partial_offline_record_preserves_pv_but_sensor_is_unknown() -> None:
    """Keep missing records while respecting the received parent's loss of telemetry."""
    previous = _real_data_page(0, total_pages=1)
    previous_pv = previous.pv_data.add()
    previous_pv.serial_number = previous.sgs_data[0].serial_number
    previous_pv.port_number = 1
    previous_pv.power = 500
    partial = _real_data_page(0, total_pages=1)
    partial.sgs_data[0].modulation_index_signal = 0
    partial.sgs_data[0].link_status = 0

    merged = _merge_partial_real_data(previous, partial)

    assert len(merged.sgs_data) == 1
    assert merged.sgs_data[0].modulation_index_signal == 0
    assert merged.sgs_data[0].link_status == 0
    assert len(merged.pv_data) == 1
    entity = HoymilesDataSensorEntity(
        _entry("entry-a", "4121a01953c8"),
        HoymilesSensorEntityDescription(
            key="pv_data[0].power",
            serial_number="1421a01a4525",
            port_number=1,
        ),
        SimpleNamespace(data=merged),
    )
    assert entity.native_value is None


@pytest.mark.asyncio
async def test_coordinator_first_incomplete_poll_raises_update_failed() -> None:
    """Test no synthetic empty snapshot is published before any good data exists."""
    dtu = _PagedDtu({0: [None, None, None]})
    coordinator = SimpleNamespace(
        _dtu=dtu,
        _hass=SimpleNamespace(loop=SimpleNamespace(time=lambda: 123.0)),
        _config_entry=SimpleNamespace(
            data={
                CONF_DTU_SERIAL_NUMBER: "4121a01953c8",
                CONF_HOST: "192.168.10.250",
            }
        ),
        _shared_meter_coordinator=None,
        _startup_refresh_pending=True,
        _last_real_data_poll_monotonic=None,
        _real_data_poll_successful=None,
        data=None,
    )

    with pytest.raises(UpdateFailed, match="cp=0 failed"):
        await HoymilesRealDataUpdateCoordinator._async_update_data(coordinator)

    assert coordinator._real_data_poll_successful is False


@pytest.mark.asyncio
async def test_coordinator_complete_poll_marks_dtu_connected() -> None:
    """Test a complete snapshot restores the DTU diagnostic state."""
    dtu = _PagedDtu({0: [_real_data_page(0, total_pages=1)]})
    coordinator = SimpleNamespace(
        _dtu=dtu,
        _hass=SimpleNamespace(loop=SimpleNamespace(time=lambda: 123.0)),
        _config_entry=SimpleNamespace(
            data={
                CONF_DTU_SERIAL_NUMBER: "4121a01953c8",
                CONF_HOST: "192.168.10.250",
            }
        ),
        _shared_meter_coordinator=None,
        _startup_refresh_pending=False,
        _last_real_data_poll_monotonic=None,
        _real_data_poll_successful=False,
        data=_real_data_page(0, total_pages=1),
    )

    response = await HoymilesRealDataUpdateCoordinator._async_update_data(coordinator)

    assert response is not coordinator.data
    assert coordinator._real_data_poll_successful is True


@pytest.mark.parametrize("poll_successful", [False, True])
def test_dtu_connectivity_reports_complete_poll_result(poll_successful: bool) -> None:
    """Test only the DTU diagnostic exposes logical poll success or failure."""
    entity = SimpleNamespace(
        coordinator=SimpleNamespace(real_data_poll_successful=poll_successful),
        _dtu=SimpleNamespace(
            get_state=lambda: pytest.fail(
                "raw DTU state should not override a known logical poll result"
            )
        ),
        _native_value=None,
    )

    HoymilesInverterSensorEntity.update_state_value(entity)

    assert entity._native_value is poll_successful


def test_stagger_slots_are_evenly_spaced_by_sorted_dtu_serial() -> None:
    """Test four DTUs are spread evenly across one update interval."""
    entries = [
        _entry("250", "4121a01953c8"),
        _entry("249", "4121a01953c9"),
        _entry("248", "4121a01953ca"),
        _entry("247", "4121a01953cb"),
    ]

    offsets = {
        entry.entry_id: _stagger_slot_for_entries(entries, entry, 300.0)[2]
        for entry in entries
    }

    assert offsets == {
        "250": 0.0,
        "249": 75.0,
        "248": 150.0,
        "247": 225.0,
    }


def test_stagger_slots_adjust_when_a_fifth_dtu_is_added() -> None:
    """Test adding another DTU recalculates slots across the same interval."""
    entries = [
        _entry("250", "4121a01953c8"),
        _entry("249", "4121a01953c9"),
        _entry("248", "4121a01953ca"),
        _entry("247", "4121a01953cb"),
        _entry("246", "4121a01953cc"),
    ]

    offsets = [
        _stagger_slot_for_entries(entries, entry, 300.0)[2] for entry in entries
    ]

    assert offsets == [0.0, 60.0, 120.0, 180.0, 240.0]


def test_stagger_slot_includes_current_entry_if_not_loaded_yet() -> None:
    """Test a current entry not present in the entries list still gets a slot."""
    entries = [_entry("250", "4121a01953c8"), _entry("248", "4121a01953ca")]
    current_entry = _entry("249", "4121a01953c9")

    slot_index, entry_count, offset = _stagger_slot_for_entries(
        entries, current_entry, 300.0
    )

    assert slot_index == 1
    assert entry_count == 3
    assert offset == 100.0


def test_stagger_filter_uses_only_real_data_entries() -> None:
    """Test entries without real-data entities do not take stagger slots."""
    real_data_entry = _entry("250", "4121a01953c8")
    empty_entry = SimpleNamespace(
        entry_id="249",
        data={
            CONF_DTU_SERIAL_NUMBER: "4121a01953c9",
            CONF_HOST: "192.168.10.249",
            CONF_INVERTERS: [],
            CONF_THREE_PHASE_INVERTERS: [],
            CONF_METERS: [],
        },
    )

    assert _uses_real_data_coordinator(real_data_entry) is True
    assert _uses_real_data_coordinator(empty_entry) is False


def test_next_staggered_refresh_uses_startup_epoch_and_slot() -> None:
    """Test the next refresh stays on the configured slot phase."""
    assert _next_staggered_refresh_time(1120.0, 1120.0, 300.0, 0.0) == 1120.0
    assert _next_staggered_refresh_time(1121.0, 1120.0, 300.0, 75.0) == 1195.0
    assert _next_staggered_refresh_time(1495.0, 1120.0, 300.0, 75.0) == 1495.0
    assert _next_staggered_refresh_time(1496.0, 1120.0, 300.0, 75.0) == 1496.0


def test_real_data_scheduler_does_not_call_private_ha_refresh_wrapper() -> None:
    """Test staggered refresh scheduling avoids HA private coordinator helpers."""
    source = inspect.getsource(HoymilesRealDataUpdateCoordinator._schedule_refresh)

    assert "__wrap_handle_refresh_interval" not in source
    assert "_handle_staggered_refresh_interval" in source


def test_staggered_refresh_handler_requests_public_refresh_task() -> None:
    """Test scheduled refreshes are dispatched through async_request_refresh."""

    class FakeHass:
        def __init__(self) -> None:
            self.created_tasks = []

        def async_create_task(self, coroutine):
            self.created_tasks.append(coroutine)
            coroutine.close()

    async def refresh():
        return None

    coordinator = SimpleNamespace(
        hass=FakeHass(),
        _unsub_refresh=lambda: None,
        async_request_refresh=refresh,
    )

    HoymilesRealDataUpdateCoordinator._handle_staggered_refresh_interval(coordinator)

    assert coordinator._unsub_refresh is None
    assert len(coordinator.hass.created_tasks) == 1


def test_sensor_reports_unknown_before_first_real_data_refresh() -> None:
    """Test delayed startup polling does not publish fake zero sensor values."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(data=None, startup_refresh_pending=True)
    entity = HoymilesDataSensorEntity(
        config_entry,
        HoymilesSensorEntityDescription(
            key="dtu_power",
            serial_number="4121a01953c8",
            is_dtu_sensor=True,
        ),
        coordinator,
    )

    assert entity.device_info["identifiers"] == {(DOMAIN, "4121a01953c8")}
    assert entity.native_value is None


def test_daily_energy_accepts_first_value_after_startup_unknown() -> None:
    """Test daily energy can recover from startup unknown to first real value."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(data=None, startup_refresh_pending=True)
    entity = HoymilesEnergySensorEntity(
        config_entry,
        HoymilesSensorEntityDescription(
            key="dtu_daily_energy",
            serial_number="4121a01953c8",
            is_dtu_sensor=True,
            force_keep_maximum_within_day=True,
        ),
        coordinator,
    )

    assert entity.native_value is None

    coordinator.data = SimpleNamespace(dtu_daily_energy=1234)
    coordinator.startup_refresh_pending = False
    entity.update_state_value()

    assert entity.native_value == 1234

    coordinator.data = SimpleNamespace(dtu_daily_energy=1200)
    entity.update_state_value()

    assert entity.native_value == 1234


def test_daily_energy_keeps_same_day_max_but_can_reset_to_zero() -> None:
    """Test daily energy preserves same-day max values and permits midnight reset."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(dtu_daily_energy=1234),
        startup_refresh_pending=False,
    )
    entity = HoymilesEnergySensorEntity(
        config_entry,
        HoymilesSensorEntityDescription(
            key="dtu_daily_energy",
            serial_number="4121a01953c8",
            is_dtu_sensor=True,
            reset_at_midnight=True,
            force_keep_maximum_within_day=True,
        ),
        coordinator,
    )

    assert entity.native_value == 1234

    coordinator.data = SimpleNamespace(dtu_daily_energy=0)
    entity.update_state_value()

    assert entity._native_value == 1234
    assert entity.native_value == 1234

    entity.reset_sensor_value()

    assert entity.native_value == 0.0
    assert entity.assumed_state is False


def test_port_daily_energy_keeps_same_day_max_without_explicit_force_flag() -> None:
    """Test port daily energy follows daily-counter semantics by reset flag alone."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(
            pv_data=[
                SimpleNamespace(
                    serial_number=22134652556250,
                    port_number=1,
                    energy_daily=1530,
                ),
            ]
        ),
        startup_refresh_pending=False,
    )
    entity = HoymilesEnergySensorEntity(
        config_entry,
        HoymilesSensorEntityDescription(
            key="pv_data[0].energy_daily",
            serial_number="1421a01a53da",
            port_number=1,
            reset_at_midnight=True,
        ),
        coordinator,
    )

    assert entity.native_value == 1530

    coordinator.data = SimpleNamespace(
        pv_data=[
            SimpleNamespace(
                serial_number=22134652556250,
                port_number=1,
                energy_daily=0,
            ),
        ]
    )
    entity.update_state_value()

    assert entity._native_value == 1530
    assert entity.native_value == 1530


def test_total_energy_still_protects_against_zero_payload() -> None:
    """Test total energy does not publish a transient zero as a counter reset."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(
            pv_data=[
                SimpleNamespace(
                    serial_number=22134652556250,
                    port_number=1,
                    energy_total=25000,
                ),
            ]
        ),
        startup_refresh_pending=False,
    )
    entity = HoymilesEnergySensorEntity(
        config_entry,
        HoymilesSensorEntityDescription(
            key="pv_data[0].energy_total",
            serial_number="1421a01a53da",
            port_number=1,
        ),
        coordinator,
    )

    assert entity.native_value == 25000

    coordinator.data = SimpleNamespace(
        pv_data=[
            SimpleNamespace(
                serial_number=22134652556250,
                port_number=1,
                energy_total=0,
            ),
        ]
    )
    entity.update_state_value()

    assert entity.native_value == 25000


def test_inverter_sensor_reads_real_data_by_serial_not_stored_index() -> None:
    """Test real-data inverter sensors do not trust discovery order."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(
            sgs_data=[
                SimpleNamespace(serial_number=22134652552530, voltage=5),
                SimpleNamespace(serial_number=22134652556250, voltage=2305),
            ]
        ),
        startup_refresh_pending=False,
    )
    entity = HoymilesDataSensorEntity(
        config_entry,
        HoymilesSensorEntityDescription(
            key="sgs_data[0].voltage",
            serial_number="1421a01a53da",
            conversion_factor=0.1,
        ),
        coordinator,
    )

    assert entity.native_value == 230.5


def test_inverter_signal_strength_is_exposed_as_numeric_sensor() -> None:
    """Test inverter RF signal strength reads from the real-data payload."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(
            sgs_data=[
                SimpleNamespace(
                    serial_number=22134652556250,
                    modulation_index_signal=-86,
                ),
            ]
        ),
        startup_refresh_pending=False,
    )
    entity = HoymilesDataSensorEntity(
        config_entry,
        HoymilesSensorEntityDescription(
            key="sgs_data[0].modulation_index_signal",
            serial_number="1421a01a53da",
        ),
        coordinator,
    )

    assert entity.native_value == -86


def test_inverter_link_status_is_exposed_as_raw_diagnostic_sensor() -> None:
    """Test raw link status, including zero, is published without smoothing."""
    description = next(
        description
        for description in HOYMILES_SENSORS
        if description.key == "sgs_data[<inverter_count>].link_status"
    )
    assert description.entity_category is EntityCategory.DIAGNOSTIC
    assert description.zero_is_valid is True

    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(
            sgs_data=[
                SimpleNamespace(
                    serial_number=22134652556250,
                    link_status=1,
                ),
            ]
        ),
        startup_refresh_pending=False,
    )
    entity = HoymilesDataSensorEntity(
        config_entry,
        replace(
            description,
            key="sgs_data[0].link_status",
            serial_number="1421a01a53da",
        ),
        coordinator,
    )

    assert entity.native_value == 1

    coordinator.data.sgs_data[0].link_status = 0
    entity.update_state_value()

    assert entity.native_value == 0


def test_three_phase_inverter_link_status_sensor_is_defined() -> None:
    """Test three-phase inverters expose the same raw diagnostic field."""
    description = next(
        description
        for description in HOYMILES_SENSORS
        if description.key == "tgs_data[<inverter_count>].link_status"
    )

    assert description.translation_key == "link_status"
    assert description.entity_category is EntityCategory.DIAGNOSTIC
    assert description.zero_is_valid is True


def test_pv_sensor_reads_real_data_by_serial_and_port_not_stored_index() -> None:
    """Test PV sensors are mapped by inverter serial and port."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(
            pv_data=[
                SimpleNamespace(
                    serial_number=22134652552530,
                    port_number=2,
                    energy_daily=None,
                ),
                SimpleNamespace(
                    serial_number=22134652556250,
                    port_number=1,
                    energy_daily=1530,
                ),
                SimpleNamespace(
                    serial_number=22134652556250,
                    port_number=2,
                    energy_daily=1681,
                ),
            ]
        ),
        startup_refresh_pending=False,
    )
    entity = HoymilesEnergySensorEntity(
        config_entry,
        HoymilesSensorEntityDescription(
            key="pv_data[0].energy_daily",
            serial_number="1421a01a53da",
            port_number=2,
        ),
        coordinator,
    )

    assert entity.native_value == 1681


def _pv_power_entity_for_zero_confirmation():
    """Build a live PV power entity for zero-confirmation tests."""
    serial_number = 22134652556250
    coordinator = SimpleNamespace(
        data=SimpleNamespace(
            pv_data=[
                SimpleNamespace(
                    serial_number=serial_number,
                    port_number=1,
                    power=1000,
                    voltage=350,
                )
            ],
            sgs_data=[
                SimpleNamespace(
                    serial_number=serial_number,
                    link_status=1,
                    modulation_index_signal=-80,
                    temperature=470,
                )
            ],
            tgs_data=[],
        ),
        startup_refresh_pending=False,
        real_data_poll_successful=True,
    )
    entity = HoymilesDataSensorEntity(
        SimpleNamespace(
            entry_id="entry-a",
            data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
        ),
        HoymilesSensorEntityDescription(
            key="pv_data[0].power",
            serial_number="1421a01a53da",
            port_number=1,
            conversion_factor=0.1,
        ),
        coordinator,
    )
    return coordinator, entity


def test_pv_power_requires_two_successful_zero_polls() -> None:
    """Test one successful zero sample does not create a production dip."""
    coordinator, entity = _pv_power_entity_for_zero_confirmation()
    assert entity.native_value == 100.0

    coordinator.data.pv_data[0].power = 0
    entity.update_state_value()

    assert entity.native_value == 100.0
    assert entity.assumed_state is True

    entity.update_state_value()

    assert entity.native_value == 0.0
    assert entity.assumed_state is False


@pytest.mark.parametrize("inverter_field", ["sgs_data", "tgs_data"])
@pytest.mark.parametrize("poll_successful", [True, False])
def test_rssi_does_not_validate_empty_four_panel_telemetry(
    inverter_field, poll_successful
) -> None:
    """Repeated default protobuf PV values must never become measured zeros."""
    serial = 22134652556250
    response = RealDataNew_pb2.RealDataNewReqDTO()
    inverter = getattr(response, inverter_field).add(serial_number=serial)
    inverter.modulation_index_signal = -80
    inverter.link_status = 1
    inverter.temperature = 470
    for port in range(1, 5):
        response.pv_data.add(
            serial_number=serial, port_number=port, power=1700, voltage=350
        )
    coordinator = SimpleNamespace(data=response, real_data_poll_successful=True)
    entry = _entry("entry-a", "4121a01953c8")
    panels = [
        HoymilesDataSensorEntity(
            entry,
            HoymilesSensorEntityDescription(
                key=f"pv_data[{port - 1}].power",
                serial_number="1421a01a53da",
                port_number=port,
                conversion_factor=0.1,
            ),
            coordinator,
        )
        for port in range(1, 5)
    ]
    signal = HoymilesDataSensorEntity(
        entry,
        HoymilesSensorEntityDescription(
            key=f"{inverter_field}[0].modulation_index_signal",
            serial_number="1421a01a53da",
        ),
        coordinator,
    )
    assert [panel.native_value for panel in panels] == [170.0] * 4

    coordinator.real_data_poll_successful = poll_successful
    for pv in response.pv_data:
        pv.ClearField("power")
        pv.ClearField("voltage")
    for _ in range(3):
        for panel in panels:
            panel.update_state_value()
        signal.update_state_value()
        assert signal.native_value == -80
        assert [panel.native_value for panel in panels] == [None] * 4

    for pv in response.pv_data:
        pv.power = 1600
        pv.voltage = 350
    coordinator.real_data_poll_successful = True
    for panel in panels:
        panel.update_state_value()
    assert [panel.native_value for panel in panels] == [160.0] * 4


def test_partial_snapshot_retains_pv_when_inverter_rssi_arrives() -> None:
    """Inverter RSSI and fresh ports must not discard ports on failed pages."""
    previous = _real_data_page(0)
    serial = previous.sgs_data[0].serial_number
    previous.sgs_data[0].temperature = 470
    for port in range(1, 5):
        previous.pv_data.add(
            serial_number=serial, port_number=port, power=1700, voltage=350
        )
    partial = _real_data_page(0)
    partial.sgs_data[0].modulation_index_signal = -85
    partial.sgs_data[0].temperature = 475
    partial.pv_data.add(
        serial_number=serial, port_number=1, power=1600, voltage=350
    )

    merged = _merge_partial_real_data(previous, partial)

    assert merged.sgs_data[0].modulation_index_signal == -85
    assert {pv.port_number: pv.power for pv in merged.pv_data} == {
        1: 1600,
        2: 1700,
        3: 1700,
        4: 1700,
    }
    for port, expected in ((1, 1600), (2, 1700), (3, 1700), (4, 1700)):
        entity = HoymilesDataSensorEntity(
            _entry("entry-a", "4121a01953c8"),
            HoymilesSensorEntityDescription(
                key=f"pv_data[{port - 1}].power",
                serial_number="1421a01a4525",
                port_number=port,
            ),
            SimpleNamespace(data=merged, real_data_poll_successful=False),
        )
        assert entity.native_value == expected
    assert len(previous.pv_data) == 4
    assert len(partial.pv_data) == 1


@pytest.mark.parametrize("inverter_field", ["sgs_data", "tgs_data"])
@pytest.mark.parametrize("failed_link_status", [0, 1])
def test_empty_inverter_telemetry_with_rssi_and_recovery(
    inverter_field, failed_link_status
) -> None:
    """Replay producing, empty telemetry with RSSI, and restored production."""
    response = RealDataNew_pb2.RealDataNewReqDTO()
    serial = 22134652556250
    inverter = getattr(response, inverter_field).add(
        serial_number=serial,
        active_power=6528,
        frequency=4995,
        temperature=470,
        modulation_index_signal=-97,
        link_status=1,
    )
    pv = response.pv_data.add(
        serial_number=serial,
        port_number=3,
        power=1699,
        voltage=502,
        current=339,
        energy_total=123458,
    )
    coordinator = SimpleNamespace(data=response, real_data_poll_successful=True)
    entry = _entry("entry-a", "4121a01953c8")

    def sensor(key, *, energy=False, **kwargs):
        cls = HoymilesEnergySensorEntity if energy else HoymilesDataSensorEntity
        return cls(
            entry,
            HoymilesSensorEntityDescription(
                key=key, serial_number="1421a01a53da", **kwargs
            ),
            coordinator,
        )

    measurements = [
        sensor(f"{inverter_field}[0].{field}")
        for field in ("active_power", "frequency", "temperature")
    ] + [
        sensor(f"pv_data[0].{field}", port_number=3)
        for field in ("power", "voltage", "current")
    ]
    signal = sensor(f"{inverter_field}[0].modulation_index_signal")
    link = sensor(f"{inverter_field}[0].link_status", zero_is_valid=True)
    energy = sensor("pv_data[0].energy_total", port_number=3, energy=True)
    assert [entity.native_value for entity in measurements] == [
        6528, 4995, 470, 1699, 502, 339
    ]
    assert energy.native_value == 123458

    inverter.Clear()
    inverter.serial_number = serial
    inverter.modulation_index_signal = -95
    inverter.link_status = failed_link_status
    pv.Clear()
    pv.serial_number = serial
    pv.port_number = 3
    for _ in range(3):
        for entity in [*measurements, signal, link, energy]:
            entity.update_state_value()
        assert [entity.native_value for entity in measurements] == [None] * 6
        assert signal.native_value == -95
        assert link.native_value == failed_link_status
        assert energy.native_value == 123458

    inverter.active_power = 6528
    inverter.frequency = 4998
    inverter.temperature = 478
    inverter.link_status = 1
    pv.power, pv.voltage, pv.current, pv.energy_total = 1700, 497, 342, 123485
    for entity in [*measurements, signal, link, energy]:
        entity.update_state_value()
    assert [entity.native_value for entity in measurements] == [
        6528, 4998, 478, 1700, 497, 342
    ]
    assert signal.native_value == -95
    assert link.native_value == 1
    assert energy.native_value == 123485


@pytest.mark.parametrize("inverter_field", ["sgs_data", "tgs_data"])
def test_valid_zero_ac_power_does_not_require_rssi(inverter_field) -> None:
    """A zero output with valid frequency is valid even without RF diagnostics."""
    response = RealDataNew_pb2.RealDataNewReqDTO()
    getattr(response, inverter_field).add(
        serial_number=22134652556250, active_power=0, frequency=5000
    )
    entity = HoymilesDataSensorEntity(
        _entry("entry-a", "4121a01953c8"),
        HoymilesSensorEntityDescription(
            key=f"{inverter_field}[0].active_power",
            serial_number="1421a01a53da",
        ),
        SimpleNamespace(data=response, real_data_poll_successful=True),
    )
    assert entity.native_value == 0


def test_missing_snapshot_never_confirms_zero_panel_power() -> None:
    """Missing coordinator data after startup must remain unknown."""
    coordinator, entity = _pv_power_entity_for_zero_confirmation()
    coordinator.data = None
    for _ in range(3):
        entity.update_state_value()
        assert entity.native_value is None


def test_partial_poll_zero_does_not_count_as_confirmation() -> None:
    """Test a transport failure cannot start or complete zero confirmation."""
    coordinator, entity = _pv_power_entity_for_zero_confirmation()
    coordinator.data.pv_data[0].power = 0
    coordinator.real_data_poll_successful = False

    entity.update_state_value()

    assert entity.native_value == 100.0
    assert entity._zero_confirmation_pending is False

    coordinator.real_data_poll_successful = True
    entity.update_state_value()

    assert entity.native_value == 100.0
    assert entity._zero_confirmation_pending is True

    coordinator.real_data_poll_successful = False
    entity.update_state_value()

    assert entity.native_value == 100.0
    assert entity._zero_confirmation_pending is True

    coordinator.real_data_poll_successful = True
    entity.update_state_value()

    assert entity.native_value == 0.0


def test_offline_panel_is_unknown_instead_of_zero() -> None:
    """Loss of inverter telemetry cannot establish zero panel production."""
    coordinator, entity = _pv_power_entity_for_zero_confirmation()
    coordinator.data.pv_data[0].power = 0
    coordinator.data.sgs_data[0].link_status = 0
    coordinator.data.sgs_data[0].modulation_index_signal = 0
    coordinator.data.sgs_data[0].temperature = 0

    entity.update_state_value()

    assert entity.native_value is None
    assert entity.assumed_state is False


def test_pv_sensor_without_matching_serial_and_port_is_unknown() -> None:
    """Test a missing PV serial/port does not fall back to another inverter."""
    config_entry = SimpleNamespace(
        entry_id="entry-a",
        data={CONF_DTU_SERIAL_NUMBER: "4121a01953c8"},
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(
            pv_data=[
                SimpleNamespace(
                    serial_number=22134652552530,
                    port_number=4,
                    energy_daily=999,
                )
            ]
        ),
        startup_refresh_pending=False,
    )
    entity = HoymilesEnergySensorEntity(
        config_entry,
        HoymilesSensorEntityDescription(
            key="pv_data[0].energy_daily",
            serial_number="1421a01a53da",
            port_number=4,
        ),
        coordinator,
    )

    assert entity.native_value is None
