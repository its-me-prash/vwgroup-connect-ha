<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>One Home Assistant integration for all seven Volkswagen Group brands — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Canada</strong><br>
  <em>Direct API access, multi-channel with automatic fallback, no middleware.</em>
</p>

<p align="center">
  <a href="https://github.com/sponsors/its-me-prash"><img src="https://img.shields.io/badge/%E2%9D%A4%20Sponsor-ec6cb9?logo=github-sponsors&logoColor=white" alt="Sponsor this project"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Default-41BDF5.svg" alt="HACS Default"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha?include_prereleases" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL%20v3-blue.svg" alt="License"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue" alt="Home Assistant"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  🌍 <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Previously published as **`vag-connect-ha`** (VAG = Volkswagen AG, standard DACH abbreviation).
> Turns out that abbreviation reads *quite* differently to English speakers 😅
>
> **What keeps working as before**: all entities (e.g. `sensor.audi_q4_battery_soc`),
> all service-calls (`vag_connect.lock`, `vag_connect.show_vag` etc.), all automations,
> the HACS install - **nothing breaks**. Marketing/display name changes, code internals
> stay unchanged. See [`MIGRATION.md`](MIGRATION.md).
>
> Huge thanks to the **Home Assistant UK** and **HA Ideas, Projects and Solutions**
> communities for the heads-up - especially **Si Gregory**, **Ben Johnson**, and **Evets David**.
>
> And a special shoutout to **Jordan Waeles**, whose `show_vag()` comment is now an officially
> supported easter egg in this integration (`vag_connect.show_vag` service, see CHANGELOG v2.2.3).

---

## What is this?

