<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>One Home Assistant integration for the Volkswagen Group brands — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Canada · Bentley</strong><br>
  <em>Direct API access, multi-channel with automatic fallback, no middleware.</em>
</p>

<p align="center">
  <a href="https://github.com/sponsors/its-me-prash"><img src="https://img.shields.io/badge/%E2%9D%A4%20Sponsor-ec6cb9?logo=github-sponsors&logoColor=white" alt="Sponsor this project"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Default-41BDF5.svg" alt="HACS Default"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha?include_prereleases" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL%20v3-blue.svg" alt="License"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2024.4%2B-blue" alt="Home Assistant"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  🌍 <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Previously published as **`vag-connect-ha`** (VAG = Volkswagen AG, standard DACH abbreviation).
> Turns out that abbreviation reads *quite* differently to English speakers 😅
>
> **What keeps working as before**: all entities (e.g. `sensor.audi_q4_battery_soc`),
> all service-calls (`vag_connect.lock`, `vag_connect.show_vag` etc.), all automations,
> the HACS install — **nothing breaks**. Marketing/display name changes, code internals
> stay unchanged. See [`MIGRATION.md`](MIGRATION.md).
>
> Huge thanks to the **Home Assistant UK** and **HA Ideas, Projects and Solutions**
> communities for the heads-up — especially **Si Gregory**, **Ben Johnson**, and **Evets David**.
>
> And a special shoutout to **Jordan Waeles**, whose `show_vag()` comment is now an officially
> supported easter egg in this integration (`vag_connect.show_vag` service, see CHANGELOG v2.2.3).

---

## What is this?

