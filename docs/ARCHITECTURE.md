# 아키텍처

## 시스템 개요

- Runtime/Framework: Python CLI Harness
- 주요 책임: phase task를 검증하고 Codex 구현·검증·review·PR 흐름을 안전하게
  직렬 오케스트레이션한다.
- 외부 의존성: Git, GitHub CLI, Codex CLI, 로컬 파일 시스템

## 디렉터리 구조

```text
scripts/
  codex_runner.py  # exec 기본/SDK opt-in, 정규화 결과와 bounded fallback 경계
  execute.py       # 한 task의 구현과 acceptance 재검증
  autopilot.py     # task별 PR, review, merge 직렬 루프
  worktree.py      # task worktree와 administrative marker lifecycle
  task_schema.py   # v1/v2 phase index validator와 memory view
  doctor.py        # template/instance readiness 검사
docs/
  WORKTREE_LIFECYCLE.md
  adr/0004-isolated-task-worktrees.md
phases/{phase}/
  index.json, stepN.md, README.md, docs-checks.json
```

## 모듈 경계

- `task_schema.py`: v1 `steps[]`와 v2 `tasks[]`를 검증하고 list-order 공통 memory
  view를 제공한다. DAG scheduler나 migration은 담당하지 않는다.
- `worktree.py`: Git worktree add/list/resume/remove와 Harness 소유권 marker,
  base SHA, 정리 gate를 담당한다. primary 파일과 사용자 branch를 수정하지 않는다.
- `execute.py`: 이미 선택된 task worktree에서 Codex 구현, acceptance 재검증,
  phase 상태 기록을 수행한다.
- `autopilot.py`: primary의 repository lock 안에서 base fetch, worktree 준비,
  execute subprocess, PR/review/merge, 성공 정리를 한 번에 하나씩 조정한다.
- `codex_runner.py`: `start`, `run`, `resume`, `review`, `interrupt` 공통 contract와
  비민감 정규화 결과를 제공한다. production 기본은 `codex exec`이며 Python SDK는
  명시 opt-in이다. SDK pin/capability/실행 오류는 기존 sandbox·approval·환경 정책을
  가진 exec 경로로만 recoverable fallback한다.

## 데이터 흐름

```text
phase index
  -> task_schema validation
  -> origin/<base> fetch + base SHA pin
  -> isolated task worktree + admin marker
  -> execute.py (implementation -> acceptance)
  -> PR draft -> local/scope/read-only review -> ready -> CI -> squash merge
  -> merged/clean/head/owner gate -> safe cleanup
```

실패·blocked·중단은 `worktree.py` marker와 checkout에 남아 동일 task를 재개할 수
있다. primary에서는 base branch를 checkout하거나 pull하지 않는다.

## 상태와 저장소

- 영속 상태: phase index는 프로젝트 파일, task marker는 Git administrative
  directory의 `harness-worktree.json`에 둔다.
- 임시 상태: task worktree는 primary 밖의 managed root에 둔다.
- 마이그레이션 전략: v1/v2 index와 사용자 worktree/branch는 자동 migration하지
  않는다. marker가 없는 기존 checkout은 소유권을 추측하지 않고 보존한다.

## 오류 처리

- schema/소유권/path 오류: Codex·GitHub 호출 전에 path/reason과 함께 fail-closed
  한다.
- Git/CI/review 실패: marker에 축약 진단을 남기고 task checkout을 보존한다.
- stale administrative entry 또는 dirty/ignored 파일: prune/force 없이 중단하고
  수동 확인을 요구한다.
- 재시도/복구: `error`, `blocked`, `interrupted` 상태의 같은 marker만 검증 후
  resume하며, 성공 merge 전에는 정리하지 않는다.

## 테스트 전략

- 단위 테스트: marker round-trip/atomic update, ownership, Windows·긴 경로,
  stale/dirty/기존 branch/path와 execute/autopilot 호출 경계
- 통합 테스트: 실제 임시 bare repository와 working repository에서 task 변경
  격리, primary branch 불변, 직렬 v1/v2 실행, 성공/실패 정리
- 수동 검증: `doctor.py --template`, 전체 `pytest scripts`, `compileall`,
  phase docs-check와 `git diff --check`
