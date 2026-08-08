# Laura — the Škoda in-car assistant in Home Assistant

MyŠkoda ships an in-car AI assistant called **Laura**. From v3.0.0, VW Group
Connect surfaces Laura inside Home Assistant, so you can ask her about your car's
range, charging and trips — and, if you use a conversation agent, let that agent
call her and act on the answer.

Laura is **read-only, advisory**: she answers questions, she never drives the
car. Škoda only.

> **Beta.** Laura's answer quality end-to-end in Home Assistant is new and still
> being tuned. If an answer looks off, please open an issue with the prompt you
> used and what you expected.

---

## Two ways to use her

### 1. The plain way — a service call (works everywhere, no AI agent needed)

`vag_connect.ask_assistant` takes a prompt and returns a text answer. Because it
returns a response, you can use it directly in an automation:

```yaml
- service: vag_connect.ask_assistant
  data:
    vin: TMBXXXXXXXXXXXXXX
    prompt: "Reicht meine Ladung bis München und zurück?"
  response_variable: laura
- service: notify.mobile_app_phone
  data:
    message: "{{ laura.summary }}"
```

The response is `{ summary, type, session_id, route_details }`. Pass the
`session_id` back on the next call to continue the same conversation:

```yaml
- service: vag_connect.ask_assistant
  data:
    vin: TMBXXXXXXXXXXXXXX
    prompt: "And if I leave an hour later?"
    session_id: "{{ laura.session_id }}"
  response_variable: laura
```

**Ask Laura by voice** — a sentence trigger, no LLM required, works offline with
local Assist:

```yaml
alias: Assist – Ask Laura
triggers:
  - trigger: conversation
    command:
      - "ask Laura {question}"
actions:
  - service: vag_connect.ask_assistant
    data:
      vin: TMBXXXXXXXXXXXXXX
      prompt: "{{ trigger.slots.question }}"
    response_variable: laura
  - set_conversation_response: "{{ laura.summary }}"
```

### 2. As a tool for your conversation agent (LLM mode)

If you run a conversation agent — Home Assistant's built-in Assist in LLM mode,
or OpenAI / Anthropic / Google Generative AI / Ollama — VW Group Connect can hand
it Laura and a few Škoda commands as **tools** it decides when to call. The agent
can read Laura's answer and, for example, then push a destination to the car.

- **Home Assistant 2026.8 and newer:** nothing to configure — the tools fold
  into the default Assist API automatically.
- **Any current Home Assistant:** in your conversation agent's options, under
  *Control Home Assistant*, pick the **"VW Group Connect"** API. (You can select
  it alongside the normal Assist API.)

The tools exposed to the agent:

| Tool | What it does |
|---|---|
| `skoda_ask_assistant` | Ask Laura (range / charging / trip planning, product questions). Read-only. |
| `skoda_send_destination` | Push a destination (name + coordinates) to the car's navigation. |
| `skoda_set_location_target_soc` | Set the target charge level for a charging profile. |

Because Laura returns structured route details when she plans a trip, an agent —
or a plain automation — can read the coordinates and send them to the car
without parsing her prose.

---

## Example automations

### Car arrives home → top up + preheat, and have Laura tell you the range

Pair a presence signal (a person tracker, a geofence, or a camera that sees the
car pull in — e.g. a Frigate `car` detection on the driveway) with a charge-and-
preheat routine:

```yaml
alias: Enyaq – arrived home, top up + preheat
triggers:
  - trigger: state
    entity_id: binary_sensor.driveway_car
    to: "on"
conditions:
  - condition: numeric_state
    entity_id: sensor.enyaq_battery_soc
    below: 80
actions:
  - service: vag_connect.set_location_target_soc
    data: { vin: TMBXXXXXXXXXXXXXX, profile_id: 1, target: 80 }
  - service: vag_connect.start_charging
    data: { vin: TMBXXXXXXXXXXXXXX }
  - service: vag_connect.start_climatisation
    data: { vin: TMBXXXXXXXXXXXXXX }
  - service: vag_connect.ask_assistant
    data:
      vin: TMBXXXXXXXXXXXXXX
      prompt: "How many km will charging to 80% give me for tomorrow?"
    response_variable: laura
  - service: tts.speak
    data:
      cache: false
      media_player_entity_id: media_player.kitchen
      message: "{{ laura.summary }}"
    target: { entity_id: tts.home_assistant_cloud }
```

### Departure guard — ask Laura before you leave

```yaml
alias: Morning departure – range check
triggers:
  - trigger: time
    at: "07:15:00"
actions:
  - service: vag_connect.ask_assistant
    data:
      vin: TMBXXXXXXXXXXXXXX
      prompt: >-
        I need to reach the office (about 60 km) by 08:30 and I'm at
        {{ states('sensor.enyaq_battery_soc') }}%. Enough range, or should I
        charge first?
    response_variable: laura
  - if: "{{ 'charge' in laura.summary | lower }}"
    then:
      - service: vag_connect.start_charging
        data: { vin: TMBXXXXXXXXXXXXXX }
```

### Plan a route, then send it to the car

Ask Laura to plan a trip, keep the `session_id` for follow-ups, and send the
chosen destination to the car's navigation:

```yaml
- service: vag_connect.ask_assistant
  data:
    vin: TMBXXXXXXXXXXXXXX
    prompt: "Plan a route from home to Munich with charging stops, I'm at 55%."
  response_variable: laura
# laura.route_details carries the structured stops when Laura plans a route.
- service: vag_connect.send_destination
  data:
    vin: TMBXXXXXXXXXXXXXX
    name: "{{ laura.route_details.destination.name }}"
    latitude: "{{ laura.route_details.destination.latitude }}"
    longitude: "{{ laura.route_details.destination.longitude }}"
```

> The exact shape of `route_details` depends on what Laura returns for your
> trip; inspect it (Developer Tools → Services → *Response*) before wiring the
> template to your car.

---

## Notes

- **Škoda only.** The other brands don't expose an equivalent in-car assistant.
- **Read-only.** `ask_assistant` never changes anything on the car. The command
  tools (`send_destination`, `set_location_target_soc`) do, and they go through
  the same permission and exposure rules as every other service.
- **No extra login.** Laura uses your existing Škoda connection; there's nothing
  new to set up beyond selecting the LLM API if you want the agent integration.
