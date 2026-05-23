# Frequently Asked Questions / Häufig gestellte Fragen

> Audience: end-users + first-time installers. Maintainer-facing
> notes are in `docs/CHANGELOG_TECHNICAL.md` and `docs/ROADMAP.md`.

## 🔋 What actually wakes the car?

**Short answer:** **nothing about normal polling** wakes the car.

Polling reads the **manufacturer cloud** (`emea.bff.cariad.digital`,
`mysmob.api.connect.skoda-auto.cz`,
`ola.prod.code.seat.cloud.vwgroup.com`, etc.). The car pushes data to
the cloud on its own schedule:

- on every lock / unlock event
- on every charge state change (started, stopped, target reached)
- on every climatisation event
- on parking (when ignition turns off)
- when the driver presses the "send to cloud now" button in the
  vehicle's infotainment system

VW Group Connect polls the cloud at your configured interval (default
**10 minutes** in v1.17.0+) and surfaces whatever the cloud already
knows. **No 12V battery cost.**

### What DOES wake the car

These actions trigger an actual radio link to the vehicle:

| Action | Wakes vehicle? | 12V cost |
|---|---|---|
| `service: vag_connect.wake_vehicle` | YES — explicit wake | High |
| `button.{auto}_wake` press | YES | High |
| Lock / unlock command | YES | Medium |
| Climate start/stop | YES | Medium |
| Charging start/stop | YES | Medium |
| Engine start (Audi ICE) | YES | Medium |
| Flash-and-honk | YES | Low |
| Force-refresh button (`button.{auto}_refresh`) | NO — just polls cloud | Zero |
| `service: vag_connect.refresh_cloud_cache` | NO — just polls cloud | Zero |
| Standard polling | NO | Zero |

### Wake protection

VW Group Connect protects your 12V battery automatically (since v1.12.0):

- **3 wakes per day per vehicle** soft cap (UTC midnight reset)
- **5-minute wake cooldown** per vehicle (since v1.13.0)
- Surfaced as `sensor.{auto}_wake_count_today`
- Both raise `wake_budget_exhausted` / `wake_cooldown_active`
  ServiceValidationError when triggered

If you genuinely want to disable polling (Read-only Mode), see the
"Read-only mode" section below.

---

## 🔒 Privacy settings — which entities degrade?

The MyCupra / MySeat / MyŠkoda / WeConnect ID / MyAudi in-car privacy
menu has 3 levels (sometimes 4 depending on firmware). Each level
restricts what the cloud is allowed to know about your vehicle.

| Setting | Entities affected | Symptom |
|---|---|---|
| **Share my position** (most permissive — **recommended for full integration use**) | none | all sensors populate normally |
| **Use my position** (mid-level) | `device_tracker.*_position`, `sensor.*_parking_address`, `sensor.*_parking_city` | location goes "unknown" or stops updating |
| **Don't share** (most restrictive) | `device_tracker.*`, `sensor.*_parking_*`, charging timestamps degrade, "online" binary sensor may flap | most location-derived entities fail |

### To change the setting

1. Open the **official manufacturer app** (MyCupra, MyŠkoda,
   WeConnect ID, MyAudi, etc.)
2. Navigate to **your vehicle → Settings → Privacy**
3. Set to **"Share my position"** (or your preferred level)
4. Save
5. The change can take **up to 5 minutes** to propagate to the cloud
6. In Home Assistant: trigger `service: vag_connect.refresh_cloud_cache`
   (or wait for the next poll)

### If sensors are STILL `unknown` 10+ minutes after changing

- Check that the vehicle has cell coverage and is awake
- Verify in the app that the privacy setting actually saved
- Open a GitHub issue with anonymized diagnostics
  (HA Settings → Devices & Services → VW Group Connect → ⋮ → Diagnostics)

---

## 📊 What is the daily API request quota?

The VAG manufacturer clouds limit the number of API calls **per day
across the official mobile app + any integration that polls** to
roughly **1,500 calls/day** for SEAT/CUPRA, similar for the other
brands. The exact limit varies per backend and is not officially
documented.

### Why does VW Group Connect default to 10-minute polling (v1.17.0+)?

