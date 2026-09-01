from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models import Statement


def test_generates_statement_id_when_missing(valid_statement):
    valid_statement.pop("id")

    statement = Statement.model_validate(valid_statement)

    assert isinstance(statement.id, UUID)


def test_rejects_non_uuid_statement_id(valid_statement):
    valid_statement["id"] = "not-a-uuid"

    with pytest.raises(ValidationError):
        Statement.model_validate(valid_statement)


@pytest.mark.parametrize("missing", ["actor", "verb", "object"])
def test_rejects_missing_required_statement_parts(valid_statement, missing):
    valid_statement.pop(missing)

    with pytest.raises(ValidationError):
        Statement.model_validate(valid_statement)


def test_rejects_actor_without_mailto_mbox(valid_statement):
    valid_statement["actor"]["mbox"] = "minjun.kim@example.com"

    with pytest.raises(ValidationError, match="mailto IRI"):
        Statement.model_validate(valid_statement)


@pytest.mark.parametrize("field", ["verb", "object"])
def test_rejects_non_iri_identifiers(valid_statement, field):
    valid_statement[field]["id"] = "relative/id"

    with pytest.raises(ValidationError, match="absolute IRI"):
        Statement.model_validate(valid_statement)


def test_rejects_out_of_range_scaled_score(valid_statement):
    valid_statement["result"]["score"]["scaled"] = 1.1

    with pytest.raises(ValidationError):
        Statement.model_validate(valid_statement)


def test_rejects_raw_score_outside_min_max(valid_statement):
    valid_statement["result"]["score"]["raw"] = 101

    with pytest.raises(ValidationError, match="must not exceed max"):
        Statement.model_validate(valid_statement)


def test_rejects_timestamp_without_timezone(valid_statement):
    valid_statement["timestamp"] = "2026-04-14T12:00:00"

    with pytest.raises(ValidationError, match="timezone"):
        Statement.model_validate(valid_statement)


def test_preserves_properties_outside_the_validated_subset(valid_statement):
    valid_statement["authority"] = {
        "objectType": "Agent",
        "mbox": "mailto:lrs@example.com",
    }

    statement = Statement.model_validate(valid_statement)
    dumped = statement.model_dump(mode="json")

    assert dumped["authority"] == valid_statement["authority"]


def test_serialization_can_preserve_explicit_null_without_adding_omitted_fields(valid_statement):
    valid_statement["result"]["response"] = None
    valid_statement["actor"].pop("objectType")

    statement = Statement.model_validate(valid_statement)
    dumped = statement.model_dump(mode="json", exclude_unset=True)

    assert dumped["result"]["response"] is None
    assert "objectType" not in dumped["actor"]
