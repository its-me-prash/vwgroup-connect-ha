# Using VW Group Connect with evcc

[evcc](https://evcc.io) can read your car's state of charge, range and charging status straight from Home Assistant, and — on a two-way car (Audi or Škoda via the MBB channel) — start/stop charging. This works by pointing evcc at Home Assistant's own REST API; nothing extra runs inside this integration.

> **Beta.** The **read** path (SoC / range / status / charge-limit / climatisation) works on **every brand**, including read-only VW EU / portal cars. The **write** path (`chargeEnable`) only works on a **two-way** car (Audi or Škoda with a live MBB command channel) and only when evcc treats the car itself as the charger (no separate wallbox). With a real smart wallbox, evcc only needs the read path.

## 1. One-time setup in Home Assistant

1. **Enable the charge-status sensor.** This integration exposes a diagnostic sensor **`evcc charge status`** per EV that reports evcc's `A`/`B`/`C` status (evcc can't use our raw charging-state text). It's **disabled by default** — open your car's device page, find *evcc charge status*, and enable it.
2. **Create a long-lived access token.** HA profile → *Security* → *Long-lived access tokens* → create one. Keep it safe — it grants API access. It will sit in `evcc.yaml` in plain text (normal for evcc); you can revoke/rotate it from the same page any time.
3. **Find your entity IDs.** *Developer Tools → States*. The IDs below are examples — yours depend on your car's name and HA language. The typical ones:

   | evcc field | Home Assistant entity | notes |
   |---|---|---|
   | `soc` | `sensor.<car>_battery_soc` | % |
   | `range` | `sensor.<car>_electric_range` | km |
   | `status` | `sensor.<car>_evcc_charge_status` | the sensor from step 1 (A/B/C) |
   | `limitSoc` | `number.<car>_target_soc` | evcc **reads** it; set the target in HA, not evcc |
   | `climater` | `binary_sensor.<car>_climatisation` | optional |
   | `chargeEnable` (write) | `switch.<car>_charging` | **two-way cars only** |

## 2. Recipe A — `custom` vehicle (recommended)

Paste into `evcc.yaml`, replacing `<HA_URL>`, `<TOKEN>` and the entity IDs:

```yaml
vehicles:
  - name: myvag
    type: custom
    title: My VW Group EV
    capacity: 77            # usable battery kWh (static — set your car's value)
    soc:
      source: http
      uri: <HA_URL>/api/states/sensor.<car>_battery_soc
      headers: { Authorization: "Bearer <TOKEN>" }
      jq: .state | tonumber
    range:
      source: http
      uri: <HA_URL>/api/states/sensor.<car>_electric_range
      headers: { Authorization: "Bearer <TOKEN>" }
      jq: .state | tonumber
    status:
      source: http
      uri: <HA_URL>/api/states/sensor.<car>_evcc_charge_status
      headers: { Authorization: "Bearer <TOKEN>" }
      jq: .state
    limitSoc:
      source: http
      uri: <HA_URL>/api/states/number.<car>_target_soc
      headers: { Authorization: "Bearer <TOKEN>" }
      jq: .state | tonumber
    climater:
      source: http
      uri: <HA_URL>/api/states/binary_sensor.<car>_climatisation
      headers: { Authorization: "Bearer <TOKEN>" }
      jq: .state == "on"
    # ── two-way cars only (Audi / Škoda MBB), and only if evcc runs the car
    #    as a vehicle-API charger. Omit this whole block otherwise. ──
    chargeEnable:
      source: http
      uri: <HA_URL>/api/services/switch/turn_{{if .chargeenable}}on{{else}}off{{end}}
      method: POST
      headers: { Authorization: "Bearer <TOKEN>" }
      body: '{"entity_id": "switch.<car>_charging"}'
```

`status` must be present whenever `chargeEnable` is used — evcc requires it.

## 3. Recipe B — native `homeassistant` vehicle (alternative)

evcc also ships a native Home Assistant template. It's cleaner but its auth has been changing across evcc versions (older `token:` is being replaced by a pairing flow), so use it only if you're on a recent evcc:

```yaml
vehicles:
  - name: myvag
    type: homeassistant
    uri: <HA_URL>
    # auth per your evcc version (token / pairing)
    sensors:
      soc: sensor.<car>_battery_soc
      range: sensor.<car>_electric_range
      status: sensor.<car>_evcc_charge_status
      limitSoc: number.<car>_target_soc
      climater: binary_sensor.<car>_climatisation
    services:
      start_charging: switch.<car>_charging   # two-way cars only; leave stop empty for a switch
```

## 4. Verify

1. `curl -s -H "Authorization: Bearer <TOKEN>" <HA_URL>/api/states/sensor.<car>_battery_soc` → should return JSON with your SoC.
2. Restart evcc, open its UI — the vehicle tile should show the same SoC, range and a plug/charging status matching the car. Check evcc's log for `[http]` parse errors.
3. Status check: unplugged → `A`, plugged & idle → `B`, charging → `C`.

## Notes & limits

- **`limitSoc` is read-only in evcc** — set your charge target with the Home Assistant `number.<car>_target_soc` entity; evcc just reflects it.
- **`maxCurrent` isn't offered** — our AC current control is a two-value (`MAXIMUM`/`REDUCED`) selector, not evcc's ampere number, so evcc current-following won't drive the car. Use a real wallbox for current control.
- **`wakeup`** exists in HA but has a small daily budget (anti-abuse). Don't wire it into evcc's polling loop or it will be exhausted by mid-morning.
- SoC/range go **stale** (not zero) during backend hiccups; the status sensor always keeps a valid A/B/C.
- Read path works for **all brands**; write path is **Audi/Škoda two-way only**.
