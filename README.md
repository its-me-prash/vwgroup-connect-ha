<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>One Home Assistant integration for Volkswagen Group cars: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW and Audi US/Canada</strong><br>
  <em>Battery, charging, range, doors, climate and GPS location in Home Assistant. Direct API access, several read channels with automatic fallback, no middleware.</em>
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
  🌍 <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.it.md">Italiano</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a> · <a href="README.da.md">Dansk</a> · <a href="README.nb.md">Norsk</a> · <a href="README.fi.md">Suomi</a>
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

**VW Group Connect is a [Home Assistant](https://www.home-assistant.io) integration that brings your Volkswagen Group car into your smart home: battery and charging state, range, odometer, climate, doors and windows, GPS location and more, for Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley and the North-American VW / Audi accounts, all from a single config entry.**

Where the brand's backend still allows it, it also sends remote commands such as lock/unlock, climate and charge control. **That part is per brand, not universal:** Audi and Škoda are two-way, Volkswagen EU on the EU Data Act portal is read-only, and SEAT/CUPRA commands are blocked by the manufacturer. The table below says exactly which is which.

To keep working through Volkswagen's 2026 API changes it speaks **several read channels and falls back automatically** when one is blocked: the brand-native backends, the read-only **EU Data Act** vehicle-data portal, an opt-in `volkswagen.de` web channel (beta), an optional **Tibber** gap-fill, and a durable **passwordless** login for older Car-Net vehicles. It runs happily **alongside [evcc](https://evcc.io)** (see [docs/EVCC.md](docs/EVCC.md)) and needs **no add-on, broker or middleware container**. Home Assistant installs three small Python packages for it automatically; they are only used by the opt-in push and companion (ADB) channels.

> 🎉 **Now available directly in HACS** — no custom repository needed.

---

## Highlights

- **9 selectable Volkswagen Group brands** in one integration: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Canada, Audi US/Canada, Porsche and Bentley.
- **Two-way control where the brand's backend allows it**: lock/unlock, climate, charging, target SoC. This is **per brand, not universal**. Check the table below before you count on a command.
- **Škoda's in-car assistant "Laura" in Home Assistant (new in 3.0.0)**: ask about range, charging and trips as a service, or hand it to any conversation agent (the built-in Assist, OpenAI, Anthropic, Google, Ollama) as a tool it can call and chain. Read-only advice your automations can act on.
- **Logbook events, firmware & calendar cards (new in 3.1.0)**: manufacturer push notifications become a per-vehicle `event` entity (Logbook + automations, no YAML bus filter), a read-only firmware `update` entity surfaces OTA status (Škoda today, no Install button), and two `calendar` entities lay out the charging schedule + service due-dates.
- **Passwordless login option** (browser/device-code) for Audi, SEAT, CUPRA and Audi US/CA. No password stored in Home Assistant. Škoda moved to email + password in 3.0.1 when VW revoked its device-code grant.
- **Multi-channel with auto-fallback**: brand-native, EU Data Act portal, opt-in vw.de web, optional Tibber, durable Car-Net. One channel going down doesn't take your data dark.
- **Companion channel (experimental, opt-in)**: when every backend path is shut, the integration can read your car by driving the official app on a spare Android phone over ADB. Volkswagen is verified against a real device; the other brands are read-only until a screen map is confirmed. Modern phones need the [ADB Bridge add-on](https://github.com/its-me-prash/vwgroup-app-adb-bridge); nothing is rooted and no app tokens are read.
- **Resilient by design**: keeps the last known values and parking position through portal outages, filters bogus "no reading" sentinels, never lets the odometer jump backwards, and tells you when a failed login is the manufacturer's outage rather than your password.
- **You control the poll rate**: a per-account **poll-interval slider** (a Number entity, in minutes) that automations can drive, created for every setup including read-only portal ones.
- **GPS device tracker**, 100+ entities across multiple platforms, 30+ service calls, multi-vehicle per account, entity names in **12 languages**.
- **Porsche runs on its own backend**, not the EU Data Act portal. The portal path structurally *excludes* Porsche, so portal-only tools can never cover it. The command code lives here, but the Porsche login itself is currently experimental (see the table).
- **Vehicle Data Scout** auto-detects API drift and offers a one-click bug report — and from 3.0.0 its redacted diagnostics download carries the raw API responses too, so one attachment is everything needed to add support for a new field. **Quality Scale: Platinum.**

---

## Brand status

| Brand | Control | Data | Notes |
|---|---|---|---|
| **Audi** (EU) | ✅ Two-way | ✅ Full | myAudi backend (incl. ICE engine start/stop) |
| **Škoda** | ✅ Two-way | ✅ Full | native Škoda backend |
| **VW US/CA** | 🇨🇦 ✅ Two-way · 🇺🇸 ⛔ blocked by VW | 🇨🇦 ✅ Full · 🇺🇸 ⛔ | Canada signs in on its own server + app client and shows full data, confirmed on a live Canadian ID.4 ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **US: since 2026-08-13 VW enforces device attestation (Play Integrity) on the North-America plane, so US sign-in / token exchange hard-fails (401) — a VW-side wall an open-source client cannot satisfy off-device ([#1215](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1215)).** |
| **VW EU** | 🔒 Read-only by default · ⚠️ commands = Car-Net **beta** | ✅ Full telemetry via EU Data Act portal | See the honest note below ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Commands blocked by VW | ✅ EU Data Act portal | OLA access revoked server-side in 2026 ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Two-way live-test gated | ✅ Login + read | My Bentley, runs on the Audi/IDK tenant |
| **Porsche** | ⚠️ Experimental | ⚠️ Experimental | Porsche Connect, its own backend. Porsche moved to the *Porsche One* app, so **login is expected to fail on current accounts**. The command code is there but unreachable until the login is rebuilt ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi US/CA** | ⏳ Two-way live-test gated | ✅ Full | myAudi NA backend. US now reads from the regional `na` vehicle service and is **confirmed working on a live US Audi Q5** (58 entities) — thanks @pouwerkerk ([#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Canada uses the EMEA service. Commands inherit the Audi two-way paths but aren't separately live-confirmed on NA yet ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |

> **Honest note on VW EU control.** Volkswagen EU vehicles are **read-only by default**: you get full telemetry through the EU Data Act portal, but no remote commands. On **2026-08-18 VW disabled the login** the modern (CARIAD) two-way used, so that channel can no longer be set up. Remote commands for VW EU now exist **only as a durable Car-Net (MBB) two-way BETA**, and only for **legacy MQB / Car-Net** cars — an opt-in toggle, **not** a default feature. **MEB / ID-family cars (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) have no command path at all** and are created read-only. The Car-Net beta is tracked in **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testers welcome.

> In 2026 Volkswagen put parts of its API behind device attestation, and it has been tightening it through the year: **Volkswagen US stopped working on 2026-08-13** (Play-Integrity attestation on the North-America plane, [#1215](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1215)) and the **modern VW EU two-way login was pulled on 2026-08-18**. This integration routes around attestation where possible (durable Car-Net login, EU Data Act portal, vw.de web) and is transparent about what each channel can and cannot do. **Tip: run only one two-way integration per car — VW rate-limits accounts that several apps hammer at once, and a locked account also breaks the official app.**

---

## Known limitations

A few things are **structural** — they come from how Volkswagen's backends work in 2026, not from the integration, and no setting fixes them:

- **VW EU is read-only by default; commands are an MBB alpha for legacy cars only.** See the brand note above. **MEB / ID-family cars are read-only** — the durable Car-Net command path doesn't recognise them (it answers "Unknown user"), and VW's MEB backend exposes no equivalent. Setup detects this and creates a **read-only entry** (with a repair notice) instead of failing, so it's a known limit, not a silent one. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT remote commands are blocked by VW.** Online-services (OLA) access for these brands was revoked server-side in 2026 (HTTP 403); a re-login or app-version bump won't restore it. Data still flows via the EU Data Act portal. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act portal data is thin and varies by car.** VW publishes only a slice of fields today (often odometer + lock + charging, sometimes much more). It widens over time as VW expands the portal ahead of the Sept-2026 deadline — fields that read `unknown` today may fill in on their own, no change needed. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **VW EU cars have no live GPS position over the EU Data Act portal.** Volkswagen Group Info Services has [confirmed in writing](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13#issuecomment-5359744122) that the portal's continuous-export Data Dictionary lists a *Vehicle Location Tracking* cluster but **no defined data point for the car's current coordinates** (latitude / longitude) — so a VW EU car read only through the portal shows its location as `unknown`. This is a limit of VW's dataset, not the integration, and the manufacturer app's position endpoint has been closed to third parties. North-American VW / Audi and other brands with a working position endpoint are unaffected. ([#923](https://github.com/its-me-prash/vwgroup-connect-ha/issues/923))
- **North America: VW and Audi both read now — Audi commands are the last unconfirmed piece.** **VW US/CA works, including Canada**, confirmed against a live Canadian ID.4: Canada signs in on its own server, and since the data-envelope fix it shows full telemetry ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **Audi US/CA now reads too**: US pulls from the regional `na` vehicle service, confirmed on a live US Audi Q5 (thanks @pouwerkerk, [#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Canada uses the EMEA service. Commands inherit the Audi two-way paths but aren't separately live-confirmed on North-American accounts yet ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)).
- **Porsche login is expected to fail right now.** Porsche retired the *My Porsche* app this integration authenticates against in favour of *Porsche One*. Reads and commands are implemented, but you probably can't get past the login until that is rebuilt. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Push (near-real-time) updates are an opt-in BETA, off by default.** The MQTT (Škoda) and Firebase (Audi/VW, CUPRA/SEAT) channels are wired but not live-validated, and the brands increasingly gate them behind app attestation, which cannot be satisfied off-device. Leave them off unless you want to help test. Normal polling is the supported path.

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

- **Browser / device-code (passwordless)** for *Audi, SEAT, CUPRA and Audi US/CA*. Sign in on your phone or laptop and approve the device; no password is stored in Home Assistant (it keeps a real refresh token). This step also offers the optional **S-PIN** and scan interval.
- **Portal, email + password** for *Volkswagen EU, Škoda, Volkswagen US/CA, Bentley and Porsche (experimental)*. Enter your brand login. This step exposes a brand picker, email, password, optional **S-PIN**, scan interval, and an **"enable MBB commands"** toggle (which takes effect on Volkswagen EU and, experimentally, on legacy Car-Net Audi, see [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). For **Volkswagen US/Canada** a **country selector (US vs CA)** appears here; it renders **only** for that brand and is not used by any other.

> The **EU Data Act portal is not a third login button.** It's the read-only strategy the coordinator automatically falls back to, and it can additionally be *added* as a supplementary read channel from **Configure → Options**. The same is true of the `volkswagen.de` web channel (an opt-in beta, Options-only, read-only) and the optional **Tibber** channel, which fills gaps the first-party channels left empty and never overwrites fresher data.

### The S-PIN field — when you need it

The **S-PIN** is your brand app's security PIN. It's optional in the form and only required for some actions: it's needed for **VW US/Canada data reads and commands**, and for security-sensitive remote commands on brands that gate them behind the S-PIN. Leave it blank if your car doesn't ask for one.

---

### Volkswagen EU — getting your data flowing (important)

For Volkswagen EU, **logging in is not enough** — VW only streams vehicle data once *you* have switched on data sharing on VW's side. If your car shows up with no data (or doesn't show up at all), this is almost always the reason, **not** a wrong password. Do this once:

1. **Add the integration:** choose **Portal (email + password)** and pick **Volkswagen EU**, then log in.
2. **Complete any one-time prompt on VW's portal.** Open the VW data portal once in a browser or the brand app and finish whatever it asks: **accept terms, confirm consent, finish onboarding / region selection.** Headless access can't get past these — this is the `portal_interaction_required` case ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Grant data-sharing consent.** On the portal, set **"Use of non-personal data" = Granted** (the EU Data Act data-sharing consent).
4. **Don't go looking for a "continuous data request" switch — there isn't one.** The integration creates that request for each car itself, and it is **free**. Since v2.29.0 the request is created **without an expiry date**; earlier versions asked for one month, which is why some setups quietly went silent after about four weeks. If your data stopped and you set the account up before v2.29.0, remove the account from the integration and add it again once so a fresh request is created. Without a request the portal returns nothing for that VIN and the car shows up with no readings.
5. **Wait for the car to push a snapshot.** Even after all of the above, propagation takes time. The car can read **`offline` / `unknown` for a while — often until its next drive or wake, up to ~24 h** — before sensors populate. This is normal.

The portal initially serves only a **slice of fields**, and that slice **widens over time** as VW expands portal coverage ahead of the Sept-2026 deadline — fields that read `unknown` today may fill in on their own. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Full field list.** The complete official VW-Group data dictionary (every EU Data Act key -> field, description and unit) is in [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). A weekly workflow watches the portal's dictionary page and opens a pull request when VW publishes a newer version, so the table doesn't quietly go stale.

> The Options toggle **`eu_data_act_auto_kickoff`** is what creates that 15-minute Custom Data Request, and it's **on by default** — in portal mode there's no data without one. Turn it off only if you'd rather manage the request yourself.

---

## What you get

- **Sensors:** battery SoC, range (electric / combustion / total), fuel level, odometer, temperatures, charging power, charge rate (always in km/h, converted for you if your car reports miles per hour) and charge type, charge target, per-charge-session history (energy · duration · start · AC/DC, on Škoda and SEAT/CUPRA), trip stats & lifetime aggregates, service & oil-service intervals, software version, connection state, last seen, and — on Škoda — last fill-up, current pay-to-park session, service reminders, departure timers and preferred charge mode, and more.
- **Binary sensors:** doors locked, doors/windows/trunk/hood/sunroof open, plug connected, charging, OTA update available, lights, vehicle online, departure timers, alarm.
- **Control:** lock/unlock, climate start/stop, charging start/stop, window heating, departure timers, set target SoC / temperature / max charge current, honk-and-flash (with a choice of duration, and lights-only or horn as well), wake, refresh, find charging stations, camping mode and active ventilation (Škoda cabin airing without heating) *(availability depends on brand & model)*.
- **Device tracker:** GPS position for the Home Assistant map. A poll that comes back without coordinates keeps the last known parking position instead of losing it.
- **Images:** vehicle renders where the brand provides them.
- **Events, updates & calendars (new in 3.1.0):** a per-vehicle push-`event` entity (manufacturer notifications in the Logbook + automations), a read-only firmware **update** entity (Škoda OTA status — no Install button, the car flashes itself), and **charging-schedule + service calendars** that lay the timers and due-dates on a timeline.
- **Settings:** a per-account **poll interval** slider in minutes, so an automation can poll more often while you're driving and back off overnight. It exists on every setup, read-only portal entries included.
- **12 languages:** entity names are fully translated into English, German, French, Spanish, Italian, Dutch, Polish, Czech, Swedish, Danish, Norwegian and Finnish.

> 💡 **Energy dashboard:** the charged-energy sensor is `total_increasing`, so add it to the Home Assistant **Energy dashboard** directly, or wrap it in a `utility_meter` helper for daily/monthly charged-energy totals. Use the cumulative **charged-energy (kWh)** sensor for this — not the per-100 km efficiency sensors (those are averages, not meters).

### Services

The integration ships **30+ service calls** (`vag_connect.*`), many of them brand-specific — *availability depends on brand & model*. Among them: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi ICE), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (auxiliary / parking heater — SEAT/CUPRA, Škoda, and VW/Audi on a two-way command channel, where the car is equipped), `send_destination` (SEAT/CUPRA/Škoda) and `update_charging_settings` (SEAT/CUPRA), the Škoda `ask_assistant` (see below), `set_location_target_soc` and `set_seat_heating`, `open_app`, `execute_vehicle_action`, `abrp_send`, and the `show_vag` easter egg.

---

## evcc

[evcc](https://evcc.io) can take your car's state of charge, range and charging status straight out of Home Assistant, so solar-surplus charging plans around the real battery instead of a guess. Nothing extra runs inside this integration: evcc reads Home Assistant's own REST API. The **read** path works on **every brand**, including read-only VW EU / portal cars. The **write** path (`chargeEnable`) only works on a two-way car (Audi or Škoda with a live command channel) and only when evcc treats the car itself as the charger. With a real smart wallbox the read path is all evcc needs.

Ready-made `evcc.yaml` recipes and the one-time setup are in [docs/EVCC.md](docs/EVCC.md). This connector is **beta**.

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

## iOS Live Activity — charging countdown on the Lock Screen

A native **Live Activity** (Lock Screen + Dynamic Island) that counts down to your car finishing its charge, with a state-of-charge progress bar. The integration already exposes an **absolute** *charge target time* (`sensor.*_charge_target_time`), so iOS can tick the countdown on its own — no per-second push.

**Import the shipped blueprint** *"Live Activity — EV charging countdown (iOS)"* (`blueprints/automation/vag_connect/live_activity_charging_countdown.yaml`), pick your vehicle's charging / SoC / charge-target-time sensors and your phone's `notify.mobile_app_*` service. It starts when charging begins, refreshes as the ETA and SoC move, and clears when charging stops.

> 📱 **Requirements:** the Home Assistant Companion app with **Live Activities** enabled (iOS 17.2+, HA Core 2026.7+). Live Activities are currently a **Labs** feature in the app's **TestFlight** build — enable them under Labs. A Live Activity needs a token handshake between the app and Home Assistant, so your phone has to be able to reach HA (locally or via a remote connection) when charging starts. This ships now so you're ready the day it leaves TestFlight.

---

## Škoda AI assistant ("Laura") — new in 3.0.0

MyŠkoda's own in-car assistant, **Laura**, is available inside Home Assistant.
Ask her about range, charging and trips with the `vag_connect.ask_assistant`
service (she returns a text answer you can notify, speak, or branch on), or hand
her to a **conversation agent** — the built-in Assist in LLM mode, or OpenAI /
Anthropic / Google / Ollama — as a tool it can call and chain (ask Laura → then
`send_destination` to the car). She is **read-only, advisory, and Škoda only**;
it's a **beta**, so feedback on answer quality is welcome.

Setup, the voice ("ask Laura …") trigger, and ready-made example automations —
including *car arrives home → top up + preheat + speak the range* — are in
**[docs/AI_ASSISTANT.md](docs/AI_ASSISTANT.md)**.

---

## Options (Configure)

From **Settings → Devices & Services → VW Group Connect → Configure** you can adjust:
scan interval (also available live as the poll-interval slider), S-PIN (plus a per-vehicle S-PIN when the account has more than one car), reverse-geocoding, **read-only mode**, force PPE climate (Audi), push toggles (MQTT/FCM/Audi-VW, all opt-in beta and off by default), client-id override, **`eu_data_act_auto_kickoff`** (on by default), hide-empty-entities (default on), **ABRP** (enable + api_key + user token, validated as a pair), plus **add / remove** the supplementary read channels: `volkswagen.de` (beta), the EU Data Act portal, **Tibber**, and the experimental **companion phone** channel.

---

## Support this project ❤️

This is a one-person project — and VW doesn't make it easy: every backend change means days of reverse-engineering to find a working path again. That persistence is what keeps it alive where established projects have given up. If it's worth something to you, you can support continued maintenance via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Thank you! 🙏

---

## Contributing

PRs welcome, see [`CONTRIBUTING.md`](CONTRIBUTING.md). Common questions are answered in [docs/FAQ.md](docs/FAQ.md). The **Vehicle Data Scout** turns unknown API fields into a one-click, pre-filled bug report, so you can help improve coverage without reading code.

## License

[GNU AGPL v3.0-or-later](LICENSE) for the integration code. Mandatory attribution + name/trademark terms on use/fork: see [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream open-source attributions in [`NOTICE.md`](NOTICE.md).
