# Issue 2: Step 6 SDK caller-deadline 외부 리뷰 차단

## 상태

- Phase: `harness-v2-modernization`
- Step: `6 runner-adapter`
- GitHub Issue: `#19`
- PR: `#32`
- 분류: 외부 read-only review P1 및 재리뷰 횟수 소진
- 현재 상태: 차단 — 수정은 반영됐으나 외부 CLEAR 재검증 대기

## 현상과 수정

최종 허용 재리뷰는 SDK turn을 daemon thread에서 실행한 뒤 timeout에 interrupt와
close를 시도해도, 종료되지 않은 turn이 worktree를 계속 변경할 수 있다고 지적했다.

이를 해소하기 위해 caller deadline이 있는 SDK 실행은 시작 전에 recoverable capability
오류로 거부하고, `FallbackRunner`가 timeout을 강제할 수 있는 exec adapter로 넘기도록
변경했다. SDK의 명시적 interrupt와 close는 계속 bounded, fail-closed 처리한다.

## 리뷰 이력

- 최초 외부 review: process timeout 정규화, read-only worktree 검사, review/fix session
  분리 P1 3건을 수정했다.
- 재리뷰 1회: explicit SDK interrupt가 무기한 대기할 수 있는 P1 1건을 수정했다.
- 재리뷰 2회: SDK caller-deadline turn의 잔류 실행 P1 1건을 확인했고, 위 fallback
  경계로 로컬 수정했다.

계약상 재리뷰은 최대 2회이므로 추가 외부 재리뷰 없이 PR을 Draft로 유지한다.

## 복구 조건

사용자가 추가 외부 재리뷰 또는 동등한 독립 검증을 승인한 뒤, 고정 head에서 CLEAR를
확인한다. 그 전에는 Step 6을 완료로 표시하거나 PR을 Ready로 전환하지 않는다.

## 로컬 검증

- runner adapter targeted pytest
- 전체 `scripts` pytest
- compileall, template doctor, phase docs-check, `git diff --check`

Python PATH가 없는 환경에서는 `uv run --isolated --no-project`로 pytest를 실행한다.
