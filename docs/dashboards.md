# Dashboard Guide — VW Group Connect entities in Home Assistant Lovelace

> Audience: end-users who already have VW Group Connect installed and want
> to surface the entities on a Lovelace dashboard. Covers the most
> frequent "Add to Dashboard does nothing" troubleshooting plus the
> dedicated VW Group Connect Lovelace card.

---

## 🎯 Quick start — add an entity to an existing view

If you just want to drop a sensor onto a card you already have:

1. Open the view you want
2. Click the **pencil** (Edit Dashboard) in the top-right corner
3. Click **+ Add Card** → pick the card type (Entities, Glance,
   Gauge, Sensor)
4. Search for your VAG entity by VIN (last 6 chars) or
   `vag_connect` substring

If you went via **Settings → Devices → VW Group Connect → \[entity\] →
Add to Dashboard** instead and your target view didn't appear, see
the next section.

---

## ❓ "Add to Dashboard" doesn't show my view

`Add to Dashboard` is a Home Assistant feature that opens a picker
listing all eligible dashboards + views. There are three common
reasons your existing view doesn't appear:

### Reason 1 — Dashboard is YAML-mode (most common)

`Add to Dashboard` only writes into **Storage-mode** dashboards
(UI-editable). If your dashboard is maintained via
`configuration.yaml` or `dashboards/*.yaml` files, HA cannot inject
new cards into it — the picker hides those dashboards.

**Check:**
- *Settings → Dashboards*
- Look at the **Mode** column for your dashboard
- `Storage` = UI-editable → will appear in the picker
- `YAML` = manual file-based → will NOT appear

**Workaround for YAML dashboards:** add the entity reference
manually to the YAML file. Example for an Entities card:

```yaml
type: entities
entities:
  - sensor.audi_q4_battery_soc
  - sensor.audi_q4_range_km
  - sensor.audi_q4_charging_state
```

### Reason 2 — The target view doesn't exist yet

HA's picker only lists **already-created** views. If you see your
dashboard but no sub-views, you need to create the empty view first:

1. Open the dashboard
2. Click the **pencil** (Edit) top-right
3. Click **+ Add View** (the `+` tab next to your existing views)
4. Save the empty view
5. Re-try **Add to Dashboard** — the new view will now appear

### Reason 3 — View uses the new "Sections" layout (HA 2024+)

The newer Sections layout sometimes refuses cards added via the
quick-workflow. Workaround:

1. Navigate to the view
2. Edit Mode (pencil top-right) → **+ Add Card**
3. Select the entity manually from the picker

---

## 🎨 Dedicated VW Group Connect Lovelace Card (BETA)

We maintain a separate Lovelace card optimised for VW Group Connect:

**Repo:** https://github.com/its-me-prash/vag-connect-cards

### Status (as of v2.2.x)

- ✅ **Functional:** PHEV-range-triple, charging-state badge,
  connection-state indicator, vehicle-render display all work
- ⚠️ **Cosmetic — BETA:** the card currently ships with a
  **Mercedes-style background** because the original design
  inspiration came from a Mercedes HA card. **VAG-themed redesign
  is in progress** — purely cosmetic, no functional impact
- 🧪 **Iterating UX:** feedback drives the design direction; please
  open issues on the card repo with screenshots if something
  doesn't look right

### Install

1. HACS → Frontend (or Integrations on older HACS)
2. **+ Explore & Add Repositories** → search `vag-connect-cards`
3. If not yet listed: **Custom Repositories** → paste
   `https://github.com/its-me-prash/vag-connect-cards` → Category:
   Plugin → Add
4. Install + restart HA
5. Add to a Lovelace view via **+ Add Card → Custom: VAG Vehicle
   Card** (or via YAML — see card-repo README)

### When NOT to use the dedicated card

- You want a single-purpose tile (just charge %, just range) →
  use stock Gauge / Sensor cards
- You're on a strict-policy install that disallows custom cards →
  stock cards work everywhere
- You want full UX-customisation freedom → use Mushroom + templates

### Issues / Feature Requests

Card-specific issues go to the card repo:
https://github.com/its-me-prash/vag-connect-cards/issues

Integration-specific issues (sensors missing, wrong values, etc.)
stay here on the integration repo.

---

## 🫧 Ready-made Bubble Card templates (recommended starter)

