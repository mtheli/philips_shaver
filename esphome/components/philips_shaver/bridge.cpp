#include "bridge.h"
#include "coordinator.h"

#include "esphome/core/log.h"
#include "esphome/core/helpers.h"

#include <esp_system.h>

namespace esphome {
namespace philips_shaver {

static const char *const TAG = "philips_shaver.bridge";

std::string ShaverBridge::svc_name_(const std::string &action) {
  if (this->bridge_id_.empty())
    return action;
  return action + "_" + this->bridge_id_;
}

void ShaverBridge::setup() {
  this->register_service(&ShaverBridge::on_read_characteristic,
                          this->svc_name_("ble_read_char"),
                          {"service_uuid", "char_uuid"});
  this->register_service(&ShaverBridge::on_subscribe,
                          this->svc_name_("ble_subscribe"),
                          {"service_uuid", "char_uuid"});
  this->register_service(&ShaverBridge::on_unsubscribe,
                          this->svc_name_("ble_unsubscribe"),
                          {"service_uuid", "char_uuid"});
  this->register_service(&ShaverBridge::on_write_characteristic,
                          this->svc_name_("ble_write_char"),
                          {"service_uuid", "char_uuid", "data"});
  this->register_service(&ShaverBridge::on_set_throttle,
                          this->svc_name_("ble_set_throttle"),
                          {"throttle_ms"});
  this->register_service(&ShaverBridge::on_get_info,
                          this->svc_name_("ble_get_info"), {});
  ESP_LOGI(this->log_tag_.c_str(), "Services registered (bridge_id: '%s')",
           this->bridge_id_.c_str());
}

void ShaverBridge::loop() {
  uint32_t now = millis();

  if (this->coord_ != nullptr)
    this->coord_->on_loop(now);

  if ((now - this->last_heartbeat_ms_) >= HEARTBEAT_INTERVAL_MS) {
    this->last_heartbeat_ms_ = now;
    char uptime_str[16];
    snprintf(uptime_str, sizeof(uptime_str), "%u", now / 1000);

    std::map<std::string, std::string> data = {
        {"status", "heartbeat"},
        {"version", PHILIPS_SHAVER_VERSION},
        {"uptime_s", std::string(uptime_str)},
    };
    if (this->coord_ != nullptr) {
      data["ble_connected"] = this->coord_->is_connected() ? "true" : "false";
      data["mac"] = this->coord_->get_remote_mac();
    }
    this->fire_event(EVENT_STATUS, data);

    // If BLE is connected and authenticated but no one has subscribed yet,
    // re-fire "ready" so HA can set up subscriptions. After OTA reboot, BLE
    // connects before the HA API stream is up — the initial "ready" is lost.
    // This keeps signalling every heartbeat until HA subscribes
    // (subscriptions become non-empty → self-terminating).
    if (this->coord_ != nullptr && this->coord_->is_connected() &&
        this->coord_->is_services_discovered() &&
        this->coord_->is_authenticated() &&
        !this->coord_->has_subscriptions()) {
      ESP_LOGI(this->log_tag_.c_str(),
               "BLE connected, no subscriptions — re-firing ready");
      this->fire_event(EVENT_STATUS,
                       {
                           {"status", "ready"},
                           {"mac", this->coord_->get_remote_mac()},
                           {"version", PHILIPS_SHAVER_VERSION},
                           {"uptime_s", std::string(uptime_str)},
                       });
    }
  }
}

void ShaverBridge::dump_config() {
  ESP_LOGCONFIG(this->log_tag_.c_str(), "Philips Shaver BLE Bridge v%s",
                PHILIPS_SHAVER_VERSION);
  if (!this->bridge_id_.empty())
    ESP_LOGCONFIG(this->log_tag_.c_str(), "  Bridge ID: %s",
                  this->bridge_id_.c_str());
}

void ShaverBridge::fire_event(const std::string &event_type,
                               const std::map<std::string, std::string> &data) {
  this->fire_homeassistant_event(event_type, data);
}

void ShaverBridge::publish_connected(bool connected) {
  if (this->connected_sensor_ != nullptr)
    this->connected_sensor_->publish_state(connected);
}

void ShaverBridge::on_read_characteristic(std::string service_uuid,
                                           std::string char_uuid) {
  if (this->coord_ != nullptr)
    this->coord_->read_char(service_uuid, char_uuid);
}

void ShaverBridge::on_subscribe(std::string service_uuid,
                                 std::string char_uuid) {
  if (this->coord_ != nullptr)
    this->coord_->subscribe(service_uuid, char_uuid);
}

void ShaverBridge::on_unsubscribe(std::string service_uuid,
                                   std::string char_uuid) {
  if (this->coord_ != nullptr)
    this->coord_->unsubscribe(service_uuid, char_uuid);
}

void ShaverBridge::on_write_characteristic(std::string service_uuid,
                                             std::string char_uuid,
                                             std::string hex_data) {
  if (this->coord_ != nullptr)
    this->coord_->write_char(service_uuid, char_uuid, hex_data);
}

void ShaverBridge::on_set_throttle(std::string throttle_ms) {
  if (this->coord_ == nullptr)
    return;
  uint32_t ms = std::stoul(throttle_ms);
  this->coord_->set_throttle(ms);
}

void ShaverBridge::on_get_info() {
  if (this->coord_ == nullptr)
    return;

  char uptime_str[16];
  snprintf(uptime_str, sizeof(uptime_str), "%u", millis() / 1000);

  char heap_str[16];
  snprintf(heap_str, sizeof(heap_str), "%u",
           (uint32_t) esp_get_free_heap_size());

  auto info = this->coord_->collect_info_data();
  info["status"] = "info";
  info["bridge_id"] = this->bridge_id_;
  info["uptime_s"] = std::string(uptime_str);
  info["free_heap"] = std::string(heap_str);

  this->fire_event(EVENT_STATUS, info);

  ESP_LOGI(this->log_tag_.c_str(),
           "Info: v%s uptime=%ss heap=%s subs=%s paired=%s name=%s",
           PHILIPS_SHAVER_VERSION, uptime_str, heap_str,
           info["subscriptions"].c_str(), info["paired"].c_str(),
           info.count("ble_name") ? info["ble_name"].c_str() : "(none)");
}

}  // namespace philips_shaver
}  // namespace esphome
