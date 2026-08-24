# DataPlug / plug&play cloud reader — handoff

**Status:** Audi (acpp) **live-validated** 2026-08-24 (real enrolled A5 B8). VW (wcg) **tester-gated**
(endpoints mapped, login not wired). New source; foundation committed on
`feat/plugandplay-cloud-reader`. Integration (config-flow / factory / coordinator / sensors) is
left for the main OBD-solution work — see **Integration TODO** below.

## Why this exists

The plug&play apps — `de.audi.connectplugandplay` (Audi connect plug&play) and
`de.volkswagen.vwconnect` (VW We Connect Go) — pair a **TEXA OBD dongle** with OLD cars that have
**no built-in connectivity**. Those cars are invisible to the modern CARIAD BFF and to the
EU-Data-Act portal, so **this is the only cloud read path** for a dongle-equipped Touareg / e-up! /
pre-connectivity A4/A5/Golf, etc. It is attestation-free and hands out a **durable refresh token**.

The dongle uploads a **snapshot** on sync (odometer, 12V battery, fuel, service, tyres, warnings).
Live engine PIDs (speed/rpm/coolant/boost/…) are **not** in the cloud — they stay dongle-local and
are read over Bluetooth (that is the separate `dataplug-reconnect` local reader project).

## Audi (acpp) — validated flow

| step | value |
|---|---|
| client_id | `ec6198b1-b31e-41ec-9a69-95d42d6497ed@apps_vw-dilab_com` |
| authorize | `https://identity.vwgroup.io/oidc/v1/authorize` (authorization_code + PKCE) |
| scope | `openid email profile` — **not** `… https://audiid.vwgroup.io/account` (→ `consent_required`) |
| redirect | `acpp://de.audi.connectplugandplay/oauth2redirect/identitykit` |
| token | `https://prod.acpp.cariad.digital/token` — plain OAuth, **no x-qmauth**, returns refresh_token |
| data base | `https://prod.acpp.cariad.digital` |

Reuse of the existing auth stack (no new login code needed for Audi):

```python
IDKAuth(session, BRAND_AUDI_ACPP, token_url_override="https://prod.acpp.cariad.digital/token")
```

`BRAND_AUDI_ACPP.name == "audi_acpp"` (NOT `"audi"`) so `IDKAuth._exchange_code()` takes the
plain-OAuth branch instead of the CARIAD BFF x-qmauth branch, and honours the `token_url_override`.

### Data endpoints (Bearer <acpp access token>)

Only VINs **enrolled in the account** exist — an unknown VIN returns
`404 {"message":"Vehicle with vin ... does not exist"}` (Prash's S6 was not enrolled → 404).

| path | method | returns (observed on the B8) |
|---|---|---|
| `vehicle/{vin}` | GET 200 | `{"vehicle":{"id","vin","carPlatform":"KWP2000"},"odometer":369290.0,"batteryVoltage":11.76,"tankFuelAmount":3.0,"registrationDate","mainCheck","vehicleSpecificDealer":{...}}` |
| `vehicle/{vin}/tires` | GET 200 | `[{"id","mileage","manufacturer","changeDate","tireActive",...}]` |
| `vehicle/{vin}/warning-lights` | GET 200 | `{"warningLights":[]}` |
| `vehicle/{vin}/last-parking-position` | GET 200 | `{"gpsLocation":{"latitude","longitude"}}` (0/0 with this dongle) |
| `vehicle/{vin}/driverlogs` | GET 200 | paginated logbook |
| `vehicle/{vin}/appointment` | GET 200 | `[]` |
| `vehicle/{vin}/vehicle_app_services` | GET 200 | notification settings |
| `user/fuellog/{vin}` | GET 200 | paginated fuel log |
| `user/achievements/v2` | GET 200 | gamification points |
| `vehicle/{vin}/details` | 405 (POST) · `vehicle/{vin}/carport` | 500 without a `lang` param (query `?lang=de` did **not** satisfy it — likely a header/param name mismatch, TODO) |
| `vehicle/{vin}/{status,state,measurements,statistics,...}` | 404 | **live PIDs are NOT stored** — dongle-local only |
| `user/cars/{vin}/…` | 404 | wrong family (early dead end); the live family is `vehicle/{vin}/…` |

### Token does NOT open the BFF

The acpp access token (`aud` = the acpp client itself, `scp: profile email openid`) is **not
BFF-whitelisted**: `emea.bff.cariad.digital/vehicle/v1/*` → `403 "clientId in the token claim is
either unknown or not whitelisted"`. Confirms the BFF client-whitelist gate; this is not a wall
bypass, it is its own silo. (Consistent with `vag_connect_apk_sweep` client sweep.)

## VW (wcg) — mapped, tester-gated

| | value |
|---|---|
| client_id | `ac42b0fa-3b11-48a0-a941-43a399e7ef84@apps_vw-dilab_com` |
| IDP | `identity.legacy.vwgroup.io` — **legacy `signin-service`, not Auth0** |
| data base | `https://prod.wcg.cariad.digital` |
| data paths | `vehicles/{vin}/{measurements,warnings,config,series/measurements}` (note `vehicles` **plural**) |
| garage list | `api/v1/users/{user_id}/vehicles` |

**Blocker:** `IDKAuth.authenticate()` targets Auth0 Universal Login; against the legacy
signin-service it returns `HTTP 400` at the identifier POST
(`identity.legacy.vwgroup.io/signin-service/v1/{client_id}/login/identifier`). Implement the
signin-service legs (identifier → authenticate → code) — `auth/_vweu_twoway_login.py` already has
this pattern — then point `token_url_override` at the legacy token endpoint. Not live-testable here
(no VW dongle car available); gate behind a tester like the other unvalidated paths.

## Integration TODO (for the main OBD-solution work)

1. **config-flow**: add a "DataPlug / plug&play (OBD dongle)" source option (email+password; Audi
   ready, VW behind a tester flag).
2. **factory.py**: register `PlugAndPlayCloudClient` (acpp) — it already mirrors the
   `(session, brand, email, password, spin="")` constructor and exposes `authenticate()` +
   `get_status(vin)`.
3. **VehicleData mapping**: `get_status()` fills `odometer_km`, `warning_active/count`,
   `model_year`, `has_combustion`. acpp fields with **no current column** — 12V `batteryVoltage`,
   `tankFuelAmount` (litres), `registrationDate`, `mainCheck`, per-tyre records — come back via
   `get_raw_snapshot()`. Decide: add columns (e.g. `battery_12v_voltage`, `fuel_litres`,
   `service_due_date`) or surface them as extra state attributes.
4. **Poll cadence**: snapshot only updates when the dongle syncs (i.e. after a drive); a slow poll
   is fine. No live PIDs here — pair with the local BT reader for real-time data.
5. **wcg**: implement the legacy signin-service login + wire `WCGCloudClient`, tester-gated.

## Reference

Working, credential-driven probes used to validate this live are in the session scratchpad
(`acpp_login.py`, `acpp_read.sh`, `acpp_bff.sh`) — not committed (they read `~/.claude/private`
creds and cache a token in `~/.claude/private/acpp_token.json`). The committed code
(`api/plugandplay.py`) is the clean-room equivalent that reuses `IDKAuth`.
