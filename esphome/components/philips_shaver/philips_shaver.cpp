#include "philips_shaver.h"

#include "esphome/core/log.h"

namespace esphome {
namespace philips_shaver {

void PhilipsShaver::setup() {
  // Hand the BLEClientNode's parent (an external ble_client::BLEClient,
  // which IS-A esp32_ble_client::BLEClientBase) to the Coordinator so it
  // can issue GATT operations and read remote-state.
  if (this->coord_ != nullptr) {
    this->coord_->set_parent(this->parent());
    // BLEClient (Mode A wrapper) exposes set_enabled() that BLEClientBase
    // doesn't — route it through a callback so the Coordinator can toggle
    // it during auth-failure backoff without depending on the wrapper type.
    auto *p = this->parent();
    this->coord_->set_set_enabled_cb([p](bool en) { p->set_enabled(en); });
  }
}

void PhilipsShaver::dump_config() {
  // Bridge already prints version + bridge_id in its own dump_config(); this
  // override exists only to satisfy the Component contract.
}

}  // namespace philips_shaver
}  // namespace esphome
