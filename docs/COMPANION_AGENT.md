# Companion agent protocol (v4.4.0, experimental)

The companion channel drives the manufacturer's own Android app on a spare
phone and reads the values off the screen. Until now Home Assistant had to
reach **into** the phone to do that — ADB over TCP directly, or the
[ADB Bridge add-on](https://github.com/its-me-prash/vwgroup-app-adb-bridge)
doing the same with a real `adb` binary.

That direction is where setups fail. Android 11+ wireless debugging has to be
paired by hand and switches itself off, phone IPs move under DHCP, and guest or
IoT networks with client isolation block the connection outright ([#968]).

The **agent relay** inverts it. A small app on the phone opens an ordinary
outbound HTTPS request to Home Assistant and holds it open; HA answers with the
next command when it has one, and the agent posts the result back on its next
poll. Nothing has to reach the phone, so NAT, changing IPs, client isolation and
wireless debugging all stop mattering.

This document specifies that protocol. It is the contract between
`custom_components/vag_connect/companion/relay.py` and any agent app; an agent
written against this file alone will work.

> **Status.** The Home Assistant side ships in v4.4.0 and is covered by tests.
> The phone-side agent app is a separate artifact and is **not** part of this
> repository yet — see "Writing an agent" below.

## Shape

One endpoint, one direction, one command in flight:

```
POST /api/vag_connect/companion_agent
X-Agent-Token: <the entry's agent token>
Content-Type: application/json
```

The endpoint is unauthenticated in Home Assistant's sense (a phone has no HA
user) and is gated entirely by the token, compared with `hmac.compare_digest`.
A token resolves to exactly **one** config entry; if two entries carry the same
token the lookup fails closed rather than binding the phone to an arbitrary car.
Give every vehicle its own token, at least 32 random characters. Prefer an HTTPS
URL: over plain HTTP the token crosses the LAN in the clear.

### Request (agent → HA)

```json
{
  "agent_version": "1.0.0",
  "app_version": "4.3.2",
  "battery": 58,
  "result": { "id": "c17", "ok": true, "value": "<hierarchy …/>" }
}
```

| Field | Meaning |
|---|---|
| `agent_version` | The agent app's own version. Heartbeat only. |
| `app_version` | Version of the manufacturer app on the phone. Heartbeat only — the version gate reads it through the `app_version` verb. |
| `battery` | Phone battery percentage, 0–100. Heartbeat only. |
| `result` | The answer to the command from a previous poll, if any. |

`result.ok: false` with `result.error` fails that command on the HA side with
the given reason. A result for a command that already timed out is dropped: the
caller has moved on, and so has the screen.

### Response (HA → agent)

```json
{ "command": { "id": "c18", "verb": "dump_ui", "args": {} } }
```

or, when the hold window (25 s) elapsed with nothing to do:

```json
{ "command": null }
```

Either way the agent polls again immediately. An unknown token answers HTTP 404
— the same answer as "no such entry", so an unauthorised caller learns nothing
about which tokens exist.

## Verbs

The vocabulary is deliberately short. A non-rooted phone has no shell for an app
to run anyway, and keeping it this narrow means a compromised Home Assistant
cannot ask the phone for anything the companion channel does not already do.

| Verb | Args | Returns |
|---|---|---|
| `dump_ui` | — | The visible accessibility tree as `uiautomator dump` XML (string) |
| `tap` | `x`, `y` | anything (ignored) |
| `swipe` | `x1`, `y1`, `x2`, `y2`, `duration_ms` | ignored |
| `back` | — | ignored |
| `foreground` | `package` | ignored |
| `is_foreground` | `package` | boolean |
| `app_version` | `package` | version string, or null |
| `wake` | — | ignored |
| `sleep` | — | ignored |

`dump_ui` is the one that matters: the agent serialises Android's live
accessibility node tree into the same XML shape `uiautomator dump` produces, so
every selector in `companion/presets.py` and all of `companion/screen.py` work
unchanged across all three transports. At minimum each node needs
`resource-id`, `content-desc`, `text`, `class`, `clickable` and `bounds`.

## Setting it up

1. Install and start an agent app on the phone, sign the manufacturer app in,
   and leave it on the vehicle overview.
2. Generate a random token in the agent (≥ 32 characters) and give it the Home
   Assistant base URL.
3. In Home Assistant add **VW Group Connect → Companion phone**, tick **Use the
   companion agent app**, paste the same token, and leave the address field
   empty.
4. The entry waits for the agent's first poll; diagnostics then report
   `companion_relay` as the source channel.

Everything above the transport is unchanged: the same brand presets, the same
write quarantine, the same app-version gate, the same opt-in nav reads.

## Writing an agent

An agent needs to do three things: hold the outbound poll, answer the verbs
above, and serialise the accessibility tree. On Android that means an
`AccessibilityService` — the app observes the **visible** UI of the
manufacturer app and performs only the gestures Home Assistant asks for. It must
not read the manufacturer app's storage, its credentials or its private API
tokens, and it must not intercept traffic; the whole contract is *screen in,
taps out*, exactly as for the ADB transports.

Two rules an agent must keep:

- **Only the manufacturer app.** Restrict the service to the manufacturer app's
  package; never dump or drive anything else on the phone.
- **The token goes to exactly one host.** The configured Home Assistant URL,
  and nowhere else, ever.

[#968]: https://github.com/its-me-prash/vwgroup-connect-ha/issues/968
