"""Constants for the Twin Eagles integration."""

DOMAIN = "twin_eagles"
MANUFACTURER = "Twin Eagles"

CONF_SOURCE = "source"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_TECHNOLOGY = "technology"
CONF_MODEL = "model"

SOURCE_CLOUD = "cloud"

# Poll slowly while the grill is off or offline and faster while it is cooking (the grill itself reports every ~4 s).
# Both are configurable in the options flow, in seconds.
CONF_IDLE_INTERVAL = "idle_interval"
CONF_ACTIVE_INTERVAL = "active_interval"
DEFAULT_IDLE_INTERVAL = 120
DEFAULT_ACTIVE_INTERVAL = 20
