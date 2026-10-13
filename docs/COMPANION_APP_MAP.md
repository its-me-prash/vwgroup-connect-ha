# Volkswagen app map for the ADB Companion

> **Reference.** This is the screen-by-screen map of the VW app. The **[Companion design](COMPANION.md)** is the place to start: it covers
> the entities, polling, commands, limits and known issues. The baseline app is now **4.6.4**; the intro below and the tables that cite
> 4.3.2 are the original 2026-10-06 mapping, and 4.6.4 reads the same unless a row says otherwise.

A screen-by-screen map of the Volkswagen app (`com.volkswagen.weconnect` 4.3.2)
as the Companion channel sees it: what each screen shows, how the channel reaches
it, which app string keys identify it, and which Home Assistant field it feeds.

Sources:

- A live, read-only walkthrough of a Tiguan Life 1.5 l eHybrid on 2026-10-06
  (English app). Only navigation was tapped; nothing that acts on the car.
- The 2026-10-02 capture set of the same car (58 screens).
- Every dump attached to upstream issue #968:
  - WEZANGO: CUPRA Born, 8 screens.
  - kgroshert: e-Up! and ID.4, German, 8 screens.
  - plainmad: Golf GTE Mk8 on imperial units, 11 screens.
- String keys come from the 4.3.2 APK's `resources.arsc`.

**Rule for every mapping:** a companion value goes into the field the VW cloud
parser (`cariad/api/vw_eu.py`) fills for the same value, never into a field only
the EU Data Act portal fills.

**Reading this table:**

- *Mapped* means the channel reads it as of 4.11.0-6; `#N` is the PR that
  added or changed it.
- *Opt-in* reads run only while their switch on the VW Group Connect
  Settings device is on (Read departure times, Read driving data, …).
- *Not mapped* means it is shown in the app but not read.

Cached navigation readings expire after 24 hours without a successful screen
read. This tolerates temporary navigation failures and long refresh intervals
without keeping yesterday's parking position or warnings available indefinitely.
Affected entities expose `companion_read_at` (UTC), the time the app screen was
read, not when the car last sent data. Expiry adds no navigation, retry or car
request.

### When the driving data, parking position and Vehicle Health are read

These three opt-in reads are not walked on every poll. Their values can change
only when the car sends new data, so a poll that cannot have changed them keeps
the last reading. Their switches work as for every other read: on reads them on
the next poll, off drops their values.

| Read | Walked when |
|---|---|
| Driving data, parking position | a trip has ended: the overview's Driving data tile (`Last driven: … Average consumption: …`) changed; or the car sent new data and the electric or petrol range dropped since the last read, while not charging (two identical trips leave the tile as it was) |
| Vehicle Health (odometer, service, warnings) | the car sent new data (a trip end included) |

"The car sent new data" means the overview's *Synchronised … ago* time moved
past its rounding and then stood still for 10 minutes, so a car still sending
data on the move is read once it has parked. With the vehicle sync interval
on, each sync is new data.

All three are also read:

- on the first poll after a start or reload, and when their switch is turned on;
- every 12 hours, well before the 24-hour expiry above;
- driving data and the parking position, every 6 hours while the Driving data
  tile is not on the overview;
- on **Refresh app screen data**, and on the read that follows **Refresh vehicle data**.

