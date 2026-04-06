"""Provision, configure, and make calls with Twilio phone numbers."""

import logging
import os

import requests
from dotenv import load_dotenv
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

log = logging.getLogger("coldcall")


def get_client() -> Client:
    """Create a Twilio client from environment variables."""
    load_dotenv()
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise RuntimeError(
            "Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN. "
            "Set them in coldcall.yaml or environment variables."
        )
    return Client(sid, token)


def list_numbers(client: Client) -> list:
    """List all phone numbers on the account."""
    try:
        return client.incoming_phone_numbers.list()
    except TwilioRestException as e:
        raise RuntimeError(f"Failed to list Twilio numbers: {e.msg}") from e


def buy_number(client: Client, area_code: str = "415") -> str:
    """Buy a local US number. Returns the phone number SID."""
    try:
        available = client.available_phone_numbers("US").local.list(
            area_code=area_code, limit=1
        )
    except TwilioRestException as e:
        raise RuntimeError(f"Failed to search available numbers: {e.msg}") from e

    if not available:
        raise RuntimeError(f"No numbers available for area code {area_code}")

    try:
        number = client.incoming_phone_numbers.create(
            phone_number=available[0].phone_number,
            friendly_name="coldcall",
        )
    except TwilioRestException as e:
        raise RuntimeError(f"Failed to buy number: {e.msg}") from e

    log.info(f"Bought {number.phone_number} (SID: {number.sid})")
    return number.sid


def configure_webhook(client: Client, phone_sid: str, webhook_url: str) -> None:
    """Point a phone number's voice webhook at our server."""
    try:
        client.incoming_phone_numbers(phone_sid).update(
            voice_url=webhook_url,
            voice_method="POST",
            status_callback=webhook_url.rstrip("/").replace("/voice", "") + "/voice/status",
            status_callback_method="POST",
        )
    except TwilioRestException as e:
        raise RuntimeError(f"Failed to configure webhook: {e.msg}") from e

    log.info(f"Configured {phone_sid} -> {webhook_url}")


def provision(webhook_url: str, area_code: str = "415") -> str:
    """Buy a number (or reuse existing coldcall number) and point it at webhook_url."""
    client = get_client()

    existing = [n for n in list_numbers(client) if n.friendly_name == "coldcall"]
    if existing:
        phone = existing[0]
        log.info(f"Reusing existing number {phone.phone_number} (SID: {phone.sid})")
        phone_sid = phone.sid
    else:
        phone_sid = buy_number(client, area_code)

    configure_webhook(client, phone_sid, webhook_url)

    phone = client.incoming_phone_numbers(phone_sid).fetch()
    return phone.phone_number


def get_coldcall_number(client: Client) -> str:
    """Get the coldcall phone number. Raises if not provisioned."""
    existing = [n for n in list_numbers(client) if n.friendly_name == "coldcall"]
    if not existing:
        raise RuntimeError(
            "No coldcall number provisioned. Run 'coldcall setup --provider twilio' first."
        )
    return existing[0].phone_number


def make_outbound_call(to_number: str, public_url: str, websocket_url: str) -> str:
    """Make an outbound call connecting via Media Stream WebSocket. Returns Call SID."""
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

    try:
        call = client.calls.create(
            from_=from_number,
            to=to_number,
            twiml=twiml,
            status_callback=f"{public_url}/voice/status",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )
    except TwilioRestException as e:
        raise RuntimeError(f"Failed to place outbound call: {e.msg}") from e

    log.info(f"Outbound call: {from_number} -> {to_number} (SID: {call.sid})")
    return call.sid


def download_recording(recording_sid: str, output_path: str = "recording.mp3") -> None:
    """Download a Twilio recording as MP3."""
    load_dotenv()
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        raise RuntimeError("Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN")

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"
        f"/Recordings/{recording_sid}.mp3"
    )
    resp = requests.get(url, auth=(account_sid, auth_token), timeout=30)
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(resp.content)

    size_kb = len(resp.content) / 1024
    log.info(f"Downloaded {output_path} ({size_kb:.0f} KB)")
