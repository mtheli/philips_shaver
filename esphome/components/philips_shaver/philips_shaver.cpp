#include "philips_shaver.h"
#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esp_gap_ble_api.h"

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

void PhilipsShaver::setup() {
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
  // The on_connect lambda in the YAML calls esp_ble_set_encryption() with
  // ESP_BLE_SEC_ENCRYPT_MITM to initiate pairing using these params.
  //
  // Note: This overrides ESPHome's io_capability YAML setting.
  uint8_t auth_req = 0x2D;  // Bond(1) | MITM(4) | SC(8) | CT2(0x20)
  esp_ble_io_cap_t io_cap = ESP_IO_CAP_IO;  // DisplayYesNo (0x01)
  uint8_t key_size = 16;
  uint8_t init_key = ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK;
  uint8_t rsp_key = ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK;

  esp_ble_gap_set_security_param(ESP_BLE_SM_AUTHEN_REQ_MODE, &auth_req, sizeof(auth_req));
  esp_ble_gap_set_security_param(ESP_BLE_SM_IOCAP_MODE, &io_cap, sizeof(io_cap));
  esp_ble_gap_set_security_param(ESP_BLE_SM_MAX_KEY_SIZE, &key_size, sizeof(key_size));
  esp_ble_gap_set_security_param(ESP_BLE_SM_SET_INIT_KEY, &init_key, sizeof(init_key));
  esp_ble_gap_set_security_param(ESP_BLE_SM_SET_RSP_KEY, &rsp_key, sizeof(rsp_key));
  ESP_LOGI(TAG, "SMP security configured for LE Secure Connections");

  this->register_service(&PhilipsShaver::on_read_characteristic,
                          "ble_read_char", {"service_uuid", "char_uuid"});
  this->register_service(&PhilipsShaver::on_subscribe,
                          "ble_subscribe", {"service_uuid", "char_uuid"});
  this->register_service(&PhilipsShaver::on_unsubscribe,
                          "ble_unsubscribe", {"service_uuid", "char_uuid"});
  this->register_service(&PhilipsShaver::on_write_characteristic,
                          "ble_write_char", {"service_uuid", "char_uuid", "data"});
  ESP_LOGI(TAG, "Services registered: ble_read_char, ble_subscribe, ble_unsubscribe, ble_write_char");
}

void PhilipsShaver::loop() {}

void PhilipsShaver::dump_config() {
  ESP_LOGCONFIG(TAG, "Philips Shaver BLE Bridge");
}

