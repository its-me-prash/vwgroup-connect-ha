# Volkswagen Companion: Air Conditioning tile

This builds on Prash Balan's (@its-me-prash) Companion channel: its transport,
nav-read walk, overlay and rate-limit handling, version gate, and the existing
Home Assistant climate entities. It is a stand-alone change against upstream
`b13d764`. It needs no other PR, no add-on update and no new dependency.

## Home Assistant mapping

| App element | HA field → existing entity | Source on screen |
|---|---|---|
| Climate running | `climatisation_active` → climate entity, climatisation switch, binary sensor | `cta_start`/`cta_stop` id, then the row description / mode title |
| Window heating running on its own | `window_heating_front` → window heating switch | Picker title "Window heating" + `cta_stop`, or Mk8 `window_heating_description` |
| Target temperature | `target_temperature` → climate entity, number, sensor | Centre label of `clima_compose_view` (15.5 = LO … 30.0 = HI) |
| Outside temperature | `outside_temp` → sensor, climate current temperature | "<place>: 22°C" line |
| Remaining time | `climate_remaining_time_min` → sensor | " • N min" after "Active"; 0 when idle |
| Automatic window heating (setting) | `window_heating_enabled` → binary sensor | "Autom." on the sheet; `WindowHeatingEnabled` on Settings |
| Auxiliary air conditioning at unlock (setting) | `climate_at_unlock` → binary sensor | `ClimatisationAtUnlockEnabled` on Settings |
| Air conditioning using battery (setting) | `climate_without_external_power` → binary sensor | `ClimatisationWithoutExternalPowerEnabled`, where shown |
| Start / Stop | `command_start_climate` / `command_stop_climate` | `cta_start` / `cta_stop` |
| Window heating only | `command_start_window_heating` / `command_stop_window_heating` | Picker row 2, or Mk8 toggles, then `cta_start` |
| Set target temperature | `command_set_climate_temperature` | Tap the neighbouring dial label, one 0.5 step at a time |

The sheet is read by the existing `climate_detail` opt-in. The Settings sheet
is one tap deeper and has a new opt-in, `companion_read_climate_settings`, off
by default.

## How the app behaves (installed 4.3.2 APK)

- The Mk8 toggles and the "Select mode" picker only choose what Start will
  start. They are not state and changing them sends nothing.
- `cta_start` flips to `cta_stop` while air conditioning or window heating
  runs. After the app's request succeeds, the sheet closes itself.
- A dial change is sent by the app 1 s after the dial stops (debounced), while
  idle or running. Cars that only take a temperature at start lock the dial
  while running.
- The Settings sheet applies changes only on an explicit Save. This change
  reads it and never saves.
- Start can ask "Activate air conditioning using battery?" when unplugged.
  That changes a vehicle setting, so it is never confirmed automatically.

## Commands and safety

- **Shortest path.** Start and stop are two taps: the climate tile, then
  Start or Stop. The mode picker opens only to switch to or from
  window-heating-only. Each step waits only for the screen it expects, not for
  a generic settle. After the app closes the sheet itself, no walk back is
  needed. A command drops only the climate values from the cache: the overview
  tile, read on every poll, shows the new state, and no other detail path is
  re-walked.
- Commands are armed for app 4.3.2 only. Other builds are refused before any
  tap. Reads keep the preset's verified versions.
- Every step is read back:
  - a toggle's `checked` after tapping it;
  - the chosen picker row's title on the sheet;
  - the dial's centre after every step, and again after the debounce.
- A start or stop counts as accepted only when the app closes the sheet or
  flips the button. The next poll supplies the vehicle state.
- Start when running, stop when idle, and setting the current temperature send
  nothing. Stopping window heating while air conditioning also runs is refused,
  because the app's single Stop ends both.
- The channel's read-only option, rate-limit backoff and 60 s minimum interval
  all apply. Climate walks hold the same lock as polls, and the charge channel's
  lock where one exists.
- The walk returns with the app's own close controls. The overview anchor is
  now recognised by its id: on 4.3.2 the `rangeTile` container has no text, so
  the return walk could press Android BACK past the overview and leave the app.

## Language and version scope

- **Independent of language:**
  - running state, from the button id;
  - target and outside temperature;
  - the Settings switches;
  - every command step: toggles by id, mode by picker position verified
    against the row's own title, and the dial by geometry.
- **English/German only:**
  - the overview tile wording, already used upstream;
  - the "Active / Off / Autom." descriptions;
  - the "Window heating" mode title;
  - "min" in the remaining time.

  In other languages these few fields stay unknown. They are never guessed.
- German words come from captures, not the APK. The investigated phone has only
  the English split installed.

## Evidence and credits

Each fixture's contributor, original file, attachment and comment are listed in
[`sources.json`](../tests/fixtures/companion_climate/sources.json). Fixtures
keep only climate nodes, and the town in the outside-temperature line is
replaced with "Somewhere".

| Function | Capture and credit | Backtrace |
|---|---|---|
| Idle sheet is off although the AC toggle is checked (bug fix); toggle layout; dial and outside temperature | @plainmad, Mk8 Golf GTE, 4.3.2 `Climate Screen` | [#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5386248711) |
| Running state: `cta_stop`, "Active" / "Off" descriptions | @plainmad, Mk8 Golf GTE, 4.3.2 `Climate screen whilst active` | [#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5441678954) |
| Overview tile "Climate control. On" | @plainmad, Mk8 Golf GTE, 4.3.2 `Overview Climate On` | [#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5449476597) |
| Same ids on 4.2.1 | @plainmad, Mk8 Golf GTE, 4.2.1 `UI Climate` | [#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5306430728) |
| Picker layout, German, enabled | @kgroshert, ID.4, 4.2.1 climatisation screen | [#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5200485856) |
| Picker disabled, "Aus" | @kgroshert, e-up!, 4.2.1 climatisation screen | [#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5189757805) |
| German tile "Vorklimatisierung. Aus." | @kgroshert, ID.4, 4.2.1 main screen | [#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5183597867) |
| Picker layout, "Autom." window heating, "Select mode" order, Settings switches, overview anchor | @gszigethy, Tiguan 1.5 l eHybrid, 4.3.2, Android 10: live captures 2026-10-04 (equivalents of `07-climate.xml`, `47-climate-settings.xml`, `01-vehicle-main.xml` in the ZIP) | [#968](https://github.com/its-me-prash/vwgroup-connect-ha/issues/968#issuecomment-5950045566) |

@WEZANGO's CUPRA climate captures were reviewed and are not used. That is a
different app and preset, and its two buttons by the car image are seat heating.

The app behaviour above was read from @gszigethy's installed Volkswagen 4.3.2
APK (SHA-256 `81a3719746dfc7c3ac035afb1cac23b08a24155d7dd910a87432a6d60bdaa7b1`).
Classes: `ClimaViewModel`, `ClimaBottomSheetFragment`, `TemperatureSlider`,
`StartMode`, `ClimaSettingsViewModel`. No APK or decompiled code is
distributed.

## Validation boundary

- Live, read-only, on the Tiguan (4.3.2) through a local ADB CLI adapter. Both
  walks opened their sheets and returned with the app's own close controls:
  - `climate_detail` read off / 22.0 °C target / 20 °C outside / automatic
    window heating on;
  - `climate_settings` read climate at unlock off / window heating setting on.
- No climate command was sent to the real vehicle. Start, stop, window heating
  and temperature are covered by a fake phone that renders the captured layouts
  and reacts like the APK.
- This stays a draft until the owner runs one start, stop and temperature
  change on the car.
