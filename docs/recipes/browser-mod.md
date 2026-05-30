# Recipe: Browser Mod + VAG Connect

> [browser_mod](https://github.com/thomasloven/hass-browser_mod) ist ein
> Top-Tier Frontend-Plugin (1.7k Stars, MIT, HACS Default) das jeden
> verbundenen HA-Browser-Tab in eine ansteuerbare Entity verwandelt
> + Services für Popups, Notifications, Navigation, Theme-Switch, etc.
> exposed.
>
> Diese Recipes nutzen browser_mod **als Frontend-Layer für VAG Connect**:
> Auto-Events triggern Popups / Notifications / Navigation auf dem Tab
> wo der User gerade ist (Tablet im Flur, Telefon, Desktop).

## Voraussetzungen

1. VAG Connect installiert + mindestens 1 Vehicle-Device aktiv (siehe
   [README](../../README.md))
2. browser_mod via HACS installiert (Default-Repo, kein Custom-Add nötig)
3. Mindestens 1 Browser registriert in browser_mod (Sidebar-Panel öffnen,
   "Register Browser" klicken)

Alle Beispiele unten gehen davon aus dass dein Vehicle entity-prefix
`audi_a4_b9` ist — ersetze mit deinem.

---

## Recipe 1 — 12V-Battery-Low Fullscreen-Popup

**Use-case:** Wenn die 12V-Starter-Battery deines Autos unter 11.5V
fällt (warning-Sensor seit v1.12.0) → fullscreen-Popup auf dem Tablet
im Flur, **bevor** das Auto morgens nicht mehr anspringt.

```yaml
alias: "VAG: 12V Battery Low Popup"
description: Fullscreen warning when starter battery drops below 11.5V
trigger:
  - platform: state
    entity_id: binary_sensor.audi_a4_b9_warning_12v_low
    to: "on"
action:
  - service: browser_mod.popup
    data:
      title: "⚠️ Auto-Batterie schwach"
      content: |
        Dein Audi A4 B9 zeigt eine 12V-Spannung unter 11.5V.
        Häufige Ursachen:
        - Auto stand >2 Wochen ohne Bewegung
        - Standheizung/Standlüftung läuft trockendraht
        - Battery-Wartung steht an

        Empfehlung: Heute fahren (>30 min) oder Ladegerät anstecken.
      right_button: "Verstanden"
      right_button_close: true
      initial_style: fullscreen
      dismissable: true
mode: single
```

---

## Recipe 2 — NFC-Tag triggert Quick-Command-Sheet

**Use-case:** NFC-Tag an der Wohnungstür kleben. Telefon ranhalten →
browser_mod Popup auf dem Telefon mit allen 5 wichtigsten VAG Connect
Buttons (Lock, Unlock, Climate Start, Wake, Flash).

```yaml
alias: "VAG: NFC → Quick Commands"
description: NFC tag opens VAG Connect quick-command sheet
trigger:
  - platform: tag
    tag_id: <your-nfc-tag-uuid>
action:
  - service: browser_mod.popup
    target:
      device_id: "{{ trigger.device_id }}"
    data:
      title: "Audi A4 B9 — Quick Actions"
      content:
        type: vertical-stack
        cards:
          - type: button
            entity: lock.audi_a4_b9_door_lock
            tap_action:
              action: call-service
              service: lock.lock
              service_data:
                entity_id: lock.audi_a4_b9_door_lock
            name: 🔒 Lock
          - type: button
            entity: lock.audi_a4_b9_door_lock
            tap_action:
              action: call-service
              service: lock.unlock
              service_data:
                entity_id: lock.audi_a4_b9_door_lock
            name: 🔓 Unlock (S-PIN required)
          - type: button
            entity: switch.audi_a4_b9_climate_start
            tap_action:
              action: call-service
              service: switch.turn_on
              service_data:
                entity_id: switch.audi_a4_b9_climate_start
            name: ❄️/🔥 Klima Start
          - type: button
            entity: button.audi_a4_b9_wake
            tap_action:
              action: call-service
              service: button.press
              service_data:
                entity_id: button.audi_a4_b9_wake
            name: ⏰ Auto wecken
          - type: button
            entity: button.audi_a4_b9_flash
            tap_action:
              action: call-service
              service: button.press
              service_data:
                entity_id: button.audi_a4_b9_flash
            name: 💡 Flash
      initial_style: classic
      dismissable: true
      timeout: 30000  # auto-close after 30s
mode: single
```

---

## Recipe 3 — Send-Destination Confirm-Dialog

**Use-case:** Lovelace-Karte zeigt eine Adresse aus deinem Adress-Buch.
Klick → browser_mod-Popup "Wirklich diese Adresse ans Auto senden?" mit
ha-form für letzte Editier-Möglichkeit, dann ruft VAG Connect den
`send_destination` Service.

```yaml
script:
  vag_send_destination_with_confirm:
    sequence:
      - service: browser_mod.popup
        data:
          title: "📍 Navigationsziel ans Auto senden?"
          content:
            type: ha-form
            schema:
              - name: address
                selector:
                  text:
              - name: latitude
                selector:
                  number:
                    min: -90
                    max: 90
              - name: longitude
                selector:
                  number:
                    min: -180
                    max: 180
            data:
              address: "{{ address | default('') }}"
              latitude: "{{ latitude | default(0) }}"
              longitude: "{{ longitude | default(0) }}"
          right_button: "Senden"
          right_button_action:
            service: vag_connect.send_destination
            data:
              vin: "{{ vin }}"
              latitude: "{{ FORM.latitude }}"
              longitude: "{{ FORM.longitude }}"
              name: "{{ FORM.address }}"
          left_button: "Abbrechen"
          left_button_close: true
          dismissable: true
```

---

## Recipe 4 — Charging-Done Toast (alle Browser)

**Use-case:** Auto fertig geladen → Toast-Notification auf JEDEM
registrierten Browser (Tablet, Desktop, Telefon) — kein Popup, nicht
intrusiv, einfach "fertig".

```yaml
alias: "VAG: Charging done — toast all browsers"
trigger:
  - platform: state
    entity_id: binary_sensor.audi_a4_b9_is_charging
    from: "on"
    to: "off"
condition:
  # Nur toasten wenn das Charging "natürlich" beendet wurde
  # (full battery), nicht wenn der User den Stecker zog.
  - condition: state
    entity_id: binary_sensor.audi_a4_b9_plug_connected
    state: "on"
  - condition: numeric_state
    entity_id: sensor.audi_a4_b9_battery_soc
    above: 95
action:
  - service: browser_mod.notification
    data:
      message: "🔋 Audi A4 B9 fertig geladen ({{ states('sensor.audi_a4_b9_battery_soc') }}%)"
      duration: 8000
mode: single
```

---

## Recipe 5 — Vehicle-Render im Picture-Card mit Popup-Detail

**Use-case:** Lovelace-Karte zeigt das Auto-Bild (image entity, populated
seit v1.20.0). Klick aufs Bild → fullscreen Popup mit allen Vehicle-
Details + Live-Karte + Battery-Gauge.

```yaml
type: picture-entity
entity: image.audi_a4_b9_render_side_lg
camera_view: live
show_state: false
show_name: false
tap_action:
  action: call-service
  service: browser_mod.popup
  service_data:
    title: "Audi A4 B9"
    content:
      type: vertical-stack
      cards:
        - type: glance
          entities:
            - sensor.audi_a4_b9_battery_soc
            - sensor.audi_a4_b9_range_km
            - sensor.audi_a4_b9_outside_temp
            - binary_sensor.audi_a4_b9_doors_locked
        - type: map
          default_zoom: 15
          entities:
            - device_tracker.audi_a4_b9_position
        - type: history-graph
          entities:
            - sensor.audi_a4_b9_battery_soc
          hours_to_show: 24
    initial_style: wide
    dismissable: true
```

---

## Tipp: Browser-Mod-Targeting

- **Default**: Service-Call ohne `target` triggered ALLE registrierten Browser
- **`target.device_id`**: Triggered nur den Browser mit dieser device_id
- **`{{ trigger.device_id }}`** in einer NFC-Trigger-Action: das Telefon das den NFC-Tag gescannt hat

Siehe [browser_mod README §Targeting](https://github.com/thomasloven/hass-browser_mod#targeting) für die volle Matrix.

---

## Cross-Reference

- VAG Connect Services: [`services.yaml`](../../custom_components/vag_connect/services.yaml)
- VAG Connect Entities: [README §What you get](../../README.md#-was-du-bekommst)
- browser_mod Repo: [thomasloven/hass-browser_mod](https://github.com/thomasloven/hass-browser_mod)
- Architektur-Audit: [_private/research-archive/browser-mod-integration-2026-05-03.md](../research/browser-mod-integration-2026-05-03.md)
