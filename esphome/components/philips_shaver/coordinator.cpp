#include "coordinator.h"
#include "bridge.h"

#include "esphome/core/log.h"
#include "esphome/core/helpers.h"

#include <esp_system.h>

namespace espbt = esphome::esp32_ble_tracker;

namespace esphome {
namespace philips_shaver {

static const char *const TAG = "philips_shaver.coord";

static espbt::ESPBTUUID parse_uuid(const std::string &uuid_str) {
  if (uuid_str.length() <= 8) {
    uint16_t uuid16 = std::stoul(uuid_str, nullptr, 16);
    return espbt::ESPBTUUID::from_uint16(uuid16);
  }
  return espbt::ESPBTUUID::from_raw(uuid_str);
}

void ShaverCoordinator::emit_(const std::string &event_type,
                               const std::map<std::string, std::string> &data) {
  if (this->bridge_ != nullptr)
    this->bridge_->fire_event(event_type, data);
}

std::string ShaverCoordinator::get_remote_mac() const {
  if (this->parent_ == nullptr)
    return "";
  char mac[18];
  auto *bda = this->parent_->get_remote_bda();
  snprintf(mac, sizeof(mac), "%02X:%02X:%02X:%02X:%02X:%02X",
           bda[0], bda[1], bda[2], bda[3], bda[4], bda[5]);
  return std::string(mac);
}

void ShaverCoordinator::apply_smp_params_() {
  // --- BLE Security (SMP) configuration ---
  //
  // The Philips shaver requires LE Secure Connections for pairing.
  // ESPHome's default pair() uses ESP_BLE_SEC_ENCRYPT (level 1) which the
  // shaver rejects with disconnect reason 0x13 ("Remote User Terminated").
  //
  // These parameters were derived from a btmon capture of a successful
  // pairing on a Linux host:
  //   Host  → Shaver:  io=DisplayYesNo(0x01), auth=0x2D (Bond+MITM+SC+CT2)
  //   Shaver → Host:   io=NoInputNoOutput(0x03), auth=0x09 (Bond+SC)
  //   Result: LE SC "Just Works" pairing (ECDH key exchange, no PIN)
  //
  // esp_ble_set_encryption(ENCRYPT_MITM) is called in SEARCH_CMPL_EVT
  // to initiate pairing using these params.
  //
  // Note: io_cap must be DisplayYesNo to enable Numeric Comparison (NC)
  // pairing when the shaver also reports DisplayYesNo (e.g. XP9400).
  // Without NC, auth completes without MITM, causing INSUF_AUTHENTICATION
  // (status 5) on models that require authenticated encryption.
  // NC requests are auto-confirmed via gap_event_handler().
  // Models with NoInputNoOutput (e.g. XP9201) still use Just Works.
  uint8_t auth_req = 0x2D;  // Bond(1) | MITM(4) | SC(8) | CT2(0x20)
  esp_ble_io_cap_t io_cap = ESP_IO_CAP_IO;  // DisplayYesNo → enables NC when needed
  uint8_t key_size = 16;
  uint8_t init_key = ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK;
  uint8_t rsp_key = ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK;

  esp_ble_gap_set_security_param(ESP_BLE_SM_AUTHEN_REQ_MODE, &auth_req,
                                  sizeof(auth_req));
  esp_ble_gap_set_security_param(ESP_BLE_SM_IOCAP_MODE, &io_cap, sizeof(io_cap));
  esp_ble_gap_set_security_param(ESP_BLE_SM_MAX_KEY_SIZE, &key_size,
                                  sizeof(key_size));
  esp_ble_gap_set_security_param(ESP_BLE_SM_SET_INIT_KEY, &init_key,
                                  sizeof(init_key));
  esp_ble_gap_set_security_param(ESP_BLE_SM_SET_RSP_KEY, &rsp_key,
                                  sizeof(rsp_key));
  ESP_LOGI(this->log_tag_.c_str(),
           "SMP security params applied (io_cap=DisplayYesNo, auth=0x2D)");
}

void ShaverCoordinator::on_loop(uint32_t now) {
  // Re-enable BLE client after auth failure backoff expires
  if (this->backoff_until_ms_ != 0 && now >= this->backoff_until_ms_) {
    ESP_LOGI(this->log_tag_.c_str(),
             "Auth backoff expired — re-enabling BLE connection");
    this->backoff_until_ms_ = 0;
    this->auth_fail_count_ = 0;
    if (this->set_enabled_cb_)
      this->set_enabled_cb_(true);
  }

  // Pair-mode timeout — disarm and emit pair_timeout. Mode B only; in
  // Mode A pair_mode_active_ is never set so this branch is dead.
  if (this->pair_mode_active_ && this->pair_mode_until_ms_ != 0 &&
      now >= this->pair_mode_until_ms_) {
    ESP_LOGW(this->log_tag_.c_str(),
             "Pair-mode timeout — no brush found in window");
    this->pair_mode_active_ = false;
    this->pair_mode_until_ms_ = 0;
    this->target_mac_.clear();
    this->emit_(EVENT_STATUS,
                {
                    {"status", "pair_timeout"},
                    {"version", PHILIPS_SHAVER_VERSION},
                });
    if (this->set_enabled_cb_)
      this->set_enabled_cb_(false);
  }

  // Scan-mode timeout — emit scan_complete + count.
  if (this->scan_mode_active_ && this->scan_mode_until_ms_ != 0 &&
      now >= this->scan_mode_until_ms_) {
    char count_str[8];
    snprintf(count_str, sizeof(count_str), "%d",
             (int) this->scan_results_seen_.size());
    ESP_LOGI(this->log_tag_.c_str(),
             "Scan complete — %s unique result(s)", count_str);
    this->scan_mode_active_ = false;
    this->scan_mode_until_ms_ = 0;
    this->emit_(EVENT_STATUS,
                {
                    {"status", "scan_complete"},
                    {"count", std::string(count_str)},
                    {"version", PHILIPS_SHAVER_VERSION},
                });
    this->scan_results_seen_.clear();
    if (this->set_enabled_cb_ && !this->pair_mode_active_)
      this->set_enabled_cb_(false);
  }

  // Unpair drain — fire `unpaired` after the BLE stack settled.
  if (this->unpair_drain_until_ms_ != 0 &&
      now >= this->unpair_drain_until_ms_) {
    this->unpair_drain_until_ms_ = 0;
    ESP_LOGI(this->log_tag_.c_str(), "Unpair drain complete");
    this->emit_(EVENT_STATUS,
                {
                    {"status", "unpaired"},
                    {"version", PHILIPS_SHAVER_VERSION},
                });
  }
}

std::map<std::string, std::string> ShaverCoordinator::collect_info_data() {
  char subs_str[8];
  snprintf(subs_str, sizeof(subs_str), "%u",
           (uint32_t) this->notify_map_.size());

  char throttle_str[16];
  snprintf(throttle_str, sizeof(throttle_str), "%u", this->notify_throttle_ms_);

  // Check if shaver MAC is in the bonded device list
  std::string paired = "false";
  if (this->parent_ != nullptr) {
    int bond_num = esp_ble_get_bond_device_num();
    if (bond_num > 0) {
      auto *bond_list = new esp_ble_bond_dev_t[bond_num];
      esp_ble_get_bond_device_list(&bond_num, bond_list);
      auto *bda = this->parent_->get_remote_bda();
      for (int i = 0; i < bond_num; i++) {
        if (memcmp(bond_list[i].bd_addr, bda, 6) == 0) {
          paired = "true";
          break;
        }
      }
      delete[] bond_list;
    }
  }

  std::map<std::string, std::string> data = {
      {"version", PHILIPS_SHAVER_VERSION},
      {"ble_connected", this->connected_ ? "true" : "false"},
      {"mac", this->get_remote_mac()},
      {"subscriptions", std::string(subs_str)},
      {"notify_throttle_ms", std::string(throttle_str)},
      {"paired", paired},
      {"mode", this->mode_},
      {"identity_source", this->identity_source_},
      {"pair_capable",
       this->mode_ == MODE_STANDALONE ? "true" : "false"},
  };
  if (!this->identity_address_.empty()) {
    data["identity_address"] = this->identity_address_;
  }
  if (!this->remote_name_.empty()) {
    data["ble_name"] = this->remote_name_;
  }
  return data;
}

void ShaverCoordinator::on_gattc_event(esp_gattc_cb_event_t event,
                                        esp_gatt_if_t gattc_if,
                                        esp_ble_gattc_cb_param_t *param) {
  if (this->parent_ == nullptr)
    return;

  switch (event) {
    case ESP_GATTC_OPEN_EVT: {
      if (param->open.status == ESP_GATT_OK) {
        // Apply SMP params now, before service discovery and pairing.
        // Must happen here because BLEClientBase triggers on_connect (→ pair())
        // in SEARCH_CMPL_EVT before our node handler runs.
        this->apply_smp_params_();
        this->auth_completed_ = false;
        this->connect_time_ms_ = millis();
        ESP_LOGI(this->log_tag_.c_str(), "Connected to shaver (%s)",
                 this->get_remote_mac().c_str());
        this->connected_ = true;
        if (this->bridge_ != nullptr)
          this->bridge_->publish_connected(true);
        this->emit_(EVENT_STATUS,
                    {
                        {"status", "connected"},
                        {"mac", this->get_remote_mac()},
                    });
      } else {
        ESP_LOGW(this->log_tag_.c_str(), "Connection failed, status=%d",
                 param->open.status);
      }
      break;
    }

    case ESP_GATTC_DISCONNECT_EVT: {
      // Detect stale bond: if we keep disconnecting quickly without auth,
      // the stored bond keys are likely invalid (e.g. after OTA or shaver BT
      // reset). Clear the bond after repeated failures so the next connect
      // starts fresh pairing.
      uint32_t connect_duration_ms = millis() - this->connect_time_ms_;
      if (this->auth_completed_ ||
          connect_duration_ms > RAPID_DISCONNECT_THRESHOLD_MS) {
        this->rapid_disconnect_count_ = 0;
      } else {
        this->rapid_disconnect_count_++;
        ESP_LOGD(this->log_tag_.c_str(),
                 "Rapid disconnect without auth after %ums (%d/%d), reason=0x%02X",
                 connect_duration_ms, this->rapid_disconnect_count_,
                 MAX_RAPID_DISCONNECTS, param->disconnect.reason);
        if (this->rapid_disconnect_count_ >= MAX_RAPID_DISCONNECTS) {
          ESP_LOGW(this->log_tag_.c_str(),
                   "Detected %d rapid disconnects without auth — "
                   "clearing stale bond for fresh pairing",
                   this->rapid_disconnect_count_);
          esp_ble_remove_bond_device(this->parent_->get_remote_bda());
          this->rapid_disconnect_count_ = 0;
        }
      }

      ESP_LOGW(this->log_tag_.c_str(),
               "Disconnected from shaver (reason=0x%02X). "
               "%d subscription(s) will be restored on reconnect.",
               param->disconnect.reason,
               this->desired_subscriptions_.size());
      this->connected_ = false;
      this->services_discovered_ = false;
      this->auth_completed_ = false;
      this->encryption_requested_ = false;
      this->retry_read_after_auth_ = false;
      this->probe_handle_ = 0;
      this->ready_fired_ = false;
      if (this->bridge_ != nullptr)
        this->bridge_->publish_connected(false);
      this->pending_handle_ = 0;
      this->name_handle_ = 0;
      // Clear handle-based maps (handles are invalid after disconnect)
      // but keep desired_subscriptions_ for auto-resubscribe
      this->notify_map_.clear();
      this->cccd_map_.clear();
      this->char_props_map_.clear();
      this->last_notify_ms_.clear();
      char reason_str[5];
      snprintf(reason_str, sizeof(reason_str), "0x%02X",
               param->disconnect.reason);
      this->emit_(EVENT_STATUS,
                  {
                      {"status", "disconnected"},
                      {"mac", this->get_remote_mac()},
                      {"reason", reason_str},
                  });
      break;
    }

    case ESP_GATTC_SEARCH_CMPL_EVT: {
      ESP_LOGI(this->log_tag_.c_str(), "Service discovery complete");
      this->services_discovered_ = true;

      // Read GAP Device Name (0x2A00) for display in HA config flow
      if (this->remote_name_.empty()) {
        auto gap_svc = espbt::ESPBTUUID::from_uint16(0x1800);
        auto name_chr = espbt::ESPBTUUID::from_uint16(0x2A00);
        auto *chr = this->parent_->get_characteristic(gap_svc, name_chr);
        if (chr) {
          this->name_handle_ = chr->handle;
          auto status = esp_ble_gattc_read_char(
              this->parent_->get_gattc_if(),
              this->parent_->get_conn_id(), chr->handle,
              ESP_GATT_AUTH_REQ_NONE);
          if (status != ESP_GATT_OK) {
            ESP_LOGD(this->log_tag_.c_str(),
                     "Failed to initiate device name read: %d", status);
            this->name_handle_ = 0;
          }
        }
      }

      // Lazy encryption: instead of proactively calling
      // esp_ble_set_encryption() (which on cache-hit reconnects can race
      // BTM rehydrate → reason=97 → bond cleared, see Issue #6), issue a
      // probe read on a Philips proprietary characteristic that requires
      // auth. The READ_CHAR_EVT handler then either confirms the
      // connection is encrypted (status OK) or triggers SMP via
      // INSUF_AUTH/INSUF_ENCR.
      auto philips_svc = espbt::ESPBTUUID::from_raw(
          "8d560100-3cb9-4387-a7e8-b79d826a7025");
      auto probe_chr = espbt::ESPBTUUID::from_raw(
          "8d560117-3cb9-4387-a7e8-b79d826a7025");
      auto *chr = this->parent_->get_characteristic(philips_svc, probe_chr);
      if (chr) {
        this->probe_handle_ = chr->handle;
        auto status = esp_ble_gattc_read_char(
            this->parent_->get_gattc_if(),
            this->parent_->get_conn_id(), chr->handle,
            ESP_GATT_AUTH_REQ_NONE);
        if (status != ESP_GATT_OK) {
          ESP_LOGD(this->log_tag_.c_str(),
                   "Probe read request failed, status=%d", status);
          this->probe_handle_ = 0;
        } else {
          ESP_LOGD(this->log_tag_.c_str(),
                   "Probe read issued for handle 0x%04X — waiting on result",
                   chr->handle);
        }
      }

      if (this->probe_handle_ == 0) {
        // Fallback for unknown models without the probe char: keep the
        // legacy proactive-encrypt path. SEC_ENCRYPT (no MITM) for
        // bonded devices preserves the v1.5.2 fix; SEC_ENCRYPT_MITM
        // for fresh pairing.
        bool already_bonded = this->is_already_bonded_();
        this->encryption_requested_ = true;
        if (already_bonded) {
          ESP_LOGI(this->log_tag_.c_str(),
                   "No probe char — proactively re-encrypting bonded device");
          esp_ble_set_encryption(this->parent_->get_remote_bda(),
                                  ESP_BLE_SEC_ENCRYPT);
        } else {
          ESP_LOGI(this->log_tag_.c_str(),
                   "No probe char and no bond — initiating LE SC pairing");
          esp_ble_set_encryption(this->parent_->get_remote_bda(),
                                  ESP_BLE_SEC_ENCRYPT_MITM);
        }
      }
      // "ready" + resubscribe are deferred to start_post_auth_setup_(),
      // called from probe-success in READ_CHAR_EVT or from
      // AUTH_CMPL_EVT.success on the fallback path.
      break;
    }

    case ESP_GATTC_READ_CHAR_EVT: {
      // Handle device name read (from GAP 0x2A00)
      if (this->name_handle_ != 0 && param->read.handle == this->name_handle_) {
        if (param->read.status == ESP_GATT_OK && param->read.value_len > 0) {
          this->remote_name_ = std::string(
              reinterpret_cast<const char *>(param->read.value),
              param->read.value_len);
          ESP_LOGI(this->log_tag_.c_str(), "Device name: %s",
                   this->remote_name_.c_str());
        } else {
          ESP_LOGD(this->log_tag_.c_str(),
                   "Device name read failed, status=%d", param->read.status);
        }
        this->name_handle_ = 0;
        break;
      }

      // Probe read dispatch (lazy-encrypt path)
      if (this->probe_handle_ != 0 &&
          param->read.handle == this->probe_handle_) {
        if (param->read.status == ESP_GATT_OK) {
          ESP_LOGI(this->log_tag_.c_str(),
                   "Probe OK — connection encrypted, ready");
          this->probe_handle_ = 0;
          this->retry_read_after_auth_ = false;
          this->start_post_auth_setup_();
        } else if (param->read.status == ESP_GATT_INSUF_AUTHENTICATION ||
                   param->read.status == ESP_GATT_INSUF_ENCRYPTION) {
          if (!this->encryption_requested_) {
            bool already_bonded = this->is_already_bonded_();
            ESP_LOGI(this->log_tag_.c_str(),
                     "Probe needs encryption (status=%d, %s) — initiating",
                     param->read.status,
                     already_bonded ? "bonded" : "fresh pair");
            this->encryption_requested_ = true;
            this->retry_read_after_auth_ = true;
            esp_ble_set_encryption(this->parent_->get_remote_bda(),
                already_bonded ? ESP_BLE_SEC_ENCRYPT
                               : ESP_BLE_SEC_ENCRYPT_MITM);
            // probe_handle_ stays set — retry happens in AUTH_CMPL.success
          } else {
            ESP_LOGW(this->log_tag_.c_str(),
                     "Probe still failing after encrypt (status=%d) — "
                     "firing ready as fallback",
                     param->read.status);
            this->probe_handle_ = 0;
            this->retry_read_after_auth_ = false;
            this->start_post_auth_setup_();
          }
        } else {
          ESP_LOGD(this->log_tag_.c_str(),
                   "Probe read returned status=%d — firing ready anyway",
                   param->read.status);
          this->probe_handle_ = 0;
          this->retry_read_after_auth_ = false;
          this->start_post_auth_setup_();
        }
        break;
      }

      if (param->read.status != ESP_GATT_OK) {
        // Insufficient Authentication / Encryption on a HA-driven read:
        // initiate encryption and let HA retry the read. Avoids the
        // proactive set_encryption() race with BTM rehydrate.
        if ((param->read.status == ESP_GATT_INSUF_AUTHENTICATION ||
             param->read.status == ESP_GATT_INSUF_ENCRYPTION) &&
            !this->encryption_requested_) {
          bool already_bonded = this->is_already_bonded_();
          ESP_LOGI(this->log_tag_.c_str(),
                   "Read requires encryption (status=%d) — initiating (%s)",
                   param->read.status,
                   already_bonded ? "bonded" : "fresh pair");
          this->encryption_requested_ = true;
          esp_ble_set_encryption(this->parent_->get_remote_bda(),
              already_bonded ? ESP_BLE_SEC_ENCRYPT
                             : ESP_BLE_SEC_ENCRYPT_MITM);
        }
        ESP_LOGW(this->log_tag_.c_str(), "Read failed for %s, status=%d",
                 this->pending_char_uuid_.c_str(), param->read.status);
        this->emit_(EVENT_DATA,
                    {
                        {"uuid", this->pending_char_uuid_},
                        {"payload", ""},
                        {"error", "read_failed"},
                        {"mac", this->get_remote_mac()},
                    });
        this->pending_handle_ = 0;
        break;
      }

      if (param->read.handle == this->pending_handle_) {
        std::string hex_payload =
            format_hex(param->read.value, param->read.value_len);

        ESP_LOGI(this->log_tag_.c_str(), "Read %s: %s (%d bytes)",
                 this->pending_char_uuid_.c_str(), hex_payload.c_str(),
                 param->read.value_len);

        this->emit_(EVENT_DATA,
                    {
                        {"uuid", this->pending_char_uuid_},
                        {"payload", hex_payload},
                        {"mac", this->get_remote_mac()},
                    });

        this->pending_handle_ = 0;
      }
      break;
    }

    case ESP_GATTC_WRITE_CHAR_EVT: {
      if (param->write.status == ESP_GATT_OK) {
        ESP_LOGI(this->log_tag_.c_str(), "Write confirmed for handle 0x%04X",
                 param->write.handle);
      } else {
        ESP_LOGW(this->log_tag_.c_str(),
                 "Write FAILED for handle 0x%04X, status=%d",
                 param->write.handle, param->write.status);
      }
      break;
    }

    case ESP_GATTC_REG_FOR_NOTIFY_EVT: {
      if (param->reg_for_notify.status == ESP_GATT_OK) {
        ESP_LOGI(this->log_tag_.c_str(),
                 "Notify registered for handle 0x%04X",
                 param->reg_for_notify.handle);

        // Write CCCD with the right bit: 0x0001 notify, 0x0002 indicate, 0x0003 both.
        auto it = this->cccd_map_.find(param->reg_for_notify.handle);
        if (it != this->cccd_map_.end()) {
          uint16_t cccd_val = 0x0001;  // default: notify
          auto props_it = this->char_props_map_.find(param->reg_for_notify.handle);
          if (props_it != this->char_props_map_.end()) {
            bool has_notify = props_it->second & ESP_GATT_CHAR_PROP_BIT_NOTIFY;
            bool has_indicate =
                props_it->second & ESP_GATT_CHAR_PROP_BIT_INDICATE;
            if (has_indicate && has_notify)
              cccd_val = 0x0003;
            else if (has_indicate)
              cccd_val = 0x0002;
          }
          esp_ble_gattc_write_char_descr(
              gattc_if, this->parent_->get_conn_id(), it->second,
              sizeof(cccd_val), (uint8_t *) &cccd_val,
              ESP_GATT_WRITE_TYPE_RSP, ESP_GATT_AUTH_REQ_NO_MITM);
          ESP_LOGI(this->log_tag_.c_str(),
                   "CCCD written for handle 0x%04X (descr 0x%04X, value 0x%04X)",
                   param->reg_for_notify.handle, it->second, cccd_val);
        }
      } else {
        ESP_LOGW(this->log_tag_.c_str(), "Notify registration failed, status=%d",
                 param->reg_for_notify.status);
      }
      break;
    }

    case ESP_GATTC_NOTIFY_EVT: {
      auto it = this->notify_map_.find(param->notify.handle);
      if (it == this->notify_map_.end())
        break;

      // Throttle: max 1 event per NOTIFY_THROTTLE_MS per characteristic
      uint32_t now = millis();
      auto last_it = this->last_notify_ms_.find(param->notify.handle);
      if (last_it != this->last_notify_ms_.end() &&
          (now - last_it->second) < this->notify_throttle_ms_) {
        break;
      }
      this->last_notify_ms_[param->notify.handle] = now;

      std::string hex_payload =
          format_hex(param->notify.value, param->notify.value_len);

      ESP_LOGD(this->log_tag_.c_str(), "%s %s: %s (%d bytes)",
               param->notify.is_notify ? "Notify" : "Indicate",
               it->second.c_str(), hex_payload.c_str(),
               param->notify.value_len);

      this->emit_(EVENT_DATA,
                  {
                      {"uuid", it->second},
                      {"payload", hex_payload},
                      {"mac", this->get_remote_mac()},
                  });
      break;
    }

    default:
      break;
  }
}

void ShaverCoordinator::on_gap_event(esp_gap_ble_cb_event_t event,
                                      esp_ble_gap_cb_param_t *param) {
  if (this->parent_ == nullptr)
    return;

  switch (event) {
    case ESP_GAP_BLE_NC_REQ_EVT:
      ESP_LOGI(this->log_tag_.c_str(),
               "Numeric Comparison request — auto-confirming (passkey %06lu)",
               (unsigned long) param->ble_security.key_notif.passkey);
      esp_ble_confirm_reply(param->ble_security.key_notif.bd_addr, true);
      break;

    case ESP_GAP_BLE_AUTH_CMPL_EVT: {
      // Only handle events for our device (GAP events fire for all connections)
      if (memcmp(param->ble_security.auth_cmpl.bd_addr,
                 this->parent_->get_remote_bda(), 6) != 0) {
        break;
      }

      if (param->ble_security.auth_cmpl.success) {
        this->auth_completed_ = true;
        this->rapid_disconnect_count_ = 0;
        this->auth_fail_count_ = 0;
        // Mode B: emit pair_complete on the AUTH_CMPL that ends the
        // pair-mode window. The Worker has already persisted NVS +
        // updated identity_source by the time we get here (it runs
        // pre-forward inside its own gap_event_handler), so the values
        // we report below are post-persist.
        if (this->pair_mode_active_) {
          ESP_LOGI(this->log_tag_.c_str(),
                   "Pair complete — disarming pair-mode (identity_source=%s)",
                   this->identity_source_.c_str());
          this->pair_mode_active_ = false;
          this->pair_mode_until_ms_ = 0;
          this->target_mac_.clear();
          this->emit_(EVENT_STATUS,
                      {
                          {"status", "pair_complete"},
                          {"version", PHILIPS_SHAVER_VERSION},
                          {"mac", this->get_remote_mac()},
                          {"identity_address", this->identity_address_},
                          {"identity_source", this->identity_source_},
                          {"bonding", "bonded"},
                      });
        }
        if (this->retry_read_after_auth_ && this->probe_handle_ != 0) {
          // Path A: probe returned INSUF_AUTH, our explicit set_encryption()
          // triggered SMP, encryption is now up — retry the probe.
          this->retry_read_after_auth_ = false;
          ESP_LOGI(this->log_tag_.c_str(),
                   "Auth complete — retrying probe read on handle 0x%04X",
                   this->probe_handle_);
          auto status = esp_ble_gattc_read_char(
              this->parent_->get_gattc_if(),
              this->parent_->get_conn_id(),
              this->probe_handle_, ESP_GATT_AUTH_REQ_NONE);
          if (status != ESP_OK) {
            ESP_LOGW(this->log_tag_.c_str(),
                     "Probe retry failed (status=%d) — firing ready anyway",
                     status);
            this->probe_handle_ = 0;
            this->start_post_auth_setup_();
          }
          // Success path: READ_CHAR_EVT fires ready on probe-OK
        } else if (this->services_discovered_ && this->probe_handle_ == 0) {
          // Path B: SEARCH_CMPL already done and no probe pending — either
          // probe-char missing (fallback proactive encrypt) or probe already
          // resolved. Safe to fire ready (start_post_auth_setup_ is idempotent).
          this->start_post_auth_setup_();
        } else {
          // Path C: AUTH_CMPL fired before SEARCH_CMPL (Bluedroid auto-encrypt
          // common case) OR probe is in flight without retry flag. Don't fire
          // ready prematurely — the probe issued in/from SEARCH_CMPL will
          // emit ready when it resolves.
          ESP_LOGD(this->log_tag_.c_str(),
                   "Auth complete — deferring ready to probe-OK");
        }
      } else {
        this->auth_fail_count_++;
        ESP_LOGW(this->log_tag_.c_str(),
                 "Auth failed (reason=%d, attempt %d/%d) — removing bond",
                 param->ble_security.auth_cmpl.fail_reason,
                 this->auth_fail_count_, MAX_AUTH_FAILURES);
        esp_ble_remove_bond_device(param->ble_security.auth_cmpl.bd_addr);

        if (this->auth_fail_count_ >= MAX_AUTH_FAILURES &&
            this->backoff_until_ms_ == 0) {
          uint32_t backoff_s = AUTH_BACKOFF_MS / 1000;
          ESP_LOGE(this->log_tag_.c_str(),
                   "%d consecutive auth failures — disabling BLE for %us. "
                   "Clear Bluetooth pairing on the shaver.",
                   this->auth_fail_count_, backoff_s);
          this->backoff_until_ms_ = millis() + AUTH_BACKOFF_MS;
          if (this->set_enabled_cb_)
            this->set_enabled_cb_(false);

          char fail_str[4], backoff_str[8];
          snprintf(fail_str, sizeof(fail_str), "%d", this->auth_fail_count_);
          snprintf(backoff_str, sizeof(backoff_str), "%u", backoff_s);
          this->emit_(EVENT_STATUS,
                      {
                          {"status", "auth_failed"},
                          {"mac", this->get_remote_mac()},
                          {"fail_count", std::string(fail_str)},
                          {"backoff_s", std::string(backoff_str)},
                      });
        }
      }
      break;
    }

    default:
      break;
  }
}

void ShaverCoordinator::read_char(const std::string &service_uuid,
                                   const std::string &characteristic_uuid) {
  if (!this->connected_ || this->parent_ == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(), "Cannot read: not connected");
    this->emit_(EVENT_DATA,
                {
                    {"uuid", characteristic_uuid},
                    {"payload", ""},
                    {"error", "not_connected"},
                    {"mac", this->get_remote_mac()},
                });
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent_->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(),
             "Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    this->emit_(EVENT_DATA,
                {
                    {"uuid", characteristic_uuid},
                    {"payload", ""},
                    {"error", "not_found"},
                    {"mac", this->get_remote_mac()},
                });
    return;
  }

