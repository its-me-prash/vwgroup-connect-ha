# Bubble Card Templates for VW Group Connect

> Pre-built Lovelace YAML snippets that use [**Bubble Card**](https://github.com/Clooos/Bubble-Card)
> to give your VAG vehicles a beautiful, glass-morphism dashboard out
> of the box — designed by community feedback (FB-group 2026-05-17).

---

## ✨ What you get

Drop these snippets into your dashboard and get:

- **Vehicle button stack** at the top (room/device selector pattern from Bubble Card)
- **Pop-up panel per vehicle** with charging / range / climate / lock controls
- **Per-feature sub-cards** for charging settings, climate timers, door status
- **Automatically themed** to match Bubble Card's modern aesthetic
- **Multi-vehicle ready** — copy-paste the per-vehicle blocks for each car

---

## 📦 Prerequisites

1. **VW Group Connect** integration installed and at least one vehicle configured
2. **Bubble Card** installed via HACS:
   - HACS → Frontend → "+ Explore & Add Repositories"
   - Search "Bubble Card" → install
   - Restart HA
3. Your dashboard is in **Storage mode** (UI-editable) OR you're comfortable editing YAML

---

## 🧩 Snippets

| File | Purpose |
|------|---------|
| [`01-vehicle-button-stack.yaml`](01-vehicle-button-stack.yaml) | Horizontal button-stack at top — one button per vehicle |
| [`02-vehicle-popup.yaml`](02-vehicle-popup.yaml) | Pop-up panel with battery / range / charging / climate state (EV) |
| [`02b-vehicle-popup-diesel.yaml`](02b-vehicle-popup-diesel.yaml) | **Diesel variant** — fuel / AdBlue / remote engine / service intervals (Audi S6 TDI example) |
| [`03-charging-controls.yaml`](03-charging-controls.yaml) | Charging start/stop, target SoC slider, charge mode select |
| [`04-climate-controls.yaml`](04-climate-controls.yaml) | Climate start/stop, target temp, departure timers |
| [`05-door-status.yaml`](05-door-status.yaml) | Lock state, per-door open status, parking position |
| [`99-full-dashboard.yaml`](99-full-dashboard.yaml) | Complete dashboard combining all above for a single vehicle |

---

## 🚀 Quick start (single vehicle)

1. Find your vehicle's entity-id prefix:
   - Developer Tools → States
   - Filter `vag_connect`
   - You'll see entities like `sensor.audi_q4_battery_soc` — the
     **prefix** here is `audi_q4`
2. Copy [`99-full-dashboard.yaml`](99-full-dashboard.yaml) into a new
   Lovelace view (Raw configuration editor)
3. Search-replace `audi_q4` with your actual prefix
4. Search-replace `Audi Q4 e-tron` with your vehicle's display name
5. Save → done

---

## 🚗 Multi-vehicle setup

For each additional vehicle:

1. Copy the `popup_audi_q4:` block (entire pop-up YAML segment)
2. Rename to `popup_<your_other_vehicle_prefix>:` everywhere
3. Search-replace `audi_q4` → `<other_prefix>` inside the new block
4. Add a new button to `01-vehicle-button-stack.yaml` for the new
   vehicle (one extra `- type: 'custom:bubble-card'` row)

---

## 🎨 Theming notes

- All snippets use Bubble Card's **default styling** — no extra CSS
- The gradient colors come from Bubble Card's built-in palette;
  override via the `styles:` block on individual cards if you want
  brand-specific colors (e.g. Audi red, Cupra copper, Skoda green)
- Pop-ups use Bubble Card's blur backdrop — works best on dark themes

---

## 🐛 Troubleshooting

**"Card type not found: custom:bubble-card"**
→ Bubble Card not installed or HA not restarted after install

**"Entity not found: sensor.audi_q4_battery_soc"**
→ Replace `audi_q4` placeholder with your actual vehicle's entity
prefix (see Quick Start step 1)

**Pop-up doesn't open**
→ Check the `hash:` field in the pop-up YAML matches the `link:`
on the button. Bubble Card uses URL hashes for pop-up routing.

**Card looks broken / no gradients**
→ Bubble Card requires HA Frontend 2024.5+ (CSS containment).
Update HA if you're on an older release.

---

## 📚 Related

- [`docs/dashboards.md`](../../dashboards.md) — general dashboard
  guide ("Add to Dashboard" troubleshooting, view setup)
- [Bubble Card docs](https://github.com/Clooos/Bubble-Card/wiki) —
  full reference for all card types and styling options
- [`its-me-prash/vag-connect-cards`](https://github.com/its-me-prash/vag-connect-cards) —
  dedicated VW Group Connect Lovelace card (BETA — alternative to
  Bubble Card if you want a single-purpose VAG dashboard)

---

*Templates contributed by the VW Group Connect community. Issues +
improvements welcome via PR.*
