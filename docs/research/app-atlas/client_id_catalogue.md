# VAG App-Atlas — Client-ID & Auth Catalogue

> Consolidated catalogue of **every OAuth/auth client_id** found across the
> 2026-06 cross-brand app-atlas (apkeep apk-pure pulls + DEX/config/JS-bundle
> grep, strict UUID regex). Includes clients we do **not** use yet — they
> "might become useful" as fallbacks, for a future MBB/legacy adapter, or as
> auth intelligence. Sourced from the app binaries; values re-verify against a
> live token exchange before being trusted as more than catalogued candidates.

## Auth schemes in the VAG ecosystem (which client format goes with which flow)

| Scheme | Token endpoint | Client format | Brands/apps |
|---|---|---|---|
| **IDK / CARIAD-BFF** | `identity.vwgroup.io/oidc/v1/token` or `emea.bff.cariad.digital/auth/v1/idk/oidc/token` (+ `x-qmauth` HMAC) | `<uuid>@apps_vw-dilab_com` | VW EU, Audi, Bentley (Audi tenant), modern Škoda/SEAT/CUPRA |
| **OLA** (SEAT/CUPRA) | `identity.vwgroup.io` IDK → OLA backend `ola.prod.code.seat.cloud.vwgroup.com` (+ `app-version`/`app-brand` headers, App-Check since 2026-05-20) | `<uuid>@apps_vw-dilab_com` | My SEAT, My CUPRA |
| **MBB** (legacy) | `mbboauth-1d.prd.ece.vwg-connect.com/mobile/oauth2/v1/token` (+ `X-Client-Id` header, hybrid id_token) | bare UUID (no suffix) **or** runtime-provisioned | We Connect e-Remote, SEAT/CUPRA mod2, Audi MMI, legacy Škoda |
| **SDP-proxy MBB** | `sdp.lamborghini.com/unicav2/mbbcoauth` (scope `sc2:fal`, client held server-side) | not in APK | Lamborghini Unica |
| **NA IdP** | `identity.na.vwgroup.io` → `con-veh.net` | `<uuid>_MYVW_ANDROID` | myVW (US/CA) |
| **Porsche ID** | `identity.porsche.com` / Auth0 | opaque (`Xhyg…`) / runtime BuildConfig | My Porsche, Porsche Connect |
| **Sovereign regional** | India `lpms.nscindia.co.in` (VIN+OTP) · China `prd.cn.vwg-connect.cn`/Timan · Korea `myvw.vwkr.co.kr` | own/none — **NOT vwgroup** | India SAVWIPL, China FAW/SAIC, Korea-VW |

---

## 1. dilab clients — `@apps_vw-dilab_com` (usable in our IDK `oauth_client_id_chain`)

These are the only format our resolver chain accepts. ✅ = wired in repo today.

| client_id | brand / source app(s) | status |
|---|---|---|
| `a24fba63-…` | VW EU — weconnect (primary) | ✅ BRAND_VW_EU + alternate |
| `4edc53db-…` | VW EU — weconnect (2nd) | ✅ `_ALTERNATE['volkswagen']` |
| `09b6cbec-…` | Audi (primary) **+ Bentley** (idkClientIDLive) | ✅ BRAND_AUDI; ✅ BRAND_BENTLEY (v2.14.11) |
| `16dd7960-…` | Audi — myAudi (2nd) | ✅ `_ALTERNATE['audi']` |
| `f4d0934f-…` | Audi — evcc-derived | ✅ `_ALTERNATE['audi']` (not APK-confirmed) |
| `7f045eee-…` | Škoda (primary) — myskoda + connect | ✅ BRAND_SKODA |
| `4fffed6b-…` | Škoda — myskoda **+** connect (shared) | ✅ `_ALTERNATE['skoda']` (v2.14.11) |
| `99a5b77d-…` | SEAT (primary) — myseat.ola + mycupra | ✅ BRAND_SEAT |
| `3c756d46-…` | CUPRA (primary) — mycupra + myseat.ola | ✅ BRAND_CUPRA |
| `3f16b970-…` | SEAT+CUPRA OLA (shared) | ✅ `_ALTERNATE['seat']`+`['cupra']` (v2.14.11) |
| `f1cd60b6-…` | SEAT+CUPRA OLA (shared) | ✅ `_ALTERNATE['seat']`+`['cupra']` (v2.14.11) |
| `7cd71138-…` | Bentley — Approval/QA (non-prod) | catalogued, **not shipped** (non-prod) |
| `a9d0a852-…` | Bentley — Dev (non-prod) | catalogued, **not shipped** (non-prod) |
| `0670adb8 · 0f365c6e · 4e5f4b01 · 6abd22ad · 72f9d29d · f9a2359a` | Škoda — connect (legacy, 6× per-addon/per-env IDK) | **catalogued, not chained** — bloats the chain (6× extra 401 hops); use individually only if 7f045eee+4fffed6b both rotate |
| `9496332b-…` | VW EU — e-Remote (legacy VWID-login bolt-on) | **LONG-SHOT chained** (v2.14.11) in `_ALTERNATE['volkswagen']` — its MBB stack predates the App-Check wall, the one candidate that might luck past it; keep only if a tester confirms a real token |
| `ac42b0fa-…` | VW EU — We Connect Go (OBD dongle) | **LONG-SHOT chained** (v2.14.11) tail candidate for VW; `identity.legacy.vwgroup.io` + cardata, low odds |
| `b6628921-…` | Škoda — Connect Lite (OBD dongle) | **catalogued** — Cubic CARDATA backend, NOT mysmob; would 401 on the car API |
| `ec6198b1-…` | Audi — connect plug&play (OBD dongle) | **catalogued** — CARIAD `cardata` backend, not the connected-car API |
| `7a35ab5a-…` | SEAT — SEAT Plus (DataPlug OBD) | **catalogued** — DataPlug cloud, not OLA |