void PhilipsShaver::gattc_event_handler(esp_gattc_cb_event_t event,
                                         esp_gatt_if_t gattc_if,
                                         esp_ble_gattc_cb_param_t *param) {
  switch (event) {
    case ESP_GATTC_OPEN_EVT: {
      if (param->open.status == ESP_GATT_OK) {
        ESP_LOGI(TAG, "Connected to shaver");
        this->connected_ = true;
      } else {
        ESP_LOGW(TAG, "Connection failed, status=%d", param->open.status);
      }
      break;
    }

    case ESP_GATTC_DISCONNECT_EVT: {
      ESP_LOGI(TAG, "Disconnected from shaver");
      this->connected_ = false;
      this->pending_handle_ = 0;
      this->notify_map_.clear();
      this->cccd_map_.clear();
      break;
    }

    case ESP_GATTC_SEARCH_CMPL_EVT: {
      ESP_LOGI(TAG, "Service discovery complete");
      break;
    }

    case ESP_GATTC_READ_CHAR_EVT: {
      if (param->read.status != ESP_GATT_OK) {
        ESP_LOGW(TAG, "Read failed for %s, status=%d",
                 this->pending_char_uuid_.c_str(), param->read.status);
        this->pending_handle_ = 0;
        break;
      }

      if (param->read.handle == this->pending_handle_) {
        std::string hex_payload =
            format_hex(param->read.value, param->read.value_len);

        ESP_LOGI(TAG, "Read %s: %s (%d bytes)",
                 this->pending_char_uuid_.c_str(),
                 hex_payload.c_str(), param->read.value_len);

        this->fire_homeassistant_event(
            "esphome.philips_shaver_ble_data",
            {
                {"uuid", this->pending_char_uuid_},
                {"payload", hex_payload},
            });

        this->pending_handle_ = 0;
      }
      break;
    }

    case ESP_GATTC_REG_FOR_NOTIFY_EVT: {
      if (param->reg_for_notify.status == ESP_GATT_OK) {
        ESP_LOGI(TAG, "Notify registered for handle 0x%04X",
                 param->reg_for_notify.handle);

        // Write CCCD to tell the remote device to start sending notifications
        auto it = this->cccd_map_.find(param->reg_for_notify.handle);
        if (it != this->cccd_map_.end()) {
          uint16_t notify_en = 0x0001;
          esp_ble_gattc_write_char_descr(
              gattc_if,
              this->parent()->get_conn_id(),
              it->second,
              sizeof(notify_en),
              (uint8_t *) &notify_en,
              ESP_GATT_WRITE_TYPE_RSP,
              ESP_GATT_AUTH_REQ_NO_MITM);
          ESP_LOGI(TAG, "CCCD written for handle 0x%04X (descr 0x%04X)",
                   param->reg_for_notify.handle, it->second);
        }
      } else {
        ESP_LOGW(TAG, "Notify registration failed, status=%d",
                 param->reg_for_notify.status);
      }
      break;
    }

    case ESP_GATTC_NOTIFY_EVT: {
      auto it = this->notify_map_.find(param->notify.handle);
      if (it == this->notify_map_.end())
        break;

      std::string hex_payload =
          format_hex(param->notify.value, param->notify.value_len);

      ESP_LOGD(TAG, "Notify %s: %s (%d bytes)",
               it->second.c_str(),
               hex_payload.c_str(), param->notify.value_len);

      this->fire_homeassistant_event(
          "esphome.philips_shaver_ble_data",
          {
              {"uuid", it->second},
              {"payload", hex_payload},
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
    ESP_LOGW(TAG, "Cannot read: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent()->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(TAG, "Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    return;
  }

  this->pending_handle_ = chr->handle;
  this->pending_char_uuid_ = characteristic_uuid;

  ESP_LOGI(TAG, "Reading %s (handle 0x%04X)...",
           characteristic_uuid.c_str(), chr->handle);

  auto status = esp_ble_gattc_read_char(
      this->parent()->get_gattc_if(),
      this->parent()->get_conn_id(),
      chr->handle,
      ESP_GATT_AUTH_REQ_NO_MITM);

  if (status != ESP_OK) {
    ESP_LOGW(TAG, "Read request failed: %d", status);
    this->pending_handle_ = 0;
  }
}

void PhilipsShaver::on_subscribe(std::string service_uuid,
                                  std::string characteristic_uuid) {
  if (!this->connected_) {
    ESP_LOGW(TAG, "Cannot subscribe: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent()->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(TAG, "Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    return;
  }

  // Find CCCD descriptor (0x2902) for this characteristic
  uint16_t cccd_handle = 0;
  for (auto *desc : chr->descriptors) {
    if (desc->uuid == espbt::ESPBTUUID::from_uint16(0x2902)) {
      cccd_handle = desc->handle;
      break;
    }
  }

  if (cccd_handle == 0) {
    // Fallback: CCCD is typically at handle + 1
    cccd_handle = chr->handle + 1;
    ESP_LOGW(TAG, "No CCCD descriptor found, using fallback handle 0x%04X",
             cccd_handle);
  }
  this->cccd_map_[chr->handle] = cccd_handle;

  this->notify_map_[chr->handle] = characteristic_uuid;

  ESP_LOGI(TAG, "Subscribing to %s (handle 0x%04X, cccd 0x%04X)...",
           characteristic_uuid.c_str(), chr->handle, cccd_handle);

  auto status = esp_ble_gattc_register_for_notify(
      this->parent()->get_gattc_if(),
      this->parent()->get_remote_bda(),
      chr->handle);

  if (status != ESP_OK) {
    ESP_LOGW(TAG, "Subscribe failed: %d", status);
    this->notify_map_.erase(chr->handle);
    this->cccd_map_.erase(chr->handle);
  }
}

void PhilipsShaver::on_unsubscribe(std::string service_uuid,
                                    std::string characteristic_uuid) {
  if (!this->connected_) {
    ESP_LOGW(TAG, "Cannot unsubscribe: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent()->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(TAG, "Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    return;
  }

  ESP_LOGI(TAG, "Unsubscribing from %s (handle 0x%04X)...",
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
    ESP_LOGW(TAG, "Cannot write: not connected");
    return;
  }

  auto svc = parse_uuid(service_uuid);
  auto chr_uuid = parse_uuid(characteristic_uuid);

  auto *chr = this->parent()->get_characteristic(svc, chr_uuid);
  if (chr == nullptr) {
    ESP_LOGW(TAG, "Characteristic %s not found in service %s",
             characteristic_uuid.c_str(), service_uuid.c_str());
    return;
  }

  // Parse hex string to bytes
  std::vector<uint8_t> bytes;
  size_t count = hex_data.length() / 2;
  if (count == 0 || !parse_hex(hex_data, bytes, count)) {
    ESP_LOGW(TAG, "Invalid hex data: %s", hex_data.c_str());
    return;
  }

  ESP_LOGI(TAG, "Writing %s (handle 0x%04X): %s (%d bytes)",
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
    ESP_LOGW(TAG, "Write request failed: %d", status);
  }
}

}  // namespace philips_shaver
}  // namespace esphome
