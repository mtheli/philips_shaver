#pragma once

#include "esphome/components/esp32_ble_client/ble_client_base.h"
#include "esphome/components/esp32_ble_tracker/esp32_ble_tracker.h"

#include <esp_gap_ble_api.h>
#include <esp_gattc_api.h>

#include <deque>
#include <functional>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace esphome {
namespace philips_shaver {

class ShaverBridge;  // forward — defined in bridge.h

// Bridge firmware version — injected at build time from the component's VERSION
// file (see __init__.py). The fallback only applies if the define is missing
// (e.g. the header is compiled outside the ESPHome codegen path).
#ifndef PHILIPS_SHAVER_BRIDGE_VERSION
#define PHILIPS_SHAVER_BRIDGE_VERSION "dev"
#endif
static const char *const PHILIPS_SHAVER_VERSION = PHILIPS_SHAVER_BRIDGE_VERSION;
static const char *const EVENT_STATUS = "esphome.philips_shaver_ble_status";
static const char *const EVENT_DATA = "esphome.philips_shaver_ble_data";
static const char *const EVENT_SERVICES = "esphome.philips_shaver_ble_services";

// Bridge mode (reported in collect_info_data so HA can detect pair_capable)
static const char *const MODE_EXTERNAL = "external";    // Mode A
static const char *const MODE_STANDALONE = "standalone";  // Mode B

// Identity-source values reported in collect_info_data + pair_complete event.
// Mode A and Mode-B-with-YAML-MAC pin the identity in YAML; Mode-B
// auto-discovery persists it in NVS; "none" means the bridge is unpaired
// and ready for a new pair-mode arming.
static const char *const IDENTITY_SOURCE_YAML = "yaml";
static const char *const IDENTITY_SOURCE_NVS = "nvs";
static const char *const IDENTITY_SOURCE_NONE = "none";

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
  // Mode + identity reported in collect_info_data / heartbeat so HA can
  // detect whether this bridge supports the pair-mode flow and what the
  // bound brush is. set_mode is "external" (Mode A) or "standalone" (Mode B).
  void set_mode(const std::string &mode) { this->mode_ = mode; }
  void set_identity_source(const std::string &source) {
    this->identity_source_ = source;
  }
  const std::string &get_identity_source() const {
    return this->identity_source_;
  }
  void set_identity_address(const std::string &mac) {
    this->identity_address_ = mac;
  }

  // ── Mode B service operations ─────────────────────────────────────────────
  // Called by Bridge service `ble_pair_mode`. enable=true arms UUID-scan for
  // timeout_s seconds; enable=false cancels. No-op outside Mode B.
  void set_pair_mode(bool enable, uint32_t timeout_s);
  bool is_pair_mode_active() const { return this->pair_mode_active_; }
  // Called by Bridge service `ble_unpair`. Removes the BLE bond, clears
  // any cached identity (Worker side via callback) and disconnects.
  void unpair();
  // Discovery-only: arm UUID-scan for timeout_s seconds, emit one
  // scan_result event per unique MAC observed, then scan_complete.
  // Does NOT connect.
  void set_scan_mode(uint32_t timeout_s);
  bool is_scan_mode_active() const { return this->scan_mode_active_; }
  // Worker calls this for each UUID-matching advert during scan-mode.
  // Internally deduplicates by MAC.
  void emit_scan_result(const std::string &mac,
                         const std::string &addr_type,
                         const std::string &local_name,
                         const std::string &mfr_data, int rssi,
                         const std::string &service_uuid);
  // Targeted pairing: arm pair-mode but only connect to one specific MAC
  // (not the first UUID-match). MAC is normalized to "AA:BB:CC:DD:EE:FF".
  void set_pair_mac(const std::string &mac, uint32_t timeout_s);
  const std::string &get_target_mac() const { return this->target_mac_; }
  // Emit the GATT service list (after a connect) as a one-shot event.
  void list_services();

  // Worker registers callbacks for Mode B-specific operations:
  void set_unpair_cb(std::function<void()> cb) {
    this->unpair_cb_ = std::move(cb);
  }
  // Open-GATT bond detection: fires in the rare path where AUTH_CMPL is
  // skipped (e.g. some legacy brushes that auto-bond). Worker persists the
  // currently-connected MAC as identity. Shaver bonding is the norm so
  // this is mostly a safety hatch for symmetry with Sonicare.
  void set_save_identity_cb(std::function<void()> cb) {
    this->save_identity_cb_ = std::move(cb);
  }

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
  // True while any ATT operation this coordinator issued is outstanding:
  // a HA-driven read, the encryption probe, a HA-driven characteristic
  // write, or the subscribe burst (notify registrations awaiting their
  // REG_FOR_NOTIFY_EVT plus CCCD descriptor writes awaiting their
  // WRITE_DESCR_EVT). Only one ATT request may be in flight per
  // connection — Bluedroid has been observed to lose the response of an
  // operation that races another one — so read_char/write_char defer
  // through pending_calls_ while this holds.
  bool att_busy_() const {
    return this->pending_handle_ != 0 || this->probe_handle_ != 0 ||
           this->write_handle_ != 0 || this->reg_notify_pending_ > 0 ||
           this->pending_cccd_writes_ > 0;
  }
  // Record ATT progress (an op started or completed) for the watchdog.
  void att_progress_();
  // Fire deferred calls from pending_calls_ until one occupies the ATT
  // slot (att_busy_) or the queue is empty. Loop, not recursion: calls
  // that fail synchronously (not_found, gatt_err) simply let the loop
  // continue with the next entry, so no completion path can strand the
  // queue. Re-entrant calls (a fired call completing synchronously and
  // invoking a drain) are no-ops via draining_.
  void drain_pending_calls_();
  // Wrapper around bridge_->fire_event() — keeps emit-call-sites short.
  void emit_(const std::string &event_type,
             const std::map<std::string, std::string> &data);

