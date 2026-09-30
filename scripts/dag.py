"""Deterministic ready-set selection for v2 task indexes."""

from __future__ import annotations

from typing import Any


MAX_CONCURRENCY = 4
DEFAULT_CONCURRENCY = 2


def ready_tasks(index: Any) -> list[dict]:
    """Return pending tasks whose declared dependencies have merged.

    The persisted ``completed`` status is the only dependency success signal.
    Error, blocked, and interrupted work never releases a dependent task.
    """
    if index.schema_version != 2:
        return [task for task in index.tasks if task["status"] == "pending"][:1]
    by_id = {task["id"]: task for task in index.tasks}
    return [
        task for task in index.tasks
        if task["status"] == "pending"
        and all(by_id[dep]["status"] == "completed" for dep in task.get("dependsOn", []))
    ]


def select_batch(index: Any, concurrency: int = DEFAULT_CONCURRENCY) -> list[dict]:
    if isinstance(concurrency, bool) or not isinstance(concurrency, int) or not 1 <= concurrency <= MAX_CONCURRENCY:
        raise ValueError(f"concurrency must be between 1 and {MAX_CONCURRENCY}")
    if index.schema_version != 2:
        return ready_tasks(index)
    selected: list[dict] = []
    locked: set[str] = set()
    for task in ready_tasks(index):
        resources = set(task.get("resources", []))
        if resources & locked:
            continue
        selected.append(task)
        locked.update(resources)
        if len(selected) == concurrency:
            break
    return selected
