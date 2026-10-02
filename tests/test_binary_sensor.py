"""Regression tests for zero-export entity naming."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.hoymiles_wifi.binary_sensor import (
    HoymilesBinarySensorEntityDescription,
    HoymilesExportManagementSensorEntity,
    _repair_export_management_entity_id,
)
from custom_components.hoymiles_wifi.const import CONF_DTU_SERIAL_NUMBER, DOMAIN


CANONICAL_ID = "binary_sensor.dtu_4121a01954d1_zero_export_enable"
GENERATED_ID = "binary_sensor.solar_dtu_4121a01954d1_export_management_enabled"


def test_export_sensor_has_explicit_serial_entity_id():
    """HA must receive an explicit ID rather than derive it from the device name."""
    entry = SimpleNamespace(
        entry_id="test-entry",
        data={CONF_DTU_SERIAL_NUMBER: "4121A01954D1"},
    )
    sensor = HoymilesExportManagementSensorEntity(
        entry,
        HoymilesBinarySensorEntityDescription(
            key="zero_export_enable",
            translation_key="zero_export_enable",
            is_dtu_sensor=True,
            serial_number="4121A01954D1",
        ),
        MagicMock(config_entry=None),
    )
    assert sensor.entity_id == CANONICAL_ID
    assert sensor.unique_id == "hoymiles_test-entry_zero_export_enable"


@pytest.mark.parametrize(
    ("existing_id", "occupied", "rename"),
    [
        (GENERATED_ID, False, True),
        (CANONICAL_ID, False, False),
        (None, False, False),
        (GENERATED_ID, True, False),
    ],
)
def test_export_sensor_repairs_existing_name(existing_id, occupied, rename):
    """Rename the existing registry row without deleting it or replacing conflicts."""
    registry = MagicMock()
    registry.async_get_entity_id.return_value = existing_id
    registry.async_get.return_value = object() if occupied else None
    sensor = SimpleNamespace(entity_id=CANONICAL_ID, unique_id="export-unique-id")
    with patch(
        "custom_components.hoymiles_wifi.binary_sensor.er.async_get",
        return_value=registry,
    ):
        _repair_export_management_entity_id(object(), sensor)
    registry.async_get_entity_id.assert_called_once_with(
        "binary_sensor", DOMAIN, "export-unique-id"
    )
    if rename:
        registry.async_update_entity.assert_called_once_with(
            GENERATED_ID, new_entity_id=CANONICAL_ID
        )
    else:
        registry.async_update_entity.assert_not_called()
