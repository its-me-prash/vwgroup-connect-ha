# Škoda official public vehicle API — grounded reference

> Source of truth: the live OpenAPI spec at `https://public.api.connect.skoda-auto.cz/v3/api-docs` (re-fetched 2026-11-01: **83120 bytes, 12 routes**, openapi 3.1.0 — it was 66993 bytes and 9 routes when this file was written), cross-checked against the evcc write-up (https://docs.evcc.io/de/blog/2026/08/27/skoda-vehicle-api/) and the MyŠkoda APK. This file is the complete surface, generated from the spec; the **Changes since 9 routes** section below records what grew.

## What this is (and is NOT)

- **Official, first-party** end-customer API on Škoda's own zone `public.api.connect.skoda-auto.cz` (base `/api/v1`).
- **NOT** the pan-VW EU Data Act endpoint (`cardata.apps.emea.vwapps.io`, still pre-launch) — a separate, brand-native gateway.
- **NOT** our current channel: we read Škoda via the unofficial reverse-engineered `mysmob.api.connect.skoda-auto.cz` (51 routes). This official API is a smaller (**12 routes** as of 2026-11-01, 9 when this file was written) but durable, attestation-free alternative.
- **Availability (updated 2026-11-01):** keys ARE mintable now. MyŠkoda **8.18.0** (versionCode 261012003, pulled 2026-11-01) carries the flow: `cz.myskoda.api.bff_public_api_keys.v2.ktor.data.PublicApiKeysApi` with `createPublicApiKey`, `deletePublicApiKey`, `getPublicApiKeys` and a validity check, over `POST /api/v2/public-api-keys` and `/api/v2/public-api-keys/{id}` on **mysmob** — the same route our `mint_api_key` uses, so the 8.16-derived implementation is still correct in 8.18. User path: **Settings → Smart Home**, per vehicle, with a delete confirmation. Two distinct DTOs (`CreatedApiKeyDto` vs `ApiKeyDto`) corroborate that the secret is returned only at creation. The build also carries a `PUBLIC_API_KEY_MANAGEMENT` flag, which looks like a server-side gate — the menu may not be visible for every account.
- **The minting dependency is the thing to plan around:** the key can only be created THROUGH mysmob. When the old API stops answering, anyone without a key has no way left to obtain one, because the public API cannot issue its own credentials.

## Auth

- **`X-API-Key: <key>` header** (OpenAPI `apiKeyAuth`, type apiKey in header). NOT OAuth/Bearer.
- The key is created/managed in the MyŠkoda app (v8.16+, key-management screen / QR), **bound to the vehicles selected at creation time**, and **expires** (`X-API-Key-Expires-At` response header).
- Privileged commands (auxiliary heating) additionally require the vehicle **S-PIN** in the JSON body (`spin`).
- Requests target a vehicle by **VIN in the path**. There is **no list-vehicles endpoint** — the VIN must be known/entered (the key is vehicle-bound).

## Rate limit (HARD constraint)

- **20 requests / hour / key** (spec/evcc note it is 'not final'). Response headers: `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`.
- 429 problem type `api-key-rate-limit-exceeded`; expired key → problem type `api-key-expired`.
- **Implication:** far too tight for a 15-min feed. A conservative poll (e.g. every 5–10 min = 6–12/h) leaves little headroom for commands. Any channel we build must budget against `RateLimit-Remaining` and back off — this is a low-frequency official channel, not a replacement for mysmob.

## State values + gotchas (⚠️ not formal enums — read the field descriptions)

The state fields are plain `string` with **no `enum` type** in the schema; the
real values live only in each field's `description`. Guessing them wrong
silently mis-reports state, so they are pinned here (and in the client tests):

- **`charging.status.state`**: `CONNECT_CABLE` · `CHARGING` · `CONSERVING` · `READY_FOR_CHARGING` · `DISCHARGING` · `CHARGING_INTERRUPTED`. (We treat CHARGING + CONSERVING as "charging".)
- **`charging.status.chargeType`**: `AC` · `DC` · `OFF`.
- **`airConditioning.state`**: `OFF` · `COOLING` · `HEATING` · `HEATING_AUXILIARY` · `VENTILATION` · `COMPLETED` · `UNKNOWN`. **There is no `ON`.** (Active only while COOLING/HEATING/HEATING_AUXILIARY/VENTILATION.)
- **`status.overall.doorsLocked` / `locked`**: `YES` · `NO` · `OPENED` · `UNKNOWN`. **`YES` = locked** (not `"LOCKED"`).
- **`status.overall.doors` / `windows`, `detail.trunk` / `bonnet` / `sunroof`**: `OPEN` · `CLOSED` · `UNKNOWN` (sunroof also `UNSUPPORTED`).
- **`windowHeating.front` / `rear`**: `ON` · `OFF` · `UNKNOWN` · `UNSUPPORTED`.
- **`fuelStatus.primaryEngineRange.engineType`**: `ELECTRIC` · `GASOLINE` · `DIESEL` · `CNG` · `LPG` · `UNKNOWN`. `fuelStatus.carType`: `HYBRID` · `GASOLINE` · … . New values may appear — clients must tolerate unknowns.
- **`chargingSettings.maxChargeCurrentAc`** is a string (`REDUCED`/`MAXIMUM`); the numeric amps live in `maxChargeCurrentAcAmpere`.

## License / token facts (Škoda announcement, 2026-08-28)

- **Up to 5 access tokens per VIN**, minted in the app (v8.16+). Free.
- **Data depends on the account's active Škoda Connect services.** Notably: **without a Remote Access license the parking position (GPS) is not returned** — so the GPS read is a bonus where licensed, not universal. Our parse already treats every field as optional.
- Škoda is building its own dedicated HA integration (HA 2026.10) with the community; our use of this API is as an opt-in **resilience/failover** source inside a multi-brand integration, which is complementary rather than competing.

## APK signing baseline (first recorded 2026-11-01)

`apkget` ends with "verify the signing cert against a known-good copy before
trusting the APK" — and when that was attempted there was **no known-good copy**:
a search for any recorded Škoda signing-cert hash across the repo returned zero.
So this is the baseline, recorded from the first pull, for the next one to be
compared against. A changed hash on a later pull is not proof of tampering, but
it is the point at which to stop and find out why.

| Field | Value |
|---|---|
| Package | `cz.skodaauto.myskoda` |
| versionName / versionCode | `8.18.0` / `261012003` |
| Pulled | 2026-11-01, via `C:/tools/apkget.sh` (Google Play) |
| APK SHA-256 | `06cedc1de59f1ee33d71f0967f2f81b7b528e9769d4ae7e9cd8bfdfe6c886f56` |
| Signing cert SHA-256 | `960c025bd51d1ba21ed72df18a38a121191e185f8705ce5f4ccb8b21116df176` |
| Signatures / DEX files | 1 / 4 (`dex
039`, 35 MB total) |

The APK itself was deleted after the strings were read: 130 MB, reproducible
from the same command, and a downloaded binary is not something to keep lying
around. The cert hash is the part worth keeping.

## Changes since 9 routes (re-fetched 2026-11-01)

Three **write** routes appeared, all `PUT`, all with a declared body:

| Route | Body schema | Fields |
|---|---|---|
| `PUT /api/v1/vehicles/{vin}/charging/limit` | `ChargingLimit` | `targetStateOfChargeInPercent` — integer, **required** |
| `PUT /api/v1/vehicles/{vin}/charging/mode` | `ChargeMode` | `chargeMode` — string, required, **no enum declared** |
| `PUT /api/v1/vehicles/{vin}/charging-profiles/{id}` | `ChargingProfile` | `id`, `name`, `settings`, `preferredChargingTimes`, `timers` — all required |

And `ChargingStatus` gained two read fields: **`plugConnectionState`** and
**`plugLockState`**, both `string` with **no enum declared**.

### What was implemented, and what deliberately was not

**Implemented:** the two read fields, in `cariad/api/skoda_official.py`. They are
passed through raw — no mapping is invented, because the spec declares no allowed
values — and the coordinator's `normalize_enum_states` folds the token onto the
sensor's declared options, so an unrecognised value becomes no value rather than
a wrong one. `drop_charge_sentinel` runs first, for the same reason it guards
`chargeType`. Pinned by `tests/test_1286_official_api_grew_the_plug_fields.py`.

**Not implemented: the three write routes.** Not an oversight — there is no
caller. `official_only` mode changes **reads**; commands are dispatched through
`_skoda_official_command_fallback` against an explicit six-command allowlist
(`_SKODA_OFFICIAL_COMMANDS`), and the comment there states the entry condition:
those six have the *same signature* as their mysmob counterparts, vin and nothing
else. A target-SoC write takes a value, so adding it means widening that
allowlist — and that list is a deliberate safety boundary, not a backlog. The
fallback fires only on 401/403/404, the failures that *prove* the car never saw
the command; anything else may have executed, and sending a non-idempotent
command twice on a second channel is worse than reporting a failure.

So wiring these three is a design decision about the command fallback, not a
parser addition. Recorded here so the next reader finds the routes and the reason
together instead of only the gap.

### A note on sources

The APK does **not** carry `plugConnectionState`, `plugLockState` or
`charging/limit` — checked in 8.18.0. That is consistent rather than
contradictory: the app talks to mysmob, not to the public API. For this surface
the spec is the authority and the app is not; the app is the authority for the
*key-minting* route, which is why both were checked.

## Endpoints

### `POST /api/v1/vehicles/{vin}/charging/stop` — stopCharging

Stop charging for a given vehicle.

- param `vin` in path (required)

### `POST /api/v1/vehicles/{vin}/charging/start` — startCharging

Start charging for a given vehicle.

- param `vin` in path (required)

### `POST /api/v1/vehicles/{vin}/auxiliary-heating/stop` — stopAuxiliaryHeating

Stop auxiliary heating inside the desired vehicle.

- param `vin` in path (required)

### `POST /api/v1/vehicles/{vin}/auxiliary-heating/start` — startAuxiliaryHeating

Start auxiliary heating inside the desired vehicle.

- request body (application/json): `StartAuxiliaryHeatingConfiguration`
- param `vin` in path (required)

### `POST /api/v1/vehicles/{vin}/air-conditioning/stop` — stopAirConditioning

Stops an air-conditioning process inside a vehicle.

- param `vin` in path (required)

### `POST /api/v1/vehicles/{vin}/air-conditioning/start` — startAirConditioning

Starts an air-conditioning process inside a vehicle to reach the target temperature.

- request body (application/json): `StartAirConditioningConfiguration`
- param `vin` in path (required)

### `POST /api/v1/vehicles/{vin}/active-ventilation/stop` — stopActiveVentilation

Stop active ventilation inside the desired vehicle.

- param `vin` in path (required)

### `POST /api/v1/vehicles/{vin}/active-ventilation/start` — startActiveVentilation

Start active ventilation inside the desired vehicle.

- param `vin` in path (required)

### `GET /api/v1/vehicles/{vin}` — getVehicle

Returns the vehicle and its current state.

- param `vin` in path (required)
- param `include` in query

## Schemas (complete)

### ActiveVentilation

- `state`: string  _(**required**)_ — State of the active ventilation. Possible values are:   * OFF   * PREHEATING   * VENTILATION   * UNKNOWN - system cannot recognise correct value   * UNSUPPORTED - the vehicle does not report this state 
- `durationInSeconds`: integer  _(fmt=int32)_ — Duration in seconds the active ventilation runs for when started.
- `carCapturedTimestamp`: string  _(fmt=date-time)_ — Timestamp when the data was last captured and sent by the vehicle. Standard ISO 8601 format.

### AirConditioning

- `state`: string  _(**required**)_ — State of the air conditioning. Possible values are:   * OFF   * COOLING   * HEATING   * HEATING_AUXILIARY - the auxiliary heater is assisting with heating the cabin   * VENTILATION   * COMPLETED   * UNKNOWN - system cannot recognise correct value   * UNSUPPORTED - the vehicle does not report this state 
- `targetTemperature`: TargetTemperature
- `estimatedReachOfTargetTemperatureAt`: string  _(fmt=date-time)_ — Timestamp when the cabin is expected to reach the target temperature. Standard ISO 8601 format.
- `airConditioningWithoutExternalPower`: boolean — Setting indicating whether the air conditioning may run without the vehicle being connected to an external power source.
- `airConditioningAtUnlock`: boolean — Setting indicating whether the air conditioning starts automatically when the vehicle is unlocked.
- `windowHeating`: WindowHeating
- `carCapturedTimestamp`: string  _(fmt=date-time)_ — Timestamp when the data was last captured and sent by the vehicle. Standard ISO 8601 format.

### AuxiliaryHeating

- `state`: string  _(**required**)_ — State of the auxiliary heating. Possible values are:   * OFF   * PREHEATING   * HEATING_AUXILIARY   * VENTILATION   * UNKNOWN - system cannot recognise correct value   * UNSUPPORTED - the vehicle does not report this state 
- `startMode`: string — Mode the auxiliary heating starts in. Possible values are:   * HEATING   * VENTILATION 
- `durationInSeconds`: integer  _(fmt=int32)_ — Duration in seconds the auxiliary heating runs for when started.
- `targetTemperature`: TargetTemperature
- `estimatedReachOfTargetTemperatureAt`: string  _(fmt=date-time)_ — Timestamp when the cabin is expected to reach the target temperature. Standard ISO 8601 format.
- `carCapturedTimestamp`: string  _(fmt=date-time)_ — Timestamp when the data was last captured and sent by the vehicle. Standard ISO 8601 format.

### BatteryStatus

- `remainingCruisingRangeInMeters`: integer  _(fmt=int32)_ — Remaining cruising range with HV battery power in meters.
- `stateOfChargeInPercent`: integer  _(fmt=int32)_ — State of charge in percent.

### Charging

- `tings`: Charging
- `isVehicleInSavedLocation`: boolean  _(**required**)_ — Indicates whether the vehicle is in a saved location (a specific location with defined charging settings).
- `status`: ChargingStatus
- `settings`: ChargingSettings
- `carCapturedTimestamp`: string  _(fmt=date-time)_ — Timestamp when the data was last captured and sent by the vehicle. Standard ISO 8601 format.

### ChargingProfile

- `tings`: ChargingProfile
- `id`: integer  _(fmt=int64, **required**)_ — Identifier of this profile.
- `name`: string  _(**required**)_ — The name of the charging profile as specified by the user.
- `settings`: ChargingProfileSettings  _(**required**)_
- `preferredChargingTimes`: array<ChargingTime>  _(**required**)_
- `timers`: array<Timer>  _(**required**)_

### ChargingProfileSettings

- `maxChargingCurrent`: string — Value that should be used when start charging. Possible values are:   * REDUCED   * MAXIMUM 
- `minBatteryStateOfCharge`: MinBatteryStateOfCharge
- `targetStateOfChargeInPercent`: integer  _(fmt=int32)_ — Target charging level in percent set by user.
- `autoUnlockPlugWhenCharged`: string — Value for auto unlock plug, when charging is finished. Possible values are:   * PERMANENT   * OFF 

### ChargingProfiles

- `profiles`: array<ChargingProfile>  _(**required**)_
- `currentVehiclePositionProfile`: CurrentVehiclePositionProfile
- `carCapturedTimestamp`: string  _(fmt=date-time)_ — Timestamp when the data was last captured and sent by the vehicle. Standard ISO 8601 format.

### ChargingSettings

- `targetStateOfChargeInPercent`: integer  _(fmt=int32)_ — Target state of charge in percent.
- `batteryCareModeTargetValueInPercent`: integer  _(fmt=int32)_ — Recommended target state of charge in percent when battery care mode is enabled.
- `preferredChargeMode`: string — Preferred charging mode. Possible values are:   * MANUAL   * TIMER   * TIMER_CHARGING_WITH_CLIMATISATION   * PREFERRED_CHARGING_TIMES   * ONLY_OWN_CURRENT   * IMMEDIATE_DISCHARGING   * HOME_STORAGE_CHARGING New values may be added over time, so clients must tolerate values they do not recognize. 
- `availableChargeModes`: array<string> — List of available charging modes. Possible values are:   * MANUAL   * TIMER   * TIMER_CHARGING_WITH_CLIMATISATION   * PREFERRED_CHARGING_TIMES   * ONLY_OWN_CURRENT   * IMMEDIATE_DISCHARGING   * HOME_STORAGE_CHARGING New values may be added over time, so clients must tolerate values they do not recognize. 
- `chargingCareMode`: string — Indicates whether is charging care mode activated. Possible values are:   * ACTIVATED   * DEACTIVATED New values may be added over time, so clients must tolerate values they do not recognize. 
- `autoUnlockPlugWhenCharged`: string — Value for auto unlock plug, when charging is finished. Possible values are:   * PERMANENT   * OFF New values may be added over time, so clients must tolerate values they do not recognize. 
- `maxChargeCurrentAc`: string — Value that should be used when start charging. Possible values are:   * REDUCED   * MAXIMUM New values may be added over time, so clients must tolerate values they do not recognize. 
- `maxChargeCurrentAcAmpere`: integer  _(fmt=int32)_ — Maximum charging current limit in ampere. Can acquire values 5, 10, 13 or 32.

### ChargingStatus

- `chargingRateInKilometersPerHour`: number  _(fmt=double)_ — Rate of charging in kilometers per hour.
- `chargePowerInKw`: number  _(fmt=double)_ — Charge power in kilowatts.
- `remainingTimeToFullyChargedInMinutes`: integer  _(fmt=int32)_ — Remaining charging time to complete in minutes.
- `fullyChargedAt`: string  _(fmt=date-time)_ — Timestamp when the vehicle is expected to be fully charged
- `state`: string — Charging state. Possible values are:   * CONNECT_CABLE   * CHARGING   * CONSERVING   * READY_FOR_CHARGING   * DISCHARGING   * CHARGING_INTERRUPTED 
- `chargeType`: string — Type of charging. Possible values are:   * AC   * DC   * OFF New values may be added over time, so clients must tolerate values they do not recognize. 
- `battery`: BatteryStatus

### ChargingTime

- `id`: integer  _(fmt=int64, **required**)_ — Identifier of this charging time.
- `enabled`: boolean  _(**required**)_ — Indicates if this preferred charging time is enabled.
- `startTime`: string  _(**required**)_ — Specifies when the preferred charging time should start. Local time in vehicle in ISO 8601 format (HH:mm).
- `endTime`: string  _(**required**)_ — Specifies when the preferred charging time should stop. Local time in vehicle in ISO 8601 format (HH:mm).

### CurrentVehiclePositionProfile

- `id`: integer  _(fmt=int64, **required**)_ — Identifier of profile.
- `name`: string  _(**required**)_ — The name of the charging profile as specified by the user.
- `targetStateOfChargeInPercent`: integer  _(fmt=int32)_ — Target charging level in percent set by user for this profile.
- `nextChargingTime`: string — Specifies next charging time which will be triggered at current profile. Time is in vehicle local in ISO 8601 format (HH:mm).

### EngineRange

- `engineType`: string — Vehicle's engine type. Possible values are `ELECTRIC`, `GASOLINE`, `DIESEL`, `CNG`, `LPG` and `UNKNOWN`. New values may be added over time, so clients must tolerate values they do not recognize. 
- `currentSoCInPercent`: number — Vehicle's State of Charge in percent.
- `currentFuelLevelInPercent`: number — Vehicle's fuel level in percent.
- `remainingRangeInKm`: number — Vehicle's remaining range in kilometers.

### FuelStatus

- `carType`: string — Vehicle's type. Possible values are `HYBRID`, `GASOLINE`, `DIESEL`, `CNG`, `LPG` and `UNKNOWN`. New values may be added over time, so clients must tolerate values they do not recognize. 
- `adBlueRange`: number — Vehicle's adBlue range in kilometers. Available only for vehicles with diesel engine.
- `totalRangeInKm`: number — Vehicle's total range in kilometers.
- `primaryEngineRange`: EngineRange
- `secondaryEngineRange`: EngineRange
- `carCapturedTimestamp`: string  _(fmt=date-time)_ — Timestamp when the data was last captured and sent by the vehicle. Standard ISO 8601 format.

### MinBatteryStateOfCharge

- `enabled`: boolean — True if this feature is enabled.
- `minimumBatteryStateOfChargeInPercent`: integer  _(fmt=int32)_ — If battery drop below this value, then start immediate charging.

### Odometer

- `mileageInKm`: integer  _(fmt=int64, **required**)_ — Current mileage of the vehicle in kilometers.
- `carCapturedTimestamp`: string  _(fmt=date-time)_ — Timestamp when the data was last captured and sent by the vehicle. Standard ISO 8601 format.

### OverallVehicleStatusDto

- `doorsLocked`: string  _(**required**)_ — Overall doors and trunk lock state. Possible values are:   * YES - all supported doors AND trunk are LOCKED+CLOSED.   * NO - at least one supported door OR trunk is UNLOCKED but CLOSED.   * OPENED - at least one supported door OR bonnet is OPEN.   * TRUNK_OPENED - trunk is OPEN but all supported doors AND trunk are CLOSED.   * UNKNOWN - system cannot recognise correct value. 
- `locked`: string  _(**required**)_ — Possible values are:   * YES - at least one door is supported AND all supported doors and trunk are LOCKED+CLOSED.   * NO - any supported door is UNLOCKED/OPEN and no door is UNKNOWN.   * UNKNOWN - system cannot recognise correct value. 
- `doors`: string  _(**required**)_ — Possible values are:   * OPEN - any supported door is OPEN.   * CLOSED - at least one door is supported AND all supported doors are CLOSED.   * UNKNOWN - system cannot recognise correct value. 
- `windows`: string  _(**required**)_ — Aggregated over the side windows; the sunroof is excluded and reported separately in `detail`. Possible values are:   * OPEN - any supported side window is OPEN.   * CLOSED - at least one window is supported AND all supported windows are CLOSED.   * UNKNOWN - system cannot recognise correct value.   * UNSUPPORTED - vehicle does not have all electric windows. 
- `lights`: string  _(**required**)_ — Possible values are:   * ON - at least one supported light is ON.   * OFF - all supported lights are OFF.   * UNKNOWN - system cannot recognise correct value. 
- `reliableLockStatus`: string — Provides information if vehicle is locked. Unlocked value is returned only for MOD4 vehicles. Possible values are:   * LOCKED - all supported doors AND trunk are LOCKED+CLOSED.   * UNLOCKED - any supported door is UNLOCKED/OPEN and no door is UNKNOWN.   * UNKNOWN - system cannot recognise correct value. 

### ParkingPosition

- `state`: string  _(**required**)_ — State of the vehicle from parking position point of view. Possible values are: [IN_MOTION, PARKED]
- `gpsCoordinates`: ParkingPosition_gpsCoordinates
- `formattedAddress`: string — Formatted address of the vehicle parking position: Street, House Number, Zip Code, City, Country. Only present when `state` is `PARKED`, and omitted when the address could not be resolved.

### ParkingPosition_gpsCoordinates

- `latitude`: number  _(fmt=double, **required**)_ — Latitude coordinate.
- `longitude`: number  _(fmt=double, **required**)_ — Longitude coordinate.

### ProblemDetail

- `type`: string — URI reference identifying the problem type. Generic problems that carry no semantics beyond their HTTP status code use `about:blank`. More specific problem types are:   * https://public.api.connect.skoda-auto.cz/problems/api-key-expired - the API key used to authenticate has expired and must be rotated.   * https://public.api.connect.skoda-auto.cz/problems/api-key-not-authorized - the API key is not authorized to execute the operation.   * https://public.api.connect.skoda-auto.cz/problems/operation-not-authorized - the vehicle refused the operation for the user the API key belongs to.   * https://public.api.connect.skoda-auto.cz/problems/operation-not-supported - the vehicle lacks the capability the operation needs.   * https://public.api.connect.skoda-auto.cz/problems/operation-disabled - the capability the operation needs is currently disabled for the vehicle.   * https://public.api.connect.skoda-auto.cz/problems/rate-limit-exceeded - the rate limit for the API key has been exceeded.   * https://public.api.connect.skoda-auto.cz/problems/vehicle-not-accepting-requests - the vehicle declined the operation and it can be retried later. 
- `title`: string — Short, human-readable summary of the problem type.
- `status`: integer  _(fmt=int32)_ — HTTP status code of this occurrence of the problem.
- `detail`: string — Human-readable explanation specific to this occurrence of the problem.
- `instance`: string — URI reference identifying this specific occurrence of the problem.

### StartAirConditioningConfiguration

- `targetTemperature`: TargetTemperature
- `airConditioningWithoutExternalPower`: boolean — Allow or forbid air conditioning when no external power connection is available.

### StartAuxiliaryHeatingConfiguration

- `targetTemperature`: TargetTemperature
- `spin`: string  _(**required**)_ — Security PIN code.
- `durationInSeconds`: integer  _(fmt=int32)_ — Duration in seconds the auxiliary heating runs for.
- `startMode`: string — Start mode of the auxiliary heating device. Possible values are:   * HEATING   * VENTILATION 

### TargetTemperature

- `value`: number  _(fmt=double, **required**)_ — Target temperature value, in the unit given by `unit`.
- `unit`: string  _(**required**)_ — Temperature unit. Possible values are:   * CELSIUS   * FAHRENHEIT 

### Timer

- `id`: integer  _(fmt=int64, **required**)_ — Timer identifier.
- `enabled`: boolean  _(**required**)_ — Is timer enabled.
- `time`: string — Time of start this timer in ISO 8601 format (HH:mm).
- `type`: string  _(**required**)_ — Type of timer. Possible values are:   * ONE_OFF - one time timer   * RECURRING - timer repeating on days you choose 
- `oneOffDay`: string  _(enum: MONDAY | TUESDAY | WEDNESDAY | THURSDAY | FRIDAY | SATURDAY | SUNDAY)_ — Day in week when ONE_OFF timer is required. ONE_OFF timer only.
- `recurringOn`: array<string>

### Vehicle

- `vin`: string — Vehicle Identification Number.
- `name`: string — User-defined vehicle name. When the user has not named the vehicle, the model name (e.g. `Enyaq`) is returned instead.
- `licensePlate`: string
- `renderUrl`: string  _(fmt=uri)_
- `status`: VehicleStatus
- `fuelStatus`: FuelStatus
- `odometer`: Odometer
- `parkingPosition`: ParkingPosition
- `airConditioning`: AirConditioning
- `auxiliaryHeating`: AuxiliaryHeating
- `activeVentilation`: ActiveVentilation
- `charging`: Charging
- `chargingProfiles`: ChargingProfiles

### VehicleError

- `type`: string  _(**required**)_ — Machine-readable error type identifying the part of the response that is affected. Possible values are:   * RENDER_UNAVAILABLE - the vehicle render image URL could not be retrieved; name and licensePlate are unaffected   * VEHICLE_STATUS_UNSUPPORTED - vehicle status (doors, windows, lights, ...) is not supported   * VEHICLE_STATUS_DISABLED - vehicle status (doors, windows, lights, ...) is supported, but currently disabled   * VEHICLE_STATUS_UNAVAILABLE - vehicle status (doors, windows, lights, ...) could not be retrieved   * FUEL_STATUS_UNSUPPORTED - fuel status is not supported (for example a battery-electric vehicle)   * FUEL_STATUS_DISABLED - fuel status is supported, but currently disabled   * FUEL_STATUS_UNAVAILABLE - fuel status could not be retrieved   * ODOMETER_UNSUPPORTED - odometer reading is not supported   * ODOMETER_DISABLED - odometer reading is supported, but currently disabled   * ODOMETER_UNAVAILABLE - odometer reading could not be retrieved   * PARKING_POSITION_UNSUPPORTED - parking position is not supported   * PARKING_POSITION_DISABLED - parking position is supported, but currently disabled   * PARKING_POSITION_UNAVAILABLE - parking position could not be retrieved   * AIR_CONDITIONING_UNSUPPORTED - air conditioning information is not supported   * AIR_CONDITIONING_DISABLED - air conditioning information is supported, but currently disabled   * AIR_CONDITIONING_UNAVAILABLE - air conditioning information could not be retrieved   * AUXILIARY_HEATING_UNSUPPORTED - auxiliary heating information is not supported   * AUXILIARY_HEATING_DISABLED - auxiliary heating information is supported, but currently disabled   * AUXILIARY_HEATING_UNAVAILABLE - auxiliary heating information could not be retrieved   * ACTIVE_VENTILATION_UNSUPPORTED - active ventilation information is not supported   * ACTIVE_VENTILATION_DISABLED - active ventilation information is supported, but currently disabled   * ACTIVE_VENTILATION_UNAVAILABLE - active ventilation information could not be retrieved   * CHARGING_UNSUPPORTED - charging status is not supported   * CHARGING_DISABLED - charging status is supported, but currently disabled   * CHARGING_UNAVAILABLE - charging status could not be retrieved   * CHARGING_PROFILES_UNSUPPORTED - charging profiles are not supported   * CHARGING_PROFILES_DISABLED - charging profiles are supported, but currently disabled   * CHARGING_PROFILES_UNAVAILABLE - charging profiles could not be retrieved 
- `description`: string — Detail information about what and why happened.

### VehicleResponse

- `vehicle`: Vehicle  _(**required**)_
- `errors`: array<VehicleError> — Errors encountered while gathering the vehicle data. The response combines data from multiple sources; if some of them fail, the response contains partial data and the affected parts are omitted, each described by an error in this list. Parts that the vehicle does not support, or that it supports but are currently disabled, are reported the same way.

### VehicleStatus

- `overall`: OverallVehicleStatusDto  _(**required**)_
- `detail`: VehicleStatusDetailDto  _(**required**)_
- `carCapturedTimestamp`: string  _(fmt=date-time)_ — Timestamp when the data was last captured and sent by the vehicle. Standard ISO 8601 format.

### VehicleStatusDetailDto

- `sunroof`: string  _(**required**)_ — Possible value is OPEN, CLOSED, UNKNOWN or UNSUPPORTED.
- `trunk`: string  _(**required**)_ — Possible value is OPEN, CLOSED, UNKNOWN.
- `bonnet`: string  _(**required**)_ — Possible value is OPEN, CLOSED, UNKNOWN.

### WindowHeating

- `enabled`: boolean — True if window heating is enabled for the vehicle. Absent when the vehicle did not report its climatisation settings. 
- `front`: string — State of the front window heating. Possible values are:   * ON   * OFF   * UNKNOWN - system cannot recognise correct value   * UNSUPPORTED - vehicle does not support front window heating 
- `rear`: string — State of the rear window heating. Possible values are:   * ON   * OFF   * UNKNOWN - system cannot recognise correct value   * UNSUPPORTED - vehicle does not support rear window heating 

