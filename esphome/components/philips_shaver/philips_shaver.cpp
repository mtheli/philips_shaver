#include "philips_shaver.h"
#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esp_gap_ble_api.h"
#include "esp_gattc_api.h"
#include "esp_system.h"

namespace espbt = esphome::esp32_ble_tracker;

namespace esphome {
namespace philips_shaver {

static const char *const TAG = "philips_shaver";

static espbt::ESPBTUUID parse_uuid(const std::string &uuid_str) {
  if (uuid_str.length() <= 8) {
    uint16_t uuid16 = std::stoul(uuid_str, nullptr, 16);
    return espbt::ESPBTUUID::from_uint16(uuid16);
  }
  return espbt::ESPBTUUID::from_raw(uuid_str);
}

void PhilipsShaver::apply_smp_params_() {
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

  esp_ble_gap_set_security_param(ESP_BLE_SM_AUTHEN_REQ_MODE, &auth_req, sizeof(auth_req));
  esp_ble_gap_set_security_param(ESP_BLE_SM_IOCAP_MODE, &io_cap, sizeof(io_cap));
  esp_ble_gap_set_security_param(ESP_BLE_SM_MAX_KEY_SIZE, &key_size, sizeof(key_size));
  esp_ble_gap_set_security_param(ESP_BLE_SM_SET_INIT_KEY, &init_key, sizeof(init_key));
  esp_ble_gap_set_security_param(ESP_BLE_SM_SET_RSP_KEY, &rsp_key, sizeof(rsp_key));
  ESP_LOGI(this->log_tag_.c_str(),"SMP security params applied (io_cap=DisplayYesNo, auth=0x2D)");
}

void PhilipsShaver::setup() {
  this->log_tag_ = this->bridge_id_.empty()
      ? "philips_shaver"
      : "philips_shaver." + this->bridge_id_;
  this->apply_smp_params_();

  this->register_service(&PhilipsShaver::on_read_characteristic,
                          this->svc_name_("ble_read_char"), {"service_uuid", "char_uuid"});
  this->register_service(&PhilipsShaver::on_subscribe,
                          this->svc_name_("ble_subscribe"), {"service_uuid", "char_uuid"});
  this->register_service(&PhilipsShaver::on_unsubscribe,
                          this->svc_name_("ble_unsubscribe"), {"service_uuid", "char_uuid"});
  this->register_service(&PhilipsShaver::on_write_characteristic,
                          this->svc_name_("ble_write_char"), {"service_uuid", "char_uuid", "data"});
  this->register_service(&PhilipsShaver::on_set_throttle,
                          this->svc_name_("ble_set_throttle"), {"throttle_ms"});
  this->register_service(&PhilipsShaver::on_get_info,
                          this->svc_name_("ble_get_info"), {});
  ESP_LOGI(this->log_tag_.c_str(),"Services registered (bridge_id: '%s')", this->bridge_id_.c_str());
}

void PhilipsShaver::loop() {
  uint32_t now = millis();

  // Re-enable BLE client after auth failure backoff expires
  if (this->backoff_until_ms_ != 0 && now >= this->backoff_until_ms_) {
    ESP_LOGI(this->log_tag_.c_str(),"Auth backoff expired — re-enabling BLE connection");
    this->backoff_until_ms_ = 0;
    this->auth_fail_count_ = 0;
    this->parent()->set_enabled(true);
  }

  if ((now - this->last_heartbeat_ms_) >= HEARTBEAT_INTERVAL_MS) {
    this->last_heartbeat_ms_ = now;
    char uptime_str[16];
    snprintf(uptime_str, sizeof(uptime_str), "%u", now / 1000);
    this->fire_homeassistant_event(
        "esphome.philips_shaver_ble_status",
        {
            {"status", "heartbeat"},
            {"ble_connected", this->connected_ ? "true" : "false"},
            {"mac", this->get_shaver_mac_()},
            {"version", PHILIPS_SHAVER_VERSION},
            {"uptime_s", std::string(uptime_str)},
        });

    // If BLE is connected and authenticated but no one has subscribed yet,
    // re-fire "ready" so HA can set up subscriptions.  After OTA reboot, BLE
    // connects before the HA API stream is up — the initial "ready" is lost.
    // This keeps signalling every heartbeat until HA subscribes
    // (notify_map_ becomes non-empty → self-terminating).
    if (this->connected_ && this->services_discovered_ && this->auth_completed_ &&
        this->notify_map_.empty()) {
      ESP_LOGI(this->log_tag_.c_str(),"BLE connected, no subscriptions — re-firing ready");
      this->fire_homeassistant_event(
          "esphome.philips_shaver_ble_status",
          {
              {"status", "ready"},
              {"mac", this->get_shaver_mac_()},
              {"version", PHILIPS_SHAVER_VERSION},
              {"uptime_s", std::string(uptime_str)},
          });
    }
  }
}

std::string PhilipsShaver::get_shaver_mac_() {
  char mac[18];
  auto *bda = this->parent()->get_remote_bda();
  snprintf(mac, sizeof(mac), "%02X:%02X:%02X:%02X:%02X:%02X",
           bda[0], bda[1], bda[2], bda[3], bda[4], bda[5]);
  return std::string(mac);
}

std::string PhilipsShaver::svc_name_(const std::string &action) {
  if (this->bridge_id_.empty())
    return action;
  return action + "_" + this->bridge_id_;
}

void PhilipsShaver::dump_config() {
  ESP_LOGCONFIG(this->log_tag_.c_str(),"Philips Shaver BLE Bridge v%s", PHILIPS_SHAVER_VERSION);
  if (!this->bridge_id_.empty())
    ESP_LOGCONFIG(this->log_tag_.c_str(),"  Bridge ID: %s", this->bridge_id_.c_str());
}

void PhilipsShaver::gattc_event_handler(esp_gattc_cb_event_t event,
                                         esp_gatt_if_t gattc_if,
                                         esp_ble_gattc_cb_param_t *param) {
  switch (event) {
    case ESP_GATTC_OPEN_EVT: {
      if (param->open.status == ESP_GATT_OK) {
        // Apply SMP params now, before service discovery and pairing.
        // Must happen here because BLEClientBase triggers on_connect (→ pair())
        // in SEARCH_CMPL_EVT before our node handler runs.
        this->apply_smp_params_();
        this->auth_completed_ = false;
        this->connect_time_ms_ = millis();
        ESP_LOGI(this->log_tag_.c_str(),"Connected to shaver (%s)", this->get_shaver_mac_().c_str());
        this->connected_ = true;
        if (this->connected_sensor_ != nullptr)
          this->connected_sensor_->publish_state(true);
        this->fire_homeassistant_event(
            "esphome.philips_shaver_ble_status",
            {
                {"status", "connected"},
                {"mac", this->get_shaver_mac_()},
            });
      } else {
        ESP_LOGW(this->log_tag_.c_str(),"Connection failed, status=%d", param->open.status);
      }
      break;
    }

    case ESP_GATTC_DISCONNECT_EVT: {
      // Detect stale bond: if we keep disconnecting quickly without auth,
      // the stored bond keys are likely invalid (e.g. after OTA or shaver BT reset).
      // Clear the bond after repeated failures so the next connect starts fresh pairing.
      uint32_t connect_duration_ms = millis() - this->connect_time_ms_;
      if (this->auth_completed_ ||
          connect_duration_ms > RAPID_DISCONNECT_THRESHOLD_MS) {
        this->rapid_disconnect_count_ = 0;
      } else {
        this->rapid_disconnect_count_++;
        ESP_LOGD(this->log_tag_.c_str(),"Rapid disconnect without auth after %ums (%d/%d), reason=0x%02X",
                 connect_duration_ms,
                 this->rapid_disconnect_count_, MAX_RAPID_DISCONNECTS,
                 param->disconnect.reason);
        if (this->rapid_disconnect_count_ >= MAX_RAPID_DISCONNECTS) {
          ESP_LOGW(this->log_tag_.c_str(),"Detected %d rapid disconnects without auth — "
                   "clearing stale bond for fresh pairing",
                   this->rapid_disconnect_count_);
          esp_ble_remove_bond_device(this->parent()->get_remote_bda());
          this->rapid_disconnect_count_ = 0;
        }
      }

      ESP_LOGW(this->log_tag_.c_str(),"Disconnected from shaver (reason=0x%02X). "
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
      if (this->connected_sensor_ != nullptr)
        this->connected_sensor_->publish_state(false);
      this->pending_handle_ = 0;
      this->name_handle_ = 0;
      // Clear handle-based maps (handles are invalid after disconnect)
      // but keep desired_subscriptions_ for auto-resubscribe
      this->notify_map_.clear();
      this->cccd_map_.clear();
      this->char_props_map_.clear();
      this->last_notify_ms_.clear();
      char reason_str[5];
      snprintf(reason_str, sizeof(reason_str), "0x%02X", param->disconnect.reason);
      this->fire_homeassistant_event(
          "esphome.philips_shaver_ble_status",
          {
              {"status", "disconnected"},
              {"mac", this->get_shaver_mac_()},
              {"reason", reason_str},
          });
      break;
    }

    case ESP_GATTC_SEARCH_CMPL_EVT: {
      ESP_LOGI(this->log_tag_.c_str(),"Service discovery complete");
      this->services_discovered_ = true;

      // Read GAP Device Name (0x2A00) for display in HA config flow
      if (this->remote_name_.empty()) {
        auto gap_svc = espbt::ESPBTUUID::from_uint16(0x1800);
        auto name_chr = espbt::ESPBTUUID::from_uint16(0x2A00);
        auto *chr = this->parent()->get_characteristic(gap_svc, name_chr);
        if (chr) {
          this->name_handle_ = chr->handle;
          auto status = esp_ble_gattc_read_char(
              this->parent()->get_gattc_if(),
              this->parent()->get_conn_id(),
              chr->handle, ESP_GATT_AUTH_REQ_NONE);
          if (status != ESP_GATT_OK) {
            ESP_LOGD(this->log_tag_.c_str(),"Failed to initiate device name read: %d", status);
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
      auto *chr = this->parent()->get_characteristic(philips_svc, probe_chr);
      if (chr) {
        this->probe_handle_ = chr->handle;
        auto status = esp_ble_gattc_read_char(
            this->parent()->get_gattc_if(),
            this->parent()->get_conn_id(),
            chr->handle, ESP_GATT_AUTH_REQ_NONE);
        if (status != ESP_GATT_OK) {
          ESP_LOGD(this->log_tag_.c_str(),"Probe read request failed, status=%d", status);
          this->probe_handle_ = 0;
        } else {
          ESP_LOGD(this->log_tag_.c_str(),"Probe read issued for handle 0x%04X — waiting on result",
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
          ESP_LOGI(this->log_tag_.c_str(),"No probe char — proactively re-encrypting bonded device");
          esp_ble_set_encryption(this->parent()->get_remote_bda(),
                                  ESP_BLE_SEC_ENCRYPT);
        } else {
          ESP_LOGI(this->log_tag_.c_str(),"No probe char and no bond — initiating LE SC pairing");
          esp_ble_set_encryption(this->parent()->get_remote_bda(),
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
          ESP_LOGI(this->log_tag_.c_str(),"Device name: %s", this->remote_name_.c_str());
        } else {
          ESP_LOGD(this->log_tag_.c_str(),"Device name read failed, status=%d", param->read.status);
        }
        this->name_handle_ = 0;
        break;
      }

      // Probe read dispatch (lazy-encrypt path)
      if (this->probe_handle_ != 0 && param->read.handle == this->probe_handle_) {
        if (param->read.status == ESP_GATT_OK) {
          ESP_LOGI(this->log_tag_.c_str(),"Probe OK — connection encrypted, ready");
          this->probe_handle_ = 0;
          this->retry_read_after_auth_ = false;
          this->start_post_auth_setup_();
        } else if (param->read.status == ESP_GATT_INSUF_AUTHENTICATION ||
                   param->read.status == ESP_GATT_INSUF_ENCRYPTION) {
          if (!this->encryption_requested_) {
            bool already_bonded = this->is_already_bonded_();
            ESP_LOGI(this->log_tag_.c_str(),"Probe needs encryption (status=%d, %s) — initiating",
                     param->read.status,
                     already_bonded ? "bonded" : "fresh pair");
            this->encryption_requested_ = true;
            this->retry_read_after_auth_ = true;
            esp_ble_set_encryption(this->parent()->get_remote_bda(),
                already_bonded ? ESP_BLE_SEC_ENCRYPT
                               : ESP_BLE_SEC_ENCRYPT_MITM);
            // probe_handle_ stays set — retry happens in AUTH_CMPL.success
          } else {
            ESP_LOGW(this->log_tag_.c_str(),"Probe still failing after encrypt (status=%d) — "
                     "firing ready as fallback",
                     param->read.status);
            this->probe_handle_ = 0;
            this->retry_read_after_auth_ = false;
            this->start_post_auth_setup_();
          }
        } else {
          ESP_LOGD(this->log_tag_.c_str(),"Probe read returned status=%d — firing ready anyway",
                   param->read.status);
          this->probe_handle_ = 0;
          this->retry_read_after_auth_ = false;
          this->start_post_auth_setup_();
        }
        break;
      }

      if (param->read.status != ESP_GATT_OK) {
        // Insufficient Authentication / Encryption on a HA-driven read:
        // initiate encryption and let HA retry the read.  Avoids the
        // proactive set_encryption() race with BTM rehydrate.
        if ((param->read.status == ESP_GATT_INSUF_AUTHENTICATION ||
             param->read.status == ESP_GATT_INSUF_ENCRYPTION) &&
            !this->encryption_requested_) {
          bool already_bonded = this->is_already_bonded_();
          ESP_LOGI(this->log_tag_.c_str(),"Read requires encryption (status=%d) — initiating (%s)",
                   param->read.status,
                   already_bonded ? "bonded" : "fresh pair");
          this->encryption_requested_ = true;
          esp_ble_set_encryption(this->parent()->get_remote_bda(),
              already_bonded ? ESP_BLE_SEC_ENCRYPT
                             : ESP_BLE_SEC_ENCRYPT_MITM);
        }
        ESP_LOGW(this->log_tag_.c_str(),"Read failed for %s, status=%d",
                 this->pending_char_uuid_.c_str(), param->read.status);
        this->fire_homeassistant_event(
            "esphome.philips_shaver_ble_data",
            {
                {"uuid", this->pending_char_uuid_},
                {"payload", ""},
                {"error", "read_failed"},
                {"mac", this->get_shaver_mac_()},
            });
        this->pending_handle_ = 0;
        break;
      }

      if (param->read.handle == this->pending_handle_) {
        std::string hex_payload =
            format_hex(param->read.value, param->read.value_len);

        ESP_LOGI(this->log_tag_.c_str(),"Read %s: %s (%d bytes)",
                 this->pending_char_uuid_.c_str(),
                 hex_payload.c_str(), param->read.value_len);

        this->fire_homeassistant_event(
            "esphome.philips_shaver_ble_data",
            {
                {"uuid", this->pending_char_uuid_},
                {"payload", hex_payload},
                {"mac", this->get_shaver_mac_()},
            });

        this->pending_handle_ = 0;
      }
      break;
    }

    case ESP_GATTC_WRITE_CHAR_EVT: {
      if (param->write.status == ESP_GATT_OK) {
        ESP_LOGI(this->log_tag_.c_str(),"Write confirmed for handle 0x%04X", param->write.handle);
      } else {
        ESP_LOGW(this->log_tag_.c_str(),"Write FAILED for handle 0x%04X, status=%d",
                 param->write.handle, param->write.status);
      }
      break;
    }

    case ESP_GATTC_REG_FOR_NOTIFY_EVT: {
      if (param->reg_for_notify.status == ESP_GATT_OK) {
        ESP_LOGI(this->log_tag_.c_str(),"Notify registered for handle 0x%04X",
                 param->reg_for_notify.handle);

        // Write CCCD with the right bit: 0x0001 notify, 0x0002 indicate, 0x0003 both.
        auto it = this->cccd_map_.find(param->reg_for_notify.handle);
        if (it != this->cccd_map_.end()) {
          uint16_t cccd_val = 0x0001;  // default: notify
          auto props_it = this->char_props_map_.find(param->reg_for_notify.handle);
          if (props_it != this->char_props_map_.end()) {
            bool has_notify = props_it->second & ESP_GATT_CHAR_PROP_BIT_NOTIFY;
            bool has_indicate = props_it->second & ESP_GATT_CHAR_PROP_BIT_INDICATE;
            if (has_indicate && has_notify)
              cccd_val = 0x0003;
            else if (has_indicate)
              cccd_val = 0x0002;
          }
          esp_ble_gattc_write_char_descr(
              gattc_if,
              this->parent()->get_conn_id(),
              it->second,
              sizeof(cccd_val),
              (uint8_t *) &cccd_val,
              ESP_GATT_WRITE_TYPE_RSP,
              ESP_GATT_AUTH_REQ_NO_MITM);
          ESP_LOGI(this->log_tag_.c_str(),"CCCD written for handle 0x%04X (descr 0x%04X, value 0x%04X)",
                   param->reg_for_notify.handle, it->second, cccd_val);
        }
      } else {
        ESP_LOGW(this->log_tag_.c_str(),"Notify registration failed, status=%d",
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

      ESP_LOGD(this->log_tag_.c_str(),"%s %s: %s (%d bytes)",
               param->notify.is_notify ? "Notify" : "Indicate",
               it->second.c_str(),
               hex_payload.c_str(), param->notify.value_len);

      this->fire_homeassistant_event(
          "esphome.philips_shaver_ble_data",
          {
              {"uuid", it->second},
              {"payload", hex_payload},
              {"mac", this->get_shaver_mac_()},
          });
      break;
    }

    default:
      break;
  }
}

void PhilipsShaver::on_read_characteristic(std::string service_uuid,
                                            std::string characteristic_uuid) {
  if (!this->connected_) {
    ESP_LOGW(this->log_tag_.c_str(),"Cannot read: not connected");
    this->fire_homeassistant_event(
        "esphome.philips_shaver_ble_data",
        {
            {"uuid", characteristic_uuid},
            {"payload", ""},
            {"error", "not_connected"},
            {"mac", this->get_shaver_mac_()},
        });
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent()->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(),"Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    this->fire_homeassistant_event(
        "esphome.philips_shaver_ble_data",
        {
            {"uuid", characteristic_uuid},
            {"payload", ""},
            {"error", "not_found"},
            {"mac", this->get_shaver_mac_()},
        });
    return;
  }

  this->pending_handle_ = chr->handle;
  this->pending_char_uuid_ = characteristic_uuid;

  ESP_LOGI(this->log_tag_.c_str(),"Reading %s (handle 0x%04X)...",
           characteristic_uuid.c_str(), chr->handle);

  auto status = esp_ble_gattc_read_char(
      this->parent()->get_gattc_if(),
      this->parent()->get_conn_id(),
      chr->handle,
      ESP_GATT_AUTH_REQ_NO_MITM);

  if (status != ESP_OK) {
    ESP_LOGW(this->log_tag_.c_str(),"Read request failed: %d", status);
    this->pending_handle_ = 0;
    char err_str[16];
    snprintf(err_str, sizeof(err_str), "gatt_err_%d", status);
    this->fire_homeassistant_event(
        "esphome.philips_shaver_ble_data",
        {
            {"uuid", characteristic_uuid},
            {"payload", ""},
            {"error", std::string(err_str)},
            {"mac", this->get_shaver_mac_()},
        });
  }
}

void PhilipsShaver::on_subscribe(std::string service_uuid,
                                  std::string characteristic_uuid) {
  if (!this->connected_) {
    ESP_LOGW(this->log_tag_.c_str(),"Cannot subscribe: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent()->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(),"Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    return;
  }

  // Skip chars that advertise neither NOTIFY nor INDICATE — CCCD write
  // would fail silently and no data would ever arrive.
  if (!(chr->properties & (ESP_GATT_CHAR_PROP_BIT_NOTIFY |
                            ESP_GATT_CHAR_PROP_BIT_INDICATE))) {
    ESP_LOGW(this->log_tag_.c_str(),"Characteristic %s has no NOTIFY/INDICATE property (props=0x%02X), skipping",
             characteristic_uuid.c_str(), chr->properties);
    return;
  }

  // Check if already subscribed (e.g., restored after reconnect)
  if (this->notify_map_.count(chr->handle)) {
    ESP_LOGD(this->log_tag_.c_str(),"Already subscribed to %s (handle 0x%04X), skipping",
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

  ESP_LOGI(this->log_tag_.c_str(),"Subscribing to %s (handle 0x%04X, cccd 0x%04X)...",
           characteristic_uuid.c_str(), chr->handle, cccd_handle);

  auto status = esp_ble_gattc_register_for_notify(
      this->parent()->get_gattc_if(),
      this->parent()->get_remote_bda(),
      chr->handle);

  if (status != ESP_OK) {
    ESP_LOGW(this->log_tag_.c_str(),"Subscribe failed: %d", status);
    this->notify_map_.erase(chr->handle);
    this->cccd_map_.erase(chr->handle);
    this->char_props_map_.erase(chr->handle);
  }
}

void PhilipsShaver::on_unsubscribe(std::string service_uuid,
                                    std::string characteristic_uuid) {
  if (!this->connected_) {
    ESP_LOGW(this->log_tag_.c_str(),"Cannot unsubscribe: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent()->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(),"Characteristic %s not found in service %s",
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

  ESP_LOGI(this->log_tag_.c_str(),"Unsubscribing from %s (handle 0x%04X)...",
           characteristic_uuid.c_str(), chr->handle);

  esp_ble_gattc_unregister_for_notify(
      this->parent()->get_gattc_if(),
      this->parent()->get_remote_bda(),
      chr->handle);

  this->notify_map_.erase(chr->handle);
}

void PhilipsShaver::on_write_characteristic(std::string service_uuid,
                                              std::string characteristic_uuid,
                                              std::string hex_data) {
  if (!this->connected_) {
    ESP_LOGW(this->log_tag_.c_str(),"Cannot write: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent()->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(this->log_tag_.c_str(),"Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    return;
  }

  // Parse hex string to bytes
  std::vector<uint8_t> bytes;
  size_t count = hex_data.length() / 2;
  if (count == 0 || !parse_hex(hex_data, bytes, count)) {
    ESP_LOGW(this->log_tag_.c_str(),"Invalid hex data: %s", hex_data.c_str());
    return;
  }

  ESP_LOGI(this->log_tag_.c_str(),"Writing %s (handle 0x%04X): %s (%d bytes)",
           characteristic_uuid.c_str(), chr->handle,
           hex_data.c_str(), bytes.size());

  auto status = esp_ble_gattc_write_char(
      this->parent()->get_gattc_if(),
      this->parent()->get_conn_id(),
      chr->handle,
      bytes.size(),
      bytes.data(),
      ESP_GATT_WRITE_TYPE_RSP,
      ESP_GATT_AUTH_REQ_NO_MITM);

  if (status != ESP_OK) {
    ESP_LOGW(this->log_tag_.c_str(),"Write request failed: %d", status);
  }
}

void PhilipsShaver::on_set_throttle(std::string throttle_ms) {
  uint32_t ms = std::stoul(throttle_ms);
  this->notify_throttle_ms_ = ms;
  ESP_LOGI(this->log_tag_.c_str(),"Notification throttle set to %u ms", ms);
}

void PhilipsShaver::on_get_info() {
  char uptime_str[16];
  snprintf(uptime_str, sizeof(uptime_str), "%u", millis() / 1000);

  char heap_str[16];
  snprintf(heap_str, sizeof(heap_str), "%u", (uint32_t) esp_get_free_heap_size());

  char subs_str[8];
  snprintf(subs_str, sizeof(subs_str), "%u", (uint32_t) this->notify_map_.size());

  char throttle_str[16];
  snprintf(throttle_str, sizeof(throttle_str), "%u", this->notify_throttle_ms_);

  // Check if shaver MAC is in the bonded device list
  std::string paired = "false";
  int bond_num = esp_ble_get_bond_device_num();
  if (bond_num > 0) {
    auto *bond_list = new esp_ble_bond_dev_t[bond_num];
    esp_ble_get_bond_device_list(&bond_num, bond_list);
    auto *bda = this->parent()->get_remote_bda();
    for (int i = 0; i < bond_num; i++) {
      if (memcmp(bond_list[i].bd_addr, bda, 6) == 0) {
        paired = "true";
        break;
      }
    }
    delete[] bond_list;
  }

  std::map<std::string, std::string> info = {
      {"status", "info"},
      {"version", PHILIPS_SHAVER_VERSION},
      {"bridge_id", this->bridge_id_},
      {"ble_connected", this->connected_ ? "true" : "false"},
      {"mac", this->get_shaver_mac_()},
      {"uptime_s", std::string(uptime_str)},
      {"free_heap", std::string(heap_str)},
      {"subscriptions", std::string(subs_str)},
      {"notify_throttle_ms", std::string(throttle_str)},
      {"paired", paired},
  };
  if (!this->remote_name_.empty()) {
    info["ble_name"] = this->remote_name_;
  }
  this->fire_homeassistant_event("esphome.philips_shaver_ble_status", info);

  ESP_LOGI(this->log_tag_.c_str(),"Info: v%s uptime=%ss heap=%s subs=%s paired=%s name=%s",
           PHILIPS_SHAVER_VERSION, uptime_str, heap_str, subs_str, paired.c_str(),
           this->remote_name_.empty() ? "(none)" : this->remote_name_.c_str());
}

void PhilipsShaver::gap_event_handler(esp_gap_ble_cb_event_t event,
                                       esp_ble_gap_cb_param_t *param) {
  switch (event) {
    case ESP_GAP_BLE_NC_REQ_EVT:
      ESP_LOGI(this->log_tag_.c_str(),"Numeric Comparison request — auto-confirming (passkey %06lu)",
               (unsigned long) param->ble_security.key_notif.passkey);
      esp_ble_confirm_reply(param->ble_security.key_notif.bd_addr, true);
      break;

    case ESP_GAP_BLE_AUTH_CMPL_EVT: {
      // Only handle events for our device (GAP events fire for all connections)
      if (memcmp(param->ble_security.auth_cmpl.bd_addr,
                 this->parent()->get_remote_bda(), 6) != 0) {
        break;
      }

      if (param->ble_security.auth_cmpl.success) {
        this->auth_completed_ = true;
        this->rapid_disconnect_count_ = 0;
        this->auth_fail_count_ = 0;
        if (this->retry_read_after_auth_ && this->probe_handle_ != 0) {
          // Path A: probe returned INSUF_AUTH, our explicit set_encryption()
          // triggered SMP, encryption is now up — retry the probe.
          this->retry_read_after_auth_ = false;
          ESP_LOGI(this->log_tag_.c_str(),"Auth complete — retrying probe read on handle 0x%04X",
                   this->probe_handle_);
          auto status = esp_ble_gattc_read_char(
              this->parent()->get_gattc_if(),
              this->parent()->get_conn_id(),
              this->probe_handle_, ESP_GATT_AUTH_REQ_NONE);
          if (status != ESP_OK) {
            ESP_LOGW(this->log_tag_.c_str(),"Probe retry failed (status=%d) — firing ready anyway",
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
          ESP_LOGD(this->log_tag_.c_str(),"Auth complete — deferring ready to probe-OK");
        }
      } else {
        this->auth_fail_count_++;
        ESP_LOGW(this->log_tag_.c_str(),"Auth failed (reason=%d, attempt %d/%d) — removing bond",
                 param->ble_security.auth_cmpl.fail_reason,
                 this->auth_fail_count_, MAX_AUTH_FAILURES);
        esp_ble_remove_bond_device(param->ble_security.auth_cmpl.bd_addr);

        if (this->auth_fail_count_ >= MAX_AUTH_FAILURES &&
            this->backoff_until_ms_ == 0) {
          uint32_t backoff_s = AUTH_BACKOFF_MS / 1000;
          ESP_LOGE(this->log_tag_.c_str(),"%d consecutive auth failures — disabling BLE for %us. "
                   "Clear Bluetooth pairing on the shaver.",
                   this->auth_fail_count_, backoff_s);
          this->backoff_until_ms_ = millis() + AUTH_BACKOFF_MS;
          this->parent()->set_enabled(false);

          char fail_str[4], backoff_str[8];
          snprintf(fail_str, sizeof(fail_str), "%d", this->auth_fail_count_);
          snprintf(backoff_str, sizeof(backoff_str), "%u", backoff_s);
          this->fire_homeassistant_event(
              "esphome.philips_shaver_ble_status",
              {
                  {"status", "auth_failed"},
                  {"mac", this->get_shaver_mac_()},
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

uint16_t PhilipsShaver::find_cccd_handle_(uint16_t char_handle) {
  // Query the ESP-IDF GATT table directly — synchronous RAM lookup,
  // bypasses ESPHome's potentially empty descriptor cache.
  uint16_t count = 1;
  esp_gattc_descr_elem_t result;
  memset(&result, 0, sizeof(result));
  esp_bt_uuid_t cccd_uuid;
  cccd_uuid.len = ESP_UUID_LEN_16;
  cccd_uuid.uuid.uuid16 = 0x2902;

  auto status = esp_ble_gattc_get_descr_by_char_handle(
      this->parent()->get_gattc_if(),
      this->parent()->get_conn_id(),
      char_handle,
      cccd_uuid,
      &result,
      &count);

  if (status == ESP_GATT_OK && count > 0) {
    ESP_LOGD(this->log_tag_.c_str(),"CCCD found via ESP-IDF API: handle 0x%04X for char 0x%04X",
             result.handle, char_handle);
    return result.handle;
  }

  // Fallback: handle + 1 (standard BLE layout)
  uint16_t fallback = char_handle + 1;
  ESP_LOGW(this->log_tag_.c_str(),"CCCD not found via API for char 0x%04X, using fallback 0x%04X",
           char_handle, fallback);
  return fallback;
}

void PhilipsShaver::resubscribe_all_() {
  for (const auto &entry : this->desired_subscriptions_) {
    const auto &svc_uuid_str = entry.first;
    const auto &chr_uuid_str = entry.second;

    auto svc = parse_uuid(svc_uuid_str);
    auto chr_uuid = parse_uuid(chr_uuid_str);

    auto *chr = this->parent()->get_characteristic(svc, chr_uuid);
    if (chr == nullptr) {
      ESP_LOGW(this->log_tag_.c_str(),"Resubscribe: characteristic %s not found, skipping",
               chr_uuid_str.c_str());
      continue;
    }

    uint16_t cccd_handle = this->find_cccd_handle_(chr->handle);
    this->cccd_map_[chr->handle] = cccd_handle;
    this->char_props_map_[chr->handle] = chr->properties;
    this->notify_map_[chr->handle] = chr_uuid_str;

    auto status = esp_ble_gattc_register_for_notify(
        this->parent()->get_gattc_if(),
        this->parent()->get_remote_bda(),
        chr->handle);

    if (status == ESP_OK) {
      ESP_LOGI(this->log_tag_.c_str(),"Resubscribe: %s (handle 0x%04X, cccd 0x%04X)",
               chr_uuid_str.c_str(), chr->handle, cccd_handle);
    } else {
      ESP_LOGW(this->log_tag_.c_str(),"Resubscribe failed for %s: %d",
               chr_uuid_str.c_str(), status);
      this->notify_map_.erase(chr->handle);
      this->cccd_map_.erase(chr->handle);
    }
  }
}

bool PhilipsShaver::is_already_bonded_() {
  int bond_num = esp_ble_get_bond_device_num();
  if (bond_num <= 0)
    return false;
  auto *bond_list = new esp_ble_bond_dev_t[bond_num];
  esp_ble_get_bond_device_list(&bond_num, bond_list);
  bool found = false;
  for (int i = 0; i < bond_num; i++) {
    if (memcmp(bond_list[i].bd_addr,
               this->parent()->get_remote_bda(), 6) == 0) {
      found = true;
      break;
    }
  }
  delete[] bond_list;
  return found;
}

void PhilipsShaver::fire_ready_event_() {
  this->fire_homeassistant_event(
      "esphome.philips_shaver_ble_status",
      {
          {"status", "ready"},
          {"mac", this->get_shaver_mac_()},
          {"version", PHILIPS_SHAVER_VERSION},
      });
}

void PhilipsShaver::start_post_auth_setup_() {
  if (this->ready_fired_) {
    ESP_LOGD(this->log_tag_.c_str(),"start_post_auth_setup_: ready already fired this connection");
    return;
  }
  this->ready_fired_ = true;
  this->fire_ready_event_();
  if (!this->desired_subscriptions_.empty()) {
    ESP_LOGI(this->log_tag_.c_str(),"Restoring %d notification subscription(s)...",
             this->desired_subscriptions_.size());
    this->resubscribe_all_();
  }
}

}  // namespace philips_shaver
}  // namespace esphome