Vehicle Settings shares the health switch but holds the charge limit, which can
change in the app at any time, so it is still read on every poll. Whether a
health warning can reach the app without a vehicle sync is open (gszigethy/vwgroup-connect-ha#78).

## Overview (Vehicle tab)

The overview is read on every poll; no tap is needed. Each tile narrates
itself as `<label>. <value>. <hint>`.

| Tile | Example narration | Field → entity | Keys | Status |
|---|---|---|---|---|
| Range | `Range overview. Battery range: 92 kilometres. Fuel range: 410 kilometres. Open details` | `electric_range_km`, `combustion_range_km` → Electric/Fuel Range | `acc_vehicle_tab_range_tile_value_*` | Mapped |
| Range, charging | `Range overview. Currently charging. Battery range: …` | `is_charging`, `charging_state` | `…_battery_currently_charging` | Mapped; a state, not the whole narration, since gszigethy/vwgroup-connect-ha#7 |
| Climate control | `Climate control. Off. Open details` (DE `Vorklimatisierung. Aus.`) | `climatisation_active`, `climatisation_state` | `acc_vehicle_tab_clima_tile_label`, `…_all_clima_on/_off` | Mapped by the app's keys (gszigethy/vwgroup-connect-ha#11); EN/DE regex as fallback |
| Vehicle (lock) | `Vehicle. Locked. Open details` | `doors_locked` → Doors Locked | `acc_vehicle_tab_label_lock_unlock_vehicle`, `…_state_locked/_unlocked` | Mapped by the app's keys (gszigethy/vwgroup-connect-ha#11); EN/DE regex as fallback |
| Horn and Turn Signals | `Horn and Turn Signals. Open details` | — | — | Not mapped (a command surface; never opened live) |
| Departure times | `Departure times. Open details` | — | — | See Departure times |
| Driving data | `Driving data. Last driven: 3.0 kilometres. Average consumption: 0 litres per 100 kilometres. Open details` | — | `acc_vehicle_tab_label_driving_data` | See Driving data |
| Vehicle Health Report | `Vehicle Health Report. Open details` | — | — | See Vehicle Health Report |
| Your vehicle | `Your vehicle: <model>. Synchronised 4 hours 4 minutes ago` | `companion_app_synced_at` → Last vehicle sync | `SYNC_*` | Mapped |

`binary_sensor.<car>_doors_locked` showing **off** while the app says *Locked*
is correct. It uses HA's LOCK device class, where off means locked.

## Range sheet (nav read `charge_detail`)

Tap the range tile; close with *Close sheet*.

| Row | Example | Field → entity | Status |
|---|---|---|---|
| `rangeArcBatterySoc` | `Charging status. Battery charge level: 83 per cent. Target charge level reached` | `battery_soc`, `charging_state`, `is_charging` | Mapped |
| Charging details | `Charging details. Target charge level: 80 per cent` | `target_soc` | Mapped |
| Power, speed, time | ID.4: 10 kW, 270 min | `charging_power_kw`, `charging_rate_kmh`, `remaining_charge_time_min` | Mapped |
| Charging method | `Charging method. Immediate charging. Change charging method` | `charge_mode` → Charging Mode (read-only sensor) | Mapped (gszigethy/vwgroup-connect-ha#13) |
| Start/Stop charging | CTA | `command_start/stop_charging` | Mapped (command) |

## Air Conditioning sheet and Settings (nav reads `climate_detail`, `climate_settings`)

These are covered in [COMPANION_CLIMATE.md](COMPANION_CLIMATE.md):

- **Sheet:** dial, mode, remaining minutes and the window-heating row.
- **Settings:** climate at unlock, window heating, without external power, and
  the zones (driver/passenger front zones on the Tiguan).

Since gszigethy/vwgroup-connect-ha#6 both screens are read on one walk.

## Vehicle (lock) sheet

On the Tiguan it shows only `Vehicle` / `Locked`: no doors, windows, bonnet or
boot. Nothing beyond the overview tile to read.

### Lock status is read-only (no lock/unlock)

On the companion channel the lock status is a read-only sensor
(`doors_locked`). Lock and unlock commands are deliberately not offered, for
security:

- Unlocking needs the S-PIN. It would have to be typed into the phone over ADB,
  and Home Assistant would have to store it.
- The app's lock control is a slider with no stable handle to target reliably.
- A wrong or misread tap sends the opposite command: unlock instead of lock.
- Repeated attempts risk an S-PIN lockout and spend the car's daily request
  budget.

If your brand's backend supports remote lock, use that channel instead.

## Departure times

Nav read `departure_times` (opt-in, gszigethy/vwgroup-connect-ha#15). Three timers. Each has a time
(`07:25 AM`), a recurrence (`Weekdays`, `Saturday`) and a `checkable` switch
(all off on the Tiguan). The climate target is in the description (`… chosen
temperature of 22.0°C`). Without timer data the app shows only the section
headers and `departure_timer_subscreen_climadeactivated_footer`. The charging
section needs charging locations set in the car; its preferred charging times
go with the charge mode *Charge at preferred times*. The optional
`charging_locations` read covers that section (see Charging locations).

| Value | Field → entity | Status |
|---|---|---|
| Timer on/off | `departure_timer_N_enabled` → Departure Timer N Enabled | Read from the switch's `checked` state (gszigethy/vwgroup-connect-ha#15); unknown when not read (gszigethy/vwgroup-connect-ha#10) |
| Timer time | `departure_timer_N_time` | 24-hour `HH:MM` (gszigethy/vwgroup-connect-ha#15) |
| Enabled count | `departure_timer_enabled_count` | When all three rows are on screen (gszigethy/vwgroup-connect-ha#15) |
| Weekdays | `departure_timer_N_weekdays` | From the timer's page (`cta_monday` … `cta_sunday`), app 4.6.4 |
| Repeat | `departure_timer_N_repeat` | From the timer's page (`cta_repeat`), app 4.6.4 |

Writes (VW, app 4.6.4; the switch also on 4.3.2), all through
`command_set_departure_timer`:

- **Departure Timer N** switch: taps the row's switch, which the app sends at
  once, and watches it for a flip back.
- **Departure Timer N — Time** entity and the `set_departure_timer` service: set
  the time, weekdays and Repeat on the timer's page one read-back tap at a
  time, then Save (one request). The app's Save switches the timer on, so an
  edit with `enabled: false` is refused; `enabled` may be left out. The
  service refuses `charging`, `climatisation` and `target_soc_pct`, and maps
  `one_off_day` (today to six days ahead) to a one-time timer on that weekday.
- A write needs all three rows read. A page edit also needs the timer's time
  to differ from the other two (the page shows no timer number), and the
  opened page's time must match its row. Anything unexpected before Save
  cancels the page; nothing is sent.

## Charging locations

Nav read `charging_locations`, controlled by **Read charging locations**
(`companion_read_charging_locations`, off by default). Verified from the VW
app 4.6.4 captures in `tests/fixtures/companion_charging_locations/`; 4.3.2
has not been verified. It shares the Departure times tile with
`departure_times`, so both opt-ins use one trip into that screen. It refreshes
when a trip ends, every 12 hours, and on Refresh app screen data / Refresh vehicle data.

Up to five locations are created in the car's infotainment. Slots `N = 1..5`
follow the list's top-to-bottom order; timers `M = 1..3` follow their page's
order. The reader swipes to reach lower rows and deduplicates by name. Two
visible rows with the same name stop the read, preserving the values already
read. Count, current location and clearing of removed slots require a full
list read with at least one location; partial walks preserve what they read.

An empty Charging section is not read as "no locations". Live 2026-10-10,
during a request-limit pause (App request status *restricted*), the app showed
no climate timers and no locations, only the section headers and the "First,
create your charging locations" text, on two phones, while the location was
still saved in the car. The app shows that same text when the car has none
(APK `DepartureTimerViewModel`: an empty profile list without a capability
status), so a walk that finds no rows leaves the last values as they are. A
car whose last location was deleted keeps the old values until a location
exists again.

The app itself also lags behind the car here: a location deleted in the car
stays in the app's list until the app is closed and restarted (observed live).
A vehicle sync, *Synchronise now* included, does not refresh the list. Until
the restart the walk reads the deleted location as before; with *close the app
after each read* on, the next poll starts the app fresh and picks it up.

| Value | Companion-only field → entity |
|---|---|
| Locations read | `charging_location_count` → sensor |
| Location the car is parked in (Active badge) | `charging_location_current` → sensor; `none` after a full read with no active location |
| Name | `charging_location_N_name` → Charging location N sensor |
| Car parked there | `charging_location_N_active` → binary sensor |
| Active departure times (app plural text) | `charging_location_N_active_timers` → sensor |
| Timer on/off | `charging_location_N_timer_M_enabled` → binary sensor |
| Timer time | `charging_location_N_timer_M_time` → sensor, 24-hour `HH:MM` |
| Timer recurrence | `charging_location_N_timer_M_weekdays` → sensor, HA codes such as `mon,tue,wed,thu,fri`; unknown labels leave it unset |
| Reduced AC charging current | `charging_location_N_reduced_ac_current` → binary sensor |
| Automatically release AC connector | `charging_location_N_auto_release_connector` → binary sensor |

All these entities are diagnostic and require an electric vehicle. Unread
fields stay `None`, so unread slots create no entities. A full read clears all
fields in slots beyond the locations found (never on an empty list, see above). The fixed `none` state has a
translation; location names are user text. These values never populate cloud
charging profiles, charge targets or vehicle-wide settings.

The walk taps only location **name text** and the structural settings icon to
the right of its toolbar title, then uses BACK. It verifies both the location
page title and the settings chip's name. It never taps the Active badge,
settings chip, switches, sliders or Save, and it never opens charging timer
pages: those timers always repeat and their labels contain the weekdays.
Labels come from the installed app's string and plural resources.

**Slider limitation:** Direct charging up to (0–50%) and Charging up to
(50–100%) are the VW design-system slider (`com.volkswagen.ui.selection.slider`),
which draws its notch labels with a `TextMeasurer` and sets no semantics, so
neither value is in the dump; FLAG_SECURE blocks screenshots. Other paths
checked on 4.6.4, none of which carries the values: the slider card's
`valueText` is never rendered, the info sheet is static text, the settings
fragment's arguments hold only the location id, the home-screen widget shows
range and fuel only, release builds log no HTTP bodies, and the app's external
files hold only a map cache. The EU Data Act catalogue defines
`profile_state_report.profiles[*].minimum_soc` / `target_soc`, but the Tiguan's
portal feed does not deliver them. Neither slider is mapped.

One indirect source: the charge sheet's *Target charge level* comes from
`GetVehicleTargetStateOfChargeUseCase`, which shows the active location's
`targetSOC_pct` when the app's remote flag `DisplayTargetSocEnabled` is on and
the car reports `supportsVehiclePositionedInProfileID`, and the vehicle-wide
value otherwise. On 2026-10-10 both were 80 %, so which one the Tiguan shows is
not confirmed yet; the companion still writes that sheet value and the vehicle
Settings slider into the same `target_soc`.

**Precedence (APK analysis):** the active location's settings apply while the
car is parked there; otherwise the vehicle-wide Settings apply. The app's own
text under vehicle Settings' *Charging up to* says so: "This setting does not
apply to charging sessions at specified charging locations." Immediate
charging ignores departure times. These rules describe the app's behaviour;
the reader only observes it.

## Driving data

Nav read `driving_data` (opt-in, gszigethy/vwgroup-connect-ha#16). The trip cards sit in a sideways
carousel; the second is drawn clipped (labels, no values) until one sideways
swipe.

| Card | Values | Fields | Status |
|---|---|---|---|
| Last single trip | date, time, distance, consumption (kWh/100 km and l/100 km), average speed, driving time | `last_trip_*` | Mapped (gszigethy/vwgroup-connect-ha#16), not date/time |
| From charging or refuelling | the same set | `refuel_trip_*` | Mapped (gszigethy/vwgroup-connect-ha#16), not date/time |
| Last long-haul trip | the same set | — | Not mapped |
| Month | average consumption | — | Not mapped |

Keys: `volkswagen_acc_cat_snowshoe_rts_*` labels and `volkswagen_cat_snowshoe_rts_unit*`
units; durations by `duration_hours` / `duration_minutes`.

## Vehicle Health Report (nav read `vehicle_health`)

| Row | Tiguan | Golf GTE (mi) | Field → entity | Key | Status |
|---|---|---|---|---|---|
| Total distance | `322 km` | `22,015 mi` | `odometer_km` → Odometer | `screen_vehiclehealth_subhead_totaldistance` | Mapped by key (gszigethy/vwgroup-connect-ha#8) |
| Next service | `711 days / 29,700 km` | `71 days / 12,100 mi` | `service_due_in_days`, `service_km` | `…_subhead_nextinspection` | Mapped, days and distance (gszigethy/vwgroup-connect-ha#8) |
| Next oil service | — | `71 days / 1,500 mi` | `oil_service_due_in_days`, `oil_service_km` | `…_subhead_oil_service` | Mapped, days and distance (gszigethy/vwgroup-connect-ha#8) |
| AdBlue range | — | — | `adblue_range_km` | `…_subhead_adblue_level` | Mapped (gszigethy/vwgroup-connect-ha#8), no dump yet |
| Warning header and categories | `No issues found` + 7 categories | same | `warning_active`, `warning_count`, `warning_messages` | `screen_vehiclehealth_overview_*` | Mapped (gszigethy/vwgroup-connect-ha#14); a warning layout not seen live yet |

## Vehicle Settings (nav read `vehicle_settings`)

| Row | Tiguan | Field → entity | Key | Status |
|---|---|---|---|---|
| Charging up to (50–100 %) | `80%` | `target_soc` + Charge Target number | — | Mapped (read and set) |
| Reduced AC charging current | off | — (`vw_eu` has amps, not on/off) | `vehiclesettingsscreen_reducedchargingspeed` | Not mapped |
| Automatically release AC connector | on | `auto_unlock_when_charged` → binary sensor | `vehiclesettingsscreen_automaticplugunlock` | Mapped (gszigethy/vwgroup-connect-ha#9) |
| Synchronise now | button | `command_sync_vehicle` → App sync interval number, Refresh vehicle data button | — | Mapped (command); the button syncs once, then re-reads the app after 3 minutes |
| Plug & Charge, users, notifications, contracts | links | — | — | Not mapped (account) |

## Other tabs

| Screen | Notes |
|---|---|
| Navigation tab | Map, find vehicle, parking marker, share (nav read `parking_position` → latitude/longitude). |
| Profile tab | Account, app settings, help, We Charge, wallbox, roadside assistance. Not read. |
| Authorised workshop, Digital extras | Text and offers. Not read. |

The **Read parking position** switch opts into opening Map, Find vehicle, the
parking marker and Share to read the coordinate preview; nothing is shared.
On app 4.6.4, this walk also taps **Agree** if the Google Maps consent appears,
only while that switch is on. Other reads and commands press BACK without
agreeing and stop that attempt, even if BACK reveals the overview. A missing
Agree button makes the walk back out and stop. Consent that remains after the
bounded dismissal attempts also stops the walk.

## Other brands in the #968 dumps

| Car | Overview read today | Detail screens |
|---|---|---|
| CUPRA Born (WEZANGO) | SoC 51, range 182, locked, ignition | Battery, max charge, battery management, climate, doors/lights captured; the CUPRA preset has no nav reads. |
| e-Up!, ID.4 (kgroshert, DE) | range, charging, locked, climate *Aus* | Charge sheet: SoC, target 90, 10 kW, remaining time; climate sheet. |
| Golf GTE Mk8 (plainmad, mi) | range (mi → km), charging, locked, climate on/off | Charge, climate (idle and active), health. |

## Stale entities on the companion entry

Three registered entities nothing in the current companion code fed were
removed from the HA registry on 2026-10-06: `sensor.<car>_vehicle_requests`
(left from the dropped betas), `sensor.<car>_vehicle_status`
(`vehicle_state`) and `binary_sensor.<car>_rear_window_heating`
(`window_heating_back`).

## Decisions (resolved 2026-10-06)

- **D1, departure times:** a new opt-in nav read (gszigethy/vwgroup-connect-ha#15).
- **D2, charge mode:** read into `charge_mode` with a read-only sensor (gszigethy/vwgroup-connect-ha#13).
  In the APK the charging method is set per charging location; *Charge at
  preferred times* charges only inside that location's preferred times,
  which are set in the infotainment.
- **D3, driving data:** a new opt-in nav read (gszigethy/vwgroup-connect-ha#16).
- **D4, health warnings:** read into the warning fields (gszigethy/vwgroup-connect-ha#14).
- **D5, stale entities:** removed.
