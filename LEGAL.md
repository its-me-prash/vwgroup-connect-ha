# Legal basis & attribution

## Why this integration is lawful

VW Group Connect lets a vehicle's **owner** access data their own car already
produces, for personal smart-home use. That use rests on:

- **EU Software Directive 2009/24/EC, Art. 6** (interoperability exception) —
  and its national transpositions **§69e UrhG** (Germany) and **Art. 21 URG**
  (Switzerland). Reverse-engineering the minimum necessary to make an
  independently-created program interoperate is permitted for a lawful user.
- **EU Data Act — Regulation (EU) 2023/2854, Arts. 4–6** — gives users the
  right to access the data their connected product generates, and to share it
  with a third party of their choice on fair, reasonable, non-discriminatory
  terms. Core access obligations apply from 12 September 2025; in-situ design
  obligations from 12 September 2026.
- **DMCA §1201(f)** (USA) — the interoperability carve-out, relevant because
  the project is hosted on GitHub.

We use only client identifiers and flows that are reachable by any owner with
a working account, derived from clean-room observation of public web/app
protocols. We do **not** embed or impersonate any third-party commercial
partner's credentials.

## VW EU Data Act portal connector

As of June 2026 every token-based WeConnect auth route is closed to
third-party tools (hybrid OIDC blocked, public-client code-exchange
unsupported, device-grant disabled for the VW client). The integration's VW
passenger-car path therefore uses the **EU Data Act portal**
(`eu-data-act.drivesomethinggreater.com`) — the route VW must keep open under
the Data Act. It is read-only, runs on a ~15-minute cadence, and requires the
owner to enable a one-time "continuous data request" on the portal.

The portal connector's login mechanics and `/proxy_api` endpoint paths were
adapted from MIT-licensed community projects that independently
reverse-engineered the portal's public web flow:

- the CarConnectivity VW EU Data Act connector (MIT)
- the Home Assistant VW EU Data Act integration (MIT)

The OIDC hybrid-flow reference (for the now-closed WeConnect path) came from:

- the `volkswagencarnet` library (Apache-2.0), PR #333
- the CarConnectivity Volkswagen connector (MIT), PR #109

All field-name and endpoint research is cross-checked against the upstream
brand libraries (`pycupra`, `myskoda`, `audi_connect_ha`) before shipping.
License notices for adapted code are preserved per the MIT/Apache-2.0 terms;
where a project is identified by its public package/repository name the
attribution is to the project, not to any individual.

## Good-faith response to rights holders

We respond promptly to good-faith requests from rights holders, while
reserving all rights under the statutes cited above. Open an issue or contact
the maintainer.