**VW Group Connect is a [Home Assistant](https://www.home-assistant.io) integration that brings connected-car data and control into your smart home for the Volkswagen Group brands — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/Canada and Bentley — from a single config entry.**

It surfaces battery & charging state, range, odometer, climate, doors & windows, location and more, and — where the brand's backend still allows it — sends remote commands such as lock/unlock, climate and charge control. To keep working through Volkswagen's 2026 API changes it speaks **several channels and falls back automatically** when one is blocked: the brand-native backends, the read-only **EU Data Act** vehicle-data portal, an opt-in `volkswagen.de` web channel, and a durable **passwordless** login for older Car-Net vehicles. It runs happily **alongside [evcc](https://evcc.io)** and needs **zero PyPI dependencies**.

> 🎉 **Now available directly in HACS** — no custom repository needed.

---

## Highlights

- **8 selectable Volkswagen Group brands** in one integration — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Canada, Porsche and Bentley.
- **Porsche-capable** — Porsche rides its own *Porsche Connect* backend, **not** the EU Data Act portal. The portal path structurally *excludes* Porsche, so portal-only tools can never cover it; this integration can.
- **Two-way control where the brand's backend allows it** — lock/unlock, climate, charging, target SoC. Read which brands have genuine command support in the table below; VW EU is read-only by default (see the honest note there).
- **Passwordless login option** (browser/device-code) for Audi/Škoda/SEAT/CUPRA — no password stored in Home Assistant.
- **Multi-channel with auto-fallback** — brand-native → EU Data Act portal → opt-in vw.de web → durable Car-Net. One channel going down doesn't take your data dark.
- **Resilient by design** — keeps last-known values through portal outages, filters bogus "no reading" sentinels, never lets the odometer jump backwards.
- **GPS device tracker**, 100+ entities across multiple platforms, 20+ service calls, multi-vehicle per account.
- **Vehicle Data Scout** — auto-detects API drift and offers a one-click bug report. **Quality Scale: Platinum.**

---

## Brand status

| Brand | Control | Data | Notes |
|---|---|---|---|
| **Audi** | ✅ Two-way | ✅ Full | myAudi backend (incl. ICE engine start/stop) |
| **Škoda** | ✅ Two-way | ✅ Full | native Škoda backend |
| **Porsche** | ✅ Two-way | ✅ Full | Porsche Connect — own backend, not the EU Data Act portal |
| **VW US/CA** | ✅ Two-way | ✅ Full | VW NA cloud (needs the US/CA country selector + S-PIN) |
| **VW EU** | 🔒 Read-only by default · ⚠️ commands = MBB **alpha** | ✅ Full telemetry via EU Data Act portal | See the honest note below — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Commands blocked by VW | ✅ EU Data Act portal | OLA access revoked server-side in 2026 — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ Two-way live-test gated | ✅ Login + read | My Bentley — runs on the Audi/IDK tenant |

> **Honest note on VW EU control.** Volkswagen EU vehicles are **read-only by default**: you get full telemetry through the EU Data Act portal, but no remote commands. Remote commands for VW EU exist **only as an experimental durable-MBB two-way ALPHA**, and only for **legacy MQB / Car-Net** cars — it's an opt-in toggle, **not** a default feature. **MEB / ID-family cars (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) have no command path at all** and are created read-only. The MBB alpha is tracked in **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testers welcome.

> In 2026 Volkswagen put parts of its API behind device attestation. This integration routes around it where possible (durable Car-Net login, EU Data Act portal, vw.de web) and is transparent about what each channel can and cannot do.

---

## Known limitations

A few things are **structural** — they come from how Volkswagen's backends work in 2026, not from the integration, and no setting fixes them:

- **VW EU is read-only by default; commands are an MBB alpha for legacy cars only.** See the brand note above. **MEB / ID-family cars are read-only** — the durable Car-Net command path doesn't recognise them (it answers "Unknown user"), and VW's MEB backend exposes no equivalent. Setup detects this and creates a **read-only entry** (with a repair notice) instead of failing, so it's a known limit, not a silent one. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT remote commands are blocked by VW.** Online-services (OLA) access for these brands was revoked server-side in 2026 (HTTP 403); a re-login or app-version bump won't restore it. Data still flows via the EU Data Act portal. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act portal data is thin and varies by car.** VW publishes only a slice of fields today (often odometer + lock + charging, sometimes much more). It widens over time as VW expands the portal ahead of the Sept-2026 deadline — fields that read `unknown` today may fill in on their own, no change needed. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

> **Where we stand.** Under the EU Data Act (Regulation 2023/2854), your car's data is *yours*. Running this integration on your own hardware is *you* accessing *your own* data (Article 4) — owed at the same quality the manufacturer serves itself, in real time where technically feasible. VW's read-only, hours-stale portal falls short of that today. This integration is deliberately **channel-agnostic**: the moment VW gives owners a real-time, control-capable interface — as the Data Act requires, and as some manufacturers already offer their owners — we'll support it here, for free, for everyone. We back your right to real-time access to your own car.

---

## Install

**Via HACS (recommended):**

1. Open **HACS** in Home Assistant.
2. Search for **"VW Group Connect"** and install it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration → VW Group Connect** and follow the login flow.

<sup>Just merged into HACS default — if it isn't searchable yet, give the HACS index a little time to refresh, or add `its-me-prash/vwgroup-connect-ha` as a custom repository in the meantime.</sup>

**Minimum Home Assistant: `2024.4.0`.**

### Login options (the setup wizard has two paths)

The integration's first screen offers **two** login methods. Pick the one your brand supports:

- **Browser / device-code (passwordless)** — *Audi · Škoda · SEAT · CUPRA.* Sign in on your phone or laptop and approve the device; no password is stored in Home Assistant (it keeps a real refresh token). This step also offers the optional **S-PIN** and scan interval.
- **Portal — email + password** — *Volkswagen EU · Porsche.* Enter your brand login. This step exposes a brand picker (Volkswagen EU, Porsche, and the other email/password brands), email, password, optional **S-PIN**, scan interval, and an **"enable MBB commands"** toggle (which only has an effect on Volkswagen EU — see [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). For **Volkswagen US/Canada** a **country selector (US vs CA)** appears here — it renders **only** for that brand and is not used by any other.

> The **EU Data Act portal is not a third login button.** It's the read-only strategy the coordinator automatically falls back to, and it can additionally be *added* as a supplementary read channel from **Configure → Options**. The same is true of the `volkswagen.de` web channel (an opt-in Options-only supplementary read channel).

### The S-PIN field — when you need it

The **S-PIN** is your brand app's security PIN. It's optional in the form and only required for some actions: it's needed for **VW US/Canada data reads and commands**, and for security-sensitive remote commands on brands that gate them behind the S-PIN. Leave it blank if your car doesn't ask for one.

---

### Volkswagen EU — getting your data flowing (important)

For Volkswagen EU, **logging in is not enough** — VW only streams vehicle data once *you* have switched on data sharing on VW's side. If your car shows up with no data (or doesn't show up at all), this is almost always the reason, **not** a wrong password. Do this once:

1. **Add the integration:** choose **Portal (email + password)** and pick **Volkswagen EU**, then log in.
2. **Complete any one-time prompt on VW's portal.** Open the VW data portal once in a browser or the brand app and finish whatever it asks: **accept terms, confirm consent, finish onboarding / region selection.** Headless access can't get past these — this is the `portal_interaction_required` case ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Grant data-sharing consent.** On the portal, set **"Use of non-personal data" = Granted** (the EU Data Act data-sharing consent).
4. **Don't go looking for a "continuous data request" switch — there isn't one.** The integration creates that request for each car itself. It registers a 1-month subscription on your VW account, which is **free**. Without a request the portal returns nothing for that VIN and the car shows up with no readings.
5. **Wait for the car to push a snapshot.** Even after all of the above, propagation takes time. The car can read **`offline` / `unknown` for a while — often until its next drive or wake, up to ~24 h** — before sensors populate. This is normal.

The portal initially serves only a **slice of fields**, and that slice **widens over time** as VW expands portal coverage ahead of the Sept-2026 deadline — fields that read `unknown` today may fill in on their own. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Full field list.** The complete official VW-Group data dictionary (every EU Data Act key -> field, description and unit) is in [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md).

> The Options toggle **`eu_data_act_auto_kickoff`** is what creates that 15-minute Custom Data Request, and it's **on by default** — in portal mode there's no data without one. Turn it off only if you'd rather manage the request yourself.

---

## What you get

- **Sensors:** battery SoC, range (electric / combustion / total), fuel level, odometer, temperatures, charging power/rate/type, charge target, trip stats & lifetime aggregates, service & oil-service intervals, software version, connection state, last seen, and more.
- **Binary sensors:** doors locked, doors/windows/trunk/hood/sunroof open, plug connected, charging, OTA update available, lights, vehicle online, departure timers, alarm.
- **Control:** lock/unlock, climate start/stop, charging start/stop, window heating, departure timers, set target SoC / temperature / max charge current, honk-and-flash, wake, refresh, find charging stations *(availability depends on brand & model)*.
- **Device tracker:** GPS position for the Home Assistant map.
- **Images:** vehicle renders where the brand provides them.

> 💡 **Energy dashboard:** the charged-energy sensor is `total_increasing`, so add it to the Home Assistant **Energy dashboard** directly, or wrap it in a `utility_meter` helper for daily/monthly charged-energy totals. Use the cumulative **charged-energy (kWh)** sensor for this — not the per-100 km efficiency sensors (those are averages, not meters).

### Services

The integration ships **20+ service calls** (`vag_connect.*`), many of them brand-specific — *availability depends on brand & model*. Among them: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi ICE), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` and `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send`, and the `show_vag` easter egg.

---

## ABRP (A Better Routeplanner) live telemetry

You can push your car's live data to **[A Better Routeplanner](https://abetterrouteplanner.com/)** so it plans around your real state of charge. It's **opt-in and off by default** — nothing leaves your network until you turn it on and an upload actually runs.

**1. Get the two credentials.**

- **`token`** (per vehicle) — open the ABRP app → **Settings → your car → Live Data → "Generic" / other car** and copy the token it shows.
- **`api_key`** (developer key) — this is a partner/developer key issued by **iternio**, *not* something the app hands out. Request one from iternio (their developer/API-key request form). **We deliberately do not ship a key** — hardcoding one we don't own would be impersonation and would bake a non-owned secret into a public repo. Paste your own.

**2. Enable it.** Integration → **Configure** → scroll to the **ABRP** section → tick *Enable ABRP telemetry push* and paste both values. They're validated as a pair (you'll get an error if only one is set), stored masked and **never written to the log**.

**3. Automate the upload.** Import the shipped blueprint **"ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), pick your vehicle and its **ABRP data changed** sensor, and you're done. The blueprint uploads only when there's a genuinely new snapshot (the *ABRP data changed* binary sensor is the idempotent trigger — it resets after each successful send, so the same snapshot is never sent twice).

You can also call the **`vag_connect.abrp_send`** service directly (target a device or VIN; the api_key/token come from the options unless you pass them inline).

> 🔒 **Privacy:** the telemetry includes GPS. It only leaves your network when `abrp_send` runs (i.e. when *you* trigger it / enable the blueprint). What we send: state of charge, charging state, GPS, heading, energy + capacity, estimated range, ambient + battery temperature, odometer. What we deliberately **don't** send: anything we can't measure reliably (speed, HV pack voltage/current, state-of-health) — omitted rather than guessed.

---

## Options (Configure)

From **Settings → Devices & Services → VW Group Connect → Configure** you can adjust:
scan interval, S-PIN (plus a per-vehicle S-PIN when the account has more than one car), reverse-geocoding, **read-only mode**, force PPE climate (Audi), push toggles (MQTT/FCM/Audi-VW), client-id override, **`eu_data_act_auto_kickoff`** (on by default), hide-empty-entities (default on), **ABRP** (enable + api_key + user token, validated as a pair), plus **add / remove** the `volkswagen.de` and EU Data Act portal supplementary read channels.

---

## Support this project ❤️

This is a one-person project — and VW doesn't make it easy: every backend change means days of reverse-engineering to find a working path again. That persistence is what keeps it alive where established projects have given up. If it's worth something to you, you can support continued maintenance via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Thank you! 🙏

---

## Contributing

PRs welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md). The **Vehicle Data Scout** turns unknown API fields into a one-click, pre-filled bug report, so you can help improve coverage without reading code.

## License

[GNU AGPL v3.0-or-later](LICENSE) for the integration code. Mandatory attribution + name/trademark terms on use/fork: see [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream open-source attributions in [`NOTICE.md`](NOTICE.md).