  this->pending_handle_ = chr->handle;
  this->pending_char_uuid_ = characteristic_uuid;

  ESP_LOGI(this->log_tag_.c_str(), "Reading %s (handle 0x%04X)...",
           characteristic_uuid.c_str(), chr->handle);

  auto status = esp_ble_gattc_read_char(
      this->parent_->get_gattc_if(), this->parent_->get_conn_id(),
      chr->handle, ESP_GATT_AUTH_REQ_NO_MITM);

  if (status != ESP_OK) {
    ESP_LOGW(this->log_tag_.c_str(), "Read request failed: %d", status);
    this->pending_handle_ = 0;
    char err_str[16];
    snprintf(err_str, sizeof(err_str), "gatt_err_%d", status);
    this->emit_(EVENT_DATA,
                {
                    {"uuid", characteristic_uuid},
                    {"payload", ""},
                    {"error", std::string(err_str)},
                    {"mac", this->get_remote_mac()},
                });
  }
}

void ShaverCoordinator::subscribe(const std::string &service_uuid,
                                   const std::string &characteristic_uuid) {
  if (!this->connected_ || this->parent_ == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(), "Cannot subscribe: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent_->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(),
             "Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    return;
  }

  // Skip chars that advertise neither NOTIFY nor INDICATE — CCCD write
  // would fail silently and no data would ever arrive.
  if (!(chr->properties & (ESP_GATT_CHAR_PROP_BIT_NOTIFY |
                            ESP_GATT_CHAR_PROP_BIT_INDICATE))) {
    ESP_LOGW(this->log_tag_.c_str(),
             "Characteristic %s has no NOTIFY/INDICATE property (props=0x%02X), skipping",
             characteristic_uuid.c_str(), chr->properties);
    return;
  }

  // Check if already subscribed (e.g., restored after reconnect)
  if (this->notify_map_.count(chr->handle)) {
    ESP_LOGD(this->log_tag_.c_str(),
             "Already subscribed to %s (handle 0x%04X), skipping",
             characteristic_uuid.c_str(), chr->handle);
    return;
  }

  uint16_t cccd_handle = this->find_cccd_handle_(chr->handle);
  this->cccd_map_[chr->handle] = cccd_handle;
  this->char_props_map_[chr->handle] = chr->properties;

  this->notify_map_[chr->handle] = characteristic_uuid;

  // Track for auto-resubscribe after reconnect
  auto pair = std::make_pair(service_uuid, characteristic_uuid);
  bool already_tracked = false;
  for (const auto &entry : this->desired_subscriptions_) {
    if (entry.first == service_uuid && entry.second == characteristic_uuid) {
      already_tracked = true;
      break;
    }
  }
  if (!already_tracked) {
    this->desired_subscriptions_.push_back(pair);
  }

  ESP_LOGI(this->log_tag_.c_str(),
           "Subscribing to %s (handle 0x%04X, cccd 0x%04X)...",
           characteristic_uuid.c_str(), chr->handle, cccd_handle);

  auto status = esp_ble_gattc_register_for_notify(
      this->parent_->get_gattc_if(), this->parent_->get_remote_bda(),
      chr->handle);

  if (status != ESP_OK) {
    ESP_LOGW(this->log_tag_.c_str(), "Subscribe failed: %d", status);
    this->notify_map_.erase(chr->handle);
    this->cccd_map_.erase(chr->handle);
    this->char_props_map_.erase(chr->handle);
  }
}

