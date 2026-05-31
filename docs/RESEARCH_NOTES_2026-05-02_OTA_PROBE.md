# Cross-Brand OTA Software-Version Endpoint Probe

> **Status:** Pending Live-Test (not blocked, just needs cooperative testers)
> **Origin:** v1.15.0 Skoda OTA shipped (myskoda PR #541) — open question whether
> CARIAD-BFF (Audi+VW EU) and OLA (SEAT/CUPRA) expose an equivalent endpoint.
> **Created:** 2026-05-02 in v1.16.0 session.

## Context

`v1.15.0` shipped the Skoda software-version + OTA-update binary_sensor backed
by mysmob's `GET /v1/vehicle-information/{vin}/software-version/update-status`
endpoint (myskoda PR #541, ships in Skoda app v8.10.0+).

Initial research (`docs/RESEARCH_NOTES_2026-05-02.md` Cross-Brand OTA Probe)
confirmed:

- **CARIAD-BFF (Audi + VW EU)** — no equivalent endpoint found in
  `arjenvrh/upstream`, `upstream/volkswagencarnet`,
  `upstream/cc-vw`. No open PRs / issues
  asking for it. **Best guess:** not yet shipped on the EU BFF, or gated to
  apps the FOSS community hasn't reverse-engineered yet.

- **OLA (SEAT/CUPRA)** — `upstream/pycupra` clean. The OLA path style mirrors
  CARIAD-BFF (`{baseurl}/v1/vehicles/{vin}/{capability}/...`) so the endpoint
  *might* exist server-side, but nobody has confirmed it.

## Probe Plan

When a cooperative tester is available with one of these brands + an active
subscription, run these `curl` probes against the brand's authenticated
session (token from a fresh setup; expires in ~1h). **Always** anonymise VIN
and tokens before posting results.

### CARIAD-BFF probe (Audi + VW EU)

```bash
TOKEN="<bearer from cariad/auth/idk.py session>"
VIN="<your VIN>"

# Direct attempt (mirrors mysmob path with CARIAD-BFF prefix)
curl -i \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  "https://emea.bff.cariad.digital/vehicle/v1/vehicles/$VIN/software-version/update-status"

# Plausible alternative paths
curl -i ... ".../vehicle/v1/vehicles/$VIN/software-version"
curl -i ... ".../vehicle/v1/vehicles/$VIN/firmware-update-status"
curl -i ... ".../vehicle/v1/vehicles/$VIN/ota-status"

# Capabilities probe — does the backend list a software-version cap?
curl -i ... ".../vehicle/v1/vehicles/$VIN/capabilities" | grep -iE "software|ota|update"
```

### OLA probe (SEAT/CUPRA)

```bash
TOKEN="<bearer from cariad/auth/idk.py with OLA scope set>"
VIN="<your VIN>"

curl -i ... \
  "https://ola.prod.code.seat.cloud.vwgroup.com/v1/vehicles/$VIN/software-version/update-status"

# OLA has its own capabilities endpoint — probe for the new id
curl -i ... \
  "https://ola.prod.code.seat.cloud.vwgroup.com/v1/vehicles/$VIN/capabilities" \
  | grep -iE "software|ota|update"
```

## Expected outcomes

| Status | What it means | Next step |
|---|---|---|
| `200 OK` + JSON with `status`/`currentSoftwareVersion` | Endpoint exists. Adopt the same parser as `cariad/api/skoda.py::get_status` software-version block. | Extend `vw_eu.py` + `seat_cupra.py` clients with `get_software_update_status`. Drop `_DATA_PRESENT_REQUIRED` gating for `software_version` + `ota_update_available` on those brands. |
| `404 Not Found` | Endpoint doesn't exist (yet). | Document in this file; check capabilities response for hints. |
| `403 Forbidden` | Endpoint exists but account lacks the capability. | Cross-check against capabilities endpoint to find the cap-id. Add to `CAPABILITY_MAP[brand]`. |
| `401 Unauthorized` | Token expired during probe. | Re-fetch token. |

## Adoption plan post-probe

If CARIAD-BFF or OLA returns `200`:

1. Add the new method to the brand's client class (`get_software_update_status(vin)`).
2. Hook into `get_status` `gather()` like Skoda does (8th item in the tuple).
3. Re-use the existing parsing block (it's already shape-tolerant).
4. Remove the `_DATA_PRESENT_REQUIRED` gating for the brand to allow the entities to be created.
5. Add the cap-id to `CAPABILITY_MAP[brand]["command_software_update"]`.

Estimated implementation: **2 hours of work + tests** once the probe confirms.

## Live-Tester Asks

When v1.16.0 ships, post a Live-Test request in the Brand Captains channel:

- Audi 2024+ owner with Audi connect Plus — needed for CARIAD-BFF probe
- VW ID.4 / ID.5 / ID.7 owner with WeConnect — alternative CARIAD-BFF probe
- CUPRA Born / Tavascan owner with CUPRA Connect — needed for OLA probe
- SEAT Mii electric / Tarraco e-Hybrid owner — alternative OLA probe

The probe is **read-only** and **safe** — `GET` request to a status endpoint
that already requires a valid auth token. No vehicle-side effects.

## References

- mysmob model: https://github.com/skodaconnect/myskoda/blob/main/myskoda/models/software_status.py
- Skoda implementation: `cariad/api/skoda.py::get_status` (post-v1.15.0)
- Original research: `docs/RESEARCH_NOTES_2026-05-02.md` § Cross-Brand OTA Probe
