import json
from pathlib import Path

import pytest

import task_schema


def v1_index():
    return {
        "project": "Demo",
        "phase": "0-example",
        "steps": [
            {"step": 0, "name": "setup", "status": "completed", "summary": "골격 완료"},
            {"step": 1, "name": "feature", "status": "pending"},
        ],
    }


def v2_index():
    return {
        "schemaVersion": 2,
        "project": "Demo",
        "phase": "0-v2-example",
        "tasks": [
            {
                "id": "setup",
                "objective": "프로젝트 골격을 완성한다.",
                "dependsOn": [],
                "issue": 16,
                "risk": "low",
                "status": "completed",
                "summary": "골격 완료",
            },
            {
                "id": "feature",
                "objective": "핵심 기능을 완성한다.",
                "dependsOn": ["setup"],
                "risk": "medium",
                "status": "pending",
            },
        ],
    }


def assert_schema_error(payload, expected):
    with pytest.raises(task_schema.TaskSchemaError) as exc_info:
        task_schema.normalize_phase_index(payload, path="phases/0-v2-example/index.json")
    message = str(exc_info.value)
    for fragment in expected:
        assert fragment in message
    return exc_info.value


def test_normalizes_v1_without_mutating_or_migrating_payload():
    payload = v1_index()
    original = json.loads(json.dumps(payload, ensure_ascii=False))

    normalized = task_schema.normalize_phase_index(payload, path="phases/0-example/index.json")

    assert normalized.schema_version == 1
    assert normalized.format_name == "v1"
    assert normalized.task_key == "steps"
    assert [(task["step"], task["name"], task["status"]) for task in normalized["steps"]] == [
        (0, "setup", "completed"),
        (1, "feature", "pending"),
    ]
    assert payload == original
    assert normalized.to_payload() == original


def test_normalizes_v2_outcome_fields_and_preserves_v2_shape():
    payload = v2_index()

    normalized = task_schema.normalize_phase_index(payload, path="phases/0-v2-example/index.json")

    assert normalized.schema_version == 2
    assert normalized.format_name == "v2"
    assert normalized.task_key == "tasks"
    assert normalized["steps"][0]["step"] == 0
    assert normalized["steps"][0]["name"] == "setup"
    assert normalized["steps"][1]["id"] == "feature"
    assert normalized["steps"][1]["objective"] == "핵심 기능을 완성한다."
    assert normalized["steps"][1]["dependsOn"] == ["setup"]
    assert normalized["steps"][0]["issue"] == 16
    assert normalized["steps"][0]["risk"] == "low"
    assert normalized.to_payload() == payload
    assert "steps" not in normalized.to_payload()


def test_v2_defaults_missing_dependencies_to_empty_list():
    payload = v2_index()
    del payload["tasks"][1]["dependsOn"]

    normalized = task_schema.normalize_phase_index(payload)

    assert normalized["steps"][1]["dependsOn"] == []
    assert normalized.to_payload() == payload


def test_normalized_v2_syncs_lifecycle_updates_without_writing_v1_aliases():
    payload = v2_index()
    normalized = task_schema.normalize_phase_index(payload)
    normalized["steps"][1]["status"] = "completed"
    normalized["steps"][1]["summary"] = "기능 완료"
    normalized["completed_at"] = "2026-09-04T12:00:00+0900"

    saved = normalized.to_payload()

    assert saved["tasks"][1]["status"] == "completed"
    assert saved["tasks"][1]["summary"] == "기능 완료"
    assert saved["completed_at"] == "2026-09-04T12:00:00+0900"
    assert "step" not in saved["tasks"][1]
    assert "name" not in saved["tasks"][1]


def test_duplicate_v2_ids_are_rejected_with_field_path():
    payload = v2_index()
    payload["tasks"][1]["id"] = "setup"

    assert_schema_error(
        payload,
        ["phases/0-v2-example/index.json", "tasks[1].id", "duplicate id 'setup'"],
    )


def test_unknown_dependency_is_rejected_with_dependency_path():
    payload = v2_index()
    payload["tasks"][1]["dependsOn"] = ["missing"]

    assert_schema_error(
        payload,
        ["tasks[1].dependsOn[0]", "unknown task id 'missing'"],
    )


def test_self_dependency_is_rejected_before_execution():
    payload = v2_index()
    payload["tasks"][1]["dependsOn"] = ["feature"]

    assert_schema_error(
        payload,
        ["tasks[1].dependsOn[0]", "self dependency"],
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("id", 1, "id must be a string"),
        ("objective", ["outcome"], "objective must be a string"),
        ("dependsOn", "setup", "dependsOn must be a list"),
        ("issue", True, "issue must be a positive integer"),
        ("risk", 3, "risk must be a string"),
        ("status", "running", "status must be one of"),
    ],
)
def test_v2_field_contract_rejects_wrong_types_or_status(field, value, reason):
    payload = v2_index()
    payload["tasks"][1][field] = value

    assert_schema_error(payload, [f"tasks[1].{field}", reason])


def test_v1_status_contract_is_shared_with_v2():
    payload = v1_index()
    payload["steps"][1]["status"] = "running"

    error = assert_schema_error(
        payload,
        ["phases/0-v2-example/index.json", "step 1 status must be one of"],
    )

    assert set(task_schema.VALID_STATUSES) == {"pending", "completed", "error", "blocked"}
    assert error.errors[0].path.endswith("steps[1].status")


def test_schema_discriminator_rejects_mixed_or_unsupported_shapes():
    mixed = v2_index()
    mixed["steps"] = []
    assert_schema_error(mixed, ["schemaVersion 2 requires `tasks` and cannot contain `steps`"])

    unsupported = v1_index()
    unsupported["schemaVersion"] = 3
    assert_schema_error(unsupported, ["schemaVersion", "must be 1 or 2"])


def test_load_phase_index_reports_json_path(tmp_path: Path):
    path = tmp_path / "index.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(task_schema.TaskSchemaError, match="phases/demo/index.json"):
        task_schema.load_phase_index(path, display_path="phases/demo/index.json")
