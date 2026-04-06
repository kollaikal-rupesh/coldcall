# ColdCall

**Synthetic callers that test your voice AI agent over real phone calls.**

ColdCall calls your voice agent, has a realistic conversation, and tells you if it passed — latency, interruptions, and per-criteria evaluation included. One command, fully automated.

```
pip install coldcall
coldcall serve --scenario dental-appointment --public-url https://your.ngrok.app --once
```

---

## What is this?

Every voice AI team tests by manually calling their agent. That doesn't scale. ColdCall is an open-source synthetic caller that dials your agent, plays a realistic persona, and evaluates the conversation against your success criteria — automatically. Think of it as end-to-end testing for voice agents.

## Quickstart

### 1. Install

```bash
pip install coldcall
# or
uv add coldcall
```

### 2. Configure

```bash
cp coldcall.yaml.example coldcall.yaml
```

```yaml
# coldcall.yaml
twilio:
  account_sid: "ACxxxxxxxx"
  auth_token: "your-auth-token"
deepgram:
  api_key: "your-deepgram-key"
openai:
  api_key: "your-openai-key"
cartesia:
  api_key: "your-cartesia-key"
server:
  public_url: "https://your-domain.ngrok.app"
```

### 3. Set up your phone number

```bash
coldcall setup --provider twilio
```

### 4. Start a test

```bash
# Start the server (exposes webhook for Twilio)
coldcall serve --scenario dental-appointment --once

# Or make an outbound call to your agent
coldcall call +14155559876 --public-url https://your.ngrok.app
```

### 5. View results

```bash
coldcall results --last
```

Every test produces a `results/<timestamp>/` directory with WAV recordings, transcript, metrics, evaluation, and an HTML report you can open in a browser.

---

## How it works

```
                    ┌──────────────┐
  Your Agent  ◄──── │   Twilio     │ ◄──── Phone Call
  (any platform)    │   (PSTN)     │
                    └──────┬───────┘
                           │ WebSocket (Media Streams)
                    ┌──────▼───────┐
                    │   ColdCall   │
                    │   Server     │
                    ├──────────────┤
                    │ Deepgram STT │  ← hears your agent
                    │ GPT-4o-mini  │  ← decides what to say
                    │ Cartesia TTS │  ← speaks back
                    │ Humanizer    │  ← adds "um", pauses
                    │ Noise        │  ← cafe/street/car ambiance
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   Results    │
                    ├──────────────┤
                    │ transcript   │  ← full conversation
                    │ metrics      │  ← latency, interruptions
                    │ evaluation   │  ← per-criteria pass/fail
                    │ report.html  │  ← shareable report
                    │ audio WAVs   │  ← recordings
                    └──────────────┘
```

## Scenarios

ColdCall ships with **20 built-in scenarios** across 4 categories. Drop a YAML file to create your own.

### Writing a scenario

```yaml
# scenarios/my-test.yaml
name: pizza_order
persona: |
  You are Mike, calling to order a large pepperoni pizza for delivery.
  Your address is 42 Oak Street.
goal: Successfully order a pizza for delivery
max_duration_seconds: 120
noise_profile: street        # cafe, street, office, car, wind
humanize: true               # add fillers, pauses, corrections
success_criteria:
  - "agent took the pizza order correctly"
  - "agent confirmed the delivery address"
  - "agent provided an estimated delivery time"
```

That's it. ColdCall handles the persona prompt, voice, STT/TTS pipeline, evaluation, and reporting.

```bash
coldcall serve --scenario pizza_order --once
```

### Built-in scenarios

**Happy paths**
| Scenario | Persona | What it tests |
|----------|---------|---------------|
| `dental-appointment` | Sarah Mitchell | Booking an appointment for Thursday |
| `order-status` | David Chen | Checking order #A7829 |
| `general-faq` | Lisa Park | Hours, location, walk-in policy |
| `address-change` | Rachel Torres | Updating mailing address |
| `prescription-refill` | James Cooper | Refilling Lisinopril 10mg |

**Difficult callers**
| Scenario | Persona | What it tests |
|----------|---------|---------------|
| `angry-refund` | Mark Johnson | Furious about broken blender, wants refund |
| `confused-elderly` | Dorothy, 81 | Confused about bill, calls WiFi "the blinking box" |
| `impatient-interrupter` | Kevin Wright | Between meetings, cuts off explanations |
| `mind-changer` | Priya Sharma | Changes restaurant order 4 times |
| `escalation-request` | Tom Bradley | 4th call about billing, wants a manager |

**Edge cases**
| Scenario | Persona | What it tests |
|----------|---------|---------------|
| `wrong-info-correction` | Amy Wilson | Gives wrong DOB, then corrects |
| `long-silence` | Nathan Brooks | Goes silent for 10 seconds mid-call |
| `fast-speaker` | Carlos Mendez | Rapid-fires insurance claim details |
| `repeat-requests` | Helen Park | Hard of hearing, asks to repeat 3 times |
| `off-topic` | Betty Morrison | Wants balance check, talks about weather |

