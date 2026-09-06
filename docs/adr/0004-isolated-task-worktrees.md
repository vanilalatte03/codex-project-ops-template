# ADR-0004: Isolated task worktree lifecycle

## Status

Accepted

## Context

`execute.py`와 `autopilot.py`의 기존 경로는 현재 checkout에서 branch를 전환하고
base를 pull한 뒤 구현·검증·review를 수행했다. 사용자의 dirty worktree를 보호하려면
task 변경을 별도 checkout에서 실행하고, 중단 후에도 같은 task를 재식별할 수 있어야
한다. 동시에 v1/v2 phase index의 list-order 직렬 실행과 기존 PR gate는 유지해야
한다.

## Decision

1. `scripts/worktree.py`에 task worktree의 생성·조회·재개·안전 정리를 분리한다.
2. Harness는 Git administrative directory의 `harness-worktree.json` marker에
   `owner`, `taskId`, phase, branch, 절대 path, `baseRef`, `baseSha`와 lifecycle
   진단을 기록한다. marker는 atomic replace하며 working tree에는 파일을 만들지
   않는다.
3. 기존 marker의 owner, task/path/branch/base가 모두 일치할 때만 재개한다. 이미
   존재하는 사용자 branch/path, marker 없는 directory, owner 불일치, stale
   administrative entry는 보존하고 명확한 충돌 또는 stale 오류로 중단한다.
4. autopilot은 primary에서 branch switch/commit/stage하지 않는다. base는
   `fetch`와 remote ref/SHA 확인으로만 동기화하고, 구현·acceptance·review·PR
   준비는 task worktree에서 수행한다.
5. 기존 `.codex/autopilot.lock`을 repository-wide concurrency 1 gate로 유지하며,
   base sync와 PR merge를 같은 직렬 critical section에서 수행한다. v1 `steps[]`와
   v2 `tasks[]`의 배열 순서 및 `dependsOn` reference-only 의미는 바꾸지 않는다.
6. PR merge 후 `merged` marker, Harness owner, clean status, expected HEAD, active
   administrative entry와 managed path를 모두 재검증한 경우에만 force 없는
   `git worktree remove`와 Harness 소유 branch의 non-force `git branch -d`를
   시도한다. 실패·blocked·중단은 marker와 checkout을 남긴다.

## Consequences

- primary checkout의 현재 branch와 변경사항을 보존하면서 task 단위 isolation과
  resume 정보를 얻는다.
- stale marker와 실패 checkout이 자동으로 사라지지 않아 수동 복구가 필요할 수
  있지만, 사용자 작업을 잃지 않고 원인을 재현할 수 있다.
- 별도 SDK, telemetry, native review adapter, DAG scheduler, ready-set 계산과
  bounded concurrency는 이 결정에 포함하지 않는다. 후속 Issue가 별도 결정한다.
- marker는 Git commit에 포함되지 않으므로 업그레이드 시 기존 phase/index와
  프로젝트 소유 branch를 자동 migration하지 않는다.

## 검증

- 실제 임시 bare/working repository를 사용해 create/list/resume/cleanup과 branch
  및 worktree isolation을 확인한다.
- Windows 경로, 잠금 파일, 긴 경로, stale administrative entry, 기존 branch/path,
  비정상 종료 후 재실행을 fixture로 검증한다.
- execute/autopilot unit test에서 primary의 branch switch/commit/stage가 없고,
  v1/v2 task가 같은 list-order로 한 번에 하나씩 task worktree에서 실행되는지
  확인한다.
