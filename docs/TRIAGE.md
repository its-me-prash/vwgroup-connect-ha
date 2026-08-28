# How issues get triaged

> This integration is maintained by one person, on their own time, against
> a backend that Volkswagen keeps changing. This page explains — honestly —
> how a report travels from your Home Assistant instance to a fix in a
> release, so you know what to expect and can help the process along.

It's descriptive, not a promise: there are no service-level guarantees here.
Good reports get fixed faster, and every reporter gets a real reply and a
credit. That's the deal.

---

## Pick the right template

Open a report at
[**Issues → New issue**](https://github.com/its-me-prash/vwgroup-connect-ha/issues/new/choose).
Blank issues are disabled on purpose — the templates ask the handful of
questions that otherwise cost a round-trip to get answers to.

| Template | Use it when | Auto-label |
|---|---|---|
| 🐛 **Bug Report** | A feature works in the manufacturer app but not here, or an entity shows something wrong. | `bug` |
| 💡 **Feature Request** | A sensor, command or capability is missing and you'd like it added. | `enhancement` |
| 🚗 **Brand live-test report** | You want to report whether your brand/model works — especially the ones still short on real-car testing (Porsche, VW US/CA, VW Commercial, broader Škoda). | `testing` |
| 🚨 **Error Reporter** | You clicked "Mehr erfahren" on the HA Error-Reporter repair notification — it opens this pre-filled. | `error-report`, `needs-triage` |
| 🛰️ **Vehicle Data Scout Report** | You clicked "Mehr erfahren" on the Scout repair notification — the integration found a backend field it doesn't recognise yet. | `scout-report`, `needs-triage` |

Not a bug and not sure where it fits? The template chooser also links out to:

- **Discussions** — general questions, dashboard examples, community exchange.
- **HA Community Forum** — general Home Assistant questions.
- **Security vulnerability** — report it *privately* (see [Security](#security-goes-somewhere-else) below), never as a public issue.

The two auto-generated templates (Error Reporter, Vehicle Data Scout) come
from features inside the integration: the report is built on your device,
masked there, and nothing leaves HA until you click through and submit.

---

## What a good report contains

The Bug Report template asks for these because each one changes the answer:

- **VW Group Connect version** (from `manifest.json` / the integration page)
- **Home Assistant version**
- **Brand, model + year**
- **Country / region** — some endpoints and entitlements differ by market
- **Does the same action work in the official manufacturer app?**
- **Is the connected-services subscription active?** — some brands block
  commands server-side when a plan lapses; that isn't a bug here
- **Is an S-PIN configured?** — required for lock and some other commands
- **Sanitised logs** — HA → Settings → System → Logs, filter `vag_connect`
  (enable *Enable debug logging* on the integration first)
- **Diagnostics** — Settings → Devices & Services → VW Group Connect → ⋮ →
  *Download diagnostics*. Sensitive fields auto-redact on current versions.

Logs and diagnostics are what make a report reproducible. A one-line "it
doesn't work" almost always comes back with "can you attach the debug log?",
so attaching it up front saves a day.

### Redact before you paste

**Diagnostics redact the sensitive fields for you.** A raw HA log does not —
so if you paste log text, mask it yourself first. The templates require you
to confirm you've done this:

- **VIN** → keep only the last 6 characters, e.g. `***003577`. A full VIN
  ties to registration, insurance and ownership records.
- **Tokens** (`access_token`, `refresh_token`, `id_token`) → remove entirely.
- **S-PIN** → never share, not even masked.
- **Email** → mask the local part, e.g. `u***@***.com`.
- **GPS** (`latitude`, `longitude`) → round to 1 decimal, or remove.
- **Account ID / user_id** (UUIDs) → remove.

If something slips through, say so in the issue and the maintainer will edit
it out — but the masking is on the reporter first. The full maintainer-side
data-handling rules live in
[`CONTRIBUTING.md`](../CONTRIBUTING.md#privacy--data-handling-added-2026-04-30-after-53-review).

---

## Triage yourself first (it might not be a bug)

A "command failed" isn't always a code defect. The
[FAQ in CONTRIBUTING.md](../CONTRIBUTING.md#faq--subscription--service-plus--paid-plans-closes-47)
carries the full decision table; the short version — check the error body:

| What you see | Likely cause | Who fixes it |
|---|---|---|
| `missing-capability` | The server says this VIN doesn't have the feature (region / trim / firmware). | Not fixable here — the entity gets hidden, like the app hides the button. |
| `subscription_expired` / `not_entitled` | Paid plan lapsed. | Renew in the manufacturer portal. |
| `spin_error` with `spinState: "DEFINED"` | The command needs an S-PIN. | Configure the S-PIN in the integration options. |
| `Bad Gateway` / `4007` / `4111` | Transient backend hiccup. | Usually clears on retry. |
| `404 Not Found` | Endpoint doesn't exist for that vehicle's API profile. | May need new code — worth a bug report. |
| `403`, no body | Auth token expired, retry budget exceeded, or a temporary rate limit. | Restart the integration; report if it persists. |

If your case is genuinely one of the top three, a Discussion or a comment is
usually a faster path to an answer than a bug report. If it's a `404`, a
scout finding, or the official app clearly does something we don't — that's a
real bug and very welcome.

---

## How the maintainer works a report

Once a report lands, the loop is roughly:

1. **Read it and reply.** Every reporter gets a substantive answer — a
   question, a diagnosis, or "reproduced, fixing it" — not a canned close.
   Replies are written in the reporter's own language where it's inferable
   from the Country field or how the issue was written; English otherwise.
2. **Reproduce.** With the log/diagnostics, against a fixture where possible.
   A real-world payload that gets turned into a regression test is first
   anonymised (VIN, tokens, IDs, GPS stripped) — and only with the reporter's
   consent. See the fixture rules in
   [`CONTRIBUTING.md`](../CONTRIBUTING.md#what-goes-in-the-repo--fixtures--commits).
3. **Locate it in code.** Find the brand client, parser, or coordinator path
   that's actually wrong — not a symptom patch.
4. **Fix on a branch, with a test.** One PR = one concern. New behaviour
   ships with a test (a parser test, an entity test, or a coordinator
   dispatch test), the CHANGELOG is updated, and CI has to be green:
   `ruff`, `mypy --strict`, JSON validation, and a check that the CHANGELOG
   mentions the version. Fixes go through a PR, not straight to `main`.
5. **Release and credit.** When the fix ships, the issue is closed with a
   note (never silently), the reporter is thanked in the release, and their
   handle is added to the contributor list.

Scout reports have their own handling rules — a new field is *parsed and
surfaced*, not just silenced. That policy is written up in full in
[`docs/SCOUT_POLICY.md`](SCOUT_POLICY.md).

---

## Labels you'll see

Labels here are lightweight. Picking a template applies the first one for
you:

| Label | Meaning |
|---|---|
| `bug` | A defect to reproduce and fix. |
| `enhancement` | A requested feature or new capability. |
| `testing` | A live-test / brand-verification report. |
| `error-report` | Auto-generated from the in-app Error Reporter. |
| `scout-report` | Auto-generated from the Vehicle Data Scout. |
| `needs-triage` | New auto-generated report, not yet looked at. |

A few more come from automation rather than issue triage — `ci` and
`dependencies` on Dependabot's grouped Action-bump PRs, and internal
watcher workflows raise their own tracking issues (e.g. `auth-status-change`
when the VW EU login state shifts). You don't need to touch those.

There's deliberately no sprawling priority/severity taxonomy — with one
maintainer, an elaborate label scheme would be theatre. The state that
matters is "has this been reproduced and is there a branch," and that lives
in the issue thread.

---

## Every reporter gets credited

This isn't a courtesy afterthought, it's a rule:

- **A real reply** on the issue, in the reporter's language where possible —
  full coverage, meaning everyone who added information gets addressed, not
  just the original poster.
- **A Thanks line in the [CHANGELOG](../CHANGELOG.md)** for the release that
  carries the fix — e.g. *"Thanks @yourhandle"* right next to the change.
- **An entry in [CONTRIBUTORS.md](../CONTRIBUTORS.md)** — everyone who filed a
  report, sent diagnostics, requested a feature, tested on a real car, or
  took part in a discussion.

If you contributed and don't see yourself listed, that's an oversight, not a
snub — open an issue and it gets fixed.

---

## Security goes somewhere else

Please don't file a suspected vulnerability as a public issue. Report it
privately through
[**GitHub Security Advisories**](https://github.com/its-me-prash/vwgroup-connect-ha/security/advisories/new),
as described in [`SECURITY.md`](../SECURITY.md). That keeps users safe while
a fix is prepared.

---

## A note on pace

There's no SLA and there won't be one — this is one person against a moving
backend. What travels furthest is a well-redacted report with a debug log and
the template fields filled in. Patches and patience go a long way; demands
don't. Thanks for helping keep it alive.
