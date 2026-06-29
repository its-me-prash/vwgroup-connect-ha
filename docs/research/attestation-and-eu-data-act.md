# Why some commands/reads are blocked by VW — device attestation & the EU Data Act endpoint

_Maintainer research note. No secrets. Captures why certain VW-side walls cannot be worked around from an open-source client, and where the official EU Data Act data source is heading._

## 1. Device attestation (Play Integrity) — a permanent, off-device wall

Some VW Group online-service backends now require a **Google-signed, hardware-rooted device-attestation token** (Firebase App Check / Play Integrity) on top of a normal OAuth bearer. The official apps mint this from a hardened, Play-signed build on a genuine device.

An open-source / headless client **cannot reproduce such a token**:

- Play Integrity and hardware key attestation are rooted in a **hardware-backed keystore** and a **Google signing** step that only happens on a genuine, uncompromised device with Play Services. (See A. Mayrhofer et al., _Comparing key attestation and the Play Integrity API_, 2024.)
- There is no server-side or library way to forge one; known "bypasses" require a real (usually rooted/patched) device and are fragile.

**Consequence for this integration:**

- **CUPRA / SEAT remote commands** (OLA `*.con-veh` backend) — gated by attestation. Blocked server-side; not fixable here. Tracked in #464 (and surfaced for users in #526). Vehicle **data** still flows read-only via the EU Data Act portal.
- **VW US/CA per-vehicle data reads** — if the 403 carries an attestation marker, it is the same wall (#503). The S-PIN–derived `carnetVehicleToken` path (v2.15.5) is the only non-attestation route we can try; if reads still 403 with it, the honest answer is "VW-gated, not reproducible off-device."

When a 403 carries an attestation marker, the integration classifies it and surfaces a clear repair notice rather than retrying forever or implying a user error.

## 2. The official EU Data Act endpoint — `cardata.apps.emea.vwapps.io`

The read path currently depends on a **third-party reverse-proxy facade** (`eu-data-act.drivesomethinggreater.com`) — live and functional, but **unofficial** (a single-source dependency).

The **official, first-party** VW EU Data Act ("cardata") vehicle-data-sharing endpoint is:

```
https://cardata.apps.emea.vwapps.io/        (+ cardata-sandbox.apps.emea.vwapps.io)
```

It is baked into the **We Connect EU app** (`com.volkswagen.weconnect` 3.63.2) config, but **not yet wired** (present as a base-URL constant only, no consuming code) and, as of 2026-06-26, **not yet reachable**: DNS returns **NXDOMAIN** for both prod and sandbox (the parent zone `emea.vwapps.io` exists on AWS Route 53, but the `cardata` record has not been provisioned). It is pre-launch.

**Action for maintainers:** periodically re-check `cardata.apps.emea.vwapps.io` (DNS/HTTP). When it goes live, evaluate migrating the read path to it as the official first-party source, removing the third-party-proxy dependency. The per-vehicle data-consent grant page (`vwid.vwgroup.io/account/vehicle-consent`) is already live and would gate any such pull.
