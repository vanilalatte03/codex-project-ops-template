import json
from pathlib import Path

import pytest

import run_state


def identity(tmp_path: Path, *, task_id: str = "phase:step7:resumable-telemetry") -> run_state.RunIdentity:
    worktree = (tmp_path / "worktree").resolve()
    return run_state.RunIdentity(
        phase="phase",
        task_id=task_id,
        issue=20,
        branch="codex/phase-step7-resumable-telemetry",
        worktree_path=worktree,
        model="gpt-5.6",
        effort="medium",
    )


def store(tmp_path: Path, **kwargs) -> run_state.RunStateStore:
    return run_state.RunStateStore(tmp_path / "state", **kwargs)


def test_begin_persists_local_identity_and_public_record_omits_thread(tmp_path):
    states = store(tmp_path, clock=lambda: "2026-09-14T00:00:00Z")

    created = states.begin(identity(tmp_path))
    running = states.transition(created.identity.task_id, "running", thread_id="thread-private", process_id=123)

    assert states.read(created.identity.task_id) == running
    assert running.to_payload()["threadId"] == "thread-private"
    assert "threadId" not in running.to_public_record()
    assert "processId" not in running.to_public_record()


def test_same_task_identity_is_reused_but_mismatch_is_rejected(tmp_path):
    states = store(tmp_path)
    original = identity(tmp_path)
    assert states.begin(original) == states.begin(original)

    changed = run_state.RunIdentity(
        phase="phase",
        task_id=original.task_id,
        issue=20,
        branch="codex/different",
        worktree_path=original.worktree_path,
    )
    with pytest.raises(run_state.RunStateConflictError, match="identity"):
        states.begin(changed)


def test_resume_requires_preserved_state_and_reuses_same_task_identity(tmp_path):
    states = store(tmp_path, clock=lambda: "2026-09-14T00:00:00Z")
    created = states.begin(identity(tmp_path))
    states.transition(created.identity.task_id, "running", process_id=999)
    interrupted = states.transition(created.identity.task_id, "interrupted", diagnostic="process stopped")

    resumed = states.resume(interrupted.identity.task_id, process_id=1000)

    assert resumed.status == "running"
    assert resumed.attempt == 1
    assert resumed.process_id == 1000
    with pytest.raises(run_state.RunStateTransitionError, match="중단된"):
        states.resume(resumed.identity.task_id)


def test_invalid_transition_and_duplicate_action_with_changed_fingerprint_fail_closed(tmp_path):
    states = store(tmp_path)
    created = states.begin(identity(tmp_path))

    with pytest.raises(run_state.RunStateTransitionError, match="상태 전이"):
        states.transition(created.identity.task_id, "merged")

    first, changed = states.complete_action(created.identity.task_id, "pr-created", "https://example.test/pr/20")
    same, changed_again = states.complete_action(created.identity.task_id, "pr-created", "https://example.test/pr/20")
    assert changed is True
    assert changed_again is False
    assert first == same
    with pytest.raises(run_state.RunStateTransitionError, match="fingerprint"):
        states.complete_action(created.identity.task_id, "pr-created", "https://example.test/pr/other")


def test_stale_process_detection_uses_injected_process_probe(tmp_path):
    states = store(tmp_path, process_exists=lambda pid: pid == 7)
    created = states.begin(identity(tmp_path))
    states.transition(created.identity.task_id, "running", process_id=8)
    assert states.is_stale(created.identity.task_id) is True

    states.transition(created.identity.task_id, "running", process_id=7)
    assert states.is_stale(created.identity.task_id) is False


def test_diagnostics_and_metric_reason_are_redacted(tmp_path):
    states = store(tmp_path)
    created = states.begin(identity(tmp_path))
    state = states.transition(
        created.identity.task_id,
        "running",
        diagnostic="authorization=Bearer-secret prompt=private-text",
        metrics={"tokens": None, "unavailableReason": "api_key=hidden"},
    )

    joined = " ".join(state.diagnostics) + " " + str(state.metrics["unavailableReason"])
    assert "Bearer-secret" not in joined
    assert "private-text" not in joined
    assert "hidden" not in joined
    assert state.metrics["tokens"] is None


def test_corrupted_state_is_preserved_and_reported(tmp_path):
    states = store(tmp_path)
    item = identity(tmp_path)
    path = states._path_for(item.task_id)
    path.parent.mkdir(parents=True)
    path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(run_state.RunStateCorruptionError, match="읽지 못했습니다"):
        states.read(item.task_id)
    assert path.read_text(encoding="utf-8") == "{bad json"


def test_corrupted_identity_type_is_reported_as_run_state_corruption(tmp_path):
    states = store(tmp_path)
    item = identity(tmp_path)
    path = states._path_for(item.task_id)
    path.parent.mkdir(parents=True)
    payload = run_state.RunState(item, created_at="now", updated_at="now").to_payload()
    payload["issue"] = "20"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(run_state.RunStateCorruptionError, match="issue"):
        states.read(item.task_id)


def test_atomic_replace_failure_keeps_previous_state_and_cleans_temp_file(tmp_path, monkeypatch):
    states = store(tmp_path)
    created = states.begin(identity(tmp_path))
    path = states._path_for(created.identity.task_id)
    before = path.read_text(encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(run_state.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        states.transition(created.identity.task_id, "running")

    assert path.read_text(encoding="utf-8") == before
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_for_repository_uses_linked_worktree_git_directory(tmp_path):
    admin = tmp_path / "admin" / "worktrees" / "task"
    admin.mkdir(parents=True)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")

    states = run_state.RunStateStore.for_repository(checkout)

    assert states.directory == (admin / "harness-runs").resolve()
