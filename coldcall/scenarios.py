"""Scenario configuration for ColdCall test calls.

Supports two YAML formats:

Simple (drop-in):
    name: appointment_booking
    persona: |
      You are Sarah, a 35-year-old woman calling to book a dental cleaning...
    goal: Book a dental cleaning appointment
    success_criteria:
      - "agent confirmed appointment day and time"
      - "agent confirmed caller's name"
    max_duration_seconds: 120

Rich (full control):
    name: dental-appointment
    description: Customer calling to book a dental appointment
    goal: Successfully book a dental appointment
    max_duration_seconds: 120
    persona:
      name: Sarah Mitchell
      phone: "555-0142"
      voice_id: "694f9389-aac1-45b6-b726-9d9369183238"
      system_prompt: |
        You are Sarah...
    success_criteria:
      - id: greeting
        description: Agent greets the caller professionally
      - "agent confirms the appointment"
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"

# Default Cartesia voice (Sarah)
DEFAULT_VOICE_ID = "694f9389-aac1-45b6-b726-9d9369183238"
DEFAULT_MAX_DURATION = 120

# Conversational style instructions appended to simple persona prompts
PHONE_STYLE = (
    "\n\nKeep your responses conversational and brief — you're on a phone call. "
    "Respond naturally, like a real person would on the phone. "
    "Don't use bullet points or lists. One or two sentences at a time."
)


@dataclass
class Criterion:
    id: str
    description: str


@dataclass
class Persona:
    name: str
    phone: str
    voice_id: str
    system_prompt: str


@dataclass
class Scenario:
    name: str
    description: str
    goal: str
    persona: Persona
    success_criteria: list[Criterion] = field(default_factory=list)
    max_duration_seconds: int = DEFAULT_MAX_DURATION
    humanize: bool = True
    noise_profile: str = ""
    noise_volume: float = 0.15

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Scenario":
        """Load a scenario from a YAML file or name.

        Accepts:
          - A full path: "scenarios/my-test.yaml"
          - A name: "dental-appointment" (looked up in scenarios/ dir)
        """
        path = _resolve_path(path)
        data = yaml.safe_load(path.read_text())
        _validate(data, path)

        persona = _parse_persona(data.get("persona", ""))
        criteria = _parse_criteria(data.get("success_criteria", []))

        return cls(
            name=data["name"],
            description=data.get("description", data["goal"]),
            goal=data["goal"],
            persona=persona,
            success_criteria=criteria,
            max_duration_seconds=data.get("max_duration_seconds", DEFAULT_MAX_DURATION),
            humanize=data.get("humanize", True),
            noise_profile=data.get("noise_profile", ""),
            noise_volume=data.get("noise_volume", 0.15),
        )

    def criteria_text(self) -> str:
        """Format success criteria as numbered list for the judge prompt."""
        lines = []
        for i, c in enumerate(self.success_criteria, 1):
            lines.append(f"{i}. [{c.id}] {c.description}")
        return "\n".join(lines)


def list_scenarios() -> list[str]:
    """List available scenario names from the scenarios directory."""
    if not SCENARIOS_DIR.exists():
        return []
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))


def _resolve_path(path: str | Path) -> Path:
    """Resolve a scenario name or path to an actual file."""
    path = Path(path)
    if path.exists():
        return path

    # Try scenarios directory with .yaml extension
    alt = SCENARIOS_DIR / f"{path}.yaml"
    if alt.exists():
        return alt

    # Try scenarios directory as-is
    alt2 = SCENARIOS_DIR / path
    if alt2.exists():
        return alt2

    available = list_scenarios()
    hint = f" Available: {', '.join(available)}" if available else ""
    raise FileNotFoundError(f"Scenario not found: {path}.{hint}")


def _validate(data: dict, path: Path):
    """Validate required fields in scenario YAML."""
    if not isinstance(data, dict):
        raise ValueError(f"Invalid scenario file (not a YAML mapping): {path}")

    missing = []
    for field in ("name", "goal"):
        if field not in data:
            missing.append(field)

    if "persona" not in data:
        missing.append("persona")

    if missing:
        raise ValueError(
            f"Scenario {path} missing required fields: {', '.join(missing)}"
        )

    if "success_criteria" in data:
        criteria = data["success_criteria"]
        if not isinstance(criteria, list):
            raise ValueError(
                f"Scenario {path}: success_criteria must be a list"
            )
        for i, c in enumerate(criteria):
            if not isinstance(c, (str, dict)):
                raise ValueError(
                    f"Scenario {path}: success_criteria[{i}] must be a string or dict"
                )
            if isinstance(c, dict) and "description" not in c:
                raise ValueError(
                    f"Scenario {path}: success_criteria[{i}] dict must have 'description'"
                )


def _parse_persona(raw) -> Persona:
    """Parse persona from string or dict format."""
    if isinstance(raw, str):
        # Simple format: persona is the system prompt text
        prompt = raw.strip()
        if not any(kw in prompt.lower() for kw in ["brief", "concise", "short", "phone call"]):
            prompt += PHONE_STYLE

        return Persona(
            name=_extract_name(prompt),
            phone="",
            voice_id=DEFAULT_VOICE_ID,
            system_prompt=prompt,
        )

    if isinstance(raw, dict):
        # Rich format: explicit fields
        system_prompt = raw.get("system_prompt", "").strip()
        if not system_prompt:
            raise ValueError("persona.system_prompt is required when persona is a dict")

        return Persona(
            name=raw.get("name", _extract_name(system_prompt)),
            phone=str(raw.get("phone", "")),
            voice_id=raw.get("voice_id", DEFAULT_VOICE_ID),
            system_prompt=system_prompt,
        )

    raise ValueError(f"persona must be a string or dict, got {type(raw).__name__}")


def _parse_criteria(raw: list) -> list[Criterion]:
    """Parse success criteria from strings or dicts."""
    criteria = []
    for i, item in enumerate(raw):
        if isinstance(item, str):
            # Auto-generate ID from description
            cid = _slugify(item)
            criteria.append(Criterion(id=cid, description=item))
        elif isinstance(item, dict):
            cid = item.get("id", _slugify(item["description"]))
            criteria.append(Criterion(id=cid, description=item["description"]))
    return criteria


def _extract_name(prompt: str) -> str:
    """Try to extract a persona name from a system prompt."""
    # Match patterns like "You are Sarah", "Your name is Sarah Mitchell"
    patterns = [
        r"[Yy]our name is (\w+(?:\s\w+)?)",
        r"[Yy]ou are (\w+),",
        r"[Yy]ou are (\w+)\.",
        r"[Yy]ou are (\w+) ",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt)
        if match:
            return match.group(1)
    return "Caller"


def _slugify(text: str) -> str:
    """Convert a description string to a snake_case ID."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", "_", text)
    # Truncate to reasonable length
    return text[:50].rstrip("_")
