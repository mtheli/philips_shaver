#pragma once

#include "esphome/core/component.h"
#include "esphome/core/preferences.h"
#include "esphome/components/esp32_ble_client/ble_client_base.h"
#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"

#ifdef USE_BLE_CLIENT
#include "esphome/components/ble_client/ble_client.h"
#endif

#include "coordinator.h"

namespace esphome {
namespace philips_shaver {

#ifdef USE_BLE_CLIENT
// Mode A worker: thin BLEClientNode adapter that forwards GATT/GAP events
// to the ShaverCoordinator. Used when an external `ble_client:` block is
// referenced via `ble_client_id`. All GATT logic lives in the Coordinator.
// Compiled only when the user includes `ble_client:` in their YAML.
class PhilipsShaver : public ble_client::BLEClientNode, public Component {
 public:
  void setup() override;
  void loop() override;
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
#endif  // USE_BLE_CLIENT

// Mode B standalone client: extends BLEClientBase directly so we don't
// depend on the `ble_client` component (no dummy `ble_client:` YAML block
// needed). Combines BLE infrastructure + UUID-scan + NVS-persisted
// identity into one class. The Coordinator (mode-agnostic) handles GATT
// state and event emission.
class PhilipsShaverStandalone : public esp32_ble_client::BLEClientBase {
 public:
  void setup() override;
  void loop() override;
  bool parse_device(const esp32_ble_tracker::ESPBTDevice &device) override;
  bool gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                            esp_ble_gattc_cb_param_t *param) override;
  void gap_event_handler(esp_gap_ble_cb_event_t event,
                          esp_ble_gap_cb_param_t *param) override;

  // Wired by to_code(): coordinator pointer, NVS pref namespace (CRC32 of
  // the YAML id so each instance gets its own slot), and per-instance
  // log tag.
  void set_coordinator(ShaverCoordinator *coord) { this->coord_ = coord; }
  void set_pref_namespace(uint32_t ns) { this->pref_ns_ = ns; }
  void set_log_tag(const std::string &tag) { this->log_tag_ = tag; }

  // Mode B set_enabled — closes any in-flight GATT connection if disabling.
  // BLEClientBase's enabled_ field controls whether parse_device() will
  // accept adverts; we override to also tear down a live connection on
  // disable so auth-backoff actually disconnects.
  void set_enabled(bool enabled);

 protected:
  ShaverCoordinator *coord_{nullptr};
  std::string log_tag_;
  // True on first scan when no YAML mac and no NVS identity. parse_device()
  // does the UUID-match in this mode; once an identity is bound (from
  // pair-mode or NVS load) we flip it off and let BLEClientBase's
  // address-match logic take over.
  bool uuid_scan_mode_{true};
  // BLEClientBase has no `enabled_` — it lives on `BLEClient` (the Mode A
  // wrapper). We declare our own here for the Coordinator's set_enabled
  // callback to toggle. parse_device() and loop() gate on it.
  bool enabled_{true};
  // Captured at setup() — pin set to true if YAML had `mac_address:`.
  // Governs unpair-callback behavior: Fixed-MAC keeps the YAML target,
  // Auto-Discovery clears address_ and flips uuid_scan_mode_ back on.
  bool has_yaml_mac_{false};
  uint32_t pref_ns_{0};
  ESPPreferenceObject pref_;
};

}  // namespace philips_shaver
}  // namespace esphome
