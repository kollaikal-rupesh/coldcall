"""Tests for scenario loading, validation, and edge cases."""

import tempfile
from pathlib import Path

import pytest

from coldcall.scenarios import Scenario, list_scenarios, _slugify, _extract_name


class TestScenarioLoading:
    def test_load_all_builtin_scenarios(self):
        names = list_scenarios()
        assert len(names) == 20
        for name in names:
            s = Scenario.from_yaml(name)
            assert s.name
            assert s.goal
            assert s.persona.system_prompt
            assert len(s.success_criteria) > 0
            assert s.max_duration_seconds > 0

    def test_load_by_name(self):
        s = Scenario.from_yaml("dental-appointment")
        assert s.name == "dental-appointment"
        assert s.persona.name == "Sarah Mitchell"
        assert len(s.success_criteria) == 6

    def test_load_simple_format(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("name: test\ngoal: do stuff\npersona: You are Bob.\nsuccess_criteria:\n  - did the thing\n")
            f.flush()
            s = Scenario.from_yaml(f.name)
        assert s.name == "test"
        assert s.persona.name == "Bob"
        assert s.success_criteria[0].description == "did the thing"
        assert s.humanize is True
        assert s.noise_profile == ""

    def test_load_with_noise_and_humanize(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("name: noisy\ngoal: test\npersona: You are Eve.\nnoise_profile: cafe\nnoise_volume: 0.2\nhumanize: false\n")
            f.flush()
            s = Scenario.from_yaml(f.name)
        assert s.noise_profile == "cafe"
        assert s.noise_volume == 0.2
        assert s.humanize is False

    def test_missing_required_fields(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("name: test\n")
            f.flush()
            with pytest.raises(ValueError, match="missing required fields"):
                Scenario.from_yaml(f.name)

    def test_invalid_criteria_type(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("name: test\ngoal: x\npersona: You are X.\nsuccess_criteria: not-a-list\n")
            f.flush()
            with pytest.raises(ValueError, match="must be a list"):
                Scenario.from_yaml(f.name)

    def test_not_found(self):
        with pytest.raises(FileNotFoundError, match="Scenario not found"):
            Scenario.from_yaml("nonexistent-scenario-xyz")

    def test_malformed_yaml(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(":\n  bad: [yaml\n  unclosed")
            f.flush()
            with pytest.raises(Exception):
                Scenario.from_yaml(f.name)


class TestHelpers:
    def test_slugify(self):
        assert _slugify("agent confirmed the order") == "agent_confirmed_the_order"
        assert _slugify("Agent's name was collected!") == "agents_name_was_collected"
        assert len(_slugify("a" * 100)) <= 50

    def test_extract_name(self):
        assert _extract_name("You are Sarah, a customer") == "Sarah"
        assert _extract_name("Your name is John Smith.") == "John Smith"
        assert _extract_name("No name here") == "Caller"
