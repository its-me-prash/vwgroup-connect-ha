# Volkswagen Companion battery tile

This change builds on Prash Balan's (@its-me-prash) Companion transport,
screen selectors, navigation, and Home Assistant entity model. It is a single
battery feature against upstream `b13d764`; it does not require another PR,
an add-on update, an APK decoder installed in HA, or a new Python dependency.

## Home Assistant mapping

| App value/control | Existing HA field/entity | Behaviour |
|---|---|---|
| Electric range | `electric_range_km` sensor | Battery range only; miles converted to kilometres for HA's unit system. |
| Battery % | `battery_soc` sensor | Actual battery percentage, separate from the charge target. Enable the existing charge-detail read option when the overview omits it. |
| Petrol range | `combustion_range_km` sensor | Read separately from electric range. Evidence of petrol range unlocks the existing PHEV/combustion entities. |
| Charging state | `charging_state` sensor and `is_charging` binary sensor | Target reached is not active charging; translated resource states map to consistent values. |
| Upper charge limit | `target_soc` sensor | Optional: shown on the Tiguan and ID.4 captures, absent on the Mk8 Golf GTE. |
| Set the charge limit | Existing `target_soc` number, `command_set_target_soc` | The "Charging up to (50-100%)" slider on vehicle Settings: 50 … 100 % in 10 % steps, then Save. See below. Only app 4.3.2 is armed. |
| Start/Stop charging | Existing charging switch and charging services | Open battery detail, match the requested CTA, tap once, and return. Only app 4.3.2 is armed. No climate command is enabled. |
| Power, speed, remaining time | Existing charging sensors | Filled only where the app exposes them. Spoken units, zero/one plural forms, and the period in “hours and. …” are handled. |

Charge-detail reads retain their existing explicit opt-in and cadence.
Commands retain the HA read-only setting, app-version gate, rate-limit backoff,
and minimum interval. Polls and commands share a screen lock. Disabled CTA
hints are checked because Compose can report `enabled=true` even when the
button's description says to check charging status. A tap is not a confirmed
vehicle result: cached pre-command details are cleared and later polling must
provide the real state. Real vehicle command testing is still pending.

## Also fixed

- **Charging switch.** The HA charging switch now follows the parsed
  `is_charging` flag and uses the raw state words only when a channel leaves the
  flag unset. This is the rule the climatisation switch already follows.
  "Currently charging" and "Target charge level reached" read correctly.
- **Overview anchor.** It is recognised by its resource-id. On 4.3.2 the
  `rangeTile` container has no text of its own, so the old check never matched,
  and the walk back after a command could press Android BACK past the overview
  and out of the app. The Air Conditioning PR carries the same fix, byte for
  byte, so either PR can land first.

