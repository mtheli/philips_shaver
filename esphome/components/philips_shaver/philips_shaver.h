#pragma once

#include "esphome/core/component.h"
#include "esphome/components/ble_client/ble_client.h"

#include "coordinator.h"

namespace esphome {
namespace philips_shaver {

// Mode A worker: thin BLEClientNode adapter that forwards GATT/GAP events
// to the ShaverCoordinator. Used when an external `ble_client:` block is
// referenced via `ble_client_id`. All GATT logic lives in the Coordinator.
class PhilipsShaver : public ble_client::BLEClientNode, public Component {
 public:
  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override {
    return setup_priority::AFTER_BLUETOOTH;
  }

  void gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                            esp_ble_gattc_cb_param_t *param) override {
    if (this->coord_ != nullptr)
      this->coord_->on_gattc_event(event, gattc_if, param);
  }
  void gap_event_handler(esp_gap_ble_cb_event_t event,
                          esp_ble_gap_cb_param_t *param) override {
    if (this->coord_ != nullptr)
      this->coord_->on_gap_event(event, param);
  }

  void set_coordinator(ShaverCoordinator *coord) { this->coord_ = coord; }
  void set_log_tag(const std::string &tag) { this->log_tag_ = tag; }

 protected:
  ShaverCoordinator *coord_{nullptr};
  std::string log_tag_;
};

}  // namespace philips_shaver
}  // namespace esphome