void ShaverCoordinator::unsubscribe(const std::string &service_uuid,
                                     const std::string &characteristic_uuid) {
  if (!this->connected_ || this->parent_ == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(), "Cannot unsubscribe: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent_->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(),
             "Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    return;
  }

  // Remove from desired subscriptions
  for (auto it = this->desired_subscriptions_.begin();
       it != this->desired_subscriptions_.end(); ++it) {
    if (it->first == service_uuid && it->second == characteristic_uuid) {
      this->desired_subscriptions_.erase(it);
      break;
    }
  }

  ESP_LOGI(this->log_tag_.c_str(), "Unsubscribing from %s (handle 0x%04X)...",
           characteristic_uuid.c_str(), chr->handle);

  esp_ble_gattc_unregister_for_notify(this->parent_->get_gattc_if(),
                                       this->parent_->get_remote_bda(),
                                       chr->handle);

  this->notify_map_.erase(chr->handle);
}

void ShaverCoordinator::write_char(const std::string &service_uuid,
                                    const std::string &characteristic_uuid,
                                    const std::string &hex_data) {
  if (!this->connected_ || this->parent_ == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(), "Cannot write: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent_->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(),
             "Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    return;
  }

  // Parse hex string to bytes
  std::vector<uint8_t> bytes;
  size_t count = hex_data.length() / 2;
  if (count == 0 || !parse_hex(hex_data, bytes, count)) {
    ESP_LOGW(this->log_tag_.c_str(), "Invalid hex data: %s", hex_data.c_str());
    return;
  }

  ESP_LOGI(this->log_tag_.c_str(),
           "Writing %s (handle 0x%04X): %s (%d bytes)",
           characteristic_uuid.c_str(), chr->handle, hex_data.c_str(),
           bytes.size());

  auto status = esp_ble_gattc_write_char(
      this->parent_->get_gattc_if(), this->parent_->get_conn_id(),
      chr->handle, bytes.size(), bytes.data(),
      ESP_GATT_WRITE_TYPE_RSP, ESP_GATT_AUTH_REQ_NO_MITM);

  if (status != ESP_OK) {
    ESP_LOGW(this->log_tag_.c_str(), "Write request failed: %d", status);
  }
}

