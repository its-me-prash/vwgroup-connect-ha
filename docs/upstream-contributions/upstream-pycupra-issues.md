# Upstream Contribution Drafts — upstream/homeassistant-pycupra

> **Purpose:** 8 ready-to-post issues / feature requests for the
> upstream pycupra HA integration, distilled from anonymized
> community observations + public release notes.
>
> **Usage:** Copy-paste each section as a new GitHub issue at
> `https://github.com/upstream/homeassistant-pycupra/issues/new`.
> No AI/automation attribution included — these are framed as your
> own constructive feedback to the maintainer.
>
> Created: 2026-05-02

---

## Issue 1 — Add `async_step_reauth` for in-UI credential refresh

**Title:** `feat: in-UI re-authentication after manufacturer password change`

**Body:**

After a Cupra/Seat ID password change, after accepting new T&Cs, or
after a temporary account lock, the integration's background refresh
fails with `Login failed for <user>`. The current resolution path
requires removing and re-adding the integration.

This works but has two real costs:

1. **Long-term statistics history is lost** — the
   `recorder`/`statistics` tables are keyed by the entity's
   `unique_id`, so removing the device drops aggregated kWh /
   distance / duration history. Users charging tracking / fuel
   cost dashboards lose months of data per password change.
2. **Lovelace cards bound to the entity_ids** sometimes need
   manual re-wiring after re-add (entity_id can change if a
   collision was previously resolved with a `_2` suffix).

Home Assistant's `config_entries.ConfigFlow.async_step_reauth` is
designed exactly for this:

- HA detects auth failure (the integration raises
  `ConfigEntryAuthFailed`)
- A "Reconfigure" button appears in the integrations UI for the
  affected entry
- The user re-enters credentials in a single dialog
- The entry is updated in place — entity_ids preserved, statistics
  history kept

### Suggested implementation sketch

```python
# config_flow.py
async def async_step_reauth(self, entry_data):
    self.reauth_entry = self.hass.config_entries.async_get_entry(
        self.context["entry_id"]
    )
    return await self.async_step_reauth_confirm()

async def async_step_reauth_confirm(self, user_input=None):
    errors = {}
    if user_input is not None:
        # Try login with new credentials
        try:
            await _try_login(
                self.hass,
                self.reauth_entry.data["username"],
                user_input["password"],
            )
            self.hass.config_entries.async_update_entry(
                self.reauth_entry,
                data={
                    **self.reauth_entry.data,
                    "password": user_input["password"],
                },
            )
            await self.hass.config_entries.async_reload(
                self.reauth_entry.entry_id
            )
            return self.async_abort(reason="reauth_successful")
        except (LoginFailed, ApiTokenError):
            errors["base"] = "invalid_auth"
    return self.async_show_form(
        step_id="reauth_confirm",
        data_schema=vol.Schema({vol.Required("password"): str}),
        errors=errors,
    )

# __init__.py — in async_setup_entry, when login fails with bad creds:
raise ConfigEntryAuthFailed("invalid_credentials")
```

### Why this benefits both the maintainer and the community

- Cuts the most-frequent Discord support question
- Removes a reason users churn the integration on every password rotation
- Aligns with HA core's standard pattern (search core for
  `async_step_reauth` — every well-maintained integration has one)

Happy to PR this if you'd like a starting point.

---

## Issue 2 — "API requests remaining today" sensor + repair issue at zero

**Title:** `feat: surface daily API request quota as a sensor + repair issue`

**Body:**

The MyCupra/MySeat portal has a per-day API call limit
(~1,500 across the official mobile app + any integration that polls).
When this is exhausted, the integration silently stops getting fresh
data until the cloud resets at ~02:00. Users typically notice when
their dashboards "freeze" but can't tell whether it's:

- Cloud outage
- Vehicle offline
- Privacy setting blocking
- Quota exhausted

A diagnostic sensor solves this:

- `sensor.<vehicle>_api_requests_remaining_today` —
  `state_class=total`, `entity_category=diagnostic`
