import zlib
from pathlib import Path

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor, ble_client, esp32_ble_tracker
from esphome.const import CONF_ID, CONF_MAC_ADDRESS

DEPENDENCIES = ["esp32_ble_tracker", "api"]
AUTO_LOAD = ["binary_sensor", "esp32_ble_client"]
MULTI_CONF = True

CONF_AUTO_CONNECT = "auto_connect"
CONF_BLE_CLIENT_ID = "ble_client_id"
CONF_BRIDGE_GENERATED_ID = "bridge_generated_id"
CONF_BRIDGE_ID = "bridge_id"
CONF_COORD_GENERATED_ID = "coord_generated_id"
CONF_CONNECTED_SENSOR = "connected"
CONF_DEVICE_ID_LEGACY = "device_id"
CONF_NOTIFY_THROTTLE = "notify_throttle_ms"

philips_shaver_ns = cg.esphome_ns.namespace("philips_shaver")
PhilipsShaver = philips_shaver_ns.class_(
    "PhilipsShaver",
    ble_client.BLEClientNode,
    cg.Component,
)
PhilipsShaverStandalone = philips_shaver_ns.class_(
    "PhilipsShaverStandalone",
    cg.Component,
)
ShaverBridge = philips_shaver_ns.class_(
    "ShaverBridge",
    cg.Component,
)
ShaverCoordinator = philips_shaver_ns.class_("ShaverCoordinator")

# Shared optional fields. The per-mode schemas below extend this; the
# primary `cv.GenerateID()` (no key) is added per mode so cv.Any can
# distinguish them.
_BASE_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_BRIDGE_GENERATED_ID): cv.declare_id(ShaverBridge),
        cv.GenerateID(CONF_COORD_GENERATED_ID): cv.declare_id(
            ShaverCoordinator
        ),
        cv.Optional(CONF_BRIDGE_ID, default=""): cv.string,
        cv.Optional(CONF_DEVICE_ID_LEGACY): cv.string,  # deprecated
        cv.Optional(CONF_NOTIFY_THROTTLE, default=500): cv.positive_int,
        cv.Optional(CONF_CONNECTED_SENSOR): binary_sensor.binary_sensor_schema(
            device_class="connectivity",
        ),
    }
).extend(cv.COMPONENT_SCHEMA)

# Mode A — external ble_client (backward compatible). Worker is PhilipsShaver.
# `ble_client_id` is Required so cv.Any can route a config without it to
# _INTERNAL_SCHEMA cleanly.
_EXTERNAL_SCHEMA = _BASE_SCHEMA.extend(
    {
        cv.GenerateID(): cv.declare_id(PhilipsShaver),
        cv.Required(CONF_BLE_CLIENT_ID): cv.use_id(ble_client.BLEClient),
    }
)

# Mode B — standalone client. Worker IS the BLE client (BLEClientBase
# subclass). Optional mac_address pins identity in YAML; without it, NVS
# auto-discovery via ble_pair_mode kicks in.
_INTERNAL_SCHEMA = _BASE_SCHEMA.extend(
    esp32_ble_tracker.ESP_BLE_DEVICE_SCHEMA
).extend(
    {
        cv.GenerateID(): cv.declare_id(PhilipsShaverStandalone),
        cv.Optional(CONF_MAC_ADDRESS): cv.mac_address,
        cv.Optional(CONF_AUTO_CONNECT): cv.boolean,
    }
)


def _internal_set_defaults(config):
    # Without mac_address, the bridge would auto-pair with the first
    # shaver in range — risky in mixed Direct-BLE / multi-bridge setups.
    # auto_connect defaults to false unless the user explicitly targets
    # one device via mac_address (or opts in by setting auto_connect: true).
    if CONF_AUTO_CONNECT not in config:
        config[CONF_AUTO_CONNECT] = CONF_MAC_ADDRESS in config
    return config


_INTERNAL_VALIDATOR = cv.All(_INTERNAL_SCHEMA, _internal_set_defaults)


def _validate_config(config):
    # Route to the appropriate schema based on the user's keys before any
    # schema runs. Previously this used cv.Any(_EXTERNAL_SCHEMA, _INTERNAL_VALIDATOR),
    # but nested schemas with deferred-ID generation (e.g. binary_sensor_schema
    # inside `connected:`) pollute cv.Any's backtracking — when Mode A's
    # validation attempt fires the deferred declare_id, Mode B can no longer
    # be entered cleanly and cv.Any reports Mode A's error verbatim
    # ("'ble_client_id' is a required option"), even when the user supplied
    # a valid Mode B config with `mac_address`.
    #
    # Explicit routing avoids backtracking entirely: presence of `ble_client_id`
    # selects Mode A, absence selects Mode B. Each schema then runs exactly
    # once against a fresh config dict.
    if CONF_BLE_CLIENT_ID in config:
        return _EXTERNAL_SCHEMA(config)
    return _INTERNAL_VALIDATOR(config)