void ShaverCoordinator::set_throttle(uint32_t ms) {
  this->notify_throttle_ms_ = ms;
  ESP_LOGI(this->log_tag_.c_str(), "Notification throttle set to %u ms", ms);
}

uint16_t ShaverCoordinator::find_cccd_handle_(uint16_t char_handle) {
  // Query the ESP-IDF GATT table directly — synchronous RAM lookup,
  // bypasses ESPHome's potentially empty descriptor cache.
  uint16_t count = 1;
  esp_gattc_descr_elem_t result;
  memset(&result, 0, sizeof(result));
  esp_bt_uuid_t cccd_uuid;
  cccd_uuid.len = ESP_UUID_LEN_16;
  cccd_uuid.uuid.uuid16 = 0x2902;

  auto status = esp_ble_gattc_get_descr_by_char_handle(
      this->parent_->get_gattc_if(), this->parent_->get_conn_id(),
      char_handle, cccd_uuid, &result, &count);

  if (status == ESP_GATT_OK && count > 0) {
    ESP_LOGD(this->log_tag_.c_str(),
             "CCCD found via ESP-IDF API: handle 0x%04X for char 0x%04X",
             result.handle, char_handle);
    return result.handle;
  }

  // Fallback: handle + 1 (standard BLE layout)
  uint16_t fallback = char_handle + 1;
  ESP_LOGW(this->log_tag_.c_str(),
           "CCCD not found via API for char 0x%04X, using fallback 0x%04X",
           char_handle, fallback);
  return fallback;
}

