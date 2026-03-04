import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor, ble_client
from esphome.const import CONF_ID

DEPENDENCIES = ["ble_client", "esp32_ble_tracker", "api"]
AUTO_LOAD = ["binary_sensor"]
MULTI_CONF = False

CONF_CONNECTED_SENSOR = "connected"

philips_shaver_ns = cg.esphome_ns.namespace("philips_shaver")
PhilipsShaver = philips_shaver_ns.class_(
    "PhilipsShaver",
    ble_client.BLEClientNode,
    cg.Component,
)

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(PhilipsShaver),
            cv.Optional(CONF_CONNECTED_SENSOR): binary_sensor.binary_sensor_schema(
                device_class="connectivity",
            ),
        }
    )
    .extend(ble_client.BLE_CLIENT_SCHEMA)
    .extend(cv.COMPONENT_SCHEMA)
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await ble_client.register_ble_node(var, config)

    if CONF_CONNECTED_SENSOR in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_CONNECTED_SENSOR])
        cg.add(var.set_connected_sensor(sens))
