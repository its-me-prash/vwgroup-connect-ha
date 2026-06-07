# Roadmap

Living plan for VW Group Connect. Phased by release. Updated 2026-06-07.

This is internal planning, not a promise — items move between phases as
upstream backends change and as live-test feedback arrives. Tracker issues
are referenced by number.

## Where we are

- **Stable:** v2.11.4
- **In validation:** v2.12.0 (EU Data Act portal connector for VW EU, beta)

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

### v2.12.0 — shipping (in validation)
- EU Data Act portal connector for VW EU (cookie login + ZIP delivery →
  curated VehicleData mapping). Read-only, beta.
- `/login/login/` duplicate-segment guard in the portal login.
- Škoda trip overall-cost (total / fuel / electricity / cng + currency).
- Future-dated `carCapturedTimestamp` guard (all brands).
- Scout `EXPECTED_KEYS` cross-brand cleanup. Closes the scout reports on
  #411, #414, #415, #416, #417, #419.
- `LEGAL.md` (statutory basis + attribution).

Scope is frozen — no further additions before tag; remaining backlog needs
either a DEBUG log or a live tester, so it belongs in later phases.

### v2.12.1 — next (verified, post-validation)
- CUPRA Formentor PHEV field mapping: fuel level, combustion/total range,
  primary/secondary engine values, target/outside temperature, permissions,
  trip stats. **Blocked on a DEBUG log** (raw mycar + climatisation
  response) so the exact PHEV key paths are mapped, not guessed (#392).
- Portal connector hardening from VW EU live feedback (#388, #393).
- Portal field coverage — expand beyond the curated ~15 fields toward the
  fuller EU Data Act dictionary, as live datasets confirm shapes.

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