void ShaverCoordinator::resubscribe_all_() {
  for (const auto &entry : this->desired_subscriptions_) {
    const auto &svc_uuid_str = entry.first;
    const auto &chr_uuid_str = entry.second;

    auto svc = parse_uuid(svc_uuid_str);
    auto chr_uuid = parse_uuid(chr_uuid_str);

    auto *chr = this->parent_->get_characteristic(svc, chr_uuid);
    if (chr == nullptr) {
      ESP_LOGW(this->log_tag_.c_str(),
               "Resubscribe: characteristic %s not found, skipping",
               chr_uuid_str.c_str());
      continue;
    }

    uint16_t cccd_handle = this->find_cccd_handle_(chr->handle);
    this->cccd_map_[chr->handle] = cccd_handle;
    this->char_props_map_[chr->handle] = chr->properties;
    this->notify_map_[chr->handle] = chr_uuid_str;

    auto status = esp_ble_gattc_register_for_notify(
        this->parent_->get_gattc_if(), this->parent_->get_remote_bda(),
        chr->handle);

    if (status == ESP_OK) {
      ESP_LOGI(this->log_tag_.c_str(),
               "Resubscribe: %s (handle 0x%04X, cccd 0x%04X)",
               chr_uuid_str.c_str(), chr->handle, cccd_handle);
    } else {
      ESP_LOGW(this->log_tag_.c_str(), "Resubscribe failed for %s: %d",
               chr_uuid_str.c_str(), status);
      this->notify_map_.erase(chr->handle);
      this->cccd_map_.erase(chr->handle);
    }
  }
}