  esp32_ble_client::BLEClientBase *parent_{nullptr};
  ShaverBridge *bridge_{nullptr};
  std::function<void(bool)> set_enabled_cb_;
  std::function<void()> unpair_cb_;
  std::function<void()> save_identity_cb_;
  std::string log_tag_;  // fallback to file-scope TAG until set

  // Mode + identity (set from to_code() / Worker setup)
  std::string mode_{MODE_EXTERNAL};
  std::string identity_source_{IDENTITY_SOURCE_YAML};
  std::string identity_address_;

  // Pair-mode state machine (Mode B)
  bool pair_mode_active_{false};
  uint32_t pair_mode_until_ms_{0};
  std::string target_mac_;

  // Scan-mode state machine (Mode B)
  bool scan_mode_active_{false};
  uint32_t scan_mode_until_ms_{0};
  std::set<std::string> scan_results_seen_;  // dedup by MAC

  // Unpair drain — short window after ble_unpair before the bridge is
  // re-armed. Lets the BLE stack finish close+disconnect+bond_remove
  // before we accept new connect attempts.
  uint32_t unpair_drain_until_ms_{0};

  static const uint32_t UNPAIR_DRAIN_MS = 2000;
  static const uint32_t MAX_PAIR_MODE_TIMEOUT_S = 600;
  static const uint32_t MAX_SCAN_TIMEOUT_S = 120;

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

  // Pending HA-driven read. Single slot — only one GATT read can be in
  // flight per connection; concurrent requests are serialised via
  // pending_calls_ (see below).
  uint16_t pending_handle_{0};
  std::string pending_char_uuid_;
  std::string pending_service_uuid_;

  // Pending HA-driven characteristic write (single slot, cleared from
  // WRITE_CHAR_EVT). Gated like reads: a write racing an in-flight read
  // is the same Bluedroid response-loss class observed live for CCCD
  // descriptor writes.
  uint16_t write_handle_{0};

  // Subscribe burst tracking. reg_notify_pending_ counts notify
  // registrations issued whose REG_FOR_NOTIFY_EVT hasn't arrived yet —
  // incremented synchronously at issue time so the gate is armed BEFORE
  // the burst's CCCD writes start (the events arrive asynchronously).
  // pending_cccd_writes_ counts issued CCCD descriptor writes awaiting
  // WRITE_DESCR_EVT. Reads racing this burst lose their READ_CHAR_EVT
  // (observed three times live).
  uint8_t reg_notify_pending_{0};
  uint8_t pending_cccd_writes_{0};

  // ATT watchdog: att_last_progress_ms_ is stamped whenever a tracked ATT
  // op starts or completes. If att_busy_() holds with no progress for
  // ATT_WATCHDOG_MS (response event lost — Bluedroid hiccup, consumed by
  // another dispatch branch, …), on_loop() force-clears all in-flight
  // markers, emits read_timeout for a stuck read, falls back to ready for
  // a stuck probe, and keeps the queue draining instead of wedging until
  // disconnect.
  uint32_t att_last_progress_ms_{0};
  static const uint32_t ATT_WATCHDOG_MS = 10000;

  // Re-entrancy guard for drain_pending_calls_().
  bool draining_{false};

  // Subscriptions
  std::map<uint16_t, std::string> notify_map_;            // handle → char_uuid
  std::map<uint16_t, uint16_t> cccd_map_;                 // char_handle → cccd_handle
  std::map<uint16_t, uint8_t> char_props_map_;            // char_handle → properties
  std::vector<std::pair<std::string, std::string>>
      desired_subscriptions_;  // Restored after reconnect
  std::map<uint16_t, uint32_t> last_notify_ms_;           // throttle bookkeeping
  uint32_t notify_throttle_ms_{500};

  // Pending HA service calls deferred until they can run. Two reasons a
  // call lands here: (a) service discovery hasn't completed yet — HA's
  // coordinator fires read/subscribe/write the moment the BLE link is up
  // (OPEN_EVT), but characteristics aren't queryable until SEARCH_CMPL
  // (~5–11 s later for our shavers); (b) another read is already in
  // flight — pending_handle_ is a single slot, so concurrent reads (HA
  // pipelines its poll via asyncio.gather since bridge 1.10.0) are
  // serialised here and drained one at a time as each read completes.
  // Each lambda re-enters the originating method, which re-checks
  // connected_/services_discovered_/parent_ and either runs or
  // re-queues. Drained from start_post_auth_setup_() and each
  // read-completion path, cleared on disconnect.
  // Bounded to keep flash/heap predictable if discovery never completes.
  std::deque<std::function<void()>> pending_calls_;
  static const size_t MAX_PENDING_CALLS = 64;
};

}  // namespace philips_shaver
}  // namespace esphome