CONFIG_SCHEMA = _validate_config


def _final_validate(config):
    """Validate that bridge_id is set when multiple instances are configured."""
    if isinstance(config, list) and len(config) > 1:
        for i, entry in enumerate(config):
            bid = entry.get(CONF_BRIDGE_ID) or entry.get(CONF_DEVICE_ID_LEGACY, "")
            if not bid:
                raise cv.Invalid(
                    f"'bridge_id' is required when using multiple philips_shaver "
                    f"instances (missing in entry {i + 1})"
                )
        ids = [
            entry.get(CONF_BRIDGE_ID) or entry.get(CONF_DEVICE_ID_LEGACY, "")
            for entry in config
        ]
        if len(ids) != len(set(ids)):
            raise cv.Invalid(
                f"Each philips_shaver instance must have a unique 'bridge_id', "
                f"found duplicates: {ids}"
            )
    return config


FINAL_VALIDATE_SCHEMA = _final_validate


async def to_code(config):
    # Single source of truth for the bridge firmware version: the VERSION file
    # next to this component, baked into the binary as a compile define so the
    # ESP reports it at runtime and the HA integration's update entity can read
    # the same file from GitHub. Bare string — add_define quotes it itself via
    # safe_exp()/StringLiteral; adding our own quotes would double-quote it.
    version = (Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip()
    cg.add_define("PHILIPS_SHAVER_BRIDGE_VERSION", version)

    # Accept both bridge_id (new) and device_id (deprecated)
    bridge_id = config.get(CONF_BRIDGE_ID) or config.get(CONF_DEVICE_ID_LEGACY, "")

    # Per-instance log tag — every ESP_LOG call routes through it so
    # multi-bridge log streams are unambiguous.
    log_tag = f"philips_shaver.{bridge_id}" if bridge_id else "philips_shaver"

    # Coordinator (plain C++ object — owns BLE/GATT logic)
    coord_var = cg.new_Pvariable(config[CONF_COORD_GENERATED_ID])
    cg.add(coord_var.set_notify_throttle(config[CONF_NOTIFY_THROTTLE]))
    cg.add(coord_var.set_log_tag(log_tag))

    # Bridge — HA service registration, event firing, sensors
    bridge_var = cg.new_Pvariable(config[CONF_BRIDGE_GENERATED_ID])
    await cg.register_component(bridge_var, config)
    cg.add(bridge_var.set_bridge_id(bridge_id))
    cg.add(bridge_var.set_log_tag(log_tag))
    cg.add(bridge_var.set_coordinator(coord_var))
    cg.add(coord_var.set_bridge(bridge_var))

    if CONF_CONNECTED_SENSOR in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_CONNECTED_SENSOR])
        cg.add(bridge_var.set_connected_sensor(sens))

    if CONF_BLE_CLIENT_ID in config:
        # Mode A — PhilipsShaver as BLEClientNode of an external ble_client.
        # ESPHome 2026.4.5+ does not auto-define USE_BLE_CLIENT, so we set
        # it ourselves: philips_shaver.h's `#ifdef USE_BLE_CLIENT` block
        # gates the Mode A class on this. Defining it once here is enough
        # for the whole compilation unit.
        cg.add_define("USE_BLE_CLIENT")
        var = cg.new_Pvariable(config[CONF_ID])
        await cg.register_component(var, config)
        cg.add(var.set_coordinator(coord_var))
        cg.add(var.set_log_tag(log_tag))
        await ble_client.register_ble_node(var, config)
    else:
        # Mode B — PhilipsShaverStandalone extends BLEClientBase directly
        var = cg.new_Pvariable(config[CONF_ID])
        await cg.register_component(var, config)
        cg.add(var.set_coordinator(coord_var))
        cg.add(var.set_log_tag(log_tag))

        pref_ns = zlib.crc32(config[CONF_ID].id.encode())
        cg.add(var.set_pref_namespace(pref_ns))

        if CONF_MAC_ADDRESS in config:
            cg.add(var.set_address(config[CONF_MAC_ADDRESS].as_hex))
        cg.add(var.set_auto_connect(config[CONF_AUTO_CONNECT]))

        await esp32_ble_tracker.register_client(var, config)
