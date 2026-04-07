# Philips Shaver TODO

- [ ] ESP: Include `device_id` in info event payload for robust multi-device MAC detection (ported from Sonicare fix)
- [ ] ESP: Skip duplicate subscribe when subscriptions already restored after reconnect (ported from Sonicare)
- [ ] ESP: Don't fire "ready" before GATT service discovery completes (ported from Sonicare v1.2.1)
- [ ] Zeroconf cross-detection: Shaver detects Sonicare ESP bridges and vice versa (shared `_esphomelib._tcp.local.`)
