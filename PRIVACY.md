# Privacy / Datenschutz

> **Summary:** VW Group Connect runs entirely inside your Home Assistant instance.
> Your credentials and vehicle data never leave Home Assistant, except to the
> manufacturer's official API — or to one of the optional services listed below.
> Every third-party service is **off until you switch it on**. Two things do run
> by default, both acting on your own manufacturer account, and both are named
> below. We do not collect telemetry, we do not have a server, we do not have
> your data.

> **Kurzfassung:** VW Group Connect läuft komplett in deiner Home Assistant
> Instanz. Deine Zugangsdaten und Fahrzeugdaten verlassen Home Assistant nur
> direkt zu den offiziellen Hersteller-APIs — oder zu einem der unten
> aufgeführten optionalen Dienste. Jeder Dienst eines Dritten ist
> **ausgeschaltet, bis du ihn einschaltest**. Zwei Dinge laufen von sich aus,
> beide auf deinem eigenen Herstellerkonto, und beide stehen unten. Wir sammeln
> keine Telemetrie, wir haben keinen Server, wir haben deine Daten nicht.

---

## What data the integration handles

| Data | Where it goes | Stored where |
|---|---|---|
| Email + password | VW IDK / Auth0 / OLA / Škoda mysmob | HA config entry (encrypted by HA) |
| S-PIN | Brand API (only when you trigger lock/unlock/etc.) | HA config entry (encrypted by HA) |
| OAuth access + refresh tokens | Refreshed against VW IDK | Written to your disk in `.storage/vag_connect_tokens_<entry id>`, so a restart does not force a new login. Some brands also keep channel tokens in the HA config entry. |
| Vehicle data (SoC, range, doors, …) | CARIAD BFF / OLA / mysmob / PPA | HA recorder (your DB) |
| GPS position | CARIAD BFF / OLA / mysmob / PPA → HA | HA recorder + device tracker |
| VIN | Brand API + HA device registry | HA device registry, and in cached image filenames (see below) |
| EU Data Act datasets (raw ZIP) | Manufacturer's Data Act portal → HA | Parsed into HA; raw ZIPs only if you opt in (see below) |
| Phone screen content | Only between your phone and your HA, if you enable the companion | Not persisted |
| Push registration token | Brand push service (FCM / MQTT), if you enable push | In memory only — not written to disk |

**Nothing in this list goes to the maintainer.** There is no "phone home" and no
analytics.

---

## Optional third-party and extra data paths

Every row in this first table is **OFF by default**. None of it happens unless
you turn it on in HA → VW Group Connect → Configure. Two things that are **on**
by default follow in the second table.

| Feature | Goes to | Default | What is sent |
|---|---|---|---|
| Reverse geocoding (parking address) | `nominatim.openstreetmap.org` (OpenStreetMap) | **OFF** | The vehicle coordinate rounded to 3 decimals (~110 m), plus a `User-Agent` naming the integration. Results are cached per cell, so the same parking spot is not re-queried. **Up to and including 5.2.3b1 this was not true:** the rounding reached only the cache key and the request carried the full-precision coordinate. That is fixed in the repository but is not yet in a released version. |
| ABRP telemetry | `api.iternio.com` (A Better Route Planner) | **OFF** | Only when your own automation calls the `vag_connect.abrp_send` service — there is no automatic feed. Then: time, state of charge, charging and parked flags, position, heading, battery capacity and temperature, outside temperature, estimated range and odometer, under the ABRP token you supply. Speed is never sent. |
| Tibber as a supplementary source | `thewall.tibber.com` (Tibber) | **OFF** | An OAuth sign-in to your own Tibber account, to read vehicle data Tibber already holds. Tibber tokens are stored in the HA config entry. |
| Push notifications | Brand push infrastructure — Firebase Cloud Messaging (Audi/VW, CUPRA/SEAT) or MQTT (Škoda) | **OFF** | A push registration token, so the brand's service can wake the integration instead of it polling. Separate switches per brand. |
| Companion agent (phone) | Your phone ↔ your HA only | **OFF** | High-level verbs (dump the visible screen, tap, press BACK, report app version) and the screen content that comes back. Nothing leaves your network. See [`docs/COMPANION_AGENT.md`](docs/COMPANION_AGENT.md). |
| Raw EU Data Act dataset archive | Nowhere — stays on your disk | **OFF** | See the next section. |

### Two things that are ON by default

These are not third-party calls — they act on your own manufacturer account,
and they run unless you turn them off.

| Feature | Default | What it does |
|---|---|---|
| EU Data Act auto-kickoff | **ON** | In portal mode, the integration creates a standing "Custom Data Request" (a continuous 15-minute feed) on your manufacturer portal account, because portal mode returns empty entities without one. A one-time notification tells you when it has done so. Turn it off in Configure if you would rather create the request yourself. |
| Škoda official-API key | **ON** (source mode `auto`) | On a Škoda login the integration enrols an official API key for the car, sending the VIN and a key name. Set the Škoda source mode to `mysmob_only` to prevent it. |

Neither is revoked when you remove the integration — see below.

---

