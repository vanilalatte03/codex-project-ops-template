# Review policy

## 목적

Harness PR review는 버그·범위 위반·검증 누락을 발견하는 read-only gate다. review 결과는
local checks, diff 검사, scope scan, 원격 CI를 대체하지 않는다.

## Reviewer 선택

- 모든 task는 general reviewer 한 명으로 시작한다.
- v2 task metadata의 `risk`가 `high` 또는 `critical`이면 high-risk specialist를 하나 더
  실행한다.
- `risk`가 없거나 `low`/`medium`이면 추가 reviewer를 실행하지 않는다.

## Native fallback과 불변조건

- 지원되는 Codex CLI는 `codex review --base <ref>`를 우선 사용한다.
- native command capability 또는 실행이 실패하면 구조화된 read-only `codex exec` review로
  한 번 fallback한다.
- review 전후 Git worktree status가 달라지면 결과와 무관하게 gate는 실패한다.
- review 출력이 요구 형식으로 해석되지 않으면 성공으로 추정하지 않고 fail-closed 한다.
