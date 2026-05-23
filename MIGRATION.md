# Migration Guide — `vag-connect-ha` → `vwgroup-connect-ha`

> **TL;DR**: Nothing breaks. The repo URL + display name changed; the
> code internals (DOMAIN, entity-IDs, service-calls, automations) all
> stayed the same. You don't need to do anything for existing setups —
> HACS auto-updates over the GitHub repo-rename redirect, your entities
> keep their IDs, your automations keep firing, your dashboards keep
> rendering. Read on for context + the optional cleanup steps.

---

## What changed in v2.4.0

| Aspect | Before | After |
|---|---|---|
| Repo URL | `github.com/its-me-prash/vag-connect-ha` | `github.com/its-me-prash/vwgroup-connect-ha` |
| Display name (HACS, integration card, config-flow titles) | `VAG Connect` | `VW Group Connect` |
| Manifest `name` | `VAG Connect` | `VW Group Connect` |
| HACS `name` | `VAG Connect` | `VW Group Connect` |

## What did **NOT** change (intentional)

| Aspect | Stays |
|---|---|
| Integration DOMAIN | `vag_connect` (unchanged — entity-IDs depend on this) |
| Entity-IDs | `sensor.audi_q4_battery_soc`, `lock.audi_q4_central_locking`, etc. — **identical** |
| Service-call prefixes | `vag_connect.lock`, `vag_connect.unlock`, `vag_connect.show_vag`, etc. — **identical** |
| Python imports | `from custom_components.vag_connect.*` — **identical** |
| HACS install directory | `custom_components/vag_connect/` — **identical** |
| Easter-egg service name | `vag_connect.show_vag` (per Jordan Waeles' original joke — preserved) |
| Long-term recorder history | All sensor history is keyed on entity-ID, which is unchanged → **preserved** |
| Your automations / scripts / dashboards | **All continue working** without edits |

## Why a marketing-only rename?

Because the internal DOMAIN is bound to every existing user's config
entries, entity registry rows, and history database. Renaming the DOMAIN
would force every user to:

- Remove + reinstall the integration
- Lose their entity-ID history (graphs reset)
- Rewrite every automation that references a service or entity
- Re-configure dashboards
- Re-pair any external systems that reference the old entity-IDs

That's a hostile experience for a marketing change. The rename was
prompted by a humorous community thread (see CHANGELOG v2.2.3 for full
credits), not by a real architectural issue — so we keep the joke alive
inside (service-name `vag_connect.show_vag` stays, code namespace
`vag_connect` stays) while presenting the cleaner display name to new
users discovering the integration.

If a real architectural reason ever requires a full DOMAIN rename, it
will ship as a v4.0.0 MAJOR with a proper `async_migrate_entry` flow.
Until then: marketing-only.

---

## What HACS users need to do

### Existing installations

**Nothing.** GitHub's repo-rename keeps the old URL `vag-connect-ha`
working as a permanent redirect, so HACS continues to fetch updates
from the new URL automatically. The next HACS update will:

1. Pull the new commit (manifest version bumped to 2.4.0)
2. Display the new name "VW Group Connect" in the HACS card and the
   HA integration card
3. Leave all your entities, automations, services, dashboards
   **untouched**

### New installations

Use the new URL when adding the custom repository:

```
https://github.com/its-me-prash/vwgroup-connect-ha
```

The old `vag-connect-ha` URL also works (GitHub redirect) — both
resolve to the same integration.

---

## Optional cleanup (for the perfectionists)

If you want your local references to match the new name:

### Update your custom HACS repo URL (optional)

HACS → Frontend → ⋮ → Custom repositories → find the old
`vag-connect-ha` URL → edit to `vwgroup-connect-ha`. **Not required**
— the old URL keeps working forever.

### Update your automation comments (optional)

If you have YAML comments mentioning "VAG Connect" by name, you can
update them to "VW Group Connect". The service-call names themselves
(`vag_connect.lock` etc.) **must stay** — those are bound to the
DOMAIN and renaming them would break the call.

### Discord / Forum / Facebook references

Continue to call it whatever your community prefers — `vag-connect-ha`
and `VW Group Connect` both refer to the same integration. The HA UK
+ HA Ideas + DACH FB-Gruppen know it under both names now.

---

## History preservation note

CHANGELOG entries pre-v2.4.0 (i.e. v1.x and v2.0.x through v2.3.x)
reference the project under its previous name `VAG Connect`. They
have **not** been retroactively rewritten — those releases really
shipped under that name, and rewriting history would be inaccurate.

The `docs/research/2026-*.md` files are similarly preserved as-is;
they were research notes timestamped during the original-name era and
keep their original references for archival accuracy.

---

## Credits

The rename was prompted by community feedback on:

- **Home Assistant UK** Facebook group
- **HA Ideas, Projects and Solutions** Facebook group

Specifically:
- **Si Gregory** — suggested the rename
- **Ben Johnson** — seconded
- **Evets David** — "Is it a dating integration?" (the question that
  made the case unmistakable)
- **Stuart McBride** — added supporting input
- **Jordan Waeles** — the immortal Pandas-style `show_vag()` joke that
  became an officially supported easter-egg service in v2.2.3

Thank you all. 🏁
