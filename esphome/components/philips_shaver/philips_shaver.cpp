#include "philips_shaver.h"
#include "esphome/core/log.h"
#include "esphome/core/helpers.h"

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
  this->register_service(&PhilipsShaver::on_read_characteristic,
                          "ble_read_char", {"service_uuid", "char_uuid"});
  this->register_service(&PhilipsShaver::on_subscribe,
                          "ble_subscribe", {"service_uuid", "char_uuid"});
  this->register_service(&PhilipsShaver::on_unsubscribe,
                          "ble_unsubscribe", {"service_uuid", "char_uuid"});
  ESP_LOGI(TAG, "Services registered: ble_read_char, ble_subscribe, ble_unsubscribe");
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

}  // namespace philips_shaver
}  // namespace esphome
