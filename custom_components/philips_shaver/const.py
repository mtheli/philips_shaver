DOMAIN = "philips_shaver"

PHILIPS_SERVICE_UUIDS = [
    "8d560100-3cb9-4387-a7e8-b79d826a7025",
    "8d560200-3cb9-4387-a7e8-b79d826a7025",
    "8d560300-3cb9-4387-a7e8-b79d826a7025",
    "8d560600-3cb9-4387-a7e8-b79d826a7025",
]

# Device infos
"""
	Model Number String
	UUID: 0x2A24 Properties: READ
	Value: XP9201
"""
CHAR_MODEL_NUMBER = "00002a24-0000-1000-8000-00805f9b34fb"
"""
	Serial Number String
	UUID: 0x2A25
	Properties: READ
	Value: XXXXXXXXXXXXXXXXXXXX
"""
CHAR_SERIAL_NUMBER = "00002a25-0000-1000-8000-00805f9b34fb"
"""
	Firmware Revision String
	UUID: 0x2A26
	Properties: READ
	Value: 300012593881
"""
CHAR_FIRMWARE_REVISION = "00002a26-0000-1000-8000-00805f9b34fb"

# shaving infos
"""
	Unknown Characteristic
	UUID: 8d560108-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 00-00
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_DAYS_SINCE_LAST_USED = "8d560108-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d560117-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 61, "a"
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_HEAD_REMAINING = "8d560117-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d56010f-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 1B-00
	Descriptors: Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_SHAVING_TIME = "8d56010f-3cb9-4387-a7e8-b79d826a7025"
# 01=off, 02=shaving, 03=charging
"""
	Unknown Characteristic => SHAVER_HANDLE_STATE_CHARACTERISTIC_UUID (01 = aktiv | 02 = charging)
	UUID: 8d56010a-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 01
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_DEVICE_STATE = "8d56010a-3cb9-4387-a7e8-b79d826a7025"
# 00=unlocked, 01=locked
"""
	Unknown Characteristic
	UUID: 8d56010c-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 00
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_TRAVEL_LOCK = "8d56010c-3cb9-4387-a7e8-b79d826a7025"

# Cleaning characteristics
"""
	Unknown Characteristic
	UUID: 8d56011a-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 64, "d"
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_CLEANING_PROGRESS = "8d56011a-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d56031a-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ, WRITE
	Value: (0x) 16-00
	Client Characteristic Configuration
	Descriptors:
	UUID: 0x2902
"""
CHAR_CLEANING_CYCLES = "8d56031a-3cb9-4387-a7e8-b79d826a7025"

# ------------------------------------------------------
# Motor characteristics
# ------------------------------------------------------
"""
	Unknown Characteristic
	UUID: 8d560102-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 00-00
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_MOTOR_CURRENT = "8d560102-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d560103-3cb9-4387-a7e8-b79d826a7025
	Properties: READ
	Value: (0x) D0-07
"""
CHAR_MOTOR_CURRENT_MAX = "8d560103-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d560104-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 00-00
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_MOTOR_RPM = "8d560104-3cb9-4387-a7e8-b79d826a7025"

# Charging characteristics
"""
	Battery Level
	UUID: 0x2A19
	Properties: NOTIFY, READ
	Value: 76%
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
"""
	Unknown Characteristic
	UUID: 8d560109-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 01-00
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_AMOUNT_OF_CHARGES = "8d560109-3cb9-4387-a7e8-b79d826a7025"

"""
	Unknown Characteristic
	UUID: 8d560107-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 1A-00
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_AMOUNT_OF_OPERATIONAL_TURNS = "8d560107-3cb9-4387-a7e8-b79d826a7025"

# Color rings
"""
	Unknown Characteristic
	UUID: 8d560311-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, WRITE
	Value: (0x)
	00-8F-FF-FF
"""
CHAR_LIGHTRING_COLOR_LOW = "8d560311-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d560312-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, WRITE
	Value: (0x) 37-FF-00-FF
"""
CHAR_LIGHTRING_COLOR_OK = "8d560312-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d560313-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, WRITE
	Value: (0x) FF-85-00-FF
"""
CHAR_LIGHTRING_COLOR_HIGH = "8d560313-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d56031c-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, WRITE
	Value: (0x) FF-49-FF-FF
"""
CHAR_LIGHTRING_COLOR_MOTION = "8d56031c-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d560331-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, WRITE
	Value: (0x) FF
"""
CHAR_LIGHTRING_COLOR_BRIGHTNESS = "8d560331-3cb9-4387-a7e8-b79d826a7025"

LIGHTRING_DEFAULT_COLORS = {
    CHAR_LIGHTRING_COLOR_LOW: (0xFF, 0x00, 0x00),  # (0x00, 0x8F, 0xFF),
    CHAR_LIGHTRING_COLOR_OK: (0xFF, 0x00, 0x00),  # (0xFF, 0x49, 0xFF),
    CHAR_LIGHTRING_COLOR_HIGH: (0xFF, 0x00, 0x00),  # (0xFF, 0x85, 0x00),
    CHAR_LIGHTRING_COLOR_MOTION: (0xFF, 0x00, 0x00),  # (0x37, 0xFF, 0x00),
}

