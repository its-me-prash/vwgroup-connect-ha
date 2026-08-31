# v3.0.0 "Bazinga" — Škoda beta tester-recruitment issue · DRAFT (nothing posted)

> **HARD GATE:** DRAFT. Nothing gets posted and no one gets tagged without
> Prash's explicit OK — and the wave must be pushed + the **3.0.0 beta tagged
> FIRST** (right now `feat/skoda-wave` is held and unpushed, so testers would
> have nothing to install). Re-check every handle against the CLAUDE.md
> do-not-ping blocklist before any tag.
>
> **Play:** open the ONE opt-in thread below and let people self-select. Do NOT
> mass-@-tag the 19 handles — it reads as spam. If you tag at all, tag only the
> few most-relevant recent reporters whose exact issue a feature fixes, in the
> comment that announces the thread. Curated Tier-1 list is in
> `vag_connect_laura_mvp_gtm` memory (foobarth / tader / RaAdNe / divanguz-alt /
> Chr1sDub) — none currently on the blocklist; re-verify.

---

**Title:** `Škoda v3.0.0 "Bazinga" beta — Laura AI in HA, send-to-car, per-location SoC, camping, charge-telemetry fixes — comment to join`

---

**What's new in the Škoda "Bazinga" wave (v3.0.0)**

A big Škoda surface built against the MyŠkoda 8.15.0 app. All of it is opt-in and none of it is required for existing users.

**"Laura" — the MyŠkoda in-car assistant, now in Home Assistant (read-only)**
- New service `vag_connect.ask_assistant` — ask the in-car AI about EV route / charging planning and Škoda product questions. Returns a text answer + a `session_id` you can pass back for follow-ups. She can also be handed to your **conversation agent** (built-in Assist in LLM mode, or OpenAI / Anthropic / Google / Ollama) as a tool it can call and chain. Advisory only — Laura never drives the car. See [docs/AI_ASSISTANT.md](../AI_ASSISTANT.md).

**Commands (some are live-gated — see below)**
- `vag_connect.send_destination` — push a navigation destination to the car's infotainment (now Škoda, not just SEAT/CUPRA).
- `vag_connect.set_location_target_soc` — per-charging-profile (per-location) target SoC.
- `vag_connect.set_seat_heating` — front / rear seat heating.
- Camping switch, auto-unlock-plug switch, aux-heating.

**New read-only sensors / entities**
- Preferred charge mode, departure timers, aux / camping / window-heating state.
- Last fill-up (fuel, amount, cost, station, time) for PHEVs.
- Current pay-to-park session (location, cost, start/end, still-running).
- Service reminders: technical inspection, seasonal tyre change, first-aid kit, tyre-repair kit.
- Mandatory & marketing consent state, plus a **mandatory-consent Repair** that self-heals the T&C / consent wall.

**Charge-telemetry fixes (all brands, not only Škoda)**
- **#1090** — charging power / rate now drop to **0** the moment a charge stops, instead of showing the last value for minutes (seen on the Audi e-tron GT).
- **#1088** — the state-of-charge no longer sticks on a stale value when a Volkswagen EU data export lists the battery field twice.

**What we'd love you to test** — pick whatever matches your car, you don't need to test everything.

- **Laura / `ask_assistant`:** EV route + charging-stop prompts ("plan a route to X with charging stops, I'm at Y%") and product questions. Are the answers accurate and useful? Does multi-turn (`session_id`) continuity work? *(Newest, least-battle-tested feature — your feedback here matters most.)*
- **send-to-car (`send_destination`):** does a destination actually arrive on your infotainment? *(Live-gated — report if it silently no-ops.)*
- **Per-location target SoC:** Enyaq / Elroq owners especially — does a per-location target stick?
- **Camping + auto-unlock-plug switches:** toggle, check state + the camping auto-stop attribute.
- **Seat heating / aux-heating:** *(live-gated)* report actuation success/failure.
- **Service reminders + departure timers:** do the values match the app?
- **Charge telemetry (#1090):** after a charge finishes, does power/rate go to 0 promptly?

**How to install the beta**

VW Group Connect is a **default HACS integration**, so there's no custom repository to add:

1. In **HACS**, search for **"VW Group Connect"** and open it.
2. Three-dot menu → **Redownload** → enable **"Show beta versions"**, pick the `3.0.0` beta once it's tagged, download, and **restart** Home Assistant.
3. Reload the integration — new Škoda entities appear automatically for exposed vehicles.

*(Backup tip: snapshot your HA config before installing a beta.)*

**How to report** — please include, per issue:
- Brand + model + year (e.g. Enyaq 2024, Octavia iV 2023) and whether it's BEV / PHEV.
- The exact service call or entity, what you expected, what happened.
- For command failures: the HA log lines around the call (redact your VIN / tokens).
- For Laura: paste the prompt and her summary (redact anything personal) so we can judge answer quality.

**Want in?** Comment with your Škoda model + which features you can test, and we'll keep this thread updated as fixes land. Thanks for helping shape the Škoda wave. 🚗⚡
