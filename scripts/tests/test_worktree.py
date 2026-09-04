import json
import os
import subprocess
from pathlib import Path
from shutil import rmtree

import pytest

import autopilot
import worktree


def git(cwd: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Path, str]:
    remote = tmp_path / "remote.git"
    primary = tmp_path / "primary"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(primary))
    git(primary, "config", "user.name", "Harness Test")
    git(primary, "config", "user.email", "harness@example.invalid")
    git(primary, "switch", "-c", "develop")
    (primary / "README.md").write_text("base\n", encoding="utf-8")
    git(primary, "add", "README.md")
    git(primary, "commit", "-m", "base")
    git(primary, "push", "-u", "origin", "develop")
    sha = git(primary, "rev-parse", "HEAD")
    return primary, sha


@pytest.fixture
def lifecycle(git_repo: tuple[Path, str], tmp_path: Path) -> tuple[worktree.WorktreeLifecycle, Path, str]:
    primary, sha = git_repo
    manager = worktree.WorktreeLifecycle(
        primary,
        worktree_root=tmp_path / "managed-worktrees",
    )
    return manager, primary, sha


def create_task(manager: worktree.WorktreeLifecycle, *, task_id: str = "phase:task-0", path: Path | None = None):
    return manager.create_or_resume(
        task_id=task_id,
        phase="phase",
        branch=f"codex/{task_id.replace(':', '-')}",
        base_ref="refs/remotes/origin/develop",
        path=path,
    )


def test_create_records_marker_and_preserves_primary_checkout(lifecycle):
    manager, primary, sha = lifecycle

    handle = create_task(manager)

    assert handle.path.is_absolute()
    assert handle.path != primary.resolve()
    assert handle.path.is_relative_to(manager.worktree_root)
    assert handle.marker_path.exists()
    payload = json.loads(handle.marker_path.read_text(encoding="utf-8"))
    assert payload == {
        "schemaVersion": 1,
        "owner": "codex-harness",
        "taskId": "phase:task-0",
        "phase": "phase",
        "branch": "codex/phase-task-0",
        "worktreePath": str(handle.path),
        "baseRef": "refs/remotes/origin/develop",
        "baseSha": sha,
        "status": "created",
        "createdAt": payload["createdAt"],
        "updatedAt": payload["updatedAt"],
    }
    assert git(primary, "branch", "--show-current") == "develop"
    assert git(primary, "status", "--porcelain") == ""
    assert git(handle.path, "branch", "--show-current") == "codex/phase-task-0"
    assert git(handle.path, "rev-parse", "HEAD") == sha


def test_list_and_resume_reuse_same_owned_worktree_and_preserve_diagnostics(lifecycle):
    manager, _, _ = lifecycle
    handle = create_task(manager)

    interrupted = manager.transition(
        handle,
        "interrupted",
        error="process interrupted",
        diagnostics=["pid=1234", "resume from same marker"],
    )
    records = manager.list()
    record = next(item for item in records if item.state.task_id == handle.state.task_id)
    assert record.stale is False
    assert record.attached is True
    assert record.state.status == "interrupted"
    assert record.marker_path == handle.marker_path

    resumed = manager.resume(handle.state.task_id)

    assert resumed.path == handle.path
    assert resumed.marker_path == handle.marker_path
    assert resumed.state.status == "running"
    assert resumed.state.last_error == interrupted.state.last_error
    assert "pid=1234" in resumed.state.diagnostics
    assert resumed.state.resume_count == 1


def test_existing_branch_without_marker_is_never_reused(lifecycle):
    manager, primary, _ = lifecycle
    git(primary, "branch", "codex/phase-existing")

    with pytest.raises(worktree.WorktreeConflictError, match="branch"):
        manager.create_or_resume(
            task_id="phase:existing",
            phase="phase",
            branch="codex/phase-existing",
            base_ref="refs/remotes/origin/develop",
        )


def test_existing_path_without_marker_is_never_deleted(lifecycle, tmp_path: Path):
    manager, _, _ = lifecycle
    path = tmp_path / "managed-worktrees" / "manual"
    path.mkdir(parents=True)
    sentinel = path / "user-file.txt"
    sentinel.write_text("preserve me", encoding="utf-8")

    with pytest.raises(worktree.WorktreeConflictError, match="path"):
        create_task(manager, task_id="phase:manual", path=path)

    assert sentinel.read_text(encoding="utf-8") == "preserve me"


def test_stale_administrative_entry_is_reported_and_preserved(lifecycle):
    manager, _, _ = lifecycle
    handle = create_task(manager, task_id="phase:stale")
    rmtree(handle.path)

    records = manager.list()
    record = next(item for item in records if item.state.task_id == "phase:stale")
    assert record.stale is True
    assert record.attached is False
    assert record.marker_path.exists()

    with pytest.raises(worktree.StaleWorktreeError, match="stale"):
        manager.resume("phase:stale")

    assert handle.marker_path.exists()


def test_foreign_marker_cannot_be_resumed_or_cleaned(lifecycle):
    manager, _, sha = lifecycle
    handle = create_task(manager, task_id="phase:foreign")
    payload = json.loads(handle.marker_path.read_text(encoding="utf-8"))
    payload["owner"] = "user"
    handle.marker_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(worktree.WorktreeOwnershipError, match="owner"):
        manager.resume("phase:foreign")

    with pytest.raises(worktree.WorktreeOwnershipError, match="owner"):
        manager.safe_cleanup(handle, expected_head_sha=sha)

    assert handle.path.exists()


