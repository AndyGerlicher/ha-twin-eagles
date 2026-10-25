"""Constants for the Twin Eagles integration."""
from datetime import timedelta

DOMAIN = "twin_eagles"
MANUFACTURER = "Twin Eagles"

CONF_SOURCE = "source"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_TECHNOLOGY = "technology"
CONF_MODEL = "model"

SOURCE_CLOUD = "cloud"

SCAN_INTERVAL = timedelta(seconds=30)
