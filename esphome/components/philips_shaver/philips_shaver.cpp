#include "philips_shaver.h"

#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/components/esp32_ble/ble.h"

#include <cctype>

namespace espbt = esphome::esp32_ble_tracker;

namespace esphome {
namespace philips_shaver {

static const char *const TAG = "philips_shaver";

// Universal Philips shaver Platform Service — present on every confirmed
// family (V3 OneBlade, V4 XP9201/XP94xx, S9000). Used as the discovery
// filter for Mode B auto-pair scans.
static const espbt::ESPBTUUID SHAVER_SERVICE_UUID =
    espbt::ESPBTUUID::from_raw("8d560100-3cb9-4387-a7e8-b79d826a7025");

// ── PhilipsShaver (Mode A wrapper, BLEClientNode) ────────────────────────────
// Compiled only when the user has a ble_client: block in YAML
// (USE_BLE_CLIENT is defined by ESPHome's loader).

#ifdef USE_BLE_CLIENT

void PhilipsShaver::setup() {
  if (this->coord_ == nullptr) {
    ESP_LOGE(this->log_tag_.c_str(),
             "Coordinator not wired — Mode A worker disabled");
    this->mark_failed();
    return;
  }
  this->coord_->set_parent(this->parent());
  // BLEClient (Mode A wrapper) exposes set_enabled() that BLEClientBase
  // doesn't — route it through a callback so the Coordinator can toggle
  // it during auth-failure backoff without depending on the wrapper type.
  auto *p = this->parent();
  this->coord_->set_set_enabled_cb([p](bool en) { p->set_enabled(en); });
  this->coord_->set_mode(MODE_EXTERNAL);
  // Mode A is YAML-pinned by the ble_client: mac_address — identity can
  // never transition to "nvs" or "none" while this firmware runs.
  this->coord_->set_identity_source(IDENTITY_SOURCE_YAML);
  if (p) {
    auto *bda = p->get_remote_bda();
    char mac[18];
    snprintf(mac, sizeof(mac), "%02X:%02X:%02X:%02X:%02X:%02X",
             bda[0], bda[1], bda[2], bda[3], bda[4], bda[5]);
    this->coord_->set_identity_address(mac);
  }
}

void PhilipsShaver::loop() {
  // Drive the Coordinator's timer state machine here too — Bridge::loop
  // also calls it, on_loop is idempotent so duplicate ticks are harmless.
  if (this->coord_ != nullptr)
    this->coord_->on_loop(millis());
}

void PhilipsShaver::dump_config() {
  // Bridge prints version + bridge_id — keep this brief.
  ESP_LOGCONFIG(this->log_tag_.c_str(),
                "Philips Shaver Mode A worker v%s",
                PHILIPS_SHAVER_VERSION);
}

#endif  // USE_BLE_CLIENT

// ── PhilipsShaverStandalone (Mode B, extends BLEClientBase) ──────────────────

void PhilipsShaverStandalone::setup() {
  // Restore identity (if any) before tracker logic kicks in.
  this->pref_ = global_preferences->make_preference<uint64_t>(this->pref_ns_);

  // Capture YAML provenance BEFORE any branch — at this point a non-zero
  // address_ can only have come from to_code()'s set_address(YAML_MAC).
  // NVS-restored addresses are loaded later inside the else branch.
  this->has_yaml_mac_ = (this->address_ != 0);
  // identity_source default — overwritten in the NVS branch below if the
  // load succeeds. YAML-MAC users skip both branches and it stays "yaml".
  std::string identity_source = IDENTITY_SOURCE_NONE;

  if (this->address_ != 0) {
    ESP_LOGI(this->log_tag_.c_str(),
             "Using configured MAC address — Fixed-MAC mode");
    this->uuid_scan_mode_ = false;
    identity_source = IDENTITY_SOURCE_YAML;
  } else {
    uint64_t stored = 0;
    if (this->pref_.load(&stored) && stored != 0) {
      ESP_LOGI(this->log_tag_.c_str(),
               "Loaded identity address from flash — MAC mode");
      this->set_address(stored);
      this->uuid_scan_mode_ = false;
      identity_source = IDENTITY_SOURCE_NVS;
    } else {
      ESP_LOGI(this->log_tag_.c_str(),
               "No identity in flash — UUID-scan mode "
               "(waiting for ble_pair_mode)");
    }
  }

  if (this->coord_ != nullptr) {
    this->coord_->set_parent(this);
    this->coord_->set_set_enabled_cb(
        [this](bool enabled) { this->set_enabled(enabled); });
    this->coord_->set_mode(MODE_STANDALONE);
    this->coord_->set_identity_source(identity_source);
    if (!this->uuid_scan_mode_ && this->address_ != 0) {
      uint64_t a = this->address_;
      char mac[18];
      snprintf(mac, sizeof(mac), "%02X:%02X:%02X:%02X:%02X:%02X",
               (uint8_t) (a >> 40), (uint8_t) (a >> 32),
               (uint8_t) (a >> 24), (uint8_t) (a >> 16),
               (uint8_t) (a >> 8), (uint8_t) (a));
      this->coord_->set_identity_address(mac);
    }
    // Bond removed by Coordinator::unpair() — react based on identity
    // source:
    //
    // - Fixed-MAC (YAML mac_address:): keep targeting the configured MAC,
    //   wipe NVS as a precaution (was likely empty), don't touch address_.
    //   The brush re-bonds automatically on the next connect (mirrors
    //   Mode A).
    //
    // - Auto-Discovery (no YAML MAC): clear runtime identity, drop back to
    //   UUID-scan mode and wait for the next ble_pair_mode arming.
    this->coord_->set_unpair_cb([this]() {
      uint64_t prev = this->address_;
      uint64_t zero = 0;
      this->pref_.save(&zero);
      if (this->has_yaml_mac_) {
        ESP_LOGW(this->log_tag_.c_str(),
                 "Bond cleared, YAML MAC %02X:%02X:%02X:%02X:%02X:%02X "
                 "stays — will re-bond on next connect",
                 (uint8_t) (prev >> 40), (uint8_t) (prev >> 32),
                 (uint8_t) (prev >> 24), (uint8_t) (prev >> 16),
                 (uint8_t) (prev >> 8), (uint8_t) (prev));
        return;
      }
      this->uuid_scan_mode_ = true;
      this->set_address(0);
      if (prev != 0) {
        ESP_LOGW(this->log_tag_.c_str(),
                 "Identity cleared (was %02X:%02X:%02X:%02X:%02X:%02X) — "
                 "back to UUID-scan mode",
                 (uint8_t) (prev >> 40), (uint8_t) (prev >> 32),
                 (uint8_t) (prev >> 24), (uint8_t) (prev >> 16),
                 (uint8_t) (prev >> 8), (uint8_t) (prev));
      } else {
        ESP_LOGW(this->log_tag_.c_str(),
                 "Identity cleared — back to UUID-scan mode");
      }
    });
    // Open-GATT pair complete — Coordinator detected success without SMP.
    // Persists current MAC as identity (mirrors AUTH_CMPL path in
    // gap_event_handler for bonded brushes). Shavers normally bond, so
    // this is a safety hatch for future families that don't.
    this->coord_->set_save_identity_cb([this]() {
      auto *bda = this->get_remote_bda();
      uint64_t identity = esp32_ble::ble_addr_to_uint64(bda);
      ESP_LOGI(this->log_tag_.c_str(),
               "Open-GATT pair complete — saving identity "
               "%02X:%02X:%02X:%02X:%02X:%02X",
               bda[0], bda[1], bda[2], bda[3], bda[4], bda[5]);
      this->pref_.save(&identity);
      this->set_address(identity);
      this->set_auto_connect(true);
      this->uuid_scan_mode_ = false;
    });
  }

  BLEClientBase::setup();
  // Stay disabled in pure UUID-scan mode (no YAML MAC, no NVS identity)
  // until HA arms pair-mode. With a known identity, behave like Mode A.
  this->enabled_ = !this->uuid_scan_mode_;
  // BLEClientBase::parse_device returns early when auto_connect_ is false,
  // so a bridge with a known target would never reconnect on adverts
  // otherwise. Force it on whenever we have an identity.
  if (!this->uuid_scan_mode_)
    this->set_auto_connect(true);
}

void PhilipsShaverStandalone::loop() {
  // Coordinator's on_loop drives pair-mode timeout + auth-backoff timers,
  // so it must run regardless of enabled_. The BLEClientBase loop is only
  // skipped while we're explicitly disabled (auth backoff) and not idle.
  if (this->enabled_ || this->state() == espbt::ClientState::IDLE)
    BLEClientBase::loop();
  if (this->coord_ != nullptr)
    this->coord_->on_loop(millis());
}

void PhilipsShaverStandalone::set_enabled(bool enabled) {
  if (enabled == this->enabled_)
    return;
  if (!enabled && this->state() != espbt::ClientState::IDLE) {
    ESP_LOGI(this->log_tag_.c_str(), "Disabling BLE client.");
    auto err = esp_ble_gattc_close(this->gattc_if_, this->conn_id_);
    if (err != ESP_OK) {
      ESP_LOGW(this->log_tag_.c_str(),
               "esp_ble_gattc_close error, status=%d", err);
    }
  }
  this->enabled_ = enabled;
}

bool PhilipsShaverStandalone::parse_device(
    const espbt::ESPBTDevice &device) {
  if (!this->enabled_)
    return false;

  if (!this->uuid_scan_mode_)
    return BLEClientBase::parse_device(device);

  if (this->coord_ == nullptr)
    return false;

  // Match against the universal Philips Shaver Platform Service UUID
  // (8d560100). Returns true when matched so callers can label
  // scan_result events.
  bool matched = false;
  for (const auto &uuid : device.get_service_uuids()) {
    if (uuid == SHAVER_SERVICE_UUID) {
      matched = true;
      break;
    }
  }

  // Scan-only: emit one event per unique MAC, never connect.
  if (this->coord_->is_scan_mode_active()) {
    if (matched) {
      const char *addr_type = device.get_address_type() == BLE_ADDR_TYPE_PUBLIC
                                  ? "public"
                                  : "random";
      std::string mfr_hex;
      const auto &mfr_datas = device.get_manufacturer_datas();
      if (!mfr_datas.empty()) {
        const auto &m = mfr_datas[0];
        if (m.uuid.get_uuid().len == ESP_UUID_LEN_16) {
          uint16_t cid = m.uuid.get_uuid().uuid.uuid16;
          char buf[5];
          // Company ID is little-endian on wire — preserve that here.
          snprintf(buf, sizeof(buf), "%02X%02X",
                   (uint8_t) (cid & 0xFF), (uint8_t) ((cid >> 8) & 0xFF));
          mfr_hex = buf;
        }
        if (!m.data.empty())
          mfr_hex += format_hex(m.data.data(), m.data.size());
      }
      this->coord_->emit_scan_result(device.address_str(), addr_type,
                                      device.get_name(), mfr_hex,
                                      device.get_rssi(),
                                      "philips_shaver_platform");
    }
    return false;
  }

  // Pair-mode: connect to first match (or to target_mac_ if set).
  if (!this->coord_->is_pair_mode_active())
    return false;
  if (this->state() != espbt::ClientState::IDLE)
    return false;

  const std::string &target = this->coord_->get_target_mac();
  if (!target.empty()) {
    // Targeted (ble_pair_mac): match exactly this MAC, no UUID filter
    // (the brush may not advertise its service UUID in some adverts).
    if (device.address_str() != target)
      return false;
    ESP_LOGI(this->log_tag_.c_str(), "Pair-mode targeted match: %s",
             target.c_str());
  } else {
    if (!matched)
      return false;
    ESP_LOGI(this->log_tag_.c_str(),
             "Found Philips shaver via UUID at %s (pair-mode)",
             device.address_str().c_str());
  }

  this->set_address(device.address_uint64());
  this->remote_addr_type_ = device.get_address_type();
  this->set_state(espbt::ClientState::DISCOVERED);
  return true;
}

bool PhilipsShaverStandalone::gattc_event_handler(
    esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
    esp_ble_gattc_cb_param_t *param) {
  // BLEClientBase returns true only when this event is for our own GATT
  // connection (matched conn_id / gattc_if). On multi-bridge boards this
  // gate is what keeps us from reacting to other bridges' events.
  bool result = BLEClientBase::gattc_event_handler(event, gattc_if, param);
  if (this->coord_ != nullptr && result)
    this->coord_->on_gattc_event(event, gattc_if, param);
  return result;
}

void PhilipsShaverStandalone::gap_event_handler(
    esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {
  BLEClientBase::gap_event_handler(event, param);

  // Identity persistence: after first successful bonding while in
  // UUID-scan mode, save the (now stable) identity to flash so future
  // boots can target it directly. GAP events are global (every registered
  // client sees them), so on multi-bridge boards we must filter to events
  // for *our* connection — otherwise a parallel bond on bridge A would
  // overwrite bridge B's NVS with bridge A's identity.
  if (event == ESP_GAP_BLE_AUTH_CMPL_EVT &&
      param->ble_security.auth_cmpl.success && this->uuid_scan_mode_ &&
      memcmp(this->remote_bda_, param->ble_security.auth_cmpl.bd_addr, 6) ==
          0) {
    uint64_t identity =
        esp32_ble::ble_addr_to_uint64(param->ble_security.auth_cmpl.bd_addr);
    const auto *bda = param->ble_security.auth_cmpl.bd_addr;
    char mac[18];
    snprintf(mac, sizeof(mac), "%02X:%02X:%02X:%02X:%02X:%02X",
             bda[0], bda[1], bda[2], bda[3], bda[4], bda[5]);
    ESP_LOGI(this->log_tag_.c_str(),
             "Bonded — saving identity %s, switching to MAC mode", mac);
    this->pref_.save(&identity);
    this->set_address(identity);
    this->set_auto_connect(true);
    this->remote_addr_type_ = param->ble_security.auth_cmpl.addr_type;
    this->uuid_scan_mode_ = false;
    if (this->coord_ != nullptr) {
      this->coord_->set_identity_source(IDENTITY_SOURCE_NVS);
      this->coord_->set_identity_address(mac);
    }
  }

  if (this->coord_ != nullptr)
    this->coord_->on_gap_event(event, param);
}

}  // namespace philips_shaver
}  // namespace esphome
