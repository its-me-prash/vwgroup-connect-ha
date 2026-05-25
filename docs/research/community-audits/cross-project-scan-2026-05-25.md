# Cross-Project Scan — 2026-05-25

> What's happened in parallel community projects since our last audit
> (2026-05-15 v2.0.0 era). Focus on actionable findings: new features
> we don't have, improvements we missed, projects that died.

## 🚨 mitch-dc/volkswagen_we_connect_id — ARCHIVED

**Status as of 2025-10-29**: archived. No more updates ever.

| Stat | Value |
|---|---|
| Stars | 254 |
| Last commit | 2025-02-20 |
| Last push (archive) | 2025-10-29 |
| Status | Read-only, no maintainer |

This was THE reference VW EU community integration for 3+ years. Its archival is a big deal.

**Actions:**
1. Update `docs/research/app-atlas/_community-projects.md` to mark it as legacy/archived
2. Notify the broader community: we (vwgroup-connect-ha) + tillsteinbach/CarConnectivity-connector-volkswagen are now the active VW EU references
3. Audit if any mitch-dc users would benefit from migrating to us — opportunity for a "migrating from mitch-dc" guide alongside our existing `MIGRATION.md`

## arjenvrh/audi_connect_ha — maintenance-only

Last 6 weeks: only dependency-bump and pre-commit-autoupdate PRs.

**Activity since 2026-04:**
- 2026-04-16: chore: pre-commit autoupdate (#720)
- 2026-04-16: chore(deps): bump ad-m/github-push-action (#724)

**Conclusion**: stable but not evolving. No new features to learn from. Continues to be a reference for Audi-specific quirks but we're already cross-brand mature.

**Action**: nothing.

## skodaconnect/homeassistant-myskoda — VERY active

Last 6 weeks: multiple substantive feature/fix PRs. **Two are actionable for us:**

### PR #1087 — ACTIVE_VENTILATION capability switch (Skoda ICE) — 2026-05-19

Exposes the "10-minute cabin ventilation" feature for Skoda ICE vehicles without auxiliary heater (e.g. Octavia). Same as the MySkoda app's air-circulation-without-heat function.

**Status in our code**: unknown. We support Skoda mysmob backend but our capability table may not include ACTIVE_VENTILATION.

**Action C1**: audit our `cariad/_capabilities.py` for ACTIVE_VENTILATION presence. If absent, add the capability mapping + a switch entity (similar to our existing aux-heater switch but no S-PIN required).

**Estimated effort**: 1-2h. P2 because affects only Skoda ICE Octavia owners.

### PR #1083 — Firebase-backed MQTTv5 auth integration — 2026-04-28

Major refactor (1048 add / 206 del) of their MQTT push-update integration. Changes:
1. Replaced deprecated `MySkoda.connect_with_refresh_token` with unified `MySkoda.connect`
2. Integrated FCM Token refresh in MQTT reconnection logic
3. Force new FCM Token every 10 reconnection attempts
4. Persist FCM Token after successful MQTT connection

**Status in our code**: our `cariad/push/skoda_mqtt.py` was built as scaffolding (v1.18.0+) but live activation is still **tester-blocked** (#161). When we do activate, we should follow the new Firebase-MQTTv5 pattern from the start instead of the older refresh-token approach.

**Action C2**: when picking up #161 (Push Phase 2 Live Activation), use skodaconnect's PR #1083 as the auth-flow reference. Specific patterns to copy:
- FCM token rotation cadence (every-10-reconnects)
- Token persistence after successful connect
- Unified connect-with-credentials-or-token API instead of two separate methods

**Estimated effort**: bundled into eventual #161 work, no separate v2.5.0 PR.

### PR #1085 — image renders fix for new models — 2026-05-02

Skoda backend started returning slightly different image-URL shapes for newer models (Enyaq Coupe iV gen2, Kodiaq gen2). They patched their image parser.

**Status in our code**: we have `cariad/api/skoda.py` image-render parsing. Likely affected too.

**Action C3**: quick test against a Skoda Mk2 user (Christian on #75) — does our render-URL parser still return populated URLs for new models?

**Estimated effort**: 30min audit; fix if needed = 1h.

## tillsteinbach/CarConnectivity-* family — active

This is the same maintainer who runs CarConnectivity-connector-seatcupra (our daily-watched OLA source). They also maintain `-volkswagen`, `-audi`, `-skoda`, `-volkswagen-na`, `-porsche` connectors. Last 1-2 months show steady evolution.

**Spot check needed for**:
- CarConnectivity-connector-audi — did they add any Audi-specific endpoints we don't have?
- CarConnectivity-connector-skoda — sibling check for the ACTIVE_VENTILATION work above

**Action C4**: low-priority sibling scan, defer to v2.6.0.

## Summary table

| Project | Status | Action | Priority |
|---|---|---|---|
| mitch-dc/volkswagen_we_connect_id | **ARCHIVED 2025-10-29** | Update community-projects.md, write migration guide | P2 |
| arjenvrh/audi_connect_ha | Maintenance-only | None | — |
| skodaconnect/homeassistant-myskoda — ACTIVE_VENTILATION (PR #1087) | Active, new feature | Audit our capability + add switch | P2 |
| skodaconnect/homeassistant-myskoda — Firebase-MQTTv5 (PR #1083) | Active, refactor | Use as reference when shipping #161 | Deferred |
| skodaconnect/homeassistant-myskoda — image renders (PR #1085) | Active, fix | Audit our render parser for Skoda Mk2 | P2 |
| tillsteinbach/CarConnectivity-* family | Active | Sibling scan | P3 (v2.6.0) |

## Total v2.5.0 candidate work from this scan

- **Estimated**: 4-6h (C1 + C3 actions, migration-guide for mitch-dc users)
- **Combined with daern audit findings** (A1+A2+A3 = 4-6h): **~10h total for v2.5.0**

See [`docs/research/v2.5.0-action-plan.md`](../v2.5.0-action-plan.md) for the
consolidated decision matrix.
