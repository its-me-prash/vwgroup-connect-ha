# Changelog

All notable changes are documented here. / Alle wesentlichen Änderungen werden hier dokumentiert.

Format: [Keep a Changelog 1.0.0](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning 2.0.0](https://semver.org/)

> 📖 **Bi-lingual convention (v1.12.3 → v2.4.0 — DE-primary)**: section-titles were **DE / EN** joined by ` / ` and body content was German-only. Past entries are preserved as-is for historical accuracy.
>
> 📖 **Bi-lingual convention (v2.4.1+ — EN-primary, switched 2026-05-23)**: section-titles are now **EN / DE** joined by ` / `, body content is **English-primary** with German callouts where the original context was DACH-specific (Facebook-group threads, German tester names, brand-specific German terminology). The project's GitHub audience + the new "VW Group Connect" branding both lean international — English-primary makes the changelog readable for non-DACH users while keeping the DACH community's voice visible. Translations of individual body texts are available on request via [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md) — same pattern.

## Semver-Regeln für dieses Projekt (pre-1.0.0)

| Was | Version | Beispiel |
|---|---|---|
| Breaking Change, Architekturwechsel | `0.MINOR.0` | 0.10.0 → 0.11.0 |
| Neue Features, neue Sensoren/Services | `0.MINOR.0` | 0.10.0 → 0.11.0 |
| Bugfix, kleine Enhancement | `0.MINOR.PATCH` | 0.11.0 → 0.11.1 |
| Ab v1.0.0 | Standard `MAJOR.MINOR.PATCH` | 1.0.0 → 1.1.0 |

> **Hinweis:** Die Versionen 0.9.0–0.14.0 wurden am 2026-04-11/12 mit falschen
> Semver-Typen vergeben. Retroaktive Korrektur:
> `0.9.0→0.8.1`, `0.10.0→0.8.2`, `0.11.0→0.9.0`,
> `0.12.0→0.10.0`, `0.13.0→0.10.1`, `0.14.0→0.11.0`
>
> **v1.19.1 historischer Hinweis (2026-05-07 Audit):** v1.19.1 hat
> einen neuen Sensor `requests_remaining_today` eingeführt — nach
> strikter Semver-Regel wäre das MINOR (`v1.20.0`) gewesen, nicht
> PATCH. Wurde als PATCH released für HACS-Continuity (User-Side
> kein Breaking Change). Tag bleibt v1.19.1; nachfolgende Releases
> v1.20.0+ zählen ab v1.19.4 → v1.20.0 als legitime MINOR-Bumps.
> Lessons-learned dokumentiert für v1.20.2+ Audit-Disziplin.

---

> 💡 **Für Entwickler / Contributors:** Vollständige technische Detail-Notes
> für v1.8.6+ findest du in [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md)
> — mit jeder geänderten Datei, jeder Zeile, jeder Issue-Referenz und der
> Methodik dahinter.

## [Unreleased]

### Fixed
- **Porsche login follows the Auth0 resume step instead of giving up (experimental).** In Auth0's identifier-first flow the password step does not redirect straight to the app callback: it returns a resume URL that has to be followed before the authorization code appears. The login required the callback immediately, so it always ended in "wrong credentials or captcha" even when the credentials were right, a failure of our own regardless of any app migration. It now follows the resume hop (relative or absolute, bounded so it cannot loop) through to the code. Porsche stays experimental and still needs a Porsche owner to confirm the full login end to end.
- **Ten of the eleven translations were missing the companion-channel strings.** Home Assistant does not fall back to English for a custom integration, so a key that exists only in English renders as the raw key or as nothing at all. The twelve strings added with the companion channel and the export-file import had reached German only, which left the add-on checkbox, its error message, the two companion option toggles and the three import error messages blank for everyone running Home Assistant in French, Spanish, Italian, Dutch, Polish, Czech, Swedish, Danish, Norwegian or Finnish. All twelve are translated now, and a test fails the build if a language ever falls behind again.

### Changed
- **An identity token from the portal export no longer enters field discovery.** The export carries `idp_idt`, which identifies the account holder rather than anything about the car, and it was reaching the Vehicle Data Scout as an unmapped field. Only the token masker kept its value out of a public issue. It is now withheld from discovery entirely, so it can never end up in an entity attribute, a backup or a diagnostics download. This is a deliberate single exception to the rule that every discovered field stays visible until mapped, it is scoped to one named field, and each withholding is logged.

### Fixed
- **The companion channel could not read the range off the Volkswagen app.** The app narrates its units in words, so the overview tile reads "Batteriereichweite: 253 Kilometer", while the selector required the symbol "km". On those cars the channel reported itself healthy and read no range at all. Grounded in two accessibility dumps from We Connect 4.2.1, an ID.4 and an e-up. Thanks to kgroshert for the dumps.
- **A reading of zero no longer makes a sensor disappear.** The parsers read the same quantity under several field names and took whichever answered, which quietly skipped a legitimate zero. That is the value that matters most: a service interval of 0 km means due now, an empty tank reports 0 km of range, a flat battery reports 0 %, and 0 degrees is an ordinary winter morning. Each of those arrived as "no reading at all", so with hide-empty-entities on the sensor vanished at the moment it was worth looking at. Worse, the combustion and battery capability flags were derived from the same collapsed value, so a tank showing 0 km made the car count as not-a-combustion-car and took every combustion entity with it. Affects SEAT and CUPRA most, plus Skoda ranges, VW US/CA odometer and charge power, and the VW EU brake-service intervals.

## [2.29.0] - 2026-08-04

### Fixed
- **A charge level that flipped between two numbers now settles (#957, #1002).** The portal export sometimes carries the same reading twice inside one snapshot with different values and nothing to tell them apart, so the sensor jumped between them on a car that was neither driven nor charged, and the charge target did the same. Deciding inside the file does not work, because the obvious tie-breaker is duplicated too. The integration now compares the candidates against the last reading it already had and keeps the one that fits, so a car that is genuinely charging is still followed and only the impossible jump is dropped. Nothing changes on a poll where the export was unambiguous.
- **Charge power and charge rate are no longer a tenth of the truth on some cars (#1022, #1002).** The feed uses two encodings for the same number and we only understood one of them, so cars sending the plain value had it divided by ten: 10.4 kW showed as 1.0. Both encodings are now recognised.
- **The terms-and-conditions message points at the right place (#1027, #465).** Two Audi owners were stuck at a consent page after having accepted everything in the brand app, because the data portal asks separately. The message named only the app, so they went looking in the wrong place. It now names both and says that accepting in one does not cover the other.
- **Queued climate-timer changes are counted on Audi firmware too (#1030).** That firmware ships the same queue under a different name, so the sensor stayed empty.
- **The portal feed no longer expires after four weeks.** Every feed was created with a one-month duration, so roughly four weeks after setup the data quietly stopped: no error, no warning, just sensors that stopped moving while the integration reported itself healthy. The feed is now requested without an expiry date. If a portal ever refuses that, we still ask for the month rather than end up with no feed at all.

### Added
- **Battery calibration sensors (#1020).** Cars that ask for a high-voltage battery calibration now report it: the request and its two escalation steps, the method being asked for, and whether an attempt failed. Seven diagnostic sensors, off by default, in all twelve languages.

## [2.28.0] - 2026-08-01

### Added
- **The vehicle-signal service can now choose duration and horn (#1009).** The manufacturer app's signal screen lets you pick how long the car signals and whether the horn joins in, and `flash_lights` only ever sent a fixed ten-second flash. It now takes an optional duration (10, 20 or 30 seconds) and signal type (lights only, or horn and lights). Leaving both out does exactly what it did before, so nothing changes for existing automations. Volkswagen and Audi honour both settings and Skoda honours the horn; on the remaining brands the values are not documented in their apps, so they are accepted and ignored rather than guessed at. Thanks to Kimmy42-J for the request.

## [2.27.0] - 2026-08-01

### Added
- **The companion channel can now run through the ADB Bridge add-on (#968).** On a phone running Android 11 or newer, the only way in is wireless debugging, which needs a TLS handshake and a pairing step that the built-in connection cannot do. It reaches the phone and fails, which is as far as most people got. The [ADB Bridge add-on](https://github.com/its-me-prash/vwgroup-app-adb-bridge) bundles the real tooling and does the pairing, and the integration can now talk to it instead: tick "Connect through the ADB Bridge add-on" when you add the companion channel, and give the add-on's address instead of the phone's. Everything after that is unchanged, including the read-only quarantine, so an older phone still connects directly exactly as before. Thanks to plainmad for testing the add-on and reporting precisely where it stopped.

## [2.26.3] - 2026-08-01

### Fixed
- **A backend hiccup no longer makes every entity look broken.** The integration has always been meant to keep showing a car's last known values through a short outage, with the "last updated" timestamp telling you how old they are. That tolerance never actually applied when the whole poll failed, which on a single-car account is any brief error at all, so entities went unavailable immediately instead. They now stay visible with their last known values, exactly as intended, and still disappear once the data is genuinely too old.
- **A sensor whose value changes type no longer breaks.** When a manufacturer turns a number into a text value (CUPRA once changed the max charge current to "maximum"/"reduced"), the affected sensor used to break outright. Each case was patched individually after someone had already hit it. Any sensor that expects a number now simply reports unknown and logs why, so one changed field cannot take an entity down.
- **A brief portal error during startup no longer costs you the setup.** Listing your cars gave up on the first server error, while the very same call already retried three times if the connection timed out instead. Both are now retried the same way. If the portal is genuinely down the result is unchanged.

### Added
- **A charge target for cars that only report a battery-care limit.** Some cars (the Audi Q4 e-tron is the known one) send a battery-care charge ceiling and no separate charge target, so the target sensor stayed empty even though the car does have a limit. That ceiling now fills the target when nothing else provides one, and it is still shown separately as before.

## [2.26.2] - 2026-08-01

### Fixed
- **The "Visit" link on the car's device page works again (#1001).** The Volkswagen, Skoda and SEAT links pointed at owner pages those brands have since renamed, so the button led to a 404. All brand links were re-checked and the dead ones now point at pages that exist.
- **The saved volkswagen.de session no longer sends one host the wrong cookie.** VW reuses a few cookie names across its two sign-in hosts with different values for each. Restoring the saved session pushed every cookie to both hosts, so for those names whichever one was written last won on both and one host always got the wrong value. Names that differ per host are now restored only to the host they came from; everything else, including the single sign-on cookie that makes the silent resume work, is unchanged.
- **SEAT and CUPRA doors could still read "open" on a locked car.** When the car reports locked but the (sometimes stale) door positions still say open, the integration trusts the lock and forces the doors closed. That safeguard was written before the v2.23.2 open/closed correction and was missed by it, so it forced them to the wrong value and every per-door sensor showed "Open" on a locked car. It now writes closed, as its own log line always claimed. A second, dormant path that reads the older flat door format had the same leftover inversion and is fixed too, and the tests for both now drive the real parser instead of a copy of the logic, which is why this went unnoticed for so long.
- **Resuming the extra volkswagen.de session no longer gives up on a longer sign-in chain.** The silent resume sends exactly the same request as the interactive login, but it allowed only half as many redirect hops and reported the resulting failure as a generic, redacted error. If the sign-in chain gets longer at VW's end, the resume would fail while a fresh login still worked, and the log would not say why. It now uses the same budget as the login and reports a clear "re-authentication needed" instead.

## [2.26.1] - 2026-07-29

### Fixed
- **Volkswagen Canada sign-in reaches the right host again (#990, #915).** v2.26.0 sent Canada to its own regional host (ca00) for everything, including the login. That was half right: the vehicle data does live on ca00, but the login does not, and ca00 has no working authorize endpoint, so Canadian setup started failing at the login step with an HTTP 400 (before v2.26.0 it got past the login and failed later with a 500). A Canadian owner confirmed the official app signs in on the shared North America identity host, so the login now goes back there (as it did in 2.25.0) while only the vehicle data stays on ca00. Thanks to vrouleau for the capture and the details.

## [2.26.0] - 2026-07-27

> This release is about the companion (ADB) channel from 2.25.0, and it changes nothing for anyone not using it. Two things stand out: the Volkswagen screen-reading is now grounded against a real, independently verified reference instead of our own guesses, and CUPRA reads real data for the first time thanks to a contributor's screen dump. Command sending on the companion channel is paused for now — see below.

### Changed

- **Volkswagen companion reads are re-grounded against a verified reference.** The words we looked for on screen (state of charge, range, charge target) were our best guess and did not actually match what the We Connect app shows. They are now aligned with a real-device reference, so the values read reliably. The old wording is kept as a fallback, so nothing that already worked stops working.
- **CUPRA now reads real data.** Thanks to a screen dump a CUPRA owner shared (#968), the app's actual layout is known: it shows the numbers as bare values without the labels we were looking for, so the previous version read nothing. It now reads charge, range, lock state and engine state, plus how long ago the car last synced. Still read-only until an owner confirms the command screens.

### Added

- **Charge target on Volkswagen (opt-in).** The charge target, live power and remaining time live on a detail screen you have to open, so reading them means the integration briefly navigates there in the app and comes back. Because that taps the phone, it is off by default and runs at most every 15 minutes when on. Turn it on under the companion entry's options once you have confirmed it behaves on your phone.
- **Wake screen to poll, sleep after (opt-in) (#974).** A new companion option that wakes the phone's display for the read and puts it back to sleep afterwards, so a locked or sleeping phone shows the app without you having to keep the screen on permanently.
- **"Reset companion connection" button.** Clears a stuck back-off (after a failure run or an app rate-limit) and reads again immediately, instead of waiting the back-off out.
- **Bidirectional (V2G) charging usage sensors (#981).** For cars that support vehicle-to-grid, eight new diagnostic sensors surface the usage accounting the car keeps: energy dispensed, charge cycles, operating hours and quota, each with its limit. Disabled by default. Values are shown as-is (the data source does not state a unit, so none is invented).
- **Import a data-export ZIP you downloaded yourself (#702).** If a car is not enrolled in the EU Data Act portal, the connector has nothing to fetch for it, so the existing import brought nothing back. A new service, `import_export_file`, lets you point the connector at the ZIP you downloaded from the VW data portal by hand: it parses the file exactly the way the portal path does and fills in only the empty values, never overwriting live data. Put the file in your Home Assistant config folder (or another allowed folder) and give the service its name plus the VIN.

### Fixed

- **Setting up the companion channel on a modern phone now tells you what to do.** On an Android 11+ phone the direct ADB connection fails with a cryptic error, because that phone uses wireless debugging (TLS + pairing) which the built-in connection cannot speak. Instead of a generic "could not connect", the setup now recognises that case and points you at the companion add-on (older phones still connect directly). The setup screen says the same.
- **The off-peak charge reason is read again on cars that report it in a sub-block (#978).** Some cars nest `profile_charge_reason` inside a `charging_state_report` container; that spelling was being flagged as an unknown field instead of filling the existing sensor. Now handled.
- **A companion rate-limit now survives a restart.** If the app shows a "too many requests" screen the channel backs off for hours, and that back-off is now remembered across a Home Assistant restart — a real account lockout should not be cleared just by restarting the way a brief network blip is.
- **Volkswagen Canada now uses its own regional backend (#915).** Canada was being sent to the US host, which returns HTTP 500 for a Canadian car. A Canadian owner captured the official app and it talks to the Canada host (`ca00`) directly — the host is built from the country code at runtime, so it never showed up in a static scan of the app, which is why we had it pointed at the US host. Canada now goes to its own host. (If your Canada login still fails after this, a fresh log would show what the Canada backend wants next — it could not be worse than the 500 it returned before.)
- **Setup no longer hangs on the best-effort prefetches (#909).** After reading your cars, the integration warms a few caches (capabilities, static info, command availability) and kicks off the Data Act data request. These are meant not to block setup, but they were being awaited during it, so a slow or flaky backend could leave the entry stuck on "still setting up" for a long time (and Home Assistant kept retrying). They now run in the background once setup has returned; entities appear right away from the restored snapshot and these fill in a moment later.
- **The map marker no longer disappears when the volkswagen.de sign-in expires (#984).** On a car whose GPS comes only from the extra volkswagen.de channel, an expired session meant there were no coordinates, so the tracker was never created — and an existing one eventually got cleaned up by Home Assistant, breaking maps and automations that pointed at it. The tracker is now kept whenever that channel is set up: it simply reads unavailable while the session is expired and fills back in once you sign in again, instead of vanishing.

> **Note on Volkswagen commands (climate / charge start-stop).** These are paused on the companion channel in this release. They never actually worked: the app needs a two-step tap (open a tile, then press the button on the detail screen) that the old code did not do, so a command could only ever fail silently. Rather than ship buttons that do nothing, the companion Volkswagen entry is read-only for now; the command path returns once the two-step flow is confirmed on a real car. The network command paths (QR / portal / MBB) are unaffected.

## [2.25.0] - 2026-07-27

> The companion (ADB) channel that was briefly pre-released as 3.0.0a1 ships here in the stable line instead. It is still opt-in and experimental, and it changes nothing unless you set it up: if you do not pick it in the hub menu, the integration behaves exactly like 2.24.2.

### Added

- **Companion phone (ADB) channel — experimental, opt-in.** A fourth source in the hub menu at the start of setup, next to the QR login, the portal login, and MBB. It drives the official manufacturer app on a spare Android phone over ADB and reads the values off the screen, so it works as a last-resort two-way path on cars where the network side is read-only. There is no separate login and no credentials are stored: the phone is already signed in, nothing is rooted, and no app tokens are read. The integration only reads the screen and taps buttons.
  - **Volkswagen is verified** (built and tested against the We Connect app 4.2.1): it reads state of charge, range and charging state, and can start/stop climate and charging.
  - **Audi, Škoda, SEAT and CUPRA ship read-only for now.** The structure is there, but their on-screen maps are not yet confirmed against a real device, so they read what they can and refuse to tap a button rather than risk hitting the wrong control. They switch to two-way once a tester with that car confirms the screen map.
  - Safety built in: a write quarantine that disables taps whenever the app version on the phone differs from the one a preset was verified against (reads keep working), and a cooldown after a connection failure so a sleeping phone never turns into an error storm.
  - Needs a spare Android phone signed into the brand app with ADB over Wi-Fi, and the app language set to German or English. See the tracking issue to set it up and to volunteer as a tester for the non-VW brands.

### Fixed

- **The extra volkswagen.de channel no longer loses its session on every restart (#966, #632).** After you added the channel with the email code, its sign-in cookies were never saved back as they refreshed, so every restart replayed the original ones until they expired and the channel reported "SSO session expired, full re-login required" even though it had been working moments earlier. The refreshed cookies are now stored the same way the standalone volkswagen.de mode already did, so the session carries across restarts. (This is the standalone channel's twin; the main channel was already fine.)
- **A car that is currently sending a "no reading" placeholder no longer re-reports the same field as new on every poll (#958, #969, #970).** Some readings, most visibly tyre pressures, come through as a placeholder meaning "no value right now" when the car has nothing to report. Those fields are already mapped, so the placeholder was being flagged as an undiscovered field over and over. It is now recognised as the mapped field it is: the sensor stays unavailable until a real value arrives, and the repeated reports stop. Genuinely unknown fields still surface for mapping exactly as before.

## [2.24.2] - 2026-07-27

### Fixed

- **A command the car declines now explains itself instead of looking like a crash.** When the gateway refuses to hand over the list of services a car offers, the resulting "not available on this vehicle" was thrown at Home Assistant in a form it does not recognise, so pressing a button produced an "Unexpected exception" with a full traceback. The explanation was there the whole time and was being thrown away. It is now shown as a normal, readable message. The same thing was already fixed for the S-PIN check a while back and simply never carried over to this one.
- **A single unlucky rejection no longer keeps a working car quiet for half a day.** When the gateway explicitly says the account is not authorised for a car, that is a decision only you can change in the brand app, so we stop asking for twelve hours. That was also being applied to any other rejection, including ones that are merely temporary, so one bad response could silence a perfectly fine car until the next day. Those now back off for half an hour and recover on their own.
- **Two readings stopped being reported as "undiscovered" on every single poll (#959, #960, #961, #963).** Both were already being read correctly, but the bookkeeping never recorded that, so the same one-line report kept coming back and there was nothing anyone could do about it. One affected an opening state (three people filed the identical report within a day, and the report could not identify which opening it referred to because around ten of them share the same name). The other affected cars that send a measurement's quality marker without the measurement itself. Nothing was ever suppressed to achieve this, the fields are simply accounted for properly now.
- **The log no longer floods when SEAT or CUPRA online services are blocked (#779).** One poll asks around nineteen addresses, and each refusal wrote its own warning, so a blocked account produced roughly twenty identical lines every few minutes for something the owner cannot fix. The retry is routine and is now quiet. The single clear error and the repair notice are unchanged.
- **A volkswagen.de channel that stops resuming now says why.** Previously only the error type was logged, so an expired sign-in, a redirect loop and an outage looked identical and reports arrived with nothing to work from. Note this is the already-added channel; adding a new one was fixed in v2.24.1. Unknown errors still have their details held back deliberately, because some of them carry the sign-in address including access tokens.
- **The historical import service says what happened.** It reported nothing at all in several completely different situations: no export requested yet, the portal still preparing the file, an empty file, or a successful read where every value was already up to date. All four now say so plainly in the log.
- **Two log lines that were still in German are now English**, like the rest of the log.

## [2.24.1] - 2026-07-27

### Fixed

- **Your car's recorded values are no longer wiped when a restart happens during a backend outage (#702).** If the very first data fetch after starting Home Assistant came back empty, the integration wrote that emptiness over everything it had saved, and the next poll then made it permanent. So a car that the portal was quiet about lost its history on every restart, and importing an older export was pointless because the next restart deleted it again. The periodic polls have been protected against this for a while; the fetch that runs at startup was not, and now is. A brand new car still appears normally on its first setup.
- **A parking position that is being kept during an outage now says how old it is.** Keeping the last known position when the backend answers without coordinates is deliberate, since a parked car has not moved. But it was being kept indefinitely and with nothing to indicate its age, so a position from last week looked exactly like one from a minute ago. It is now kept for at most a day, the map entry carries the time the car itself reported that position, and the address is kept and dropped together with the coordinates instead of leaving a half-filled location behind.
- **Parking lights and parking brake no longer read as "on" when the car says they are off.** Some cars send a flag that only means "this section of the report is present" alongside the real reading. That flag was being trusted first, so a car reporting both parking lights explicitly off, or the parking brake explicitly released, was still shown as on or engaged. The real reading now wins. Cars that send nothing but the flag are unaffected.
- **Adding the volkswagen.de channel now says why it failed.** Every failure was reported as a wrong password and nothing was written to the log, so an expired session, a redirect loop and an actual typo all looked the same and none of them could be told apart. The reason is now logged, exactly like the equivalent step during initial setup already did.

## [2.24.0] - 2026-07-26

### Added

- **Two new battery-care sensors on EU-portal cars (#938, #947).** The portal ships a score for how well the battery charging care mode is being used, plus the threshold it's measured against. Both are diagnostic and off by default, and they have no unit because the data dictionary doesn't give one.

### Changed

- **We identify as the current We Connect app version again.** One of the two places that announce the VW app version had drifted two releases behind the other, so the integration was introducing itself with two different app versions depending on which channel it used. Both now say 4.2.1, which is what the live app sends. Nothing else about the app changed.

### Fixed

- **Audi US / Canada email and password login: found the actual reason it never worked (#13).** The token step was being sent to Audi's identity server directly, and that endpoint requires a client secret which Audi's app-style login simply does not have, so it always came back as "invalid client". The exchange now goes through the North-American backend that does accept it. This also explains why adding a secret never helped: the endpoint was wrong, not the credential. The QR login was unaffected and keeps working the way it did. Still needs a confirmation on a real US or Canadian Audi before it can be called done.
- **VW Canada sign-ins no longer get blamed on your password when VW is having an outage (#915).** If VW's own login server answered with a server error, the integration told you your credentials were wrong and opened a login prompt that could never succeed. It now says plainly that this is a problem on the manufacturer's side and retries on its own. A genuinely wrong password is still reported as such.
- **The start_climate_control service works on Audi PPE cars again (#912).** The "force PPE climate" option was only being applied to the simple climate start, so the service with the richer options kept sending a target temperature that PPE cars reject, and the whole command failed. Both paths now respect the option.
- **Charging speed is no longer about ten times too high, and it respects the unit your car uses (#931).** One of the charge rate readings was published exactly as the portal sent it instead of being scaled, and a car reporting miles per hour was shown as if the number were km/h. Both are corrected, so the sensor now means what it says.
- **A car the VW gateway refuses to describe is no longer asked about on every single poll (#909).** That refusal is about how the car is registered to your account and cannot change by itself, so it is now remembered for a while and explained once in the log instead of repeating the same warning every few minutes. On top of that, a setup that fails on something only you can fix (pending terms, missing consent, two factor, wrong password) now asks you to sign in again instead of retrying forever in the background.
- **The integration's own rate-limit pause is no longer treated as a backend failure (#933).** When it deliberately pauses to protect your account from being locked out, that is normal and temporary, so it no longer counts as an error worth escalating.
- **A missing position no longer wipes your car's last known location (#923).** When the backend answers without coordinates, the previous parking position is kept instead of the car jumping to an unknown location until the next good poll.
- **Ambient temperature and parking brake stopped showing up as "new fields" every poll (#938, #947).** Some cars send those two readings under a doubled-up name. The value was already being read, but the doubled spelling kept getting reported as undiscovered. Nothing changes on the entities themselves.
- **A sign-in that lands on a proxied login page no longer risks a confusing server error.** The integration now takes the client identifier from the page it actually landed on instead of assuming it matches the one it started with. North American VW logins go through a proxy that uses its own identifier, and guessing wrong there produced a server error that looked like an outage.
- **Settings groups we cannot map yet no longer hide their own contents (#843, #868).** A group of settings was being filtered out together with everything inside it, which meant a diagnostic sent in to help map those settings could not actually contain them. The group itself stays quiet, but the individual settings inside it are visible again, so they can be mapped from a real report.
- **The window-heating command queue no longer counts as an unknown field (#934).** It's the same pending-command list the charging and climate blocks already have, so it's now recognised as such instead of being reported.

## [2.23.3] - 2026-07-24

### Fixed

- **VW US / CA logins that returned "no vehicles" despite a successful sign-in now find the car (#503, #659).** The North-American garage response nests the vehicle list differently for some (e.g. Canadian) accounts, and the parser was looking in one fixed spot. It now walks the whole response to find your vehicle wherever it sits. A genuinely empty account still reports empty.
- **The charge-mode selector no longer appears in read-only mode.** It sends a command, so like the other command entities it's now hidden when the integration is running read-only.
- **Audi/VW render images show a localized name.** The seven fixed render viewpoints (side/angle/large/small…) were showing their hardcoded German label in every language; they now use the translated name.

### Changed

- **Fewer duplicate diagnostic sensors.** Six sensors that mirror another sensor's value from a second source (two max-AC-current variants, the charging-block HV min/max temperature clones, and the EU-portal battery-care and energy-flow twins) are now diagnostic and disabled by default. Nothing is removed — existing setups keep them, and the primary sensor of each pair stays enabled.

## [2.23.2] - 2026-07-24

### Fixed

- **SEAT and CUPRA per-door sensors were showing open/closed backwards.** The individual door binary sensors on SEAT/CUPRA cars stored "closed" where the rest of the integration means "open", so a closed door read as open and vice-versa. They now match the correct convention.
- **Eight climate/connection/power binary sensors had no name.** A handful of entities (climate zones, "Connection active", the daily-power-budget and low-battery warnings) had their name filed in the wrong place internally, so they showed up unnamed. They now have proper names in all 12 languages.
- **French, Spanish, Dutch, Polish, Czech and Swedish are now fully translated.** Around 70 entity names were still showing in English in those six languages while the others were translated. They're now complete.
- **The vehicle-render image entity now shows a localized name** instead of a hardcoded English "Vehicle Render".

## [2.23.1] - 2026-07-23

### Fixed

- **Door, window and light sensors now show localized names.** The per-part door / window / light binary sensors hardcoded their English names ("Door Front Left", "Trunk", "Light left"…), so they stayed English even in a German (or French, Spanish, …) Home Assistant while their neighbours were translated. They now use proper translation keys with names in all 12 languages ("Tür vorne links", "Kofferraum", "Licht links"…). Entity IDs are unchanged, only the display names.

### Changed

- **Clearer message when the account has no vehicle yet.** When login works but the manufacturer lists no vehicle, the setup error used to say "No vehicles found. Check credentials and network." — which is misleading, since the credentials are fine. It now explains the real common causes: a VW data-sharing request still propagating, or a primary-user ("Hauptnutzer") re-confirmation that the brand app requires after you change your S-PIN or account settings.
- **Fewer duplicate range and fuel sensors.** On a single-energy car (pure petrol/diesel) the total-range and combustion-range sensors just repeated the main "Range" value, so three identical range sensors showed up; the redundant two are now hidden on those cars while genuine hybrids still get the full electric / combustion / total breakdown. The second fuel-level sensor ("primary engine fuel level"), which mirrors the main tank sensor, is now a diagnostic that is disabled by default (existing setups keep it).

## [2.23.0] - 2026-07-23

### Added

- **In-repo EU Data Act data dictionary + auto-update watcher.** The official SVK data-dictionary fields (what every EU Data Act portal key means, with types and units) are now documented in-repo at [`docs/EU_DATA_ACT_DATA_DICTIONARY.md`](docs/EU_DATA_ACT_DATA_DICTIONARY.md), linked from all 12 READMEs. A weekly GitHub Action watches the upstream source PDFs and opens an issue when a fresher version appears, so the doc stays current.
- **Four new driving-telemetry entities from the EU Data Act feed (#901).** Some VW cars report live speed, ignition state, a "driver is braking" flag, and a brake-pressure indication. They now show up as diagnostic entities (disabled by default) — speed as a proper km/h sensor (auto-converts to mph), the other three surfaced as-is while we confirm their exact meaning. Picked up from a Scout report.
- **The poll interval is now a slider you can automate (#847).** Until now the interval only lived in the integration's options; it's now also a Number entity (in minutes) on a per-account "VW Group Connect" device, so you can drive it from an automation — for example poll more often while you're driving and back off overnight — to go easier on the manufacturer's servers. It shows up for every account, including read-only / portal ones, and takes effect on the next poll without a restart.

### Fixed

- **Two-way commands on legacy Car-Net cars no longer refuse themselves with a false "not granted / check your subscription".** The service-directory grant check was treated as the final word, but it can briefly drop grants right after a reconfigure (or vary by cache) even on cars that fully allow the command. It's now advisory: on a negative result it refetches the service directory once and, if still unconfirmed, goes ahead — letting the car's own security-token step be the authority (which safely rejects a genuinely-ungranted command before any S-PIN attempt is spent).
- **A locked S-PIN no longer hides your lock / climate / charge buttons for a day.** After too many wrong S-PIN tries the car returns a "security PIN locked" error; the integration was misreading that as "your account isn't entitled", which hid the command entities for ~24 h and pointed you at a phantom subscription renewal. It's now correctly treated as an S-PIN problem — unlock it in the brand app and the buttons stay put.
- **A locked S-PIN now shows a plain "unlock it in the app" message instead of a scary error dump.** Pressing a command with a locked (or missing) S-PIN used to log a raw Python traceback that looked like the integration crashed. It's now a clean, one-line notification telling you what to do. This covers every command, including window heating.
- **Missing/locked-S-PIN feedback also reaches window heating.** Same clean-error handling as the other commands — no more traceback when you start window heating without a valid S-PIN.
- **You can finish enabling MBB commands even when your account uses two-factor login.** If a VW/Audi login needed a 2FA code, ticking "enable MBB commands" was silently dropped and you ended up with a read-only entry. The command-channel setup now continues after the 2FA step, exactly like a non-2FA login.
- **A per-vehicle S-PIN can now be removed again.** Clearing a car's individual S-PIN field in the options used to do nothing — the old value stuck around. Blanking it now actually clears it (falling back to the shared S-PIN).
- **Optimistic button states no longer snap back for a moment after a refresh.** Right after you pressed lock/climate/charge, the next data poll could briefly show the old state before settling. The poll now respects the short optimistic hold, so the button stays where you put it.
- **"Push notifications" no longer shows up as a permanent "capability drift" in diagnostics.** Push is off by default (and can be blocked by the manufacturer's app-attestation), so "declared but not seen" is its normal state — it's no longer reported as a mismatch. Genuine vehicle-data gaps are still surfaced.
- **The 12V-battery alert-time sensor reads plain durations correctly.** When the EU Data Act feed sends `bem_alert_time` as a countdown rather than a wall-clock time, it's no longer misread as a date far in the past/future.

## [2.22.1] - 2026-07-22

### Added

- **New auxiliary-battery alert-time sensor from the EU Data Act feed.** Some VW cars report a `bem_alert_time` — the moment the 12V (auxiliary) battery's BEM level-2 pre-warning kicks in. It now shows up as a diagnostic timestamp sensor (disabled by default). Picked up from a Scout report; the tyre-pressure and charge-rate fields in the same report were already mapped in earlier versions.

### Fixed

- **Audi US / CA login now completes instead of failing with "Invalid credentials" (#13).** The North-American login itself was working — the app sign-in went through and handed back an authorization code — but the integration then tried to exchange that code at the European backend, which can't read a code the US identity server issued (it came back `invalid key id`). The exchange (and token refresh) now go to the North-American identity endpoint that issued the code, matching the QR / device-code path. Reads are unchanged (they still use the shared global backend).

### Thanks

Thanks to **@coreywillwhat** for loading the integration onto a real US Audi and sending the full logs that pinned down the #13 token-exchange endpoint — credited in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.22.0] - 2026-07-22

### Added

- **evcc integration (read path, works on every brand).** You can now feed your car's state of charge, range and charging status straight into [evcc](https://evcc.io) — it reads them from Home Assistant's own REST API, so nothing extra runs inside this integration. A new diagnostic sensor **evcc charge status** (the A/B/C plug/charge state evcc expects, which it can't derive from our raw status text) is added per EV, disabled by default — enable it and follow the copy-paste recipe in [docs/EVCC.md](docs/EVCC.md). The read path (SoC / range / status / charge-limit / climate) works everywhere, including read-only VW EU; the write path (start/stop charging) works only on a two-way car (Audi / Škoda via MBB).

### Fixed

- **Two-way MBB commands (lock, climate, charging) no longer refuse themselves on cars that don't report an S-PIN attempt count.** When you send a command, the car first hands back a security challenge — and many cars report the remaining-tries count as `-1` at that stage, which just means "not tracked yet" (the real count only shows up if you actually get the PIN wrong). The command path was reading that `-1` as "you have -1 tries left" and blocking every lock/climate/charge command to dodge a lockout that couldn't happen. It now only holds back when there really are 0 or 1 attempts left.
- **The "please reauthenticate" prompt no longer fires on legacy Car-Net cars whose command gateway rejects them (#584).** On some MQB / Car-Net cars the command service-directory call comes back with an authorization rejection that a fresh login can't fix — it's an enrolment / primary-user thing on that car's account, not a token problem (confirmed by re-approving a brand-new token that still gets rejected one second later). The integration used to refresh the token and retry on every poll, which slowly tripped the "token refresh storm — please reauthenticate" guard and sent you off to re-log-in for nothing. It now recognises that rejection for what it is, logs a clear one-line explanation, and stops hammering the login endpoint.
- **No more `'NoneType' object has no attribute 'get_status'` right after a Reconfigure (#584).** Reconfiguring an entry could race a manual refresh that was already in flight, briefly leaving it without a client handle mid-fetch.

### Thanks

Thanks to **@Mattheisen87** for the meticulous #584 diagnostics that pinned down both guard fixes — the authorization-401 refresh storm and the reconfigure crash — and to **@nekas123** for raising the evcc use-case that motivated the read-path connector. Both credited in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.21.1] - 2026-07-21

### Fixed

- **VW EU cars no longer get a false "authentication expired / check your password" (#875).** On MEB / ID. cars, the WeConnect login path is blocked by VW's device-attestation wall, so its saved token can't be refreshed. The integration was treating that dead refresh as a login failure and taking the whole entry down — even though the EU Data Act portal login (the one that actually feeds your data) was working fine. It now falls back to a fresh portal login and keeps going, instead of asking you to re-enter a password that was never wrong. A genuinely wrong password is still reported as before.

### Thanks

Thanks to **@bobbasli**, **@leMineGaming**, **@m3gg3** and **@shaarkys** for the reports and the debug logs that pinned this down (#875) — credited in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.21.0] - 2026-07-21

### Added

- **12V battery-support sensor (MEB / ID. cars).** Newer MEB firmware reports a "battery support" state (`enabled` / `disabled`) that keeps the 12V battery topped up. It's now a diagnostic sensor (off by default — enable it under the device if you want it). This is the field a whole wave of Vehicle Data Scout reports flagged as unmapped; it's now mapped instead of just silenced.

### Fixed

- **Vehicle Data Scout stops flooding on `batterySupport` and active-ventilation.** Two fields were slipping past the Scout's noise filter because their real payload nested one level deeper than the interim filter reached — so dozens of ID./MEB cars kept opening "new field" reports for the same two items. Both are now properly consumed (the battery-support state as the new sensor above; the active-ventilation state + remaining time fold into the existing Active Ventilation sensors), so they no longer surface as unmapped.

### Thanks

Thanks to the many ID./MEB owners who reported the `batterySupport` field (#832 and ~26 more) and the active-ventilation spelling (#845, #856, #859) — all now credited in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.20.1] - 2026-07-21

### Fixed

- **Škoda charge controls work again (#866).** Setting the charge limit — plus the battery-care, charging-current and auto-unlock controls alongside it — failed with a server error even though the official app worked. They were being sent as an *action* rather than a *settings change*, so Škoda's backend rejected them. All four now use the exact request the app sends, checked against the actively-maintained Škoda library.
- **Two-way controls no longer vanish on older Car-Net cars.** On some legacy Car-Net vehicles the integration couldn't read the car's service directory (it came back "unauthorised"), and a v2.20.0 change then hid *every* lock / climate / charging control for the rest of the session. Now, when that directory simply can't be read, the controls stay available (a failed command is reported when you use it) instead of disappearing — while a car that genuinely proves it lacks a service still correctly hides it. That directory read is now also retried once after refreshing the login.

### Changed

- Internal tidy-up of some out-of-date code comments left by the v2.20.0 command-routing change. No behaviour change.

### Thanks

Thanks to **@tader** for the clean Škoda charge-limit report (#866). The full roll of reporters and testers is in [CONTRIBUTORS.md](CONTRIBUTORS.md). 🙏

## [2.20.0] - 2026-07-20

### Added

- **Clear reasons when a control is missing or a command is refused (#752).** Until now, if a lock / climate / charge control couldn't be offered, it just quietly disappeared — and if a command failed, you got a bare error. The integration now decodes the backend's own error codes and per-service licence status into a plain reason: *your subscription has expired*, *this feature isn't licensed on this car*, *terms & conditions not accepted*, *privacy mode is on*, *the car is offline / in deep sleep*, and so on. So instead of a silent gap you get told **why** — and what, if anything, you can do about it.
- **Škoda: care-mode, auto-unlock-plug and active-ventilation controls (experimental).** Grounded in the current myŠkoda app's own routes. Treat as experimental until a Škoda owner confirms them on a real car.

### Fixed

- **Licence "days remaining" no longer goes negative on an active subscription.** On some cars (seen on an Audi S6 with a live subscription) a long-lapsed side-feature's old expiry date was winning out and showing the subscription as expired with negative days left. Only genuinely entitled services now count toward the expiry, so the figure reflects your real, active plan.
- **SEAT / CUPRA remote commands removed — they could only ever fail.** VW guards SEAT/CUPRA remote control behind a Google device-attestation check that only the official app on a real phone can pass, so lock / climate / charging sent from here were always refused. Those controls are now hidden, with an honest one-line explanation, instead of showing buttons that don't work. Vehicle **data still updates** as before.
- **Legacy Car-Net two-way now only offers controls the car actually grants.** For older Car-Net vehicles driven through the durable command channel, the integration reads the car's own service directory and creates a lock / climate / charge control **only** when that car currently licenses it — so you no longer get, say, a lock button on a car whose plan doesn't include remote lock. Nothing invented that can't run.
- **Škoda battery-care switch works again.** It was wired to a stub that raised instead of sending the command; it now sends the real care-mode request.
- **More command routes and payloads corrected to match the current official apps.** A fresh, byte-for-byte pass over the latest Audi / VW / Škoda / SEAT / CUPRA / VW-US apps caught several commands still using an old route or a mis-named field (Škoda flash + charge-target, SEAT/CUPRA battery-care + charge-target + climate temperature, VW-US flash / wake / charge-target, separate window-heating routes), plus the app-version headers were refreshed to the current builds.
- **VW US / Canada: Canada now uses the working US configuration.** The current myVW app ships no Canada-specific server or login client, so Canadian cars now use the same US endpoint that already works, instead of an unverified Canada-only config. (A Canadian tester should still confirm.)
- **Lock / climate / charge commands stop wasting a failed first attempt.** They were trying a combined endpoint that no current app exposes — always a 404 — before falling back to the route that works. The working route is now tried first, so commands are a touch faster and don't burn a needless round-trip.
- **Quieter, more honest logs; account e-mail masked (#779, #709).** The CUPRA/SEAT read channel no longer floods the log on a repeated backend refusal (it says once, plainly, what's happening), and your account e-mail is masked wherever it appears in logs.

### Changed

- **A few backend-error classifications corrected** so a transient or consent-related backend response no longer hides a working entity for a day.

### Thanks

Thanks to **@heyensh-sys**, whose reports on missing controls drove the "explain why" work (#752); **@rmalbrecht** (#779) and **@dazj1990** (#709) for the read-channel and logging reports. The full roll of reporters, requesters and testers is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you. 🙏

## [2.19.1] - 2026-07-19

### Fixed

- **PHEV charging power was reading 10× too high (#764).** On plug-in hybrids the portal feed reports charge power in tenths of a kW, but it was being taken as whole kW — so a 1.9 kW trickle showed as 19 kW, above what the car can even draw. It's now scaled correctly. The same real-world charging export also surfaced three smaller portal glitches, all fixed too: the charging state no longer flips to a junk value mid-charge, an odd placeholder charge-mode is ignored instead of shown, and a sentinel "0" odometer at trip start no longer masquerades as a real reading.
- **Cabin and outside temperature from the portal feed were decoded wrong.** Both were read as deci-Kelvin, but the data dictionary actually encodes them with a 0.1 °C step and a −46 °C offset — so a normal 22 °C cabin could come out around −205 °C. Both now use the correct formula (including the nested one-time-export spelling of the outside reading), with the Fahrenheit sub-range handled too.
- **Several Audi / VW commands were hitting the wrong backend path and silently failing (#752).** Parking-heater start, climate start, charge-mode and vehicle wake were each using a mistyped route or a mis-named field, so the backend answered with a 404 that led nowhere. The routes and payloads now match what the official app actually sends (parking-heater, charge-mode on its own route, the climate temperature / at-unlock keys, wake), and the VIN is upper-cased before every command because some backend nodes are case-sensitive. Note: on a car where a given function simply isn't provisioned for remote control, the backend will still legitimately refuse it.
- **Honk & flash ignored the requested duration.** The duration field was mis-named, so "flash the lights" always ran the backend's default length instead of the value sent. Fixed, grounded in the official app's own wire format.
- **Your car's model now shows even when the long name is missing (#764).** When the backend returns no full model name, the device now falls back to the short model name from the vehicle list before dropping to a plain brand label.
- **CUPRA / SEAT read channel: app-version header refreshed (#779).** Bumped to the current version so requests keep matching what the backend expects.
- **The "no data yet" help text now leads with the consent step (#755).** If the portal feed hasn't produced anything, the guidance starts with enabling the continuous-data consent in your VW/Audi account — the step people most often miss — before the rest.

### Changed

- **Commands now wait to confirm they actually ran (#666).** Instead of firing a command and assuming success, the integration briefly polls the backend until the request reaches a final state, so a genuine failure surfaces as an error instead of looking like it silently did nothing. It adds a little latency but is far more honest about what happened.

### Thanks

Huge thanks to **@Motii08**, whose real charging export pinned down the 10× power bug and three other portal glitches (#764); **@heyensh-sys** for patiently testing the Audi commands and sending the exact error logs that isolated the route bugs (#752); **@dazj1990** (#709) and **@rmalbrecht** (#779) for the read-channel reports; **@Mech0z** for flagging the confusing "no data" guidance (#755); and **@torstentosh**, whose command errors drove the completion-confirmation work (#666). The full roll of reporters, requesters and testers is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you. 🙏

## [2.19.0] - 2026-07-18

### Fixed

- **Your car's model + year now show properly on the device page.** Instead of a bare "VAG Vehicle", the device model reads like "S6 Avant TDI quattro tiptronic (2021)" — the redundant leading brand is stripped (the manufacturer field already shows it) and the model year is appended. Cars with no model name at all fall back to a clean brand label rather than "VAG Vehicle", and the VIN stays the device serial number.
- **Trunk, engine hood and sunroof open-state can read from the newer portal feed too (#794, #807).** Some cars send openings in a compact form where the trunk, the hood, the sunroof, every door and every window all share one generic `open` flag — told apart only by a hidden dictionary ID — so on its own the flag was meaningless (which is why the Scout kept surfacing a bare `open`). We now decode that ID against the official data dictionary and route trunk / hood / front-sunroof to their existing sensors. (Per-door and per-window openings share the same shape but are position-indexed — a follow-up; and real-feed confirmation is still pending, so treat it as best-effort.)
- **A brief DNS/network hiccup no longer files a spurious error report (#814).** When your Home Assistant box momentarily can't reach the VW backend (a DNS timeout), the integration already retries and recovers on its own — but that self-healing blip was still being escalated to the Error Reporter, which auto-files a GitHub issue. Those transient network errors are now recognised and logged quietly instead of raised.

### Added

- **Audi US / CA groundwork (experimental).** myAudi in North America runs on the same CARIAD backend as Europe, just the North-American region — so there's now an "Audi US / CA" brand wired to the real NA endpoints (host, identity provider and the live app client), with device-code (QR) login. Heads-up: it's a login foundation — whether North-American Audi vehicle data comes through off-device still needs a real US Audi tester to confirm, so treat it as experimental until then.
- **Tibber can now fill in your EV's charge data (EU, opt-in).** If you're a Tibber customer with your car paired, you can add Tibber as an extra read channel in the integration options — it reads state of charge, target SoC, range and plug/charging status from Tibber's official Data API and folds them in as a *lowest-priority* source: only filling gaps your car's own channels left empty, never overwriting fresher data. Read-only (Tibber can't command the car). One-time setup: create your own OAuth2 client on the Tibber developer portal, authorize once, and the integration keeps the token refreshed from there. Because Tibber only updates while the car is connected/charging, its readings are treated as the least-trusted source, and every field it contributes is attributed to the `tibber` channel.

### Thanks

Thanks to **@gomble**, whose error report showed the integration was filing a GitHub issue over a brief DNS blip that fixes itself (#814). **@loungelizard2018** and **@cafemonkey**'s Scout reports are what surfaced the packed opening states we now decode (#794, #807). The full roll of reporters, requesters and testers is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you. 🙏

## [2.18.1] - 2026-07-17

### Fixed

- **Closed windows and the roof no longer read as "open" on Audi / VW-EU cars.** Every window on the CARIAD channel — plus the rear sunroof and roof cover — showed *open* while the car was shut, even though the aggregate "windows open" sensor said closed. Two causes in the parser: the per-window map stored the state inverted (the lone place breaking the `True == closed` convention the rest of the integration follows), and option-dependent roof parts on a car without an opening roof were written as "open" instead of not shown at all. Both fixed — shut windows read *closed* and non-existent roofs don't surface. Thanks **@lucson**, verified on a real PPE Audi Q6 (#810).
- **A handful of Vehicle Data Scout reports that wouldn't go away — none of them real gaps.** Aux-heating (Standheizung) started turning up in a second spot on Audis, and the climate-timer's error wrapper read as an unknown field (#752, #785, #789); Škoda's AC charge-current-in-amps was already being read but was never ticked off the catalogue (#781, #795); and on the EU Data Act feed the raw oil-level status is recognised now (#794). The catalogue simply hadn't been told about these — so the Scout stops flagging them.
- **The portal Scout stops crying wolf on account/envelope metadata.** The EU Data Act feed repeats your account id, VIN, poll/message timestamps and a pile of per-export UUIDs on every single poll — none of it mappable vehicle data. These used to stay visible on principle; they're now dropped from the Scout/diagnostic surface (anything with a real, vehicle-specific field name still shows up), which clears a long tail of pure-repetition "N new fields" reports (#747, #782, #804 and a dozen more like them).

## [2.18.0] - 2026-07-17

### Fixed

- **Settings you'd saved were being read back empty — the big one, found by @lucson (#806).** Home Assistant hands the integration your saved configuration as a read-only mapping, not a plain dictionary, and a type check deep in the read was written for the wrong one. So it came back empty on every real install, no matter that you'd saved it correctly. This is why S-PIN commands told you to "configure your S-PIN" when you already had (that whole #666 saga), why the aux-heating sliders snapped back to their default, why turning read-only mode on could be silently ignored, and why the PPE climate flag did nothing. The tests had faked the saved config as a plain dictionary, so it looked verified for as long as it shipped. All four now read what you actually set.
- **Two settings that shipped but never switched on.** The push toggles (Škoda MQTT, CUPRA/SEAT and Audi/VW notifications) and the saved per-vehicle S-PIN map were read from an area Home Assistant blanks on save, and opening Options even wrote blanks back over the map. Nobody has ever had working push; the per-vehicle S-PIN (#759) is now read from where it lands, and Options stops clobbering it.
- **Your data stops disappearing after a command.** If your car is read over more than one channel, locking it — or restarting Home Assistant — used to blank out everything the second channel contributed until the next poll. Those readings are kept now.
- **Scout reports stop crying wolf.** A day's worth of reports arrived and almost none contained a field we don't already read — our own catalogue simply hadn't been told. The rear climate zones, the climate mode, the battery-care error notice and the capture timestamp are all recognised now, plus two new "changes pending" counters (queued charging-profile and climate-timer edits) that a couple of Audis surfaced (#799, #801).
- **A failing button gives you an error instead of a crash report.** Pressing e.g. Wake on a car that refuses it produced "Unexpected exception" and a Python traceback; you now get what the car actually said.
- **Diagnostics tells the truth about push.** It reported push as active on every setup, including ones with all push toggles off.
- **The portal is no longer re-probed on every restart**, and Škoda's AC charge-current limit is read.
- **A failed portal data-request now says why it failed (#709).** When the portal's security-token fetch fell over, the log said only "no CSRF token — aborting", which made a stuck feed impossible to diagnose (a 403, a 404, a timeout and a renamed field all looked identical). It now names the status or the reason — never the token value.
- **MBB commands died after about an hour (#584).** The refresh request was malformed — it announced `grant_type=refresh_token` but carried no refresh token in it, just an empty scope and the value under the wrong field. **@Mattheisen87**'s diagnostics show the result: a 500 error on every refresh and a token expiry frozen for four days on a 60-minute token, so it never once succeeded — and the 500 (rather than a clean rejection) is why it kept looking like a passing VW hiccup. The request is now well-formed and standard; whether that fully clears the 500 wants confirming on a real car, so if you run MBB, please shout.
- **And once MBB was on, there was no way back to the approval (#584).** The re-approval was gated off the moment the channel was armed — precisely the state you're in when you need it — and the checkbox showed unticked no matter what was stored, so it looked off while the code thought it was on. The only escape was deleting the integration and re-adding it, which renames every entity and takes your dashboards with it. Both fixed; re-run Reconfigure with the box ticked to re-approve.
- **The app watcher opened a pull request every single day (#727)** announcing version changes that weren't there — it was comparing the file, and the file always carries the time it last looked. It also never managed to check Volkswagen at all: the mirrors it asked don't carry the app, so it recorded "checked" and learned nothing, for months. It asks Google Play first now, which is where the apps actually come from.

### Added

- **Battery care is settable, not just visible.** A switch and a target slider — the reading has been there since 2.10.0, the control never was. Appears only on cars whose backend actually reports it.
- **Every reading tells you where it came from.** Each entity carries a `source` attribute naming its read channel, and the data-source sensor now works for single-channel cars too — on a Golf GTE the fuel level and the charge level genuinely come from different places.
- Both new controls are translated in 12 languages.
- **One-time historical export from the EU Data Act portal (Phase C, opt-in).** The portal offers a second kind of data pull besides the 15-minute feed: a one-time snapshot of your car's full configuration — departure timers, charge profiles, climate settings, the charge floor — in the older Car-Net format. Two new services: `request_historical_export` asks the portal to build it (it takes roughly half an hour), and `import_historical_export` fetches the ready file and folds its settings into your car's data. It only ever fills gaps — your live readings are never overwritten, so a hybrid can't get mislabelled electric by the older dump. This is wired end-to-end (the request, download and parse are all built from real portal traces) but the very last step, confirming a freshly-built export flows all the way through on a live account, still wants a real round-trip — so treat it as a beta.
- **Groundwork for Touareg-era cars (2021), which this release does _not_ yet fix.** Those cars ship the old Car-Net export format and we now understand it — charge level, charge mode, current limit, target temperature. But understanding it changes nothing on its own: the portal offers those cars only a one-time export, we only ever create and read the continuous 15-minute feed, and so we never actually fetch a payload for the mapping to work on. Reading one-time exports is the missing piece and it isn't built. #702 stays open.

### Removed

- **Three settings that did nothing.** Wake-before-poll (and its delay slider), force-access, and the EU Data Act browser fallback. None of them had ever been wired to anything — ticking them changed nothing.

### Docs

- **The README was sending people to look for a switch that doesn't exist.** It told you to enable a "continuous data request" in the VW portal; the integration creates that itself. It also called the auto-kickoff opt-in and promised we "won't do it without your say-so" — it has been on by default since 2.17.1, and the 1-month subscription it registers is free. Corrected in all 12 languages, along with two translation errors found on the way.

### Thanks

**@lucson** found the config-entry type bug and sent a fix for it — the reason so many "I saved it but it does nothing" reports never resolved. **@ChristophCaina** asked for the per-vehicle S-PIN, and **@Mattheisen87** put a real car on the MBB channel and pinned down both of its failures. **@shaunadam** turned on raw logging and sent the log that showed us the traceback. **Bugi66**'s export is what makes the Touareg-era format work possible (the reading itself is still to come), and **Mech0z** is why the README stopped lying. **@DvorakMartin1** surfaced Škoda's charge-current limit, **@thcherry**'s diagnostics caught the push mislabel, and **@Motii08** offered to charge their car for us. Thanks also to **@neuhausf**, **@dlupsa**, **@fefe-home**, **@jandebeule**, **@alexthegalex13**, **@YouriJansen**, **@GiuseppeAlbano** and **@Lagaff86**, whose Scout reports showed our catalogue was the thing that was out of date. The full roll is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you, all of you. 🙏

## [2.17.5] - 2026-07-13

### Fixed

- **No more "30 / 46 / 55 new field(s)" Scout reports full of cryptic ids.** A change in 2.17.4 accidentally surfaced every internal id-only data-point as its own "new field", so cars started filing huge Scout reports. Those ids are handled internally again; only genuinely new, readable fields are reported now.
- **The charging plug no longer shows a raw "invalid" state.** When the car reports an "invalid"/"unsupported" plug state, the text sensor now stays unknown instead of showing the raw marker (the plugged-in yes/no was already correct).
- **Boot/trunk lock is read correctly on cars that report it in a compact form** — and it no longer accidentally drives the *doors* locked state.

### Added

- **More coverage over the EU Data Act portal, reusing existing sensors:** oil low-level warning (petrol cars), rear climate-zone on/off, and sunroof position on cars that report it in a second slot.
- **Live "currently active" sensors** for mirror heating and each climate zone (front/rear, left/right) — the live-status companions to the existing on/off settings. Diagnostic, off by default.
- **"Battery Care Changes Pending"** diagnostic sensor.
- **Parking-light coverage** for cars that report it as a single flag.
- **A different S-PIN per vehicle (#759).** If the cars on your account each have their own S-PIN, you can now set a per-vehicle S-PIN under Settings → the integration → Configure. Leave a vehicle blank to keep using the shared S-PIN. Thanks **@ChristophCaina** for the request.
- All new entities are translated in 12 languages.

### Thanks

Every fix and field above started with someone filing a report, a request or a diagnostic. Special thanks to **@ChristophCaina** for the per-vehicle S-PIN request, and to everyone whose Vehicle Data Scout reports surfaced the new portal fields and flagged the field-list flood. The full roll of reporters, feature-requesters, testers and discussion contributors is in [CONTRIBUTORS.md](CONTRIBUTORS.md) — thank you, all of you. 🙏

## [2.17.4] - 2026-07-13

### Fixed

- **Electric VW ID.3 / ID.4 / ID.5 / ID.7 (and other MEB cars) show their driving range again over the EU Data Act portal.** These cars report the range in an anonymous field that only an internal id distinguishes, so the integration couldn't recognise it and the range stayed empty; it now resolves it correctly.
- **A bogus "service due in ~2.1 billion km" reading is gone.** A specific "no value" marker the service countdown sends slipped through the filter and got flipped into a huge positive distance; it's now dropped like the other no-reading markers.
- **No more pointless re-login loop when the data portal is briefly busy.** A "429 too many requests" or a "400 not ready yet" while fetching your data used to look like a failed login and kicked off a re-authentication loop; those are now treated as "no data this poll" and the next poll just tries again.

### Thanks

These EU Data Act read-path fixes (MEB/ID.x range, the "no reading" unit markers, transient-status handling) came out of benchmarking portal data quality across the wider EU Data Act community — thank you to everyone sharing real field data and edge cases, and to the reporters who flagged the missing ID.x range. 🙏

## [2.17.3] - 2026-07-13

### Fixed

- **VW EU passenger cars get their data flowing again.** The EU Data Act portal changed the format it expects for a data request, so the request the integration creates for you was being silently rejected — and status could stay "unavailable" with no obvious reason. It now sends what the portal expects, so the feed provisions correctly. This affects every VW EU car that reads over the portal.
- **Charging power and charge rate no longer read ten times too high** on EU Data Act cars. The portal reports these in tenths, so e.g. a real 7.4 kW showed up as 74 kW; they're now scaled correctly.
- **The diagnostics download no longer contains your account ID or VIN in the raw-fields section.** Those values are redacted now, while the field names stay visible so nothing is hidden.
- **Combustion VW (North America) cars are no longer wrongly told they need a subscription.** The "not entitled" check keyed off the EV-only charge/climate reads, which legitimately don't apply to a petrol car; it now keys off the main vehicle-status read instead.
- **The vw.de companion channel works on Car-Net (MBB) cars again** and stops forcing a repeated re-login. It was pinned to the wrong data-centre id for MBB cars, and it treated a "no data yet" reply as if your login had failed.
- **Clearer errors when a command can't run on a Car-Net (MBB) car.** Honk & Flash now tells you it isn't available on that channel instead of a misleading "GPS position needed"; a rejected Security PIN now says exactly that — check your S-PIN — instead of looking like an expired subscription; and remote wake explains that VW doesn't permit it on that channel. Thanks to the live diagnostic that pinned all three down.

### Thanks

These fixes exist because people filed clear reports and ran real cars: **@SparkyDan555** (charge power/rate reading 10× too high), **@Rizencip** and **@shaunadam** (combustion VW North America), **@dazj1990** (the VW EU portal feed going quiet), and **@torstentosh** and **@Mattheisen87** (the MBB command diagnostics). 🙏

## [2.17.2] - 2026-07-11

### Added

- **The integration now speaks four more languages: Italian, Norwegian (Bokmål), Danish and Finnish.** Full UI translations plus a translated README for each — twelve languages in total now.
- **You can switch on the two-way command channel for an existing VW or Audi account without deleting and re-adding it.** Open Settings → Devices & Services → Reconfigure and tick "enable MBB commands" — the QR confirmation runs and the command channel is attached to your existing entry (so your entity IDs, automations and dashboards stay intact). Still **experimental** and legacy Car-Net only, exactly as at first setup.

### Fixed

- **Reconfigure no longer wipes an existing command channel.** Updating your password (or any other setting) through Reconfigure used to silently drop a durable-MBB two-way channel you'd set up — you'd have had to add it again. Reconfigure now merges your changes on top of what's already there instead of replacing everything.
- **The manual "Create EU Data Act data request" button now works even if you turned automatic provisioning off.** Pressing it is an explicit request, so it now always creates the data request rather than doing nothing.
- **"No data → self-heal" now kicks in right away instead of waiting for the host's first six hours of uptime.** A clock comparison meant the runtime re-provisioning could stay dormant on a freshly booted Home Assistant; it now fires on the first cycle that needs it.
- **Bentley setup and reconfigure no longer crash** when building the entry title (Bentley isn't in the internal brand-name table — it now falls back to a plain label instead of erroring).
- **Lock / climate / charge toggles no longer snap back after you press them.** The control flipped to the new state immediately, but the very next data poll overwrote it with the car's still-pre-command state, so it looked like the command hadn't worked until you hit refresh. The optimistic state is now held until the car's backend actually reports the change (or a couple of minutes pass). Thanks @torstentosh for pinning this down on a PPE Q4 e-tron.

### Changed

- **Porsche login rebuild — groundwork only, nothing changes for users yet.** The experimental Porsche path targets the retired My-Porsche (Auth0) app; the live app is Porsche One (PingFederate device login). This release adds that device-login implementation (unit-tested against mocked endpoints) so the rewrite is ready, but it is **not wired in** and still needs a Porsche One owner to verify it end-to-end before Porsche can be switched back on. Porsche stays flagged experimental.

## [2.17.1] - 2026-07-10

### Fixed

- **"Configure your S-PIN" no longer appears when your S-PIN is already correct (#666).** On a setup that pairs EU-Data-Act reads with the legacy two-way command channel, the command connector grabbed your S-PIN once when it started up — so an S-PIN you added or changed *later* through the integration's Options never reached it, and every lock/climate/charge command failed asking you to configure a PIN you'd already configured. The connector now reads the S-PIN Options-first at start-up **and** picks up a changed PIN live, without a restart. Thanks @torstentosh for the report and the testing.
- **Clearer errors for S-PIN and SEAT/CUPRA attestation walls (#666).** A remote command that needs an S-PIN but has none configured now reports a clean "S-PIN required" instead of a raw traceback, and SEAT/CUPRA commands blocked by their AWS WAF are now correctly identified as a device-attestation wall (not a phantom subscription/renewal problem).
- **Reconfigure no longer aborts with "already configured" (#584).** Reconfiguring an existing account (Settings → Devices & Services → Reconfigure) immediately failed with "This account is already configured", because the check matched the very entry you were reconfiguring. It now only refuses if you switch to a *different* account that already has its own entry — reconfiguring the same account updates it in place. That means you no longer have to delete and re-add the integration (which would regenerate every entity_id from the default device name and break your automations and dashboards). Thanks @Mattheisen87 for the precise root-cause.
- **Legacy Car-Net remote lock/unlock now targets the correct backend URL (#666).** The MBB lock/unlock request was being sent to the wrong host and path shape (it dropped the brand/country and used the setter host), so on a real Car-Net car it would have 404'd. Corrected to the verified `{Brand}/{country}` form on the vehicle's home-region host — the same shape our other Car-Net calls already use. Grounded against the myAudi/We-Connect app internals.

- **The "open the brand app" button now uses each app's real link (#666).** Several brands' deep-link schemes were launcher guesses (`wecharge://`, `myseat://`, `mycupra://`, `myporsche://`, `vwapp://`) that didn't match the app; corrected to the schemes the shipping apps actually register (`weconnect://`, `seat://`, `cupra://`, `porsche-app://`, `myvw://`). Audi and Škoda were already correct.

### Changed

- **Porsche is now flagged experimental — its login may fail (#666).** The fresh app teardown showed Porsche moved from the old My-Porsche (Auth0) app to **Porsche One**, which uses a completely different login (PingFederate device-grant). Our current Porsche login targets the retired Auth0 app, so it's expected to fail on current accounts. Rather than quietly advertise it as working, Porsche is now labelled experimental in the brand picker. The rebuild path is documented and confirmed feasible — it just needs a Porsche owner to help verify it end-to-end before it's switched back on. (Testers with a Porsche account welcome.)

### Added

- **The EU Data Act data request is now set up for you automatically — no more "device with empty entities" (#584).** In portal mode the integration can only receive data once there's an *active continuous data request* on the VW EU Data Act portal. Until now you had to create that request yourself on the portal website first — and if you didn't (or it lapsed), you got a device full of empty entities and reasonably assumed the integration was broken. Now it **creates the request for you automatically** and, if data stops arriving, **re-provisions it on the fly** — so "no data coming in" self-heals. A one-time notification tells you when a request was created. You can turn automatic provisioning off under Configure, or trigger it yourself with the new **"Create EU Data Act data request"** button. (We're the only VW-EU Home Assistant integration that can create the request for you — the others require you to do it by hand.)
- **Audi Car-Net owners can now enable the two-way command channel too — experimental (#666).** The legacy command path (lock/climate/charge over the older Car-Net backend) was Volkswagen-only; it's now offered for Audi as well, since the underlying command catalog is identical and the brand routing is handled. This is **experimental** and applies only to older legacy Car-Net Audis (not the newer MEB/PPE e-tron generation) — it hasn't been confirmed end-to-end on a real car yet, so treat it as opt-in testing.
- **New sensors for EU-portal cars: cabin temperature, HV-battery min/max temperature, charge-target time and profile user count.** The latest round of Vehicle Data Scout reports (a VW ID.7 among them) carried a handful of signals we didn't map yet. If your car sends them in its portal data, they now appear as sensors. Everything else in those reports was already covered.

## [2.17.0] - 2026-07-10

### Added

- **Škoda now reports its heater source too (#682).** Škoda EVs expose a `heaterSource` value on the climate endpoint (e.g. "AUTOMATIC") — the same signal VW, Audi, SEAT and CUPRA already surface. It now feeds Škoda's **heater source** sensor as well (electric cars, where the field is present). Thanks @ra666ack for the Scout report.

### Fixed

- **Charging settings (target %, charge mode, min charge, max AC current) work on PPE Audis again (#666).** Same root cause as the v2.16.3 climate-temperature fix: these were sent as a POST where VW's backend expects a **PUT**, so on the stricter PPE/MEB Audis (Q4/Q6 e-tron) every charging-settings change came back **404** — @torstentosh confirmed the charge-target still 404'd on 2.16.3 right after the climate fix started working. All four charging setters now use the correct PUT (through a shared helper that also covers climate), keep the old POST as a no-regression fallback, and surface a clean error instead of a raw 404 traceback if a vehicle genuinely doesn't expose the write. The legacy MBB two-way charge path is unchanged.

## [2.16.4] - 2026-07-09

### Fixed

- **Repair prompts show correctly in six more languages.** Several of the integration's repair messages (two-factor needed, terms & conditions, marketing consent, rate-limited, auth failed) were missing the `{brand}` / `{username}` placeholders in the Czech, Spanish, French, Dutch, Polish and Swedish translations — so Home Assistant logged translation-validation warnings and could blank those messages out. All six now match the English source, with the account name and brand back where they belong. Thanks @shaarkys, whose debug log surfaced the Czech warnings.

## [2.16.3] - 2026-07-09

### Fixed

- **Setting the climate temperature works again on Audi Q4/Q6 e-tron and other PPE cars (#666).** The "set target temperature" action was going out as the wrong kind of request — a POST carrying the *read*-side field name (`targetTemperature_C`) — where VW's backend actually expects a **PUT** with `targetTemperature` + a unit. On the stricter PPE/MEB Audis the gateway answered that with a **404**, so every temperature change failed with an "unexpected error" (older models were more forgiving, which is why this went unnoticed). It now sends the correct PUT + body, keeps the old request as a fallback so nothing that worked before can break, and if a vehicle genuinely doesn't expose a standalone temperature-set it now says so cleanly instead of dumping a 404 traceback. The verb + field were cross-checked against four independent VW/Audi CARIAD clients.

### Thanks 🙏

Huge thanks to @torstentosh for the pin-sharp debug log + diagnostics that made this a five-minute root-cause instead of a guessing game. Exactly the kind of report that makes a fix like this possible.

## [2.16.2] - 2026-07-08

### Added

- **New diagnostic sensor: what triggered the last EU Data Act delivery (#636).** On EU Data Act cars there's now a "report trigger" sensor that tells you what kicked off the most recent data report — e.g. a remote request you made, or the car reporting on its own. It ships **disabled by default** (it's diagnostic detail most people won't need), so turn it on if you're curious. Thanks for the field spot.
- **New diagnostic sensor: which climate mode your car is set to (#671).** Audi and other CARIAD EU cars report a `climatisationMode` setting — "comfort" in the wild — that we already used when *sending* a climate command but never read *back*. There's now a "climate mode" sensor showing the current value. Like the trigger sensor above, it's **disabled by default** and only shows up on cars that actually send the field. Thanks @tsvyatkov for the Scout report.

### Fixed

- **VW: your car stays alive when the EU Data Act portal has a bad moment.** If you've got a VW EU car set up with the volkswagen.de website channel as a backup on top of the EU Data Act portal, and the portal times out for a poll, we now fall back to the website data for that cycle instead of freezing the entity on its last-known values. Before, a portal hiccup would quietly leave you looking at stale numbers even though volkswagen.de had fresh ones sitting right there. Single-source setups are completely unchanged. And if the website session itself has actually expired, you get a proper re-login prompt rather than silent staleness.

- **Škoda: warning lights no longer read "Problem" on a perfectly healthy car (#649).** Škoda's health endpoint always sends one entry per monitored category (engine, brakes, tyres, oil…) even when nothing's wrong — a healthy category just comes back with an empty defect list. We were treating "the list has entries" as "something's wrong", so on every Škoda all the warning sensors flipped to Problem while the MySkoda app calmly showed "All good". Now a category only counts as a warning when it actually carries a defect, so an all-clear car reads all-clear. Thanks @divanguz-alt for the report and the spot-on root-cause.

### Thanks 🙏

This release came straight from your field reports. Special thanks to @divanguz-alt (Škoda warning root-cause, #649), @chrischtili (the `trigger_type` field, #636) and @tsvyatkov (the `climatisationMode` field, #671). And to everyone who filed a Vehicle Data Scout report or bug this cycle — @bachjessen @BalooDK @datenhamster @Drachendiadem @fesch89 @fugazzy @gr6803 @heikone @IanNorthern @janez78 @joostbouten @kaufmannralf @KratosLionXD @Lagaff86 @littlecake @LouisFk @MaFi1504 @Manuel-Hanak @MaTi8383 @MichaelNeys @moltke69 @NevelSavage @Ola-Skallberg @PollenNor @Raymondgijzen @roeleert @Sacha72 @sebastianedse @sotiropoulos123 @Svenruotsi @tolnaiz @torstentosh @wfa001 — even the reports that turn out already-covered help confirm the field mapping is holding up. The full roster of everyone who's ever reported here is in [CONTRIBUTORS.md](CONTRIBUTORS.md).

## [2.16.1] - 2026-07-05

### Fixed

- **volkswagen.de proactive session-roll: the first roll no longer gets wrongly skipped on a freshly-booted host.** The debounce used `0.0` as the "never rolled yet" marker, but `time.monotonic()` can be a small number right after boot — so on a fresh start the very first proactive roll could be debounced away. Uses a proper `-inf` marker now, so the first roll always fires regardless of uptime. (CI caught this on a fresh runner; no user-visible impact, but the guard now behaves as intended.)
- **LICENSE is detected as AGPL-3.0 again (HACS validation).** The LICENSE file carried a short custom copyright/intro header above the licence text, which made GitHub's licence detector report "Other" and failed HACS's licence check. The canonical AGPL-3.0-or-later text now stands alone in LICENSE (so it's correctly detected), and the copyright notice + the AGPL §7 attribution/naming terms moved to a new NOTICE file (pointing at the existing ATTRIBUTION.md). **No change to the licence itself** — same AGPL-3.0-or-later, same attribution requirements.

## [2.16.0] - 2026-07-05

### Added

- **Service & oil-change now also show an absolute due-date on EU Data Act cars, not just "in N days."** The portal path already gave you the "next service in 155 days" counter, but the companion "due on <date>" sensors (`service_due_at` / `oil_service_at`) stayed empty on EU-Data-Act vehicles — they only filled in on the brand-native paths. Now the portal path feeds them too, so a dashboard can show the actual date. (No new entities — it populates the sensors that were already there.)
- **volkswagen.de channel: two new read signals + the car's nickname & plate (beta).** If you use the opt-in volkswagen.de read channel, it now also reports the **number of active dashboard warning lights** and your **last confirmed remote lock/unlock action + time**, and surfaces the vehicle's nickname and licence plate. These ship **disabled by default** — they're beta, hitting live endpoints we haven't broadly validated yet, so enable them if you'd like to help test — and they fail soft: if VW's backend doesn't answer, the sensors just stay "unknown" and never hold up the rest of your data. Want to help validate the channel? See #632.

### Fixed

- **The optional volkswagen.de read channel no longer quietly drops its session between polls.** That channel's sign-in lapses roughly 30 minutes after login and normal data reads don't keep it alive, while the poll runs every 15 minutes — so on a slow cycle the session could die silently, and the next read would fail (sometimes forcing a re-login with a fresh email code) with nothing to tell you why. The integration now proactively refreshes that session at the start of each cycle, well inside the expiry window, so it stays alive. Best-effort — a failed refresh just falls back to the existing on-demand re-login. (No effect unless you enabled the volkswagen.de channel.)

### Thanks 🙏

None of this happens without the people who file Vehicle Data Scout reports, open issues, send diagnostics + logs, and test on real cars — you're the reason the field coverage and reliability keep improving. Thanks to everyone who fed into this stretch of releases, including @brokkolo @MBrunk85 @PascalFlierman @normand198 @JosefAuer84 @jebeke65 @oh-supra @kotipalvelu @Carbolithos @jwmaas @saxmanio85 @danst0 @StefanSch84 @ravest @bachjessen @VanHynten @daydy16 @tsvyatkov @gudden @jamiegt10 for the recent field-Scout reports, and @CyberChris79 + @Ra72xx for the diagnostics and repros that drove the MBB command-cascade and the duration-parsing fixes. The full roster of everyone who's ever reported here lives in [CONTRIBUTORS.md](CONTRIBUTORS.md).

## [2.15.12] - 2026-07-04

### Fixed

- **A failed MBB command no longer knocks all your sensors offline (#584).** On the legacy Car-Net two-way alpha, reads and commands run through the same connection and shared one token-refresh budget. So when VW's backend kept 500ing a lock/climate command, the retries burned through that budget, tripped the "too many refreshes — pause" guard, and that guard then also blocked the normal data poll — every entity went unavailable with a red exclamation mark until a restart. Now a command failure stays contained to that command: it can't exhaust the poll's refresh budget or drag your reads down with it. On top of that, a transient MBB 5xx from VW is retried with a short backoff instead of failing instantly. Reads keep flowing even when a command can't get through. Thanks to CyberChris for the clean repro and logs.
- **Aux-heating (Standheizung) now fails cleanly on legacy Car-Net cars instead of leaking the wrong credentials (#584).** On an MBB car the engine pre-heater command was sending the MBB token to VW's newer backend, which rejected it with a `400 missing auth header`. There's no verified MBB route for the pre-heater yet, so rather than send the wrong credentials it now returns a clear "not available on the legacy two-way path yet" message. Non-MBB cars (the newer portal + Audi) are unaffected. Wiring up real MBB aux-heating is a separate future item.

## [2.15.11] - 2026-07-03

### Added

- **HV battery status sensor.** EU Data Act cars that report a high-voltage battery status flag now get a diagnostic sensor for it, separate from the state-of-charge reading. It's off by default and translated into all 8 supported languages — turn it on if you want it. Thanks to the reporter for surfacing the field.
- **Spoiler position sensor (#614).** On cars with a movable spoiler, the actual spoiler position as a percentage now shows up as a diagnostic sensor, alongside the open/closed state we already had — same as we did for the sunroof. It's off by default and translated into all 8 supported languages.

### Fixed

- **Charging-scenario and immediate-action sensors on more cars.** Some EU Data Act vehicles send these two charging status readings under a slightly different name than others, so they were showing up empty. They now fill in either way. Thanks to the CUPRA Tavascan reporter.

## [2.15.10] - 2026-07-02

### Added

- **Live push updates — experimental opt-in BETA (Audi, VW, Škoda, CUPRA, SEAT).** Instead of only polling on a timer, the integration can now listen for the car's own push notifications and refresh the moment something changes — a lock/unlock, charging kicking in, climate switching over. It's off by default; flip it on per brand in the integration options if you want to try it. Heads up: it's genuinely experimental and still needs testers with a live car to confirm it works end-to-end on each brand, so expect rough edges. If it can't connect it quietly backs off and falls back to normal polling — no log spam.
- **Set the AC charging current on Škoda.** Škoda EVs now get a "Max. Charging Current" dropdown so you can switch the car between drawing the full AC current and a reduced rate — handy if you want to go easy on a shared or older circuit. It reads back the car's current setting and is translated into all 8 supported languages. Only Škoda cars with a battery get it.

## [2.15.9] - 2026-07-02

### Added

- **Rear climate-zone on/off sensors for Audi (#597).** Cars with a rear climate zone now expose whether the rear-left and rear-right zones are switched on, matching the front-zone sensors we already had. They're diagnostic and off by default — turn them on if you want them. Cars without a rear zone won't get an empty entity. Thanks to @kaledii for the report.

### Fixed

- **VW North America dropouts got reported as errors (#593).** When the VW-NA backend was briefly slow or the connection dropped mid-poll, the timeout bubbled all the way up and showed in the Error Reporter as if the integration had broken — the same "backend temporarily unavailable" blip we already shrug off everywhere else. Now a connection drop or timeout on a VW-NA request is treated as exactly that: a transient hiccup, skipped for this poll, no error logged. A real 403 (entitlement/attestation) or any genuine server error still surfaces normally, so nothing real gets swallowed. Thanks to @dardares for the report.
- **Consent/terms prompts flooded the Error Reporter every poll (#596).** If your account was waiting on a one-time action in the brand app — a privacy-consent acceptance, updated terms, a 2FA confirmation, or a portal onboarding step — the integration correctly showed a Repair telling you to go accept it, but *also* logged an error to the Reporter on every single poll (dozens of duplicate entries). Those prompts are something only you can clear in the app, not a bug in the integration, so they no longer get recorded to the Error Reporter — you still get the clear Repair notice telling you what to do. Genuine problems are still reported as before. Thanks to @knalp for flagging it.
- **Charging-mode dropdown was stuck in German for everyone (#589).** The `Charging Mode` select baked the German option labels ("Manuell", "Bevorzugte Ladezeiten", …) straight into the entity, so a UK user (or anyone not on German) saw German verbatim — Home Assistant had nothing it could translate. The options are now stable canonical keys that HA localises per your language, with proper translations shipped for all 8 supported languages; the current value localises too, no matter which spelling the car's backend sends back. This is a display/localisation change only — it doesn't touch how a mode is sent, so command behaviour is unchanged on the brands that support switching it. Thanks to @ColinSainsbury for reporting.
- **Stopped a harmless "new field" report on Audi (#598).** When the Audi backend has a brief hiccup fetching your car's capabilities list, it tacks on a little error wrapper that the field scout hadn't seen before and flagged as new. It's just the same "backend was momentarily busy" placeholder we already ignore everywhere else — there's nothing to show for it, so it no longer gets reported. Thanks to @zapadee for the report.

## [2.15.8] - 2026-06-30

### Added

- **New "Charge Mode Changes Pending" sensor for Audi/VW (#583).** The portal now ships a little queue counter for charge-mode switches (e.g. flipping between manual and timer charging), right next to the charging-settings and charging-commands queues we already track. It's a diagnostic sensor, off by default — flip it on if you want to confirm a charge-mode change actually went through.

### Fixed

- **VW EU portal login that timed out got reported as an error (#576, #578).** When the EU Data Act portal was briefly slow or unreachable during sign-in, the timeout bubbled all the way up and showed up in the Error Reporter as if the integration had broken — same as the "backend temporarily unavailable" hiccups we already shrug off everywhere else. Now a connection drop or timeout during login is treated as exactly that: a transient blip, skipped for this poll, no error logged, no re-login churn. A genuinely wrong password (or a consent/2FA prompt) still surfaces normally, so nothing real gets swallowed.

## [2.15.7] - 2026-06-30

### Fixed

- **Electric and combustion ranges were swapped on plug-in hybrids (#555, #565).** On PHEVs like the Passat GTE 1.4 eHybrid and the Tiguan eHybrid, the "electric range" sensor showed the petrol range and the combustion sensor showed the electric one — battery and fuel levels read fine, only the two ranges were flipped. Turns out on these cars the *primary* engine is the combustion one (the opposite of an ID.x, where the primary engine is electric), and we were mapping the two ranges by position. Now we work out which range is which from the engine type, so electric and combustion line up with the VW app again. Pure EVs are unaffected. Thanks to the reporters of #555 and #565 for the clear write-ups.
- **VW EU login that ended in "check email and password" after a correct password (#527).** On accounts where VW shows a one-time consent/authorization page, the integration tried to accept it but submitted the form the wrong way, so VW rejected it with a blank `400` and login never finished. Two things were off: the consent form posts back to its own URL with the query string attached (where the security tokens live) and we were stripping that query off; and the form lists each granted scope as its own field, which we were collapsing down to one and dropping a required scope. Both are fixed now, so the consent step completes on its own and login goes through. Huge thanks to **@RaimondB**, who reproduced it offline, root-caused both defects, and verified the fix end-to-end on his own car. 🙏

### Added

- **New "Battery climate energy use" sensor.** Picks up the battery-climatisation (thermal-management) energy your car already reports on the EU Data Act portal — handy for the e-cars that pre-heat or cool the battery. It's a diagnostic sensor, off by default, so flip it on under the device if you want it.

## [2.15.6] - 2026-06-27

### Fixed

- **Honest message when a portal car can't take commands (#543).** If your car connects through VW's read-only EU Data Act portal and you try to send a command (lock, climate, charging), you used to get told to "disable read-only mode in the options" — but there's no switch that helps: the portal simply has no command path. The message now says that plainly, so you're not sent hunting for a setting that can't change anything. Cars where read-only really is just a toggle you flipped still get the old "disable it in the options" hint.
- **No more stray US/Canada dropdown for non-US cars (#465).** Setting up an EU car (or any brand before you'd picked one) showed a "country" field that only offered USA and Canada — confusing, since it never applied to you. That picker now only appears when you choose Volkswagen US/Canada, where it actually selects your region. Pick VW US/CA and the US↔Canada chooser is right there as before; everyone else never sees it.

## [2.15.5] - 2026-06-27

### Added

- **Optional ABRP (A Better Routeplanner) live telemetry push.** You can now feed your car's live data straight into ABRP so it plans routes around your real state of charge. It's off by default and opt-in: turn it on in the integration options, paste your ABRP token (and a developer api_key — see the README on how to get one), and a shipped blueprint uploads automatically whenever there's something new to send. There's a small diagnostic "ABRP data changed" sensor that makes sure the same snapshot never gets uploaded twice. Your location only ever leaves the house when an upload actually runs, and the token + key are never written to the log.
- **More mapped fields.** The "last update reason" — why the car last pushed a report to the backend (e.g. it started charging, ignition went on/off, climate ran) — now surfaces as a diagnostic sensor (disabled by default). One of the recurring VW-EU Scout fields, now off the list. Nothing hidden.
- **Bidirectional charging (V2G) limits (#541).** If your car reports them, the upper and lower charge-level limits it'll bidi-charge within now show up as two diagnostic sensors (disabled by default).
- **Sunroof position (#544).** On top of the open/closed state we already had, the actual sunroof position (as a percentage) now surfaces as a diagnostic sensor (disabled by default).

### Fixed

- **Aux-consumer consumption no longer shows a bogus 65535 (#544).** When the car had no reading, the average auxiliary-consumer consumption sensors were passing the "no data" placeholder through as if it were a real value. They now read empty in that case instead, so it can't poison your long-term stats.

- **VW US/CA: data reads work again on locked-down accounts with an S-PIN (#503).** Some US/Canada accounts could log in and list the garage but every per-vehicle read came back 403. If you've set your S-PIN, the integration now unlocks those reads the way the official app does — it asks for a short-lived per-car token and uses that for the data. It's done carefully: the token is cached and only refreshed when it expires (never on every poll), and if your S-PIN looks wrong or you're near the attempt limit it backs off immediately and falls back to the normal path, so it can't lock your S-PIN. Accounts without an S-PIN are unchanged. And a persistent 403 that used to stay silent now raises the repair notice after it keeps happening.
- **EU Data Act portal: "check email and password" with a correct password (#527).** After you typed the right login, the portal sometimes showed a one-time "authorize this app" consent screen instead of finishing — and the integration mistook that for a wrong password. It now accepts that consent for you automatically (you already entered your login and want it connected, exactly what the app does), so login just goes through. If for some reason it can't, you now get a clear "finish the consent in your browser" message instead of being told your password is wrong. A genuinely wrong password still says so.
- **Flash-lights button works again on VW/Audi (EU).** It was calling an endpoint that doesn't exist with the wrong body, so the car always answered "bad request" and nothing happened. It now sends the same request the official app does. If your car insists on a location for the flash, it retries with the car's last-known position automatically, and if there's no position yet you get a clear hint to wake the car first instead of a silent failure.
- **The US/Canada region setting is no longer saved on non-US/CA cars.** That dropdown only matters for Volkswagen US/Canada, but every brand was quietly getting "United States" stored in its config even when it was irrelevant — so a Swiss or EU car ended up looking like a US car in the diagnostics. It never affected your data (EU cars ignored it), but it was confusing and could have tripped up future code. Now it's only kept for Volkswagen US/Canada, where it actually does something; everyone else leaves it blank. Existing setups that already have the stray value keep working untouched.
- **Turning OFF read-only mode now actually re-enables commands (#543).** If your car was set up with read-only on, switching it off in the integration options had no effect — the old value still won and lock/climate/charge stayed blocked. Now your choice in the options always takes priority, so disabling read-only brings the command buttons back as expected.

## [2.15.4] - 2026-06-26

### Fixed

- **VW US/CA: clearer diagnosis when sensors stay empty (#503).** Login + the garage list now succeed (US/Canada selector), but if the per-vehicle data endpoints return 403, the integration classifies why — an inactive Car-Net / VW Connect subscription, a VW device-attestation lockdown, or a transient block — and raises a repair notice (with the cause in the debug log, no secrets) instead of silently showing nothing. Last-known data keeps showing.

- **Battery capacity / available energy were 10x too high (#534).** The EU-portal energy-content readings are in 0.1-kWh units but were passed through unscaled — an ID.4 showed 756 kWh instead of 75.6 (and 461 instead of 46.1 available). Now scaled correctly.

- **Clearer login errors (#527).** A portal login that fails for a non-password reason — terms/consent not yet accepted, a 2FA or onboarding step, a region/soft-block — no longer shows the misleading "check email and password". You now get the real reason and what to do (open the portal once in a browser, finish the prompt, retry), so users with correct credentials aren't sent chasing a password problem. Failure logging now records the landing page type/error code (no secrets) to pin the cause.

- **Charge-timer & slope-consumption now actually populate, and the Scout stops re-reporting them.** These EU-portal fields were only read under one payload shape and silently missed the realistic one — so they never showed AND recurred in the Vehicle Data Scout for every VW-EU user. Now read from either shape; uphill/downhill slope no longer collide; the Scout only lists genuine unmapped metadata.

- **VIN privacy.** Scout / error-report titles no longer expose the full VIN. For a car whose name was never changed (notably Audi, where CARIAD defaults the vehicle name to the VIN) the "model" fell back to the raw 17-char VIN — bypassing the last-6 masking the footer promises. The model is now omitted when it is (or contains) a VIN; the brand alone scopes the issue.

### Added

- **More EU Data Act portal fields mapped (#518).** Active charge target, charge-time display, charging power, and the dual charging-plug state set (plug 1 + 2: flap, flap-lock, lock, infrastructure, connection) now surface as diagnostic sensors. Nothing hidden — unmapped fields stay in the Scout.
- **More mapped fields (#521, #522).** Next-charging-timer schedule (start/finish/reachability), uphill/downhill slope consumption, the charging error code, and an outdoor-temperature alias. Diagnostic; low-confidence disabled by default; nothing hidden.
- **More mapped fields (#523).** Actual charge rate (folded into the charge-rate sensor), comfort settings (climatisation-at-unlock, mirror heating, front climate-zone enable) and the start/stop charging action. Diagnostic, disabled by default; nothing hidden.
- **More mapped fields (#528).** Start/stop modification, hood state, front tyre pressures, and the last-trip gas / range-gain / zero-emission aggregates (the short-term counterparts to the lifetime figures). Diagnostic, disabled by default; nothing hidden.
- **Audi next-charging-timer fallback (#530).** Some Audis report the charge-timer id + target-SoC-reachable under a different container than the integration was reading, so the sensor stayed empty. Now read as a fallback — the existing 'target SoC reachable' sensor populates. No new entities.
- **More mapped fields (#535).** App/master data-result status enums now surface as diagnostic sensors (disabled by default). With this, the recurring VW-EU Scout reports are down to genuine envelope metadata only.
- **More mapped fields (#537).** The next-charge-timer slot number (which of the profile timers is next) now surfaces as a diagnostic sensor (disabled by default).
- **More mapped fields (#538).** Rear + spare actual tyre pressures (the front pair shipped earlier) and the full target/required tyre-pressure set now surface as diagnostic sensors (disabled by default, unit ambiguous so unitless).
- **EU portal values could disagree with each other (#529).** Battery level, odometer and "last seen" were each read independently from the portal's multi-snapshot export, so they could come from different moments — wrong/uncorrelated readings and even a phantom "moved overnight". Now every field is taken from its latest sample so they stay in sync; the odometer's never-go-backwards guard now lives at the cross-poll layer where it belongs. (VW EU portal only; the BFF path was unaffected.)

## [2.15.3] - 2026-06-26

### Added

- **~28 more EU Data Act portal fields mapped (#465, #514, #515, #516).** Selected charge mode, max AC charge current, auto-unlock charge port, battery-care mode, bulk-charge threshold, door/closure safe-states + bonnet lock, sunroof / service-hatch / spoiler state, trip-odometer endpoints, fuel level + oil / AdBlue (SCR), per-corner tyre-pressure differentials, the instrument-cluster warning indicator, and more — now surface as (mostly diagnostic) sensors, named in all supported languages. Low-confidence fields are disabled by default; nothing is hidden — anything still unmapped stays visible in the Scout.
- **Vehicle model shown in the Scout / Error reports.** The auto-filed issue title and body now include the vehicle model (e.g. "…on volkswagen ID.4"), so reports are recognisable at a glance. Model name only — no VIN or other personal data.
- **More mapped fields + surfaced entities (#517).** `hv_soc` (folds into State of Charge), long/short-term auxiliary and gas consumption averages, range-gain and zero-emission distance, and the charger-update trigger; plus new sensors for battery available/capacity energy (kWh), Škoda trip costs, and oil level (%). Opaque/heartbeat fields (`scope_potential_total`, `echo`) stay Scout-only.
- **MBB durable-login setup translated** into French, Spanish, Dutch, Polish, Czech and Swedish (was English-only).

### Fixed

- **VW US/Canada EVs: battery, range and charged energy now populate (#503).** v2.15.2 read these from the wrong endpoint (`…/hvbattery` is only the departure-timer "use HV battery" toggle) and from guessed field names, so nothing filled. Verified against the dismantled MyVW app: the EV State of Charge, range and charged energy live on the charge-summary `batteryStatus` object (`currentSOCPct`, `cruisingRange.range`, `chargeEnergy`), and the charge-complete time field is `remainingChargingTimeToComplete` (the prior `_min` suffix never matched). All corrected.
- **Charging error code:** a `0.0` value is now treated as "no error" instead of surfacing a bogus code.
- **Charged energy is per-session, not lifetime (#511).** The portal's `charge_energy` (and the VW US/CA charge value) is a current-session gauge that reads 0 when idle — it was mislabelled onto the lifetime **Total Charged Energy**, and now feeds the per-session **Charged energy** sensor where it belongs. The lifetime total stays sourced only from genuinely cumulative fields (CUPRA/SEAT/Škoda).
- **Volkswagen EU login uses the current app version** (User-Agent We Connect 3.63.2; a stale 3.61.0 was still riding the login/data path while the command path already used 3.63.2).
- **Robustness (full-codebase audit).** The VW US/Canada vehicle model now appears in Scout/Error reports; the climate / on-board-electronics energy fields now populate (were mapped to non-existent keys); de-duplicated two sensor definitions; and a charging-state sentinel value can no longer hide an unrelated field from the Scout.

## [2.15.2] - 2026-06-25

### Added

- **More charger-detail fields (#513).** External power supply state, energy flow, charging reason, charging error code, remaining-time charge target, and the charge-port LED (colour + pattern, disabled by default) now surface as (mostly diagnostic) sensors. The keep-alive `echo` field and raw IDs stay Scout-only.

### Fixed

- **VW US/Canada EVs showed no battery or range (#503).** The EV traction State of Charge and electric range come from the dedicated `…/hvbattery` endpoint and `cruiseRangeFirst`, not the 12V `rvs.batteryStatus` / bare `cruiseRange` we read before. The integration now reads both (additive fallbacks), verified against the MyVW app. Confirmed against the dismantled MyVW APK.
- **Charging / climate remaining-time read as seconds (#511).** The EU Data Act portal sends these durations as seconds with a trailing `s` (e.g. `"2400s"` = 40 min, `"0s"` = 0); v2.15.1 read them as a plain number and left the sensors empty. They now convert `Ns` → minutes, and the climate-time read also accepts the `remaining_climate_time` key. A bare number is still treated as minutes (older firmwares). Thanks to @Ra72xx for the sample data.

## [2.15.1] - 2026-06-25

### Added

- **Volkswagen US/Canada: region selector.** Setup now asks US vs Canada, so Canadian accounts authenticate against the Canadian backend and client id instead of silently defaulting to the US one (which made Canadian logins fail). Existing entries keep working (default US). (#503)
- **~30 more vehicle-data fields mapped.** Many fields the Vehicle Data Scout surfaced now become proper sensors — charge type / scenario / reason, charged energy, battery-care target, available & maximal energy content, trip and lifetime consumption + recuperation, parking brake and lights, per-corner tire-pressure status, LPG/CNG, engine status and more (several diagnostic or disabled-by-default). Nothing is hidden — anything still unmapped stays visible in the Scout. (#504, #508, #509, #510)
- **EU Data Act portal: charged energy.** The older charger format also reports `battery_state_report.charge_energy`; it now maps to the cross-brand charged-energy sensor (`total_charged_energy_kwh`), the same one CUPRA/SEAT already populate.
- **volkswagen.de setup now states the prerequisite.** The opt-in Volkswagen.de website channel returns no data unless your Volkswagen ID is the vehicle's **primary user** — the setup screen now says so (complete "Confirm identity" once on volkswagen.de). Added in all supported languages.

### Fixed

- **Target SoC (and other repeated fields) could show a stale value (#465).** The EU Data Act portal ships a flat, ordered event-log where each snapshot's capture time arrives as its own `car_captured_time` data-point. When a field changed across snapshots (e.g. battery-care lowering the charge target from 100% to 80%), the parser tied on the dataset-level timestamp and kept the first-seen (stale) value. It now carries the running `car_captured_time` so the value from the latest snapshot wins. Thanks to @RaAdNe for the precise diagnosis and data.

### Docs

- Regenerated the 6 language READMEs (fr/es/nl/pl/cs/sv) from the current English README — localized the sponsor text (was English), corrected the install steps to HACS Default, fixed the language picker; removed the orphan `README.en.md`.
- `NOTICE.md`: corrected the copyright footer to GNU AGPL v3.0-or-later (was Apache-2.0); added Bentley to the trademark table; replaced placeholder reference URLs with plain-text credits.
- `ATTRIBUTION.md`: use the current display name "VW Group Connect" as the primary name (keeping "VAG Connect" in the protected-names list).
- `CONTRIBUTING.md`: added Bentley to the live-testers table.

## [2.15.0] - 2026-06-25

First stable release of the 2.15.0 line (consolidates the `2.15.0a*` / `2.15.0b*` betas). Highlights:

### Added

- **Command channel for portal-primary setups (opt-in).** Climate and charging commands now work for accounts whose data comes from the EU Data Act portal, via a second sign-in on a durable command backend. Opt-in per entry; existing read-only setups are unchanged.
- **Portal-safety / last-known-good cache.** Each vehicle's last good readout is cached locally and restored across restarts, so a momentary empty/failed portal fetch no longer blanks your dashboard — values carry forward (the odometer never goes backwards) until fresh data arrives, and the failed poll just feeds the staleness watchdog.
- **More fields surfaced.** The Vehicle Data Scout no longer hides any portal field, and the older VW EU charger format now maps its battery level to State of Charge.

### Fixed

- **VW US/Canada login (#503).** Two separate causes — an over-widened OAuth scope and a stale, separate sign-in client-id — both removed; the North-America flow now matches the live MyVW app end-to-end.
- **Duplicate / stale portal fields (#465, #504).** Reworked the portal field de-duplication so the freshest value wins and array-nested fields don't collapse onto the wrong key.
- **App-identity refreshed** to current builds (We Connect 3.63.2, myAudi 5.5.1) so the command/data endpoints stop rejecting stale versions.
- **Škoda lock/unlock** uses the current PIN field name.

### Changed

- **Honest CUPRA/SEAT command status.** Those brands' command backend is now gated server-side (App Check + WAF); the integration says so plainly instead of silently failing. Data continues via the EU Data Act portal.
- **MEB "commands unavailable" notice** surfaces as a Home Assistant repair when a newer MEB car can't use the legacy command channel.

## [2.15.0b14] - 2026-06-25

> **Beta / pre-release** — the actual fix for VW US/Canada login (#503).

### Fixed

- **VW US/Canada login (#503) — the real cause.** b13 reverted an over-widened OAuth scope, but sign-in still dead-ended at VW's North-America sign-in service with "no code in …/signin-service/v1/b680e751…". The real culprit was a stale, separate "browser" client-id (`b680e751…`) that was used *only* to build the NA sign-in URL — but the current MyVW app uses the same app client all the way through. Removed that stale override so the sign-in now uses the real per-country MyVW client; confirmed against the live MyVW app (its code has zero `b680e751` / `identity.na` literals) and an independent working US setup. (A live US/CA login confirms the close.)

## [2.15.0b13] - 2026-06-24

> **Beta / pre-release** — one car, reads *and* commands: the EU Data Act portal for data + a durable-MBB command channel on top. And a simpler 2-path setup.

### Added

- **The setup login is now two clear paths.** "Browser-Login (QR)" for Audi / Škoda / SEAT / CUPRA (passwordless, two-way native), and "Portal (E-Mail + Passwort)" for Volkswagen EU / Porsche. The standalone "MBB durable login" and "Volkswagen.de" menu entries are gone — MBB is now a toggle on the Portal path, and vw.de stays an options-only extra read channel.
- **MBB remote commands on a Volkswagen portal entry.** On the Portal login you can tick "Enable MBB remote commands"; after the email/password sign-in it adds one QR confirm and arms a durable-MBB command channel **alongside** the portal. Result on one device: reads come from the EU Data Act portal, and lock / climate / charge / target-SoC / window-heating commands go through MBB. The MBB bearer refreshes itself (survives restarts). If the car turns out to be MBB-ineligible (newer ID/MEB), the portal entry is still created — you just get reads without commands, instead of the whole setup failing.
- **Portal-safety: your recorded values now survive an outage *and* a restart.** The integration keeps a small local cache of each car's last-known telemetry. When a poll comes back empty or partial — a common thing on the EU Data Act portal — it no longer blanks the fields it didn't get this time: SoC, odometer, range, fuel, service intervals and the like stay visible at their last recorded value until real new data arrives. That cache is now written to disk, so after a Home Assistant restart your dashboard shows the recorded values immediately instead of "unknown" until the first poll finishes. Volatile states (locks, charging, doors) are deliberately *not* carried forward — a stale "unlocked" would be misleading — so those still reflect the latest poll.
- **A backwards odometer reading is rejected.** The portal occasionally serves a stale or zero mileage, so the "km" sensor would jump down and then back up. It now keeps the recorded value whenever a fresh reading is lower than what we already have, so the odometer only ever moves forward.
- **A clear notice when an MEB / ID car can't do remote commands.** If you enable MBB commands on the Portal login but the car turns out to be an MEB / ID-family model (ID.3/4/5/7, Enyaq, Born, Q4), commands aren't possible — VW's MEB backend doesn't speak the durable command path. Instead of silently missing the lock/climate/charge entities, the integration now creates the read-only entry **and** raises a clear repair explaining it's a known MEB limitation, not a setup error. The README also gained a "Known limitations" section spelling out MEB, the CUPRA/SEAT command block, and the portal's thin-and-growing data.

### Changed

- A Volkswagen portal entry that has the MBB command channel armed is no longer forced read-only — its command entities (lock/switch/climate/buttons) now appear. A portal entry without the command channel stays read-only as before.
- **The Vehicle Data Scout no longer hides any fields.** b10 had started filtering "plumbing" fields (request ids, envelope timestamps, and the like) out of the Scout report — that was the wrong call, because it also hid things worth mapping. The Scout now surfaces *everything* the portal sends, so nothing gets quietly dropped before it can be turned into a real sensor.
- **A device-attestation block on commands is now reported honestly.** VW is rolling Firebase App Check / Play Integrity across its backends (it already killed CUPRA/SEAT reads). If that ever reaches a command channel, the 403 used to be mislabeled as "not entitled" — sending you to chase a subscription renewal that wouldn't help. It's now recognised from the response body as an attestation lock and surfaced as exactly that: commands gone on that channel, reads continue. (No current channel is affected — this is so the day it happens, the message is the truth.)
- **VW EU command headers now track the current We Connect app version.** The app-identity the integration presents to VW's command endpoints was pinned at an old build (3.51.1); it's bumped to the live `com.volkswagen.weconnect` version (3.63.2, confirmed by dismantling the current APK). These endpoints can reject stale app versions, so tracking the real build keeps the command path healthy — and a regression test now pins it so it can't quietly drift stale again.
- **Audi app-identity refreshed to the current myAudi build, everywhere.** All four places the integration claimed to be the myAudi app were stale (4.31.0 / 4.24.0 / 4.18.0); they're now the live `de.myaudi.mobile.assistant` version 5.5.1 (versionCode 800344232, verified against the dismantled APK manifest) — the brand config, GraphQL headers, the MBB app-identity and the market-config fetch. Same rationale: stay indistinguishable from the real app so a future version check can't lock us out. Pinned by a regression test.
- **The CUPRA/SEAT "online services blocked" notice now names the real cause and is honest about it.** Reverse-engineering the current apps confirmed VW's block is **device attestation** (Firebase App Check / Play Integrity) plus a web-application firewall on the SEAT/CUPRA backend — not a header or app-version problem, and not something an open-source client can reproduce. The repair message (all 9 languages) now says exactly that and sets honest expectations: remote **commands** for these brands are unlikely to come back, while vehicle **data** keeps flowing through the EU Data Act portal. Also documented the dismantle-verified fallback OAuth client-ids (for the `client_id` override option) in case VW ever blocklists a primary. (#464)

### Fixed

- **Volkswagen US / Canada login was broken (#503).** A v2.11.0 change widened the North-America OAuth scope from `openid` to `openid profile cars vin` based on a source-read that was never live-tested against the NA backend — and it silently regressed sign-in: the authorize redirect stopped returning a code, so login failed with a misleading "email or password wrong". Reverted to bare `openid`, which is **confirmed against the live MyVW app** (the dismantled APK carries `openid` as its only OAuth scope; the wider chain appears nowhere) and matches the value an NA tester verified in #269. (Canada keeps its own app client-id, which the APK confirms is genuine — it wasn't the cause.)
- **Wrong value shown when VW sends duplicate data points (#465).** The EU Data Act portal sometimes returns several data points with the *same* name (e.g. multiple SoC or target-SoC candidates). We were resolving ties by array order, so a stale duplicate could win — one reporter's ID.5 showed 80% SoC while the car and app showed 90%. Now duplicates are resolved by each point's own capture time (a genuine timestamp beats the shared dataset floor; the newer of two real timestamps wins; with neither, the first is kept deterministically), and a field nested inside an array (like a charge profile) no longer collapses onto the active top-level value.
- **State of charge now shows for cars on the legacy charger format (#504).** Some VWs report the traction battery only as `battery_level_HV` (the old Car-Net charger report) instead of the standard field, so their SoC sensor was blank. It's now read as a last-resort source — cars that send the standard field are unaffected, and the duplicate-resolution above keeps the freshest reading.
- **Škoda unlock now sends the correct S-PIN field.** A reverse-engineering pass against the current MyŠkoda app showed its unlock body uses the wire key `currentSpin` (and never a bare `spin`) — our old `spin` key was being rejected by Škoda's backend, so unlock-with-PIN failed. Fixed to `currentSpin`. (Lock is unaffected — it needs no PIN.)

## [2.15.0b12] - 2026-06-23

> **Beta / pre-release** — the EU Data Act portal as a *supplementary* read channel now actually delivers data (e.g. portal reads alongside MBB commands).

### Fixed

- **Adding the EU Data Act portal as a read channel on a non-portal entry (e.g. an MBB command entry) returned no data — silently.** The portal only delivers while an active "continuous data request" exists for the car, and the request kickoff was only ever run for a portal-*primary* entry. So a portal *supplementary* never got a request → it logged in fine but every read came back empty, with nothing in the log to explain it. Now the kickoff also runs for a configured portal supplementary (it shares the signed-in session), and the "no active data request" notice is surfaced for the supplementary channel too, so it's no longer a silent dead end. **Note:** the kickoff is still opt-in — turn on "EU Data Act: automatically create a custom data request" in the options for the channel to populate (it starts a 1-month data subscription on your portal account).

> **Beta / pre-release** — keeps a durable-MBB entry alive (it was going stale ~an hour after setup).

### Fixed

- **Durable-MBB entries stopped working about an hour after setup.** The MBB bearer was only ever refreshed when a request came back with "expired" — but the main MBB reads deliberately don't trigger a refresh on a rejection (to avoid hammering the login endpoint when the car's data access is simply restricted). The result: once the bearer actually expired, every read failed with "token expired" until a restart. It's now refreshed proactively, just before it expires, so an MBB entry (and its remote commands) stays alive on its own. This is what makes the "commands via MBB + reads via the EU Data Act portal" combination usable unattended.

### Security

- **The EU Data Act portal password was stored in the clear in the diagnostics download.** The supplementary-channel credentials added in b8/b9 (portal email + password, and the vw.de session cookies, which carry the sign-in tokens) were never registered with the diagnostics redaction, so a downloaded diagnostics file exposed them in plaintext — the very file users attach to bug reports. They're now redacted like every other secret. **If you added a portal or vw.de read channel on an earlier 2.15.0 beta, change that portal password** and don't re-share any diagnostics you exported from those builds.

### Added

- **You can now remove a supplementary read channel.** Until now the vw.de and EU Data Act portal read-channel toggles could only ADD a channel — once added there was no way to turn one back off, so a redundant or no-longer-resuming channel kept retrying (and showing a "re-add" repair) on every restart. The options now show a "Remove …" toggle for each channel that's currently active; ticking it clears that channel and reloads, and any leftover "re-add" repair is cleared with it.

## [2.15.0b10] - 2026-06-23

> **Beta / pre-release** — EU Data Act portal: many more signals mapped, a lock-state bug fixed, and a tidier Scout. (Includes the b9 vw.de silent-resume fix.)

### Fixed

- **The "doors locked" sensor could read *unlocked* on a locked car.** The portal reports each door's lock state individually (and no single overall flag), which we weren't reading — so the lock sensor fell back to a stale/empty value and showed unlocked. It's now derived from the actual per-door lock states, so a fully-locked car reads locked.

### Added

- **Lots more from the EU Data Act portal, now as proper sensors.** Per-door open + lock states, the tailgate and bonnet, per-window open/closed + how far each window is down, last-trip distance & duration, lifetime average speed & driving time, average monthly mileage, an inspection-due warning, and remaining charge/climate time — all read from the portal and mapped onto the right entities (enum meanings + units taken from the official data dictionary).
- **The Vehicle Data Scout report now shows the official spec name** for each unknown field (it was blank before because the lookup didn't match the portal's field names).

### Changed

- **The Vehicle Data Scout is less noisy.** Pure plumbing / identity fields (request ids, hashed account id, VIN, envelope timestamps, measurement-quality flags) are no longer reported as "new fields" — only real vehicle signals are.

## [2.15.0b9] - 2026-06-23

> **Beta / pre-release** — the vw.de channel finally resumes silently (no more code-email on every restart).

### Fixed

- **vw.de no longer asks for a new email code on every reload.** The session now resumes through a silent re-authorization (it re-uses the long-lived sign-in cookie to mint a fresh session in the background), instead of probing a data endpoint and falling back to a full login when that probe failed. The data probe was the wrong test — the portal session quietly expires about half an hour after sign-in even while the underlying sign-in is still good, so it kept forcing a needless code-email. The silent resume only ever asks for a code when the sign-in itself has genuinely expired (a one-time re-add), never on a routine restart. Applies to both the vw.de primary mode and the vw.de supplementary read channel.
- **vw.de reads were silently coming back empty.** Every request now sends the CSRF token the portal expects (echoed from its cookie), which the reads require — without it the portal answered with empty data.

## [2.15.0b8] - 2026-06-23

> **Beta / pre-release** — the real two-way + reads combo: EU Data Act portal as a supplementary read channel.

### Added

- **Add the EU Data Act portal as a read channel on top of a command-capable entry (e.g. durable MBB).** MBB gives you remote commands and fuel but can't read SoC / charging / odometer / service; the portal can. Tick "Add an EU Data Act portal read channel" in the options, sign in with email + password (no one-time code), and the portal's reads are merged onto your primary channel — so you get commands *and* full data on one device. Read-only, email/pw with automatic re-login (reliable, unlike the OTP-bound vw.de channel), and it never touches command routing. The merged "Data source channel" sensor shows both channels contributing.

## [2.15.0b7] - 2026-06-23

> **Beta / pre-release** — event-loop hygiene.

### Fixed

- **No more "blocking call" warning from the data dictionary.** Once the Scout report started naming portal fields from the dictionary, the first lookup read the 288 KB spec file on the event loop. The cache is now warmed off-loop at setup, so the in-poll lookups never block.

## [2.15.0b6] - 2026-06-23

> **Beta / pre-release** — service-countdown sign fix, no more vw.de code-email storm, unmapped fields in the Scout.

### Fixed

- **Service & oil-change countdowns now read correctly.** They were showing as overdue (negative) when the car actually has them coming up — the portal reports these as a negative "remaining until due", so "due in 155 days / 14900 km" was landing as −155 / −14900. Now flipped: a positive countdown, and only genuinely-overdue cars go negative.
- **The vw.de channel no longer triggers a new code-email on every poll.** When its session couldn't be resumed it kept starting a fresh login, which made Volkswagen send a new one-time-code email each cycle. It now only probes (no email) and raises the re-login repair once — re-add it from the options when you're ready, no more code-email storm.

### Changed

- **Unmapped portal fields now also show up in the Vehicle Data Scout report**, not just on the raw-fields sensor — so the long tail of fields we haven't curated yet is visible and one-click reportable, which is how more of them become proper sensors over time.

## [2.15.0b5] - 2026-06-23

> **Beta / pre-release** — more service data straight from the portal + graceful vw.de re-login.

### Added

- **Service & maintenance intervals, lock status and window heating now come straight from the EU Data Act portal.** The raw-field discovery surfaced that the portal already sends inspection + oil-change intervals (distance and days), central-lock state and window-heating state for Golf-class cars — these are now mapped onto the proper sensors, so you get them without needing the separate vw.de channel.

### Fixed

- **The vw.de read channel now fails gracefully instead of silently.** When its session can't be resumed without a fresh one-time code, it raises a clear "Volkswagen.de read channel needs re-login" repair you can act on, rather than just logging "stale". The primary channel is unaffected, and the repair clears itself once the channel is back.

## [2.15.0b4] - 2026-06-23

> **Beta / pre-release** — supplementary-channel resume fix.

### Fixed

- **The supplementary vw.de channel now resumes from freshly-added cookies.** Even after re-adding the channel, it kept reporting "cookies stale" — the cheap resume probe returns a redirect for a valid session, and the supplementary path gave up on it instead of trying the full silent login (which a valid session completes without an OTP). It now falls back to that login exactly like the primary vw.de channel, so a freshly-added channel arms and merges. If the session is genuinely dead the log now says why (`login=otp_required` → re-add), and the primary channel is unaffected either way.

## [2.15.0b3] - 2026-06-23

> **Beta / pre-release** — declutter: hide entities without data.

### Added

- **Entities without data are now hidden by default, so a vehicle isn't flooded with dozens of "unknown" sensors.** Only sensors and binary sensors that actually have a value are created; an entity still appears automatically the moment its value first arrives (the dynamic spawner now re-evaluates every poll and tracks entities individually). Controls (lock, climate, buttons, …) are never affected. Untick **"Hide entities without data"** in the integration options if you'd rather see everything.

## [2.15.0b2] - 2026-06-23

> **Beta / pre-release** — hotfix for the b1 multi-channel live test.

### Fixed

- **The supplementary vw.de read channel now arms reliably alongside an EU Data Act portal entry.** In b1 the supplementary channel reused the shared session, and because vw.de and the portal share the same login host and cookie names, importing the vw.de cookies clobbered the portal's — the resume probe failed ("cookies stale") and the merge never ran. The vw.de channel now uses its own isolated session, so the two channels can't interfere; this also clears the duplicate-entity warnings that the cookie clash could trigger. Update and restart — the saved cookies should now resume directly (re-add the channel only if they've genuinely expired).

## [2.15.0b1] - 2026-06-23

> **Beta / pre-release** — bundles the unreleased a11–a13 work plus the EU Data Act read-path expansion, the official data dictionary + raw-field discovery, the multi-channel merge with a live vw.de opt-in, and reliability hardening. Install via the HACS beta channel to test.

### Added

- **Rich EU Data Act reads for legacy & PHEV cars, with miles→km auto-conversion.** Flat field names used by older Golf GTE and PHEV vehicles now map cleanly — fuel level, oil level, outside temperature, service intervals — instead of being silently skipped. Distance units are detected and converted (miles → km via the companion unit field) so readings land in the car's market unit. Drivetrain detection now infers electric/combustion/hybrid from the data present, fixing EVs shown as combustion-only and PHEVs as neither.
- **The official EU Data Act data dictionary (V5.0, 1142 fields).** The Vehicle Data Scout report now names an unmapped field from the official spec when its path is a known identifier — opaque UUIDs become human names for maintainers.
- **Raw field discovery — one diagnostic sensor for unmapped portal fields.** A single disabled-by-default sensor per car shows how many portal fields aren't curated yet, with the full value set in its attributes. Same detection that feeds the Scout, so you see every value the backend sent without waiting for a curated mapping — and without an entity per field. Available in all 8 languages.
- **Multi-channel data merge with provenance.** For cars whose data is split across channels (fuel on one, SoC on another, odometer on a third), a field-level union now gap-fills in priority order — the highest-trust channel is never overwritten — and records which channels contributed in a new "Data source channel" diagnostic sensor.
- **Live multi-channel polling: opt-in vw.de read channel.** A new "Add a Volkswagen.de read channel" option pulls VIN / odometer / service / master data from volkswagen.de in parallel and merges it onto your primary channel. Read-only, Volkswagen-only (email + email-OTP). Single-channel setups are byte-for-byte unchanged, and it fails gracefully if vw.de is unavailable.
- **MBB "two-way available" diagnostic sensor.** Tells you when the durable Car-Net backend grants a remote command (climate/charge) on a currently-licensed service — derived from the operation list, no extra request, icon-only.
- **Charge-rate and plug-connection mapping** from the EU Data Act portal, plus the energy-dashboard tip in the README (use the cumulative charged-energy sensor, not the per-100 km averages). Bentley added to the brand table.

### Fixed

- **Account rate-limit protection.** When the backend hard-limits (HTTP 430, or 429 after retries are spent), the integration now pauses all requests on that account for a cool-down (429 → 30 min, 430 → 2 h) instead of hammering and risking an IP ban. Self-clears on expiry.
- **Bogus "no reading" values no longer reach your dashboard.** Portal sentinel markers (65535 / 2147483647 / 4294967295, −1 charging-time, 0/1 tyre-pressure) are filtered out instead of poisoning SoC / range / odometer statistics. The odometer also never jumps backwards — monotonic fields keep the highest reading regardless of delivery order — and bare fields inherit the dataset capture time so the freshest snapshot wins.
- **Per-session/trip kWh deltas no longer carry the energy device-class** (HA 2026.6 rejects energy + measurement together).
- **No source-aliasing in the merge** — gap-filled list/dict fields are deep-copied so a merged result can't be corrupted by a later change to a source snapshot.

### Changed

- **VW enum labels shortened for display** (strip CHARGE_STATE_/CHARGING_MODE_/PLUG_STATE_… prefixes) so charging state reads cleanly — display only, logic unchanged.
- **Coordinator passes its config entry explicitly** (HA 2026.8 readiness).
- **Automatic discovery of unmapped portal fields** keeps logging the long tail so coverage grows from real payloads, not guesswork. Test suite modernized for Python 3.14.

## [2.15.0a10] - 2026-06-22

> **Alpha / pre-release** — reliability batch (from the failsafe audit + a tester log).

### Fixed

- **Vehicle entities keep their last values during a portal outage instead of going blank.** When the EU Data Act portal times out or is briefly down, the car's sensors used to flip to unknown for that cycle (and the "last updated" time falsely reset to now). The integration now recognises a no-data poll and keeps the previous values visible (marked stale) — so a portal hiccup no longer blanks your dashboard. A brand-new car with no data yet still appears and fills in as before.
- **MBB no longer hammers the login endpoint when a read is blocked.** On the durable-MBB path, a blocked status read could trigger a token refresh every poll, which tripped the safety guard ("pausing to prevent IP ban"). Those reads no longer refresh on a block, so the integration stops risking a rate-limit / IP ban while the read channel is unavailable. The scheduled refresh still keeps the session fresh.

## [2.15.0a9] - 2026-06-22

> **Alpha / pre-release** — small fix from a tester report (#442).

### Fixed

- **Climatisation no longer shows as "on" when the car can't actually start it.** On some Audi/VW cars the climatisation status comes back as `invalid` — a no-data state the car returns when climatisation can't run, e.g. at a low battery. The integration was treating anything that wasn't an explicit "off" as "running", so the climatisation binary sensor flipped on by mistake. It now treats those no-data states as off, so the sensor reflects reality.

## [2.15.0a8] - 2026-06-22

> **Alpha / pre-release** — small but important UX fix from a tester report (#498).

### Fixed

- **The MBB login now tells newer ID / MEB owners why it can't work, instead of looping the VIN screen.** If the durable MBB login returns `Unknown user`, that means the car is a newer ID.3/4/5 / MEB model that was never enrolled in the legacy Car-Net backend — so the durable login + remote commands genuinely can't reach it. Instead of bouncing you back to the VIN form with a cryptic error, the flow now stops with a clear message pointing you to the EU Data Act portal (or email + password) for those vehicles. The MBB login is for older Car-Net cars (most PHEV / combustion models).

## [2.15.0a7] - 2026-06-22

> **Alpha / pre-release — the "Endstufe" two-way test.** The deep dive settled what the durable VW login can and can't do, and this build ships the part that genuinely works durably: **remote commands**. No re-add needed — update and restart, then try a command.

### Added

- **Durable two-way commands over the MBB login: climate, charging and charge target.** The investigation proved the durable (password-free) VW login can't *read* live data — VW closed that path for this token type — but it CAN issue **commands** (the command path does an extra authorisation step that reads don't). So with the MBB login + your S-PIN you now get durable **climate start/stop, window heating, charging start/stop, and set charge target %** — and these keep working across restarts, no app-attestation, no ~1‑hour re-login.
- **Country-agnostic by design.** Commands are routed through the car's own service directory (the operationList), which hands over the right server per service per market — so this works for German, Austrian, Dutch, etc. VW EU vehicles, not just the Swiss car it was discovered on. Each command is only attempted if the directory says your car+subscription actually allows it (so you don't waste S-PIN tries on a 403).

> ⚠️ **Live-test the commands deliberately.** The command bodies are grounded against the classic Car-Net app + the car's own directory but haven't been actuated on every model — try one (e.g. start climate) and check it acts. A wrong S‑PIN counts toward the 3‑try lock, so the integration refuses to act when the car reports you're down to your last attempt. Reads still come from your other channel (EU Data Act / the existing login) — the MBB login is login + licence + commands.

## [2.15.0a6] - 2026-06-21

> **Alpha / pre-release** — the diagnostics paid off. Live probing revealed the durable VW login works perfectly *and* reads data — the empty status on the test car was simply an **expired We Connect subscription** (every paid service was off). This build reads the car's service directory so it knows that, and tells you instead of failing silently. No re-add needed — update and restart.

### Added

- **The MBB integration now reads your vehicle's "service directory" (operationList).** This is the authoritative list of which connected services your car has and whether they're licensed/active. From it the integration now:
  - **tells you when your We Connect / connect subscription is expired or inactive** — the `subscription_active` / subscription-expiry / days-remaining sensors are populated, and the log says "renew it in the app" instead of dumping cryptic 403 errors;
  - **skips the status read entirely when the subscription is inactive** (it would only 403), so the log stays clean and the poll is faster;
  - lays the groundwork for the full command set later (the directory hands over the exact per-service hosts and the granted remote-commands for climate, charging and timers).

> ℹ️ If your car shows everything "unknown" and `subscription_active` is off, that's the cause — renew We Connect for that vehicle (or test on a car with an active subscription) and the data flows. The durable login itself is working.

## [2.15.0a5] - 2026-06-21

> **Alpha / pre-release** — diagnostics build. a4 got the car to appear via the VIN; now the status read returns nothing, so this surfaces exactly why. No re-add needed — just update and restart.

### Changed

- **MBB status read now logs exactly what the server returns.** Your Golf GTE shows up but all sensors are "unknown" — to pin down whether the status endpoint rejects the token, returns an empty body, or returns data in a shape we don't yet map, the read now logs the host/country it used and, on an empty result, the exact field IDs (or envelope keys) the car returned. This is the same diagnostic approach that pinned the garage issue in one step.

## [2.15.0a4] - 2026-06-21

> **Alpha / pre-release** — second live-test follow-up. The diagnostics from a3 pinned the exact blocker, and this fixes it.

### Fixed

- **MBB: you now enter your VIN directly, and the car finally appears.** The a3 diagnostics showed the durable VW token is allowed to read your *car* but not to list your *account's garage* (the server replied `403 — no permission for systemId XID_APP_VW`). That's expected for this token type — so the MBB login now has a **VIN field**: enter your 17-character VIN (windscreen / registration; comma-separate multiple cars) and the integration uses it directly. Everything car-level — status, and lock/unlock with your S-PIN — works with this token; only the garage *listing* didn't, and the VIN field replaces it.

> ℹ️ **If you already added the MBB login on a2/a3:** delete that entry and add it again with the new "Volkswagen EU — Durable Login (MBB)" option so you can enter the VIN. The browser confirm is quick.

## [2.15.0a3] - 2026-06-21

> **Alpha / pre-release** — follow-up to a2 from the first live test. The MBB durable login itself worked end-to-end (browser confirm → durable token); the only blocker was finding your cars afterwards.

### Fixed

- **MBB: the car list is now looked up with the right country and headers.** On the first live test the durable VW login succeeded but the integration found no vehicles, because the account-list call was hardcoded to Germany (`DE`) and was missing the app-identification headers the VW servers expect. It now reads your account's country from the login token (e.g. `CH` for Switzerland), sends the `Volkswagen`/`myAudi` app headers on every MBB call, and tries the known server/country combinations until your cars appear.
- **Better diagnostics:** if the car list still comes back empty, the log now shows the exact HTTP status for each server/country it tried (instead of a vague "APIError"), so the endpoint can be pinned down quickly.

## [2.15.0a2] - 2026-06-21

> **Alpha / pre-release** — please live-test and report back. Expect rough edges.

### Added

- **Volkswagen EU durable login (MBB) — now a real option in the integration, not just a test script.** There's a new sign-in choice "Volkswagen EU — Durable Login (MBB)": you confirm once in your browser (no password stored in Home Assistant) and the integration keeps a long-lived, self-refreshing session that survives restarts — unlike the read-only portal. Add your S-PIN in the options to also get **two-way lock/unlock**. VW-only, alpha — the status read works best for combustion/PHEV (fuel level, range, AdBlue) for now; EV battery fields via this path come later.
- **Remote lock/unlock over the MBB path**, using the classic security-PIN handshake. The S-PIN is checked locally before anything is sent so a typo can't burn one of your three tries, and the integration refuses to act if the car reports you're down to your last attempt (3 wrong PINs locks it until you reset in the car/app).

> ⚠️ The durable VW path needs a confirmation from your account to fully verify end-to-end on real cars — that's exactly what this alpha is for. If lock/unlock reports a failure with the doors open or the key inside the car, that's the car refusing, not a bug.

### Internal (MBB hardening, pre-release review)

- The MBB session now auto-refreshes when its token expires (previously the durable token could go stale after a restart and the car would show "unknown" until you re-confirmed in the browser — the whole point of "durable" is that it shouldn't).
- Tightened token isolation: several background calls (capability/trip-stats prefetch, the field-probe pass, wake, charging-station lookup) are now skipped for MBB sessions so the MBB token is only ever sent to the MBB servers, never to the (dead, for VW) app backend.

## [2.15.0a1] - 2026-06-20

> **Alpha / pre-release** — ships the latest reverse-engineering findings for live testing. Expect rough edges; please report what you see.

### Added

- **Bentley is now a selectable brand (login + read).** My Bentley runs on the same backend as Audi, so it slots straight in. Two-way (commands) for Bentley is a follow-up.
- **Login resilience for Škoda, SEAT and CUPRA.** If the app's login key ever gets rotated by the manufacturer, the integration now has spare keys to fall back to automatically — so a rotation doesn't lock you out.
- **VW Group app-atlas research** in `docs/research/` — a catalogue of every brand app's login scheme, plus the discovery of a durable, refreshable login path for Volkswagen that gets past the new app-attestation wall. A local test tool (`scripts/mbb_dag_test.py`) lets you verify the VW path against your own account via a confirmation link (your credentials stay in your browser; it never prints tokens).

### Changed

- **Project relicensed to GNU AGPL v3.0-or-later** (was Apache-2.0). Forks must stay open-source under the same license. See [`ATTRIBUTION.md`](ATTRIBUTION.md) for the attribution + naming terms, and consider supporting the project via GitHub Sponsors.

### Fixed

- The advanced OLA User-Agent override for SEAT/CUPRA is no longer silently overwritten, so it actually applies now.

## [2.14.10] - 2026-06-18

### Fixed

- **volkswagen.de website login (beta): the email code is finally accepted instead of looping with a new code every time.** Entering the emailed code kept failing as a "credential issue", and a fresh code was sent after each attempt. The login page's code box isn't always named the same thing internally, and the integration was filling in the wrong one — so the identity service saw an empty code, rejected it, and emailed a new one, over and over. It now fills whichever code box the page actually shows (and ticks "remember this browser" when offered, so the saved session lasts longer). (Opt-in beta channel only.)

## [2.14.9] - 2026-06-17

### Fixed

- **volkswagen.de website login (beta): a restart now actually resumes the session instead of looping / asking for a new email code.** This was the real root cause behind the redirect loop on resume. The single-sign-on cookie that keeps you logged in lives only on the identity host and has no domain attached, so the old code quietly dropped it when saving and never restored it — which meant a restart had no valid session to resume and bounced back to the login page. The login cookies (the SSO one included) are now captured and restored across both hosts, so a restart silently reuses your session. A stale session reported as `412`/`428` (not just `401`/`403`) now also correctly triggers a clean re-login. (Opt-in beta channel only.)

## [2.14.8] - 2026-06-17

### Fixed

- **EU Data Act portal: a slow/unreachable portal no longer errors the whole poll — it just means "no data this poll".** When the portal was sluggish, the request could time out at the network layer (before any response), and that timeout slipped past the retry logic and surfaced as an error (the spike of auto-reported `TimeoutError`s on June 16). Now a timeout or dropped connection is retried with the same short backoff as a transient server error, and if it keeps failing the poll quietly skips and tries again next cycle — instead of erroring or, worse, forcing a pointless re-login. Affects both the data-listing and the dataset-download steps.

## [2.14.7] - 2026-06-15

### Added

- **volkswagen.de website login (beta): redirect-chain debug logging, so a stuck login can finally be diagnosed.** When the website login bounces in a loop, the error message is redacted (it can carry tokens), which made the root cause invisible from a normal log. This adds a `DEBUG`-level, hostname-only trace of the redirect chain (and the resume-probe result) — e.g. `volkswagen.de → identity.vwgroup.io → volkswagen.de → …`. Only hostnames are logged; paths and query strings (where the OAuth `state`/tokens live) are never written. Turn on debug logging for `custom_components.vag_connect` to capture it. No functional change — purely diagnostics for the beta channel.

## [2.14.6] - 2026-06-15

### Fixed

- **volkswagen.de website login (beta) now actually resumes a saved session instead of re-logging-in every time.** v2.14.5 stopped the redirect-loop crash, but it still kicked you back to a fresh email-OTP whenever the resume wobbled. Now, when the integration comes back up it does a quick, redirect-free check against the data endpoint with your saved cookies: if the session is still good it's adopted straight away — no login dance, no OTP — and only a genuinely expired session falls back to a fresh login. As a belt-and-suspenders extra, the credential step also can't get stuck in a redirect loop anymore. (Opt-in beta channel only; no change for any other brand or mode.)

## [2.14.5] - 2026-06-15

### Fixed

- **volkswagen.de website login (beta) no longer crashes with a redirect loop when resuming a saved session.** When the integration came back up and reused the saved login cookies, the website login could bounce in a redirect loop (`TooManyRedirects`) and surface as a bogus "invalid credentials". It now caps the redirects and handles the two real cases cleanly: an already-logged-in session is recognised straight away (no re-login, no OTP), and a stale-cookie loop is reported as a normal "please re-authenticate" instead of a crash. (Opt-in beta channel only.)

## [2.14.4] - 2026-06-15

### Fixed

- **The "Email 2FA required" repair notice stops throwing translation errors for good.** v2.14.3 supplied the missing `{brand}` value, but a notice already sitting in the repairs list from an older version had no value and kept spamming `MISSING_VALUE` in the logs. The notice title no longer depends on a placeholder at all (all 8 languages), so old and new notices both render cleanly, and the repair description now also gets its `{username}` value supplied. Purely a cosmetics/log-noise fix.

## [2.14.3] - 2026-06-14

### Fixed

- **volkswagen.de website login (beta): you only enter the email code once now, not on every restart.** The beta channel logged you in (code and all) when you set it up, but then threw all that away and started fresh every time Home Assistant restarted — which meant it asked for a new email code on every single restart, and if you weren't there to type it in, the integration just got stuck. It now remembers the login session from setup and reuses it, so a restart picks up where it left off instead of pestering you for another code. If the saved session has genuinely gone stale, it falls back to asking you to sign in again, same as before. The session keeps itself fresh in the background after each successful login. (Opt-in beta channel only; still read-only.)
- **Repair notifications show the brand name properly instead of a literal `{brand}`.** A couple of the "please sign in again" repair prompts (including the email-code one) had a `{brand}` placeholder that wasn't being filled in, so the title could read awkwardly. It now drops in the actual brand (or a sensible fallback) so the message reads cleanly.

## [2.14.2] - 2026-06-14

### Fixed

- **volkswagen.de website login (beta): the email code now submits correctly.** The OTP step was posting just the code + state, but the VW identity email-challenge page is a form with hidden fields (`_csrf` / `relayState` / …) that have to come along — without them the code didn't go through cleanly. It now parses the challenge form exactly like the password step does and submits the code inside the real form, so email-OTP logins complete. (Opt-in beta channel only.)

## [2.14.1] - 2026-06-14

### Fixed

- **System Health no longer falsely reports the VW/Audi backend as unreachable.** The connectivity check pinged an old discovery URL (`/login/v1/idk/openid-configuration`) that VW has started answering with a `403` before you even log in — so Home Assistant's System Health card showed the CARIAD backend as "failed" even when everything was working. It now pings the current endpoint (the same one the login already uses), which answers normally.

## [2.14.0] - 2026-06-14

### Added

- **New opt-in beta way to connect a Volkswagen: the volkswagen.de website (read-only).** There's now a third sign-in option when you add a Volkswagen — "Volkswagen.de website (beta)" — that logs in the same way the volkswagen.de "myVolkswagen" web area does and reads your car through it. The point: that website uses its own server-side login, so it goes around the app-attestation wall that's been killing the normal token logins for VW. You sign in with your Volkswagen ID email + password (and an emailed code if your account asks for one), and you get charge level, range, charging state and power, charge target, plus odometer and service-due info. It's **read-only** — no lock/climate/charge commands — and **opt-in**: you have to pick it on purpose. Nothing changes for anyone who doesn't, every existing setup (app login, browser login, EU Data Act portal) behaves exactly as before. It's a beta and hasn't been verified end-to-end against a live VW account yet, so treat it as experimental.

## [2.13.1] - 2026-06-14

### Fixed

- **Fewer dropped polls when the EU Data Act portal is having a moment.** The portal throws transient server errors (500/502/503/504) that come and go within seconds — and until now a single blip meant skipping the whole poll and waiting 15 minutes for the next one. The integration now backs off briefly and retries (a couple of times, a few seconds apart) before giving up as "no data this poll", so a short hiccup no longer costs you a full cycle of data. The "you haven't enabled the data request yet" case (404) still returns instantly with no added delay, and a real auth failure still re-authenticates as before.

## [2.13.0] - 2026-06-13

The EU Data Act portal becomes the **universal read-only safety net**: as VW keeps closing native API access brand by brand (VW EU's token logins are gone, CUPRA/SEAT's online services are now behind a device-attestation wall), each affected brand now degrades gracefully to the read-only portal instead of going dark.

### Fixed

- **CUPRA, SEAT and Škoda now route their data reads through the EU Data Act portal when the portal fallback is active** — not just their login. Until now, when a brand's native backend went dark (e.g. CUPRA/SEAT's online services getting blocked by VW), the login correctly fell back to the read-only portal, but the very next data poll still hit the dead native endpoint — so you'd get a successful login and then no data. These brands now follow the same portal-routing path VW EU already used, both for the vehicle list and the status read. It's the EU Data Act portal becoming the universal read-only safety net: as VW keeps closing native access brand by brand, each one degrades gracefully to the portal instead of going dark. Non-breaking — the native path is completely unchanged whenever the portal fallback isn't engaged.
- **CUPRA/SEAT now actually reach that fallback.** There was a catch: the portal fallback only ever armed when the *login* failed — but for CUPRA/SEAT the login still succeeds and it's only the data call that gets blocked (the 403 device-attestation wall). So the fallback never fired and the previous fix couldn't help. Now, when the native garage call comes back 403 despite a valid login, the integration arms the read-only EU Data Act portal on the spot and serves the vehicle list from there. This is what makes the portal safety net real for the brands that are blocked *today*.
- **Quieter logs in EU Data Act portal mode.** When a car is running on the read-only portal, the integration was still trying the manufacturer-backend "capabilities" call on every setup — which can't work there (the portal session isn't a real backend token) and just logged a `400` every time. It now skips that call in portal mode. Cars on a normal (non-portal) connection are unaffected, including when you've turned on read-only mode yourself.

## [2.12.6] - 2026-06-13

An honesty fix for the CUPRA/SEAT repair notice.

### Changed

- **The CUPRA/SEAT "OLA 403" repair notice now tells the truth.** It used to suggest the app-identifying headers might be outdated and told you to check for an update or try an app-version override — but those 403s are a VW server-side access revocation for SEAT/CUPRA, not anything a header bump or a reconfigure can fix. The notice now says that plainly (in all eight languages), drops the dead-end advice, and notes the integration falls back to the read-only EU Data Act portal where it can (#432, #444, #456, #392).

## [2.12.5] - 2026-06-13

A data-quality patch for the EU Data Act portal, plus a scout-noise fix for Audi.

### Fixed

- **Jumping SoC / odometer on the EU Data Act portal.** The portal ships an unordered event-log, and we were keeping the first value we happened to see for each field (often the oldest), so battery level and mileage bounced around. We now keep the newest value per field by timestamp — the same data-quality problem the whole portal ecosystem hit. Empty / no-content / corrupt portal ZIPs are also handled as "no data this poll" instead of being mistaken for a login failure (which used to trigger a pointless re-login).
- **Audi scout noise on deeper charging timer/profile fields** (#446, #448). The selectivestatus backend started nesting `chargingTimers` / `chargingProfiles` one level deeper (4 segments, e.g. `…Status.value.timers`); registered the deeper wildcards so the Vehicle Data Scout stops re-flagging fields we already read.

### Changed

- Housekeeping: removed an orphaned repair-notice translation key (`data_act_wake_needed`) that was superseded by the "no vehicle data" notice and is never shown. No user-facing change.

## [2.12.4] - 2026-06-09

A resilience release for the ongoing VW-side backend outage: the integration now rides out transient server errors quietly instead of treating them like a broken login.

### Fixed

- **VW portal outage no longer spams errors or triggers needless re-logins** (#428, #429, #430, #431). While VW's EU Data Act portal is in its ongoing outage, the data endpoints keep returning HTTP 500. We were treating that 500 as an authentication failure — so it logged an error every poll and kicked off pointless re-login attempts. A 500 is the portal having a bad moment, not a dead session, so it's now handled as "no data this poll" (the existing "no vehicle data" notice already explains the outage). A genuine 401/403 still re-authenticates exactly as before.
- **Token-refresh hiccups no longer look like a wrong password** (#438). When the VW token server returns a transient gateway error (HTTP 502/503/504) on an otherwise-valid login — common while their backend is flaky — the integration was treating it as an authentication failure: it popped up a "please reconfigure" reauth prompt and filed error reports for what is purely a VW-side blip. Now a 5xx on the token endpoint is treated as "VW backend temporarily unavailable": your entities keep their last value, the integration retries on the next poll, and nothing prompts you to re-enter credentials. A genuinely rejected refresh token (HTTP 400) still triggers a real re-login. Applies to every brand (Audi, VW, Škoda, SEAT, CUPRA).
- **Quieter during outages** (#435, #436, #437, #438, #439). Transient VW-backend 5xx errors — the kind above — no longer get escalated to the in-app Error Reporter. They're a server-side outage symptom, not an actionable bug, and were generating a stream of noise reports. Your entities stay available through the normal failure-tolerance window in the meantime.

## [2.12.3] - 2026-06-08

### Changed

- **Everything's translated now — all eight languages, end to end.** We went through every string the integration shows and filled in the gaps: the newer entity names (battery temperature, climate zones, navigation charge target, parking-map links, plug LED colour, the "command pending" sensors and friends), the little help texts under the login and options fields, the "open the brand app" service, and the repair notices (wake the car, portal session expired, optional browser package missing, OLA headers outdated). Until now anything we hadn't translated quietly fell back to English, so non-English users saw a mix. EN, DE, NL, SV, FR, ES, PL and CS are now complete — with everyday wording for the car terms instead of literal tech-speak.

## [2.12.2] - 2026-06-08

### Added

- **"No vehicle data" hint when the portal is empty.** When the VW EU Data Act portal logs in but returns no data, the integration now raises a clear Home Assistant repair notice instead of staying silent. It explains the likely causes — most often the VW-side portal outage that's been running since late May 2026 (which hits every tool, not just us), or a data request that isn't set up yet — and tells you the quickest check: open the VW data portal in a browser and see whether *you* can see your car's data there. If it's empty there too, it's on VW's side. The notice clears by itself once data starts flowing. Fully translated across all eight bundled languages (EN, DE, NL, SV, FR, ES, PL, CS).

Quick follow-up to the v2.12.0 VW EU portal beta, from the first round of live testing.

### Fixed

- **VW EU portal broke after a Home Assistant restart** (#393). The portal saves a cookie-session placeholder token, and on restart the integration reused it and skipped the login — so the portal session was never rebuilt and the next call hit the old (dead) endpoint with a useless token, ending in "No vehicles found". Now a fresh portal login runs on every restart, so the session is always re-established.
- **"No data request" no longer spams errors** (#393, #424). Until you manually create a continuous data request for your car in the VW data portal, the data endpoint returns 404/500 — that's expected, not a failure. The integration now treats it as "no data yet" (the car still appears, data fills in once the request goes live) instead of logging an error every poll.
- **Scout noise on Audi charging timers/profiles** (#423). Registered the deeper `chargingTimers` / `chargingProfiles` sub-paths and the DC auto-unlock setting the Scout kept flagging.

## [2.12.0] - 2026-06-07

The big one for VW EU. We confirmed live that VW has closed every token-based login route for passenger cars — the hybrid trick another project used now gets a hard 403 from Auth0, the code-flow needs a client secret we can't have, and device-login isn't enabled for the VW client. The only door VW has to keep open under the EU Data Act is the read-only data portal, so that's the path we built.

### Added

- **VW EU Data Act portal connector (read-only, BETA).** A brand-new cookie-based login + data path for VW passenger cars, using the EU Data Act portal. It logs in, pulls the vehicle's data export, and surfaces the high-value bits (charge level, odometer, range, charging state, doors, window heating, temperatures). Trade-offs: it's read-only (no remote climate/charge commands), updates on roughly a 15-minute cadence, and you have to switch on a one-time "continuous data request" on the VW portal first. Kicks in automatically once the old token logins fail. Marked beta — the live login is being validated on #388/#393 before we lean on it.
- **Brand-aware portal config.** The portal connector is wired as a fallback in every brand's login chain, so it now picks the right OAuth client + brand selector per brand (VW, CUPRA, SEAT verified; others fall back gracefully) instead of always using VW's. Foundation for offering the read-only portal path to more brands later.
- **Skoda trip cost.** Total / fuel / electricity / CNG cost for the trip overview, with the currency, when Skoda ships it.

### Fixed

- **Cars stuck showing "online" forever.** Some vehicles report a capture timestamp years in the future (a known broken-clock quirk on certain control units), which pinned the connection state to "online" with a nonsense last-seen time. We now ignore timestamps beyond a 5-minute window. Applies to every brand.
- **Scout noise.** Registered the climatisation sub-blocks (CUPRA/SEAT) and the battery-support / charging-profiles / charging-timers blocks (VW/Audi) the Data Scout kept flagging, so it stops re-reporting fields we already read. Closes the scout reports behind #411, #414, #415, #416, #417, #419.

### Legal

- Added `LEGAL.md` documenting the statutory basis (EU Software Directive Art. 6, §69e UrhG, Art. 21 URG, DMCA §1201(f), EU Data Act Arts. 4–6) and attribution for the open-source projects the portal connector's mechanics were adapted from.

## [2.11.4] - 2026-06-05

Bundle release covering the v2.11.3 fallout. After v2.11.3 unblocked the Auth0 state-token wall, the next bottleneck surfaced: the VW EU signin-service flow is a TWO-step submit (POST email first to get a fresh hmac for the password page, then POST password to a different URL). Plus a handful of upstream-sync fixes for Skoda + small parser additions from the latest scout reports.

### Fixed

- **VW EU signin-service 2-step SPA login** (#388 swebachus, #393 SniperWCW). v2.11.3 extracted hmac + postAction from the templateModel JSON literal correctly but then POSTed the password straight to the identifier URL — got HTTP 405 every time, because the email-page hmac is bound to the identifier session only. v2.11.4 does the full upstream-canonical flow: POST email + identifier-hmac → identifier URL, regex-extract the FRESH hmac out of the response (the password page), swap "identifier" → "authenticate" in the URL path, POST email + password + fresh-hmac + relayState → authenticate URL. Pattern lifted from the audi_services.py implementation.
- **Skoda charging-statistics timezone header**. The upstream charging-statistics replacement endpoint (which we adopted preemptively in v2.11.0) tightened its server-side parser to require `X-Device-Timezone: GMT` instead of accepting any Olson zone. Switched from `Europe/Berlin` to `GMT` so the endpoint stops 400'ing on accounts where the server got picky.
- **SEAT / CUPRA climatisation field-layout for newer firmware** (#411 heidle78 scout). The scout caught two new top-level keys in the climatisation response: `climatisationStatus` (state / remaining-time / outside-temp moved here) and `windowHeatingStatus` (front/rear states moved here). Parser now checks the new sub-blocks first and falls back to the legacy `status`-wrapped layout for older firmwares.
- **Auto-reporter empty-body issues** (#409, #412 — empty bodies). Some browsers silently drop the `body` query param when the final encoded URL crosses 8KB. URL-encoded markdown inflates ~1.5x, so the 6500-char budget we shipped overflowed in some cases. Dropped to 4000 raw → ~6000 encoded so even chatty error reports survive the round-trip.

## [2.11.3] - 2026-06-04

Bundle release. Five fixes spanning SEAT / CUPRA endpoint corrections, VW EU signin-service SPA auth, and Audi token refresh defense. Built from a fresh round of upstream-lib source-walks (pycupra const.py + connection.py, audi_connect_ha audi_services.py, volkswagencarnet vw_connection.py) plus the live diags from #392 (heidle78) and #388 (swebachus).

### Fixed

- **SEAT / CUPRA climatisation read endpoint** (#392 heidle78 v2.11.1 trace). We were hitting `/v2/vehicles/{vin}/climatisation` for the read which 404s — that path is the command prefix only (the start / stop / settings / window-heating POSTs hang off it). The actual read endpoint is `/v1/vehicles/{vin}/climatisation/status`. Restores `climatisation_state`, `target_temperature`, `outside_temp`, `aux_heating_*` etc. on every CUPRA / SEAT that's been silently null for these fields.
- **SEAT / CUPRA door-lock parser presence check** (same trace). The "sub-job absent" failure in `parser_stats.door_lock` was a stats-misclassification — the parser actually populates `doors_locked` + `doors_individual` correctly from `/v2/vehicles/{vin}/status`, but the presence check only looked at `mycar.access.accessStatus.value` which is empty on newer firmware. Check now accepts either source so cars don't show false-positive parser failures in the diag.
- **SEAT / CUPRA `permission_*` + `capabilities_count` plumbing**. The `/v1/vehicles/{vin}/permissions` URL we polled for the `permission_is_owner` / `permission_can_command` entities consistently 404'd in production — the canonical endpoint is `/v1/users/{userId}/vehicles/{vin}/relation-status`. Also added a `capabilities_count` diagnostic sensor for SEAT / CUPRA (already exists for VW EU and VW NA), cached for 24h so we don't hammer the capabilities endpoint on every scan_interval tick.
- **VW EU SPA login on the signin-service flow** (#388 swebachus, Volkswagen ID.7 Sweden). The Auth0 SPA branch we shipped in v2.10.x was Auth0-specific — it hunted for `state=hKFo...` tokens which only exist on the universal-login path, then POSTed to `/u/login`. Users routed through the legacy `signin-service/v1/<client>` flow with a SPA-rendered password page (zero hidden inputs) hit a hard "no Auth0 state token found" error. Now: when the page embeds the `templateModel: { hmac, postAction, relayState, ... }` JSON literal (the SPA shell does), we pull those three fields and POST to the signin-service authenticate URL with the proper body shape. Same approach pycupra and audi_connect_ha use. Also covers a softer fallback (relayState alone via URL / JSON / escaped-JSON) for SPA shells that don't ship a full templateModel.
- **Audi / VW refresh-token defense** (audi_connect_ha upstream PR #749 pattern). When the IDK token endpoint returns a fresh `access_token` but omits the `refresh_token`, we used to hard-fail with `AuthenticationError` and force a full re-login. Some IDK refresh responses do exactly that — the existing refresh-token stays valid for the rotation lifetime. Now: we keep the previously-known refresh-token when the response omits it, instead of throwing the user back to the config flow.

## [2.11.2] - 2026-06-04

### Fixed

- **SEAT / CUPRA trip stats + aux-heating status** (#392 heidle78 v2.11.0/v2.11.1 trace). The trip endpoints we'd used since v1.x (`/trips/shortTerm`, `/trips/longTerm`, `/trips/lastrefuel`) and the standalone aux-heating status endpoint (`/api/auxiliary-heating/v1/{vin}/status`) all 404 on Formentor PHEV firmware — they're not the canonical OLA paths. Replaced with the actual ones the app uses: a single `driving-data/SHORT` for last-trip + lifetime totals + `recent_trips` list, `driving-data/CYCLIC` for per-tank / per-charge refuel events, and the aux-heating sub-block that already comes back inside the existing `/v2/vehicles/{vin}/climatisation` payload (no extra request). Should unblock `last_trip_*`, `lifetime_*`, `refuel_trip_*`, `recent_trips`, `aux_heating_*` on Formentor PHEV and likely every other CUPRA / SEAT that's been silently null since v1.0.

## [2.11.1] - 2026-06-04

### Fixed

- **SEAT / CUPRA `max_charge_current` enum → amperage** (#392 heidle78 v2.11.0 trace regression). v2.11.0's pycupra-verified `settings.maxChargeCurrentAc` reader now correctly hits the canonical key on Formentor PHEV MJ22-23 firmware, but that firmware returns the enum string `"maximum"` / `"reduced"` instead of an integer amperage. The HA `sensor.cupra_max_ladestrom` is registered as `device_class=current, unit=A, numeric` and blew up with `ValueError: could not convert string to float: 'maximum'`. Now: prefer the explicit integer field when present, otherwise map the enum to the canonical amperage values verified against zackcornelius's VW NA APK decompile (`maximum`/`max` → 32 A, `reduced`/`min`/`minimum` → 10 A). Leaves the field `None` when neither path produces a usable value.

## [2.11.0] - 2026-06-04

Cross-brand parser audit against upstream lib source code. Five parallel deep diffs (pycupra, myskoda, volkswagencarnet, audi_connect_ha + CarConnectivity-VW, CarConnectivity-connector-volkswagen-na) surfaced field-name and parsing bugs that have been silently returning null on every car for some time. Bundled into one PR rather than the per-brand hotfix chain pattern.

### Fixed (cross-brand)

- **Skoda driving range fields** (myskoda source-verified). `electricRange.distanceInKm` / `combustionRange.distanceInKm` / `secondaryEngineRange.distanceInKm` are scout-derived paths that myskoda's DrivingRange model does NOT include. Canonical keys are `primaryEngineRange.remainingRangeInKm` + `secondaryEngineRange.remainingRangeInKm` plus an `engineType` enum to decide which is electric vs combustion. Old paths kept as fallback for any firmware that genuinely ships them. `adBlueRange` is a flat int upstream, not a dict.
- **Skoda doors_open / windows_open** were reading from `access.doorsOpenedCount` / `windowsOpenedCount` which do not exist on Skoda mysmob vehicle-status (no `access` subobject). For years these sensors silently reported false. Now reads `overall.doors == "OPEN"` / `overall.windows == "OPEN"` per myskoda Status.Overall model.
- **Skoda driving_score** was reading non-existent top-level `score` / `drivingScoreClass`. Upstream DrivingScore model is per-period (`daily/weekly/monthly/quarterlyScore.main`). Now prefers `weeklyScore.main` then falls back through the other periods.
- **SEAT / CUPRA charging path-prefix** (pycupra source-verified). The canonical path is `charging.status.charging.*` and `charging.status.battery.chargeEnergyInKwh` on Born MY24+. Pre-v2.11.0 we only tried `charging.charging.*` (direct) so `charging_power_kw`, `charging_rate_kmh`, `charging_type`, `total_charged_energy_kwh` were silently null on newer firmwares. Now adds the `.status.` segment as the canonical primary, keeps direct as fallback.
- **SEAT / CUPRA `battery_care_target_soc_pct`** field name. pycupra reads `targetSocPercentage` (no underscores); we previously tried `targetSOC_pct` and other variants only.
- **VW EU / Audi `plug_led_color` double-write bug**. A second unconditional assignment at the end of the charging block overwrote a valid PPE-firmware value (`plugLedColor` on access or chargingStatus) with `None` from `plugStatus.value.ledColor`. Now consolidated into a single defensive chain ordered upstream-canonical-first.
- **VW EU / Audi `battery_care` parent block order**. Volkswagencarnet's `vw_const` puts the canonical path under `batteryChargingCare.chargingCareSettings.*`; we previously tried `charging.chargingCareSettings.*` FIRST and the dedicated batteryChargingCare block was a fallback. Flipped so the canonical wins.

### Added

- **SEAT / CUPRA min_soc** read at `settings.minBatteryStateOfChargeInPercent` on `/v1/charging/info` (pycupra `get_min_charge_level`). Sensor previously stayed null.
- **SEAT / CUPRA climate_remaining_time_min + climate_ready_at** wired. The OLA climate payload already shipped `status.remainingClimatisationTime_min`; we just never read it. Derived `climate_ready_at` ISO timestamp lets HA show a "ready by" clock.
- **VW EU missing selectivestatus jobs**: `activeVentilation`, `batterySupport`, `chargingProfiles`, `chargingTimers`. Without these requested, parsers that read from those blocks (active ventilation state at v2.10.0 Group A, next-charging-timer at #173) returned null on any car whose data didn't happen to ship inside a sibling block.
- **VW EU `measurements.rangeStatus.value.electricRange`** added as a third fallback in the electric range chain. Some pure-EV ID.x firmware ships only this leaf.
- **VW EU / Audi aux-heating legacy fallback** at `climatisation.auxiliaryHeatingStatus.value.*`. Older Audi A4 B9 / MIB3 cars ship aux-heating state under the climatisation parent, NOT under top-level auxiliaryHeating. audi_connect_ha references this legacy path; we missed it pre-v2.11.0.

### Added (cont. - new endpoint integrations)

- **Skoda dedicated warning-lights health endpoint** (`/api/v1/vehicle-health-report/warning-lights/{vin}`, myskoda Health model). Canonical source for dashboard warning lamps with per-category breakdown (engine / brakes / tyre / oil / fluid) and human-readable defect text. Previously the warning_* fields relied on data piggybacking inside other responses.
- **Skoda trip statistics endpoint** (`/api/v1/trip-statistics/{vin}`, myskoda TripStatistics model). Populates `lifetime_distance_km`, `lifetime_avg_fuel_consumption_l_100km`, `lifetime_avg_electric_consumption_kwh_100km` from the overview block plus `last_trip_*` fields from `detailedStatistics[0]`.
- **SEAT / CUPRA aux-heating status read** (`/api/auxiliary-heating/v1/{vin}/status`). We have used this host for start/stop commands since v1.x; the status read now fills in `auxiliary_heating_status`, `aux_heating_active`, `auxiliary_heating_remaining_min`, and `heater_source` which were null on every car before.
- **SEAT / CUPRA trip statistics** via three OLA endpoints (`/v1/vehicles/{vin}/trips/{shortTerm,longTerm,lastrefuel}`, pycupra references). Populates `last_trip_*`, `lifetime_*`, and `refuel_trip_*` with defensive field-name variants for both legacy MBB-suffixed and CARIAD-suffixed shapes.

### Fixed (VW NA - in-place corrections, full rewrite still scheduled)

- **VW NA SPIN flow algorithm + token field** (zackcornelius source-verified). The canonical hash is `SHA-512("{challenge}.{spin}")` (challenge first, period, then spin); pre-v2.11.0 used `SHA-1(spin + nonce)` which fails on modern Cox firmware. SHA-512 is now the primary attempt; the legacy SHA-1 stays as fallback on 4xx so users on older firmware are not regressed. The session token field is `carnetVehicleToken` (NOT `sessionToken`); both are tried.
- **VW NA Canada client_id** at `69eb3c39-d2be-4006-8197-37cc4971e8fe_MYVW_ANDROID`. CA accounts that authenticated with the shared US client_id were rejected on newer firmware.
- **VW NA OAuth scope** now `openid profile cars vin` (was bare `openid`). The NA IDP returns reduced consent + missing claims when only `openid` is requested.
- **VW NA field-name corrections**: `data.location` (not `vehicleLocation`), `data.readiness.readinessStatus.value.connectionState.isOnline` (boolean) as primary online signal, `chargingStatus.currentChargeState` (not `chargingState`), `chargingStatus.chargePower` (not `chargePower_kW`), `chargeSettings.targetSOCPercentage` (not `chargingSettings.targetSOC_pct`), `chargingStatus.currentSOCPct` for battery_soc (was on wrong endpoint), `climateStatusReport.climateStatusInd` (not `climateState`), `data.timestamp` (epoch-ms) as canonical last-seen. `cruiseRangeUnits == "MI"` now converts to km (was silently treated as km, miles users had ~38% underreported range).

### Added (cont. - post-audit upstream sync)

- **Skoda charging statistics endpoint** (myskoda PR #586 source-verified). POSTs to `prod.emea.mobile.charging.cariad.digital/charging_statistics` with a VIN-filtered date range and Skoda-brand headers (`X-Brand: skoda`, `X-Device-Timezone: Europe/Berlin`, `X-Api-Version: 1`). The legacy `/v1/charging/{vin}/history` endpoint started returning HTTP 500 for many users after the Skoda app update on 2026-05-15 (upstream issue #585). The replacement uses `monthSections[].entries[].{primaryValue.value, secondaryValue.value, sessionDetails.startedAt, sessionDetails.currentType}` to populate `total_charged_energy_kwh` (sum across all entries), `last_charging_session_kwh`, `last_charging_session_duration_min`, `last_charging_session_start`, `last_charging_session_current_type`, and a compact `recent_charging_sessions` list. Adopted preemptively because PR #586 has not yet landed upstream but the broken state affects every Skoda user on current firmware.
- **VW EU / Audi `chargeMode` selectivestatus sub-job** (volkswagencarnet PR #328 source-verified, merged 2026-06-01). CARIAD-BFF now exposes a dedicated `charging.chargeMode.value` block carrying `preferredChargeMode` + `availableChargeModes`. Independent of the auth crisis - this is a real additive backend change. Now populates `charging_preferred_mode` and `available_charge_modes` for VW EU / Audi vehicles (CUPRA / SEAT have already shipped these from OLA endpoints since v2.10.0).

### Verified aligned with upstream (no action required)

- **SEAT / CUPRA `app-market: android` header** already set in `_ola_headers.py` for both brands since v2.1.x. Aligned with pycupra v0.2.30 403 fix.
- **`tokentype: IDK_TECHNICAL` header** is not set anywhere in our codebase. Aligned with volkswagencarnet v5.4.7 removal.
- **VW NA OAuth scope** confirmed `openid profile cars vin` against zackcornelius HEAD source — both repo source and live API behavior verified.
- **VW EU auth situation**: refresh tokens dead, Play Integrity X-Assertion required, Python cannot bypass. Confirmed wide community consensus (volkswagencarnet pinned #989, o11e's APK Frida writeup, evcc-io). Our Data Act portal fallback is the realistic ceiling.
- **Skoda mysmob charging-history /v1/charging/{vin}/history**: upstream broken with HTTP 500 since 2026-05-15 (myskoda issue #585). We adopt the in-progress fix from myskoda PR #586 (rsa-wusel APK reverse-engineered) preemptively because the upstream-broken state hits every Skoda user on 2026-05-15+ firmware.

### Still pending (separate PRs scheduled)

- **VW NA write-side full rewrite** (lock/unlock HTTP verbs, set-target-SOC method + body shape, climate-settings PUT shape, departure-timer shape). zackcornelius HEAD now has the APK-decompiled reference: `GET /ss/v1/user/{userId}/challenge` → `POST /ss/v1/user/{userId}/vehicle/{uuid}/session` body `{idToken, spinHash, tsp:"WCT"}` → carnetVehicleToken as Bearer (not X-Spin-Session). Lock = PUT body `{"lock":bool}`. Verbatim port scheduled v2.11.1.
- **VW NA subscription/privileges** parser shape (zackcornelius reads `data.services[*].operations[*].capabilityStatus`, not a top-level `subscription` block) - v2.11.1.
- **Audi refresh_token KeyError defense** (audi_connect_ha PR #749 source-verified) - backend now intermittently omits refresh_token. Our refresh path needs same `if "refresh_token" in resp` guard - v2.11.1.
- **Audi IDK discovery URL preference** (audi_connect_ha PR #738) - verify `_audi_market_config.py` reads `idkLoginServiceConfigurationURLProduction` with fallback to `/auth/v1/idk/oidc/openid-configuration` - v2.11.1.
- **Skoda TripStatistics OverallCost/FuelCost fields** (myskoda v2.11.1 additive). Needs new VehicleData attributes + sensor.py registrations + 9-lang translations + currency-aware unit handling - v2.11.1.

## [2.10.12] - 2026-06-04

### Fixed

- **SEAT / CUPRA field-name corrections cross-referenced against pycupra source** (#392 heidle78 v2.10.10 follow-up - still-null trace). v2.10.10's static-info fix guessed top-level field names on the garage response that don't exist; the actual data lives in nested sub-blocks. Deep-diff against pycupra (the established Python lib for OLA backend) surfaced four concrete bugs:

  - **model**: now reads `specifications.factoryModel.vehicleModel` (was guessing top-level `model`/`modelName`), optionally concatenated with `specifications.carBody` for the full display name.
  - **model_year**: now reads `specifications.factoryModel.modYear` (was guessing `modelYear` - note the missing `el`).
  - **manufacturer**: now reads `specifications.factoryModel.vehicleBrand` (was guessing top-level `brand`).
  - **odometer_km**: added `mileageKm` as the FIRST field-name variant on `/v1/mileage` (pycupra's canonical key, was missing from our chain so offline-state Formentor PHEVs came out with odometer null).
  - **target_soc** + **max_charge_current** + **auto_unlock_charge**: now read from the `settings` sub-dict on `/v1/charging/info` (pycupra: `settings.targetSoc` / `settings.maxChargeCurrentAcInAmperes` / `settings.maxChargeCurrentAc` / `settings.autoUnlockPlugWhenCharged`). Pre-v2.10.12 read top-level only and silently missed the nested data on most CUPRA/SEAT firmwares.

## [2.10.11] - 2026-06-04

### Fixed

- **Data Act portal SPA: 3 new state-extraction patterns + 2-source forensic dump** (#388 swebachus v2.10.10 trace). swebachus's v2.10.10 warning log showed the portal returns a pure-SPA shell as the password page: `password_html.contains '<input'=False, contains 'state'=True, contains '__STORE__'=False`. Three new extraction patterns target the actual shapes this means: (a) Auth0 native state signature `hKFo...` regex (state tokens always start with that msgpack 2-key map marker so they are catchable even when minified into a bare string literal); (b) escaped JSON `\"state\":\"...\"` for double-encoded inline payloads; (c) URL-encoded state inside the HTML body for `window.location = "...state=X..."` patterns. The warning log now also covers `landing_html` (not just `password_html`), prints the raw URL strings, and dumps the 110-char context window around any `"state"` substring so the next failing trace pinpoints exactly where the token lives or proves the page is purely JS-rendered post-bundle.

## [2.10.10] - 2026-06-04

### Fixed

- **SEAT / CUPRA static vehicle info from garage** (#392 heidle78 v2.10.8 follow-up diag). Pre-v2.10.10 the parser never read `model`, `model_year`, `manufacturer`, or `firmware_version` from the OLA garage response, so every SEAT / CUPRA vehicle showed "Unbekannt" / `None` for those device-card fields even when the data was clearly present in the API. Now extracts them in `get_vehicles` with defensive multi-variant lookup (`model`/`modelName`, `modelYear`/`year`, `brand`/`manufacturer`/`brandName`, `firmwareVersion`/`softwareVersion`, plus a `specifications` / `vehicleSpecification` sub-block) and caches per-VIN like the existing licensePlate + nickname pattern.

## [2.10.9] - 2026-06-04

### Fixed

- **Data Act portal SPA: attribute-order-agnostic state extraction + forensic logs** (#388 Arno-MA-73 v2.10.8 trace). v2.10.7's HTML hidden-input regex required `name` to appear before `value` in the markup; some Auth0 SPA bundles ship the attributes in the opposite order and the v2.10.7 regex silently missed those. Now walks every `<input ...>` tag, captures `name` and `value` as two independent regex matches the way `idk.py:_parse_csrf_robust` already does for the main BFF flow. Adds `data-state="..."` attribute as a third extraction path. Plus full DEBUG forensic logs at every step in the SPA branch (landing/identifier/password URLs, HTML lengths, parser field key sets, state extraction source and first 12 chars on success, first-200-char dump of password HTML when nothing works) so the next failing trace surfaces what shape the portal actually returns.

## [2.10.8] - 2026-06-03

### Fixed

- **CUPRA / SEAT PHEV classification** (#392 heidle78 Formentor diag). Some OLA firmware versions ship `engines.primary.fuelType="gasoline"` but DO NOT populate a combustion range in the `ranges` block on the same response. Pre-v2.10.8 the integration derived `has_combustion` purely from the ranges block, so a Formentor PHEV came out classified as `is_hybrid=False` and `has_combustion=False`, suppressing the fuel-tank / combustion-range sensors downstream. Now also treats any non-electric `primary_engine_type` (gasoline / diesel / cng) as combustion so the PHEV flag flips correctly regardless of which response branch carries the range data on a given poll.

## [2.10.7] - 2026-06-03

### Fixed

- **Data Act portal SPA: state token extraction from HTML** (#388 Arno-MA-73 post-restart trace). v2.10.6 fixed the 405 but then failed with "no Auth0 state parameter in URL" because aiohttp's redirect-following strips the state from the final response URL on some SPA flows. Now mirrors `idk.py`'s extraction order: HTML hidden input first (most reliable, Auth0 always embeds `<input type="hidden" name="state" value="...">` in the page body even on SPA), regex over hidden inputs as fallback, JSON-embed pattern as third option, then the URL query strings as last resort. Both `password_html` (most recent) and `landing_html` (original GET) get checked.

## [2.10.6] - 2026-06-03

### Fixed

- **Data Act portal SPA password POST 405** (#388 xeonixo + Arno-MA-73). v2.10.3 POSTed the SPA password to the parsed identifier-form action URL, which returned HTTP 405 Method Not Allowed for several users. Auth0 Universal Login actually routes the SPA password submission through the SAME `/u/login?state=<x>` URL as the identifier step; differentiation happens via the body's `action` field. Now mirrors `idk.py`'s SPA fallback exactly: form-encoded POST first, JSON-content-type fallback when that lands on 4xx or back on the IDP host, follow the redirect chain. State is pulled from the password-page URL with a fallback to the original landing URL.

## [2.10.5] - 2026-06-03

EU Data Act portal: no more manual click-through. When the integration is in read-only portal mode and you opt in via the new toggle, it kicks off the Custom Data Request on its own.

### Added

- **EU Data Act portal Custom Data Request auto-kickoff** (live-trace based). At startup in read-only `data_act_portal` mode, the coordinator checks each VIN for an existing 15-min Custom Request and creates one when none exists. Uses the verified `/proxy_api/euda-apim/` endpoints captured 2026-06-03: GET `metadata/partial` to detect, CSRF + POST `requests/partial` to kick off, GET `datadelivery/{Identifier}/list` to pick up the ZIPs. The portal accepts at most one active custom request per VIN at a time so the check-then-create order is critical; we adopt an existing request if one is already running instead of double-kicking. New toggle `eu_data_act_auto_kickoff` in OptionsFlow defaults to OFF because the kickoff implies a 1-month data subscription on the user's account at the portal.
- **Repairs issue on portal session expiry**. HTTP 401 on any portal API call now opens a guided `data_act_session_expired` Repairs issue pointing the user at the Reconfigure flow. Portal sessions are cookie-bound and not refreshable, so we surface the prompt instead of silently looping.

## [2.10.4] - 2026-06-03

Two power-user tools for keeping the auth chain alive when VW rotates client_ids.

### Added

- **APK watcher: auto-issue on new OAuth client_id**. The daily atlas builder already polled VW Group APKs and extracted client_ids; now there is a diff step that compares the latest extraction against everything wired into source. When a brand-new id appears, a labeled issue gets opened so the maintainer (or anyone) can promote it into the alternates list without waiting for someone to notice manually.
- **OAuth client_id override in OptionsFlow** (power-user). When the community spots a fresh client_id in a new APK before the daily watcher catches it, paste the full `UUID@apps_vw-dilab_com` into the new field and the resolver tries it first. All existing fallbacks stay in the chain. Empty / malformed values are silently ignored.

## [2.10.3] - 2026-06-03

VW EU users finally get a working read-only path again.

### Fixed

- **Data Act portal SPA password completion** (#388 caraar12345's trace). When the portal's password page is SPA-rendered, v2.10.2 detected it but bailed out telling the user the fallback in idk.py was the route - except that route is for the BFF client, not the portal client, so users on VW EU had nowhere to land. The Data Act portal flow now finishes the SPA-rendered password page itself with a form-encoded POST that includes `action=default` and the state lifted out of the page URL, then runs the standard token exchange. The portal client_id passes the Azure WAF where the main VW Android client_id is blocked, so this is the one path most affected VW EU users can actually use for read-only data.

## [2.10.2] - 2026-06-03

EU Data Act portal flow rebuilt against a verified live trace.

### Fixed

- **Data Act portal OAuth flow** (#388, #393). The portal client uses plain authorization-code flow with `prompt=login`, not the hybrid response_type we were sending. That mismatch was the source of the "unexpected landing URL - IDP may have rejected client_id" error several users hit when the live BFF strategies all failed and the integration tried the read-only fallback. Now switched to standard code flow plus PKCE-S256 plus a token exchange against `identity.vwgroup.io/oidc/v1/token`. Hybrid fragment delivery is kept as a defensive fallback so accounts that happened to work on the old path are not regressed.
- **Data Act portal state-string order**. Was `{country}__{language}__{BRAND}`, now `{language}__{country}__{BRAND}` per the live trace. DE/DE users worked by coincidence; non-matching country/language combinations were routed to the wrong portal locale.

### Added

- **EU Data Act portal usership-verification scaffolding**. New `check_verification_state()` and `submit_usership_verification()` on the scraper detect whether the one-time EU Data Act declaration is on file per VIN and can submit it on behalf of the user when an opt-in config flag is set. The Repairs / OptionsFlow wire-up lands in v2.10.3; the methods are usable from external code today.
- **Data request submission scaffolding**. New `submit_data_request()` and `poll_for_dataset_url()` for the async ZIP delivery flow. Endpoint shapes are best-effort against the documented form fields; verified shapes ship in v2.10.3 once a live trace captures the AJAX call that populates "Ihre Dateien".

## [2.10.1] - 2026-06-03

VW EU login hotfix. The v2.10.0 SPA fix unblocked one path, but several users still hit HTTP 403 on the authorize endpoint itself - the Azure WAF in front of `identity.vwgroup.io` started rejecting the Android user-agent some time on 2026-05-31. Same finding the wider HA-VAG community converged on this week.

### Fixed

- **VW EU 403 on authorize endpoint** (#388, #393). When the initial GET to `/oidc/v1/authorize` comes back 401 or 403, retry once with a plain mobile-browser user-agent. Picks up users blocked at the WAF without affecting accounts that already work on the Android UA.
- **VW user-agent bumped** to `Volkswagen/3.61.0-android/14` to match the current shipping APK. The old `3.51.1` string is what the WAF presumably flagged.

## [2.10.0] - 2026-06-02

The biggest single release so far. VW EU login is unblocked again after the 2026-05-31 backend change, parked cars no longer show all-Unknown, and SEAT/CUPRA gets its Energy-Dashboard story plus settable battery-care.

### Added

- **One service for every vehicle command**. Pick from a dropdown of 14 actions (lock, unlock, climate, charge, lights, window heating, wake, aux heating, ventilation) on any vehicle device. The individual services still work too, no automations break.
- **Wake your car before polling it** (opt-in). When the previous poll said the car was OFFLINE, send a wake first, then poll. Trades one extra API call for getting actual data back. Off by default.
- **See in-flight commands**. New pending-action sensors tell you when a lock/unlock/climate request the app sent is still being processed by the car, so automations can wait for real ack instead of guessing with sleeps. Closes #389.
- **Trip stats per tank or charge session**. 9 new sensors for distance, time, average speed, fuel and electric consumption, plus totals you can feed into the Energy Dashboard. Filled the long-standing gap in HA-VAG land.
- **Real warning-light data on SEAT/CUPRA** from a dedicated backend endpoint, with per-category booleans (engine, brakes, tyre, oil) plus a readable message list.
- **Set the battery-care preservation mode and target SoC** directly from HA on SEAT/CUPRA. Read-side was added in v2.8.1, this completes the write side.
- **Audi plug LED colour** wired up for Q6/A6 e-tron PPE. Older Audis keep the sensor hidden.
- **Real-time charging rate** on Audi + VW EU where the firmware reports it separately from the averaged rate.
- **Rich climate-start service** that lets you set per-seat heating, glass heating, eco-vs-comfort mode, continue-while-unlocked and target temperature in one call. Audi + VW EU only.
- **Charging history with power-curve points** for SEAT/CUPRA, so the DC-fast-charge kW-vs-SoC story finally works there. Diagnostic sensor exposes the curve in attributes, ready for Lovelace charts.
- **Group B: 7 more SEAT/CUPRA endpoints**. App notifications (count + last subject + severity), permissions (owner / can-command), engine + coolant temperature, charging profiles (same shape as Skoda already had), charging modes, a service to push charging settings to the car, and the public charging-station catalog now works on SEAT/CUPRA too.

#### VW EU field parity (Group A) — 10 new sensors

- HV battery min/max temperature (separate from the average) — useful for thermal-runaway alarms on long DC charges.
- Max AC charging current split into "what you set" vs "what the wallbox actually delivers".
- Born MY24+ AC connector auto-release flag + state.
- Optimised battery use toggle (longevity vs performance, distinct from battery-care).
- Active ventilation status + countdown to end.
- Rear sunroof + Cabrio roof-cover position.
- 12V battery health bucket (low / normal / high), distinct from the existing voltage sensor.
- Last-trip absolute fuel + electric consumption totals.

#### VW NA endpoint parity (Group C)

- Subscription + capabilities sensors on VW NA (Cox-backend). Pre-v2.10.0 SEAT/CUPRA + VW EU only.
- Modern Cox two-step SPIN flow for privileged actions. The old in-body SPIN still works as fallback.
- Modern lock/unlock endpoint, falls back to the legacy one on 404.
- NA-specific climate + window-heating endpoints, falls back to EU-style on 404.

### Fixed

- **VW NA "everything Unknown" on ID.4 US 2023** (#322 roberttco). Cox migrated the response shape; we now read both old and new shapes so accounts on either firmware get real values.
- **Scout stops shouting** about warning-light error envelopes and pending-action requests. Both are bff-internal wrappers, not real new data. Closes #389.
- **VW EU login broken after 2026-05-31** (#388 BalooDK + swebachus). VW migrated the password page to a JS-rendered shape and our form POST started getting "wrong credentials" even when they were right; the Data-Act fallback then mistook the SPA's `consent.js` asset for a real consent wall. Retry the same login URL with JSON content-type, and tightened the consent-wall detection so it doesn't trip on `consent.js`. VW EU users can log in again.
- **Tire pressure on newer PPC firmware**. Same data, new branch in the response; the parser now checks both branches.

### Documented

- Active-ventilation TODO from v2.4.x is cleared — Group A above shipped the parser and entities.
- Deeplink scheme TODOs are cleared. The smali extractions don't carry URI scheme strings (they live in AndroidManifest.xml + iOS Info.plist), so the shipped schemes stay sourced from each brand's launcher metadata.

## [2.9.0] - 2026-06-02

Hardening bundle: provenance canaries + weekly watcher, SPDX license headers across all Python files, and VW account-lock detection with a guided Repair issue.

### Added

- **VW account-lock detection**. After the 2026-05-31 ecosystem-wide VW Auth chaos surfaced a new failure mode (oliverrahner on volkswagencarnet#332 reporting his brand account getting locked for ~24h after too many failed token-refresh attempts), the coordinator now tracks HTTP 423 (Locked) and HTTP 403 with throttling-marker bodies on the token endpoint. Three such responses inside a 30-minute sliding window surface a Repair issue (`account_locked`) explaining the lock + next steps (wait, raise scan_interval, optionally switch to read-only Data Act portal mode). Auto-clears on the next successful auth. Native DE translation, EN parity for the other 7 supported languages.
- **Provenance canaries + weekly watcher**. New `custom_components/vag_connect/_canaries.py` declares 5 uniquely-spelled identifier strings, one per strategic module (auth resolver, Data Act scraper, DAG flow, Scout, watchdog). Each canary is also referenced from the module it watermarks so it travels with any port. Weekly cron in `.github/workflows/canary-watch.yml` queries GitHub Code Search for the canaries outside the `its-me-prash` namespace and opens a triage issue tagged `provenance` when a foreign hit appears. Apache 2.0 permits the port; the canaries make stripping the LICENSE + NOTICE observable.

### Changed

- **SPDX-License-Identifier headers** added to all 158 Python files. Files already carried the copyright + Apache 2.0 line; this adds the machine-readable SPDX identifier on the line below so REUSE / FOSSA / SCANCODE-class license scanners pick them up without parsing free-text. Mechanical change, no behaviour impact.

## [2.8.2] - 2026-06-02

### Fixed

- Scout no longer auto-fires on the 6-key `.error.*` envelope the Cariad BFF returns when the `vehicleHealthWarnings.warningLights` job hits a 5xx upstream. Same shape as the v2.7.4 fix for `oilLevel.error` / `tyrePressure.error` / `auxiliaryHeating.error`, one branch deeper. Closes #384 (moltke69 Audi scout).

## [2.8.1] - 2026-06-01

Closes 11 SEAT/CUPRA OLA-field parser gaps surfaced via side-by-side comparison with the pycupra reference, after the v2.5.3 OLA v1/v5 fallback chain did not fix DanielBie's offline-Leon entity coverage (issue #306).

### Added

- 11 new sensors backed by OLA fields that the seat_cupra parser was not reading: `adblue_level_pct` (% tank level for diesel SCR, separate from the existing `adblue_range_km`), `cng_level_pct` + `cng_range_km` (CNG variants like Polo TGI, Mii Ecofuel, Leon TGI), `primary_engine_range_km` (PHEV / dual-fuel parity with the existing `secondary_engine_range_km`), `charging_preferred_mode` (user-selected mode mirror), `seat_heating` (any-seat-on aggregate), `parking_light`, `external_power` (charger is actually energising the cable, distinct from `plug_connected`), `battery_care` (preservation mode flag), `energy_flow` (any HV-battery exchange happening), `area_alarm` (geofence event). All entries phantom-protected via `_DATA_PRESENT_REQUIRED` so vehicles without the underlying field stay clean.
- Translations for the 11 new entities mirrored across all 9 supported languages (DE + EN canonical, the other 7 carry the EN labels until per-language polish; cross-lang parity test pinned).

## [2.8.0] - 2026-06-01

Stable cut of the v2.8.0 series. Promotes 2.8.0rc1 + 2.8.0rc2 from release-candidate to stable with no further code changes; the rc cycle ran under 24 hours and the only reported field issue (#378 from jwaeles) was fixed in rc2.

### What is new vs v2.7.4

- Five action items from the 2026-05-30 competitive scan: MFA / Email-OTP handler, coordinator auto-reload watchdog, headless EU Data Act portal zip scraper, FCM push live activation for Audi and VW, Repairs flow for DAG-to-hybrid_full degradation.
- Five v3.0 quick wins pulled forward: auxiliary-heating entities (switch + 2 numbers + sensors) for Audi and VW, `vag_connect.open_app` service with per-brand deeplinks, brake-service plus preferred-workshop sensors for all 4 Cariad brands, per-job parser-health telemetry in diagnostics, per-brand declared-vs-observed capability snapshot in diagnostics.
- 30-day device-bound IDP cookie persistence across HA restarts to skip the email-OTP challenge.
- Roadmap consolidation: five overlapping roadmap docs reduced to one canonical top-level `ROADMAP.md` with a new "Won't do" block listing 11 explicit exclusions.
- Dead-weight cleanup: Pydantic dual-write scaffold removed (blocking-IO warning gone), `euda.py` shim retired, 6 stale v1.x docs + 12 dead probe scripts deleted.
- README rewritten for all nine languages: DE + EN canonical, the other seven mechanically synchronised. Drops the v2.0 Big-Bang highlights and adds honest "Where we lead" + "Where the limits are" blocks.

### What changed during the rc cycle (rc2 hotfixes folded in)

- VW EU re-auth after the 2h token expiry was crashing in the Data Act portal fallback because the IDP migrated the `hmac` and `_csrf` fields out of plain `<input type="hidden">` markup into a SPA-rendered JSON block. The portal-side form parser now mirrors the multi-fallback strategy already in `idk.py:_parse_csrf_robust` (HTMLParser, regex over hidden inputs, form-action regex, and JSON/script-block extraction). Reported in #378.
- Two-way auth recovery for VW EU and Audi hybrid_full. After the hybrid flow succeeds, the integration now opportunistically exchanges the auth_code that Auth0 also delivers in the callback URL for a token set that may include a real refresh_token. Strictly additive: when the standard token endpoint is still Play-Integrity-walled the exchange fails silently and the hybrid-only TokenSet is kept (v2.6.0 behaviour preserved); when the wall has been loosened (as observed across the ecosystem around 2026-05-31) the upgraded TokenSet replaces the hybrid one and the next 2h boundary refreshes against `/auth/v1/idk/oidc/token` instead of triggering a full relogin.

## [2.8.0rc2] - 2026-06-01

Two-way VW EU re-auth recovery + hotfix for the 2026-05-31 IDP markup migration that broke the Data Act portal fallback. Same feature set as 2.8.0rc1 plus the two fixes below.

### Fixed

- VW EU re-auth after the 2h token expiry was crashing in the Data Act portal fallback because the IDP migrated the `hmac` and `_csrf` fields out of plain `<input type="hidden">` markup into a SPA-rendered JSON block. The portal-side form parser now mirrors the multi-fallback strategy already in `idk.py:_parse_csrf_robust` (HTMLParser, regex over hidden inputs, form-action regex, and JSON/script-block extraction), so a markup migration on either side fails loudly in the regression tests instead of in production. Reported in #378.

### Changed

- Two-way auth recovery for VW EU and Audi hybrid_full strategy. After the hybrid flow succeeds, the integration now opportunistically exchanges the auth_code that Auth0 also delivers in the callback URL for a token set that may include a real refresh_token. Strictly additive: when the standard token endpoint is still Play-Integrity-walled the exchange fails silently and the hybrid-only TokenSet is kept (v2.6.0 behaviour preserved). When the wall has been loosened (as observed across the ecosystem around 2026-05-31) the upgraded TokenSet replaces the hybrid one and the next 2h boundary refreshes against `/auth/v1/idk/oidc/token` instead of triggering a full relogin. Combined with the form-parser fix above this gives two independent recovery paths (refresh + full relogin via portal fallback) so a single endpoint flap on either side does not break re-auth.

## [2.8.0rc1] - 2026-05-31

First release candidate for v2.8.0. Bundles the five action items from the 2026-05-30 competitive scan with five v3.0 quick wins pulled forward, plus a dead-weight cleanup pass and a roadmap consolidation. README rewritten across all nine supported languages for v2.7.x reality (DAG MVP positioning + honest VW EU Play-Integrity limits).

### Action items

- MFA / Email-OTP config_flow handler (#1). The VW IDP can challenge for a 6-digit code on first sign-in; the flow now captures it cleanly instead of failing with a generic `cannot_connect`.
- Coordinator auto-reload watchdog (#2). When all VINs on the hybrid_full strategy show `failure_count >= 2` and `last_good_at` is older than 2x the scan interval, the coordinator silently re-authenticates without dropping entities. Mirrors the upstream community automation pattern but internalised so users do not have to wire it themselves.
- Headless EU Data Act portal zip scraper (#3). New `cariad/auth/_data_act_scraper.py` wired as Tier 3.5 (activates only when the active strategy is `data_act_portal`). Route A probes a research-confirmed JSON endpoint; Route B is fully scaffolded behind a new `CONF_ENABLE_DATA_ACT_BROWSER` OptionsFlow toggle that drives a headless Chromium via the optional `playwright` package (NOT in `manifest.json` — 100 MB Chromium download stays opt-in). Missing-dep surfaces a `data_act_browser_missing` Repair issue.
- FCM push channel for Audi and VW now ships live activation (#4). Decoded payloads (lockState, chargingState, climateState, alarm) are fired onto the HA event bus as `vag_connect_push_event` and trigger a coordinator refresh. The Cariad Firebase sender_id / api_key / app_id are still tester-gated behind a `NotImplementedError` in `_resolve_fcm_credentials` until the live APK extraction lands; the OptionsFlow toggle label moves from "EXPERIMENTAL" to "Live (beta)".
- Repairs flow when DAG degrades to hybrid_full (#5). New `auth_strategy_degraded` issue surfaces in the HA UI after 3 consecutive successful polls confirm the resolver has silently fallen back, with two guided remediations: re-run the browser-login setup, or pin the read-only Data Act portal mode (via the new `CONF_PREFERRED_AUTH_STRATEGY` option).
- MFA / 30-day device-bound IDP cookie persistence. The VW IDP issues a cookie after a successful email-OTP that suppresses the OTP for around 30 days; until now we discarded it on every restart, reload, and 2h re-login. `TokenSet`, `TokenStorage`, and `IDKAuth` all extended to round-trip the cookie. Latent bug-fix included: the storage layer never persisted `strategy` or `auth_cookies`, so the watchdog never saw the active strategy after a restart.

### Quick wins from the v3.0 roadmap (pulled forward)

- Standheizung / auxiliary-heating surface (quick win A): switch + duration number (5–60 min) + target-temp number (16–30 °C) + new `auxiliary_heating_status` + `aux_heating_active` + `auxiliary_heating_remaining_min` sensors. Audi + VW EU only; SEAT/CUPRA flow continues to require S-PIN. Capability map declares `auxiliaryHeating` for the two new brands.
- `vag_connect.open_app` service (quick win B). Fires `vag_connect_open_app` on the HA event bus with `{vin, brand, deeplink_url, action}` so a Lovelace card can open the brand's native mobile app on the calling device via `window.location.href`. Deeplink schemes are defined in `const.DEEPLINK_SCHEMES`; the per-brand scheme strings are marked `TODO(2.8.1)` for device-side re-verification once the v2.8.1 IPA/smali pass lands.
- Brake-service + preferred-workshop sensors (quick win C). Six new sensors: `brake_fluid_change_due_at`, `brake_pads_front_inspection_due_at`, `brake_pads_rear_inspection_due_at`, `preferred_workshop_name`, `preferred_workshop_address`, `preferred_workshop_phone`. Populated for VW EU + Audi (CARIAD-BFF `serviceCare`), Skoda mysmob `maintenanceReport`, and SEAT/CUPRA OLA `maintenance` when the dealer has wired up the service plan. Phantom-protected via `_DATA_PRESENT_REQUIRED`.
- Parser-health telemetry in diagnostics (quick win D). Each brand client's `parser_stats` dict records `{success, fail, last_error[:200]}` per named job (`oil_level`, `charging`, `climatisation`, `tyre_pressure`, `auxiliary_heating`, `trip_statistics`, `service_care`, etc.) and is exported in the diagnostics dump, so a silent parser regression on one job is visible while the rest of the poll succeeds. PII redaction reuses the existing JWT/VIN/email scrubber.
- Per-brand capability advertisement in diagnostics (quick win E). New `cariad/_capabilities.py` declares the expected per-brand capability matrix; `coordinator.capabilities_snapshot()` adds the observed-this-poll view and a `drift` list flagging declared-True-but-observed-False. Lets a missing entity be triaged as "brand never supported it" vs "parser dropped a field" without reading source code.

### Housekeeping

- Dead-weight cleanup pass. Removed the v2.2.0 Pydantic dual-write scaffold (one model, return value discarded everywhere, plus a blocking-IO warning on every fresh HA startup), retired the `euda.py` v2.0 shim that had zero callers, deleted 6 stale v1.x docs and 12 dead probe scripts from the v1.27 research era.
- Roadmap consolidation. Five overlapping roadmap docs reduced to one canonical top-level `ROADMAP.md`. New "Won't do" block records the 11 things we have explicitly ruled out (MBB direct-data path, Lamborghini/Bentley/Bugatti commands, VW China, etc.) so future feature requests can point at it.
- README rewritten for all nine languages. Drops the v2.0 Big-Bang highlights and adds honest "Where we lead" + "Where the limits are" blocks. DE + EN canonical, the other seven languages mechanically synchronised.

## [2.2.0-rc1] — 2026-05-16 — "Legen — wait for it — dary" (Release Candidate)


## [2.2.0] — 2026-05-17 — "Legen — wait for it — dary" (Final)


## [2.2.1] — 2026-05-17 — Phase 8 "alles parsen statt silencen" + Cross-Brand Expansion

- Cross-Brand App Atlas
- OLA watcher gains upstream as 3rd consensus source
- App Atlas covers all 7 brands

## [2.7.4] - 2026-05-31

### Fixed
- Scout no longer auto-fires on the 6-key `.error.*` envelope the Cariad BFF returns when `oilLevel` / `tyrePressure` / `auxiliaryHeating` jobs hit a 5xx upstream. v2.7.1 silenced the parent path but the single-level `.*` wildcard did not cover the 4-component child paths. Closes #371 and #373.

## [2.7.3] - 2026-05-31

### Changed
- Data Act portal auth: when the password form is missing in the response, scan the returned HTML for EU Data Act consent signals (`data act`, `consent`, `einwilligung`, `zustimmung`, `shape the future`, `datenverarbeitung`) before falling back to the generic credentials-rejected message. Surfaces a clearer instruction for users who hit the consent wall on `myvolkswagen.*` (issue #372).

## [2.7.2] - 2026-05-31

### Security
- Coordinator setup-failure log no longer prints the raw exception message at ERROR level. An aiohttp `InvalidURL` raised on the OAuth callback path could surface the full redirect URL including `access_token`, `id_token`, and `code` JWTs, all of which base64-decode to the user's email and a working access token. Log type only at ERROR; message at DEBUG.

### Fixed
- Multi-strategy auth resolver in `base.py` now also catches non-`AuthenticationError` exceptions (e.g. `aiohttp.InvalidURL`), converts them to a clean `AuthenticationError`, and falls through to the next strategy. Prevents the raw URL from leaking up to the coordinator's catch-all.

## [2.7.1] - 2026-05-31

### Fixed
- Vehicle Data Scout no longer auto-fires on `oilLevel` / `tyrePressure` / `auxiliaryHeating` branches we just promoted in v2.7.0. Closes scout-report issues #366 and #367.

## [2.7.0] - 2026-05-31

### Added
- Browser-Login (OAuth Device Authorization Grant) for Audi, Škoda, SEAT, CUPRA. Open a QR code on your phone, sign in to your Brand ID account, confirm a short code. No password stored in Home Assistant, real refresh_token from the IDP.
- Trip statistics: `last_trip_*` and `lifetime_*` sensors populate from `/tripstatistics?type=shortTerm|longTerm`.
- `warning_messages` sensor surfaces every backend warning the manufacturer app would show (Audi STO / towing-bracket alerts etc), not just the hardcoded oil/engine/brake/tyre family.
- `oilLevel` and `tyrePressure` jobs added to the selectivestatus request. Populates `oil_level_warning` binary_sensor and the existing `tire_pressure_*_bar` sensors.

### Fixed
- Per-door, per-window, sun-roof, trunk-lock state now populate on locked cars (was only on unlocked).
- Outside temperature parser tries multiple backend key variants for Audi MY24+ compatibility.
- Window heating front/back parser tries multiple JSON shape variants.
- `wake_count_today` defaults to 0 instead of Unknown.
- TIMESTAMP sensors parse ISO 8601 strings to tz-aware datetime (cures entity-add failure on subscription_expiry_at).
- Cross-language translation parity. All 8 supported languages now ship the full config_flow translation set (browser_login, browser_login_approve, menu_options, progress, errors).

### Notes
- If field labels in the config dialog render as raw keys (`brand`, `spin`, etc) after upgrade, do a hard browser refresh (Ctrl+Shift+R). Home Assistant caches translations client-side and may not pick up the new keys until the browser cache clears.

## [2.7.0b11] - 2026-05-31

### Added
- Trip statistics endpoint wired. `last_trip_*` and `lifetime_*` sensors now populate from `/vehicle/v1/vehicles/{vin}/tripstatistics?type=shortTerm|longTerm`. Closes Unbekannt on Lifetime Distance, Last Trip Distance / Avg Speed / Avg Fuel Consumption, Lifetime Avg Fuel Consumption.
- `warning_messages` text sensor showing every backend warning as `type: text`, comma-joined. Surfaces brand-specific warnings the hardcoded oil/engine/brake/tyre binary sensors miss (e.g. Audi STO / towing-bracket alerts that come through in the myAudi email notifications).
- `wake_count_today` defaults to 0 on first data load instead of None / Unbekannt. The counter only increments when the user uses the wake button; users who never wake the car now see 0 instead of "Unknown".

### Fixed
- Outside temperature parser tries multiple backend key variants (`outsideTemperature_K`, `temperatureOutside_K` under `outsideTemperatureStatus` and `temperatureOutsideStatus`). Closes Unbekannt on Audi MY24+ models where the key differs from the canonical Cariad name.
- Window heating front / back parser tries multiple JSON shape variants (`windowHeatingStatus` / `statusList` / `windowHeatingStatusList` / direct array under value). Closes Unbekannt on brands shipping the data under a non-canonical key.

## [2.7.0b10] - 2026-05-31

### Added
- `oilLevel` job in the CARIAD-BFF selectivestatus request. New binary_sensor `oil_level_warning` (Oil Level / Ölstand). Closes "Oil Level" Unbekannt gap vs upstream.
- `tyrePressure` job in the same request. Populates the existing `tire_pressure_*_bar` sensors and `tire_pressure_warning` binary_sensor. Closes per-wheel pressure Unbekannt gap.
- `auxiliaryHeating` job for future Webasto / standheizung parity.

### Fixed
- Per-door and per-window state was only populated when the car was unlocked (`overallStatus == "UNSAFE"`). On a locked car the parser left `doors_individual` / `windows_individual` empty and all per-position entities (Left Front Door, Sun Roof, etc) rendered as Unbekannt. Now always iterate the doors and windows arrays regardless of overall status.
- Trunk lock state was never extracted from the access response. Pulled from the doors array entry with name "trunk", populating the existing `trunk_locked` binary_sensor.

## [2.7.0b9] - 2026-05-31

### Changed
- DAG browser-login Phase 2: URL and user_code now live inside the form schema as pre-filled fields, not just in the description. Description rendering kept failing on real installs (translation-loader miss or HA frontend quirk). Schema fields render reliably.
- Added a QR code selector showing the verification URL. Scan with phone camera to open the login page in one tap.
- Field labels chosen so the raw-key fallback ("verification_url", "user_code", "approved_in_browser") stays readable when translations miss.
- Persistent notification and WARNING log line from b8 kept as belt-and-suspenders.

## [2.7.0b8] - 2026-05-31

### Fixed
- DAG browser-login: URL and user_code now surface through three independent paths so at least one always renders even when the others fail. (1) form description (was already in b7), (2) persistent_notification fired on form first entry, (3) WARNING log line with both values. Defense against the empty-dialog-body symptom seen on b7 even after full HA restart.
- DAG browser-login form: switched from empty `vol.Schema({})` to a single optional confirm boolean. Empty schemas caused HA's frontend to skip description rendering on at least one install.

## [2.7.0b7] — 2026-05-31 — "DAG spinner-forever fix #3 — form-based URL display (beta)"

- After b4 and b6 both failed to reliably surface the verification URL + user_code in the show_progress dialog (HA frontend cached the progress description per flow id and didn't always pick up `description_placeholders` even when the show_progress task and step_id changed), Phase 2 is now rendered as a normal config_flow form. Forms substitute placeholders via the standard text-rendering pipeline which works reliably.
- New UX:
  - URL + 6-digit code shown as plain markdown text — fully visible and copyable
  - Submit button visible from the start
  - User opens URL in their browser (any device), signs in, approves
  - When done, clicks Submit
  - Background poll task validates with VW backend
  - If poll done + tokens → advance to entry creation
  - If poll done + error → drop back to brand picker (retry)
  - If user clicked Submit before approval was complete → re-renders form with a "still waiting for browser approval" hint
- Trade-off vs show_progress: lost auto-advance (user has to click Submit once they've approved), but gained guaranteed visibility of the URL + code. Worth it.
- Translation key added: `still_waiting_browser` (DE + EN).

## [2.7.0b6] — 2026-05-31 — "DAG spinner-forever fix #2 — split phases into distinct step_ids (beta)"

- Browser-login progress dialog now reliably shows the verification URL + user_code after the device_code is acquired. The b4 attempt at a single-step two-phase flow ran into HA's frontend caching the progress description per step_id — when the same step_id returned a second `show_progress` with a different `progress_action` and new `description_placeholders`, the dialog often kept showing the first (empty) description and the spinner appeared to spin forever.
- Refactored into two distinct step_ids:
  - `browser_login_pending` — Phase 1 only (request /device_authorization). Shows "Requesting login code…".
  - `browser_login_approve` — Phase 2 only (poll /token). Shows "Open {url}, enter {code}, sign in".
- HA tears down the first dialog cleanly between phases and renders a fresh one for Phase 2, so the placeholders apply correctly the first time.

## [2.7.0b5] — 2026-05-31 — "TIMESTAMP sensors fix (beta)"

- subscription_expiry_at (and any other ISO-string sensors with TIMESTAMP device class) now parse to timezone-aware datetime in native_value. Pre-fix HA rejected the entity at add-time with 'str has no attribute tzinfo'.

## [2.7.0b4] — 2026-05-31 — "Menu + DAG progress UX fix (beta)"

- Browser-Login / Email+Password menu now passes labels in the code instead of relying on the HA translation lookup — cures empty-chevron rendering when the integration is updated without an HA restart.
- Browser-Login progress: split into two phases so the URL + user_code populate in the progress text BEFORE the long poll begins. Previously the progress UI showed only "Waiting for browser approval…" with the URL/code never appearing.

## [2.7.0b3] — 2026-05-31 — "Hassfest + test contract fixes (beta)"

- Translations: moved progress key from inside step to top-level config.progress per HA schema.
- Tests aligned with v2.7.0b1 menu split and v2.7.0b2 5-header default.

## [2.7.0b2] — 2026-05-31 — "Audi token-headers fix (beta)"

- Audi email+password login: dropped the dummy x-assertion / x-platform / x-android-package-name trio from token requests — VW backend now rejects the dummy value and lets through requests that omit the headers entirely. Matches upstream v1.19.2+ behaviour.

## [2.7.0b1] — 2026-05-31 — "Browser-Login UI (beta)"

- New config_flow menu: choose between Browser-Login (recommended) and Email + Password (legacy).
- Browser-Login wires the v2.6.0 OAuth Device Authorization Grant module into HA's show_progress flow — open a URL, enter a short code, no password stored in HA.
- Available for Audi, Škoda, SEAT, CUPRA. VW EU + Porsche stay on the email + password path.

## [2.6.0] — 2026-05-31 — "Multi-Strategy Auth (Hybrid + DAG + Data Act)"

- VW EU now logs in via OIDC hybrid flow (response_type=code id_token token) — bypasses Play Integrity wall.
- OAuth Device Authorization Grant (RFC 8628) module for Audi/Skoda/SEAT/CUPRA — browser-based, password-less, refresh-token-friendly. UI wiring lands in v2.7.0.
- Per-brand strategy resolver with automatic fallback (up to 3 tiers per brand).
- In-house EU Data Act portal auth as last-resort read-only fallback strategy.

## [2.5.13] — 2026-05-30 — "Play Integrity Wall Decoded"

- Discovered: Play Integrity attestation

## [2.5.12] — 2026-05-30 — "Market-Config Activation + Atlas Pipeline Audit"

- `refresh_audi_market_config()` was never called in v2.5.11
- Atlas-builder APK extraction pipeline broken since 2026-05-25
- Strategic update on #336 (VW GIS Migration)

## [2.5.11] — 2026-05-30 — "Field-tested Auth Hardening"

- VW EU was silently impersonating the Audi app via the `x-android-package-name` token
- Audi market-config dynamic discovery
- evcc-derived alternate OAuth `client_id` for Audi

## [2.5.10] — 2026-05-29 — "VW NA Polish (roberttco bundle, 2 of 5)"

- #323 — "Last Update value does not reflect last time data was updated"
- #325 — "Controls become disabled after using them"
- #322 — "Sensors are unknown or incorrect"

## [2.5.9] — 2026-05-29 — "Scout-Policy T1 — Parse What We Silenced"

- NEW `binary_sensor.camping_mode`
- CUPRA `battery.chargeEnergyInKwh` → `sensor.total_charged_energy_kwh`

## [2.5.8] — 2026-05-29 — "Silencer Sweep (campingMode + CUPRA charging rename)"

- Silenced 11 scout-reports in one sweep
- Why a single silencer-sweep release

## [2.5.7] — 2026-05-29 — "502 Resilience + OIDC Discovery + qmauth Fallback Chain"

- Stop misdiagnosing VW server outages as credentials failures
- OIDC discovery for token URL
- qmauth fallback chain

## [2.5.6] — 2026-05-28 — "APK-Primary Auth-Config with OAuth Client-ID Fallback Chain"

- NEW
- New module: `cariad/auth/_auth_config_resolver.py`
- OAuth client_id fallback chain

## [2.5.5] — 2026-05-28 — "App Atlas Phase A.5: Auth-Config Shield"

- App Atlas APK extraction now mines auth-config secrets too
- New `auth_secrets` bucket
- Audi

## [2.5.4] — 2026-05-28 — "VW Azure WAF Migration Emergency Hotfix (#313)"

- Audi and Volkswagen EU login failed with HTTP 403
- The fix (ported from evcc PR #30277 + PR #30292, MIT-licensed, merged hours earlier on
- Cross-reference (independent confirmations of the same migration)

## [2.5.3] — 2026-05-28 — "OLA v1↔v5 Fallback Chain (#306 Mii/Tavascan/Leon FR-KL Fix)"

- SEAT + CUPRA users on older vehicle generations (SEAT Mii Electric, CUPRA Tavascan VZ,
- `doors_locked` vs `doors_open` contradiction resolved
- Offline vehicle?

## [2.5.2] — 2026-05-28 — "Scout Pipeline Expansion"

- Vehicle Data Scout coverage widened across all 7 brands
- What this means for you
- Public framing

## [2.5.1] — 2026-05-28 — "Consent Wall Auto-Skip Hotfix"

- Audi/VW/Škoda/SEAT/CUPRA login regression — consent wall now auto-skipped
- Better error message for "Login redirect missing after password submission"
- Affected users

## [2.5.0] — 2026-05-27 — "Have You Met Mii?" (PyCupra Parity Sprint Part 1)

- 4 new binary_sensors
- Hints toward v3.0 — "Suit Up: The Push Tech Edition" 🎩

## [2.4.2] — 2026-05-27 — "Retro-Silencer Sweep + ActiveVentilation Interim"

- VW EU + Audi
- Silenced by code (3)
- Already-fixed in v2.4.1 — reporters on stale versions (4)

## [2.4.1] — 2026-05-25 — "OLA Defense + VW NA Garage + Scout Policy"

- OLA authentication — defense-in-depth
- Scout Policy

## [2.4.0] — 2026-05-23 — "Marketing-Rename: VAG Connect → VW Group Connect (Community Tribute)"

- 🪪 Marketing-Rename: "VAG Connect" → "VW Group Connect"

## [2.3.0] — 2026-05-23 — "VW North America Login Fix + Audi Route-aware Charging"

- #269 (roberttco VW NA, 2026-05-21) — VW North America Login (US/CA) endlich funktional
- #264 (moltke69 Audi, 2026-05-19) — Route-aware Smart Charging Sensoren

## [2.2.3] — 2026-05-23 — "Easter Egg + Sprint A Quick-wins"

- 🥚 Easter-Egg Service `vag_connect.show_vag` (Community Tribute)
- #270 (roberttco VW NA, 2026-05-21) — Config-flow Brand-Selection
  bleibt nach
- Scout #268 + #271 (VW EU arvcer, 2026-05-21/22) —
  `charging.chargingStatus.requests`

## [2.2.2] — 2026-05-18 — "Silencer Catch-up + Laien-friendly Names + Diesel Dashboards"

- Scout #260 silencer-fix + cross-language entity-name laien-cleanup
- Bubble Card ready-made templates für VAG Connect (`docs/lovelace/bubble-card/`)
- Bubble Card diesel variant `02b-vehicle-popup-diesel.yaml` (Audi
  S6 TDI tailored)

## [2.2.1] — 2026-05-17 — Phase 8 "alles parsen statt silencen" + Cross-Brand Expansion (continued)

- Phase 8 PR #5 — `car_type` cross-brand derivation helper
- Phase 8 PR #4 — VW EU/Audi `primary_engine_fuel_level_pct` mirror
- Phase 8 PR #3 — Porsche electric/combustion range split

## [2.1.0] - 2026-05-15 ✨🌍 Post-Big-Bang Wins — Skoda Climate-Ready + HomeRegion + User-Tools / Post-Big-Bang Wins — Skoda Climate-Ready + HomeRegion + User-Tools

- Skoda Climate-Ready-At Sensor
- `scripts/verify_my_vin.py` — User-facing pre-flight diagnostic
- `docs/recipes/browser-mod.md` — Cookbook für browser_mod ↔ VAG Connect

## [2.0.1] - 2026-05-15 🚨🔒 Safety-Fix: `doors_locked` False-Negative Cross-Brand / Safety-Fix: `doors_locked` False-Negative Cross-Brand

- Critical Safety-Fix: `doors_locked` zeigte fälschlich "Unlocked" für tatsächlich
- CUPRA Born MY26 `charging.rateInKmph` Parser-Fallback (closes Scout #192)

## [2.0.0] - 2026-05-15 🎯🚀 Big-Bang Release — 19 PRs in einem Schlag / Big-Bang Release — 19 PRs in one shot

- `quality_scale: platinum`
- DeviceInfo `configuration_url` + `suggested_area="Garage"`
- System Health Panel

## [1.27.2] - 2026-05-11 ⚡🔌 Scout-Felder Power-Patch + Plug-Diagnose / Scout-Felder Power-Patch + Plug Diagnostics

- ✨ Neue Entities
- 🎯 Scout Issues Closed
- 📋 Scout-Pipeline-Policy

## [1.27.1] - 2026-05-11 🚨🔧 Hotfix: device_tracker GPS-Daten / Hotfix: device_tracker GPS data

- 🐛 Root cause
- 🔧 Fix
- ✅ Was jetzt funktioniert

## [1.27.0] - 2026-05-11 🔬📋 Pre-Cariad PHEV Research + Strategic Roadmap / Pre-Cariad PHEV Research + Strategic Roadmap

- `_private/research-archive/2026-05_pre-cariad-mbb-and-golf-7-gte-audit.md`
- `_private/research-archive/2026-05_strategic-roadmap-v1.27-to-v2.0.md`
- `ROADMAP.md`

## [1.26.2] - 2026-05-09 🚨🔧 Hotfix-2: Root cause `zip_release` revertet — HACS install path / Hotfix-2: Root cause `zip_release` reverted — HACS install path

- `hacs.json`
- 🔍 Root cause
- 🔄 Reverted

## [1.26.1] - 2026-05-09 🚨 Hotfix: Integration lädt nicht in v1.25.x / Hotfix: integration won't load in v1.25.x

- `manifest.json`
- `entity_base.py:device_info`
- 🔄 Reverted

## [1.26.0] - 2026-05-09 🎯 Welle-6 Feature Backlog (#173) — 7 neue Entitäten + Cross-Brand Parity / Welle-6 Feature Backlog (#173) — 7 new entities + Cross-Brand Parity

- `sensor.<vin>_secondary_engine_range_km`
- `sensor.<vin>_next_charging_timer_id`
- `sensor.<vin>_next_charging_timer_target_soc_reachable`

## [1.25.0] - 2026-05-09 🚀 Sprint C — Cross-Brand Parity + UX/UI + MBB VSR Phase 2 (Golf 7 GTE Tank) / Sprint C — Cross-Brand Parity + UX/UI + MBB VSR Phase 2 (Golf 7 GTE Tank)

- Cross-brand parity wins
- `_normalize.py`
- Porsche HTTP hardening

## [1.24.2] - 2026-05-08 🧪 Test Foundation: Property-Tests + Porsche/VW NA Parity + safe_int/float Migration / Test Foundation: Property-Tests + Porsche/VW NA Parity + safe_int/float Migration

- Echter Production-Bug gefunden + gefixt
- 🧪 Property-Tests via hypothesis / Property-Tests via hypothesis
- 🧪 Porsche + VW NA Parser Parity / Porsche + VW NA Parser Parity

## [1.24.1] - 2026-05-08 🛠️ v1.24.0 CI-Failure-Fix + Doc Hygiene + Quick-Win-Hardening / v1.24.0 CI-Failure-Fix + Doc Hygiene + Quick-Win-Hardening

- Ruff `E741` Ambiguous variable name `l`
- 🐛 Bugfix / Bugfix
- 🔒 Security / Security

## [1.24.0] - 2026-05-08 🚗 Cross-brand Image-Entity Wiring (CUPRA/SEAT silent bug + Skoda multi-angle) / Cross-brand Image-Entity Wiring (CUPRA/SEAT silent bug + Skoda multi-angle)

- Post-Fix
- 🐛 Bugfix — CUPRA/SEAT Silent Bug (seit OLA-Support live) / Bugfix — CUPRA/SEAT Silent Bug
- 🚀 Neu — Skoda mysmob Multi-Angle Wire-In / New — Skoda mysmob Multi-Angle Wire-In

## [1.23.0] - 2026-05-07 🚀 Audi/VW Push Foundation (Cariad FCM channel) / Audi/VW Push Foundation (Cariad FCM channel)

- Neues Modul
- Neuer Config-Flow Toggle
- Bilingual translations

## [1.22.0] - 2026-05-07 🖼️ Skoda Widget Render → Image Entity (Bundle 2 Phase B Pragmatic) / Skoda Widget Render → Image Entity (Bundle 2 Phase B Pragmatic)

- Neue Image-Entity
- `VagSkodaWidgetImageEntity` Klasse
- `_cache_all_images` Erweiterung

## [1.21.0] - 2026-05-07 🔄 Audi/VW MBB Legacy-Path Migration Phase 1 / Audi/VW MBB Legacy-Path Migration Phase 1

- MBB für andere Commands
- SPIN secure-token flow
- Country-detection

## [1.20.3] - 2026-05-07 🚨 Cariad-wrapper-404 Detection + Switch Hasattr-Gate (Audi/VW user-report) / Cariad-wrapper-404 Detection + Switch Hasattr-Gate

- Audi App-Push "Fahrzeug derzeit nicht erreichbar"
- Wake/Climate/Charging 404
- Single info-log per command

## [1.20.2] - 2026-05-07 🧹 Skoda Parser Hardening + Phantom-Entity Fix + Code-Hygiene Bundle / Skoda Parser Hardening + Phantom-Entity Fix + Code-Hygiene Bundle

- 3 Scaffolding-Module mit `# SCAFFOLDING — NOT WIRED` Header
- ROADMAP "Standalone enhancements" Cleanup
- ROADMAP "Last updated" Header

## [1.20.1] - 2026-05-07 🔓📚 BinarySensor LOCK-class fix (#131) + Doc refresh / BinarySensor LOCK-class fix (#131) + Doc refresh

- README.md "Was noch in Arbeit ist"
- FAQ.md
- #131

## [1.20.0] - 2026-05-06 🚗 Bundle 2 Phase A: Skoda Widget + Vehicle-Info + Equipment / Bundle 2 Phase A: Skoda Widget + Vehicle-Info + Equipment

- `GET /api/v2/widgets/vehicle-status/{vin}`
- `GET /api/v1/vehicle-information/{vin}`
- `GET /api/v1/vehicle-information/{vin}/equipment`

## [1.19.4] - 2026-05-06 🔧📊 Bundle 1: T&C Brand-Deeplinks + Quota Repair-Issue / Bundle 1: T&C Brand-Deeplinks + Quota Repair-Issue

- Quota auto-pause polling
- `is_fixable=True` mit handler
- Per-VIN quota tracking

## [1.19.3] - 2026-05-06 🛰️ Scout-Welle 6: 5 Reports, 19 truly new paths silenced / Scout Wave 6: 5 reports, 19 truly new paths silenced

- `charging` endpoint
- `air-conditioning` endpoint
- `readiness` endpoint

## [1.19.2] - 2026-05-05 🔐 Token-Persistence über HACS-Updates (#118 fix) / Token Persistence across HACS Updates (#118 fix)

- Neues Modul
- `CariadBaseClient` Erweiterungen
- Coordinator Wire-Up

## [1.19.1] - 2026-05-04 📊 Pycupra-style API Quota Sensor / Pycupra-style API Quota Sensor

- `base.py:_capture_rate_limit_headers(headers)`
- `models.py`
- `coordinator.py:_enrich`

## [1.19.0] - 2026-05-04 🚀 CUPRA/SEAT FCM Push Foundation (#57 Phase 1 cont.) / CUPRA/SEAT FCM Push Foundation (#57 Phase 1 cont.)

- Neues Push-Module
- Neuer Config-Flow Toggle
- Bilingual Translations

## [1.18.0] - 2026-05-04 🚀 Skoda MQTT Push Foundation (#57 Phase 1) / Skoda MQTT Push Foundation (#57 Phase 1)

- Neues Push-Package
- Neuer Config-Flow Toggle
- Lazy-Import-Strategie

## [1.17.7] - 2026-05-04 🌡️🔧 Skoda outside_temperature + preferred_workshop attrs / Skoda outside_temperature + preferred_workshop attrs

- Kein neuer Sensor, kein neuer Translation-Key, kein neues HACS-Manifest-Field
- `extra_state_attributes` auf bestehendem `service_due_in_days` Sensor
- Kein neuer Sensor, kein neuer Entity-ID

## [1.17.6] - 2026-05-04 🌍 HomeRegion-Helper Scaffolding (evcc port) / HomeRegion Helper Scaffolding (evcc port)

- `custom_components/vag_connect/cariad/_home_region.py`
- `tests/bruno/cariad_bff/22_GET_homeRegion.bru`
- `tests/test_v1176_homeregion.py`

## [1.17.5] - 2026-05-04 🛰️ Scout-Welle 5: 4 Community-Reports an einem Tag + 4 Verification-Pings / Scout Wave 5: 4 community reports in one day + 4 verification pings

- #118 eismarkt
- #51 Audi RS e-tron GT 404
- #48 all-actions-fail

## [1.17.4] - 2026-05-03 🎯 Bruno-CI Stufe 2 COMPLETE — Full Strict Coverage / Bruno-CI Stufe 2 Complete (Skoda + CARIAD-BFF strict)

- Skoda: +17 neue .bru files
- CARIAD-BFF: +11 neue .bru files
- `{path_suffix}` placeholder expansion

## [1.17.3] - 2026-05-03 🤖🛡️📚 Bruno-CI Stufe 2 + Lovelace Cards + 3 Research Docs

- Drift-check: 35/35 match, 0 drift, strict mode AKTIV in CI
- flex-table-card
- vehicle-info-card

## [1.17.2] - 2026-05-03 🧹🤖 Stale-Cleanup + Bruno-CI Stufe 1 / Stale-Reference Cleanup + Bruno-CI Foundation

- `tests/bruno/seat_cupra/`
- `tests/bruno/{skoda,cariad_bff}/`
- `scripts/check_bruno_url_drift.py`

## [1.17.1] - 2026-05-02 🚙🌬️🔥 Bruno Quick-Wins Bundle / Bruno Quick-Wins (Window heating fix + Ventilation + Aux Heating + Battery Care + Navigation #36 + 2× A/B-fallback)

- `Timwun/Cupra-WeConnect-Bruno-Collection`
- `upstream/pycupra`
- 🐛 Bug-Fixes / Bug-Fixes

## [1.17.0] - 2026-05-02 🛡️📚 Operational Hardening Bundle / Operational Hardening (Quota-protective polling + FAQ + HACS Checklist + Year-rollover Tests + Deactivated Notification)

- `vag-ha-integration-research.md`
- 🔄 Geändert / Changed
- ✨ Neu / Added

## [1.16.1] - 2026-05-02 🐛 SEAT/CUPRA Climate Fix + #122 Scout-Paths / SEAT/CUPRA Climate 404 Fix + SEAT scout-path registration

- #53 Climate
- #53 Phase 3 Phantom-Button
- 🐛 Bug-Fixes / Bug-Fixes

## [1.16.0] - 2026-05-02 ⏰📍 Cross-Brand UX + Skoda Charging Profiles / Cross-Brand UX + Skoda Charging Profiles (HA time platform #26 + #25/#31 read-only via charging-profiles + OTA Probe planning)

- Neue `entity.time` Sektion
- Skoda Vehicle-Information Bundle
- Charging Profile Write-Side

## [1.15.0] - 2026-05-02 🛰️🔋 Skoda Modernization Bundle / Skoda Modernization (Charging History #35 + OTA + 8 cap-ids + capability tolerance + anonymize hardening)

- #75 Skoda Kodiaq Mk2 403
- #26 Klima-Timer / Departure-Timer datetime UI
- #25 Standort-spezifischer Ladeziel + #31 Ladeprofile pro Standort

## [1.14.0] - 2026-05-02 🚗 Audi Feature Pack Bundle / Audi Feature Pack (Trip Stats + Engine Start ICE + PPC Climate Body) + Skoda Scout-Pfade #116

- #35 Ladehistorie LTS
- #51 RS e-tron GT Facelift
- PPE Auto-Detection

## [1.13.0] - 2026-05-02 🛡️ Production Hardening Bundle / Production Hardening (Capability Phase 3 + Read-only Phase 2 + Diagnostics-Polish + Process)

- ✨ Neu / Added
- 🔄 Geändert / Changed
- 🌐 Übersetzungen / Translations

## [1.12.3] - 2026-05-01 🛰️ Scout-Pfade #111 + #113 + #114 / Scout paths bundled with wildcard strategy

- fuelStatus
- vehicleHealthInspection
- departureProfiles

## [1.12.2] - 2026-05-01 🌟🛰️ Erstes Community-Scout-Report (Skoda #107 von tritanium73) / First community Scout report

- 4 unexpected findings sind bereits durch v1
- 2 Error-Reporter Findings sind transiente 502 Bad Gateway → v1

## [1.12.1] - 2026-04-30 🛰️📚 Scout-Pfade #105/#106 + Gerhard's Born Fixture + FAQ #47 / Scout paths + Born fixture + Subscription FAQ

- Wildcards
- Komplett anonymisiert
- Zweck

## [1.12.0] - 2026-04-30 🔋💡⚡🧯🔒 5-in-1 Feature-Sprint / Five features in one MINOR

- 📋 Doc-only — User-Data Handling + `[Inference]` Marker

## [1.11.1] - 2026-04-30 🐛💨 Golf 7 GTE Fuel-Range Fix (#96) + Optimistic UI (3B-Part-3)

- 🔧 **Drivetrain-Detection** liest jetzt aus 4 Quellen (statt 2): zusätzlich measurements
- 🔧 **carType="hybrid" flag** explizit erkannt → setzt has_battery=True UND
- 🔧 **Total range fallback** aus measurements

## [1.11.0] - 2026-04-30 🔆🔧 Issue #91 Closure: Light-Status, Service-Days, Max-Charge-Current

- Lichter-Status war nirgends zugänglich
- Service-Tage konnte man nur als Datum sehen, nicht als "noch X Tage"
- Max-Ladestrom war als Field da aber kein Sensor

## [1.10.2] - 2026-04-30 🚗 CUPRA Born 2026 Firmware-Shapes (Gerhard's #53 Live-Test)

- 🔋 battery
- 🔒 status
- 🚪 status

## [1.10.1] - 2026-04-30 🛡️ Defensive Coding Phase 2 (Issue #58)

- Skoda Parser
- VW EU/Audi Parser
- SEAT/CUPRA Parser

## [1.10.0] - 2026-04-29 🔋⛽ PHEV-Range-Triple + Audi-Diesel-Range (Issue #94)

- 🔋 **electric_range_km** ("Elektrische Reichweite")
- ⛽ **combustion_range_km** ("Kraftstoff-Reichweite")
- 🛣️ **total_range_km** ("Gesamtreichweite")

## [1.9.1] - 2026-04-29 🔧 Audi/VW Lock + Wake Hotfix + Capability-Filter Phase 2

- Audi S6 (Diesel)
- VW Golf 7 GTE

## [1.9.0] - 2026-04-29 🔬 Vehicle Data Scout + Error Reporter

- 📚 Documentation refresh

## [1.8.12] - 2026-04-29 🌐 Multi-Brand Connection-State (MVP-Move)

- 🟢🟡⚫ **connection_state Sensor** funktioniert jetzt nicht nur für Škoda (v1
- 🏆 **Erste VAG-Integration mit centralisiertem Multi-Brand Connection-State

## [1.8.11] - 2026-04-29 🚙 Škoda Online/Standby/Offline + Live-API-Erkenntnisse

- 🟢🟡⚫ **Verbindungsstatus-Sensor**
- 🚪 **Schiebedach, Kofferraum, Motorhaube** funktionieren jetzt
- 🔒 **Bessere Türschloss-Erkennung** auf neueren Modellen (Kodiaq 2026+) durch

## [1.8.10] - 2026-04-29 🩹 Hotfix


## [1.8.9] - 2026-04-29 🚗 CUPRA Born Bug-Fix-Bündel

- 🚪 **Türen, Fenster, Kofferraum, Motorhaube, Schiebedach** werden jetzt
- 🚗 **"Auto fährt gerade"** funktioniert wieder
- ⚡ **Lade-Power und Restzeit** werden korrekt angezeigt

## [1.8.8] - 2026-04-29 🔓 Lock / Climate / Charging für Audi 2025+ und Passat B9

- 🔒 **Lock/Unlock** funktioniert auf neuen Audi-Modellen (war vorher 404)
- ❄️ **Klimatisierung Start/Stop** funktioniert auf neuen Modellen
- ⚡ **Laden Start/Stop** funktioniert auf neuen Modellen

## [1.8.7] - 2026-04-29 🛡️ Stabilität — kein "Unavailable"-Flackern mehr

- 🌐 **Wochenend-Backend-Probleme** werden jetzt ausgesessen
- 🔁 **Einzelne fehlgeschlagene Polls** lösen kein "Unavailable" mehr aus
- 🐢 **Gateway-Timeouts (504)** werden automatisch nochmal versucht statt zu

## [1.8.6] - 2026-04-29 📚 Docs-Truthfulness Hotfix

- 🏆 **Multi-Brand-Successor-Position:** README sagt jetzt klar dass VAG Connect
- 🏷️ **Dynamic CI-Badge:** Statt hardcoded Test-Counts (die schnell veraltet
- 📝 **Aktuelle Stand & ehrliche Limits Section** in allen 8 README-Sprachen

## [1.8.5] - 2026-04-27

- `CommandProfile` enum
- Coordinator helpers `get_command_profile(vin)` /
  `set_command_profile(vin, profile)`
- VWEUClient `_post_command(vin, suffix)` helper

## [1.8.4] - 2026-04-27

- SEAT/CUPRA `command_lock` and `command_unlock` now use the SecToken
  flow
- `coordinator.async_lock` now requires S-PIN for SEAT/CUPRA brands
- `SpinError`

## [1.8.3] - 2026-04-27

- `vehicle_supports_capability(vin, capability_id)`
- `button.py` reads from the helper
- No effect on Audi / VW EU / Škoda / Porsche / VW NA

## [1.8.2] - 2026-04-27

- `CommandFailureReason` enum + `classify_command_failure()` helper
- Three-state feature model
- Capabilities cache

## [1.8.1] - 2026-04-27

- VIN masking in logs and diagnostics
- Diagnostics now redact more PII fields by default
- Issue templates

## [1.8.0] - 2026-04-26

- Per-VIN availability
- S-PIN fail-fast
- Fake writable entities removed

## [1.7.0] - 2026-04-25

- Škoda: Complete API rewrite
- Car-friendly entity names
- Škoda parking v3

## [1.6.1] - 2026-04-25

- Škoda
- GraphQL
- Bootstrap

## [1.6.0] - 2026-04-24

- SEAT/CUPRA
- SEAT/CUPRA vehicle renders
- SEAT/CUPRA window heating

## [1.5.13] - 2026-04-24

- Škoda camelCase tokens

## [1.5.12] - 2026-04-23

- Entity translations
- Škoda token exchange
- SEAT token exchange

## [1.5.11] - 2026-04-23

- Brand-specific token endpoints
- Token refresh

## [1.5.10] - 2026-04-22

- CUPRA/SEAT user_id
- Lock platform
- Nightly polling reduction

## [1.5.9] - 2026-04-22

- CUPRA auth
- CUPRA/SEAT scope
- SEAT/CUPRA/Škoda token endpoint

## [1.5.8] - 2026-04-22

- SEAT/CUPRA/Škoda auth
- English entity labels
- CUPRA/SEAT OAuth scope

## [1.5.6] - 2026-04-18

- Sicherheits- und Performance-Audit
- Sicherheit
- Performance

## [1.5.5] - 2026-04-18

- Behoben — IDK Auth-Logs erschienen als "Fehler" in HA

## [1.5.4] - 2026-04-13

- Bereinigung — README, Issues, letzter toter Sensor
- `connection_state` Sensor entfernt
- README komplett neu geschrieben

## [1.5.3] - 2026-04-13

- Audi Images
- GDC Filter
- Behoben — Log-Auswertung

## [1.5.3] - 2026-04-13

- Behoben — Log-Rauschen
- AZS Token / Audi Images funktioniert ✅

## [1.5.2] - 2026-04-13

- Behoben — Kompletter Entity-Audit: API-Realität vs. Erwartungen
- Entfernte Dead Entities
- API-Wahrheit: Was CARIAD BFF wirklich liefert

## [1.5.2] - 2026-04-13

- Behoben — Binary Sensor Audit
- 5 tote Binary-Sensor-Entities entfernt

## [1.5.1] - 2026-04-13

- Behoben — Sensor-Audit
- 11 tote Sensoren entfernt
- Abfahrtstimer-Sensoren repariert

## [1.5.1] - 2026-04-13

- Behoben — Sensor-Qualität
- 11 tote Sensoren entfernt
- Abfahrtstimer Zeitanzeige repariert

## [1.5.0] - 2026-04-13

- v1.5.0 — Bugs & Stabilität
- Bug #32 — `is_charging` stuck nach Ladeende
- #34 — Warnleuchten als binary_sensor

## [1.4.1] - 2026-04-13

- Docs

## [1.4.1] - 2026-04-13

- Docs

## [1.4.0] - 2026-04-13

- manifest.json
- strings.json + 8 Übersetzungen
- hacs.json

## [1.3.8] - 2026-04-13

- Behoben
- CI mypy `no-any-return` Fehler

## [1.3.7] - 2026-04-13

- Behoben
- Nicht-unterstützte Fahrzeugplattformen überspringen — Issue #709

## [1.3.6] - 2026-04-13

- Behoben
- Audi Render Images — AZS Token Exchange
- `graphql.py` — `graphql_url` Override-Parameter

## [1.3.5] - 2026-04-13

- Behoben
- GraphQL 403 Audi — korrekter Portal-Client
- VW EU GraphQL 404 — korrigierte Domain

## [1.3.4] - 2026-04-13

- Behoben
- Sensor-Crash: Inspektionsdatum + Ölwechseldatum
- Kilometerangaben ohne Dezimalstellen — Issue #17

## [1.3.3] - 2026-04-13

- Auf der Geräteseite
- Auf jeder Entity
- Behoben + Hinzugefügt

## [1.3.2] - 2026-04-12

- Hinzugefügt
- Render Images für alle EU-Marken
- Code-Refactoring

## [1.3.1] - 2026-04-12

- Geändert
- 7 Image-Entities statt 1 pro Fahrzeug
- Lokales Caching

## [1.3.0] - 2026-04-12

- Hinzugefügt
- Vehicle Render Images — Issue #15

## [1.2.0] - 2026-04-12

- Hinzugefügt
- Lademodus-Steuerung — Issue #891
- Mindest-Akkustand (Min SoC) — Issue #889

## [1.1.1] - 2026-04-12

- Behoben
- #917 — Ladegeschwindigkeit/Ladeleistung zeigt "unavailable" wenn nicht geladen wird
- #927 — Options-Flow triggert kompletten Integration-Neustart

## [1.1.0] - 2026-04-12

- Hinzugefügt
- Universelle Felder für alle Marken — `coordinator._enrich()`
- Code-Qualität

## [1.0.0] - 2026-04-12

- Erstes stabiles Release

## [0.14.25] - 2026-04-12

- Hinzugefügt
- Neue Marken: Porsche + VW North America
- Config Flow

## [0.14.23] - 2026-04-12

- Alle Entities standardmäßig sichtbar
- Geändert

## [0.14.22] - 2026-04-12

- Bug: `window_heating` mapped auf `command_start_climate`
- 7 neue Entities
- `iot_class`: `cloud_polling` → `cloud_push`

## [0.14.10] - 2026-04-12

- VW EU Scope
- BRAND_AUDI client_id
- Research-Ergebnis

## [0.14.9] - 2026-04-12

- Fixed — basierend auf volkswagencarnet (MIT) Analyse

## [0.14.8] - 2026-04-12

- Auth0 400: login_url direkt verwenden
- Kombinierter POST
- Fallback

## [0.14.7] - 2026-04-12

- Auth0 UL v2: 400 Bad Request behoben

## [0.14.6] - 2026-04-12

- Auth0 Universal Login v2
- 2FA-Unterstützung

## [0.14.5] - 2026-04-12

- Auth0 Universal Login

## [0.14.4] - 2026-04-12

- Abfahrtstimer schreiben

## [0.14.3] - 2026-04-12

- IDK Login: robusteres CSRF-Parsing
- Detailliertes Schritt-Logging

## [0.14.2] - 2026-04-12

- Audi/VW Login
- AZS Token Exchange (Audi)
- VW US/CA aus Brand-Liste entfernt

## [0.14.1] - 2026-04-12

- Semver retroaktiv korrigiert: 0
- iot_class: cloud_push → cloud_polling (wir pollen, kein Push-Protokoll)
- CI: CarConnectivity-Dependencies entfernt, mypy + coverage-threshold hinzugefügt

## [0.11.0] - 2026-04-12

- Platinum Quality Scale

## [0.10.1] - 2026-04-12

- CarConnectivity und alle 5 Brand-Connectors aus manifest
- manifest

## [0.10.0] - 2026-04-12

- cariad/
- cariad/auth/idk
- cariad/api/vw_eu

## [0.9.0] - 2026-04-12

- Lizenz: MIT → **Apache 2
- Copyright: Prash Balan (@its-me-prash) in allen Dateien
- strict-typing Platinum-Regel: 0 mypy-Fehler (--disallow-untyped-defs

## [0.8.2] - 2026-04-12

- Automatische Erkennung des requests-Versionskonflikts (HA 2026
- repairs
- Stabiler Betrieb auch bei requests-Konflikt

## [0.8.1] - 2026-04-11

- Python 3

## [0.8.0] - 2026-04-11

- diagnostics
- Stale-Device-Bereinigung bei Fahrzeugwechsel
- Gold Quality Scale vollständig: runtime_data, reauth, reconfigure,

## [0.7.0] - 2026-04-09

- Abfahrtstimer (Timer 1–3): set_departure_timer Service
- number
- Gold Quality Scale: runtime_data, reauth-Flow, reconfigure-Flow

## [0.6.0] - 2026-04-08

- EntityCategory für diagnostische Sensoren
- Sensoren: Ladeleistung kW, Ladegeschwindigkeit km/h, Akkutemperatur, Ölstand

## [0.5.0] - 2026-04-06

- Abfahrtstimer-Sensor (read-only): zeigt nächsten aktiven Timer

## [0.4.6] - 2026-04-05

- Coordinator-Crash wenn GPS-Daten None zurückgeben

## [0.4.5] - 2026-04-04

- Fensterheizung: is_on nach manuellem Toggle korrekt

## [0.4.4] - 2026-04-04

- SEAT/CUPRA: fehlende user_id → 404 auf Garage-Endpoint

## [0.4.3] - 2026-04-03

- Klimatisierungstemperatur: Kelvin→Celsius für alle Marken

## [0.4.2] - 2026-04-03

- Ladeende-ETA: negativer Wert wenn Fahrzeug voll geladen

## [0.4.1] - 2026-04-02

- Config Flow reconfigure verlor Scan-Intervall nach Speichern

## [0.4.0] - 2026-04-01

- Standort-Adresse als Sensor (OpenStreetMap Geocoding)
- Fahrtrichtung (Heading) als Sensor
- Ladesäulen-Informationen: Name, Betreiber, Adresse, Leistung

## [0.3.4] - 2026-03-31

- Škoda: Mehrfache Initialisierung des MQTT-Listeners

## [0.3.3] - 2026-03-30

- Audi: AZS-Token-Refresh nach 1h zuverlässig

## [0.3.2] - 2026-03-29

- VW EU: doors_individual leer wenn overallStatus == SAFE

## [0.3.1] - 2026-03-28

- CUPRA: command_wake 405 bei manchen Modellen ignoriert

## [0.3.0] - 2026-03-27

- Individuelle Tür-Sensoren (Fahrertür, Beifahrertür, Fond, Kofferraum)
- Fensterstatus-Sensoren

## [0.2.2] - 2026-03-25

- Mehrfache Fehlerlog-Einträge bei dauerhafter Nichterreichbarkeit

## [0.2.1] - 2026-03-24

- GPS: None statt 0

## [0.2.0] - 2026-03-23

- Ladeleistung-Sensor kW
- Ladegeschwindigkeit-Sensor km/h
- Ladeende-ETA-Sensor

## [0.1.1] - 2026-03-21

- HA 2024

## [0.1.0] - 2026-03-20

- Erste Version: VW EU, Audi, Škoda, SEAT, CUPRA
- Sensoren: Akkustand, Reichweite, Kilometerstand, GPS, Türen, Fenster, Klimatisierung,
- Services: lock, unlock, start/stop Klimatisierung, flash, wake, refresh

