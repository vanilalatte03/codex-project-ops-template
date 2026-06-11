import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import autopilot as ap


def cp(cmd=None, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(cmd or [], returncode, stdout, stderr)


@pytest.fixture
def tmp_repo(tmp_path):
    (tmp_path / "issues").mkdir()
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "scope-rules.json").write_text(json.dumps({"forbidden": []}), encoding="utf-8")
    phase_dir = tmp_path / "phases" / "0-mvp"
    phase_dir.mkdir(parents=True)
    (phase_dir / "README.md").write_text("# Phase\n\n## 목표\nMVP를 구현한다.\n", encoding="utf-8")
    (phase_dir / "index.json").write_text(
        json.dumps(
            {
                "project": "Demo",
                "phase": "0-mvp",
                "steps": [
                    {"step": 0, "name": "project-scaffold", "status": "pending"},
                    {"step": 1, "name": "api-layer", "status": "pending"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (phase_dir / "step0.md").write_text("# 단계 0\n\n## 작업\n프로젝트 골격을 만든다.\n", encoding="utf-8")
    (phase_dir / "step1.md").write_text("# 단계 1\n\n## 작업\nAPI 레이어를 만든다.\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def runner(tmp_repo):
    return ap.AutopilotRunner("0-mvp", root=tmp_repo)


def _mark_step_complete(tmp_repo, step_num, summary="완료"):
    index_path = tmp_repo / "phases" / "0-mvp" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for step in index["steps"]:
        if step["step"] == step_num:
            step["status"] = "completed"
            step["summary"] = summary
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


def test_preconditions_stop_on_dirty_worktree(runner):
    def fake_git(*args, check=True):
        if args == ("status", "--short", "--untracked-files=all"):
            return cp(stdout=" M README.md\n")
        return cp()

    runner._git = fake_git

    with pytest.raises(ap.AutopilotError) as exc_info:
        runner._ensure_preconditions()

    assert "작업트리가 clean 상태가 아닙니다" in str(exc_info.value)
    assert "README.md" in str(exc_info.value)


def test_preconditions_stop_on_gh_auth_failure(runner):
    runner._git = lambda *args, check=True: cp()

    def fake_gh(*args, check=True):
        raise ap.AutopilotError("gh auth failed")

    runner._gh = fake_gh

    with pytest.raises(ap.AutopilotError) as exc_info:
        runner._ensure_preconditions()

    assert "gh auth failed" in str(exc_info.value)


def test_step_success_creates_draft_pr_comments_and_merges(runner, tmp_repo):
    gh_calls = []
    executed = []

    runner._ensure_preconditions = lambda: None
    runner._sync_base = lambda: None
    runner._run_final_gate = lambda: None

    def fake_run_step(branch, step):
        executed.append((branch, step["step"]))
        _mark_step_complete(tmp_repo, step["step"], f"{step['name']} 완료")

    runner._run_step = fake_run_step
    runner._run_review_gate = lambda step: ap.ReviewResult(True, [], "ok", commands=("cmd",))

    def fake_gh(*args, check=True, timeout=None):
        gh_calls.append(args)
        if args[:2] == ("pr", "create"):
            pr_count = len([call for call in gh_calls if call[:2] == ("pr", "create")])
            return cp(stdout=f"https://github.com/org/repo/pull/{pr_count}\n")
        return cp()

    runner._gh = fake_gh

    pr_urls = runner.run()

    assert executed == [
        ("codex/0-mvp-step0-project-scaffold", 0),
        ("codex/0-mvp-step1-api-layer", 1),
    ]
    assert "https://github.com/org/repo/pull/1" in pr_urls
    assert "https://github.com/org/repo/pull/2" in pr_urls
    assert gh_calls[0][:8] == (
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        "codex/0-mvp-step0-project-scaffold",
        "--title",
        "feat: 0-mvp 0단계 project-scaffold 구현",
    )
    assert "--draft" in gh_calls[0]
    assert any(call[:2] == ("pr", "comment") and "## 자체 리뷰" in call[4] for call in gh_calls)
    assert ("pr", "ready", "https://github.com/org/repo/pull/1") in gh_calls
    assert ("pr", "checks", "https://github.com/org/repo/pull/1", "--watch") in gh_calls
    assert ("pr", "merge", "https://github.com/org/repo/pull/2", "--squash", "--delete-branch") in gh_calls


def test_pr_body_uses_step_specific_change_reason(runner, tmp_repo):
    _mark_step_complete(tmp_repo, 1, "API 계약 타입을 추가함")
    runner._changed_files = lambda: ["app/shared/src/contracts/agent.ts"]

    body = runner._pr_body(
        "codex/0-mvp-step1-api-layer",
        {"step": 1, "name": "api-layer"},
    )

    assert "Harness 작업을 작은 step 단위로 리뷰하고 안전하게 병합하기 위해 분리했습니다." not in body
    assert "이 PR은 \"API 레이어를 만든다\" 요구사항을 완료하기 위한 변경입니다." in body
    assert "실제 변경 결과: API 계약 타입을 추가함." in body


def test_review_fail_records_issue_and_leaves_pr_open(runner, tmp_repo):
    gh_calls = []
    runner.max_review_fixes = 0
    runner._ensure_preconditions = lambda: None
    runner._sync_base = lambda: None
    runner._run_final_gate = lambda: None
    runner._run_step = lambda branch, step: _mark_step_complete(tmp_repo, step["step"], "완료")
    runner._run_review_gate = lambda step: ap.ReviewResult(
        False,
        ["src/app.py:10 - 테스트 실패"],
        "fail",
        checks_passed=False,
    )

    def fake_gh(*args, check=True, timeout=None):
        gh_calls.append(args)
        if args[:2] == ("pr", "create"):
            return cp(stdout="https://github.com/org/repo/pull/8\n")
        if args[:2] == ("issue", "create"):
            return cp(stdout="https://github.com/org/repo/issues/1\n")
        return cp()

    runner._gh = fake_gh

    with pytest.raises(ap.AutopilotError):
        runner.run()

    issue_path = tmp_repo / "issues" / "0-mvp" / "issue-1.md"
    assert issue_path.exists()
    issue_text = issue_path.read_text(encoding="utf-8")
    assert "Step: 0 `project-scaffold`" in issue_text
    assert "src/app.py:10 - 테스트 실패" in issue_text
    assert any(call[:2] == ("issue", "create") for call in gh_calls)
    assert any(call[:2] == ("pr", "comment") and "## 자체 리뷰" in call[4] for call in gh_calls)
    assert not any(call[:2] == ("pr", "close") for call in gh_calls)
    assert not any(call[:2] == ("pr", "merge") for call in gh_calls)


def test_review_fail_fixes_same_pr_then_merges_and_continues(runner, tmp_repo):
    gh_calls = []
    fix_calls = []
    dirty_commits = []
    pushed = []
    runner._ensure_preconditions = lambda: None
    runner._sync_base = lambda: None
    runner._run_final_gate = lambda: None
    runner._run_step = lambda branch, step: _mark_step_complete(tmp_repo, step["step"], "완료")
    reviews = [
        ap.ReviewResult(False, ["src/app.py:1 - 실패"], "fail"),
        ap.ReviewResult(True, [], "ok"),
        ap.ReviewResult(True, [], "ok"),
    ]
    runner._run_review_gate = lambda step: reviews.pop(0)
    runner._invoke_codex_fix = lambda issue, branch, step, review, attempt: fix_calls.append(
        (issue.number, branch, step["step"], attempt)
    )
    runner._commit_dirty_fix = lambda step: dirty_commits.append(step["step"])
    runner._push_branch = lambda branch: pushed.append(branch)

    def fake_gh(*args, check=True, timeout=None):
        gh_calls.append(args)
        if args[:2] == ("pr", "create"):
            pr_count = len([call for call in gh_calls if call[:2] == ("pr", "create")])
            return cp(stdout=f"https://github.com/org/repo/pull/{pr_count}\n")
        if args[:2] == ("issue", "create"):
            return cp(stdout="https://github.com/org/repo/issues/1\n")
        return cp()

    runner._gh = fake_gh

    pr_urls = runner.run()

    assert fix_calls == [(1, "codex/0-mvp-step0-project-scaffold", 0, 1)]
    assert dirty_commits == [0]
    assert pushed == ["codex/0-mvp-step0-project-scaffold"]
    issue_text = (tmp_repo / "issues" / "0-mvp" / "issue-1.md").read_text(encoding="utf-8")
    assert "## 자동 수정 완료" in issue_text
    assert any(call[:2] == ("issue", "close") and call[2] == "https://github.com/org/repo/issues/1" for call in gh_calls)
    assert ("pr", "merge", "https://github.com/org/repo/pull/1", "--squash", "--delete-branch") in gh_calls
    assert ("pr", "merge", "https://github.com/org/repo/pull/2", "--squash", "--delete-branch") in gh_calls
    assert "https://github.com/org/repo/pull/1" in pr_urls
    assert "https://github.com/org/repo/pull/2" in pr_urls


def test_review_stops_after_max_fix_attempts_without_closing_pr(runner, tmp_repo):
    gh_calls = []
    fix_calls = []
    runner.max_review_fixes = 1
    runner._ensure_preconditions = lambda: None
    runner._sync_base = lambda: None
    runner._run_step = lambda branch, step: _mark_step_complete(tmp_repo, step["step"], "완료")
    reviews = [
        ap.ReviewResult(False, ["첫 실패"], "fail"),
        ap.ReviewResult(False, ["재시도 실패"], "fail again"),
    ]
    runner._run_review_gate = lambda step: reviews.pop(0)
    runner._invoke_codex_fix = lambda issue, branch, step, review, attempt: fix_calls.append(attempt)
    runner._commit_dirty_fix = lambda step: None
    runner._push_branch = lambda branch: None

    def fake_gh(*args, check=True, timeout=None):
        gh_calls.append(args)
        if args[:2] == ("pr", "create"):
            return cp(stdout="https://github.com/org/repo/pull/8\n")
        if args[:2] == ("issue", "create"):
            return cp(stdout="https://github.com/org/repo/issues/1\n")
        return cp()

    runner._gh = fake_gh

    with pytest.raises(ap.AutopilotError) as exc_info:
        runner.run()

    issue_path = tmp_repo / "issues" / "0-mvp" / "issue-1.md"
    assert "재시도 1 리뷰 실패" in issue_path.read_text(encoding="utf-8")
    assert fix_calls == [1]
    assert "최대 횟수" in str(exc_info.value)
    assert any(call[:2] == ("issue", "comment") for call in gh_calls)
    assert not any(call[:2] == ("pr", "close") for call in gh_calls)
    assert not any(call[:2] == ("pr", "merge") for call in gh_calls)


def test_parse_codex_review_json(runner):
    result = runner._parse_review_result('{"pass": true, "summary": "ok", "findings": []}')

    assert result.passed is True
    assert result.summary == "ok"
    assert result.findings == []


def test_parse_codex_review_json_from_event_stream(runner):
    stdout = "\n".join([
        '{"type":"started"}',
        '{"type":"message","message":{"content":[{"type":"output_text","text":"{\\"pass\\": true, \\"summary\\": \\"ok\\", \\"findings\\": []}"}]}}',
    ])

    result = runner._parse_review_result(stdout)

    assert result.passed is True
    assert result.summary == "ok"
    assert result.findings == []


def test_parse_codex_review_json_from_fenced_event(runner):
    stdout = "\n".join([
        '{"type":"started"}',
        '{"type":"event","item":{"type":"message","content":[{"type":"output_text","text":"```json\\n{\\"pass\\": true, \\"summary\\": \\"ok\\", \\"findings\\": []}\\n```"}]}}',
        '{"type":"result","status":"success"}',
    ])

    result = runner._parse_review_result(stdout)

    assert result.passed is True
    assert result.summary == "ok"
    assert result.findings == []


def test_codex_review_prompt_excludes_issue_records_and_uses_step_contract(runner):
    prompt = runner._codex_review_prompt({"step": 1, "name": "api-layer"})

    assert "issues/**" in prompt
    assert "audit logs" in prompt
    assert "not implementation changes" in prompt
    assert "phases/0-mvp/README.md" in prompt
    assert "phases/0-mvp/step1.md" in prompt
    assert "Current Harness step is Step 1 `api-layer`" in prompt
    assert "Missing functionality assigned to future steps is not a blocker" in prompt
    assert "Implementing future-step scope inside the current step is a blocker" in prompt
    assert str(Path(sys.executable)) in prompt
    assert "instead of assuming `python` or `py` is available on PATH" in prompt


def test_codex_review_uses_step_scoped_exec_prompt(runner):
    seen = {}
    runner._git = lambda *args, check=True: cp(stdout="")

    def fake_run(cmd, check=True, timeout=None, input_text=None):
        seen["cmd"] = cmd
        seen["input_text"] = input_text
        schema_path = Path(cmd[cmd.index("--output-schema") + 1])
        seen["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        return cp(stdout='{"pass": true, "summary": "ok", "findings": []}')

    runner._run = fake_run

    review = runner._run_codex_review({"step": 0, "name": "project-scaffold"})

    assert review.passed is True
    assert seen["cmd"][:2] == [ap.CODEX_BIN, "exec"]
    assert "review" not in seen["cmd"][2:]
    assert "--base" not in seen["cmd"]
    assert ap.CODEX_ENV_CONFIG in seen["cmd"]
    assert "--output-schema" in seen["cmd"]
    assert seen["schema"]["required"] == ["pass", "summary", "findings"]
    assert "--output-last-message" in seen["cmd"]
    assert "--json" in seen["cmd"]
    assert seen["cmd"][-1] == "-"
    assert seen["input_text"].startswith("Read-only review only.")
    assert "Current Harness step is Step 0 `project-scaffold`" in seen["input_text"]


def test_codex_review_parses_output_last_message(runner):
    runner._git = lambda *args, check=True: cp(stdout="")

    def fake_run(cmd, check=True, timeout=None, input_text=None):
        last_message_path = Path(cmd[cmd.index("--output-last-message") + 1])
        last_message_path.write_text('{"pass": true, "summary": "ok", "findings": []}', encoding="utf-8")
        return cp(stdout='{"type":"started"}')

    runner._run = fake_run

    review = runner._run_codex_review({"step": 0, "name": "project-scaffold"})

    assert review.passed is True
    assert review.summary == "ok"


def test_codex_review_parses_native_priority_findings(runner):
    runner._git = lambda *args, check=True: cp(stdout="")

    def fake_run(cmd, check=True, timeout=None, input_text=None):
        last_message_path = Path(cmd[cmd.index("--output-last-message") + 1])
        last_message_path.write_text(
            "Review comment:\n\n"
            "- [P2] Pass step-scoped review instructions to Codex - scripts/autopilot.py:410\n"
            "  The review lacks the step contract.",
            encoding="utf-8",
        )
        return cp(stdout='{"type":"turn.completed"}')

    runner._run = fake_run

    review = runner._run_codex_review({"step": 0, "name": "project-scaffold"})

    assert review.passed is False
    assert review.codex_passed is False
    assert review.findings == [
        "- [P2] Pass step-scoped review instructions to Codex - scripts/autopilot.py:410"
    ]


def test_run_step_uses_current_python_executable(runner):
    seen = {}
    step = {"step": 0, "name": "project-scaffold"}

    def fake_run(cmd, check=True, timeout=None):
        seen["cmd"] = cmd
        seen["timeout"] = timeout
        return cp()

    runner._run = fake_run
    runner._run_step("codex/test", step)

    assert seen["cmd"][:2] == [sys.executable, "scripts/execute.py"]
    assert "--codex-effort" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--codex-effort") + 1] == "medium"
    assert seen["timeout"] == 1800


def test_codex_review_uses_high_reasoning_effort_by_default(runner):
    seen = {}
    runner._git = lambda *args, check=True: cp(stdout="")

    def fake_run(cmd, check=True, timeout=None, input_text=None):
        seen["cmd"] = cmd
        return cp(stdout='{"pass": true, "summary": "ok", "findings": []}')

    runner._run = fake_run

    review = runner._run_codex_review({"step": 0, "name": "project-scaffold"})

    assert review.passed is True
    assert "-c" in seen["cmd"]
    assert 'model_reasoning_effort="high"' in seen["cmd"]
    assert ap.CODEX_ENV_CONFIG in seen["cmd"]


def test_codex_fix_uses_medium_reasoning_effort(runner, tmp_repo):
    seen = {}
    issue = ap.IssueRecord(1, "title", "body", tmp_repo / "issues" / "issue-1.md", "")

    def fake_run(cmd, check=True, timeout=None, input_text=None):
        seen["cmd"] = cmd
        seen["input_text"] = input_text
        seen["timeout"] = timeout
        return cp()

    runner._run = fake_run
    runner._invoke_codex_fix(
        issue,
        "codex/test",
        {"step": 0, "name": "project-scaffold"},
        ap.ReviewResult(False, ["finding"], "failed"),
        1,
    )

    assert seen["cmd"][:2] == [ap.CODEX_BIN, "exec"]
    assert 'model_reasoning_effort="medium"' in seen["cmd"]
    assert ap.CODEX_ENV_CONFIG in seen["cmd"]
    assert seen["input_text"].startswith("당신은 Harness step PR 자동 리뷰 수정 담당자입니다.")
    assert seen["timeout"] == 1800


def test_codex_review_fails_if_worktree_changes(runner):
    statuses = iter([cp(stdout=""), cp(stdout=" M src/app.py\n")])
    runner._git = lambda *args, check=True: next(statuses)
    runner._run = lambda cmd, check=True, timeout=None, input_text=None: cp(
        stdout='{"pass": true, "summary": "ok", "findings": []}'
    )

    review = runner._run_codex_review({"step": 0, "name": "project-scaffold"})

    assert review.passed is False
    assert "changed the worktree" in review.findings[0]


def test_review_gate_passes_current_step_to_codex_review(runner):
    step = {"step": 1, "name": "api-layer"}
    seen = {}

    def fake_shell(command, check=True, timeout=None):
        if command == ap.FALLBACK_REVIEW_CHECK_COMMAND:
            return cp()
        if command == "git diff --check origin/main...HEAD":
            return cp()
        raise AssertionError(command)

    def fake_codex(current_step):
        seen["codex"] = current_step
        return ap.ReviewResult(True, [], "ok")

    runner._run_shell = fake_shell
    runner._scan_scope_diff = lambda current_step: []
    runner._run_codex_review = fake_codex

    review = runner._run_review_gate(step)

    assert review.passed is True
    assert seen == {"codex": step}


def test_review_markdown_is_table_and_dedupes_findings():
    review = ap.ReviewResult(
        False,
        ["a.py:1 - 실패", "a.py:1 - 실패"],
        "블로커가 있어 merge하지 않습니다.",
        diff_passed=False,
        commands=("python scripts/checks.py --stage manual",),
    )

    markdown = review.to_markdown()

    assert "| diff 검사 | 실패 |" in markdown
    assert markdown.count("a.py:1 - 실패") == 1
    assert "## 리뷰 결론" in markdown


def test_dry_run_lists_pending_steps_without_side_effects(tmp_repo):
    runner = ap.AutopilotRunner("0-mvp", root=tmp_repo, dry_run=True, max_steps=1)
    runner._git = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("git should not run"))
    runner._gh = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("gh should not run"))

    summary = runner.run()

    assert "[dry-run]" in summary
    assert "Step 0 `project-scaffold`" in summary
    assert "Step 1" not in summary
    assert not (tmp_repo / ".codex" / "autopilot.lock").exists()


def test_lock_blocks_concurrent_runs(tmp_repo):
    lock_path = tmp_repo / ".codex" / "autopilot.lock"
    lock_path.write_text(str(os.getpid()), encoding="utf-8")
    runner = ap.AutopilotRunner("0-mvp", root=tmp_repo)

    with pytest.raises(ap.AutopilotError, match="이미 실행 중"):
        runner.run()

    assert lock_path.exists()


def test_stale_lock_is_replaced_and_released(tmp_repo):
    lock_path = tmp_repo / ".codex" / "autopilot.lock"
    lock_path.write_text("999999999", encoding="utf-8")
    runner = ap.AutopilotRunner("0-mvp", root=tmp_repo)
    runner._run_loop = lambda: "done"

    assert runner.run() == "done"
    assert not lock_path.exists()


def test_max_steps_stops_loop_after_limit(runner, tmp_repo):
    runner.max_steps = 1
    runner._ensure_preconditions = lambda: None
    runner._sync_base = lambda: None
    runner._run_final_gate = lambda: (_ for _ in ()).throw(AssertionError("final gate must not run"))
    runner._run_step = lambda branch, step: _mark_step_complete(tmp_repo, step["step"], "완료")
    runner._run_review_gate = lambda step: ap.ReviewResult(True, [], "ok")

    def fake_gh(*args, check=True, timeout=None):
        if args[:2] == ("pr", "create"):
            return cp(stdout="https://github.com/org/repo/pull/1\n")
        return cp()

    runner._gh = fake_gh

    result = runner.run()

    assert "https://github.com/org/repo/pull/1" in result
    assert "--max-steps 1 도달" in result


def test_review_gate_blocks_dangerous_acceptance_command(runner, tmp_repo):
    step_path = tmp_repo / "phases" / "0-mvp" / "step1.md"
    step_path.write_text(
        "\n".join(
            [
                "# 단계 1",
                "",
                "## 인수 기준",
                "",
                "```bash",
                "rm -r -f build",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    shell_calls = []
    runner._run_shell = lambda command, check=True, timeout=None: shell_calls.append(command) or cp()
    runner._scan_scope_diff = lambda current_step: []
    runner._run_codex_review = lambda current_step: ap.ReviewResult(True, [], "ok")

    review = runner._run_review_gate({"step": 1, "name": "api-layer"})

    assert review.passed is False
    assert review.checks_passed is False
    assert "rm -r -f build" not in shell_calls
    assert any("위험 명령 정책" in finding for finding in review.findings)


def test_scope_rules_config_extends_forbidden_and_allows_messages(tmp_repo):
    (tmp_repo / ".codex" / "scope-rules.json").write_text(
        json.dumps(
            {
                "forbidden": [
                    {
                        "message": "GraphQL 범위가 추가되었습니다.",
                        "anyLowered": ["graphql"],
                    },
                    {
                        "message": "Cache 범위가 추가되었습니다.",
                        "anyLowered": ["cache"],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    phase_dir = tmp_repo / "phases" / "0-mvp"
    (phase_dir / "scope-rules.json").write_text(
        json.dumps(
            {
                "allowedScopeMessages": [
                    {
                        "message": "Cache 범위가 추가되었습니다.",
                        "steps": [1],
                        "requiresAnyLowered": ["existing"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    runner = ap.AutopilotRunner("0-mvp", root=tmp_repo)

    def fake_git(*args, check=True):
        assert args[:2] == ("diff", "--unified=0")
        return cp(
            stdout="\n".join(
                [
                    "diff --git a/docs/PRD.md b/docs/PRD.md",
                    "+++ b/docs/PRD.md",
                    "@@ -1,0 +1,2 @@",
                    "+GraphQL API를 구현한다.",
                    "+existing cache contract를 유지한다.",
                ]
            )
        )

    runner._git = fake_git

    findings = runner._scan_scope_diff({"step": 1, "name": "api-layer"})

    assert any("GraphQL 범위" in finding for finding in findings)
    assert not any("Cache 범위" in finding for finding in findings)


def test_merge_waits_for_pr_checks_and_blocks_on_failure(runner):
    gh_calls = []

    def fake_gh(*args, check=True, timeout=None):
        gh_calls.append(args)
        if args[:2] == ("pr", "checks"):
            return cp(returncode=1, stdout="build  fail  1m  https://ci")
        return cp()

    runner._gh = fake_gh

    with pytest.raises(ap.AutopilotError, match="원격 체크"):
        runner._mark_ready_and_merge("https://github.com/org/repo/pull/3")

    assert not any(call[:2] == ("pr", "merge") for call in gh_calls)


def test_no_checks_grace_retries_until_checks_appear(runner, monkeypatch):
    gh_calls = []
    sleeps = []
    checks_results = [
        cp(returncode=1, stderr="no checks reported on the 'codex/x' branch"),
        cp(returncode=0, stdout="build  pass  1m  https://ci"),
    ]
    monkeypatch.setattr(ap.time, "sleep", lambda seconds: sleeps.append(seconds))

    def fake_gh(*args, check=True, timeout=None):
        gh_calls.append(args)
        if args[:2] == ("pr", "checks"):
            return checks_results.pop(0)
        return cp()

    runner._gh = fake_gh

    runner._mark_ready_and_merge("https://github.com/org/repo/pull/3")

    assert len([call for call in gh_calls if call[:2] == ("pr", "checks")]) == 2
    assert sleeps == [ap.NO_CHECKS_POLL_SECONDS]
    assert any(call[:2] == ("pr", "merge") for call in gh_calls)


def test_allow_no_checks_skips_grace_wait(tmp_repo, monkeypatch):
    runner = ap.AutopilotRunner("0-mvp", root=tmp_repo, allow_no_checks=True)

    def fail_sleep(seconds):
        raise AssertionError("--allow-no-checks must not wait")

    monkeypatch.setattr(ap.time, "sleep", fail_sleep)

    def fake_gh(*args, check=True, timeout=None):
        if args[:2] == ("pr", "checks"):
            return cp(returncode=1, stderr="no checks reported on the 'codex/x' branch")
        return cp()

    runner._gh = fake_gh

    runner._mark_ready_and_merge("https://github.com/org/repo/pull/3")


def test_detect_default_base_uses_origin_head(tmp_path, monkeypatch):
    def fake_run(cmd, cwd, capture_output, text, timeout):
        assert cmd == ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"]
        return cp(stdout="origin/trunk\n")

    monkeypatch.setattr(ap.subprocess, "run", fake_run)

    assert ap.detect_default_base(tmp_path) == "trunk"


def test_detect_default_base_falls_back_to_main(tmp_path, monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=30)

    monkeypatch.setattr(ap.subprocess, "run", fake_run)

    assert ap.detect_default_base(tmp_path) == "main"
