"""Unit tests for shared Hoymiles meter data merging."""

from types import SimpleNamespace

from homeassistant.const import CONF_HOST
from hoymiles_wifi.protobuf import RealDataNew_pb2

from custom_components.hoymiles_wifi.const import CONF_DTU_SERIAL_NUMBER
from custom_components.hoymiles_wifi.sensor import (
    HoymilesSensorEntityDescription,
    HoymilesSharedMeterDataSensorEntity,
    HoymilesSharedMeterEnergySensorEntity,
)
from custom_components.hoymiles_wifi.shared_meter import (
    HoymilesSharedMeterCoordinator,
)


METER_RAW_SERIAL_NUMBER = 18417131393072
METER_SERIAL_NUMBER = "10c012931030"

GOOD_METER_ENERGY_FIELDS = {
    "energy_total_power": 705965,
    "energy_phase_A": 176114,
    "energy_phase_B": 314128,
    "energy_phase_C": 215723,
    "energy_total_consumed": 1610765,
    "energy_phase_A_consumed": 704306,
    "energy_phase_B_consumed": 410489,
    "energy_phase_C_consumed": 495970,
}

BAD_247_METER_ENERGY_FIELDS = {
    "energy_total_power": 228800,
    "energy_phase_A": 228500,
    "energy_phase_B": 229700,
    "energy_phase_C": 1410000,
    "energy_total_consumed": 3360000,
    "energy_phase_A_consumed": 9390000,
    "energy_phase_B_consumed": 429136729,
    "energy_phase_C_consumed": 2220000,
}


def _config_entry(entry_id: str, host: str, dtu_serial_number: str = "4121a01953c8"):
    """Build minimal config entry data for shared meter tests."""
    return SimpleNamespace(
        entry_id=entry_id,
        data={CONF_HOST: host, CONF_DTU_SERIAL_NUMBER: dtu_serial_number},
    )


def _real_data(dtu_serial_number: str, timestamp: int, **meter_fields):
    """Build a real-data response with one meter."""
    data = RealDataNew_pb2.RealDataNewReqDTO()
    data.device_serial_number = dtu_serial_number
    data.timestamp = timestamp
    meter_data = data.meter_data.add()
    meter_data.serial_number = METER_RAW_SERIAL_NUMBER
    meter_data.device_type = 1

    for name, value in meter_fields.items():
        setattr(meter_data, name, value)

    return data


def _meter_record(coordinator: HoymilesSharedMeterCoordinator):
    """Return the merged shared meter record."""
    return coordinator.data[METER_SERIAL_NUMBER]


def test_shared_meter_coordinator_does_not_poll_independently(hass):
    """Test the shared meter coordinator is only push-fed by DTU coordinators."""
    coordinator = HoymilesSharedMeterCoordinator(hass)

    assert coordinator.update_interval is None


def test_remove_meter_clears_shared_meter_record(hass):
    """Test removing a meter clears only its shared in-memory record."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    entry = _config_entry("entry-a", "192.168.10.248")
    coordinator.update_from_real_data(
        _real_data("4121a01953c8", 100, energy_total_consumed=1567000),
        entry,
    )

    coordinator.remove_meter(METER_SERIAL_NUMBER.upper())

    assert METER_SERIAL_NUMBER not in coordinator.data


def test_missing_energy_fields_do_not_clear_shared_totals(hass):
    """Test missing energy fields do not overwrite stored totals."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    entry_a = _config_entry("entry-a", "192.168.10.248")
    entry_b = _config_entry("entry-b", "192.168.10.247")

    coordinator.update_from_real_data(
        _real_data(
            "4121a01953c8",
            100,
            energy_total_consumed=1567000,
            phase_total_power=-200,
        ),
        entry_a,
    )
    coordinator.update_from_real_data(
        _real_data("4121a01953c9", 101, phase_total_power=-250),
        entry_b,
    )

    record = _meter_record(coordinator)
    assert record["values"]["energy_total_consumed"] == 1567000
    assert record["values"]["phase_total_power"] == -250
    assert record["last_source_dtu"] == "4121a01953c9"
    assert record["last_energy_source_dtu"] == "4121a01953c8"


def test_lower_energy_total_rejects_entire_meter_sample(hass):
    """Test stale cumulative energy rejects all values from that sample."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    entry_a = _config_entry("entry-a", "192.168.10.248")
    entry_b = _config_entry("entry-b", "192.168.10.249")

    coordinator.update_from_real_data(
        _real_data(
            "4121a01953c8",
            100,
            energy_total_consumed=1567000,
            phase_total_power=-200,
        ),
        entry_a,
    )
    coordinator.update_from_real_data(
        _real_data(
            "4121a01953c9",
            101,
            energy_total_consumed=1566500,
            phase_total_power=-999,
        ),
        entry_b,
    )

    record = _meter_record(coordinator)
    assert record["values"]["energy_total_consumed"] == 1567000
    assert record["values"]["phase_total_power"] == -200
    assert record["last_source_dtu"] == "4121a01953c8"
    assert record["last_energy_source_dtu"] == "4121a01953c8"

    coordinator.update_from_real_data(
        _real_data(
            "4121a01953c9",
            102,
            energy_total_consumed=1567500,
            phase_total_power=-250,
        ),
        entry_b,
    )

    record = _meter_record(coordinator)
    assert record["values"]["energy_total_consumed"] == 1567500
    assert record["values"]["phase_total_power"] == -250
    assert record["last_source_dtu"] == "4121a01953c9"
    assert record["last_energy_source_dtu"] == "4121a01953c9"


def test_inconsistent_energy_total_rejects_first_meter_sample(hass):
    """Test internally inconsistent cumulative values cannot seed the meter."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    bad_entry = _config_entry("entry-bad", "192.168.10.247")

    coordinator.update_from_real_data(
        _real_data("4121A0194E49", 100, **BAD_247_METER_ENERGY_FIELDS),
        bad_entry,
    )

    assert METER_SERIAL_NUMBER not in coordinator.data