**VW Group Connect is a [Home Assistant](https://www.home-assistant.io) integration that brings connected-car data and control into your smart home for all seven Volkswagen Group brands — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche and VW US/Canada — plus Bentley (read-only), from a single config entry.**

It surfaces battery & charging state, range, odometer, climate, doors & windows, location and more, and — where the brand's backend still allows it — sends remote commands such as lock/unlock, climate and charge control. To keep working through Volkswagen's 2026 API changes it speaks **several channels and falls back automatically** when one is blocked: the brand-native backends, the read-only **EU Data Act** vehicle-data portal, an opt-in `volkswagen.de` web channel, and a durable **passwordless** login for older Car-Net vehicles. It runs happily **alongside [evcc](https://evcc.io)** and needs **zero PyPI dependencies**.

> 🎉 **Now available directly in HACS** — no custom repository needed.

---

## Highlights

- **All 7 VW Group brands incl. Porsche & VW US/Canada** in one integration — the EU Data Act portal structurally *excludes* Porsche, so portal-only tools can never cover it.
- **Two-way control** where the brand allows it (lock/unlock, climate, charging, target SoC) — not just reads.
- **Passwordless login option** (browser/device-code) — no password stored in Home Assistant.
- **Multi-channel with auto-fallback** — brand-native → EU Data Act portal → opt-in vw.de web → durable Car-Net. One channel going down doesn't take your data dark.
- **Resilient by design** — keeps last-known values through portal outages, filters bogus "no reading" sentinels, never lets the odometer jump backwards.
- **GPS device tracker**, 100+ entities across 11 platforms, 20+ service calls, multi-vehicle per account.
- **Vehicle Data Scout** — auto-detects API drift and offers a one-click bug report. **Quality Scale: Platinum.**

---

## Brand status

| Brand | Control | Data | Notes |
|---|---|---|---|
| **Audi** | ✅ Two-way | ✅ Full | myAudi backend |
| **Škoda** | ✅ Two-way | ✅ Full | native Škoda backend |
| **Porsche** | ✅ Two-way | ✅ Full | Porsche Connect |
| **VW US/CA** | ✅ Two-way | ✅ Full | VW NA cloud |
| **VW EU** | ⚠️ Durable Car-Net (older models) | ✅ EU Data Act + vw.de (beta) | newer ID/MEB cars: read-only via portal |
| **CUPRA / SEAT** | ⚠️ Limited | ✅ EU Data Act | brand backend gated by VW since 2026 |
| **Bentley** | ⏳ Live-test gated | ✅ Login + read | My Bentley — runs on the Audi platform/tenant |

> Honest note: in 2026 Volkswagen put parts of its API behind device attestation. This integration routes around it where possible (durable Car-Net login, EU Data Act portal, vw.de web) and is transparent about what each channel can and cannot do.

---

## Known limitations

A few things are **structural** — they come from how Volkswagen's backends work in 2026, not from the integration, and no setting fixes them:

- **MEB / ID-family cars are read-only** (ID.3 / ID.4 / ID.5 / ID.7, Enyaq, Born, Q4 e-tron). Remote commands — lock, climate, charge — are **not available** for these cars: the durable Car-Net command path we use doesn't recognise them (it answers "Unknown user"), and VW's MEB backend exposes no equivalent. You still get telemetry through the EU Data Act portal — just no control. Setup detects this and creates a **read-only entry** instead of failing, so it's a known limit, not a silent one.
- **CUPRA / SEAT remote commands are blocked by VW.** Online-services (OLA) access for these brands was revoked server-side in 2026 (HTTP 403); a re-login or app-version bump won't restore it. Data still flows via the EU Data Act portal. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act portal data is thin and varies by car.** VW publishes only a slice of fields today (often odometer + lock + charging, sometimes much more). It widens over time as VW expands the portal ahead of the Sept-2026 deadline — fields that read `unknown` today may fill in on their own, no change needed. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

---

## Install

**Via HACS (recommended):**

1. Open **HACS** in Home Assistant.
2. Search for **“VW Group Connect”** and install it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration → VW Group Connect** and follow the login flow.

<sup>Just merged into HACS default — if it isn't searchable yet, give the HACS index a little time to refresh, or add `its-me-prash/vwgroup-connect-ha` as a custom repository in the meantime.</sup>

**Login options** (pick what your car/brand supports):
- **Browser / device-code (passwordless)** — sign in on your phone or laptop, approve the device; no password stored. (Audi, Škoda, SEAT, CUPRA.)
- **Email + password** — required for Volkswagen EU and Porsche.
- **EU Data Act portal** — read-only fallback for all brands.

---

## What you get

- **Sensors:** battery SoC, range (electric / combustion / total), fuel level, odometer, temperatures, charging power/rate/type, charge target, trip stats & lifetime aggregates, service & oil-service intervals, software version, connection state, last seen, and more.
- **Binary sensors:** doors locked, doors/windows/trunk/hood/sunroof open, plug connected, charging, OTA update available, lights, vehicle online, departure timers, alarm.
- **Control:** lock/unlock, climate start/stop, charging start/stop, window heating, departure timers, set target SoC / temperature / max charge current, honk-and-flash, wake, refresh, find charging stations *(availability depends on brand & model)*.
- **Device tracker:** GPS position for the Home Assistant map.
- **Images:** vehicle renders where the brand provides them.

> 💡 **Energy dashboard:** the charged-energy sensor is `total_increasing`, so add it to the Home Assistant **Energy dashboard** directly, or wrap it in a `utility_meter` helper for daily/monthly charged-energy totals. Use the cumulative **charged-energy (kWh)** sensor for this — not the per-100 km efficiency sensors (those are averages, not meters).

---

## ABRP (A Better Routeplanner) live telemetry

You can push your car's live data to **[A Better Routeplanner](https://abetterrouteplanner.com/)** so it plans around your real state of charge. It's **opt-in and off by default** — nothing leaves your network until you turn it on and an upload actually runs.

**1. Get the two credentials.**

- **`token`** (per vehicle) — open the ABRP app → **Settings → your car → Live Data → "Generic" / other car** and copy the token it shows.
- **`api_key`** (developer key) — this is a partner/developer key issued by **iternio**, *not* something the app hands out. Request one from iternio (their developer/API-key request form). **We deliberately do not ship a key** — hardcoding one we don't own would be impersonation and would bake a non-owned secret into a public repo. Paste your own.

**2. Enable it.** Integration → **Configure** → scroll to the **ABRP** section → tick *Enable ABRP telemetry push* and paste both values. Both are stored masked and **never written to the log**.

**3. Automate the upload.** Import the shipped blueprint **"ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), pick your vehicle and its **ABRP data changed** sensor, and you're done. The blueprint uploads only when there's a genuinely new snapshot (the *ABRP data changed* binary sensor is the idempotent trigger — it resets after each successful send, so the same snapshot is never sent twice).

You can also call the **`vag_connect.abrp_send`** service directly (target a device or VIN; the api_key/token come from the options unless you pass them inline).

> 🔒 **Privacy:** the telemetry includes GPS. It only leaves your network when `abrp_send` runs (i.e. when *you* trigger it / enable the blueprint). What we send: state of charge, charging state, GPS, heading, energy + capacity, estimated range, ambient + battery temperature, odometer. What we deliberately **don't** send: anything we can't measure reliably (speed, HV pack voltage/current, state-of-health) — omitted rather than guessed.

---

## Support this project ❤️

This is a one-person project — and VW doesn't make it easy: every backend change means days of reverse-engineering to find a working path again. That persistence is what keeps it alive where established projects have given up. If it's worth something to you, you can support continued maintenance via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Thank you! 🙏

---

## Contributing

PRs welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md). The **Vehicle Data Scout** turns unknown API fields into a one-click, pre-filled bug report, so you can help improve coverage without reading code.

## License

[GNU AGPL v3.0-or-later](LICENSE) for the integration code. Mandatory attribution + name/trademark terms on use/fork: see [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream open-source attributions in [`NOTICE.md`](NOTICE.md).
