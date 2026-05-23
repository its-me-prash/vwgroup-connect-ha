# NOTICE — VW Group Connect for Home Assistant

## No Runtime Dependencies

VW Group Connect has zero external runtime dependencies (`requirements: []`).
The integration communicates directly with manufacturer APIs using Home
Assistant's built-in `aiohttp` session.

---

## Research Attribution

The API endpoints, authentication flows, and client IDs used in this
integration were discovered through publicly available open-source research.
The following MIT/Apache-2.0 licensed projects were used as **reference only**
— no source code was copied from any of them:

| Project | License | Used for |
|---|---|---|
| [audiconnect](https://github.com/audiconnect/audi_connect_ha) | MIT | Audi API endpoint reference |
| [myskoda](https://github.com/skodaconnect/myskoda) | MIT | Škoda API endpoint reference |
| [pycupra](https://github.com/WulfgarW/pycupra) | Apache-2.0 | SEAT/CUPRA API reference |
| [pyporscheconnectapi](https://github.com/CJNE/pyporscheconnectapi) | MIT | Porsche API reference (v0.15.0) |
| [CarConnectivity-connector-audi](https://github.com/acfischer42/CarConnectivity-connector-audi) | MIT | Audi client_id reference |
| [CarConnectivity-connector-volkswagen-na](https://github.com/zackcornelius/CarConnectivity-connector-volkswagen-na) | MIT | VW NA auth reference (v0.16.0) |

All API endpoints, authentication methods, and client IDs are functional
facts discovered from public sources — they are not copyrightable. The
integration code itself is an original clean-room implementation.

---

## Trademark Notices

The following brand names and trademarks are the exclusive property of their
respective owners. Their use in this project is purely descriptive
(nominative fair use) to identify the vehicles and services this software is
compatible with. This project is **not** affiliated with, endorsed by, or
associated with any of these companies.

| Trademark | Owner |
|---|---|
| Audi, myAudi, Audi Connect | Audi AG, Ingolstadt, Germany |
| Volkswagen, VW, WeConnect | Volkswagen AG, Wolfsburg, Germany |
| CARIAD | CARIAD SE, Berlin, Germany (subsidiary of Volkswagen AG) |
| Škoda, MyŠkoda | Škoda Auto a.s., Mladá Boleslav, Czech Republic |
| SEAT, My SEAT | SEAT, S.A., Barcelona, Spain |
| CUPRA, MyCupra | CUPRA Automóvil S.L., Barcelona, Spain |
| Porsche, My Porsche | Dr. Ing. h.c. F. Porsche AG, Stuttgart, Germany |
| Home Assistant | Nabu Casa, Inc. |

---

## Unofficial API Disclaimer

This software interacts with vehicle manufacturer APIs in the same way their
official mobile applications do. These are **unofficial, undocumented APIs**
that may change without notice. Use at your own risk. The authors of this
project are not responsible for any consequences arising from the use of this
software, including but not limited to account suspension or data loss.

---

*Copyright 2026 Prash Balan (@its-me-prash) — Apache License 2.0*
