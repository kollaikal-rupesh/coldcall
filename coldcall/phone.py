"""Provision, configure, and make calls with Twilio phone numbers."""

import os

import requests
from dotenv import load_dotenv
from twilio.rest import Client


def get_client() -> Client:
    load_dotenv()
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    return Client(sid, token)


def list_numbers(client: Client) -> list:
    return client.incoming_phone_numbers.list()


def buy_number(client: Client, area_code: str = "415") -> str:
    """Buy a local US number. Returns the phone number SID."""
    available = client.available_phone_numbers("US").local.list(
        area_code=area_code, limit=1
    )
    if not available:
        raise RuntimeError(f"No numbers available for area code {area_code}")

    number = client.incoming_phone_numbers.create(
        phone_number=available[0].phone_number,
        friendly_name="coldcall",
    )
    print(f"Bought {number.phone_number} (SID: {number.sid})")
    return number.sid


def configure_webhook(client: Client, phone_sid: str, webhook_url: str):
    """Point a phone number's voice webhook at our server."""
    client.incoming_phone_numbers(phone_sid).update(
        voice_url=webhook_url,
        voice_method="POST",
        status_callback=webhook_url.rstrip("/").replace("/voice", "") + "/voice/status",
        status_callback_method="POST",
    )
    print(f"Configured {phone_sid} -> {webhook_url}")


def provision(webhook_url: str, area_code: str = "415") -> str:
    """Buy a number (or reuse existing coldcall number) and point it at webhook_url."""
    client = get_client()

    # Reuse existing coldcall number if we have one
    existing = [n for n in list_numbers(client) if n.friendly_name == "coldcall"]
    if existing:
        phone = existing[0]
        print(f"Reusing existing number {phone.phone_number} (SID: {phone.sid})")
        phone_sid = phone.sid
    else:
        phone_sid = buy_number(client, area_code)

    configure_webhook(client, phone_sid, webhook_url)

    # Fetch the number to return it
    phone = client.incoming_phone_numbers(phone_sid).fetch()
    return phone.phone_number


def get_coldcall_number(client: Client) -> str:
    """Get the coldcall phone number. Raises if not provisioned."""
    existing = [n for n in list_numbers(client) if n.friendly_name == "coldcall"]
    if not existing:
        raise RuntimeError("No coldcall number provisioned. Run 'coldcall provision' first.")
    return existing[0].phone_number


def make_outbound_call(to_number: str, public_url: str, websocket_url: str) -> str:
    """Make an outbound call to a target number, connecting via Media Stream WebSocket.

    Returns the Call SID.
    """
    client = get_client()
    from_number = get_coldcall_number(client)

    twiml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response>'
        f'<Start>'
        f'<Recording name="coldcall" track="both" channels="dual" '
        f'recordingStatusCallback="{public_url}/recording-status" '
        f'recordingStatusCallbackEvent="in-progress completed" '
        f'trim="do-not-trim" />'
        f'</Start>'
        f'<Connect><Stream url="{websocket_url}" /></Connect>'
        f'</Response>'
    )

    call = client.calls.create(
        from_=from_number,
        to=to_number,
        twiml=twiml,
        status_callback=f"{public_url}/voice/status",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )

    print(f"Outbound call initiated")
    print(f"  From: {from_number}")
    print(f"  To:   {to_number}")
    print(f"  Call SID: {call.sid}")
    return call.sid


def download_recording(recording_sid: str, output_path: str = "recording.mp3"):
    """Download a Twilio recording as MP3."""
    load_dotenv()
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"
        f"/Recordings/{recording_sid}.mp3"
    )
    resp = requests.get(url, auth=(account_sid, auth_token))
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(resp.content)

    size_kb = len(resp.content) / 1024
    print(f"Downloaded {output_path} ({size_kb:.0f} KB)")
