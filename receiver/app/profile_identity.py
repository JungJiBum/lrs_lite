import json
from dataclasses import dataclass
from urllib.parse import urlparse


class InvalidProfileOwner(ValueError):
    pass


@dataclass(frozen=True)
class AgentIdentity:
    kind: str
    value: str

    @property
    def owner_key(self) -> str:
        return f"{self.kind}:{self.value}"


def canonicalize_agent(agent_parameter: str) -> AgentIdentity:
    try:
        agent = json.loads(agent_parameter)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidProfileOwner("agent must be a JSON object") from exc

    if not isinstance(agent, dict):
        raise InvalidProfileOwner("agent must be a JSON object")
    if agent.get("objectType", "Agent") != "Agent":
        raise InvalidProfileOwner("agent.objectType must be Agent")

    ifi_names = ("mbox", "mbox_sha1sum", "openid", "account")
    present_ifis = [name for name in ifi_names if name in agent]
    if len(present_ifis) != 1:
        raise InvalidProfileOwner("agent must contain exactly one inverse functional identifier")

    ifi_name = present_ifis[0]
    if ifi_name != "mbox":
        raise InvalidProfileOwner(f"agent identifier {ifi_name} is not supported yet")

    return AgentIdentity(kind="mbox", value=_canonicalize_mbox(agent["mbox"]))


def canonicalize_activity(activity_id: str) -> str:
    parsed = urlparse(activity_id)
    if not parsed.scheme:
        raise InvalidProfileOwner("activityId must be an absolute IRI")
    return activity_id


def _canonicalize_mbox(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("mailto:"):
        raise InvalidProfileOwner("agent.mbox must be a mailto IRI")

    address = value[7:]
    if address.count("@") != 1:
        raise InvalidProfileOwner("agent.mbox must contain a valid email address")

    local_part, domain = address.rsplit("@", 1)
    if not local_part or not domain:
        raise InvalidProfileOwner("agent.mbox must contain a valid email address")

    # xAPI specifies only the domain portion of an mbox as case-insensitive.
    return f"mailto:{local_part}@{domain.lower()}"
