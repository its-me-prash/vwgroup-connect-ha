# Community Projects — Comparison + Resource Index

> Auto-curated reference of parallel VAG-brand Home Assistant /
> Python integrations. We track these as **upstream signal sources**
> for our cross-brand work (cf. App Atlas `README.md`).
>
> Last reviewed: 2026-05-27

## 2026-05-27 Cross-project convergence snapshot

7-day sweep confirmed the **multi-source consensus pattern works in
practice**:

- **3 of 3 OLA-aware projects converged on the same 2026-05-20 fix**
  within 4 days (upstream v0.6.3 / upstream v0.50.17 /
  pycupra login bugfix) — all 4 app-fingerprint headers
  (`app-market`, `app-brand`, `app-version=2.15.0`, `origin=app`).
  We shipped the same fix as v2.4.1 with a 4-layer defense-in-depth on
  top (centralized constants + OptionsFlow override + multi-version
  fallback chain + HA Repair-card escalation) — the architectural
  upgrade above just-headers.
- **evcc** additionally adds `User-Agent: OLACupra/2.15.0 (Android 12...)`
  on top of the 4 headers. We have brand-specific iOS-style UAs since
  v2.4.1 (`_ola_headers._OLA_USER_AGENT_BY_BRAND`) — different platform
  signature but functionally equivalent.
- **mitch-dc/volkswagen_we_connect_id**: stays archived (2025-10-29). No
  fork has resurrected it with momentum (max stars on any fork = 5).
- **lendy007/skodaconnect**: archived since 2024-09-10 (not listed below;
  active successor is `skodaconnect/homeassistant-myskoda`).
- **skodaconnect/homeassistant-myskoda** very active this week:
  [PR #1102](https://github.com/skodaconnect/homeassistant-myskoda/pull/1102)
  splits coordinator into fast/slow + MQTT events no longer trigger full
  refresh — directly relevant to our v3.0 push-tech architecture, see
  research deliverable `docs/research/app-atlas/_v3.0-myskoda-architecture.md`.
- **pycupra v0.2.31** added CNG instruments (`cng_level`, `cng_range`)
  for CUPRA TGI variants — silenced pre-emptively in `_unexpected_keys.py`
  cupra:charging set.

---

## OLA backend (SEAT + CUPRA)

Three independent community projects target the SEAT/CUPRA OLA
backend (`ola.prod.code.seat.cloud.vwgroup.com`). All three were
broken by the 2026-05-20 app-header enforcement; all three fixed it
with the same `app-market` + `app-brand` + `app-version` + `origin`
header injection.

| Project | Maintainer | Brand coverage | Architecture |
|---|---|---|---|
| [CarConnectivity-connector-seatcupra](https://github.com/upstream/cc-seatcupra) | upstream | SEAT + CUPRA | Direct OLA, Android-app client_id, full OAuth + token refresh |
| [PyCupra](https://github.com/upstream/pycupra) ([pip](https://pypi.org/project/pycupra/)) | upstream | SEAT + CUPRA | Direct OLA, similar architecture, separate auth-session manager |
| [WeConnect-Cupra-python](https://github.com/upstream/WeConnect-Cupra-python) ([pip](https://pypi.org/project/weconnect-cupra-daern/)) + [HA integration](https://github.com/upstream/cupra_we_connect) | upstream | CUPRA only | **Cariad-BFF + OLA hybrid** — uses browser-IDP client_id (`3c756d46-...@apps_vw-dilab_com`), different signin-service path |

**Why we monitor all three**:
- Three independent maintainers confirming a header value = high confidence
- Earliest-warning when one of them detects API breakage before the others
- Catches per-brand divergence (e.g. CarConnectivity ships SEAT `2.17.0`
  while PyCupra ships `2.13.3` — both work in the wild, real-world example of why multi-source matters)

**Why upstream is architecturally interesting for us long-term**:
- Their CUPRA-via-Cariad-BFF route is a backup architecture we don't have today
- If OLA enforcement ever escalates beyond what the 4-layer defense-in-depth can handle, this path is a viable Plan B
- Phase B follow-up: investigate if we can add Cariad-BFF as a CUPRA fallback parallel to OLA

---

## VW EU + Audi (Cariad-BFF backend)

| Project | Maintainer | Brand coverage | Status |
|---|---|---|---|
| [mitch-dc/volkswagen_we_connect_id](https://github.com/mitch-dc/volkswagen_we_connect_id) | mitch-dc | VW EU | **⚠️ ARCHIVED 2025-10-29** — 254 ⭐, was THE reference; no longer maintained |
| [upstream](https://github.com/arjenvrh/upstream) | arjenvrh | Audi | Maintenance only (dependency bumps since 2026-04) |
| [volkswagencarnet](https://github.com/upstream/volkswagencarnet) | upstream | VW + Audi (legacy MBB) | Maintenance mode |
| [upstream/cc-vw](https://github.com/upstream/cc-vw) | upstream | VW EU | Active, sibling of seatcupra connector |
| [upstream/cc-connector-audi](https://github.com/upstream/cc-connector-audi) | upstream | Audi | Active |

With mitch-dc now archived, **we (vwgroup-connect-ha) and the upstream community** carry the active VW EU + Audi references. See [`_private/research-archive/community-audits/`](../community-audits/) for the 2026-05 community scan.

These are not currently monitored by automation (no Cariad-BFF
header-enforcement detected yet), but we cross-check during major
refactors.

---

## VW NA (con-veh.net backend)

| Project | Maintainer | Notes |
|---|---|---|
| [matpoulin/CarConnectivity-connector-volkswagen-na](https://github.com/matpoulin/CarConnectivity-connector-volkswagen-na) | matpoulin | Only known active VW NA reference — used as primary research source for our v2.3.0 #269 auth fix + v2.4.1 #285 garage-envelope fix |

---

## Škoda (mysmob backend)

| Project | Maintainer | Notes |
|---|---|---|
| [skodaconnect/homeassistant-myskoda](https://github.com/skodaconnect/homeassistant-myskoda) | skodaconnect | Most active Skoda reference |
| [Skode/myskoda](https://github.com/Skode/myskoda) | Skode | Newer alternative |

---

## Porsche (PPA backend)

| Project | Maintainer | Notes |
|---|---|---|
| [evcc-io/evcc vehicle/porsche](https://github.com/evcc-io/evcc/tree/master/vehicle/porsche) | evcc team | Go reference, cross-vehicle EVCC project |

---

## Cross-brand multi-OEM EVCC

| Project | Notes |
|---|---|
| [evcc-io/evcc](https://github.com/evcc-io/evcc) | Go-based EV-charging coordinator. Covers 30+ vehicle brands incl. all VAG brands. Excellent reference for API patterns even though it's a different runtime. |

---

## How we use this

- **Daily**: OLA watcher polls the 3 OLA-aware projects (`upstream-ola-watcher.yml`)
- **On scout reports**: cross-reference against the relevant brand's projects to validate findings
- **Architecture audits**: review their auth flows + endpoint maps when planning major refactors
- **Code attribution**: when we port a fix-pattern from one of these projects, cite them in the commit message + cariad/api/{brand}.py docstring (per `RELEASE_PROCESS.md`)

We are **not** a fork of any of these — we have our own clean-room
implementation. They are colleagues + signal-sources, not upstreams
we depend on at runtime.
