# v3.0.0 "Bazinga" (Škoda Wave) — Advertising copy · FINAL (for Prash to post)

> v3.0.0 is **live** (full release, HACS-listed). Tester thread:
> https://github.com/its-me-prash/vwgroup-connect-ha/issues/1098
> Post these where it fits; reply in-thread; no mass-tagging.

---

## A. Home Assistant Community Forum (English)

**Title:** VW Group Connect 3.0.0 — big Škoda update: in-car "Laura" assistant in HA, send-to-car, per-spot charge targets

**Body:**

Hi all — a large update just landed for **VW Group Connect** (the default-HACS integration for Volkswagen-Group cars: Audi, VW, Škoda, SEAT, CUPRA, Porsche, Bentley + VW/Audi US-CA). This one is **Škoda-heavy**:

- **"Laura" — the in-car MyŠkoda assistant — usable from Home Assistant.** Ask it about range/charging or a trip and the answer comes back into HA, so your voice assistant or LLM agent (built-in Assist, OpenAI, Anthropic, Google, Ollama) can use it too.
- **Send a destination to the car**, **per-location charge target**, **camping** & **auto-unlock-plug** switches, **seat heating**.
- **Read-only extras:** last fill-up, parking sessions, service reminders, departure timers, battery state-of-health, and more.
- Also across brands: charging power now zeroes the moment a charge stops, and a VW-EU state-of-charge oscillation is fixed.

It's **free and open-source (AGPL)**, runs alongside evcc, and needs no add-on or broker.

**Install:** HACS → **VW Group Connect** → update to 3.0.0 → restart. Pick Škoda; passwordless login supported.

Škoda owners: there's a thread to share feedback on the new features (especially Laura, which is brand new): https://github.com/its-me-prash/vwgroup-connect-ha/issues/1098 — repo: https://github.com/its-me-prash/vwgroup-connect-ha

If it's useful to you, sponsoring keeps the reverse-engineering going: https://github.com/sponsors/its-me-prash 🙏

---

## B. Facebook — short post (English)

Škoda + Home Assistant folks 👋 Big **VW Group Connect 3.0.0** is out (free, open-source): your car's own **"Laura" assistant now works inside Home Assistant**, plus **send-a-destination-to-the-car**, **per-spot charge targets**, camping mode, seat heating, and read-only sensors (fill-ups, parking, service reminders, battery health…). Works with your HA voice assistant / LLM, so "car arrives home → top up + pre-heat + tell me the range" is a real automation.

Update via HACS (VW Group Connect → 3.0.0), pick Škoda, done. Feedback thread + repo:
→ https://github.com/its-me-prash/vwgroup-connect-ha/issues/1098
→ https://github.com/its-me-prash/vwgroup-connect-ha
Support it: https://github.com/sponsors/its-me-prash 🚗⚡

---

## C. Facebook — kurze Version (Deutsch)

Škoda- und Home-Assistant-Leute 👋 **VW Group Connect 3.0.0** ist da (kostenlos, Open Source): der **hauseigene „Laura"-Assistent läuft jetzt in Home Assistant**, dazu **Ziel-ans-Auto-senden**, **Ladeziel pro Standort**, Camping-Modus, Sitzheizung und viele Nur-Lese-Sensoren (Tankvorgänge, Parken, Service-Erinnerungen, Batteriegesundheit …). Funktioniert mit deinem HA-Sprachassistenten / LLM — „Auto kommt heim → laden + vorheizen + Reichweite ansagen" ist damit eine echte Automation.

Update über HACS (VW Group Connect → 3.0.0), Škoda auswählen, fertig. Feedback + Repo:
→ https://github.com/its-me-prash/vwgroup-connect-ha/issues/1098
→ https://github.com/its-me-prash/vwgroup-connect-ha
Unterstützen: https://github.com/sponsors/its-me-prash 🚗⚡

---

## Guardrails (do NOT put in the public copy)
- Don't name/compare competitor projects. Don't over-promise Laura's answer quality — it's new; honest "try it, feedback wanted" is deliberate.
- Don't @-tag maintainers or mass-tag users. HA forum: one post, no cross-posting, no self-promo spam.
