# ADR-0001: Harness Step PR Workflow

## Status
Accepted

## Context
이 템플릿은 여러 프로젝트에 이식해 쓰는 Codex 운영 레이어다. phase 전체를 한 번에
구현하고 리뷰하면 변경 범위가 커지고, 실패 원인을 추적하기 어렵다.

## Decision
Harness 작업은 작은 step PR 단위로 운영한다.

- 단일 step 실행은 `scripts/execute.py --step N` 또는 `--next-step-only`가 담당한다.
- PR 생성, 로컬 검증, Codex read-only review, GitHub Issue 및 로컬 issue 기록,
  자동 수정 재시도, 자동 병합은 `scripts/autopilot.py`가 담당한다.
- 자동 병합은 해당 step PR의 로컬 검증과 자체 리뷰가 모두 통과한 경우에만 허용한다.
- 리뷰 실패는 같은 PR의 자체 리뷰 코멘트, GitHub Issue,
  `issues/{phase}/issue-N.md`에 함께 기록한다.
- 같은 PR 브랜치에서 최대 `--max-review-fixes`회 자동 수정과 재리뷰를 진행한다.
- 자동 수정 후에도 실패하면 PR과 Issue를 열어둔 채 루프를 중단한다.
- 자동 병합 방식은 squash merge로 고정한다.
- PR ready 후 원격 체크는 `gh pr checks --watch`로 확인하고, 체크 생성 지연은 grace
  기간 동안 재시도한다.
- 금지/허용 범위 규칙은 템플릿 스크립트가 아니라 `.codex/scope-rules.json`과
  `phases/<phase>/scope-rules.json`에 데이터로 둔다.

## Consequences
- 구현 작업은 `codex/{phase}-step{N}-{name}` 브랜치와 작은 PR 중심으로 추적된다.
- 실패 원인은 GitHub와 로컬 파일 양쪽에 남아 재시도 맥락이 보존된다.
- `gh auth status`가 유효하지 않으면 자동 PR 루프는 시작할 수 없다.
- 템플릿은 특정 도메인의 금지 키워드나 제품 규칙을 내장하지 않는다. 범위 판단은
  `AGENTS.md`, `docs/`, phase `README.md`, 현재 `stepN.md`, scope rule overlay를
  기준으로 수행한다.
