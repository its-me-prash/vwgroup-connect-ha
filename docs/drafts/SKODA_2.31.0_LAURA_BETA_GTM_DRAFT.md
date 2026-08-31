Grounded: `feat/skoda-wave` branch exists (tip `4c1cfeb`), `ask_assistant` service is real (services.yaml:607), manifest is `dependencies: []` / version `2.30.3` (research said 2.30.2 — minor drift, noted). Here is the deliverable.

---

# MyŠkoda "Laura" + Škoda 2.31.0 Wave — Product & Release Decision Pack (DRAFT)

*Status: DRAFT for Prash. Nothing posted, tagged, or pushed. Branch `feat/skoda-wave` is HELD (tip `4c1cfeb`, current manifest v2.30.3 → bump to 2.31.0 at release). Two facts still need a LIVE probe before shipping the MVP — flagged in Part 1.*

---

## Part 1 — Laura MVP Spec

### What the MVP is

The MVP is **already ~80% built**: the `vag_connect.ask_assistant` service exists (services.yaml:607, handler `__init__.py:814`) and returns a `response_variable` of `{summary, type, session_id}`. That alone makes Laura usable *today* from any HA automation via `response_variable` + a sentence trigger (no new code). The remaining MVP deliverable is the **HA-AI coupling**: exposing Laura and the key Škoda commands as **LLM tools** so HA's built-in Assist (in LLM mode) *and* any 3rd-party conversation agent (OpenAI / Google / Ollama / Anthropic) can call and chain them.

### The exact current mechanism (2026.8)

Everything routes through one abstraction in `homeassistant.helpers.llm`: a **`Tool`** (name + description + `vol.Schema` params + `async_call`) that lands in an `APIInstance.tools` list. Every conversation agent — built-in Assist LLM mode, OpenAI, Anthropic, Google, Ollama — consumes that identical list through the shared `conversation.ChatLog`, converts each tool's schema with the same helper (`voluptuous_openapi.convert(tool.parameters, custom_serializer=…)`), and dispatches back through `APIInstance.async_call_tool(...)`. The tool's returned dict is fed straight back to the model as a tool result — **that return-dict is exactly what makes Laura's prose chainable** (the agent reads her `summary` and can then call `send_destination`).

**There are two ways in, and the MVP should ship BOTH (they share one list of `Tool` classes — cheap):**

| Path | HA versions | UX | Notes |
|---|---|---|---|
| **(A) `llm.py` platform** — export `async_get_tools()` returning `LLMTools(tools, prompt)` | **2026.8.0+ only** | Cleanest: folds into the default "Assist" API every agent already has selected. Zero user config, coexists with built-in device tools. | New protocol `LLMToolsPlatformProtocol` in `homeassistant/components/llm/__init__.py`. Gate on `if api_id != LLM_API_ASSIST: return None`. |
| **(B) Custom API** — `llm.async_register_api(hass, VagConnectAPI(...))` | **~2024.6+ (all current)** | User must select "VW Group Connect" under the agent's *Control Home Assistant* option. On 2026.8+ it merges with Assist (`MergedAPI`, tools namespaced `vag_connect__…`); on older single-select builds it *replaces* Assist. | Version-robust fallback. |

### Minimal code sketch

Ship `custom_components/vag_connect/llm.py` with the `Tool` subclasses, wire the platform (A), and register the custom API (B) in `__init__.py`. Both consume `_TOOL_CLASSES`.

```python
# custom_components/vag_connect/llm.py
import voluptuous as vol
from homeassistant.helpers import config_validation as cv, llm
from .const import DOMAIN

class AskAssistantTool(llm.Tool):
    name = "skoda_ask_assistant"
    description = (
        "Ask the MyŠkoda in-car AI 'Laura' about EV route/charging planning or "
        "Škoda product questions for one vehicle. Read-only advisory — cannot control "
        "the car. Returns a text summary you can act on (e.g. then call "
        "skoda_send_destination). Pass the returned session_id back to continue.")
    parameters = vol.Schema({
        vol.Required("vin"): cv.string,
        vol.Required("prompt"): cv.string,
        vol.Optional("timezone"): cv.string,
        vol.Optional("session_id"): cv.string,
    })
    async def async_call(self, hass, tool_input, llm_context):
        result = await hass.services.async_call(
            DOMAIN, "ask_assistant", dict(tool_input.tool_args),
            blocking=True, return_response=True, context=llm_context.context)
        return {"success": True, **(result or {})}   # -> {summary, type, session_id}

class SendDestinationTool(llm.Tool):
    name = "skoda_send_destination"
    description = "Send a navigation destination to the Škoda infotainment."
    parameters = vol.Schema({
        vol.Required("vin"): cv.string,
        vol.Optional("latitude"): vol.Coerce(float),
        vol.Optional("longitude"): vol.Coerce(float),
        vol.Optional("name"): cv.string,
    })
    async def async_call(self, hass, tool_input, llm_context):
        await hass.services.async_call(DOMAIN, "send_destination",
            dict(tool_input.tool_args), blocking=True, context=llm_context.context)
        return {"success": True}

# + SetLocationTargetSocTool, SetSeatHeatingTool (same shape)
_TOOL_CLASSES = [AskAssistantTool, SendDestinationTool]

from homeassistant.core import callback
@callback
def async_get_tools(hass, llm_context, api_id):        # PATH A (2026.8+)
    if api_id != llm.LLM_API_ASSIST:
        return None
    from homeassistant.components.llm import LLMTools
    return LLMTools(
        tools=[c() for c in _TOOL_CLASSES],
        prompt=("For Škoda EV route/charging planning or product questions use "
                "skoda_ask_assistant; if it returns a destination the user accepts, "
                "push it with skoda_send_destination."))
```

