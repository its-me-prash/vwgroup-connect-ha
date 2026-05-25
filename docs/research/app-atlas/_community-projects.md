# Community Projects — Comparison + Resource Index

> Auto-curated reference of parallel VAG-brand Home Assistant /
> Python integrations. We track these as **upstream signal sources**
> for our cross-brand work (cf. App Atlas `README.md`).
>
> Last reviewed: 2026-05-25

---

## OLA backend (SEAT + CUPRA)

Three independent community projects target the SEAT/CUPRA OLA
backend (`ola.prod.code.seat.cloud.vwgroup.com`). All three were
broken by the 2026-05-20 app-header enforcement; all three fixed it
with the same `app-market` + `app-brand` + `app-version` + `origin`
header injection.

| Project | Maintainer | Brand coverage | Architecture |
|---|---|---|---|
| [CarConnectivity-connector-seatcupra](https://github.com/tillsteinbach/CarConnectivity-connector-seatcupra) | tillsteinbach | SEAT + CUPRA | Direct OLA, Android-app client_id, full OAuth + token refresh |
| [PyCupra](https://github.com/WulfgarW/pycupra) ([pip](https://pypi.org/project/pycupra/)) | WulfgarW | SEAT + CUPRA | Direct OLA, similar architecture, separate auth-session manager |
| [WeConnect-Cupra-python](https://github.com/daernsinstantfortress/WeConnect-Cupra-python) ([pip](https://pypi.org/project/weconnect-cupra-daern/)) + [HA integration](https://github.com/daernsinstantfortress/cupra_we_connect) | daernsinstantfortress | CUPRA only | **Cariad-BFF + OLA hybrid** — uses browser-IDP client_id (`3c756d46-...@apps_vw-dilab_com`), different signin-service path |

**Why we monitor all three**:
- Three independent maintainers confirming a header value = high confidence
- Earliest-warning when one of them detects API breakage before the others
- Catches per-brand divergence (e.g. CarConnectivity ships SEAT `2.17.0`
  while PyCupra ships `2.13.3` — both work in the wild, real-world example of why multi-source matters)

**Why daernsinstantfortress is architecturally interesting for us long-term**:
- Their CUPRA-via-Cariad-BFF route is a backup architecture we don't have today
- If OLA enforcement ever escalates beyond what the 4-layer defense-in-depth can handle, this path is a viable Plan B
- Phase B follow-up: investigate if we can add Cariad-BFF as a CUPRA fallback parallel to OLA

---

## VW EU + Audi (Cariad-BFF backend)

| Project | Maintainer | Brand coverage | Status |
|---|---|---|---|
| [mitch-dc/volkswagen_we_connect_id](https://github.com/mitch-dc/volkswagen_we_connect_id) | mitch-dc | VW EU | Active, large community |
| [audi_connect_ha](https://github.com/arjenvrh/audi_connect_ha) | arjenvrh | Audi | Active |
| [volkswagencarnet](https://github.com/robinostlund/volkswagencarnet) | robinostlund | VW + Audi (legacy MBB) | Maintenance mode |
| [tillsteinbach/CarConnectivity-connector-volkswagen](https://github.com/tillsteinbach/CarConnectivity-connector-volkswagen) | tillsteinbach | VW EU | Newer, sibling of seatcupra connector |
| [tillsteinbach/CarConnectivity-connector-audi](https://github.com/tillsteinbach/CarConnectivity-connector-audi) | tillsteinbach | Audi | Newer |

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
| [andig/evcc vehicle/porsche](https://github.com/andig/evcc/tree/master/vehicle/porsche) | andig | Go reference, cross-vehicle EVCC project |

---

## Cross-brand multi-OEM EVCC

| Project | Notes |
|---|---|
| [andig/evcc](https://github.com/andig/evcc) | Go-based EV-charging coordinator. Covers 30+ vehicle brands incl. all VAG brands. Excellent reference for API patterns even though it's a different runtime. |

---

## How we use this

- **Daily**: OLA watcher polls the 3 OLA-aware projects (`upstream-ola-watcher.yml`)
- **On scout reports**: cross-reference against the relevant brand's projects to validate findings
- **Architecture audits**: review their auth flows + endpoint maps when planning major refactors
- **Code attribution**: when we port a fix-pattern from one of these projects, cite them in the commit message + cariad/api/{brand}.py docstring (per `RELEASE_PROCESS.md`)

We are **not** a fork of any of these — we have our own clean-room
implementation. They are colleagues + signal-sources, not upstreams
we depend on at runtime.