- Updated from the response header / endpoint each time it's
  available (the OLA backend exposes a remaining counter; pycupra's
  connection layer already sees it but doesn't surface it)
- Optional: `entity_picture` shows a fuel-gauge-style icon

When `remaining_today == 0`, raise a HA Repair issue (via
`homeassistant.helpers.issue_registry.async_create_issue`) with:

- Title: "Daily API quota exhausted — fresh vehicle data not
  available until ~02:00 local"
- Description: explains the daily limit, that the vehicle is fine,
  what time the reset happens, and that polling can be reduced via
  Options Flow

### Why

- Most "the integration is broken" reports correlate with quota
  exhaustion when investigated
- Users who understand the limit can self-correct (raise their poll
  interval, enable nightly throttle if implemented, enable push)
- Reduces "broken" reports without code regressions

---

## Issue 3 — One-click "Retry login" action on auth-failure notification

**Title:** `feat: actionable notification when mid-session auth fails`

**Body:**

When tokens go stale mid-session (currently logged as
`Could not refresh tokens`), the integration creates a passive
warning notification. Users have to:

1. Read the notification
2. Navigate to Settings → Devices & Services → Integrations
3. Find the integration
4. Click "Reconfigure" → enter credentials

Home Assistant's `persistent_notification.async_create` supports
inline actions (via the Notify service buttons or the new
`HA action button` payload). The notification can include a single
"Re-authenticate now" button that triggers the reauth flow directly.

This pairs with Issue 1 above (`async_step_reauth`) — once that
exists, the action button just calls
`hass.config_entries.flow.async_init(domain, context={"source":
"reauth", "entry_id": entry.entry_id})`.

### UX win

- One click instead of four screens
- User stays in the dashboard view they were debugging
- Encourages prompt re-auth rather than ignoring the warning until
  data is days stale

---

## Issue 4 — Push-notification dispatcher hardening (unknown-type log + no-op)

**Title:** `fix: harden push-notification dispatcher against unknown notification types`

**Body:**

Looking at the v0.2.10 / v0.2.12 / v0.2.13 release notes, each shipped
handling for previously-unknown push types
(`charging-settings-failed-timeout`, `charging-error`,
`user-capabilities-change`, `vehicle-connection-state-online`,
`charging-stop-error`, `vehicle-wake-up-failed`).

This pattern of "VAG ships a new push type → integration crashes →
patch release" is preventable with a defensive dispatcher:

### Suggested pattern

```python
# push.py
HANDLERS = {
    "charging-error": _handle_charging_error,
    "charging-settings-failed-timeout": _handle_charging_timeout,
    "user-capabilities-change": _handle_user_caps_change,
    "vehicle-connection-state-online": _handle_connection_state,
    "charging-stop-error": _handle_charging_stop_error,
    "vehicle-wake-up-failed": _handle_wake_failed,
    # add new ones here as they're observed
}

async def dispatch(notification: dict) -> None:
    n_type = notification.get("type")
    handler = HANDLERS.get(n_type)
    if handler is None:
        _LOGGER.info(
            "Unknown push notification type %r — logged for follow-up "
            "(payload keys: %s). Please open an issue with the full "
            "anonymized payload.",
            n_type, list(notification.keys()),
        )
        return  # no-op — don't crash
    try:
        await handler(notification)
    except Exception:
        _LOGGER.exception(
            "Push handler for %r raised — recovering and continuing",
            n_type,
        )
```

### Plus regression-test fixtures

`tests/fixtures/push/` with one JSON per known type. A single
parametrized test verifies every known type round-trips through the
dispatcher without raising:

```python
@pytest.mark.parametrize("fixture", glob("tests/fixtures/push/*.json"))
async def test_known_push_type_does_not_crash(fixture):
    payload = json.load(open(fixture))
    await dispatcher.dispatch(payload)  # must not raise
```

Adding a new known type is then one line in `HANDLERS` + one fixture
file — no release-cycle gap.

---

## Issue 5 — Add hassfest + hacs/action GitHub Actions workflows

**Title:** `ci: add hassfest + hacs/action validation workflows`

**Body:**

The v0.2.7 release notes mention having to remove URLs from
`strings.json` / translation files because `hassfest` rejected them.
Without `hassfest` running in CI, this kind of regression can ship
silently and only get caught when a downstream user updates HA core
or HACS.

### Workflow 1: hassfest

```yaml
# .github/workflows/hassfest.yml
name: Hassfest
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master
```

### Workflow 2: hacs/action

```yaml
# .github/workflows/hacs.yml
name: HACS Validation
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration
```

### Why

- Catches `strings.json` URL regression
- Catches `manifest.json` schema drift (new HA core releases tighten
  the schema periodically)
- Catches missing `iot_class`, `config_flow`, `dependencies` etc.
- Pre-condition for ever applying to HACS Default Repository

---

## Issue 6 — Year-end / DST unit tests for estimated-end timestamps

**Title:** `test: add year-rollover + DST tests for estimated-end timestamp parsing`

**Body:**

Issue #33 (estimated-end timestamps showing the previous year) is a
classic date-arithmetic-against-API-strings bug. The class of bug is
worth covering with tests so it can't regress:

### Test cases that should be in `tests/test_datetime_boundaries.py`

```python
import pytest
from datetime import datetime, timezone, timedelta
from freezegun import freeze_time

@pytest.mark.parametrize("now,api_string,expected_year", [
    # Year-rollover: API says "in 7 hours", computed during 2025-12-31 23:00
    ("2025-12-31T23:00:00Z", "PT7H", 2026),
    # DST transition: API says "in 90 minutes" during the spring-forward hour
    ("2026-03-29T01:30:00+01:00", "PT1H30M", 2026),
    # Year-end "tomorrow at 06:00" inferred from time-of-day only
    ("2025-12-31T22:00:00Z", "06:00", 2026),
    # Leap day boundary
    ("2024-02-29T12:00:00Z", "PT24H", 2024),  # → 2024-03-01
])
def test_estimated_end_datetime_handles_boundaries(now, api_string, expected_year):
    with freeze_time(now):
        result = compute_estimated_end(api_string)
        assert result.year == expected_year
```

### Why

- Cheap insurance against a recurring class of bug
- `freezegun` is already a common test dep (or `pytest-freezer`)
- Explicit cases at year-end + DST transitions catch off-by-one bugs
  the rest of the year can't surface

---

## Issue 7 — Adopt MQTT freshness validation pattern

**Title:** `fix(mqtt): drop MQTT events older than the most recent API timestamp`

**Body:**

The Skoda HA stack hit a bug where MQTT push events arriving late or
out-of-order would overwrite fresher API data, causing SoC / charging
sensors to "jump back" mid-charging session. They fixed it in
`skodaconnect/homeassistant-myskoda` v1.31.1 by stamping each MQTT
event with the most recent API timestamp for that field and rejecting
events older than the snapshot.

The pycupra MQTT path has the same vulnerability — Firebase delivery
order is not guaranteed under load, and a `vehicle.charging.update`
event with a 30-second-old timestamp will currently silently
overwrite a fresh API poll.

### Suggested pattern (lifted from myskoda PR #536)

```python
# When applying any MQTT event:
def apply_mqtt_event(event: dict, snapshot: VehicleSnapshot) -> None:
    event_ts = parse_iso(event.get("timestamp"))
    snapshot_ts = snapshot.car_captured_timestamp
    if event_ts and snapshot_ts and event_ts <= snapshot_ts:
        _LOGGER.debug(
            "Dropping MQTT event %r — older than snapshot (event %s ≤ snap %s)",
            event.get("type"),
            event_ts.isoformat(timespec="seconds"),
            snapshot_ts.isoformat(timespec="seconds"),
        )
        return
    # apply the event...
```

### Why

- Eliminates the SoC graph "jump-back" UX bug
- Prevents long-term-statistics corruption (each spurious overwrite
  pollutes the recorder histogram for that minute)
- Tiny code change, one line of guard before the apply

Reference: skodaconnect/homeassistant-myskoda#1083 (MQTTv5 auth) +
the v1.31.1 release notes ("MQTT freshness validation").

---

## Issue 8 — FAQ: privacy-setting matrix mapping in-car settings → degraded entities

**Title:** `docs: FAQ — privacy-setting matrix (which entities degrade per privacy level)`

**Body:**

The most common first-week support pattern in the community is
"sensor X says unknown, sensor Y is empty, what's broken?" — and
the answer is almost always "the in-car privacy setting is stricter
than 'Share my position', and entities that depend on
location/parking-time/quota-counter degrade or stop completely."

A `FAQ.md` section that maps each in-car privacy setting to which
HA entities are affected would let users self-diagnose in 30 seconds.

### Suggested structure

```markdown
## Privacy settings — which entities are affected?

The MyCupra / MySeat in-car privacy menu has 3 levels (or 4 on some
firmware):

| Setting | Entities affected | Symptom |
|---|---|---|
| **Share my position** (most permissive — recommended for full integration use) | none affected | all sensors populate |
| **Use my position** (mid-level) | `device_tracker.*_position`, `sensor.*_parking_time`, `sensor.*_parking_address` | location goes "unknown" |
| **Don't share** (most restrictive) | `device_tracker.*`, `sensor.*_parking_*`, `sensor.*_requests_remaining`, plus charging timestamps degrade | most location-derived entities fail |

To change the setting:

1. Open the official MyCupra / MySeat app
2. Navigate to your vehicle → Settings → Privacy
3. Set to "Share my position"
4. Save
5. The change can take up to 5 minutes to propagate to the cloud
6. In Home Assistant: trigger a "Request full update" (or wait for
   the next poll) — affected sensors should populate

If sensors are STILL `unknown` 10 minutes after changing the
privacy setting:
- Check that the vehicle has cell coverage and is awake
- Verify in the app that the privacy setting actually saved
- Open a GitHub issue with anonymized diagnostics
```

### Why

- Cuts the second-most-common Discord support question
- 100% documentation, zero code change
- Format is reusable for `vag-connect-ha` and other integrations

---

## How to use these drafts

1. Open https://github.com/upstream/homeassistant-pycupra/issues/new
2. Copy a section (Issue 1 through 8) — title to the GitHub title
   field, body to the body field
3. Adjust wording if you'd like a different tone
4. Submit

If you'd like to PR any of these instead of opening as feature
requests, fork the repo and reference the issue number in the PR
description.