def test_inconsistent_energy_total_rejects_entire_meter_sample(hass):
    """Test inconsistent cumulative values reject all values from that sample."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    good_entry = _config_entry("entry-good", "192.168.10.250")
    bad_entry = _config_entry("entry-bad", "192.168.10.247")

    coordinator.update_from_real_data(
        _real_data(
            "4121A01953C8",
            100,
            phase_total_power=873,
            **GOOD_METER_ENERGY_FIELDS,
        ),
        good_entry,
    )
    coordinator.update_from_real_data(
        _real_data(
            "4121A0194E49",
            101,
            phase_total_power=867,
            **BAD_247_METER_ENERGY_FIELDS,
        ),
        bad_entry,
    )

    record = _meter_record(coordinator)
    assert record["values"]["energy_total_power"] == 705965
    assert record["values"]["energy_total_consumed"] == 1610765
    assert record["values"]["energy_phase_B_consumed"] == 410489
    assert record["values"]["phase_total_power"] == 873
    assert record["last_source_dtu"] == "4121A01953C8"
    assert record["last_energy_source_dtu"] == "4121A01953C8"


def test_equal_energy_total_keeps_newest_energy_source_metadata(hass):
    """Test equal cumulative values do not make source metadata move backward."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    entry_a = _config_entry("entry-a", "192.168.10.248")
    entry_b = _config_entry("entry-b", "192.168.10.250")

    coordinator.update_from_real_data(
        _real_data("4121a01953c8", 100, energy_total_power=697148),
        entry_a,
    )
    coordinator.update_from_real_data(
        _real_data("4121a01953ca", 101, energy_total_power=697148),
        entry_b,
    )
    coordinator.update_from_real_data(
        _real_data("4121a01953c8", 99, energy_total_power=697148),
        entry_a,
    )

    record = _meter_record(coordinator)
    assert record["values"]["energy_total_power"] == 697148
    assert record["last_energy_source_dtu"] == "4121a01953ca"
    assert record["last_energy_source_timestamp"] == 101


def test_instantaneous_power_uses_newest_dtu_sample(hass):
    """Test instantaneous meter fields can update from any DTU."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    entry_a = _config_entry("entry-a", "192.168.10.248")
    entry_b = _config_entry("entry-b", "192.168.10.250")

    coordinator.update_from_real_data(
        _real_data("4121a01953c8", 100, phase_total_power=-200),
        entry_a,
    )
    coordinator.update_from_real_data(
        _real_data("4121a01953ca", 101, phase_total_power=-225),
        entry_b,
    )
    coordinator.update_from_real_data(
        _real_data("4121a01953c8", 99, phase_total_power=-300),
        entry_a,
    )

    record = _meter_record(coordinator)
    assert record["values"]["phase_total_power"] == -225
    assert record["last_source_dtu"] == "4121a01953ca"
    assert record["last_source_timestamp"] == 101


def test_shared_meter_data_sensor_reads_shared_store(hass):
    """Test meter sensors read from the shared meter coordinator."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    entry = _config_entry("entry-a", "192.168.10.248")
    coordinator.update_from_real_data(
        _real_data("4121a01953c8", 100, phase_total_power=-225),
        entry,
    )

    entity = HoymilesSharedMeterDataSensorEntity(
        entry,
        HoymilesSensorEntityDescription(
            key="meter_data[0].phase_total_power",
            serial_number=METER_SERIAL_NUMBER,
            conversion_factor=10,
        ),
        coordinator,
    )

    assert entity.native_value == -2250


def test_shared_meter_energy_sensor_reads_shared_store(hass):
    """Test meter energy sensors read from the shared meter coordinator."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    entry = _config_entry("entry-a", "192.168.10.248")
    coordinator.update_from_real_data(
        _real_data("4121a01953c8", 100, energy_total_consumed=1567000),
        entry,
    )

    entity = HoymilesSharedMeterEnergySensorEntity(
        entry,
        HoymilesSensorEntityDescription(
            key="meter_data[0].energy_total_consumed",
            serial_number=METER_SERIAL_NUMBER,
            conversion_factor=10.0,
        ),
        coordinator,
    )

    assert entity.native_value == 15670000


def test_shared_meter_source_sensor_exposes_metadata(hass):
    """Test source diagnostic sensor exposes useful shared meter metadata."""
    coordinator = HoymilesSharedMeterCoordinator(hass)
    entry = _config_entry("entry-a", "192.168.10.248")
    coordinator.update_from_real_data(
        _real_data(
            "4121a01953c8",
            100,
            phase_total_power=-225,
            energy_total_consumed=1567000,
        ),
        entry,
    )

    entity = HoymilesSharedMeterDataSensorEntity(
        entry,
        HoymilesSensorEntityDescription(
            key="meter_data[0].last_source_dtu",
            serial_number=METER_SERIAL_NUMBER,
        ),
        coordinator,
    )

    assert entity.native_value == "4121a01953c8"
    assert entity.extra_state_attributes["last_source_host"] == "192.168.10.248"
    assert entity.extra_state_attributes["last_source_config_entry_id"] == "entry-a"
    assert entity.extra_state_attributes["last_source_timestamp"] == 100
    assert entity.extra_state_attributes["last_energy_source_dtu"] == "4121a01953c8"
    assert entity.extra_state_attributes["last_energy_source_timestamp"] == 100