```python
# __init__.py, once during setup — PATH B (all versions)
from homeassistant.helpers import llm
from .llm import _TOOL_CLASSES

class VagConnectAPI(llm.API):
    async def async_get_api_instance(self, llm_context):
        return llm.APIInstance(api=self, llm_context=llm_context,
            api_prompt="Talk to the MyŠkoda assistant and control the Škoda.",
            tools=[c() for c in _TOOL_CLASSES],
            custom_serializer=llm.selector_serializer)

entry.async_on_unload(
    llm.async_register_api(hass, VagConnectAPI(
        hass=hass, id="vag_connect", name="VW Group Connect")))
```

Manifest: add `"after_dependencies": ["llm"]` (soft dep so the `llm` component is up and the platform is discovered) — keeps `dependencies: []`.

### How a user wires it

- **Path A (2026.8+):** nothing. Once the tools ship, they appear to any agent using the default Assist API. User just talks to their configured OpenAI/Claude/Ollama agent: *"Ask Laura if I have range for a ski weekend, and if she suggests a charger, send it to the car."*
- **Path B (older HA):** Settings → the conversation agent → *Control Home Assistant* → select "VW Group Connect".
- **No-LLM path (works right now, no MVP code needed):** a `conversation` sentence trigger — `"ask Laura {question}"` → `ask_assistant` with `response_variable` → `set_conversation_response: "{{ laura.summary }}"`. Deterministic, offline-capable with local Assist, zero LLM cost. (Full YAML in Part 2, Scenario 6.)

### Critical gotchas

- **`ask_assistant` must be registered `SupportsResponse.OPTIONAL` (or `ONLY`).** `return_response=True` requires it, or the tool can't retrieve `{summary,…}`. Verify the current service registration does this.
- **Switch commands are nearly free:** `switch.*_camping_switch` / `switch.*_auto_unlock_plug_switch` become LLM-controllable via the built-in `HassTurnOn/Off` tool the moment they're exposed to Assist — no custom tool needed, both HA eras.
- **`number` (per-location SoC) and `select` (seat heating) ship NO `llm.py` platform in 2026.8** → "set charge target to 80%" via LLM needs your explicit `Tool` (as sketched) or an `intent_script:`. Exposing the number entity only makes it *readable* via `GetLiveContext`, not settable.
- **Reads need no tool at all** — SoC, range, charge power, timers, service reminders, fill-up, consent all surface to every agent via `GetLiveContextTool` if the entities are exposed.
- **Don't rely on `intent.async_register` alone on 2026.8** — auto-exposure of arbitrary registered intents as tools was **removed in 2026.8** (only a curated set remains). This is why the `Tool`/`llm.py` path is correct, not a plain intent.

### Version-sensitivity & what to VERIFY LIVE

1. **[LIVE PROBE] The `llm.py`-platform API (`LLMTools`, `LLMToolsPlatformProtocol.async_get_tools`) is confirmed present in tag `2026.8.0`, absent in `2026.7.0`.** This is a very new refactor — verify the exact import path and signature against the running HA version before shipping Path A, and set `hacs.json` min HA version to 2026.8 if Path A is the primary. Path B (custom API) is the version-robust floor and should ship regardless.
2. **[LIVE PROBE] Laura answer quality is UNTESTED end-to-end in HA.** The handler drops `routeDetails` and returns only prose `summary`. Nobody has measured whether Laura's summaries are (a) accurate for EV routing and (b) parseable enough for an LLM to reliably extract coordinates. Run 5–10 real prompts against a portal-enrolled Enyaq/Elroq before announcing Laura as a route planner. This is the single biggest unknown in the MVP.
3. **[LIVE PROBE] `send_destination` for Škoda is wired in code (`coordinator.py:5363`) but services.yaml still labels it SEAT/CUPRA (label lag).** Confirm the Škoda nav-to-car path actually actuates on a real car before promoting Scenario 7.

### Highest-leverage follow-up (1-file enhancement, recommend for the wave)

Surface `routeDetails` as structured response fields instead of dropping it at `__init__.py:826-830`. This turns Scenario 7 (route → nav-to-car) from an "LLM parses coords out of prose" flow into a **plain automation** and makes the whole scenario set demo-able with zero external LLM. Strong candidate for the next Škoda-wave commit.

---

## Part 2 — Killer Scenarios (drop-in for docs/announcement)

*Entity_ids use placeholder device slugs `enyaq` (BEV) / `octavia_iv` (PHEV) and VIN `TMBJB9NY8SF00000`. Swap for the reader's real slug/VIN. All names verified against `feat/skoda-wave`.*

**Decision rule:** anything that only *reads triggers and calls command services* is a plain automation. Laura only needs an LLM layer when you must turn her **prose** into a **decision or parameter** — because the service returns `summary` text, not structured fields.

### 1. Driveway arrival → auto top-up + preheat (the hero — Frigate)
- **Trigger:** Frigate detects a `car` object in the driveway zone → `binary_sensor.driveway_car_occupancy` (or `frigate/events` MQTT filtered on `after.label == "car"`).
- **Logic:** condition `binary_sensor.enyaq_plug_connected` is `on` (else notify "plug me in"); read `sensor.enyaq_battery_soc`; branch on `< 40`.
- **vag_connect:** `set_location_target_soc` (home profile) → `start_charging`; in parallel `start_climatisation` + `set_climatisation_temperature`. *Laura (optional):* `ask_assistant "How many km will 80% give me for tomorrow's commute?"` → TTS the summary to a room speaker.
- **Outcome:** Car rolls in, plugs itself into the right charge plan, cabin pre-conditioned, spoken range summary. Zero taps.

```yaml
alias: Enyaq – driveway arrival auto top-up
trigger:
  - platform: state
    entity_id: binary_sensor.driveway_car_occupancy
    to: "on"
condition:
  - condition: state
    entity_id: binary_sensor.enyaq_plug_connected
    state: "on"
  - condition: numeric_state
    entity_id: sensor.enyaq_battery_soc
    below: 40
action:
  - service: vag_connect.set_location_target_soc
    data: { vin: "TMBJB9NY8SF00000", profile_id: 1, target: 80 }
  - service: vag_connect.start_charging
    data: { vin: "TMBJB9NY8SF00000" }
  - service: vag_connect.start_climatisation
    data: { vin: "TMBJB9NY8SF00000" }
```

