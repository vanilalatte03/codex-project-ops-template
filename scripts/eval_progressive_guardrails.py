#!/usr/bin/env python3
"""Compare the legacy and progressive guardrail prompts without storing prompt text."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from codex_common import read_acceptance_commands, resolve_codex_bin
from execute import ROOT, StepExecutor


DEFAULT_PHASE = "harness-v2-modernization"
DEFAULT_V1_COMMIT = "eb7192d"
DEFAULT_STEP = 2
REPETITIONS = 3


def _git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _load_phase_step(phase: str, step_number: int | None) -> tuple[dict, Path]:
    phase_dir = ROOT / "phases" / phase
    index = json.loads((phase_dir / "index.json").read_text(encoding="utf-8"))
    if step_number is None:
        step = next((item for item in index["steps"] if item.get("status") == "pending"), None)
    else:
        step = next((item for item in index["steps"] if item.get("step") == step_number), None)
    if step is None:
        raise RuntimeError(f"phase {phase} has no step {step_number}")
    return step, phase_dir / f"step{step['step']}.md"


def _fixture_sha256(phase: str) -> str:
    phase_dir = ROOT / "phases" / phase
    paths = [
        ROOT / "AGENTS.md",
        phase_dir / "README.md",
        phase_dir / "index.json",
        *sorted(phase_dir.glob("step*.md")),
        ROOT / ".codex" / "project-profile.json",
        ROOT / "docs" / "COMMANDS.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "docs" / "adr").glob("*.md")),
    ]
    digest = hashlib.sha256()
    seen: set[Path] = set()
    for path in paths:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _legacy_module(v1_commit: str):
    source = _git_output("show", f"{v1_commit}:scripts/execute.py")
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".py", prefix="legacy_execute_", delete=False
    ) as file:
        file.write(source)
        module_path = Path(file.name)

    spec = importlib.util.spec_from_file_location("legacy_execute_for_eval", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("legacy execute module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        module_path.unlink(missing_ok=True)
    module.ROOT = ROOT
    return module


def _build_v1_prompt(phase: str, step: dict, step_path: Path, v1_commit: str) -> str:
    legacy = _legacy_module(v1_commit)
    executor = legacy.StepExecutor(phase)
    guardrails = executor._load_guardrails()
    index = executor._read_json(executor._index_file)
    context = executor._build_step_context(index)
    command_context = executor._load_command_context()
    preamble = executor._build_preamble(guardrails, context, command_context)
    return preamble + step_path.read_text(encoding="utf-8")


def _build_v2_prompt(phase: str, step: dict) -> str:
    executor = StepExecutor(phase)
    index = executor._read_json(executor._index_file)
    guardrails = executor._load_guardrails()
    context = executor._build_step_context(index)
    command_context = executor._load_command_context()
    return executor._build_preamble(
        guardrails,
        context,
        command_context,
        step=step,
    )


def _document_body_markers(phase: str) -> list[str]:
    phase_dir = ROOT / "phases" / phase
    paths = [ROOT / "AGENTS.md", phase_dir / "README.md"]
    for path in (ROOT / "docs").glob("*.md"):
        paths.append(path)
    markers: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                markers.append(line.strip())
                break
    return markers


def _contract_quality(prompt: str, phase: str, step: dict, step_path: Path) -> dict:
    step_text = step_path.read_text(encoding="utf-8")
    expected_paths = {
        "AGENTS.md",
        f"phases/{phase}/README.md",
        f"phases/{phase}/{step_path.name}",
        *StepExecutor._step_read_paths(step_text),
    }
    expected_commands = read_acceptance_commands(step_path)
    required_hard_constraints = ("기존 테스트", "이 step에 명시된 작업만", "index.json")
    step_definition = StepExecutor._section_text(step_text, "## 작업")
    path_ok = all(
        any(marker in prompt for marker in (f"`{path}`", path, f"/{path}"))
        for path in expected_paths
        if path != f"phases/{phase}/{step_path.name}"
    )
    step_definition_ok = not step_definition or step_definition in prompt
    commands_ok = all(command in prompt for command in expected_commands)
    constraints_ok = all(marker in prompt for marker in required_hard_constraints)
    body_markers = _document_body_markers(phase)
    body_free = not any(marker in prompt for marker in body_markers)
    return {
        "requiredPaths": sorted(expected_paths),
        "acceptanceCommandsPreserved": commands_ok,
        "hardConstraintsPreserved": constraints_ok,
        "directReadPathsPreserved": path_ok,
        "stepDefinitionPreserved": step_definition_ok,
        "documentBodiesAbsent": body_free,
        "contractQualityPass": path_ok and step_definition_ok and commands_ok and constraints_ok,
        "progressiveDisclosurePass": body_free,
    }


def _codex_version() -> str | None:
    try:
        result = subprocess.run(
            [resolve_codex_bin(), "--version"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0] or None


def evaluate(phase: str, v1_commit: str, step_number: int | None) -> dict:
    step, step_path = _load_phase_step(phase, step_number)
    v1_prompt = _build_v1_prompt(phase, step, step_path, v1_commit)
    v2_prompt = _build_v2_prompt(phase, step)
    fixture_sha = _fixture_sha256(phase)
    v1_quality = _contract_quality(v1_prompt, phase, step, step_path)
    v2_quality = _contract_quality(v2_prompt, phase, step, step_path)
    repetitions = []
    for repetition in range(1, REPETITIONS + 1):
        repetitions.extend(
            [
                {
                    "variant": "v1",
                    "scenario": "EVAL-DOCS/EVAL-CODE prompt-contract proxy",
                    "repetition": repetition,
                    "promptChars": len(v1_prompt),
                    "promptBytes": len(v1_prompt.encode("utf-8")),
                    "quality": v1_quality,
                },
                {
                    "variant": "v2",
                    "scenario": "EVAL-DOCS/EVAL-CODE prompt-contract proxy",
                    "repetition": repetition,
                    "promptChars": len(v2_prompt),
                    "promptBytes": len(v2_prompt.encode("utf-8")),
                    "quality": v2_quality,
                },
            ]
        )

    v1_bytes = len(v1_prompt.encode("utf-8"))
    v2_bytes = len(v2_prompt.encode("utf-8"))
    return {
        "scope": "prompt construction contract proxy; no Codex task was executed",
        "baseCommit": v1_commit,
        "v2Commit": _git_output("rev-parse", "HEAD"),
        "fixtureSha256": fixture_sha,
        "phase": phase,
        "step": {"step": step["step"], "name": step["name"]},
        "conditions": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "codex": _codex_version(),
            "model": "not invoked",
            "effort": "medium",
            "sandbox": "not invoked",
            "approvalPolicy": "not invoked",
            "retryLimit": StepExecutor.MAX_RETRIES,
            "setupIncluded": False,
            "cacheState": "not applicable",
            "repetitions": REPETITIONS,
        },
        "variants": {
            "v1": {
                "promptChars": len(v1_prompt),
                "promptBytes": v1_bytes,
                "quality": v1_quality,
            },
            "v2": {
                "promptChars": len(v2_prompt),
                "promptBytes": v2_bytes,
                "quality": v2_quality,
            },
        },
        "delta": {
            "promptChars": len(v2_prompt) - len(v1_prompt),
            "promptBytes": v2_bytes - v1_bytes,
            "promptBytesReductionPercent": round((v1_bytes - v2_bytes) / v1_bytes * 100, 2),
            "v2ContractQualityNoRegression": v2_quality["contractQualityPass"],
            "v2ProgressiveDisclosurePass": v2_quality["progressiveDisclosurePass"],
        },
        "repetitions": repetitions,
        "tokens": None,
        "unavailableReason": "prompt proxy does not invoke codex exec and stores no prompt text",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default=DEFAULT_PHASE)
    parser.add_argument("--v1-commit", default=DEFAULT_V1_COMMIT)
    parser.add_argument("--step", type=int, default=DEFAULT_STEP)
    args = parser.parse_args(argv)
    print(json.dumps(evaluate(args.phase, args.v1_commit, args.step), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
