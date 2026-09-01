import json

import pytest

from app.profile_identity import (
    InvalidProfileOwner,
    canonicalize_activity,
    canonicalize_agent,
)


def test_canonicalizes_only_mbox_domain_case():
    agent = json.dumps(
        {"objectType": "Agent", "name": "Example", "mbox": "mailto:User@EXAMPLE.COM"}
    )

    identity = canonicalize_agent(agent)

    assert identity.owner_key == "mbox:mailto:User@example.com"


def test_name_does_not_affect_agent_identity():
    first = canonicalize_agent(json.dumps({"name": "First", "mbox": "mailto:a@example.com"}))
    second = canonicalize_agent(json.dumps({"name": "Second", "mbox": "mailto:a@example.com"}))

    assert first == second


def test_requires_exactly_one_agent_identifier():
    with pytest.raises(InvalidProfileOwner, match="exactly one"):
        canonicalize_agent(json.dumps({"objectType": "Agent"}))

    with pytest.raises(InvalidProfileOwner, match="exactly one"):
        canonicalize_agent(
            json.dumps(
                {
                    "mbox": "mailto:a@example.com",
                    "openid": "https://example.com/users/a",
                }
            )
        )


@pytest.mark.parametrize("identifier", ["account", "openid", "mbox_sha1sum"])
def test_marks_future_agent_identifiers_as_explicitly_unsupported(identifier):
    with pytest.raises(InvalidProfileOwner, match="not supported yet"):
        canonicalize_agent(json.dumps({identifier: "placeholder"}))


def test_rejects_group_for_agent_profile():
    with pytest.raises(InvalidProfileOwner, match="must be Agent"):
        canonicalize_agent(
            json.dumps({"objectType": "Group", "mbox": "mailto:group@example.com"})
        )


def test_accepts_absolute_activity_iri():
    assert (
        canonicalize_activity("https://example.com/activities/course-1")
        == "https://example.com/activities/course-1"
    )


def test_rejects_relative_activity_id():
    with pytest.raises(InvalidProfileOwner, match="absolute IRI"):
        canonicalize_activity("activities/course-1")