### 2. Geofence "coming home" pre-conditioning
- **Trigger:** `zone` — `person.prash` enters a 2 km `home_approach` zone.
- **Logic:** outside temp `< 5 °C` or `> 28 °C`; guard `sensor.enyaq_charging_state != charging`.
- **vag_connect:** `set_climatisation_temperature` + `start_climatisation`; if plugged and below target, `start_charging`.
- **Outcome:** Cabin comfortable (and charging if plugged) by the time they pull in — presence-driven, no phone.

### 3. Solar-surplus opportunistic charging
- **Trigger:** `numeric_state` on `sensor.solar_export_power` `above: 3000` `for: "00:05:00"`.
- **Logic:** condition plug connected; a paired automation stops when surplus `< 1400 W` for 5 min.
- **vag_connect:** `start_charging` / `stop_charging`; `set_target_soc` capped (e.g. 90% on solar days). *Laura (advisory):* `"At 3 kW, how long from 55% to 90%?"` → surface summary on the energy dashboard.
- **Outcome:** Free-electron charging that follows the sun and self-limits.

### 4. Dynamic-tariff cheapest-window charging
- **Trigger:** `binary_sensor.energy_cheap_now` (Nord Pool / Tibber / EPEX helper).
- **Logic:** charge only inside the cheap window AND while `sensor.enyaq_departure_timer_1_time` leaves headroom; compute needed % from range deficit.
- **vag_connect:** `set_target_soc` (departure-driven), `start_charging` at window open, `stop_charging` at close if target reached. *Laura:* `"Cheapest way to be at 100% by 07:00?"` → notify summary.
- **Outcome:** Filled on the cheapest kWh, always ready by the timer the car already reports.

### 5. Calendar departure guard with Laura range check
- **Trigger:** `calendar` trigger, `offset: "-1:30:0"` on `calendar.prash` for located events.
- **Logic:** build a prompt from `trigger.calendar_event.location` + current SoC/range; call Laura.
- **vag_connect:** `ask_assistant "I need to reach {{ location }} at {{ start }}, I'm at {{ soc }}%. Enough range, or charge / stop en route?"`.
  - *Plain path:* TTS + notify the summary; human decides.
  - *LLM path (adds value):* the HA conversation agent reads Laura's verdict and, if "insufficient", autonomously calls `set_target_soc` + `start_charging` + `start_climatisation`. Needed because Laura returns prose, not a boolean.
- **Outcome:** 90 min before a meeting, go/no-go from Laura — and with the LLM layer, the car silently tops itself up.

### 6. Voice: "Hey Assist, ask Laura …"
- **Plain variant (no LLM, ships today):** `conversation` sentence trigger, capture the `{question}` slot, call `ask_assistant`, `set_conversation_response` the summary. Deterministic, offline-capable, zero LLM cost.

```yaml
alias: Assist – Ask Laura
trigger:
  - platform: conversation
    command:
      - "ask Laura {question}"
      - "frag Laura {question}"
action:
  - service: vag_connect.ask_assistant
    data: { vin: "TMBJB9NY8SF00000", prompt: "{{ trigger.slots.question }}" }
    response_variable: laura
  - set_conversation_response: "{{ laura.summary }}"
```

- **LLM variant:** expose `ask_laura` as a tool (Part 1) so *any* free-form Škoda question routes to Laura without a fixed sentence and can chain with other tools.
- **Outcome:** Laura becomes a first-class voice citizen in every room.

### 7. Multi-turn route planning → nav-to-car
- **Trigger:** dashboard button / voice "plan a trip to {dest}".
- **Logic / vag_connect:** (1) `ask_assistant "Plan a route from home to {{ dest }} with charging stops, I'm at {{ soc }}%"` → store `laura.session_id` in `input_text.laura_session`; (2) follow-ups reuse it — `ask_assistant {prompt:"make the stops shorter", session_id:"{{ states('input_text.laura_session') }}"}` for true multi-turn continuity; (3) actuate the chosen stop via `send_destination {latitude, longitude, name}`.
- **Known gap:** the service exposes only `summary`, not structured `routeDetails` (dropped at `__init__.py:826-830`). So getting lat/lon needs either (a) an LLM agent parsing coords from the summary, or (b) the 1-file enhancement in Part 1 → then this becomes a plain automation. **This scenario is gated on the Part-1 Live Probe #2 (Laura quality) and #3 (`send_destination` actuation).**
- **Outcome:** Conversational trip planning inside HA that ends by pushing the first fast-charger to the Škoda's nav — no competing integration does this.

### 8. Proactive low-SoC overnight trip guard
- **Trigger:** nightly `time` (22:00) or `template` when range drops below tomorrow's need.
- **Logic:** template compares tomorrow's first calendar-event distance vs `sensor.enyaq_range_km` × 1.3 safety.
- **vag_connect:** if short → raise `set_target_soc` + `set_departure_timer {timer_id:1, enabled:true, departure_time:"07:00"}` (finishes charging *and* preheats by departure); notify. *Laura/LLM:* recommends target % → LLM feeds `set_target_soc`.
- **Outcome:** Never wake to a car that can't make the day's first trip.

### 9. Camping-mode automation
- **Trigger:** `zone` — `device_tracker.enyaq` enters a `campsite` zone AND ignition off `for: "00:10:00"`; or forecast overnight low `< 8 °C`.
- **Logic:** parked at campsite in the evening → enable camping climate; read `switch.enyaq_camping_switch` attribute `camping_ends_at` (switch.py:199) to re-arm before it auto-stops.
- **vag_connect:** turn on `switch.enyaq_camping_switch`, set `number.enyaq_target_temperature`; enable `switch.enyaq_auto_unlock_plug_switch` (tent-power cable stays usable); cold nights → `start_aux_heating` (grounded, live-gated).
- **Outcome:** Turns the Enyaq into a climate-controlled camper that manages its own comfort window and unlocks its plug for the awning lights.

