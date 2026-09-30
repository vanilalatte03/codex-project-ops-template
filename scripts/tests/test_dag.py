import pytest

import dag
import task_schema


def phase(tasks):
    return task_schema.normalize_phase_index(
        {"project": "demo", "phase": "demo", "schemaVersion": 2, "tasks": tasks},
        path="phases/demo/index.json",
    )


def task(task_id, *, depends=None, status="pending", resources=None):
    result = {"id": task_id, "objective": task_id, "status": status}
    if depends is not None:
        result["dependsOn"] = depends
    if resources is not None:
        result["resources"] = resources
    return result


@pytest.mark.parametrize("tasks, expected", [
    ([task("a", depends=["missing"])], "unknown task id"),
    ([task("a", depends=["a"])], "self dependency"),
    ([task("a", depends=["b"]), task("b", depends=["a"])], "cycle"),
    ([task("a", resources=["db", "db"])], "duplicate resource"),
])
def test_invalid_graph_fails_before_dispatch(tasks, expected):
    with pytest.raises(task_schema.TaskSchemaError, match=expected):
        phase(tasks)


def test_ready_set_waits_for_dependencies_and_preserves_order():
    index = phase([task("a"), task("b"), task("c", depends=["a", "b"])])
    assert [t["id"] for t in dag.ready_tasks(index)] == ["a", "b"]
    index.tasks[0]["status"] = "completed"
    assert [t["id"] for t in dag.ready_tasks(index)] == ["b"]
    index.tasks[1]["status"] = "completed"
    assert [t["id"] for t in dag.ready_tasks(index)] == ["c"]


def test_resource_lock_and_limit():
    index = phase([
        task("a", resources=["db"]), task("b", resources=["db"]),
        task("c", resources=["cache"]), task("d"),
    ])
    assert [t["id"] for t in dag.select_batch(index, 2)] == ["a", "c"]
    assert [t["id"] for t in dag.select_batch(index, 3)] == ["a", "c", "d"]
    with pytest.raises(ValueError, match="concurrency"):
        dag.select_batch(index, 0)
    with pytest.raises(ValueError, match="concurrency"):
        dag.select_batch(index, dag.MAX_CONCURRENCY + 1)


def test_reconcile_blocks_failed_ancestor_and_retries_only_pending():
    index = phase([task("a", status="error"), task("b", depends=["a"]), task("c")])
    assert [t["id"] for t in dag.ready_tasks(index)] == ["c"]
    index.tasks[0]["status"] = "pending"
    assert [t["id"] for t in dag.ready_tasks(index)] == ["a", "c"]