If you want the **fastest path to a beautiful VW Group Connect dashboard**
without writing YAML from scratch, install
[**Bubble Card**](https://github.com/Clooos/Bubble-Card) via HACS
and drop in our pre-built templates:

📁 [`docs/lovelace/bubble-card/`](lovelace/bubble-card/)

What's in the folder:

| File | Purpose |
|------|---------|
| `README.md` | Setup guide + multi-vehicle instructions |
| `01-vehicle-button-stack.yaml` | Horizontal vehicle selector at top |
| `02-vehicle-popup.yaml` | Main pop-up: battery / range / charging / climate / lock |
| `03-charging-controls.yaml` | Detailed charging settings + target SoC |
| `04-climate-controls.yaml` | Climate, defrost, departure timers |
| `05-door-status.yaml` | Lock state, per-door + trunk + hood + alarm |
| `99-full-dashboard.yaml` | Complete single-vehicle dashboard combining all of the above |

**Quick start (under 5 minutes):**

1. Install Bubble Card (HACS → Frontend → "Bubble Card")
2. Open [`99-full-dashboard.yaml`](lovelace/bubble-card/99-full-dashboard.yaml)
3. Copy → paste into your dashboard's Raw configuration editor
4. Search-replace `audi_q4` with your vehicle's entity prefix
5. Done

Bubble Card gives you the glass-morphism / gradient aesthetic shown
in the upstream [card gallery](https://github.com/Clooos/Bubble-Card#screenshots).
Our templates configure all buttons, pop-ups and quick-actions
that match how VW Group Connect exposes vehicle state.

---

## 🧱 Other 3rd-party cards that work with VW Group Connect

The integration exposes `extra_state_attributes.image_url` on the
device-tracker + image entities, so generic vehicle cards pick it
up automatically:

- **[Ultra-Vehicle-Card](https://github.com/WJDDesigns/Ultra-Vehicle-Card)** —
  full-featured visual dashboard card
- **[vehicle-info-card](https://github.com/ngocjohn/vehicle-info-card)** —
  Mercedes-MBUX-style layout (works with VAG entities too)
- **[Mushroom](https://github.com/piitaya/lovelace-mushroom)** —
  template cards for compact mobile-friendly tiles
- **[card-mod](https://github.com/thomasloven/lovelace-card-mod)** —
  style any other card with custom CSS
- **[button-card](https://github.com/custom-cards/button-card)** —
  custom action buttons (Lock, Unlock, Start Climate)

Examples in [`docs/lovelace-example.yaml`](lovelace-example.yaml).

---

## 🔍 Finding the entity IDs you want

VW Group Connect entity-IDs follow the pattern:

```
<platform>.<vehicle_nickname_or_vin>_<field>
```

Examples (for a vehicle named "Q4 e-tron"):

```
sensor.q4_e_tron_battery_soc
sensor.q4_e_tron_range_km
sensor.q4_e_tron_charging_state
binary_sensor.q4_e_tron_doors_locked
device_tracker.q4_e_tron
image.q4_e_tron
button.q4_e_tron_start_climatisation
lock.q4_e_tron_central_locking
```

**Quickest way to discover them:**

1. *Developer Tools → States* (left sidebar bottom)
2. Filter: `vag_connect` (or your nickname / VIN-last-6)
3. Copy the `entity_id` column

---

## 📦 Per-version feature highlights (what's available where)

| HA Entity | Since | Brands |
|---|---|---|
| `binary_sensor.doors_locked` | v1.0.0 | All 6 |
| `binary_sensor.ignition_on` | v2.2.0 | Skoda |
| `binary_sensor.daily_power_budget_available` | v2.2.0 | VW EU + Audi |
| `binary_sensor.subscription_active` | v2.2.0 | SEAT/CUPRA + VW EU + Audi |
| `binary_sensor.vehicle_at_saved_location` | v2.2.0 | Skoda |
| `binary_sensor.battery_protection_limit_on` | v2.2.1 | Skoda |
| `sensor.subscription_expiry_at` | v2.2.0 | SEAT/CUPRA + VW EU + Audi |
| `sensor.subscription_days_remaining` | v2.2.0 | SEAT/CUPRA + VW EU + Audi |
| `sensor.car_type` | v2.2.1 | **all 6 brands** (derived cross-brand) |
| `sensor.primary_engine_type` | v2.2.0–v2.2.1 | All 4 Cariad + CUPRA/SEAT |
| `sensor.secondary_engine_type` | v2.2.0–v2.2.1 | Skoda + CUPRA/SEAT + VW EU + Audi |
| `sensor.electric_range_km` | v1.10.0 + v2.2.1 (Porsche) | 5 brands |
| `sensor.combustion_range_km` | v1.10.0 + v2.2.1 (Porsche) | 5 brands |
| `sensor.battery_temp_max` | v2.2.0 | VW EU + Audi |
| `sensor.steering_wheel_position` | v2.2.0 | Skoda |
| `sensor.climate_timer_enabled_count` | v2.2.0 + v2.2.2 (VW EU/Audi) | Skoda + VW EU + Audi |
| `sensor.departure_timer_enabled_count` | v2.2.0 | VW EU + Audi |

Many entities are **phantom-protected** — they only appear if your
specific vehicle's backend actually publishes that field. If you
don't see one of the diagnostic sensors above, it usually means
your model / firmware doesn't ship that data.

---

## 🆘 Still stuck?

- Check [`docs/FAQ.md`](FAQ.md) for general installation +
  configuration questions
- Open a [Discussion](https://github.com/its-me-prash/vwgroup-connect-ha/discussions)
  if you're unsure whether it's a bug or a config issue
- Open an [Issue](https://github.com/its-me-prash/vwgroup-connect-ha/issues)
  with the **HA version**, **integration version**, and your
  **dashboard mode** (Storage / YAML) — saves a back-and-forth round

---

*Last updated: 2026-05-17 (v2.2.1 + v2.2.2 in-flight)*
