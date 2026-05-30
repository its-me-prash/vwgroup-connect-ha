# vwgroup-connect-ha Roadmap

> Living document. Updated quarterly. Last update: 2026-05-11.

## Where we are

**v1.27.0** ships Pre-Cariad PHEV first-class support, MBB metadata entities,
long-term trip aggregates, and departure timer detail entities. Based on the
[Pre-Cariad MBB audit](_private/research-archive/2026-05_pre-cariad-mbb-and-golf-7-gte-audit.md)
and [strategic roadmap](_private/research-archive/2026-05_strategic-roadmap-v1.27-to-v2.0.md).

## Five strategic pillars

1. **Single integration, all 7 brands** (Audi, VW EU, Skoda, SEAT, CUPRA, Porsche, VW NA). No middleware.
2. **Pre-Cariad PHEV as a first-class citizen.** Golf 7 GTE, Passat B8 GTE, Audi A3 e-tron 8V, etc.
3. **Auth that survives 2026 reality.** 2FA email codes, marketing-consent prompts, HA core update credential loss.
4. **Push > Poll.** Skoda MQTT + FCM for VW/Audi/CUPRA/SEAT (Issue #161).
5. **EU Data Act-ready architecture.** Backend abstraction layer for Cariad-Global / SDV-East / SDV-West.

## Releases

| Version | Theme | Target | Highlights |
|---|---|---|---|
| **v1.27.0** | Pre-Cariad PHEV + new entities | 2-3 weeks | PR #179 audit + Bruno collection, MBB metadata sensors, long-term trip aggregates, departure timer detail, polish features (Issue #178) |
| **v1.28.0** | Auth resilience | 4 weeks | Email-code 2FA, marketing-consent prompt detection, persistent session storage, reconfigure flow for password updates |
| **v1.29.0** | Push Phase 2 Live | 4 weeks (parallel) | Skoda MQTT live, FCM live for CUPRA/SEAT/Audi/VW, push-vs-poll fallback (Issue #161) |
| **v1.30.0** | MBB Phase 2 + Lovelace Card | 6 weeks | MIB3 lock/climate/charger fallbacks (Issue #160), alarm sensor (Issue #33), heaterSource (Issue #163), companion Lovelace card (Issue #162) |
| **v2.0.0** | EU Data Act + SDV-West readiness | Q3/Q4 2026 | Backend abstraction, optional VSS output, deprecate legacy MBB shims, SDV-West auth (Rivian JV), `quality_scale: platinum` |

## What we won't do

- **Won't reverse-engineer legacy MBB direct-data endpoints** — audit confirmed the `XID_APP_VW`
  permission gate is structural and not bypassable from public clients.
- **Won't ship `quality_scale` improvements until HA core stabilizes** — this triggered the
  v1.26.1 install regression. Waiting upstream.
- **Won't add scout-detected fields without entity intent** — every new field becomes an entity
  in the next minor or gets closed.

## Get involved

- 🐛 Bug? → [Issues](https://github.com/its-me-prash/vwgroup-connect-ha/issues)
- 🧪 Tester for Skoda/SEAT/CUPRA hardware? → comment on [#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)
- 💬 Pre-Cariad PHEV owner? → check the [audit doc](_private/research-archive/2026-05_pre-cariad-mbb-and-golf-7-gte-audit.md)
  and run `scripts/verify_cariad_full.py` to inventory your VIN's data
- 📋 Want detailed competitor analysis + ecosystem trends? → [strategic roadmap](_private/research-archive/2026-05_strategic-roadmap-v1.27-to-v2.0.md)
