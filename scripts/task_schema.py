#!/usr/bin/env python3
"""Validate and normalize Harness phase task indexes.

The template has two input formats:

* v1: ``steps[]`` entries with ``step``, ``name`` and ``status``.
* v2: ``schemaVersion: 2`` and ``tasks[]`` entries with outcome metadata.

The normalized view always exposes the v1-shaped ``steps`` list to callers.  A
writer can serialize the view back to the original shape, so merely reading a
v1 or v2 index never performs a migration.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION_KEY = "schemaVersion"
SCHEMA_V1 = 1
SCHEMA_V2 = 2
VALID_STATUSES = frozenset({"pending", "completed", "error", "blocked"})

V1_TASK_KEY = "steps"
V2_TASK_KEY = "tasks"
V2_REQUIRED_TASK_FIELDS = frozenset({"id", "objective", "status"})
V2_OPTIONAL_TASK_FIELDS = frozenset({"dependsOn", "issue", "risk"})
LIFECYCLE_FIELDS = frozenset(
    {
        "summary",
        "error_message",
        "blocked_reason",
        "started_at",
        "completed_at",
        "failed_at",
        "blocked_at",
    }
)
V2_ALLOWED_TASK_FIELDS = V2_REQUIRED_TASK_FIELDS | V2_OPTIONAL_TASK_FIELDS | LIFECYCLE_FIELDS
TOP_LEVEL_PERSISTABLE_FIELDS = frozenset({"created_at", "completed_at"})
NORMALIZED_ALIAS_FIELDS = frozenset({"step", "name"})


class SchemaIssue:
    """One path-specific schema validation failure."""

    __slots__ = ("path", "reason")

    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


class TaskSchemaError(ValueError):
    """Raised when a phase index cannot be safely read by Harness."""

    def __init__(self, errors: Iterable[SchemaIssue] | SchemaIssue | str):
        if isinstance(errors, str):
            normalized = (SchemaIssue("index.json", errors),)
        elif isinstance(errors, SchemaIssue):
            normalized = (errors,)
        else:
            normalized = tuple(errors)
        if not normalized:
            normalized = (SchemaIssue("index.json", "schema validation failed"),)
        self.errors = normalized
        self.issues = normalized
        self.path = normalized[0].path
        self.reason = normalized[0].reason
        message = "phase index schema validation failed:\n" + "\n".join(
            f"- {error}" for error in normalized
        )
        super().__init__(message)


class NormalizedTask(dict[str, Any]):
    """Dictionary-like task view with the source fields needed for round-trip writes."""

    def __init__(
        self,
        values: Mapping[str, Any],
        *,
        source_index: int,
        source_keys: Iterable[str],
        persistable_keys: Iterable[str],
    ):
        super().__init__(copy.deepcopy(dict(values)))
        self.source_index = source_index
        self.source_keys = frozenset(source_keys)
        self.persistable_keys = frozenset(persistable_keys)


class NormalizedPhaseIndex(dict[str, Any]):
    """Validated phase index with a common serial execution view.

    ``normalized["steps"]`` is the canonical list consumed by the current
    serial executor.  For v2 it is an in-memory alias only; ``to_payload``
    writes ``tasks[]`` and never writes synthetic ``step``/``name`` aliases.
    """

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        schema_version: int,
        task_key: str,
        tasks: list[NormalizedTask],
    ):
        self.schema_version = schema_version
        self.format_name = f"v{schema_version}"
        self.task_key = task_key
        self._raw_payload = copy.deepcopy(dict(payload))
        super().__init__(copy.deepcopy(dict(payload)))
        # Both names are available to callers, but only the original source
        # key is serialized by to_payload().
        self["steps"] = tasks
        self["tasks"] = tasks

    @property
    def tasks(self) -> list[NormalizedTask]:
        return self["steps"]

    def to_payload(self) -> dict[str, Any]:
        """Return the original v1/v2 shape with lifecycle changes applied."""
        payload = copy.deepcopy(self._raw_payload)

        for key, value in self.items():
            if key in {V1_TASK_KEY, V2_TASK_KEY}:
                continue
            if key in payload or key in TOP_LEVEL_PERSISTABLE_FIELDS:
                payload[key] = copy.deepcopy(value)

        source_tasks = payload[self.task_key]
        for task, source in zip(self.tasks, source_tasks):
            if not isinstance(source, dict):
                continue
            for key in list(source):
                if key not in task:
                    source.pop(key, None)
                elif key in task.source_keys:
                    source[key] = copy.deepcopy(task[key])
            for key in task.persistable_keys:
                if key in task and key not in source and key not in NORMALIZED_ALIAS_FIELDS:
                    source[key] = copy.deepcopy(task[key])

        return payload


def normalize_phase_index(
    payload: Mapping[str, Any],
    *,
    path: str | Path = "index.json",
) -> NormalizedPhaseIndex:
    """Validate an index payload and return a non-migrating normalized view."""
    display_path = str(path).replace("\\", "/")
    errors: list[SchemaIssue] = []
    if not isinstance(payload, Mapping):
        raise TaskSchemaError(SchemaIssue(display_path, "index must contain a JSON object"))

    version, task_key = _detect_schema(payload, display_path, errors)
    _validate_top_level(payload, version, task_key, display_path, errors)
    raw_tasks = payload.get(task_key) if task_key else None
    if not isinstance(raw_tasks, list):
        if task_key:
            errors.append(
                SchemaIssue(
                    f"{display_path} {task_key}",
                    f"{task_key} must be a non-empty list",
                )
            )
        raise TaskSchemaError(errors)
    if not raw_tasks:
        errors.append(SchemaIssue(f"{display_path} {task_key}", f"{task_key} must be a non-empty list"))

    tasks: list[NormalizedTask] = []
    ids: dict[str, str] = {}
    for index, raw_task in enumerate(raw_tasks):
        task_path = f"{display_path} {task_key}[{index}]"
        if version == SCHEMA_V1:
            task = _normalize_v1_task(raw_task, index, task_path, errors)
        else:
            task = _normalize_v2_task(raw_task, index, task_path, errors)
        if task is None:
            continue
        tasks.append(task)

        if version == SCHEMA_V2:
            task_id = task.get("id")
            id_path = f"{task_path}.id"
            if isinstance(task_id, str):
                previous_path = ids.get(task_id)
                if previous_path is not None:
                    errors.append(
                        SchemaIssue(
                            id_path,
                            f"duplicate id '{task_id}' (already declared at {previous_path})",
                        )
                    )
                else:
                    ids[task_id] = id_path

    if version == SCHEMA_V2:
        _validate_dependencies(tasks, ids, display_path, task_key, errors)

    if errors:
        raise TaskSchemaError(errors)

    return NormalizedPhaseIndex(
        payload,
        schema_version=version,
        task_key=task_key,
        tasks=tasks,
    )


def validate_phase_index(
    payload: Mapping[str, Any],
    *,
    path: str | Path = "index.json",
) -> NormalizedPhaseIndex:
    """Explicit alias for callers that want to emphasize validation."""
    return normalize_phase_index(payload, path=path)


def load_phase_index(path: Path, *, display_path: str | Path | None = None) -> NormalizedPhaseIndex:
    """Read, parse, validate and normalize an index file."""
    shown_path = display_path if display_path is not None else path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        shown = str(shown_path).replace("\\", "/")
        raise TaskSchemaError(SchemaIssue(shown, f"invalid JSON: {exc}")) from exc
    return normalize_phase_index(payload, path=shown_path)


def tasks_from_index(
    index: Mapping[str, Any],
    *,
    path: str | Path = "index.json",
) -> list[NormalizedTask]:
    """Return normalized serial tasks for a raw or already-normalized payload."""
    if isinstance(index, NormalizedPhaseIndex):
        return index.tasks
    return normalize_phase_index(index, path=path).tasks


def _detect_schema(
    payload: Mapping[str, Any],
    display_path: str,
    errors: list[SchemaIssue],
) -> tuple[int | None, str | None]:
    marker = payload.get(SCHEMA_VERSION_KEY)
    if SCHEMA_VERSION_KEY in payload and (isinstance(marker, bool) or not isinstance(marker, int)):
        errors.append(SchemaIssue(f"{display_path}.{SCHEMA_VERSION_KEY}", "must be an integer 1 or 2"))
        return None, None
    if marker is not None and marker not in {SCHEMA_V1, SCHEMA_V2}:
        errors.append(SchemaIssue(f"{display_path}.{SCHEMA_VERSION_KEY}", "must be 1 or 2"))
        return None, None

    has_steps = V1_TASK_KEY in payload
    has_tasks = V2_TASK_KEY in payload
    if has_steps and has_tasks:
        if marker == SCHEMA_V2:
            errors.append(
                SchemaIssue(
                    display_path,
                    "schemaVersion 2 requires `tasks` and cannot contain `steps`",
                )
            )
        else:
            errors.append(
                SchemaIssue(display_path, "define exactly one of `steps` (v1) or `tasks` (v2)")
            )
        return None, None

    if marker == SCHEMA_V1:
        if not has_steps:
            errors.append(SchemaIssue(display_path, "schemaVersion 1 requires `steps`"))
        return SCHEMA_V1, V1_TASK_KEY
    if marker == SCHEMA_V2:
        if not has_tasks:
            errors.append(SchemaIssue(display_path, "schemaVersion 2 requires `tasks`"))
        return SCHEMA_V2, V2_TASK_KEY
    if has_steps:
        return SCHEMA_V1, V1_TASK_KEY
    if has_tasks:
        return SCHEMA_V2, V2_TASK_KEY

    errors.append(SchemaIssue(display_path, "must define `steps` (v1) or `tasks` (v2)"))
    return None, None


def _validate_top_level(
    payload: Mapping[str, Any],
    version: int | None,
    task_key: str | None,
    display_path: str,
    errors: list[SchemaIssue],
) -> None:
    for key in ("project", "phase"):
        if key in payload and not _non_empty_string(payload[key]):
            errors.append(SchemaIssue(f"{display_path}.{key}", f"{key} must be a non-empty string"))

    for key in TOP_LEVEL_PERSISTABLE_FIELDS:
        if key in payload and not isinstance(payload[key], str):
            errors.append(SchemaIssue(f"{display_path}.{key}", f"{key} must be a string"))

    if version == SCHEMA_V2:
        supported = {
            SCHEMA_VERSION_KEY,
            "project",
            "phase",
            V2_TASK_KEY,
            *TOP_LEVEL_PERSISTABLE_FIELDS,
        }
        for key in payload:
            if key not in supported:
                errors.append(SchemaIssue(f"{display_path}.{key}", f"unsupported v2 field '{key}'"))


def _normalize_v1_task(
    raw_task: Any,
    index: int,
    task_path: str,
    errors: list[SchemaIssue],
) -> NormalizedTask | None:
    if not isinstance(raw_task, Mapping):
        errors.append(SchemaIssue(task_path, "step must be an object"))
        return None

    values = dict(raw_task)
    step = values.get("step")
    name = values.get("name")
    status = values.get("status")
    valid = True
    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        errors.append(SchemaIssue(f"{task_path}.step", "step must be a non-negative integer"))
        valid = False
    if not _non_empty_string(name):
        errors.append(SchemaIssue(f"{task_path}.name", "name must be a non-empty string"))
        valid = False
    if status not in VALID_STATUSES:
        label = step if isinstance(step, int) and not isinstance(step, bool) else index
        errors.append(
            SchemaIssue(
                f"{task_path}.status",
                f"step {label} status must be one of {', '.join(sorted(VALID_STATUSES))}",
            )
        )
        valid = False
    if not valid:
        return None

    values["id"] = name
    values["objective"] = values.get("objective")
    values["dependsOn"] = values.get("dependsOn", [])
    return NormalizedTask(
        values,
        source_index=index,
        source_keys=raw_task.keys(),
        persistable_keys=set(raw_task.keys()) | LIFECYCLE_FIELDS,
    )


def _normalize_v2_task(
    raw_task: Any,
    index: int,
    task_path: str,
    errors: list[SchemaIssue],
) -> NormalizedTask | None:
    if not isinstance(raw_task, Mapping):
        errors.append(SchemaIssue(task_path, "task must be an object"))
        return None

    values = dict(raw_task)
    valid = True
    unknown = set(values) - V2_ALLOWED_TASK_FIELDS
    for key in sorted(unknown):
        errors.append(SchemaIssue(f"{task_path}.{key}", f"unsupported v2 task field '{key}'"))
        valid = False

    for field in sorted(V2_REQUIRED_TASK_FIELDS):
        if field not in values:
            errors.append(SchemaIssue(f"{task_path}.{field}", f"{field} is required"))
            valid = False

    task_id = values.get("id")
    if "id" in values and not _non_empty_string(task_id):
        errors.append(SchemaIssue(f"{task_path}.id", "id must be a string"))
        valid = False

    objective = values.get("objective")
    if "objective" in values and not _non_empty_string(objective):
        errors.append(SchemaIssue(f"{task_path}.objective", "objective must be a string"))
        valid = False

    status = values.get("status")
    if status not in VALID_STATUSES:
        errors.append(
            SchemaIssue(
                f"{task_path}.status",
                f"status must be one of {', '.join(sorted(VALID_STATUSES))}",
            )
        )
        valid = False

    depends_on = values.get("dependsOn", [])
    if not isinstance(depends_on, list):
        errors.append(SchemaIssue(f"{task_path}.dependsOn", "dependsOn must be a list"))
        valid = False
    else:
        dependency_ids: set[str] = set()
        for dep_index, dependency in enumerate(depends_on):
            dependency_path = f"{task_path}.dependsOn[{dep_index}]"
            if not _non_empty_string(dependency):
                errors.append(SchemaIssue(dependency_path, "dependency id must be a string"))
                valid = False
                continue
            if dependency in dependency_ids:
                errors.append(SchemaIssue(dependency_path, f"duplicate dependency '{dependency}'"))
                valid = False
            dependency_ids.add(dependency)

    if "issue" in values:
        issue = values["issue"]
        if isinstance(issue, bool) or not isinstance(issue, int) or issue <= 0:
            errors.append(SchemaIssue(f"{task_path}.issue", "issue must be a positive integer"))
            valid = False

    if "risk" in values and not _non_empty_string(values["risk"]):
        errors.append(SchemaIssue(f"{task_path}.risk", "risk must be a string"))
        valid = False

    for field in LIFECYCLE_FIELDS:
        if field in values and not isinstance(values[field], str):
            errors.append(SchemaIssue(f"{task_path}.{field}", f"{field} must be a string"))
            valid = False

    if not valid:
        return None

    values["dependsOn"] = list(depends_on)
    # The existing executor still addresses companion stepN.md files and runs
    # serially. These aliases are only an in-memory compatibility view.
    values["step"] = index
    values["name"] = values["id"]
    return NormalizedTask(
        values,
        source_index=index,
        source_keys=raw_task.keys(),
        persistable_keys=set(raw_task.keys()) | LIFECYCLE_FIELDS,
    )


def _validate_dependencies(
    tasks: list[NormalizedTask],
    ids: Mapping[str, str],
    display_path: str,
    task_key: str,
    errors: list[SchemaIssue],
) -> None:
    for task in tasks:
        index = task.source_index
        task_id = task.get("id")
        for dep_index, dependency in enumerate(task.get("dependsOn", [])):
            dependency_path = f"{display_path} {task_key}[{index}].dependsOn[{dep_index}]"
            if not isinstance(dependency, str):
                continue
            if dependency == task_id:
                errors.append(SchemaIssue(dependency_path, "self dependency is not allowed"))
            elif dependency not in ids:
                errors.append(
                    SchemaIssue(
                        dependency_path,
                        f"unknown task id '{dependency}'",
                    )
                )


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
