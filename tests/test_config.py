"""Tests for configuration loading."""

import os
import tempfile
from pathlib import Path

import pytest

from coldcall.config import load_config, ColdCallConfig


class TestConfigLoading:
    def test_default_config(self):
        cfg = load_config(Path("/nonexistent/path.yaml"))
        assert isinstance(cfg, ColdCallConfig)
        assert cfg.server.port == 8080
        assert cfg.defaults.scenario == "dental-appointment"

    def test_yaml_config(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("twilio:\n  account_sid: ACTEST\nserver:\n  port: 9999\n")
            f.flush()
            cfg = load_config(Path(f.name))
        assert cfg.twilio.account_sid == "ACTEST"
        assert cfg.server.port == 9999

    def test_env_overrides_yaml(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("deepgram:\n  api_key: from-yaml\n")
            f.flush()
            os.environ["DEEPGRAM_API_KEY"] = "from-env"
            try:
                cfg = load_config(Path(f.name))
                assert cfg.deepgram_api_key == "from-env"
            finally:
                del os.environ["DEEPGRAM_API_KEY"]

    def test_malformed_yaml(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(":\n  bad: [yaml\n  unclosed")
            f.flush()
            with pytest.raises(RuntimeError, match="Error parsing"):
                load_config(Path(f.name))