**Rule:** the dongle/cardata + per-addon dilab clients are real but scoped to the WRONG backend — chaining them adds a guaranteed-401 hop for normal users, so they are catalogued-only. Add to `_ALTERNATE_CLIENT_IDS` only the cross-app, same-backend ones (done: skoda/seat/cupra).

## 2. Legacy MBB clients — bare UUID, **different flow** (NOT for the dilab chain)

Usable only by a future MBB adapter (Tier-3, for old combustion/PHEV cars). Do **NOT** put these in `_ALTERNATE_CLIENT_IDS` (the `@apps_vw-dilab_com` guard drops them).

| client_id | source apps | note |
|---|---|---|
| `9523ee15-f6e0-4eb9-9907-59d058d7e16e` | eremote **+** seat-mod2 **+** cupra-mod2 (shared) | **the** shared legacy MBB client — the prize for an MBB adapter |
| `fbd7e560 · d34abd2b · b818fbe4 · ad3df97f · 2ee56a12 · 2990be23` | seat-mod2 + cupra-mod2 (shared pair) | mod2 string-pool UUIDs (some may be config, not OAuth — verify before use) |
| `6f5355f5-c630-4bd2-b763-060d204789dc` | Porsche Connect (legacy) | MBB JWT `iss VWGMBB01DEAPP1 / sys XID_PCC_APP`; 2019-era, backend likely dead |
| _(runtime)_ | Škoda connect (`MbbXClientIdRepositoryImpl`), Audi mmiapp (`AppIdentifierToGuid`) | MBB X-Client-Id provisioned per-install from server — **no static value in the APK** |

## 3. Region / sovereign / separate-IdP clients (NOT cross-usable)

| client | brand/app | why not usable |
|---|---|---|
| `59992128-…_MYVW_ANDROID` | VW NA (myVW US-prod) | ✅ BRAND_VW_NA — NA IdP, different format/flow |
| `2322ce5a · 3bf2dad2 · 69eb3c39 · 83728e19 · 8ce196c0 · dd813889` (`…_MYVW_ANDROID`) | VW NA — env-siblings | per-environment (uat/ci/int/pre) of the SAME app; document-only, never chain |
| `XhygisuebbrqQ80byOuU5VncxLIm8E6H` | Porsche (Auth0) | ✅ BRAND_PORSCHE — own Porsche IdP; absent from all 3 current Porsche apps (older gen) |
| _(none)_ | **India** (SAVWIPL): audi.drive, vwindia.*, skoda*india* | sovereign `lpms.nscindia.co.in` / `skoda-auto.co.in`, VIN+OTP / OBD-dongle — **no vwgroup client** (verified by grep) |
| _(none)_ | **China** (Timan/SAIC): com.timanetworks.*, com.svw.* | sovereign `prd.cn.vwg-connect.cn` / Timan — no extractable vwgroup client; store-only, PIPL |
| _(none)_ | **Korea-VW** `kr.co.volkswagen.my` | React-Native app, bundle points only at sovereign `myvw.vwkr.co.kr` — no identity.vwgroup.io, no dilab client (verified in JS bundle) |

**Verified (not assumed):** the India/China/Korea-VW sovereign apps were pulled + grepped — they carry **no `@apps_vw-dilab_com` client**, so there is no cross-acceptable client to harvest there. The "might become useful" payoff is confined to §1 (dilab, same-ecosystem) and §2 (MBB, future adapter).

---

_Generated from the 2026-06 cross-brand atlas corpus (apkeep apk-pure pulls + DEX/config/JS-bundle grep). Regenerate via `scripts/app_atlas` over a fresh corpus._