- **Plug safeguard.** The coordinator's "unplugged means not charging"
  safeguard (fix #32) now acts only on a known `plug_connected=False`. The
  companion cannot see the plug and leaves it `None`, which used to reset a
  live charging reading to off.
- **Command readback.** After a charge command only the charge sheet's own
  cached values are dropped, and only that path is re-read on the next poll.
  The other opted-in paths (Vehicle Health, map, …) keep their cadence, so a
  command never triggers a walk through every screen.

## Charge limit (vehicle Settings)

The existing charge-limit number entity is offered with the slider's own
range, 50 … 100 % in 10 % steps; a value in between is rounded to the nearest
step (75 → 80).

- **Path.** Overview → the Settings row → the slider → Save → the app's back
  arrow. The Settings row is matched by the installed translation of
  `acc_vehicle_tab_label_settings` plus the "Open details" hint, with the
  existing English/German pattern as the fallback.
- **No pixels from one phone.** The slider (`GradientSlider`, a Material
  `Slider`) has no node in the UIAutomator tree. Its neighbours do, and the
  installed 4.3.2 layout fixes the track between them: `subtitle` sits 40 dp
  from the screen edge, which gives the scale on the phone itself; the track
  starts 6 dp after `subtitle` and ends 26 dp before `value`; `value` is
  centred on it. This was checked against the slider's real bounds
  (`dumpsys activity top`) at display densities 320, 420 and 560 on the
  Tiguan phone: the prediction is within 1 px every time, for track widths of
  776, 680 and 550 px.
- **Read back before sending.** Moving the slider sends nothing; the app keeps
  the value on screen and shows Save (`vwd_save_button`). Each slider tap is
  read back from the row's own "NN%" and corrected if the slider landed on
  another step. If it does not reach the target in three taps, the app's X
  cancels the change and nothing is sent.
- **Save is the command.** The 60 s interval, the rate-limit backoff, the
  read-only option and the version gate apply to it. The change counts only
  when the app finishes "Synchronising ..." and leaves edit mode showing the
  new value; otherwise the command fails and says so.
- **Battery Care note.** Above the Battery Care target the app may show a
  one-time note over the row. It asks nothing; one BACK closes it and the row
  must be back before Save is pressed.
- **Already set.** Asking for the value the slider already shows sends
  nothing.

## When the car refuses more requests

Each remote request wakes the car and spends part of a daily power budget that
protects its 12 V battery. When it is used up, the 4.3.2 app answers a tap
with an alert instead of the screen: "Too many requests sent to the vehicle"
(daily power budget, backend error 4295) or "Request limit reached" (HTTP
429). Both say starting the car makes everything available again.

The alert titles are read from the installed app's translation tables
(`alert_daily_power_budget_title`, `dialog_maxrequests_headline`,
`dialog_maxrequest_bff_error_headline`), so they are recognised in any app
language; "Request limit reached" is also added to the existing English
fallback. Seeing one trips the channel's existing 12 h backoff, closes the
alert, and the command fails with a reason that says to start the car. The
integration's Reset companion connection button clears the pause.

## Language independent matching

On direct ADB and the ADB Bridge's existing `/shell` transport, HA reads the
installed app's `resources.arsc` tables, including language splits, using
Android's `pm path`, `unzip`, `gzip`, and `base64`. Stable resource **names**
identify battery/fuel range, percentages, target, states, and CTA labels. The
matching templates come from the installed translations, so the algorithm
does not need a branch or manually translated regex for each language.
Decoded labels are cached in memory and refreshed on app-version changes or
hourly. Root, account tokens, and app-private files are not accessed.

The live test used the installed English 4.3.2 build. German contributor
captures validate the existing fallbacks; synthetic translated labels test
that the resource mechanism does not rely on English/German words. This is
not a claim of live validation in every locale. Unsupported resource-table
entries and missing extraction commands fail closed. The current relay agent
cannot supply resource tables and retains its existing language fallbacks;
the agent is not a dependency of this PR.

## Why the visible petrol % cannot be presented on this PHEV

@gszigethy's Tiguan overview visibly shows **410 km petrol range and 49%**,
but its UIAutomator hierarchy contains only the range. Static inspection of
the same installed Volkswagen 4.3.2 APK explains the discrepancy:

- `VehicleRangeStatusMapper` builds the PHEV's `VehicleRangeViewState.Hybrid`
  description through `e(...)`, using charging state, electric distance,
  petrol distance, and the Open details hint. It does not include the fuel
  percentage.
- `RangeTileKt.b(...)` supplies this description as merged tile semantics.
  The percentage is rendered visually from the combustion range view state,
  but does not become a separate accessible numeric node.
- The APK contains `acc_vehicle_tab_range_tile_value_petrol_level`, and this
  reader can map it to `fuel_level` if a layout actually exposes that template.
  The current PHEV layout does not. A compiled template is not a live value.

Therefore this vehicle's petrol percentage stays unavailable through ADB.
We do not hard-code 49%, estimate percentage from 410 km, or substitute battery
percentage. Petrol range supplies the requested useful HA reading. Recovering
the drawn percentage would need another data source or a separate image-reading
feature; neither is required by this PR.

## Evidence and contributor credits

All 43 comments and all 28 XML/ZIP attachments in upstream issue #968 were
retrieved. The battery regression fixtures retain only relevant UI nodes and
Close controls. Each fixture's original filename, contributor, attachment,
and comment URL are recorded in
[`sources.json`](../tests/fixtures/companion_battery/sources.json).

| Function | Capture and credit | Backtrace |
|---|---|---|
| PHEV electric/petrol range, separate 70% current / 80% target, 2 kW, 11 km/h, 55 minutes, Immediate charging and Stop CTA | @gszigethy, Tiguan 1.5 l eHybrid, VW 4.3.2, Android 10; ZIP `01-vehicle-main.xml`, `04-range.xml` | [#968 capture ZIP](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5950045566) |
| Current 80%, target 80%, Target charge level reached, disabled Start hint | @gszigethy, supplemental 2026-10-04 ADB charge dump and live read; `tiguan_target_reached.xml` is a local supplemental capture, not a file from the earlier ZIP | [#1684 context](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1684) |
| Imperial electric/petrol separation, stopped SoC, idle Start CTA, optional fields absent | @plainmad, Mk8 Golf GTE, VW 4.3.2; Overview and Charging Screen attachments | [#968 idle captures](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5386248711) |
| Active 40%, Stop CTA, 2 hours and. 15 minutes | @plainmad, Mk8 Golf GTE, VW 4.3.2; Charging screen (Whilst charging) | [#968 active captures](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5441678954) |
| German spoken kilometre range on a BEV | @kgroshert, ID.4, We Connect 4.2.1; main ID.4 attachment | [#968 overview captures](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5183597867) |
| German active 34%, 90% target, 10 Kilowatt, 4 hours and. 30 minutes | @kgroshert, ID.4, We Connect 4.2.1; charging-screen ID.4 attachment | [#968 charging captures](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5200485856) |
| Charge limit slider row, Settings entry, geometry at densities 320/420/560 | @gszigethy, Tiguan, VW 4.3.2, Android 10; local supplemental captures 2026-10-04 (`tiguan_overview_settings.xml`, `tiguan_settings*.xml`; same screen as `27-settings.xml` in the ZIP) and `dumpsys` slider bounds | [#968 capture ZIP](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5950045566) |
| German active 13%, 4 hours and. 5 minutes; target/power absent | @kgroshert, e-up!, We Connect 4.2.1; charging-screen e-up! attachment | [#968 e-up! captures](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5189757805) |

@WEZANGO's CUPRA captures and @Philip-Wiege's version reports were also
considered in the issue inventory. This PR changes Volkswagen battery
mapping only; it does not claim validation or command support for those cars.

The small resource-label fixture was extracted from @gszigethy's installed
Volkswagen 4.3.2 APK on 2026-10-04. The slider's range and step, the track
inset, Save-only sending, the Battery Care note and the Save outcome were read
from the same APK (`item_vehicle_settings_slider`, `GradientSlider`,
`BaseSlider`, `VwToolbar`, `VehicleSettingsViewModel`). APK SHA-256:
`81a3719746dfc7c3ac035afb1cac23b08a24155d7dd910a87432a6d60bdaa7b1`.
English split SHA-256:
`fce8359cc63d03b83926fee6ab4138e9a44912a9ba22aa38fa4272027fb18f21`.
APKs and decompiled application code are not distributed in the repository.

## Validation boundary

The implemented channel was exercised read-only on the live phone, using the
same screen/resource methods through a local ADB CLI adapter: 96 km electric,
410 km petrol, 80% battery, 80% target, Target charge level reached, charging
false, and 71 installed resource keys. This did not deploy anything to HA or
validate a running HA entity update. The CLI adapter does not verify the
`adb-shell` TCP connection or Bridge HTTP transport end to end.

Fixture tests cover parsing and HA model/switch behaviour; fake-phone tests
cover Start/Stop navigation, version changes, disabled controls, command
serialization, transport failure, repeat protection, and resource-table
formats. The charge-limit walk was run live, read-only: it opened Settings
with one tap, found the row at 80 % and the track at 122–802 px (the slider's
real track is 121–803), and returned with the app's back arrow. Fake-phone
tests cover every step at all three densities, a drifted layout corrected by
the read-back, an unreachable target cancelled unsaved, the Battery Care note,
an unconfirmed save, a foreign-language Settings row, and the version gate.
No charging command or charge-limit Save was issued to the real vehicle. The PR stays
draft until the owner can test with the car ready for charging.