| Poll interval | Polls/day | % of 1,500 quota | Headroom for app |
|---|---|---|---|
| 3 min (old min) | 480 | 32% | low |
| 5 min (old default) | 288 | 19% | medium |
| **10 min (v1.17.0+ default)** | **144** | **10%** | **high** |
| 15 min | 96 | 6% | very high |

When the official mobile app is also active, **3-minute polling
exhausts the quota by mid-day**. After exhaustion, no fresh data
until the cloud resets at ~02:00 local.

### Recommended intervals

- **Single user, no app use during day:** 5 minutes minimum
- **Standard household:** 10 minutes (v1.17.0 default)
- **Heavy app users + multiple integrations:** 15 minutes

---

## 🔁 How do I update credentials after a manufacturer password change?

VW Group Connect supports HA's standard re-authentication flow since
v1.8.x. **Since v1.19.2 IDK tokens are persisted via HA's Store
helper** — HACS-Updates und HA-Restarts zwingen dich nicht mehr
zu Re-Auth, solange das hinterlegte Password noch gültig ist.

1. After your password change, the integration's next poll fails
   with a "Reauthenticate" notice
2. **Settings → Devices & Services → VW Group Connect → Reconfigure**
3. Enter the new password
4. The entry updates in place

### Why not just remove and re-add?

Removing and re-adding would **lose long-term statistics history**
(charging energy, distance, etc.) because HA's `recorder` /
`statistics` tables key on the entity's `unique_id`. Reconfigure
preserves the entity_id, so dashboards and statistics are kept.

### What if the Reconfigure button is missing?

That means the integration didn't detect the auth failure as an
auth issue (it might have classified it as a network error). Try
this sequence:

1. **Reload** the integration via the ⋮ menu — forces a fresh login attempt
2. If that surfaces a "Reauthenticate" prompt, follow it
3. If still no prompt, **only then** remove and re-add

---

## 🆔 Entity-ID stability across versions

VW Group Connect follows this policy (since v1.13.0):

- **Bug fixes that change a sensor's value** but keep the same
  meaning → keep the entity_id, ship as a PATCH or MINOR.
- **Schema-changing fixes that change what a sensor REPRESENTS** →
  ship a NEW entity_id with the updated meaning, deprecate the old
  one for 2 minor versions, then remove.

This protects your dashboards and long-term statistics from breaking
when we ship semantic improvements.

### When entity_ids DO change

- A vehicle is removed and re-added (HA assigns new entity_ids if
  the old ones were already taken by something else)
- A platform is renamed in HA core (rare, but happens — e.g. the
  switch_as_sensor pattern transition)
- We explicitly call out the change in the CHANGELOG

---

## 🛡️ Read-only Mode

If you want VW Group Connect to give you vehicle telemetry **without any
risk of accidental commands** (e.g. for guest dashboards, automations
that should never actuate), enable Read-only Mode:

1. **Settings → Devices & Services → VW Group Connect → Configure**
2. Toggle **"Read-only Mode"** on
3. Reload the integration

In Read-only Mode (since v1.12.0 / v1.13.0):

- **No** lock / unlock / climate / charging / window-heating switches
- **No** charge-current Number entities
- **No** flash / wake buttons
- **Refresh button stays** (it only polls the cloud, sends no command)
- Service-side enforcement (since v1.13.0) — even direct service calls
  (e.g. from automations) raise `read_only_mode_active`

Sensors and binary_sensors stay enabled — full read-only telemetry.

---

## 🚗 My vehicle disappeared after a release — why?

Two possible reasons (since v1.17.0 we surface a notification for
each):

1. **Vehicle removed from your account** — sold, ownership
   transferred, or the manufacturer deactivated it. VW Group Connect
   detects this on the next poll, removes the device + entities,
   and fires a persistent_notification with the reason.
   - Long-term-statistics data **is preserved** in HA's recorder
     even after device removal.
   - If you re-acquire the vehicle later, re-add it and the
     statistics history will rejoin under the same entity_ids
     automatically.

2. **Subscription expired** — Connect-Plus / WeConnect Plus / Audi
   connect Plus has different sub-tiers; some features depend on
   the highest tier. Phase 3 capability filtering (since v1.13.0)
   hides entities that the backend reports as unsupported. After
   a subscription change, give the next poll cycle 10 minutes,
   then trigger a refresh.

---

## 📞 How do I report a bug?