### 10. Cost tracking + service-reminder nudges
- **(a) Cost — Trigger:** state change on `sensor.octavia_iv_last_refuel_at` (new fill-up) or `sensor.enyaq_parking_ended_at`.
  - *Logic:* feed `last_refuel_cost` + `parking_cost` into `utility_meter`/statistics for a monthly running-cost sensor; charging-cost template (`charging_power_kw` × tariff). Notify per event ("58.2 l / CHF 112 at {{ station }}").
  - *Outcome:* one "cost of ownership" card fed by fuel + parking + charging — data the Škoda app shows only piecemeal.
- **(b) Service nudges — Trigger:** `sensor.enyaq_reminder_technical_inspection` / `_reminder_seasonal_tyre_change` / `_reminder_first_aid_kit` crossing a threshold.
  - *Logic:* notify + optional `calendar.create_event`. *Laura:* `"Nearest Škoda service partner and what a scheduled inspection includes?"` → TTS/notify.
  - *Outcome:* the car reminds you about inspection/MFK, seasonal tyres, first-aid-kit expiry — and Laura tells you where to go.

**Competitive framing (internal, do not post):** we are the only free tool wiring `ai-assistant/ask` (Laura) at all — myskoda/TommiG1/mikrohard don't. And for Škoda specifically, **Laura is the ONLY in-HA trip/charging-stop planner** (structured `find_charging_stations` is Audi + VW EU only), so nobody else can replicate these on the Škoda side.

---

## Part 3 — Tester-Recruitment Issue DRAFT (ready to paste, NO @-mentions in body)

> **Title:** `MyŠkoda 2.31.0 beta — new Škoda wave (Laura AI, send-to-car, per-location SoC, camping, telemetry) — comment to join`

---

**What's new in the Škoda 2.31.0 wave**

This beta adds a big Škoda surface built against the MyŠkoda 8.15.0 app. All of it is opt-in beta and none of it is required for existing users.

**AI assistant ("Laura") — read-only advisory**
- New service `vag_connect.ask_assistant` — ask the in-car MyŠkoda AI about EV route/charging planning and Škoda product questions. Returns a text summary + a `session_id` you can pass back to continue the same conversation across follow-ups. It's advisory only: Laura cannot control the car.

**Commands (some are live-gated — see below)**
- `vag_connect.send_destination` — push a navigation destination to the car's infotainment.
- `vag_connect.set_location_target_soc` — per-location (per charge profile) target SoC.
- `vag_connect.set_seat_heating` — front/rear seat heating.
- Camping switch, auto-unlock-plug switch, aux-heating, charge-mode.

**New sensors / entities**
- Battery SoC & range, charging power (kW) and rate (km/h) — with the ×10 telemetry scaling fix.
- Preferred charge mode, target SoC, departure timers.
- Aux / camping / window-heating state; auto-unlock-when-charged.
- Last fill-up (litres, cost, currency, fuel type, station, time) for PHEVs.
- Pay-to-park session (location, cost, start/end, address, city).
- Service reminders: technical inspection, seasonal tyre change, first-aid kit, tyre-repair kit.
- Mandatory & marketing consent state — plus a **mandatory-consent Repair** that self-heals the T&C / consent wall.

**What we'd love you to test**

Pick whatever matches your car — you don't need to test everything.

- **Laura / `ask_assistant`:** try EV route + charging-stop prompts ("plan a route to X with charging stops, I'm at Y%") and product questions. Tell us if the answers are accurate and useful, and whether multi-turn (`session_id`) continuity works. *(This is the newest, least-battle-tested feature — your feedback here matters most.)*
- **send-to-car (`send_destination`):** does a destination actually arrive on your infotainment? *(Live-gated — report if it silently no-ops.)*
- **Per-location target SoC (`set_location_target_soc`) / charge-mode:** especially Enyaq/Elroq owners — does setting a per-location target stick?
- **Charging telemetry:** confirm charging power (kW) and rate (km/h) read sane values (the ×10 bug is fixed — verify).
- **Camping + auto-unlock-plug switches:** toggle them, check state + the `camping_ends_at` auto-stop attribute.
- **Seat heating / aux-heating:** *(live-gated)* report actuation success/failure.
- **Service reminders + departure timers:** do the values match the app? Any false-positives when the defects list is empty?
- **Token-storm / consent Repair:** if you previously hit rate-limiting or a T&C wall, check whether the Repair clears it and stays cleared.

**How to install the beta (HACS custom repo)**

1. HACS → three-dot menu → **Custom repositories** → add `its-me-prash/vwgroup-connect-ha`, category **Integration**.
2. Open the integration in HACS → enable **"Show beta versions"** (or select the `2.31.0` pre-release once tagged), install, restart HA.
3. *Advanced (branch install):* point the custom repo at the `feat/skoda-wave` branch if you want the raw wave before the tag lands.
4. Reload the VW Group Connect integration; new Škoda entities appear automatically for exposed vehicles.

*(Backup tip: snapshot your HA config before installing a beta.)*

**How to report**

Please include, per issue:
- Brand + model + year (e.g. Enyaq 2024, Octavia iV 2023) and whether it's BEV/PHEV.
- The exact service call or entity, what you expected, what happened.
- For command failures: the HA log lines around the call (redact your VIN/tokens).
- For Laura: paste the prompt and her summary (redact anything personal) so we can judge answer quality.

**Want in?** Comment below with your Škoda model + which features you can test, and we'll keep this thread updated as fixes land. Thanks for helping shape the Škoda wave.

---

## Part 4 — Curated Tag List + Etiquette

**Hard gate:** this is a DRAFT. **Nothing gets posted, and no one gets tagged, without Prash's explicit OK — and the wave must be pushed + the 2.31.0 beta tagged FIRST** (right now `feat/skoda-wave` is held and unpushed, so testers would have nothing to install). Re-check every handle against the CLAUDE.md do-not-ping blocklist before any tag; none of the below are currently on it, but re-verify.