## What stays on your disk

### Raw EU Data Act dataset archive (opt-in)

If you enable it, the last few **raw** portal ZIPs are kept so a wrong or
missing field can be reproduced from the exact bytes the car sent, instead of
asking you to extract and share data by hand.

A raw dataset carries GPS, VIN and telemetry, so this is a privacy cost you
take on knowingly — which is why it is off by default. When it is on:

- the archive is bounded: at most **20 files and 10 MiB per vehicle**, oldest pruned first
- the **VIN never appears in a path** — it is hashed
- identical datasets are stored once (content-hash naming)
- a failure to write or prune never disturbs a poll

### Vehicle render images (Audi and others)

Vehicle render images are fetched from the manufacturer's public CDN (for Audi,
`mediaservice.audi.com` — the same CDN the myAudi web portal uses). The image
URL is discovered through an authenticated query; the PNG itself is public and
unauthenticated.

Images are cached under `/config/www/vehicles/` and served by Home Assistant at
`/local/vehicles/{vin}_{tag}.png` so you can use them in a picture entity.

**Two things to know about that.** The filename contains your **full VIN**. And
Home Assistant serves everything under `/config/www/` at `/local/` **without
authentication** — that is how HA's `www` folder works, not something this
integration chooses. So anyone who can reach your Home Assistant over the
network can fetch that image, and the VIN is in the URL. If your HA is exposed
to the internet, treat this as public.

### What removing the integration does and does not delete

Removing the config entry deletes the stored OAuth tokens. That is all it
deletes. It does **not** remove:

- the last-known vehicle snapshot in `.storage/vag_connect_vehicles_<entry id>`,
  which holds the VIN, the last position, parking address, licence plate,
  nickname, odometer, recent trips and charging sessions
- cached vehicle images under `/config/www/vehicles/`
- the raw dataset archive, if you had enabled it
- the ADB key pair in `.storage/vag_connect_adbkey`, if you used the companion
- any `utility_meter` helpers the integration created for you
- repair notices it had raised

On the manufacturer's side it also does not withdraw the standing Data Act
request or the Škoda API key described above. If you want all of that gone,
remove the files by hand after removing the integration, delete the helpers in
HA, and cancel the data request in the manufacturer's portal.

---

## What you should do as a user

- **Use a unique password** for your manufacturer account that you do not reuse
  anywhere else. The integration stores it as plain config (HA encrypts the
  on-disk file, but anything inside HA can read it).
- **Use the S-PIN feature** if your manufacturer supports it. Locking commands
  without S-PIN are blocked since v1.8.0.
- **Restrict who can access your Home Assistant.** Anyone who can log in to
  your HA can see every entity from this integration, including GPS. Services
  this integration registers are not restricted to admin users.
- **Use the diagnostics export with care, and know what it does not hide.** It
  redacts credentials, S-PIN, tokens, email address, the VIN, licence plate,
  nickname, parking address, image URLs and GPS coordinates. It does **not**
  redact your odometer reading, recent trips, charging history including
  station names and addresses, your preferred workshop's name, address, phone
  and coordinates, the driver score, or the heading. None of those identify you
  directly, but together they describe where you drive. Always read an export
  before sharing it. A GPS-precision defect on two report surfaces is fixed in
  the repository but is **not yet in a released version**
  ([#1378](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1378)), so
  an export made with 5.2.3b1 or earlier can still contain a precise
  coordinate.
- **Watch out for filenames when you share files.** A manufacturer portal export
  is named with your **full VIN**, so the filename carries it even when the
  file's contents are masked. The same is true of the cached image files above.

---

## EU / GDPR (DSGVO) considerations

VW Group Connect itself is **not a data processor under Article 28 GDPR**
because it does not run on a service we operate. It runs on your Home Assistant
instance, owned and controlled by you, the data subject.

The maintainer of this project does not collect, store, transmit or process any
personal data of users.

The **EU Data Act** (mandatory in-vehicle data access for third parties) applies
since September 2026. The integration can use a manufacturer's Data Act portal
as a data source where one exists; see issue
[#59](https://github.com/its-me-prash/vwgroup-connect-ha/issues/59). In that
mode the manufacturer hands out datasets as ZIP files, which the integration
downloads and parses in your HA.

---

## EU Cyber Resilience Act (CRA)

VW Group Connect is a community-maintained, non-commercial open-source
integration. It is not "commercial software" under the CRA, but the maintainer
voluntarily follows CRA-aligned practices:

- Coordinated vulnerability disclosure — see [`SECURITY.md`](SECURITY.md)
- No telemetry to the maintainer, no analytics, no remote update channel beyond
  HACS. (The optional ABRP feed above is telemetry you send to a service of your
  choosing, under your own token — it never reaches us.)
- Reproducible release ZIPs uploaded to GitHub Releases
- Source code under the GNU AGPL v3.0-or-later, fully auditable

---

## Changes to this policy

This policy may be updated when the integration adds features that change how
data is handled. The change log of this file is the git history of `PRIVACY.md`.

---

*Last updated: 2026-11-04 — describes the repository state after v5.2.3b1.*
