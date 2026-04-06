# How to add voice agent tests to your CI/CD pipeline

ColdCall can run as part of your CI/CD pipeline to automatically test voice agents on every push or PR.

## How it works

1. ColdCall starts a server and waits for an inbound call (or makes an outbound call)
2. When the call connects, the bot runs through the scenario
3. After the call ends, ColdCall evaluates the transcript against success criteria
4. In CI mode (`--ci`), it exits with code 0 on PASS, 1 on FAIL

## Prerequisites

You need:
- A Twilio account with a provisioned phone number
- A publicly reachable URL for webhooks (use a static endpoint or tunnel)
- API keys for Deepgram (STT), OpenAI (LLM judge), and Cartesia (TTS)

### Setting up a persistent webhook URL

For CI, you need a stable public URL. Options:

1. **ngrok with a reserved domain** (recommended for testing):
   ```bash
   ngrok http 8080 --domain=your-reserved-domain.ngrok.app
   ```

2. **Deploy ColdCall to a cloud server** (recommended for production CI):
   Deploy the server to Railway, Render, Fly.io, or any platform that gives you a stable URL.

3. **Use a GitHub Actions self-hosted runner** with a known public IP.

## GitHub Actions setup

### 1. Add secrets to your repository

Go to Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|--------|-------|
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token |
| `DEEPGRAM_API_KEY` | Deepgram API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `CARTESIA_API_KEY` | Cartesia API key |
| `PUBLIC_URL` | Your stable public URL (e.g. `https://your-domain.ngrok.app`) |

### 2. Add the workflow

```yaml
# .github/workflows/voice-test.yml
name: Voice Agent Test
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Install ColdCall
        run: uv sync

      - name: Run voice agent test
        run: |
          uv run coldcall serve \
            --scenario dental-appointment \
            --ci \
            --once \
            --timeout 120 \
            --public-url "$PUBLIC_URL"
        env:
          TWILIO_ACCOUNT_SID: ${{ secrets.TWILIO_ACCOUNT_SID }}
          TWILIO_AUTH_TOKEN: ${{ secrets.TWILIO_AUTH_TOKEN }}
          DEEPGRAM_API_KEY: ${{ secrets.DEEPGRAM_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          CARTESIA_API_KEY: ${{ secrets.CARTESIA_API_KEY }}
          PUBLIC_URL: ${{ secrets.PUBLIC_URL }}

      - name: Generate reports
        if: always()
        run: uv run coldcall report --last

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: voice-test-results
          path: results/
          retention-days: 30
```

### 3. Trigger a test

The test will run on every push to `main` or on PRs. You can also trigger it manually from the Actions tab.

## CLI flags for CI

| Flag | Purpose |
|------|---------|
| `--ci` | Machine-readable JSON output, no colors |
| `--once` | Exit after one call completes (don't keep listening) |
| `--timeout 120` | Abort if no call within 120 seconds |
| `--scenario X` | Which scenario to run |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All criteria passed |
| 1 | One or more criteria failed, or timeout/error |

## Running multiple scenarios

Test several scenarios in one workflow:

```yaml
    strategy:
      matrix:
        scenario:
          - dental-appointment
          - order-status
          - angry-refund
          - prompt-extraction

    steps:
      # ... setup steps ...
      - name: Run ${{ matrix.scenario }}
        run: |
          uv run coldcall serve \
            --scenario ${{ matrix.scenario }} \
            --ci --once --timeout 120 \
            --public-url "$PUBLIC_URL"
```

## Viewing results

After the workflow completes:
1. Go to the workflow run in GitHub Actions
2. Download the `voice-test-results` artifact
3. Open `report.html` in a browser — it's a self-contained file with embedded audio player, transcript, metrics, and pass/fail badges

Or view the JSON report programmatically:
```bash
cat results/*/report.json | jq '.result'
```
