DOMAIN = "philips_shaver"

PHILIPS_SERVICE_UUIDS = [
    # Philips-specific services
    "8d560100-3cb9-4387-a7e8-b79d826a7025",  # Platform Service (model, serial, state)
    "8d560200-3cb9-4387-a7e8-b79d826a7025",  # History Service (battery raw, firmware, age)
    "8d560300-3cb9-4387-a7e8-b79d826a7025",  # Control Service (mode, light ring)
    "8d560600-3cb9-4387-a7e8-b79d826a7025",  # Serial/Diagnostic Service
    "8d560700-3cb9-4387-a7e8-b79d826a7025",  # Smart Groomer Service (OneBlade)
    # Standard Bluetooth services (required for standard characteristics)
    "0000180f-0000-1000-8000-00805f9b34fb",  # Battery Service (0x180F)
    "0000180a-0000-1000-8000-00805f9b34fb",  # Device Information Service (0x180A)
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
CHAR_SOFTWARE_REVISION = "00002a28-0000-1000-8000-00805f9b34fb"

# Device Type (Platform Service) — returns "OneBlade" for OneBlade, model number for shavers
CHAR_DEVICE_TYPE = "8d560119-3cb9-4387-a7e8-b79d826a7025"

# Smart Groomer Service (0x0700) — OneBlade only
CHAR_GROOMER_CAPABILITIES = "8d560702-3cb9-4387-a7e8-b79d826a7025"
CHAR_SPEED = "8d560703-3cb9-4387-a7e8-b79d826a7025"
CHAR_SPEED_ZONE_THRESHOLD = "8d560705-3cb9-4387-a7e8-b79d826a7025"
CHAR_SPEED_VERDICT = "8d560706-3cb9-4387-a7e8-b79d826a7025"

SPEED_VERDICTS = {
    0: "optimal",
    1: "too_fast",
    2: "none",
}

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
System Notifications — uint32 LE bitfield (NOTIFY, READ, WRITE)

UUID: 8d560110-3cb9-4387-a7e8-b79d826a7025
Bit 0: Motor Blocked
Bit 1: Clean Reminder
Bit 2: Head Replacement
Bit 3: Battery Overheated
Bit 4: Unplug Before Use
"""
CHAR_CLEANING_REMINDER = "8d56010d-3cb9-4387-a7e8-b79d826a7025"
CHAR_BLADE_REPLACEMENT = "8d56010e-3cb9-4387-a7e8-b79d826a7025"
CHAR_SYSTEM_NOTIFICATIONS = "8d560110-3cb9-4387-a7e8-b79d826a7025"

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
	UUID: 8d560118-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
	Value: (0x) F2-07
	Descriptors: Client Characteristic Configuration
	UUID: 0x2902

"""
CHAR_HEAD_REMAINING_MINUTES = "8d560118-3cb9-4387-a7e8-b79d826a7025"
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
	Unknown Characteristic => SHAVER_HANDLE_STATE_CHARACTERISTIC_UUID (01 = active | 02 = charging)
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
"""
	MOTOR_RPM_MAX_CHARACTERISTIC_UUID
	UUID: 8d560105-3cb9-4387-a7e8-b79d826a7025
	Properties: READ
"""
CHAR_MOTOR_RPM_MAX = "8d560105-3cb9-4387-a7e8-b79d826a7025"
"""
	MOTOR_RPM_MIN_CHARACTERISTIC_UUID
	UUID: 8d56011b-3cb9-4387-a7e8-b79d826a7025
	Properties: READ
"""
CHAR_MOTOR_RPM_MIN = "8d56011b-3cb9-4387-a7e8-b79d826a7025"

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

"""
    SMART_SHAVER_CHARACTERISTIC_APP_HANDLE_SETTINGS
    UUID: 8d560319-3cb9-4387-a7e8-b79d826a7025
    Properties: NOTIFY, READ, WRITE
    Service: Smart Shaver Handle Service (0x0300)

    Coaching & feedback settings bitfield.
    Format: 4 bytes little-endian uint32 (APOLLO/PHOENIX), 1 byte (legacy APA).
    Contains 11 boolean flags packed as a binary integer (MSB-first in app).

    Bit layout (byte[0], bits 0-7):
      Bit 0: notificationSuppression    — suppress app notifications
      Bit 1: realtimeGuidanceSoundOn    — sound alerts during shaving
      Bit 2: postShaveFeedbackSoundOn   — tone after shaving session
      Bit 3: postShaveFeedbackHapticOn  — haptic pulse after shaving
      Bit 4: fullCoachingMode           — light ring on/off (all guidance)
      Bit 5: maxPressureCoachingMode    — pressure-only coaching (no light ring)
      Bit 6: autoUnitDetection          — auto-detect metric/imperial
      Bit 7: starRatingVerdict          — post-session star rating

    Bit layout (byte[1], bits 8-10):
      Bit 8:  fullMotionCoachingMode    — full motion guidance
      Bit 9:  maxMotionCoachingMode     — max motion coaching only
      Bit 10: unknown                   — possibly battery saving mode

    Bytes 1-3 (bits 11-31): unused, must be 0.

    App behavior for light ring toggle:
      ON:  set bit 4 (fullCoachingMode), clear bit 5 (maxPressureCoachingMode)
      OFF: clear bit 4, clear bit 5
      All other bits preserved (read-modify-write).

    Source: Reverse-engineered from BLE interface
"""
CHAR_APP_HANDLE_SETTINGS = "8d560319-3cb9-4387-a7e8-b79d826a7025"
APP_SETTINGS_FULL_COACHING = 1 << 4   # bit 4: light ring on (fullCoachingMode)
APP_SETTINGS_MAX_PRESSURE = 1 << 5    # bit 5: pressure-only coaching

# Cleaning cartridge constants (evaporation algorithm)
CARTRIDGE_CAPACITY = 30.0
EVAPORATION_RATE = 0.04  # cycles lost per day due to fluid evaporation
CLEANING_CONSTANTS = {0: 0.96, 1: 0.96, 2: 1.17, 3: 1.38, 4: 1.58, 5: 1.79, 6: 1.99}
CLEANING_CONSTANT_DEFAULT = 2.20  # for avg >= 7 days between cleanings

LIGHTRING_BRIGHTNESS_MODES = {
    0xFF: "high",
    0xCD: "medium",
    0x9B: "low",
}

LIGHTRING_DEFAULT_COLORS = {
    CHAR_LIGHTRING_COLOR_LOW: (0x00, 0x8F, 0xFF),
    CHAR_LIGHTRING_COLOR_OK: (0xFF, 0x49, 0xFF),
    CHAR_LIGHTRING_COLOR_HIGH: (0xFF, 0x85, 0x00),
    CHAR_LIGHTRING_COLOR_MOTION: (0x37, 0xFF, 0x00),
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

# Motion type
"""
	SMART_SHAVER_CHARACTERISTIC_MOTION_TYPE
	UUID: 8d560305-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
"""
CHAR_MOTION_TYPE = "8d560305-3cb9-4387-a7e8-b79d826a7025"

# Handle load type
"""
	SMART_SHAVER_CHARACTERISTIC_HANDLE_LOAD_TYPE
	UUID: 8d560322-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ
"""
CHAR_HANDLE_LOAD_TYPE = "8d560322-3cb9-4387-a7e8-b79d826a7025"
HANDLE_LOAD_TYPES = {
    0: "not_supported",
    1: "undefined",
    2: "detection_in_progress",
    3: "trimmer",
    4: "shaving_heads",
    5: "styler",
    6: "brush",
    7: "precision_trimmer",
    8: "beardstyler",
    9: "precision_trimmer_or_beardstyler",
    65535: "no_load",
}

# ------------------------------------------------------
# History characteristics
# ------------------------------------------------------
"""
	HISTORY_SYNCHRONIZATION_STATUS_CHARACTERISTIC
	UUID: 8d560209-3cb9-4387-a7e8-b79d826a7025
	Properties: NOTIFY, READ, WRITE
	Value: Number of available history sessions (UINT8)
	Write 0 to advance to next record after reading.
"""
CHAR_HISTORY_SYNC_STATUS = "8d560209-3cb9-4387-a7e8-b79d826a7025"
"""
	HISTORY_TIMESTAMP_CHARACTERISTIC
	UUID: 8d560202-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, NOTIFY
	Value: Unix timestamp (UINT32)
"""
CHAR_HISTORY_TIMESTAMP = "8d560202-3cb9-4387-a7e8-b79d826a7025"
"""
	HISTORY_OPERATION_DURATION_CHARACTERISTIC
	UUID: 8d560207-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, NOTIFY
	Value: Duration in seconds (UINT16)
"""
CHAR_HISTORY_DURATION = "8d560207-3cb9-4387-a7e8-b79d826a7025"
"""
	HISTORY_AVERAGE_CURRENT_CHARACTERISTIC
	UUID: 8d560206-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, NOTIFY
	Value: Average current in mA (UINT16)
"""
CHAR_HISTORY_AVG_CURRENT = "8d560206-3cb9-4387-a7e8-b79d826a7025"
"""
	HISTORY_OPERATION_RPM_CHARACTERISTIC
	UUID: 8d560208-3cb9-4387-a7e8-b79d826a7025
	Properties: READ, NOTIFY
"""
CHAR_HISTORY_RPM = "8d560208-3cb9-4387-a7e8-b79d826a7025"

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
    CHAR_SOFTWARE_REVISION,
    CHAR_HEAD_REMAINING,
    CHAR_HEAD_REMAINING_MINUTES,
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
    # CHAR_MOTOR_RPM_MAX,   # not present on all models, no known use
    # CHAR_MOTOR_RPM_MIN,   # not present on all models, no known use
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
    CHAR_HANDLE_LOAD_TYPE,
    CHAR_MOTION_TYPE,
    CHAR_APP_HANDLE_SETTINGS,
    CHAR_SYSTEM_NOTIFICATIONS,
    CHAR_SPEED,
    CHAR_SPEED_ZONE_THRESHOLD,
]

# Characteristics for initial reading of live thread (same as poll)
LIVE_READ_CHARS = POLL_READ_CHARS

DEFAULT_POLL_INTERVAL = 60
DEFAULT_ENABLE_LIVE_UPDATES = True

CONF_ADDRESS = "address"
CONF_POLL_INTERVAL = "poll_interval"
CONF_ENABLE_LIVE_UPDATES = "enable_live_updates"
CONF_CAPABILITIES = "capabilities"
CONF_SERVICES = "services"
CONF_DEVICE_TYPE = "device_type"

# Transport configuration
CONF_TRANSPORT_TYPE = "transport_type"
TRANSPORT_BLEAK = "bleak"
TRANSPORT_ESP_BRIDGE = "esp_bridge"

CONF_ESP_DEVICE_NAME = "esp_device_name"
CONF_ESP_DEVICE_ID = "esp_device_id"

# Minimum ESP bridge component version required for full functionality
MIN_BRIDGE_VERSION = "1.5.1"

MIN_POLL_INTERVAL = 30
MAX_POLL_INTERVAL = 300

CONF_NOTIFY_THROTTLE = "notify_throttle_ms"
DEFAULT_NOTIFY_THROTTLE = 500
MIN_NOTIFY_THROTTLE = 100
MAX_NOTIFY_THROTTLE = 5000

# Service UUID for each BLE service
SVC_BATTERY = "0000180f-0000-1000-8000-00805f9b34fb"
SVC_DEVICE_INFO = "0000180a-0000-1000-8000-00805f9b34fb"
SVC_PLATFORM = "8d560100-3cb9-4387-a7e8-b79d826a7025"
SVC_HISTORY = "8d560200-3cb9-4387-a7e8-b79d826a7025"
SVC_CONTROL = "8d560300-3cb9-4387-a7e8-b79d826a7025"
SVC_SERIAL = "8d560600-3cb9-4387-a7e8-b79d826a7025"
SVC_GROOMER = "8d560700-3cb9-4387-a7e8-b79d826a7025"

# Characteristic UUID → parent service UUID (required by ESP32 bridge)
CHAR_SERVICE_MAP: dict[str, str] = {
    # Battery Service (0x180F)
    CHAR_BATTERY_LEVEL: SVC_BATTERY,
    # Device Information Service (0x180A)
    CHAR_MODEL_NUMBER: SVC_DEVICE_INFO,
    CHAR_SERIAL_NUMBER: SVC_DEVICE_INFO,
    CHAR_FIRMWARE_REVISION: SVC_DEVICE_INFO,
    CHAR_SOFTWARE_REVISION: SVC_DEVICE_INFO,
    # Platform Service (0x0100)
    CHAR_DEVICE_STATE: SVC_PLATFORM,
    CHAR_MOTOR_CURRENT: SVC_PLATFORM,
    CHAR_MOTOR_CURRENT_MAX: SVC_PLATFORM,
    CHAR_MOTOR_RPM: SVC_PLATFORM,
    CHAR_MOTOR_RPM_MAX: SVC_PLATFORM,
    CHAR_MOTOR_RPM_MIN: SVC_PLATFORM,
    CHAR_TOTAL_AGE: SVC_PLATFORM,
    CHAR_AMOUNT_OF_OPERATIONAL_TURNS: SVC_PLATFORM,
    CHAR_DAYS_SINCE_LAST_USED: SVC_PLATFORM,
    CHAR_AMOUNT_OF_CHARGES: SVC_PLATFORM,
    CHAR_TRAVEL_LOCK: SVC_PLATFORM,
    CHAR_SHAVING_TIME: SVC_PLATFORM,
    CHAR_BLADE_REPLACEMENT: SVC_PLATFORM,
    CHAR_SYSTEM_NOTIFICATIONS: SVC_PLATFORM,
    CHAR_HEAD_REMAINING: SVC_PLATFORM,
    CHAR_HEAD_REMAINING_MINUTES: SVC_PLATFORM,
    CHAR_CLEANING_PROGRESS: SVC_PLATFORM,
    # History Service (0x0200)
    CHAR_HISTORY_SYNC_STATUS: SVC_HISTORY,
    CHAR_HISTORY_TIMESTAMP: SVC_HISTORY,
    CHAR_HISTORY_DURATION: SVC_HISTORY,
    CHAR_HISTORY_AVG_CURRENT: SVC_HISTORY,
    CHAR_HISTORY_RPM: SVC_HISTORY,
    # Control / Smart Shaver Handle Service (0x0300)
    CHAR_CAPABILITIES: SVC_CONTROL,
    CHAR_MOTION_TYPE: SVC_CONTROL,
    CHAR_PRESSURE: SVC_CONTROL,
    CHAR_LIGHTRING_COLOR_LOW: SVC_CONTROL,
    CHAR_LIGHTRING_COLOR_OK: SVC_CONTROL,
    CHAR_LIGHTRING_COLOR_HIGH: SVC_CONTROL,
    CHAR_LIGHTRING_COLOR_MOTION: SVC_CONTROL,
    CHAR_LIGHTRING_COLOR_BRIGHTNESS: SVC_CONTROL,
    CHAR_CLEANING_CYCLES: SVC_CONTROL,
    CHAR_HANDLE_LOAD_TYPE: SVC_CONTROL,
    CHAR_SHAVING_MODE: SVC_CONTROL,
    CHAR_SHAVING_MODE_SETTINGS: SVC_CONTROL,
    CHAR_CUSTOM_SHAVING_MODE_SETTINGS: SVC_CONTROL,
    CHAR_APP_HANDLE_SETTINGS: SVC_CONTROL,
    # Platform Service extras
    CHAR_DEVICE_TYPE: SVC_PLATFORM,
    # Smart Groomer Service (0x0700) — OneBlade only
    CHAR_GROOMER_CAPABILITIES: SVC_GROOMER,
    CHAR_SPEED: SVC_GROOMER,
    CHAR_SPEED_ZONE_THRESHOLD: SVC_GROOMER,
    CHAR_SPEED_VERDICT: SVC_GROOMER,
}
