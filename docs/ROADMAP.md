# Roadmap

Living plan for VW Group Connect. Phased by release. Updated 2026-06-09.

This is internal planning, not a promise — items move between phases as
upstream backends change and as live-test feedback arrives. Tracker issues
are referenced by number.

## Where we are

- **Stable:** v2.12.4
- **VW EU Data Act portal:** connector shipped (beta, read-only). Currently
  riding out the VW-side all-brands portal outage that started late May
  2026 — login + entities work, but telemetry only flows when VW's backend
  is up. v2.12.4 makes the integration treat that outage as transient
  instead of an auth failure.

## Auth paths by brand (2026-06-07)

VW closed the token-based login routes for VW passenger cars over
2026-05/06 (hybrid response_type → 403, public-client code exchange needs a
client secret, device-grant disabled for the VW client). Verified live.
This splits the auth model:

| Brand | Auth path | Data | Commands |
|---|---|---|---|
| Škoda | token (mysmob) | full | yes |
| CUPRA / SEAT | token (OLA) | full | yes |
| Audi | token (CARIAD BFF) | full | yes |
| VW EU (passenger) | **EU Data Act portal (cookie)** | read-only, ~15 min | no |
| VW NA | token (Cox) | full | partial |

The EU Data Act portal is the route VW must keep open under Regulation
(EU) 2023/2854 (obligations from Sep 2026). It is the foundation other
brands can fall back to if their token routes close later.

## Phases

### Shipped (v2.12.0 → v2.12.4)
- **v2.12.0** — EU Data Act portal connector for VW EU (cookie login + ZIP
  delivery → curated VehicleData mapping, read-only beta);
  `/login/login/` duplicate-segment guard; Škoda trip overall-cost;
  future-dated `carCapturedTimestamp` guard (all brands); Scout
  `EXPECTED_KEYS` cross-brand cleanup; `LEGAL.md`.
- **v2.12.1** — portal session re-established on every restart (#393);
  metadata 404/500 treated as "no data yet", not an error (#393, #424);
  Audi scout depth for charging timers/profiles (#423).
- **v2.12.2** — "no vehicle data" repair notice when the portal logs in but
  returns nothing (points at the VW outage / missing data request), 8 langs.
- **v2.12.3** — complete translations across all 8 languages (no more
  English fallback for non-EN users).
- **v2.12.4** — outage resilience: a transient VW-backend 5xx (portal HTTP
  500, CARIAD token-endpoint 502) is treated as "temporarily unavailable"
  instead of an auth failure, so it no longer triggers a reauth prompt or
  spams the Error Reporter (#428–#439). Entities keep their last value
  through the failure-tolerance window.

### Next (verified backlog)
- **CUPRA Formentor PHEV field mapping** — fuel level, combustion/total
  range, primary/secondary engine, target/outside temperature, permissions,
  trip stats. Still **blocked on a DEBUG log** (raw mycar + climatisation
  response) so the exact PHEV key paths are mapped, not guessed (#392).
- **Portal bootstrap-merge** — on first run, fetch all available portal
  datasets and merge the latest value per field for a better cold-start.
  Deliberately deferred until the VW outage lifts (mid-outage it would only
  multiply requests against a failing portal).
- **Portal field coverage** — expand beyond the curated ~15 fields toward
  the fuller EU Data Act dictionary, as live datasets confirm shapes.

### v2.13 — mid-term
- Offer the EU Data Act portal path for other brands as an optional
  read-only fallback (Škoda / Audi expose equivalent portals).
- Reconfigure flow for password updates, brand-agnostic (part of #183).
- Marketing-consent prompt detection + re-auth UX (#183).

### Parked — blocked on tester or trigger
- **#161 Push Phase 2** — foundation shipped (v1.18–v1.23); needs a live
  tester per brand. Not applicable to VW EU (read-only portal has no push);
  still relevant for Škoda / CUPRA / SEAT / Audi.
- **#160 MBB Legacy Phase 2** — write-side fallback for older MIB3
  vehicles; needs an MBB-vehicle owner to confirm the v1.21.0 wake fallback
  fires live before setter commands can be verified.

### Continuous
- **#13 Live-Tests** — active across CUPRA Formentor, VW EU ID.7, VW Golf,
  SEAT Mii, CUPRA Terramar via the open issues. Broadest brand coverage so
  far.
- **#59 EU Data Act** — was research/monitor; now the active delivery line
  (v2.12.0 is the first concrete connector). Continues as the long-term
  spine through the Sep 2026 obligations.

## Notes

- Releases go out PR-first (not direct push + tag), max 1–2 per day after
  clean prep.
- Field names are verified against the upstream brand libraries before
  shipping, never guessed.
