# Privacy / Datenschutz

> **Summary:** VW Group Connect runs entirely inside your Home Assistant instance.
> Your credentials and vehicle data never leave Home Assistant unless they
> go directly to the manufacturer's official API. We do not collect
> telemetry, we do not have a server, we do not have your data.

> **Kurzfassung:** VW Group Connect läuft komplett in deiner Home Assistant
> Instanz. Deine Zugangsdaten und Fahrzeugdaten verlassen Home Assistant
> nur direkt zu den offiziellen Hersteller-APIs. Wir sammeln keine
> Telemetrie, wir haben keinen Server, wir haben deine Daten nicht.

---

## What data the integration handles

| Data | Where it goes | Stored where |
|---|---|---|
| Email + password | VW IDK / Auth0 / OLA / Škoda mysmob | HA config entry (encrypted by HA) |
| S-PIN | Brand API (only when you trigger lock/unlock/etc.) | HA config entry (encrypted by HA) |
| OAuth access + refresh tokens | Held in memory, refreshed against VW IDK | HA config entry |
| Vehicle data (SoC, range, doors, …) | CARIAD BFF / OLA / mysmob / PPA | HA recorder (your DB) |
| GPS position | CARIAD BFF / OLA / mysmob / PPA → HA | HA recorder + device tracker |
| VIN | Brand API + HA device registry | HA device registry |

**Nothing in this list goes to the maintainer.** Nothing goes to
third-party analytics. There is no "phone home".

---

## Optional third-party calls

The following calls only happen if **you explicitly enable them**:

| Feature | Third party | Default | How to enable |
|---|---|---|---|
| Reverse geocoding (parking address) | OpenStreetMap Nominatim | **OFF** | HA → VW Group Connect → Configure → "Reverse Geocoding" |

When reverse geocoding is on, the rounded vehicle coordinate (3 decimals,
~110m precision) is sent to `nominatim.openstreetmap.org` with a
`User-Agent` identifying the integration. Results are cached so the same
parking spot is not re-queried.

---

## Vehicle render images (Audi)

Audi vehicle render images are fetched from `mediaservice.audi.com` (the
public CDN that the myAudi web portal uses). The image URL itself is
discovered via an authenticated GraphQL query to Audi. The PNG file is
public and unauthenticated.

Fetched images are cached locally under `/config/www/vehicles/` so they
do not re-download on every restart.

---

## What you should do as a user

- **Use a unique password** for your manufacturer account that you do not
  reuse anywhere else. The integration stores it as plain config (HA
  encrypts the on-disk file, but anything inside HA can read it).
- **Use the S-PIN feature** if your manufacturer supports it. Locking
  commands without S-PIN are blocked since v1.8.0.
- **Restrict who can access your Home Assistant**. Anyone who can log in
  to your HA can see every entity from this integration, including GPS.
- **Use the diagnostics export with care.** It already redacts password,
  S-PIN, username and GPS, but always review before sharing.

---

## EU / GDPR (DSGVO) considerations

VW Group Connect itself is **not a data processor under Article 28 GDPR**
because it does not run on a service we operate. It runs on your Home
Assistant instance, owned and controlled by you, the data subject.

The maintainer of this project does not collect, store, transmit or
process any personal data of users.

The EU Data Act (mandatory in-vehicle data access for third parties)
takes effect in September 2026 and may give vehicle owners formal,
documented API access — see issue
[#59](https://github.com/its-me-prash/vwgroup-connect-ha/issues/59).

---

## EU Cyber Resilience Act (CRA)

VW Group Connect is a community-maintained, non-commercial open-source
integration. It is not "commercial software" under the CRA, but the
maintainer voluntarily follows CRA-aligned practices:

- Coordinated vulnerability disclosure — see [`SECURITY.md`](SECURITY.md)
- No telemetry / no analytics / no remote update channel beyond HACS
- Reproducible release ZIPs uploaded to GitHub Releases
- Source code under Apache 2.0, fully auditable

---

## Changes to this policy

This policy may be updated when the integration adds features that change
how data is handled. The change log of this file is the git history of
`PRIVACY.md`.

---

*Last updated: 2026-04-26 — v1.8.0*