# Shaving mode
"""
	Unknown Characteristic
	UUID: 8d56032a-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ, WRITE
	Value: (0x) 03
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_SHAVING_MODE = "8d56032a-3cb9-4387-a7e8-b79d826a7025"
SHAVING_MODES = {
    0: "sensitive",
    1: "regular",
    2: "intense",
    3: "custom",
    4: "foam",
    5: "battery_saving",
}
# Shaving mode settings
"""
	Unknown Characteristic
	UUID: 8d560332-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) BD-18-F4-01-DC-05-A0-OF-3C-00
	Descriptors:
	Client
	Characteristic Configuration
	UUID: 0x2902
"""
CHAR_SHAVING_MODE_SETTINGS = "8d560332-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic
	UUID: 8d560330-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, WRITE
	Value: (0x) BD-18-F4-01-DC-05-A0-OF-3C-00
"""
# Custom Shaving mode settings for mode "custom" (3
CHAR_CUSTOM_SHAVING_MODE_SETTINGS = "8d560330-3cb9-4387-a7e8-b79d826a7025"
"""
	Unknown Characteristic => SMART_SHAVER_CHARACTERISTIC_PRESSURE
	UUID: 8d56030c-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) 00-00
	Descriptors:
	Client Characteristic Configuration UUID: 0x2902
"""
CHAR_PRESSURE = "8d56030c-3cb9-4387-a7e8-b79d826a7025"

# Shaver age
"""
	Unknown Characteristic
	UUID: 8d560106-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ, WRITE
	Value: (0x) 59-8A-2F-00
	Descriptors:
	Client Characteristic Configuration
	UUID: 0x2902
"""
CHAR_TOTAL_AGE = "8d560106-3cb9-4387-a7e8-b79d826a7025"

# Shaver capabilities
"""
	Unknown Characteristic => SMART_SHAVER_CHARACTERISTIC_CAPABILITY
	UUID: 8d560302-3cb9-4387-a7e8-b79d826a7025
	Properties: READ
	Value: (0x) 69-00-00-00
"""
CHAR_CAPABILITIES = "8d560302-3cb9-4387-a7e8-b79d826a7025"

# characteristics to poll
POLL_READ_CHARS = [
    CHAR_BATTERY_LEVEL,
    CHAR_FIRMWARE_REVISION,
    CHAR_HEAD_REMAINING,
    CHAR_DAYS_SINCE_LAST_USED,
    CHAR_MODEL_NUMBER,
    CHAR_SERIAL_NUMBER,
    CHAR_SHAVING_TIME,
    # CHAR_CLEANING_PROGRESS,
    CHAR_CLEANING_CYCLES,
    # CHAR_MOTOR_CURRENT,
    CHAR_MOTOR_CURRENT_MAX,
    # CHAR_MOTOR_RPM,
    CHAR_LIGHTRING_COLOR_LOW,
    CHAR_LIGHTRING_COLOR_OK,
    CHAR_LIGHTRING_COLOR_HIGH,
    CHAR_LIGHTRING_COLOR_MOTION,
    CHAR_LIGHTRING_COLOR_BRIGHTNESS,
    CHAR_AMOUNT_OF_CHARGES,
    CHAR_AMOUNT_OF_OPERATIONAL_TURNS,
    CHAR_SHAVING_MODE,
    CHAR_SHAVING_MODE_SETTINGS,
    CHAR_CUSTOM_SHAVING_MODE_SETTINGS,
    # CHAR_PRESSURE,
    CHAR_TOTAL_AGE,
]

# characteristics for initial reading of live thread
LIVE_READ_CHARS = [
    CHAR_BATTERY_LEVEL,
    CHAR_FIRMWARE_REVISION,
    CHAR_HEAD_REMAINING,
    CHAR_DAYS_SINCE_LAST_USED,
    CHAR_MODEL_NUMBER,
    CHAR_SERIAL_NUMBER,
    CHAR_SHAVING_TIME,
    CHAR_DEVICE_STATE,
    CHAR_TRAVEL_LOCK,
    # CHAR_CLEANING_PROGRESS,
    CHAR_CLEANING_CYCLES,
    # CHAR_MOTOR_CURRENT,
    CHAR_MOTOR_CURRENT_MAX,
    # CHAR_MOTOR_RPM,
    CHAR_LIGHTRING_COLOR_LOW,
    CHAR_LIGHTRING_COLOR_OK,
    CHAR_LIGHTRING_COLOR_HIGH,
    CHAR_LIGHTRING_COLOR_MOTION,
    CHAR_LIGHTRING_COLOR_BRIGHTNESS,
    CHAR_AMOUNT_OF_CHARGES,
    CHAR_AMOUNT_OF_OPERATIONAL_TURNS,
    CHAR_SHAVING_MODE,
    CHAR_SHAVING_MODE_SETTINGS,
    CHAR_CUSTOM_SHAVING_MODE_SETTINGS,
    # CHAR_PRESSURE,
    CHAR_TOTAL_AGE,
]

DEFAULT_POLL_INTERVAL = 60
DEFAULT_ENABLE_LIVE_UPDATES = True

CONF_ADDRESS = "address"
CONF_POLL_INTERVAL = "poll_interval"
CONF_ENABLE_LIVE_UPDATES = "enable_live_updates"
CONF_CAPABILITIES = "capabilities"

MIN_POLL_INTERVAL = 30
MAX_POLL_INTERVAL = 300