bool ShaverCoordinator::is_already_bonded_() {
  if (this->parent_ == nullptr)
    return false;
  int bond_num = esp_ble_get_bond_device_num();
  if (bond_num <= 0)
    return false;
  auto *bond_list = new esp_ble_bond_dev_t[bond_num];
  esp_ble_get_bond_device_list(&bond_num, bond_list);
  bool found = false;
  for (int i = 0; i < bond_num; i++) {
    if (memcmp(bond_list[i].bd_addr, this->parent_->get_remote_bda(), 6) ==
        0) {
      found = true;
      break;
    }
  }
  delete[] bond_list;
  return found;
}

void ShaverCoordinator::fire_ready_event_() {
  this->emit_(EVENT_STATUS,
              {
                  {"status", "ready"},
                  {"mac", this->get_remote_mac()},
                  {"version", PHILIPS_SHAVER_VERSION},
              });
}

void ShaverCoordinator::start_post_auth_setup_() {
  if (this->ready_fired_) {
    ESP_LOGD(this->log_tag_.c_str(),
             "start_post_auth_setup_: ready already fired this connection");
    return;
  }
  this->ready_fired_ = true;
  this->fire_ready_event_();
  if (!this->desired_subscriptions_.empty()) {
    ESP_LOGI(this->log_tag_.c_str(),
             "Restoring %d notification subscription(s)...",
             this->desired_subscriptions_.size());
    this->resubscribe_all_();
  }
}