**Recommended play: open the ONE opt-in thread above and let people self-select. Do NOT mass-@-tag 19 handles — it reads as spam and sours goodwill.** If you tag at all, tag only the few most-relevant *recent* reporters whose exact issue a feature fixes, in the comment that announces the thread — not a batch ping.

### Tier 1 — recent Škoda reporters, direct feature match (OK to @ individually, sparingly)
| Handle | Feature it fixes | Issue |
|---|---|---|
| `@foobarth` | token-storm resilience + mandatory-consent Repair | #1078, #465 |
| `@tader` | per-location / target-SoC charge command (Elroq — prime EV cohort) | #866 |
| `@RaAdNe` | charge power/rate telemetry + auto-unlock-plug | #1002, #510 |
| `@divanguz-alt` | service-reminder / warning-light sensors | #649 |
| `@Chr1sDub` | command control (send_destination, seat-/aux-heating) | #131 |

### Tier 2 — invite via the opt-in thread (do NOT direct-ping)
- **Camping switch:** `@whaak58`, `@tritanium73`, `@microcens`, `@derolli1976`, `@ichwars`, `@mk-lp`, `@MavericklCS`
- **Auto-unlock-plug:** `@rocksandclouds`, `@whaak58`, `@RaAdNe`
- **Commands (send-to-car / seat heating) + S-PIN gating:** `@GitHobi`, `@ChristophCaina`
- **Broad Škoda reads/sensors:** `@christianmhz`, `@indigomejor`, `@DvorakMartin1`, `@Winbergarnas`, `@GitHobi`

### No dedicated reporter — recruit from the thread
- **Laura (`ask_assistant`)** and **`send_destination`** have no existing reporter. Recruit EV Škoda owners (Enyaq/Elroq) — `@tader` (Elroq) and the charge-telemetry folks (`@RaAdNe`) are the natural EV cohort to nudge.

