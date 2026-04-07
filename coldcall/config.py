"""Configuration loading for ColdCall.

Priority: CLI flags > environment variables > coldcall.yaml > defaults.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

CONFIG_FILENAMES = ["coldcall.yaml", "coldcall.yml"]


@dataclass
class TwilioConfig:
    account_sid: str = ""
    auth_token: str = ""


@dataclass
class ServerConfig:
    public_url: str = ""
    port: int = 8080


@dataclass
class DefaultsConfig:
    scenario: str = "dental-appointment"
    area_code: str = "415"


@dataclass
class LiveKitConfig:
    url: str = ""
    api_key: str = ""
    api_secret: str = ""


@dataclass
class ColdCallConfig:
    twilio: TwilioConfig = field(default_factory=TwilioConfig)
    livekit: LiveKitConfig = field(default_factory=LiveKitConfig)
    deepgram_api_key: str = ""
    openai_api_key: str = ""
    cartesia_api_key: str = ""
    server: ServerConfig = field(default_factory=ServerConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    _path: Path | None = None


def find_config_file() -> Path | None:
    """Find coldcall.yaml in cwd or parent dirs."""
    cwd = Path.cwd()
    for name in CONFIG_FILENAMES:
        p = cwd / name
        if p.exists():
            return p
    return None


def load_config(path: Path | None = None) -> ColdCallConfig:
    """Load config from YAML file, falling back to environment variables."""
    load_dotenv()

    cfg = ColdCallConfig()

    # Load YAML if available
    if path is None:
        path = find_config_file()

    if path and path.exists():
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as e:
            raise RuntimeError(f"Error parsing {path}: {e}") from e
        cfg._path = path

        tw = data.get("twilio", {})
        cfg.twilio.account_sid = tw.get("account_sid", "")
        cfg.twilio.auth_token = tw.get("auth_token", "")

        lk = data.get("livekit", {})
        cfg.livekit.url = lk.get("url", "")
        cfg.livekit.api_key = lk.get("api_key", "")
        cfg.livekit.api_secret = lk.get("api_secret", "")

        cfg.deepgram_api_key = data.get("deepgram", {}).get("api_key", "")
        cfg.openai_api_key = data.get("openai", {}).get("api_key", "")
        cfg.cartesia_api_key = data.get("cartesia", {}).get("api_key", "")

        srv = data.get("server", {})
        cfg.server.public_url = srv.get("public_url", "")
        cfg.server.port = srv.get("port", 8080)

        defs = data.get("defaults", {})
        cfg.defaults.scenario = defs.get("scenario", "dental-appointment")
        cfg.defaults.area_code = defs.get("area_code", "415")

    # Environment variables override YAML
    cfg.twilio.account_sid = os.getenv("TWILIO_ACCOUNT_SID", cfg.twilio.account_sid)
    cfg.twilio.auth_token = os.getenv("TWILIO_AUTH_TOKEN", cfg.twilio.auth_token)
    cfg.livekit.url = os.getenv("LIVEKIT_URL", cfg.livekit.url)
    cfg.livekit.api_key = os.getenv("LIVEKIT_API_KEY", cfg.livekit.api_key)
    cfg.livekit.api_secret = os.getenv("LIVEKIT_API_SECRET", cfg.livekit.api_secret)
    cfg.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY", cfg.deepgram_api_key)
    cfg.openai_api_key = os.getenv("OPENAI_API_KEY", cfg.openai_api_key)
    cfg.cartesia_api_key = os.getenv("CARTESIA_API_KEY", cfg.cartesia_api_key)

    return cfg


def apply_config_to_env(cfg: ColdCallConfig):
    """Push config values into environment variables for libraries that read them."""
    if cfg.twilio.account_sid:
        os.environ["TWILIO_ACCOUNT_SID"] = cfg.twilio.account_sid
    if cfg.twilio.auth_token:
        os.environ["TWILIO_AUTH_TOKEN"] = cfg.twilio.auth_token
    if cfg.livekit.url:
        os.environ["LIVEKIT_URL"] = cfg.livekit.url
    if cfg.livekit.api_key:
        os.environ["LIVEKIT_API_KEY"] = cfg.livekit.api_key
    if cfg.livekit.api_secret:
        os.environ["LIVEKIT_API_SECRET"] = cfg.livekit.api_secret
    if cfg.deepgram_api_key:
        os.environ["DEEPGRAM_API_KEY"] = cfg.deepgram_api_key
    if cfg.openai_api_key:
        os.environ["OPENAI_API_KEY"] = cfg.openai_api_key
    if cfg.cartesia_api_key:
        os.environ["CARTESIA_API_KEY"] = cfg.cartesia_api_key


def save_config(cfg: ColdCallConfig, path: Path | None = None):
    """Save config to YAML file."""
    if path is None:
        path = cfg._path or Path("coldcall.yaml")

    data = {
        "twilio": {
            "account_sid": cfg.twilio.account_sid,
            "auth_token": cfg.twilio.auth_token,
        },
        "deepgram": {"api_key": cfg.deepgram_api_key},
        "openai": {"api_key": cfg.openai_api_key},
        "cartesia": {"api_key": cfg.cartesia_api_key},
        "server": {
            "public_url": cfg.server.public_url,
            "port": cfg.server.port,
        },
        "defaults": {
            "scenario": cfg.defaults.scenario,
            "area_code": cfg.defaults.area_code,
        },
    }

    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