// ── Mode B: pair-mode / scan / unpair / pair-mac ─────────────────────────────

void ShaverCoordinator::set_pair_mode(bool enable, uint32_t timeout_s) {
  if (this->mode_ != MODE_STANDALONE) {
    ESP_LOGW(this->log_tag_.c_str(),
             "ble_pair_mode is Mode B only — ignoring (mode=%s)",
             this->mode_.c_str());
    return;
  }
  if (!enable) {
    if (!this->pair_mode_active_)
      return;
    ESP_LOGI(this->log_tag_.c_str(), "Pair-mode disarmed by user");
    this->pair_mode_active_ = false;
    this->pair_mode_until_ms_ = 0;
    this->target_mac_.clear();
    if (this->set_enabled_cb_)
      this->set_enabled_cb_(false);
    return;
  }
  if (timeout_s == 0 || timeout_s > MAX_PAIR_MODE_TIMEOUT_S)
    timeout_s = 60;
  this->pair_mode_active_ = true;
  this->pair_mode_until_ms_ = millis() + timeout_s * 1000;
  ESP_LOGI(this->log_tag_.c_str(), "Pair-mode armed for %us%s", timeout_s,
           this->target_mac_.empty()
               ? ""
               : (" (target " + this->target_mac_ + ")").c_str());
  if (this->set_enabled_cb_)
    this->set_enabled_cb_(true);
  char timeout_str[8];
  snprintf(timeout_str, sizeof(timeout_str), "%u", timeout_s);
  std::map<std::string, std::string> data = {
      {"status", "pair_mode_armed"},
      {"version", PHILIPS_SHAVER_VERSION},
      {"timeout_s", std::string(timeout_str)},
  };
  if (!this->target_mac_.empty())
    data["target_mac"] = this->target_mac_;
  this->emit_(EVENT_STATUS, data);
}