def test_safe_cleanup_requires_merged_clean_owned_head_and_removes_local_branch(lifecycle):
    manager, primary, sha = lifecycle
    handle = create_task(manager, task_id="phase:cleanup")
    merged = manager.transition(handle, "merged", head_sha=sha)

    result = manager.safe_cleanup(merged, expected_head_sha=sha)

    assert result.worktree_removed is True
    assert result.branch_removed is True
    assert not handle.path.exists()
    assert not handle.marker_path.exists()
    assert git(primary, "show-ref", "--verify", "refs/heads/codex/phase-cleanup", check=False) == ""
    assert all(item.state.task_id != "phase:cleanup" for item in manager.list())


def test_dirty_worktree_is_preserved_even_after_merge_marker(lifecycle):
    manager, _, sha = lifecycle
    handle = create_task(manager, task_id="phase:dirty")
    (handle.path / "dirty.txt").write_text("do not remove", encoding="utf-8")
    merged = manager.transition(handle, "merged", head_sha=sha)

    with pytest.raises(worktree.WorktreeCleanupError, match="dirty"):
        manager.safe_cleanup(merged, expected_head_sha=sha)

    assert handle.path.exists()
    assert handle.marker_path.exists()
    assert (handle.path / "dirty.txt").read_text(encoding="utf-8") == "do not remove"


def test_ignored_file_also_blocks_cleanup(lifecycle):
    manager, _, sha = lifecycle
    handle = create_task(manager, task_id="phase:ignored")
    (handle.path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (handle.path / "ignored.txt").write_text("preserve", encoding="utf-8")
    merged = manager.transition(handle, "merged", head_sha=sha)

    with pytest.raises(worktree.WorktreeCleanupError, match="ignored"):
        manager.safe_cleanup(merged, expected_head_sha=sha)

    assert handle.path.exists()


def test_long_windows_style_managed_path_is_normalized_and_bounded(lifecycle, tmp_path: Path):
    manager, _, _ = lifecycle
    long_root = tmp_path / "managed"
    manager = worktree.WorktreeLifecycle(manager.root, worktree_root=long_root)
    task_id = "phase:" + ("task-" * 80)

    handle = manager.create_or_resume(
        task_id=task_id,
        phase="phase",
        branch="codex/phase-long-path",
        base_ref="refs/remotes/origin/develop",
    )

    assert handle.path.is_absolute()
    assert handle.path.parent == long_root.resolve()
    assert len(handle.path.name) <= worktree.MAX_TASK_DIRECTORY_NAME_LENGTH


@pytest.mark.skipif(os.name != "nt", reason="Windows Git path limit is platform-specific")
def test_overlong_windows_path_is_rejected_before_git_and_preserves_root(lifecycle, tmp_path: Path):
    manager, _, _ = lifecycle
    long_root = tmp_path / ("nested-" * 35)
    manager = worktree.WorktreeLifecycle(manager.root, worktree_root=long_root)

    with pytest.raises(worktree.WorktreeConflictError, match="안전한 worktree path 길이"):
        create_task(manager, task_id="phase:long-path")

    assert not long_root.exists()


@pytest.mark.parametrize("schema_version", [1, 2])
def test_serial_v1_v2_task_worktrees_are_isolated(lifecycle, schema_version):
    manager, primary, sha = lifecycle
    runner = autopilot.AutopilotRunner(
        "phase",
        root=primary,
        worktree_root=manager.worktree_root,
    )
    runner._base_ref = "refs/remotes/origin/develop"
    runner._base_sha = sha

    first_step = {"step": 0, "name": "first"}
    second_step = {"step": 1, "name": "second"}
    if schema_version == 2:
        first_step["id"] = "task-first"
        second_step["id"] = "task-second"

    first = runner._task_worktree(first_step)
    second = runner._task_worktree(second_step)
    first_only = first.path / "task-only.txt"
    second_only = second.path / "task-two-only.txt"
    first_only.write_text("first task", encoding="utf-8")
    second_only.write_text("second task", encoding="utf-8")

    assert not (first.path / "task-two-only.txt").exists()
    assert not (second.path / "task-only.txt").exists()
    assert git(primary, "branch", "--show-current") == "develop"

    first_only.unlink()
    second_only.unlink()
    for handle in (first, second):
        merged = runner._lifecycle.transition(handle, "merged", head_sha=sha)
        runner._lifecycle.safe_cleanup(merged, expected_head_sha=sha)


def test_autopilot_failure_preserves_task_worktree_for_resume(lifecycle):
    manager, primary, sha = lifecycle
    runner = autopilot.AutopilotRunner(
        "phase",
        base="develop",
        root=primary,
        worktree_root=manager.worktree_root,
    )
    runner._base_ref = "refs/remotes/origin/develop"
    runner._base_sha = sha
    step = {"step": 0, "name": "failure"}
    handle = runner._task_worktree(step)

    runner._ensure_preconditions = lambda: None
    runner._next_pending_step = lambda: step
    runner._task_worktree = lambda current_step: handle

    def fail_step(branch, current_step):
        raise autopilot.AutopilotError("implementation failed")

    runner._run_step = fail_step

    with pytest.raises(autopilot.AutopilotError, match="implementation failed"):
        runner.run()

    record = next(item for item in manager.list() if item.state.task_id == handle.state.task_id)
    assert record.state.status == "error"
    assert record.state.last_error == "implementation failed"
    assert record.path.exists()
    assert record.marker_path.exists()
