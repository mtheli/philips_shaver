#pragma once

#include "esphome/components/esp32_ble_client/ble_client_base.h"
#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"

#include <esp_gap_ble_api.h>
#include <esp_gattc_api.h>

#include <functional>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace esphome {
namespace philips_shaver {

class ShaverBridge;  // forward — defined in bridge.h

static const char *const PHILIPS_SHAVER_VERSION = "1.7.1-rc.1";
static const char *const EVENT_STATUS = "esphome.philips_shaver_ble_status";
static const char *const EVENT_DATA = "esphome.philips_shaver_ble_data";

// BLE/GATT logic for a single Philips shaver. Mode-agnostic: works with any
// esp32_ble_client::BLEClientBase parent (an external ble_client::BLEClient
// in Mode A; a standalone subclass added in PR2 for Mode B). Receives raw
// GAP/GATT events from the Worker, manages subscription state, lazy
// encryption and auth tracking. Emits HA events through the Bridge.
class ShaverCoordinator {
 public:
  // ── Setup wiring (called from to_code()) ──────────────────────────────────
  void set_parent(esp32_ble_client::BLEClientBase *parent) {
    this->parent_ = parent;
  }
  void set_bridge(ShaverBridge *bridge) { this->bridge_ = bridge; }
  // Worker registers a callback that toggles its own BLE-client enabled
  // state. Coord uses this to disable the client during auth-failure
  // backoff and re-enable it when the backoff window expires. Routed
  // through a callback because `set_enabled()` lives on BLEClient (Mode A
  // wrapper) and on the standalone subclass (Mode B), neither of which is
  // reachable through the BLEClientBase parent_ pointer.
  void set_set_enabled_cb(std::function<void(bool)> cb) {
    this->set_enabled_cb_ = std::move(cb);
  }
  void set_notify_throttle(uint32_t ms) { this->notify_throttle_ms_ = ms; }
  // Per-instance log tag, set in to_code(): "philips_shaver" (single-bridge)
  // or "philips_shaver.<bridge_id>" (multi-bridge).
  void set_log_tag(const std::string &tag) { this->log_tag_ = tag; }

  // ── Lifecycle (driven by Bridge::loop()) ──────────────────────────────────
  // Drains time-based state (auth backoff). Idempotent — safe to call from
  // multiple loops if needed in the future.
  void on_loop(uint32_t now);

  // ── Event entry points (from Worker) ──────────────────────────────────────
  void on_gattc_event(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                      esp_ble_gattc_cb_param_t *param);
  void on_gap_event(esp_gap_ble_cb_event_t event,
                    esp_ble_gap_cb_param_t *param);

  // ── Service operations (called from Bridge service shims) ─────────────────
  void read_char(const std::string &service_uuid,
                 const std::string &characteristic_uuid);
  void subscribe(const std::string &service_uuid,
                 const std::string &characteristic_uuid);
  void unsubscribe(const std::string &service_uuid,
                   const std::string &characteristic_uuid);
  void write_char(const std::string &service_uuid,
                  const std::string &characteristic_uuid,
                  const std::string &hex_data);
  void set_throttle(uint32_t ms);

  // ── Bridge queries (heartbeat / on_get_info) ──────────────────────────────
  // Snapshot of state used to fill heartbeat + ble_get_info events. Bridge
  // adds bridge_id and event-routing fields itself.
  std::map<std::string, std::string> collect_info_data();
  bool is_connected() const { return this->connected_; }
  bool is_authenticated() const { return this->auth_completed_; }
  bool is_services_discovered() const { return this->services_discovered_; }
  bool has_subscriptions() const { return !this->notify_map_.empty(); }
  std::string get_remote_mac() const;

 protected:
  void apply_smp_params_();
  uint16_t find_cccd_handle_(uint16_t char_handle);
  void resubscribe_all_();
  bool is_already_bonded_();
  void fire_ready_event_();
  void start_post_auth_setup_();
  // Wrapper around bridge_->fire_event() — keeps emit-call-sites short.
  void emit_(const std::string &event_type,
             const std::map<std::string, std::string> &data);

  esp32_ble_client::BLEClientBase *parent_{nullptr};
  ShaverBridge *bridge_{nullptr};
  std::function<void(bool)> set_enabled_cb_;
  std::string log_tag_;  // fallback to file-scope TAG until set

  // Connection state
  bool connected_{false};
  bool services_discovered_{false};
  bool auth_completed_{false};
  uint32_t connect_time_ms_{0};
  uint8_t rapid_disconnect_count_{0};
  static const uint8_t MAX_RAPID_DISCONNECTS = 3;
  // Service discovery on XP9201 takes ~5.5s; 10s covers it with a small
  // margin so a disconnect right after re-encrypt is still counted as
  // rapid (the 5s previous threshold was too tight).
  static const uint32_t RAPID_DISCONNECT_THRESHOLD_MS = 10000;

  // Auth failure backoff
  uint8_t auth_fail_count_{0};
  uint32_t backoff_until_ms_{0};
  static const uint8_t MAX_AUTH_FAILURES = 3;
  static const uint32_t AUTH_BACKOFF_MS = 60000;  // 60 seconds

  // Lazy encryption: don't proactively call set_encryption() on bonded
  // reconnect. SEARCH_CMPL issues a probe read; if it returns
  // INSUF_AUTH/INSUF_ENCR, set_encryption() is triggered then. This
  // avoids racing BTM-rehydrate on cache-hit reconnects (Issue #6).
  bool encryption_requested_{false};
  bool retry_read_after_auth_{false};
  uint16_t probe_handle_{0};
  // Idempotent ready-event fire: ensures start_post_auth_setup_() runs
  // exactly once per connection regardless of how many code paths reach it.
  bool ready_fired_{false};

  // Device-name lookup (GAP 0x2A00) for HA setup-dialog display.
  uint16_t name_handle_{0};
  std::string remote_name_;

  // Pending HA-driven read
  uint16_t pending_handle_{0};
  std::string pending_char_uuid_;

  // Subscriptions
  std::map<uint16_t, std::string> notify_map_;            // handle → char_uuid
  std::map<uint16_t, uint16_t> cccd_map_;                 // char_handle → cccd_handle
  std::map<uint16_t, uint8_t> char_props_map_;            // char_handle → properties
  std::vector<std::pair<std::string, std::string>>
      desired_subscriptions_;  // Restored after reconnect
  std::map<uint16_t, uint32_t> last_notify_ms_;           // throttle bookkeeping
  uint32_t notify_throttle_ms_{500};
};

}  // namespace philips_shaver
}  // namespace esphome