1. **Settings → Devices & Services → VW Group Connect → ⋮ → Diagnose herunterladen**
2. The downloaded JSON has VINs masked, GPS rounded, tokens redacted,
   user_ids SHA-256-hashed (since v1.15.0). Safe to post publicly.
3. Open an issue at
   [github.com/its-me-prash/vwgroup-connect-ha/issues/new](https://github.com/its-me-prash/vwgroup-connect-ha/issues/new)
4. Pick the right template — `Bug Report`, `Vehicle Data Scout`
   (for new field discoveries), or `Error Reporter` (for ring-buffer
   error dumps that the integration auto-collects)

---

## 🌍 Supported brands + regions

| Brand | Region | Backend | Status |
|---|---|---|---|
| Volkswagen EU | Europe | CARIAD-BFF (`emea.bff.cariad.digital`) | ✅ Production |
| Audi | Europe | CARIAD-BFF (inherits VW EU) | ✅ Production |
| Škoda | Europe | mysmob (`mysmob.api.connect.skoda-auto.cz`) | ✅ Production |
| SEAT | Europe | OLA (`ola.prod.code.seat.cloud.vwgroup.com`) | ✅ Production |
| CUPRA | Europe | OLA (same as SEAT) | ✅ Production |
| Volkswagen US/CA | North America | UUID-based | ⚠️ Limited (no PPE) |
| Porsche | Worldwide | Auth0 + PPA backend | ⚠️ Limited |

### Not yet supported

- **VW China (2026+)** — CEA/XPeng platform, undocumented
- **Lamborghini / Bentley / Bugatti** — no verified public API
- **Ford Explorer Electric** — use [marq24/ha-fordpass](https://github.com/marq24/ha-fordpass)

---

## 🚀 Push Updates (v1.18.0+ Foundation, Phase 2 pending)

Since v1.18.0 (Skoda MQTT) and v1.19.0 (CUPRA/SEAT FCM), VW Group Connect
ships **opt-in Push-Foundation** für Real-Time-Updates ohne 12V-
Wake-Cycle:

- **Skoda** (mysmob MQTT broker `mqtt.messagehub.de:8883`)
- **CUPRA / SEAT** (Firebase Cloud Messaging via OLA)

### Aktueller Status

**Phase 1 = Foundation komplett** (v1.18.0 + v1.19.0):
- `cariad/push/skoda_mqtt.py` — `SkodaPushManager` mit Lifecycle + Reconnect-Backoff
- `cariad/push/cupra_seat_fcm.py` — `CupraSeatPushManager` analog
- `OptionsFlow` toggles `enable_push_mqtt` (Skoda) + `enable_push_fcm` (CUPRA/SEAT) — beide default OFF
- Lazy-Import: `aiomqtt` + `firebase-messaging` werden nur beim Aktivieren benötigt (kein Bloat für Polling-User)

**Phase 2 = Live-Activation pending Community-Tester**:
- Wir brauchen einen User mit aktiver Skoda Connect Subscription für FCM-Project-ID + TOTP-Verifikation
- Genauso für MyCupra/MySeat: aktive Subscription + FCM credential check
- Ping uns auf #57 wenn du dich als Tester anbieten willst

### Wenn ich den Toggle JETZT aktiviere?

Aktuell läuft die Foundation-Stub: Manager startet, schläft im Connect-Loop, aber sendet keine echten MQTT/FCM-Subscriptions. Polling läuft normal weiter — kein Daten-Verlust. Foundation-only ist sicher zu aktivieren, schadet nichts, hilft aber auch noch nicht real-time.

---

## 📊 API Quota Sensor (v1.19.1+) + Quota Repair-Issue (v1.19.4+)

Seit v1.19.1 zeigt VW Group Connect den **API Quota** des Tages an:

- `sensor.<vehicle>_requests_remaining_today` (Diagnostic) — verbleibende Anfragen heute
- Wenn dein Backend X-RateLimit-Remaining Header sendet (alle modernen VAG-APIs tun das), siehst du wieviel Quota du noch hast

**v1.19.4+ Repair-Issue** — bei kritischem Stand bekommst du eine HA-Repair-Notification:

- Warning bei < 100 verbleibenden Anfragen
- Critical bei < 25 verbleibenden Anfragen
- Auto-clears bei Erholung (z.B. nach Mitternacht)

Tipp: Wenn du mehrere VAG-Integrationen parallel betreibst (volkswagencarnet, audi, etc.) zählen die alle gegen das gleiche Quota.

---

## 📜 Token-Persistence (v1.19.2+)

Vor v1.19.2: bei jedem HACS-Update wurden IDK-Tokens neu geholt → bei transient Auth-Issues triggerte das Reauth-Prompt → User musste Password neu eingeben.

Ab v1.19.2: IDK-Tokens werden via HA's `Store` Helper in `.storage/vag_connect_tokens_<entry_id>` persistiert. HACS-Update + HA-Restart laden die Tokens automatisch — kein Reauth-Prompt mehr.

**Was du tun musst beim Wechsel von v1.19.1 (oder älter) auf v1.19.2+**:
1. HACS-Update + HA-Restart
2. Einmalig Reauth-Prompt durchklicken (da noch keine Tokens persistiert)
3. Ab dann nie wieder

---

## 🔧 T&C / Terms-Repair-Issue (v1.19.4+)

Wenn das VAG-Backend "terms-and-conditions" oder "terms_of_use" body sendet (= neue AGB akzeptieren nötig), wird ein HA-Repair-Issue erstellt. **Seit v1.19.4** zeigt der "Learn more"-Button direkt zum richtigen Brand-Account-Portal:

- Skoda → `skodaid.vwgroup.io/landing-page`
- VW EU → `vwid.vwgroup.io/account`
- Audi → `my.audi.com`
- SEAT/CUPRA → `seat-cupra.cloud.vwgroup.com`
- Porsche → `my.porsche.com`
- VW NA → `vw.com/myvw`

Klick → Login → AGB akzeptieren → HA-Restart → Issue verschwindet automatisch.

---

## 🚗 Skoda Vehicle-Info Extras (v1.20.0+ Phase A)

Skoda-User bekommen seit v1.20.0 zwei neue Diagnostic-Sensoren + DeviceInfo-Enrichment:

- `sensor.<vehicle>_license_plate` — Kennzeichen aus Skoda mysmob widget endpoint (myskoda PR #557)
- `sensor.<vehicle>_equipment_count` — Anzahl der Ausstattungsfeatures (z.B. "Sitzheizung", "Anhängerkupplung")
  - Volle Liste als `extra_state_attributes` (klick auf Sensor → Attribute)
- DeviceInfo zeigt jetzt model-name + model-year + software-version aus `/vehicle-information/{vin}` wenn vom Garage-Call leer

Static data wird 24h gecached — kein Quota-Burn pro Poll.

---

## 🎨 Dashboards — "Add to Dashboard" doesn't show my view

Most-common HA UI stumble — you're not doing anything wrong, the
picker just hides certain dashboards. Three usual causes:

1. **Dashboard is in YAML-mode** (most common): the `Add to
   Dashboard` flow only writes to **Storage-mode** dashboards.
   Check *Settings → Dashboards* — column "Mode" shows YAML vs
   Storage. YAML dashboards need manual `entities: - sensor.foo`
   edits in the YAML file.
2. **View doesn't exist yet**: HA only lists already-created
   views. Create an empty view first (Dashboard → pencil → "+
   Add View" → save), then retry.
3. **HA 2024+ "Sections" layout view**: occasionally rejects the
   quick-add workflow. Workaround: go into the view, edit-mode,
   "+ Add Card" → pick the entity manually.

Quickest workaround if nothing helps: navigate to the view, edit
mode, "+ Add Card" → "Entities" → filter `vag_connect` or your
VIN-last-6 to find your sensors.

Full guide + dedicated VW Group Connect Lovelace card (BETA — in
testing, currently still has a Mercedes-style background that's
being redesigned): [`docs/dashboards.md`](dashboards.md).

---

## 📚 Where to find more details

- **Dashboard troubleshooting + Lovelace cards:** `docs/dashboards.md`
- **Per-brand technical detail:** `docs/CHANGELOG_TECHNICAL.md`
- **Future roadmap + planned releases:** `docs/ROADMAP.md`
- **Pre-implementation research:** `docs/research/`
- **Brand Captains community:** `BRAND_CAPTAINS.md`
- **GitHub Issues:** https://github.com/its-me-prash/vwgroup-connect-ha/issues