### Verify-before-including / excluded (honesty flags)
- **Lower-confidence, verify Škoda ownership first:** `@KawoAdm` (#674 is a VW scout mentioning Škoda), `@sonypsx` (#1001 device-info, likely VW ID.4). Left off the roster.
- **Excluded as not-Škoda:** `@nekas123` (#442 requester is an Audi e-tron owner); CUPRA owners `@matthias0304`, `@ColinSainsbury`, `@Gerhard2808`. The #465/#1027 T&C-wall engagers (`@AlexLeChauve`, `@Arno-MA-73`, `@gr6803`, `@shaarkys`, `@TomJonesGreggs`, `@zdravac`, `@wittl74`=Audi) are portal-affected VW/Audi users, not confirmed Škoda — treat as portal-affected, not primary Škoda testers.

### Coverage caveat
The bulk issue list only returned the newest ~300 (#716–#1091); older Škoda scout clusters (#129–#147 auto-unlock, #315–#333 camping) were recovered via targeted search, so a few very old Škoda threads could still be unlisted. Each Škoda issue showed reporter + maintainer only (no cross-user engagement), so testers == the reporters listed.

---

### Bottom line for Prash
- **MVP is close:** `ask_assistant` already returns `{summary, session_id, type}`; the no-LLM sentence-trigger path works today. The only new code for the AI coupling is `llm.py` (Path A) + a custom-API fallback (Path B) sharing one `_TOOL_CLASSES` list.
- **Two live probes gate the announcement:** (1) the 2026.8 `llm.py`-platform API against your running HA version, and (2) **Laura's real answer quality** — untested end-to-end and the biggest unknown. Add (3) confirming `send_destination` actually actuates on Škoda.
- **One high-leverage commit** (surface `routeDetails`) turns the flagship route→nav scenario into a plain automation and makes the whole set demo-able with no external LLM.
- **Sequence:** land the wave → push → tag 2.31.0 beta → open the opt-in thread → *then*, with your OK, a light Tier-1 nudge. No pings before the beta exists.
---

# Appendix — full scenario research (raw)

＃ Škoda "Laura" + new-entity automation playbook — 10 killer HA scenarios (DRAFT)

All names below are verified against the held `feat/skoda-wave` branch (not guessed). Entity_ids use a placeholder device name `enyaq` (BEV) and `octavia_iv` (PHEV, for fuel scenarios); VIN placeholder `TMBJB9NY8SF00000` (Škoda VINs start `TMB`). Swap for the reader's real device slug/VIN.

## 0. Ground truth — what the surface ACTUALLY gives us (read this first)

**Three load-bearing facts that shape every scenario:**

1. **Laura is advisory TEXT only.** `vag_connect.ask_assistant` returns a `response_variable` with exactly `{summary, type, session_id}` — the handler at `custom_components/vag_connect/__init__.py:826-830` maps the API's `AIAssistantResponseDto` down to those three keys and **drops `routeDetails`**. So Laura's charging-stop coordinates are NOT machine-readable today. Every actuation (charge, preheat, nav) goes through a *separate command service*. Laura never actuates (the AiAssistantApi package has zero command DTOs — `skoda.py:2024-2032`).
2. **For Škoda, Laura IS the route/charge-station planner.** `vag_connect.find_charging_stations` (the structured POI lookup with a machine-readable list) is **Audi + VW EU only** (`services.yaml:558-565`, "nur Audi + VW EU"). Škoda has no structured POI service — so Laura is the *only* in-HA trip/charging-stop planner for Škoda. No competitor (myskoda lib, TommiG1, mikrohard) wires the `ai-assistant/ask` endpoint at all → this is a genuine first.
3. **`send_destination` is the nav-to-car actuator** wired for Škoda in `coordinator.py:5363` (`command_send_destination`). Required fields `vin, latitude, longitude, name`; the rest of the postal address is optional (`services.yaml:490-555`). It is LIVE-GATED (services.yaml still labels it SEAT/CUPRA — label lag; the Škoda command path is wired).

**Verified entity/service inventory (feat/skoda-wave):**

| Kind | entity_id / service | Source |
|---|---|---|
| Service | `vag_connect.ask_assistant` {vin, prompt, timezone?, session_id?} → `{summary,type,session_id}` | `__init__.py:814`, `services.yaml:607` |
| Service | `vag_connect.send_destination` {vin, latitude, longitude, name, +postal} | `coordinator.py:5363`, `services.yaml:490` |
| Service | `vag_connect.set_location_target_soc` {vin, profile_id, target} | `services.yaml:290` |
| Service | `vag_connect.set_seat_heating` {vin, front_left/right, rear_left/right} | `services.yaml:319` |
| Service | `vag_connect.set_target_soc` {vin, target} (global) · `set_departure_timer` {vin, timer_id, enabled, departure_time?, recurring_on?} | `services.yaml:271,364` |
| Service | `start_charging`/`stop_charging`, `start_climatisation`/`stop_climatisation`, `set_climatisation_temperature`, `start_window_heating`/`stop`, `start_aux_heating`/`stop`, `wake_vehicle` | `services.yaml:129,109,345,188,465,208` |
| Switch | `switch.enyaq_camping_switch` (attr `camping_ends_at`) · `switch.enyaq_auto_unlock_plug_switch` · battery-care switch | `switch.py:182,216`; `switch.py:199` |
| Sensor | `sensor.enyaq_battery_soc` (%), `sensor.enyaq_range_km`, `sensor.enyaq_charging_state`, `sensor.enyaq_charging_power_kw`, `sensor.enyaq_charging_rate_kmh`, `sensor.enyaq_target_soc`, `sensor.enyaq_preferred_charge_mode` | `sensor.py:85,95,160,227,237,189,554` |
| Sensor (fuel) | `sensor.octavia_iv_last_refuel_quantity` (l), `_last_refuel_cost`, `_last_refuel_currency`, `_last_refuel_fuel_type`, `_last_refuel_station`, `_last_refuel_at` | `sensor.py:564-602` |
| Sensor (park) | `sensor.enyaq_parking_location`, `_parking_cost`, `_parking_currency`, `_parking_started_at`, `_parking_ended_at`, `_parking_address`, `_parking_city` | `sensor.py:609-639,820` |
| Sensor (service) | `sensor.enyaq_reminder_technical_inspection`, `_reminder_seasonal_tyre_change`, `_reminder_first_aid_kit`, `_reminder_tyre_repair_kit` | `sensor.py:646-669` |
| Sensor (timer) | `sensor.enyaq_departure_timer_1_time` (…2,3), `_departure_timer_enabled_count` | `sensor.py:675-691` |
| Binary | `binary_sensor.enyaq_plug_connected`, `_is_charging`, `_camping_mode`, `_seat_heating`, `_window_heating_front/back`, `_auto_unlock_when_charged`, `_mandatory_consent_given`, `_marketing_consent_given` | `binary_sensor.py:145,153,432,289,269/277,393,299,306` |
| Number/Climate | `number.enyaq_target_soc`, `number.enyaq_target_temperature`, `number.enyaq_battery_care_target` · `climate.enyaq` | `number.py:43,74,60`; `climate.py` |
| Tracker | `device_tracker.enyaq` (GPS) | `device_tracker.py` |
| Repair | mandatory-consent / T&C Repair (self-heals) | `repairs.py:47,76,107` |

---

## Scenario 1 — Driveway arrival → auto top-up + preheat (the seed, expanded)
**Category: camera/Frigate.** **Plain automation (no LLM).**
- **Trigger:** Frigate detects the car object in the `driveway` camera zone → the Frigate HA integration exposes `binary_sensor.driveway_car_occupancy` (or subscribe to the `frigate/events` MQTT topic and filter `after.label == "car"` + your camera). (HA Frigate integration docs; `docs.frigate.video/integrations/home-assistant`).
- **HA logic:** `condition`: `binary_sensor.enyaq_plug_connected` is `on` (only fire once actually plugged — otherwise notify "plug me in"). Read `sensor.enyaq_battery_soc`. Branch on a threshold (`< 40`).
- **vag_connect surface:** if SoC low → `set_location_target_soc` (profile_id = the home charge profile read from the charge-profiles sensor attributes; profile-aware so "home" gets its own %), then `start_charging`. In parallel `start_climatisation` + `set_climatisation_temperature` (weather-aware preheat/precool). **Laura (optional, advisory):** `ask_assistant` "How many km will 80% give me for tomorrow's commute?" → TTS the `summary` to a room speaker.
- **Outcome:** Car rolls in → plugs itself into the right charge plan, tops up to the location target, cabin pre-conditioned, owner hears a spoken range summary. Zero taps.

```yaml
alias: Enyaq – driveway arrival auto top-up
trigger:
  - platform: state
    entity_id: binary_sensor.driveway_car_occupancy
    to: "on"
condition:
  - condition: state
    entity_id: binary_sensor.enyaq_plug_connected
    state: "on"
  - condition: numeric_state
    entity_id: sensor.enyaq_battery_soc
    below: 40
action:
  - service: vag_connect.set_location_target_soc
    data: { vin: "TMBJB9NY8SF00000", profile_id: 1, target: 80 }
  - service: vag_connect.start_charging
    data: { vin: "TMBJB9NY8SF00000" }
  - service: vag_connect.start_climatisation
    data: { vin: "TMBJB9NY8SF00000" }
```

## Scenario 2 — Geofence "coming home" pre-conditioning
**Category: presence/geofence.** **Plain automation.**
- **Trigger:** `zone` trigger — `person.prash` enters a 2 km `home_approach` zone (HA zone trigger, `home-assistant.io/docs/automation/trigger/#zone-trigger`).
- **HA logic:** conditions: outside temp `< 5 °C` OR `> 28 °C` (weather entity) → precondition worthwhile; guard on `sensor.enyaq_charging_state != charging` so you don't fight an active session.
- **vag_connect surface:** `set_climatisation_temperature` (warm in winter, cool in summer) + `start_climatisation`; if BEV and `plug_connected` and SoC below target, `start_charging`. On leaving-home zone at low SoC, notify instead.
- **Outcome:** By the time they pull into the garage the cabin is comfortable and (if plugged) charging — presence-driven, no phone interaction.

## Scenario 3 — Solar-surplus opportunistic charging
**Category: energy/solar-surplus.** **Plain automation** (Laura optional).
- **Trigger:** `numeric_state` on your PV-surplus sensor (`sensor.solar_export_power`, from your inverter / Forecast.Solar, `home-assistant.io/integrations/forecast_solar`) `above: 3000` for `for: "00:05:00"`.
- **HA logic:** condition `binary_sensor.enyaq_plug_connected` on. Start when surplus sustained; a second automation stops when surplus `< 1400 W` for 5 min. Optionally set `sensor.enyaq_preferred_charge_mode`-equivalent via the charging-settings service so the car favours slow PV charging.
- **vag_connect surface:** `start_charging` / `stop_charging`; `set_target_soc` capped (e.g. 90% for solar days). **Laura (advisory):** `ask_assistant` "At 3 kW, how long from 55% to 90%?" → surface the `summary` on the energy dashboard so the human sees whether the surplus window is long enough.
- **Outcome:** Free-electron charging that follows the sun and self-limits — a headline energy-community use case.

## Scenario 4 — Dynamic-tariff cheapest-window charging
**Category: dynamic tariff.** **Plain automation.**
- **Trigger:** `template`/`state` on a cheapest-hours helper from Nord Pool / Tibber / EPEX (`home-assistant.io/integrations/tibber`) — e.g. `binary_sensor.energy_cheap_now`.
- **HA logic:** Only charge inside the cheap window AND while `sensor.enyaq_departure_timer_1_time` implies you still have headroom before departure. Compute needed % from `range_km` deficit.
- **vag_connect surface:** `set_target_soc` (departure-driven %), `start_charging` at window open, `stop_charging` at window close if target reached. **Laura (advisory):** "What's the cheapest way to be at 100% by 07:00?" → spoken/notified `summary`.
- **Outcome:** Battery filled on the cheapest kWh, always ready by the departure timer the car already reports.

## Scenario 5 — Calendar departure guard with Laura range check
**Category: calendar/departure + trip guard.** **Plain to speak the answer; LLM-tool-exposure to ACT on it.**
- **Trigger:** `calendar` trigger with `offset: "-1:30:0"` on `calendar.prash` for events that carry a location (HA calendar automation, `home-assistant.io/integrations/calendar/#automation`).
- **HA logic:** Build a prompt from `trigger.calendar_event.location` and current `sensor.enyaq_battery_soc`/`range_km`. Call Laura.
- **vag_connect surface:** `ask_assistant` `{prompt: "I need to reach {{ location }} at {{ start }} and I'm at {{ soc }}%. Do I have enough range, or do I need to charge / stop en route?"}` → `summary`.
  - **Plain path:** TTS the `summary` to the bedroom speaker + `notify` — human decides.
  - **LLM path (adds value):** expose a `top_up_to(target)` script as a tool to your HA conversation agent (OpenAI/Anthropic/Ollama via the HA LLM API, `developers.home-assistant.io/docs/core/llm/`). The LLM reads Laura's free-text verdict and, if "insufficient", calls `set_target_soc` + `start_charging` + `start_climatisation` autonomously. Needed because Laura returns prose, not a boolean.
- **Outcome:** 90 min before a meeting, the car (via Laura) tells you go/no-go and — with the LLM layer — silently tops itself up to make the trip.

## Scenario 6 — Voice: "Hey Assist, ask Laura …"
**Category: voice.** **Two variants — pick per need.**
- **Plain variant (no LLM):** a `conversation` **sentence trigger** (`home-assistant.io/docs/automation/trigger/#sentence-trigger`): `trigger.sentence: "ask Laura {question}"`, capture the `{question}` slot, call `ask_assistant` with `prompt: "{{ trigger.slots.question }}"`, and `set_conversation_response` / TTS the returned `summary`. Deterministic, offline-capable with local Assist, zero LLM cost.

```yaml
alias: Assist – Ask Laura
trigger:
  - platform: conversation
    command:
      - "ask Laura {question}"
      - "frag Laura {question}"
action:
  - service: vag_connect.ask_assistant
    data: { vin: "TMBJB9NY8SF00000", prompt: "{{ trigger.slots.question }}" }
    response_variable: laura
  - set_conversation_response: "{{ laura.summary }}"
```

- **LLM variant (adds value):** expose an `ask_laura` script as a tool to the HA LLM conversation agent so *any* free-form Škoda question ("is my charge enough for a ski weekend?") gets routed to Laura without a fixed sentence, and the agent can chain it with other tools.
- **Outcome:** Laura becomes a first-class voice citizen in HA Assist — a Škoda-brain in every room.

## Scenario 7 — Multi-turn route planning with charging stops → nav-to-car
**Category: multi-turn route planning.** **LLM-tool-exposure recommended for the auto-forward leg.**
- **Trigger:** dashboard button or voice "plan a trip to {dest}".
- **HA logic / vag_connect surface:**
  1. First `ask_assistant` `{prompt: "Plan a route from home to {{ dest }} with charging stops; I'm at {{ soc }}%"}` → store `laura.session_id` in `input_text.laura_session`.
  2. Follow-ups reuse it for true multi-turn continuity: `ask_assistant {prompt: "make the stops shorter", session_id: "{{ states('input_text.laura_session') }}"}` (session_id continuity confirmed `skoda.py:2033-2040`).
  3. **Actuate:** forward the chosen charging stop to the car via `send_destination {latitude, longitude, name}` (nav-to-car).
- **Known gap / why LLM helps:** the service currently exposes only `summary` text, not the structured `routeDetails` (handler drops it, `__init__.py:826-830`). So to get lat/lon for `send_destination` you either (a) let an LLM conversation agent parse coordinates out of Laura's `summary` and call `send_destination`, or (b) — the single highest-leverage integration follow-up — **surface `routeDetails` in the service response** so a plain automation can forward stop[0] with no LLM. Flag this as a 1-line enhancement.
- **Outcome:** Conversational trip planning inside HA that ends by pushing the first fast-charger straight to the Škoda's nav — a flow no competing integration can do.

## Scenario 8 — Proactive low-SoC overnight trip guard
**Category: low-SoC trip guard.** **Plain + optional Laura/LLM.**
- **Trigger:** nightly `time` trigger (e.g. 22:00) OR a `template` trigger when `range_km` drops below tomorrow's need.
- **HA logic:** template compares tomorrow's first `calendar` event distance vs `sensor.enyaq_range_km` with a 1.3× safety factor.
- **vag_connect surface:** if short → `set_target_soc` raise + `set_departure_timer {timer_id:1, enabled:true, departure_time:"07:00"}` so the car finishes charging *and* preheats by departure; `notify` the owner. **Laura (advisory):** "Given 220 km tomorrow and current charge, what target % do you recommend?" → LLM parses the % and feeds `set_target_soc` (same prose→action pattern as #5).
- **Outcome:** You never wake up to a car that can't make the day's first trip.

## Scenario 9 — Camping-mode automation
**Category: camping-mode.** **Plain automation.**
- **Trigger:** `zone` trigger — car (`device_tracker.enyaq`) enters a `campsite` zone AND ignition off `for: "00:10:00"`; or weather forecast "overnight low < 8 °C".
- **HA logic:** evening + parked at campsite → offer/enable camping climate; read `switch.enyaq_camping_switch` attribute `camping_ends_at` (`switch.py:199`) to know when it will auto-stop and re-arm before it lapses.
- **vag_connect surface:** turn on `switch.enyaq_camping_switch`, set `number.enyaq_target_temperature`; enable `switch.enyaq_auto_unlock_plug_switch` so a tent-power cable stays usable; for cold nights schedule `start_aux_heating` (Škoda aux-heating route grounded `skoda.py:1859`, live-gated). Auto-stop honoured via the `camping_ends_at` attribute.
- **Outcome:** Turn the Enyaq into a climate-controlled camper that manages its own comfort window and unlocks its plug for the awning lights — a delight feature owners screenshot.

## Scenario 10 — Cost tracking + service-reminder nudges
**Category: cost tracking (fuel/parking/charging) + service reminders.** **Plain automation; Laura optional.**
- **(a) Cost tracking — Trigger:** state change on `sensor.octavia_iv_last_refuel_at` (new fill-up) or `sensor.enyaq_parking_ended_at` (parking session closed).
  - **HA logic / surface:** feed `last_refuel_cost` + `parking_cost` into `utility_meter`/statistics (`home-assistant.io/integrations/utility_meter`) for a monthly running-cost sensor; add a charging-cost template (`charging_power_kw` integrated × tariff). `notify` on each new fill-up ("58.2 l / CHF 112 at {{ station }}") and parking session ("CHF 4.50, 2h at {{ parking_address }}").
  - **Outcome:** A single "cost of ownership" card fed by fuel + parking + charging — data the Škoda app itself surfaces only piecemeal.
- **(b) Service nudges — Trigger:** `numeric_state`/`template` when `sensor.enyaq_reminder_technical_inspection` (days/km) crosses a threshold, or `_reminder_seasonal_tyre_change` / `_reminder_first_aid_kit` fires.
  - **HA logic / surface:** `notify` + optionally create a `calendar.create_event` for the inspection. **Laura (advisory):** `ask_assistant "Where is the nearest Škoda service partner and what does a scheduled inspection include?"` → TTS/notify the `summary`.
  - **Outcome:** The car reminds you about MFK/inspection, seasonal tyres and the first-aid-kit expiry — and Laura tells you where to go. Ties into your PB-Autowerx angle nicely for a demo.

---

## Plain-automation vs 3rd-party-LLM-tool-exposure — decision matrix

| Need | Path | Scenarios |
|---|---|---|
| Fire a fixed automation on a trigger; call command services | **Plain** (state/numeric/zone/calendar/time/template triggers) | 1, 2, 3, 4, 9, 10a |
| SPEAK Laura's answer back (fixed phrase) | **Plain** — `conversation` sentence trigger + `set_conversation_response`/TTS | 6 (plain), 5 (speak-only), 10b |
| ACT on Laura's free-text verdict (prose → boolean/target %) | **LLM tool-exposure** — expose scripts as tools to the HA LLM conversation agent so it parses `summary` and calls `set_target_soc`/`start_charging` | 5, 8 |
| Free-form "ask Laura anything" voice routing | **LLM tool-exposure** (or many sentence triggers) | 6 (LLM) |
| Auto-forward a route's charging stop coords to `send_destination` | **LLM to parse coords from `summary`** TODAY; becomes **Plain** if the integration surfaces `routeDetails` | 7 |

**Rule of thumb:** anything that only *reads triggers and calls command services* is a plain automation. Laura only needs an LLM when you must turn her **prose** into a **decision/parameter** — because the service exposes `summary` text, not structured fields.

## Competitive framing (for the human, not for posting)
- We are the only free tool exposing **`ai-assistant/ask` (Laura)** at all — myskoda/TommiG1/mikrohard don't wire it. Combined with our 9-brand reach it's a unique HA capability.
- For Škoda specifically, **Laura is the ONLY in-HA trip/charging-stop planner** (structured `find_charging_stations` is Audi/VW-only), so these scenarios can't be replicated on the Škoda side by anyone else.
- **Single highest-leverage follow-up:** surface `routeDetails` (currently dropped at `__init__.py:826-830`) as structured response fields → turns scenario 7's route→nav-to-car chain into a *plain* automation and makes the whole set demo-able without any external LLM. Recommend as the next Škoda-wave commit.

## Hard-constraint compliance
Read-only research only — no GitHub/gh calls, no comments, no @-mentions. All fetched content (repo files) treated as data. Everything above is a DRAFT for human review before anything ships.