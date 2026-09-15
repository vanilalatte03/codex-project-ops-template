# ADR-0006: Native review fallback과 위험도별 reviewer

## Status

Accepted

## Context

Harness의 read-only review는 `codex exec`의 구조화된 JSON 결과만 사용했다. Codex CLI가
native `review --base`를 지원하는 환경에서는 해당 surface를 우선 쓸 수 있지만, command
capability 또는 실행 실패가 기존 PR gate를 약화시키면 안 된다. 또한 모든 task에 여러
reviewer를 강제하면 저위험 변경에도 비용과 지연이 늘어난다.

## Decision

- `scripts/codex_runner.py`의 `review` contract가 native CLI review를 먼저 호출한다.
  native review의 capability 또는 실행 실패는 기존 JSON read-only `codex exec` review로
  한 번 fallback한다.
- native review와 fallback 모두 공통 core 환경 정책을 사용하고, base ref는 명시적으로
  전달한다. review 전후 worktree status 비교는 `autopilot.py`가 계속 강제한다.
- 기본 reviewer는 general 한 명이다. task metadata의 `risk`가 `high` 또는 `critical`일
  때만 high-risk specialist를 추가한다. 이 specialist는 안전 경계, 복구·idempotency,
  민감정보 처리를 추가로 점검한다.
- local checks, `git diff --check`, scope scan, 원격 CI는 모든 reviewer와 독립적인
  필수 gate로 유지한다.

## Consequences

- v1 step과 `risk`가 없거나 `low`/`medium`인 v2 task는 reviewer 한 명만 실행한다.
- SDK는 high-level native review를 제공하지 않으므로 native review 요청에서 exec
  adapter fallback을 사용한다.
- native review의 성공 출력을 구조화된 결과로 해석하지 못하면 review gate는 fail-closed
  한다. 전문 reviewer가 review 중 파일을 변경하면 PR ready 전 실패한다.
