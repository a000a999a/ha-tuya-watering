"""Constants for Tuya Watering."""

DOMAIN = "tuya_watering"
DOMAIN_CORE = "tuya_home_core"

# Config / options keys
CONF_CORE_ENTRY_ID    = "core_entry_id"
CONF_VALVES           = "valves"

# SMTP (stored in entry.data)
CONF_SMTP_HOST        = "smtp_host"
CONF_SMTP_PORT        = "smtp_port"
CONF_SMTP_SENDER      = "smtp_sender"
CONF_SMTP_PASSWORD    = "smtp_password"

# Notification recipient (stored in entry.options)
CONF_SKIP_RECIPIENT   = "skip_recipient"

DEFAULT_SMTP_HOST     = "smtp.gmail.com"
DEFAULT_SMTP_PORT     = 587

# Per-valve keys
CONF_VALVE_NAME       = "name"
CONF_DEVICE_ID        = "device_id"
CONF_GATEWAY_ID       = "gateway_id"
CONF_GATEWAY_IP       = "gateway_ip"
CONF_GATEWAY_KEY      = "gateway_key"
CONF_SUB_CID          = "sub_cid"
CONF_DEFAULT_DURATION = "default_duration"
CONF_DPS_DURATION     = "dps_duration"
CONF_DPS_TRIGGER      = "dps_trigger"
CONF_DPS_STOP         = "dps_stop"

# GIEX GX-02BT defaults — user can override in config flow
DEFAULT_DURATION    = 120   # seconds
DEFAULT_DPS_DURATION = 104
DEFAULT_DPS_TRIGGER  = 116
DEFAULT_DPS_STOP     = 1

# Local tinytuya
SOCKET_TIMEOUT    = 8      # seconds — prevents event loop hang on unreachable gateway
DPS_SET_DELAY     = 0.5    # seconds between DPS 104 and DPS 116
TUYA_VERSION      = "3.4"
