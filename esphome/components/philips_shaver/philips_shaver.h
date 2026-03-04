#pragma once

#include "esphome/core/component.h"
#include "esphome/components/ble_client/ble_client.h"
#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"
#include "esphome/components/api/custom_api_device.h"

#include <map>
#include <string>

namespace esphome {
namespace philips_shaver {

class PhilipsShaver : public ble_client::BLEClientNode,
                      public Component,
                      public api::CustomAPIDevice {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override {
    return setup_priority::AFTER_BLUETOOTH;
  }

  void gattc_event_handler(esp_gattc_cb_event_t event,
                            esp_gatt_if_t gattc_if,
                            esp_ble_gattc_cb_param_t *param) override;

  void on_read_characteristic(std::string service_uuid,
                               std::string characteristic_uuid);
  void on_subscribe(std::string service_uuid,
                     std::string characteristic_uuid);
  void on_unsubscribe(std::string service_uuid,
                       std::string characteristic_uuid);
  void on_write_characteristic(std::string service_uuid,
                                std::string characteristic_uuid,
                                std::string hex_data);

 protected:
  std::string get_shaver_mac_();

  bool connected_{false};
  uint16_t pending_handle_{0};
  std::string pending_char_uuid_;
  // handle → char_uuid for active notification subscriptions
  std::map<uint16_t, std::string> notify_map_;
  // char_handle → cccd_handle for writing notification enable
  std::map<uint16_t, uint16_t> cccd_map_;
};

}  // namespace philips_shaver
}  // namespace esphome