void ShaverCoordinator::unpair() {
  if (this->mode_ != MODE_STANDALONE) {
    ESP_LOGW(this->log_tag_.c_str(),
             "ble_unpair is Mode B only — ignoring (mode=%s)",
             this->mode_.c_str());
    return;
  }
  // Best-effort bond removal for the current remote (if any). Workers'
  // unpair_cb_ also clears NVS-persisted identity.
  if (this->parent_ != nullptr) {
    auto *bda = this->parent_->get_remote_bda();
    bool any_set = false;
    for (int i = 0; i < 6; i++) {
      if (bda[i] != 0) {
        any_set = true;
        break;
      }
    }
    if (any_set) {
      esp_ble_remove_bond_device(const_cast<uint8_t *>(bda));
      ESP_LOGI(this->log_tag_.c_str(), "Bond removed");
    }
  }
  if (this->unpair_cb_)
    this->unpair_cb_();
  this->identity_source_ = IDENTITY_SOURCE_NONE;
  this->identity_address_.clear();
  this->unpair_drain_until_ms_ = millis() + UNPAIR_DRAIN_MS;
  if (this->set_enabled_cb_)
    this->set_enabled_cb_(false);
  ESP_LOGI(this->log_tag_.c_str(),
           "Unpair initiated — drain window %ums, awaiting `unpaired` emit",
           UNPAIR_DRAIN_MS);
}

void ShaverCoordinator::set_scan_mode(uint32_t timeout_s) {
  if (this->mode_ != MODE_STANDALONE) {
    ESP_LOGW(this->log_tag_.c_str(),
             "ble_scan is Mode B only — ignoring (mode=%s)",
             this->mode_.c_str());
    return;
  }
  if (timeout_s == 0 || timeout_s > MAX_SCAN_TIMEOUT_S)
    timeout_s = 30;
  this->scan_mode_active_ = true;
  this->scan_mode_until_ms_ = millis() + timeout_s * 1000;
  this->scan_results_seen_.clear();
  ESP_LOGI(this->log_tag_.c_str(), "Scan-mode armed for %us", timeout_s);
  if (this->set_enabled_cb_)
    this->set_enabled_cb_(true);
  char timeout_str[8];
  snprintf(timeout_str, sizeof(timeout_str), "%u", timeout_s);
  this->emit_(EVENT_STATUS,
              {
                  {"status", "scan_started"},
                  {"timeout_s", std::string(timeout_str)},
                  {"version", PHILIPS_SHAVER_VERSION},
              });
}

void ShaverCoordinator::set_pair_mac(const std::string &mac,
                                      uint32_t timeout_s) {
  if (this->mode_ != MODE_STANDALONE) {
    ESP_LOGW(this->log_tag_.c_str(),
             "ble_pair_mac is Mode B only — ignoring (mode=%s)",
             this->mode_.c_str());
    return;
  }
  if (mac.size() != 17) {
    ESP_LOGW(this->log_tag_.c_str(),
             "ble_pair_mac: invalid MAC '%s' (expected AA:BB:CC:DD:EE:FF)",
             mac.c_str());
    return;
  }
  std::string upper = mac;
  for (auto &c : upper)
    c = toupper(static_cast<unsigned char>(c));
  this->target_mac_ = upper;
  ESP_LOGI(this->log_tag_.c_str(), "Pair-mac armed: target=%s",
           this->target_mac_.c_str());
  this->set_pair_mode(true, timeout_s);
}

void ShaverCoordinator::emit_scan_result(const std::string &mac,
                                          const std::string &addr_type,
                                          const std::string &local_name,
                                          const std::string &mfr_data,
                                          int rssi,
                                          const std::string &service_uuid) {
  if (this->scan_results_seen_.count(mac))
    return;
  this->scan_results_seen_.insert(mac);
  char rssi_str[8];
  snprintf(rssi_str, sizeof(rssi_str), "%d", rssi);
  this->emit_(EVENT_STATUS,
              {
                  {"status", "scan_result"},
                  {"mac", mac},
                  {"addr_type", addr_type},
                  {"local_name", local_name},
                  {"mfr_data", mfr_data},
                  {"rssi", std::string(rssi_str)},
                  {"service_uuid", service_uuid},
              });
}

void ShaverCoordinator::list_services() {
  // Stub — Sonicare exposes this via `ble_list_services`; Shaver doesn't
  // need it for the current HA flow (HA reads everything via `ble_get_info`
  // and known service UUIDs). Leaving a no-op so the Bridge service
  // registration compiles; revisit if a use-case appears.
  ESP_LOGD(this->log_tag_.c_str(), "list_services: not implemented");
}

}  // namespace philips_shaver
}  // namespace esphome
