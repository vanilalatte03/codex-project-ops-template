# Issue 2: Step 6 runner-adapter 병합 예외와 검증 한계

## 상태

- Phase: `harness-v2-modernization`
- Step: `6 runner-adapter`
- GitHub Issue: `#19`
- PR: `#32`
- 분류: 외부 read-only review P1 수정, 재리뷰 횟수 소진, 명시적 병합 예외
- 현재 상태: 완료(병합 예외) — PR #32가 `develop`에 병합됐지만 최종 외부 CLEAR는
  확인하지 못했다.

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

계약상 재리뷰는 최대 2회이므로 당시에는 추가 외부 재리뷰 없이 PR을 Draft로
유지했다. 이후 사용자가 최종 외부 CLEAR 미확보 사실을 인지한 상태에서 PR #32의
병합을 예외로 승인했고, 병합 커밋 `19ce1b52c62b03b0d346466c39f209c230a1c464`이
`develop`에 반영됐다.

## 판정과 후속 경계

Step 6의 상태 `completed`는 위 병합 예외를 반영한 진행 상태이며, 외부 read-only
review의 CLEAR가 있었다는 뜻이 아니다. 추가 외부 재리뷰 또는 동등한 독립 검증이
필요하면 새 승인과 별도 작업으로 수행하고, 그 결과를 PR #32의 기존 검증으로
소급해 표현하지 않는다.

## 로컬 검증

- runner adapter targeted pytest
- 전체 `scripts` pytest
- compileall, template doctor, phase docs-check, `git diff --check`

Python PATH가 없는 환경에서는 `uv run --isolated --no-project`로 pytest를 실행한다.
