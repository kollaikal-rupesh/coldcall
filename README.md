# ColdCall

Benchmark and test voice AI agents via cold calls.

## Setup

```bash
uv sync
cp coldcall.yaml.example coldcall.yaml
# Fill in your API keys
```

## Usage

```bash
# Start the server
coldcall serve --public-url https://YOUR-NGROK-URL

# List scenarios
coldcall scenarios list

# Create a new scenario
coldcall scenarios init my-test

# View results
coldcall results --last

# Set up Twilio
coldcall setup --provider twilio
```

## Dashboard

Start the server and visit `http://localhost:8080/` for the web dashboard.
