import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor, ble_client
from esphome.const import CONF_ID

DEPENDENCIES = ["ble_client", "esp32_ble_tracker", "api"]
AUTO_LOAD = ["binary_sensor"]
MULTI_CONF = True

CONF_CONNECTED_SENSOR = "connected"
CONF_NOTIFY_THROTTLE = "notify_throttle_ms"
CONF_BRIDGE_ID = "bridge_id"
CONF_DEVICE_ID_LEGACY = "device_id"
CONF_BRIDGE_GENERATED_ID = "bridge_generated_id"
CONF_COORD_GENERATED_ID = "coord_generated_id"

philips_shaver_ns = cg.esphome_ns.namespace("philips_shaver")
PhilipsShaver = philips_shaver_ns.class_(
    "PhilipsShaver",
    ble_client.BLEClientNode,
    cg.Component,
)
ShaverBridge = philips_shaver_ns.class_(
    "ShaverBridge",
    cg.Component,
)
ShaverCoordinator = philips_shaver_ns.class_("ShaverCoordinator")

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(PhilipsShaver),
            cv.GenerateID(CONF_BRIDGE_GENERATED_ID): cv.declare_id(ShaverBridge),
            cv.GenerateID(CONF_COORD_GENERATED_ID): cv.declare_id(
                ShaverCoordinator
            ),
            cv.Optional(CONF_BRIDGE_ID, default=""): cv.string,
            cv.Optional(CONF_DEVICE_ID_LEGACY): cv.string,  # deprecated, use bridge_id
            cv.Optional(CONF_NOTIFY_THROTTLE, default=500): cv.positive_int,
            cv.Optional(CONF_CONNECTED_SENSOR): binary_sensor.binary_sensor_schema(
                device_class="connectivity",
            ),
        }
    )
    .extend(ble_client.BLE_CLIENT_SCHEMA)
    .extend(cv.COMPONENT_SCHEMA)
)


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
    # Accept both bridge_id (new) and device_id (deprecated)
    bridge_id = config.get(CONF_BRIDGE_ID) or config.get(CONF_DEVICE_ID_LEGACY, "")

    # Per-instance log tag — every ESP_LOG call routes through it so multi-bridge
    # log streams are unambiguous and `logger:` can filter per bridge.
    log_tag = f"philips_shaver.{bridge_id}" if bridge_id else "philips_shaver"

    # Coordinator (plain C++ object — owns BLE/GATT logic, no Component lifecycle)
    coord_var = cg.new_Pvariable(config[CONF_COORD_GENERATED_ID])
    cg.add(coord_var.set_notify_throttle(config[CONF_NOTIFY_THROTTLE]))
    cg.add(coord_var.set_log_tag(log_tag))

    # Bridge (ShaverBridge) — HA service registration, event firing, sensors
    bridge_var = cg.new_Pvariable(config[CONF_BRIDGE_GENERATED_ID])
    await cg.register_component(bridge_var, config)
    cg.add(bridge_var.set_bridge_id(bridge_id))
    cg.add(bridge_var.set_log_tag(log_tag))
    cg.add(bridge_var.set_coordinator(coord_var))
    cg.add(coord_var.set_bridge(bridge_var))

    if CONF_CONNECTED_SENSOR in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_CONNECTED_SENSOR])
        cg.add(bridge_var.set_connected_sensor(sens))

    # Worker (Mode A: PhilipsShaver as BLEClientNode of an external ble_client).
    # Mode B (standalone) will be added in PR2 via cv.Any schema split.
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_coordinator(coord_var))
    cg.add(var.set_log_tag(log_tag))
    await ble_client.register_ble_node(var, config)
