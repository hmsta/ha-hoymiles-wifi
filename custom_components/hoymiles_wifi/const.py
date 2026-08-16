"""Constants for the Hoymiles integration."""

DOMAIN = "hoymiles_wifi"
NAME = "Hoymiles"
DOMAIN = "hoymiles_wifi"
DOMAIN_DATA = f"{DOMAIN}_data"
CONFIG_VERSION = 7

ISSUE_URL = "https://github.com/hmsta/ha-hoymiles-wifi/issues"

CONF_UPDATE_INTERVAL = "update_interval"
CONF_STARTUP_COOLDOWN = "startup_cooldown"
CONF_DTU_SERIAL_NUMBER = "dtu_serial_number"
CONF_INVERTERS = "inverters"
CONF_THREE_PHASE_INVERTERS = "three_phase_inverters"
CONF_HYBRID_INVERTERS = "hybrid_inverters"
CONF_PORTS = "ports"
CONF_METERS = "meters"
CONF_METER_TYPE = "meter_type"
CONF_DELETE_MISSING_INVERTERS = "delete_missing_inverters"
CONF_IS_ENCRYPTED = "is_encrypted"
CONF_ENC_RAND = "enc_rand"
CONF_TIMEOUT = "timeout"

METER_TYPE_AUTO = "auto"
METER_TYPE_SINGLE_PHASE = "single_phase"
METER_TYPE_THREE_PHASE = "three_phase"

DEFAULT_UPDATE_INTERVAL_SECONDS = 35
MIN_UPDATE_INTERVAL_SECONDS = 1
DEFAULT_STARTUP_COOLDOWN_SECONDS = 120
MIN_STARTUP_COOLDOWN_SECONDS = 0
DEFAULT_TIMEOUT_SECONDS = 10
MIN_TIMEOUT_SECONDS = 1

DEFAULT_CONFIG_UPDATE_INTERVAL_SECONDS = 60 * 5
DEFAULT_APP_INFO_UPDATE_INTERVAL_SECONDS = 60 * 60 * 2


HASS_DATA_COORDINATOR = "data_coordinator"
HASS_SHARED_METER_COORDINATOR = "shared_meter_coordinator"
HASS_REAL_DATA_STAGGER_EPOCH = "real_data_stagger_epoch"
HASS_CONFIG_COORDINATOR = "config_coordinator"
HASS_APP_INFO_COORDINATOR = "app_info_coordinator"
HASS_ENERGY_STORAGE_DATA_COORDINATOR = "energy_stroage_data_coordinator"
HASS_DTU = "dtu"
HASS_DATA_UNSUB_OPTIONS_UPDATE_LISTENER = "unsub_options_update_listener"


FCTN_GENERATE_DTU_VERSION_STRING = "generate_dtu_version_string"
FCTN_GENERATE_INVERTER_HW_VERSION_STRING = "generate_version_string"
FCTN_GENERATE_INVERTER_SW_VERSION_STRING = "generate_sw_version_string"

STARTUP_MESSAGE = f"""

-------------------------------------------------------------------
{NAME}
This is a custom integration!
If you have any issues with it please open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
