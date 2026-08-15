"""Unit tests for Hoymiles coordinator scheduling helpers."""

from types import SimpleNamespace

from homeassistant.const import CONF_HOST

from custom_components.hoymiles_wifi.const import (
    CONF_DTU_SERIAL_NUMBER,
    CONF_INVERTERS,
    CONF_METERS,
    CONF_THREE_PHASE_INVERTERS,
    DOMAIN,
)
from custom_components.hoymiles_wifi.coordinator import (
    _next_staggered_refresh_time,
    _stagger_slot_for_entries,
    _uses_real_data_coordinator,
)
from custom_components.hoymiles_wifi.sensor import (
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
