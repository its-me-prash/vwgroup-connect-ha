# Attribution & Naming Requirements

This project — **VW Group Connect** (`vag_connect`), repository
[`its-me-prash/vwgroup-connect-ha`](https://github.com/its-me-prash/vwgroup-connect-ha),
created and maintained by **Prash Balan ([@its-me-prash](https://github.com/its-me-prash))** —
is licensed under the **GNU Affero General Public License v3.0 or later** (see
[`LICENSE`](LICENSE)). The reverse-engineering research under `docs/research/`
is additionally licensed **CC BY-NC-ND 4.0** (see `LICENSE-RESEARCH`).

If you use, fork, port, vendor, or build upon ANY part of this project, the
AGPL-3.0 requires you to **keep your source open under the same license** —
including network/hosted use. In addition, the following attribution and naming
terms apply:

## 1. Mandatory attribution

Any derivative, fork, or product that incorporates code, methods, or
discoveries from this project MUST, in its README (or equivalent primary
documentation) and its in-app/about credits, clearly and visibly state:

> Based on **VW Group Connect** (`vag_connect`) by **@its-me-prash** —
> https://github.com/its-me-prash/vwgroup-connect-ha

The credit must name **both** the project/repository name **and** that it is
the integration the code/feature was taken from. Removing, obscuring, or
relocating this attribution out of the primary documentation is a license
violation.

## 2. Originating research credit

The VW Group connectivity reverse-engineering in this project — including the
cross-brand app-atlas, the OAuth `client_id`/auth-scheme catalogue, and the
specific discovery of how to obtain durable, refreshable vehicle access on the
App-Check-gated brands — originated here. Derivative works that rely on these
findings must credit this project as the origin of the discovery.

### Referenced open-source projects (reimplemented with attribution)

We independently re-implement — never copy — from these projects; endpoint
shapes and flows were cross-checked against their sources for grounding:

- **pyporscheconnectapi** (Apache-2.0) — original Porsche Connect auth flow.
- **hass-vw-eu-data-act** and **HA_VAG-EU-Data-Act** — community EU-Data-Act
  portal readers; their read-only design + issue history informed our
  auto-provisioning approach (we create the data request they require by hand).
- **WeConnect-python**, **CarConnectivity-connector-audi/-volkswagen/-seatcupra**,
  **volkswagencarnet**, **pycupra**, **evcc** — CARIAD-BFF / MBB / OLA endpoint +
  `client_id` grounding.

### Community credit

- The `650d46ca` VW-EU device-authorization client that our opt-in **VW EU
  Two-Way** channel uses was first surfaced by community researcher **@magicus**.
  We independently probed and confirmed it against a live account and
  re-implemented the login flow (never copied), with our own multi-channel +
  security design. Credit to **@magicus** for surfacing the device-grant client.

## 3. Name / trademark

The names **"VW Group Connect"**, **"VAG Connect"** and **"vwgroup-connect-ha"**, together with the
project's branding, are asserted as the unregistered trademarks of the author.
You may exercise your AGPL rights over the **code**, but you may **not**:

- present a fork or derivative under these names or confusingly similar names,
- imply endorsement by, or affiliation with, the author or this project,
- strip the project name from attribution while reusing the code.

Use of the name for a fork requires written permission from the author.

## 4. Support the project

This work — including the VW Group connectivity reverse-engineering and the
durable two-way auth research — took significant effort. If it is useful to you
or your product, please support it via **GitHub Sponsors**
([@its-me-prash](https://github.com/sponsors/its-me-prash)). Commercial users
relying on the AGPL code or the findings are especially encouraged to sponsor.

---

*Not legal advice. These terms supplement — they do not replace — the AGPL-3.0
in `LICENSE`. Questions / permission requests: open an issue or contact
[@its-me-prash](https://github.com/its-me-prash).*