**Adversarial / Red team**
| Scenario | Persona | What it tests |
|----------|---------|---------------|
| `prompt-extraction` | "Alex" | Tries to extract system prompt |
| `inappropriate-content` | "Jordan" | Tries to get agent to say something bad |
| `social-engineering` | "Chris Taylor" | Impersonates manager for customer data |
| `contradictory-info` | "Sam Rivera" | Gives conflicting dates, names, details |
| `mixed-language` | Maria Gonzalez | Switches between English and Spanish |

```bash
coldcall scenarios list        # see all available
coldcall scenarios init        # copy all built-ins to ./scenarios/
coldcall scenarios init my-test  # create from template
```

## Metrics

Every call measures:

| Metric | What it measures |
|--------|-----------------|
| **Response latency** | Time between ColdCall finishing speaking and agent starting to respond. Reports p50, p95, p99 |
| **Interruptions** | Agent starts talking while ColdCall is still speaking |
| **Silence gaps** | Pauses > 2 seconds where nobody is speaking |
| **Turn count** | Total back-and-forth exchanges |
| **Call duration** | Total call time |

Metrics are computed using Silero VAD on both audio channels.

## Humanizer

ColdCall doesn't sound like a robot. The humanizer layer transforms clean LLM output into natural speech:

| Transform | Example | Rate |
|-----------|---------|------|
| Filler words | "I need to cancel" → "Um, I need to cancel" | ~18% |
| Self-correction | "I want a refund" → "I want— actually, I'd like a refund" | ~5% |
| Sentence fragments | "I ordered shoes and they arrived damaged" → "I ordered shoes... and they arrived damaged" | ~20% |
| Thinking pauses | "..." before first response | ~25% |

Background noise profiles (`cafe`, `street`, `office`, `car`, `wind`) make it even more realistic.

## CI/CD Integration

ColdCall exits with code 0 on pass, 1 on fail. Drop it into your pipeline:

```yaml
# .github/workflows/voice-test.yml
- name: Test voice agent
  run: |
    coldcall serve \
      --scenario dental-appointment \
      --ci --once --timeout 120 \
      --public-url "$PUBLIC_URL"
  env:
    TWILIO_ACCOUNT_SID: ${{ secrets.TWILIO_ACCOUNT_SID }}
    TWILIO_AUTH_TOKEN: ${{ secrets.TWILIO_AUTH_TOKEN }}
    DEEPGRAM_API_KEY: ${{ secrets.DEEPGRAM_API_KEY }}
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    CARTESIA_API_KEY: ${{ secrets.CARTESIA_API_KEY }}
    PUBLIC_URL: ${{ secrets.PUBLIC_URL }}
```

See [docs/ci-guide.md](docs/ci-guide.md) for the full setup guide.

## Configuration

### `coldcall.yaml`

```yaml
twilio:
  account_sid: ""
  auth_token: ""
deepgram:
  api_key: ""
openai:
  api_key: ""
cartesia:
  api_key: ""
server:
  public_url: ""       # your ngrok/tunnel URL
  port: 8080
defaults:
  scenario: "dental-appointment"
  area_code: "415"
```

Environment variables (`TWILIO_ACCOUNT_SID`, etc.) also work and override the YAML config.

### CLI reference

```
coldcall serve       Start server and listen for calls
coldcall call        Make an outbound call to a target agent
coldcall setup       Provision Twilio phone number
coldcall scenarios   List or create scenarios
coldcall results     View test results
coldcall report      Generate JSON + HTML reports
coldcall evaluate    Re-run LLM judge on a transcript
coldcall metrics     Re-compute audio metrics
coldcall recording   Download a Twilio recording
```

## Dashboard

Start the server and visit `http://localhost:8080/` for the web dashboard:
- Browse and create scenarios
- View call results with pass/fail badges
- Inspect transcripts, metrics, and evaluations
- Create custom scenarios via the UI

## Results

Each test produces a directory with everything:

```
results/2026-04-10T14:23:00/
├── metadata.json        # call info, timing, scenario name
├── transcript.json      # speaker-labeled turns with timestamps
├── metrics.json         # latency percentiles, interruptions, gaps
├── evaluation.json      # per-criteria pass/fail from LLM judge
├── report.json          # CI-friendly summary
├── report.html          # self-contained shareable report with audio player
├── agent_audio.wav      # what the target agent said
├── caller_audio.wav     # what ColdCall said
└── mixed_audio.wav      # both channels mixed
```

## Roadmap

- [ ] WebRTC transport (Daily) for Pipecat users
- [ ] WebRTC transport (LiveKit) for LiveKit users
- [ ] Multi-scenario batch runs
- [ ] Concurrent test calls
- [ ] Webhook results (POST to URL after each test)
- [ ] ColdCall Cloud (hosted, no infra setup)
- [ ] Public leaderboard for voice AI platforms

## Contributing

Contributions welcome. The easiest ways to help:

- **Add scenarios** — Write a YAML file, open a PR. See [scenarios/](scenarios/) for examples.
- **Improve the humanizer** — Add filler patterns, better correction templates.
- **Add noise profiles** — Generate realistic ambient audio.
- **Report bugs** — Open an issue with your scenario YAML and the error.

```bash
git clone https://github.com/kollaikal-rupesh/coldcall
cd coldcall
uv sync
coldcall --help
```

## License

MIT
